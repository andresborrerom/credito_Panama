"""Pieza A — Implied path Fed Funds desde futuros SOFR (SR3) / EuroDollar (ED).

v0.1.0: implied puro, sin risk premium term-structure.
v0.2.0 (futuro): suma risk premium Cieslak-Povala u otro.

Convencion:
- SR3 (3-month SOFR future): el contrato del trimestre n cubre la tasa
  promedio del trimestre que termina en el 3er miercoles del mes del contrato.
- EuroDollar (pre-SOFR): mismo convention con LIBOR 3M.
- implied_rate = 100 - price.

Para horizontes del modelo:
- 1M: SFR1 (proximo vencimiento, cubre 0-3M).
- 3M: SFR1.
- 6M: promedio(SFR1, SFR2).
- 12M: promedio(SFR3, SFR4).
- 24M: promedio(SFR7, SFR8).

Esta es la aproximacion baseline. Iteracion v0.2 hace interpolacion lineal
contra fechas IMM reales.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ...data.store import MasterStore
from ...data.queries import get_implied_path_strip, get_fed_funds_snapshot


MODEL_VERSION = "0.1.0"


@dataclass
class ImpliedPathPrediction:
    """Prediccion de la Pieza A para una as_of_date dada."""
    as_of: date
    fed_funds_now: float
    family: str  # "SR3" o "ED"
    forecast_1m: float | None
    forecast_3m: float | None
    forecast_6m: float | None
    forecast_12m: float | None
    forecast_24m: float | None
    strip: pd.DataFrame  # el strip completo usado
    model_version: str = MODEL_VERSION
    notes: str = ""


def _avg(*xs) -> float | None:
    valid = [x for x in xs if x is not None and not pd.isna(x)]
    return sum(valid) / len(valid) if valid else None


def compute_implied_path(store: MasterStore, as_of: date) -> ImpliedPathPrediction:
    """Calcula el implied path Fed Funds en `as_of`.

    Args:
        store: MasterStore cargado.
        as_of: fecha del corte.

    Returns:
        ImpliedPathPrediction con horizontes {1M, 3M, 6M, 12M, 24M}.

    Raises:
        ValueError: si no hay strip disponible (muy raro, pre-1986).
    """
    strip = get_implied_path_strip(store, as_of)
    if strip.empty:
        raise ValueError(f"No hay strip de futuros disponible a {as_of}")

    family = strip["family"].iloc[0]

    # Mapeo n -> implied_rate
    rate_by_n = dict(zip(strip["n"], strip["implied_rate"]))

    forecast_1m  = rate_by_n.get(1)
    forecast_3m  = rate_by_n.get(1)
    forecast_6m  = _avg(rate_by_n.get(1), rate_by_n.get(2))
    forecast_12m = _avg(rate_by_n.get(3), rate_by_n.get(4))
    forecast_24m = _avg(rate_by_n.get(7), rate_by_n.get(8))

    # Tasa actual: para fed funds usamos midpoint del target (post-2008) o el
    # target unique (pre-2008). Si no hay target, usamos effective.
    fed = get_fed_funds_snapshot(store, as_of)
    fed_now = (fed.get("target_midpoint") or
               fed.get("target_unique") or
               fed.get("effective"))

    return ImpliedPathPrediction(
        as_of=as_of,
        fed_funds_now=fed_now,
        family=family,
        forecast_1m=forecast_1m,
        forecast_3m=forecast_3m,
        forecast_6m=forecast_6m,
        forecast_12m=forecast_12m,
        forecast_24m=forecast_24m,
        strip=strip,
        notes=f"v{MODEL_VERSION} implied puro sin risk premium. {family} strip.",
    )


def predict_to_frame(pred: ImpliedPathPrediction) -> pd.DataFrame:
    """Aplanar prediccion a DataFrame de una fila."""
    return pd.DataFrame([{
        "as_of": pred.as_of,
        "model": "rival_implied",
        "model_version": pred.model_version,
        "fed_funds_now": pred.fed_funds_now,
        "forecast_1m": pred.forecast_1m,
        "forecast_3m": pred.forecast_3m,
        "forecast_6m": pred.forecast_6m,
        "forecast_12m": pred.forecast_12m,
        "forecast_24m": pred.forecast_24m,
        "family": pred.family,
        "notes": pred.notes,
    }])
