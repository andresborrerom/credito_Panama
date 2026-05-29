"""Backfill historico FRED (no-vintage) + ALFRED (vintage macro).

Baja las series macro y de tasas desde 1985-01-01 hasta hoy via los endpoints
CSV publicos (no requiere API key).

Uso:
    python -m src.tasas_mercantil.data.backfill_fred --non-vintage  # ~30 segundos
    python -m src.tasas_mercantil.data.backfill_fred --vintage      # ~10-15 minutos
    python -m src.tasas_mercantil.data.backfill_fred --all
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from .ingest_fred import (
    FREDConfig,
    fetch_series,
    fetch_series_vintage,
)


# Mapeo feature_name modelo -> FRED series_id (no se revisan)
NON_VINTAGE = {
    # Politica monetaria
    "fred_fed_funds_effective":      "DFF",       # 1954+
    "fred_fed_funds_target_pre2008": "DFEDTAR",   # 1982+
    "fred_fed_funds_target_upper":   "DFEDTARU",  # 2008+
    "fred_fed_funds_target_lower":   "DFEDTARL",  # 2008+
    "fred_iorb":                     "IORB",      # 2021+ (nombre actual; antes era IOER)
    "fred_ioer_legacy":              "IOER",      # 2008-2021 (nombre viejo)
    "fred_on_rrp_award":             "RRPONTSYAWARD",  # 2013+ Reverse Repo AWARD RATE (la tasa, en %)
    "fred_on_rrp_volume_usd_b":      "RRPONTSYD", # 2013+ VOLUMEN en USD billion (no es la tasa)
    # UST nominal
    "fred_ust_2y":  "DGS2",
    "fred_ust_5y":  "DGS5",
    "fred_ust_10y": "DGS10",
    "fred_ust_30y": "DGS30",
    # TIPS real
    "fred_tips_5y":  "DFII5",
    "fred_tips_10y": "DFII10",
    "fred_tips_30y": "DFII30",
    # Breakevens
    "fred_be_5y":          "T5YIE",
    "fred_be_10y":         "T10YIE",
    "fred_be_5y5y_forward": "T5YIFR",
    # SOFR
    "fred_sofr":         "SOFR",      # 2018-04+
    "fred_sofr_30d_avg": "SOFR30DAYAVG",
    "fred_sofr_90d_avg": "SOFR90DAYAVG",
    # === Globales — politica monetaria ===
    "fred_ecb_dfr":             "ECBDFR",       # BCE Deposit Facility Rate (daily)
    "fred_ecb_mro":             "ECBMRRFR",     # BCE Main Refi Rate (daily)
    "fred_ecb_estr":            "ECBESTRVOLWGTTRMDMNRT",  # ESTR (overnight)
    "fred_boe_bank_rate":       "IUDSOIA",      # BoE Bank Rate (daily)
    # BoJ: las series FRED estan descontinuadas (call rate hasta 2023, discount rate hasta 2017).
    # Mantener como historico; para el snapshot del mes hay que reportar manualmente.
    "fred_boj_call_rate_hist":  "IRSTCB01JPM156N",
    # === Globales — curvas soberanas 10Y (mensuales) ===
    "fred_bund_10y":            "IRLTLT01DEM156N",
    "fred_gilt_10y":            "IRLTLT01GBM156N",
    "fred_jgb_10y":             "IRLTLT01JPM156N",
    "fred_mexico_10y":          "IRLTLT01MXM156N",
    # === FX ===
    "fred_dxy_broad":           "DTWEXBGS",     # Broad Dollar Index (proxy DXY)
    # === Term premium (Kim-Wright modelo del Fed Board) — Pieza D ===
    "fred_kw_yield_10y":        "THREEFY10",    # KW model 10Y yield
    "fred_kw_tp_10y":           "THREEFYTP10",  # KW term premium 10Y (en %)
    "fred_kw_tp_5y":            "THREEFYTP5",   # KW term premium 5Y
}


# Para vintage (macro con revisiones) iteramos cierres mensuales como vintage_date
VINTAGE_SERIES = {
    "fred_cpi_core":      "CPILFESL",
    "fred_pce_core":      "PCEPILFE",
    "fred_unemployment":  "UNRATE",
    "fred_nonfarm_payrolls": "PAYEMS",
}


def backfill_non_vintage(start: date, out_path: Path) -> None:
    """Baja ~20 series no-vintage. Tarda ~20-30 segundos con throttle 1s."""
    cfg = FREDConfig()
    print(f"Backfill FRED no-vintage: {len(NON_VINTAGE)} series desde {start}")
    frames = []
    for feature, sid in NON_VINTAGE.items():
        try:
            df = fetch_series(sid, start=start, config=cfg)
            df["feature_name"] = feature
            df["source"] = "fred"
            df["ticker"] = sid
            df["sheet"] = "fred_non_vintage"
            frames.append(df[["feature_name", "ticker", "obs_date", "value", "vintage_date", "source", "sheet"]])
            print(f"  [{sid:>15}] {len(df):>6,} filas (feature={feature})")
        except Exception as e:
            print(f"  [{sid:>15}] FALLO: {e}")

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["feature_name", "obs_date"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"\n[OK] {out_path}")
    print(f"     {len(out):,} filas, {out['feature_name'].nunique()} features, "
          f"{out['obs_date'].min()} -> {out['obs_date'].max()}")


def backfill_vintage(start: date, end: date, out_path: Path,
                     vintage_freq: str = "ME") -> None:
    """Baja vintages mensuales (end-of-month) de las 4 series macro.

    vintage_freq="ME" = end of month. Para 1985-2026 son ~500 vintages.
    Con 4 series x 500 = 2000 requests x 1s = ~33 min.

    Si es mucho, usar vintage_freq="QE" (quarterly, ~165 vintages).
    """
    cfg = FREDConfig()
    vintage_dates = pd.date_range(start=start, end=end, freq=vintage_freq).date
    print(f"Backfill FRED vintage: {len(VINTAGE_SERIES)} series x "
          f"{len(vintage_dates)} vintage dates = "
          f"{len(VINTAGE_SERIES) * len(vintage_dates)} requests")
    print(f"Estimado: {len(VINTAGE_SERIES) * len(vintage_dates) * 1.0 / 60:.0f} minutos\n")

    frames = []
    for feature, sid in VINTAGE_SERIES.items():
        print(f"  [{sid}] iniciando...")
        df = fetch_series_vintage(sid, vintage_dates, start=start, config=cfg)
        df["feature_name"] = feature
        df["source"] = "fred_alfred"
        df["ticker"] = sid
        df["sheet"] = "fred_vintage"
        frames.append(df[["feature_name", "ticker", "obs_date", "value", "vintage_date", "source", "sheet"]])
        print(f"  [{sid}] {len(df):,} filas (feature={feature})")

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["feature_name", "obs_date", "vintage_date"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"\n[OK] {out_path}")
    print(f"     {len(out):,} filas, {out['feature_name'].nunique()} features")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--non-vintage", action="store_true", help="Series no-vintage")
    ap.add_argument("--vintage", action="store_true", help="Series vintage macro")
    ap.add_argument("--all", action="store_true", help="Ambos")
    ap.add_argument("--start", default="1985-01-01", help="Fecha inicio (YYYY-MM-DD)")
    ap.add_argument("--end", default="2026-05-29", help="Fecha fin para vintage (YYYY-MM-DD)")
    ap.add_argument("--vintage-freq", default="ME", choices=["ME", "QE", "YE"],
                    help="ME=monthly, QE=quarterly, YE=yearly")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("data/external/tasas_mercantil"))
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.all or args.non_vintage:
        backfill_non_vintage(start, args.out_dir / "fred_non_vintage.parquet")
    if args.all or args.vintage:
        backfill_vintage(start, end,
                          args.out_dir / "fred_vintage_macro.parquet",
                          vintage_freq=args.vintage_freq)


if __name__ == "__main__":
    main()
