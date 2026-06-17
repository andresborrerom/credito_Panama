"""Iter 6: gate combinado con 4 señales — agrega BREAKEVEN INFLATION proxy.

Hipótesis: breakeven inflation fue LEADING en H2-2021 (subió antes que MOVE
o curve flattening). Atraparía los 3 meses jul/ago/sep 2021 que Iter 5 perdió.

Proxy del cambio en breakeven inflation:
  bei_change_12m(t) = log(TIP[t]/IEF[t]) - log(TIP[t-12]/IEF[t-12])

Cuando TIPS supera Treasuries en retorno rolling → breakeven inflation
subiendo → expectativa de Fed más restrictiva → stress sobre tasas.

Gate Iter 6:
  stress = max(MOVE_pct, slope_pct, vel_us2y_pct, breakeven_pct)
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
STRESS_HIGH = 0.80; STRESS_EXTREME = 0.95
STRESS_LOOKBACK = 60

CACHE_DIR = Path("data/external/tasas_mercantil")
MOVE_CACHE = CACHE_DIR / "move_eom.parquet"
US2Y_CACHE = CACHE_DIR / "us2y_eom.parquet"
US10Y_CACHE = CACHE_DIR / "us10y_eom.parquet"
US2Y_DAILY_CACHE = CACHE_DIR / "us2y_daily.parquet"
TIP_CACHE = CACHE_DIR / "tip_eom.parquet"
IEF_CACHE = CACHE_DIR / "ief_eom.parquet"


def hdi(s, mass):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def _fetch_eom_adj(ticker, cache_path, col="adjusted_close",
                   start=date(2008, 1, 1), end=date(2025, 6, 30)):
    """Fetch end-of-month, usando adjusted_close si está disponible (para ETFs)."""
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")[df.columns[-1]]
    print(f"Descargando {ticker} ({col})...")
    df = fetch_etf_history(ticker, period="d", start=start, end=end)
    df["date"] = pd.to_datetime(df["obs_date"])
    col_use = col if col in df.columns else "close"
    s = df.set_index("date")[col_use].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s.index, ticker.replace(".", "_"): s.values})
    out.to_parquet(cache_path, index=False)
    return s


def _fetch_daily(ticker, cache_path, start=date(2008, 1, 1), end=date(2025, 6, 30)):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")["close"]
    print(f"Descargando diario {ticker}...")
    df = fetch_etf_history(ticker, period="d", start=start, end=end)
    df["date"] = pd.to_datetime(df["obs_date"])
    s = df.set_index("date")["close"].dropna().sort_index()
    out = pd.DataFrame({"date": s.index, "close": s.values})
    out.to_parquet(cache_path, index=False)
    return s


def fetch_signals():
    move = _fetch_eom_adj("MOVE.INDX", MOVE_CACHE, col="close")
    us2y = _fetch_eom_adj("US2Y.INDX", US2Y_CACHE, col="close")
    us10y = _fetch_eom_adj("US10Y.INDX", US10Y_CACHE, col="close")
    us2y_d = _fetch_daily("US2Y.INDX", US2Y_DAILY_CACHE)
    tip = _fetch_eom_adj("TIP.US", TIP_CACHE, col="adjusted_close")
    ief = _fetch_eom_adj("IEF.US", IEF_CACHE, col="adjusted_close")
    return move, us2y, us10y, us2y_d, tip, ief


def percentile_in_window(series, as_of, lookback=STRESS_LOOKBACK):
    cut = pd.Timestamp(as_of)
    history = series.loc[series.index <= cut]
    if len(history) < lookback: return None
    window = history.iloc[-lookback:]
    current = window.iloc[-1]
    return float((window <= current).mean())


def compute_stress(as_of, move, us2y, us10y, us2y_daily, tip, ief):
    p_move = percentile_in_window(move, as_of)
    slope = us10y - us2y
    p_slope_low = percentile_in_window(slope, as_of)
    p_slope_stress = (1 - p_slope_low) if p_slope_low is not None else None
    cut = pd.Timestamp(as_of)
    daily_hist = us2y_daily.loc[us2y_daily.index <= cut]
    if len(daily_hist) > 60:
        vel_abs = (daily_hist - daily_hist.shift(60)).abs().resample("ME").last().dropna()
        p_vel = percentile_in_window(vel_abs, as_of)
    else:
        p_vel = None
    # Breakeven inflation proxy: cambio 12m en log(TIP/IEF)
    tip_ief = np.log(tip / ief)
    bei_change = tip_ief - tip_ief.shift(12)
    p_bei = percentile_in_window(bei_change.dropna(), as_of)
    components = {
        "move": p_move, "slope_stress": p_slope_stress,
        "vel_us2y": p_vel, "breakeven": p_bei,
    }
    valid = [v for v in components.values() if v is not None]
    stress = max(valid) if valid else None
    return stress, components


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
    U_raw, lo, hi = usability_raw(samples, w_max, p_grid)
    if stress_pct is None: return U_raw, lo, hi, "sin_dato"
    if stress_pct >= extreme: return 0.0, lo, hi, "stress_extremo"
    if stress_pct >= high:
        capped = min(U_raw, 0.50)
        if capped < U_raw and capped > 0:
            lo, hi = hdi(samples, capped)
        return capped, lo, hi, "stress_alto"
    return U_raw, lo, hi, "normal"


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
        out.append({"as_of": ds[t], "bma_samples": combine_forecasts(fd, bw),
                    "realized": reals[t]})
        w_prev = w_t
    return out


def main():
    move, us2y, us10y, us2y_d, tip, ief = fetch_signals()
    print(f"MOVE  : {move.index.min().date()} → {move.index.max().date()}")
    print(f"US2Y  : {us2y.index.min().date()} → {us2y.index.max().date()}")
    print(f"US10Y : {us10y.index.min().date()} → {us10y.index.max().date()}")
    print(f"TIP   : {tip.index.min().date()} → {tip.index.max().date()}")
    print(f"IEF   : {ief.index.min().date()} → {ief.index.max().date()}\n")

    fps, reals, ds = build_all()
    print(f"Forecasts (4 modelos): {len(fps)} fechas\n")
    records = run_iter3(fps, reals, ds)

    rows = []
    for r in records:
        stress, comps = compute_stress(r["as_of"], move, us2y, us10y, us2y_d, tip, ief)
        U_raw, lo_r, hi_r = usability_raw(r["bma_samples"], W_MAX)
        U_gat, lo_g, hi_g, regime = usability_gated(r["bma_samples"], W_MAX, stress)
        rows.append({
            "as_of": r["as_of"],
            "MOVE_pct": comps["move"], "slope_pct": comps["slope_stress"],
            "vel_pct": comps["vel_us2y"], "bei_pct": comps["breakeven"],
            "stress": stress, "regime": regime,
            "U_raw": int(U_raw * 100), "U_gat": int(U_gat * 100),
            "HDI_gat_lo": lo_g, "HDI_gat_hi": hi_g, "realized": r["realized"],
            "real_in_HDI": lo_g <= r["realized"] <= hi_g,
        })
    df = pd.DataFrame(rows)

    iter5 = pd.read_parquet(CACHE_DIR / "bma_iter5_gate_curva.parquet")
    iter5["as_of"] = pd.to_datetime(iter5["as_of"]).dt.date
    df_cmp = df.merge(
        iter5[["as_of", "U_gat", "regime"]].rename(
            columns={"U_gat": "U_iter5", "regime": "reg_iter5"}),
        on="as_of", how="left",
    )

    print("=== Foco: jul-2021 a mar-2022 ===")
    mask = (pd.to_datetime(df_cmp["as_of"]) >= "2021-07-01") & \
           (pd.to_datetime(df_cmp["as_of"]) <= "2022-03-31")
    cols = ["as_of", "MOVE_pct", "slope_pct", "vel_pct", "bei_pct", "stress",
            "U_raw", "U_iter5", "U_gat", "realized"]
    fc = df_cmp.loc[mask, cols].copy()
    for c in ["MOVE_pct", "slope_pct", "vel_pct", "bei_pct", "stress"]:
        fc[c] = fc[c].round(2)
    fc["realized"] = fc["realized"].round(3)
    print(fc.to_string(index=False))

    print(f"\n=== Distribución régimen ===")
    print(df["regime"].value_counts().to_string())

    print(f"\n=== Validación honestidad U_gat Iter 6 ===")
    for u in sorted(df["U_gat"].unique(), reverse=True):
        sub = df[df["U_gat"] == u]
        if len(sub) == 0: continue
        emp = 100 * sub["real_in_HDI"].mean()
        lbl = "NO USABLE" if u == 0 else f"U={u}"
        print(f"  {lbl:>10} (n={len(sub):>2}): cobertura empírica = "
              f"{emp:5.1f}%  (esperada ≈ {u}%)")

    print(f"\n=== Comparación Iter 4 vs 5 vs 6 ===")
    iter4 = pd.read_parquet(CACHE_DIR / "bma_iter4_gate_stress.parquet")
    iter4["as_of"] = pd.to_datetime(iter4["as_of"]).dt.date
    iter5_d = pd.read_parquet(CACHE_DIR / "bma_iter5_gate_curva.parquet")
    iter5_d["as_of"] = pd.to_datetime(iter5_d["as_of"]).dt.date
    summ = []
    for name, d, ucol, rcol in [
        ("Iter 4 (MOVE)", iter4, "U_gat(%)", "regime"),
        ("Iter 5 (+ slope, vel US2Y)", iter5_d, "U_gat", "regime"),
        ("Iter 6 (+ breakeven)", df, "U_gat", "regime"),
    ]:
        n_extr = (d[rcol] == "stress_extremo").sum()
        n_alto = (d[rcol] == "stress_alto").sum()
        n_norm = (d[rcol] == "normal").sum()
        n_zero = (d[ucol] == 0).sum()
        n_50 = (d[ucol] == 50).sum()
        n_high = ((d[ucol] >= 60)).sum()
        summ.append({
            "iter": name, "n": len(d), "normal": n_norm,
            "stress_alto": n_alto, "stress_extremo": n_extr,
            "U=0": n_zero, "U=50": n_50, "U≥60": n_high,
        })
    print(pd.DataFrame(summ).to_string(index=False))

    # Plot
    fig, axes = plt.subplots(3, 1, figsize=(13, 10))
    dts = pd.to_datetime(df["as_of"])

    ax = axes[0]
    ax.plot(dts, df["MOVE_pct"], lw=1.3, color="#2c3e50", label="MOVE")
    ax.plot(dts, df["slope_pct"], lw=1.3, color="#27ae60", label="Slope stress")
    ax.plot(dts, df["vel_pct"], lw=1.3, color="#9b59b6", label="Vel US2Y")
    ax.plot(dts, df["bei_pct"], lw=1.8, color="#e67e22", label="Breakeven (NUEVA)")
    ax.fill_between(dts, 0, df["stress"], color="#e74c3c", alpha=0.20,
                    label="Stress combo")
    ax.axhline(STRESS_HIGH, color="#e74c3c", ls="--", lw=0.7, alpha=0.6)
    ax.axhline(STRESS_EXTREME, color="#c0392b", ls=":", lw=0.7, alpha=0.6)
    ax.set_ylim(0, 1.02); ax.set_ylabel("Percentile 5y")
    ax.set_title("Iter 6 — 4 señales: MOVE + Slope + Vel US2Y + Breakeven inflation")
    ax.legend(loc="upper right", fontsize=8, ncol=3); ax.grid(alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    ax = axes[1]
    width = 7
    o5 = pd.Timedelta(days=width); o6 = pd.Timedelta(days=0)
    ax.bar(dts - o5, df_cmp["U_iter5"], width=width, color="#3498db",
           edgecolor="black", linewidth=0.3, label="Iter 5 (3 señales)")
    ax.bar(dts + o6, df_cmp["U_gat"], width=width, color="#e74c3c",
           edgecolor="black", linewidth=0.3, label="Iter 6 (+ breakeven)")
    ax.set_ylabel("U gated (%)"); ax.set_ylim(0, 100)
    ax.set_title("U gated — Iter 5 vs Iter 6"); ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    ax = axes[2]
    HDI_lo = df["HDI_gat_lo"].values; HDI_hi = df["HDI_gat_hi"].values
    is_zero = df["U_gat"] == 0
    ax.fill_between(dts[~is_zero], HDI_lo[~is_zero], HDI_hi[~is_zero],
                    color="#3498db", alpha=0.3, label="HDI U_gat Iter6")
    ax.scatter(dts[is_zero], [0] * is_zero.sum(), marker="x", color="black",
               s=40, label="NO usable")
    ax.plot(dts, df["realized"], "o-", color="#c0392b", markersize=4, lw=1.2,
            label="retorno realizado")
    ax.axhline(0, color="grey", lw=0.7); ax.set_ylabel("Retorno log 6m")
    ax.set_title("HDI Iter 6 vs realizado")
    ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    fig.tight_layout()
    out_fig = CACHE_DIR / "bma_iter6_gate_breakeven.png"
    fig.savefig(out_fig, dpi=130, bbox_inches="tight"); plt.close(fig)
    df.to_parquet(CACHE_DIR / "bma_iter6_gate_breakeven.parquet", index=False)
    print(f"\n[OK] {out_fig}")


if __name__ == "__main__":
    main()
