"""Smoke M2 — helpers de horizonte operativo.

Valida:
  1. horizon_remaining_year en todos los meses (incluye casos borde).
  2. horizon_next_12m es constante 12.
  3. both_horizons devuelve dict bien formado.
  4. forecast_lqd_both_horizons corre el motor para los 2 horizontes y
     skipea correctamente cuando "resto_del_anio" es 0 (diciembre).
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.horizons import (
    horizon_remaining_year, horizon_next_12m, both_horizons,
    forecast_lqd_both_horizons,
)


def test_horizon_remaining_year():
    casos = [
        (date(2026, 1, 31), 11),
        (date(2026, 3, 31), 9),
        (date(2026, 6, 30), 6),
        (date(2026, 9, 30), 3),
        (date(2026, 11, 30), 1),
        (date(2026, 12, 31), 0),
    ]
    for as_of, expected in casos:
        got = horizon_remaining_year(as_of)
        assert got == expected, f"horizon_remaining_year({as_of}) = {got}, esperado {expected}"
        print(f"  {as_of} → {got} meses ✓")


def test_horizon_next_12m():
    assert horizon_next_12m() == 12
    print(f"  horizon_next_12m() = 12 ✓")


def test_both_horizons():
    h_jun = both_horizons(date(2026, 6, 30))
    assert h_jun == {"resto_del_anio": 6, "proximos_12m": 12}, h_jun
    h_dec = both_horizons(date(2026, 12, 31))
    assert h_dec == {"resto_del_anio": 0, "proximos_12m": 12}, h_dec
    print(f"  both_horizons(jun-2026) = {h_jun} ✓")
    print(f"  both_horizons(dic-2026) = {h_dec} ✓")


def test_forecast_both_horizons():
    # Caso típico mid-year: as_of = 30-jun-2024, ambos horizontes válidos.
    print(f"  Corriendo forecast_lqd_both_horizons(2024-06-30)...")
    results = forecast_lqd_both_horizons(date(2024, 6, 30))
    assert set(results.keys()) == {"resto_del_anio", "proximos_12m"}, results.keys()
    r_resto = results["resto_del_anio"]   # h=6
    r_12m = results["proximos_12m"]       # h=12
    print(f"    resto_del_anio (h=6): centro {r_resto.center:+.4f}, "
          f"U={r_resto.U}%, sweet p={int(r_resto.sweet_spot['p']*100)}%, "
          f"régimen {r_resto.regime}")
    print(f"    proximos_12m  (h=12): centro {r_12m.center:+.4f}, "
          f"U={r_12m.U}%, sweet p={int(r_12m.sweet_spot['p']*100)}%, "
          f"régimen {r_12m.regime}")
    # Propiedad estructural: centro 12m ≥ centro 6m si drift positivo (LQD venía recuperando)
    assert r_resto.center < r_12m.center, \
        f"Centro 12m ({r_12m.center}) debería ser ≥ 6m ({r_resto.center}) en este as_of"
    print(f"    centro 12m > centro 6m ✓ (drift positivo coherente)")

    # Caso borde dic: solo debe haber proximos_12m
    print(f"  Corriendo forecast_lqd_both_horizons(2024-12-31)...")
    results_dec = forecast_lqd_both_horizons(date(2024, 12, 31))
    assert set(results_dec.keys()) == {"proximos_12m"}, results_dec.keys()
    print(f"    diciembre → solo proximos_12m emitido (skipea resto_del_anio=0) ✓")


def main():
    print("=" * 80)
    print("SMOKE M2 — helpers de horizonte operativo")
    print("=" * 80)
    print("\n[1/4] horizon_remaining_year — casos borde")
    test_horizon_remaining_year()
    print("\n[2/4] horizon_next_12m — constante 12")
    test_horizon_next_12m()
    print("\n[3/4] both_horizons — dict con dos horizontes")
    test_both_horizons()
    print("\n[4/4] forecast_lqd_both_horizons — convenience end-to-end")
    test_forecast_both_horizons()
    print("\n✅ SMOKE M2 PASS")


if __name__ == "__main__":
    main()
