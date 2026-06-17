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


def load_master() -> pd.DataFrame:
    """Concatena BBG + FRED. Para features comunes, conserva el dataset con
    fecha máxima más reciente (no se mezclan filas de los dos en una misma
    serie). Devuelve formato long: feature_name | ticker | obs_date | value
    | source.
    """
    parts = []
    bbg = None
    if BBG.exists():
        bbg = pd.read_parquet(BBG)
        bbg["obs_date"] = pd.to_datetime(bbg["obs_date"])
        # bloomberg_historico tiene cols ['feature_name','ticker','obs_date',
        # 'value','vintage_date','source','sheet']; normalizamos
        keep = ["feature_name", "ticker", "obs_date", "value", "source"]
        bbg = bbg[keep].copy()
        parts.append(bbg)

    fred = None
    if FRED.exists():
        fred = pd.read_parquet(FRED)
        fred["obs_date"] = pd.to_datetime(fred["obs_date"])

    if not parts and fred is None:
        raise RuntimeError("Ningún parquet de datos disponible.")

    if fred is None:
        return parts[0]

    if not parts:
        return fred

    # Decidir por feature_name: cuál fuente está más al día
    bbg_last = bbg.groupby("feature_name")["obs_date"].max()
    fred_last = fred.groupby("feature_name")["obs_date"].max()
    all_feats = set(bbg_last.index) | set(fred_last.index)

    chosen = []
    for f in all_feats:
        b_last = bbg_last.get(f, pd.NaT)
        f_last = fred_last.get(f, pd.NaT)
        # Si FRED tiene la feature Y es más reciente (o BBG no la tiene), usar FRED
        if pd.notna(f_last) and (pd.isna(b_last) or f_last >= b_last):
            chosen.append(fred[fred["feature_name"] == f])
        else:
            chosen.append(bbg[bbg["feature_name"] == f])

    out = pd.concat(chosen, ignore_index=True)
    return out


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
