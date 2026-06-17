"""Ejemplo concreto: reproducir el forecast BMA para una fecha específica
mostrando las nubes de los 5 modelos, la nube combinada, y cómo se calculan
las métricas para ESE punto.

Fecha elegida: as_of = 2022-03-31 → horizonte = 6 meses → ventana abril-sept 2022.
Período: subida agresiva de Fed (Mar 0.5% → Sep 3.25%) → LQD cayó fuerte.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.producto_b.nearest_neighbors import (
    build_macro_history, find_neighbors, compute_forward_returns, macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    ModelForecast, BMAWeights,
    combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1, model_drift_vol

ETF = "LQD"
HORIZON = 6
WARMUP = 12
ALPHA = 1.0
RHO = 0.95
AS_OF_EJEMPLO = date(2022, 3, 31)


def _hdi(s, mass=0.5):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def crps_sample_vs_obs(samples, y):
    """CRPS empírico para una nube vs un solo valor observado."""
    samples = np.asarray(samples); n = len(samples)
    term1 = np.mean(np.abs(samples - y))
    # E|X - X'| por sort trick
    s = np.sort(samples)
    term2 = (2.0 / (n * n)) * np.sum((2 * np.arange(1, n + 1) - n - 1) * s)
    return float(term1 - 0.5 * term2)


def model_nn(target, macro_hist, etf_ret, K, h):
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=7)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(), etf_ret, h, ETF)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target.as_of,
                         horizon_months=h, samples=fwd, center=float(np.median(fwd)))


def model_naive(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub[sub.index <= cut]["return_log"].dropna()
    if len(history) < 12: return None
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=h, replace=True).sum() for _ in range(1000)])
    return ModelForecast(model_name="Naive_boot", as_of=as_of,
                         horizon_months=h, samples=sims, center=float(np.median(sims)))


def realized_return(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    if len(window) < max(1, h - 1): return None
    return float(window.sum())


def build_all_forecasts():
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")
    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    forecasts_per_date, realized_list, dates_used = [], [], []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None: continue
        models = {
            "NN_K10":     model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON),
            "NN_K20":     model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON),
            "Naive_boot": model_naive(d, etf_ret, HORIZON),
            "AR1":        model_ar1(d, etf_ret, ETF, HORIZON, n_sims=1000),
            "Drift_vol":  model_drift_vol(d, etf_ret, ETF, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        forecasts_per_date.append(models)
        realized_list.append(real)
        dates_used.append(d)
    return forecasts_per_date, realized_list, dates_used


def run_iter3_with_records(forecasts_per_date, realized_list, dates_used):
    """Walk-forward Iter 3 grabando combined samples + pesos para cada fecha."""
    model_names = list(forecasts_per_date[0].keys())
    eq_w = {m: 1.0 / len(model_names) for m in model_names}
    records = []
    w_prev = None
    for t, fd in enumerate(forecasts_per_date):
        if t < WARMUP:
            w_t = eq_w
        else:
            scores = _crps_scores_up_to(forecasts_per_date, realized_list, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else eq_w)
            w_shrunk = bma_shrinkage(w_data, alpha=ALPHA)
            w_t = apply_temporal_smoothing(w_shrunk, w_prev, rho=RHO)
        bw = BMAWeights(horizon_months=HORIZON, weights=w_t,
                        iteration=3, method="shrinkage+smoothing")
        bma_samples = combine_forecasts(fd, bw)
        bma_center = combine_centers(fd, bw)
        records.append({
            "as_of": dates_used[t],
            "fd": fd,
            "weights": w_t,
            "bma_samples": bma_samples,
            "bma_center": bma_center,
            "realized": realized_list[t],
        })
        w_prev = w_t
    return records


def plot_example(rec, out_path):
    fd = rec["fd"]; weights = rec["weights"]; bma = rec["bma_samples"]
    realized = rec["realized"]
    model_names = list(fd.keys())
    colors = {"NN_K10": "#3498db", "NN_K20": "#2c3e50",
              "Naive_boot": "#e67e22", "AR1": "#9b59b6", "Drift_vol": "#16a085"}

    fig, axes = plt.subplots(2, 1, figsize=(12, 9),
                              gridspec_kw={"height_ratios": [2, 1.4]})

    # Panel A: nubes (KDE/hist) de cada modelo + BMA
    ax = axes[0]
    bins = np.linspace(-0.30, 0.30, 60)
    for m in model_names:
        s = fd[m].samples
        ax.hist(s, bins=bins, density=True, histtype="step", linewidth=1.4,
                color=colors[m],
                label=f"{m} (peso BMA={weights[m]:.2f})")
        lo, hi = _hdi(s, 0.5)
        ax.plot([lo, hi], [-(0.5 + model_names.index(m) * 0.4)] * 2,
                color=colors[m], lw=3, solid_capstyle="butt")

    # BMA superpuesto en gris fuerte
    ax.hist(bma, bins=bins, density=True, histtype="stepfilled",
            color="black", alpha=0.18, label="BMA combinado")
    ax.hist(bma, bins=bins, density=True, histtype="step",
            color="black", lw=2.2)
    lo_bma, hi_bma = _hdi(bma, 0.5)
    ax.axvspan(lo_bma, hi_bma, color="black", alpha=0.08,
               label=f"HDI50 BMA = [{lo_bma:+.1%}, {hi_bma:+.1%}]")

    # Realized
    ax.axvline(realized, color="red", lw=2.5,
               label=f"Retorno REAL = {realized:+.1%}")
    ax.set_xlabel("Retorno log acumulado a 6m")
    ax.set_ylabel("Densidad")
    ax.set_title(
        f"As-of {rec['as_of']} — 5 nubes individuales + BMA combinado (LQD, h=6m)"
    )
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)

    # Panel B: tabla — métricas por modelo
    ax = axes[1]; ax.axis("off")
    rows = []
    for m in model_names:
        s = fd[m].samples
        lo, hi = _hdi(s, 0.5)
        in_hdi = "SI" if lo <= realized <= hi else "NO"
        crps_m = crps_sample_vs_obs(s, realized)
        rows.append([m, f"{weights[m]:.2f}",
                     f"{float(np.median(s)):+.1%}",
                     f"[{lo:+.1%}, {hi:+.1%}]",
                     f"{hi - lo:.3f}", in_hdi,
                     f"{crps_m:.4f}"])
    lo_b, hi_b = _hdi(bma, 0.5)
    in_b = "SI" if lo_b <= realized <= hi_b else "NO"
    crps_b = crps_sample_vs_obs(bma, realized)
    rows.append(["BMA combinado", "1.00",
                 f"{rec['bma_center']:+.1%}",
                 f"[{lo_b:+.1%}, {hi_b:+.1%}]",
                 f"{hi_b - lo_b:.3f}", in_b,
                 f"{crps_b:.4f}"])
    col_labels = ["Modelo", "Peso", "Mediana", "HDI 50%",
                  "Sharpness", "¿Real cayó en HDI50?", "CRPS"]
    tbl = ax.table(cellText=rows, colLabels=col_labels,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9)
    tbl.scale(1, 1.6)
    for i in range(len(col_labels)):
        tbl[(0, i)].set_facecolor("#dfe6e9")
        tbl[(0, i)].set_text_props(weight="bold")
    # Resaltar fila BMA
    for j in range(len(col_labels)):
        tbl[(len(rows), j)].set_facecolor("#fff3cd")
        tbl[(len(rows), j)].set_text_props(weight="bold")
    ax.set_title(
        f"Métricas por modelo en esta fecha — retorno real = {realized:+.1%}",
        pad=10,
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return rows


def main():
    fps, real, ds = build_all_forecasts()
    records = run_iter3_with_records(fps, real, ds)
    rec = next(r for r in records if r["as_of"] == AS_OF_EJEMPLO)
    out = Path("data/external/tasas_mercantil/bma_ejemplo_2022_03_31.png")
    rows = plot_example(rec, out)

    print(f"=== Ejemplo as_of = {AS_OF_EJEMPLO} ===\n")
    print(f"Horizonte: {HORIZON} meses → ventana {AS_OF_EJEMPLO} a 2022-09-30")
    print(f"Retorno REAL observado: {rec['realized']:+.4f} = {rec['realized']:+.2%}\n")
    print(f"Pesos BMA Iter 3 (α=1.0, ρ=0.95):")
    for m, w in sorted(rec["weights"].items(), key=lambda kv: -kv[1]):
        print(f"  {m:>12}: {w:.3f}")
    print()
    print("Métricas por modelo:")
    cols = ["Modelo", "Peso", "Mediana", "HDI50", "Width", "InHDI", "CRPS"]
    print("  " + " | ".join(f"{c:>12}" for c in cols))
    for r in rows:
        print("  " + " | ".join(f"{c:>12}" for c in r))

    # Agregado: cómo se escala
    print(f"\n=== Escalamiento a {len(records)} fechas ===")
    all_in_hdi = []
    all_crps = []
    all_widths = []
    for r in records:
        lo_b, hi_b = _hdi(r["bma_samples"], 0.5)
        all_in_hdi.append(lo_b <= r["realized"] <= hi_b)
        all_crps.append(crps_sample_vs_obs(r["bma_samples"], r["realized"]))
        all_widths.append(hi_b - lo_b)
    print(f"  Cobertura HDI50 BMA: {sum(all_in_hdi)}/{len(all_in_hdi)} = "
          f"{100*sum(all_in_hdi)/len(all_in_hdi):.1f}%")
    print(f"  CRPS medio BMA:      {np.mean(all_crps):.5f}")
    print(f"  Sharpness medio BMA: {np.mean(all_widths):.4f}")
    print(f"\n[OK] figura → {out}")


if __name__ == "__main__":
    main()
