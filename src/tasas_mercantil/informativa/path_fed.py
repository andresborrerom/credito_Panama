"""L_USA_2 — Path Fed Funds multi-fuente.

Compara, en los horizontes 1m/3m/6m/12m/24m:
  - Pieza A (implied path SR3 — el mercado, equivalente a WIRP)
  - Pieza B (Taylor rule con R* dinámico)
  - Mercantil v0.3.0 (55% A + 45% B — combinación validada con +18%-+46% skill)
  - Sentiment EODHD TLT como "termómetro" lateral (no como traza forecasting)

Trazas pendientes que aparecerán cuando estén los datos:
  - NY Fed Primary Dealer Survey (PDF semestral)
  - ECFC Bloomberg (encuesta economistas, plantilla v0.3)
  - LLM semántico sobre top headlines (futuro)

Lección Mercantil v0.3.0 encarnada: la señal está en el desacuerdo entre
mercado (A) y modelo simple (B). La combinación pesa más cuando coinciden.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.modelo.aggregate import compute_mercantil_aggregate

HORIZONS_M = [1, 3, 6, 12, 24]
SENTIMENT_PARQUET = Path("data/external/tasas_mercantil/news_sentiment_monthly.parquet")
DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
# Sentiment TLT — termómetro
# ---------------------------------------------------------------------------
def tlt_sentiment_snapshot(as_of: date, lookback_months: int = 24) -> dict:
    """Sentiment polarity de TLT.US: valor reciente vs histórico.

    Sentiment alto (>0.5) → optimismo sobre bonos largos → mercado descuenta
    cuts agresivos (yields bajos). Sentiment bajo → pesimismo → más Fed
    hawkish o miedo de inflación. Lectura cualitativa.
    """
    out = {"value": np.nan, "mean": np.nan, "std": np.nan, "z": np.nan,
           "n_obs": 0, "delta_3m": np.nan, "label": "n/a"}
    if not SENTIMENT_PARQUET.exists():
        return out
    df = pd.read_parquet(SENTIMENT_PARQUET)
    tlt = df[df["symbol"] == "TLT.US"].copy()
    if tlt.empty:
        return out
    tlt["yyyymm"] = pd.to_datetime(tlt["yyyymm"])
    cut = pd.Timestamp(as_of)
    hist = tlt[tlt["yyyymm"] <= cut].sort_values("yyyymm")
    if hist.empty:
        return out
    last = hist.iloc[-1]
    sel = hist.tail(lookback_months)
    mean = float(sel["sentiment_mean"].mean())
    std = float(sel["sentiment_mean"].std(ddof=1)) if len(sel) > 1 else np.nan
    val = float(last["sentiment_mean"])
    z = (val - mean) / std if std and np.isfinite(std) and std > 0 else np.nan

    # Δ 3m: valor actual vs hace ~3 meses
    if len(hist) >= 4:
        delta_3m = val - float(hist.iloc[-4]["sentiment_mean"])
    else:
        delta_3m = np.nan

    # Etiqueta cualitativa
    if np.isfinite(z):
        if z > 1.0:    label = "Muy bullish bonos (>1σ)"
        elif z > 0.3:  label = "Bullish bonos"
        elif z < -1.0: label = "Muy bearish bonos (<-1σ)"
        elif z < -0.3: label = "Bearish bonos"
        else:          label = "Neutral"
    else:
        label = "Neutral"

    out.update({
        "value": val, "mean": mean, "std": std, "z": z,
        "n_obs": len(sel), "delta_3m": delta_3m, "label": label,
        "as_of_obs": last["yyyymm"].date(),
    })
    return out


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def plot_path_fed(as_of: date, output_path: Path | str,
                  figsize=(14, 7.5), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    store = load_master_store()
    merc = compute_mercantil_aggregate(store, as_of)

    spot = merc.fed_funds_now
    pa = merc.pieza_a
    pb = merc.pieza_b

    xs = HORIZONS_M
    a_vals = [pa.forecast_1m, pa.forecast_3m, pa.forecast_6m, pa.forecast_12m, pa.forecast_24m]
    b_vals = [pb.forecast_1m, pb.forecast_3m, pb.forecast_6m, pb.forecast_12m, pb.forecast_24m]
    m_vals = [merc.forecast_1m, merc.forecast_3m, merc.forecast_6m, merc.forecast_12m, merc.forecast_24m]

    sent = tlt_sentiment_snapshot(as_of)

    # Mensaje principal
    d12m = (merc.forecast_12m - spot) * 100
    direction = ("HIKES" if d12m > 25 else "CUTS" if d12m < -25 else "HOLD")
    msg = (f"Mercantil v0.3.0 proyecta Fed {direction} "
           f"({d12m:+.0f} bps a 12m) · Mercado (Pieza A) {(pa.forecast_12m-spot)*100:+.0f} bps · "
           f"Taylor (Pieza B) {(pb.forecast_12m-spot)*100:+.0f} bps · "
           f"Sentiment TLT: {sent['label']}")

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 3, width_ratios=[2.2, 1.1, 1.1],
                          height_ratios=[0.22, 3.0, 0.95],
                          hspace=0.35, wspace=0.28)
    ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
    ax_msg.text(0.5, 0.5, "MENSAJE PRINCIPAL · " + msg,
                ha="center", va="center", fontsize=11.5, weight="bold",
                color="#0d1b2a", wrap=True,
                bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.6))
    ax = fig.add_subplot(gs[1, 0])
    ax_sent = fig.add_subplot(gs[1, 1])
    ax_tbl = fig.add_subplot(gs[1, 2])
    ax_foot = fig.add_subplot(gs[2, :])
    ax_foot.axis("off")

    # Spot reference
    ax.axhline(spot, color="black", lw=1.0, alpha=0.6,
               label=f"Spot Fed Funds {spot:.2f}%")

    # Pieza A (mercado / WIRP)
    ax.plot(xs, a_vals, color="#2a6fb3", lw=1.8, ls=(0,(5,2)),
            marker="o", ms=6, label="Pieza A — Implied SR3 (mercado)")
    # Pieza B (Taylor)
    ax.plot(xs, b_vals, color="#b32a2a", lw=1.8, ls=(0,(5,2)),
            marker="s", ms=6, label="Pieza B — Taylor rule (R* dinámico)")
    # Mercantil agregado
    ax.plot(xs, m_vals, color="#0d1b2a", lw=2.8, marker="D", ms=7,
            label=f"Mercantil v{merc.model_version} (55%A + 45%B)")

    # Trazas pendientes — placeholder textual en la leyenda
    from matplotlib.lines import Line2D
    placeholder_handles = [
        Line2D([], [], color="#cccccc", lw=1.6, ls=":",
               label="NY Fed PD Survey · pendiente"),
        Line2D([], [], color="#cccccc", lw=1.6, ls=":",
               label="ECFC BBG · pendiente (plantilla v0.3)"),
        Line2D([], [], color="#cccccc", lw=1.6, ls=":",
               label="LLM semántico · pendiente"),
    ]
    # Combina handles
    handles_main, labels_main = ax.get_legend_handles_labels()
    ax.legend(handles=handles_main + placeholder_handles,
              loc="best", fontsize=8.2, framealpha=0.95)

    ax.set_xticks(xs)
    ax.set_xticklabels([f"{m}m" for m in xs])
    ax.set_xlabel("Horizonte", fontsize=10)
    ax.set_ylabel("Fed Funds Rate (%)", fontsize=10)
    ax.set_title("Path Fed Funds — fuentes complementarias",
                 fontsize=12, weight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    # Sentiment panel (gauge simple)
    ax_sent.axis("off")
    ax_sent.set_title("Sentiment TLT (EODHD)", fontsize=11, weight="bold")
    val = sent["value"]; z = sent["z"]; lbl = sent["label"]
    color_box = ("#1a7a1a" if (z and np.isfinite(z) and z > 0.3)
                 else "#b32a2a" if (z and np.isfinite(z) and z < -0.3) else "#888")
    txt = (f"Polarity\n{val:+.2f}\n\n"
           f"z-score 24m: {z:+.1f}σ\n"
           f"Δ vs 3m: {sent['delta_3m']:+.2f}\n\n"
           f"Lectura:\n{lbl}") if np.isfinite(val) else "n/a"
    ax_sent.text(0.5, 0.55, txt, ha="center", va="center",
                 fontsize=10, family="monospace",
                 bbox=dict(boxstyle="round,pad=0.8", facecolor="white",
                           edgecolor=color_box, linewidth=2.0))
    ax_sent.text(0.5, 0.04,
                 "Termómetro cualitativo.\nNo es predictor cuantitativo.",
                 ha="center", va="bottom", fontsize=7.5, style="italic",
                 color="#777")

    # Tabla forecasts vs spot
    ax_tbl.axis("off")
    ax_tbl.set_title("Δ vs spot (bps)", fontsize=11, weight="bold")
    rows = [["Horizon", "A", "B", "Mercantil"]]
    for i, h in enumerate(xs):
        da = (a_vals[i] - spot) * 100
        db = (b_vals[i] - spot) * 100
        dm = (m_vals[i] - spot) * 100
        rows.append([f"{h}m", f"{da:+.0f}", f"{db:+.0f}", f"{dm:+.0f}"])
    tbl = ax_tbl.table(cellText=rows[1:], colLabels=rows[0],
                       loc="center", cellLoc="center",
                       bbox=[0.0, 0.05, 1.0, 0.80])
    tbl.auto_set_font_size(False); tbl.set_fontsize(9.0)
    for j in range(4):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    # Color delta Mercantil
    for i in range(1, len(rows)):
        v = float(rows[i][3].replace("+", ""))
        c = "#dff0df" if v > 0 else "#f6dede" if v < 0 else "#f0f0f0"
        tbl[i, 3].set_facecolor(c)

    # Footer narrativa
    delta_12m = (merc.forecast_12m - spot) * 100
    direction = ("cuts" if delta_12m < -5 else "hikes" if delta_12m > 5
                 else "hold")
    skill_note = ("Skill mediano vs naive (backtest 2022-25): +18% (1m), "
                  "+24% (6m), +46% (12m). Bootstrap P(skill>0)≥99%.")
    foot = (f"Lectura: Mercantil v0.3.0 proyecta {delta_12m:+.0f} bps a 12m "
            f"({direction}). Pieza A (mercado) {((a_vals[3]-spot)*100):+.0f} bps; "
            f"Pieza B (Taylor) {((b_vals[3]-spot)*100):+.0f} bps. "
            f"Sentiment TLT: {sent['label']}.\n{skill_note}")
    ax_foot.text(0.5, 0.55, foot, ha="center", va="center",
                 fontsize=9.0, wrap=True,
                 bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f8fb",
                           edgecolor="#aaa", alpha=0.9))

    fig.suptitle(f"Fed Funds — mercado · analistas · sentiment · "
                 f"corte {as_of}",
                 fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
