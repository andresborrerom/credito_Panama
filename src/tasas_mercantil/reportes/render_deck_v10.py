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
from ..modelo.pieces.implied_path import compute_implied_path
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

    # Implied path (der)
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
            name="Path implícito (SR3)",
            line=dict(color=COLORS["accent"], width=3.5),
            marker=dict(size=12),
            legendgroup="path", legendgrouptitle_text="Expectativa Fed",
        ),
        row=1, col=2,
    )
    fig.add_hline(
        y=pred.fed_funds_now, line=dict(color=COLORS["muted"], dash="dash", width=1.5),
        annotation_text=f"Fed Funds hoy: {pred.fed_funds_now:.2f}%",
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
        text="<b>Tasa Fed que descuenta el mercado</b>",
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

    ed = Editorial(
        que_dice="Curva UST con pendiente positiva (2s10s +43 bps) y un sweet spot 5-10Y; el mercado descuenta tasas Fed estables a ligeramente alcistas en los próximos 24 meses.",
        por_que="Curva: datos diarios Bloomberg de constant-maturity UST en 3 fechas — cierre 2025, cierre abril 2026 y hoy. Path: precio del strip SR3 (8 futuros trimestrales) leído como tasa promedio para cada trimestre futuro.",
        para_que="Refuerza la vista UST 5-10Y overweight (lámina 2). Si la pendiente se aplana <20 bps o el path implícito baja >25 bps, revisamos duración objetivo.",
        como_se_lee="Izquierda: cuanto más alta y empinada la curva, mejor el carry por plazo. Derecha: el eje horizontal es tiempo futuro; cada punto naranja es la tasa Fed que el mercado paga hoy por cubrirse en ese horizonte.",
    )
    fig.add_trace(_editorial_table(ed), row=2, col=1)

    fig.update_layout(
        title=_slide_title(
            "Fed Funds + curva UST",
            "Sweet spot 5-10Y · target yield 4.20-4.50%",
        ),
        height=1080,
        legend=dict(orientation="h", y=0.46, font=dict(size=14)),
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


def lamina_5_global() -> go.Figure:
    ed = Editorial(
        que_dice="Va a mostrar el diferencial de política monetaria Fed vs BCE/BoE/BoJ y su impacto en el DXY a 12 meses.",
        por_que="Lectura del mercado, no modelo propio. Para los bancos centrales no-Fed, en v1.0 no aplica el modelo Mercantil predictivo (ver 13_GLOBALES_Y_OTROS_PAISES.md).",
        para_que="Contexto del marco global para las decisiones USD del grupo. Un DXY que rompe rango cambia la conversación de la aseguradora con activos EUR y del WM en EM USD.",
        como_se_lee="Pendiente. Diseño previsto: line plot de spreads de política + DXY a 12M con anotaciones de cada decisión BCE/BoE.",
    )
    return _lamina_skeleton(
        "Global — BCE/BoE + USD index",
        "Vigilamos divergencia Fed-BCE y su impacto en DXY",
        ed,
    )


def lamina_6_panama() -> go.Figure:
    ed = Editorial(
        que_dice="Va a mostrar la curva soberana Panamá vs UST, el spread vs UST en percentil histórico, y los buckets de VCN, Letras del Tesoro y Bonos Hipotecarios locales.",
        por_que="Datos ya existentes en el proyecto credito_Panama: curves_monthly.parquet, trades.parquet (84,191 operaciones con 18,210 YTM calculados). Trabajo de integración, no nueva ingesta.",
        para_que="Es la lámina más relevante para Mercantil Banco Panamá. Define si el libro de inversiones recibe duración nueva o si esperamos repricing.",
        como_se_lee="Pendiente. Diseño previsto: curva Panamá superpuesta con UST + tabla de spreads percentil 5Y + 5 hechos relevantes del mes en Latinex.",
    )
    return _lamina_skeleton(
        "Panamá — soberana + corporativos locales",
        "Spread PAN 10Y vs UST hoy ~130 bps · mediana 5Y 240 bps",
        ed,
    )


def lamina_7_venezuela() -> go.Figure:
    ed = Editorial(
        que_dice="Va a mostrar tasa de política BCV, encaje legal, tipo de cambio oficial vs paralelo (promedio de 3 fuentes públicas) y precio de bonos VEN / PDVSA.",
        por_que="Scrapers propios para BCV (publica con lag) y promedio Monitor Dólar + EnParaleloVzla + DolarToday para el paralelo. Bonos VEN/PDVSA reportados a precio porque están en default.",
        para_que="Define el marco de Banco Mercantil Venezuela: brecha cambiaria condiciona la lectura del balance dolarizado y el riesgo regulatorio de la operación local.",
        como_se_lee="Pendiente. Diseño previsto: dual axis (oficial vs paralelo) + tabla con encaje, tasa BCV y posición soberana defaulteada.",
    )
    return _lamina_skeleton(
        "Venezuela — BCV vs paralelo + bonos",
        "Brecha cambiaria oficial-paralelo y status PDVSA / VENZ defaulteados",
        ed,
    )


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
