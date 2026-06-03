"""Smoke test BMA Iter 2 con 5 modelos diversos.

Modelos:
  NN_K10, NN_K20 — pattern matching macro state.
  Naive_boot    — bootstrap del último año (asume estacionariedad).
  AR1           — autorregresión orden 1 de log returns.
  Drift_vol     — random walk con drift histórico 36m.

Gate Iter 2: con 5 modelos diversos, esperamos que shrinkage tenga más espacio
para encontrar diversificación real. Si CRPS Iter 2 ≥5% mejor que Iter 1, pasa.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.producto_b.nearest_neighbors import (
    build_macro_history, find_neighbors, compute_forward_returns, macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    ModelForecast,
    bma_equal_weights, combine_forecasts, combine_centers,
    walk_forward_bma_equal,
    calibrate_alpha_walkforward, walk_forward_bma_shrinkage,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage, BMAWeights,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1, model_drift_vol
from tasas_mercantil.producto_b.evaluation import (
    crps_batch, crps_sample, coverage_hdi, sharpness_mean, bias,
)


ETF_LABEL = "LQD"
HORIZON = 6
WARMUP = 12
ALPHA_GRID = (0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)


def _hdi(s, mass=0.50):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def model_nn(target, macro_hist, etf_ret, K, h, exclude_w=7):
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=exclude_w)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(), etf_ret, h, ETF_LABEL)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target.as_of,
                         horizon_months=h, samples=fwd, center=float(np.median(fwd)))


def model_naive(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub[sub.index <= cut]["return_log"].dropna()
    if len(history) < 12: return None
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=h, replace=True).sum() for _ in range(500)])
    return ModelForecast(model_name="Naive_boot", as_of=as_of,
                         horizon_months=h, samples=sims, center=float(np.median(sims)))


def realized_return(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    if len(window) < max(1, h - 1): return None
    return float(window.sum())


def eval_individual(model_name, forecasts, realized):
    samples = [f.samples for f in forecasts]
    centers = np.array([f.center for f in forecasts])
    hdi_pairs = [_hdi(f.samples, 0.50) for f in forecasts]
    lows = np.array([p[0] for p in hdi_pairs])
    highs = np.array([p[1] for p in hdi_pairs])
    real = np.array(realized)
    return {
        "model": model_name,
        "n": len(real),
        "CRPS": round(crps_batch(samples, real), 5),
        "Cobertura HDI50": round(coverage_hdi(lows, highs, real) * 100, 1),
        "Sharpness": round(sharpness_mean(lows, highs), 4),
        "Sesgo": round(bias(centers, real), 4),
        "MAE": round(np.mean(np.abs(centers - real)), 4),
    }


def main():
    print(f"=== Smoke BMA Iter 2 extended — {ETF_LABEL} h={HORIZON} ===\n")
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")

    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    print(f"test_dates: {len(test_dates)}")

    forecasts_per_date = []
    realized_list = []
    skipped = 0
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: skipped += 1; continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None: skipped += 1; continue
        models = {
            "NN_K10":     model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON),
            "NN_K20":     model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON),
            "Naive_boot": model_naive(d, etf_ret, HORIZON),
            "AR1":        model_ar1(d, etf_ret, ETF_LABEL, HORIZON, n_sims=1000),
            "Drift_vol":  model_drift_vol(d, etf_ret, ETF_LABEL, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): skipped += 1; continue
        forecasts_per_date.append(models)
        realized_list.append(real)
    print(f"Forecasts construidos: {len(forecasts_per_date)} (saltados {skipped})\n")

    model_names = list(forecasts_per_date[0].keys())

    # Métricas modelos individuales
    print("=== Modelos individuales ===")
    rows = []
    for m in model_names:
        fs = [d[m] for d in forecasts_per_date]
        rows.append(eval_individual(m, fs, realized_list))
    df_models = pd.DataFrame(rows).sort_values("CRPS").reset_index(drop=True)
    print(df_models.to_string(index=False))

    # Iter 1: equal
    weights_eq = bma_equal_weights(model_names, HORIZON)
    samples_iter1 = [combine_forecasts(fd, weights_eq) for fd in forecasts_per_date]
    centers_iter1 = np.array([combine_centers(fd, weights_eq) for fd in forecasts_per_date])
    hdi_iter1 = [_hdi(s, 0.50) for s in samples_iter1]
    lows1 = np.array([p[0] for p in hdi_iter1]); highs1 = np.array([p[1] for p in hdi_iter1])
    real_arr = np.array(realized_list)
    m_iter1 = {
        "model": "BMA equal (Iter 1)", "n": len(real_arr),
        "CRPS": round(crps_batch(samples_iter1, real_arr), 5),
        "Cobertura HDI50": round(coverage_hdi(lows1, highs1, real_arr) * 100, 1),
        "Sharpness": round(sharpness_mean(lows1, highs1), 4),
        "Sesgo": round(bias(centers_iter1, real_arr), 4),
        "MAE": round(np.mean(np.abs(centers_iter1 - real_arr)), 4),
    }

    # Calibración α por walk-forward causal (CRPS-based)
    print("\n=== Calibración α (score=CRPS, warmup=12) ===")
    alpha_opt, df_alpha = calibrate_alpha_walkforward(
        forecasts_per_date, realized_list,
        alpha_grid=ALPHA_GRID, warmup=WARMUP,
        score_method="crps", temperature=50.0,
    )
    print(df_alpha.to_string(index=False))
    print(f"\n  α* = {alpha_opt:.2f}")

    # Iter 2: shrinkage con α*
    samples_iter2 = []
    centers_iter2 = []
    pesos_t_final = None
    for t, fd in enumerate(forecasts_per_date):
        if t < WARMUP:
            bw = weights_eq
        else:
            scores = _crps_scores_up_to(forecasts_per_date, realized_list, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else {m: 1.0 / len(model_names) for m in model_names})
            w_shrunk = bma_shrinkage(w_data, alpha=alpha_opt)
            bw = BMAWeights(horizon_months=HORIZON, weights=w_shrunk,
                            iteration=2, method="shrinkage")
        samples_iter2.append(combine_forecasts(fd, bw))
        centers_iter2.append(combine_centers(fd, bw))
        if t == len(forecasts_per_date) - 1:
            pesos_t_final = bw.weights

    centers_iter2 = np.array(centers_iter2)
    hdi_iter2 = [_hdi(s, 0.50) for s in samples_iter2]
    lows2 = np.array([p[0] for p in hdi_iter2]); highs2 = np.array([p[1] for p in hdi_iter2])
    m_iter2 = {
        "model": f"BMA shrink α={alpha_opt:.2f} (Iter 2)", "n": len(real_arr),
        "CRPS": round(crps_batch(samples_iter2, real_arr), 5),
        "Cobertura HDI50": round(coverage_hdi(lows2, highs2, real_arr) * 100, 1),
        "Sharpness": round(sharpness_mean(lows2, highs2), 4),
        "Sesgo": round(bias(centers_iter2, real_arr), 4),
        "MAE": round(np.mean(np.abs(centers_iter2 - real_arr)), 4),
    }

    # Comparación final
    print("\n=== Comparación final ===")
    df_final = pd.concat([df_models, pd.DataFrame([m_iter1, m_iter2])],
                         ignore_index=True)
    print(df_final.to_string(index=False))

    print(f"\n=== Pesos Iter 2 finales ({forecasts_per_date[-1]['NN_K10'].as_of}) ===")
    for m, w in sorted(pesos_t_final.items(), key=lambda kv: -kv[1]):
        print(f"  {m:>12}: {w:.3f}")

    # Gate
    best_indiv_crps = df_models["CRPS"].min()
    print(f"\n=== Gate Iter 2 ===")
    print(f"  Best individual CRPS:    {best_indiv_crps:.5f}")
    print(f"  BMA equal (Iter 1) CRPS: {m_iter1['CRPS']:.5f}")
    print(f"  BMA shrink (Iter 2) CRPS: {m_iter2['CRPS']:.5f}")
    delta1 = (m_iter1["CRPS"] - best_indiv_crps) / best_indiv_crps * 100
    delta2_vs_eq = (m_iter1["CRPS"] - m_iter2["CRPS"]) / m_iter1["CRPS"] * 100
    delta2_vs_best = (best_indiv_crps - m_iter2["CRPS"]) / best_indiv_crps * 100
    print(f"  Δ Iter1 vs best indiv:   {delta1:+.2f}%")
    print(f"  Δ Iter2 vs Iter1:        {delta2_vs_eq:+.2f}%")
    print(f"  Δ Iter2 vs best indiv:   {delta2_vs_best:+.2f}%")
    if delta2_vs_eq >= 5:
        print(f"  [PASS] Iter 2 mejora ≥5% sobre Iter 1.")
    elif delta2_vs_eq > 0:
        print(f"  [MARGINAL] Iter 2 mejora pero <5%.")
    else:
        print(f"  [FAIL] Iter 2 NO mejora.")

    # Guardar
    out = Path("data/external/tasas_mercantil/bma_iter2_ext.parquet")
    df_final.to_parquet(out, index=False)
    df_alpha.to_parquet(
        Path("data/external/tasas_mercantil/bma_iter2_ext_alpha_grid.parquet"),
        index=False,
    )
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
