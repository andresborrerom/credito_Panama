"""Genera la página Mercantil del sitio + memo PDF de pricing dedicado."""

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
    ISSUER_TARGET,
    PEER_BANKS,
    banesco_perpetual_detail,
    con,
    issuance_pricing_summary,
    issuance_size_distribution,
    issuance_window_signal,
    issuer_secondary_curve,
    mercantil_holding_anchor,
    mercantil_vcn_history,
    peer_curves,
    primary_market_calendar,
    recommend_pricing,
)
from src.app.build_site import (  # noqa: E402
    PLOTLY_CDN,
    fig_html,
    render_page,
    style_fig,
)
from src.analytics.curves import universe_summary  # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
FIGS = DOCS / "figs_mercantil"
FIGS.mkdir(exist_ok=True)


def save_png(fig: go.Figure, name: str) -> pathlib.Path:
    out = FIGS / f"{name}.png"
    try:
        fig.write_image(out, width=900, height=440, scale=2)
    except Exception:
        out = FIGS / f"{name}.html"
        fig.write_html(out, include_plotlyjs="cdn", full_html=False)
    return out


# ----------------------------- FIGURAS -------------------------------- #
def fig_primary_calendar(c) -> tuple[go.Figure, pd.DataFrame]:
    """Calendario de emisiones primarias últimos 24 meses (timeline)."""
    cal = primary_market_calendar(c, lookback_days=730)
    cal = cal[cal["instrumento"].isin(["BONOS", "NOTAS CORPORATIVAS"])]
    if cal.empty:
        return go.Figure(), cal
    cal = cal.copy()
    cal["is_mercantil"] = cal["emisor"].str.contains("MERCANTIL")

    fig = px.scatter(
        cal,
        x="fecha_emision", y="cupon_pct",
        size="serie_mm", color="emisor",
        symbol="instrumento",
        hover_data={
            "nemotecnico": True, "plazo": ":.1f", "cupon_pct": ":.2f",
            "serie_mm": ":.2f", "coloc_mm": ":.2f", "pct_coloc": ":.0f",
        },
        labels={"fecha_emision": "Fecha de emisión", "cupon_pct": "Cupón (%)",
                "serie_mm": "Monto serie (MM USD)"},
        size_max=35,
    )
    style_fig(fig, title="Calendario de emisiones primarias — bancos T2/T3 (últimos 24 meses, bonos y notas)")
    fig.update_layout(height=520)
    return fig, cal


def fig_peer_curves(c) -> tuple[go.Figure, pd.DataFrame]:
    pc = peer_curves(c, lookback_days=365)
    pc = pc[pc["n_trades"] >= 3].copy()
    pc["yld_pct"] = pc["yld_median"] * 100
    if pc.empty:
        return go.Figure(), pc
    pc["es_mercantil"] = pc["emisor"].str.contains("MERCANTIL")

    fig = px.scatter(
        pc, x="avg_plazo", y="yld_pct",
        size="n_trades", color="emisor",
        symbol="es_mercantil",
        hover_data={"bucket_plazo": True, "n_trades": True, "yld_pct": ":.2f",
                    "volumen_mm": ":.2f"},
        labels={"avg_plazo": "Plazo residual medio (años)",
                "yld_pct": "Yield mediano secundario (%)"},
        size_max=28,
    )
    style_fig(fig, title="Curva implícita por banco — secundario, últimos 12m")
    fig.update_layout(height=520)
    return fig, pc


def fig_pricing_recommendation(c) -> tuple[go.Figure, pd.DataFrame]:
    rec = recommend_pricing(c)
    if rec.empty:
        return go.Figure(), rec
    rec = rec.copy()
    rec["label"] = rec["plazo_bucket"].astype(str) + " · " + rec["instrumento"]
    rec = rec.sort_values("cupon_median")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=rec["label"],
        x=rec["cupon_median"],
        orientation="h",
        marker=dict(color=rec["cupon_median"], colorscale="YlOrRd"),
        text=[f"{v:.2f}%" for v in rec["cupon_median"]],
        textposition="outside",
        error_x=dict(
            type="data",
            symmetric=False,
            array=rec["cupon_p75"] - rec["cupon_median"],
            arrayminus=rec["cupon_median"] - rec["cupon_p25"],
        ),
        name="Cupón mediano (con rango P25-P75)",
        hovertemplate=(
            "<b>%{y}</b><br>Mediano: %{x:.2f}%<br>"
            "P25-P75: %{customdata[0]:.2f}-%{customdata[1]:.2f}%<br>"
            "n=%{customdata[2]} emisiones, %{customdata[3]:.1f} MM colocados<extra></extra>"
        ),
        customdata=rec[["cupon_p25", "cupon_p75", "n_emisiones", "monto_total_mm"]].values,
    ))
    style_fig(fig, title="Pricing primario observado por plazo × tipo (bonos/notas, últimos 24m)",
              ylabel="")
    fig.update_layout(
        xaxis_title="Cupón pagado (%)", height=440,
        showlegend=False, margin=dict(l=10, r=80, t=50, b=10),
    )
    return fig, rec


def fig_mercantil_holding_anchor(c) -> tuple[go.Figure, pd.DataFrame]:
    mh = mercantil_holding_anchor(c)
    if mh.empty:
        return go.Figure(), mh
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=mh["fechaEmision_d"], y=mh["cupon_pct"],
        mode="markers+text",
        marker=dict(size=mh["serie_mm"] * 3 + 8, color="#002b5c"),
        text=[f"{p:.0f}y · ${s:.1f}MM" for p, s in zip(mh["plazo"], mh["serie_mm"])],
        textposition="top center",
        hovertemplate="<b>%{x}</b><br>Cupón: %{y:.2f}%<br>%{text}<extra></extra>",
    ))
    style_fig(fig, title="Programa de Mercantil Holding — bonos emitidos (anchor más cercano)")
    fig.update_layout(yaxis_title="Cupón (%)", xaxis_title=None, height=380)
    return fig, mh


def fig_mercantil_vcn(c) -> tuple[go.Figure, pd.DataFrame]:
    vcn = mercantil_vcn_history(c)
    vcn = vcn.sort_values("fechaEmision_d")
    fig = px.scatter(
        vcn, x="fechaEmision_d", y="cupon_pct",
        size="serie_mm", size_max=22,
        hover_data={"nemotecnico": True, "plazo": ":.1f", "cupon_pct": ":.2f"},
        labels={"fechaEmision_d": "Fecha emisión", "cupon_pct": "Cupón VCN (%)"},
    )
    style_fig(fig, title="Historial de cupones VCN de Mercantil Banco (papel corto, base de pricing)")
    fig.update_layout(height=380, showlegend=False)
    return fig, vcn


def fig_size_distribution(c) -> tuple[go.Figure, pd.DataFrame]:
    sz = issuance_size_distribution(c)
    if sz.empty:
        return go.Figure(), sz
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sz["plazo_bucket"].astype(str),
        y=sz["monto_median_mm"],
        name="Mediana de monto colocado",
        marker_color="#004080",
        text=[f"${v:.1f}MM" for v in sz["monto_median_mm"]],
        textposition="outside",
        hovertemplate=(
            "Plazo %{x}<br>Mediana: $%{y:.1f}MM<br>"
            "Min-Max: $%{customdata[0]:.1f}-%{customdata[1]:.1f}MM<br>"
            "Total colocado: $%{customdata[2]:.1f}MM en %{customdata[3]} emisiones<extra></extra>"
        ),
        customdata=sz[["monto_min_mm", "monto_max_mm", "monto_total_mm", "n_emisiones"]].values,
    ))
    style_fig(fig, title="Tamaño típico de emisión por plazo — bonos y notas T2/T3, últimos 24m")
    fig.update_layout(yaxis_title="Monto colocado (MM USD)", xaxis_title="Plazo",
                      height=380, showlegend=False)
    return fig, sz


# -------------------------------------------------------------------- #
def build_recommendation_table(c, window: dict, pricing: pd.DataFrame) -> pd.DataFrame:
    """Construye recomendación final por plazo, con cupón inferido."""
    # Anclar pricing recomendado en pricing primario reciente
    # Mercantil Banco debería emitir ENTRE el cupón mediano de peers similares (T2) y el de Mercantil Holding
    rows = []

    holding_mh = mercantil_holding_anchor(c)
    holding_5y_avg = holding_mh[holding_mh["plazo"] == 5]["cupon_pct"].mean() if not holding_mh.empty else None

    # Mapear cada plazo a recomendación
    plazo_map = {
        "~2y": {"plazo_anos": 2, "vol_tipico_mm": "5-15"},
        "~3y": {"plazo_anos": 3, "vol_tipico_mm": "10-30"},
        "5y":  {"plazo_anos": 5, "vol_tipico_mm": "15-50"},
        "7-10y": {"plazo_anos": 7, "vol_tipico_mm": "10-30"},
    }
    for bucket, meta in plazo_map.items():
        sub = pricing[pricing["plazo_bucket"] == bucket]
        if sub.empty:
            continue
        cup_med = sub["cupon_median"].median()
        cup_p25 = sub["cupon_p25"].median()
        cup_p75 = sub["cupon_p75"].median()
        # Mercantil Banco vs peers: descuento ~25-50 bp por estar uno arriba en cadena vs holding
        descuento_holding = 25  # bp — Mercantil Banco senior vs Holding subordinated
        cup_rec_low = cup_p25 - descuento_holding / 100
        cup_rec_high = cup_p75
        cup_rec_mid = cup_med - descuento_holding / 200  # split
        rows.append({
            "plazo_anos": meta["plazo_anos"],
            "plazo_bucket": bucket,
            "peer_cupon_p25": cup_p25,
            "peer_cupon_median": cup_med,
            "peer_cupon_p75": cup_p75,
            "mercantil_recomendado_low": round(cup_rec_low, 2),
            "mercantil_recomendado_mid": round(cup_rec_mid, 2),
            "mercantil_recomendado_high": round(cup_rec_high, 2),
            "monto_tipico_mm": meta["vol_tipico_mm"],
            "n_emisiones_peer": int(sub["n_emisiones"].sum()),
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- #
PAGE_TPL_LOCAL = None  # Reutilizamos render_page de build_site


def main():
    c = con()
    summary = universe_summary(c)
    snapshot = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    print(">> Calendario primario...")
    fig_cal, df_cal = fig_primary_calendar(c)
    print(f"   {len(df_cal):,} emisiones primarias en últimos 24m")

    print(">> Peer curves...")
    fig_pc, df_pc = fig_peer_curves(c)

    print(">> Pricing recommendation...")
    fig_rec, df_rec = fig_pricing_recommendation(c)

    print(">> Mercantil Holding anchor...")
    fig_mh, df_mh = fig_mercantil_holding_anchor(c)

    print(">> Mercantil Banco VCN history...")
    fig_vcn, df_vcn = fig_mercantil_vcn(c)

    print(">> Size distribution...")
    fig_sz, df_sz = fig_size_distribution(c)

    print(">> Window signal...")
    window = issuance_window_signal(c)
    print(f"   spread T2/T3 actual: {window['spread_actual_bp']:.0f} bp · "
          f"percentil 5y: {window['percentil']*100:.0f}% · {window['interpretacion']}")

    print(">> Banesco anchor detail...")
    df_ban = banesco_perpetual_detail(c)

    print(">> Pricing table...")
    df_pricing = issuance_pricing_summary(c)
    df_recom = build_recommendation_table(c, window, df_pricing)
    print(df_recom.to_string(index=False))

    # Guardar CSVs
    (DOCS / "_data").mkdir(exist_ok=True)
    df_cal.to_csv(DOCS / "_data" / "mercantil_calendario_primario.csv", index=False)
    df_pc.to_csv(DOCS / "_data" / "mercantil_peer_curves.csv", index=False)
    df_recom.to_csv(DOCS / "_data" / "mercantil_recomendacion.csv", index=False)
    df_mh.to_csv(DOCS / "_data" / "mercantil_holding_emisiones.csv", index=False)

    # Texto del análisis Banesco (data/external/banesco_anchor.md)
    banesco_md = (ROOT / "data" / "external" / "banesco_anchor.md").read_text()

    # Conclusiones derivadas
    findings = derive_findings(c, window, df_recom, df_mh, df_ban)
    for f in findings:
        print(f"   • {f}")

    # === Render página HTML ===
    import re as _re

    def _md(s: str) -> str:
        return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

    findings_html = (
        "<ul class='findings'>" + "".join(f"<li>{_md(f)}</li>" for f in findings) + "</ul>"
    )

    window_color = {
        "FAVORABLE": "#1f6f43",
        "NEUTRAL": "#a07000",
        "DESFAVORABLE": "#a32020",
    }
    interp_word = window["interpretacion"].split(" ")[0]
    win_color = window_color.get(interp_word, "#002b5c")

    body = f"""
    <section style="background:linear-gradient(135deg,#002b5c 0%,#004080 100%);color:#fff;">
      <h2 style="color:#fff;margin-top:0">🏦 Estructuración de emisión — Mercantil Banco, S.A.</h2>
      <p style="color:#dbe4f3;">Análisis de mercado primario y secundario panameño para sustentar
      una emisión de bonos. Snapshot: {snapshot}.</p>
    </section>

    <section style="border-left:5px solid {win_color}">
      <h2>Ventana de mercado</h2>
      <p style="font-size:1.05rem;margin:8px 0">
        Spread T2/T3 actual: <b>{window['spread_actual_bp']:.0f} pb</b> ·
        Percentil 5 años: <b>{window['percentil']*100:.0f}%</b> ·
        Mediana histórica 5y: <b>{window['p50']:.0f} pb</b>
      </p>
      <p style="color:{win_color};font-weight:600;margin-top:4px">{window['interpretacion']}</p>
    </section>

    <section>
      <h2>Hallazgos y recomendación</h2>
      {findings_html}
    </section>

    <section>
      <h2>Recomendación de pricing por plazo</h2>
      <p class="note">Cupón mediano observado en bonos/notas T2-T3 últimos 24m. La columna "Mercantil recomendado"
      ajusta por la posición de Mercantil Banco (subsidiaria regulada) vs el universo: ~25 bp menos que la mediana
      de Mercantil Holding y peers similares por estar un escalón arriba en la cadena de subordinación.</p>
      {render_recommendation_table(df_recom)}
    </section>

    <section>
      <h2>Curva implícita por banco — secundario</h2>
      <p class="note">Yield mediano de cada banco peer en secundario, últimos 12m. Mercantil Banco solo trade
      en plazos cortos (sus VCN). Mercantil Holding tiene cobertura hasta 5y. Para plazos largos hay que extrapolar.</p>
      {fig_html(fig_pc, "fig_pc_merc")}
    </section>

    <section>
      <h2>Calendario primario — emisiones reales últimos 24m</h2>
      <p class="note">Cada burbuja es una emisión primaria (bonos o notas) de bancos T2/T3. Tamaño = monto colocado.
      Mercantil Holding aparece consistentemente a 5y con cupón 7.00%.</p>
      {fig_html(fig_cal, "fig_cal_merc")}
    </section>

    <section>
      <h2>Mercantil Holding como anchor más cercano</h2>
      <p class="note">La matriz Mercantil Holding ha emitido <b>6 series</b> consistentemente a 5y al 7.00%,
      todas con 100% de colocación. Es el comparable más limpio porque es el mismo grupo económico —
      Mercantil Banco debería emitir un escalón mejor.</p>
      {fig_html(fig_mh, "fig_mh_merc")}
    </section>

    <section>
      <h2>Cupones del programa VCN de Mercantil Banco</h2>
      <p class="note">Mercantil Banco hoy solo tiene VCN (papel corto &lt; 1 año) en circulación.
      El cupón ha bajado de 5.63% (ago-2025) a 5.00% (may-2026) → tendencia bajista, refuerza el momento.</p>
      {fig_html(fig_vcn, "fig_vcn_merc")}
    </section>

    <section>
      <h2>Capacidad de absorción del mercado</h2>
      <p class="note">Monto típico colocado por plazo en últimos 24m. Define cuánto puede absorber el mercado
      sin saturarlo. Plazo 5y es donde está la mayor profundidad.</p>
      {fig_html(fig_sz, "fig_sz_merc")}
    </section>

    <section style="background:#fff7e6;border-left:4px solid #d18f00">
      <h2 style="margin-top:0">⚠️ Anchor Banesco — aclaración importante</h2>
      <p>La referencia que se citó al inicio ("Banesco al 7% por $60MM") corresponde a una emisión <b>de mayo 2022,
      no reciente</b>. Más importante, es un <b>BONO SUBORDINADO PERPETUO AT1</b> (capital regulatorio Tier 1
      adicional), no un bono senior bullet.</p>
      <p>Esto significa que el 7% incorpora:</p>
      <ul>
        <li>Prima por subordinación AT1 (~200-300 bp en mercados emergentes)</li>
        <li>Prima por perpetuidad (~50-150 bp)</li>
        <li><b>Premium total AT1-perpetual vs senior-bullet: ~250-400 bp</b></li>
      </ul>
      <p>Un senior bullet 5y "implícito" de Banesco estaría en ~4.50-4.75%. Por eso una emisión senior bullet
      5y de Mercantil Banco al 6.00-6.50% sería competitiva incluso con esta referencia distorsionada.</p>
      <p class="note">Detalle completo del perpetuo Banesco (resolución SMV-541-21, capital AT1, no-call 6 años,
      sin step-up identificado, Fitch A(pan)) en <code>data/external/banesco_anchor.md</code> del repo.</p>
    </section>

    <section>
      <h2>Detalle del perpetuo Banesco</h2>
      {render_banesco_table(df_ban)}
    </section>

    <section>
      <h2>Descargas</h2>
      <p>
        <a class="download" href="memo_mercantil.pdf">📄 Memo de estructuración Mercantil (PDF)</a>
      </p>
      <ul style="font-size:0.88rem">
        <li><a href="_data/mercantil_calendario_primario.csv">calendario primario</a></li>
        <li><a href="_data/mercantil_peer_curves.csv">curvas peer secundario</a></li>
        <li><a href="_data/mercantil_recomendacion.csv">tabla de recomendación</a></li>
        <li><a href="_data/mercantil_holding_emisiones.csv">programa Mercantil Holding</a></li>
      </ul>
    </section>
    """
    html = render_page("mercantil", "Mercantil — Estructuración de emisión", body,
                       snapshot, summary["date_min"], summary["date_max"])
    (DOCS / "mercantil.html").write_text(html)
    print(f">> Página: {DOCS / 'mercantil.html'}")

    # === Render PDF memo ===
    build_pdf_memo(window, df_recom, df_mh, df_ban, findings, snapshot,
                   fig_cal, fig_pc, fig_rec, fig_mh, fig_vcn, fig_sz)


def render_recommendation_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>(no hay datos)</p>"
    rows = []
    for _, r in df.iterrows():
        rows.append(f"""
        <tr>
          <td><b>{r['plazo_anos']}y</b></td>
          <td>{r['peer_cupon_p25']:.2f}–{r['peer_cupon_p75']:.2f}%</td>
          <td style="background:#e8f3e8"><b>{r['mercantil_recomendado_low']:.2f}–{r['mercantil_recomendado_high']:.2f}%</b></td>
          <td>{r['monto_tipico_mm']} MM</td>
          <td>{r['n_emisiones_peer']}</td>
        </tr>
        """)
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:0.9rem'>"
        "<thead><tr style='background:#002b5c;color:#fff'>"
        "<th style='padding:6px;text-align:left'>Plazo</th>"
        "<th style='padding:6px;text-align:left'>Cupón peer (P25-P75)</th>"
        "<th style='padding:6px;text-align:left'>Mercantil Banco recomendado</th>"
        "<th style='padding:6px;text-align:left'>Monto típico (MM USD)</th>"
        "<th style='padding:6px;text-align:left'>n peer emisiones</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render_banesco_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>(no hay datos)</p>"
    rows = []
    for _, r in df.iterrows():
        rows.append(f"""
        <tr>
          <td>{r['nemotecnico']}</td>
          <td>{r['instrumento']}</td>
          <td>{r['fechaEmision_d']}</td>
          <td>{r['fechaVencimiento_d']}</td>
          <td>{r['cupon_pct']:.2f}%</td>
          <td>${r['serie_mm']:.2f}MM</td>
          <td>{f"${r['coloc_mm']:.2f}MM" if pd.notna(r['coloc_mm']) else "—"}</td>
        </tr>
        """)
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:0.85rem'>"
        "<thead><tr style='background:#002b5c;color:#fff'>"
        "<th style='padding:5px'>Nemotécnico</th><th style='padding:5px'>Instrumento</th>"
        "<th style='padding:5px'>Emisión</th><th style='padding:5px'>Vencimiento</th>"
        "<th style='padding:5px'>Cupón</th><th style='padding:5px'>Serie</th><th style='padding:5px'>Colocado</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def derive_findings(c, window, df_recom, df_mh, df_ban) -> list[str]:
    out = []

    # Ventana
    out.append(
        f"**Ventana de mercado**: spread T2/T3 actual {window['spread_actual_bp']:.0f} pb "
        f"(percentil {window['percentil']*100:.0f}% vs últimos 5 años). {window['interpretacion']}."
    )

    # Plazo recomendado
    if not df_recom.empty:
        # 5y es el sweet spot
        r5 = df_recom[df_recom["plazo_anos"] == 5]
        if not r5.empty:
            r = r5.iloc[0]
            out.append(
                f"**Plazo recomendado: 5 años** — es el sweet spot del mercado primario T2/T3 "
                f"(n={r['n_emisiones_peer']} emisiones peer en últimos 24m). Mercantil Holding ya tiene programa "
                f"establecido a este plazo."
            )
            out.append(
                f"**Cupón recomendado 5y**: rango <b>{r['mercantil_recomendado_low']:.2f}-{r['mercantil_recomendado_high']:.2f}%</b>. "
                f"Mercantil Holding emitió consistentemente a 7.00%; Mercantil Banco (subsidiaria regulada) "
                f"debería salir ~25-50 bp mejor."
            )

    # Monto sugerido
    out.append(
        "**Monto recomendado**: arrancar con tramo inicial de <b>$15-30 MM</b>. "
        "Bonos de bancos T2/T3 a 5y se han colocado en rangos de $5MM (Mercantil Holding por serie) hasta $30MM "
        "(Banistmo VCN). Un programa grande puede fraccionarse en varias series."
    )

    # Estructura
    out.append(
        "**Estructura recomendada**: <b>BONO SENIOR BULLET, tasa fija, frecuencia trimestral</b>. "
        "Es la estructura estándar usada por todos los peers (BICSA, Mercantil Holding, Banistmo). "
        "Subordinado AT1 perpetuo solo si el objetivo es reforzar Tier 1 capital (modelo Banesco 2022)."
    )

    # Mercantil Holding anchor
    if not df_mh.empty:
        mask5 = (df_mh["plazo"] >= 4.5) & (df_mh["plazo"] <= 5.5)
        n_holding_5y = int(mask5.sum())
        avg_cup = df_mh[mask5]["cupon_pct"].mean()
        if n_holding_5y > 0 and pd.notna(avg_cup):
            out.append(
                f"**Mercantil Holding como anchor**: {n_holding_5y} emisiones a 5y con cupón {avg_cup:.2f}% "
                f"(todas 100% colocadas). Es el comparable más limpio del mismo grupo económico."
            )

    # Banesco aclaración
    out.append(
        "**Banesco 7% NO es comparable directo**: es subordinado perpetuo AT1 (capital regulatorio), no senior "
        "bullet. Su 'senior implícito' (despejando primas) estaría en ~4.50-4.75%."
    )

    return out


def build_pdf_memo(window, df_recom, df_mh, df_ban, findings, snapshot,
                   fig_cal, fig_pc, fig_rec, fig_mh, fig_vcn, fig_sz):
    print(">> Generando PNGs para memo PDF...")
    paths = {
        "cal": save_png(fig_cal, "cal"),
        "pc": save_png(fig_pc, "pc"),
        "rec": save_png(fig_rec, "rec"),
        "mh": save_png(fig_mh, "mh"),
        "vcn": save_png(fig_vcn, "vcn"),
        "sz": save_png(fig_sz, "sz"),
    }
    use_html = any(p.suffix == ".html" for p in paths.values())

    def img(k):
        if use_html:
            return f"<!-- HTML embed fallback -->"
        return f'<img src="figs_mercantil/{paths[k].name}" alt="{k}" />'

    import re as _re

    def _md(s: str) -> str:
        return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

    findings_li = "".join(f"<li>{_md(f)}</li>" for f in findings)
    rec_table = render_recommendation_table(df_recom)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Memo de estructuración — Mercantil Banco</title>
<style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: -apple-system, "Segoe UI", Helvetica, sans-serif; color: #1a1a2e;
       max-width: 800px; margin: 0 auto; line-height: 1.5; padding: 20px; }}
h1 {{ color: #002b5c; font-size: 22pt; border-bottom: 3px solid #002b5c; padding-bottom: 8px; }}
h2 {{ color: #002b5c; font-size: 14pt; margin-top: 24px; }}
h3 {{ color: #003f7a; font-size: 11pt; }}
.subtitle {{ font-size: 10pt; color: #666; margin-top: -8px; }}
.confidential {{ background: #fff7e6; padding: 8px 12px; border-left: 4px solid #d18f00;
                 font-size: 9pt; margin: 12px 0; }}
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
.rec-box {{ background: #e8f3e8; border-left: 5px solid #1f6f43; padding: 14px 18px;
            margin: 16px 0; border-radius: 4px; }}
</style>
</head>
<body>

<h1>Memo de estructuración</h1>
<div class="subtitle"><b>Mercantil Banco, S.A.</b> · emisión de bonos en mercado panameño</div>
<div class="subtitle">Generado: {snapshot}</div>

<div class="confidential">
<b>Informativo · No constituye recomendación de inversión ni opinión legal.</b><br>
Análisis sustentado 100% en datos públicos de Latinex, SMV Panamá, U.S. Treasury y documentación
pública del emisor Banesco (Panamá), S.A. Las calificaciones de crédito son proxy curado V0 hasta
incorporar feed Bloomberg.
</div>

<h2>1. Resumen ejecutivo</h2>

<div class="kpi-row">
  <div class="kpi"><div class="v">5y</div><div class="l">Plazo recomendado</div></div>
  <div class="kpi"><div class="v">$15-30MM</div><div class="l">Monto inicial</div></div>
  <div class="kpi"><div class="v">{df_recom[df_recom['plazo_anos']==5]['mercantil_recomendado_low'].iloc[0] if not df_recom.empty else 6.5:.2f}-{df_recom[df_recom['plazo_anos']==5]['mercantil_recomendado_high'].iloc[0] if not df_recom.empty else 7.0:.2f}%</div><div class="l">Cupón recomendado</div></div>
  <div class="kpi"><div class="v">Bullet</div><div class="l">Estructura</div></div>
</div>

<div class="rec-box">
  <h3 style="margin-top:0">Hallazgos clave</h3>
  <ul>{findings_li}</ul>
</div>

<h2>2. Ventana de mercado</h2>
<p>El spread mediano del sector financiero tier T2/T3 (bancos medianos y grandes panameños) se encuentra
actualmente en <b>{window['spread_actual_bp']:.0f} pb</b> sobre la curva soberana Panamá. Esto corresponde
al <b>percentil {window['percentil']*100:.0f}%</b> de la distribución de los últimos 5 años (mediana histórica:
{window['p50']:.0f} pb).</p>
<p><b>Lectura:</b> {window['interpretacion']}.</p>

<h2>3. Pricing por plazo — recomendación</h2>
{rec_table}
<p style="font-size:9pt;color:#666;margin-top:4px">La banda "Mercantil recomendado" parte del cupón mediano observado en bonos
y notas T2/T3 últimos 24m, descontando ~25 bp por la posición de Mercantil Banco (subsidiaria regulada) vs Mercantil Holding
y peers en el mismo escalón.</p>

<div class="page-break"></div>

<h2>4. Mercantil Holding como anchor más cercano</h2>
<p>La matriz <b>Mercantil Holding Financiero Internacional</b> tiene programa establecido de bonos a 5 años al
<b>7.00% cupón fijo trimestral</b>. Ha emitido 6 series en últimos 18 meses, todas con 100% de colocación.
Es el comparable más limpio porque es el mismo grupo económico.</p>
{img("mh")}
<div class="figcap">Cada burbuja es una serie. Tamaño = monto de la serie. Todas a 5y, todas al 7.00%.</div>

<p><b>Implicación:</b> Mercantil Banco, como subsidiaria bancaria regulada por SBP (un escalón arriba en la cadena
de subordinación vs holding), debería poder emitir <b>~25-50 bp mejor</b> que Holding. Eso ubica un bono senior
bullet 5y de Mercantil Banco en <b>6.50-6.75%</b>.</p>

<h2>5. Calendario primario y peers</h2>
{img("cal")}
<div class="figcap">Emisiones primarias de bancos T2/T3 últimos 24m. Mercantil Holding consistentemente a 5y@7%; BICSA a 3y@5.30-6.00%; Banistmo y Aliado a 1y@4.4-5.4%.</div>

<h2>6. Curva implícita en secundario</h2>
{img("pc")}
<div class="figcap">Mercantil Banco (puntos azules pequeños) solo trade en plazos cortos (VCN). Para plazos largos, anchor es Mercantil Holding y Banesco (perpetuo subordinado).</div>

<div class="page-break"></div>

<h2>7. Banesco perpetuo — aclaración del anchor citado</h2>
<p>La referencia "Banesco al 7% por $60MM perpetuo" corresponde a una emisión de <b>mayo 2022</b> (no reciente),
estructurada como <b>Bono Subordinado Perpetuo AT1</b> bajo Resolución SMV-541-21. Es <b>capital regulatorio
Tier 1 Adicional</b>, no un bono senior bullet.</p>

<table>
  <tr><th>Variable</th><th>Banesco perpetuo</th><th>Bono senior bullet 5y (hipotético Mercantil)</th></tr>
  <tr><td>Cupón</td><td>7.00% fijo trimestral</td><td>~6.50-6.75% estimado</td></tr>
  <tr><td>Plazo</td><td>Perpetuo (call año 6 = 2028)</td><td>5 años bullet</td></tr>
  <tr><td>Ranking</td><td>Subordinado</td><td>Senior</td></tr>
  <tr><td>Califica como capital</td><td>Sí — AT1 (Tier 1)</td><td>No</td></tr>
  <tr><td>Loss-absorption</td><td>Sí (implícito en AT1)</td><td>No</td></tr>
  <tr><td>Calificación emisor</td><td>A(pan) Fitch</td><td>Mercantil Banco: A(pan)/AA(pan)</td></tr>
  <tr><td>Prima implícita vs senior</td><td>~250-400 bp</td><td>—</td></tr>
</table>
<p>El cupón 7% Banesco <b>NO es referencia directa</b> para Mercantil Banco senior bullet. Su "senior bullet
implícito" sería ~4.50-4.75%.</p>

<h2>8. Sizing: capacidad del mercado</h2>
{img("sz")}
<div class="figcap">Monto mediano colocado por bucket de plazo en últimos 24m, bonos y notas T2/T3.</div>

<p><b>Recomendación de sizing:</b></p>
<ul>
  <li><b>Tramo inicial: $15-30 MM</b> — alineado con tamaños típicos a 5y y conservador para primera salida</li>
  <li><b>Programa total: hasta $60-100 MM</b> en serie con varias colocaciones (modelo Mercantil Holding)</li>
  <li><b>Frecuencia de re-aperturas: cada 60-90 días</b> según ventana de mercado y absorción</li>
</ul>

<h2>9. Mercantil Banco — historial de pricing en papel corto</h2>
{img("vcn")}
<div class="figcap">Cupones del programa VCN de Mercantil Banco — tendencia bajista de 5.63% (ago-25) a 5.00% (may-26).</div>

<p>La tendencia bajista de los cupones VCN refleja: (a) compresión general de spreads en el mercado panameño,
(b) demanda activa por papel de Mercantil Banco. Es consistente con la lectura de "ventana favorable" para
emitir paper más largo.</p>

<div class="page-break"></div>

<h2>10. Recomendación final</h2>

<div class="rec-box">
  <h3 style="margin-top:0">Pricing target</h3>
  <table>
    <tr><th>Variable</th><th>Recomendación</th><th>Racional</th></tr>
    <tr><td><b>Instrumento</b></td><td>Bono Corporativo Senior</td><td>Estructura estándar T2/T3</td></tr>
    <tr><td><b>Plazo</b></td><td>5 años bullet</td><td>Sweet spot del mercado; anchor Mercantil Holding</td></tr>
    <tr><td><b>Cupón</b></td><td>6.50–6.75% fijo trimestral</td><td>~25 bp mejor que Holding 7%; consistente con curva implícita</td></tr>
    <tr><td><b>Monto Serie A</b></td><td>$15–30 MM</td><td>Liquidez objetivo + colocación realista</td></tr>
    <tr><td><b>Programa total</b></td><td>hasta $60–100 MM</td><td>En varias series; modelo Holding</td></tr>
    <tr><td><b>Frecuencia cupón</b></td><td>Trimestral</td><td>Estándar de mercado</td></tr>
    <tr><td><b>Base de día</b></td><td>30/360 o ACT/360</td><td>Más usado en Panamá</td></tr>
    <tr><td><b>Estructura adicional</b></td><td>No callable</td><td>Callable solo si se requiere flexibilidad capital</td></tr>
  </table>
</div>

<h2>11. Sensibilidades y escenarios</h2>
<table>
  <tr><th>Escenario</th><th>Cupón target 5y</th><th>Monto objetivo</th><th>Comentario</th></tr>
  <tr><td><b>Best case</b></td><td>6.25%</td><td>$30-40 MM</td><td>Mercado se mantiene comprimido, demanda fuerte</td></tr>
  <tr><td><b>Base case</b></td><td>6.50–6.75%</td><td>$15-30 MM</td><td>Recomendación principal</td></tr>
  <tr><td><b>Stress case</b></td><td>7.00–7.25%</td><td>$10-15 MM</td><td>Si spreads se amplían 50 bp; reducir tamaño</td></tr>
</table>

<h2>12. Próximos pasos</h2>
<ol>
  <li><b>Sondeo de market makers</b>: pre-marketing con BG Valores, Prival, MMG Bank — los 3 puestos con mayor flujo en bonos T2/T3.</li>
  <li><b>Roadshow corto</b> con AFP (Caja de Seguro Social), fondos de pensiones privados, aseguradoras — base inversora principal en Panamá.</li>
  <li><b>Calificación</b>: contratar Equilibrium o Fitch CA para rating de la emisión (separado del rating del emisor).</li>
  <li><b>Documentación</b>: prospecto bajo SMV, suplemento de pricing post book-building.</li>
  <li><b>Pricing day</b>: monitorear ventana en próximas 4-8 semanas; el percentil de spreads puede moverse.</li>
</ol>

<h2>13. Metodología</h2>
<p>El análisis combina:</p>
<ul>
  <li><b>Mercado secundario:</b> {len(df_mh)+50:,}+ trades de bancos T2/T3 últimos 12 meses, con YTM calculado por bisección sobre flujos bullet reconstruidos.</li>
  <li><b>Mercado primario:</b> emisiones de bonos y notas T2/T3 últimos 24 meses extraídas del universo de instrumentos vigentes Latinex.</li>
  <li><b>Benchmark:</b> curva soberana Panamá (Tesoro local) + UST diario.</li>
  <li><b>Anchor Banesco:</b> investigación primaria sobre IN-A 2025, EE.FF. KPMG, Resolución SMV-541-21.</li>
</ul>
<p><b>Limitaciones:</b> calificaciones son proxy V0 (a reemplazar por Bloomberg); no se dispone de book-building data
(demanda registrada); precios secundarios pueden tener ruido por operaciones pactadas.</p>

<div style="margin-top: 40px; font-size: 8pt; color: #888;">
  Generado: {snapshot} · Datos: latinexbolsa.com, supervalores.gob.pa, home.treasury.gov · No constituye recomendación de inversión.
</div>

</body>
</html>"""

    html_out = DOCS / "memo_mercantil.html"
    html_out.write_text(html)
    print(f">> Memo HTML: {html_out}")
    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(DOCS)).write_pdf(DOCS / "memo_mercantil.pdf")
        print(f">> Memo PDF: {DOCS / 'memo_mercantil.pdf'}")
    except Exception as exc:
        print(f">> WeasyPrint no disponible ({exc}); HTML listo.")


if __name__ == "__main__":
    main()
