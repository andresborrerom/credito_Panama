"""Smoke Output (1) — 7 vistas de bandas del portafolio LUZ.

Corre forecast_luz_all_views para un caso (2024-06-30, h=12) y muestra
las 7 vistas + cuantiles formateadas para revisión humana.
"""
from __future__ import annotations
from datetime import date

from tasas_mercantil.producto_b.views_bandas import forecast_luz_all_views


def pct(x):
    return f"{x*100:+.2f}%"


def main():
    as_of = date(2024, 6, 30)
    h = 12
    print("=" * 100)
    print(f"SMOKE OUTPUT (1) — 7 vistas LUZ (as_of={as_of}, h={h}m)")
    print("=" * 100)

    print(f"\nCorriendo forecast_luz_all_views (~15 min)...")
    views = forecast_luz_all_views(as_of, h)

    m = views["meta"]
    print(f"\n[META] Centro: {pct(m['center'])}  Régimen: {m['worst_regime']}")
    print(f"       Cobertura: {m['coverage_directa']*100:.0f}% directo + "
          f"{m['coverage_proxy']*100:.0f}% proxy + "
          f"{m['coverage_cash']*100:.1f}% cash")
    print(f"       w_max (IQR portfolio) = {m['w_max_used_iqr_portfolio']*100:.2f}pp")
    print(f"       n_samples = {m['n_samples']}")

    print(f"\n[Vista 1 — A: rango ≤ IQR, max confianza]")
    if views["vista_A"]:
        v = views["vista_A"]
        print(f"  Con {int(v['p']*100)}% confianza, retorno entre "
              f"{pct(v['lo'])} y {pct(v['hi'])} ({v['width']*100:.2f}pp ancho)")
    else:
        print(f"  U=0 — ningún HDI cabe en w_max={m['w_max_used_iqr_portfolio']*100:.2f}pp.")
        print(f"  El modelo no aporta sobre el IQR del portafolio histórico.")

    print(f"\n[Vista 2 — B: confianza fija {int(views['vista_B']['p']*100)}%, min rango]")
    v = views["vista_B"]
    print(f"  Al {int(v['p']*100)}% confianza, retorno entre "
          f"{pct(v['lo'])} y {pct(v['hi'])} ({v['width']*100:.2f}pp ancho)")

    print(f"\n[Vista 3 — C: sweet spot Kneedle endógeno]")
    v = views["vista_C"]
    print(f"  Con {int(v['p']*100)}% confianza, retorno entre "
          f"{pct(v['lo'])} y {pct(v['hi'])} ({v['width']*100:.2f}pp ancho)")

    print(f"\n[Vista 4 — Fan chart (HDIs anidados)]")
    for k in ["hdi_50", "hdi_80", "hdi_95"]:
        v = views["fan_chart"][k]
        print(f"  HDI {int(v['p']*100)}%: [{pct(v['lo'])}, {pct(v['hi'])}] "
              f"({v['width']*100:.2f}pp ancho)")

    print(f"\n[Vista 5 — Direccional]")
    d = views["directional"]
    print(f"  P(retorno > 0)        = {d['p_positive']*100:.1f}%")
    print(f"  P(retorno > tasa libre = {pct(d['rf_rate'])}) = {d['p_above_rf']*100:.1f}%")

    print(f"\n[Vista 6 — VaR 95]")
    v = views["var"]
    print(f"  95% del tiempo no perdés más de {pct(-v['var'])}")
    print(f"  (i.e. VaR 95 = {pct(v['var'])})")

    print(f"\n[Vista 7 — CVaR/ES 95]")
    v = views["cvar"]
    print(f"  Si te toca el peor 5%, perdés en promedio {pct(-v['cvar'])}")
    print(f"  (i.e. CVaR 95 = {pct(v['cvar'])}, threshold VaR = {pct(v['var'])})")

    print(f"\n[Bonus — Cuantiles fijos]")
    q = views["quantiles"]
    print(f"  P5 = {pct(q['p5'])}   P25 = {pct(q['p25'])}   "
          f"P50 = {pct(q['p50'])}   P75 = {pct(q['p75'])}   P95 = {pct(q['p95'])}")

    print(f"\n✅ SMOKE OUTPUT (1) PASS — 7 vistas + cuantiles emitidos.")


if __name__ == "__main__":
    main()
