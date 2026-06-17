"""Iter 4: Ensemble podado (4 modelos) + gate ex-ante por señal de stress externa.

Cambios vs Iter 3:
  1. Ensemble podado: quitamos Drift_vol (era redundante con AR1, ablation −2.1% CRPS).
     Queda: NN_K10, NN_K20, Naive_boot, AR1.
  2. Gate por MOVE index: si percentile reciente >= STRESS_HIGH, cap U a 50%.
     Si percentile >= STRESS_EXTREME, U = 0 (no usable).
     Objetivo: corregir los 9 meses de complacencia (jul-2021/mar-2022) que el
     ajuste reactivo no pudo arreglar.

MOVE index = volatilidad implícita de opciones sobre Treasuries (el "VIX de bonos").
Se mueve antes que LQD en cambios de régimen.
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
    build_macro_history, find_neighbors, compute_forward_returns, macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    ModelForecast, BMAWeights, combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1

ETF = "LQD"; HORIZON = 6; WARMUP = 12; ALPHA = 1.0; RHO = 0.95
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)
W_MAX = 0.10

# Gate por stress
STRESS_HIGH = 0.80      # percentile MOVE para cap U≤50
STRESS_EXTREME = 0.95   # percentile MOVE para U=0
STRESS_LOOKBACK = 60    # 5 años de lookback para percentil

MOVE_CACHE = Path("data/external/tasas_mercantil/move_eom.parquet")


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def fetch_move_eom():
    """Baja MOVE.INDX diario desde 2010 y devuelve serie mensual end-of-month."""
    if MOVE_CACHE.exists():
        df = pd.read_parquet(MOVE_CACHE)
        return df.set_index("date")["MOVE"]
    print("Descargando MOVE.INDX (puede tardar)...")
    df = fetch_etf_history("MOVE.INDX", period="d",
                           start=date(2010, 1, 1), end=date(2025, 6, 30))
    df["date"] = pd.to_datetime(df["obs_date"])
    s = df.set_index("date")["close"].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s.index, "MOVE": s.values})
    out.to_parquet(MOVE_CACHE, index=False)
    return s


def stress_percentile(move_series, as_of, lookback=STRESS_LOOKBACK):
    """Percentile del MOVE actual vs últimos `lookback` meses (excluyendo futuro)."""
    cut = pd.Timestamp(as_of)
    history = move_series.loc[move_series.index <= cut]
    if len(history) < lookback:
        return None
    window = history.iloc[-lookback:]
    current = window.iloc[-1]
    return float((window <= current).mean())


def usability_raw(samples, w_max, p_grid=P_GRID):
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = hdi(samples, 0.50); return 0.0, lo, hi
    return best_p, best_lo, best_hi


def usability_gated(samples, w_max, stress_pct, p_grid=P_GRID,
                    high=STRESS_HIGH, extreme=STRESS_EXTREME):
    """U con cap por stress. Si stress es alto, no permitir confianza alta."""
    U_raw, lo, hi = usability_raw(samples, w_max, p_grid)
    if stress_pct is None:
        return U_raw, lo, hi, "sin_dato_stress"
    if stress_pct >= extreme:
        return 0.0, lo, hi, "stress_extremo"
    if stress_pct >= high:
        # Cap U a 50%
        capped = min(U_raw, 0.50)
        if capped < U_raw and capped > 0:
            lo, hi = hdi(samples, capped)
        return capped, lo, hi, "stress_alto"
    return U_raw, lo, hi, "normal"


def crps_sample_vs_obs(samples, y):
    samples = np.asarray(samples); n = len(samples)
    term1 = np.mean(np.abs(samples - y))
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
        # 4 MODELOS: sin Drift_vol
        models = {
            "NN_K10":     model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON),
            "NN_K20":     model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON),
            "Naive_boot": model_naive(d, etf_ret, HORIZON),
            "AR1":        model_ar1(d, etf_ret, ETF, HORIZON, n_sims=1000),
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
            "weights": w_t,
        })
        w_prev = w_t
    return out


def main():
    move = fetch_move_eom()
    print(f"MOVE histórico: {move.index.min().date()} a {move.index.max().date()} "
          f"({len(move)} meses)\n")

    fps, reals, ds = build_all()
    print(f"Forecasts construidos (4 modelos): {len(fps)} fechas\n")
    records = run_iter3(fps, reals, ds)

    # Computar U_raw, stress_pct y U_gated por fecha
    rows = []
    for r in records:
        sp = stress_percentile(move, r["as_of"])
        U_raw, lo_r, hi_r = usability_raw(r["bma_samples"], W_MAX)
        U_gat, lo_g, hi_g, regime = usability_gated(
            r["bma_samples"], W_MAX, sp
        )
        rows.append({
            "as_of": r["as_of"],
            "MOVE": float(move.loc[pd.Timestamp(r["as_of"])])
                if pd.Timestamp(r["as_of"]) in move.index else np.nan,
            "stress_pct": sp,
            "regime": regime,
            "U_raw(%)": int(U_raw * 100),
            "U_gat(%)": int(U_gat * 100),
            "HDI_raw": (round(lo_r, 4), round(hi_r, 4)),
            "HDI_gat": (round(lo_g, 4), round(hi_g, 4)),
            "realized": r["realized"],
            "real_en_HDI_gat": lo_g <= r["realized"] <= hi_g,
        })
    df = pd.DataFrame(rows)

    print("=== Resultados por fecha ===")
    print(df.to_string(index=False))

    # Distribución por régimen
    print(f"\n=== Distribución por régimen ===")
    print(df["regime"].value_counts().to_string())

    # Validación honestidad post-gate
    print(f"\n=== Validación honestidad U_gated ===")
    for u in sorted(df["U_gat(%)"].unique(), reverse=True):
        sub = df[df["U_gat(%)"] == u]
        if len(sub) == 0: continue
        emp = 100 * sub["real_en_HDI_gat"].mean()
        lbl = "NO USABLE" if u == 0 else f"U={u}%"
        print(f"  {lbl:>10} (n={len(sub):>2}): cobertura empírica = "
              f"{emp:5.1f}%  (esperada ≈ {u}%)")

    # Foco en los 9 meses de complacencia
    print(f"\n=== Foco: meses jul-2021 a mar-2022 ===")
    mask = (pd.to_datetime(df["as_of"]) >= "2021-07-01") & \
           (pd.to_datetime(df["as_of"]) <= "2022-03-31")
    cols = ["as_of", "MOVE", "stress_pct", "U_raw(%)", "U_gat(%)", "regime", "realized"]
    fc = df.loc[mask, cols].copy()
    fc["MOVE"] = fc["MOVE"].round(1)
    fc["stress_pct"] = fc["stress_pct"].round(2)
    fc["realized"] = fc["realized"].round(3)
    print(fc.to_string(index=False))

    # Plot
    fig, axes = plt.subplots(3, 1, figsize=(13, 10),
                              gridspec_kw={"height_ratios": [1, 1, 1]})
    dts = pd.to_datetime(df["as_of"])

    # Panel A: MOVE level + percentile
    ax = axes[0]
    ax.plot(dts, df["MOVE"], color="#2c3e50", lw=1.8, label="MOVE index")
    ax2 = ax.twinx()
    ax2.fill_between(dts, 0, df["stress_pct"], color="#e74c3c", alpha=0.25,
                     label="percentile 5y")
    ax2.axhline(STRESS_HIGH, color="#e74c3c", lw=0.8, ls="--", alpha=0.6,
                label=f"high ({STRESS_HIGH:.0%})")
    ax2.axhline(STRESS_EXTREME, color="#c0392b", lw=0.8, ls=":", alpha=0.6,
                label=f"extreme ({STRESS_EXTREME:.0%})")
    ax2.set_ylim(0, 1); ax2.set_ylabel("Percentile (área roja)")
    ax.set_ylabel("MOVE index (línea)"); ax.set_title("Señal de stress: MOVE index")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8); ax2.legend(loc="upper right", fontsize=8)

    # Panel B: U raw vs U gated
    ax = axes[1]
    width = 11; offset = pd.Timedelta(days=width / 2)
    ax.bar(dts - offset, df["U_raw(%)"], width=width, color="#3498db",
           edgecolor="black", linewidth=0.4, label="U raw (sin gate)")
    ax.bar(dts + offset, df["U_gat(%)"], width=width, color="#e74c3c",
           edgecolor="black", linewidth=0.4, label="U gated (con stress)")
    ax.set_ylabel("Score U (%)"); ax.set_ylim(0, 100)
    ax.set_title("U raw vs U gated por MOVE")
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)
    ax.legend(loc="upper right"); ax.grid(axis="y", alpha=0.3)

    # Panel C: realized vs HDI_gat
    ax = axes[2]
    HDI_lo = np.array([h[0] for h in df["HDI_gat"]])
    HDI_hi = np.array([h[1] for h in df["HDI_gat"]])
    is_zero = df["U_gat(%)"] == 0
    ax.fill_between(dts[~is_zero], HDI_lo[~is_zero], HDI_hi[~is_zero],
                    color="#3498db", alpha=0.3, label="HDI U_gat (cuando hay)")
    ax.scatter(dts[is_zero], [0] * is_zero.sum(), marker="x", color="black", s=40,
               label="NO usable")
    ax.plot(dts, df["realized"], "o-", color="#c0392b", markersize=4, lw=1.2,
            label="retorno realizado")
    ax.axhline(0, color="grey", lw=0.7)
    ax.set_ylabel("Retorno log 6m"); ax.set_title("Cobertura del HDI gated vs realizado")
    ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    fig.tight_layout()
    out_fig = Path("data/external/tasas_mercantil/bma_iter4_gate_stress.png")
    fig.savefig(out_fig, dpi=130, bbox_inches="tight")
    plt.close(fig)

    df.to_parquet(Path("data/external/tasas_mercantil/bma_iter4_gate_stress.parquet"),
                  index=False)
    print(f"\n[OK] figura → {out_fig}")


if __name__ == "__main__":
    main()
