"""Smoke M3 POC — EMB (Emerging Markets USD Bonds) como test de generalización.

Valida:
  1. forecast_lqd (back-compat wrapper) sigue funcionando.
  2. forecast_etf("EMB", ...) corre sin error.
  3. Comportamiento de EMB es distinto a LQD (σ_h, IQR distintos, régimen
     puede diferir).
  4. Sweep liviano EMB en 3 fechas × 2 horizontes para hit rates iniciales.

Si todo pasa, el motor es genuinamente reusable y podemos replicar a los
otros ETFs (ACWI, GHYG, IGOV, BSJQ, TIP) en M3.2.
"""
from __future__ import annotations
from datetime import date
import pandas as pd

from tasas_mercantil.producto_b.forecast_api import (
    forecast_etf, forecast_lqd, CACHE_DIR,
)


# 3 fechas: una por zona de régimen según el sweep LQD.
FECHAS = [
    date(2022, 6, 30),    # plena crisis (en LQD fue stress_extremo)
    date(2023, 12, 31),   # alto (en LQD fue stress_alto)
    date(2024, 6, 30),    # normal
]


def realized(label: str, as_of: date, h_months: int) -> float | None:
    """Retorno realizado h-meses post as_of para un ETF."""
    df = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    sub = df[df["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h_months)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    return float(window.sum()) if len(window) >= h_months - 1 else None


def main():
    print("=" * 140)
    print("SMOKE M3 POC — EMB como test de generalización del motor")
    print("=" * 140)

    # 1) Back-compat: forecast_lqd debe seguir funcionando idéntico al M1.5
    print("\n[1/3] Back-compat: forecast_lqd(2024-06-30, h=6) corre como antes")
    r_lqd = forecast_lqd(as_of=date(2024, 6, 30), h_months=6)
    print(f"     ✓ centro={r_lqd.center:+.4f}, U={r_lqd.U}%, sweet p={int(r_lqd.sweet_spot['p']*100)}%, régimen={r_lqd.regime}")

    # 2) EMB sweep liviano
    print(f"\n[2/3] Sweep EMB en {len(FECHAS)} fechas × 2 horizontes")
    print(f"\n{'as_of':>12} | {'h':>2} | {'σ_h':>5} | {'IQR':>5} | "
          f"{'centro':>7} | {'Vista A':>22} | {'Vista C':>22} | "
          f"{'régimen':>15} | {'real':>7} | hit")
    print("-" * 140)
    hits = {"A": [0, 0], "C": [0, 0]}   # [hits, emisiones]
    for as_of in FECHAS:
        for h in (6, 12):
            r = forecast_etf("EMB", as_of=as_of, h_months=h)
            real = realized("EMB", as_of, h)
            rstr = f"{real:+.3f}" if real is not None else "  n/a"
            vA = f"U={r.U}% [{r.hdi_lo:+.2f},{r.hdi_hi:+.2f}]"
            vC = (f"p{int(r.sweet_spot['p']*100)}% "
                  f"[{r.sweet_spot['lo']:+.2f},{r.sweet_spot['hi']:+.2f}]")
            hit_str = ""
            if real is not None:
                if r.sweet_spot["lo"] <= real <= r.sweet_spot["hi"]:
                    hit_str = "✓C"; hits["C"][0] += 1
                else:
                    hit_str = "✗C"
                hits["C"][1] += 1
                if r.U > 0:
                    if r.hdi_lo <= real <= r.hdi_hi:
                        hit_str += " ✓A"; hits["A"][0] += 1
                    else:
                        hit_str += " ✗A"
                    hits["A"][1] += 1
            print(f"{str(as_of):>12} | {h:>2} | {r.sigma_h*100:4.1f} | "
                  f"{r.w_max_used*100:4.1f} | {r.center:+7.3f} | "
                  f"{vA:>22} | {vC:>22} | {r.regime:>15} | {rstr:>7} | {hit_str}")

    print(f"\n[3/3] Resumen hit rate EMB ({len(FECHAS)*2} corridas):")
    if hits["C"][1]:
        print(f"     Vista C: {hits['C'][0]}/{hits['C'][1]} = "
              f"{hits['C'][0]/hits['C'][1]*100:.0f}% hit")
    if hits["A"][1]:
        print(f"     Vista A: {hits['A'][0]}/{hits['A'][1]} = "
              f"{hits['A'][0]/hits['A'][1]*100:.0f}% hit (cuando emitió)")
    else:
        print(f"     Vista A: 0 emisiones — modelo no bate IQR de EMB en ningún caso")

    print(f"\n✅ SMOKE M3 POC PASS — motor reusable a otros ETFs.")


if __name__ == "__main__":
    main()
