"""L_PA_1 — Panamá corporate: SPREAD por crédito × sector × plazo.

Pieza informativa con foco en SPREAD vs UST (no tasa bruta). Spread es lo
que se compara entre emisores, plazos y ratings.

Datos: estudio Panamá del mismo repo:
  - `docs/_data/instruments_con_rating.csv.gz`: 2,573 emisiones con
    rating_tier (T1..T5) y rating_proxy (escala panameña).
  - `docs/_data/trades_con_rating.csv.gz`: 31,196 trades con `spread_bp`
    y `ytm_calc` ya calculados.

Escala panameña local (de src/analytics/ratings.py):
  T1 = AAA(pan) — soberano + bancos sistémicos
  T2 = AA(pan)  — bancos grandes, utilities reguladas
  T3 = A(pan)   — bancos medianos, corporates establecidos
  T4 = BBB(pan) — fideicomisos hipotecarios, real estate
  T5 = BB(pan)/NR — VCN, corporates sin rating público

Estructura visual (3 tablas + 1 ranking + mensaje principal):
  (1) Banner con mensaje principal autogenerado del corte.
  (2) Tabla MAESTRA: spread (bps) × RATING × PLAZO — mediana de trades
      últimos 6m. Lectura: "T3 a 3-5y paga 427 bps sobre UST".
  (3) Tabla SECUNDARIA: spread (bps) × SECTOR × RATING — mediana de
      tasa-vs-UST de emisiones activas. Lectura: "Bienes Raíces T3 paga
      más spread que Financiero T3 al mismo rating".
  (4) Top 10 emisiones activas por monto con rating.

Frontera: rating = proxy V0 curado. Sector se agrupa en top 6 + Otros.
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
TRADE_BUCKETS = ["0-1y", "1-3y", "3-5y", "5-7y", "7-10y", "10y+"]
UST_PILLARS = [("UST_1Y", 1.0), ("UST_2Y", 2.0), ("UST_3Y", 3.0),
               ("UST_5Y", 5.0), ("UST_7Y", 7.0), ("UST_10Y", 10.0),
               ("UST_20Y", 20.0), ("UST_30Y", 30.0)]
RATING_ORDER = ["T1", "T2", "T3", "T4", "T5"]
RATING_LABELS = {"T1": "T1·AAA", "T2": "T2·AA",
                 "T3": "T3·A",   "T4": "T4·BBB",
                 "T5": "T5·BB/NR"}
BUCKET_MIDS = {"<1y": 0.5, "1-3y": 2.0, "3-5y": 4.0,
               "5-7y": 6.0, "7-10y": 8.5, ">10y": 15.0,
               "0-1y": 0.5, "10y+": 15.0}

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
def _load_instruments() -> pd.DataFrame:
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


def _ust_at(plazo_mid: float, curve: dict[float, float]) -> float:
    if not curve:
        return float("nan")
    xs = sorted(curve.keys()); ys = [curve[x] for x in xs]
    if plazo_mid <= xs[0]: return ys[0]
    if plazo_mid >= xs[-1]: return ys[-1]
    return float(np.interp(plazo_mid, xs, ys))


# ---------------------------------------------------------------------------
def aggregate(as_of: date) -> dict:
    """Agregaciones para tablas y banner."""
    inst = _load_instruments()
    inst = inst[inst["fecha_emision"] <= pd.Timestamp(as_of)]
    inst = inst[inst["fecha_venc"] > pd.Timestamp(as_of)]
    ust = _ust_curve(as_of)

    # Tabla maestra: spread RATING × PLAZO de trades reales (últimos 6m)
    trades = _load_trades()
    cut = pd.Timestamp(as_of)
    tr = trades[(trades["fecha"] <= cut) &
                (trades["fecha"] >= cut - pd.DateOffset(months=6)) &
                trades["spread_bp"].notna() &
                trades["spread_bp"].between(-100, 2000) &
                trades["rating_tier"].isin(RATING_ORDER) &
                trades["bucket_plazo"].isin(TRADE_BUCKETS)]
    pivot_rt = (tr.groupby(["rating_tier", "bucket_plazo"])["spread_bp"]
                  .median().reset_index()
                  .pivot(index="rating_tier", columns="bucket_plazo",
                         values="spread_bp")
                  .reindex(index=RATING_ORDER, columns=TRADE_BUCKETS))
    cnt_rt = (tr.groupby(["rating_tier", "bucket_plazo"]).size()
                  .reset_index(name="n")
                  .pivot(index="rating_tier", columns="bucket_plazo",
                         values="n")
                  .reindex(index=RATING_ORDER, columns=TRADE_BUCKETS))

    # Tabla SECTOR × RATING: spread teórico (cupón emisión − UST del plazo)
    top_sectors = inst["sector"].value_counts().head(6).index.tolist()
    inst["sector_grp"] = inst["sector"].where(inst["sector"].isin(top_sectors),
                                              "Otros")
    sector_order = top_sectors + (["Otros"] if "Otros" in inst["sector_grp"].values
                                  else [])
    inst["ust_y"] = inst["plazo_anios"].apply(lambda y: _ust_at(y, ust))
    inst["spread_bp"] = (inst["tasa_pct"] - inst["ust_y"]) * 100
    inst["w"] = inst["montoSerie"].fillna(1.0).clip(lower=1.0)
    inst["spread_w"] = inst["spread_bp"] * inst["w"]
    g = (inst.groupby(["sector_grp", "rating_tier"])
              .agg(sum_sw=("spread_w", "sum"), sum_w=("w", "sum"),
                   n=("isin", "size"))
              .reset_index())
    g["spread_avg"] = g["sum_sw"] / g["sum_w"]
    pivot_sr = (g.pivot(index="sector_grp", columns="rating_tier",
                        values="spread_avg")
                 .reindex(index=sector_order, columns=RATING_ORDER))
    cnt_sr = (g.pivot(index="sector_grp", columns="rating_tier", values="n")
                .reindex(index=sector_order, columns=RATING_ORDER))

    # Top 10 emisiones por monto, con rating y spread
    top = (inst.sort_values("montoSerie", ascending=False).head(10).copy())
    top["plazo_anios"] = top["plazo_anios"].round(1)
    top["tasa_pct"] = top["tasa_pct"].round(2)
    top["montoSerie"] = (top["montoSerie"] / 1e6).round(1)
    top["spread_bp"] = top["spread_bp"].round(0)
    top["Vencimiento"] = top["fecha_venc"].dt.strftime("%Y-%m-%d")
    top = top.rename(columns={"sector_grp": "Sector", "rating_proxy": "Rating",
                              "plazo_anios": "Plazo (y)", "tasa_pct": "Tasa %",
                              "montoSerie": "USD MM", "spread_bp": "Spread bp"})

    msg = _build_message(pivot_rt, pivot_sr, ust, as_of)

    return {
        "pivot_rt": pivot_rt, "cnt_rt": cnt_rt,
        "pivot_sr": pivot_sr, "cnt_sr": cnt_sr,
        "ust_curve": ust, "top": top, "n_trades": int(len(tr)),
        "message": msg,
    }


def _build_message(pivot_rt, pivot_sr, ust, as_of) -> str:
    """Genera el mensaje principal de la slide a partir del corte."""
    parts = []
    t1 = pivot_rt.loc["T1"].dropna() if "T1" in pivot_rt.index else pd.Series()
    t2 = pivot_rt.loc["T2"].dropna() if "T2" in pivot_rt.index else pd.Series()
    t3 = pivot_rt.loc["T3"].dropna() if "T3" in pivot_rt.index else pd.Series()
    if not t1.empty and not t3.empty:
        parts.append(f"Diferencial T3·A − T1·AAA: ~{(t3.median()-t1.median()):.0f} bps")
    if not t2.empty:
        parts.append(f"T2·AA paga {t2.min():.0f}–{t2.max():.0f} bps según plazo")
    # Peak plazo en T3
    if not t3.empty:
        peak_bucket = t3.idxmax()
        parts.append(f"peak plazo en T3·A es {peak_bucket} ({t3.max():.0f} bps)")
    # Sector más caro vs financiero T3
    if "T3" in pivot_sr.columns:
        col = pivot_sr["T3"].dropna()
        if "Financiero" in col.index and len(col) > 1:
            others = col.drop("Financiero")
            if not others.empty:
                worst_sec = others.idxmax()
                parts.append(f"{worst_sec} T3 paga ~{(others.max()-col['Financiero']):.0f} bps "
                             f"más que Financiero al mismo rating")
    return " · ".join(parts) if parts else f"Universo Panamá-corp activo al {as_of}"


# ---------------------------------------------------------------------------
def _draw_pivot_table(ax, pivot: pd.DataFrame, cnt: pd.DataFrame | None,
                      title: str, fmt: str = "{:.0f}",
                      idx_labels: dict | None = None,
                      col_labels: dict | None = None,
                      highlight_max: bool = True) -> None:
    """Tabla numérica con valor + (n) coloreada por intensidad."""
    ax.axis("off")
    ax.set_title(title, fontsize=10.5, weight="bold", loc="left",
                 pad=4)
    rows = list(pivot.index)
    cols = list(pivot.columns)
    if idx_labels:
        rows_disp = [idx_labels.get(r, r) for r in rows]
    else:
        rows_disp = rows
    if col_labels:
        cols_disp = [col_labels.get(c, c) for c in cols]
    else:
        cols_disp = cols

    data = pivot.values.astype(float)
    cell = []
    for i in range(data.shape[0]):
        row = [rows_disp[i]]
        for j in range(data.shape[1]):
            v = data[i, j]
            if not np.isfinite(v):
                row.append("—")
            else:
                txt = fmt.format(v)
                if cnt is not None:
                    n = cnt.iloc[i, j]
                    if np.isfinite(n):
                        txt += f"\n(n={int(n)})"
                row.append(txt)
        cell.append(row)
    header = [""] + cols_disp

    tbl = ax.table(cellText=cell, colLabels=header,
                   cellLoc="center", loc="upper left",
                   bbox=[0.0, 0.0, 1.0, 0.92])
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5)
    for j in range(len(header)):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    # Color first column (row labels)
    for i in range(1, len(cell) + 1):
        tbl[i, 0].set_facecolor("#e8eff7")
        tbl[i, 0].set_text_props(weight="bold")
    # Color cells by intensity (RdYlBu_r)
    vmin = np.nanmin(data); vmax = np.nanmax(data)
    if np.isfinite(vmin) and np.isfinite(vmax) and vmax > vmin:
        cmap = plt.get_cmap("RdYlBu_r")
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                v = data[i, j]
                if np.isfinite(v):
                    norm = (v - vmin) / (vmax - vmin)
                    rgba = cmap(0.20 + 0.6 * norm)
                    tbl[i + 1, j + 1].set_facecolor(rgba)


def plot_l_pa_1(as_of: date, output_path: Path | str,
                figsize=(15, 10), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    a = aggregate(as_of)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 2, height_ratios=[0.32, 1.15, 1.15],
                          hspace=0.40, wspace=0.10)
    ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
    ax_t1 = fig.add_subplot(gs[1, 0])
    ax_t2 = fig.add_subplot(gs[1, 1])
    ax_top = fig.add_subplot(gs[2, :]); ax_top.axis("off")

    # Mensaje principal autogenerado
    ax_msg.text(0.5, 0.5,
                "MENSAJE PRINCIPAL · " + a["message"],
                ha="center", va="center", fontsize=11.5, weight="bold",
                color="#0d1b2a", wrap=True,
                bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.6))

    # Tabla 1: SPREAD por RATING × PLAZO (trades últimos 6m)
    _draw_pivot_table(
        ax_t1, a["pivot_rt"], a["cnt_rt"],
        f"Spread mediano (bps) · RATING × PLAZO · {a['n_trades']:,} trades últimos 6m",
        fmt="{:.0f}", idx_labels=RATING_LABELS)

    # Tabla 2: SPREAD por SECTOR × RATING (emisiones activas)
    _draw_pivot_table(
        ax_t2, a["pivot_sr"], a["cnt_sr"],
        "Spread promedio (bps) · SECTOR × RATING · emisiones activas",
        fmt="{:.0f}", col_labels=RATING_LABELS)

    # Top emisiones
    ax_top.set_title("Top 10 emisiones activas por monto",
                     fontsize=10.5, weight="bold", loc="left")
    cols = ["ISIN", "Emisor", "Sector", "Rating", "Plazo (y)",
            "Tasa %", "Spread bp", "USD MM", "Vencimiento"]
    if not a["top"].empty:
        cell = a["top"][["isin", "emisor", "Sector", "Rating", "Plazo (y)",
                         "Tasa %", "Spread bp", "USD MM",
                         "Vencimiento"]].values.tolist()
        tbl = ax_top.table(cellText=cell, colLabels=cols,
                           cellLoc="center", loc="upper center",
                           bbox=[0.0, 0.0, 1.0, 0.88])
        tbl.auto_set_font_size(False); tbl.set_fontsize(8.0)
        for j in range(len(cols)):
            tbl[0, j].set_facecolor("#2a6fb3")
            tbl[0, j].set_text_props(color="white", weight="bold")

    fig.suptitle(f"Panamá corporate — spread por crédito · sector · plazo "
                 f"· corte {as_of}", fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005,
             "Spreads en bps vs UST del plazo correspondiente. "
             "Rating: proxy V0 (escala Panamá local; reemplazable por dump "
             "oficial). Soberano + CDS pendientes plantilla BBG v0.3. "
             + DISCLAIMER,
             ha="center", fontsize=7.0, style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
