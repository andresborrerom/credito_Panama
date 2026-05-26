"""Streamlit interactivo para uso local — filtros completos.

Ejecutar: streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import pathlib
import sys
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.analytics.curves import BUCKET_MIDPOINTS, BUCKET_ORDER, con, ust_monthly  # noqa: E402

st.set_page_config(page_title="Renta Fija Panamá", layout="wide", page_icon="📊")


@st.cache_resource
def get_con():
    return con()


@st.cache_data
def load_trades() -> pd.DataFrame:
    c = get_con()
    return c.execute(
        """
        SELECT fecha_d, nemotecnico, emisor, sector, instrumento_clase,
               plazo_residual_anos, bucket_plazo, ytm_calc, precio, monto, es_tasa_fija
        FROM trades
        WHERE es_tasa_fija = TRUE
          AND ytm_calc BETWEEN 0.005 AND 0.40
          AND plazo_residual_anos BETWEEN 0 AND 30
        """
    ).df()


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
    sectores = ["(todos)"] + sorted(trades["sector"].dropna().unique().tolist())
    sector_sel = st.selectbox("Sector", sectores)

    instrs = ["(todos)"] + sorted(trades["instrumento_clase"].dropna().unique().tolist())
    instr_sel = st.multiselect("Instrumento", instrs, default=["(todos)"])

    fmin, fmax = trades["fecha_d"].min(), trades["fecha_d"].max()
    fecha_range = st.slider(
        "Rango de fechas",
        min_value=fmin,
        max_value=fmax,
        value=(fmax - timedelta(days=365), fmax),
    )

    buckets = st.multiselect("Buckets de plazo", BUCKET_ORDER, default=BUCKET_ORDER)

    emisores_top = ["(todos)"] + sorted(trades["emisor"].dropna().value_counts().head(50).index.tolist())
    emisor_sel = st.selectbox("Emisor (top 50)", emisores_top)

# ============ FILTRO ============
df = trades.copy()
df = df[(df["fecha_d"] >= fecha_range[0]) & (df["fecha_d"] <= fecha_range[1])]
if sector_sel != "(todos)":
    df = df[df["sector"] == sector_sel]
if "(todos)" not in instr_sel and instr_sel:
    df = df[df["instrumento_clase"].isin(instr_sel)]
if buckets:
    df = df[df["bucket_plazo"].isin(buckets)]
if emisor_sel != "(todos)":
    df = df[df["emisor"] == emisor_sel]

if df.empty:
    st.warning("No hay trades que cumplan los filtros. Ajusta los criterios.")
    st.stop()

# ============ STATS ============
c1, c2, c3, c4 = st.columns(4)
c1.metric("Trades", f"{len(df):,}")
c2.metric("Yield mediano", f"{df['ytm_calc'].median()*100:.2f}%")
c3.metric("Emisores", f"{df['emisor'].nunique()}")
c4.metric("Volumen USD", f"${df['monto'].sum()/1e6:,.1f}M")

# ============ TABS ============
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Curva", "Historia", "Dispersión", "Distribución", "Tabla"])

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

with tab2:
    df_m = df.copy()
    df_m["quarter"] = df_m["fecha_d"].apply(lambda d: pd.Timestamp(d).to_period("Q").to_timestamp())
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
