"""Ingesta histórica de ETFs desde EODHD (eodhistoricaldata.com).

Cubre los 7 asset classes del Producto B (modelo de retornos esperados):
- BIL.US (Treasury Bills)
- IGLA.LSE (Treasury Notes — londinense)
- LQD.US (Investment Grade)
- GHYG.US (High Yield)
- EMB.US (EM USD Bonds)
- ACWI.US (Global Equity)
- AGG.US (Global Bond Aggregate)

API key vía variable de entorno EODHD_API_KEY.

Endpoint: https://eodhd.com/api/eod/{TICKER}?api_token=...&period=m|d&fmt=json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import requests


EODHD_BASE = "https://eodhd.com/api/eod"

# Catálogo del Producto B
ETFS_PRODUCTO_B = {
    # feature_name del modelo : (ticker EODHD, asset_class, etiqueta)
    "ret_etf_bil":  ("BIL.US",   "Treasury Bills",        "BIL"),
    "ret_etf_igla": ("IGLA.LSE", "Treasury Notes",        "IGLA"),
    "ret_etf_lqd":  ("LQD.US",   "Investment Grade",      "LQD"),
    "ret_etf_ghyg": ("GHYG.US",  "High Yield Bonds",      "GHYG"),
    "ret_etf_emb":  ("EMB.US",   "EM USD Bonds",          "EMB"),
    "ret_etf_acwi": ("ACWI.US",  "Global Equity",         "ACWI"),
    "ret_etf_agg":  ("AGG.US",   "Global Bond Aggregate", "AGG"),
}


def _api_key() -> str:
    key = os.environ.get("EODHD_API_KEY")
    if not key:
        raise RuntimeError(
            "EODHD_API_KEY no está en el entorno. Setear antes de correr: "
            "export EODHD_API_KEY=tu_key"
        )
    return key


def fetch_etf_history(
    ticker: str,
    period: str = "m",            # 'm' = mensual, 'd' = diario
    start: date | None = None,
    end: date | None = None,
    throttle_seconds: float = 0.3,
) -> pd.DataFrame:
    """Baja histórico de un ticker desde EODHD.

    Output: DataFrame con columnas [obs_date, open, high, low, close, adjusted_close, volume].
    """
    params = {
        "api_token": _api_key(),
        "fmt": "json",
        "period": period,
    }
    if start:
        params["from"] = start.isoformat()
    if end:
        params["to"] = end.isoformat()

    url = f"{EODHD_BASE}/{ticker}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Respuesta inesperada para {ticker}: {data}")

    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["obs_date"] = pd.to_datetime(df["date"]).dt.date
    df = df[["obs_date", "open", "high", "low", "close", "adjusted_close", "volume"]]
    time.sleep(throttle_seconds)
    return df


def compute_returns(df: pd.DataFrame, return_type: str = "log") -> pd.Series:
    """Calcula retornos a partir de adjusted_close.

    return_type='log' = retorno logarítmico (recomendado para agregación).
    return_type='simple' = retorno simple (más interpretable).
    """
    import numpy as np
    px = df.sort_values("obs_date")["adjusted_close"]
    if return_type == "log":
        return np.log(px / px.shift(1))
    return px / px.shift(1) - 1


def ingest_all(
    etfs: dict | None = None,
    period: str = "m",
    start: date = date(2018, 1, 1),
    end: date | None = None,
) -> pd.DataFrame:
    """Baja todos los ETFs del Producto B y devuelve un DataFrame long.

    Columns: feature_name, ticker, asset_class, label, obs_date, adjusted_close, return_log.
    """
    etfs = etfs or ETFS_PRODUCTO_B
    frames = []
    for feature, (ticker, asset_class, label) in etfs.items():
        try:
            df = fetch_etf_history(ticker, period=period, start=start, end=end)
            if df.empty:
                print(f"  [{ticker:>10}] sin data")
                continue
            df["return_log"] = compute_returns(df, "log")
            df["feature_name"] = feature
            df["ticker"] = ticker
            df["asset_class"] = asset_class
            df["label"] = label
            frames.append(df[[
                "feature_name", "ticker", "asset_class", "label",
                "obs_date", "adjusted_close", "return_log",
            ]])
            print(f"  [{ticker:>10}] {len(df):>4} obs, {df['obs_date'].min()} -> {df['obs_date'].max()}, "
                  f"ret_med={df['return_log'].median()*100:.2f}%/mes")
        except Exception as e:
            print(f"  [{ticker:>10}] FALLO: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", default="m", choices=["m", "d", "w"])
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("data/external/tasas_mercantil/etfs_producto_b.parquet"),
    )
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None

    print(f"Ingesta EODHD: {len(ETFS_PRODUCTO_B)} ETFs, period={args.period}, desde {start}")
    df = ingest_all(period=args.period, start=start, end=end)
    if df.empty:
        print("[FAIL] Sin data")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"\n[OK] {args.out}  ({len(df):,} filas)")


if __name__ == "__main__":
    main()
