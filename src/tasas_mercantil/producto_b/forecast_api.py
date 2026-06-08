"""API operativa final del Producto B (LQD-gates Iter 6).

Sistema cerrado tras experimentos LQD-gates (Iter 1-6) y curva Treasury
(experimento negativo documentado en docs/producto_b/EXPERIMENTO_CURVA_TREASURY.md).

Pipeline:
  1. 4 modelos diversos: NN_K10, NN_K20, Naive_boot, AR1.
  2. BMA Iter 3: shrinkage α=1.0 + temporal smoothing ρ=0.95.
  3. Score Usabilidad U con gate ex-ante por 4 señales externas:
     - MOVE.INDX percentile 5y
     - Slope (US10Y − US2Y) invertida percentile 5y
     - Velocidad |ΔUS2Y(60d)| percentile 5y
     - Breakeven inflation (TIP/IEF) cambio 12m percentile 5y
     Stress combinado = max de los 4.
       ≥ 0.95 → U = 0 (no usable)
       ≥ 0.80 → U capado a 50
       < 0.80 → U raw

Uso:
  >>> from tasas_mercantil.producto_b.forecast_api import forecast_lqd
  >>> result = forecast_lqd(as_of=date(2024,12,31))
  >>> print(result.comment)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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

# ============================================================================
# Constantes finales del sistema operativo
# ============================================================================
ETF_LABEL = "LQD"
HORIZON_MONTHS = 6
WARMUP_MONTHS = 12
ALPHA = 1.0                  # full data-driven (Iter 2)
RHO = 0.95                   # temporal smoothing (Iter 3)
W_MAX = 0.10                 # 10pp = ancho interpretable para LQD 6m
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)
STRESS_HIGH = 0.80           # cap U≤50
STRESS_EXTREME = 0.95        # U=0
STRESS_LOOKBACK = 60         # meses (5 años)

CACHE_DIR = Path("data/external/tasas_mercantil")


@dataclass
class ForecastResult:
    as_of: date
    center: float                       # mediana retorno log 6m
    hdi_lo: float                       # bound bajo HDI U%
    hdi_hi: float                       # bound alto HDI U%
    U: int                              # score usabilidad gated, en %
    regime: str                         # normal | stress_alto | stress_extremo
    stress_components: dict             # {move, slope_stress, vel_us2y, breakeven}
    bma_weights: dict                   # pesos finales por modelo
    bma_samples: np.ndarray             # nube completa (1000+ samples)
    comment: str                        # texto interpretable para reporte

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "center": self.center,
            "hdi_lo": self.hdi_lo, "hdi_hi": self.hdi_hi,
            "U": self.U, "regime": self.regime,
            **{f"stress_{k}": v for k, v in self.stress_components.items()},
            **{f"w_{m}": w for m, w in self.bma_weights.items()},
            "comment": self.comment,
        }


# ============================================================================
# Utilidades internas
# ============================================================================
def _hdi(samples, mass):
    s = np.sort(samples); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def _usability_raw(samples, w_max=W_MAX, p_grid=P_GRID):
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = _hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = _hdi(samples, 0.50); return 0.0, lo, hi
    return best_p, best_lo, best_hi


def _usability_gated(samples, stress, w_max=W_MAX,
                     high=STRESS_HIGH, extreme=STRESS_EXTREME):
    U, lo, hi = _usability_raw(samples, w_max)
    if stress is None: return U, lo, hi, "sin_dato"
    if stress >= extreme: return 0.0, lo, hi, "stress_extremo"
    if stress >= high:
        cap = min(U, 0.50)
        if cap < U and cap > 0: lo, hi = _hdi(samples, cap)
        return cap, lo, hi, "stress_alto"
    return U, lo, hi, "normal"


def _percentile_window(series, as_of, lookback=STRESS_LOOKBACK):
    cut = pd.Timestamp(as_of)
    history = series.loc[series.index <= cut]
    if len(history) < lookback: return None
    window = history.iloc[-lookback:]
    return float((window <= window.iloc[-1]).mean())


# ============================================================================
# Modelos individuales del ensemble
# ============================================================================
def _model_nn(target, macro_hist, etf_returns, K):
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=7)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(),
                                   etf_returns, HORIZON_MONTHS, ETF_LABEL)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target.as_of,
                         horizon_months=HORIZON_MONTHS, samples=fwd,
                         center=float(np.median(fwd)))


def _model_naive(as_of, etf_returns):
    sub = etf_returns[etf_returns["label"] == ETF_LABEL].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    history = sub[sub.index <= pd.Timestamp(as_of)]["return_log"].dropna()
    if len(history) < 12: return None
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=HORIZON_MONTHS, replace=True).sum()
                     for _ in range(1000)])
    return ModelForecast(model_name="Naive_boot", as_of=as_of,
                         horizon_months=HORIZON_MONTHS, samples=sims,
                         center=float(np.median(sims)))


# ============================================================================
# Señales externas (cargadas desde cache si existen)
# ============================================================================
def _load_or_fetch_eom(ticker, cache_path, col="close",
                       start=date(2008, 1, 1), end=date(2025, 6, 30)):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")[df.columns[-1]].sort_index()
    df = fetch_etf_history(ticker, period="d", start=start, end=end)
    df["date"] = pd.to_datetime(df["obs_date"])
    use_col = col if col in df.columns else "close"
    s = df.set_index("date")[use_col].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s.index, ticker.replace(".", "_"): s.values})
    out.to_parquet(cache_path, index=False)
    return s


def _load_or_fetch_daily(ticker, cache_path,
                         start=date(2008, 1, 1), end=date(2025, 6, 30)):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")["close"]
    df = fetch_etf_history(ticker, period="d", start=start, end=end)
    df["date"] = pd.to_datetime(df["obs_date"])
    s = df.set_index("date")["close"].dropna().sort_index()
    out = pd.DataFrame({"date": s.index, "close": s.values})
    out.to_parquet(cache_path, index=False)
    return s


def _load_stress_signals():
    return {
        "move":  _load_or_fetch_eom("MOVE.INDX", CACHE_DIR / "move_eom.parquet"),
        "us2y":  _load_or_fetch_eom("US2Y.INDX", CACHE_DIR / "us2y_eom.parquet"),
        "us10y": _load_or_fetch_eom("US10Y.INDX", CACHE_DIR / "us10y_eom.parquet"),
        "us2y_d": _load_or_fetch_daily("US2Y.INDX", CACHE_DIR / "us2y_daily.parquet"),
        "tip":   _load_or_fetch_eom("TIP.US", CACHE_DIR / "tip_eom.parquet",
                                     col="adjusted_close"),
        "ief":   _load_or_fetch_eom("IEF.US", CACHE_DIR / "ief_eom.parquet",
                                     col="adjusted_close"),
    }


def _compute_stress(as_of, signals):
    p_move = _percentile_window(signals["move"], as_of)
    slope = signals["us10y"] - signals["us2y"]
    p_slope_low = _percentile_window(slope, as_of)
    p_slope_stress = (1 - p_slope_low) if p_slope_low is not None else None
    cut = pd.Timestamp(as_of)
    daily_hist = signals["us2y_d"].loc[signals["us2y_d"].index <= cut]
    if len(daily_hist) > 60:
        vel_abs = (daily_hist - daily_hist.shift(60)).abs().resample("ME").last().dropna()
        p_vel = _percentile_window(vel_abs, as_of)
    else:
        p_vel = None
    tip_ief = np.log(signals["tip"] / signals["ief"])
    bei_change = (tip_ief - tip_ief.shift(12)).dropna()
    p_bei = _percentile_window(bei_change, as_of)
    components = {"move": p_move, "slope_stress": p_slope_stress,
                  "vel_us2y": p_vel, "breakeven": p_bei}
    valid = [v for v in components.values() if v is not None]
    stress = max(valid) if valid else None
    return stress, components


# ============================================================================
# Walk-forward de pesos (necesario para reproducir pesos en as_of dado)
# ============================================================================
def _walk_forward_weights(forecasts_per_date, realized, target_idx):
    """Reproduce la secuencia de pesos Iter 3 hasta target_idx inclusive."""
    names = list(forecasts_per_date[0].keys())
    eq_w = {m: 1.0 / len(names) for m in names}
    w_prev = None; w_t = eq_w
    for t in range(target_idx + 1):
        if t < WARMUP_MONTHS:
            w_t = eq_w
        else:
            scores = _crps_scores_up_to(forecasts_per_date, realized, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else eq_w)
            w_t = apply_temporal_smoothing(bma_shrinkage(w_data, alpha=ALPHA),
                                            w_prev, rho=RHO)
        w_prev = w_t
    return w_t


# ============================================================================
# API pública
# ============================================================================
def forecast_lqd(
    as_of: date,
    history_start: date = date(2020, 1, 31),
    macro_start: date = date(2003, 1, 1),
) -> ForecastResult:
    """Forecast LQD a 6 meses con BMA Iter 6.

    Args:
        as_of: fecha de corte (último día del mes recomendado).
        history_start: inicio del walk-forward para reproducir pesos.
        macro_start: inicio del macro_history para NN.

    Returns:
        ForecastResult con centro, HDI, U gated, comentario, etc.
    """
    store = load_master_store()
    macro_hist = build_macro_history(store, start=macro_start, end=as_of)
    etf_ret = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")

    history_dates = pd.date_range(history_start, as_of, freq="ME").date.tolist()
    fps, reals, ds = [], [], []
    for d in history_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
        sub["obs_date"] = pd.to_datetime(sub["obs_date"])
        sub = sub.sort_values("obs_date").set_index("obs_date")
        cut = pd.Timestamp(d); end = cut + pd.DateOffset(months=HORIZON_MONTHS)
        window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
        real = float(window.sum()) if len(window) >= HORIZON_MONTHS - 1 else None
        models = {
            "NN_K10":     _model_nn(target, macro_hist, etf_ret, K=10),
            "NN_K20":     _model_nn(target, macro_hist, etf_ret, K=20),
            "Naive_boot": _model_naive(d, etf_ret),
            "AR1":        model_ar1(d, etf_ret, ETF_LABEL, HORIZON_MONTHS, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        fps.append(models); ds.append(d)
        reals.append(real if real is not None else 0.0)

    if not fps or ds[-1] != as_of:
        raise ValueError(f"No se pudo construir forecasts hasta {as_of}")

    target_idx = len(ds) - 1
    weights = _walk_forward_weights(fps, reals, target_idx)
    bw = BMAWeights(horizon_months=HORIZON_MONTHS, weights=weights,
                    iteration=3, method="shrinkage+smoothing")
    bma_samples = combine_forecasts(fps[target_idx], bw)
    bma_center = combine_centers(fps[target_idx], bw)

    signals = _load_stress_signals()
    stress, components = _compute_stress(as_of, signals)
    U, lo, hi, regime = _usability_gated(bma_samples, stress)

    comment = _build_comment(as_of, bma_center, lo, hi, U, regime, components)
    return ForecastResult(
        as_of=as_of, center=bma_center, hdi_lo=lo, hdi_hi=hi,
        U=int(U * 100), regime=regime, stress_components=components,
        bma_weights=weights, bma_samples=bma_samples, comment=comment,
    )


def _build_comment(as_of, center, lo, hi, U, regime, comps):
    if U == 0:
        return (
            f"[{as_of}] LQD 6m: SISTEMA NO USABLE este mes (régimen {regime}, "
            f"stress combinado {max(v for v in comps.values() if v is not None):.0%}). "
            f"Centro indicativo {center:+.1%}, pero no se debe emitir intervalo "
            f"de confianza al comité."
        )
    high_signals = [k for k, v in comps.items()
                    if v is not None and v >= STRESS_HIGH]
    base = (
        f"[{as_of}] LQD 6m — Centro {center:+.1%}, "
        f"con {int(U*100)}% de confianza estará entre {lo:+.1%} y {hi:+.1%} "
        f"(rango {(hi-lo)*100:.1f}pp)."
    )
    if regime != "normal":
        base += f" Régimen: {regime} (señales en alerta: {', '.join(high_signals)})."
    return base
