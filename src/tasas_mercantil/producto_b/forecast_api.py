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
  >>> result = forecast_lqd(as_of=date(2024,12,31))            # 6m default
  >>> result_12m = forecast_lqd(as_of=date(2024,12,31), h_months=12)
  >>> print(result.comment)

M1 (2026-06): horizonte generalizado a h_months arbitrario. W_MAX escala √h.
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
DEFAULT_H_MONTHS = 6
WARMUP_MONTHS = 12
ALPHA = 1.0                  # full data-driven (Iter 2)
RHO = 0.95                   # temporal smoothing (Iter 3)
DEFAULT_W_MAX_6M = 0.10      # fallback histórico (M1); reemplazado en M1.5 por σ_h
P_GRID = (0.50, 0.60, 0.70, 0.80, 0.90)
STRESS_HIGH = 0.80           # cap U≤50
STRESS_EXTREME = 0.95        # U=0
STRESS_LOOKBACK = 60         # meses (5 años) — también default para σ_h lookback
# M1.5: w_max anclado al IQR empírico (P75-P25) de retornos h-meses del activo.
# Sin parámetro arbitrario k. Interpretación: "el modelo informa más que mirar
# simplemente el rango intercuartílico histórico observado".

CACHE_DIR = Path("data/external/tasas_mercantil")


def _default_w_max(h_months: int) -> float:
    # Fallback usado solo si no hay datos suficientes para σ_h. En operación
    # normal, w_max sale de _natural_w_max (Ancla 1: escala del propio activo).
    return DEFAULT_W_MAX_6M * float(np.sqrt(h_months / 6.0))


def _rolling_h_returns(etf_returns, label, h_months, as_of,
                       lookback_years=5):
    """Retornos rolling h-meses (log), walk-forward causal hasta as_of.

    Devuelve la serie de retornos h-meses históricos observados (solapados).
    Es la base empírica para anclar σ_h, IQR, y cualquier otra métrica de
    escala natural del activo.
    """
    sub = etf_returns[etf_returns["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    hist = sub.loc[sub.index <= cut, "return_log"].dropna()
    if len(hist) < h_months + 12:
        return None
    rolling_h = hist.rolling(window=h_months).sum().dropna()
    window_months = lookback_years * 12
    if len(rolling_h) > window_months:
        rolling_h = rolling_h.iloc[-window_months:]
    if len(rolling_h) < 12:
        return None
    return rolling_h


def _historical_sigma_h(etf_returns, label, h_months, as_of, lookback_years=5):
    """σ de retornos h-meses solapados — info para contexto, no para w_max."""
    rolling_h = _rolling_h_returns(etf_returns, label, h_months, as_of, lookback_years)
    if rolling_h is None:
        return None
    return float(rolling_h.std(ddof=1))


def _natural_w_max(etf_returns, label, h_months, as_of, lookback_years=5):
    """w_max anclado al IQR empírico de retornos h-meses históricos.

    IQR = P75 − P25 de los retornos rolling h-meses en la ventana lookback.
    Es el "ancho del rango central observado" del activo. Sin parámetros.

    Para distribuciones simétricas unimodales, IQR ≈ HDI 50% empírico — un
    intervalo del modelo más angosto que el IQR aporta info adicional respecto
    a mirar simplemente la dispersión histórica.

    Returns:
        (w_max, sigma_h_for_context). Si no hay datos, fallback √h y NaN.
    """
    rolling_h = _rolling_h_returns(etf_returns, label, h_months, as_of, lookback_years)
    if rolling_h is None:
        return _default_w_max(h_months), float("nan")
    q25, q75 = np.quantile(rolling_h.values, [0.25, 0.75])
    iqr = float(q75 - q25)
    sigma_h = float(rolling_h.std(ddof=1))
    return iqr, sigma_h


# ---------------------------------------------------------------------------
# Vista C — sweet spot endógeno via Kneedle sobre curva (p, width)
# ---------------------------------------------------------------------------
def _kneedle_convex_increasing(x, y):
    """Índice del 'codo' de una curva y(x) convexa creciente.

    Codo = punto de máxima distancia perpendicular BAJO la cuerda que une
    (x[0], y[0]) con (x[-1], y[-1]). En espacio normalizado [0,1]^2, eso es
    argmax(x_n - y_n).
    """
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    x_n = (x - x[0]) / (x[-1] - x[0] + 1e-12)
    y_n = (y - y[0]) / (y[-1] - y[0] + 1e-12)
    return int(np.argmax(x_n - y_n))


def usability_sweet_spot(samples, p_grid=None):
    """Vista C: sweet spot endógeno sin umbrales externos.

    Para la nube `samples`, computa la curva (p, width(p)) para p ∈ p_grid.
    Devuelve el punto Kneedle: máxima ganancia de confianza por pp de ancho.

    Returns:
        dict con: p (confianza óptima), lo, hi (HDI a ese p), width, y la
        curva completa para visualizar.
    """
    if p_grid is None:
        p_grid = np.round(np.arange(0.05, 0.96, 0.05), 2)
    widths, los, his = [], [], []
    for p in p_grid:
        lo, hi = _hdi(samples, float(p))
        widths.append(hi - lo); los.append(lo); his.append(hi)
    widths = np.array(widths)
    idx = _kneedle_convex_increasing(p_grid, widths)
    return {
        "p": float(p_grid[idx]),
        "lo": float(los[idx]),
        "hi": float(his[idx]),
        "width": float(widths[idx]),
        "curve_p": [float(p) for p in p_grid],
        "curve_widths": widths.tolist(),
    }


@dataclass
class ForecastResult:
    as_of: date
    center: float                       # mediana retorno log h-meses
    hdi_lo: float                       # bound bajo HDI U% (Vista A)
    hdi_hi: float                       # bound alto HDI U% (Vista A)
    U: int                              # score usabilidad gated, en %
    regime: str                         # normal | stress_alto | stress_extremo
    stress_components: dict             # {move, slope_stress, vel_us2y, breakeven}
    bma_weights: dict                   # pesos finales por modelo
    bma_samples: np.ndarray             # nube completa (1000+ samples)
    # M1.5 anclajes empíricos (sin umbrales arbitrarios)
    sigma_h: float                      # σ histórico h-meses del activo (escala natural)
    w_max_used: float                   # w_max aplicado para Vista A (=k·σ_h por default)
    sweet_spot: dict                    # Vista C: {p, lo, hi, width, curva (p, widths)}
    comment: str                        # texto interpretable para reporte

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "center": self.center,
            "hdi_lo": self.hdi_lo, "hdi_hi": self.hdi_hi,
            "U": self.U, "regime": self.regime,
            "sigma_h": self.sigma_h, "w_max_used": self.w_max_used,
            "sweet_p": self.sweet_spot["p"],
            "sweet_lo": self.sweet_spot["lo"],
            "sweet_hi": self.sweet_spot["hi"],
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


def _usability_raw(samples, w_max=DEFAULT_W_MAX_6M, p_grid=P_GRID):
    best_p, best_lo, best_hi = 0.0, None, None
    for p in sorted(p_grid):
        lo, hi = _hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        lo, hi = _hdi(samples, 0.50); return 0.0, lo, hi
    return best_p, best_lo, best_hi


def _usability_gated(samples, stress, w_max=DEFAULT_W_MAX_6M,
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
def _model_nn(target, macro_hist, etf_returns, K, h_months, etf_label=ETF_LABEL):
    # exclude_window_months ≥ h+1 evita que el forward window del vecino
    # toque el del target (protección look-ahead).
    nr = find_neighbors(target, macro_hist, K=K,
                        exclude_window_months=max(7, h_months + 1))
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(),
                                   etf_returns, h_months, etf_label)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target.as_of,
                         horizon_months=h_months, samples=fwd,
                         center=float(np.median(fwd)))


def _model_naive(as_of, etf_returns, h_months, etf_label=ETF_LABEL):
    sub = etf_returns[etf_returns["label"] == etf_label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    history = sub[sub.index <= pd.Timestamp(as_of)]["return_log"].dropna()
    if len(history) < 12: return None
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=h_months, replace=True).sum()
                     for _ in range(1000)])
    return ModelForecast(model_name="Naive_boot", as_of=as_of,
                         horizon_months=h_months, samples=sims,
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
    h_months: int = DEFAULT_H_MONTHS,
    w_max: float | None = None,
    sigma_lookback_years: int = 5,
    history_start: date = date(2020, 1, 31),
    macro_start: date = date(2003, 1, 1),
) -> ForecastResult:
    """Forecast LQD a h_months con BMA Iter 6 (M1.5: anchors empíricos).

    Args:
        as_of: fecha de corte (último día del mes recomendado).
        h_months: horizonte en meses (default 6, soporta cualquier int ≥ 1).
        w_max: ancho aceptable para Vista A (rango fijo, max confianza).
            Si None (default), se ancla al IQR empírico de retornos h-meses
            del activo en los últimos sigma_lookback_years años. Sin
            parámetros arbitrarios — es el rango intercuartílico observado.
        sigma_lookback_years: ventana causal para anclar IQR y σ_h.
        history_start: inicio del walk-forward para reproducir pesos BMA.
        macro_start: inicio del macro_history para NN.

    Returns:
        ForecastResult con Vista A (HDI U%, anclado al IQR del activo),
        Vista C (sweet spot endógeno via Kneedle), σ_h del activo para
        contexto, pesos BMA, régimen de stress, etc.
    """
    store = load_master_store()
    macro_hist = build_macro_history(store, start=macro_start, end=as_of)
    etf_ret = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")

    if w_max is None:
        w_max, sigma_h = _natural_w_max(etf_ret, ETF_LABEL, h_months, as_of,
                                         lookback_years=sigma_lookback_years)
    else:
        sigma_h_val = _historical_sigma_h(etf_ret, ETF_LABEL, h_months, as_of,
                                          sigma_lookback_years)
        sigma_h = sigma_h_val if sigma_h_val is not None else float("nan")

    history_dates = pd.date_range(history_start, as_of, freq="ME").date.tolist()
    fps, reals, ds = [], [], []
    skipped_no_real = 0
    for d in history_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
        sub["obs_date"] = pd.to_datetime(sub["obs_date"])
        sub = sub.sort_values("obs_date").set_index("obs_date")
        cut = pd.Timestamp(d); end = cut + pd.DateOffset(months=h_months)
        window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
        real = float(window.sum()) if len(window) >= h_months - 1 else None

        # Sin realized completo no podemos scorear: descartar (excepto el target).
        # Esto evita pesos BMA contaminados por ceros falsos para horizontes largos.
        if real is None and d != as_of:
            skipped_no_real += 1
            continue

        models = {
            "NN_K10":     _model_nn(target, macro_hist, etf_ret, K=10, h_months=h_months),
            "NN_K20":     _model_nn(target, macro_hist, etf_ret, K=20, h_months=h_months),
            "Naive_boot": _model_naive(d, etf_ret, h_months),
            "AR1":        model_ar1(d, etf_ret, ETF_LABEL, h_months, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        fps.append(models); ds.append(d)
        reals.append(real if real is not None else 0.0)

    if not fps or ds[-1] != as_of:
        raise ValueError(f"No se pudo construir forecasts hasta {as_of} con h={h_months}m")

    target_idx = len(ds) - 1
    weights = _walk_forward_weights(fps, reals, target_idx)
    bw = BMAWeights(horizon_months=h_months, weights=weights,
                    iteration=3, method="shrinkage+smoothing")
    bma_samples = combine_forecasts(fps[target_idx], bw)
    bma_center = combine_centers(fps[target_idx], bw)

    signals = _load_stress_signals()
    stress, components = _compute_stress(as_of, signals)
    U, lo, hi, regime = _usability_gated(bma_samples, stress, w_max=w_max)

    sweet = usability_sweet_spot(bma_samples)

    comment = _build_comment(as_of, bma_center, lo, hi, U, regime,
                             components, h_months, sweet)
    return ForecastResult(
        as_of=as_of, center=bma_center, hdi_lo=lo, hdi_hi=hi,
        U=int(U * 100), regime=regime, stress_components=components,
        bma_weights=weights, bma_samples=bma_samples,
        sigma_h=sigma_h, w_max_used=w_max, sweet_spot=sweet,
        comment=comment,
    )


def _build_comment(as_of, center, lo, hi, U, regime, comps, h_months, sweet):
    if U == 0:
        return (
            f"[{as_of}] LQD {h_months}m: SISTEMA NO USABLE este mes (régimen {regime}, "
            f"stress combinado {max(v for v in comps.values() if v is not None):.0%}). "
            f"Centro indicativo {center:+.1%}, pero no se debe emitir intervalo "
            f"de confianza al comité."
        )
    high_signals = [k for k, v in comps.items()
                    if v is not None and v >= STRESS_HIGH]
    base = (
        f"[{as_of}] LQD {h_months}m — Centro {center:+.1%}. "
        f"Vista A (HDI más angosto que IQR histórico del activo): "
        f"{int(U*100)}% confianza, [{lo:+.1%}, {hi:+.1%}] ({(hi-lo)*100:.1f}pp). "
        f"Vista C (sweet spot Kneedle endógeno): "
        f"{int(sweet['p']*100)}% confianza, "
        f"[{sweet['lo']:+.1%}, {sweet['hi']:+.1%}] ({sweet['width']*100:.1f}pp)."
    )
    if regime != "normal":
        base += f" Régimen: {regime} (señales en alerta: {', '.join(high_signals)})."
    return base
