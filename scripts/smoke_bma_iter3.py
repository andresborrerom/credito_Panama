"""Smoke BMA Iter 3 — temporal smoothing.

Aplica ρ smoothing sobre los pesos shrunk de Iter 2 (α* = 1.0 fijado).
  w_final(t) = ρ · w_final(t-1) + (1-ρ) · w_shrunk(t)

Métrica de evaluación:
  - CRPS (debe no empeorar significativamente).
  - Turnover: mean L1 distance ‖w(t) - w(t-1)‖₁ / 2 ∈ [0, 1].
    (0 = pesos constantes, 1 = cambio total).

Gate Iter 3:
  - CRPS Iter 3 ≤ CRPS Iter 2 + 2% (margen de tolerancia).
  - Turnover Iter 3 ≤ 50% del turnover Iter 2.

Si pasa: el smoothing estabiliza pesos sin coste predictivo.
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
    ModelForecast, BMAWeights,
    bma_equal_weights, combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1, model_drift_vol
from tasas_mercantil.producto_b.evaluation import (
    crps_batch, coverage_hdi, sharpness_mean, bias,
)


ETF_LABEL = "LQD"
HORIZON = 6
WARMUP = 12
ALPHA_STAR = 1.0  # de Iter 2
RHO_GRID = (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95)


def _hdi(s, mass=0.50):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def model_nn(target, macro_hist, etf_ret, K, h):
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=7)
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


def compute_turnover(weight_series: list[dict[str, float]]) -> float:
    """Mean ‖w(t) - w(t-1)‖₁ / 2."""
    if len(weight_series) < 2: return 0.0
    diffs = []
    for i in range(1, len(weight_series)):
        prev = weight_series[i - 1]; cur = weight_series[i]
        keys = set(prev) | set(cur)
        d = sum(abs(cur.get(k, 0) - prev.get(k, 0)) for k in keys) / 2
        diffs.append(d)
    return float(np.mean(diffs))


def evaluate_rho(rho, forecasts_per_date, realized_list, model_names):
    """Aplica smoothing con ρ y devuelve métricas + serie de pesos."""
    samples_seq = []
    centers_seq = []
    weights_seq = []
    w_prev = None
    eq_w = {m: 1.0 / len(model_names) for m in model_names}
    for t, fd in enumerate(forecasts_per_date):
        if t < WARMUP:
            w_t = eq_w
        else:
            scores = _crps_scores_up_to(forecasts_per_date, realized_list, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else eq_w)
            w_shrunk = bma_shrinkage(w_data, alpha=ALPHA_STAR)
            w_t = apply_temporal_smoothing(w_shrunk, w_prev, rho=rho)
        bw = BMAWeights(horizon_months=HORIZON, weights=w_t,
                        iteration=3, method="shrinkage+smoothing")
        samples_seq.append(combine_forecasts(fd, bw))
        centers_seq.append(combine_centers(fd, bw))
        weights_seq.append(w_t)
        w_prev = w_t
    centers = np.array(centers_seq)
    hdi_pairs = [_hdi(s, 0.50) for s in samples_seq]
    lows = np.array([p[0] for p in hdi_pairs])
    highs = np.array([p[1] for p in hdi_pairs])
    real = np.array(realized_list)
    # Turnover sobre fase post-warmup
    turnover = compute_turnover(weights_seq[WARMUP:])
    return {
        "rho": rho,
        "CRPS": crps_batch(samples_seq, real),
        "Cobertura HDI50": coverage_hdi(lows, highs, real) * 100,
        "Sharpness": sharpness_mean(lows, highs),
        "Sesgo": bias(centers, real),
        "MAE": float(np.mean(np.abs(centers - real))),
        "Turnover": turnover,
    }, weights_seq


def main():
    print(f"=== Smoke BMA Iter 3 (temporal smoothing) — {ETF_LABEL} h={HORIZON} ===\n")
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")

    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    forecasts_per_date = []
    realized_list = []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None: continue
        models = {
            "NN_K10":     model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON),
            "NN_K20":     model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON),
            "Naive_boot": model_naive(d, etf_ret, HORIZON),
            "AR1":        model_ar1(d, etf_ret, ETF_LABEL, HORIZON, n_sims=1000),
            "Drift_vol":  model_drift_vol(d, etf_ret, ETF_LABEL, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        forecasts_per_date.append(models)
        realized_list.append(real)
    print(f"Forecasts construidos: {len(forecasts_per_date)}\n")
    model_names = list(forecasts_per_date[0].keys())

    # Grid ρ
    print(f"=== Grid ρ (α*={ALPHA_STAR}) ===")
    rows = []
    weights_series_by_rho = {}
    for rho in RHO_GRID:
        m, ws = evaluate_rho(rho, forecasts_per_date, realized_list, model_names)
        rows.append(m)
        weights_series_by_rho[rho] = ws
    df = pd.DataFrame(rows)
    df_disp = df.copy()
    for c in ["CRPS", "Sharpness", "Sesgo", "MAE", "Turnover"]:
        df_disp[c] = df_disp[c].round(5)
    df_disp["Cobertura HDI50"] = df_disp["Cobertura HDI50"].round(1)
    print(df_disp.to_string(index=False))

    # Baseline ρ=0 = Iter 2 puro
    base = df[df["rho"] == 0.0].iloc[0]
    base_crps = base["CRPS"]; base_turnover = base["Turnover"]
    print(f"\nBaseline (ρ=0 ≡ Iter 2): CRPS={base_crps:.5f}, Turnover={base_turnover:.4f}")

    # Buscar mejor ρ: min CRPS sujeto a turnover ≤ 0.5 × base
    candidates = df[df["Turnover"] <= 0.5 * base_turnover]
    if len(candidates) > 0:
        rho_star = candidates.sort_values("CRPS").iloc[0]
        method = "min CRPS s.a. turnover ≤ 50% base"
    else:
        rho_star = df.sort_values("CRPS").iloc[0]
        method = "min CRPS (sin restricción de turnover viable)"
    print(f"\nρ* = {rho_star['rho']:.2f}  [{method}]")

    # Comparación final
    delta_crps = (rho_star["CRPS"] - base_crps) / base_crps * 100
    delta_turnover = (rho_star["Turnover"] - base_turnover) / base_turnover * 100
    print(f"  Δ CRPS:     {delta_crps:+.2f}%")
    print(f"  Δ Turnover: {delta_turnover:+.2f}%")

    print(f"\n=== Pesos finales (último t, ρ*={rho_star['rho']}) ===")
    final_w = weights_series_by_rho[rho_star["rho"]][-1]
    for m, w in sorted(final_w.items(), key=lambda kv: -kv[1]):
        print(f"  {m:>12}: {w:.3f}")

    # Gate
    print(f"\n=== Gate Iter 3 ===")
    cond_crps = delta_crps <= 2.0
    cond_turn = delta_turnover <= -50.0
    print(f"  Cond CRPS (Δ ≤ +2%):       Δ={delta_crps:+.2f}%   {'PASS' if cond_crps else 'FAIL'}")
    print(f"  Cond Turnover (Δ ≤ -50%):  Δ={delta_turnover:+.2f}%   {'PASS' if cond_turn else 'FAIL'}")
    if cond_crps and cond_turn:
        print(f"  [PASS] Iter 3 estabiliza pesos sin coste predictivo.")
    elif cond_crps and not cond_turn:
        print(f"  [PARTIAL] CRPS preservado pero turnover no reducido lo suficiente.")
    elif not cond_crps and cond_turn:
        print(f"  [FAIL] Smoothing penaliza CRPS por más del margen.")
    else:
        print(f"  [FAIL] Ni CRPS ni turnover mejoran.")

    out = Path("data/external/tasas_mercantil/bma_iter3_grid.parquet")
    df.to_parquet(out, index=False)
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
