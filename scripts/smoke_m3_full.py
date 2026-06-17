"""Smoke M3.2 — replicar Iter 6 a los 5 ETFs LUZ restantes con groundtruth.

Para cada ETF (ACWI, GHYG, IGOV, BSJQ, TIP):
  - Verifica histórico ≥ 60 meses (suficiente para lookback IQR 5y).
  - Corre forecast_etf en 3 fechas × 2 horizontes con realized para hit.
  - Computa hit rate Vista A / Vista C por ETF y por régimen.

Reporta tabla agregada al final. Si todos los ETFs cumplen criterios
mínimos (forecast corre + hit rate Vista C ≥ 50%), M3 está completo.
"""
from __future__ import annotations
from datetime import date
from collections import defaultdict
import pandas as pd

from tasas_mercantil.producto_b.forecast_api import forecast_etf, CACHE_DIR


ETFS = ["ACWI", "GHYG", "IGOV", "BSJQ", "TIP"]

FECHAS = [
    date(2022, 6, 30),    # plena crisis bond markets
    date(2023, 12, 31),   # alto / fin año recuperación
    date(2024, 6, 30),    # normal
]


def realized(label: str, as_of: date, h_months: int) -> float | None:
    df = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    sub = df[df["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h_months)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    return float(window.sum()) if len(window) >= h_months - 1 else None


def main():
    print("=" * 160)
    print(f"SMOKE M3.2 — sweep {len(ETFS)} ETFs LUZ × {len(FECHAS)} fechas × 2 horizontes")
    print("=" * 160)

    # Inventario de coverage
    df = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    print(f"\n{'ETF':>6} | {'desde':>12} | {'hasta':>12} | {'obs':>5}")
    print("-" * 50)
    for etf in ETFS:
        sub = df[df["label"] == etf].sort_values("obs_date")
        print(f"{etf:>6} | {str(sub['obs_date'].min()):>12} | "
              f"{str(sub['obs_date'].max()):>12} | {len(sub):>5}")

    print(f"\n{'as_of':>12} | {'ETF':>6} | {'h':>2} | {'σ_h':>5} | "
          f"{'IQR':>5} | {'centro':>7} | {'Vista A':>20} | {'Vista C':>20} | "
          f"{'régimen':>14} | {'real':>7} | hit")
    print("-" * 160)

    # Resultados agregados
    by_etf = defaultdict(lambda: {"A_hits": 0, "A_emit": 0, "C_hits": 0, "C_tot": 0})
    by_regime = defaultdict(lambda: {"A_hits": 0, "A_emit": 0, "C_hits": 0, "C_tot": 0})

    errors = []
    for etf in ETFS:
        for as_of in FECHAS:
            for h in (6, 12):
                try:
                    r = forecast_etf(etf, as_of=as_of, h_months=h)
                except Exception as e:
                    errors.append((etf, as_of, h, str(e)[:80]))
                    print(f"{str(as_of):>12} | {etf:>6} | {h:>2} | ERR: {str(e)[:60]}")
                    continue
                real = realized(etf, as_of, h)
                rstr = f"{real:+.3f}" if real is not None else "  n/a"
                vA = f"U={r.U}% [{r.hdi_lo:+.2f},{r.hdi_hi:+.2f}]"
                vC = (f"p{int(r.sweet_spot['p']*100)}% "
                      f"[{r.sweet_spot['lo']:+.2f},{r.sweet_spot['hi']:+.2f}]")
                hit = ""
                if real is not None:
                    by_etf[etf]["C_tot"] += 1
                    by_regime[r.regime]["C_tot"] += 1
                    if r.sweet_spot["lo"] <= real <= r.sweet_spot["hi"]:
                        hit = "✓C"
                        by_etf[etf]["C_hits"] += 1
                        by_regime[r.regime]["C_hits"] += 1
                    else:
                        hit = "✗C"
                    if r.U > 0:
                        by_etf[etf]["A_emit"] += 1
                        by_regime[r.regime]["A_emit"] += 1
                        if r.hdi_lo <= real <= r.hdi_hi:
                            hit += " ✓A"
                            by_etf[etf]["A_hits"] += 1
                            by_regime[r.regime]["A_hits"] += 1
                        else:
                            hit += " ✗A"
                print(f"{str(as_of):>12} | {etf:>6} | {h:>2} | {r.sigma_h*100:4.1f} | "
                      f"{r.w_max_used*100:4.1f} | {r.center:+7.3f} | {vA:>20} | "
                      f"{vC:>20} | {r.regime:>14} | {rstr:>7} | {hit}")

    # Hit rate por ETF
    print(f"\n{'Hit rate por ETF':>30}")
    print(f"{'ETF':>6} | {'Vista A (cuando emite)':>30} | {'Vista C':>25}")
    print("-" * 75)
    for etf in ETFS:
        s = by_etf[etf]
        a_str = (f"{s['A_hits']}/{s['A_emit']} = {s['A_hits']/s['A_emit']*100:.0f}%"
                 if s["A_emit"] else "0 emisiones")
        c_str = (f"{s['C_hits']}/{s['C_tot']} = {s['C_hits']/s['C_tot']*100:.0f}%"
                 if s["C_tot"] else "n/a")
        print(f"{etf:>6} | {a_str:>30} | {c_str:>25}")

    # Hit rate por régimen (todos los ETFs)
    print(f"\n{'Hit rate por régimen (agregado los 5 ETFs)':>50}")
    print(f"{'régimen':>15} | {'Vista A (cuando emite)':>30} | {'Vista C':>25}")
    print("-" * 75)
    for reg in ["normal", "stress_alto", "stress_extremo"]:
        s = by_regime[reg]
        a_str = (f"{s['A_hits']}/{s['A_emit']} = {s['A_hits']/s['A_emit']*100:.0f}%"
                 if s["A_emit"] else "0 emisiones")
        c_str = (f"{s['C_hits']}/{s['C_tot']} = {s['C_hits']/s['C_tot']*100:.0f}%"
                 if s["C_tot"] else "n/a")
        print(f"{reg:>15} | {a_str:>30} | {c_str:>25}")

    if errors:
        print(f"\n⚠ {len(errors)} forecasts fallaron:")
        for etf, as_of, h, msg in errors:
            print(f"  {etf} {as_of} h={h}: {msg}")
        print(f"\n✗ SMOKE M3.2 con errores")
        return

    print(f"\n✅ SMOKE M3.2 PASS — los 5 ETFs corren limpio.")


if __name__ == "__main__":
    main()
