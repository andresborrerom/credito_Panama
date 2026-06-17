"""Pieza B — Taylor rule clásica (1993) con smoothing Fed.

v0.2.0: Taylor vanilla con coeficientes fijos. v0.3.0 (futuro): bayesiana con
prior centrado en Taylor 1993.

Fórmula:
    r_taylor(t) = r* + π(t) + 0.5*(π(t) - π*) + 0.5*output_gap(t)

donde:
    r*           = real neutral rate (asumimos 0.5%)
    π*           = inflation target (Fed: 2.0%)
    π(t)         = PCE core YoY a t (vintage point-in-time)
    output_gap   = -2 * (U-3(t) - NAIRU) [Okun]
    NAIRU        = 4.0% (asumimos)

Simplificando:
    r_taylor = 3.5 + 1.5*π - U-3

Smoothing Fed: la Fed no salta a r_taylor instantáneamente. Forma:
    r_path(h_meses) = ρ^(h/12) * r_now + (1 - ρ^(h/12)) * r_taylor_h
    ρ = 0.80 (smoothing anual típico Fed)

Para forecast en horizonte h:
    π_h = breakeven 5Y (inflación esperada mercado)
    U-3_h = U-3_now * ρ_u^h + NAIRU * (1 - ρ_u^h)  [reversión suave]
    ρ_u = 0.95 (U-3 mensual persistente)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from ...data.store import MasterStore
from ...data.queries import get_fed_funds_snapshot


MODEL_VERSION = "0.2.0"

# Parametros Taylor (constantes default)
R_STAR_DEFAULT = 0.5  # real neutral rate (%) si no hay R* dinamico
PI_STAR = 2.0         # inflation target (%)
NAIRU = 4.0           # natural rate U-3 (%)
RHO_FED = 0.80        # smoothing anual Fed
RHO_U3 = 0.95         # persistencia U-3 mensual

# Compat: alias para codigo legacy
R_STAR = R_STAR_DEFAULT


def get_r_star_dynamic(store, as_of: date) -> float | None:
    """R*(t) proxy = Cleveland Fed Real Interest Rate 10Y horizon.

    Source: REAINTRATREARAT10Y (FRED, Cleveland Fed Haubrich-Pennacchi-Ritchken
    model). Es la estimación de mercado del real rate promedio esperado a 10
    años — incluye algo de term premium real (~0.3-0.7%) pero es la proxy
    más limpia disponible vía CSV público.

    Si no hay dato disponible, devuelve None. El caller decide si usar
    R_STAR_DEFAULT como fallback.
    """
    try:
        v = store.get_value("fred_cle_real_rate_10y", as_of)
        if v is not None and not pd.isna(v):
            return float(v)
    except Exception:
        pass
    return None


@dataclass
class TaylorPrediction:
    """Forecast Pieza B para una as_of_date dada."""
    as_of: date
    fed_funds_now: float
    pi_now_pct: float
    u3_now_pct: float
    pi_expected_pct: float | None     # expectativa de inflacion (BE 5Y)
    r_star_used: float                # R* efectivo usado en el cálculo
    r_star_source: str                # "dynamic_cle_fed" | "static_default"
    r_taylor_now: float               # tasa Taylor sin smoothing, en t
    forecast_1m: float
    forecast_3m: float
    forecast_6m: float
    forecast_12m: float
    forecast_24m: float
    model_version: str = MODEL_VERSION


def _yoy_pct(series: pd.Series, as_of: date, months: int = 12) -> float | None:
    """Calcula YoY% al as_of más cercano."""
    if series.empty:
        return None
    sub = series[series.index <= as_of]
    if sub.empty:
        return None
    last = sub.iloc[-1]
    target_date = pd.Timestamp(as_of) - pd.DateOffset(months=months)
    older = sub[sub.index <= target_date.date()]
    if older.empty:
        return None
    return float((last / older.iloc[-1] - 1) * 100)


def _last_value(series: pd.Series, as_of: date) -> float | None:
    if series.empty:
        return None
    sub = series[series.index <= as_of]
    return float(sub.iloc[-1]) if not sub.empty else None


def compute_taylor_rule(
    store: MasterStore,
    as_of: date,
    use_dynamic_r_star: bool = True,
) -> TaylorPrediction:
    """Forecast Fed Funds con Pieza B Taylor rule + smoothing.

    Args:
        store: MasterStore con vintage macro (CPI core, PCE core, UNRATE).
        as_of: fecha de corte (modelo solo ve datos hasta as_of + T3).
        use_dynamic_r_star: si True, usa R*(t) de Cleveland Fed (default).
                           Si False, usa R_STAR_DEFAULT constante.

    Returns:
        TaylorPrediction con horizontes 1M/3M/6M/12M/24M.

    Raises:
        ValueError: si faltan inputs criticos.
    """
    # R* dinámico o estático
    if use_dynamic_r_star:
        r_star = get_r_star_dynamic(store, as_of)
        if r_star is not None:
            r_star_source = "dynamic_cle_fed"
        else:
            r_star = R_STAR_DEFAULT
            r_star_source = "static_default_fallback"
    else:
        r_star = R_STAR_DEFAULT
        r_star_source = "static_default"
    # === Inputs vintage ===
    # PCE core (nivel index) — calcular YoY
    try:
        pce_series = store.get_series("fred_pce_core", as_of=as_of)
        pi_now = _yoy_pct(pce_series, as_of)
    except Exception:
        pi_now = None

    if pi_now is None:
        # Fallback a CPI core
        try:
            cpi_series = store.get_series("fred_cpi_core", as_of=as_of)
            pi_now = _yoy_pct(cpi_series, as_of)
        except Exception:
            pi_now = None

    if pi_now is None:
        raise ValueError(f"Sin inflacion core disponible a {as_of}")

    # U-3
    try:
        u3_series = store.get_series("fred_unemployment", as_of=as_of)
        u3_now = _last_value(u3_series, as_of)
    except Exception:
        u3_now = None

    if u3_now is None:
        raise ValueError(f"Sin U-3 disponible a {as_of}")

    # Fed Funds actual (anchor para smoothing)
    fed = get_fed_funds_snapshot(store, as_of)
    r_now = (fed.get("target_midpoint")
             or fed.get("target_unique")
             or fed.get("effective"))
    if r_now is None:
        raise ValueError(f"Sin Fed Funds actual a {as_of}")

    # Expectativa inflación (breakeven 5Y si disponible; sino pi_now)
    pi_expected = None
    for fname in ["BE_5Y", "fred_be_5y"]:
        try:
            be = store.get_value(fname, as_of)
            if be is not None and not pd.isna(be):
                pi_expected = float(be)
                break
        except Exception:
            continue
    if pi_expected is None:
        pi_expected = pi_now  # fallback

    # === Taylor rule en t ===
    r_taylor_now = r_star + 1.5 * pi_now - u3_now + NAIRU - 0.5 * PI_STAR
    # Sustituyendo NAIRU=4, PI_STAR=2, R_STAR=0.5: r_taylor = 3.5 + 1.5*pi - u3

    # === Forecasts con smoothing ===
    def forecast_at_horizon(h_months: int) -> float:
        # Proyección de variables
        h_years = h_months / 12.0
        # Inflación: revierte a pi_expected
        rho_pi = 0.85  # anual
        pi_h = (rho_pi ** h_years) * pi_now + (1 - rho_pi ** h_years) * pi_expected

        # U-3: revierte a NAIRU
        rho_u_annual = RHO_U3 ** 12  # anualizamos persistencia mensual
        u3_h = (rho_u_annual ** h_years) * u3_now + (1 - rho_u_annual ** h_years) * NAIRU

        # Taylor en h
        r_taylor_h = r_star + 1.5 * pi_h - u3_h + NAIRU - 0.5 * PI_STAR

        # Smoothing Fed
        r_h = (RHO_FED ** h_years) * r_now + (1 - RHO_FED ** h_years) * r_taylor_h
        return float(r_h)

    return TaylorPrediction(
        as_of=as_of,
        fed_funds_now=float(r_now),
        pi_now_pct=float(pi_now),
        u3_now_pct=float(u3_now),
        pi_expected_pct=float(pi_expected) if pi_expected is not None else None,
        r_star_used=float(r_star),
        r_star_source=r_star_source,
        r_taylor_now=float(r_taylor_now),
        forecast_1m=forecast_at_horizon(1),
        forecast_3m=forecast_at_horizon(3),
        forecast_6m=forecast_at_horizon(6),
        forecast_12m=forecast_at_horizon(12),
        forecast_24m=forecast_at_horizon(24),
    )
