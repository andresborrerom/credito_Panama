"""Genera 3 histogramas ejecutivos para presentación a JLG / CFO."""
from __future__ import annotations
from datetime import date
from pathlib import Path

from tasas_mercantil.producto_b.portfolio_aggregator import forecast_luz_portfolio
from tasas_mercantil.producto_b.views_bandas import forecast_luz_all_views
from tasas_mercantil.producto_b.histograma_luz import plot_from_samples


CASOS = [
    # (as_of, h, file_suffix, title_suffix)
    (date(2024, 6, 30), 12,  "ejemplo1_normal",       "Régimen normal — uso para budget"),
    (date(2022, 6, 30), 12,  "ejemplo2_extremo",      "Régimen stress extremo — NO actuar"),
    (date(2022, 3, 31), 12,  "ejemplo3_cola_gorda",   "Cola gorda — provisión de capital"),
]


def main():
    out_dir = Path("docs/producto_b/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    for as_of, h, suf, title in CASOS:
        print(f"\n=== {as_of} h={h}m — {title} ===")
        pf = forecast_luz_portfolio(as_of, h)
        views = forecast_luz_all_views(as_of, h, portfolio_forecast=pf)
        out_path = out_dir / f"luz_{suf}_{as_of}_h{h}m.png"
        saved = plot_from_samples(
            samples=pf.samples, views=views, output_path=out_path,
            title_suffix=title,
        )
        print(f"  Centro: {pf.center*100:+.2f}%   Régimen: {pf.worst_regime}")
        print(f"  Vista B HDI 80%: [{views['vista_B']['lo']*100:+.2f}, "
              f"{views['vista_B']['hi']*100:+.2f}]%")
        print(f"  Vista C sweet: p{int(views['vista_C']['p']*100)}% "
              f"[{views['vista_C']['lo']*100:+.2f}, "
              f"{views['vista_C']['hi']*100:+.2f}]%")
        print(f"  VaR 95: {views['var']['var']*100:+.2f}%   "
              f"CVaR: {views['cvar']['cvar']*100:+.2f}%")
        print(f"  ✓ PNG: {saved} ({saved.stat().st_size//1024} KB)")

    print("\n✅ 3 histogramas ejecutivos generados.")


if __name__ == "__main__":
    main()
