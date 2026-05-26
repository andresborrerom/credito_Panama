"""Memo PDF v2 — versión completa y detallada para Mercantil Banco S.A.

Incluye:
- Anchor Banesco recalibrado con structura Prival firm-underwriting
- Explicación AT1 y mecánica de reapertura
- Comparativa 5y vs 10y (apetito + liquidez)
- Estrategia underwriter (firm vs best-efforts) con sensibilidades
- Timing & posicionamiento competitivo vs Banesco actual
- Pricing recomendado final con racional bottom-up + observado
- Ratings actuales verificados (Banesco A+(pan), Mercantil A(pa))
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.analytics.mercantil import (  # noqa: E402
    banesco_anchor_recalibrated,
    banesco_perpetual_detail,
    competing_pipeline,
    con,
    institutional_demand_proxy,
    issuance_pricing_summary,
    issuance_size_distribution,
    issuance_window_signal,
    issuer_secondary_curve,
    mercantil_holding_anchor,
    mercantil_pricing_recommendation_v2,
    mercantil_vcn_history,
    peer_curves,
    primary_market_calendar,
    secondary_liquidity_by_tenor,
    tenor_comparison_5y_vs_10y,
    underwriter_economics,
)
from src.analytics.ratings import CURRENT_RATINGS  # noqa: E402

DOCS = ROOT / "docs"
FIGS = DOCS / "figs_memo_v2"
FIGS.mkdir(parents=True, exist_ok=True)


def save_png(fig: go.Figure, name: str) -> pathlib.Path:
    out = FIGS / f"{name}.png"
    try:
        fig.write_image(out, width=900, height=440, scale=2)
    except Exception:
        out = FIGS / f"{name}.html"
        fig.write_html(out, include_plotlyjs="cdn", full_html=False)
    return out


def style(fig, *, title=None, ylabel=None):
    fig.update_layout(
        template="plotly_white",
        title=title,
        margin=dict(l=10, r=10, t=50, b=10),
        height=420,
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
        yaxis_title=ylabel,
    )
    return fig


# ============================ FIGURAS ===================================== #
def fig_peer_curves_v2(c):
    pc = peer_curves(c, lookback_days=365)
    pc = pc[pc["n_trades"] >= 3].copy()
    pc["yld_pct"] = pc["yld_median"] * 100
    pc["es_mercantil"] = pc["emisor"].str.contains("MERCANTIL")
    fig = px.scatter(
        pc, x="avg_plazo", y="yld_pct",
        size="n_trades", color="emisor", symbol="es_mercantil",
        hover_data={"bucket_plazo": True, "n_trades": True, "volumen_mm": ":.2f"},
        labels={"avg_plazo": "Plazo residual (años)", "yld_pct": "Yield mediano (%)"},
        size_max=30,
    )
    style(fig, title="Curva implícita por banco — secundario últimos 12m")
    fig.update_layout(height=500)
    return fig


def fig_tenor_comparison(c):
    df = tenor_comparison_5y_vs_10y(c)
    df = df[df["n_emisiones"] > 0]
    if df.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["tenor"], y=df["cupon_median"],
        text=[f"{c:.2f}%" for c in df["cupon_median"]],
        textposition="outside",
        error_y=dict(
            type="data", symmetric=False,
            array=df["cupon_p75"] - df["cupon_median"],
            arrayminus=df["cupon_median"] - df["cupon_p25"],
        ),
        marker_color="#002b5c",
        hovertemplate=(
            "Plazo %{x}<br>Mediana: %{y:.2f}%<br>"
            "P25-P75: %{customdata[0]:.2f}-%{customdata[1]:.2f}%<br>"
            "n=%{customdata[2]} emisiones por %{customdata[3]:.1f} MM<extra></extra>"
        ),
        customdata=df[["cupon_p25", "cupon_p75", "n_emisiones", "monto_total_mm"]].values,
    ))
    style(fig, title="Cupón observado en mercado primario por plazo (bonos T2/T3, últimos 3 años)",
          ylabel="Cupón (%)")
    return fig


def fig_secondary_liquidity(c):
    df = secondary_liquidity_by_tenor(c)
    df["yld_pct"] = df["yld_median"] * 100
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["bucket_plazo"].astype(str), y=df["vol_total_mm"],
        name="Volumen total (MM USD)",
        marker_color="#004080",
        text=[f"${v:.1f}MM" for v in df["vol_total_mm"]],
        textposition="outside",
        hovertemplate=(
            "Plazo %{x}<br>Volumen: $%{y:.1f}MM<br>"
            "Trades: %{customdata[0]}<br>Emisores: %{customdata[1]}<br>"
            "Papeles distintos: %{customdata[2]}<extra></extra>"
        ),
        customdata=df[["n_trades", "n_emisores", "n_papeles"]].values,
    ))
    style(fig, title="Liquidez secundaria por plazo — bancos T2/T3 últimos 12m",
          ylabel="Volumen (MM USD)")
    return fig


def fig_institutional_demand(c):
    df = institutional_demand_proxy(c)
    df["yld_pct"] = df["yld_median"] * 100
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["tamano_trade"], y=df["vol_mm"],
        marker_color="#1f6f43",
        text=[f"${v:.0f}MM ({n})" for v, n in zip(df["vol_mm"], df["n_trades"])],
        textposition="outside",
        hovertemplate="%{x}<br>Volumen: $%{y:.1f}MM<br>"
                       "n trades: %{customdata[0]}<br>Yield mediano: %{customdata[1]:.2f}%<extra></extra>",
        customdata=df[["n_trades", "yld_pct"]].values,
    ))
    style(fig, title="Base inversora — distribución por tamaño de trade (proxy de tipo de holder)",
          ylabel="Volumen (MM USD)")
    return fig


def fig_underwriter_sensitivity():
    """Sensibilidad de la economía firm-underwriting a fee y ahorro de bp."""
    fees = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    savings = [10, 25, 50, 75, 100, 150]
    plazo = 5.0
    monto = 30.0
    # Matriz neto NPV firm vs best-efforts
    rows = []
    for s in savings:
        row = {"ahorro_bp": s}
        for f in fees:
            r = underwriter_economics(fee_upfront_pct=f, coupon_subsidio_bp=s,
                                      plazo_anos=plazo, monto_mm=monto)
            row[f"{f}%"] = r["neto_firm_vs_be_mm"]
        rows.append(row)
    df = pd.DataFrame(rows).set_index("ahorro_bp")
    fig = go.Figure(data=go.Heatmap(
        z=df.values, x=df.columns, y=df.index.astype(str),
        colorscale="RdYlGn", zmid=0,
        text=[[f"${v:.2f}MM" for v in row] for row in df.values],
        texttemplate="%{text}",
        hovertemplate="Fee %{x} · Ahorro %{y} bp<br>NPV neto: $%{z:.2f}MM<extra></extra>",
        colorbar=dict(title="NPV neto<br>($MM)"),
    ))
    fig.update_layout(
        template="plotly_white",
        title="Sensibilidad: NPV neto firm-underwriting vs best-efforts ($30MM, 5y)",
        xaxis_title="Fee upfront (% del monto)",
        yaxis_title="Ahorro logrado en cupón (bp)",
        margin=dict(l=10, r=10, t=50, b=10), height=420,
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )
    return fig


def fig_mercantil_holding_anchor(c):
    mh = mercantil_holding_anchor(c)
    if mh.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=mh["fechaEmision_d"], y=mh["cupon_pct"],
        mode="markers+text",
        marker=dict(size=mh["serie_mm"] * 3 + 8, color="#002b5c"),
        text=[f"{p:.0f}y · ${s:.1f}MM" for p, s in zip(mh["plazo"], mh["serie_mm"])],
        textposition="top center",
        hovertemplate="<b>%{x}</b><br>Cupón: %{y:.2f}%<br>%{text}<extra></extra>",
    ))
    style(fig, title="Programa Mercantil Holding — bonos emitidos (anchor grupo)",
          ylabel="Cupón (%)")
    fig.update_layout(height=400)
    return fig


def fig_primary_calendar(c):
    cal = primary_market_calendar(c, lookback_days=730)
    cal = cal[cal["instrumento"].isin(["BONOS", "NOTAS CORPORATIVAS"])]
    cal = cal.copy()
    cal["es_mercantil"] = cal["emisor"].str.contains("MERCANTIL")
    fig = px.scatter(
        cal, x="fecha_emision", y="cupon_pct",
        size="serie_mm", color="emisor",
        hover_data={"nemotecnico": True, "plazo": ":.1f", "cupon_pct": ":.2f",
                    "serie_mm": ":.2f", "pct_coloc": ":.0f"},
        labels={"fecha_emision": "Fecha emisión", "cupon_pct": "Cupón (%)"},
        size_max=35,
    )
    style(fig, title="Calendario primario — bancos T2/T3, últimos 24m")
    fig.update_layout(height=480)
    return fig


# ============================ MEMO PDF ==================================== #
def main():
    c = con()
    snapshot = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    print(">> Computando todo...")
    window = issuance_window_signal(c)
    pricing_summary = issuance_pricing_summary(c)
    tenor_comp = tenor_comparison_5y_vs_10y(c)
    sec_liq = secondary_liquidity_by_tenor(c)
    inst_dem = institutional_demand_proxy(c)
    pipeline = competing_pipeline(c)
    mh_anchor = mercantil_holding_anchor(c)
    vcn_hist = mercantil_vcn_history(c)
    sz_dist = issuance_size_distribution(c)
    ban_anchor = banesco_anchor_recalibrated()
    ban_detail = banesco_perpetual_detail(c)
    pricing_v2 = mercantil_pricing_recommendation_v2(ban_anchor)
    # Defaults basados en precedente verificado Mercantil-Prival:
    # 0.321% estructuración + 0.535% colocación = 0.856% comisiones casa bolsa
    # All-in incluyendo SMV/Latinex/legales = 1.114%
    # "Firm underwriting" añade +25-50 bp en Panamá local → ~1.1-1.3% all-in con firm
    uw_default = underwriter_economics(fee_upfront_pct=1.10, coupon_subsidio_bp=30,
                                        plazo_anos=5, monto_mm=30)

    print(">> Generando figuras...")
    figs = {
        "peer": fig_peer_curves_v2(c),
        "tenor": fig_tenor_comparison(c),
        "liq": fig_secondary_liquidity(c),
        "dem": fig_institutional_demand(c),
        "uw": fig_underwriter_sensitivity(),
        "mh": fig_mercantil_holding_anchor(c),
        "cal": fig_primary_calendar(c),
    }
    paths = {k: save_png(v, k) for k, v in figs.items()}

    def img(k):
        return f'<img src="figs_memo_v2/{paths[k].name}" alt="{k}" />'

    # Pipeline tabla
    pipeline_bonos = pipeline[pipeline["instrumento"] == "BONOS"].head(10)
    pipeline_html = "".join(
        f"<tr><td>{r['emisor'][:35]}</td><td>{r['fechaEmision_d']}</td>"
        f"<td>{r['plazo']:.1f}y</td><td>{r['cupon_pct']:.2f}%</td>"
        f"<td>${r['serie_mm']:.1f}MM</td><td>{r['estado']}</td></tr>"
        for _, r in pipeline_bonos.iterrows()
    )

    # Ratings actuales
    mer_rat = CURRENT_RATINGS["MERCANTIL BANCO, S.A."]
    ban_rat = CURRENT_RATINGS["BANESCO (PANAMÁ), S.A."]
    mh_rat = CURRENT_RATINGS.get("MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.", {})

    html = build_html(
        snapshot=snapshot,
        window=window,
        ban_anchor=ban_anchor,
        ban_detail=ban_detail,
        ban_rat=ban_rat,
        mer_rat=mer_rat,
        mh_rat=mh_rat,
        pricing_v2=pricing_v2,
        tenor_comp=tenor_comp,
        sec_liq=sec_liq,
        inst_dem=inst_dem,
        sz_dist=sz_dist,
        mh_anchor=mh_anchor,
        vcn_hist=vcn_hist,
        pipeline_html=pipeline_html,
        uw_default=uw_default,
        img=img,
    )

    html_out = DOCS / "memo_mercantil_v2.html"
    html_out.write_text(html)
    print(f">> HTML: {html_out}")
    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(DOCS)).write_pdf(DOCS / "memo_mercantil_v2.pdf")
        print(f">> PDF: {DOCS / 'memo_mercantil_v2.pdf'}")
    except Exception as exc:
        print(f">> WeasyPrint err: {exc}")


def build_html(*, snapshot, window, ban_anchor, ban_detail, ban_rat, mer_rat, mh_rat,
               pricing_v2, tenor_comp, sec_liq, inst_dem, sz_dist, mh_anchor, vcn_hist,
               pipeline_html, uw_default, img):

    # === Tablas ===
    tenor_html = "".join(
        f"<tr><td><b>{r['tenor']}</b></td>"
        f"<td>{r['n_emisiones']}</td><td>{r['n_emisores']}</td>"
        f"<td>{r['cupon_median']:.2f}%</td>" if pd.notna(r['cupon_median']) else f"<td>—</td>"
        f"<td>${r['monto_total_mm']:.1f}MM</td>"
        f"<td>{r['pct_coloc_avg']:.0f}%</td>" if pd.notna(r['pct_coloc_avg']) else f"<td>—</td>"
        + "</tr>"
        for _, r in tenor_comp.iterrows()
    )

    sec_liq_html = "".join(
        f"<tr><td><b>{r['bucket_plazo']}</b></td>"
        f"<td>{r['n_trades']}</td><td>{r['n_papeles']}</td>"
        f"<td>${r['vol_total_mm']:.1f}MM</td>"
        f"<td>{r['yld_median']*100:.2f}%</td></tr>"
        for _, r in sec_liq.iterrows()
    )

    inst_dem_html = "".join(
        f"<tr><td>{r['tamano_trade']}</td>"
        f"<td>{r['n_trades']}</td>"
        f"<td>${r['vol_mm']:.1f}MM</td>"
        f"<td>{r['yld_median']*100:.2f}%</td></tr>"
        for _, r in inst_dem.iterrows()
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Memo v2 — Estructuración Mercantil Banco</title>
<style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: -apple-system, "Segoe UI", Helvetica, sans-serif; color: #1a1a2e;
       max-width: 820px; margin: 0 auto; line-height: 1.45; padding: 0; font-size: 10pt; }}
h1 {{ color: #002b5c; font-size: 22pt; border-bottom: 3px solid #002b5c; padding-bottom: 6px; margin-bottom: 4px; }}
h2 {{ color: #002b5c; font-size: 13pt; margin-top: 22px; border-bottom: 1px solid #ddd; padding-bottom: 3px; }}
h3 {{ color: #003f7a; font-size: 11pt; margin-top: 14px; }}
.subtitle {{ font-size: 9pt; color: #666; margin-top: 2px; }}
.confidential {{ background: #fff7e6; padding: 8px 12px; border-left: 4px solid #d18f00;
                 font-size: 8.5pt; margin: 10px 0; }}
.box {{ background: #f3f5fa; border-left: 4px solid #002b5c; padding: 10px 14px;
       margin: 12px 0; border-radius: 3px; font-size: 9.5pt; }}
.rec-box {{ background: #e8f3e8; border-left: 5px solid #1f6f43; padding: 12px 16px;
            margin: 14px 0; border-radius: 4px; }}
.warn-box {{ background: #fdecec; border-left: 4px solid #c23030; padding: 10px 14px;
             margin: 12px 0; border-radius: 4px; font-size: 9.5pt; }}
.kpi-row {{ display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }}
.kpi {{ flex: 1; min-width: 100px; background: #002b5c; color: #fff;
       padding: 10px 6px; border-radius: 5px; text-align: center; }}
.kpi .v {{ font-size: 14pt; font-weight: 700; line-height: 1.1; }}
.kpi .l {{ font-size: 7.5pt; opacity: 0.85; margin-top: 3px; }}
img {{ max-width: 100%; height: auto; margin: 8px 0; }}
ul {{ margin: 6px 0; padding-left: 20px; }}
li {{ margin: 4px 0; }}
.figcap {{ font-size: 8.5pt; color: #666; margin-top: -4px; margin-bottom: 12px; font-style: italic; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 8px 0; }}
th {{ background: #002b5c; color: #fff; padding: 5px 6px; text-align: left; }}
td {{ padding: 4px 6px; border-bottom: 1px solid #eee; vertical-align: top; }}
.page-break {{ page-break-before: always; }}
code {{ background: #eef1f7; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }}
.callout-small {{ font-size: 8.5pt; color: #555; margin-top: 4px; }}
.toc {{ font-size: 9pt; column-count: 2; column-gap: 18px; }}
.toc ol {{ padding-left: 18px; }}
</style>
</head>
<body>

<h1>Memo de estructuración — Mercantil Banco, S.A.</h1>
<div class="subtitle"><b>Versión 2 · {snapshot}</b> · Análisis para emisión de bonos en mercado panameño</div>

<div class="confidential">
<b>Informativo · No constituye recomendación de inversión, opinión legal ni asesoría regulatoria.</b><br>
Análisis sustentado en datos públicos de Latinex, SMV Panamá, U.S. Treasury, calificadoras públicas (Fitch, Moody's Local) e investigación dirigida sobre la emisión perpetua Banesco 2022. Las calificaciones citadas son las VIGENTES a la fecha del documento.
</div>

<div class="box">
<h3 style="margin-top:0">Tabla de contenido</h3>
<div class="toc"><ol>
<li>Resumen ejecutivo y recomendación</li>
<li>Ventana de mercado y timing</li>
<li>Anchor Banesco — recalibrado con estructura Prival</li>
<li>Qué es AT1 y por qué el spread es grande</li>
<li>Mecánica de reapertura del programa Banesco 2022</li>
<li>Curva propia Mercantil + comparables grupo</li>
<li>Tenor 5y vs 10y — comparativa estructurada</li>
<li>Liquidez secundaria y apetito por bonos largos</li>
<li>Base inversora institucional (proxy demanda)</li>
<li>Estrategia de underwriter (firm vs best-efforts)</li>
<li>Posicionamiento competitivo vs Banesco actual</li>
<li>Pricing final con racional bottom-up + observado</li>
<li>Sensibilidades y escenarios</li>
<li>Próximos pasos operativos</li>
<li>Metodología y limitaciones</li>
</ol></div>
</div>

<!-- ===== 1. RESUMEN ===== -->
<h2>1. Resumen ejecutivo y recomendación</h2>

<div class="rec-box">
<b>Recomendación principal:</b> emitir <b>Bono Corporativo Senior Bullet a 5 años</b>, cupón fijo trimestral
en rango <b>6.50%–7.00%</b>, monto inicial <b>$15–30 MM</b>, frecuencia trimestral, base 30/360 o ACT/360,
estructurado con underwriting firme (Prival, BG Valores o MMG Bank).
<br><br>
<b>Ventana:</b> "{window['interpretacion'].split('(')[0].strip()}" — spread T2/T3 actual {window['spread_actual_bp']:.0f} pb
(percentil {window['percentil']*100:.0f}% últimos 5 años; mediana {window['p50']:.0f} pb).
<br><br>
<b>Timing táctico:</b> ATENCIÓN — Banesco está reabriendo su programa AT1 perpetual con $40MM justo ahora
(post-upgrade a A+(pan) del 11-may-2026). Mercantil debe decidir entre salir <b>antes</b> de Banesco (próximos 30 días)
para no saturar el book institucional, o esperar <b>90+ días</b> después de Banesco para no chocar.
</div>

<div class="kpi-row">
  <div class="kpi"><div class="v">5y</div><div class="l">Plazo</div></div>
  <div class="kpi"><div class="v">$15-30MM</div><div class="l">Monto inicial</div></div>
  <div class="kpi"><div class="v">6.50–7.00%</div><div class="l">Cupón target</div></div>
  <div class="kpi"><div class="v">Senior bullet</div><div class="l">Estructura</div></div>
  <div class="kpi"><div class="v">Firm UW</div><div class="l">Distribución</div></div>
</div>

<p><b>Lo nuevo en esta versión vs v1:</b></p>
<ul>
  <li>Anchor Banesco recalibrado: el 7% NO es clearing market, es resultado de estructura firm-underwriting de Prival que apretó la tasa ~50-100 bp.</li>
  <li>Explicación detallada de AT1 y mecánica de reapertura del programa.</li>
  <li>Análisis estructurado <b>5y vs 10y</b>: el mercado primario panameño NO emite bonos a 7y+ (0 emisiones en 3 años), 10y solo vía perpetuo.</li>
  <li>Liquidez secundaria por plazo y proxy de demanda institucional (proxy por tamaño de trade).</li>
  <li>Sección "Underwriter economics": cuándo conviene firm vs best-efforts cuantitativamente.</li>
  <li>Ratings actuales verificados: Mercantil <b>A(pa) Moody's Local</b> (Fitch retiró cobertura may-2025), Banesco <b>A+(pan) Fitch</b> (upgrade may-2026).</li>
  <li>Posicionamiento competitivo con tres ventanas posibles vs Banesco.</li>
</ul>

<!-- ===== 2. VENTANA ===== -->
<h2>2. Ventana de mercado y timing</h2>
<p>El spread mediano del sector financiero tier T2/T3 sobre la curva soberana Panamá está en <b>{window['spread_actual_bp']:.0f} pb</b>
hoy, equivalente al <b>percentil {window['percentil']*100:.0f}%</b> de la distribución de los últimos 5 años (mediana histórica:
{window['p50']:.0f} pb).</p>
<p><b>Lectura:</b> {window['interpretacion']}.</p>
<p>Es un mercado <b>razonable pero no excepcional</b>. La tendencia bajista en los cupones del programa VCN de Mercantil
(de 5.63% en ago-2025 a 5.00% en may-2026, -63 bp en 9 meses) sugiere que la ventana podría seguir mejorando ligeramente.</p>

<!-- ===== 3. ANCHOR BANESCO ===== -->
<h2>3. Anchor Banesco — recalibrado con estructura Prival</h2>
<div class="warn-box">
<b>Aclaración crítica del análisis v1:</b> la referencia citada inicialmente — "Banesco al 7% por $60MM perpetuo" — corresponde a una emisión de <b>mayo 2022</b>, estructurada en formato de <b>Bono Subordinado Perpetuo AT1</b> (capital regulatorio Tier 1 adicional), bajo Resolución SMV-541-21.
<br><br>
Más importante aún: la emisión fue <b>estructurada por Prival Securities en formato firm-underwriting</b>. Prival garantizó la compra del 100% del paper absorbiendo el riesgo de inventario, y a cambio Banesco pagó un fee de estructuración (estimado 1.5-2.5% upfront) que permitió apretar el cupón ~50-100 bp por debajo del clearing natural del mercado.
<br><br>
<b>Sin esa estructura, el clearing natural en mercado abierto habría estado en {ban_anchor['cupon_clearing_natural'][0]:.1f}%-{ban_anchor['cupon_clearing_natural'][1]:.1f}%.</b>
</div>

<table>
<tr><th>Variable</th><th>Valor</th></tr>
<tr><td>Cupón observado</td><td>{ban_anchor['cupon_observado']:.2f}% (con estructura firm Prival)</td></tr>
<tr><td>Cupón clearing natural estimado</td><td>{ban_anchor['cupon_clearing_natural'][0]:.1f}%–{ban_anchor['cupon_clearing_natural'][1]:.1f}%</td></tr>
<tr><td>Premium AT1 vs senior bullet (total)</td><td>{ban_anchor['premium_at1_total_bp'][0]:.0f}–{ban_anchor['premium_at1_total_bp'][1]:.0f} bp</td></tr>
<tr><td>Senior 5y implícito (despejando primas, base observado)</td><td>{ban_anchor['senior_5y_implicito_observado'][0]:.2f}–{ban_anchor['senior_5y_implicito_observado'][1]:.2f}%</td></tr>
<tr><td>Senior 5y implícito (despejando primas, base natural)</td><td>{ban_anchor['senior_5y_implicito_natural'][0]:.2f}–{ban_anchor['senior_5y_implicito_natural'][1]:.2f}%</td></tr>
<tr><td>Estructurador</td><td>{ban_anchor['estructurador']}</td></tr>
<tr><td>Rating Banesco al momento (2022)</td><td>{ban_anchor['rating_banesco_2022']}</td></tr>
<tr><td>Rating Banesco ACTUAL</td><td>{ban_anchor['rating_banesco_actual']}</td></tr>
</table>

<div class="page-break"></div>

<!-- ===== 4. AT1 ===== -->
<h2>4. Qué es AT1 y por qué representa un spread tan grande</h2>
<p><b>AT1 = Additional Tier 1 capital.</b> Categoría regulatoria creada por <b>Basilea III</b> tras la crisis de 2008. Son instrumentos
que computan como capital del banco para efectos de ratios regulatorios, pero se emiten formalmente como bonos.</p>

<p>Para que un instrumento califique como AT1, debe tener cinco características que lo hacen <b>casi-acción</b>, no casi-bono:</p>

<table>
<tr><th>Característica</th><th>Bono senior normal</th><th>AT1 perpetual</th></tr>
<tr><td>Plazo</td><td>Definido</td><td><b>Perpetuo</b></td></tr>
<tr><td>Cupón</td><td>Obligatorio (skip = default)</td><td><b>Discrecional</b> (banco puede saltar sin default)</td></tr>
<tr><td>Subordinación</td><td>Senior a casi todo</td><td>Subordinado a depositantes, senior, Tier 2 y deuda subordinada simple — solo arriba del equity</td></tr>
<tr><td>Loss-absorption</td><td>No</td><td>Sí — write-down a cero o conversión en acciones si CET1 cae bajo trigger (~5.125-7%)</td></tr>
<tr><td>Call</td><td>Raro</td><td>Sí, pero a discreción del banco con autorización del regulador (SBP en Panamá)</td></tr>
</table>

<p>Para el inversionista, eso significa que <b>asume riesgo casi-equity en un instrumento que se llama "bono"</b>.
Por eso exige mucho más yield. Los componentes del spread AT1 vs senior bullet son aproximadamente:</p>

<table>
<tr><th>Componente del premium</th><th>Spread típico</th></tr>
<tr><td>Subordinación (cobro después de todo)</td><td>80–200 bp</td></tr>
<tr><td>Loss-absorption (write-down si capital cae)</td><td>100–200 bp</td></tr>
<tr><td>Cupón discrecional (puede saltarse sin default)</td><td>50–100 bp</td></tr>
<tr><td>Perpetuidad / extension risk (banco puede no llamar)</td><td>50–150 bp</td></tr>
<tr><td>Iliquidez (mercado secundario casi inexistente)</td><td>50–100 bp</td></tr>
<tr><td><b>TOTAL spread AT1 vs senior bullet</b></td><td><b>330–750 bp</b></td></tr>
</table>

<p>En mercados desarrollados (Europa, US), AT1 de bancos grandes están en 300-450 bp sobre senior. En mercados emergentes con
liquidez limitada como Panamá, fácilmente 400-650 bp. La amplitud del rango refleja cuán dependiente es el premium del nombre,
estructura y momento.</p>

<h2>5. Mecánica de reapertura del programa Banesco 2022</h2>
<p>En 2021, Banesco obtuvo de la SMV la autorización para un <b>programa marco</b> de hasta US$ 100 MM de bonos
subordinados perpetuos (Resolución SMV-541-21). En mayo 2022 emitió bajo ese programa:</p>
<ul>
  <li>Serie A: $60 MM al 7% (100% colocado)</li>
  <li>Serie B: $20 MM al 7% ($18.131 MM colocado, 90.7%)</li>
  <li>Saldo programa: $21.87 MM aún por emitir</li>
</ul>

<p><b>"Reapertura"</b> significa usar el programa autorizado para emitir más bonos, ya sea re-abriendo las series existentes
(mismo ISIN, simplemente más cantidad) o creando una Serie C, D, etc. bajo el mismo programa marco.</p>

<p>El bono <code>BANE0700000598B</code> (40 MM, registrado 29-may-2026, cupón 0% placeholder hasta pricing day) que
aparece en la base es <b>un nuevo programa</b>, no la reapertura del de 2022, porque:</p>
<ul>
  <li>ISIN distinto (<code>PAL7505513B8</code> vs el 2022 <code>PAL3001317A4/B2</code>)</li>
  <li>Monto $40 MM &gt; saldo del programa 2022 ($21.87 MM)</li>
</ul>

<p><b>Tres efectos en cadena que importan para Mercantil:</b></p>
<ol>
  <li><b>El 7% del 2022 funciona como anchor histórico de mercado.</b> Aunque el clearing real fuese 7.5-8%, el 7% se convirtió
  en el "fair value percibido" por inversionistas institucionales (AFP, aseguradoras, fondos pensión) que compraron vía Prival.
  Cualquier nueva emisión Banesco perpetual tiene que cotizar tight contra ese anchor — no contra el verdadero clearing.</li>
  <li><b>Con el upgrade Fitch a A+(pan), Banesco tiene argumento para mantener o BAJAR la tasa.</b> Probable que la nueva
  emisión salga a 6.85-7.00%, no arriba.</li>
  <li><b>Mercantil NO tiene este anchor histórico.</b> Va a salir "cold" al mercado de bonos largos (solo tiene VCN cortos).
  El clearing real va a observarse en su primera emisión — no hay artificio histórico que lo sostenga abajo del fair value.</li>
</ol>

<div class="page-break"></div>

<!-- ===== 6. CURVA ===== -->
<h2>6. Curva propia Mercantil + comparables del grupo</h2>
{img("peer")}
<div class="figcap">Curva implícita por banco peer en secundario, últimos 12m. Mercantil Banco (puntos pequeños azules) solo trade en plazos cortos. Mercantil Holding (mismo grupo) tiene cobertura hasta 5y. BICSA, Banistmo y otros completan el mapa.</div>

{img("mh")}
<div class="figcap">Programa Mercantil Holding — 9 emisiones a ~5y, cupón promedio {mh_anchor[(mh_anchor['plazo']>=4.5)&(mh_anchor['plazo']<=5.5)]['cupon_pct'].mean():.2f}% (todas 100% colocadas). Anchor más cercano del grupo.</div>

<p><b>Lectura:</b> Mercantil Holding ha establecido un programa exitoso a 5y con cupón anclado en 6.75-7.00%.
Mercantil Banco, como subsidiaria bancaria regulada un escalón arriba en la cadena de subordinación, debería poder
emitir <b>25-50 bp mejor</b> que Holding. Eso ubica el target Banco 5y en <b>6.25-6.75%</b> en estricta lectura jerárquica.</p>

<p>Pero atención al <b>rating differential reciente</b>: Banesco subió a A+(pan), Mercantil Banco está en A(pa) Moody's Local
(equivalente ~A(pan)) y arrastra presión por morosidad heredada de la fusión con Capital Bank. <b>Mercantil ahora paga premium
vs Banesco</b>, no descuento. Eso lleva el target práctico hacia <b>6.50-7.00%</b>.</p>

<!-- ===== 7. TENOR 5y vs 10y ===== -->
<h2>7. Comparativa estructurada — Tenor 5y vs 10y</h2>
{img("tenor")}
<div class="figcap">Mercado primario T2/T3 últimos 3 años. 5y solo tiene a Mercantil Holding (anclado al 7.00%); 3y tiene 8 emisiones a 5.76-6.00%; 7y y 10y: <b>cero emisiones</b>.</div>

<table>
<tr><th>Tenor</th><th>n emisiones</th><th>n emisores</th><th>Cupón mediano</th><th>Monto total</th><th>% coloc.</th></tr>
{tenor_html}
</table>

<div class="warn-box">
<b>Hallazgo crítico:</b> el mercado primario panameño NO emite bonos T2/T3 a 7y o 10y en formato bullet senior — <b>cero emisiones en 3 años</b>.
La única forma de plazos largos en este mercado ha sido vía bono subordinado perpetuo (modelo Banesco AT1 2022 / 2026).
<br><br>
Para Mercantil esto significa que <b>10y senior bullet sería pionero en plaza</b> — sin comparables locales directos. El pricing requeriría:
<ul>
<li>Anchor extranjero (eg. Mercantil Holding bonos USD en mercados internacionales si existen)</li>
<li>Extrapolación de curva 5y + premium plazo (típicamente 30-60 bp por año adicional para A(pan))</li>
<li>Asumir target 10y en rango 7.25-8.00% (5y target + 75-100 bp), con riesgo de placement &lt;100%</li>
</ul>
<b>Recomendación tenor:</b> mantenerse en 5y. Si se quiere plazo más largo, considerar emisión <b>internacional offshore</b> con
mejores comparables, no mercado panameño doméstico.
</div>

<!-- ===== 8. LIQUIDEZ ===== -->
<h2>8. Liquidez secundaria por plazo</h2>
{img("liq")}
<div class="figcap">Volumen total y métricas de liquidez en mercado secundario, bancos T2/T3 últimos 12m.</div>

<table>
<tr><th>Plazo</th><th>n trades</th><th>n papeles distintos</th><th>Volumen</th><th>Yield mediano</th></tr>
{sec_liq_html}
</table>

<p><b>Implicaciones para pricing y sizing:</b></p>
<ul>
<li><b>0-1y:</b> mercado muy líquido ($424MM, 684 trades). Mercantil ya está acá con sus VCN.</li>
<li><b>1-3y:</b> liquidez buena ($219MM). Tenor razonable como alternativa al 5y.</li>
<li><b>3-5y:</b> liquidez moderada ($26MM, 54 trades). <b>5y necesita expectativa de holders buy-and-hold</b> — no traders.</li>
<li><b>5-7y:</b> liquidez muy escasa ($3.5MM, 16 trades). Solo institucionales.</li>
<li><b>10y+:</b> volumen sale del perpetuo Banesco, no es comparable. Liquidez real bullet 10y = inexistente.</li>
</ul>

<!-- ===== 9. DEMANDA ===== -->
<h2>9. Base inversora institucional — proxy de demanda</h2>
{img("dem")}
<div class="figcap">Distribución de trades por tamaño en bancos T2/T3, últimos 12m. Sirve como proxy del tipo de holder.</div>

<table>
<tr><th>Tamaño trade</th><th>n trades</th><th>Volumen</th><th>Yield mediano</th></tr>
{inst_dem_html}
</table>

<p><b>Lectura:</b> aproximadamente <b>$650MM (de $694MM totales) viene de institucionales</b> (trades &gt; $250k) — base inversora
principal son AFP, aseguradoras, fondos pensión, bancas privadas. Yields que aceptan: 5.94-6.10%. <b>Cualquier emisión Mercantil
debe priorizar pre-marketing con esta base</b>, no retail.</p>

<div class="page-break"></div>

<!-- ===== 10. UNDERWRITER ===== -->
<h2>10. Estrategia de underwriter — firm vs best-efforts</h2>

<p>La emisión Banesco 2022 funcionó porque Prival aceptó <b>firm-underwriting</b>: garantizó comprar el 100% al cupón
acordado, absorbiendo el riesgo de inventario. A cambio cobró un fee upfront (estimado all-in 1.0-1.5%) que se traduce en una
"apretada" del cupón observado vs el clearing natural.</p>

<div class="box">
<b>Precedente verificado en prospectos SMV:</b><br>
El programa de bonos rotativo de <b>Mercantil Holding Financiero Internacional ($100MM)</b> fue estructurado por Prival Bank con
las siguientes comisiones <b>públicas (sección "Gastos de la Emisión" del prospecto)</b>:
<ul>
<li>Estructuración: <b>0.321%</b></li>
<li>Colocación: <b>0.535%</b></li>
<li>Total comisiones casa bolsa: <b>0.856%</b></li>
<li>All-in incluyendo SMV / Latinex / legales: <b>~1.11%</b></li>
</ul>
Este es el mejor benchmark disponible para Mercantil Banco: misma estructuradora (Prival), mismo grupo emisor, monto comparable.
Para una emisión Mercantil Banco $30MM, esto equivale aproximadamente a <b>$0.33MM all-in</b>.
</div>

<p><b>Modelo financiero firm vs best-efforts (default basado en precedente Mercantil-Prival):</b></p>

<table>
<tr><th>Variable</th><th>Valor (default)</th></tr>
<tr><td>Fee upfront all-in</td><td>{uw_default['fee_upfront_pct']:.2f}%</td></tr>
<tr><td>Ahorro logrado en cupón (asumido conservador)</td><td>{uw_default['coupon_subsidio_bp']:.0f} bp</td></tr>
<tr><td>Fee total absoluto</td><td>${uw_default['fee_total_mm']:.2f} MM</td></tr>
<tr><td>Ahorro anual cupón</td><td>${uw_default['ahorro_anual_mm']:.3f} MM/año</td></tr>
<tr><td>Ahorro NPV (5y, descuento 6%)</td><td>${uw_default['ahorro_npv_mm']:.3f} MM</td></tr>
<tr><td>NPV neto firm vs best-efforts</td><td><b>${uw_default['neto_firm_vs_be_mm']:.3f} MM</b></td></tr>
<tr><td>Break-even (bp mínimos para que el fee se pague)</td><td>{uw_default['break_even_bp']:.1f} bp</td></tr>
</table>

{img("uw")}
<div class="figcap">Heatmap de sensibilidad: NPV neto firm-underwriting vs best-efforts para distintas combinaciones de fee y ahorro logrado, asumiendo emisión $30MM a 5y. Verde = firm conviene.</div>

<p><b>Reglas prácticas (con fees reales del mercado panameño):</b></p>
<ul>
<li><b>Best-efforts default en Panamá local</b> — es la práctica dominante. Fee all-in ~0.85-1.10%.</li>
<li>Si la casa estructuradora logra apretar el cupón <b>≥ 25 bp</b> con fee 1.1%, conviene migrar a firm (margen positivo).</li>
<li>Si la apretada esperada es <b>&lt; 15 bp</b>, mantenerse en best-efforts.</li>
<li>Para AT1 / subordinado el fee se infla +20-50 bp por mayor esfuerzo de colocación.</li>
<li><b>Firm UW puro es raro en Panamá local</b>; lo más común es best-efforts con compromiso "soft" de sobre-asignación de la casa estructuradora si queda paper colgado.</li>
</ul>

<p><b>Casas candidatas en Panamá para firm-underwriting de bonos bancarios T2/T3:</b></p>
<ul>
<li><b>Prival Securities</b> — estructuró el Banesco perpetual 2022 y probable la nueva emisión 2026. Balance robusto, base inversora institucional fuerte.</li>
<li><b>BG Valores</b> (Banco General) — la casa más grande de Panamá por volumen. Capacidad de balance importante.</li>
<li><b>MMG Bank</b> — banca privada con clientes institucionales.</li>
<li><b>Banistmo Investment</b> — propio T2 emisor pero también estructura para otros.</li>
</ul>

<!-- ===== 11. TIMING ===== -->
<h2>11. Posicionamiento competitivo vs Banesco actual</h2>

<p>Banesco está reabriendo su programa AT1 perpetual con <b>$40 MM</b> registrados el 29-may-2026, pricing pendiente. Esta colocación va a
absorber inversionistas institucionales en próximas 4-8 semanas. Esto crea tres ventanas posibles para Mercantil:</p>

<table>
<tr><th>Ventana</th><th>Cuándo</th><th>Pros</th><th>Contras</th></tr>
<tr>
  <td><b>1. Antes que Banesco</b></td>
  <td>Próximos 15-30 días</td>
  <td>
    • Llega primero al book institucional<br>
    • Aprovecha rezago Banesco en pricing-day<br>
    • Narrative "alternativa senior" antes que llegue oferta AT1
  </td>
  <td>
    • Documentación apurada<br>
    • Sin tiempo para roadshow completo<br>
    • Si Banesco cierra a 7% AT1, comparación visual confunde
  </td>
</tr>
<tr>
  <td><b>2. En paralelo</b></td>
  <td>Mes de junio 2026</td>
  <td>
    • Si bases inversoras son distintas (Mercantil = senior conservador, Banesco = AT1 yield seekers), no compiten<br>
    • Aprovecha lo "hot" del mercado tras upgrade Banesco
  </td>
  <td>
    • Riesgo real de canibalizar misma base institucional<br>
    • Mercantil compite con narrativa Banesco upgraded
  </td>
</tr>
<tr>
  <td><b>3. Después de Banesco</b></td>
  <td>90+ días después del pricing Banesco (≈sep-oct 2026)</td>
  <td>
    • Base institucional ya digirió Banesco, busca diversificación<br>
    • Aprende del pricing real de Banesco<br>
    • Tiempo para roadshow completo y calificación
  </td>
  <td>
    • Spreads pueden ampliarse si entorno macro cambia<br>
    • Ventana actual neutral puede cerrarse
  </td>
</tr>
</table>

<p><b>Pipeline competidor en los últimos 60 días (bonos largos):</b></p>
<table>
<tr><th>Emisor</th><th>Fecha</th><th>Plazo</th><th>Cupón</th><th>Monto</th><th>Estado</th></tr>
{pipeline_html}
</table>

<div class="rec-box">
<b>Recomendación timing:</b> <b>Ventana 1 (antes que Banesco)</b> si la documentación lo permite — el primer mover advantage vale 10-20 bp.
Si no es viable, <b>Ventana 3 (después)</b>. Evitar Ventana 2 por riesgo de canibalización.
</div>

<div class="page-break"></div>

<!-- ===== 12. PRICING ===== -->
<h2>12. Pricing final — racional bottom-up + observado</h2>

<h3>Bottom-up teórico (desde Banesco anchor recalibrado)</h3>
<table>
<tr><th>Componente</th><th>Valor</th></tr>
<tr><td>Senior 5y implícito Banesco (despejando primas AT1)</td><td>{pricing_v2['base_banesco_senior_5y_implicito'][0]:.2f}–{pricing_v2['base_banesco_senior_5y_implicito'][1]:.2f}%</td></tr>
<tr><td>+ Diferencial rating Mercantil A(pa) vs Banesco A+(pan)</td><td>+{pricing_v2['ajustes_bp']['diferencial_rating_A_vs_Aplus']} bp</td></tr>
<tr><td>+ Premium first-time issuer en bonos largos</td><td>+{pricing_v2['ajustes_bp']['first_time_issuer_bonos_largos']} bp</td></tr>
<tr><td>+ Premium morosidad heredada Capital Bank</td><td>+{pricing_v2['ajustes_bp']['morosidad_heredada_capital_bank']} bp</td></tr>
<tr><td><b>Target teórico Mercantil 5y</b></td><td><b>{pricing_v2['mercantil_5y_target_teorico'][0]:.2f}–{pricing_v2['mercantil_5y_target_teorico'][1]:.2f}%</b></td></tr>
</table>

<p class="callout-small">Nota: el rango teórico tiene amplitud porque la prima AT1 de Banesco tiene incertidumbre alta (330-750 bp).
La banda alta del teórico es más relevante para pricing práctico.</p>

<h3>Observado en grupo Mercantil</h3>
<p>Mercantil Holding ha emitido 9 series a 5y con cupones <b>6.50-7.00%</b>, todas 100% colocadas. Mercantil Banco, escalonado un nivel
arriba pero con rating actual debilitado, debería emitir <b>en o cerca del mismo nivel</b> que Holding, no significativamente abajo.</p>

<div class="rec-box">
<h3 style="margin-top:0">Recomendación final de pricing</h3>
<table>
<tr><th>Variable</th><th>Recomendación</th><th>Racional</th></tr>
<tr><td><b>Cupón target</b></td><td><b>6.50–7.00%</b></td><td>Consenso entre teórico bottom-up y observado del grupo</td></tr>
<tr><td><b>Aim alto (firm UW agresivo)</b></td><td>6.25–6.50%</td><td>Vía Prival/BG firm-underwriting con fee 2-2.5%</td></tr>
<tr><td><b>Aim conservador (best-efforts)</b></td><td>6.75–7.00%</td><td>Sin UW firme, dejar que el mercado clear</td></tr>
<tr><td><b>Frecuencia</b></td><td>Trimestral</td><td>Estándar de mercado</td></tr>
<tr><td><b>Base día</b></td><td>30/360 ó ACT/360</td><td>Más usado en Panamá</td></tr>
<tr><td><b>Estructura</b></td><td>Senior bullet, no callable</td><td>Estándar T2/T3 Panamá</td></tr>
</table>
</div>

<!-- ===== 13. SENSIBILIDADES ===== -->
<h2>13. Sensibilidades y escenarios</h2>

<table>
<tr><th>Escenario</th><th>Cupón target 5y</th><th>Monto realista</th><th>Comentario</th></tr>
<tr>
  <td><b>Best case</b><br><i>Mercado tightens 50 bp + firm UW</i></td>
  <td>6.00-6.25%</td>
  <td>$30-50 MM</td>
  <td>Requiere ventana favorable + Prival firm. Best case extremo.</td>
</tr>
<tr>
  <td><b>Base case</b></td>
  <td>6.50-7.00%</td>
  <td>$15-30 MM</td>
  <td>Recomendación principal. Ventana actual.</td>
</tr>
<tr>
  <td><b>Stress case 1</b><br><i>Banesco satura demanda</i></td>
  <td>7.00-7.25%</td>
  <td>$10-20 MM</td>
  <td>Si Mercantil sale después de Banesco a un mercado con AFP "lleno" del AT1 7%.</td>
</tr>
<tr>
  <td><b>Stress case 2</b><br><i>Spreads amplían 50 bp</i></td>
  <td>7.25-7.75%</td>
  <td>$10-15 MM</td>
  <td>Si entorno global pone presión (Fed más hawkish, risk-off LatAm).</td>
</tr>
<tr>
  <td><b>Stress case 3</b><br><i>Downgrade Mercantil</i></td>
  <td>7.50-8.00%</td>
  <td>$5-10 MM</td>
  <td>Si Moody's Local baja por morosidad heredada Capital Bank.</td>
</tr>
</table>

<!-- ===== 14. PRÓXIMOS PASOS ===== -->
<h2>14. Próximos pasos operativos</h2>
<ol>
  <li><b>Decisión interna sobre ventana</b> (próximos 7 días): antes / después de Banesco. Driver: capacidad de Mercantil
  para tener documentación lista en 21 días si elige Ventana 1.</li>
  <li><b>Sondeo confidencial con 2-3 casas</b> (Prival, BG Valores, MMG): pedir indicación non-binding de fee + cupón target
  con firm vs best-efforts. <b>NO comprometerse</b>.</li>
  <li><b>Contratar calificación</b> a Moody's Local PA y/o re-contratar Fitch CA. Plazo: 30-45 días. Esto es necesario
  para muchos institucionales (AFP).</li>
  <li><b>Roadshow corto</b> (Ventana 1) o completo (Ventana 3) con AFP, aseguradoras, fondos pensión, bancas privadas. Pre-marketing
  semana antes de pricing day.</li>
  <li><b>Documentación SMV</b>: prospecto + suplemento. Modelo: usar el de Mercantil Holding 2024-2026 como base.</li>
  <li><b>Pricing day</b>: monitorear ventana en próximas 4-8 semanas; percentil de spreads puede moverse.</li>
</ol>

<h2>15. Metodología y limitaciones</h2>

<h3>Datos utilizados</h3>
<ul>
  <li><b>Mercado secundario:</b> 84,191 trades de la tape de Latinex en 10 años; 18,210 con YTM calculado por bisección sobre flujos bullet reconstruidos.</li>
  <li><b>Mercado primario:</b> 2,573 emisiones vigentes en Latinex extraídas vía API JSON pública.</li>
  <li><b>Benchmark:</b> curva soberana Panamá (Tesoro local) + US Treasury daily yield curve 2015-2026.</li>
  <li><b>Anchor Banesco:</b> investigación dirigida sobre IN-A 2025, EE.FF. KPMG, Resolución SMV-541-21, prensa local.</li>
  <li><b>Ratings actuales:</b> Moody's Local Panamá (Mercantil A(pa) 29-may-2025), Fitch Ratings (Banesco A+(pan) 11-may-2026).</li>
</ul>

<h3>Limitaciones declaradas</h3>
<ul>
  <li><b>Premium AT1:</b> rango amplio (330-750 bp). Cifra puntual de Banesco solo determinable con su data interna de book-building (no pública).</li>
  <li><b>Fee de estructuración Banesco-Prival:</b> rango estimado 1.5-2.5% basado en mercados análogos; no confirmado oficial.</li>
  <li><b>Calificación Mercantil:</b> solo Moody's Local viva; Fitch retiró cobertura may-2025 (señal débil).</li>
  <li><b>Liquidez secundaria 5y bullet bancario:</b> escasa ($26MM/año). Holders serán buy-and-hold, no traders.</li>
  <li><b>10y senior bullet:</b> sin comparables locales (cero emisiones en 3 años). Pricing extrapolado.</li>
  <li><b>Calificación Mercantil Holding:</b> estimada (no encontrada confirmación pública).</li>
</ul>

<h3>Sensibilidad del análisis a inputs nuevos</h3>
<p>Las siguientes piezas de información, cuando se obtengan, modificarán materialmente las cifras:</p>
<ul>
  <li><b>Fee real Prival-Banesco 2022:</b> ajusta el "senior implícito" Banesco y por tanto el target Mercantil ±25 bp.</li>
  <li><b>Cupón final Banesco reapertura 2026:</b> es la mejor evidencia disponible del clearing market post-upgrade.</li>
  <li><b>Calificación oficial Mercantil Banco por Fitch o equivalente (si vuelve a contratarla):</b> elimina el descuento por "rating retirado".</li>
  <li><b>Dump Bloomberg:</b> ratings oficiales y Z-spreads internacionales para todo el universo.</li>
</ul>

<div style="margin-top: 30px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 7.5pt; color: #888;">
  Generado: {snapshot} · Fuentes: latinexbolsa.com, supervalores.gob.pa, home.treasury.gov, fitchratings.com, moodyslocal.com.pa<br>
  No constituye recomendación de inversión, opinión legal ni asesoría regulatoria.
</div>

</body>
</html>"""


if __name__ == "__main__":
    main()
