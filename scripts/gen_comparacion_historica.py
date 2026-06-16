"""Genera la comparación FDP predictiva vs histórica para LUZ.

Para cada fecha de ejemplo corre el portafolio LUZ UNA vez (reusa el cache de
ForecastResult por ETF, ~92s c/u) y produce:
  - 1 PNG de comparación del PORTAFOLIO LUZ.
  - PNGs de comparación de los ÍNDICES PRINCIPALES (gratis: salen del mismo
    cache de forecasts del portafolio).
  - Un markdown con la matriz de señales (veredictos) de todo.

Uso:
    PYTHONPATH=src python scripts/gen_comparacion_historica.py
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import pandas as pd

from tasas_mercantil.producto_b.portfolio_aggregator import forecast_luz_portfolio
from tasas_mercantil.producto_b.comparacion_historica import (
    historical_h_returns_etf, historical_h_returns_portfolio,
    compare, plot_comparacion, _log_to_decimal, ETF_PARQUET,
)

OUT = Path("docs/producto_b/outputs/comparacion_historica")
H = 12

# (as_of, etiqueta de régimen, slug archivo)
EXAMPLES = [
    (date(2024, 6, 30), "normal",     "2024-06-30"),
    (date(2022, 6, 30), "extremo",    "2022-06-30"),
    (date(2022, 3, 31), "cola_gorda", "2022-03-31"),
]
# índices principales de LUZ (representantes de asset-class)
MAIN_INDICES = ["LQD", "IGOV", "GHYG", "EMB", "ACWI"]
# para qué fechas generar PNG por índice (las demás van solo a la tabla)
INDEX_PNG_DATES = {date(2024, 6, 30)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    etf_df = pd.read_parquet(ETF_PARQUET)
    rows = []

    for as_of, regime, slug in EXAMPLES:
        print(f"\n=== {as_of} ({regime}) — corriendo portafolio LUZ ===", flush=True)
        fc_cache: dict = {}
        pf = forecast_luz_portfolio(as_of, H, etf_forecast_cache=fc_cache)
        print(f"  portafolio listo. ETFs en cache: {sorted(fc_cache)}", flush=True)

        # --- PORTAFOLIO ---
        hist_p = historical_h_returns_portfolio(as_of, H, etf_df=etf_df)
        cmp_p = compare(pf.samples, hist_p, "Portafolio LUZ", H, as_of)
        if cmp_p:
            png = OUT / f"luz_portafolio_{slug}_h{H}m.png"
            plot_comparacion(cmp_p, png, title_suffix=regime)
            print(f"  [PORT] {cmp_p.verdict} -> {png.name}", flush=True)
            rows.append(("Portafolio LUZ", as_of, regime, cmp_p))

        # --- ÍNDICES (gratis del cache) ---
        for lab in MAIN_INDICES:
            if lab not in fc_cache:
                continue
            pred = _log_to_decimal(fc_cache[lab].bma_samples)
            hist = historical_h_returns_etf(lab, H, as_of, etf_df=etf_df)
            cmp_i = compare(pred, hist, lab, H, as_of)
            if not cmp_i:
                continue
            rows.append((lab, as_of, regime, cmp_i))
            if as_of in INDEX_PNG_DATES:
                png = OUT / f"indice_{lab}_{slug}_h{H}m.png"
                plot_comparacion(cmp_i, png, title_suffix=regime)
                print(f"  [{lab}] {cmp_i.verdict} -> {png.name}", flush=True)
            else:
                print(f"  [{lab}] {cmp_i.verdict}", flush=True)

    # --- markdown matriz de señales ---
    md = ["# Comparación FDP predictiva vs histórica — matriz de señales\n",
          f"Horizonte: {H} meses. Generado por `scripts/gen_comparacion_historica.py`.\n",
          "| Activo | as_of | régimen | Señal | Centro Δbps | Ancho HDI50 (×) | Riesgo Δbps |",
          "|---|---|---|---|---:|---:|---:|"]
    for name, as_of, regime, c in rows:
        md.append(f"| {name} | {as_of} | {regime} | **{c.verdict}** | "
                  f"{c.center_delta_bps:+.0f} | {c.width50_ratio:.2f} | "
                  f"{c.downside_delta_bps:+.0f} |")
    md_path = OUT / "SENALES.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nMatriz de señales -> {md_path}")
    print(f"PNGs en {OUT}/")


if __name__ == "__main__":
    main()
