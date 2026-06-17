"""Ingesta automática de curvas USA desde FRED (sin API key, endpoints públicos).

Independiza el deck de la plantilla Bloomberg para los datos diarios:
  - Curva UST CMT (1M a 30Y) — features UST_*
  - Curva TIPS real (5Y a 30Y) — features TIPS_*
  - Breakeven inflation (5Y, 10Y, 30Y) — features BE_*
  - SOFR overnight — feature SOFR_ON
  - Fed Funds target bracket (IORB y target ranges)

Los datos que FRED no publica (SR3 strip de futuros, swap OIS) se mantienen
del bloomberg_historico.parquet con la fecha que tengan (último cierre de
la plantilla que entregó Antulio). El L_USA_3 los usa al último valor
disponible — desactualización máxima ~1 mes.

Output: `data/external/tasas_mercantil/fred_curvas_usa.parquet` en formato
long compatible con bloomberg_historico.parquet.

Uso:
    PYTHONPATH=src python scripts/ingest_a3_fred_curvas.py
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import pandas as pd

from tasas_mercantil.data.ingest_fred import fetch_series, FREDConfig

OUT = Path("data/external/tasas_mercantil/fred_curvas_usa.parquet")

# Mapeo FRED → feature_name del proyecto
MAPPING = {
    # UST CMT
    "DGS1MO": "UST_1M",
    "DGS3MO": "UST_3M",
    "DGS6MO": "UST_6M",
    "DGS1":   "UST_1Y",
    "DGS2":   "UST_2Y",
    "DGS3":   "UST_3Y",
    "DGS5":   "UST_5Y",
    "DGS7":   "UST_7Y",
    "DGS10":  "UST_10Y",
    "DGS20":  "UST_20Y",
    "DGS30":  "UST_30Y",
    # TIPS reales
    "DFII5":  "TIPS_5Y",
    "DFII10": "TIPS_10Y",
    "DFII20": "TIPS_20Y",
    "DFII30": "TIPS_30Y",
    # Breakeven (FRED no publica T2YIE — BE_2Y queda con BBG último)
    "T5YIE":  "BE_5Y",
    "T10YIE": "BE_10Y",
    "T30YIE": "BE_30Y",
    # SOFR overnight
    "SOFR":   "SOFR_ON",
    # Fed funds + IORB
    "DFF":               "EFFR",
    "IORB":              "IORB",
    "DFEDTARU":          "FED_FUNDS_UPPER",
    "DFEDTARL":          "FED_FUNDS_LOWER",
}

START = date(2018, 1, 1)


def main() -> None:
    cfg = FREDConfig()
    rows = []
    for series_id, feature in MAPPING.items():
        print(f"fetching {series_id} → {feature}…", flush=True)
        try:
            df = fetch_series(series_id, start=START, config=cfg)
            df["feature_name"] = feature
            df["source"] = "fred"
            df["ticker"] = series_id
            rows.append(df[["feature_name", "ticker", "obs_date",
                            "value", "source"]])
        except Exception as e:
            print(f"  FALLÓ {series_id}: {e}")

    if not rows:
        raise RuntimeError("Ningún feature descargado.")

    out = pd.concat(rows, ignore_index=True)
    out["obs_date"] = pd.to_datetime(out["obs_date"])
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["value"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"\nGuardado {len(out):,} filas → {OUT}")
    print(out.groupby("feature_name").agg(
        n=("obs_date", "size"),
        first=("obs_date", "min"),
        last=("obs_date", "max")).to_string())


if __name__ == "__main__":
    main()
