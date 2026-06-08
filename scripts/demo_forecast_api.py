"""Demo del API operativa Iter 6 (Producto B LQD).

Genera el comentario mensual del comité para 3 fechas representativas:
  - 2021-08-31: complacencia (pre-crisis bonos)
  - 2022-06-30: stress extremo (bear market)
  - 2024-12-31: normalización (reciente)
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.forecast_api import forecast_lqd


def main():
    for d in [date(2021, 8, 31), date(2022, 6, 30), date(2024, 12, 31)]:
        print("=" * 80)
        r = forecast_lqd(as_of=d)
        print(r.comment)
        print(f"\n  Centro:    {r.center:+.4f}")
        print(f"  HDI U={r.U}%: [{r.hdi_lo:+.4f}, {r.hdi_hi:+.4f}]  "
              f"ancho {(r.hdi_hi - r.hdi_lo)*100:.1f}pp")
        print(f"  Régimen:   {r.regime}")
        print(f"  Stress components:")
        for k, v in r.stress_components.items():
            print(f"    {k:>14}: {v:.3f}" if v is not None else f"    {k:>14}: n/a")
        print(f"  Pesos BMA:")
        for m, w in sorted(r.bma_weights.items(), key=lambda kv: -kv[1]):
            print(f"    {m:>12}: {w:.3f}")
        print()


if __name__ == "__main__":
    main()
