"""Lámina 3 del deck Fase 1 USA — Tasas de mercado (SOFR).

Tres componentes:

Panel A — Histórico 12m de SOFR ON + SOFR 30D avg + SOFR 90D avg, con
          Fed Funds Effective overlay para visualizar el spread.

Panel B — Snapshot tabla al corte con todas las tasas SOFR + EFFR +
          spread SOFR-FFR (bps).

Panel C — Term SOFR curve 1M/3M/6M/12M como bar chart, con valores
          encima de cada barra.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from tasas_mercantil.data.store import load_master_store, FeatureNotFoundError
from tasas_mercantil.data.queries import FED_FUNDS_FEATURES


SOFR_ON_FEATURES = ["SOFR_ON", "fred_sofr"]
SOFR_30D_FEATURES = ["SOFR_30D_AVG", "fred_sofr_30d_avg"]
SOFR_90D_FEATURES = ["SOFR_90D_AVG", "fred_sofr_90d_avg"]

TERM_SOFR_TENORS = [
    ("1M",  "TERM_SOFR_1M"),
    ("3M",  "TERM_SOFR_3M"),
    ("6M",  "TERM_SOFR_6M"),
    ("12M", "TERM_SOFR_12M"),
]


def _ser(store, features: list[str], start: date, as_of: date) -> pd.Series:
    for f in features:
        try:
            s = store.get_series(f, as_of=as_of, start=start)
            if not s.empty:
                s.index = pd.to_datetime(s.index)
                return s.sort_index()
        except FeatureNotFoundError:
            continue
    return pd.Series(dtype=float)


def plot_tasas_mercado_usa(as_of: date, output_path: Path | str,
                            lookback_days: int = 365) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    store = load_master_store()
    start = as_of - timedelta(days=lookback_days)

    sofr_on = _ser(store, SOFR_ON_FEATURES, start, as_of)
    sofr_30d = _ser(store, SOFR_30D_FEATURES, start, as_of)
    sofr_90d = _ser(store, SOFR_90D_FEATURES, start, as_of)
    effr = _ser(store, FED_FUNDS_FEATURES["effective"], start, as_of)

    # Snapshots
    snap = {
        "SOFR Overnight":  float(sofr_on.iloc[-1]) if not sofr_on.empty else None,
        "SOFR 30D avg":    float(sofr_30d.iloc[-1]) if not sofr_30d.empty else None,
        "SOFR 90D avg":    float(sofr_90d.iloc[-1]) if not sofr_90d.empty else None,
        "Effective FFR":   float(effr.iloc[-1]) if not effr.empty else None,
    }
    spread_bps = ((snap["SOFR Overnight"] - snap["Effective FFR"]) * 100
                   if snap["SOFR Overnight"] is not None
                   and snap["Effective FFR"] is not None else None)

    # Term SOFR curve
    term_rows = []
    for label, feat in TERM_SOFR_TENORS:
        try:
            v = store.get_value(feat, as_of)
            term_rows.append((label, v))
        except FeatureNotFoundError:
            term_rows.append((label, None))

    # Layout: 2 columnas. Izquierda histórico (grande), derecha snap + term curve
    fig = plt.figure(figsize=(16, 8.5), dpi=130)
    gs = fig.add_gridspec(2, 2, width_ratios=[2.2, 1.0],
                            height_ratios=[1.0, 1.0],
                            wspace=0.18, hspace=0.35)
    ax_hist = fig.add_subplot(gs[:, 0])
    ax_snap = fig.add_subplot(gs[0, 1])
    ax_curve = fig.add_subplot(gs[1, 1])

    # Panel A histórico
    ax_hist.plot(sofr_on.index, sofr_on.values, color="#2a6fb3", lw=1.6,
                  label="SOFR Overnight")
    ax_hist.plot(sofr_30d.index, sofr_30d.values, color="#5a9fd4", lw=1.2,
                  ls="--", label="SOFR 30D avg")
    ax_hist.plot(sofr_90d.index, sofr_90d.values, color="#1a4a7a", lw=1.2,
                  ls="--", label="SOFR 90D avg")
    ax_hist.plot(effr.index, effr.values, color="#b32a2a", lw=1.4, alpha=0.85,
                  label="Effective FFR")

    title_extra = (f"  ·  spread SOFR–FFR = {spread_bps:+.0f} bps"
                    if spread_bps is not None else "")
    ax_hist.set_title(
        f"SOFR (ON / 30D / 90D) y Effective FFR  ·  "
        f"últimos {lookback_days // 30} meses{title_extra}",
        fontsize=12, weight="bold", pad=8,
    )
    ax_hist.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax_hist.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax_hist.set_ylabel("% anual")
    ax_hist.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax_hist.grid(True, alpha=0.3)

    # Panel B snapshot tabla
    ax_snap.axis("off")
    rows = [[k, f"{v:.3f}%" if v is not None else "—"] for k, v in snap.items()]
    if spread_bps is not None:
        rows.append(["spread SOFR–FFR", f"{spread_bps:+.0f} bps"])
    tbl = ax_snap.table(
        cellText=rows,
        colLabels=["Tasa", "Valor"],
        loc="upper center", cellLoc="left",
        colWidths=[0.62, 0.32],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.5)
    for i in range(len(rows) + 1):
        for j in range(2):
            cell = tbl[(i, j)]
            if i == 0:
                cell.set_facecolor("#2a6fb3")
                cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#f7fafc")
                if j == 1: cell.set_text_props(weight="bold", ha="right")
                if i == len(rows) and spread_bps is not None:
                    cell.set_facecolor("#fff4e1")
    ax_snap.set_title("Snapshot tasas overnight", fontsize=11,
                       weight="bold", pad=6)

    # Panel C Term SOFR
    labels = [r[0] for r in term_rows]
    vals = [r[1] if r[1] is not None else 0 for r in term_rows]
    bars = ax_curve.bar(labels, vals, color="#2a6fb3", alpha=0.85,
                          edgecolor="#1a4a7a")
    for bar, v in zip(bars, vals):
        ax_curve.text(bar.get_x() + bar.get_width() / 2,
                       bar.get_height() + 0.02, f"{v:.3f}%",
                       ha="center", va="bottom", fontsize=10, weight="bold")
    ax_curve.set_ylim(min(vals) - 0.3 if vals else 0, max(vals) + 0.4 if vals else 1)
    ax_curve.set_title("Term SOFR curve", fontsize=11, weight="bold", pad=6)
    ax_curve.set_ylabel("% anual")
    ax_curve.grid(True, alpha=0.3, axis="y")

    fig.suptitle(
        f"Fase 1 USA — Lámina 3: Tasas de mercado (SOFR)  ·  Corte {as_of}",
        fontsize=14, weight="bold", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
