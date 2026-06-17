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

    # Mensaje principal en castellano descriptivo
    mae_m = df["abs_err_M_bps"].median()
    msg = (
        f"Por qué usamos un modelo combinado en vez de elegir una sola fuente: "
        f"al juntar lo que dice el mercado de futuros con la regla de la tasa "
        f"de equilibrio (Taylor), el modelo combinado acierta más. En los "
        f"últimos 15 años solo {r['M_worst_pct']:.0f} de cada 100 meses fue "
        f"la peor predicción, mientras que el mercado solo lo fue "
        f"{r['A_worst_pct']:.0f} veces y la regla de Taylor sola "
        f"{r['B_worst_pct']:.0f}. En la mayoría de los meses "
        f"({r['M_better_than_worst']:.0f}%) el modelo combinado fue mejor que "
        f"la peor de las dos fuentes por separado."
    )

    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 3, height_ratios=[0.28, 1.10, 1.00],
                          width_ratios=[1.6, 1.1, 1.1],
                          hspace=0.45, wspace=0.32)
    ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
    ax_ts = fig.add_subplot(gs[1, :])
    ax_reg = fig.add_subplot(gs[2, 0])
    ax_hist = fig.add_subplot(gs[2, 1])
    ax_tbl = fig.add_subplot(gs[2, 2])
    ax_tbl.axis("off")

    ax_msg.text(0.5, 0.5, msg,
                ha="center", va="center", fontsize=11.0,
                color="#0d1b2a", wrap=True,
                bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.6))

    # (1) Serie temporal: predict A, B, M vs realized
    ax_ts.plot(df["as_of"], df["realized_pct"] * 100,
               color="black", lw=2.0,
               label="Tasa Fed que efectivamente ocurrió",
               zorder=4)
    ax_ts.plot(df["as_of"], df["predict_A_pct"] * 100,
               color="#2a6fb3", lw=1.0, ls=(0, (5, 2)), alpha=0.75,
               label=f"Lo que decía el mercado de futuros (peso {W_A:.0%})")
    ax_ts.plot(df["as_of"], df["predict_B_pct"] * 100,
               color="#b32a2a", lw=1.0, ls=(0, (5, 2)), alpha=0.75,
               label=f"Lo que decía la regla de Taylor (peso {W_B:.0%})")
    ax_ts.plot(df["as_of"], df["predict_M_pct"] * 100,
               color="#0d1b2a", lw=2.0,
               label="Modelo combinado (mercado + Taylor)")

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

    ax_ts.set_title("Comparación de las tres predicciones contra lo que pasó "
                    "(180 meses entre 2010 y 2024)",
                    fontsize=11, weight="bold")
    ax_ts.set_ylabel("Tasa Fed (%)", fontsize=9.5)
    ax_ts.grid(True, alpha=0.3); ax_ts.set_axisbelow(True)
    ax_ts.legend(loc="upper left", fontsize=8.5, framealpha=0.95,
                 ncol=2)
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(2))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax_ts.tick_params(axis="x", labelsize=9)
    ax_ts.text(0.99, 0.04, "Zona sombreada: meses con subidas o bajadas de tasa",
               transform=ax_ts.transAxes, ha="right", fontsize=7.5,
               style="italic", color="#888")

    # (2) Error promedio por régimen
    regs = ["Tasa estable", "Tasa cambiando"]
    raw_regs = ["CALMA", "MOVIMIENTO"]
    mae_by = []
    for reg in raw_regs:
        sub = df[df["regimen"] == reg]
        mae_by.append([sub["abs_err_A_bps"].median(),
                       sub["abs_err_B_bps"].median(),
                       sub["abs_err_M_bps"].median(),
                       sub["abs_err_naive_bps"].median()])
    mae_arr = np.array(mae_by)
    x = np.arange(len(regs))
    w = 0.20
    colors = ["#2a6fb3", "#b32a2a", "#0d1b2a", "#888"]
    labels = ["Mercado de futuros", "Regla de Taylor",
              "Modelo combinado", "Suponer sin cambios"]
    for i, (col, lab) in enumerate(zip(colors, labels)):
        bars = ax_reg.bar(x + (i - 1.5) * w, mae_arr[:, i], w,
                          color=col, label=lab)
        for b, v in zip(bars, mae_arr[:, i]):
            ax_reg.text(b.get_x() + b.get_width() / 2, v + 0.5,
                        f"{v:.0f}", ha="center", fontsize=7.5)
    ax_reg.set_xticks(x); ax_reg.set_xticklabels(regs)
    ax_reg.set_ylabel("Error típico (centésimas de %)", fontsize=9)
    ax_reg.set_title("Qué tan grande es el error típico\n"
                     "según el momento del ciclo",
                     fontsize=10.5, weight="bold")
    ax_reg.legend(loc="upper left", fontsize=7.0, framealpha=0.95)
    ax_reg.grid(True, axis="y", alpha=0.3); ax_reg.set_axisbelow(True)

    # (3) Distribución de tamaño de errores
    for col, lab, color in [
        ("abs_err_A_bps", "Mercado de futuros", "#2a6fb3"),
        ("abs_err_B_bps", "Regla de Taylor",   "#b32a2a"),
        ("abs_err_M_bps", "Modelo combinado",  "#0d1b2a"),
    ]:
        ax_hist.hist(df[col].clip(upper=100), bins=20,
                     alpha=0.45, color=color, label=lab, edgecolor="white")
    ax_hist.set_title("Cuántas veces los errores fueron\n"
                      "chicos o grandes (en 180 meses)",
                      fontsize=10.5, weight="bold")
    ax_hist.set_xlabel("Tamaño del error (centésimas de %)", fontsize=9)
    ax_hist.set_ylabel("Cantidad de meses", fontsize=9)
    ax_hist.legend(loc="upper right", fontsize=8, framealpha=0.95)
    ax_hist.grid(True, axis="y", alpha=0.3); ax_hist.set_axisbelow(True)

    # (4) Tabla ranking en castellano
    rows = [
        ["Fuente", "Veces que fue\nla más certera",
         "Veces que fue\nla más errada", "Error típico"],
        ["Mercado de futuros",
         f"{r['A_best_pct']:.0f} de cada 100",
         f"{r['A_worst_pct']:.0f} de cada 100",
         f"{df['abs_err_A_bps'].median():.0f} centésimas"],
        ["Regla de Taylor",
         f"{r['B_best_pct']:.0f} de cada 100",
         f"{r['B_worst_pct']:.0f} de cada 100",
         f"{df['abs_err_B_bps'].median():.0f} centésimas"],
        ["Modelo combinado",
         f"{r['M_best_pct']:.0f} de cada 100",
         f"{r['M_worst_pct']:.0f} de cada 100",
         f"{df['abs_err_M_bps'].median():.0f} centésimas"],
    ]
    tbl = ax_tbl.table(cellText=rows[1:], colLabels=rows[0],
                       loc="upper center", cellLoc="center",
                       bbox=[0.0, 0.42, 1.0, 0.55])
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.0)
    for j in range(len(rows[0])):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    for j in range(len(rows[0])):
        tbl[3, j].set_facecolor("#e8eff7")
        tbl[3, j].set_text_props(weight="bold")

    ax_tbl.text(0.5, 0.30,
                f"El modelo combinado fue mejor que la peor\n"
                f"de las dos fuentes en {r['M_better_than_worst']:.0f} de cada 100 meses",
                ha="center", va="center", fontsize=9, weight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.4),
                transform=ax_tbl.transAxes)
    ax_tbl.set_title("Resumen de aciertos y errores", fontsize=10.5, weight="bold")

    # Título principal en castellano descriptivo
    fig.suptitle(
        "Por qué el modelo combina dos fuentes: no siempre es la mejor "
        "predicción, pero casi nunca es la peor",
        fontsize=13.5, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.96))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
