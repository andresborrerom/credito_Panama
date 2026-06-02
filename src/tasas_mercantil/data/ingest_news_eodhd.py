"""Ingesta de news/sentiment desde EODHD para features mensuales del Producto B.

Usa el endpoint /sentiments que devuelve sentiment normalizado diario por símbolo.

Símbolos cubiertos (proxies macro):
- SPY.US  → sentiment general del mercado
- TLT.US  → sentiment sobre bonos largos (sensible a Fed)
- HYG.US  → sentiment sobre high yield (risk appetite)
- LQD.US  → sentiment sobre IG (calidad crediticia)
- GLD.US  → sentiment sobre oro (inflación / risk-off)
- DXY.INDX → sentiment sobre USD

Output: parquet con sentiment diario + features mensuales agregados.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests


EODHD_BASE = "https://eodhd.com/api/sentiments"

SYMBOLS_MACRO = {
    "ret_news_spy":  ("SPY.US",  "Sentiment SPY (mercado general)"),
    "ret_news_tlt":  ("TLT.US",  "Sentiment TLT (UST 20Y+)"),
    "ret_news_hyg":  ("HYG.US",  "Sentiment HYG (HY corporate)"),
    "ret_news_lqd":  ("LQD.US",  "Sentiment LQD (IG corporate)"),
    "ret_news_emb":  ("EMB.US",  "Sentiment EMB (EM USD bonds)"),
    "ret_news_gld":  ("GLD.US",  "Sentiment GLD (oro, hedge inflación)"),
}


def fetch_sentiment_daily(
    symbol: str,
    from_date: date = date(2018, 1, 1),
    to_date: date | None = None,
    throttle_seconds: float = 0.3,
) -> pd.DataFrame:
    """Baja sentiment diario para un símbolo desde EODHD.

    Output: DataFrame con [obs_date, count, normalized].
        normalized: sentiment score [-1, +1] (negativo malo, positivo bueno).
        count: número de noticias del día.
    """
    api_key = os.environ.get("EODHD_API_KEY")
    if not api_key:
        raise RuntimeError("EODHD_API_KEY no está en el entorno")

    params = {
        "api_token": api_key,
        "s": symbol,
        "from": from_date.isoformat(),
    }
    if to_date:
        params["to"] = to_date.isoformat()

    resp = requests.get(EODHD_BASE, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if symbol not in data:
        return pd.DataFrame()
    df = pd.DataFrame(data[symbol])
    if df.empty:
        return df
    df["obs_date"] = pd.to_datetime(df["date"]).dt.date
    df = df[["obs_date", "count", "normalized"]]
    time.sleep(throttle_seconds)
    return df


def ingest_all_macro_symbols(
    from_date: date = date(2018, 1, 1),
    to_date: date | None = None,
) -> pd.DataFrame:
    """Baja sentiment para todos los símbolos macro y devuelve DataFrame long."""
    frames = []
    for feature_name, (symbol, desc) in SYMBOLS_MACRO.items():
        try:
            df = fetch_sentiment_daily(symbol, from_date, to_date)
            if df.empty:
                print(f"  [{symbol:>10}] sin data")
                continue
            df["feature_name"] = feature_name
            df["symbol"] = symbol
            df["description"] = desc
            frames.append(df[["feature_name", "symbol", "description", "obs_date", "count", "normalized"]])
            print(f"  [{symbol:>10}] {len(df):>5} días, "
                  f"{df['obs_date'].min()} → {df['obs_date'].max()}, "
                  f"sent_mean={df['normalized'].mean():+.3f}")
        except Exception as e:
            print(f"  [{symbol:>10}] FALLO: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def aggregate_to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Agrega sentiment diario a features mensuales.

    Features por (símbolo, mes):
    - sentiment_mean: tono promedio
    - sentiment_std: volatilidad intra-mes
    - news_count_total: volumen de cobertura
    - sentiment_change_vs_prev: delta del tono vs mes anterior
    """
    if daily.empty:
        return pd.DataFrame()
    daily = daily.copy()
    daily["yyyymm"] = pd.to_datetime(daily["obs_date"]).dt.to_period("M").dt.to_timestamp()

    agg = daily.groupby(["feature_name", "symbol", "yyyymm"]).agg(
        sentiment_mean=("normalized", "mean"),
        sentiment_std=("normalized", "std"),
        news_count_total=("count", "sum"),
        n_days=("obs_date", "count"),
    ).reset_index()

    # delta vs mes anterior por símbolo
    agg = agg.sort_values(["symbol", "yyyymm"])
    agg["sentiment_change_vs_prev"] = agg.groupby("symbol")["sentiment_mean"].diff()
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default="2018-01-01")
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument(
        "--out-daily",
        type=Path,
        default=Path("data/external/tasas_mercantil/news_sentiment_daily.parquet"),
    )
    ap.add_argument(
        "--out-monthly",
        type=Path,
        default=Path("data/external/tasas_mercantil/news_sentiment_monthly.parquet"),
    )
    args = ap.parse_args()

    from_d = date.fromisoformat(args.from_date)
    to_d = date.fromisoformat(args.to_date) if args.to_date else None

    print(f"Ingesta sentiment EODHD: {len(SYMBOLS_MACRO)} símbolos, desde {from_d}\n")
    daily = ingest_all_macro_symbols(from_d, to_d)
    if daily.empty:
        print("[FAIL] sin data")
        return

    args.out_daily.parent.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(args.out_daily, index=False)
    print(f"\n[OK] daily: {args.out_daily} ({len(daily):,} filas)")

    monthly = aggregate_to_monthly(daily)
    monthly.to_parquet(args.out_monthly, index=False)
    print(f"[OK] monthly: {args.out_monthly} ({len(monthly):,} filas, "
          f"{monthly['yyyymm'].nunique()} meses, {monthly['symbol'].nunique()} símbolos)")


if __name__ == "__main__":
    main()
