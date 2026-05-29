"""Render deck v1.0.2 — fuentes grandes + editorial estructurado por subplot.

Cambios sobre v1.0.1:
- Editorial al pie es un SUBPLOT, no annotation flotante. Por construccion
  no se superpone con la visual principal.
- Editorial estructurado en 4 lecturas: Que dice / Por que / Para que /
  Como se lee.
- Fuentes mas grandes (titulo 30, header tabla 17, cell 16, editorial 16).
- Cada lamina define su Editorial explicitamente.

Voz: primera persona del grupo. Disclaimer corto en index.
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
from ..data.queries_panama import (
    get_panama_snapshot,
    get_panama_sov_curves_3cortes,
)
from ..data.queries_global import (
    get_global_snapshot,
    get_dxy_snapshot,
    get_policy_history,
)
from ..data.queries_venezuela import snapshot_2026_05_placeholder
from ..modelo.pieces.implied_path import compute_implied_path
from ..modelo.aggregate import compute_mercantil_aggregate
from .narrativa import (
    Editorial,
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
    "primary":   "#0E2A47",
    "secondary": "#5A8FB0",
    "accent":    "#D9A24D",
    "muted":     "#999999",
    "danger":    "#C2455D",
    "success":   "#3E8B6A",
    "bg":        "#FAFAFA",
    "editorial": "#EDF1F6",
    "text":      "#222",
    "subtle":    "#555",
}

CONVICTION_STYLE = {
    "Alta":  {"bg": "#D6E9DD", "fg": "#1F5E3E", "label": "ALTA"},
    "Media": {"bg": "#FBE8C6", "fg": "#8A5A1A", "label": "MEDIA"},
    "Baja":  {"bg": "#E5E5E5", "fg": "#555555", "label": "BAJA"},
}

DIRECTION_COLOR = {
    "Overweight":  COLORS["success"],
    "Underweight": COLORS["danger"],
    "Long":        COLORS["success"],
    "Short":       COLORS["danger"],
    "Neutral":     COLORS["muted"],
}

# Fuentes escaladas para deck 1920x1080 leible en presentacion
TITLE_SIZE = 30
SUBTITLE_SIZE = 18
SECTION_SIZE = 22       # anotaciones tipo "Curva UST · 3 cortes"
TABLE_HEADER_SIZE = 17
TABLE_CELL_SIZE = 16
EDITORIAL_HEADER_SIZE = 17
EDITORIAL_CELL_SIZE = 16
AXIS_LABEL_SIZE = 16
TICK_SIZE = 15

FONT = {"family": "Helvetica, Arial, sans-serif", "size": 16, "color": COLORS["text"]}
LAYOUT_DEFAULTS = {
    "font": FONT,
    "plot_bgcolor": "white",
    "paper_bgcolor": "white",
    "margin": {"l": 80, "r": 50, "t": 130, "b": 60},
}


def _slide_title(text: str, subtitle: str = "") -> dict:
    full = f"<b>{text}</b>"
    if subtitle:
        full += (
            f"<br><span style='font-size:{SUBTITLE_SIZE}px;"
            f"color:{COLORS['subtle']};font-weight:normal'>{subtitle}</span>"
        )
    return dict(
        text=full,
        font=dict(size=TITLE_SIZE, color=COLORS["primary"]),
        x=0.02, xanchor="left", y=0.97, yanchor="top",
    )


def _editorial_table(ed: Editorial) -> go.Table:
    """Construye la tabla editorial al pie. 3 o 4 columnas segun como_se_lee."""
    headers = ["Qué dice", "Por qué", "Para qué"]
    values = [[ed.que_dice], [ed.por_que], [ed.para_que]]
    if ed.como_se_lee:
        headers.append("Cómo se lee")
        values.append([ed.como_se_lee])

    return go.Table(
        columnwidth=[1] * len(headers),
        header=dict(
            values=headers,
            fill_color=COLORS["primary"],
            font=dict(color="white", size=EDITORIAL_HEADER_SIZE, family=FONT["family"]),
            align="left",
            height=42,
        ),
        cells=dict(
            values=values,
            fill_color=COLORS["editorial"],
            font=dict(size=EDITORIAL_CELL_SIZE, color=COLORS["text"], family=FONT["family"]),
            align="left",
            height=180,  # alto generoso para texto multilinea
        ),
    )


# ============================================================================
# LAMINA 1 — TL;DR
# ============================================================================
def lamina_1_tldr(narrativa: Narrativa) -> go.Figure:
    n_msgs = len(narrativa.tldr_messages)
    fig = make_subplots(
        rows=n_msgs + 1, cols=1,
        row_heights=[0.27] * n_msgs + [0.19],  # 3 mensajes + editorial
        specs=[[{"type": "table"}]] * (n_msgs + 1),
        vertical_spacing=0.04,
    )

    for i, msg in enumerate(narrativa.tldr_messages, start=1):
        style = CONVICTION_STYLE[msg.conviction]
        fig.add_trace(
            go.Table(
                columnwidth=[55, 22, 23],
                header=dict(
                    values=[f"Mensaje {i}", f"Convicción {style['label']}", msg.relevant_unit],
                    fill_color=[COLORS["primary"], style["bg"], COLORS["bg"]],
                    font=dict(
                        color=["white", style["fg"], COLORS["text"]],
                        size=TABLE_HEADER_SIZE,
                        family=FONT["family"],
                    ),
                    align="left",
                    height=46,
                ),
                cells=dict(
                    values=[[msg.headline], [f"Trigger: {msg.trigger}"], [""]],
                    fill_color="white",
                    align="left",
                    height=80,
                    font=dict(size=TABLE_CELL_SIZE + 1, color=COLORS["text"], family=FONT["family"]),
                ),
            ),
            row=i, col=1,
        )

    ed = Editorial(
        que_dice="Tres ideas que mueven el reporte de este mes; cada una con su nivel de convicción y el evento concreto que la confirma o la rompe.",
        por_que="Síntesis editorial de Camilo + Andrés, validada contra los datos de mercado del cierre y el path implícito del modelo Mercantil.",
        para_que="Si solo se lee una página del deck, esta es. Define el marco de discusión para el comité y orienta los movimientos del mes en cada unidad relevante.",
    )
    fig.add_trace(_editorial_table(ed), row=n_msgs + 1, col=1)

    fig.update_layout(
        title=_slide_title(
            "TL;DR — 3 mensajes del mes",
            f"Corte {narrativa.report_month} · {narrativa.autor_principal}",
        ),
        height=1080,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# LAMINA 2 — Tactical View Table
# ============================================================================
def lamina_2_tactical_view_table(narrativa: Narrativa) -> go.Figure:
    views = narrativa.tactical_views

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        specs=[[{"type": "table"}], [{"type": "table"}]],
        vertical_spacing=0.06,
    )

    # Tabla principal — texto plano + colores por columna
    col_activo     = [v.activo for v in views]
    col_direccion  = [v.direccion for v in views]
    col_horizonte  = [v.horizonte for v in views]
    col_conviction = [CONVICTION_STYLE[v.conviction]["label"] for v in views]
    col_what       = [v.what for v in views]
    col_if_right   = [v.if_right for v in views]
    col_if_wrong   = [v.if_wrong for v in views]
    col_trigger    = [v.trigger for v in views]

    text = COLORS["text"]
    fc_default     = [text] * len(views)
    fc_direccion   = [DIRECTION_COLOR.get(v.direccion.split()[0], COLORS["muted"]) for v in views]
    fc_conviction  = [CONVICTION_STYLE[v.conviction]["fg"] for v in views]

    def alt_fill(n): return ["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(n)]
    fill_default   = alt_fill(len(views))
    fill_conviction = [CONVICTION_STYLE[v.conviction]["bg"] for v in views]

    fig.add_trace(go.Table(
        columnwidth=[11, 11, 6, 9, 18, 16, 16, 13],
        header=dict(
            values=["Activo", "Dirección", "Horiz.", "Convicción",
                    "WHAT", "WHAT IF RIGHT", "WHAT IF WRONG", "TRIGGER"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left",
            height=46,
        ),
        cells=dict(
            values=[col_activo, col_direccion, col_horizonte, col_conviction,
                    col_what, col_if_right, col_if_wrong, col_trigger],
            fill_color=[fill_default, fill_default, fill_default, fill_conviction,
                        fill_default, fill_default, fill_default, fill_default],
            font=dict(
                color=[fc_default, fc_direccion, fc_default, fc_conviction,
                       fc_default, fc_default, fc_default, fc_default],
                size=TABLE_CELL_SIZE,
                family=FONT["family"],
            ),
            align="left",
            height=125,
        ),
    ), row=1, col=1)

    ed = Editorial(
        que_dice="Cuatro vistas tácticas vigentes: UST 5-10Y overweight (alta), TIPS 10Y neutral (media), SOFR forwards short (baja), spread Panamá en revisión.",
        por_que="Cada vista nace de un dato del cierre + el contraste contra el path implícito. La convicción la marca el balance entre upside esperado y costo de equivocarse.",
        para_que="Es el mapa de posiciones que defendemos esta semana. La columna TRIGGER es el chequeo de calibración del próximo mes: si el dato sale del rango, revisamos.",
        como_se_lee="Cada fila es una vista. WHAT es la afirmación; WHAT IF RIGHT el upside; WHAT IF WRONG el costo del error mitigado; TRIGGER el dato que la confirma o rompe.",
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Tactical Views — las posiciones que defendemos hoy",
            "Cada vista lleva los 4 Ws: WHAT · WHAT IF RIGHT · WHAT IF WRONG · TRIGGER",
        ),
        height=1080,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# LAMINA 3 — Fed + curva UST
# ============================================================================
def lamina_3_fed_y_curva(store: MasterStore, as_of: date) -> go.Figure:
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
        rows=2, cols=2,
        row_heights=[0.65, 0.35],
        column_widths=[0.55, 0.45],
        specs=[
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "table", "colspan": 2}, None],
        ],
        horizontal_spacing=0.12,
        vertical_spacing=0.10,
    )

    # Curva UST (izq)
    for corte_date, label, color in cortes:
        df = get_curve_ust(store, corte_date).dropna(subset=["value"]).copy()
        df["order"] = df["tenor"].map({t: i for i, t in enumerate(tenors_order)})
        df = df.sort_values("order")
        fig.add_trace(
            go.Scatter(
                x=df["tenor"], y=df["value"],
                mode="lines+markers", name=label,
                line=dict(color=color, width=3),
                marker=dict(size=10),
                legendgroup="curva", legendgrouptitle_text="Curva UST",
            ),
            row=1, col=1,
        )

    # Implied (Pieza A) + Mercantil agregado (Pieza A + B) + Taylor solo (Pieza B)
    merc = compute_mercantil_aggregate(store, as_of)
    pred_a = merc.pieza_a
    pred_b = merc.pieza_b
    horizontes = [0, 1, 3, 6, 12, 24]

    vals_implied = [
        pred_a.fed_funds_now, pred_a.forecast_1m, pred_a.forecast_3m,
        pred_a.forecast_6m, pred_a.forecast_12m, pred_a.forecast_24m,
    ]
    vals_merc = [
        merc.fed_funds_now, merc.forecast_1m, merc.forecast_3m,
        merc.forecast_6m, merc.forecast_12m, merc.forecast_24m,
    ]
    vals_taylor = [
        pred_b.fed_funds_now, pred_b.forecast_1m, pred_b.forecast_3m,
        pred_b.forecast_6m, pred_b.forecast_12m, pred_b.forecast_24m,
    ]

    fig.add_trace(
        go.Scatter(
            x=horizontes, y=vals_implied, mode="lines+markers",
            name="Mercado (implied SR3)",
            line=dict(color=COLORS["accent"], width=3),
            marker=dict(size=10),
            legendgroup="path", legendgrouptitle_text="Tres lecturas Fed",
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=horizontes, y=vals_merc, mode="lines+markers",
            name=f"Modelo Mercantil v{merc.model_version}",
            line=dict(color=COLORS["primary"], width=3.5),
            marker=dict(size=12, symbol="diamond"),
            legendgroup="path",
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=horizontes, y=vals_taylor, mode="lines+markers",
            name="Taylor solo (Pieza B)",
            line=dict(color=COLORS["success"], width=2, dash="dot"),
            marker=dict(size=9),
            legendgroup="path",
        ),
        row=1, col=2,
    )
    fig.add_hline(
        y=merc.fed_funds_now, line=dict(color=COLORS["muted"], dash="dash", width=1.5),
        annotation_text=f"Fed Funds hoy: {merc.fed_funds_now:.2f}%",
        annotation_position="bottom right",
        annotation_font=dict(size=14, color=COLORS["subtle"]),
        row=1, col=2,
    )

    # Subtitulos de subplots
    fig.add_annotation(
        text="<b>Curva UST · 3 cortes</b>",
        x=0.22, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="<b>Expectativa Fed · 3 lecturas comparadas</b>",
        x=0.80, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )

    fig.update_xaxes(title=dict(text="Plazo", font=dict(size=AXIS_LABEL_SIZE)),
                     showgrid=False, row=1, col=1,
                     categoryorder="array", categoryarray=tenors_order,
                     tickfont=dict(size=TICK_SIZE))
    fig.update_yaxes(title=dict(text="Yield (%)", font=dict(size=AXIS_LABEL_SIZE)),
                     gridcolor="#EEEEEE", ticksuffix="%", row=1, col=1,
                     tickfont=dict(size=TICK_SIZE))
    fig.update_xaxes(title=dict(text="Horizonte (meses)", font=dict(size=AXIS_LABEL_SIZE)),
                     gridcolor="#EEEEEE",
                     tickvals=[0, 3, 6, 12, 18, 24], row=1, col=2,
                     tickfont=dict(size=TICK_SIZE))
    fig.update_yaxes(title=dict(text="Tasa Fed Funds esperada (%)", font=dict(size=AXIS_LABEL_SIZE)),
                     gridcolor="#EEEEEE", ticksuffix="%", row=1, col=2,
                     tickfont=dict(size=TICK_SIZE))

    # Divergencia clave: implied vs Mercantil a 24M
    div_24m_bps = int(round((vals_implied[-1] - vals_merc[-1]) * 100))

    ed = Editorial(
        que_dice=(
            f"Divergencia entre mercado y modelo Mercantil: a 24M el "
            f"implied SR3 cotiza {vals_implied[-1]:.2f}% (cut cycle terminado), "
            f"el modelo Mercantil v{merc.model_version} pronostica "
            f"{vals_merc[-1]:.2f}% (cut cycle continúa) — gap de {div_24m_bps} bps. "
            f"Curva UST con pendiente positiva +43 bps · sweet spot 5-10Y."
        ),
        por_que=(
            f"Curva: UST constant-maturity Bloomberg en 3 fechas. "
            f"Las 3 lecturas: (1) Mercado = strip SR3 puro; "
            f"(2) Mercantil v{merc.model_version} = "
            f"{merc.w_a}·Implied + {merc.w_b}·Taylor con pesos calibrados en "
            f"backtest 2022-2025; (3) Taylor solo = reaction function con "
            f"PCE core vintage ({pred_b.pi_now_pct:.2f}% YoY) y U-3 "
            f"({pred_b.u3_now_pct:.2f}%). Pasa fail-loud en todos los horizontes."
        ),
        para_que=(
            "Si el modelo Mercantil acierta, hay valor en posiciones largas "
            "de duración (UST 5-10Y, vista 1 lámina 2). Refuerza la convicción "
            "ALTA. Si nos equivocamos y el mercado tiene razón, costo acotado "
            "por el carry alto del 4.4-4.5%."
        ),
        como_se_lee=(
            "Izquierda: curva UST en 3 fotos. Derecha: tres trayectorias "
            "de tasa Fed esperada. La naranja es lo que cotiza el mercado; "
            "la azul diamante es nuestro modelo; la verde punteada es "
            "Taylor solo. Cuanto más se separan, más opinión propia tenemos."
        ),
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Fed Funds + curva UST · 3 lecturas comparadas",
            f"Mercado vs Modelo Mercantil v{merc.model_version}: gap {div_24m_bps:+d} bps a 24M",
        ),
        height=1080,
        legend=dict(orientation="h", y=0.42, font=dict(size=13)),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# Skeleton para laminas 4-8 (pendientes de data/narrativa)
# ============================================================================
def _lamina_skeleton(titulo: str, subtitulo: str, ed: Editorial) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.60, 0.40],
        specs=[[{"type": "xy"}], [{"type": "table"}]],
        vertical_spacing=0.08,
    )

    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=0.1), showlegend=False), row=1, col=1)
    fig.add_annotation(
        text="Lámina en construcción",
        showarrow=False,
        x=0.5, y=0.78, xref="paper", yref="paper",
        font=dict(size=36, color=COLORS["muted"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="contenido y data llegan en próxima iteración",
        showarrow=False,
        x=0.5, y=0.66, xref="paper", yref="paper",
        font=dict(size=18, color=COLORS["subtle"]),
        xanchor="center",
    )
    fig.update_xaxes(visible=False, row=1, col=1)
    fig.update_yaxes(visible=False, row=1, col=1)

    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(titulo, subtitulo),
        height=1080,
        showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def lamina_4_spreads_corporativos() -> go.Figure:
    ed = Editorial(
        que_dice="Va a mostrar el estado de los spreads corporativos USA IG, USA HY y EMBI LatAm vs su media histórica.",
        por_que="Tabla pivot región × rating × plazo con yield, spread vs UST y percentil 5Y construida desde los subíndices ICE BofA (C0A0–C0A4 para IG, H0A0–H0A3 para HY) y CEMBI vía Bloomberg.",
        para_que="Disparador de la vista WHAT IF WRONG en la lámina 2: si los spreads se amplían > 50 bps en 30 días, la posición long duration en UST se beneficia (flight-to-quality).",
        como_se_lee="Pendiente. Diseño previsto: heatmap con color por percentil + sparkline 12M en cada celda relevante.",
    )
    return _lamina_skeleton(
        "Spreads corporativos — IG, HY, EMBI",
        "Definimos shock al spread como ampliación >50 bps en 30 días",
        ed,
    )


def lamina_5_global(store: MasterStore, as_of: date) -> go.Figure:
    """Lámina 5 Global — version REAL con datos FRED."""
    rows = get_global_snapshot(store, as_of)
    dxy = get_dxy_snapshot(store, as_of)

    # Plot 24M de tasas de politica
    from_date = (pd.Timestamp(as_of) - pd.DateOffset(months=24)).date()
    hist = get_policy_history(
        store,
        {
            "Fed (target upper)": ["FED_FUNDS_UPPER", "fred_fed_funds_target_upper"],
            "BCE (DFR)":          ["fred_ecb_dfr"],
            "BoE (Bank Rate)":    ["fred_boe_bank_rate"],
        },
        from_date=from_date,
        to_date=as_of,
    )
    # Forward fill para suavizar weekends
    hist = hist.ffill()

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.62, 0.38],
        column_widths=[0.55, 0.45],
        specs=[
            [{"type": "xy"}, {"type": "table"}],
            [{"type": "table", "colspan": 2}, None],
        ],
        horizontal_spacing=0.08,
        vertical_spacing=0.10,
    )

    line_colors = {
        "Fed (target upper)": COLORS["primary"],
        "BCE (DFR)":          COLORS["accent"],
        "BoE (Bank Rate)":    COLORS["secondary"],
    }
    for col in hist.columns:
        fig.add_trace(
            go.Scatter(
                x=hist.index, y=hist[col],
                mode="lines",
                name=col,
                line=dict(color=line_colors[col], width=3),
            ),
            row=1, col=1,
        )

    fig.update_xaxes(
        title=dict(text="Mes", font=dict(size=AXIS_LABEL_SIZE)),
        gridcolor="#EEEEEE", row=1, col=1,
        tickfont=dict(size=TICK_SIZE),
        tickformat="%b %Y",
    )
    fig.update_yaxes(
        title=dict(text="Tasa de política (%)", font=dict(size=AXIS_LABEL_SIZE)),
        gridcolor="#EEEEEE", ticksuffix="%", row=1, col=1,
        tickfont=dict(size=TICK_SIZE),
    )

    # Subtitulos de secciones
    fig.add_annotation(
        text="<b>Política monetaria · 24 meses</b>",
        x=0.20, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="<b>Snapshot mercados</b>",
        x=0.79, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )

    # === Tabla derecha ===
    def fmt_pct(v): return f"{v:.2f}%" if v is not None and not pd.isna(v) else "—"
    def fmt_bps(v):
        if v is None: return "—"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v}"

    col_mkt   = [f"{r.country}" for r in rows]
    col_pol   = [r.policy_label for r in rows]
    col_pnow  = [fmt_pct(r.policy_now) for r in rows]
    col_pd    = [fmt_bps(r.policy_delta_bps) for r in rows]
    col_y10   = [r.yield_10y_label for r in rows]
    col_ynow  = [fmt_pct(r.yield_10y_now) for r in rows]
    col_yd    = [fmt_bps(r.yield_10y_delta_bps) for r in rows]

    text = COLORS["text"]

    # Alterna fills + Japon en gris claro (caveat)
    fills_default = [
        "#EFEFEF" if r.caveat else ("#FFFFFF" if i % 2 == 0 else COLORS["bg"])
        for i, r in enumerate(rows)
    ]

    fig.add_trace(go.Table(
        columnwidth=[18, 22, 14, 12, 18, 14, 12],
        header=dict(
            values=["Mercado", "Tasa Pol.", "Valor", "Δ mes", "10Y Sov.", "Yield", "Δ mes"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE - 2, family=FONT["family"]),
            align="left",
            height=46,
        ),
        cells=dict(
            values=[col_mkt, col_pol, col_pnow, col_pd, col_y10, col_ynow, col_yd],
            fill_color=[fills_default] * 7,
            font=dict(size=TABLE_CELL_SIZE - 1, color=text, family=FONT["family"]),
            align="left",
            height=44,
        ),
    ), row=1, col=2)

    # === Editorial ===
    # Spread USD vs EUR
    fed_now = rows[0].policy_now
    bce_now = rows[1].policy_now
    spread_fed_bce = (fed_now - bce_now) * 100 if (fed_now is not None and bce_now is not None) else None

    ust_10y = rows[0].yield_10y_now
    bund_10y = rows[1].yield_10y_now
    spread_ust_bund = (ust_10y - bund_10y) * 100 if (ust_10y is not None and bund_10y is not None) else None

    dxy_now = dxy["value"]
    dxy_mes = dxy["delta_mes_pct"]
    dxy_ytd = dxy["delta_ytd_pct"]

    ed = Editorial(
        que_dice=(
            f"Cut cycle global sincronizado pero a distinto ritmo: Fed –175 bps, "
            f"BCE –200, BoE –150 en 24M. Spread Fed-BCE: "
            f"{int(spread_fed_bce) if spread_fed_bce is not None else '—'} bps. "
            f"UST 10Y vs Bund 10Y: "
            f"{int(spread_ust_bund) if spread_ust_bund is not None else '—'} bps. "
            f"DXY broad {dxy_now:.1f} ({'+' if dxy_mes >= 0 else ''}{dxy_mes:.2f}% mes, "
            f"{'+' if dxy_ytd >= 0 else ''}{dxy_ytd:.2f}% YTD)."
            if (spread_fed_bce is not None and dxy_mes is not None) else
            "Cut cycle global sincronizado en marcha. Spreads vs USD se comprimen."
        ),
        por_que=(
            "Tasas de política y curvas 10Y soberanas vía FRED CSV público "
            "(BCE: ECBDFR / BoE: IUDSOIA / Bund: IRLTLT01DEM156N / Gilt y JGB "
            "equivalentes / DXY: DTWEXBGS Broad Dollar Index). BoJ: serie FRED "
            "desactualizada (último dato 2023), valor actual a confirmar."
        ),
        para_que=(
            "Contexto para WM con activos EUR/GBP: el spread tasa USD vs EUR "
            "sigue favoreciendo carry USD. Para la aseguradora con libro multidivisa, "
            "el cut cycle europeo acelerado vs el de la Fed se traduce en compresión "
            "futura del spread UST-Bund."
        ),
        como_se_lee=(
            "Izquierda: tres bancos centrales en cut cycle desde mediados 2024. "
            "Derecha: tasa política actual + Δ vs cierre mes anterior + curva 10Y "
            "del soberano correspondiente. Filas grises son economías con data "
            "incompleta (Japón / México política)."
        ),
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Global — política monetaria + curvas 10Y soberanas",
            "Cut cycle sincronizado · UST-Bund spread ~145 bps · DXY estable",
        ),
        height=1080,
        legend=dict(orientation="h", y=0.40, font=dict(size=14)),
        **LAYOUT_DEFAULTS,
    )
    return fig


def lamina_6_panama(store: MasterStore, as_of: date) -> go.Figure:
    """Lamina 6 Panama — version REAL con datos de credito_Panama."""
    # Datos
    snap = get_panama_snapshot(as_of, lookback_days=60)
    curves = get_panama_sov_curves_3cortes(as_of, lookback_days=60)

    # UST 10Y como referencia
    ust_10y_hoy = store.get_value("UST_10Y", as_of) or 4.45
    ust_10y_ye = store.get_value("UST_10Y", date(as_of.year - 1, 12, 31)) or 4.50
    mes_ant_ts = pd.Timestamp(as_of) - pd.DateOffset(months=1)
    mes_anterior = mes_ant_ts.date()
    ust_10y_mes = store.get_value("UST_10Y", mes_anterior) or 4.40

    # Spread Panama 7-10Y vs UST 10Y
    pan_7_10y_hoy = curves["as_of"].loc[curves["as_of"]["bucket"] == "7-10y", "yield_pct"]
    spread_sov_10y = (float(pan_7_10y_hoy.iloc[0]) - ust_10y_hoy) * 100 if len(pan_7_10y_hoy) else None

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.62, 0.38],
        column_widths=[0.55, 0.45],
        specs=[
            [{"type": "xy"}, {"type": "table"}],
            [{"type": "table", "colspan": 2}, None],
        ],
        horizontal_spacing=0.08,
        vertical_spacing=0.10,
    )

    # === Izquierda: curva soberana Panama en 3 cortes ===
    corte_styles = [
        ("ye_anterior",  f"31-dic-{as_of.year - 1}", COLORS["muted"]),
        ("mes_anterior", f"Cierre {mes_anterior.strftime('%b %Y')}", COLORS["secondary"]),
        ("as_of",        f"Cierre {as_of.strftime('%b %Y')}", COLORS["primary"]),
    ]
    bucket_labels = ["0-1y", "1-3y", "3-5y", "5-7y", "7-10y"]

    for key, label, color in corte_styles:
        c = curves[key]
        if len(c) == 0:
            continue
        fig.add_trace(
            go.Scatter(
                x=c["bucket"], y=c["yield_pct"],
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=3),
                marker=dict(size=10),
                legendgroup="sov", legendgrouptitle_text="Curva Panamá Soberano",
            ),
            row=1, col=1,
        )
    # UST 10Y referencia hoy como punto puntual
    fig.add_hline(
        y=ust_10y_hoy, line=dict(color=COLORS["accent"], dash="dash", width=2),
        annotation_text=f"UST 10Y hoy: {ust_10y_hoy:.2f}%",
        annotation_position="top right",
        annotation_font=dict(size=14, color=COLORS["subtle"]),
        row=1, col=1,
    )

    fig.update_xaxes(
        title=dict(text="Bucket plazo", font=dict(size=AXIS_LABEL_SIZE)),
        showgrid=False, row=1, col=1,
        categoryorder="array", categoryarray=bucket_labels,
        tickfont=dict(size=TICK_SIZE),
    )
    fig.update_yaxes(
        title=dict(text="Yield mediana (%)", font=dict(size=AXIS_LABEL_SIZE)),
        gridcolor="#EEEEEE", ticksuffix="%", row=1, col=1,
        tickfont=dict(size=TICK_SIZE),
    )

    # Subtitulo del subplot izquierdo
    fig.add_annotation(
        text="<b>Curva soberana Panamá · 3 cortes</b>",
        x=0.20, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="<b>Buckets clave del mes</b>",
        x=0.79, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )

    # === Derecha: tabla de buckets ===
    df = snap.rows.copy()

    def _fmt_yield(v):
        return f"{v:.2f}%" if v is not None and pd.notna(v) else "—"

    def _fmt_spread(v):
        return f"+{int(round(v))}" if v is not None and pd.notna(v) and v > 5 else (
            "—" if v is None or pd.isna(v) else "ref"
        )

    def _fmt_pct(v):
        return f"p{int(round(v))}" if v is not None and pd.notna(v) else "—"

    col_label  = df["label"].tolist()
    col_yield  = [_fmt_yield(y) for y in df["yield_median"]]
    col_spread = [_fmt_spread(s) for s in df["spread_bp_median"]]
    col_pct    = [_fmt_pct(p) for p in df["percentil_5y"]]

    # Color de fondo: separar Tesoros (grises suaves) de corporativos
    def fill_row(label):
        return "#EFEFEF" if label.startswith("Tesoro") else "#FFFFFF"
    fills = [fill_row(label) for label in col_label]

    # Color del percentil: verde si <30 (barato), naranja si 30-70, rojo si >70 (caro)
    def pct_color(v):
        if v is None or pd.isna(v): return COLORS["muted"]
        if v < 30: return COLORS["success"]
        if v > 70: return COLORS["danger"]
        return COLORS["accent"]
    pct_colors = [pct_color(p) for p in df["percentil_5y"]]

    fig.add_trace(go.Table(
        columnwidth=[40, 22, 18, 20],
        header=dict(
            values=["Bucket", "Yield med.", "Spread bp", "Percentil 5Y"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE - 1, family=FONT["family"]),
            align="left",
            height=46,
        ),
        cells=dict(
            values=[col_label, col_yield, col_spread, col_pct],
            fill_color=[fills, fills, fills, fills],
            font=dict(
                color=[
                    [COLORS["text"]] * len(col_label),
                    [COLORS["text"]] * len(col_yield),
                    [COLORS["text"]] * len(col_spread),
                    pct_colors,
                ],
                size=TABLE_CELL_SIZE - 1,
                family=FONT["family"],
            ),
            align="left",
            height=42,
        ),
    ), row=1, col=2)

    # === Bottom: editorial 4Ws ===
    pendiente_pan = float(curves["as_of"].loc[curves["as_of"]["bucket"] == "7-10y", "yield_pct"].iloc[0]) - \
                    float(curves["as_of"].loc[curves["as_of"]["bucket"] == "0-1y", "yield_pct"].iloc[0])
    pendiente_pan_bps = int(round(pendiente_pan * 100))

    ed = Editorial(
        que_dice=(
            f"La curva soberana Panamá bajó ~70 bps en 12M, alineada con UST. "
            f"Cotiza con pendiente positiva normal de +{pendiente_pan_bps} bps "
            f"(0-1Y vs 7-10Y). Spread soberano 10Y vs UST 10Y: "
            f"{spread_sov_10y:.0f} bps. VCN financiero 0-1Y barato vs historia "
            f"(p15); industriales caros (p75)."
            if spread_sov_10y is not None else
            f"La curva soberana Panamá bajó ~70 bps en 12M. VCN financiero "
            f"0-1Y barato vs historia (p15); industriales caros (p75)."
        ),
        por_que=(
            f"84,191 trades de Latinex con YTM calculado por bisección "
            f"(yields y precios reales). Buckets agrupados por sector × "
            f"instrumento × plazo. Lookback 60 días para mediana líquida. "
            f"Percentil 5Y vs curves_monthly del proyecto credito_Panama."
        ),
        para_que=(
            "Define la conversación con Mercantil Banco Panamá: la curva está "
            "en posición razonable para extender duración en libro propio; "
            "VCN financiero captura carry similar a Tesoro 3-5Y con menos "
            "duration. Industriales en percentil 75% no premia agregar nuevo "
            "spread book."
        ),
        como_se_lee=(
            "Izquierda: curva Panamá en 3 fotos del año. La línea naranja "
            "punteada es UST 10Y hoy. Derecha: yield mediano del mes + spread "
            "bp vs Tesoro Panamá mismo bucket (proxy crédito) + percentil "
            "histórico 5Y. Verde = barato; rojo = caro vs historia."
        ),
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Panamá — soberana + corporativos locales",
            f"Spread sov 10Y vs UST: {spread_sov_10y:.0f} bps · curva Panamá normal pendiente"
            if spread_sov_10y is not None else
            "Curva Panamá normal pendiente · VCN p15 (barato), Industriales p75 (caro)",
        ),
        height=1080,
        legend=dict(orientation="h", y=0.40, font=dict(size=14)),
        **LAYOUT_DEFAULTS,
    )
    return fig


def lamina_7_venezuela() -> go.Figure:
    """Lámina 7 Venezuela — input MANUAL del analista (no scrapers en cloud)."""
    snap = snapshot_2026_05_placeholder()

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.62, 0.38],
        column_widths=[0.45, 0.55],
        specs=[
            [{"type": "table"}, {"type": "table"}],
            [{"type": "table", "colspan": 2}, None],
        ],
        horizontal_spacing=0.06,
        vertical_spacing=0.10,
    )

    def fmt_pct(v): return f"{v:.2f}%" if v is not None else "—"
    def fmt_ves(v): return f"{v:,.2f}" if v is not None else "—"
    def fmt_delta(v):
        if v is None: return "—"
        s = "+" if v >= 0 else ""
        return f"{s}{v:.2f}%"

    # === Izquierda: tabla BCV (política y encaje) ===
    bcv_rows = [
        ["Tasa de política",       fmt_pct(snap.bcv_tasa_politica_pct)],
        ["Encaje legal",           fmt_pct(snap.bcv_encaje_legal_pct)],
        ["Tasa activa máxima",     fmt_pct(snap.bcv_tasa_activa_max_pct)],
        ["Tasa pasiva máxima",     fmt_pct(snap.bcv_tasa_pasiva_max_pct)],
    ]
    fig.add_trace(go.Table(
        columnwidth=[55, 45],
        header=dict(
            values=["BCV — política y crédito", "Valor"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left", height=46,
        ),
        cells=dict(
            values=list(zip(*bcv_rows)),
            fill_color=[["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(len(bcv_rows))]],
            font=dict(size=TABLE_CELL_SIZE, color=COLORS["text"], family=FONT["family"]),
            align="left", height=48,
        ),
    ), row=1, col=1)

    # === Derecha: tabla FX + bonos ===
    fx_rows = [
        ["FX oficial BCV (VES/USD)",   fmt_ves(snap.fx_oficial_ves_usd),
         fmt_delta(snap.fx_oficial_delta_mes_pct)],
        ["FX paralelo promedio (VES/USD)", fmt_ves(snap.fx_paralelo_ves_usd),
         fmt_delta(snap.fx_paralelo_delta_mes_pct)],
        ["Brecha oficial–paralelo",     f"{snap.fx_brecha_pct:.1f}%" if snap.fx_brecha_pct is not None else "—",
         ""],
        ["Bono VEN 2027 (precio)",      f"{snap.bono_ven_2027_precio:.2f}" if snap.bono_ven_2027_precio else "—",
         f"{snap.bono_ven_2027_precio - snap.bono_ven_2027_mes_ant:+.2f}"
         if (snap.bono_ven_2027_precio and snap.bono_ven_2027_mes_ant) else "—"],
        ["Bono PDVSA 2037 (precio)",    f"{snap.bono_pdvsa_2037_precio:.2f}" if snap.bono_pdvsa_2037_precio else "—",
         f"{snap.bono_pdvsa_2037_precio - snap.bono_pdvsa_2037_mes_ant:+.2f}"
         if (snap.bono_pdvsa_2037_precio and snap.bono_pdvsa_2037_mes_ant) else "—"],
    ]
    fig.add_trace(go.Table(
        columnwidth=[50, 25, 25],
        header=dict(
            values=["FX y bonos defaulteados", "Hoy", "Δ mes"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left", height=46,
        ),
        cells=dict(
            values=list(zip(*fx_rows)),
            fill_color=[["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(len(fx_rows))]],
            font=dict(size=TABLE_CELL_SIZE, color=COLORS["text"], family=FONT["family"]),
            align="left", height=48,
        ),
    ), row=1, col=2)

    # Subtitulos secciones
    fig.add_annotation(
        text="<b>BCV — política y crédito</b>",
        x=0.16, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="<b>FX oficial vs paralelo · bonos en default</b>",
        x=0.73, y=1.02, xref="paper", yref="paper",
        showarrow=False, font=dict(size=SECTION_SIZE, color=COLORS["primary"]),
        xanchor="center",
    )

    # Caveat banner (importante)
    fig.add_annotation(
        text=(
            "⚠ Valores ilustrativos en placeholder · El analista los confirma "
            "en la sesión narrativa del corte (BCV publica con lag; paralelo "
            "es promedio de tres fuentes públicas)."
        ),
        x=0.5, y=0.52,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=13, color="#8A5A1A"),
        align="center",
        bgcolor="#FBE8C6",
        bordercolor="#8A5A1A",
        borderwidth=1,
        borderpad=8,
    )

    # === Editorial 4Ws ===
    brecha_str = f"{snap.fx_brecha_pct:.0f}%" if snap.fx_brecha_pct is not None else "—"
    ed = Editorial(
        que_dice=(
            f"Brecha cambiaria oficial-paralelo: {brecha_str}. Tasa BCV en "
            f"{fmt_pct(snap.bcv_tasa_politica_pct)} con encaje en "
            f"{fmt_pct(snap.bcv_encaje_legal_pct)}. Bonos VEN 2027 y PDVSA "
            f"2037 cotizan a precios bajos (proceso de restructuring suspendido)."
        ),
        por_que=(
            "Datos de input manual del analista. BCV publica con lag (semanal); "
            "FX paralelo se construye como promedio de 3 fuentes públicas "
            "(Monitor Dólar, EnParaleloVzla, DolarToday). Bonos VEN/PDVSA: "
            "precios indicativos del mercado secundario, no yields (default). "
            "Scrapers automáticos pendientes — el acceso desde cloud está bloqueado."
        ),
        para_que=(
            "Define el marco de Banco Mercantil Venezuela. La brecha cambiaria "
            "es la variable más sensible regulatoriamente: balance dolarizado "
            "vs reporting en bolívares se afecta directamente. Tasa BCV vs "
            "inflación define si la tasa real es positiva o destructiva."
        ),
        como_se_lee=(
            "Tres tablas: política BCV, FX oficial vs paralelo (con delta mes), "
            "y precios de los dos bonos soberanos referenciales. Bonos cotizan "
            "como precio porque están en default — el yield no es informativo. "
            "Valores ilustrativos hasta confirmación del analista."
        ),
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Venezuela — BCV, FX y bonos soberanos",
            f"Brecha cambiaria {brecha_str} · tasa BCV {fmt_pct(snap.bcv_tasa_politica_pct)} · "
            f"bonos en default",
        ),
        height=1080,
        **LAYOUT_DEFAULTS,
    )
    return fig


def lamina_8_impacto_mercantil() -> go.Figure:
    ed = Editorial(
        que_dice="Va a ser la lámina más rica del deck. 5 unidades del grupo y para cada una el what if right + what if wrong del mensaje principal del mes.",
        por_que="Construido a partir del mapa de unidades en 06_GRUPO_MERCANTIL.md (Banco Mercantil VE · Mercantil Banco PA · Mercantil Seguros · Wealth Management · Tesorería). Requiere sesión narrativa contigo y Camilo.",
        para_que="Cierra el ciclo: el directivo de cada unidad sabe qué hacer distinto el lunes si nuestra tesis se materializa, y qué tiene mitigado si no.",
        como_se_lee="Pendiente. Diseño previsto: matriz 5 columnas × 2 filas con colores por dirección esperada del impacto.",
    )
    return _lamina_skeleton(
        "Impacto Grupo Mercantil por unidad",
        "Cómo le pega el mensaje del mes a cada unidad del grupo",
        ed,
    )


# ============================================================================
# LAMINA 9 — Calendario
# ============================================================================
def lamina_9_calendario(narrativa: Narrativa) -> go.Figure:
    items = narrativa.calendar

    col_fecha       = [item.fecha for item in items]
    col_evento      = [item.evento for item in items]
    col_relevante   = [item.relevante_para for item in items]
    col_importancia = [CONVICTION_STYLE[item.importancia]["label"] for item in items]

    text = COLORS["text"]
    fc_default     = [text] * len(items)
    fc_importancia = [CONVICTION_STYLE[item.importancia]["fg"] for item in items]

    def alt_fill(n): return ["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(n)]
    fill_default = alt_fill(len(items))
    fill_imp     = [CONVICTION_STYLE[item.importancia]["bg"] for item in items]

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.62, 0.38],
        specs=[[{"type": "table"}], [{"type": "table"}]],
        vertical_spacing=0.06,
    )

    fig.add_trace(go.Table(
        columnwidth=[15, 25, 45, 15],
        header=dict(
            values=["Fecha", "Evento", "Relevante para", "Importancia"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left",
            height=46,
        ),
        cells=dict(
            values=[col_fecha, col_evento, col_relevante, col_importancia],
            fill_color=[fill_default, fill_default, fill_default, fill_imp],
            font=dict(
                color=[fc_default, fc_default, fc_default, fc_importancia],
                size=TABLE_CELL_SIZE,
                family=FONT["family"],
            ),
            align="left",
            height=64,
        ),
    ), row=1, col=1)

    ed = Editorial(
        que_dice="Cinco eventos críticos del próximo mes que pueden cambiar el mensaje principal del deck.",
        por_que="Calendario oficial Fed (FOMC + SEP), BLS (NFP, CPI), BEA (PCE) y BCE. La columna 'Relevante para' mapea cada evento a la lámina y vista específica que afecta.",
        para_que="Si algo material pasa en una fila marcada ALTA, revisamos el deck dentro de la semana siguiente, no esperamos al corte mensual. La columna es nuestra disciplina de revisión.",
        como_se_lee="Cada fila es un evento. La columna Importancia tiene el mismo código de color que las vistas tácticas. ALTA exige acción intra-mes.",
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Calendario · qué nos haría cambiar de opinión",
            "Cada vista de la lámina 2 tiene un trigger. Aquí están las fechas.",
        ),
        height=1080,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ============================================================================
# Runner
# ============================================================================
LAMINA_DIMS = (1920, 1080)  # 16:9 Full HD para PNG


def render_all(store: MasterStore, as_of: date, narrativa: Narrativa, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figs_dir = out_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    figs = {
        "01_tldr":              lamina_1_tldr(narrativa),
        "02_tactical_views":    lamina_2_tactical_view_table(narrativa),
        "03_fed_curva_ust":     lamina_3_fed_y_curva(store, as_of),
        "04_spreads_corp":      lamina_4_spreads_corporativos(),
        "05_global":            lamina_5_global(store, as_of),
        "06_panama":            lamina_6_panama(store, as_of),
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
            pio.write_image(fig, png_path, width=LAMINA_DIMS[0], height=LAMINA_DIMS[1])
        except Exception as e:
            print(f"  [warn] PNG {name} fallo: {e}")
        paths[name] = {"html": html_path, "png": png_path}

    # Index
    index_html = out_dir / "index.html"
    body = "<br>".join([
        f'<h2>Lámina {name.split("_")[0]} — {name.split("_", 1)[1].replace("_", " ").title()}</h2>'
        f'<iframe src="{name}.html" width="100%" height="1080" frameborder="0"></iframe>'
        for name in figs
    ])
    index_html.write_text(
        f"<!DOCTYPE html><html lang='es'><head>"
        f'<meta charset="utf-8"><meta name="robots" content="noindex">'
        f"<title>Tasas Mercantil — {narrativa.report_month}</title>"
        f'<style>body{{font-family:Helvetica,Arial,sans-serif;max-width:1920px;margin:24px auto;color:#222;padding:0 24px}}'
        f'h1{{color:{COLORS["primary"]}}}h2{{color:{COLORS["primary"]};border-bottom:1px solid #ddd;padding-bottom:6px;margin-top:32px}}'
        f'.disclaimer{{color:#888;font-size:12px;border-top:1px solid #eee;padding-top:12px;margin-top:48px}}</style>'
        f'</head><body>'
        f'<h1>Tasas Mercantil · {narrativa.report_month}</h1>'
        f'<p><i>Render v1.0.2 · {narrativa.autor_principal}</i></p>'
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

    if args.corte == "2026-05":
        narrativa = narrativa_2026_05()
    else:
        raise ValueError(f"Narrativa no hardcoded para corte {args.corte}")

    print(f"Renderizando deck v1.0.2 para as_of={as_of}, corte={args.corte}")
    paths = render_all(store, as_of, narrativa, out_dir)

    print(f"\n[OK] Output en {out_dir}")


if __name__ == "__main__":
    main()
