"""Streamlit interactivo para uso local — filtros completos.

Ejecutar: streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import pathlib
import sys
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.analytics.curves import BUCKET_MIDPOINTS, BUCKET_ORDER, con, ust_monthly  # noqa: E402
from src.analytics.ratings import TIER_DESC, TIER_ORDER  # noqa: E402

st.set_page_config(page_title="Renta Fija Panamá", layout="wide", page_icon="📊")


@st.cache_resource
def get_con():
    return con()


@st.cache_data
def load_trades() -> pd.DataFrame:
    c = get_con()
    df = c.execute(
        """
        SELECT fecha_d, nemotecnico, emisor, sector, instrumento_clase,
               plazo_residual_anos, bucket_plazo, ytm_calc, precio, monto, es_tasa_fija,
               rating_tier, rating_proxy, spread_bp, quarter
        FROM trades
        WHERE es_tasa_fija = TRUE
          AND ytm_calc BETWEEN 0.005 AND 0.40
          AND plazo_residual_anos BETWEEN 0 AND 30
        """
    ).df()
    # Normalizar fecha a datetime.date (Streamlit slider no acepta pd.Timestamp)
    df["fecha_d"] = pd.to_datetime(df["fecha_d"]).dt.date
    return df


@st.cache_data
def load_instruments() -> pd.DataFrame:
    c = get_con()
    return c.execute("SELECT * FROM instruments").df()


@st.cache_data
def load_ust() -> pd.DataFrame:
    return ust_monthly(get_con())


trades = load_trades()
instruments = load_instruments()

st.title("📊 Renta Fija de Panamá — Niveles actuales vs historia")
st.caption(f"Latinex · {len(trades):,} trades con YTM · ventana {trades['fecha_d'].min()} → {trades['fecha_d'].max()}")

# ============ SIDEBAR ============
with st.sidebar:
    st.header("Filtros")

    foco_bancos = st.checkbox("🏦 Foco: sector bancario (Financiero)", value=False)

    sectores = ["(todos)"] + sorted(trades["sector"].dropna().unique().tolist())
    sector_sel = "Financiero" if foco_bancos else st.selectbox("Sector", sectores)

    instrs = ["(todos)"] + sorted(trades["instrumento_clase"].dropna().unique().tolist())
    instr_sel = st.multiselect("Instrumento", instrs, default=["(todos)"])

    ratings_sel = st.multiselect(
        "Rating tier",
        TIER_ORDER,
        default=TIER_ORDER,
        format_func=lambda t: f"{t} · {TIER_DESC[t].split(' — ')[0]}",
    )

    fmin, fmax = trades["fecha_d"].min(), trades["fecha_d"].max()
    default_start = max(fmin, fmax - timedelta(days=365))
    fecha_range = st.date_input(
        "Rango de fechas",
        value=(default_start, fmax),
        min_value=fmin,
        max_value=fmax,
        format="YYYY-MM-DD",
    )
    # Si el usuario aún no seleccionó las dos fechas, st.date_input devuelve un solo date
    if isinstance(fecha_range, (list, tuple)) and len(fecha_range) == 2:
        fecha_ini, fecha_fin = fecha_range
    else:
        fecha_ini, fecha_fin = default_start, fmax

    buckets = st.multiselect("Buckets de plazo", BUCKET_ORDER, default=BUCKET_ORDER)

    emisores_top = ["(todos)"] + sorted(trades["emisor"].dropna().value_counts().head(50).index.tolist())
    emisor_sel = st.selectbox("Emisor (top 50)", emisores_top)

    with st.expander("Leyenda de rating tiers"):
        for t in TIER_ORDER:
            st.markdown(f"**{t}** · {TIER_DESC[t]}")

# ============ FILTRO ============
df = trades.copy()
df = df[(df["fecha_d"] >= fecha_ini) & (df["fecha_d"] <= fecha_fin)]
if sector_sel != "(todos)":
    df = df[df["sector"] == sector_sel]
if "(todos)" not in instr_sel and instr_sel:
    df = df[df["instrumento_clase"].isin(instr_sel)]
if ratings_sel and len(ratings_sel) < len(TIER_ORDER):
    df = df[df["rating_tier"].isin(ratings_sel)]
if buckets:
    df = df[df["bucket_plazo"].isin(buckets)]
if emisor_sel != "(todos)":
    df = df[df["emisor"] == emisor_sel]

if df.empty:
    st.warning("No hay trades que cumplan los filtros. Ajusta los criterios.")
    st.stop()

# ============ STATS ============
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Trades", f"{len(df):,}")
c2.metric("Yield mediano", f"{df['ytm_calc'].median()*100:.2f}%")
spread_med = df["spread_bp"].dropna().median()
c3.metric("Spread mediano", f"{spread_med:.0f} pb" if pd.notna(spread_med) else "—")
c4.metric("Emisores", f"{df['emisor'].nunique()}")
c5.metric("Volumen USD", f"${df['monto'].sum()/1e6:,.1f}M")

# ============ TABS ============
tab1, tab_sp, tab_cx, tab2, tab3, tab4, tab5 = st.tabs(
    ["Curva", "Spread × Rating", "Cross-ref", "Historia", "Dispersión", "Distribución", "Tabla"]
)

with tab1:
    g = df.groupby("bucket_plazo", observed=True)["ytm_calc"].agg(["median", "count"]).reset_index()
    g["x"] = g["bucket_plazo"].map(BUCKET_MIDPOINTS)
    g["yld_pct"] = g["median"] * 100
    g = g.sort_values("x")
    fig = px.line(
        g, x="x", y="yld_pct", markers=True,
        hover_data={"bucket_plazo": True, "count": True, "yld_pct": ":.2f"},
        labels={"x": "Plazo residual (años)", "yld_pct": "Yield mediano (%)"},
    )
    fig.update_layout(template="plotly_white", height=450)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Yield mediano por bucket bajo los filtros actuales.")

with tab_sp:
    st.markdown("**Percentil del SPREAD vs últimos 5 años, por rating × plazo.** Verde = barato (spread amplio vs historia). Rojo = caro (spread comprimido).")
    # Histórico para distribución 5y
    hist_min = df["fecha_d"].max() - timedelta(days=1825) if not df.empty else None
    full_trades = trades
    if sector_sel != "(todos)":
        full_trades = full_trades[full_trades["sector"] == sector_sel]
    if "(todos)" not in instr_sel and instr_sel:
        full_trades = full_trades[full_trades["instrumento_clase"].isin(instr_sel)]
    if ratings_sel and len(ratings_sel) < len(TIER_ORDER):
        full_trades = full_trades[full_trades["rating_tier"].isin(ratings_sel)]

    hist = full_trades[
        (full_trades["fecha_d"] >= hist_min)
        & full_trades["spread_bp"].between(-200, 3000)
    ].copy()
    curr_window = full_trades[
        (full_trades["fecha_d"] >= full_trades["fecha_d"].max() - timedelta(days=90))
        & full_trades["spread_bp"].between(-200, 3000)
    ].copy()

    if hist.empty or curr_window.empty:
        st.info("No hay suficientes trades con spread bajo los filtros.")
    else:
        cur_agg = (
            curr_window.groupby(["rating_tier", "bucket_plazo"], observed=True)["spread_bp"]
            .median().reset_index().rename(columns={"spread_bp": "spread_now"})
        )
        hist_agg = (
            hist.groupby(["rating_tier", "bucket_plazo"], observed=True)["spread_bp"]
            .agg(
                p10=lambda s: s.quantile(0.10),
                p25=lambda s: s.quantile(0.25),
                p50=lambda s: s.quantile(0.50),
                p75=lambda s: s.quantile(0.75),
                p90=lambda s: s.quantile(0.90),
                n_hist="count",
            ).reset_index()
        )
        merged = cur_agg.merge(hist_agg, on=["rating_tier", "bucket_plazo"])
        merged = merged[merged["n_hist"] >= 20]

        if merged.empty:
            st.info("No hay celdas con suficiente historia (n>=20).")
        else:
            def _pos(row):
                breaks = [0.10, 0.25, 0.50, 0.75, 0.90]
                vals = [row["p10"], row["p25"], row["p50"], row["p75"], row["p90"]]
                y = row["spread_now"]
                if y <= vals[0]: return 0.05
                if y >= vals[-1]: return 0.95
                for i in range(4):
                    if vals[i] <= y <= vals[i+1]:
                        denom = vals[i+1] - vals[i]
                        frac = (y - vals[i]) / denom if denom else 0
                        return breaks[i] + frac * (breaks[i+1] - breaks[i])
                return 0.5
            merged["percentil"] = merged.apply(_pos, axis=1)
            merged["label"] = merged["rating_tier"] + " · " + merged["bucket_plazo"].astype(str)
            merged = merged.sort_values("percentil")

            fig = px.bar(
                merged, x="percentil", y="label", color="percentil",
                color_continuous_scale="RdYlGn", range_color=[0, 1], orientation="h",
                hover_data={"spread_now": ":.0f", "p50": ":.0f", "p25": ":.0f", "p75": ":.0f", "n_hist": True, "percentil": ":.0%"},
            )
            fig.add_vline(x=0.5, line_dash="dash", line_color="gray")
            fig.update_layout(template="plotly_white", height=max(380, 30 * len(merged)),
                              coloraxis_showscale=False, yaxis_title="", xaxis_title="Percentil 5y")
            st.plotly_chart(fig, use_container_width=True)

with tab_cx:
    st.markdown("**Cross-reference rating × plazo.** Heatmap 1 = spread mediano actual (pb). Heatmap 2 = percentil 5y de ese spread (verde = barato vs su historia).")
    cur_w = df[(df["fecha_d"] >= df["fecha_d"].max() - timedelta(days=90)) & df["spread_bp"].between(-200, 3000)]
    if cur_w.empty:
        st.info("No hay trades con spread en los últimos 90 días bajo los filtros.")
    else:
        mat = (
            cur_w.groupby(["rating_tier", "bucket_plazo"], observed=True)
            .agg(spread=("spread_bp", "median"), yld=("ytm_calc", "median"), n=("spread_bp", "count"))
            .reset_index()
        )
        pivot_sp = mat.pivot(index="rating_tier", columns="bucket_plazo", values="spread")
        pivot_sp = pivot_sp.reindex([t for t in TIER_ORDER if t in pivot_sp.index])
        pivot_sp = pivot_sp[[b for b in BUCKET_ORDER if b in pivot_sp.columns]]
        fig_h = go.Figure(
            data=go.Heatmap(
                z=pivot_sp.values, x=pivot_sp.columns, y=pivot_sp.index,
                colorscale="YlOrRd",
                text=[[f"{v:.0f} pb" if pd.notna(v) else "" for v in row] for row in pivot_sp.values],
                texttemplate="%{text}",
                hovertemplate="Tier %{y} · %{x}<br>Spread: %{z:.0f} pb<extra></extra>",
            )
        )
        fig_h.update_layout(template="plotly_white", height=380, title="Spread mediano actual (pb)",
                            xaxis_title="Plazo", yaxis_title="Rating tier")
        st.plotly_chart(fig_h, use_container_width=True)

        # ----- Heatmap 2: percentil 5y -----
        # Histórico SIN respetar filtro de fechas para tener base estadística (5y atrás desde el max global)
        hist_max = trades["fecha_d"].max()
        hist_min = hist_max - timedelta(days=1825)
        hist_base = trades.copy()
        # Aplicar mismos filtros que df EXCEPTO fechas
        if sector_sel != "(todos)":
            hist_base = hist_base[hist_base["sector"] == sector_sel]
        if "(todos)" not in instr_sel and instr_sel:
            hist_base = hist_base[hist_base["instrumento_clase"].isin(instr_sel)]
        if ratings_sel and len(ratings_sel) < len(TIER_ORDER):
            hist_base = hist_base[hist_base["rating_tier"].isin(ratings_sel)]
        if buckets:
            hist_base = hist_base[hist_base["bucket_plazo"].isin(buckets)]
        if emisor_sel != "(todos)":
            hist_base = hist_base[hist_base["emisor"] == emisor_sel]
        hist = hist_base[
            (hist_base["fecha_d"] >= hist_min)
            & hist_base["spread_bp"].between(-200, 3000)
        ]
        if hist.empty:
            st.info("No hay historia 5y suficiente para computar percentiles bajo los filtros.")
        else:
            hist_q = (
                hist.groupby(["rating_tier", "bucket_plazo"], observed=True)["spread_bp"]
                .agg(
                    p10=lambda s: s.quantile(0.10),
                    p25=lambda s: s.quantile(0.25),
                    p50=lambda s: s.quantile(0.50),
                    p75=lambda s: s.quantile(0.75),
                    p90=lambda s: s.quantile(0.90),
                    n_hist="count",
                ).reset_index()
            )
            merged = mat[["rating_tier", "bucket_plazo", "spread"]].rename(columns={"spread": "spread_now"})
            merged = merged.merge(hist_q, on=["rating_tier", "bucket_plazo"])
            merged = merged[merged["n_hist"] >= 20]

            if merged.empty:
                st.info("No hay celdas con n>=20 en la ventana 5y.")
            else:
                def _pos(row):
                    breaks = [0.10, 0.25, 0.50, 0.75, 0.90]
                    vals = [row["p10"], row["p25"], row["p50"], row["p75"], row["p90"]]
                    y = row["spread_now"]
                    if y <= vals[0]: return 0.05
                    if y >= vals[-1]: return 0.95
                    for i in range(4):
                        if vals[i] <= y <= vals[i+1]:
                            denom = vals[i+1] - vals[i]
                            frac = (y - vals[i]) / denom if denom else 0
                            return breaks[i] + frac * (breaks[i+1] - breaks[i])
                    return 0.5
                merged["percentil"] = merged.apply(_pos, axis=1)

                pivot_pc = merged.pivot(index="rating_tier", columns="bucket_plazo", values="percentil")
                pivot_pc = pivot_pc.reindex([t for t in TIER_ORDER if t in pivot_pc.index])
                pivot_pc = pivot_pc[[b for b in BUCKET_ORDER if b in pivot_pc.columns]]
                fig_h2 = go.Figure(
                    data=go.Heatmap(
                        z=pivot_pc.values, x=pivot_pc.columns, y=pivot_pc.index,
                        colorscale="RdYlGn",
                        zmin=0, zmax=1,
                        text=[[f"{v*100:.0f}%" if pd.notna(v) else "" for v in row] for row in pivot_pc.values],
                        texttemplate="%{text}",
                        hovertemplate="Tier %{y} · %{x}<br>Percentil 5y: %{z:.0%}<extra></extra>",
                        colorbar=dict(tickformat=".0%"),
                    )
                )
                fig_h2.update_layout(template="plotly_white", height=380,
                                     title="Percentil 5y del spread (verde = barato vs su propia historia)",
                                     xaxis_title="Plazo", yaxis_title="Rating tier")
                st.plotly_chart(fig_h2, use_container_width=True)

        # Datos de la tabla
        st.markdown("**Tabla cruzada (90 días)**")
        show_mat = mat.copy()
        show_mat["yld"] = (show_mat["yld"] * 100).round(2)
        show_mat["spread"] = show_mat["spread"].round(0)
        st.dataframe(
            show_mat.pivot(index="rating_tier", columns="bucket_plazo", values="spread").reindex([t for t in TIER_ORDER if t in show_mat["rating_tier"].unique()]),
            use_container_width=True,
        )

with tab2:
    df_m = df.copy()
    df_m["quarter"] = pd.to_datetime(df_m["fecha_d"]).dt.to_period("Q").dt.to_timestamp()
    s = df_m.groupby(["quarter", "bucket_plazo"], observed=True)["ytm_calc"].median().reset_index()
    s["yld_pct"] = s["ytm_calc"] * 100
    fig = px.line(s, x="quarter", y="yld_pct", color="bucket_plazo",
                  category_orders={"bucket_plazo": BUCKET_ORDER},
                  labels={"quarter": "Trimestre", "yld_pct": "Yield (%)"})
    fig.update_layout(template="plotly_white", height=480)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Evolución trimestral mediana por bucket de plazo (filtros aplicados).")

with tab3:
    fig = px.scatter(
        df, x="plazo_residual_anos", y=df["ytm_calc"] * 100,
        color="instrumento_clase", size="monto", size_max=22, opacity=0.6,
        hover_data={"nemotecnico": True, "emisor": True, "fecha_d": True, "sector": True},
        labels={"plazo_residual_anos": "Plazo residual (años)", "y": "YTM (%)"},
    )
    fig.update_layout(template="plotly_white", height=560)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Cada punto = un trade. Tamaño = monto. Útil para ver clusters y outliers.")

with tab4:
    fig = px.box(df, x="instrumento_clase", y=df["ytm_calc"] * 100, points="suspectedoutliers",
                 labels={"instrumento_clase": "Instrumento", "y": "YTM (%)"})
    fig.update_layout(template="plotly_white", height=500, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Distribución de yields por tipo de instrumento (filtros aplicados).")

with tab5:
    show = df.sort_values("fecha_d", ascending=False).head(500)[
        ["fecha_d", "nemotecnico", "emisor", "sector", "instrumento_clase",
         "plazo_residual_anos", "ytm_calc", "precio", "monto"]
    ].copy()
    show["ytm_calc"] = (show["ytm_calc"] * 100).round(3)
    show["plazo_residual_anos"] = show["plazo_residual_anos"].round(2)
    st.dataframe(show, use_container_width=True)
    st.download_button(
        "Bajar CSV (filtrado)",
        data=df.to_csv(index=False).encode(),
        file_name="trades_filtrados.csv",
        mime="text/csv",
    )

st.markdown("---")
st.caption("Datos: Latinex (latinexbolsa.com) · UST: home.treasury.gov · No constituye recomendación de inversión.")
