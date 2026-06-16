"""L_PA_1 — Panamá corporate: heatmap sector × plazo + spread vs UST.

Datos: `data/raw/emisiones_activas.json` (Latinex, 2,573 emisiones).

Filtros aplicados:
  - Instrumentos de deuda (BONOS, BONOS HIPOTECARIOS, NOTAS CORPORATIVAS,
    SVS-BONOS). Excluye acciones / fondos / letras del tesoro.
  - Tipo de tasa FIJA (los variables no son comparables sin conocer el
    spread sobre lo que pagan).
  - Tasa > 0 (descarta registros incompletos).
  - País Panamá.

Bucketización:
  - Plazo (años desde fechaEmision a fechaVencimiento):
       <1y · 1-3y · 3-5y · 5-7y · 7-10y · >10y
  - Sectores: top 8 con más emisiones; el resto a "Otros".

Spread vs UST: tasa promedio Panamá-corp por bucket plazo − yield UST
del tenor más cercano al cierre del mes corte. Panamá en moneda USD-
paritaria, por eso la resta directa es spread comparable.

FRONTERA HONESTA:
  - **Rating**: no está en los datos de Latinex. Requiere dataset interno
    cruzado con calificaciones (Fitch Panamá / Equilibrium / PCR). Lo
    dejamos como dimensión pendiente; este slide cubre sector × plazo.
  - **Soberano Panamá**: necesita plantilla BBG v0.3 (PANAMA Govt + CDS).
  - **Cambio 12m del heatmap**: requiere snapshot histórico de emisiones
    activas hace un año; los snapshots actuales son point-in-time. Pendiente.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

EMISIONES_JSON = Path("data/raw/emisiones_activas.json")
BLOOMBERG_PARQUET = Path("data/external/tasas_mercantil/bloomberg_historico.parquet")

DEBT_INSTRUMENTS = {"BONOS", "BONOS HIPOTECARIOS", "NOTAS CORPORATIVAS",
                    "SVS - BONOS"}
TENOR_BINS = [(0, 1, "<1y"), (1, 3, "1-3y"), (3, 5, "3-5y"),
              (5, 7, "5-7y"), (7, 10, "7-10y"), (10, 100, ">10y")]
# Tenors UST disponibles para spread
UST_PILLARS = [("UST_1Y", 1.0), ("UST_2Y", 2.0), ("UST_3Y", 3.0),
               ("UST_5Y", 5.0), ("UST_7Y", 7.0), ("UST_10Y", 10.0),
               ("UST_20Y", 20.0), ("UST_30Y", 30.0)]

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


def _load_emisiones() -> pd.DataFrame:
    data = json.load(open(EMISIONES_JSON))["data"]
    df = pd.DataFrame(data)
    df = df[df["pais"] == "Panamá"].copy()
    df = df[df["instrumento"].isin(DEBT_INSTRUMENTS)]
    df = df[df["tipoTasa"] == "FIJA"]
    df["tasa"] = pd.to_numeric(df["tasa"], errors="coerce")
    df = df[df["tasa"].notna() & (df["tasa"] > 0)]
    df["fecha_emision"] = pd.to_datetime(df["fechaEmision"], format="%d/%m/%Y",
                                         errors="coerce")
    df["fecha_venc"] = pd.to_datetime(df["fechaVencimiento"], format="%d/%m/%Y",
                                      errors="coerce")
    df = df[df["fecha_emision"].notna() & df["fecha_venc"].notna()]
    df["plazo_anios"] = ((df["fecha_venc"] - df["fecha_emision"]).dt.days
                         / 365.25)
    df = df[df["plazo_anios"] > 0]
    df["montoSerie"] = pd.to_numeric(df["montoSerie"], errors="coerce")
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


def aggregate_corp(as_of: date) -> tuple[pd.DataFrame, pd.DataFrame,
                                         dict[float, float], pd.DataFrame]:
    """Retorna (heatmap_tasa, heatmap_count, ust_curve, top_emisiones)."""
    df = _load_emisiones()
    df = df[df["fecha_emision"] <= pd.Timestamp(as_of)]
    df = df[df["fecha_venc"] > pd.Timestamp(as_of)]
    df["bucket"] = df["plazo_anios"].apply(_bucket_plazo)
    df = df.dropna(subset=["bucket"])

    # Top 8 sectores por # emisiones, resto agrupado
    top_sectors = df["sector"].value_counts().head(8).index.tolist()
    df["sector_grp"] = df["sector"].where(df["sector"].isin(top_sectors),
                                          "Otros")

    bucket_order = [b[2] for b in TENOR_BINS]
    sector_order = top_sectors + (["Otros"] if "Otros" in df["sector_grp"].values
                                  else [])

    # Tasa promedio ponderada por montoSerie
    df["w"] = df["montoSerie"].fillna(1.0).clip(lower=1.0)
    df["wt_tasa"] = df["tasa"] * df["w"]
    g = (df.groupby(["sector_grp", "bucket"])
            .agg(sum_wt=("wt_tasa", "sum"), sum_w=("w", "sum"),
                 count=("isin", "size"))
            .reset_index())
    g["tasa_avg"] = g["sum_wt"] / g["sum_w"]

    heatmap_tasa = g.pivot(index="sector_grp", columns="bucket",
                           values="tasa_avg").reindex(index=sector_order,
                                                      columns=bucket_order)
    heatmap_count = g.pivot(index="sector_grp", columns="bucket",
                            values="count").reindex(index=sector_order,
                                                    columns=bucket_order)

    ust_curve = _ust_curve(as_of)

    # Top 10 emisiones por monto, para contexto
    top = (df.sort_values("montoSerie", ascending=False).head(10)
           [["isin", "emisor", "sector_grp", "plazo_anios", "tasa",
             "montoSerie", "fecha_venc"]].copy())
    top["plazo_anios"] = top["plazo_anios"].round(1)
    top["tasa"] = top["tasa"].round(2)
    top["montoSerie"] = (top["montoSerie"] / 1e6).round(1)
    top = top.rename(columns={"plazo_anios": "Plazo", "tasa": "Tasa %",
                              "montoSerie": "USD MM", "fecha_venc": "Venc",
                              "sector_grp": "Sector"})
    top["Venc"] = top["Venc"].dt.strftime("%Y-%m-%d")
    return heatmap_tasa, heatmap_count, ust_curve, top


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def plot_l_pa_1(as_of: date, output_path: Path | str,
                figsize=(14, 9), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    h_tasa, h_count, ust_curve, top = aggregate_corp(as_of)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(2, 2, width_ratios=[2.0, 1.4],
                          height_ratios=[1.6, 1.0], hspace=0.42, wspace=0.18)
    ax_hm = fig.add_subplot(gs[0, 0])
    ax_spread = fig.add_subplot(gs[0, 1])
    ax_tbl = fig.add_subplot(gs[1, :])
    ax_tbl.axis("off")

    # --- Heatmap principal ---
    data = h_tasa.values
    vmin = np.nanmin(data); vmax = np.nanmax(data)
    cmap = plt.get_cmap("YlOrRd")
    im = ax_hm.imshow(data, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax_hm.set_xticks(np.arange(len(h_tasa.columns)))
    ax_hm.set_xticklabels(h_tasa.columns, fontsize=9)
    ax_hm.set_yticks(np.arange(len(h_tasa.index)))
    ax_hm.set_yticklabels(h_tasa.index, fontsize=9)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            n = h_count.iloc[i, j]
            if np.isfinite(v):
                color = "white" if v > (vmin + vmax) / 2 else "black"
                ax_hm.text(j, i, f"{v:.2f}%\n(n={int(n)})",
                           ha="center", va="center", fontsize=7.5,
                           color=color)
    ax_hm.set_title("Tasa promedio ponderada Panamá-corp (FIJA, deuda activa)"
                    " · sector × plazo",
                    fontsize=11, weight="bold")
    cbar = fig.colorbar(im, ax=ax_hm, shrink=0.85, pad=0.02)
    cbar.set_label("Tasa %", fontsize=8)
    cbar.ax.tick_params(labelsize=7.5)

    # --- Spread vs UST por plazo (línea agregada) ---
    bucket_mids = {"<1y": 0.5, "1-3y": 2.0, "3-5y": 4.0, "5-7y": 6.0,
                   "7-10y": 8.5, ">10y": 15.0}
    rows = []
    for bucket in h_tasa.columns:
        col = h_tasa[bucket].dropna()
        if col.empty:
            continue
        cnts = h_count[bucket].dropna()
        # promedio ponderado por count
        common = col.index.intersection(cnts.index)
        if len(common) == 0:
            continue
        w = cnts.loc[common].values
        v = col.loc[common].values
        avg_corp = float(np.average(v, weights=w))
        ust_y = _ust_at(bucket_mids[bucket], ust_curve)
        spread = (avg_corp - ust_y) * 100  # bps
        rows.append({"bucket": bucket, "mid": bucket_mids[bucket],
                     "corp": avg_corp, "ust": ust_y, "spread_bps": spread})
    sp_df = pd.DataFrame(rows)

    ax_spread.bar(np.arange(len(sp_df)), sp_df["spread_bps"],
                  color="#2a6fb3", alpha=0.85)
    for i, v in enumerate(sp_df["spread_bps"]):
        ax_spread.text(i, v + max(sp_df["spread_bps"]) * 0.02,
                       f"{v:+.0f}", ha="center", fontsize=8.5, weight="bold")
    ax_spread.set_xticks(np.arange(len(sp_df)))
    ax_spread.set_xticklabels(sp_df["bucket"], fontsize=9)
    ax_spread.set_ylabel("Spread vs UST (bps)", fontsize=9)
    ax_spread.set_title("Spread agregado Panamá-corp vs UST · por plazo",
                        fontsize=11, weight="bold")
    ax_spread.grid(True, axis="y", alpha=0.3); ax_spread.set_axisbelow(True)
    ax_spread.axhline(0, color="black", lw=0.6, alpha=0.5)

    # --- Tabla top emisiones ---
    ax_tbl.set_title("Top 10 emisiones activas por monto (FIJA)",
                     fontsize=11, weight="bold", loc="left")
    if not top.empty:
        cell = top[["isin", "emisor", "Sector", "Plazo", "Tasa %",
                    "USD MM", "Venc"]].values.tolist()
        cols = ["ISIN", "Emisor", "Sector", "Plazo (y)", "Tasa %",
                "Monto (USD MM)", "Vencimiento"]
        tbl = ax_tbl.table(cellText=cell, colLabels=cols,
                           cellLoc="center", loc="upper center",
                           bbox=[0.0, 0.0, 1.0, 0.92])
        tbl.auto_set_font_size(False); tbl.set_fontsize(8.0)
        for j in range(len(cols)):
            tbl[0, j].set_facecolor("#2a6fb3")
            tbl[0, j].set_text_props(color="white", weight="bold")

    fig.suptitle(f"Panamá corporate — radiografía sector × plazo "
                 f"· corte {as_of}", fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005,
             "Dimensión rating pendiente (dataset interno). "
             "Soberano + CDS pendientes (plantilla BBG v0.3). " + DISCLAIMER,
             ha="center", fontsize=7.5, style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
