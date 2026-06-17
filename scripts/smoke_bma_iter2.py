"""Smoke test BMA Iter 2: shrinkage Bayesiano con α calibrado por walk-forward.

Gate Iter 2:
  CRPS(Iter 2) ≤ CRPS(Iter 1) por al menos algún margen.
  Si no mejora, no vale la pena la complejidad → quedarse con equal.

Calibración honesta:
  α se elige minimizando CRPS in-sample expansivo (causal, sin look-ahead).
  Cada t > warmup usa log scores acumulados de fechas s < t.
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
)
from tasas_mercantil.producto_b.evaluation import (
    crps_batch, coverage_hdi, sharpness_mean, bias,
)


ETF_LABEL = "LQD"
HORIZON = 6


def _hdi(samples, mass=0.50):
    s = np.sort(samples); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def model_nn(target_state, macro_hist, etf_ret, K, h, exclude_w=7):
    nr = find_neighbors(target_state, macro_hist, K=K, exclude_window_months=exclude_w)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(), etf_ret, h, ETF_LABEL)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target_state.as_of,
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


def metrics_from_df(df, model_name):
    real = df["real"].values
    centers = df["ensemble_center"].values
    lows = df["ensemble_hdi_low"].values
    highs = df["ensemble_hdi_high"].values
    return {
        "model": model_name,
        "n": len(real),
        "CRPS": None,  # se computa aparte porque necesita samples
        "Cobertura HDI50 (%)": round(coverage_hdi(lows, highs, real) * 100, 1),
        "Sharpness": round(sharpness_mean(lows, highs), 4),
        "Sesgo": round(bias(centers, real), 4),
        "MAE": round(np.mean(np.abs(centers - real)), 4),
    }


def main():
    print(f"=== Smoke test BMA Iter 2 (shrinkage) — {ETF_LABEL} h={HORIZON} ===\n")
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")

    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    print(f"test_dates: {len(test_dates)} ({test_dates[0]} → {test_dates[-1]})")

    # Construir forecasts
    forecasts_per_date = []
    realized_list = []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None: continue
        m1 = model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON)
        m2 = model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON)
        m3 = model_naive(d, etf_ret, HORIZON)
        if any(m is None for m in [m1, m2, m3]): continue
        forecasts_per_date.append({"NN_K10": m1, "NN_K20": m2, "Naive_boot": m3})
        realized_list.append(real)
    print(f"Forecasts: {len(forecasts_per_date)}\n")

    # Paso 1: calibrar α — primero con score epsilon (legacy), después con CRPS
    print("=== Calibración α — score=epsilon (legacy) ===")
    alpha_eps, df_alpha_eps = calibrate_alpha_walkforward(
        forecasts_per_date, realized_list,
        alpha_grid=(0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0), warmup=12,
        score_method="epsilon",
    )
    print(df_alpha_eps.to_string(index=False))
    print(f"  α* eps = {alpha_eps:.2f}\n")

    print("=== Calibración α — score=CRPS histórico (recomendado) ===")
    alpha_opt, df_alpha = calibrate_alpha_walkforward(
        forecasts_per_date, realized_list,
        alpha_grid=(0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0), warmup=12,
        score_method="crps", temperature=50.0,
    )
    print(df_alpha.to_string(index=False))
    print(f"\n  α* (CRPS min) = {alpha_opt:.2f}")

    # Paso 2: walk-forward Iter 1 (equal) e Iter 2 (shrinkage con α*)
    df_iter1 = walk_forward_bma_equal(forecasts_per_date, realized_list)
    df_iter2 = walk_forward_bma_shrinkage(forecasts_per_date, realized_list,
                                          alpha=alpha_opt, warmup=12,
                                          score_method="crps", temperature=50.0)

    # CRPS necesita samples → reconstruir ensemble samples
    weights_eq = bma_equal_weights(["NN_K10", "NN_K20", "Naive_boot"], HORIZON)
    samples_iter1 = [combine_forecasts(fd, weights_eq) for fd in forecasts_per_date]
    # Para iter 2, reconstruir samples con weights dinámicos (CRPS-based):
    from tasas_mercantil.producto_b.bma import (
        _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage, BMAWeights,
    )
    samples_iter2 = []
    model_names = list(forecasts_per_date[0].keys())
    for t, fd in enumerate(forecasts_per_date):
        if t < 12:
            bw = weights_eq
        else:
            scores = _crps_scores_up_to(forecasts_per_date, realized_list, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else {m: 1.0 / len(model_names) for m in model_names})
            w_shrunk = bma_shrinkage(w_data, alpha=alpha_opt)
            bw = BMAWeights(horizon_months=HORIZON, weights=w_shrunk,
                            iteration=2, method="shrinkage")
        samples_iter2.append(combine_forecasts(fd, bw))

    real_arr = np.array(realized_list)
    crps_iter1 = crps_batch(samples_iter1, real_arr)
    crps_iter2 = crps_batch(samples_iter2, real_arr)

    m1 = metrics_from_df(df_iter1, "BMA_equal (Iter 1)")
    m1["CRPS"] = round(crps_iter1, 5)
    m2 = metrics_from_df(df_iter2, f"BMA_shrink α={alpha_opt:.2f} (Iter 2)")
    m2["CRPS"] = round(crps_iter2, 5)

    print("\n=== Comparación Iter 1 vs Iter 2 ===")
    print(pd.DataFrame([m1, m2]).to_string(index=False))

    # Pesos efectivos al final del walk-forward
    print(f"\n=== Pesos Iter 2 al final ({df_iter2.iloc[-1]['as_of']}) ===")
    final = df_iter2.iloc[-1]
    for col in [c for c in df_iter2.columns if c.startswith("w_")]:
        print(f"  {col}: {final[col]:.3f}")

    # Gate Iter 2
    print(f"\n=== Gate Iter 2 ===")
    delta_pct = (crps_iter1 - crps_iter2) / crps_iter1 * 100
    print(f"  CRPS Iter 1: {crps_iter1:.5f}")
    print(f"  CRPS Iter 2: {crps_iter2:.5f}")
    print(f"  Mejora vs Iter 1: {delta_pct:+.2f}%")
    if delta_pct >= 5.0:
        print(f"  [PASS] Iter 2 mejora ≥5% — vale la complejidad.")
    elif delta_pct > 0:
        print(f"  [MARGINAL] Iter 2 mejora pero <5%. Posible mantenerse en equal.")
    else:
        print(f"  [FAIL] Iter 2 NO mejora — quedarse con equal weights.")

    # Guardar
    out = Path("data/external/tasas_mercantil/bma_iter2_smoke.parquet")
    pd.DataFrame([m1, m2]).to_parquet(out, index=False)
    df_iter2.to_parquet(
        Path("data/external/tasas_mercantil/bma_iter2_walk_forward.parquet"),
        index=False,
    )
    df_alpha.to_parquet(
        Path("data/external/tasas_mercantil/bma_iter2_alpha_grid.parquet"),
        index=False,
    )
    print(f"\n[OK] guardado: {out} + walk_forward + alpha_grid")


if __name__ == "__main__":
    main()
