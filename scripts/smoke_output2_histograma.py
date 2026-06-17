"""Smoke Output (2) — Histograma rico del portafolio LUZ.

Genera el PNG con KDE + HDIs 50/80/95 + VaR + CVaR + tasa libre + anotaciones
direccionales. Lo guarda en docs/producto_b/outputs/ con nombre por
(as_of, horizonte).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

from tasas_mercantil.producto_b.portfolio_aggregator import forecast_luz_portfolio
from tasas_mercantil.producto_b.views_bandas import forecast_luz_all_views
from tasas_mercantil.producto_b.histograma_luz import plot_from_samples


def main():
    as_of = date(2024, 6, 30)
    h = 12
    out_dir = Path("docs/producto_b/outputs")
    out_path = out_dir / f"luz_histograma_{as_of}_h{h}m.png"

    print("=" * 100)
    print(f"SMOKE OUTPUT (2) — Histograma LUZ (as_of={as_of}, h={h}m)")
    print("=" * 100)

    print(f"\n[1/3] Corriendo forecast_luz_portfolio (~15 min)...")
    pf = forecast_luz_portfolio(as_of, h)
    print(f"  Centro={pf.center*100:+.2f}%, régimen={pf.worst_regime}")

    print(f"\n[2/3] Computando las 7 vistas...")
    views = forecast_luz_all_views(as_of, h, portfolio_forecast=pf)
    print(f"  Vista C sweet spot p={int(views['vista_C']['p']*100)}%, "
          f"VaR 95={views['var']['var']*100:+.2f}%, "
          f"CVaR={views['cvar']['cvar']*100:+.2f}%")

    print(f"\n[3/3] Generando PNG en {out_path}...")
    saved = plot_from_samples(
        samples=pf.samples,
        views=views,
        output_path=out_path,
        title_suffix=f"Cierre {as_of.year+1}-{as_of.month:02d}",
    )
    print(f"  ✓ Guardado: {saved} ({saved.stat().st_size // 1024} KB)")

    print(f"\n✅ SMOKE OUTPUT (2) PASS — histograma generado.")


if __name__ == "__main__":
    main()
