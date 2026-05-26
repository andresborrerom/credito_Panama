"""Genera estudio_renta_fija_panama.pdf con conclusiones y figuras estáticas.

Si WeasyPrint no está disponible, genera un HTML imprimible que el navegador puede
exportar a PDF (Cmd+P → Guardar como PDF). El HTML imprimible se guarda en
docs/estudio_renta_fija_panama.html.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

import plotly.graph_objects as go
import plotly.io as pio

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.analytics.curves import con, universe_summary  # noqa: E402
from src.app.build_site import (  # noqa: E402
    build_curva_actual,
    build_curva_bancos_por_tier,
    build_dispersion_actual,
    build_heatmap_cross_ref,
    build_percentil_actual,
    build_serie_bancos_por_tier,
    build_serie_sectores,
    build_serie_tesoro,
    build_spread_percentil_bancos,
    build_spread_percentil_instrumento_bancos,
    build_spread_vs_ust,
    build_volumen,
    derive_conclusions,
    derive_conclusions_bancos,
)

DOCS = ROOT / "docs"
FIGS = DOCS / "figs_pdf"
FIGS.mkdir(parents=True, exist_ok=True)


def save_png(fig: go.Figure, name: str) -> pathlib.Path:
    out = FIGS / f"{name}.png"
    try:
        fig.write_image(out, width=900, height=440, scale=2)
    except Exception as exc:
        # Fallback: salvar como SVG embedible
        out = FIGS / f"{name}.svg"
        try:
            fig.write_image(out)
        except Exception:
            # Último fallback: HTML mini
            out = FIGS / f"{name}.html"
            fig.write_html(out, include_plotlyjs="cdn", full_html=False)
    return out


def main():
    c = con()
    summary = universe_summary(c)

    print(">> Generando figuras...")
    fig_curva, df_curva = build_curva_actual(c)
    fig_tes, _ = build_serie_tesoro(c)
    fig_sec, _ = build_serie_sectores(c)
    fig_sp, df_sp = build_spread_vs_ust(c)
    fig_pc, df_pc = build_percentil_actual(c)
    fig_disp, _ = build_dispersion_actual(c)
    fig_vol, _ = build_volumen(c)

    # Sección bancos
    fig_bank_curve, df_bank_curve = build_curva_bancos_por_tier(c)
    fig_bank_pc_sp, _ = build_spread_percentil_bancos(c)
    fig_bank_pc_inst, _ = build_spread_percentil_instrumento_bancos(c)
    fig_bank_heat_sp, fig_bank_heat_pc, df_bank_heat = build_heatmap_cross_ref(c)
    fig_bank_serie, _ = build_serie_bancos_por_tier(c)

    print(">> Conclusiones...")
    findings = derive_conclusions(df_curva, df_pc, df_sp)
    findings_bancos = derive_conclusions_bancos(df_bank_curve, df_bank_heat)

    print(">> Salvando PNGs...")
    figs = {
        "curva": fig_curva,
        "tesoro": fig_tes,
        "sectores": fig_sec,
        "spread": fig_sp,
        "percentil": fig_pc,
        "disp": fig_disp,
        "vol": fig_vol,
        "bank_curve": fig_bank_curve,
        "bank_pc_sp": fig_bank_pc_sp,
        "bank_pc_inst": fig_bank_pc_inst,
        "bank_heat_sp": fig_bank_heat_sp,
        "bank_heat_pc": fig_bank_heat_pc,
        "bank_serie": fig_bank_serie,
    }
    paths = {k: save_png(v, k) for k, v in figs.items()}
    use_html_fallback = any(p.suffix == ".html" for p in paths.values())

    print(">> Renderizando HTML imprimible...")

    # Si las imágenes no se pudieron generar (kaleido missing), embebemos plotly directo
    if use_html_fallback:
        def embed(fig, div):
            return fig.to_html(include_plotlyjs="cdn" if div == "fig0" else False,
                               full_html=False, div_id=div,
                               config={"responsive": True, "displaylogo": False})
        embeds = {k: embed(v, f"fig{i}") for i, (k, v) in enumerate(figs.items())}
        img = lambda k: embeds[k]  # noqa: E731
    else:
        def img_tag(k):
            return f'<img src="figs_pdf/{paths[k].name}" alt="{k}" />'
        img = img_tag

    import re
    def md_to_html(s: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    findings_li = "".join(f"<li>{md_to_html(f)}</li>" for f in findings)
    findings_bancos_li = "".join(f"<li>{md_to_html(f)}</li>" for f in findings_bancos)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Estudio de Renta Fija de Panamá</title>
<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: -apple-system, "Segoe UI", Helvetica, sans-serif; color: #1a1a2e;
       max-width: 800px; margin: 0 auto; line-height: 1.5; padding: 20px; }}
h1 {{ color: #002b5c; font-size: 22pt; border-bottom: 3px solid #002b5c;
     padding-bottom: 8px; }}
h2 {{ color: #002b5c; font-size: 14pt; margin-top: 30px; }}
h3 {{ color: #003f7a; font-size: 11pt; }}
.subtitle {{ font-size: 10pt; color: #666; margin-top: -8px; }}
.box {{ background: #f3f5fa; border-left: 4px solid #002b5c; padding: 12px 18px;
       margin: 16px 0; border-radius: 4px; }}
.kpi-row {{ display: flex; gap: 12px; margin: 14px 0; flex-wrap: wrap; }}
.kpi {{ flex: 1; min-width: 110px; background: #002b5c; color: #fff;
       padding: 10px; border-radius: 6px; text-align: center; }}
.kpi .v {{ font-size: 16pt; font-weight: 700; }}
.kpi .l {{ font-size: 8pt; opacity: 0.85; }}
img {{ max-width: 100%; height: auto; margin: 10px 0; }}
ul {{ margin: 8px 0; padding-left: 22px; }}
li {{ margin: 6px 0; }}
.figcap {{ font-size: 9pt; color: #666; margin-top: -4px; margin-bottom: 16px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9pt; margin: 10px 0; }}
th {{ background: #002b5c; color: #fff; padding: 6px; text-align: left; }}
td {{ padding: 5px 6px; border-bottom: 1px solid #eee; }}
.page-break {{ page-break-before: always; }}
code {{ background: #eef1f7; padding: 2px 5px; border-radius: 3px; }}
</style>
</head>
<body>

<h1>Estudio de Renta Fija de Panamá</h1>
<div class="subtitle">Niveles actuales de tasas vs su historia · {datetime.now().strftime("%B %Y")}</div>
<div class="subtitle">Fuente: Bolsa Latinoamericana de Valores (Latinex) · Período: {summary['date_min']} a {summary['date_max']}</div>

<h2>1. Resumen ejecutivo</h2>

<div class="kpi-row">
  <div class="kpi"><div class="v">{summary['n_instruments']:,}</div><div class="l">Emisiones activas</div></div>
  <div class="kpi"><div class="v">{summary['n_trades']:,}</div><div class="l">Trades 10y</div></div>
  <div class="kpi"><div class="v">{summary['n_ytm']:,}</div><div class="l">YTMs calculados</div></div>
  <div class="kpi"><div class="v">{summary['n_emisores']:,}</div><div class="l">Emisores</div></div>
</div>

<div class="box">
  <h3 style="margin-top:0">Hallazgos principales</h3>
  <ul>{findings_li}</ul>
</div>

<h2>2. Curva actual de rendimientos</h2>
{img("curva")}
<div class="figcap">Yield mediano por bucket de plazo y tipo de instrumento. Ventana: últimos 90 días.</div>

<p>La curva por instrumento muestra el ordenamiento esperado por riesgo crediticio:
Tesoro &lt; VCN ≈ Notas Corporativas &lt; Bonos Corporativos &lt; Bonos Hipotecarios. La
pendiente del Tesoro Panamá es positiva en todo el tramo, lo que es coherente con un
mercado dolarizado que sigue de cerca la curva UST.</p>

<div class="page-break"></div>

<h2>3. Dispersión y universo negociado</h2>
{img("disp")}
<div class="figcap">Cada punto es un trade de los últimos 180 días. Tamaño = monto operado.</div>

<h2>4. Evolución histórica — Tesoro Panamá</h2>
{img("tesoro")}
<div class="figcap">Mediana trimestral del YTM por bucket de plazo. La profundidad disminuye en los primeros años por menor liquidez registrada.</div>

<div class="page-break"></div>

<h2>5. Sectores corporativos — evolución</h2>
{img("sectores")}
<div class="figcap">Promedio ponderado de yields trimestrales por sector (top 8 por liquidez acumulada).</div>

<h2>6. Spread soberano Panamá vs UST 10y</h2>
{img("spread")}
<div class="figcap">El spread se mide entre el bucket 7-10y del Tesoro Panamá y el UST 10y promedio trimestral.</div>

<div class="page-break"></div>

<div class="page-break"></div>

<h2>7a. Foco: sector bancario — curva por rating tier</h2>
<p>El sector "Financiero" en Latinex agrupa bancos, hipotecarias, financieras especializadas y
fideicomisos. Cada trade se etiquetó con un <b>rating tier</b> proxy (T1 = AAA(pan) soberano + bancos
sistémicos top, hasta T5 = BB(pan)/Unrated). El mapeo base se sustituirá por calificaciones reales
cuando ingrese el dump de Bloomberg.</p>
{img("bank_curve")}
<div class="figcap">Curva yield del sector bancario separada por rating tier — últimos 90 días.</div>

<div class="box">
  <h3 style="margin-top:0">Hallazgos sector bancario</h3>
  <ul>{findings_bancos_li}</ul>
</div>

<h2>7b. Spread por rating × plazo — percentil 5y</h2>
{img("bank_pc_sp")}
<div class="figcap">Igual al gráfico 7 pero usando SPREAD vs Tesoro Panamá en vez de yield absoluto.
Aísla el riesgo de crédito del nivel general de tasas. Verde = spread amplio vs su historia →
bono BARATO en términos de crédito. Rojo = spread comprimido → CARO.</div>

<div class="page-break"></div>

<h2>7c. Cross-reference: rating × plazo</h2>
{img("bank_heat_sp")}
<div class="figcap">Spread mediano actual (pb) en sector bancario por rating tier × bucket de plazo.</div>

{img("bank_heat_pc")}
<div class="figcap">Mismo eje pero coloreado por percentil del spread vs su historia 5y (verde = barato vs propia historia).</div>

<h2>7d. Spread por instrumento × plazo en bancos</h2>
{img("bank_pc_inst")}
<div class="figcap">Mismo análisis abriendo por tipo de instrumento (Bonos, VCN, Bonos Hipotecarios, Notas Corp.) dentro del sector bancario.</div>

<div class="page-break"></div>

<h2>7e. Evolución histórica del spread bancario por rating</h2>
{img("bank_serie")}
<div class="figcap">Spread mediano trimestral por tier de calificación. Permite ver compresión y ampliación de premios de crédito en el tiempo.</div>

<div class="page-break"></div>

<h2>8. Posición actual vs historia 5 años — mercado total</h2>
{img("percentil")}
<div class="figcap">Cada barra es (instrumento × bucket de plazo). Percentil ALTO (verde) = yield negociado hoy es alto vs su distribución 5y → instrumento BARATO. Percentil BAJO (rojo) = yield comprimido → CARO.</div>

<h2>9. Liquidez del mercado</h2>
{img("vol")}
<div class="figcap">Volumen anual negociado (USD miles de millones).</div>

<div class="page-break"></div>

<h2>10. Metodología</h2>

<h3>Cobertura de datos</h3>
<p>Universo: 100% de emisiones vigentes registradas en Latinex (2,573) más toda la tape
de transacciones disponible (10 años, 84,191 operaciones). Adicionalmente, US Treasury
daily yield curve desde 2015 para benchmark.</p>

<h3>Cálculo de YTM</h3>
<p>Para cada trade de bono a tasa fija con información completa, se reconstruyen los
flujos hasta vencimiento (cupón × frecuencia + amortización bullet) y se resuelve por
bisección la tasa que iguala el VP de flujos al precio limpio negociado. Bases
soportadas: 30/360, ACT/360, 365/360, ACT/365, ACT/ACT.</p>

<h3>Buckets</h3>
<p>Plazo residual agrupado en 0-1y, 1-3y, 3-5y, 5-7y, 7-10y, 10y+. Para series
históricas se usa frecuencia trimestral con mínimo 3 trades por celda.</p>

<h3>Proxy de crédito y rating tiers</h3>
<p>Sin acceso a feed licenciado de calificaciones, se construye un proxy en dos niveles:</p>
<ul>
  <li><b>Mapeo manual</b> de los ~50 emisores más activos basado en su perfil
  (soberano, banco sistémico, banco mediano, hipotecaria establecida, real estate,
  VCN sin rating público) → cinco tiers <code>T1..T5</code> en escala nacional Panamá
  (AAA(pan) → BB(pan)/NR).</li>
  <li><b>Fallback por sector</b> para emisores no mapeados manualmente
  (se etiquetan con sufijo <code>[sector-proxy]</code>).</li>
</ul>
<p><b>El spread negociado vs Tesoro mismo bucket-trimestre</b> actúa como medida
<i>revealed-market</i> del riesgo crediticio — es el componente del yield que el
mercado le exige al emisor por encima de la curva soberana, y por construcción no
depende de la calidad del proxy.</p>
<p>Esta versión se reemplazará por calificaciones oficiales (Equilibrium, Fitch CA,
Moody's Local, S&amp;P, etc.) cuando ingrese el dump de Bloomberg.</p>

<h3>Limitaciones declaradas</h3>
<ul>
  <li>Los precios son de transacciones pactadas (no order book continuo) — hay ruido en yields individuales. Se mitiga con medianas por bucket.</li>
  <li>Bonos con cláusulas call/put se tratan como bullet salvo evidencia desde el endpoint <code>/pago</code>.</li>
  <li>Bonos a tasa variable se excluyen de las curvas FIJA.</li>
  <li>Calificaciones públicas reales quedan pendientes para una próxima iteración (Bloomberg, Fitch CA, Equilibrium, PCR).</li>
</ul>

<h3>Reproducibilidad</h3>
<p>El estudio es 100% reproducible desde la herramienta interactiva publicada en
GitHub Pages. Cada conclusión de este PDF puede verificarse en la app aplicando los
filtros correspondientes (Sector, Instrumento, Bucket, Período).</p>

<div style="margin-top: 40px; font-size: 8pt; color: #888;">
  Generado: {datetime.now().isoformat(timespec='minutes')} · Datos: latinexbolsa.com · UST: home.treasury.gov<br>
  Este estudio es informativo y no constituye recomendación de inversión.
</div>

</body>
</html>"""

    html_out = DOCS / "estudio_renta_fija_panama.html"
    html_out.write_text(html)
    print(f">> HTML imprimible: {html_out}")

    # Try WeasyPrint
    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(DOCS)).write_pdf(DOCS / "estudio_renta_fija_panama.pdf")
        print(f">> PDF: {DOCS / 'estudio_renta_fija_panama.pdf'}")
    except Exception as exc:
        print(f">> WeasyPrint no disponible ({exc.__class__.__name__}). HTML imprimible listo en docs/.")
        print(">> El navegador puede convertirlo a PDF con Cmd+P / Ctrl+P.")


if __name__ == "__main__":
    main()
