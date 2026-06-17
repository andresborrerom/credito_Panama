"""Helpers de horizonte operativo para el Producto B (M2).

El comité opera con dos horizontes recurrentes (acordado 2026-06-09):

  1. "Resto del año": desde as_of hasta 31-dic del año en curso.
     Variable según mes — al cierre de junio = 6m, al cierre de septiembre = 3m.
  2. "Próximos 12 meses": fijo en 12m a partir de as_of.

Estos helpers encapsulan la definición para que el motor (forecast_lqd y
futuras forecast_<asset>) reciba siempre un h_months bien definido.
"""
from __future__ import annotations
from datetime import date


def horizon_remaining_year(as_of: date) -> int:
    """Meses desde as_of (fin de mes) hasta 31-dic del año en curso.

    Casos:
      - as_of = 30-jun-2026 → 6 (jul..dic)
      - as_of = 31-mar-2026 → 9 (abr..dic)
      - as_of = 31-ene-2026 → 11
      - as_of = 31-dic-2026 → 0 (ya estamos en diciembre; usar próximos_12m)
    """
    return max(0, 12 - as_of.month)


def horizon_next_12m() -> int:
    """Horizonte fijo de 12 meses."""
    return 12


def both_horizons(as_of: date) -> dict[str, int]:
    """Devuelve los dos horizontes operativos como dict.

    Returns:
        dict con claves "resto_del_anio" y "proximos_12m".
        Si as_of es diciembre, "resto_del_anio" es 0 — el caller debe decidir
        si skipea ese forecast o lo trata como próximos_12m.
    """
    return {
        "resto_del_anio": horizon_remaining_year(as_of),
        "proximos_12m": horizon_next_12m(),
    }


def forecast_lqd_both_horizons(as_of: date, **kwargs) -> dict:
    """Convenience: corre forecast_lqd en los dos horizontes operativos.

    Si "resto_del_anio" es 0 (as_of = diciembre), se skipea ese horizonte y
    se devuelve solo "proximos_12m" — no tiene sentido predecir 0 meses.

    Args:
        as_of: fecha de corte.
        **kwargs: cualquier parámetro adicional de forecast_lqd (w_max,
            sigma_lookback_years, history_start, macro_start).

    Returns:
        dict {horizon_name: ForecastResult}. Las claves son las mismas que
        en both_horizons(), excepto que "resto_del_anio" se omite si es 0.
    """
    from .forecast_api import forecast_lqd

    horizons = both_horizons(as_of)
    out = {}
    for name, h in horizons.items():
        if h == 0:
            continue
        out[name] = forecast_lqd(as_of=as_of, h_months=h, **kwargs)
    return out
