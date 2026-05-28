"""Primer render del deck v0.1 — 3 laminas core con Plotly y datos reales.

Laminas:
- Lamina 3: Politica monetaria + mercado USA (Fed Funds, IORB, ON RRP, SOFR ON,
  UST 2/5/10).
- Lamina 4: Curva UST en 3 cortes (31-dic año anterior, mes anterior, mes en curso).
- Lamina 5: Tres lecturas de expectativas Fed (implied path SR3 + modelo Mercantil
  Pieza A; FedWatch y Pieza B llegaran en versiones siguientes).

Output: cortes/<YYYY-MM>/output/lamina_<N>.html + figs/*.png

Uso:
    python -m src.tasas_mercantil.reportes.render_deck_v01 \\
        --as-of 2026-05-29 --corte 2026-05
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ..data.store import load_master_store, MasterStore
from ..data.queries import (
    UST_TENOR_TO_FEATURE,
    get_curve_ust,
    get_fed_funds_snapshot,
    get_implied_path_strip,
)
from ..modelo.pieces.implied_path import compute_implied_path


# Paleta Mercantil (placeholder hasta que llegue la oficial)
COLORS = {
    "primary":   "#1F3A5F",
    "secondary": "#5A8FB0",
    "accent":    "#D9A24D",
    "muted":     "#999999",
    "danger":    "#C2455D",
    "success":   "#3E8B6A",
    "bg":        "#F7F7F7",
}

LAYOUT_DEFAULTS = {
    "font": {"family": "Helvetica, Arial, sans-serif", "size": 12, "color": "#222"},
    "plot_bgcolor": "white",
    "paper_bgcolor": "white",
    "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
}


# ---------------------------------------------------------------------------
# LAMINA 3 — Politica monetaria + mercado USA
# ---------------------------------------------------------------------------
def lamina_3_politica_y_mercado(store: MasterStore, as_of: date) -> go.Figure:
    """Tabla + lineas 12M de FF target / IORB / ON RRP / EFFR / SOFR ON / UST 2/5/10."""
    # Tabla snapshot
    fed = get_fed_funds_snapshot(store, as_of)
    ust_2y  = store.get_value("UST_2Y", as_of)
    ust_5y  = store.get_value("UST_5Y", as_of)
    ust_10y = store.get_value("UST_10Y", as_of)
    sofr_on = store.get_value("SOFR_ON", as_of)
    sofr_3m = store.get_value("TERM_SOFR_3M", as_of)

    # vs mes anterior
    mes_ant = as_of - pd.DateOffset(months=1)
    if isinstance(mes_ant, pd.Timestamp):
        mes_ant = mes_ant.date()

    def fmt(v): return f"{v:.2f}%" if v is not None else "—"
    def delta(now, prev):
        if now is None or prev is None: return "—"
        bps = (now - prev) * 100
        sign = "+" if bps >= 0 else ""
        return f"{sign}{bps:.0f} bps"

    ust_2y_prev  = store.get_value("UST_2Y", mes_ant)
    ust_10y_prev = store.get_value("UST_10Y", mes_ant)
    fed_prev = get_fed_funds_snapshot(store, mes_ant)

    # Cuerpo de la tabla
    rows = [
        ["Fed Funds (target)", f"{fmt(fed.get('target_lower'))} – {fmt(fed.get('target_upper'))}",
         delta(fed.get("target_upper"), fed_prev.get("target_upper"))],
        ["IORB",   fmt(fed.get("iorb")),       delta(fed.get("iorb"), fed_prev.get("iorb"))],
        ["ON RRP", fmt(fed.get("on_rrp")),     delta(fed.get("on_rrp"), fed_prev.get("on_rrp"))],
        ["EFFR",   fmt(fed.get("effective")),  delta(fed.get("effective"), fed_prev.get("effective"))],
        ["SOFR ON", fmt(sofr_on), delta(sofr_on, store.get_value("SOFR_ON", mes_ant))],
        ["Term SOFR 3M", fmt(sofr_3m), delta(sofr_3m, store.get_value("TERM_SOFR_3M", mes_ant))],
        ["UST 2Y", fmt(ust_2y),  delta(ust_2y, ust_2y_prev)],
        ["UST 5Y", fmt(ust_5y),  delta(ust_5y, store.get_value("UST_5Y", mes_ant))],
        ["UST 10Y", fmt(ust_10y), delta(ust_10y, ust_10y_prev)],
    ]

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.4, 0.6],
        specs=[[{"type": "table"}], [{"type": "xy"}]],
        subplot_titles=("Snapshot al cierre", "Evolución 12 meses"),
        vertical_spacing=0.08,
    )

    # Tabla
    fig.add_trace(
        go.Table(
            header=dict(
                values=["<b>Instrumento</b>", "<b>Valor</b>", "<b>Δ mes</b>"],
                fill_color=COLORS["primary"],
                font=dict(color="white", size=12),
                align="left",
                height=28,
            ),
            cells=dict(
                values=list(zip(*rows)),
                fill_color=[["#FFFFFF" if i % 2 else "#F7F7F7" for i in range(len(rows))]],
                align="left",
                height=26,
                font=dict(size=11),
            ),
        ),
        row=1, col=1,
    )

    # Lineas 12M
    start = as_of - timedelta(days=365)
    series_to_plot = [
        ("UST_2Y",       "UST 2Y",       COLORS["primary"]),
        ("UST_5Y",       "UST 5Y",       COLORS["secondary"]),
        ("UST_10Y",      "UST 10Y",      COLORS["accent"]),
        ("EFFR",         "EFFR",         COLORS["danger"]),
        ("TERM_SOFR_3M", "Term SOFR 3M", COLORS["success"]),
    ]
    for fname, label, color in series_to_plot:
        try:
            s = store.get_series(fname, as_of, start=start)
            if not s.empty:
                fig.add_trace(
                    go.Scatter(
                        x=s.index, y=s.values, mode="lines", name=label,
                        line=dict(color=color, width=1.8),
                    ),
                    row=2, col=1,
                )
        except Exception:
            pass

    fig.update_xaxes(showgrid=False, tickformat="%b %Y", row=2, col=1)
    fig.update_yaxes(
        title_text="Yield (%)", gridcolor="#EEEEEE", row=2, col=1, ticksuffix="%",
    )
    fig.update_layout(
        title=dict(
            text=f"<b>Fase 1 USA — Política monetaria y mercado · {as_of.strftime('%b %Y')}</b>",
            font=dict(size=18, color=COLORS["primary"]),
        ),
        height=750,
        showlegend=True,
        legend=dict(orientation="h", y=-0.05),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# LAMINA 4 — Curva UST en 3 cortes
# ---------------------------------------------------------------------------
def lamina_4_curva_ust(store: MasterStore, as_of: date) -> go.Figure:
    """3 curvas superpuestas: 31-dic año anterior, cierre mes anterior, mes en curso."""
    ye_anterior = date(as_of.year - 1, 12, 31)
    mes_anterior_dt = as_of - pd.DateOffset(months=1)
    mes_anterior = mes_anterior_dt.date() if isinstance(mes_anterior_dt, pd.Timestamp) else mes_anterior_dt

    cortes = [
        (ye_anterior,   f"31-dic-{as_of.year - 1}", COLORS["muted"]),
        (mes_anterior,  f"Cierre {mes_anterior.strftime('%b %Y')}",  COLORS["secondary"]),
        (as_of,         f"Cierre {as_of.strftime('%b %Y')}",         COLORS["primary"]),
    ]

    fig = go.Figure()
    tenors_order = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

    for corte_date, label, color in cortes:
        df = get_curve_ust(store, corte_date)
        df = df.dropna(subset=["value"]).copy()
        df["order"] = df["tenor"].map({t: i for i, t in enumerate(tenors_order)})
        df = df.sort_values("order")
        fig.add_trace(
            go.Scatter(
                x=df["tenor"], y=df["value"],
                mode="lines+markers", name=label,
                line=dict(color=color, width=2.2),
                marker=dict(size=7),
            )
        )

    fig.update_xaxes(
        title="", categoryorder="array", categoryarray=tenors_order, showgrid=False,
    )
    fig.update_yaxes(
        title="Yield (%)", gridcolor="#EEEEEE", ticksuffix="%",
    )
    fig.update_layout(
        title=dict(
            text=f"<b>Fase 1 USA — Curva UST · 3 cortes</b>",
            font=dict(size=18, color=COLORS["primary"]),
        ),
        height=520,
        legend=dict(orientation="h", y=-0.12),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# LAMINA 5 — Tres lecturas de expectativas Fed
# ---------------------------------------------------------------------------
def lamina_5_tres_lecturas(store: MasterStore, as_of: date) -> go.Figure:
    """Implied path (SR3) + Modelo Mercantil Pieza A + (placeholder FedWatch + Pieza B)."""
    pred = compute_implied_path(store, as_of)
    horizontes = [0, 1, 3, 6, 12, 24]
    valores_mercantil = [
        pred.fed_funds_now,
        pred.forecast_1m,
        pred.forecast_3m,
        pred.forecast_6m,
        pred.forecast_12m,
        pred.forecast_24m,
    ]

    # Implied puro = mismo Pieza A v0.1.0 (sin risk premium); diferenciables en v0.2+.
    fig = go.Figure()

    # Linea implied / Mercantil v0.1
    fig.add_trace(
        go.Scatter(
            x=horizontes, y=valores_mercantil, mode="lines+markers",
            name="Modelo Mercantil v0.1 (= Implied path SR3)",
            line=dict(color=COLORS["primary"], width=2.5),
            marker=dict(size=9),
        )
    )

    # Strip de SR3 puro (puntos individuales)
    strip = pred.strip
    fig.add_trace(
        go.Scatter(
            x=[n * 3 for n in strip["n"]],  # contrato n cubre el trimestre n
            y=strip["implied_rate"],
            mode="markers", name=f"Strip {pred.family} (8 contratos)",
            marker=dict(size=12, color=COLORS["accent"], symbol="x"),
        )
    )

    # Linea horizontal Fed Funds actual
    fig.add_hline(
        y=pred.fed_funds_now,
        line=dict(color=COLORS["muted"], dash="dash", width=1),
        annotation_text=f"Fed Funds actual: {pred.fed_funds_now:.2f}%",
        annotation_position="bottom left",
    )

    # Placeholders para FedWatch + Pieza B
    fig.add_annotation(
        x=12, y=valores_mercantil[4] - 0.4,
        text="<i>FedWatch implícito + Taylor rule llegan en v0.2 y v0.3</i>",
        showarrow=False,
        font=dict(size=10, color=COLORS["muted"]),
    )

    fig.update_xaxes(
        title="Horizonte (meses)",
        tickmode="array", tickvals=[0, 3, 6, 9, 12, 15, 18, 21, 24],
        ticktext=["Hoy", "3M", "6M", "9M", "12M", "15M", "18M", "21M", "24M"],
        gridcolor="#EEEEEE",
    )
    fig.update_yaxes(title="Tasa esperada (%)", gridcolor="#EEEEEE", ticksuffix="%")
    fig.update_layout(
        title=dict(
            text=f"<b>Fase 1 USA — Expectativas Fed: 3 lecturas (v0.1)</b><br>"
                 f"<span style='font-size:13px;color:{COLORS['muted']}'>"
                 f"Lectura del mercado vs modelo propio</span>",
            font=dict(size=18, color=COLORS["primary"]),
        ),
        height=520,
        legend=dict(orientation="h", y=-0.15),
        **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Render runner
# ---------------------------------------------------------------------------
def render_all(store: MasterStore, as_of: date, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    figs_dir = out_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    laminas = {
        "lamina_3_politica_y_mercado": lamina_3_politica_y_mercado(store, as_of),
        "lamina_4_curva_ust":          lamina_4_curva_ust(store, as_of),
        "lamina_5_tres_lecturas":      lamina_5_tres_lecturas(store, as_of),
    }

    paths = {}
    for name, fig in laminas.items():
        html_path = out_dir / f"{name}.html"
        png_path = figs_dir / f"{name}.png"
        pio.write_html(fig, html_path, include_plotlyjs="cdn", full_html=True)
        try:
            pio.write_image(fig, png_path, width=1280, height=720)
            paths[name] = {"html": html_path, "png": png_path}
        except Exception as e:
            paths[name] = {"html": html_path, "png_err": str(e)}

    # Index simple
    index_html = out_dir / "index.html"
    body = "<br>".join([
        f'<h2>{name}</h2><iframe src="{name}.html" width="100%" height="780" frameborder="0"></iframe>'
        for name in laminas
    ])
    index_html.write_text(
        f"<!DOCTYPE html><html><head>"
        f'<meta charset="utf-8"><meta name="robots" content="noindex">'
        f"<title>Tasas Mercantil — Borrador {as_of.strftime('%b %Y')}</title>"
        f'<style>body{{font-family:Helvetica,Arial,sans-serif;max-width:1280px;margin:24px auto;color:#222}}'
        f'h1{{color:{COLORS["primary"]}}}h2{{color:{COLORS["primary"]};border-bottom:1px solid #ddd;padding-bottom:6px}}</style>'
        f'</head><body><h1>Tasas Mercantil · borrador {as_of.strftime("%b %Y")}</h1>'
        f"<p><i>Render v0.1 con Pieza A baseline. Falta FedWatch (v0.2) y Pieza B Taylor rule (v0.3).</i></p>"
        f"{body}</body></html>"
    )
    paths["index"] = index_html
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    ap.add_argument("--corte", required=True, help="YYYY-MM")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: ProyectoTasasMercantil/cortes/<corte>/output/",
    )
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of)
    out_dir = args.out_dir or Path("ProyectoTasasMercantil/cortes") / args.corte / "output"

    print(f"Cargando store...")
    store = load_master_store()
    print(f"  {len(store.features)} features, {len(store.df):,} filas")

    print(f"Renderizando deck para as_of={as_of}, corte={args.corte}, out={out_dir}")
    paths = render_all(store, as_of, out_dir)

    print("\n[OK] Outputs:")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
