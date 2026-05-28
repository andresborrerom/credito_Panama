"""Render deck v1.0 — 9 laminas accionables segun 13b_BENCHMARK_REPORTES.md.

Aplica los 5 patrones obligatorios:
1. Una idea por lamina.
2. Sweet spot explicito con nivel/target.
3. Definicion operativa antes de la opinion.
4. Trigger calendar al inicio (lamina 1-2), no al final.
5. Conviction tags Alta/Media/Baja en cada vista y mensaje del TL;DR.

Voz: primera persona del grupo ("creemos que...", "vigilamos..."). Camilo + Andres
son los duenios editoriales.

Uso:
    python -m src.tasas_mercantil.reportes.render_deck_v10 \
        --as-of 2026-05-29 --corte 2026-05
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ..data.store import load_master_store, MasterStore
from ..data.queries import (
    get_curve_ust,
    get_fed_funds_snapshot,
)
from ..modelo.pieces.implied_path import compute_implied_path
from .narrativa import (
    Narrativa,
    TLDRMessage,
    TacticalView,
    CalendarItem,
    narrativa_2026_05,
)


# ============================================================================
# Diseno visual
# ============================================================================
COLORS = {
    "primary":   "#0E2A47",  # azul Mercantil SFI (placeholder hasta paleta oficial)
    "secondary": "#5A8FB0",
    "accent":    "#D9A24D",
    "muted":     "#999999",
    "danger":    "#C2455D",
    "success":   "#3E8B6A",
    "bg":        "#FAFAFA",
    "text":      "#222",
    "subtle":    "#666",
}

CONVICTION_STYLE = {
    "Alta":  {"bg": "#E8F4EC", "fg": "#1F5E3E", "label": "ALTA"},
    "Media": {"bg": "#FBF1DE", "fg": "#8A5A1A", "label": "MEDIA"},
    "Baja":  {"bg": "#EEEEEE", "fg": "#555555", "label": "BAJA"},
}

DIRECTION_COLOR = {
    "Overweight":  COLORS["success"],
    "Underweight": COLORS["danger"],
    "Long":        COLORS["success"],
    "Short":       COLORS["danger"],
    "Neutral":     COLORS["muted"],
}

FONT = {"family": "Helvetica, Arial, sans-serif", "size": 12, "color": COLORS["text"]}
LAYOUT_DEFAULTS = {
    "font": FONT,
    "plot_bgcolor": "white",
    "paper_bgcolor": "white",
    "margin": {"l": 60, "r": 30, "t": 80, "b": 50},
}


def _slide_title(text: str, subtitle: str = "") -> dict:
    """Titulo estandar para todas las laminas."""
    full = f"<b>{text}</b>"
    if subtitle:
        full += f"<br><span style='font-size:13px;color:{COLORS['subtle']};font-weight:normal'>{subtitle}</span>"
    return dict(text=full, font=dict(size=20, color=COLORS["primary"]), x=0.02, xanchor="left")


def _slide_footer(corte: str) -> str:
    return (
        f"Reporte mensual de tasas · Grupo Mercantil · cierre {corte}<br>"
        f"<i>Documento interno de gestión. No constituye recomendación a clientes.</i>"
    )


# ============================================================================
# LAMINA 1 — TL;DR (3 mensajes + conviction tags)
# ============================================================================
def lamina_1_tldr(narrativa: Narrativa) -> go.Figure:
    """TL;DR con los 3 mensajes del mes + conviction tags."""
    n_msgs = len(narrativa.tldr_messages)
    fig = make_subplots(
        rows=n_msgs, cols=1,
        specs=[[{"type": "table"}]] * n_msgs,
        vertical_spacing=0.04,
    )

    for i, msg in enumerate(narrativa.tldr_messages, start=1):
        style = CONVICTION_STYLE[msg.conviction]
        header_values = [
            f"<b>Mensaje {i}</b>",
            f"<b style='color:{style['fg']}'>Convicción {style['label']}</b>",
            f"<b>{msg.relevant_unit}</b>",
        ]
        cell_values = [
            [f"<b>{msg.headline}</b>"],
            [f"<i>Trigger:</i> {msg.trigger}"],
            [""],
        ]

        fig.add_trace(
            go.Table(
                columnwidth=[55, 25, 20],
                header=dict(
                    values=header_values,
                    fill_color=[COLORS["primary"], style["bg"], COLORS["bg"]],
                    font=dict(color=["white", style["fg"], COLORS["text"]], size=12),
                    align="left",
                    height=32,
                ),
                cells=dict(
                    values=cell_values,
                    fill_color="white",
                    align="left",
                    height=44,
                    font=dict(size=12, color=COLORS["text"]),
                ),
            ),
            row=i, col=1,
        )

    fig.update_layout(
        title=_slide_title(
            "TL;DR — 3 mensajes del mes",
            f"Corte {narrativa.report_month} · {narrativa.autor_principal}",
        ),
        height=180 * n_msgs + 100,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# LAMINA 2 — Tactical View Table
# ============================================================================
def lamina_2_tactical_view_table(narrativa: Narrativa) -> go.Figure:
    """Tabla con las vistas tacticas — el corazon accionable del deck."""
    rows = []
    for v in narrativa.tactical_views:
        c_style = CONVICTION_STYLE[v.conviction]
        dir_color = DIRECTION_COLOR.get(v.direccion.split()[0], COLORS["muted"])
        rows.append([
            f"<b>{v.activo}</b>",
            f"<span style='color:{dir_color};font-weight:bold'>{v.direccion}</span>",
            v.horizonte,
            f"<span style='color:{c_style['fg']};font-weight:bold'>{c_style['label']}</span>",
            v.what,
            v.if_right,
            v.if_wrong,
            v.trigger,
        ])

    fig = go.Figure(
        data=[go.Table(
            columnwidth=[12, 11, 7, 8, 18, 16, 16, 12],
            header=dict(
                values=[
                    "<b>Activo</b>", "<b>Dirección</b>", "<b>Horiz.</b>", "<b>Convicción</b>",
                    "<b>WHAT</b>", "<b>WHAT IF RIGHT</b>", "<b>WHAT IF WRONG</b>", "<b>TRIGGER</b>",
                ],
                fill_color=COLORS["primary"],
                font=dict(color="white", size=11),
                align="left",
                height=34,
            ),
            cells=dict(
                values=list(zip(*rows)),
                fill_color=[["#FFFFFF" if i % 2 else COLORS["bg"] for i in range(len(rows))]],
                align="left",
                height=70,
                font=dict(size=10, color=COLORS["text"]),
            ),
        )],
    )
    fig.update_layout(
        title=_slide_title(
            "Tactical Views — qué estamos haciendo y por qué",
            "Cada vista lleva los 4 Ws: afirmación · upside · costo del error · disparador",
        ),
        height=120 + 90 * len(rows),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# LAMINA 3 — Fed + curva UST (fusion de antiguas 3+4+5)
# ============================================================================
def lamina_3_fed_y_curva(store: MasterStore, as_of: date) -> go.Figure:
    """Curva UST 3 cortes + implied path Fed Funds."""
    ye_anterior = date(as_of.year - 1, 12, 31)
    mes_anterior_ts = as_of - pd.DateOffset(months=1)
    mes_anterior = mes_anterior_ts.date() if isinstance(mes_anterior_ts, pd.Timestamp) else mes_anterior_ts

    cortes = [
        (ye_anterior,   f"31-dic-{as_of.year - 1}", COLORS["muted"]),
        (mes_anterior,  f"Cierre {mes_anterior.strftime('%b %Y')}", COLORS["secondary"]),
        (as_of,         f"Cierre {as_of.strftime('%b %Y')}", COLORS["primary"]),
    ]
    tenors_order = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.55, 0.45],
        subplot_titles=("Curva UST · 3 cortes", "Implied path Fed Funds (SR3 strip)"),
        horizontal_spacing=0.08,
    )

    for corte_date, label, color in cortes:
        df = get_curve_ust(store, corte_date).dropna(subset=["value"]).copy()
        df["order"] = df["tenor"].map({t: i for i, t in enumerate(tenors_order)})
        df = df.sort_values("order")
        fig.add_trace(
            go.Scatter(
                x=df["tenor"], y=df["value"],
                mode="lines+markers", name=label,
                line=dict(color=color, width=2.2),
                marker=dict(size=7),
            ),
            row=1, col=1,
        )

    # Implied path
    pred = compute_implied_path(store, as_of)
    horizontes = [0, 1, 3, 6, 12, 24]
    valores = [
        pred.fed_funds_now,
        pred.forecast_1m, pred.forecast_3m, pred.forecast_6m,
        pred.forecast_12m, pred.forecast_24m,
    ]
    fig.add_trace(
        go.Scatter(
            x=horizontes, y=valores, mode="lines+markers",
            name=f"Implied Path ({pred.family})",
            line=dict(color=COLORS["accent"], width=2.5),
            marker=dict(size=10),
            showlegend=True,
        ),
        row=1, col=2,
    )
    fig.add_hline(
        y=pred.fed_funds_now, line=dict(color=COLORS["muted"], dash="dash", width=1),
        annotation_text=f"Fed Funds actual: {pred.fed_funds_now:.2f}%",
        annotation_position="bottom right",
        row=1, col=2,
    )

    fig.update_xaxes(title="", showgrid=False, row=1, col=1,
                     categoryorder="array", categoryarray=tenors_order)
    fig.update_yaxes(title="Yield (%)", gridcolor="#EEEEEE", ticksuffix="%", row=1, col=1)
    fig.update_xaxes(title="Meses adelante", gridcolor="#EEEEEE",
                     tickvals=[0, 3, 6, 12, 24], row=1, col=2)
    fig.update_yaxes(title="Tasa (%)", gridcolor="#EEEEEE", ticksuffix="%", row=1, col=2)

    fig.update_layout(
        title=_slide_title(
            "Fed Funds + curva UST",
            "Sweet spot 5-10Y: target yield 4.20-4.50%. Mercado descuenta path estable a +24M.",
        ),
        height=620,
        legend=dict(orientation="h", y=-0.12),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# LAMINA SKELETON — para Spreads, Global, Panama, Venezuela, Mercantil
# Skeletons dimensionados con titulo + bullet de "pendiente" para que el
# usuario pueda iterar la narrativa en sesion.
# ============================================================================
def _lamina_skeleton(titulo: str, subtitulo: str, pendiente_text: str, height: int = 520) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=(
            f"<span style='font-size:18px;color:{COLORS['muted']}'>"
            f"<b>Pendiente narrativa + data</b></span><br><br>"
            f"<span style='color:{COLORS['subtle']}'>{pendiente_text}</span>"
        ),
        showarrow=False,
        x=0.5, y=0.5,
        xref="paper", yref="paper",
        font=dict(size=14),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        title=_slide_title(titulo, subtitulo),
        height=height,
        **LAYOUT_DEFAULTS,
    )
    return fig


def lamina_4_spreads_corporativos() -> go.Figure:
    return _lamina_skeleton(
        "Spreads corporativos — IG, HY, EMBI",
        "Definimos shock al spread como ampliación >50 bps en 30 días.",
        "Tabla pivot región × rating × plazo con percentiles 5Y + delta mes. "
        "Llega cuando se confirme acceso a subíndices ICE BofA y CEMBI vía Bloomberg "
        "(plantilla mensual lo incluye, pero hace falta confirmar tickers C0Ax/H0Ax).",
    )


def lamina_5_global() -> go.Figure:
    return _lamina_skeleton(
        "Global — BCE/BoE + USD index",
        "Vigilamos divergencia política Fed-BCE y su impacto en DXY.",
        "Diferencial de tasa política Fed vs BCE/BoE/BoJ + DXY 12M. Pendiente bajar curvas "
        "10Y soberanas G7 históricas vía plantilla Bloomberg mensual y FRED H.10 para FX.",
    )


def lamina_6_panama() -> go.Figure:
    return _lamina_skeleton(
        "Panamá — soberana + corporativos locales",
        "Spread PAN 10Y vs UST hoy ~130 bps · mediana 5Y 240 bps.",
        "Conexión con dataset credito_Panama existente (curves_monthly.parquet, "
        "trades.parquet). Llega en la siguiente iteración integrando los datasets.",
    )


def lamina_7_venezuela() -> go.Figure:
    return _lamina_skeleton(
        "Venezuela — BCV vs paralelo + bonos",
        "Brecha cambiaria y status PDVSA/VENZ defaulteados.",
        "Scraper BCV oficial + promedio de 3 fuentes públicas para paralelo "
        "(Monitor Dólar / EnParaleloVzla / DolarToday). Implementación en M-3.",
    )


def lamina_8_impacto_mercantil() -> go.Figure:
    return _lamina_skeleton(
        "Impacto Grupo Mercantil por unidad",
        "Cómo le pega el mensaje del mes a cada unidad del grupo.",
        "Mapa con 5 columnas: Banco Mercantil VE · Mercantil Banco PA · Mercantil Seguros · "
        "Wealth Management · Tesorería / posición propia. Cada celda: WHAT IF RIGHT + "
        "WHAT IF WRONG por unidad. Insumo: 06_GRUPO_MERCANTIL.md.",
        height=560,
    )


# ============================================================================
# LAMINA 9 — Calendario + qué nos haría cambiar de opinión
# ============================================================================
def lamina_9_calendario(narrativa: Narrativa) -> go.Figure:
    """Tabla del calendario del próximo mes con importance tags."""
    rows = []
    for item in narrativa.calendar:
        style = CONVICTION_STYLE[item.importancia]
        rows.append([
            f"<b>{item.fecha}</b>",
            item.evento,
            item.relevante_para,
            f"<span style='color:{style['fg']};font-weight:bold'>{style['label']}</span>",
        ])

    fig = go.Figure(
        data=[go.Table(
            columnwidth=[15, 25, 45, 15],
            header=dict(
                values=[
                    "<b>Fecha</b>", "<b>Evento</b>",
                    "<b>Relevante para</b>", "<b>Importancia</b>",
                ],
                fill_color=COLORS["primary"],
                font=dict(color="white", size=12),
                align="left",
                height=34,
            ),
            cells=dict(
                values=list(zip(*rows)),
                fill_color=[["#FFFFFF" if i % 2 else COLORS["bg"] for i in range(len(rows))]],
                align="left",
                height=42,
                font=dict(size=11, color=COLORS["text"]),
            ),
        )],
    )
    fig.update_layout(
        title=_slide_title(
            "Calendario próximo mes · qué nos haría cambiar de opinión",
            "Cada vista de la lámina 2 tiene un trigger. Aquí están las fechas.",
        ),
        height=120 + 60 * len(rows),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# Runner
# ============================================================================
LAMINAS_ORDEN = [
    ("01_tldr",                "lamina_1_tldr"),
    ("02_tactical_views",      "lamina_2_tactical_view_table"),
    ("03_fed_curva_ust",       "lamina_3_fed_y_curva"),
    ("04_spreads_corp",        "lamina_4_spreads_corporativos"),
    ("05_global",              "lamina_5_global"),
    ("06_panama",              "lamina_6_panama"),
    ("07_venezuela",           "lamina_7_venezuela"),
    ("08_impacto_mercantil",   "lamina_8_impacto_mercantil"),
    ("09_calendario",          "lamina_9_calendario"),
]


def render_all(store: MasterStore, as_of: date, narrativa: Narrativa, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figs_dir = out_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    figs = {
        "01_tldr":              lamina_1_tldr(narrativa),
        "02_tactical_views":    lamina_2_tactical_view_table(narrativa),
        "03_fed_curva_ust":     lamina_3_fed_y_curva(store, as_of),
        "04_spreads_corp":      lamina_4_spreads_corporativos(),
        "05_global":            lamina_5_global(),
        "06_panama":            lamina_6_panama(),
        "07_venezuela":         lamina_7_venezuela(),
        "08_impacto_mercantil": lamina_8_impacto_mercantil(),
        "09_calendario":        lamina_9_calendario(narrativa),
    }

    paths = {}
    for name, fig in figs.items():
        html_path = out_dir / f"{name}.html"
        png_path = figs_dir / f"{name}.png"
        pio.write_html(fig, html_path, include_plotlyjs="cdn", full_html=True)
        try:
            pio.write_image(fig, png_path, width=1600, height=900)
        except Exception as e:
            print(f"  [warn] PNG {name} fallo: {e}")
        paths[name] = {"html": html_path, "png": png_path}

    # Index unificado
    index_html = out_dir / "index.html"
    body = "<br>".join([
        f'<h2>Lámina {name.split("_")[0]} — {name.split("_", 1)[1].replace("_", " ").title()}</h2>'
        f'<iframe src="{name}.html" width="100%" height="780" frameborder="0"></iframe>'
        for name in figs
    ])
    index_html.write_text(
        f"<!DOCTYPE html><html lang='es'><head>"
        f'<meta charset="utf-8"><meta name="robots" content="noindex">'
        f"<title>Tasas Mercantil — {narrativa.report_month}</title>"
        f'<style>body{{font-family:Helvetica,Arial,sans-serif;max-width:1600px;margin:24px auto;color:#222;padding:0 24px}}'
        f'h1{{color:{COLORS["primary"]}}}h2{{color:{COLORS["primary"]};border-bottom:1px solid #ddd;padding-bottom:6px;margin-top:32px}}'
        f'.disclaimer{{color:#888;font-size:12px;border-top:1px solid #eee;padding-top:12px;margin-top:48px}}</style>'
        f'</head><body>'
        f'<h1>Tasas Mercantil · {narrativa.report_month}</h1>'
        f'<p><i>Render v1.0 · {narrativa.autor_principal}</i></p>'
        f"{body}"
        f"<div class='disclaimer'>Documento interno de gestión. No constituye recomendación a clientes.</div>"
        f"</body></html>"
    )
    paths["index"] = index_html
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    ap.add_argument("--corte", required=True, help="YYYY-MM")
    ap.add_argument(
        "--out-dir", type=Path, default=None,
        help="Default: ProyectoTasasMercantil/cortes/<corte>/output_v10/",
    )
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of)
    out_dir = args.out_dir or Path("ProyectoTasasMercantil/cortes") / args.corte / "output_v10"

    print(f"Cargando store...")
    store = load_master_store()
    print(f"  {len(store.features)} features, {len(store.df):,} filas")

    # Narrativa: hardcoded para mayo 2026; en cortes futuros se lee de YAML
    if args.corte == "2026-05":
        narrativa = narrativa_2026_05()
    else:
        raise ValueError(f"Narrativa no hardcoded para corte {args.corte}")

    print(f"Renderizando deck v1.0 para as_of={as_of}, corte={args.corte}")
    paths = render_all(store, as_of, narrativa, out_dir)

    print(f"\n[OK] Output en {out_dir}")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
