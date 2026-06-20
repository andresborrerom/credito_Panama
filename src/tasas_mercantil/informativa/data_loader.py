"""Loader unificado de datos de mercado para la pieza informativa.

Combina:
  - `data/external/tasas_mercantil/bloomberg_historico.parquet` (carga
    mensual via plantilla Antulio — datos histórico + último cierre BBG)
  - `data/external/tasas_mercantil/fred_curvas_usa.parquet` (refresh
    automático desde FRED endpoint público — datos al día sin API key)

Para cada feature toma el **dataset con la fecha más reciente** (no
mezcla ambos en la misma serie, así evita inconsistencias por revisiones).

Features que solo están en BBG (no en FRED):
  - SR3_*Q   (futuros SOFR trimestrales — CME no en FRED)
  - SOFR_OIS_*Y (swap OIS — FRED no publica)
  - TERM_SOFR_* (CME Term SOFR — pagado)
  - BE_2Y (FRED no publica T2YIE)
  - USSW*_LIBOR (descontinuados)

Esos se quedan con la última fecha BBG disponible. El L_USA_3 los marca
con la latencia explícita en el footer cuando estén desactualizados.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

BBG = Path("data/external/tasas_mercantil/bloomberg_historico.parquet")
FRED = Path("data/external/tasas_mercantil/fred_curvas_usa.parquet")
BBG_TEMPLATE = Path("data/external/tasas_mercantil/bloomberg_template_v03.parquet")


_SOURCES = [
    ("bbg_template", BBG_TEMPLATE),  # plantilla mensual v0.3 (más reciente para los 47 instrumentos nuevos)
    ("fred",         FRED),          # daily, sin API key
    ("bbg_historico", BBG),          # histórico cargado anteriormente
]


def load_master() -> pd.DataFrame:
    """Combina las 3 fuentes (BBG plantilla v0.3 + FRED + BBG histórico).

    Para cada feature_name, toma el dataset con la fecha más reciente
    (no mezcla filas de fuentes distintas dentro de una serie).
    Devuelve formato long: feature_name | ticker | obs_date | value | source.
    """
    keep = ["feature_name", "ticker", "obs_date", "value", "source"]
    frames: dict[str, pd.DataFrame] = {}
    for name, path in _SOURCES:
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df["obs_date"] = pd.to_datetime(df["obs_date"])
        df = df[keep].copy()
        frames[name] = df

    if not frames:
        raise RuntimeError("Ningún parquet de datos disponible.")

    if len(frames) == 1:
        return next(iter(frames.values()))

    # Por feature_name, elegir la fuente con fecha máxima más reciente
    last_dates = {name: df.groupby("feature_name")["obs_date"].max()
                  for name, df in frames.items()}
    all_feats: set = set()
    for s in last_dates.values():
        all_feats.update(s.index)

    chosen = []
    for f in all_feats:
        best_name, best_date = None, pd.NaT
        for name in frames:
            d = last_dates[name].get(f, pd.NaT)
            if pd.notna(d) and (pd.isna(best_date) or d > best_date):
                best_name, best_date = name, d
        if best_name:
            chosen.append(frames[best_name][
                frames[best_name]["feature_name"] == f])

    return pd.concat(chosen, ignore_index=True)


def freshness_summary() -> pd.DataFrame:
    """Tabla resumen: por feature, qué fuente se usa y a qué fecha llega."""
    df = load_master()
    g = (df.groupby("feature_name")
           .agg(source=("source", "first"),
                last_date=("obs_date", "max"),
                n=("obs_date", "size"))
           .reset_index()
           .sort_values("feature_name"))
    return g
