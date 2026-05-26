"""Genera un sitio estático mobile-friendly en docs/ para GitHub Pages.

Incluye gráficos interactivos Plotly (HTML standalone) + texto de conclusiones.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.analytics.curves import (  # noqa: E402
    BUCKET_MIDPOINTS,
    BUCKET_ORDER,
    INSTR_GROUPS,
    con,
    cross_ref_matrix,
    latest_curve,
    monthly_yields,
    percentile_position,
    percentile_position_spread,
    quarterly_yields,
    universe_summary,
    ust_monthly,
)
from src.analytics.ratings import TIER_DESC, TIER_ORDER  # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)
ASSETS = DOCS / "assets"
ASSETS.mkdir(exist_ok=True)

PLOTLY_VERSION = get_plotlyjs_version()
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-{PLOTLY_VERSION}.min.js"

# URL de la app Streamlit cuando esté deployada en share.streamlit.io.
# Edita este valor o pásalo por env var STREAMLIT_APP_URL.
import os as _os
STREAMLIT_APP_URL = _os.environ.get(
    "STREAMLIT_APP_URL",
    "https://creditopanama-de6cpxaxkjphqlh8xgnx2x.streamlit.app",
).strip()


def fig_html(fig: go.Figure, div_id: str) -> str:
    """Renderiza fig a HTML usando Plotly CDN compartido (más liviano)."""
    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
        config={"responsive": True, "displaylogo": False},
    )


def style_fig(fig: go.Figure, *, title: str | None = None, ylabel: str = "Yield (%)") -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        title=title,
        margin=dict(l=10, r=10, t=50, b=10),
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0),
        yaxis_title=ylabel,
        xaxis_title=None,
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )
    return fig


# -------------------------------------------------------------------------- #
def build_curva_actual(c, window_days: int = 90) -> tuple[go.Figure, pd.DataFrame]:
    df = latest_curve(c, window_days=window_days)
    df = df[df["instrumento_clase"].isin(sum(INSTR_GROUPS.values(), []))]
    df["instr_group"] = df["instrumento_clase"].map(
        {v: k for k, vs in INSTR_GROUPS.items() for v in vs}
    )
    g = (
        df.groupby(["instr_group", "bucket_plazo"], observed=True)
        .agg(yld=("yld", "median"), n=("n", "sum"))
        .reset_index()
    )
    g["x_years"] = g["bucket_plazo"].map(BUCKET_MIDPOINTS)
    g["yld_pct"] = g["yld"] * 100
    g = g.sort_values("x_years")

    fig = px.line(
        g,
        x="x_years",
        y="yld_pct",
        color="instr_group",
        markers=True,
        hover_data={"bucket_plazo": True, "n": True, "yld_pct": ":.2f", "x_years": False},
        labels={"x_years": "Plazo residual (años)", "yld_pct": "Yield mediano (%)", "instr_group": "Tipo"},
    )
    style_fig(fig, title=f"Curva actual por tipo de instrumento (últimos {window_days} días)")
    return fig, g


def build_serie_tesoro(c) -> tuple[go.Figure, pd.DataFrame]:
    m = quarterly_yields(c)
    tesoro = m[m["instrumento_clase"].isin(INSTR_GROUPS["Tesoro Panamá"])].copy()
    pivot = tesoro.pivot_table(
        index="quarter_dt", columns="bucket_plazo", values="yld_median", aggfunc="median"
    ).reset_index()
    # Order columns
    cols = [b for b in BUCKET_ORDER if b in pivot.columns]
    pivot = pivot[["quarter_dt"] + cols]
    long = pivot.melt(id_vars="quarter_dt", var_name="bucket", value_name="yld")
    long = long.dropna()
    long["yld_pct"] = long["yld"] * 100

    fig = px.line(
        long,
        x="quarter_dt",
        y="yld_pct",
        color="bucket",
        category_orders={"bucket": BUCKET_ORDER},
        markers=True,
        labels={"quarter_dt": "Trimestre", "yld_pct": "Yield (%)", "bucket": "Plazo"},
    )
    style_fig(fig, title="Tesoro Panamá — yield mediano trimestral por bucket de plazo")
    return fig, long


def build_serie_sectores(c) -> tuple[go.Figure, pd.DataFrame]:
    q = quarterly_yields(c)
    foco = q[q["instrumento_clase"].isin(["BONOS", "VALORES COMERCIALES NEGOCIABLES", "BONOS HIPOTECARIOS"])]
    # Agrupar por sector (todo bucket)
    agg = (
        foco.groupby(["quarter_dt", "sector"], observed=True)
        .apply(lambda g: pd.Series({"yld": (g["yld_median"] * g["n"]).sum() / g["n"].sum(), "n": g["n"].sum()}))
        .reset_index()
    )
    # Top 8 sectores por volumen acumulado de trades
    top_sec = (
        agg.groupby("sector")["n"].sum().sort_values(ascending=False).head(8).index.tolist()
    )
    agg = agg[agg["sector"].isin(top_sec)]
    agg["yld_pct"] = agg["yld"] * 100

    fig = px.line(
        agg,
        x="quarter_dt",
        y="yld_pct",
        color="sector",
        markers=True,
        labels={"quarter_dt": "Trimestre", "yld_pct": "Yield (%)", "sector": "Sector"},
    )
    style_fig(fig, title="Yield trimestral por sector (top 8 por liquidez)")
    return fig, agg


def build_spread_vs_ust(c) -> tuple[go.Figure, pd.DataFrame]:
    """Spread del Tesoro Panamá vs UST equivalente (10y bucket)."""
    q = quarterly_yields(c)
    tesoro = q[q["instrumento_clase"].isin(INSTR_GROUPS["Tesoro Panamá"]) & (q["bucket_plazo"] == "7-10y")]
    tesoro = (
        tesoro.groupby("quarter_dt")
        .apply(lambda g: pd.Series({"yld": (g["yld_median"] * g["n"]).sum() / g["n"].sum()}))
        .reset_index()
    )

    ust = ust_monthly(c)
    ust["quarter_dt"] = ust["month_dt"].dt.to_period("Q").dt.to_timestamp()
    ust_q = ust.groupby("quarter_dt", as_index=False)["BC_10Y"].mean()
    ust_q["yld_ust"] = ust_q["BC_10Y"] / 100  # UST está en %, pasarlo a decimal

    m = tesoro.merge(ust_q[["quarter_dt", "yld_ust"]], on="quarter_dt", how="inner")
    m["spread_bp"] = (m["yld"] - m["yld_ust"]) * 10000

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m["quarter_dt"], y=m["yld"] * 100, name="Tesoro Panamá 10y", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=m["quarter_dt"], y=m["yld_ust"] * 100, name="UST 10y", mode="lines+markers"))
    fig.add_trace(
        go.Bar(
            x=m["quarter_dt"],
            y=m["spread_bp"],
            name="Spread (bp)",
            yaxis="y2",
            marker_color="rgba(150,150,150,0.4)",
        )
    )
    fig.update_layout(
        template="plotly_white",
        title="Spread Tesoro Panamá 10y vs UST 10y (pb)",
        yaxis=dict(title="Yield (%)"),
        yaxis2=dict(title="Spread (pb)", overlaying="y", side="right", showgrid=False),
        margin=dict(l=10, r=10, t=50, b=10),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )
    return fig, m


def build_percentil_actual(c) -> tuple[go.Figure, pd.DataFrame]:
    """Posición del yield actual vs distribución últimos 5y."""
    df = percentile_position(c, lookback_days=1825)
    if df.empty:
        return go.Figure(), df

    # Computar percentil del yield actual dentro de la distribución
    def pos(row):
        # interpolación lineal entre p10, p25, p50, p75, p90
        breaks = [0.10, 0.25, 0.50, 0.75, 0.90]
        vals = [row["p10"], row["p25"], row["p50"], row["p75"], row["p90"]]
        y = row["yld_now"]
        if y <= vals[0]:
            return 0.05
        if y >= vals[-1]:
            return 0.95
        for i in range(len(vals) - 1):
            if vals[i] <= y <= vals[i + 1]:
                frac = (y - vals[i]) / (vals[i + 1] - vals[i]) if vals[i + 1] != vals[i] else 0
                return breaks[i] + frac * (breaks[i + 1] - breaks[i])
        return 0.5

    df["percentil"] = df.apply(pos, axis=1)
    df["yld_now_pct"] = df["yld_now"] * 100
    df["p50_pct"] = df["p50"] * 100
    df["label"] = df["instrumento_clase"].str.replace("VALORES COMERCIALES NEGOCIABLES", "VCN") + " " + df["bucket_plazo"].astype(str)

    df = df.sort_values("percentil")

    fig = px.bar(
        df,
        x="percentil",
        y="label",
        color="percentil",
        color_continuous_scale="RdYlGn",
        range_color=[0, 1],
        orientation="h",
        hover_data={"yld_now_pct": ":.2f", "p50_pct": ":.2f", "n_hist": True, "percentil": ":.0%"},
        labels={"percentil": "Percentil vs últimos 5 años", "label": ""},
    )
    fig.add_vline(x=0.5, line_dash="dash", line_color="gray")
    style_fig(fig, title="¿Dónde está el yield actual vs su historia 5y? (verde = barato, rojo = caro)", ylabel="")
    fig.update_layout(height=max(400, 22 * len(df)), coloraxis_showscale=False)
    return fig, df


def build_dispersion_actual(c) -> tuple[go.Figure, pd.DataFrame]:
    """Scatter plazo residual vs yield para todos los trades recientes."""
    q = """
    SELECT fecha_d, nemotecnico, emisor, sector, instrumento_clase, plazo_residual_anos, ytm_calc, monto
    FROM trades
    WHERE ytm_calc BETWEEN 0.005 AND 0.30
      AND plazo_residual_anos BETWEEN 0 AND 25
      AND es_tasa_fija = TRUE
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '180' DAY FROM trades)
    """
    df = c.execute(q).df()
    df["yld_pct"] = df["ytm_calc"] * 100
    fig = px.scatter(
        df,
        x="plazo_residual_anos",
        y="yld_pct",
        color="instrumento_clase",
        size="monto",
        size_max=20,
        opacity=0.65,
        hover_data={"nemotecnico": True, "emisor": True, "sector": True, "fecha_d": True, "yld_pct": ":.2f"},
        labels={"plazo_residual_anos": "Plazo residual (años)", "yld_pct": "YTM (%)", "instrumento_clase": "Instrumento"},
    )
    style_fig(fig, title="Universo de trades (últimos 180 días) — yield vs plazo")
    fig.update_layout(height=520)
    return fig, df


def build_volumen(c) -> tuple[go.Figure, pd.DataFrame]:
    q = """
    SELECT year, SUM(monto) volumen
    FROM trades
    WHERE year IS NOT NULL AND monto IS NOT NULL
    GROUP BY 1 ORDER BY 1
    """
    df = c.execute(q).df()
    df["volumen_b"] = df["volumen"] / 1e9
    fig = px.bar(df, x="year", y="volumen_b", labels={"year": "Año", "volumen_b": "USD miles de millones"})
    style_fig(fig, title="Volumen anual negociado (USD billones)", ylabel="USD bn")
    return fig, df


# ====================== SECCIÓN BANCOS ======================================= #
def _compute_percentile_position(df: pd.DataFrame, val_col: str) -> pd.DataFrame:
    """Calcula columna 'percentil' por interpolación lineal entre p10..p90."""
    out = df.copy()
    breaks = [0.10, 0.25, 0.50, 0.75, 0.90]
    p_cols = ["p10", "p25", "p50", "p75", "p90"]

    def pos(row):
        vals = [row[c] for c in p_cols]
        y = row[val_col]
        if y <= vals[0]:
            return 0.05
        if y >= vals[-1]:
            return 0.95
        for i in range(len(vals) - 1):
            if vals[i] <= y <= vals[i + 1]:
                denom = vals[i + 1] - vals[i]
                frac = (y - vals[i]) / denom if denom != 0 else 0
                return breaks[i] + frac * (breaks[i + 1] - breaks[i])
        return 0.5

    out["percentil"] = out.apply(pos, axis=1)
    return out


def build_curva_bancos_por_tier(c, window_days: int = 90) -> tuple[go.Figure, pd.DataFrame]:
    """Curva yield del sector Financiero separada por rating tier."""
    q = f"""
    SELECT rating_tier, bucket_plazo,
           COUNT(*) n,
           MEDIAN(ytm_calc) yld,
           MEDIAN(spread_bp) spread
    FROM trades
    WHERE sector = 'Financiero'
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN 0.005 AND 0.4
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{window_days}' DAY FROM trades)
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    """
    df = c.execute(q).df()
    df["x_years"] = df["bucket_plazo"].map(BUCKET_MIDPOINTS)
    df["yld_pct"] = df["yld"] * 100
    df = df.dropna(subset=["x_years"]).sort_values(["rating_tier", "x_years"])

    fig = px.line(
        df,
        x="x_years",
        y="yld_pct",
        color="rating_tier",
        category_orders={"rating_tier": TIER_ORDER},
        markers=True,
        hover_data={"bucket_plazo": True, "n": True, "yld_pct": ":.2f", "spread": ":.0f", "x_years": False},
        labels={
            "x_years": "Plazo residual (años)",
            "yld_pct": "Yield mediano (%)",
            "rating_tier": "Rating tier",
            "spread": "Spread (pb)",
        },
    )
    style_fig(fig, title=f"Sector bancario — curva por tier de calificación (últimos {window_days} días)")
    return fig, df


def build_spread_percentil_bancos(c) -> tuple[go.Figure, pd.DataFrame]:
    """Versión SPREAD del gráfico 7: percentil 5y por (rating_tier × bucket) en bancos."""
    df = percentile_position_spread(c, sector="Financiero", by="rating_tier")
    if df.empty:
        return go.Figure(), df
    df = _compute_percentile_position(df, "spread_now")
    df["label"] = df["rating_tier"] + " · " + df["bucket_plazo"].astype(str)
    df = df.sort_values("percentil")
    fig = px.bar(
        df,
        x="percentil",
        y="label",
        color="percentil",
        color_continuous_scale="RdYlGn",
        range_color=[0, 1],
        orientation="h",
        hover_data={
            "spread_now": ":.0f",
            "p50": ":.0f",
            "p25": ":.0f",
            "p75": ":.0f",
            "n_hist": True,
            "percentil": ":.0%",
        },
        labels={
            "percentil": "Percentil del SPREAD vs últimos 5 años",
            "label": "Rating × Plazo",
            "spread_now": "Spread actual (pb)",
            "p50": "Mediana 5y (pb)",
        },
    )
    fig.add_vline(x=0.5, line_dash="dash", line_color="gray")
    style_fig(fig, title="Bancos — percentil del SPREAD vs Tesoro (verde = barato, rojo = caro)", ylabel="")
    fig.update_layout(height=max(380, 26 * len(df)), coloraxis_showscale=False)
    return fig, df


def build_spread_percentil_instrumento_bancos(c) -> tuple[go.Figure, pd.DataFrame]:
    """Mismo gráfico pero por (instrumento × bucket) dentro de bancos — útil para ver
    Bonos Hipotecarios vs VCN vs Bonos corporativos por separado."""
    df = percentile_position_spread(c, sector="Financiero", by="instrumento_clase")
    if df.empty:
        return go.Figure(), df
    df = _compute_percentile_position(df, "spread_now")
    df["label"] = (
        df["instrumento_clase"].str.replace("VALORES COMERCIALES NEGOCIABLES", "VCN")
        + " · " + df["bucket_plazo"].astype(str)
    )
    df = df.sort_values("percentil")
    fig = px.bar(
        df, x="percentil", y="label", color="percentil",
        color_continuous_scale="RdYlGn", range_color=[0, 1], orientation="h",
        hover_data={"spread_now": ":.0f", "p50": ":.0f", "n_hist": True, "percentil": ":.0%"},
        labels={"percentil": "Percentil del SPREAD vs 5y", "label": ""},
    )
    fig.add_vline(x=0.5, line_dash="dash", line_color="gray")
    style_fig(fig, title="Bancos — percentil del SPREAD por instrumento × plazo", ylabel="")
    fig.update_layout(height=max(380, 26 * len(df)), coloraxis_showscale=False)
    return fig, df


def build_heatmap_cross_ref(c) -> tuple[go.Figure, go.Figure, pd.DataFrame]:
    """Dos heatmaps en bancos: (1) spread actual y (2) percentil 5y, ambos por
    rating_tier × bucket_plazo."""
    df = cross_ref_matrix(c, lookback_days=90)
    if df.empty:
        return go.Figure(), go.Figure(), df

    # Spread con percentil
    perc = percentile_position_spread(c, sector="Financiero", by="rating_tier")
    perc = _compute_percentile_position(perc, "spread_now")
    df = df.merge(
        perc[["rating_tier", "bucket_plazo", "percentil", "p50", "n_hist"]],
        on=["rating_tier", "bucket_plazo"],
        how="left",
    )

    # Pivot para heatmap de spread
    sp_pivot = df.pivot(index="rating_tier", columns="bucket_plazo", values="spread")
    sp_pivot = sp_pivot.reindex(TIER_ORDER)
    sp_pivot = sp_pivot[[b for b in BUCKET_ORDER if b in sp_pivot.columns]]

    fig_sp = go.Figure(
        data=go.Heatmap(
            z=sp_pivot.values,
            x=sp_pivot.columns,
            y=sp_pivot.index,
            colorscale="YlOrRd",
            text=[[f"{v:.0f} pb" if pd.notna(v) else "" for v in row] for row in sp_pivot.values],
            texttemplate="%{text}",
            hovertemplate="Tier %{y} · %{x}<br>Spread: %{z:.0f} pb<extra></extra>",
            colorbar=dict(title="pb"),
        )
    )
    fig_sp.update_layout(
        template="plotly_white",
        title="Spread actual (pb) — sector bancario · rating × plazo",
        margin=dict(l=10, r=10, t=50, b=10),
        height=380,
        xaxis_title="Bucket de plazo",
        yaxis_title="Rating tier",
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )

    # Pivot percentil
    pc_pivot = df.pivot(index="rating_tier", columns="bucket_plazo", values="percentil")
    pc_pivot = pc_pivot.reindex(TIER_ORDER)
    pc_pivot = pc_pivot[[b for b in BUCKET_ORDER if b in pc_pivot.columns]]

    fig_pc = go.Figure(
        data=go.Heatmap(
            z=pc_pivot.values,
            x=pc_pivot.columns,
            y=pc_pivot.index,
            colorscale="RdYlGn",
            zmin=0, zmax=1,
            text=[[f"{v*100:.0f}%" if pd.notna(v) else "" for v in row] for row in pc_pivot.values],
            texttemplate="%{text}",
            hovertemplate="Tier %{y} · %{x}<br>Percentil 5y: %{z:.0%}<extra></extra>",
            colorbar=dict(title="%ile", tickformat=".0%"),
        )
    )
    fig_pc.update_layout(
        template="plotly_white",
        title="Percentil del SPREAD vs 5y — sector bancario (verde = barato)",
        margin=dict(l=10, r=10, t=50, b=10),
        height=380,
        xaxis_title="Bucket de plazo",
        yaxis_title="Rating tier",
        font=dict(family="-apple-system, system-ui, sans-serif", size=12),
    )

    return fig_sp, fig_pc, df


def build_serie_bancos_por_tier(c) -> tuple[go.Figure, pd.DataFrame]:
    """Evolución trimestral del spread por rating tier (sector Financiero)."""
    q = """
    SELECT DATE_TRUNC('quarter', fecha_d) AS quarter_dt,
           rating_tier,
           MEDIAN(spread_bp) spread,
           COUNT(*) n
    FROM trades
    WHERE sector = 'Financiero'
      AND es_tasa_fija = TRUE
      AND spread_bp IS NOT NULL
      AND spread_bp BETWEEN -200 AND 3000
    GROUP BY 1, 2
    HAVING COUNT(*) >= 5
    """
    df = c.execute(q).df()
    fig = px.line(
        df,
        x="quarter_dt", y="spread", color="rating_tier",
        category_orders={"rating_tier": TIER_ORDER},
        markers=True,
        labels={"quarter_dt": "Trimestre", "spread": "Spread (pb)", "rating_tier": "Rating"},
    )
    style_fig(fig, title="Bancos — evolución trimestral del spread mediano por rating tier", ylabel="Spread (pb)")
    return fig, df


# -------------------------------------------------------------------------- #
def derive_conclusions_bancos(curva_tier: pd.DataFrame, heat: pd.DataFrame) -> list[str]:
    """Conclusiones específicas del sector bancario."""
    out = []
    if not curva_tier.empty:
        for tier in ["T1", "T2", "T3", "T4", "T5"]:
            sub = curva_tier[curva_tier["rating_tier"] == tier]
            if not sub.empty:
                yld = sub["yld_pct"].mean()
                sp = sub["spread"].dropna().mean()
                out.append(
                    f"**{tier}** ({TIER_DESC[tier].split(' — ')[0]}): yield medio {yld:.2f}%"
                    + (f", spread medio ~{sp:.0f} pb sobre Tesoro" if pd.notna(sp) else "")
                    + f" (n={int(sub['n'].sum())} trades)."
                )
    if not heat.empty:
        h = heat.dropna(subset=["percentil"])
        if not h.empty:
            barato = h.sort_values("percentil", ascending=False).head(1).iloc[0]
            caro = h.sort_values("percentil", ascending=True).head(1).iloc[0]
            out.append(
                f"**Más barato en bancos vs su historia 5y**: {barato['rating_tier']} · {barato['bucket_plazo']} "
                f"— spread {barato['spread']:.0f} pb vs mediana 5y {barato['p50']:.0f} pb "
                f"(percentil {barato['percentil']*100:.0f})."
            )
            out.append(
                f"**Más caro en bancos vs su historia 5y**: {caro['rating_tier']} · {caro['bucket_plazo']} "
                f"— spread {caro['spread']:.0f} pb vs mediana 5y {caro['p50']:.0f} pb "
                f"(percentil {caro['percentil']*100:.0f})."
            )
    return out


# -------------------------------------------------------------------------- #
def derive_conclusions(curva: pd.DataFrame, perc: pd.DataFrame, spread: pd.DataFrame) -> list[str]:
    conclusions = []

    # Conclusión 1: Empinamiento curva tesoro
    tesoro_curva = curva[curva["instr_group"] == "Tesoro Panamá"]
    if len(tesoro_curva) >= 2:
        short = tesoro_curva[tesoro_curva["bucket_plazo"].isin(["0-1y", "1-3y"])]["yld_pct"].mean()
        long_ = tesoro_curva[tesoro_curva["bucket_plazo"].isin(["7-10y", "10y+"])]["yld_pct"].mean()
        slope = long_ - short
        if not pd.isna(slope):
            conclusions.append(
                f"**Pendiente Tesoro Panamá**: la curva está empinada en {slope*100:.0f} pb entre 0-3y y 7y+ "
                f"(corto {short:.2f}% vs largo {long_:.2f}%)."
            )

    # Conclusión 2: VCN vs Letras
    vcn = curva[(curva["instr_group"] == "VCN") & (curva["bucket_plazo"] == "0-1y")]
    letras = curva[(curva["instr_group"] == "Tesoro Panamá") & (curva["bucket_plazo"] == "0-1y")]
    if not vcn.empty and not letras.empty:
        prima = (vcn["yld_pct"].mean() - letras["yld_pct"].mean()) * 100
        conclusions.append(
            f"**Prima VCN vs Letras del Tesoro (0-1y)**: {prima:.0f} pb "
            f"(VCN {vcn['yld_pct'].mean():.2f}% vs Letras {letras['yld_pct'].mean():.2f}%)."
        )

    # Conclusión 3: Hipotecarios premium
    hip = curva[curva["instr_group"] == "Bonos Hipotecarios"]
    tesoro_mean = curva[curva["instr_group"] == "Tesoro Panamá"]["yld_pct"].mean()
    if not hip.empty and not pd.isna(tesoro_mean):
        prima_hip_pb = (hip["yld_pct"].mean() - tesoro_mean) * 100
        conclusions.append(
            f"**Bonos Hipotecarios**: yield mediano {hip['yld_pct'].mean():.2f}% "
            f"— prima de ~{prima_hip_pb:.0f} pb sobre Tesoro Panamá."
        )

    # Conclusión 4: Spread soberano vs UST
    if not spread.empty:
        last = spread.iloc[-1]
        hist_med = spread["spread_bp"].median()
        conclusions.append(
            f"**Spread Panamá 10y vs UST 10y**: {last['spread_bp']:.0f} pb hoy "
            f"vs mediana histórica {hist_med:.0f} pb "
            f"({'AMPLIADO' if last['spread_bp'] > hist_med else 'COMPRIMIDO'} vs media)."
        )

    # Conclusión 5: Percentil
    if not perc.empty:
        ricos = perc[perc["percentil"] <= 0.25]
        baratos = perc[perc["percentil"] >= 0.75]
        if not baratos.empty:
            top_barato = baratos.iloc[-1]
            conclusions.append(
                f"**Más barato vs su historia 5y**: {top_barato['label']} "
                f"en percentil {top_barato['percentil']*100:.0f} "
                f"({top_barato['yld_now_pct']:.2f}% vs mediana 5y {top_barato['p50_pct']:.2f}%)."
            )
        if not ricos.empty:
            top_rico = ricos.iloc[0]
            conclusions.append(
                f"**Más caro vs su historia 5y**: {top_rico['label']} "
                f"en percentil {top_rico['percentil']*100:.0f} "
                f"({top_rico['yld_now_pct']:.2f}% vs mediana 5y {top_rico['p50_pct']:.2f}%)."
            )

    return conclusions


# -------------------------------------------------------------------------- #
PAGE_TPL = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<script src="{plotly_cdn}"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #fafbfc; color: #1a1a2e; line-height: 1.55;
  }}
  header {{
    background: linear-gradient(135deg, #002b5c 0%, #004080 100%);
    color: #fff; padding: 28px 18px 22px; text-align: center;
  }}
  header h1 {{ margin: 0 0 6px; font-size: 1.45rem; font-weight: 600; }}
  header .sub {{ font-size: 0.85rem; opacity: 0.88; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 18px 14px 60px; }}
  section {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            margin-bottom: 20px; padding: 18px 16px; }}
  section h2 {{ margin: 0 0 8px; font-size: 1.1rem; color: #002b5c; }}
  section p.note {{ font-size: 0.86rem; color: #555; margin: 4px 0 14px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 10px; }}
  .stat {{ background: #f3f5fa; border-radius: 8px; padding: 12px; text-align: center; }}
  .stat .v {{ font-size: 1.25rem; font-weight: 700; color: #002b5c; }}
  .stat .l {{ font-size: 0.78rem; color: #555; margin-top: 2px; }}
  ul.findings li {{ margin: 6px 0; }}
  nav.tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
  nav.tabs a {{
    background: #fff; color: #002b5c; padding: 8px 12px; border-radius: 20px;
    text-decoration: none; font-size: 0.82rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  nav.tabs a.active {{ background: #002b5c; color: #fff; }}
  footer {{ text-align: center; color: #888; font-size: 0.78rem; padding: 30px 10px; }}
  .download {{ background: #002b5c; color: #fff !important; padding: 10px 18px; border-radius: 8px;
              display: inline-block; text-decoration: none; font-weight: 600; }}
  code {{ background: #eef1f7; padding: 2px 5px; border-radius: 4px; font-size: 0.88em; }}
  @media (max-width: 600px) {{
    header h1 {{ font-size: 1.2rem; }}
    section {{ padding: 14px 12px; }}
  }}
</style>
</head>
<body>
<header>
  <h1>Renta Fija de Panamá — Niveles actuales vs historia</h1>
  <div class="sub">Datos Latinex · {snapshot} · Cobertura {date_min} a {date_max}</div>
</header>
<main>
  <nav class="tabs">
    <a href="index.html" class="{cls_home}">Resumen</a>
    <a href="bancos.html" class="{cls_bancos}">Bancos</a>
    <a href="mercantil.html" class="{cls_mercantil}">Mercantil</a>
    <a href="curvas.html" class="{cls_curvas}">Curvas</a>
    <a href="historia.html" class="{cls_historia}">Historia</a>
    <a href="universo.html" class="{cls_universo}">Universo</a>
    <a href="metodologia.html" class="{cls_metod}">Metodología</a>
  </nav>
  {body}
</main>
<footer>
  Fuente: <a href="https://www.latinexbolsa.com">latinexbolsa.com</a> (API JSON pública) · UST: home.treasury.gov · Estudio no constituye recomendación de inversión.
</footer>
</body>
</html>"""


def render_page(slug: str, title: str, body: str, snapshot: str, date_min: str, date_max: str) -> str:
    cls = {k: "" for k in ["home", "bancos", "mercantil", "curvas", "historia", "universo", "metod"]}
    cls[slug] = "active"
    return PAGE_TPL.format(
        title=title,
        snapshot=snapshot,
        date_min=date_min,
        date_max=date_max,
        body=body,
        plotly_cdn=PLOTLY_CDN,
        cls_home=cls["home"],
        cls_bancos=cls["bancos"],
        cls_mercantil=cls["mercantil"],
        cls_curvas=cls["curvas"],
        cls_historia=cls["historia"],
        cls_universo=cls["universo"],
        cls_metod=cls["metod"],
    )


def main():
    c = con()
    summary = universe_summary(c)
    snapshot = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    # === Construir todos los gráficos ===
    print(">> Curva actual...")
    fig_curva, df_curva = build_curva_actual(c)

    print(">> Serie tesoro...")
    fig_tes, df_tes = build_serie_tesoro(c)

    print(">> Serie sectores...")
    fig_sec, df_sec = build_serie_sectores(c)

    print(">> Spread vs UST...")
    fig_sp, df_sp = build_spread_vs_ust(c)

    print(">> Percentil 5y...")
    fig_pc, df_pc = build_percentil_actual(c)

    print(">> Dispersión...")
    fig_disp, df_disp = build_dispersion_actual(c)

    print(">> Volumen...")
    fig_vol, df_vol = build_volumen(c)

    # === Conclusiones ===
    findings = derive_conclusions(df_curva, df_pc, df_sp)

    (DOCS / "_data").mkdir(exist_ok=True)
    df_curva.to_csv(DOCS / "_data" / "curva_actual.csv", index=False)
    df_pc.to_csv(DOCS / "_data" / "percentil_5y.csv", index=False)

    # CSV completo de trades con rating — comprimido para que pese poco
    trades_full = c.execute(
        """
        SELECT fecha_d, nemotecnico, emisor, sector, instrumento_clase,
               rating_tier, rating_proxy,
               plazo_residual_anos, bucket_plazo,
               ytm_calc, spread_bp, precio, nominal, monto,
               cupon_decimal, freq_int, base_days, fechaVencimiento_d
        FROM trades
        WHERE es_tasa_fija = TRUE
        ORDER BY fecha_d DESC
        """
    ).df()
    trades_full.to_csv(DOCS / "_data" / "trades_con_rating.csv.gz", index=False, compression="gzip")

    # CSV de universo de emisiones con rating asignado
    instr_full = c.execute("SELECT * FROM instruments").df()
    # Asignar rating al universo de instrumentos
    from src.analytics.ratings import assign_rating as _ar
    rt = instr_full.apply(
        lambda r: _ar(r.get("emisor"), r.get("sector"), r.get("instrumento")),
        axis=1,
    )
    instr_full["rating_tier"] = rt.apply(lambda x: x[0])
    instr_full["rating_proxy"] = rt.apply(lambda x: x[1])
    instr_full.to_csv(DOCS / "_data" / "instruments_con_rating.csv.gz", index=False, compression="gzip")

    # ============== PAGE 1: HOME / RESUMEN ==============
    stats_html = f"""
    <div class="stats">
      <div class="stat"><div class="v">{summary['n_instruments']:,}</div><div class="l">Emisiones activas</div></div>
      <div class="stat"><div class="v">{summary['n_trades']:,}</div><div class="l">Trades 10y</div></div>
      <div class="stat"><div class="v">{summary['n_ytm']:,}</div><div class="l">YTMs calculados</div></div>
      <div class="stat"><div class="v">{summary['n_emisores']:,}</div><div class="l">Emisores</div></div>
      <div class="stat"><div class="v">{summary['n_sectores']}</div><div class="l">Sectores</div></div>
    </div>
    """
    import re
    def md_to_html(s: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    findings_html = "<ul class='findings'>" + "".join(
        f"<li>{md_to_html(f)}</li>" for f in findings
    ) + "</ul>"

    if STREAMLIT_APP_URL:
        st_block = f"""
    <section style="background:linear-gradient(135deg,#004080 0%,#002b5c 100%);color:#fff;">
      <h2 style="color:#fff;margin-top:0">🛠 Herramienta interactiva</h2>
      <p style="color:#dbe4f3;margin:6px 0 14px;">Filtros cruzados (rating × sector × plazo × emisor × período) y gráficos que se recalculan en vivo.</p>
      <p><a class="download" href="{STREAMLIT_APP_URL}" style="background:#fff;color:#002b5c !important;">Abrir herramienta →</a></p>
    </section>"""
    else:
        st_block = """
    <section style="background:#fff7e6;border-left:4px solid #d18f00;">
      <h2 style="margin-top:0">🛠 Herramienta interactiva (pendiente de deploy)</h2>
      <p class="note">Para activar la app interactiva con filtros cruzados, deploy un click en
      <a href="https://share.streamlit.io">share.streamlit.io</a>: New app → repo
      <code>andresborrerom/credito_Panama</code> → archivo <code>src/app/streamlit_app.py</code>.
      Una vez deployada, exporta <code>STREAMLIT_APP_URL=https://...streamlit.app</code> y vuelve a correr
      <code>python -m src.app.build_site</code> para que este botón quede activo.</p>
    </section>"""

    body_home = f"""
    {st_block}
    <section>
      <h2>Universo</h2>
      <p class="note">Snapshot del estudio sobre la base de datos extraída de Latinex.</p>
      {stats_html}
    </section>
    <section>
      <h2>Hallazgos principales</h2>
      <p class="note">Conclusiones reproducibles desde los filtros de la herramienta. Cada bullet se puede verificar en la pestaña correspondiente.</p>
      {findings_html}
    </section>
    <section>
      <h2>Curva actual</h2>
      <p class="note">Yield mediano por bucket de plazo y tipo de instrumento — últimos 90 días.</p>
      {fig_html(fig_curva, 'fig_curva_home')}
    </section>
    <section>
      <h2>Descargas</h2>
      <p><a class="download" href="estudio_renta_fija_panama.pdf">📄 Bajar PDF del estudio</a></p>
      <h3 style="margin-bottom:6px;font-size:0.95rem">Base de datos completa (con calificación)</h3>
      <ul style="margin-top:4px;font-size:0.88rem">
        <li><a href="_data/trades_con_rating.csv.gz">trades_con_rating.csv.gz</a> — toda la tape de operaciones (84k filas) con tier T1..T5, rating proxy, spread vs Tesoro, YTM, plazo residual, etc.</li>
        <li><a href="_data/instruments_con_rating.csv.gz">instruments_con_rating.csv.gz</a> — universo de 2,573 emisiones vigentes con tier y rating proxy por emisor.</li>
      </ul>
      <h3 style="margin-bottom:6px;font-size:0.95rem">Cortes analíticos</h3>
      <ul style="margin-top:4px;font-size:0.88rem">
        <li><a href="_data/curva_actual.csv">curva_actual.csv</a> · <a href="_data/percentil_5y.csv">percentil_5y.csv</a></li>
        <li><a href="_data/bancos_curva_tier.csv">bancos_curva_tier.csv</a> · <a href="_data/bancos_cross_ref.csv">bancos_cross_ref.csv</a> · <a href="_data/bancos_spread_percentil_tier.csv">bancos_spread_percentil_tier.csv</a></li>
      </ul>
      <p class="note">La base SQLite + Parquet (más eficiente para análisis programático) vive en el repo bajo <code>data/</code>.</p>
    </section>
    """
    (DOCS / "index.html").write_text(
        render_page("home", "Renta Fija Panamá — Resumen", body_home, snapshot, summary["date_min"], summary["date_max"])
    )

    # ============== PAGE 2: CURVAS ==============
    body_curvas = f"""
    <section>
      <h2>Curva por tipo de instrumento</h2>
      <p class="note">Mediana del YTM por bucket de plazo, últimos 90 días. Cada línea agrupa una clase de instrumento.</p>
      {fig_html(fig_curva, 'fig_curva')}
    </section>
    <section>
      <h2>Dispersión actual: yield vs plazo</h2>
      <p class="note">Cada punto es una transacción de los últimos 180 días. Tamaño = monto. Hover muestra emisor y nemotécnico.</p>
      {fig_html(fig_disp, 'fig_disp')}
    </section>
    """
    (DOCS / "curvas.html").write_text(
        render_page("curvas", "Curvas de Rendimiento — Panamá", body_curvas, snapshot, summary["date_min"], summary["date_max"])
    )

    # ============== PAGE 3: HISTORIA ==============
    body_hist = f"""
    <section>
      <h2>Tesoro Panamá — evolución trimestral</h2>
      <p class="note">Yield mediano trimestral por bucket de plazo. Profundidad disminuye en años más antiguos por menor liquidez registrada.</p>
      {fig_html(fig_tes, 'fig_tes')}
    </section>
    <section>
      <h2>Yield por sector — evolución trimestral</h2>
      <p class="note">Promedio ponderado por liquidez de bonos corporativos, hipotecarios y VCN por sector.</p>
      {fig_html(fig_sec, 'fig_sec')}
    </section>
    <section>
      <h2>Spread soberano vs UST 10y</h2>
      <p class="note">Diferencia trimestral entre el Tesoro Panamá 7-10y y el UST 10y. Mide el spread país soberano dolarizado.</p>
      {fig_html(fig_sp, 'fig_sp')}
    </section>
    <section>
      <h2>Volumen negociado anual</h2>
      {fig_html(fig_vol, 'fig_vol')}
    </section>
    """
    (DOCS / "historia.html").write_text(
        render_page("historia", "Historia — Renta Fija Panamá", body_hist, snapshot, summary["date_min"], summary["date_max"])
    )

    # ============== PAGE 4: UNIVERSO + PERCENTIL ==============
    body_univ = f"""
    <section>
      <h2>¿Dónde están los yields vs su historia 5y?</h2>
      <p class="note">Cada barra es un (instrumento × bucket de plazo). Percentil ALTO (verde) = yield negociado hoy es alto vs su historia 5y → bono BARATO. Percentil BAJO (rojo) = yield comprimido → bono CARO.</p>
      {fig_html(fig_pc, 'fig_pc')}
    </section>
    <section>
      <h2>Top emisores activos por monto colocado</h2>
      <p class="note">Universo de instrumentos vigentes — agregado por emisor.</p>
      <div id="top_emisores"></div>
    </section>
    """
    top_em = c.execute(
        """
        SELECT emisor, sector, COUNT(*) n_emisiones,
               ROUND(SUM(montoColocado)/1e6, 1) monto_mm,
               ROUND(AVG(cupon_decimal)*100, 2) avg_cupon
        FROM instruments
        WHERE montoColocado IS NOT NULL
        GROUP BY 1, 2
        ORDER BY monto_mm DESC NULLS LAST
        LIMIT 25
        """
    ).df()
    top_em_html = top_em.to_html(index=False, classes="dataframe", float_format=lambda x: f"{x:,.2f}")
    body_univ = body_univ.replace('<div id="top_emisores"></div>', top_em_html)
    body_univ += """
    <style>
      .dataframe { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
      .dataframe th { background: #002b5c; color: #fff; padding: 6px; text-align: left; }
      .dataframe td { padding: 5px 6px; border-bottom: 1px solid #eee; }
    </style>
    """
    (DOCS / "universo.html").write_text(
        render_page("universo", "Universo de Emisores — Panamá", body_univ, snapshot, summary["date_min"], summary["date_max"])
    )

    # ============== PAGE 5: METODOLOGIA ==============
    body_metod = """
    <section>
      <h2>Cobertura y profundidad</h2>
      <p>La base usa la ventana <b>10 años</b> completa de la API de Latinex. La profundidad por bucket
      no se pierde al ampliar la ventana — lo que pasa es que en los primeros 2–3 años (2017–2019) había
      menos liquidez registrada, especialmente en bonos hipotecarios y notas corporativas. Por eso:</p>
      <ul>
        <li>Curvas <b>actuales</b> se calculan con últimos 90 días.</li>
        <li>Series temporales se agregan a frecuencia trimestral con mínimo 3 trades por celda.</li>
        <li>Percentiles históricos se calculan sobre los últimos 5 años (1,825 días).</li>
      </ul>
    </section>
    <section>
      <h2>Cálculo de YTM</h2>
      <p>Para cada trade de bono a tasa fija con info completa, se reconstruyen los flujos hasta vencimiento
      (cupón × frecuencia + amortización bullet al vencimiento), y se resuelve por bisección la tasa que iguala
      el VP de flujos al precio limpio negociado. Bases soportadas: 30/360, ACT/360, 365/360, ACT/365, ACT/ACT.</p>
    </section>
    <section>
      <h2>Proxy de crédito</h2>
      <p>No tenemos feed de calificaciones licenciado. Construimos un proxy basado en sector + tipo de instrumento:</p>
      <ul>
        <li><b>AAA-PAN-Sov</b>: Bonos del Tesoro, Notas del Tesoro, Letras del Tesoro</li>
        <li><b>BBB-Bank</b>: Sector Financiero</li>
        <li><b>BBB-Corp</b>: Comunicaciones, Energía, Utilidades</li>
        <li><b>BB-Corp</b>: Consumo, Industrial, Servicios, Salud</li>
        <li><b>BB-RealEstate</b>: Bienes Raíces (Bonos Hipotecarios)</li>
      </ul>
      <p>Adicionalmente, el spread negociado vs Tesoro mismo bucket se reporta como medida revealed-market del riesgo.</p>
    </section>
    <section>
      <h2>Limitaciones</h2>
      <ul>
        <li>Precios = transacciones pactadas, no order book continuo — hay ruido en yields individuales. Se mitiga con medianas por bucket.</li>
        <li>Calificaciones públicas reales (Fitch, Moody's, Equilibrium) no se incorporan en esta versión — quedan pendientes.</li>
        <li>Bonos con call/put options se tratan como bullet salvo evidencia desde <code>/pago</code> endpoint.</li>
        <li>Bonos a tasa variable se excluyen de las curvas (no se puede calcular YTM bullet con cupones flotantes futuros sin asumir trayectoria de la tasa de referencia).</li>
        <li>Tasas cupón reportadas en 0% se interpretan como cero-cupón o data missing (revisar caso por caso).</li>
      </ul>
    </section>
    <section>
      <h2>Reproducibilidad</h2>
      <p>El pipeline completo es:</p>
      <ol>
        <li><code>python -m src.etl.extract</code> — descarga raw JSON de Latinex + UST</li>
        <li><code>python -m src.etl.transform</code> — normaliza, calcula YTM, escribe SQLite + Parquet</li>
        <li><code>python -m src.app.build_site</code> — regenera este sitio estático</li>
        <li><code>streamlit run src/app/streamlit_app.py</code> — herramienta interactiva con filtros completos</li>
        <li><code>python -m src.app.build_pdf</code> — genera el PDF descargable</li>
      </ol>
      <p>La base completa está versionada en el repo. Cada vez que se quiera refrescar, basta con re-ejecutar los pasos 1–3.</p>
    </section>
    """
    (DOCS / "metodologia.html").write_text(
        render_page("metod", "Metodología — Renta Fija Panamá", body_metod, snapshot, summary["date_min"], summary["date_max"])
    )

    # ============== PAGE 6: BANCOS ==============
    print(">> Sección bancos...")
    fig_curva_tier, df_curva_tier = build_curva_bancos_por_tier(c)
    fig_perc_sp_tier, df_perc_sp_tier = build_spread_percentil_bancos(c)
    fig_perc_sp_inst, df_perc_sp_inst = build_spread_percentil_instrumento_bancos(c)
    fig_heat_sp, fig_heat_pc, df_heat = build_heatmap_cross_ref(c)
    fig_serie_tier, df_serie_tier = build_serie_bancos_por_tier(c)
    bancos_findings = derive_conclusions_bancos(df_curva_tier, df_heat)

    df_curva_tier.to_csv(DOCS / "_data" / "bancos_curva_tier.csv", index=False)
    df_heat.to_csv(DOCS / "_data" / "bancos_cross_ref.csv", index=False)
    df_perc_sp_tier.to_csv(DOCS / "_data" / "bancos_spread_percentil_tier.csv", index=False)

    tier_legend_html = "<ul style='font-size:0.85rem;color:#555;margin:6px 0 14px;padding-left:18px;'>" + "".join(
        f"<li><b>{t}</b> · {TIER_DESC[t]}</li>" for t in TIER_ORDER
    ) + "</ul>"

    import re as _re

    def _md(s: str) -> str:
        return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

    bancos_findings_html = (
        "<ul class='findings'>" + "".join(f"<li>{_md(f)}</li>" for f in bancos_findings) + "</ul>"
    )

    body_bancos = f"""
    <section>
      <h2>Foco: sector bancario</h2>
      <p class="note">Universo = sector "Financiero" (bancos, hipotecarias, financieras especializadas, fideicomisos). Cada trade se etiqueta con un <b>rating tier</b> proxy basado en mapeo manual + fallback por tipo de emisor. Las calificaciones oficiales pendientes serán cargadas desde Bloomberg.</p>
      {tier_legend_html}
    </section>

    <section>
      <h2>Curva por rating tier</h2>
      <p class="note">Yield mediano por bucket de plazo, separado por tier de calificación. Mismos plazos comparados entre tiers permiten leer el premium de crédito directamente.</p>
      {fig_html(fig_curva_tier, "fig_curva_tier")}
    </section>

    <section>
      <h2>Percentil del SPREAD vs historia 5y — por rating</h2>
      <p class="note">El gráfico de percentiles que te interesó, pero usando <b>spread vs Tesoro Panamá mismo bucket-trimestre</b> en lugar de yield. Aísla el riesgo de crédito del nivel general de tasas. Verde = spread amplio vs su historia → barato. Rojo = spread comprimido → caro.</p>
      {fig_html(fig_perc_sp_tier, "fig_pc_sp_tier")}
    </section>

    <section>
      <h2>Cross-reference: rating × plazo</h2>
      <p class="note">Matriz de doble entrada. Heatmap 1 = spread actual en pb. Heatmap 2 = en qué percentil de su distribución 5y está ese spread (verde = barato vs historia, rojo = caro).</p>
      {fig_html(fig_heat_sp, "fig_heat_sp")}
      {fig_html(fig_heat_pc, "fig_heat_pc")}
    </section>

    <section>
      <h2>Percentil del SPREAD por instrumento × plazo</h2>
      <p class="note">Misma idea pero abriendo por tipo de instrumento (VCN, Bonos Hipotecarios, Bonos Corp.) en lugar de tier. Útil para detectar dónde el premio de plazo se desvía.</p>
      {fig_html(fig_perc_sp_inst, "fig_pc_sp_inst")}
    </section>

    <section>
      <h2>Evolución histórica del spread por rating tier</h2>
      <p class="note">Spread mediano trimestral, sector bancario, separado por tier de calificación. Muestra cómo se mueve el premio de crédito en el tiempo.</p>
      {fig_html(fig_serie_tier, "fig_serie_tier")}
    </section>

    <section>
      <h2>Conclusiones — bancos</h2>
      {bancos_findings_html}
    </section>
    """
    (DOCS / "bancos.html").write_text(
        render_page("bancos", "Bancos — Renta Fija Panamá", body_bancos, snapshot, summary["date_min"], summary["date_max"])
    )

    # Mostrar findings de bancos en consola
    for f in bancos_findings:
        print(f"   [banco] {f}")

    # === GH Pages support files ===
    (DOCS / ".nojekyll").write_text("")
    print(f">> Sitio escrito en {DOCS}")
    print(f">> Páginas: index, curvas, historia, universo, metodologia")
    print(f">> Findings: {len(findings)}")
    for f in findings:
        print(f"   - {f}")


if __name__ == "__main__":
    main()
