"""Ingest A.1.1 — series Fed/SOFR/UST30Y para el deck Fase 1 USA.

Descarga via FRED (endpoint público, sin API key) y persiste en parquets
independientes en data/external/tasas_mercantil/.

Series:
  DFF             — Fed Funds Effective Rate (daily)
  FEDFUNDS        — Fed Funds Rate (monthly average)
  IORB            — Interest on Reserve Balances (daily)
  RRPONTSYD       — Overnight Reverse Repo Operations volume (daily)
  SOFR            — Secured Overnight Financing Rate (daily)
  SOFR30DAYAVG    — SOFR 30-day average (daily)
  SOFR90DAYAVG    — SOFR 90-day average (daily)
  SOFR180DAYAVG   — SOFR 180-day average (daily)
  DGS30           — UST 30Y constant maturity (daily)

Idempotente: si el parquet existe, no re-descarga.
Override de timeout: FRED CSV puede ser lento para series largas.
"""
from __future__ import annotations
import io
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests


CACHE = Path("data/external/tasas_mercantil")
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

SERIES = [
    ("DFF",            "fed_funds_effective_daily"),
    ("FEDFUNDS",       "fed_funds_monthly"),
    ("IORB",           "iorb_daily"),
    ("RRPONTSYD",      "rrp_operations_daily"),
    ("SOFR",           "sofr_overnight_daily"),
    ("SOFR30DAYAVG",   "sofr_30d_avg_daily"),
    ("SOFR90DAYAVG",   "sofr_90d_avg_daily"),
    ("SOFR180DAYAVG",  "sofr_180d_avg_daily"),
    ("DGS30",          "us30y_daily"),
]


def fetch_one(series_id: str, start: date, end: date,
              read_timeout: int = 120) -> pd.DataFrame:
    """Fetch directo con timeout largo + 3 retries con backoff."""
    url = f"{FRED_CSV}?id={series_id}&cosd={start.isoformat()}&coed={end.isoformat()}"
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (tasas_mercantil ingest)"},
                timeout=(10, read_timeout),
            )
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns={df.columns[0]: "obs_date",
                                     df.columns[1]: "value"})
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna(subset=["value"])
            df["obs_date"] = pd.to_datetime(df["obs_date"])
            return df
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            time.sleep(2 ** attempt)
    raise last_exc


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    start = date(2010, 1, 1)
    end = date(2025, 12, 31)

    print(f"Ingest FRED: {len(SERIES)} series ({start} → {end})\n")
    for series_id, fname in SERIES:
        path = CACHE / f"{fname}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            print(f"  {series_id:16s} → ya existe ({len(df)} filas) — skip")
            continue
        try:
            df = fetch_one(series_id, start, end)
            if df.empty:
                print(f"  {series_id:16s} → vacío, skip")
                continue
            out = df[["obs_date", "value"]].rename(
                columns={"obs_date": "date", "value": series_id}
            )
            out.to_parquet(path, index=False)
            print(f"  {series_id:16s} → {len(out)} filas, "
                  f"{out['date'].min().date()} → {out['date'].max().date()}, "
                  f"last={out[series_id].iloc[-1]:.3f}")
        except Exception as e:
            print(f"  {series_id:16s} → ERROR: {str(e)[:80]}")
        time.sleep(1.0)   # throttle entre series

    print(f"\n✅ Ingest completo. Cache: {CACHE}")


if __name__ == "__main__":
    main()
