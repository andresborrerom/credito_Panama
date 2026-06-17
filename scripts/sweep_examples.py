"""Sweep histórico para identificar buenos ejemplos didácticos.

Corre forecast_lqd en fechas representativas de regímenes distintos y compara
contra el retorno realizado. Útil para encontrar casos donde el sistema
genera valor obvio.
"""
from __future__ import annotations
import sys
from datetime import date
import pandas as pd

from tasas_mercantil.producto_b.forecast_api import forecast_lqd, CACHE_DIR


def main():
    etf = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    sub = etf[etf["label"] == "LQD"].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")

    candidatos = [
        date(2021, 6, 30),
        date(2021, 12, 31),
        date(2022, 3, 31),
        date(2022, 6, 30),
        date(2022, 9, 30),
        date(2022, 12, 31),
        date(2023, 6, 30),
        date(2023, 12, 31),
        date(2024, 6, 30),
    ]

    print(f"{'as_of':>12} | {'h':>2} | {'sig':>4} | {'IQR':>4} | "
          f"{'centr':>6} | {'Vista A':>22} | {'Vista C':>22} | "
          f"{'regimen':>15} | {'real':>7} | hit")
    print("-" * 150)
    for as_of in candidatos:
        for h in (6, 12):
            sys.stdout.flush()
            try:
                r = forecast_lqd(as_of=as_of, h_months=h)
            except Exception as e:
                print(f"{str(as_of):>12} | h={h:>2} | ERR: {str(e)[:60]}")
                sys.stdout.flush()
                continue
            cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h)
            window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
            real = float(window.sum()) if len(window) >= h - 1 else None
            rstr = f"{real:+.3f}" if real is not None else "   n/a"
            vA = f"U={r.U}% [{r.hdi_lo:+.2f},{r.hdi_hi:+.2f}]"
            vC = (f"p{int(r.sweet_spot['p']*100)}% "
                  f"[{r.sweet_spot['lo']:+.2f},{r.sweet_spot['hi']:+.2f}]")
            # Hit en Vista C si el realizado está dentro del sweet spot
            hit_C = ""
            if real is not None:
                if r.sweet_spot["lo"] <= real <= r.sweet_spot["hi"]:
                    hit_C = "✓C"
                else:
                    hit_C = "✗C"
                if r.U > 0:
                    if r.hdi_lo <= real <= r.hdi_hi:
                        hit_C += " ✓A"
                    else:
                        hit_C += " ✗A"
            print(f"{str(as_of):>12} | {h:>2} | {r.sigma_h*100:4.1f} | "
                  f"{r.w_max_used*100:4.1f} | {r.center:+6.3f} | {vA:>22} | "
                  f"{vC:>22} | {r.regime:>15} | {rstr:>7} | {hit_C}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
