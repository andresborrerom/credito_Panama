"""Queries del dataset Panamá (credito_Panama) para la lámina 6.

El proyecto credito_Panama ya tiene data lista: 84,191 trades con YTM
calculado, spread vs UST y rating proxy. Aquí extraemos snapshots para
el deck mensual.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd


PANAMA_TRADES_PATH = Path("data/processed/trades.parquet")
PANAMA_CURVES_PATH = Path("data/processed/curves_monthly.parquet")


# Buckets canonicos a reportar en el deck
BUCKETS_REPORTE = [
    # (sector, instrumento_clase, bucket_plazo, label_corto)
    ("Gobierno",    "LETRAS DEL TESORO",                "0-1y",  "Tesoro 0-1Y"),
    ("Gobierno",    "NOTAS DEL TESORO",                 "1-3y",  "Tesoro 1-3Y"),
    ("Gobierno",    "NOTAS DEL TESORO",                 "3-5y",  "Tesoro 3-5Y"),
    ("Gobierno",    "BONOS DEL TESORO",                 "5-7y",  "Tesoro 5-7Y"),
    ("Gobierno",    "BONOS DEL TESORO",                 "7-10y", "Tesoro 7-10Y"),
    ("Financiero",  "VALORES COMERCIALES NEGOCIABLES",  "0-1y",  "VCN Fin 0-1Y"),
    ("Financiero",  "BONOS",                            "3-5y",  "Bonos Fin 3-5Y"),
    ("Financiero",  "BONOS HIPOTECARIOS",               "1-3y",  "Bonos Hip 1-3Y"),
    ("Industriales", "BONOS",                           "1-3y",  "Bonos Ind 1-3Y"),
]


@dataclass
class PanamaSnapshot:
    """Snapshot Panamá para una as_of_date dada."""
    as_of: date
    lookback_days: int
    rows: pd.DataFrame  # columnas: label, sector, instrumento_clase, bucket, yield_median, spread_bp_median, percentil_5y, n_trades


def _load_trades() -> pd.DataFrame:
    df = pd.read_parquet(PANAMA_TRADES_PATH)
    df["fecha_d"] = pd.to_datetime(df["fecha_d"]).dt.date
    return df


def _load_curves() -> pd.DataFrame:
    return pd.read_parquet(PANAMA_CURVES_PATH)


def get_panama_snapshot(
    as_of: date,
    lookback_days: int = 60,
    trades: pd.DataFrame | None = None,
    curves: pd.DataFrame | None = None,
) -> PanamaSnapshot:
    """Snapshot de la curva Panamá + buckets clave en `as_of`.

    Calcula:
    - yield mediano por bucket en los últimos `lookback_days`
    - spread mediano vs UST (de la columna precalculada `spread_bp`)
    - percentil histórico 5Y del yield actual vs la serie de `curves_monthly`
    """
    trades = trades if trades is not None else _load_trades()
    curves = curves if curves is not None else _load_curves()

    start = as_of - timedelta(days=lookback_days)
    sub = trades[
        (trades["fecha_d"] >= start) & (trades["fecha_d"] <= as_of)
        & trades["yield_used"].notna()
        & (trades["yield_used"] > 0) & (trades["yield_used"] < 0.30)
    ]

    rows = []
    for sector, instr, bucket, label in BUCKETS_REPORTE:
        sub_b = sub[
            (sub["sector"] == sector)
            & (sub["instrumento_clase"] == instr)
            & (sub["bucket_plazo"] == bucket)
        ]
        if len(sub_b) == 0:
            rows.append({
                "label": label, "sector": sector, "instrumento_clase": instr,
                "bucket_plazo": bucket,
                "yield_median": None, "spread_bp_median": None,
                "percentil_5y": None, "n_trades": 0,
            })
            continue

        y_med = float(sub_b["yield_used"].median()) * 100  # a %
        s_med = sub_b["spread_bp"].median()
        s_med = float(s_med) if pd.notna(s_med) else None

        # Percentil 5Y desde curves_monthly
        ym_start = (pd.Timestamp(as_of) - pd.DateOffset(years=5)).strftime("%Y-%m")
        ym_end = pd.Timestamp(as_of).strftime("%Y-%m")
        hist = curves[
            (curves["sector"] == sector)
            & (curves["instrumento_clase"] == instr)
            & (curves["bucket_plazo"] == bucket)
            & (curves["yyyymm"] >= ym_start)
            & (curves["yyyymm"] <= ym_end)
        ]
        if len(hist) >= 12:
            valores_pct = hist["yield_median"].values * 100
            pct = float((valores_pct <= y_med).mean() * 100)
        else:
            pct = None

        rows.append({
            "label": label, "sector": sector, "instrumento_clase": instr,
            "bucket_plazo": bucket,
            "yield_median": y_med, "spread_bp_median": s_med,
            "percentil_5y": pct, "n_trades": int(len(sub_b)),
        })

    return PanamaSnapshot(
        as_of=as_of,
        lookback_days=lookback_days,
        rows=pd.DataFrame(rows),
    )


# ---------------------------------------------------------------------------
# Curva soberana Panama en N cortes
# ---------------------------------------------------------------------------
TESORO_BUCKETS_CURVE = [
    ("LETRAS DEL TESORO", "0-1y",  0.5),
    ("NOTAS DEL TESORO",  "1-3y",  2.0),
    ("NOTAS DEL TESORO",  "3-5y",  4.0),
    ("BONOS DEL TESORO",  "5-7y",  6.0),
    ("BONOS DEL TESORO",  "7-10y", 8.5),
]


def get_panama_sov_curve(
    as_of: date,
    lookback_days: int = 60,
    trades: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Curva soberana Panamá a `as_of`. DataFrame con [bucket, tenor_years, yield_pct]."""
    trades = trades if trades is not None else _load_trades()
    start = as_of - timedelta(days=lookback_days)
    sub = trades[
        (trades["fecha_d"] >= start) & (trades["fecha_d"] <= as_of)
        & (trades["sector"] == "Gobierno")
        & trades["yield_used"].notna()
        & (trades["yield_used"] > 0) & (trades["yield_used"] < 0.20)
    ]
    out = []
    for instr, bucket, tenor_years in TESORO_BUCKETS_CURVE:
        sub_b = sub[
            (sub["instrumento_clase"] == instr)
            & (sub["bucket_plazo"] == bucket)
        ]
        if len(sub_b) > 0:
            out.append({
                "bucket": bucket,
                "instrumento": instr,
                "tenor_years": tenor_years,
                "yield_pct": float(sub_b["yield_used"].median()) * 100,
                "n_trades": int(len(sub_b)),
            })
    return pd.DataFrame(out)


def get_panama_sov_curves_3cortes(as_of: date, lookback_days: int = 60) -> dict:
    """Devuelve tres curvas: cierre año anterior, cierre mes anterior, hoy."""
    trades = _load_trades()
    ye_anterior = date(as_of.year - 1, 12, 31)
    mes_ant_ts = pd.Timestamp(as_of) - pd.DateOffset(months=1)
    mes_anterior = mes_ant_ts.date()
    return {
        "ye_anterior":   get_panama_sov_curve(ye_anterior, lookback_days, trades),
        "mes_anterior":  get_panama_sov_curve(mes_anterior, lookback_days, trades),
        "as_of":         get_panama_sov_curve(as_of, lookback_days, trades),
    }
