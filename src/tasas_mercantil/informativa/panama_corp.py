"""L_PA_1 — Panamá corporate: rating × plazo, sector × plazo, spreads.

Fuente enriquecida (encontrada el 2026-06-16): el estudio de tasas
Panamá ya tiene cruzado el dataset Latinex con ratings proxy.

  - `docs/_data/instruments_con_rating.csv.gz`: 2,573 emisiones con
    `rating_tier` (T1..T5) y `rating_proxy` (escala local Panamá).
  - `docs/_data/trades_con_rating.csv.gz`: 31,196 transacciones con
    `spread_bp` y `ytm_calc` ya calculados, bucketizadas por plazo.

Escala (src/analytics/ratings.py):
  T1 = AAA(pan)   — soberano + bancos sistémicos
  T2 = AA(pan)    — bancos grandes + utilities reguladas
  T3 = A(pan)     — bancos medianos, corporates establecidos
  T4 = BBB(pan)   — fideicomisos hipotecarios, real estate
  T5 = BB(pan)/NR — VCN, corporativos sin rating público

Paneles:
  (1) Heatmap RATING × PLAZO — tasa promedio ponderada por monto.
  (2) Heatmap SECTOR × PLAZO — la dimensión anterior, mantenida.
  (3) Spread observado (bps) por rating × plazo, calculado de trades reales.
  (4) Top 10 emisiones activas por monto, con rating.

Frontera: rating es PROXY V0 curado (ISSUER_RATING_PROXY + fallback por
sector). Se reemplaza por calificaciones oficiales cuando se incorpore
el dump Bloomberg/Equilibrium/Fitch.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INSTR_CSV = Path("docs/_data/instruments_con_rating.csv.gz")
TRADES_CSV = Path("docs/_data/trades_con_rating.csv.gz")
BLOOMBERG_PARQUET = Path("data/external/tasas_mercantil/bloomberg_historico.parquet")

DEBT_INSTRUMENTS = {"BONOS", "BONOS HIPOTECARIOS", "NOTAS CORPORATIVAS",
                    "SVS - BONOS"}
TENOR_BINS = [(0, 1, "<1y"), (1, 3, "1-3y"), (3, 5, "3-5y"),
              (5, 7, "5-7y"), (7, 10, "7-10y"), (10, 100, ">10y")]
# Bucket plazo en trades: '0-1y','1-3y','3-5y','5-7y','7-10y','10y+'
TRADE_BUCKETS = ["0-1y", "1-3y", "3-5y", "5-7y", "7-10y", "10y+"]
# Tenors UST para spread teórico
UST_PILLARS = [("UST_1Y", 1.0), ("UST_2Y", 2.0), ("UST_3Y", 3.0),
               ("UST_5Y", 5.0), ("UST_7Y", 7.0), ("UST_10Y", 10.0),
               ("UST_20Y", 20.0), ("UST_30Y", 30.0)]
RATING_ORDER = ["T1", "T2", "T3", "T4", "T5"]
RATING_LABELS = {"T1": "T1 · AAA(pan)", "T2": "T2 · AA(pan)",
                 "T3": "T3 · A(pan)",   "T4": "T4 · BBB(pan)",
                 "T5": "T5 · BB/NR(pan)"}

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_instruments() -> pd.DataFrame:
    """Universo de emisiones activas con rating ya cruzado."""
    df = pd.read_csv(INSTR_CSV)
    df = df[df["pais"] == "Panamá"].copy()
    df = df[df["instrumento"].isin(DEBT_INSTRUMENTS)]
    df = df[df["es_tasa_fija"] == True]
    df["cupon_decimal"] = pd.to_numeric(df["cupon_decimal"], errors="coerce")
    df = df[df["cupon_decimal"].notna() & (df["cupon_decimal"] > 0)]
    df["fecha_emision"] = pd.to_datetime(df["fechaEmision_d"])
    df["fecha_venc"] = pd.to_datetime(df["fechaVencimiento_d"])
    df["plazo_anios"] = pd.to_numeric(df["plazo_original_anos"], errors="coerce")
    df = df[df["plazo_anios"] > 0]
    df["tasa_pct"] = df["cupon_decimal"] * 100
    df["montoSerie"] = pd.to_numeric(df["montoSerie"], errors="coerce")
    return df


def _load_trades() -> pd.DataFrame:
    """Trades 10y con spread observado."""
    df = pd.read_csv(TRADES_CSV)
    df["fecha"] = pd.to_datetime(df["fecha_d"])
    return df


def _bucket_plazo(years: float) -> str | None:
    for lo, hi, name in TENOR_BINS:
        if lo <= years < hi:
            return name
    return None


def _ust_curve(as_of: date) -> dict[float, float]:
    df = pd.read_parquet(BLOOMBERG_PARQUET)
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    cut = pd.Timestamp(as_of)
    out = {}
    for feat, t in UST_PILLARS:
        sub = df[(df["feature_name"] == feat) & (df["obs_date"] <= cut)]
        if sub.empty:
            continue
        v = float(sub.sort_values("obs_date").iloc[-1]["value"])
        if np.isfinite(v):
            out[t] = v
    return out


def _ust_at(plazo_mid: float, ust_curve: dict[float, float]) -> float:
    if not ust_curve:
        return float("nan")
    xs = sorted(ust_curve.keys())
    ys = [ust_curve[x] for x in xs]
    if plazo_mid <= xs[0]:
        return ys[0]
    if plazo_mid >= xs[-1]:
        return ys[-1]
    return float(np.interp(plazo_mid, xs, ys))


# ---------------------------------------------------------------------------
# Agregaciones
# ---------------------------------------------------------------------------
def _heatmap(df: pd.DataFrame, row_col: str, row_order: list[str]
             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Heatmap (tasa_avg ponderada por monto, count) por row_col × bucket."""
    df["bucket"] = df["plazo_anios"].apply(_bucket_plazo)
    sub = df.dropna(subset=["bucket"]).copy()
    sub["w"] = sub["montoSerie"].fillna(1.0).clip(lower=1.0)
    sub["wt_tasa"] = sub["tasa_pct"] * sub["w"]
    g = (sub.groupby([row_col, "bucket"])
            .agg(sum_wt=("wt_tasa", "sum"), sum_w=("w", "sum"),
                 count=("isin", "size"))
            .reset_index())
    g["tasa_avg"] = g["sum_wt"] / g["sum_w"]
    bucket_order = [b[2] for b in TENOR_BINS]
    avg = g.pivot(index=row_col, columns="bucket", values="tasa_avg")
    cnt = g.pivot(index=row_col, columns="bucket", values="count")
    return (avg.reindex(index=row_order, columns=bucket_order),
            cnt.reindex(index=row_order, columns=bucket_order))


def aggregate_corp(as_of: date) -> dict:
    """Agregaciones para los 4 paneles."""
    df = _load_instruments()
    df = df[df["fecha_emision"] <= pd.Timestamp(as_of)]
    df = df[df["fecha_venc"] > pd.Timestamp(as_of)]

    # Sectores: top 8 con más emisiones
    top_sectors = df["sector"].value_counts().head(8).index.tolist()
    df["sector_grp"] = df["sector"].where(df["sector"].isin(top_sectors),
                                          "Otros")
    sector_order = top_sectors + (["Otros"] if "Otros" in df["sector_grp"].values
                                  else [])

    rating_avg, rating_cnt = _heatmap(df.copy(), "rating_tier", RATING_ORDER)
    sector_avg, sector_cnt = _heatmap(df.copy(), "sector_grp", sector_order)
    rating_avg.index = [RATING_LABELS[r] for r in rating_avg.index]
    rating_cnt.index = rating_avg.index

    # Spread observado por rating × bucket usando trades (últimos 6 meses
    # vs as_of para foto reciente)
    trades = _load_trades()
    cut = pd.Timestamp(as_of)
    trades_recent = trades[(trades["fecha"] <= cut) &
                           (trades["fecha"] >= cut - pd.DateOffset(months=6)) &
                           trades["spread_bp"].notna() &
                           trades["spread_bp"].between(-100, 2000) &  # winsorize
                           trades["rating_tier"].isin(RATING_ORDER) &
                           trades["bucket_plazo"].isin(TRADE_BUCKETS)]
    spread_med = (trades_recent
                  .groupby(["rating_tier", "bucket_plazo"])["spread_bp"]
                  .median().reset_index()
                  .pivot(index="rating_tier", columns="bucket_plazo",
                         values="spread_bp")
                  .reindex(index=RATING_ORDER, columns=TRADE_BUCKETS))
    spread_med.index = [RATING_LABELS[r] for r in spread_med.index]

    ust_curve = _ust_curve(as_of)

    # Top 10 emisiones por monto, con rating
    top = (df.sort_values("montoSerie", ascending=False).head(10)
           [["isin", "emisor", "sector_grp", "rating_proxy", "plazo_anios",
             "tasa_pct", "montoSerie", "fecha_venc"]].copy())
    top["plazo_anios"] = top["plazo_anios"].round(1)
    top["tasa_pct"] = top["tasa_pct"].round(2)
    top["montoSerie"] = (top["montoSerie"] / 1e6).round(1)
    top = top.rename(columns={"sector_grp": "Sector", "rating_proxy": "Rating",
                              "plazo_anios": "Plazo (y)", "tasa_pct": "Tasa %",
                              "montoSerie": "USD MM",
                              "fecha_venc": "Vencimiento"})
    top["Vencimiento"] = top["Vencimiento"].dt.strftime("%Y-%m-%d")

    return {
        "rating_avg": rating_avg, "rating_cnt": rating_cnt,
        "sector_avg": sector_avg, "sector_cnt": sector_cnt,
        "spread_obs": spread_med, "ust_curve": ust_curve,
        "top": top,
        "n_trades_used": int(len(trades_recent)),
    }


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------
def _draw_heatmap(ax, h_avg: pd.DataFrame, h_cnt: pd.DataFrame, title: str,
                  fmt: str = "{:.2f}%", cmap: str = "YlOrRd",
                  cbar_label: str = "Tasa %") -> None:
    data = h_avg.values.astype(float)
    if np.all(np.isnan(data)):
        ax.text(0.5, 0.5, "sin datos", transform=ax.transAxes,
                ha="center", va="center")
        ax.set_title(title, fontsize=10, weight="bold")
        return
    vmin = float(np.nanmin(data)); vmax = float(np.nanmax(data))
    im = ax.imshow(data, aspect="auto", cmap=plt.get_cmap(cmap),
                   vmin=vmin, vmax=vmax)
    ax.set_xticks(np.arange(len(h_avg.columns)))
    ax.set_xticklabels(h_avg.columns, fontsize=8)
    ax.set_yticks(np.arange(len(h_avg.index)))
    ax.set_yticklabels(h_avg.index, fontsize=8.5)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isfinite(v):
                n = h_cnt.iloc[i, j] if h_cnt is not None else None
                color = "white" if v > (vmin + vmax) / 2 else "black"
                txt = fmt.format(v)
                if n is not None and np.isfinite(n):
                    txt += f"\n(n={int(n)})"
                ax.text(j, i, txt, ha="center", va="center",
                        fontsize=6.5, color=color)
    ax.set_title(title, fontsize=10.5, weight="bold")
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.78, pad=0.02)
    cbar.set_label(cbar_label, fontsize=7.5)
    cbar.ax.tick_params(labelsize=7)


def plot_l_pa_1(as_of: date, output_path: Path | str,
                figsize=(15, 10.5), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    a = aggregate_corp(as_of)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 0.85],
                          width_ratios=[1.0, 1.0], hspace=0.50, wspace=0.18)
    ax_rt = fig.add_subplot(gs[0, 0])
    ax_st = fig.add_subplot(gs[0, 1])
    ax_sp = fig.add_subplot(gs[1, 0])
    ax_legend = fig.add_subplot(gs[1, 1])
    ax_tbl = fig.add_subplot(gs[2, :])

    # (1) Rating × Plazo
    _draw_heatmap(ax_rt, a["rating_avg"], a["rating_cnt"],
                  "Tasa promedio ponderada · RATING × PLAZO")
    # (2) Sector × Plazo
    _draw_heatmap(ax_st, a["sector_avg"], a["sector_cnt"],
                  "Tasa promedio ponderada · SECTOR × PLAZO")
    # (3) Spread observado por rating × bucket (de trades reales)
    _draw_heatmap(ax_sp, a["spread_obs"], None,
                  f"Spread OBSERVADO mediano (bps) · trades últimos 6m · "
                  f"n={a['n_trades_used']:,}",
                  fmt="{:.0f}", cmap="RdYlBu_r", cbar_label="bps")

    # (4) Leyenda compacta del rating + UST curve actual
    ax_legend.axis("off")
    rt_text = "Escala Panamá local:\n" + "\n".join(
        f"  {RATING_LABELS[t]}" for t in RATING_ORDER)
    ust_text = "Curva UST al corte (referencia spread):\n" + "\n".join(
        f"  {y:>4.1f}y → {v:.2f}%"
        for y, v in sorted(a["ust_curve"].items()))
    ax_legend.text(0.02, 0.98, rt_text, transform=ax_legend.transAxes,
                   ha="left", va="top", fontsize=9, family="monospace",
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f8fb",
                             edgecolor="#aaa"))
    ax_legend.text(0.02, 0.42, ust_text, transform=ax_legend.transAxes,
                   ha="left", va="top", fontsize=8.5, family="monospace",
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                             edgecolor="#aaa"))

    # (5) Top 10 emisiones
    ax_tbl.axis("off")
    ax_tbl.set_title("Top 10 emisiones activas por monto (FIJA, con rating)",
                     fontsize=10.5, weight="bold", loc="left")
    if not a["top"].empty:
        cols = ["ISIN", "Emisor", "Sector", "Rating", "Plazo (y)",
                "Tasa %", "USD MM", "Vencimiento"]
        cell = a["top"][["isin", "emisor", "Sector", "Rating", "Plazo (y)",
                         "Tasa %", "USD MM", "Vencimiento"]].values.tolist()
        tbl = ax_tbl.table(cellText=cell, colLabels=cols,
                           cellLoc="center", loc="upper center",
                           bbox=[0.0, 0.0, 1.0, 0.88])
        tbl.auto_set_font_size(False); tbl.set_fontsize(7.8)
        for j in range(len(cols)):
            tbl[0, j].set_facecolor("#2a6fb3")
            tbl[0, j].set_text_props(color="white", weight="bold")

    fig.suptitle(f"Panamá corporate — rating · sector · plazo · spread "
                 f"observado · corte {as_of}",
                 fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005,
             "Rating: proxy V0 curado por emisor + fallback por sector. "
             "Spread observado: mediana de trades últimos 6m. "
             "Soberano + CDS Panamá pendientes plantilla BBG v0.3. "
             + DISCLAIMER,
             ha="center", fontsize=7.0, style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
