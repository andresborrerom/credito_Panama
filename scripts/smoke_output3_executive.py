"""Smoke Output (3) — Mensaje primera diapositiva para el comité.

Valida que compose_executive_summary(as_of) devuelve mensajes listos para
pegar en la primera diapositiva, para los dos horizontes operativos.

Casos:
  1. as_of = 30-jun (mid-year): ambos horizontes activos
  2. as_of = 31-dic (fin-año):  solo proximos_12m emitido
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.executive_summary import compose_executive_summary


def main():
    print("=" * 120)
    print("SMOKE OUTPUT (3) — Mensaje primera diapositiva")
    print("=" * 120)

    # Caso típico: mid-year (junio)
    as_of = date(2024, 6, 30)
    print(f"\n[1/2] as_of = {as_of} (mid-year, ambos horizontes activos)")
    summary = compose_executive_summary(as_of)
    assert set(summary.keys()) == {"resto_del_anio", "proximos_12m"}, summary.keys()
    for name, data in summary.items():
        print(f"\n  --- {name.upper()} ({data['horizon_label']}) ---")
        print(f"  Center: {data['center']*100:+.2f}%   "
              f"Sweet C{int(data['sweet_p']*100)}%: "
              f"[{data['sweet_lo']*100:+.2f}, {data['sweet_hi']*100:+.2f}]%   "
              f"Régimen: {data['worst_regime']}")
        print(f"\n  MENSAJE CORTO (titular):")
        print(f"    {data['message_short']}")
        print(f"\n  MENSAJE COMPLETO (diapo):")
        print(f"    {data['message_full']}")

    # Caso borde: fin-año
    print(f"\n\n[2/2] as_of = 2024-12-31 (fin-año, solo proximos_12m)")
    summary_dec = compose_executive_summary(date(2024, 12, 31))
    assert set(summary_dec.keys()) == {"proximos_12m"}, summary_dec.keys()
    data = summary_dec["proximos_12m"]
    print(f"\n  MENSAJE COMPLETO:")
    print(f"    {data['message_full']}")
    print(f"\n  (resto_del_anio omitido correctamente — 0 meses)")

    print(f"\n✅ SMOKE OUTPUT (3) PASS")


if __name__ == "__main__":
    main()
