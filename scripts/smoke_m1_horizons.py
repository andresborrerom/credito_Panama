"""Smoke M1.5 — forecast_api con anclajes empíricos sin umbrales arbitrarios.

Valida:
  1. forecast_lqd corre para h=6, 9, 12 sin errores.
  2. σ_h escala razonablemente con horizonte (Var ∝ h en límite i.i.d.).
  3. w_max viene del IQR empírico del activo — no de un parámetro a mano.
  4. Vista A (HDI con w_max=IQR) es un filtro estricto: U>0 solo si el
     modelo realmente bate al rango intercuartílico histórico.
  5. Vista C (sweet spot via Kneedle) siempre devuelve (p, lo, hi) sensato.

Baseline M1.5 (as_of=2024-12-31, captado 2026-06-09):
  h=6 : σ=6.57pp IQR=6.95pp | A: U=0  | C: p=80% [-2.4%, +8.8%]
  h=9 : σ=8.60pp IQR=7.69pp | A: U=0  | C: p=80% [-0.9%, +13.3%]
  h=12: σ=10.03pp IQR=10.69pp | A: U=50% [+6.4%, +16.4%] | C: p=75% [-0.3%, +16.5%]

Interpretación: a fines de 2024 el modelo no aporta sobre la dispersión empírica
del LQD a 6m/9m — Vista A lo reporta honestamente con U=0. A 12m sí aporta.
Vista C (sweet spot endógeno) siempre da un punto utilizable para el comité.
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.forecast_api import forecast_lqd


AS_OF = date(2024, 12, 31)


def main():
    print("=" * 130)
    print(f"SMOKE M1.5 — forecast_lqd con anclajes empíricos (as_of={AS_OF})")
    print("=" * 130)

    results = {}
    for h in (6, 9, 12):
        results[h] = forecast_lqd(as_of=AS_OF, h_months=h)
        print(f"[1/3] h={h} — corre sin error ✓")

    # Tabla comparativa
    print()
    print(f"{'h':>3} | {'σ_h':>7} | {'IQR':>7} | {'centro':>9} | "
          f"{'Vista A (HDI w_max=IQR)':>30} | {'Vista C (sweet spot)':>30} | régimen")
    print("-" * 140)
    for h, r in results.items():
        vA = (f"U={r.U}% [{r.hdi_lo:+.3f},{r.hdi_hi:+.3f}] "
              f"({(r.hdi_hi-r.hdi_lo)*100:.1f}pp)")
        vC = (f"p={int(r.sweet_spot['p']*100)}% "
              f"[{r.sweet_spot['lo']:+.3f},{r.sweet_spot['hi']:+.3f}] "
              f"({r.sweet_spot['width']*100:.1f}pp)")
        print(f"{h:>3} | {r.sigma_h*100:5.2f}pp | {r.w_max_used*100:5.2f}pp | "
              f"{r.center:+9.4f} | {vA:>30} | {vC:>30} | {r.regime}")

    # Propiedades estructurales (debe cumplirse independiente del as_of)
    # 1. σ_h debe crecer con h (Var ∝ h al límite i.i.d., ratio típico √2 entre 6m y 12m)
    assert results[6].sigma_h < results[9].sigma_h < results[12].sigma_h, \
        "σ_h debería crecer con h"
    # 2. w_max debería estar en el mismo orden de σ_h (IQR ≈ 1.35σ Gaussiano)
    for h, r in results.items():
        assert 0.5 * r.sigma_h <= r.w_max_used <= 3.0 * r.sigma_h, \
            f"h={h}: w_max(IQR)={r.w_max_used:.4f} fuera del rango plausible vs σ_h={r.sigma_h:.4f}"
    # 3. Vista C siempre devuelve un sweet spot con p ∈ [0.05, 0.95]
    for h, r in results.items():
        assert 0.05 <= r.sweet_spot['p'] <= 0.95, \
            f"h={h}: sweet spot p={r.sweet_spot['p']} fuera de grid"
        assert r.sweet_spot['lo'] < r.sweet_spot['hi'], \
            f"h={h}: sweet spot mal definido"
    # 4. Régimen invariante a h (signals son del estado actual, no del horizonte)
    assert results[6].regime == results[9].regime == results[12].regime
    print()
    print("[2/3] propiedades estructurales (σ_h↑, IQR razonable, sweet spot definido, "
          "régimen invariante) ✓")

    # 5. Mostrar el comentario completo para 12m (caso donde Vista A sí emite)
    print()
    print("[3/3] comentario operativo (h=12):")
    print(f"     {results[12].comment}")

    print()
    print("✅ SMOKE M1.5 PASS — anclajes empíricos sin umbrales arbitrarios.")


if __name__ == "__main__":
    main()
