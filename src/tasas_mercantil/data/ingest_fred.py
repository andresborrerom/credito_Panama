"""Ingesta FRED + ALFRED (vintage) via endpoints CSV publicos.

NO requiere API key — los endpoints fred.stlouisfed.org/graph/fredgraph.csv
y alfred.stlouisfed.org/graph/alfredgraph.csv son publicos.

Probado 2026-05-28: HTTP 200 para DGS10 (267 KB CSV) y CPILFESL con vintage_date.

Rate limit: no hay limite documentado para los CSV publicos. La API REST
tiene limite de 120 req/min — aplicamos throttle conservador de 1 req/seg
por respeto a los Terms of Use.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import requests


FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ALFRED_CSV_BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
USER_AGENT = "Mercantil-Tasas-ETL/0.1 (contact: andres.borrerom@gmail.com)"

# Throttle entre requests (segundos). Conservador.
THROTTLE_SECONDS = 1.0


@dataclass(frozen=True)
class FREDConfig:
    cache_dir: Path = Path("data/external/tasas_mercantil/fred_cache")
    throttle_seconds: float = THROTTLE_SECONDS
    user_agent: str = USER_AGENT


def _http_get(url: str, config: FREDConfig) -> str:
    """GET con timeout y user-agent. Lanza si HTTP != 200."""
    resp = requests.get(
        url,
        headers={"User-Agent": config.user_agent},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def fetch_series(
    series_id: str,
    start: date | None = None,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja serie no-vintage desde FRED (endpoint publico CSV).

    Output: DataFrame con columnas:
        [feature_name=series_id, obs_date, value, vintage_date=obs_date]

    Listo para hacer concat con otros features en formato long.
    """
    cfg = config or FREDConfig()

    params = [f"id={series_id}"]
    if start:
        params.append(f"cosd={start.isoformat()}")
    if end:
        params.append(f"coed={end.isoformat()}")
    url = f"{FRED_CSV_BASE}?{'&'.join(params)}"

    text = _http_get(url, cfg)
    time.sleep(cfg.throttle_seconds)

    df = pd.read_csv(
        io.StringIO(text),
        parse_dates=["observation_date"],
    )
    df = df.rename(columns={"observation_date": "obs_date", series_id: "value"})
    # FRED usa "." para missing
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["obs_date"] = df["obs_date"].dt.date
    df["feature_name"] = series_id
    df["vintage_date"] = df["obs_date"]  # no-vintage: vintage == obs
    return df[["feature_name", "obs_date", "value", "vintage_date"]]


def fetch_series_alfred_one_vintage(
    series_id: str,
    vintage_date: date,
    start: date | None = None,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja UN vintage especifico de una serie revisable.

    Output: DataFrame con columnas:
        [feature_name=series_id, obs_date, value, vintage_date=vintage_date]
    """
    cfg = config or FREDConfig()

    params = [f"id={series_id}", f"vintage_date={vintage_date.isoformat()}"]
    if start:
        params.append(f"cosd={start.isoformat()}")
    if end:
        params.append(f"coed={end.isoformat()}")
    url = f"{ALFRED_CSV_BASE}?{'&'.join(params)}"

    text = _http_get(url, cfg)
    time.sleep(cfg.throttle_seconds)

    df = pd.read_csv(io.StringIO(text), parse_dates=["observation_date"])
    # La columna de valor se llama "SERIES_YYYYMMDD"
    value_col = [c for c in df.columns if c != "observation_date"][0]
    df = df.rename(columns={"observation_date": "obs_date", value_col: "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["obs_date"] = df["obs_date"].dt.date
    df["feature_name"] = series_id
    df["vintage_date"] = vintage_date
    return df[["feature_name", "obs_date", "value", "vintage_date"]]


def fetch_series_vintage(
    series_id: str,
    vintage_dates: Sequence[date],
    start: date | None = None,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja MULTIPLES vintages de una serie revisable.

    Itera sobre vintage_dates haciendo una request por vintage. Devuelve
    DataFrame consolidado en formato long.

    Para 190 cortes mensuales × 4 series macro = 760 requests × 1s throttle
    = ~13 minutos. Si se necesita correr mas rapido, considerar paralelismo
    suave con rate limit respetado.
    """
    frames = []
    for vd in vintage_dates:
        try:
            df = fetch_series_alfred_one_vintage(
                series_id, vd, start=start, end=end, config=config
            )
            frames.append(df)
        except requests.HTTPError as e:
            # Algunos vintage_dates podrian no existir (antes del primer release).
            # Lo registramos y seguimos.
            print(f"[WARN] {series_id} @ {vd}: {e}")
    if not frames:
        return pd.DataFrame(columns=["feature_name", "obs_date", "value", "vintage_date"])
    return pd.concat(frames, ignore_index=True)


def ingest_non_vintage_batch(
    feature_to_series: dict[str, str],
    start: date,
    end: date | None = None,
    config: FREDConfig | None = None,
) -> pd.DataFrame:
    """Baja batch de series no-vintage. Mapea series_id de FRED -> feature_name del modelo.

    Args:
        feature_to_series: dict {feature_name_modelo: fred_series_id}
        start, end: rango temporal
        config: FREDConfig opcional

    Output: DataFrame long con todas las series concatenadas.
    """
    frames = []
    for feature_name, series_id in feature_to_series.items():
        df = fetch_series(series_id, start=start, end=end, config=config)
        df["feature_name"] = feature_name  # sobrescribir con el nombre del modelo
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def save_to_parquet(df: pd.DataFrame, out_path: Path) -> None:
    """Guarda en parquet con ordenamiento y dtype consistentes."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["feature_name", "obs_date", "vintage_date"])
    df.to_parquet(out_path, index=False)
    print(f"[OK] {out_path} ({len(df):,} filas)")
