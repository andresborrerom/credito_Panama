"""Smoke M4 — comparar 3 paths para predecir retorno de bonos UST directos.

Para cada bono LUZ × fecha × horizonte, corre los 3 paths (C naive carry,
A AR1, B BMA equal-weights) y compara contra realized.

Métricas:
  - MAE del centro vs realized (precisión punto)
  - Ancho del intervalo HDI 80% (cuándo aplica)
  - Hit rate (realized dentro del HDI 80%)

Criterio de éxito M4: A o B debe BATIR a C en MAE del centro, o dar bandas
útiles. Si C gana, lo documentamos honestamente.
"""
from __future__ import annotations
from datetime import date
from collections import defaultdict
import numpy as np

from tasas_mercantil.producto_b.bond_mapping import (
    LUZ_BONDS, forecast_bond_C_naive, forecast_bond_A_AR1,
    forecast_bond_B_BMA, realized_bond_return,
)


FECHAS = [
    date(2022, 6, 30),
    date(2023, 12, 31),
    date(2023, 6, 30),  # para tener más data limpia con h=12
]
HORIZONS = [6, 12]


def hdi_80(samples: np.ndarray) -> tuple[float, float, float]:
    """Devuelve (lo, hi, width) del HDI 80% de samples. Para 1-sample, lo=hi=center."""
    if len(samples) <= 1:
        s = float(samples[0])
        return s, s, 0.0
    s = np.sort(samples); n = len(s); w = int(np.ceil(n * 0.80))
    if w >= n:
        return float(s[0]), float(s[-1]), float(s[-1] - s[0])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w]), float(s[j + w] - s[j])


def main():
    print("=" * 175)
    print(f"SMOKE M4 — Comparación A/B/C para {len(LUZ_BONDS)} bonos × "
          f"{len(FECHAS)} fechas × {len(HORIZONS)} horizontes")
    print("=" * 175)

    print(f"\n{'as_of':>12} | {'bono':>22} | {'h':>2} | {'D':>4} | "
          f"{'y_now':>6} | {'carry':>6} | "
          f"{'C centro':>9} | {'A centro':>9} | {'A 80%':>17} | "
          f"{'B centro':>9} | {'B 80%':>17} | {'real':>7} | hit")
    print("-" * 175)

    results = defaultdict(lambda: defaultdict(list))   # results[path][metric] = list

    for as_of in FECHAS:
        for bond in LUZ_BONDS:
            for h in HORIZONS:
                real = realized_bond_return(bond, as_of, h)
                if real is None:
                    continue
                cF = forecast_bond_C_naive(bond, as_of, h)
                aF = forecast_bond_A_AR1(bond, as_of, h)
                bF = forecast_bond_B_BMA(bond, as_of, h)
                if cF is None or aF is None or bF is None:
                    continue

                lo_a, hi_a, w_a = hdi_80(aF.samples)
                lo_b, hi_b, w_b = hdi_80(bF.samples)
                hit_a = "✓" if lo_a <= real <= hi_a else "✗"
                hit_b = "✓" if lo_b <= real <= hi_b else "✗"

                print(f"{str(as_of):>12} | {bond.name:>22} | {h:>2} | "
                      f"{cF.duration:4.1f} | {cF.yield_at_as_of:5.2f} | "
                      f"{cF.carry*100:+5.2f} | "
                      f"{cF.center*100:+8.2f}% | "
                      f"{aF.center*100:+8.2f}% | "
                      f"[{lo_a*100:+5.2f},{hi_a*100:+5.2f}]% | "
                      f"{bF.center*100:+8.2f}% | "
                      f"[{lo_b*100:+5.2f},{hi_b*100:+5.2f}]% | "
                      f"{real*100:+6.2f}% | A:{hit_a} B:{hit_b}")

                results["C"]["err"].append(abs(cF.center - real))
                results["A"]["err"].append(abs(aF.center - real))
                results["A"]["width"].append(w_a)
                results["A"]["hits"].append(1 if lo_a <= real <= hi_a else 0)
                results["B"]["err"].append(abs(bF.center - real))
                results["B"]["width"].append(w_b)
                results["B"]["hits"].append(1 if lo_b <= real <= hi_b else 0)

    # Tabla resumen
    print(f"\n{'Métrica comparativa':>30}")
    print(f"{'path':>12} | {'MAE centro':>12} | {'ancho 80% medio':>18} | "
          f"{'hit rate 80%':>14}")
    print("-" * 75)
    for p in ["C", "A", "B"]:
        if not results[p]["err"]:
            continue
        mae = np.mean(results[p]["err"]) * 100
        widths = results[p].get("width", [])
        w_str = f"{np.mean(widths)*100:.2f}pp" if widths else "—"
        hits = results[p].get("hits", [])
        hr = (f"{sum(hits)}/{len(hits)} = {sum(hits)/len(hits)*100:.0f}%"
              if hits else "—")
        print(f"{p:>12} | {mae:9.2f}pp | {w_str:>18} | {hr:>14}")

    # Veredicto
    print()
    mae_c = np.mean(results["C"]["err"]) * 100 if results["C"]["err"] else float("inf")
    mae_a = np.mean(results["A"]["err"]) * 100 if results["A"]["err"] else float("inf")
    mae_b = np.mean(results["B"]["err"]) * 100 if results["B"]["err"] else float("inf")
    print(f"Veredicto MAE: C={mae_c:.2f}pp  A={mae_a:.2f}pp  B={mae_b:.2f}pp")
    if mae_b < mae_c and mae_b < mae_a:
        print("→ B (BMA) gana en precisión punto. Vale la pena el sweep walk-forward.")
    elif mae_a < mae_c:
        print("→ A (AR1) bate a C. Modelo simple aporta sobre carry.")
    else:
        print("→ C (carry naive) gana. Modelos sobre Δyield NO aportan precision punto. "
              "Las bandas de A/B siguen siendo útiles si tienen hit rate alto.")

    print()
    print("✅ SMOKE M4 PASS (corrió sin errores; ver veredicto arriba para acción).")


if __name__ == "__main__":
    main()
