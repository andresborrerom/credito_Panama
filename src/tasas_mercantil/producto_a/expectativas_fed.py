"""Lámina 5 del deck Fase 1 USA — Expectativas Fed (modelo Mercantil).

Forecast Mercantil v0.3.0:
  Pieza A = implied path SR3 (mercado)         w_a = 0.55
  Pieza B = Taylor rule (reaction function)    w_b = 0.45
  Agregado = w_a * A + w_b * B  por cada horizonte ∈ {1,3,6,12,24} m

Lámina:
  - Línea histórica Effective FFR + Target Midpoint últimos 12m
  - Forward 1/3/6/12/24m proyectado de:
      · Mercantil agregado (línea sólida negra gruesa)
      · Pieza A (azul punteada)
      · Pieza B (rojo punteada)
  - Tabla a la derecha con valores y delta vs spot
  - Subtítulo con interpretación auto-generada
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from tasas_mercantil.data.store import load_master_store, FeatureNotFoundError
from tasas_mercantil.data.queries import (
    get_fed_funds_snapshot, FED_FUNDS_FEATURES,
)
from tasas_mercantil.modelo.aggregate import compute_mercantil_aggregate


HORIZONS = [1, 3, 6, 12, 24]


def _add_months(d: date, m: int) -> date:
    y = d.year + (d.month - 1 + m) // 12
    mo = (d.month - 1 + m) % 12 + 1
    return date(y, mo, min(d.day, 28))


def _interp(text_now, text_12m, text_24m) -> str:
    """Genera texto interpretativo simple."""
    d12 = text_12m - text_now
    d24 = text_24m - text_now
    def desc(d):
        if abs(d) < 0.05: return "sin cambios"
        elif d < 0: return f"−{abs(d * 100):.0f} bps (cortes)"
        else: return f"+{d * 100:.0f} bps (subas)"
    return (f"Mercantil ve: 12m → {desc(d12)},  24m → {desc(d24)}.")


def plot_expectativas_fed(as_of: date, output_path: Path | str,
                            lookback_days: int = 365) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    store = load_master_store()
    snap = get_fed_funds_snapshot(store, as_of)
    pred = compute_mercantil_aggregate(store, as_of)

    # Histórico
    start = as_of - timedelta(days=lookback_days)
    def _ser(features):
        for f in features:
            try:
                s = store.get_series(f, as_of=as_of, start=start)
                if not s.empty:
                    s.index = pd.to_datetime(s.index)
                    return s.sort_index()
            except FeatureNotFoundError:
                continue
        return pd.Series(dtype=float)
    eff = _ser(FED_FUNDS_FEATURES["effective"])
    upper = _ser(FED_FUNDS_FEATURES["upper"])
    lower = _ser(FED_FUNDS_FEATURES["lower"])
    band = pd.concat([upper.rename("u"), lower.rename("l")], axis=1)
    band = band.sort_index().ffill().dropna()
    upper, lower = band["u"], band["l"]

    # Forward points
    fwd_dates = [_add_months(as_of, h) for h in HORIZONS]
    fwd_merc = [getattr(pred, f"forecast_{h}m") for h in HORIZONS]
    fwd_a = [getattr(pred.pieza_a, f"forecast_{h}m") for h in HORIZONS]
    fwd_b = [getattr(pred.pieza_b, f"forecast_{h}m") for h in HORIZONS]

    # Pegamos el spot al inicio del forward para conexión visual
    spot = pred.fed_funds_now
    fwd_dates_full = [as_of] + fwd_dates
    fwd_merc_full = [spot] + fwd_merc
    fwd_a_full = [spot] + fwd_a
    fwd_b_full = [spot] + fwd_b

    # Layout
    fig = plt.figure(figsize=(16, 8.5), dpi=130)
    gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.0], wspace=0.18)
    ax = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    # Histórico — target range shaded
    ax.fill_between(upper.index, lower.values, upper.values,
                     alpha=0.15, color="#2a6fb3", label="Target Range hist.")
    ax.plot(eff.index, eff.values, color="#222", lw=1.4,
             label="Effective FFR histórico")

    # Forwards
    ax.plot(fwd_dates_full, fwd_a_full, color="#2a6fb3", lw=1.4,
             ls="--", marker="o", ms=6, alpha=0.85,
             label=f"Pieza A — Implied Path SR3 (w={pred.w_a})")
    ax.plot(fwd_dates_full, fwd_b_full, color="#b32a2a", lw=1.4,
             ls="--", marker="s", ms=6, alpha=0.85,
             label=f"Pieza B — Taylor Rule (w={pred.w_b})")
    ax.plot(fwd_dates_full, fwd_merc_full, color="#111", lw=2.6,
             marker="D", ms=8, label="Mercantil agregado")

    # Spot
    ax.scatter([as_of], [spot], color="#222", s=80, zorder=10,
                edgecolor="#ffd700", lw=2, label=f"Spot ({spot:.2f}%)")
    ax.axvline(as_of, color="#999", lw=0.8, ls=":", alpha=0.5)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.set_ylabel("Fed Funds (% anual)")
    ax.set_title(
        f"Modelo Mercantil v{pred.model_version} — Expectativas Fed Funds  "
        f"(horizontes 1, 3, 6, 12, 24 meses)",
        fontsize=12, weight="bold", pad=8,
    )
    ax.legend(loc="lower left", fontsize=9, framealpha=0.95, ncol=2)
    ax.grid(True, alpha=0.3)

    # Tabla derecha
    ax_table.axis("off")
    rows = []
    for i, h in enumerate(HORIZONS):
        m = fwd_merc[i]; a = fwd_a[i]; b = fwd_b[i]
        delta = m - spot
        delta_str = f"{delta*100:+.0f} bps"
        rows.append([
            f"{h}m",
            f"{m:.3f}%" if m is not None else "—",
            f"{a:.3f}%" if a is not None else "—",
            f"{b:.3f}%" if b is not None else "—",
            delta_str,
        ])

    table = ax_table.table(
        cellText=rows,
        colLabels=["Horiz.", "Mercantil", "Pieza A", "Pieza B", "Δ vs spot"],
        loc="upper center", cellLoc="center",
        colWidths=[0.12, 0.20, 0.20, 0.20, 0.20],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.7)
    for i in range(len(rows) + 1):
        for j in range(5):
            cell = table[(i, j)]
            if i == 0:
                cell.set_facecolor("#2a6fb3")
                cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#f7fafc" if j != 1 else "#e8eef7")
                if j == 1: cell.set_text_props(weight="bold")
                if j == 4:
                    d_val = float(rows[i - 1][4].split()[0])
                    c = ("#b32a2a" if d_val > 0 else
                         "#1f7a1f" if d_val < 0 else "#666")
                    cell.set_text_props(color=c, weight="bold")
    ax_table.set_title(
        f"Forecast desglosado\n(Pesos: A={pred.w_a}  B={pred.w_b})",
        fontsize=11, weight="bold", pad=8,
    )

    # Subtítulo interpretativo
    interp_text = _interp(spot, pred.forecast_12m, pred.forecast_24m)
    fig.text(0.5, -0.01, interp_text,
              ha="center", fontsize=11, weight="bold", color="#222",
              bbox=dict(boxstyle="round,pad=0.5",
                         facecolor="#fff4e1", edgecolor="#b3892a"))

    fig.suptitle(
        f"Fase 1 USA — Lámina 5: Expectativas Fed (modelo Mercantil)  ·  "
        f"Corte {as_of}",
        fontsize=14, weight="bold", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
