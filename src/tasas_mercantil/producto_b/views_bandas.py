"""Output (1) — 7 vistas de bandas de confianza del portafolio LUZ.

Todas las vistas se computan de la misma nube MC del portafolio agregado.
El comité elige cuál ver en cada lámina; el motor entrega todas listas.

  1. Vista A — fijar rango (=IQR de la nube), max confianza
  2. Vista B — fijar confianza (default 80%), min rango (HDI)
  3. Vista C — sweet spot endógeno via Kneedle
  4. Fan chart — HDIs a 50% / 80% / 95% (estilo Bank of England)
  5. Direccional — P(retorno > 0), P(retorno > tasa libre riesgo)
  6. VaR 95 — "95% del tiempo no perdés más de X%"
  7. CVaR/ES 95 — "si te toca el peor 5%, perdés en promedio X%"

Bonus:
  - quantiles: tabla fija P5/P25/P50/P75/P95
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .forecast_api import _hdi, usability_sweet_spot, CACHE_DIR
from .portfolio_aggregator import forecast_luz_portfolio, PortfolioForecast


P_GRID_VISTA_A = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def _vista_A(samples: np.ndarray, w_max: float) -> dict | None:
    """Vista A: HDI más amplio cuyo ancho ≤ w_max. None si ninguno cabe."""
    best_p = 0.0
    best_lo = best_hi = None
    for p in sorted(P_GRID_VISTA_A):
        lo, hi = _hdi(samples, p)
        if (hi - lo) <= w_max:
            best_p, best_lo, best_hi = p, lo, hi
    if best_p == 0.0:
        return None
    return {"p": float(best_p), "lo": float(best_lo), "hi": float(best_hi),
            "width": float(best_hi - best_lo)}


def _vista_B(samples: np.ndarray, p_fixed: float = 0.80) -> dict:
    """Vista B: HDI al nivel de confianza fijo p_fixed."""
    lo, hi = _hdi(samples, p_fixed)
    return {"p": float(p_fixed), "lo": float(lo), "hi": float(hi),
            "width": float(hi - lo)}


def _fan_chart(samples: np.ndarray) -> dict:
    """HDIs anidados al 50%, 80%, 95% para fan chart."""
    out = {}
    for p in (0.50, 0.80, 0.95):
        lo, hi = _hdi(samples, p)
        out[f"hdi_{int(p*100)}"] = {"p": float(p), "lo": float(lo),
                                     "hi": float(hi), "width": float(hi - lo)}
    return out


def _directional(samples: np.ndarray, rf_rate: float) -> dict:
    return {
        "p_positive": float(np.mean(samples > 0)),
        "p_above_rf": float(np.mean(samples > rf_rate)),
        "rf_rate": float(rf_rate),
    }


def _var_at_level(samples: np.ndarray, level: float = 0.95) -> dict:
    """VaR al nivel especificado. VaR 95 = P5 (cola izquierda)."""
    q = (1 - level) * 100
    return {"level": float(level), "var": float(np.percentile(samples, q))}


def _cvar_at_level(samples: np.ndarray, level: float = 0.95) -> dict:
    """CVaR/ES: mean de samples en la cola más allá del VaR."""
    q = (1 - level) * 100
    threshold = np.percentile(samples, q)
    tail = samples[samples <= threshold]
    es = float(np.mean(tail)) if len(tail) > 0 else float(threshold)
    return {"level": float(level), "var": float(threshold), "cvar": es}


def _quantiles(samples: np.ndarray) -> dict:
    qs = (5, 25, 50, 75, 95)
    return {f"p{q}": float(np.percentile(samples, q)) for q in qs}


def _risk_free_rate(as_of: date, h_months: int) -> float:
    """Tasa libre de riesgo para el horizonte: US3M anual al as_of × h/12."""
    df = pd.read_parquet(Path(CACHE_DIR) / "us3m_eom.parquet")
    s = df.set_index("date").iloc[:, 0].sort_index()
    cut = pd.Timestamp(as_of)
    hist = s.loc[s.index <= cut].dropna()
    if hist.empty:
        return 0.0
    y_now_pp = float(hist.iloc[-1])
    return (y_now_pp / 100.0) * (h_months / 12.0)


def forecast_luz_all_views(
    as_of: date,
    h_months: int,
    w_max: float | None = None,
    p_fixed_vista_B: float = 0.80,
    portfolio_forecast: PortfolioForecast | None = None,
) -> dict:
    """Devuelve las 7 vistas + cuantiles del portafolio LUZ.

    Args:
        as_of: fecha de corte.
        h_months: horizonte.
        w_max: ancho para Vista A. Si None, se ancla al IQR de la nube
            (P75-P25 de los samples del portafolio).
        p_fixed_vista_B: nivel de confianza fijo para Vista B (default 80%).
        portfolio_forecast: si ya lo computaste, pasalo para evitar re-correr
            el motor (~15 min ahorrados).

    Returns:
        dict con: meta, vista_A, vista_B, vista_C, fan_chart, directional,
        var, cvar, quantiles.
    """
    pf = portfolio_forecast or forecast_luz_portfolio(as_of, h_months)
    s = pf.samples

    if w_max is None:
        q25, q75 = np.percentile(s, [25, 75])
        w_max = float(q75 - q25)

    rf = _risk_free_rate(as_of, h_months)

    return {
        "meta": {
            "as_of": as_of, "h_months": h_months,
            "center": pf.center,
            "coverage_directa": pf.coverage_directa,
            "coverage_proxy": pf.coverage_proxy,
            "coverage_cash": pf.coverage_cash,
            "worst_regime": pf.worst_regime,
            "w_max_used_iqr_portfolio": w_max,
            "n_samples": len(s),
        },
        "vista_A": _vista_A(s, w_max),
        "vista_B": _vista_B(s, p_fixed_vista_B),
        "vista_C": pf.sweet_spot,
        "fan_chart": _fan_chart(s),
        "directional": _directional(s, rf),
        "var": _var_at_level(s, 0.95),
        "cvar": _cvar_at_level(s, 0.95),
        "quantiles": _quantiles(s),
    }
