"""Streamlit interactivo para uso local — filtros completos.

Ejecutar: streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.analytics.curves import BUCKET_MIDPOINTS, BUCKET_ORDER, con, ust_monthly  # noqa: E402
from src.analytics.ratings import TIER_DESC, TIER_ORDER  # noqa: E402
from src.analytics.capital import (  # noqa: E402
    CAR_MIN_TOTAL,
    INSTRUMENT_TO_ASSET_CLASS,
    RISK_WEIGHTS_SBP,
    capital_for_position,
    credit_capacity_by_rw,
    resolve_asset_class,
)
from src.analytics.provisiones import (  # noqa: E402
    LGD_BY_INSTRUMENT,
    PD_BY_TIER,
    provision_for_position,
    sensitivity_table,
)

st.set_page_config(page_title="Renta Fija Panamá", layout="wide", page_icon="📊")


def _git_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, timeout=2
        ).strip()
    except Exception:
        return "unknown"


COMMIT = _git_short()
BOOT_TS = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


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
st.caption(
    f"Latinex · {len(trades):,} trades con YTM · ventana {trades['fecha_d'].min()} → {trades['fecha_d'].max()} "
    f"· **commit `{COMMIT}` · boot {BOOT_TS}**"
)

# ============ SIDEBAR ============
with st.sidebar:
    st.header("Filtros")

    foco_bancos = st.checkbox("🏦 Foco: sector bancario (Financiero)", value=False)

    sectores = ["(todos)"] + sorted(trades["sector"].dropna().unique().tolist())
    sector_sel = "Financiero" if foco_bancos else st.selectbox("Sector", sectores)

    instrs = ["(todos)"] + sorted(trades["instrumento_clase"].dropna().unique().tolist())
    instr_sel = st.multiselect("Instrumento", instrs, default=["(todos)"],
                                help="Vacío o '(todos)' = no filtra por instrumento.")

    ratings_sel = st.multiselect(
        "Rating tier",
        TIER_ORDER,
        default=TIER_ORDER,
        format_func=lambda t: f"{t} · {TIER_DESC[t].split(' — ')[0]}",
        help="Vacío = todos los tiers (no filtra). Selecciona uno o más para acotar.",
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

    buckets = st.multiselect("Buckets de plazo", BUCKET_ORDER, default=BUCKET_ORDER,
                              help="Vacío = todos los buckets (no filtra). Selecciona uno o más para acotar.")

    emisores_top = ["(todos)"] + sorted(trades["emisor"].dropna().value_counts().head(50).index.tolist())
    emisor_sel = st.selectbox("Emisor (top 50)", emisores_top)

    with st.expander("Leyenda de rating tiers"):
        for t in TIER_ORDER:
            st.markdown(f"**{t}** · {TIER_DESC[t]}")

    st.divider()
    if st.button("🔄 Limpiar cache y recargar", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

# ============ FILTRO ============
df = trades.copy()
df = df[(df["fecha_d"] >= fecha_ini) & (df["fecha_d"] <= fecha_fin)]
active_filters = [f"fechas: {fecha_ini} → {fecha_fin}"]
if sector_sel != "(todos)":
    df = df[df["sector"] == sector_sel]
    active_filters.append(f"sector: {sector_sel}")
if "(todos)" not in instr_sel and instr_sel:
    df = df[df["instrumento_clase"].isin(instr_sel)]
    active_filters.append(f"instrumento: {', '.join(instr_sel)}")
if ratings_sel and len(ratings_sel) < len(TIER_ORDER):
    df = df[df["rating_tier"].isin(ratings_sel)]
    active_filters.append(f"rating: {', '.join(ratings_sel)}")
if buckets and len(buckets) < len(BUCKET_ORDER):
    df = df[df["bucket_plazo"].isin(buckets)]
    active_filters.append(f"plazos: {', '.join(buckets)}")
if emisor_sel != "(todos)":
    df = df[df["emisor"] == emisor_sel]
    active_filters.append(f"emisor: {emisor_sel}")

st.info("🔎 **Filtros activos:** " + " · ".join(active_filters))

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
tab1, tab_sp, tab_cx, tab_calc, tab2, tab3, tab4, tab5 = st.tabs(
    ["Curva", "Spread × Rating", "Cross-ref", "🧮 Calculadora",
     "Historia", "Dispersión", "Distribución", "Tabla"]
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

# ==========================================================================
# TAB CALCULADORA: Diferencial de yield vs Diferencial de crédito
#                  + Adecuación de capital + Provisiones potenciales
# ==========================================================================
with tab_calc:
    st.markdown("### 🧮 Calculadora: Yield vs Crédito · Capital · Provisiones")
    st.caption(
        "Ingresa un instrumento hipotético (rating, plazo, monto) y calcula los cuatro "
        "componentes en paralelo. Los supuestos de PD/LGD/RW son editables y su procedencia "
        "es visible; nada está inventado."
    )

    # ---------- Inputs ----------
    ci1, ci2, ci3, ci4 = st.columns([1, 1, 1.2, 1.4])
    with ci1:
        calc_tier = st.selectbox(
            "Rating tier",
            TIER_ORDER,
            index=2,
            format_func=lambda t: f"{t} · {TIER_DESC[t].split(' — ')[0]}",
            help="Escala nacional Panamá (T1=AAA(pan) → T5=BB(pan)/NR).",
        )
    with ci2:
        calc_plazo = st.number_input(
            "Plazo residual (años)",
            min_value=0.25, max_value=30.0, value=5.0, step=0.25,
            help="Horizonte para PD acumulada y para bucket de plazo.",
        )
    with ci3:
        instr_options = list(INSTRUMENT_TO_ASSET_CLASS.keys())
        calc_instrumento = st.selectbox(
            "Instrumento",
            instr_options,
            index=instr_options.index("BONOS") if "BONOS" in instr_options else 0,
            help=(
                "Determina asset class regulatoria y LGD default. "
                "SUB_T2 y AT1 aplican para bonos de capital regulatorio."
            ),
        )
    with ci4:
        calc_ead = st.number_input(
            "EAD (USD)",
            min_value=1_000.0, max_value=1_000_000_000.0, value=10_000_000.0,
            step=100_000.0, format="%.0f",
            help="Exposición al default. Para bono bullet ≈ face value.",
        )
    calc_sector = st.selectbox(
        "Sector emisor (afecta asset class regulatoria)",
        ["(sin sector — usar default)", "Financiero", "Gobierno", "Industriales",
         "Comunicaciones", "Energía", "Utilidades", "Bienes Raíces", "Consumo Básico",
         "Consumo Discresional", "Materiales", "Salud", "Tecnología", "Servicios"],
        index=1,
        help="Si es 'Financiero', bonos senior se clasifican como BANK (RW puede diferir).",
    )
    sector_arg = None if calc_sector.startswith("(") else calc_sector

    # ---------- Resolver bucket_plazo para lookup en df ----------
    def _plazo_to_bucket(p: float) -> str:
        for label, (lo, hi) in zip(
            BUCKET_ORDER,
            [(0, 1), (1, 3), (3, 5), (5, 7), (7, 10), (10, 100)],
        ):
            if lo <= p < hi or (label == "0-1y" and p == 0):
                return label
        return BUCKET_ORDER[-1]

    calc_bucket = _plazo_to_bucket(calc_plazo)

    # ---------- Cálculos ----------
    # (A) Diferencial de yield: buscar spread observado bajo los filtros actuales
    df_calc_ctx = df[
        (df["rating_tier"] == calc_tier)
        & (df["bucket_plazo"] == calc_bucket)
        & (df["instrumento_clase"] == calc_instrumento)
    ]
    if df_calc_ctx.empty:
        # Relajar filtro: solo tier + bucket
        df_calc_ctx = df[(df["rating_tier"] == calc_tier)
                         & (df["bucket_plazo"] == calc_bucket)]
    n_ctx = len(df_calc_ctx)
    spread_obs = df_calc_ctx["spread_bp"].dropna().median() if n_ctx > 0 else float("nan")
    yield_obs = df_calc_ctx["ytm_calc"].dropna().median() if n_ctx > 0 else float("nan")

    # (C) Capital
    try:
        cap_res = capital_for_position(
            tier=calc_tier, ead=calc_ead,
            instrumento=calc_instrumento, sector=sector_arg,
        )
    except Exception as exc:
        cap_res = None
        cap_err = str(exc)
    # (D) Provisión
    prov_res = provision_for_position(
        tier=calc_tier, ead=calc_ead,
        instrumento=calc_instrumento, horizon_years=calc_plazo,
    )

    st.markdown("---")

    # ---------- Panel A: Diferencial de yield (mercado) ----------
    pa, pb = st.columns(2)
    with pa:
        st.markdown("#### A. Diferencial de yield (mercado)")
        if pd.isna(spread_obs):
            st.warning(
                f"No hay trades observados para tier={calc_tier}, bucket={calc_bucket}, "
                f"instrumento={calc_instrumento} bajo los filtros actuales. "
                "Prueba a relajar rango de fechas o instrumentos."
            )
        else:
            st.metric("Spread mediano vs Tesoro Panamá", f"{spread_obs:,.0f} pb",
                       help=(
                           f"n={n_ctx} trades en el filtro actual, mismo bucket-quarter. "
                           "Es el diferencial de yield que el mercado cobra hoy por este "
                           "combo tier+plazo+instrumento."
                       ))
            st.metric("Yield mediano (todo-incluido)", f"{yield_obs*100:.2f}%")
            st.caption(
                "El spread está calculado como (YTM − yield Tesoro Panamá mismo bucket, "
                "mismo trimestre) × 10000."
            )

    # ---------- Panel B: Diferencial de crédito por rating (curva de tiers) ----------
    with pb:
        st.markdown("#### B. Diferencial de crédito por rating")
        # Calcular spread mediano por tier para este bucket
        df_bucket = df[df["bucket_plazo"] == calc_bucket]
        tier_curve = (
            df_bucket.groupby("rating_tier", observed=True)["spread_bp"]
            .median().reindex(TIER_ORDER).dropna()
        )
        if tier_curve.empty:
            st.info(f"No hay data suficiente para bucket {calc_bucket}.")
        else:
            fig_tier = px.bar(
                x=tier_curve.index, y=tier_curve.values,
                labels={"x": "Rating tier", "y": "Spread mediano (pb)"},
                text=[f"{v:.0f}" for v in tier_curve.values],
                color=tier_curve.values, color_continuous_scale="YlOrRd",
            )
            fig_tier.update_traces(textposition="outside")
            fig_tier.update_layout(
                template="plotly_white", height=290,
                title=f"Spread por tier en bucket {calc_bucket}",
                margin=dict(l=10, r=10, t=40, b=10),
                showlegend=False, coloraxis_showscale=False,
            )
            # Marcar el tier seleccionado
            if calc_tier in tier_curve.index:
                fig_tier.add_annotation(
                    x=calc_tier, y=tier_curve[calc_tier],
                    text="👆 seleccionado", showarrow=True, arrowhead=2, yshift=25,
                )
            st.plotly_chart(fig_tier, use_container_width=True)
            # Diferencial vs T1 (soberano)
            if "T1" in tier_curve.index and calc_tier in tier_curve.index:
                credit_prem = tier_curve[calc_tier] - tier_curve["T1"]
                st.caption(
                    f"Diferencial de crédito {calc_tier} vs T1 en {calc_bucket}: "
                    f"**{credit_prem:+.0f} pb**"
                )

    st.markdown("---")

    # ---------- Panel C: Adecuación de capital ----------
    pc, pd_ = st.columns(2)
    with pc:
        st.markdown("#### C. Adecuación de capital (SBP)")
        if cap_res is None:
            st.error(f"Error calculando capital: {cap_err}")
        else:
            st.metric("Asset class regulatoria", cap_res.asset_class)
            st.metric("Risk Weight aplicado", f"{cap_res.risk_weight*100:.1f}%",
                       help=cap_res.rw_source)
            st.metric("RWA", f"${cap_res.rwa:,.0f}")
            st.metric(
                f"Capital requerido ({cap_res.car_min*100:.1f}%)",
                f"${cap_res.capital_required:,.0f}",
                help="RWA × CAR mínimo SBP (8% Acuerdo 1-2015).",
            )
            st.caption(
                f"Fuente RW: {cap_res.rw_source} · "
                f"Capital = EAD × RW × CAR_min. "
                f"Para {calc_tier} {cap_res.asset_class} = "
                f"{cap_res.ead:,.0f} × {cap_res.risk_weight*100:.0f}% × "
                f"{cap_res.car_min*100:.1f}%."
            )

    # ---------- Panel D: Provisión esperada por calificación ----------
    with pd_:
        st.markdown("#### D. Provisión esperada por calificación")
        st.metric("PD (1 año)", f"{prov_res.pd_1y*100:.3f}%",
                   help=PD_BY_TIER[calc_tier]["source"])
        st.metric(f"PD acumulada ({calc_plazo:.2f}y)",
                   f"{prov_res.pd_cumulative*100:.3f}%")
        st.metric("LGD aplicada", f"{prov_res.lgd*100:.1f}%",
                   help=LGD_BY_INSTRUMENT.get(calc_instrumento,
                                               LGD_BY_INSTRUMENT["DEFAULT"])["source"])
        st.metric(
            f"EL @ {calc_plazo:.2f}y (provisión esperada)",
            f"${prov_res.el_horizon:,.0f}",
            delta=f"{prov_res.provision_pct_ead*100:.3f}% del EAD",
            help="EL = PD_cumulative × LGD × EAD",
        )
        st.metric("EL @ 1 año (referencia)", f"${prov_res.el_1y:,.0f}")

    st.markdown("---")

    # ---------- Resumen: Yield vs Costo integrado ----------
    st.markdown("#### 📊 Resumen integrado")
    # yield observado - LO EL "amortizado por año" (aproximación)
    if not pd.isna(yield_obs) and cap_res is not None:
        # Costo de capital anual asumiendo return on capital 12%
        rendimiento_capital_esperado = 0.12
        costo_capital_anual = cap_res.capital_required * rendimiento_capital_esperado
        el_anual_aprox = prov_res.el_1y  # aproximación año 1
        ingreso_bruto_anual = calc_ead * yield_obs
        margen_neto = ingreso_bruto_anual - el_anual_aprox - costo_capital_anual
        margen_bp = (margen_neto / calc_ead) * 10000 if calc_ead > 0 else 0
        st.markdown(
            f"""
            | Componente | Valor anual |
            |---|---:|
            | (+) Ingreso bruto (EAD × yield {yield_obs*100:.2f}%) | ${ingreso_bruto_anual:,.0f} |
            | (−) Provisión esperada (EL 1y) | ${el_anual_aprox:,.0f} |
            | (−) Costo de capital ({rendimiento_capital_esperado*100:.0f}% s/ ${cap_res.capital_required:,.0f}) | ${costo_capital_anual:,.0f} |
            | **= Margen neto** | **${margen_neto:,.0f}** ({margen_bp:+,.0f} pb sobre EAD) |
            """
        )
        st.caption(
            "El 'costo de capital' asume 12% de retorno esperado sobre el capital "
            "que la posición inmoviliza. Este supuesto es editable por el usuario "
            "(en versión futura). Marcado como supuesto interno del banco."
        )
    else:
        st.info(
            "Selecciona un combo con trades observados para ver el resumen integrado "
            "(necesita yield de mercado)."
        )

    # ---------- Procedencia expandible ----------
    with st.expander("🔎 Procedencia de los supuestos", expanded=False):
        st.markdown(
            f"""
**PD (T{calc_tier[1:]}, 1y): {PD_BY_TIER[calc_tier]['pd_1y']*100:.3f}%**
Fuente: {PD_BY_TIER[calc_tier]['source']}
Confianza: {PD_BY_TIER[calc_tier]['confidence']}
Nota: {PD_BY_TIER[calc_tier]['note']}

**LGD ({calc_instrumento}): {LGD_BY_INSTRUMENT.get(calc_instrumento, LGD_BY_INSTRUMENT['DEFAULT'])['lgd']*100:.0f}%**
Fuente: {LGD_BY_INSTRUMENT.get(calc_instrumento, LGD_BY_INSTRUMENT['DEFAULT'])['source']}
Confianza: {LGD_BY_INSTRUMENT.get(calc_instrumento, LGD_BY_INSTRUMENT['DEFAULT'])['confidence']}

**Risk Weight ({cap_res.asset_class if cap_res else '—'}, {calc_tier}): {cap_res.risk_weight*100 if cap_res else '—'}%**
Fuente: {cap_res.rw_source if cap_res else '—'}

**CAR mínimo:** 8% (SBP Acuerdo 1-2015 Art. 4)
"""
        )

    # ==========================================================================
    # SUB-VISTA: SENSIBILIDAD
    # ==========================================================================
    st.markdown("---")
    st.markdown("### 🎛️ Sensibilidad")
    st.caption(
        "Mueve los sliders para PD y LGD y observa cómo cambian la provisión "
        "esperada y el capital requerido. Útil para stress testing y para "
        "calibrar contra data histórica interna del banco."
    )

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        pd_base = PD_BY_TIER[calc_tier]["pd_1y"]
        pd_mult = st.slider(
            "Multiplicador PD (× base)",
            min_value=0.1, max_value=5.0, value=1.0, step=0.1,
            help=f"PD base para {calc_tier}: {pd_base*100:.3f}%. Multiplicador 2.0 → 2×.",
        )
        pd_custom = pd_base * pd_mult
        st.caption(f"PD aplicada: **{pd_custom*100:.3f}%**")
    with sc2:
        lgd_base = LGD_BY_INSTRUMENT.get(
            calc_instrumento, LGD_BY_INSTRUMENT["DEFAULT"]
        )["lgd"]
        lgd_custom = st.slider(
            "LGD (fracción)",
            min_value=0.05, max_value=1.00, value=float(lgd_base), step=0.05,
            help=f"LGD base para {calc_instrumento}: {lgd_base*100:.0f}%.",
        )
    with sc3:
        rw_base = cap_res.risk_weight if cap_res else 0.50
        rw_custom = st.slider(
            "Risk Weight (fracción)",
            min_value=0.00, max_value=2.50, value=float(rw_base), step=0.05,
            help=f"RW base para ({cap_res.asset_class if cap_res else 'CORPORATE'}, {calc_tier}): {rw_base*100:.0f}%.",
        )

    # Recalcular con los overrides
    prov_sens = provision_for_position(
        tier=calc_tier, ead=calc_ead, instrumento=calc_instrumento,
        horizon_years=calc_plazo, pd_override=pd_custom, lgd_override=lgd_custom,
    )
    cap_sens = capital_for_position(
        tier=calc_tier, ead=calc_ead, instrumento=calc_instrumento,
        sector=sector_arg, rw_override=rw_custom,
    )

    ss1, ss2, ss3 = st.columns(3)
    with ss1:
        st.metric(
            "Provisión esperada (sensibilidad)",
            f"${prov_sens.el_horizon:,.0f}",
            delta=f"${prov_sens.el_horizon - prov_res.el_horizon:+,.0f} vs base",
        )
    with ss2:
        st.metric(
            "Capital requerido (sensibilidad)",
            f"${cap_sens.capital_required:,.0f}",
            delta=f"${cap_sens.capital_required - (cap_res.capital_required if cap_res else 0):+,.0f} vs base",
        )
    with ss3:
        # % del EAD que representa la carga total (provisión + capital)
        carga_pct = (prov_sens.el_horizon + cap_sens.capital_required) / calc_ead * 100
        st.metric(
            "Carga total sobre EAD",
            f"{carga_pct:.2f}%",
            help="(Provisión + Capital requerido) / EAD",
        )

    # Heatmap de sensibilidad PD × LGD
    st.markdown("**Heatmap: EL sobre grid de PD × LGD**")
    sens_df = sensitivity_table(
        tier=calc_tier, ead=calc_ead, instrumento=calc_instrumento,
        horizon_years=calc_plazo,
    )
    pivot = sens_df.pivot(index="lgd", columns="pd_1y", values="el_pct_ead")
    fig_heat = go.Figure(data=go.Heatmap(
        z=pivot.values * 100,
        x=[f"{v*100:.2f}%" for v in pivot.columns],
        y=[f"{v*100:.0f}%" for v in pivot.index],
        colorscale="Reds",
        text=[[f"{v*100:.2f}%" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        colorbar=dict(title="EL % EAD"),
        hovertemplate="PD %{x} · LGD %{y}<br>EL/EAD: %{z:.2f}%<extra></extra>",
    ))
    fig_heat.update_layout(
        template="plotly_white", height=380,
        xaxis_title="PD (1y)", yaxis_title="LGD",
        title=f"Provisión / EAD como % (horizonte {calc_plazo:.1f}y)",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

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
         "rating_tier", "rating_proxy",
         "plazo_residual_anos", "bucket_plazo",
         "ytm_calc", "spread_bp", "precio", "monto"]
    ].copy()
    show["ytm_calc"] = (show["ytm_calc"] * 100).round(3)
    show["spread_bp"] = show["spread_bp"].round(0)
    show["plazo_residual_anos"] = show["plazo_residual_anos"].round(2)
    show = show.rename(columns={
        "ytm_calc": "ytm_%",
        "spread_bp": "spread_pb",
        "rating_tier": "tier",
        "rating_proxy": "rating",
        "instrumento_clase": "instrumento",
    })
    st.dataframe(show, use_container_width=True)
    st.caption("Mostrando 500 más recientes. El CSV incluye TODOS los trades filtrados con columnas tier, rating, spread_pb, etc.")
    st.download_button(
        "📥 Bajar CSV (filtrado, con rating)",
        data=df.to_csv(index=False).encode(),
        file_name=f"trades_filtrados_{date.today().isoformat()}.csv",
        mime="text/csv",
    )

st.markdown("---")
st.caption("Datos: Latinex (latinexbolsa.com) · UST: home.treasury.gov · No constituye recomendación de inversión.")
