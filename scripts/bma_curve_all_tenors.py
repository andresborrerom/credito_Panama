"""Experimento curva completa: BMA Iter 3 sobre Δyield_6m para 4 plazos
(US1Y, US2Y, US5Y, US10Y).

Hipótesis científica:
  H0 (nulo): el BMA no mejora al baseline trivial 'Δyield=0' en NINGÚN plazo.
  H1: existe al menos un plazo donde BMA gana al baseline con margen
      material (≥10% de Δ MAE) y cobertura HDI50 dentro de banda 45-55%.

Diseño:
  - Mismos 4 modelos: NN_K10, NN_K20, Naive_boot, AR1.
  - Mismo pipeline Iter 3 (shrinkage α=1.0 + smoothing ρ=0.95).
  - Walk-forward 2020-01 a 2024-06 (H=6m → deja 6m al final).
  - Métricas por plazo: CRPS, MAE_BMA vs MAE_baseline, cobertura HDI50,
    sharpness (bps), sesgo, vol realizada, fracción U=0 con W_max=50bps.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.data.ingest_eodhd import fetch_etf_history
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

HORIZON = 6; WARMUP = 12; ALPHA = 1.0; RHO = 0.95
W_MAX_BPS = 0.50
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)

CACHE_DIR = Path("data/external/tasas_mercantil")

TENORS = [
    ("US1Y",  CACHE_DIR / "us1y_eom.parquet"),
    ("US2Y",  CACHE_DIR / "us2y_eom.parquet"),
    ("US5Y",  CACHE_DIR / "us5y_eom.parquet"),
    ("US10Y", CACHE_DIR / "us10y_eom.parquet"),
]


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def usability(samples, w_max, p_grid=P_GRID):
    best = 0.0
    for p in sorted(p_grid):
        lo, hi = hdi(samples, p)
        if (hi - lo) <= w_max: best = p
    return best


def load_yield(tenor, cache_path):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")[df.columns[-1]].sort_index()
    print(f"  Descargando {tenor}.INDX ...")
    df = fetch_etf_history(f"{tenor}.INDX", period="d",
                           start=date(2010, 1, 1), end=date(2025, 6, 30))
    df["date"] = pd.to_datetime(df["obs_date"])
    s = df.set_index("date")["close"].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s.index, tenor: s.values})
    out.to_parquet(cache_path, index=False)
    return s


def run_bma_for_tenor(tenor, ys, store, macro_hist):
    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 6, 30), freq="ME").date.tolist()
    fps, reals, ds = [], [], []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_yield_change(d, ys, HORIZON)
        if real is None: continue
        models = {
            "NN_K10":     model_nn_yield(target, macro_hist, ys, find_neighbors,
                                          K=10, h=HORIZON),
            "NN_K20":     model_nn_yield(target, macro_hist, ys, find_neighbors,
                                          K=20, h=HORIZON),
            "Naive_boot": model_naive_yield(d, ys, HORIZON, n_sims=1000),
            "AR1":        model_ar1_yield(d, ys, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        fps.append(models); reals.append(real); ds.append(d)

    names = list(fps[0].keys()); eq_w = {m: 1.0 / len(names) for m in names}
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
    centers = np.array(centers_bma)
    hdis = [hdi(s, 0.5) for s in samples_bma]
    lows = np.array([p[0] for p in hdis]); highs = np.array([p[1] for p in hdis])
    U_zero_frac = float(np.mean([usability(s, W_MAX_BPS) == 0
                                  for s in samples_bma]))
    metrics = {
        "tenor": tenor, "n": len(reals),
        "CRPS_BMA": crps_batch(samples_bma, real_arr),
        "MAE_BMA": float(np.mean(np.abs(centers - real_arr))),
        "MAE_baseline_zero": float(np.mean(np.abs(real_arr - 0))),
        "Cobertura HDI50 (%)": coverage_hdi(lows, highs, real_arr) * 100,
        "Sharpness (bps)": sharpness_mean(lows, highs) * 100,
        "Sesgo (pp)": float(np.mean(centers - real_arr)),
        "Vol realizada (pp)": float(np.std(real_arr, ddof=1)),
        "Mean realizado (pp)": float(np.mean(real_arr)),
        "Frac U=0 (%)": U_zero_frac * 100,
    }
    metrics["Δ MAE vs baseline (%)"] = (
        (metrics["MAE_BMA"] - metrics["MAE_baseline_zero"])
        / metrics["MAE_baseline_zero"] * 100
    )
    return metrics, ds, real_arr, centers, lows, highs


def main():
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))

    series = {tenor: load_yield(tenor, cache) for tenor, cache in TENORS}

    all_metrics = []
    series_for_plot = {}
    for tenor, _ in TENORS:
        print(f"=== Plazo {tenor} ===")
        m, ds, real, centers, lows, highs = run_bma_for_tenor(
            tenor, series[tenor], store, macro_hist
        )
        all_metrics.append(m)
        series_for_plot[tenor] = {"ds": ds, "real": real, "centers": centers,
                                   "lows": lows, "highs": highs}
        print(f"  n={m['n']}, MAE_BMA={m['MAE_BMA']:.4f}, "
              f"baseline={m['MAE_baseline_zero']:.4f}, "
              f"Δ={m['Δ MAE vs baseline (%)']:+.1f}%")

    df = pd.DataFrame(all_metrics)
    cols_show = [
        "tenor", "n", "CRPS_BMA", "MAE_BMA", "MAE_baseline_zero",
        "Δ MAE vs baseline (%)", "Cobertura HDI50 (%)",
        "Sharpness (bps)", "Sesgo (pp)", "Vol realizada (pp)",
        "Mean realizado (pp)", "Frac U=0 (%)",
    ]
    df_disp = df[cols_show].copy()
    for c in ["CRPS_BMA", "MAE_BMA", "MAE_baseline_zero", "Sesgo (pp)",
              "Vol realizada (pp)", "Mean realizado (pp)"]:
        df_disp[c] = df_disp[c].round(4)
    for c in ["Δ MAE vs baseline (%)", "Cobertura HDI50 (%)",
              "Sharpness (bps)", "Frac U=0 (%)"]:
        df_disp[c] = df_disp[c].round(1)

    print(f"\n=== Resumen comparativo por plazo ===")
    print(df_disp.to_string(index=False))

    # Plot: 4 paneles, uno por tenor
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    for ax, (tenor, _) in zip(axes.flat, TENORS):
        sp = series_for_plot[tenor]
        dts = pd.to_datetime(sp["ds"])
        ax.fill_between(dts, sp["lows"], sp["highs"], color="#3498db",
                        alpha=0.3, label="HDI 50%")
        ax.plot(dts, sp["centers"], color="#2c3e50", lw=1.4, label="Centro BMA")
        ax.plot(dts, sp["real"], "o-", color="#c0392b", markersize=4,
                label="Δyield realizado")
        ax.axhline(0, color="grey", lw=0.7)
        m = next(x for x in all_metrics if x["tenor"] == tenor)
        ax.set_title(
            f"{tenor} — n={m['n']}, MAE Δ vs baseline={m['Δ MAE vs baseline (%)']:+.1f}%, "
            f"Cob={m['Cobertura HDI50 (%)']:.0f}%, U=0 {m['Frac U=0 (%)']:.0f}% meses"
        )
        ax.set_ylabel(f"Δ{tenor} (pp) a 6m"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.suptitle("BMA sobre Δyield_6m por plazo Treasury",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = CACHE_DIR / "bma_curve_all_tenors.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    df.to_parquet(CACHE_DIR / "bma_curve_all_tenors.parquet", index=False)

    # Veredicto por plazo
    print(f"\n=== Veredicto por plazo (H1: Δ MAE ≤ -10% Y Cob en [45, 55]) ===")
    for m in all_metrics:
        c1 = m["Δ MAE vs baseline (%)"] <= -10
        c2 = 45 <= m["Cobertura HDI50 (%)"] <= 55
        v = "PASS" if (c1 and c2) else ("PARCIAL" if (c1 or c2) else "FAIL")
        print(f"  {m['tenor']:>6}: Δ MAE {m['Δ MAE vs baseline (%)']:+5.1f}% "
              f"({'OK' if c1 else 'no'}), Cob {m['Cobertura HDI50 (%)']:.1f}% "
              f"({'OK' if c2 else 'no'})  →  {v}")

    print(f"\n[OK] {out}")
    print(f"[OK] {CACHE_DIR / 'bma_curve_all_tenors.parquet'}")


if __name__ == "__main__":
    main()
