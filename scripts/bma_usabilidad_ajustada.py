"""Métrica de Usabilidad AJUSTADA por cobertura empírica reciente.

Idea: el U_raw declara confianza basado solo en el ancho del HDI actual,
sin saber si históricamente el HDI_p del modelo cumple su promesa. El ajuste
penaliza p si la cobertura empírica reciente de HDI_p está por debajo de p
con tolerancia, para auto-corregir COMPLACENCIA detectada (jul-2021/mar-2022).

Definición:
  U_adj(t) = max { p ∈ P_grid : ancho HDI_p(t) ≤ W_max
                              AND emp_cov_reciente(p, t) ≥ p − tolerancia }
donde emp_cov_reciente usa los últimos `lookback` forecasts cuyo realizado
ya es observable al momento t (forecasts hechos en t-h o anterior).
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
W_MAX = 0.10
TOL = 0.10
LOOKBACK_COV = 12


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def usability_raw(samples, w_max, p_grid=P_GRID):
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = hdi(samples, 0.50); return 0.0, lo, hi
    return best_p, best_lo, best_hi


def empirical_cov_history(records_observable, p_grid=P_GRID):
    """Cobertura empírica por nivel p sobre records ya observables."""
    if not records_observable: return {p: None for p in p_grid}
    out = {}
    for p in p_grid:
        hits = 0
        for r in records_observable:
            lo, hi = hdi(r["bma_samples"], p)
            if lo <= r["realized"] <= hi: hits += 1
        out[p] = hits / len(records_observable)
    return out


def usability_adjusted(samples_current, records_observable, w_max,
                       p_grid=P_GRID, lookback=LOOKBACK_COV, tol=TOL):
    emp = empirical_cov_history(records_observable[-lookback:], p_grid)
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = hdi(samples_current, p)
        ec = emp[p]
        elig_cov = (ec is None) or (ec >= p - tol)
        if (hi - lo) <= w_max and elig_cov:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = hdi(samples_current, 0.50); return 0.0, lo, hi, emp
    return best_p, best_lo, best_hi, emp


# ===== reuso =====
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
    n = len(records)
    rows = []
    for t in range(n):
        # records cuyo realizado YA es observable en el momento del as_of[t]
        # (forecasts hechos h meses atrás o más)
        observable_idx_end = max(0, t - HORIZON + 1)
        observable = records[:observable_idx_end]
        U_raw, lo_r, hi_r = usability_raw(records[t]["bma_samples"], W_MAX)
        U_adj, lo_a, hi_a, emp = usability_adjusted(
            records[t]["bma_samples"], observable, W_MAX,
            lookback=LOOKBACK_COV, tol=TOL,
        )
        rows.append({
            "as_of": records[t]["as_of"],
            "centro": records[t]["bma_center"],
            "U_raw(%)": int(U_raw * 100),
            "U_adj(%)": int(U_adj * 100),
            "HDI_raw_low": lo_r, "HDI_raw_high": hi_r,
            "HDI_adj_low": lo_a, "HDI_adj_high": hi_a,
            "realized": records[t]["realized"],
            "real_en_HDI_adj": lo_a <= records[t]["realized"] <= hi_a,
            "emp_cov_70": emp.get(0.70),
            "emp_cov_60": emp.get(0.60),
            "emp_cov_50": emp.get(0.50),
        })
    df = pd.DataFrame(rows)

    print(f"=== Usabilidad AJUSTADA (LQD, W_max={W_MAX:.0%}, "
          f"lookback={LOOKBACK_COV}m, tol={TOL:.0%}) ===\n")
    cols = ["as_of", "U_raw(%)", "U_adj(%)", "emp_cov_70",
            "emp_cov_60", "emp_cov_50", "realized", "real_en_HDI_adj"]
    df_disp = df[cols].copy()
    for c in ["emp_cov_70", "emp_cov_60", "emp_cov_50", "realized"]:
        df_disp[c] = df_disp[c].round(3)
    print(df_disp.to_string(index=False))

    # Distribuciones comparadas
    print(f"\n=== Distribución comparada ===")
    print(f"{'Nivel U':>10} | {'raw':>5} | {'ajustado':>9}")
    for u in [90, 80, 70, 60, 50, 0]:
        nr = (df["U_raw(%)"] == u).sum()
        na = (df["U_adj(%)"] == u).sum()
        lbl = "NO USABLE" if u == 0 else f"U={u}%"
        print(f"  {lbl:>8} | {nr:>5} | {na:>9}")

    # Validación de honestidad después del ajuste
    print(f"\n=== Validación honestidad (U_adj) ===")
    for u in sorted(df["U_adj(%)"].unique(), reverse=True):
        sub = df[df["U_adj(%)"] == u]
        if len(sub) == 0: continue
        emp = 100 * sub["real_en_HDI_adj"].mean()
        lbl = "NO USABLE" if u == 0 else f"U_adj={u}%"
        print(f"  {lbl:>13} (n={len(sub):>2}): cobertura empírica = {emp:5.1f}%  "
              f"(esperada ≈ {u}%)")

    # Foco en los 9 meses jul-2021 a mar-2022
    print(f"\n=== Foco: meses de complacencia detectados (jul-2021 a mar-2022) ===")
    mask = (pd.to_datetime(df["as_of"]) >= "2021-07-01") & \
           (pd.to_datetime(df["as_of"]) <= "2022-03-31")
    print(df.loc[mask, ["as_of", "U_raw(%)", "U_adj(%)",
                        "emp_cov_70", "realized"]].to_string(index=False))

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                              gridspec_kw={"height_ratios": [1.4, 1]})
    dts = pd.to_datetime(df["as_of"])

    ax = axes[0]
    width = 11
    offset = pd.Timedelta(days=width / 2)
    ax.bar(dts - offset, df["U_raw(%)"], width=width, color="#3498db",
           edgecolor="black", linewidth=0.4, label="U raw")
    ax.bar(dts + offset, df["U_adj(%)"], width=width, color="#e74c3c",
           edgecolor="black", linewidth=0.4, label="U ajustado")
    ax.set_ylabel("Score de Usabilidad (%)")
    ax.set_title("U raw vs U ajustado por cobertura empírica reciente (LQD, h=6m)")
    ax.set_ylim(0, 100); ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12, label="meses complacencia")

    ax = axes[1]
    levels = [0, 50, 60, 70, 80, 90]
    counts_raw = [(df["U_raw(%)"] == u).sum() for u in levels]
    counts_adj = [(df["U_adj(%)"] == u).sum() for u in levels]
    x = np.arange(len(levels)); w = 0.4
    ax.bar(x - w/2, counts_raw, w, color="#3498db", label="raw", edgecolor="black")
    ax.bar(x + w/2, counts_adj, w, color="#e74c3c", label="ajustado", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels(["NO\nusable"] + [f"U={u}%" for u in levels[1:]])
    ax.set_ylabel("Número de meses")
    ax.set_title(f"Distribución (n={len(df)} meses)")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    for i, (r, a) in enumerate(zip(counts_raw, counts_adj)):
        if r > 0: ax.text(i - w/2, r + 0.3, str(r), ha="center", fontsize=9)
        if a > 0: ax.text(i + w/2, a + 0.3, str(a), ha="center", fontsize=9)

    fig.tight_layout()
    out_fig = Path("data/external/tasas_mercantil/bma_usabilidad_ajustada.png")
    fig.savefig(out_fig, dpi=130, bbox_inches="tight")
    plt.close(fig)
    df.to_parquet(Path("data/external/tasas_mercantil/bma_usabilidad_ajustada.parquet"),
                  index=False)
    print(f"\n[OK] figura → {out_fig}")


if __name__ == "__main__":
    main()
