"""L_USA_0 — La combinación WIRP + Taylor (Mercantil v0.3.0): backtest 2010-2024.

Primera slide del bloque USA. Demuestra **por qué combinamos**: ni el mercado
solo (WIRP/Pieza A) ni la regla simple sola (Taylor/Pieza B) son robustos
en todos los regímenes. La combinación 55%/45% reduce el riesgo de los
casos donde una de las dos se equivoca mucho.

Backtest: `data/external/tasas_mercantil/fed_funds_benchmark_v2.parquet`
180 cortes mensuales 2010-01 a 2024-12, horizonte 6m.

Paneles:
  (1) Serie temporal: predict A, B, M (Mercantil) vs realized.
  (2) MAE por régimen (CALMA vs MOVIMIENTO) — la robustez de Mercantil.
  (3) Distribución de errores absolutos por modelo (Mercantil tiene
      menos cola derecha = menos errores catastróficos).
  (4) Tabla "ranking": % de veces cada modelo es el mejor / el peor.

Mensaje central: combinar no garantiza ser el mejor en cada corte; garantiza
**casi nunca ser el peor**. Esa es la ventaja: reduce el riesgo de
seleccionar el predictor equivocado para el régimen actual.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BACKTEST = Path("data/external/tasas_mercantil/fed_funds_benchmark_v2.parquet")
W_A, W_B = 0.55, 0.45

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
def _load_backtest() -> pd.DataFrame:
    df = pd.read_parquet(BACKTEST).copy()
    df["as_of"] = pd.to_datetime(df["as_of"])
    df = df.sort_values("as_of").reset_index(drop=True)
    df["predict_M_pct"] = W_A * df["predict_A_pct"] + W_B * df["predict_B_pct"]
    df["realized_pct"] = df["realized_A_pct"]
    df["abs_err_M_bps"] = (df["predict_M_pct"] - df["realized_pct"]).abs() * 100
    df["abs_err_naive_bps"] = (df["fed_now_pct"] - df["realized_pct"]).abs() * 100
    return df


def _rank_summary(df: pd.DataFrame) -> dict:
    cols = ["abs_err_A_bps", "abs_err_B_bps", "abs_err_M_bps"]
    e = df[cols].values
    is_best = (e == e.min(axis=1, keepdims=True))
    is_worst = (e == e.max(axis=1, keepdims=True))
    n = len(df)
    return {
        "A_best_pct":  is_best[:, 0].mean() * 100,
        "B_best_pct":  is_best[:, 1].mean() * 100,
        "M_best_pct":  is_best[:, 2].mean() * 100,
        "A_worst_pct": is_worst[:, 0].mean() * 100,
        "B_worst_pct": is_worst[:, 1].mean() * 100,
        "M_worst_pct": is_worst[:, 2].mean() * 100,
        "M_better_than_worst": (df["abs_err_M_bps"] <
                                df[["abs_err_A_bps", "abs_err_B_bps"]]
                                .max(axis=1)).mean() * 100,
        "n": n,
    }


# ---------------------------------------------------------------------------
def plot_l_usa_0(as_of: date, output_path: Path | str,
                 figsize=(15, 9), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _load_backtest()
    r = _rank_summary(df)

    # Mensaje principal autogenerado
    mae_a = df["abs_err_A_bps"].median()
    mae_b = df["abs_err_B_bps"].median()
    mae_m = df["abs_err_M_bps"].median()
    msg = (f"Mercantil v0.3.0 (55% WIRP + 45% Taylor) es el peor en SOLO "
           f"{r['M_worst_pct']:.0f}% de los cortes vs {r['A_worst_pct']:.0f}% A "
           f"sola y {r['B_worst_pct']:.0f}% B sola · "
           f"mejor que el peor de A,B en {r['M_better_than_worst']:.0f}% de los "
           f"cortes · MAE mediana 6m: {mae_m:.0f} bps")

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 3, height_ratios=[0.20, 1.10, 1.00],
                          width_ratios=[1.6, 1.1, 1.1],
                          hspace=0.45, wspace=0.32)
    ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
    ax_ts = fig.add_subplot(gs[1, :])
    ax_reg = fig.add_subplot(gs[2, 0])
    ax_hist = fig.add_subplot(gs[2, 1])
    ax_tbl = fig.add_subplot(gs[2, 2])
    ax_tbl.axis("off")

    ax_msg.text(0.5, 0.5, "MENSAJE PRINCIPAL · " + msg,
                ha="center", va="center", fontsize=11.5, weight="bold",
                color="#0d1b2a", wrap=True,
                bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.6))

    # (1) Serie temporal: predict A, B, M vs realized
    ax_ts.plot(df["as_of"], df["realized_pct"] * 100,
               color="black", lw=2.0, label="Realized Fed Funds (6m fwd)",
               zorder=4)
    ax_ts.plot(df["as_of"], df["predict_A_pct"] * 100,
               color="#2a6fb3", lw=1.0, ls=(0, (5, 2)), alpha=0.75,
               label=f"Pieza A · WIRP/Mercado (peso {W_A:.0%})")
    ax_ts.plot(df["as_of"], df["predict_B_pct"] * 100,
               color="#b32a2a", lw=1.0, ls=(0, (5, 2)), alpha=0.75,
               label=f"Pieza B · Taylor (peso {W_B:.0%})")
    ax_ts.plot(df["as_of"], df["predict_M_pct"] * 100,
               color="#0d1b2a", lw=2.0,
               label="Mercantil v0.3.0 (55% A + 45% B)")

    # Sombrear MOVIMIENTO en gris claro
    mov = df[df["regimen"] == "MOVIMIENTO"]
    if not mov.empty:
        # Detectar bloques contiguos
        d = mov["as_of"].values
        groups = np.split(d, np.where(np.diff(d) > np.timedelta64(45, "D"))[0] + 1)
        for g in groups:
            if len(g) > 0:
                ax_ts.axvspan(g.min(), g.max(), color="#fff5e6", alpha=0.55,
                              zorder=0)

    ax_ts.set_title("Backtest 2010–2024 · 180 cortes mensuales · "
                    "horizonte 6 meses",
                    fontsize=12, weight="bold")
    ax_ts.set_ylabel("Fed Funds (%)", fontsize=9.5)
    ax_ts.grid(True, alpha=0.3); ax_ts.set_axisbelow(True)
    ax_ts.legend(loc="upper left", fontsize=8.5, framealpha=0.95,
                 ncol=2)
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(2))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_ts.tick_params(axis="x", labelsize=9)
    ax_ts.text(0.99, 0.04, "Sombreado: régimen MOVIMIENTO (hike/cut)",
               transform=ax_ts.transAxes, ha="right", fontsize=7.5,
               style="italic", color="#888")

    # (2) MAE por régimen
    regs = ["CALMA", "MOVIMIENTO"]
    mae_by = []
    for reg in regs:
        sub = df[df["regimen"] == reg]
        mae_by.append([sub["abs_err_A_bps"].median(),
                       sub["abs_err_B_bps"].median(),
                       sub["abs_err_M_bps"].median(),
                       sub["abs_err_naive_bps"].median()])
    mae_arr = np.array(mae_by)
    x = np.arange(len(regs))
    w = 0.20
    colors = ["#2a6fb3", "#b32a2a", "#0d1b2a", "#888"]
    labels = ["A (mercado)", "B (Taylor)", "Mercantil", "Naive (spot)"]
    for i, (col, lab) in enumerate(zip(colors, labels)):
        bars = ax_reg.bar(x + (i - 1.5) * w, mae_arr[:, i], w,
                          color=col, label=lab)
        for b, v in zip(bars, mae_arr[:, i]):
            ax_reg.text(b.get_x() + b.get_width() / 2, v + 0.5,
                        f"{v:.0f}", ha="center", fontsize=7.5)
    ax_reg.set_xticks(x); ax_reg.set_xticklabels(regs)
    ax_reg.set_ylabel("MAE mediano (bps)", fontsize=9)
    ax_reg.set_title("Error mediano por régimen",
                     fontsize=11, weight="bold")
    ax_reg.legend(loc="upper left", fontsize=7.5, framealpha=0.95)
    ax_reg.grid(True, axis="y", alpha=0.3); ax_reg.set_axisbelow(True)

    # (3) Histograma de errores absolutos (cola derecha = errores grandes)
    for col, lab, color in [
        ("abs_err_A_bps", "A · WIRP",     "#2a6fb3"),
        ("abs_err_B_bps", "B · Taylor",   "#b32a2a"),
        ("abs_err_M_bps", "Mercantil",    "#0d1b2a"),
    ]:
        ax_hist.hist(df[col].clip(upper=100), bins=20,
                     alpha=0.45, color=color, label=lab, edgecolor="white")
    ax_hist.set_title("Distribución de errores absolutos",
                      fontsize=11, weight="bold")
    ax_hist.set_xlabel("|error| (bps, cap 100)", fontsize=9)
    ax_hist.set_ylabel("frecuencia", fontsize=9)
    ax_hist.legend(loc="upper right", fontsize=8, framealpha=0.95)
    ax_hist.grid(True, axis="y", alpha=0.3); ax_hist.set_axisbelow(True)

    # (4) Tabla ranking
    rows = [
        ["Modelo",      "% mejor", "% peor", "MAE mediana (bps)"],
        ["A · WIRP",    f"{r['A_best_pct']:.0f}%", f"{r['A_worst_pct']:.0f}%",
                        f"{df['abs_err_A_bps'].median():.1f}"],
        ["B · Taylor",  f"{r['B_best_pct']:.0f}%", f"{r['B_worst_pct']:.0f}%",
                        f"{df['abs_err_B_bps'].median():.1f}"],
        ["Mercantil",   f"{r['M_best_pct']:.0f}%", f"{r['M_worst_pct']:.0f}%",
                        f"{df['abs_err_M_bps'].median():.1f}"],
    ]
    tbl = ax_tbl.table(cellText=rows[1:], colLabels=rows[0],
                       loc="upper center", cellLoc="center",
                       bbox=[0.0, 0.40, 1.0, 0.55])
    tbl.auto_set_font_size(False); tbl.set_fontsize(9.0)
    for j in range(len(rows[0])):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    # Highlight Mercantil row
    for j in range(len(rows[0])):
        tbl[3, j].set_facecolor("#e8eff7")
        tbl[3, j].set_text_props(weight="bold")

    ax_tbl.text(0.5, 0.30,
                f"Mercantil es mejor que el PEOR de A,B en\n"
                f"el {r['M_better_than_worst']:.0f}% de los cortes",
                ha="center", va="center", fontsize=10, weight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.4),
                transform=ax_tbl.transAxes)
    ax_tbl.set_title("Ranking de modelos (n=180)", fontsize=11, weight="bold")

    # Mensaje central
    fig.suptitle(
        "El modelo Mercantil combina mercado (WIRP) + regla (Taylor): "
        "no siempre es el mejor, pero casi nunca es el peor",
        fontsize=13.5, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.96))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
