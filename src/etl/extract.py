"""Descarga raw de los endpoints Latinex + UST. Guarda JSON crudo con timestamp."""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.etl import endpoints as E  # noqa: E402

RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": E.UA, "Accept": "application/json,*/*"}


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def get_json(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return r.json()


def save(name: str, payload) -> pathlib.Path:
    out = RAW / f"{name}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False))
    return out


def fetch_all() -> dict[str, str]:
    stamp = datetime.now(timezone.utc).isoformat()
    log: dict[str, str] = {"timestamp": stamp}

    jobs = [
        ("emisiones_activas", E.EMISIONES_ACTIVAS, None),
        ("transacciones_10y", E.TRANSACCIONES, {"rango": "10Y"}),
        ("volumen_emisor", E.VOLUMEN_EMISOR, None),
        ("ofertas_home", E.OFERTAS_HOME, None),
        ("emisiones_sostenibles", E.EMISIONES_SOSTENIBLES, None),
        ("emisiones_tramites", E.EMISIONES_TRAMITES, None),
        ("emisiones_prospectos", E.EMISIONES_PROSPECTOS, None),
        ("ranking_creadores", E.RANKING_CREADORES, None),
        ("hechos_relevantes", E.HECHOS_RELEVANTES, None),
        ("emisiones_nuevas", E.EMISIONES_NUEVAS, {"rango": "1Y"}),
    ]

    for name, url, params in jobs:
        try:
            data = get_json(url, params)
            p = save(name, data)
            n = len(data.get("data", [])) if isinstance(data, dict) else len(data)
            log[name] = f"OK {n} rows -> {p.relative_to(ROOT)}"
            print(f"[OK]   {name:32s} {n:>7,} rows")
        except Exception as exc:
            log[name] = f"ERR {exc}"
            print(f"[ERR]  {name}: {exc}")

    # US Treasury yields desde 2015 (cubre nuestra ventana 10y)
    ust_years = list(range(2015, datetime.now().year + 1))
    ust_payload = {}
    for y in ust_years:
        try:
            r = requests.get(E.US_TREASURY_YIELDS.format(year=y), headers=HEADERS, timeout=60)
            r.raise_for_status()
            ust_payload[y] = r.text
            entries = r.text.count("<entry>")
            print(f"[OK]   ust_{y:<27d} {entries:>7,} entries")
        except Exception as exc:
            print(f"[ERR]  ust_{y}: {exc}")
            log[f"ust_{y}"] = f"ERR {exc}"
    save("ust_yields_raw", ust_payload)
    log["ust_yields"] = f"OK {len(ust_payload)} years"

    (RAW / "_manifest.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
    return log


if __name__ == "__main__":
    fetch_all()
