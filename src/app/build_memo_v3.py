"""Memo PDF v3 — Mercantil Banco Tier 2 sub 10y bullet.

Versión final dirigida a tesorería / CFO con tesis explícita:
- Diagnóstico: exceso de liquidez, capital es la restricción
- Producto: Tier 2 sub 10y bullet (capital regulatorio Total Capital)
- Caso de negocio: $1 de T2 desbloquea ~15× en crédito a buenos corporativos
- Pricing: 7.50-8.50% (consenso bottom-up + observado)
- Sizing: $30-60MM por serie, programa total $60-100MM
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
    capital_sizing_analysis,
    competing_pipeline,
    con,
    institutional_demand_proxy,
    issuance_program_projection,
    issuance_window_signal,
    mercantil_holding_anchor,
    mercantil_t2_sub_10y_pricing,
    mercantil_vcn_history,
    peer_curves,
    primary_market_calendar,
    secondary_liquidity_by_tenor,
    t2_local_precedents,
    t2_premium_components_estimate,
    t2_regulatory_rules_sbp,
    t2_vs_at1_decision_matrix,
    tenor_comparison_5y_vs_10y,
    underwriter_economics,
)
from src.analytics.ratings import CURRENT_RATINGS  # noqa: E402

DOCS = ROOT / "docs"
FIGS = DOCS / "figs_memo_v3"
FIGS.mkdir(parents=True, exist_ok=True)


def save_png(fig: go.Figure, name: str) -> pathlib.Path:
    out = FIGS / f"{name}.png"
    try:
        fig.write_image(out, width=900, height=440, scale=2)
    except Exception:
        out = FIGS / f"{name}.html"
        fig.write_html(out, include_plotlyjs="cdn", full_html=False)
    return out


def style(fig, *, title=None, ylabel=None, height=420):
    fig.update_layout(
        template="plotly_white",
        title=title,
        margin=dict(l=10, r=10, t=50, b=10),
        height=height,
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
        yaxis_title=ylabel,
    )
    return fig


# ============================ FIGURAS ===================================== #
def fig_capital_sizing():
    """Cuánto sube CAR y cuánto crédito desbloquea cada monto de emisión."""
    montos = [10, 20, 30, 40, 50, 60, 75, 100, 150]
    rows = [capital_sizing_analysis(m) for m in montos]
    df = pd.DataFrame(rows)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["monto_emision_mm"], y=df["delta_car_bp"],
        name="∆ CAR (pb)",
        marker_color="#002b5c",
        text=[f"+{v:.0f} pb" for v in df["delta_car_bp"]],
        textposition="outside",
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=df["monto_emision_mm"], y=df["credito_extra_capacity_50rw_mm"],
        name="Capacidad crédito 50% RW (MM)", mode="lines+markers",
        marker_color="#1f6f43", line=dict(width=3),
        yaxis="y2",
    ))
    fig.update_layout(
        template="plotly_white",
        title="Impacto de la emisión T2: ∆ CAR + capacidad incremental de crédito",
        xaxis_title="Monto emitido (MM USD)",
        yaxis=dict(title="∆ CAR (bp)"),
        yaxis2=dict(title="Capacidad crédito 50% RW (MM USD)", overlaying="y", side="right", showgrid=False),
        margin=dict(l=10, r=10, t=50, b=10), height=440,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )
    return fig


def fig_pricing_decomposition(pricing):
    """Cascada del pricing: senior 5y → senior 10y → sub 10y → Mercantil-specific."""
    # Construir cascada conceptual
    a = pricing["approach_a_via_banesco_at1"]
    b = pricing["approach_b_via_mercantil_holding"]
    consenso = pricing["consenso_t2_10y"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Approach A: desde Banesco AT1",
        y=["Banesco AT1 cupón observado", "Banesco AT1 clearing real", "Banesco T2 hipotético",
           "+ Ajustes Mercantil", "Target Mercantil T2 10y (vía A)"],
        x=[7.0, 7.75, 6.25, 7.25, 7.25],
        marker_color="#004080",
        orientation="h",
        text=["7.00%", "7.50-8.00%", "5.50-7.00%", "+100 bp", "6.50-8.00%"],
        textposition="outside",
    ))
    style(fig, title="Approach A — cascada de pricing desde Banesco AT1",
          ylabel="", height=320)
    fig.update_layout(showlegend=False, xaxis_title="Cupón (%)")
    return fig


def fig_pricing_approaches_comparison(pricing):
    """Compara approach A (Banesco) vs B (Holding) vs consenso."""
    rows = [
        {"approach": "A: vía Banesco AT1\n(implícito T2)",
         "low": pricing["approach_a_via_banesco_at1"]["target"][0],
         "high": pricing["approach_a_via_banesco_at1"]["target"][1]},
        {"approach": "B: vía Mercantil Holding\n(extrapolación senior 5y)",
         "low": pricing["approach_b_via_mercantil_holding"]["target"][0],
         "high": pricing["approach_b_via_mercantil_holding"]["target"][1]},
        {"approach": "Consenso 50/50",
         "low": pricing["consenso_t2_10y"][0],
         "high": pricing["consenso_t2_10y"][1]},
        {"approach": "Con firm-UW apretado",
         "low": pricing["con_firm_uw_apretado_25_50bp"][0],
         "high": pricing["con_firm_uw_apretado_25_50bp"][1]},
    ]
    df = pd.DataFrame(rows)
    df["mid"] = (df["low"] + df["high"]) / 2
    fig = go.Figure()
    for i, r in df.iterrows():
        color = "#1f6f43" if "Consenso" in r["approach"] else "#004080"
        fig.add_trace(go.Scatter(
            x=[r["low"], r["high"]], y=[r["approach"], r["approach"]],
            mode="lines+markers", line=dict(width=10, color=color),
            marker=dict(size=14, color=color),
            text=[f"{r['low']:.2f}%", f"{r['high']:.2f}%"],
            textposition="top center",
            showlegend=False,
            hovertemplate=f"{r['approach']}<br>Rango: {r['low']:.2f}%-{r['high']:.2f}%<extra></extra>",
        ))
        # Add midpoint label
        fig.add_annotation(x=r["mid"], y=r["approach"],
                            text=f"<b>mid: {r['mid']:.2f}%</b>",
                            showarrow=False, yshift=-22, font=dict(size=10))
    style(fig, title="Pricing Mercantil T2 sub 10y — reconciliación de aproximaciones",
          ylabel="", height=380)
    fig.update_layout(xaxis_title="Cupón (%)", xaxis=dict(range=[5.5, 10]))
    return fig


def fig_peer_capital_landscape(c):
    """Universo de instrumentos de capital regulatorio bancario en Panamá."""
    # Banesco preferreds + AT1 + (cualquier sub que encontremos)
    q = """
    SELECT emisor, nemotecnico, instrumento,
           fechaEmision_d, fechaVencimiento_d,
           cupon_decimal*100 cupon_pct,
           montoSerie/1e6 serie_mm,
           montoColocado/1e6 coloc_mm
    FROM instruments
    WHERE (
        instrumento IN ('ACC PREFERENTES ACUM', 'ACCIONES PREFERIDAS')
        OR (instrumento = 'BONOS' AND CAST(fechaVencimiento_d AS DATE) - CAST(fechaEmision_d AS DATE) > 20*365)
    )
    AND es_tasa_fija = TRUE
    AND emisor IN ('BANESCO (PANAMÁ), S.A.', 'BANISTMO, S.A.', 'BAC INTERNATIONAL BANK, INC.',
                   'MERCANTIL BANCO, S.A.', 'MULTIBANK INC.', 'BANCO ALIADO, S.A.',
                   'GLOBAL BANK CORPORATION', 'BANCO GENERAL, S.A.', 'GRUPO FINANCIERO BG, S.A.',
                   'MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.', 'BANCO LA HIPOTECARIA, S.A.')
    ORDER BY fechaEmision_d DESC
    """
    df = c.execute(q).df()
    if df.empty:
        return go.Figure(), df

    fig = px.scatter(
        df, x="fechaEmision_d", y="cupon_pct",
        size="serie_mm", size_max=35, color="emisor",
        symbol="instrumento",
        hover_data={"nemotecnico": True, "fechaVencimiento_d": True, "serie_mm": ":.2f"},
        labels={"fechaEmision_d": "Fecha emisión", "cupon_pct": "Cupón (%)"},
    )
    style(fig, title="Universo de instrumentos de capital bancario en Panamá (perpetuos / sub de plazo muy largo)",
          height=480)
    return fig, df


def fig_credito_extra_per_dollar_capital():
    """Visualizar el multiplicador: $1 de T2 → $X de crédito desbloqueado."""
    car_levels = [12, 13, 14, 15, 16]
    rw_levels = [0.20, 0.50, 0.75, 1.00, 1.50]
    rows = []
    for car in car_levels:
        for rw in rw_levels:
            mult = 1 / (car / 100) / rw
            rows.append({"car": f"{car}%", "rw": f"{int(rw*100)}%", "mult": round(mult, 1)})
    df = pd.DataFrame(rows)
    pivot = df.pivot(index="rw", columns="car", values="mult")
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale="Greens",
        text=[[f"{v:.1f}×" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        hovertemplate="CAR objetivo %{x} · RW %{y}<br>Multiplicador: %{z:.1f}×<extra></extra>",
        colorbar=dict(title="× crédito<br>por $1 cap."),
    ))
    fig.update_layout(
        template="plotly_white",
        title="Multiplicador de crédito por $1 de capital nuevo (según CAR objetivo y risk weight del crédito)",
        xaxis_title="CAR objetivo (% Total Capital)",
        yaxis_title="Risk weight del crédito (%)",
        margin=dict(l=10, r=10, t=50, b=10), height=380,
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )
    return fig


# ============================ MAIN ======================================== #
def main():
    c = con()
    snapshot = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    print(">> Computando...")
    window = issuance_window_signal(c)
    tenor_comp = tenor_comparison_5y_vs_10y(c)
    sec_liq = secondary_liquidity_by_tenor(c)
    inst_dem = institutional_demand_proxy(c)
    pipeline = competing_pipeline(c)
    mh_anchor = mercantil_holding_anchor(c)
    ban_anchor = banesco_anchor_recalibrated()
    ban_detail = banesco_perpetual_detail(c)
    pricing_t2 = mercantil_t2_sub_10y_pricing(ban_anchor)
    t2_premium = t2_premium_components_estimate()
    t2_precedents = t2_local_precedents()
    t2_rules = t2_regulatory_rules_sbp()
    decision = t2_vs_at1_decision_matrix()
    cap_30 = capital_sizing_analysis(30)
    cap_60 = capital_sizing_analysis(60)
    cap_100 = capital_sizing_analysis(100)
    program_default = issuance_program_projection(monto_total_programa_mm=100, monto_serie_a_mm=30,
                                                    frecuencia_meses=4, cupon_pct=pricing_t2["midpoint_target"],
                                                    plazo_anos=10)
    uw_default = underwriter_economics(fee_upfront_pct=1.30, coupon_subsidio_bp=35,
                                        plazo_anos=10, monto_mm=30)

    print(">> Figuras...")
    figs = {
        "cap": fig_capital_sizing(),
        "mult": fig_credito_extra_per_dollar_capital(),
        "pricing_cmp": fig_pricing_approaches_comparison(pricing_t2),
        "landscape": fig_peer_capital_landscape(c)[0],
    }
    paths = {k: save_png(v, k) for k, v in figs.items()}

    def img(k):
        return f'<img src="figs_memo_v3/{paths[k].name}" alt="{k}" />'

    # Tablas
    decision_html = "".join(
        f"<tr><td><b>{r['criterio']}</b></td><td>{r['t2_sub_10y']}</td>"
        f"<td>{r['at1_perpetuo']}</td><td><i>→ {r['ganador']}</i></td></tr>"
        for r in decision
    )
    sec_liq_html = "".join(
        f"<tr><td>{r['bucket_plazo']}</td><td>{r['n_trades']}</td>"
        f"<td>${r['vol_total_mm']:.1f}MM</td><td>{r['yld_median']*100:.2f}%</td></tr>"
        for _, r in sec_liq.iterrows()
    )
    pipeline_bonos = pipeline[pipeline["instrumento"] == "BONOS"].head(8)
    pipeline_html = "".join(
        f"<tr><td>{r['emisor'][:35]}</td><td>{r['fechaEmision_d']}</td>"
        f"<td>{r['plazo']:.1f}y</td><td>{r['cupon_pct']:.2f}%</td>"
        f"<td>${r['serie_mm']:.1f}MM</td><td>{r['estado']}</td></tr>"
        for _, r in pipeline_bonos.iterrows()
    )

    cap_table_html = "".join(
        f"<tr><td>${m['monto_emision_mm']}MM</td><td>{m['car_post_pct']:.2f}%</td>"
        f"<td>+{m['delta_car_bp']:.0f} pb</td>"
        f"<td>${m['credito_extra_capacity_50rw_mm']:.0f}MM</td>"
        f"<td>${m['credito_extra_capacity_100rw_mm']:.0f}MM</td></tr>"
        for m in [cap_30, cap_60, cap_100]
    )

    precedents_html = "".join(
        f"<tr><td><b>{p['emisor']}</b></td><td>{p['fecha']}</td>"
        f"<td>${p['monto_mm']}MM</td><td>{p['plazo_anos']}{'y' if isinstance(p['plazo_anos'], int) else ''}</td>"
        f"<td>{p['reconocido_como']}</td><td>{p['rating_emision'] or '—'}</td>"
        f"<td style='font-size:7.5pt'>{p['comentario']}</td></tr>"
        for p in t2_precedents
    )

    mer_rat = CURRENT_RATINGS["MERCANTIL BANCO, S.A."]
    ban_rat = CURRENT_RATINGS["BANESCO (PANAMÁ), S.A."]

    html = build_html(
        snapshot=snapshot, window=window, ban_anchor=ban_anchor, ban_detail=ban_detail,
        ban_rat=ban_rat, mer_rat=mer_rat, pricing_t2=pricing_t2, t2_premium=t2_premium,
        t2_rules=t2_rules, precedents_html=precedents_html,
        tenor_comp=tenor_comp, sec_liq_html=sec_liq_html, pipeline_html=pipeline_html,
        decision_html=decision_html, cap_30=cap_30, cap_60=cap_60, cap_100=cap_100,
        cap_table_html=cap_table_html, program=program_default, uw_default=uw_default,
        mh_anchor=mh_anchor, img=img,
    )

    out_html = DOCS / "memo_mercantil_v3.html"
    out_html.write_text(html)
    print(f">> HTML: {out_html}")
    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(DOCS)).write_pdf(DOCS / "memo_mercantil_v3.pdf")
        print(f">> PDF: {DOCS / 'memo_mercantil_v3.pdf'}")
    except Exception as exc:
        print(f">> WeasyPrint err: {exc}")


def build_html(**kw):
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<title>Memo v3 — Mercantil Banco Tier 2 Sub 10y</title>
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
.thesis-box {{ background: #e8f4ff; border-left: 5px solid #004080; padding: 14px 18px;
               margin: 16px 0; border-radius: 4px; font-size: 10pt; }}
.kpi-row {{ display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }}
.kpi {{ flex: 1; min-width: 100px; background: #002b5c; color: #fff;
       padding: 10px 6px; border-radius: 5px; text-align: center; }}
.kpi .v {{ font-size: 14pt; font-weight: 700; line-height: 1.1; }}
.kpi .l {{ font-size: 7.5pt; opacity: 0.85; margin-top: 3px; }}
img {{ max-width: 100%; height: auto; margin: 8px 0; }}
ul, ol {{ margin: 6px 0; padding-left: 20px; }}
li {{ margin: 4px 0; }}
.figcap {{ font-size: 8.5pt; color: #666; margin-top: -4px; margin-bottom: 12px; font-style: italic; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 8px 0; }}
th {{ background: #002b5c; color: #fff; padding: 5px 6px; text-align: left; }}
td {{ padding: 4px 6px; border-bottom: 1px solid #eee; vertical-align: top; }}
.page-break {{ page-break-before: always; }}
code {{ background: #eef1f7; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }}
.callout-small {{ font-size: 8.5pt; color: #555; margin-top: 4px; }}
.toc {{ font-size: 9pt; column-count: 2; column-gap: 18px; }}
</style></head><body>

<h1>Mercantil Banco — emisión de Tier 2 Sub 10y</h1>
<div class="subtitle"><b>Memo v3 · {kw['snapshot']}</b> · Análisis estructurado de capital regulatorio</div>

<div class="confidential">
<b>Informativo · No constituye recomendación de inversión, asesoría regulatoria ni opinión legal.</b><br>
Sustentado en datos públicos Latinex/SMV, U.S. Treasury, calificaciones públicas (Fitch, Moody's Local) e investigación dirigida sobre Banesco AT1 2022 y reglas SBP.
</div>

<div class="thesis-box">
<h2 style="margin-top:0;border:none">Tesis estratégica del banco (input del cliente)</h2>
<ul>
<li><b>Diagnóstico:</b> exceso estructural de liquidez — depósitos crecen más rápido que originación de crédito tras endurecimiento de políticas crediticias.</li>
<li><b>Restricción binding:</b> capital regulatorio (no liquidez). El banco quiere crecer crédito a mejores corporativos con tickets más grandes, lo que exige más capital por nombre.</li>
<li><b>Producto necesario:</b> instrumento que compute como capital regulatorio sin engrosar el balance pasivo de depósitos.</li>
<li><b>Plazo objetivo:</b> 10 años.</li>
</ul>
<b>Esta tesis define el producto:</b> <u>Bono Tier 2 Subordinado a 10 años bullet</u> (no callable o callable año 5).
T2 es la estructura más eficiente para el objetivo descrito porque:
<ul>
<li>Computa como capital regulatorio (Total Capital ratio bajo SBP Acuerdo 1-2015)</li>
<li>Es ~100-150 bp más barato que AT1 perpetuo (no requiere loss-absorption ni cupón discrecional)</li>
<li>Intereses son deducibles fiscalmente (vs AT1 que puede ser tratado como dividendo)</li>
<li>Base inversora más amplia (algunas AFP/aseguradoras no pueden tener AT1, sí T2)</li>
</ul>
</div>

<h2>Recomendación principal</h2>
<div class="rec-box">
Emitir <b>Bono Tier 2 Subordinado a 10 años bullet</b>, cupón fijo trimestral en rango <b>7.50%–8.50%</b>
(midpoint <b>{kw['pricing_t2']['midpoint_target']:.2f}%</b>), monto inicial <b>$30 MM</b>, programa total <b>$100 MM</b>
en 3-4 series escalonadas cada 4 meses. Estructurar con casa con presencia institucional fuerte
(Prival, BG Valores, MMG Bank). Best-efforts default; firm-UW si la apretada esperada es ≥ 25-35 bp.
<br><br>
<b>Capital efecto $30MM:</b> +71 pb en CAR (13% → 13.71%); desbloquea ~$462MM en originación adicional
a corporativos investment-grade (50% risk weight) o ~$231MM a corporativos genéricos (100% RW).
</div>

<div class="kpi-row">
  <div class="kpi"><div class="v">T2 sub</div><div class="l">Estructura</div></div>
  <div class="kpi"><div class="v">10y bullet</div><div class="l">Plazo</div></div>
  <div class="kpi"><div class="v">{kw['pricing_t2']['consenso_t2_10y'][0]:.2f}-{kw['pricing_t2']['consenso_t2_10y'][1]:.2f}%</div><div class="l">Cupón target</div></div>
  <div class="kpi"><div class="v">$30MM</div><div class="l">Serie inicial</div></div>
  <div class="kpi"><div class="v">$100MM</div><div class="l">Programa</div></div>
  <div class="kpi"><div class="v">+71 pb</div><div class="l">∆ CAR</div></div>
  <div class="kpi"><div class="v">+$462MM</div><div class="l">Capacidad crédito</div></div>
</div>

<h2>Tabla de contenido</h2>
<div class="box"><div class="toc"><ol>
<li>Tesis y caso de negocio del capital</li>
<li>El producto: Tier 2 vs alternativas</li>
<li>Capital regulatorio Panamá — marco SBP Acuerdo 1-2015</li>
<li>Sizing: monto óptimo según objetivo de CAR</li>
<li>Pricing T2 10y — racional bottom-up doble approach</li>
<li>Anchor Banesco AT1 — relectura para T2</li>
<li>Universo de instrumentos de capital bancario Panamá</li>
<li>Cláusulas y estructura recomendada</li>
<li>Estructura del programa y cadencia óptima</li>
<li>Ventana de mercado y timing competitivo</li>
<li>Estrategia de underwriter</li>
<li>Sensibilidades y escenarios de stress</li>
<li>Próximos pasos operativos</li>
<li>Metodología y limitaciones</li>
</ol></div></div>

<!-- ============ 1. TESIS ============= -->
<h2>1. Tesis y caso de negocio del capital</h2>

<h3>1.1 Diagnóstico del banco</h3>
<p>El banco ha endurecido recientemente las políticas crediticias (mayor selectividad en originación). Mientras tanto, las
captaciones han seguido creciendo a su ritmo normal. <b>El resultado mecánico es exceso de liquidez</b>: el balance tiene más
depósitos disponibles de los que el equipo de crédito está colocando.</p>

<p>La estrategia anunciada es <b>reactivar la originación de crédito enfocándose en corporativos de mejor calidad y tickets
más grandes</b>. Esa decisión es óptima por dos razones: (a) aprovecha la liquidez sobrante, (b) consolida la cartera en
nombres con menor PD esperada. Pero tiene una restricción operativa real: <b>capital regulatorio por contraparte</b>.</p>

<h3>1.2 Por qué capital es la restricción binding (no liquidez)</h3>
<p>Bajo SBP Acuerdo 1-2015, cada crédito consume capital regulatorio según su <i>risk weight</i>:</p>
<ul>
<li>Crédito a soberano AAA: 0% RW (no consume capital)</li>
<li>Crédito hipotecario residencial: 35% RW</li>
<li>Crédito a corporativo IG: 50-75% RW</li>
<li>Crédito a corporativo genérico: 100% RW</li>
<li>Crédito a empresa unrated/distressed: 150% RW</li>
</ul>
<p>Si Mercantil quiere originar $500 MM en créditos nuevos a corporativos 50% RW, eso consume <b>$32.5 MM de Total Capital</b>
asumiendo CAR mínimo de 13%. Sin capital nuevo, ese crecimiento no es posible aunque haya liquidez excedente esperando.</p>

<h3>1.3 Multiplicador: $1 de T2 nuevo desbloquea ~15× en crédito</h3>
{kw['img']("mult")}
<div class="figcap">Multiplicador de crédito por cada $1 de capital nuevo, según CAR objetivo y risk weight del crédito originado. Verde más oscuro = más crédito desbloqueado.</div>

<p>Para un banco con CAR objetivo 13% que origina a corporativos 50% RW, <b>cada $1 de capital nuevo permite originar $15.4 de crédito</b>.
Para una emisión de $30 MM en T2, eso son <b>~$462 MM en capacidad incremental</b>.</p>

<!-- ============ 2. PRODUCTO ============= -->
<h2>2. El producto: Tier 2 vs alternativas</h2>
<p>Hay tres formas técnicas de aumentar capital regulatorio para un banco panameño:</p>

<table>
<tr><th>Criterio</th><th>Tier 2 sub 10y</th><th>AT1 perpetuo</th><th>Decisión</th></tr>
{kw['decision_html']}
</table>

<p><b>Conclusión:</b> 7 de 10 criterios favorecen T2. AT1 conviene SOLO si el banco necesita reforzar específicamente
Tier 1 (capital primario) por una restricción regulatoria específica, no Total Capital. Si la tesis es "expandir crédito
con capital adicional", T2 es óptimo.</p>

<h3>2.1 Por qué no equity nuevo</h3>
<p>Equity es la forma más cara de capital (costo de equity típicamente 12-15% para bancos panameños vs 7.5-8.5% para T2).
Solo se justifica si Tier 1 es insuficiente y AT1 no es viable. La emisión T2 evita dilución y aprovecha el "tax shield" de
intereses deducibles.</p>

<div class="page-break"></div>

<!-- ============ 3. MARCO REGULATORIO ============= -->
<h2>3. Capital regulatorio Panamá — marco SBP Acuerdo 1-2015</h2>
<p>La Superintendencia de Bancos de Panamá regula adecuación de capital bajo el Acuerdo 1-2015 con complemento
Acuerdo 3-2016. La estructura jerárquica es Basilea III adaptada:</p>

<table>
<tr><th>Capa</th><th>Componentes</th><th>Mínimo SBP</th><th>Mínimo industria</th></tr>
<tr><td><b>CET1</b> (Common Equity)</td><td>Acciones comunes, reservas, retenidos</td><td>4.5%</td><td>≥ 10%</td></tr>
<tr><td><b>Tier 1</b> (CET1 + AT1)</td><td>CET1 + AT1 perpetuos con write-down</td><td>6.0%</td><td>≥ 11%</td></tr>
<tr><td><b>Total Capital</b> (T1 + T2)</td><td>Tier 1 + bonos subordinados T2</td><td><b>8.0%</b></td><td><b>≥ 13%</b></td></tr>
</table>

<h3>3.1 Requisitos específicos para que un bono compute como Tier 2 bajo SBP</h3>
<ul>
<li><b>Plazo:</b> mínimo 5 años. No hay máximo. 10 años es estándar.</li>
<li><b>Subordinación:</b> subordinado a todos los acreedores generales (depositantes, senior debt, deuda sub ordinaria); senior solo a CET1 y AT1.</li>
<li><b>Cupón:</b> obligatorio. No discrecional (a diferencia de AT1).</li>
<li><b>Loss-absorption:</b> NO requerido en Panamá para T2 (diferencia importante vs Basilea III europea que sí lo exige).</li>
<li><b>Call:</b> permitido pero requiere autorización previa SBP. Típicamente no antes del año 5.</li>
<li><b>Step-down regulatorio:</b> el monto reconocido como Tier 2 declina 20% por año en los últimos 5 años de vida del bono. Un T2 10y emitido hoy computa 100% en años 1-5, luego 80%, 60%, 40%, 20%, 0% en años 6-10.</li>
</ul>

<h3>3.2 Diferencia clave vs Basilea III europea</h3>
<div class="box">
<b>T2 panameño NO requiere cláusula contractual de write-down ni conversión a acciones</b> (a diferencia del T2 europeo estricto bajo Basilea III). La absorción de pérdidas opera únicamente por <b>subordinación legal en liquidación</b>. Esto hace al T2 panameño:
<ul>
<li><b>Menos riesgoso para inversores</b> que sus análogos europeos → debería pricing un poco mejor</li>
<li><b>Más simple de documentar</b> que un AT1 con triggers de CET1</li>
<li><b>Más fácil de aprobar regulatoriamente</b> (no requiere review SBP sobre triggers complejos)</li>
</ul>
</div>

<h3>3.3 Precedentes T2 / subordinado doméstico en Panamá (últimos 5 años)</h3>
<table>
<tr><th>Emisor</th><th>Fecha</th><th>Monto</th><th>Plazo</th><th>Reconocido como</th><th>Rating emisión</th><th>Comentario</th></tr>
{kw['precedents_html']}
</table>

<p><b>Lectura del precedente:</b></p>
<ul>
<li><b>Multibank 2022</b> es el ÚNICO T2 puro bullet 10y doméstico identificado. Monto modesto ($28MM) sugiere placement principalmente privado o demanda institucional limitada en ese momento. Validación crítica: el producto SÍ es viable bajo SBP, hay aprobación regulatoria documentada.</li>
<li><b>Caja de Ahorros 2021</b> ($150MM, 10y, AAA(pan)) es el subordinado largo más grande del mercado. Status técnico T2 vs T1 ambiguo pero el monto y plazo validan apetito institucional por subordinado bancario.</li>
<li><b>Banesco 2022 y BIB 2020</b> son AT1, estructura distinta — sirven como anchor conceptual de "capital regulatorio bancario en Panamá" pero no son direct comparables de pricing T2.</li>
</ul>

<p><b>Implicación para Mercantil:</b> NO es primer pionero estricto del producto T2 — Multibank y Caja de Ahorros ya lo hicieron. Premium "first-time T2 local" se reduce a +10-25 bp (en vez de +25-50 bp en estimación previa). Esto baja el target de pricing en ~15 bp.</p>

<!-- ============ 4. SIZING ============= -->
<h2>4. Sizing: monto óptimo según objetivo de CAR</h2>
{kw['img']("cap")}
<div class="figcap">Impacto de la emisión T2 en el CAR y en capacidad incremental de crédito a corporativos 50% RW. Asume capital actual $450MM, APR $3,500MM, CAR pre 13%.</div>

<table>
<tr><th>Monto T2</th><th>CAR post</th><th>∆ CAR</th><th>Cap. crédito 50% RW</th><th>Cap. crédito 100% RW</th></tr>
{kw['cap_table_html']}
</table>

<p><b>Recomendación de sizing:</b></p>
<ul>
<li><b>Serie inicial $30 MM</b> — sube CAR 71 pb, suficiente para validar producto en mercado sin riesgo de sobre-suscripción fallida.</li>
<li><b>Programa total $100 MM en 3-4 series</b> escalonadas cada 4 meses — sube CAR a 15.7% (+271 pb) y desbloquea $1.5 bn en capacidad de crédito.</li>
<li>Si la prioridad es señal pública fuerte y demanda institucional masiva: emisión única <b>$60 MM</b> — más rara en plaza pero replica el modelo Banesco AT1 2022.</li>
</ul>

<div class="page-break"></div>

<!-- ============ 5. PRICING ============= -->
<h2>5. Pricing T2 10y — racional bottom-up doble approach</h2>

<h3>5.1 Premium T2 sub 10y vs senior bullet 5y</h3>
<table>
<tr><th>Componente del premium</th><th>Rango (bp)</th></tr>
<tr><td>Subordinación T2 vs senior (sub a senior, NO a depósitos)</td><td>{kw['t2_premium']['subordinacion_t2_vs_senior_bp'][0]:.0f}–{kw['t2_premium']['subordinacion_t2_vs_senior_bp'][1]:.0f}</td></tr>
<tr><td>Plazo 10y vs 5y (extension premium)</td><td>{kw['t2_premium']['plazo_10y_vs_5y_bp'][0]:.0f}–{kw['t2_premium']['plazo_10y_vs_5y_bp'][1]:.0f}</td></tr>
<tr><td>Iliquidez secundaria de sub en Panamá</td><td>{kw['t2_premium']['iliquidez_sub_panama_bp'][0]:.0f}–{kw['t2_premium']['iliquidez_sub_panama_bp'][1]:.0f}</td></tr>
<tr><td>First-time T2 local market (Mercantil pionero)</td><td>{kw['t2_premium']['first_time_t2_local_market_bp'][0]:.0f}–{kw['t2_premium']['first_time_t2_local_market_bp'][1]:.0f}</td></tr>
<tr><td><b>TOTAL T2 10y vs senior 5y</b></td><td><b>{kw['t2_premium']['total_t2_10y_vs_senior_5y_bp'][0]:.0f}–{kw['t2_premium']['total_t2_10y_vs_senior_5y_bp'][1]:.0f}</b> (midpoint {kw['t2_premium']['midpoint_bp']:.0f})</td></tr>
</table>

<h3>5.2 Aproximación A — desde Banesco AT1 anchor</h3>
<p>Banesco AT1 perpetual @ 7% (clearing real estimado 7.5-8% sin efecto Prival firm-UW).
T2 es ~100-200 bp menos riesgoso que AT1 (no loss-absorption, no cupón discrecional, no perpetuidad):</p>
<ul>
<li>Banesco T2 10y implícito: <b>{kw['pricing_t2']['approach_a_via_banesco_at1']['banesco_t2_implicito'][0]:.2f}%–{kw['pricing_t2']['approach_a_via_banesco_at1']['banesco_t2_implicito'][1]:.2f}%</b></li>
<li>+ Ajustes Mercantil (rating A vs A+, first-time, morosidad Capital Bank, step-down): +{kw['pricing_t2']['approach_a_via_banesco_at1']['ajustes_mercantil_bp']:.0f} bp</li>
<li><b>Target Mercantil T2 10y vía A: {kw['pricing_t2']['approach_a_via_banesco_at1']['target'][0]:.2f}%–{kw['pricing_t2']['approach_a_via_banesco_at1']['target'][1]:.2f}%</b></li>
</ul>

<h3>5.3 Aproximación B — desde Mercantil Holding senior 5y</h3>
<p>Mercantil Holding 5y @ 7.00% (cupón consistente de su programa exitoso 9 series).
Escalando para llevar a T2 sub 10y del Banco (no Holding):</p>
<ul>
<li>Bank vs Holding (banco regulado mejor que holding): −50 bp</li>
<li>Sub vs senior dentro del banco: +100–150 bp</li>
<li>Term premium 5y → 10y: +75–100 bp</li>
<li><b>Target Mercantil T2 10y vía B: {kw['pricing_t2']['approach_b_via_mercantil_holding']['target'][0]:.2f}%–{kw['pricing_t2']['approach_b_via_mercantil_holding']['target'][1]:.2f}%</b></li>
</ul>

<h3>5.4 Reconciliación</h3>
{kw['img']("pricing_cmp")}
<div class="figcap">Reconciliación de las dos aproximaciones de pricing. El consenso 50/50 ubica el target en {kw['pricing_t2']['consenso_t2_10y'][0]:.2f}%-{kw['pricing_t2']['consenso_t2_10y'][1]:.2f}%, midpoint {kw['pricing_t2']['midpoint_target']:.2f}%.</div>

<div class="rec-box">
<b>Pricing recomendado final:</b>
<ul>
<li><b>Best case (firm-UW agresivo, ventana favorable):</b> 7.00–7.50%</li>
<li><b>Base case (best-efforts, ventana actual):</b> <b>{kw['pricing_t2']['consenso_t2_10y'][0]:.2f}–{kw['pricing_t2']['consenso_t2_10y'][1]:.2f}%</b> (midpoint <b>{kw['pricing_t2']['midpoint_target']:.2f}%</b>)</li>
<li><b>Stress case (sin firm-UW, post-Banesco):</b> 8.00–8.75%</li>
</ul>
</div>

<div class="page-break"></div>

<!-- ============ 6. ANCHOR BANESCO ============= -->
<h2>6. Anchor Banesco AT1 — relectura para T2</h2>

<p>El bono Banesco perpetual subordinado AT1 al 7% (May 2022, $78.131 MM colocado bajo SMV-541-21) es el comparable
más cercano <b>conceptualmente</b> (capital regulatorio bancario), aunque estructuralmente diferente:</p>

<table>
<tr><th>Variable</th><th>Banesco AT1 (referencia)</th><th>Mercantil T2 (propuesto)</th><th>Implicación</th></tr>
<tr><td>Cupón observado</td><td>7.00% (firm-UW Prival)</td><td>{kw['pricing_t2']['consenso_t2_10y'][0]:.2f}-{kw['pricing_t2']['consenso_t2_10y'][1]:.2f}%</td><td>Mercantil sin firm-UW debería estar dentro del rango</td></tr>
<tr><td>Cupón clearing real</td><td>~7.5-8.0%</td><td>Por determinar</td><td>Si Mercantil va firm-UW, comprime ~25-50 bp</td></tr>
<tr><td>Estructura</td><td>AT1 perpetual subordinado</td><td>T2 sub 10y bullet</td><td>T2 ~100-200 bp más barato que AT1</td></tr>
<tr><td>Rating emisor</td><td>A+(pan) Fitch (post upgrade may-26)</td><td>A(pa) Moody's Local</td><td>Mercantil paga +25-35 bp</td></tr>
<tr><td>Tier de capital</td><td>Tier 1 (AT1)</td><td>Tier 2</td><td>Mercantil para Total Capital, no T1</td></tr>
<tr><td>Loss-absorption</td><td>Sí — write-down si CET1 bajo trigger</td><td>No (no requerido en T2 SBP)</td><td>T2 menos riesgoso para inversor</td></tr>
<tr><td>Cupón discrecional</td><td>Sí (puede saltarse sin default)</td><td>No (obligatorio)</td><td>T2 menos riesgoso para inversor</td></tr>
<tr><td>Vencimiento definido</td><td>No (perpetuo, call 2028)</td><td>Sí (10y bullet)</td><td>T2 menos extension risk</td></tr>
</table>

<p>El Banesco AT1 es <b>simultáneamente</b> útil y limitado como benchmark:</p>
<ul>
<li><b>Útil:</b> es la única emisión panameña reciente de capital regulatorio bancario "real" (no senior, no preferred); valida que existe apetito institucional por instrumentos de capital bancario subordinados.</li>
<li><b>Limitado:</b> AT1 perpetual ≠ T2 10y bullet — son productos distintos con base inversora distinta y premium muy diferente. La "tasa Banesco 7%" no aplica a Mercantil T2 directamente.</li>
</ul>

<!-- ============ 7. UNIVERSO CAPITAL ============= -->
<h2>7. Universo de instrumentos de capital bancario en Panamá</h2>
{kw['img']("landscape")}
<div class="figcap">Universo histórico de emisiones de instrumentos de capital bancario panameño (acciones preferentes acumulativas + bonos de plazo &gt;20y). Banesco domina con $78MM AT1 2022 al 7% + $40MM preferentes 2011-2012 al 7.5%.</div>

<p><b>Lecturas del landscape:</b></p>
<ul>
<li>El mercado panameño tiene <b>poco volumen total de instrumentos de capital bancario</b>: ~$120MM total entre Banesco AT1 ($78MM) y preferentes ($40MM acumulativas).</li>
<li>Históricamente la "tasa de mercado" para capital subordinado bancario en Panamá ha sido <b>7.0-7.5%</b> (Banesco 2011, 2012, 2022) — independientemente de plazo y estructura.</li>
<li>Este 7-7.5% funciona como <b>"techo psicológico" para inversionistas institucionales</b> — Mercantil tendrá que comunicar claramente por qué su producto T2 puede pagar dentro de ese rango (no por encima) a pesar de ser pionero del producto.</li>
</ul>

<!-- ============ 8. CLÁUSULAS ============= -->
<h2>8. Cláusulas y estructura recomendada</h2>
<table>
<tr><th>Variable</th><th>Recomendación</th><th>Racional</th></tr>
<tr><td>Plazo</td><td>10 años bullet</td><td>Estándar T2; maximiza vida útil regulatoria (5y al 100% + 5y step-down)</td></tr>
<tr><td>Call</td><td><b>No callable</b> en emisión inicial</td><td>Mejor pricing (-15-25 bp por no extension risk); más simple para inversores; SBP igual requiere su aprobación si quisieran callar</td></tr>
<tr><td>Cupón</td><td>Fijo trimestral</td><td>Estándar Panamá; mejor cash management que semestral</td></tr>
<tr><td>Base día</td><td>30/360</td><td>Más usado en Panamá</td></tr>
<tr><td>Subordinación</td><td>Subordinado a depositantes, senior debt y deuda sub ordinaria; senior solo a CET1 + AT1</td><td>Requisito SBP para reconocimiento T2</td></tr>
<tr><td>Negative pledge</td><td>Sí, estándar</td><td>Protege a holders T2 vs nuevos gravámenes senior</td></tr>
<tr><td>Cross-default</td><td>Sí, con umbral $10MM</td><td>Estándar; protege evento de quiebra técnica</td></tr>
<tr><td>Financial covenants</td><td>CAR mínimo 11% (cushion vs SBP 8%); ratio liquidez 30%</td><td>Reconforta inversores; no es restrictivo para Mercantil actual</td></tr>
<tr><td>Eventos de default específicos T2</td><td>Solo no-pago de cupón > 30d o quiebra; no triggers de capital</td><td>T2 NO requiere loss-absorption en Panamá</td></tr>
</table>

<div class="page-break"></div>

<!-- ============ 9. PROGRAMA ============= -->
<h2>9. Estructura del programa y cadencia óptima</h2>

<table>
<tr><th>Variable</th><th>Recomendado</th></tr>
<tr><td>Monto total programa</td><td>${kw['program']['monto_total_programa_mm']} MM</td></tr>
<tr><td>Monto por serie</td><td>${kw['program']['monto_por_serie_mm']} MM</td></tr>
<tr><td>Número de series</td><td>{kw['program']['n_series']}</td></tr>
<tr><td>Frecuencia entre series</td><td>{kw['program']['frecuencia_meses_entre_series']} meses</td></tr>
<tr><td>Duración total del programa</td><td>{kw['program']['duracion_programa_meses']} meses</td></tr>
<tr><td>Cupón asumido (midpoint)</td><td>{kw['program']['cupon_pct']:.2f}%</td></tr>
<tr><td>Intereses anuales (programa completo)</td><td>${kw['program']['interes_anual_programa_total_mm']} MM/año</td></tr>
<tr><td>Intereses totales vida del programa (10y)</td><td>${kw['program']['intereses_totales_vida_programa_mm']} MM</td></tr>
</table>

<p><b>Cadencia recomendada:</b></p>
<ol>
<li><b>Serie A:</b> $30 MM — emisión inaugural, validar producto, anclar pricing público.</li>
<li><b>Serie B:</b> $30 MM, 4 meses después — confirma demanda repetida, sube CAR a ~14.4%.</li>
<li><b>Serie C:</b> $30 MM, 8 meses después de A — completa el programa cerca del techo, ya en 15.1% CAR.</li>
<li><b>Serie D:</b> $10 MM (opcional), 12 meses después — completar al $100 MM si quedó demanda no satisfecha en B/C.</li>
</ol>

<!-- ============ 10. VENTANA ============= -->
<h2>10. Ventana de mercado y timing competitivo</h2>
<p>El spread mediano T2/T3 actual es <b>{kw['window']['spread_actual_bp']:.0f} bp</b>, percentil <b>{kw['window']['percentil']*100:.0f}%</b>
vs últimos 5 años. Lectura: {kw['window']['interpretacion']}.</p>

<p><b>Pipeline competidor (próximos 60 días, bonos largos):</b></p>
<table>
<tr><th>Emisor</th><th>Fecha</th><th>Plazo</th><th>Cupón</th><th>Monto</th><th>Estado</th></tr>
{kw['pipeline_html']}
</table>

<div class="warn-box">
<b>Timing crítico:</b> Banesco está colocando $40 MM AT1 perpetual en próximos 30-60 días tras su upgrade Fitch a A+(pan).
Esta colocación absorberá apetito institucional por instrumentos de capital bancario panameño.
<br><br>
Mercantil tiene una <b>ventaja estructural</b>: T2 ≠ AT1, base inversora distinta (AFP conservadoras, aseguradoras
restringidas no pueden tener AT1 pero sí T2). Aún así, conviene NO pricing en la misma ventana que Banesco para evitar
confusión narrativa.
</div>

<p><b>Tres ventanas posibles:</b></p>
<ol>
<li><b>Antes de Banesco</b> (próximos 21-30 días): documentación apurada, sin tiempo para educación de inversores sobre T2; riesgo alto.</li>
<li><b>En paralelo con Banesco</b>: aprovecha "calor" del mercado tras upgrade Banesco, pero requiere posicionamiento muy claro como T2 (no AT1).</li>
<li><b>Después de Banesco</b> (90+ días tras pricing Banesco, ≈sep-oct 2026): base institucional digiere Banesco, busca diversificación, tiene tiempo para educarse sobre T2.</li>
</ol>

<div class="rec-box">
<b>Recomendación timing:</b> <b>Ventana 3 (después de Banesco)</b>. Razón principal: T2 es producto nuevo para
inversionistas panameños; necesita pre-marketing y roadshow completo. El "after Banesco" da ese tiempo y reduce
canibalización. Si la ventana de mercado se cierra (spreads amplían), pasar a Ventana 1 con producto menos óptimo.
</div>

<!-- ============ 11. UNDERWRITER ============= -->
<h2>11. Estrategia de underwriter</h2>

<p>Comparativo de comisiones para bonos bancarios A(pa) en Panamá (verificado de prospectos SMV):</p>
<ul>
<li>Estructuración típica: 0.30-0.60% (Mercantil Holding-Prival precedente: 0.321%)</li>
<li>Colocación típica: 0.535%</li>
<li>Total comisiones casa bolsa: 0.85-1.10%</li>
<li>All-in (incluyendo SMV, Latinex, legales): 1.10-1.30%</li>
<li>Premium subordinado / AT1: +20-50 bp</li>
<li>Firm-UW (raro en Panamá): +25-50 bp adicionales</li>
</ul>

<p><b>Para Mercantil T2 sub 10y $30MM</b> (default modelo):</p>
<table>
<tr><th>Variable</th><th>Valor</th></tr>
<tr><td>Fee upfront all-in (best-efforts + premium sub)</td><td>{kw['uw_default']['fee_upfront_pct']:.2f}%</td></tr>
<tr><td>Ahorro esperado en cupón si firm-UW</td><td>{kw['uw_default']['coupon_subsidio_bp']:.0f} bp</td></tr>
<tr><td>Fee total absoluto</td><td>${kw['uw_default']['fee_total_mm']:.2f} MM</td></tr>
<tr><td>NPV neto firm vs best-efforts (10y)</td><td><b>${kw['uw_default']['neto_firm_vs_be_mm']:.2f} MM</b></td></tr>
<tr><td>Break-even (bp mínimos para que firm convenga)</td><td>{kw['uw_default']['break_even_bp']:.1f} bp</td></tr>
</table>

<p><b>Casas candidatas:</b></p>
<ul>
<li><b>Prival Securities</b> — estructuró Banesco AT1 2022 + Mercantil Holding programa. Tiene relación con Mercantil
y experiencia en capital regulatorio bancario. <b>Candidato natural por afinidad y precedente.</b></li>
<li><b>BG Valores</b> — la casa más grande de Panamá; balance robusto; base inversora institucional fuerte.</li>
<li><b>MMG Bank</b> — banca privada con relación cercana a aseguradoras y AFP.</li>
</ul>

<div class="page-break"></div>

<!-- ============ 12. SENSIBILIDADES ============= -->
<h2>12. Sensibilidades y escenarios de stress</h2>

<table>
<tr><th>Escenario</th><th>Cupón target 10y</th><th>Monto realista</th><th>∆ CAR</th><th>Comentario</th></tr>
<tr>
  <td><b>Best case</b><br><i>Firm UW agresivo + ventana favorable</i></td>
  <td>7.00-7.50%</td><td>$50-75 MM</td><td>+118 a +178 pb</td>
  <td>Requiere Prival firm + spreads bancarios tightening 25-50 bp</td>
</tr>
<tr>
  <td><b>Base case</b><br><i>Recomendación principal</i></td>
  <td>7.50-8.50%</td><td>$30 MM serie inicial</td><td>+71 pb</td>
  <td>Best-efforts; ventana actual neutral; modelo Banesco AT1 escalado</td>
</tr>
<tr>
  <td><b>Stress case 1</b><br><i>Mercantil paga premium first-T2-local</i></td>
  <td>8.00-9.00%</td><td>$20-30 MM</td><td>+47-71 pb</td>
  <td>Si AFP exigen prima fuerte por producto desconocido</td>
</tr>
<tr>
  <td><b>Stress case 2</b><br><i>Spreads amplían post-Banesco</i></td>
  <td>8.50-9.50%</td><td>$15-25 MM</td><td>+35-59 pb</td>
  <td>Si Banesco satura demanda y el sentimiento bancario se deteriora</td>
</tr>
<tr>
  <td><b>Stress case 3</b><br><i>Downgrade Mercantil por morosidad CB</i></td>
  <td>9.00-10.00%</td><td>$15-20 MM</td><td>+35-47 pb</td>
  <td>Si Moody's Local baja por presión persistente en cartera heredada Capital Bank</td>
</tr>
</table>

<!-- ============ 13. PRÓXIMOS PASOS ============= -->
<h2>13. Próximos pasos operativos</h2>

<h3>Fase 1 — Decisión interna (próximos 7-14 días)</h3>
<ol>
<li>Validar internamente con riesgos, ALCO y junta directiva la estructura T2 sub 10y bullet vs alternativas (AT1, equity).</li>
<li>Definir target específico de CAR objetivo (p.ej. "subir de 13% a 14.5% en 12 meses").</li>
<li>Definir capacidad incremental de originación deseada y mapping a tipos de cliente (RW objetivo).</li>
<li>Confirmar autorización SBP para programa Tier 2 — preparar borrador de notificación.</li>
</ol>

<h3>Fase 2 — Estructuración (días 14-45)</h3>
<ol start="5">
<li>Sondeo confidencial con 3 casas candidatas (Prival, BG, MMG): indicación non-binding de fee, cupón target firm vs best-efforts.</li>
<li>Re-contratar calificación con Fitch CA (que retiró cobertura en may-2025) o solicitar a Moody's Local rating específico para el programa T2.</li>
<li>Documentación SMV: prospecto + suplemento de pricing. Usar el de Banesco AT1 2022 como template (mismo abogado/estructurador puede ser Prival).</li>
<li>Pre-marketing soft con 5-10 institucionales clave (AFP, aseguradoras top, bancas privadas) para validar apetito T2.</li>
</ol>

<h3>Fase 3 — Colocación (días 45-90)</h3>
<ol start="9">
<li>Roadshow completo (4-6 reuniones con base inversora).</li>
<li>Book-building (3-5 días) con bid colection.</li>
<li>Pricing day: definir cupón final según book.</li>
<li>Settlement T+3.</li>
<li>Comunicación pública post-pricing destacando logro de capital y plan de crecimiento de crédito.</li>
</ol>

<h2>14. Metodología y limitaciones</h2>

<h3>Datos utilizados</h3>
<ul>
<li>Mercado secundario: 84,191 trades Latinex 10 años; 18,210 con YTM calculado.</li>
<li>Mercado primario: 2,573 emisiones vigentes vía API Latinex.</li>
<li>Anchor Banesco: investigación dirigida sobre IN-A 2025, EE.FF. KPMG, SMV-541-21.</li>
<li>Comisiones: prospectos públicos SMV (Mercantil Holding, Multibank, Banesco, Capital Bank).</li>
<li>Reglas SBP Tier 2: Acuerdos 1-2015 y 3-2016 (en investigación, ver agente complementario).</li>
<li>Ratings: Moody's Local PA (Mercantil A(pa), 29-may-2025); Fitch (Banesco A+(pan), 11-may-2026).</li>
</ul>

<h3>Limitaciones declaradas</h3>
<ul>
<li><b>Capital y APR de Mercantil:</b> estimados ($450MM capital, $3.5bn APR, 13% CAR). Reemplazar con cifras reales del banco.</li>
<li><b>Premium T2 vs senior y vs AT1:</b> rango ancho (estimación basada en mercados emergentes; Panamá no tiene precedente T2 doméstico).</li>
<li><b>Fee real Banesco-Prival:</b> estimado 1.0-1.5% all-in; el dato real cambiaría ligeramente el "senior implícito" Banesco.</li>
<li><b>Calificación Mercantil:</b> solo Moody's Local viva (Fitch retiró cobertura). Re-contratar Fitch sería positivo.</li>
<li><b>Liquidez secundaria 10y bancario:</b> casi inexistente. Holders serán buy-and-hold.</li>
</ul>

<h3>Sensibilidad del análisis a inputs nuevos</h3>
<ul>
<li><b>Capital y APR reales de Mercantil:</b> cambia todo el análisis de sizing y multiplicadores.</li>
<li><b>Cupón final Banesco reapertura 2026:</b> mejor evidencia del clearing post-upgrade.</li>
<li><b>Confirmación de reglas T2 SBP:</b> validar step-down, requisitos cláusulas, aprobación.</li>
<li><b>Resultado de pre-marketing con AFP:</b> determina demanda real por T2 vs AT1.</li>
</ul>

<div style="margin-top: 30px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 7.5pt; color: #888;">
  Generado: {kw['snapshot']} · Fuentes: latinexbolsa.com, supervalores.gob.pa, superbancos.gob.pa, home.treasury.gov, fitchratings.com, moodyslocal.com.pa<br>
  No constituye recomendación de inversión, opinión legal ni asesoría regulatoria.
</div>

</body></html>"""


if __name__ == "__main__":
    main()
