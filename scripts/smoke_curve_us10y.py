"""Smoke #1 del capítulo curva: BMA Iter3 sobre ΔUS10Y a 6m.

Mismos 4 modelos (NN_K10, NN_K20, Naive_boot, AR1) adaptados a Δyield.
Mismo pipeline Iter 3 (shrinkage α=1.0 + smoothing ρ=0.95).
Walk-forward 2020-01 a 2024-06 (deja 6m al final para realized).

Métricas:
  CRPS en pp (puntos porcentuales de yield)
  Cobertura HDI50
  Sharpness = ancho HDI50 medio en bps
  W_max para Usabilidad: 50 bps (±25 bps del centro = "interpretable")
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.producto_b.nearest_neighbors import (
    build_macro_history, find_neighbors, macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    BMAWeights, combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.curve_target import (
    model_nn_yield, model_naive_yield, model_ar1_yield, realized_yield_change,
)
from tasas_mercantil.producto_b.evaluation import (
    crps_batch, coverage_hdi, sharpness_mean,
)

YIELD_LABEL = "US10Y"
HORIZON = 6; WARMUP = 12; ALPHA = 1.0; RHO = 0.95
W_MAX_BPS = 0.50  # 50 bps = "interpretable"
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)

CACHE_DIR = Path("data/external/tasas_mercantil")


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def usability(samples, w_max, p_grid=P_GRID):
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = hdi(samples, 0.50); return 0.0, lo, hi
    return best_p, best_lo, best_hi


def main():
    yields = pd.read_parquet(CACHE_DIR / "us10y_eom.parquet")
    ys = yields.set_index("date")[yields.columns[-1]].sort_index()
    print(f"US10Y yield: {ys.index.min().date()} → {ys.index.max().date()}"
          f"  range [{ys.min():.2f}, {ys.max():.2f}]%\n")

    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))

    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 6, 30), freq="ME").date.tolist()
    fps, reals, ds = [], [], []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_yield_change(d, ys, HORIZON)
        if real is None: continue
        models = {
            "NN_K10":     model_nn_yield(target, macro_hist, ys, find_neighbors, K=10, h=HORIZON),
            "NN_K20":     model_nn_yield(target, macro_hist, ys, find_neighbors, K=20, h=HORIZON),
            "Naive_boot": model_naive_yield(d, ys, HORIZON, n_sims=1000),
            "AR1":        model_ar1_yield(d, ys, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        fps.append(models); reals.append(real); ds.append(d)
    print(f"Forecasts: {len(fps)} fechas\n")

    # Métricas individuales
    print("=== Modelos individuales ===")
    names = list(fps[0].keys())
    rows = []
    for m in names:
        sams = [fd[m].samples for fd in fps]
        cents = np.array([fd[m].center for fd in fps])
        hdis = [hdi(s, 0.5) for s in sams]
        lows = np.array([p[0] for p in hdis]); highs = np.array([p[1] for p in hdis])
        real = np.array(reals)
        rows.append({
            "model": m,
            "CRPS (pp)": round(crps_batch(sams, real), 4),
            "Cobertura HDI50": round(coverage_hdi(lows, highs, real) * 100, 1),
            "Sharpness (bps)": round(sharpness_mean(lows, highs) * 100, 1),
            "MAE (pp)": round(np.mean(np.abs(cents - real)), 4),
            "Sesgo (pp)": round(np.mean(cents - real), 4),
        })
    df_models = pd.DataFrame(rows).sort_values("CRPS (pp)")
    print(df_models.to_string(index=False))

    # BMA Iter3
    eq_w = {m: 1.0 / len(names) for m in names}
    samples_bma, centers_bma, w_prev = [], [], None
    for t, fd in enumerate(fps):
        if t < WARMUP:
            w_t = eq_w
        else:
            scores = _crps_scores_up_to(fps, reals, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else eq_w)
            w_t = apply_temporal_smoothing(bma_shrinkage(w_data, alpha=ALPHA),
                                            w_prev, rho=RHO)
        bw = BMAWeights(horizon_months=HORIZON, weights=w_t,
                        iteration=3, method="shrinkage+smoothing")
        samples_bma.append(combine_forecasts(fd, bw))
        centers_bma.append(combine_centers(fd, bw))
        w_prev = w_t

    real_arr = np.array(reals)
    centers_bma = np.array(centers_bma)
    hdis_bma = [hdi(s, 0.5) for s in samples_bma]
    lows_b = np.array([p[0] for p in hdis_bma])
    highs_b = np.array([p[1] for p in hdis_bma])
    crps_b = crps_batch(samples_bma, real_arr)
    cob_b = coverage_hdi(lows_b, highs_b, real_arr) * 100
    sharp_b = sharpness_mean(lows_b, highs_b)
    mae_b = float(np.mean(np.abs(centers_bma - real_arr)))
    print(f"\n=== BMA Iter 3 sobre ΔUS10Y ===")
    print(f"  CRPS:      {crps_b:.4f} pp")
    print(f"  Cobertura: {cob_b:.1f}%")
    print(f"  Sharpness: {sharp_b*100:.1f} bps")
    print(f"  MAE:       {mae_b:.4f} pp")

    # Baseline: Δyield_h = 0 ("no change")
    crps_zero = float(np.mean(np.abs(real_arr - 0)))
    print(f"\n=== Baseline 'sin cambio' (Δy=0) ===")
    print(f"  MAE: {crps_zero:.4f} pp")
    print(f"  Δ vs BMA MAE: {(mae_b - crps_zero)/crps_zero*100:+.1f}%  "
          f"{'(BMA mejora)' if mae_b < crps_zero else '(BMA NO mejora)'}")

    # Usabilidad
    U_vals = [usability(s, W_MAX_BPS)[0] for s in samples_bma]
    dist_U = pd.Series([int(u * 100) for u in U_vals]).value_counts().sort_index(ascending=False)
    print(f"\n=== Usabilidad (W_max = 50 bps) ===")
    for u, n in dist_U.items():
        print(f"  U={u}%: {n} meses ({100*n/len(U_vals):.1f}%)")

    # LQD derivado: dLQD ≈ -8.5 × ΔUS10Y + carry. Carry ≈ yield × h/12.
    print(f"\n=== Derivado: LQD esperado vía duration (D=8.5y) ===")
    duration = 8.5
    yield_at_t = [float(ys.loc[ys.index <= pd.Timestamp(d)].iloc[-1]) for d in ds]
    lqd_centers = np.array([-duration * c + (y / 100) * (HORIZON / 12)
                            for c, y in zip(centers_bma, yield_at_t)])
    # Realized LQD: leer del parquet de ETFs
    etf = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    lqd = etf[etf["label"] == "LQD"].copy()
    lqd["obs_date"] = pd.to_datetime(lqd["obs_date"])
    lqd = lqd.sort_values("obs_date").set_index("obs_date")
    lqd_real = []
    for d in ds:
        cut = pd.Timestamp(d); end = cut + pd.DateOffset(months=HORIZON)
        w = lqd.loc[(lqd.index > cut) & (lqd.index <= end), "return_log"].dropna()
        lqd_real.append(float(w.sum()) if len(w) >= HORIZON - 1 else np.nan)
    lqd_real = np.array(lqd_real)
    valid = ~np.isnan(lqd_real)
    corr = np.corrcoef(lqd_centers[valid], lqd_real[valid])[0, 1]
    mae_derived = float(np.mean(np.abs(lqd_centers[valid] - lqd_real[valid])))
    print(f"  Correlación predicho-real: {corr:.3f}")
    print(f"  MAE LQD derivado:          {mae_derived:.4f} log-ret")

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(13, 8))
    dts = pd.to_datetime(ds)

    ax = axes[0]
    ax.fill_between(dts, lows_b, highs_b, color="#3498db", alpha=0.3,
                    label="HDI 50% BMA")
    ax.plot(dts, centers_bma, color="#2c3e50", lw=1.5, label="Centro BMA")
    ax.plot(dts, real_arr, "o-", color="#c0392b", markersize=4,
            label="ΔUS10Y realizado (6m)")
    ax.axhline(0, color="grey", lw=0.7)
    ax.set_ylabel("ΔUS10Y (pp) a 6m")
    ax.set_title(f"BMA Iter 3 sobre ΔUS10Y_6m — {len(ds)} fechas, "
                 f"CRPS={crps_b:.3f}pp Cob={cob_b:.0f}% Sharp={sharp_b*100:.0f}bps")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(dts[valid], lqd_real[valid], "o-", color="#c0392b", lw=1.2,
            label="LQD realizado")
    ax.plot(dts[valid], lqd_centers[valid], "s--", color="#27ae60", lw=1.2,
            label="LQD derivado de ΔUS10Y")
    ax.axhline(0, color="grey", lw=0.7); ax.set_ylabel("Retorno LQD 6m")
    ax.set_title(f"LQD derivado vs realizado (correlación = {corr:.2f}, "
                 f"MAE = {mae_derived:.3f})")
    ax.legend(); ax.grid(alpha=0.3)

    fig.tight_layout()
    out = CACHE_DIR / "bma_curve_us10y_smoke.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
