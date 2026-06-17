"""Ingest A.1.3 — extras EODHD para deck Fase 1 USA.

Aprovecha el plan EODHD ilimitado del environment para descargar:

1. UST 1M y 7Y (cierra la curva entera: 1M, 3M, 6M, 1Y, 2Y, 5Y, 7Y, 10Y, 30Y)
2. Economic events USA — mensual (FOMC, Fed speakers, NFP, CPI, PCE, ISM,
   Treasury auctions, etc.) con actual/previous/estimate
3. News macro filtradas por tags fed/fomc/treasury/rate/inflation/powell

Todo persistido en data/external/tasas_mercantil/. Idempotente.
"""
from __future__ import annotations
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests


CACHE = Path("data/external/tasas_mercantil")
EODHD_BASE = "https://eodhd.com/api"
API = os.environ.get("EODHD_API_TOKEN") or os.environ.get("EODHD_API_KEY")


def _get(path: str, params: dict | None = None, timeout: int = 30):
    p = {"api_token": API, "fmt": "json"}
    if params: p.update(params)
    r = requests.get(f"{EODHD_BASE}/{path}", params=p, timeout=timeout)
    r.raise_for_status()
    return r.json()


def ingest_ust_extras():
    """US1M y US7Y EOM yields."""
    targets = [
        ("US1M.INDX", "us1m_eom.parquet", "US1M_INDX"),
        ("US7Y.INDX", "us7y_eom.parquet", "US7Y_INDX"),
    ]
    for ticker, fname, col in targets:
        path = CACHE / fname
        if path.exists():
            print(f"  {ticker:14s} → ya existe, skip")
            continue
        try:
            data = _get(f"eod/{ticker}", {"period": "d", "from": "2010-01-01"})
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            s = df.set_index("date")["close"].resample("ME").last().dropna()
            out = pd.DataFrame({"date": s.index, col: s.values})
            out.to_parquet(path, index=False)
            print(f"  {ticker:14s} → {len(out)} filas EOM, last={out[col].iloc[-1]:.3f}")
        except Exception as e:
            print(f"  {ticker:14s} → ERROR: {str(e)[:80]}")
        time.sleep(0.5)


def ingest_economic_events_us(months: list[str]):
    """Calendario USA mes a mes. Un parquet por mes (idempotente)."""
    cal_dir = CACHE / "economic_events_us"
    cal_dir.mkdir(exist_ok=True)

    for ym in months:
        path = cal_dir / f"{ym}.parquet"
        if path.exists():
            print(f"  events {ym} → ya existe, skip")
            continue
        y, m = ym.split("-")
        last = 28 if m == "02" else (30 if m in ["04","06","09","11"] else 31)
        try:
            data = _get("economic-events", {
                "from": f"{ym}-01", "to": f"{ym}-{last}",
                "country": "US", "limit": 1000,
            })
            if not isinstance(data, list):
                print(f"  events {ym} → respuesta no-list, skip")
                continue
            df = pd.DataFrame(data)
            df.to_parquet(path, index=False)
            print(f"  events {ym} → {len(df)} eventos")
        except Exception as e:
            print(f"  events {ym} → ERROR: {str(e)[:80]}")
        time.sleep(0.5)


def ingest_news_macro_us():
    """News macro USA por tag. Rolling: cada corrida sobrescribe."""
    path = CACHE / "news_macro_us.parquet"
    all_news = []
    seen_titles = set()
    tags = ["fed", "fomc", "treasury", "rate", "inflation", "powell"]
    for tag in tags:
        try:
            data = _get("news", {"t": tag, "limit": 80,
                                  "from": "2026-05-01", "to": "2026-06-30"})
            if not isinstance(data, list):
                continue
            for n in data:
                t = n.get("title")
                if not t or t in seen_titles: continue
                seen_titles.add(t)
                n["_tag"] = tag
                all_news.append(n)
            print(f"  news tag '{tag}' → {len(data)} crudo, {len(seen_titles)} acumuladas")
        except Exception as e:
            print(f"  news tag '{tag}' → ERROR: {str(e)[:80]}")
        time.sleep(0.5)

    if all_news:
        df = pd.DataFrame(all_news)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        df.to_parquet(path, index=False)
        print(f"  ✓ {len(df)} noticias únicas guardadas en {path.name}")


def main():
    if not API:
        raise SystemExit("EODHD_API_TOKEN no está configurado en el environment")
    CACHE.mkdir(parents=True, exist_ok=True)

    print("=== 1) Cierre de curva: US1M, US7Y EOM ===")
    ingest_ust_extras()

    print("\n=== 2) Economic events USA (mensual) ===")
    # Histórico 2024 + corriente + próximo
    months = [f"2024-{m:02d}" for m in range(1, 13)] \
        + [f"2025-{m:02d}" for m in range(1, 13)] \
        + [f"2026-{m:02d}" for m in range(1, 13)]
    ingest_economic_events_us(months)

    print("\n=== 3) News macro USA (rolling) ===")
    ingest_news_macro_us()

    print(f"\n✅ Ingest extras completo. Cache: {CACHE}")


if __name__ == "__main__":
    main()
