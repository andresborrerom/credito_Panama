"""Ingesta histórica FX G10 + DXY desde EODHD.

Catálogo:
  - EURUSD.FOREX  (1 EUR en USD)
  - GBPUSD.FOREX  (1 GBP en USD)
  - JPY.FOREX     (= USDJPY: 1 USD en JPY)
  - CHF.FOREX     (= USDCHF: 1 USD en CHF)
  - DXY.INDX      (Dollar Index ICE)

Persiste en `data/external/tasas_mercantil/fx_g10.parquet` con:
  feature_name | ticker | obs_date | close | source

Uso:
    PYTHONPATH=src EODHD_API_KEY=... python scripts/ingest_a2_eodhd_fx.py
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import os
import time

import pandas as pd
import requests

OUT = Path("data/external/tasas_mercantil/fx_g10.parquet")
EODHD_BASE = "https://eodhd.com/api/eod"

CATALOG = {
    "fx_eurusd": ("EURUSD.FOREX", "EUR/USD"),
    "fx_gbpusd": ("GBPUSD.FOREX", "GBP/USD"),
    "fx_usdjpy": ("JPY.FOREX",    "USD/JPY"),
    "fx_usdchf": ("CHF.FOREX",    "USD/CHF"),
    "fx_dxy":    ("DXY.INDX",     "DXY"),
}

START = "2019-01-01"


def _api_key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if not k:
        raise RuntimeError("EODHD_API_KEY no está en el entorno.")
    return k


def _fetch_one(ticker: str, start: str, end: str, key: str,
               retries: int = 3) -> pd.DataFrame:
    url = f"{EODHD_BASE}/{ticker}"
    params = {"api_token": key, "fmt": "json", "from": start, "to": end,
              "period": "d"}
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or not data:
                raise RuntimeError(f"empty response for {ticker}")
            df = pd.DataFrame(data)
            return df
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed {ticker}: {last_err}")


def main() -> None:
    key = _api_key()
    end = date.today().isoformat()
    rows = []
    for feature, (ticker, _label) in CATALOG.items():
        print(f"fetching {feature} ({ticker})…", flush=True)
        df = _fetch_one(ticker, START, end, key)
        df["obs_date"] = pd.to_datetime(df["date"])
        df = df[["obs_date", "close"]].copy()
        df["feature_name"] = feature
        df["ticker"] = ticker
        df["source"] = "eodhd"
        rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out = out[["feature_name", "ticker", "obs_date", "close", "source"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"\nSaved {len(out):,} rows → {OUT}")
    print(out.groupby("feature_name").agg(
        n=("obs_date", "size"),
        first=("obs_date", "min"),
        last=("obs_date", "max")).to_string())


if __name__ == "__main__":
    main()
