"""Ingest IGOV, BSJQ, TIP a etfs_producto_b.parquet (idempotente).

Si el ETF ya está en cache con suficiente histórico, no re-descarga.
Schema target (mismo que LQD/EMB):
  feature_name, ticker, asset_class, label, obs_date, adjusted_close, return_log
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

from tasas_mercantil.data.ingest_eodhd import fetch_etf_history


CACHE_PATH = "data/external/tasas_mercantil/etfs_producto_b.parquet"

NEW_ETFS = [
    # (label, ticker EODHD, asset_class)
    ("IGOV", "IGOV.US", "International Treasuries"),
    ("BSJQ", "BSJQ.US", "Short Duration HY"),
    ("TIP",  "TIP.US",  "TIPS"),
]


def main():
    df = pd.read_parquet(CACHE_PATH)
    existing = set(df["label"].unique())
    print(f"Existing labels in cache: {sorted(existing)}")

    new_chunks = []
    for label, ticker, asset_class in NEW_ETFS:
        if label in existing:
            n = (df["label"] == label).sum()
            print(f"  {label}: ya en cache ({n} obs) — skip")
            continue
        print(f"  {label}: descargando {ticker}...")
        raw = fetch_etf_history(ticker, period="m",
                                start=date(2017, 1, 1),
                                end=date(2026, 6, 30))
        if raw.empty:
            print(f"    ✗ EODHD devolvió vacío para {ticker}")
            continue
        # Compute log return on adjusted_close
        raw = raw.sort_values("obs_date").reset_index(drop=True)
        raw["return_log"] = np.log(raw["adjusted_close"] / raw["adjusted_close"].shift(1))
        chunk = pd.DataFrame({
            "feature_name": f"ret_etf_{label.lower()}",
            "ticker": ticker,
            "asset_class": asset_class,
            "label": label,
            "obs_date": raw["obs_date"],
            "adjusted_close": raw["adjusted_close"],
            "return_log": raw["return_log"],
        })
        # match dtypes
        chunk["feature_name"] = chunk["feature_name"].astype("string")
        chunk["ticker"] = chunk["ticker"].astype("string")
        chunk["asset_class"] = chunk["asset_class"].astype("string")
        chunk["label"] = chunk["label"].astype("string")
        print(f"    ✓ {len(chunk)} obs, {chunk['obs_date'].min()} → {chunk['obs_date'].max()}")
        new_chunks.append(chunk)

    if new_chunks:
        out = pd.concat([df] + new_chunks, ignore_index=True)
        out.to_parquet(CACHE_PATH, index=False)
        print(f"\nGuardado: {len(out)} obs total, {sorted(out['label'].unique())}")
    else:
        print("\nNo había nada nuevo que descargar.")


if __name__ == "__main__":
    main()
