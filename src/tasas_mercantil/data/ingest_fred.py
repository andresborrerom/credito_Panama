"""Ingesta FRED y FRED ALFRED (vintage). Stub inicial — implementacion
completa viene en sesion M-0 una vez confirmemos:
- FRED_API_KEY disponible (env var)
- Conectividad de salida hacia api.stlouisfed.org desde el entorno

Patron:
- Series no-vintage (DGS10, DFF, SOFR) -> endpoint `series/observations`
- Series vintage (CPILFESL, PAYEMS) -> endpoint `series/observations` con
  `realtime_start` y `realtime_end` para reconstruir vintage history.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


FRED_BASE_URL = "https://api.stlouisfed.org/fred"


@dataclass(frozen=True)
class FREDConfig:
    api_key: str
    cache_dir: Path = Path("data/external/tasas_mercantil/fred_cache")


def load_config() -> FREDConfig:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FRED_API_KEY no esta en el entorno. "
            "Obtenla gratis en https://fredaccount.stlouisfed.org/apikey "
            "y exportala antes de correr el pipeline."
        )
    return FREDConfig(api_key=api_key)


def fetch_series(
    series_id: str,
    start: date,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja serie no-vintage desde FRED.

    Output: DataFrame con columnas [obs_date, value]. NaN para missing values.
    """
    raise NotImplementedError(
        "Implementar en sesion M-0. Llama a "
        f"{FRED_BASE_URL}/series/observations?series_id={series_id}&..."
    )


def fetch_series_vintage(
    series_id: str,
    start: date,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja TODA la historia de vintages para una serie usando ALFRED.

    Output: DataFrame con columnas [obs_date, value, vintage_date].
    Para cada (obs_date, vintage_date) hay una observacion -- representa
    "lo que se sabia de obs_date al momento de vintage_date".

    Esto es CRITICO para el backtest sin look-ahead.
    """
    raise NotImplementedError(
        "Implementar en sesion M-0. Llama a "
        f"{FRED_BASE_URL}/series/observations con realtime_start/realtime_end."
    )


def ingest_all(features: Iterable[str], start: date, end: date | None = None) -> pd.DataFrame:
    """Orquesta la ingesta de un conjunto de features definidos en features.yaml.

    Devuelve DataFrame consolidado con columnas:
        [feature_name, obs_date, value, vintage_date]

    Compatible con `data/snapshot.py::get_point_in_time`.
    """
    raise NotImplementedError("Implementar en sesion M-0.")
