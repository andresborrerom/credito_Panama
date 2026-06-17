"""Lámina 4 del deck Fase 1 USA — Curva UST.

Visualiza la curva entera de UST (3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y) con 3 trazas:
  - Cierre del año anterior (31-dic-YYYY-1)
  - Mes anterior (as_of - 1 mes, fin de mes)
  - Mes en curso (as_of, fin de mes)

Anotaciones:
  - Spreads 2s10s y 3M-2Y (cambio vs mes anterior)
  - Tabla de yields y deltas
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


CACHE = Path("data/external/tasas_mercantil")

TENORES = [
    ("US3M",  "3M",  0.25, "us3m_eom.parquet",  "US3M_INDX"),
    ("US6M",  "6M",  0.50, "us6m_eom.parquet",  "US6M_INDX"),
    ("US1Y",  "1Y",  1.00, "us1y_eom.parquet",  "US1Y_INDX"),
    ("US2Y",  "2Y",  2.00, "us2y_eom.parquet",  "US2Y_INDX"),
    ("US5Y",  "5Y",  5.00, "us5y_eom.parquet",  "US5Y_INDX"),
    ("US10Y", "10Y", 10.0, "us10y_eom.parquet", "US10Y_INDX"),
    ("US30Y", "30Y", 30.0, "us30y_eom.parquet", "US30Y_INDX"),
]


def load_curve_at(as_of: date) -> dict[str, float]:
    """Yields de la curva entera al fin del mes de as_of."""
    out = {}
    cut = pd.Timestamp(as_of)
    for tenor, _, _, fname, _ in TENORES:
        df = pd.read_parquet(CACHE / fname)
        df["date"] = pd.to_datetime(df["date"])
        hist = df[df["date"] <= cut].sort_values("date")
        if not hist.empty:
            # Primera columna no-"date"
            value_col = [c for c in df.columns if c != "date"][0]
            out[tenor] = float(hist.iloc[-1][value_col])
    return out


def plot_curva_ust(as_of: date, output_path: Path | str) -> Path:
    """Genera PNG de la lámina 4: Curva UST con 3 cortes temporales."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 3 fechas: cierre año anterior, mes anterior, as_of
    fin_ant = date(as_of.year - 1, 12, 31)
    mes_ant_pd = (pd.Timestamp(as_of) - pd.offsets.MonthEnd(1)).date()

    curve_ant = load_curve_at(fin_ant)
    curve_mes = load_curve_at(mes_ant_pd)
    curve_now = load_curve_at(as_of)

    plazos = np.array([p for _, _, p, _, _ in TENORES])
    labels = [lbl for _, lbl, _, _, _ in TENORES]

    fig, (ax_curva, ax_tabla) = plt.subplots(
        1, 2, figsize=(14, 6), dpi=130,
        gridspec_kw={"width_ratios": [2.2, 1]},
    )

    # Panel izquierdo: curva
    series = [
        (curve_ant, f"31-dic-{as_of.year - 1}", "#8b8b8b", "--", "o"),
        (curve_mes, f"Mes anterior ({mes_ant_pd})", "#2a6fb3", "-", "s"),
        (curve_now, f"Mes en curso ({as_of})",       "#b32a2a", "-", "D"),
    ]
    for curve, label, color, style, marker in series:
        ys = [curve.get(t, np.nan) for t, _, _, _, _ in TENORES]
        ax_curva.plot(plazos, ys, label=label, color=color, linestyle=style,
                       linewidth=2.0, marker=marker, markersize=7)

    ax_curva.set_xscale("log")
    ax_curva.set_xticks(plazos)
    ax_curva.set_xticklabels(labels)
    ax_curva.set_xlabel("Plazo")
    ax_curva.set_ylabel("Yield (%)")
    ax_curva.set_title(f"Curva UST — corte mensual ({as_of})",
                       fontsize=13, weight="bold")
    ax_curva.grid(True, alpha=0.3)
    ax_curva.set_axisbelow(True)
    ax_curva.legend(loc="best", fontsize=10)

    # Anotaciones de spreads
    def spread(c, a, b):
        if a in c and b in c: return c[a] - c[b]
        return None
    s_2s10s_now = spread(curve_now, "US10Y", "US2Y")
    s_2s10s_mes = spread(curve_mes, "US10Y", "US2Y")
    s_3m2y_now = spread(curve_now, "US2Y", "US3M")
    s_3m2y_mes = spread(curve_mes, "US2Y", "US3M")
    ann = []
    if s_2s10s_now is not None:
        delta = (s_2s10s_now - s_2s10s_mes) * 100 if s_2s10s_mes is not None else None
        ann.append(f"2s10s: {s_2s10s_now*100:+.0f}bps"
                   + (f" ({delta:+.0f}bps vs mes ant.)" if delta is not None else ""))
    if s_3m2y_now is not None:
        delta = (s_3m2y_now - s_3m2y_mes) * 100 if s_3m2y_mes is not None else None
        ann.append(f"3M-2Y: {s_3m2y_now*100:+.0f}bps"
                   + (f" ({delta:+.0f}bps vs mes ant.)" if delta is not None else ""))
    if ann:
        ax_curva.text(0.02, 0.02, "\n".join(ann), transform=ax_curva.transAxes,
                       fontsize=10, family="monospace",
                       verticalalignment="bottom",
                       bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                                  edgecolor="#888", alpha=0.92))

    # Panel derecho: tabla de yields y deltas
    ax_tabla.axis("off")
    rows = []
    for tenor, lbl, _, _, _ in TENORES:
        y_now = curve_now.get(tenor)
        y_mes = curve_mes.get(tenor)
        y_ant = curve_ant.get(tenor)
        if y_now is None: continue
        d_mes = (y_now - y_mes) * 100 if y_mes is not None else None
        d_ano = (y_now - y_ant) * 100 if y_ant is not None else None
        rows.append([
            lbl,
            f"{y_now:.2f}%",
            f"{d_mes:+.0f} bps" if d_mes is not None else "—",
            f"{d_ano:+.0f} bps" if d_ano is not None else "—",
        ])
    table = ax_tabla.table(
        cellText=rows,
        colLabels=["Plazo", "Yield", "Δ Mes", f"Δ {as_of.year}"],
        loc="center", cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.6)
    for i in range(len(rows) + 1):
        for j in range(4):
            cell = table[(i, j)]
            if i == 0:
                cell.set_facecolor("#2a6fb3"); cell.set_text_props(color="white", weight="bold")
            elif i % 2 == 0:
                cell.set_facecolor("#f0f4f8")
    ax_tabla.set_title("Yields y variaciones", fontsize=12, weight="bold", pad=12)

    fig.suptitle(
        f"Fase 1 USA — Lámina 4: Curva UST  ·  Corte {as_of}",
        fontsize=14, weight="bold", y=1.02,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
