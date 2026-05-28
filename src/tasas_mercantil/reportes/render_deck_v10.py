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
    "editorial": "#EDF1F6",  # fondo del bloque editorial al pie
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

# Tamanos de fuente — escalados para deck 16:9 leible en presentacion
TITLE_SIZE = 26
SUBTITLE_SIZE = 16
TABLE_HEADER_SIZE = 15
TABLE_CELL_SIZE = 14
EDITORIAL_SIZE = 15
AXIS_LABEL_SIZE = 14
TICK_SIZE = 13

FONT = {"family": "Helvetica, Arial, sans-serif", "size": 14, "color": COLORS["text"]}
LAYOUT_DEFAULTS = {
    "font": FONT,
    "plot_bgcolor": "white",
    "paper_bgcolor": "white",
    "margin": {"l": 70, "r": 40, "t": 110, "b": 200},  # bottom para editorial
}


def _slide_title(text: str, subtitle: str = "") -> dict:
    """Titulo grande, subtitulo en linea separada con espacio."""
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


def _add_editorial(fig: go.Figure, text: str) -> go.Figure:
    """Agrega bloque editorial al pie (texto plano corto, sin HTML)."""
    fig.add_annotation(
        text=text,
        x=0.5, y=-0.22,
        xref="paper", yref="paper",
        xanchor="center", yanchor="top",
        showarrow=False,
        font=dict(size=EDITORIAL_SIZE, color=COLORS["text"]),
        align="left",
        bgcolor=COLORS["editorial"],
        bordercolor=COLORS["primary"],
        borderwidth=1,
        borderpad=18,
        width=1500,
    )
    return fig


# ============================================================================
# LAMINA 1 — TL;DR (3 mensajes + conviction tags)
# ============================================================================
def lamina_1_tldr(narrativa: Narrativa) -> go.Figure:
    """TL;DR con los 3 mensajes del mes + conviction tags. Sin HTML inline en cells."""
    n_msgs = len(narrativa.tldr_messages)
    fig = make_subplots(
        rows=n_msgs, cols=1,
        specs=[[{"type": "table"}]] * n_msgs,
        vertical_spacing=0.05,
    )

    for i, msg in enumerate(narrativa.tldr_messages, start=1):
        style = CONVICTION_STYLE[msg.conviction]

        # Headers: aqui Plotly si soporta HTML para que se vea grande/bold
        header_values = [
            f"Mensaje {i}",
            f"Convicción {style['label']}",
            msg.relevant_unit,
        ]

        # Cells: texto PLANO, sin <b>, sin <i>. El formato sale via font + fill.
        cell_values = [
            [msg.headline],
            [f"Trigger: {msg.trigger}"],
            [""],
        ]

        fig.add_trace(
            go.Table(
                columnwidth=[55, 22, 23],
                header=dict(
                    values=header_values,
                    fill_color=[COLORS["primary"], style["bg"], COLORS["bg"]],
                    font=dict(
                        color=["white", style["fg"], COLORS["text"]],
                        size=TABLE_HEADER_SIZE,
                        family=FONT["family"],
                    ),
                    align="left",
                    height=42,
                ),
                cells=dict(
                    values=cell_values,
                    fill_color="white",
                    align="left",
                    height=60,
                    font=dict(size=TABLE_CELL_SIZE + 1, color=COLORS["text"]),
                ),
            ),
            row=i, col=1,
        )

    fig.update_layout(
        title=_slide_title(
            "TL;DR — 3 mensajes del mes",
            f"Corte {narrativa.report_month} · {narrativa.autor_principal}",
        ),
        height=280 * n_msgs + 200,
        **LAYOUT_DEFAULTS,
    )
    _add_editorial(
        fig,
        "Tres ideas que mueven el reporte de este mes. Cada una con su nivel de "
        "convicción y el evento concreto que la confirma o la rompe. Si solo lee "
        "una página del deck, esta es."
    )
    return fig


# ============================================================================
# LAMINA 2 — Tactical View Table
# ============================================================================
def lamina_2_tactical_view_table(narrativa: Narrativa) -> go.Figure:
    """Tabla con vistas tacticas. Texto PLANO en cells. Color via font.color por columna."""
    views = narrativa.tactical_views

    # Columnas como listas (texto plano, sin tags)
    col_activo     = [v.activo for v in views]
    col_direccion  = [v.direccion for v in views]
    col_horizonte  = [v.horizonte for v in views]
    col_conviction = [CONVICTION_STYLE[v.conviction]["label"] for v in views]
    col_what       = [v.what for v in views]
    col_if_right   = [v.if_right for v in views]
    col_if_wrong   = [v.if_wrong for v in views]
    col_trigger    = [v.trigger for v in views]

    # Color del texto por columna (listas de length=n_filas)
    text = COLORS["text"]
    fc_activo     = [text] * len(views)
    fc_direccion  = [DIRECTION_COLOR.get(v.direccion.split()[0], COLORS["muted"]) for v in views]
    fc_horizonte  = [text] * len(views)
    fc_conviction = [CONVICTION_STYLE[v.conviction]["fg"] for v in views]
    fc_what       = [text] * len(views)
    fc_if_right   = [text] * len(views)
    fc_if_wrong   = [text] * len(views)
    fc_trigger    = [text] * len(views)

    # Fill por columna; conviction tiene fill propio para destacar
    def alt_fill(n): return ["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(n)]
    fill_default   = alt_fill(len(views))
    fill_conviction = [CONVICTION_STYLE[v.conviction]["bg"] for v in views]

    fig = go.Figure(data=[go.Table(
        columnwidth=[12, 10, 6, 9, 18, 16, 16, 13],
        header=dict(
            values=["Activo", "Dirección", "Horiz.", "Convicción",
                    "WHAT", "WHAT IF RIGHT", "WHAT IF WRONG", "TRIGGER"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left",
            height=44,
        ),
        cells=dict(
            values=[col_activo, col_direccion, col_horizonte, col_conviction,
                    col_what, col_if_right, col_if_wrong, col_trigger],
            fill_color=[fill_default, fill_default, fill_default, fill_conviction,
                        fill_default, fill_default, fill_default, fill_default],
            font=dict(
                color=[fc_activo, fc_direccion, fc_horizonte, fc_conviction,
                       fc_what, fc_if_right, fc_if_wrong, fc_trigger],
                size=TABLE_CELL_SIZE,
                family=FONT["family"],
            ),
            align="left",
            height=110,
        ),
    )])
    fig.update_layout(
        title=_slide_title(
            "Tactical Views — las posiciones que defendemos hoy",
            "Cada vista lleva los 4 Ws: qué afirmamos · qué pasa si acertamos · qué cuesta si erramos · qué nos haría revisar",
        ),
        height=200 + 130 * len(views) + 220,  # extra para editorial
        **LAYOUT_DEFAULTS,
    )
    _add_editorial(
        fig,
        "Estas son las posiciones de mesa del mes, cuatro vistas tácticas. Las "
        "publicamos juntas para que se vea el balance — no todo es Alta convicción. "
        "Si una vista no aguanta el costo del error, se cambia o se elimina."
    )
    return fig


# ============================================================================
# LAMINA 3 — Fed + curva UST (fusion de antiguas 3+4+5)
# ============================================================================
def lamina_3_fed_y_curva(store: MasterStore, as_of: date) -> go.Figure:
    """Curva UST 3 cortes (izq) + implied path Fed Funds (der). Sin subplot_titles que se superponen."""
    ye_anterior = date(as_of.year - 1, 12, 31)
    mes_anterior_ts = as_of - pd.DateOffset(months=1)
    mes_anterior = mes_anterior_ts.date() if isinstance(mes_anterior_ts, pd.Timestamp) else mes_anterior_ts

    cortes = [
        (ye_anterior,   f"31-dic-{as_of.year - 1}", COLORS["muted"]),
        (mes_anterior,  f"Cierre {mes_anterior.strftime('%b %Y')}", COLORS["secondary"]),
        (as_of,         f"Cierre {as_of.strftime('%b %Y')}", COLORS["primary"]),
    ]
    tenors_order = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

    # SIN subplot_titles (eso es lo que se superponia con el title general)
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.55, 0.45],
        horizontal_spacing=0.10,
    )

    for corte_date, label, color in cortes:
        df = get_curve_ust(store, corte_date).dropna(subset=["value"]).copy()
        df["order"] = df["tenor"].map({t: i for i, t in enumerate(tenors_order)})
        df = df.sort_values("order")
        fig.add_trace(
            go.Scatter(
                x=df["tenor"], y=df["value"],
                mode="lines+markers", name=label,
                line=dict(color=color, width=2.8),
                marker=dict(size=9),
                legendgroup="curva", legendgrouptitle_text="Curva UST",
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
            name=f"Path implícito (SR3)",
            line=dict(color=COLORS["accent"], width=3),
            marker=dict(size=11),
            legendgroup="path", legendgrouptitle_text="Expectativa Fed",
        ),
        row=1, col=2,
    )
    fig.add_hline(
        y=pred.fed_funds_now, line=dict(color=COLORS["muted"], dash="dash", width=1.5),
        annotation_text=f"Fed Funds hoy: {pred.fed_funds_now:.2f}%",
        annotation_position="bottom right",
        annotation_font=dict(size=13, color=COLORS["subtle"]),
        row=1, col=2,
    )

    # Anotaciones grandes "izquierda" y "derecha" arriba de cada subplot
    fig.add_annotation(
        text="<b>Curva UST · 3 cortes</b>",
        x=0.22, y=1.04, xref="paper", yref="paper",
        showarrow=False, font=dict(size=18, color=COLORS["primary"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="<b>Tasa Fed que descuenta el mercado</b>",
        x=0.78, y=1.04, xref="paper", yref="paper",
        showarrow=False, font=dict(size=18, color=COLORS["primary"]),
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

    fig.update_layout(
        title=_slide_title(
            "Fed Funds + curva UST",
            "Sweet spot 5-10Y · target yield 4.20-4.50%",
        ),
        height=820,
        legend=dict(orientation="h", y=-0.20, font=dict(size=13)),
        **LAYOUT_DEFAULTS,
    )
    _add_editorial(
        fig,
        "Izquierda: la curva UST en tres fotos para ver cómo se movió en el año y "
        "en el último mes. Hoy es positivamente inclinada (2s10s +43 bps). "
        "Derecha: lo que el mercado paga hoy por la tasa Fed esperada en cada "
        "horizonte futuro, leído del strip de futuros SR3. El path descuenta "
        "tasas estables a ligeramente alcistas; el cut cycle parece terminado."
    )
    return fig


# ============================================================================
# LAMINA SKELETON — para Spreads, Global, Panama, Venezuela, Mercantil
# Skeletons dimensionados con titulo + bullet de "pendiente" para que el
# usuario pueda iterar la narrativa en sesion.
# ============================================================================
def _lamina_skeleton(titulo: str, subtitulo: str, editorial: str, height: int = 750) -> go.Figure:
    """Skeleton para laminas pendientes. Texto grande, claro, sin labels confusos."""
    fig = go.Figure()
    fig.add_annotation(
        text="Lámina en construcción",
        showarrow=False,
        x=0.5, y=0.62,
        xref="paper", yref="paper",
        font=dict(size=32, color=COLORS["muted"]),
        xanchor="center",
    )
    fig.add_annotation(
        text="contenido y data llegan en próxima iteración",
        showarrow=False,
        x=0.5, y=0.45,
        xref="paper", yref="paper",
        font=dict(size=16, color=COLORS["subtle"]),
        xanchor="center",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        title=_slide_title(titulo, subtitulo),
        height=height,
        **LAYOUT_DEFAULTS,
    )
    _add_editorial(fig, editorial)
    return fig


def lamina_4_spreads_corporativos() -> go.Figure:
    return _lamina_skeleton(
        "Spreads corporativos — IG, HY, EMBI",
        "Definimos shock al spread como ampliación >50 bps en 30 días",
        "Va a ser una tabla pivot región × rating × plazo con yield, spread vs UST "
        "y percentil histórico 5Y. Más un sparkline mostrando los buckets que más se "
        "movieron este mes. La data llega cuando Antulio confirme acceso a los "
        "subíndices ICE BofA (C0A0-C0A4 para IG, H0A0-H0A3 para HY) y CEMBI."
    )


def lamina_5_global() -> go.Figure:
    return _lamina_skeleton(
        "Global — BCE/BoE + USD index",
        "Vigilamos divergencia Fed–BCE y su impacto en DXY",
        "Aquí va el diferencial de tasa política Fed vs BCE / BoE / BoJ, curva 10Y "
        "soberana G7 y DXY a 12 meses. Lectura del mercado, no modelo propio: para "
        "BCE/BoE/BoJ el modelo predictivo Mercantil no aplica en v1.0 (decisión en "
        "13_GLOBALES_Y_OTROS_PAISES.md)."
    )


def lamina_6_panama() -> go.Figure:
    return _lamina_skeleton(
        "Panamá — soberana + corporativos locales",
        "Spread PAN 10Y vs UST hoy ~130 bps · mediana 5Y 240 bps",
        "Conecta con el dataset que ya existe en credito_Panama "
        "(curves_monthly.parquet, trades.parquet con 18 mil YTMs calculados). "
        "Lámina con la curva soberana Panamá vs UST, spread vs UST, hechos "
        "relevantes del mes en Latinex y los buckets de VCN, Letras del Tesoro y "
        "Bonos Hipotecarios. Es trabajo de integración, no nueva ingesta."
    )


def lamina_7_venezuela() -> go.Figure:
    return _lamina_skeleton(
        "Venezuela — BCV vs paralelo + bonos",
        "Brecha cambiaria oficial-paralelo y status PDVSA / VENZ defaulteados",
        "Aquí va tasa de política BCV, encaje legal, tipo de cambio oficial vs "
        "promedio de 3 fuentes públicas para el paralelo (Monitor Dólar, "
        "EnParaleloVzla, DolarToday). Bonos VEN / PDVSA reportados a precio, no "
        "yield (están en default). La data exige scrapers propios — implementación "
        "en M-3."
    )


def lamina_8_impacto_mercantil() -> go.Figure:
    return _lamina_skeleton(
        "Impacto Grupo Mercantil por unidad",
        "Cómo le pega el mensaje del mes a cada unidad del grupo",
        "Esta es la lámina más rica del deck. Mapa con 5 columnas — Banco Mercantil "
        "VE · Mercantil Banco PA · Mercantil Seguros · Wealth Management · Tesorería "
        "del grupo — y dos filas por unidad: qué pasa si nuestra tesis funciona y "
        "qué pasa si nos equivocamos. Requiere sesión narrativa contigo y Camilo "
        "para mapear cada unidad antes de poblar.",
        height=820,
    )


# ============================================================================
# LAMINA 9 — Calendario + qué nos haría cambiar de opinión
# ============================================================================
def lamina_9_calendario(narrativa: Narrativa) -> go.Figure:
    """Calendario del proximo mes. Texto plano + color por columna."""
    items = narrativa.calendar

    col_fecha       = [item.fecha for item in items]
    col_evento      = [item.evento for item in items]
    col_relevante   = [item.relevante_para for item in items]
    col_importancia = [CONVICTION_STYLE[item.importancia]["label"] for item in items]

    # Color de texto: importancia destaca con su color
    text = COLORS["text"]
    fc_default     = [text] * len(items)
    fc_importancia = [CONVICTION_STYLE[item.importancia]["fg"] for item in items]

    def alt_fill(n): return ["#FFFFFF" if i % 2 == 0 else COLORS["bg"] for i in range(n)]
    fill_default = alt_fill(len(items))
    fill_imp     = [CONVICTION_STYLE[item.importancia]["bg"] for item in items]

    fig = go.Figure(data=[go.Table(
        columnwidth=[15, 25, 45, 15],
        header=dict(
            values=["Fecha", "Evento", "Relevante para", "Importancia"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=TABLE_HEADER_SIZE, family=FONT["family"]),
            align="left",
            height=44,
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
            height=58,
        ),
    )])
    fig.update_layout(
        title=_slide_title(
            "Calendario · qué nos haría cambiar de opinión",
            "Cada vista de la lámina 2 tiene un trigger. Aquí están las fechas.",
        ),
        height=200 + 75 * len(items) + 220,
        **LAYOUT_DEFAULTS,
    )
    _add_editorial(
        fig,
        "Las fechas críticas del próximo mes y a qué vista táctica afecta cada "
        "evento. Si algo material pasa en una fila marcada ALTA, revisamos el deck "
        "dentro de la semana siguiente, no esperamos al corte mensual."
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
