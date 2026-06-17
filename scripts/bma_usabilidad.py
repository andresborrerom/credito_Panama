"""Métrica de USABILIDAD del forecast mensual.

Para cada mes, computa U = max p tal que HDI_p(t) tiene ancho ≤ W_max.
Interpretación: nivel máximo de confianza al que podemos hacer una afirmación
de ancho 'interpretable' (W_max) para el comité.

Convención para LQD horizonte 6m: W_max = 0.10 (10 puntos porcentuales).
Cambiable por activo/horizonte (es decisión de negocio, no estadística).
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
    ModelForecast, BMAWeights, combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1, model_drift_vol

ETF = "LQD"; HORIZON = 6; WARMUP = 12; ALPHA = 1.0; RHO = 0.95
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)
W_MAX = 0.10  # 10pp = ancho "interpretable" para LQD 6m


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def usability(samples, w_max, p_grid=P_GRID):
    """Devuelve (U, lo, hi) donde U = max p tal que ancho_HDI_p ≤ w_max.
    Si ningún p es factible, U=0 y devuelve HDI50 igual (informativo)."""
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = hdi(samples, 0.50)
        return 0.0, lo, hi
    return best_p, best_lo, best_hi


def crps_sample_vs_obs(samples, y):
    samples = np.asarray(samples); n = len(samples)
    term1 = np.mean(np.abs(samples - y))
    s = np.sort(samples)
    term2 = (2.0 / (n * n)) * np.sum((2 * np.arange(1, n + 1) - n - 1) * s)
    return float(term1 - 0.5 * term2)


# ===== reutilizado del ejemplo anterior =====
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


def build_all():
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")
    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    fps, reals, ds = [], [], []
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
        fps.append(models); reals.append(real); ds.append(d)
    return fps, reals, ds


def run_iter3(fps, reals, ds):
    names = list(fps[0].keys())
    eq_w = {m: 1.0 / len(names) for m in names}
    out = []; w_prev = None
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
        out.append({
            "as_of": ds[t],
            "bma_samples": combine_forecasts(fd, bw),
            "bma_center": combine_centers(fd, bw),
            "realized": reals[t],
        })
        w_prev = w_t
    return out


def main():
    fps, reals, ds = build_all()
    records = run_iter3(fps, reals, ds)
    rows = []
    for r in records:
        U, lo, hi = usability(r["bma_samples"], W_MAX)
        rows.append({
            "as_of": r["as_of"],
            "centro": r["bma_center"],
            "U(%)": int(U * 100),
            "HDI_U_low": lo, "HDI_U_high": hi,
            "ancho": hi - lo,
            "realized": r["realized"],
            "real_en_HDI_U": (lo <= r["realized"] <= hi),
        })
    df = pd.DataFrame(rows)

    print(f"=== Usabilidad mensual (LQD, h=6m, W_max={W_MAX:.0%}) ===\n")
    df_disp = df.copy()
    for c in ["centro", "HDI_U_low", "HDI_U_high", "ancho", "realized"]:
        df_disp[c] = df_disp[c].round(4)
    print(df_disp.to_string(index=False))

    # Distribución de U
    print(f"\n=== Distribución del score U ===")
    dist = df["U(%)"].value_counts().sort_index(ascending=False)
    total = len(df)
    for u, n in dist.items():
        lbl = "NO USABLE" if u == 0 else f"U≥{u}%"
        print(f"  {lbl:>12}: {n:>2}/{total} = {100*n/total:5.1f}%")

    # Validación: si U=p, esperamos que ~p% de esos meses caigan en su HDI
    print(f"\n=== Validación (¿el real cae en HDI_U el % esperado?) ===")
    for u in sorted(df["U(%)"].unique(), reverse=True):
        sub = df[df["U(%)"] == u]
        if len(sub) == 0: continue
        emp = 100 * sub["real_en_HDI_U"].mean()
        lbl = "NO USABLE" if u == 0 else f"U={u}%"
        print(f"  {lbl:>10} (n={len(sub):>2}): cobertura empírica = {emp:5.1f}%  "
              f"(esperada ≈ {u}%)")

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                              gridspec_kw={"height_ratios": [1.4, 1]})

    # Time series U
    ax = axes[0]
    dts = pd.to_datetime(df["as_of"])
    U_vals = df["U(%)"].values
    colors_u = ["#c0392b" if u == 0 else "#e67e22" if u <= 60
                else "#f1c40f" if u <= 70 else "#27ae60" for u in U_vals]
    ax.bar(dts, U_vals, color=colors_u, width=22, edgecolor="black", linewidth=0.4)
    ax.set_ylabel("Score de Usabilidad U (%)")
    ax.set_title(
        f"Usabilidad mensual del BMA (LQD, h=6m, W_max={W_MAX:.0%})\n"
        "Verde = afirmación de alta confianza posible | "
        "Amarillo = afirmación media | Naranja = baja | Rojo = no usable"
    )
    ax.axhline(50, color="grey", lw=0.7, ls="--", alpha=0.6)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.3)

    # Histograma de U
    ax = axes[1]
    bins = [-5, 5, 55, 65, 75, 85, 95]
    counts, _ = np.histogram(U_vals, bins=bins)
    labels = ["NO\nusable\n(0%)", "U=50%", "U=60%", "U=70%", "U=80%", "U=90%"]
    bar_colors = ["#c0392b", "#e67e22", "#e67e22", "#f1c40f", "#27ae60", "#27ae60"]
    bars = ax.bar(labels, counts, color=bar_colors, edgecolor="black")
    ax.set_ylabel("Número de meses")
    ax.set_title(f"Distribución del score U (n={total} meses)")
    for b, c in zip(bars, counts):
        if c > 0:
            ax.text(b.get_x() + b.get_width() / 2, c + 0.3,
                    f"{c} ({100*c/total:.0f}%)",
                    ha="center", fontsize=9, fontweight="bold")
    ax.set_ylim(0, max(counts) + 3)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    out_fig = Path("data/external/tasas_mercantil/bma_usabilidad.png")
    fig.savefig(out_fig, dpi=130, bbox_inches="tight")
    plt.close(fig)

    df.to_parquet(Path("data/external/tasas_mercantil/bma_usabilidad.parquet"),
                  index=False)
    print(f"\n[OK] figura → {out_fig}")


if __name__ == "__main__":
    main()
