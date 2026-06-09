"""Smoke M1 — forecast_api.py generalizado a horizonte arbitrario.

Verifica:
  1. Regresión exacta para h_months=6 (bit-perfect vs baseline pre-M1).
  2. Corre h=9 y h=12 sin errores.
  3. Centros y anchos crecen razonablemente con el horizonte.
  4. Pesos BMA pueden rotar entre horizontes (no se asume invarianza).

Baseline pre-M1 capturado el 2026-06-09 con as_of=2024-12-31:
  center=0.02677188 hdi=[-0.01373877, 0.08583464] U=70 regime=normal
  w_NN_K20=0.28952 w_NN_K10=0.24849 w_AR1=0.24264 w_Naive_boot=0.21935
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.forecast_api import forecast_lqd, _default_w_max


AS_OF = date(2024, 12, 31)

BASELINE_H6 = {
    "center": 0.02677188,
    "hdi_lo": -0.01373877,
    "hdi_hi": 0.08583464,
    "U": 70,
    "regime": "normal",
    "w_NN_K20": 0.28951850,
    "w_NN_K10": 0.24848838,
    "w_AR1":    0.24264244,
    "w_Naive_boot": 0.21935068,
}


def _assert_close(actual, expected, tol, label):
    diff = abs(actual - expected)
    assert diff <= tol, f"{label}: {actual} vs {expected} (diff {diff:.2e} > {tol:.2e})"


def main():
    print("=" * 130)
    print(f"SMOKE M1 — forecast_lqd con horizonte arbitrario (as_of={AS_OF})")
    print("=" * 130)

    # 1) regresión exacta h=6
    r6 = forecast_lqd(as_of=AS_OF, h_months=6)
    _assert_close(r6.center, BASELINE_H6["center"], 1e-7, "center h=6")
    _assert_close(r6.hdi_lo, BASELINE_H6["hdi_lo"], 1e-7, "hdi_lo h=6")
    _assert_close(r6.hdi_hi, BASELINE_H6["hdi_hi"], 1e-7, "hdi_hi h=6")
    assert r6.U == BASELINE_H6["U"], f"U h=6: {r6.U} vs {BASELINE_H6['U']}"
    assert r6.regime == BASELINE_H6["regime"]
    for m, w_exp in [(k.replace("w_", ""), v) for k, v in BASELINE_H6.items() if k.startswith("w_")]:
        _assert_close(r6.bma_weights[m], w_exp, 1e-7, f"weight {m} h=6")
    print("[1/3] h=6 — regresión bit-perfect contra baseline pre-M1 ✓")

    # 2) y 3) h=9, h=12 corren y producen forecasts coherentes
    results = {6: r6}
    for h in (9, 12):
        results[h] = forecast_lqd(as_of=AS_OF, h_months=h)
        print(f"[2/3] h={h} — corre sin error ✓")

    # 4) tabla comparativa
    print()
    print(f"{'h':>3} | {'w_max':>7} | {'centro':>9} | {'hdi_lo':>9} | {'hdi_hi':>9} | "
          f"{'ancho':>7} | {'U':>4} | {'régimen':>14} | pesos BMA (orden desc)")
    print("-" * 130)
    for h, r in results.items():
        wm = _default_w_max(h)
        pesos = " ".join(f"{m}={w:.2f}" for m, w in
                         sorted(r.bma_weights.items(), key=lambda kv: -kv[1]))
        print(f"{h:>3} | {wm*100:5.1f}pp | {r.center:+9.4f} | {r.hdi_lo:+9.4f} | "
              f"{r.hdi_hi:+9.4f} | {(r.hdi_hi-r.hdi_lo)*100:6.1f}pp | {r.U:>3}% | "
              f"{r.regime:>14} | {pesos}")
        print(f"    samples: n={len(r.bma_samples)}  mean={r.bma_samples.mean():+.4f}  "
              f"std={r.bma_samples.std():.4f}")

    # 5) propiedades estructurales esperadas
    # centro monótono creciente (el modelo cree LQD subirá; mayor h → más retorno acumulado)
    assert results[6].center < results[9].center < results[12].center, \
        "Centro debería crecer con horizonte si el drift estimado es positivo"
    # vol crece (más incertidumbre a mayor horizonte)
    assert results[6].bma_samples.std() < results[12].bma_samples.std(), \
        "Vol debería crecer con horizonte"
    # régimen estable (stress signals no dependen de h)
    assert results[6].regime == results[9].regime == results[12].regime
    print()
    print("[3/3] propiedades estructurales (monotonicidad centro/vol, régimen estable) ✓")
    print()
    print("✅ SMOKE M1 PASS — forecast_api.py soporta h_months arbitrario.")


if __name__ == "__main__":
    main()
