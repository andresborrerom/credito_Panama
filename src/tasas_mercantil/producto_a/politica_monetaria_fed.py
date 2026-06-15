"""Lámina 2 del deck Fase 1 USA — Política monetaria Fed.

Panel izquierdo: histórico Fed Funds Target Range (upper / lower) últimos
24 meses con shading entre upper y lower, más línea de Effective FFR
encima.

Panel derecho: snapshot tabla con target_upper, target_lower, target mid,
effective FFR, IORB, ON RRP, fecha y estimate de la próxima decisión FOMC.

Datos: FRED ya cacheados en data/external/tasas_mercantil/fred_non_vintage.parquet
       (features fred_fed_funds_target_upper/lower, _effective, _iorb,
       _on_rrp_award). Próxima FOMC del calendario EODHD.
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
from tasas_mercantil.data.queries import (
    get_fed_funds_snapshot, FED_FUNDS_FEATURES,
)
from tasas_mercantil.producto_a.calendario_usa import load_events


def _series_from_features(store, features: list[str], start: date,
                            as_of: date) -> pd.Series:
    """Intenta features en orden hasta encontrar una serie no vacía."""
    for f in features:
        try:
            s = store.get_series(f, as_of=as_of, start=start)
            if not s.empty:
                s.index = pd.to_datetime(s.index)
                return s.sort_index()
        except FeatureNotFoundError:
            continue
    return pd.Series(dtype=float)


def _next_fomc(as_of: date):
    """Devuelve (date, hora_str, estimate) de la próxima FOMC, o None."""
    df = load_events(as_of, days_ahead=90)
    fomc = df[df["type"].str.contains("Fed Interest Rate Decision",
                                         na=False, regex=False)]
    if fomc.empty: return None
    r = fomc.iloc[0]
    return (r["date"].date(), r["date"].strftime("%H:%M UTC"),
            r.get("estimate"))


def plot_politica_monetaria_fed(as_of: date,
                                 output_path: Path | str,
                                 lookback_days: int = 730) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    store = load_master_store()
    snap = get_fed_funds_snapshot(store, as_of)
    start = as_of - timedelta(days=lookback_days)

    upper = _series_from_features(store, FED_FUNDS_FEATURES["upper"], start, as_of)
    lower = _series_from_features(store, FED_FUNDS_FEATURES["lower"], start, as_of)
    eff = _series_from_features(store, FED_FUNDS_FEATURES["effective"], start, as_of)
    # Alinear upper/lower a un índice común (forward-fill por días hábiles)
    band = pd.concat([upper.rename("upper"), lower.rename("lower")], axis=1)
    band = band.sort_index().ffill().dropna()
    upper, lower = band["upper"], band["lower"]

    # Decisiones del FOMC en el período (cambios en upper)
    changes = upper.diff().fillna(0)
    decisions = upper[changes != 0]
    hikes = (changes > 0).sum()
    cuts = (changes < 0).sum()

    fomc_next = _next_fomc(as_of)

    # Layout
    fig = plt.figure(figsize=(16, 8.5), dpi=130)
    gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.0], wspace=0.18)
    ax = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    # Panel izquierdo
    ax.fill_between(upper.index, lower.values, upper.values,
                     alpha=0.20, color="#2a6fb3",
                     label="Target Range (upper / lower)")
    ax.plot(upper.index, upper.values, color="#2a6fb3", lw=1.2, alpha=0.7)
    ax.plot(lower.index, lower.values, color="#2a6fb3", lw=1.2, alpha=0.7)
    ax.plot(eff.index, eff.values, color="#222", lw=1.6,
             label="Effective FFR (EFFR)")
    # Marcar decisiones
    for d, v in decisions.items():
        delta = changes.loc[d]
        marker_color = "#b32a2a" if delta > 0 else "#1f7a1f"
        ax.scatter([d], [v], color=marker_color, s=42, zorder=5,
                    edgecolor="white", lw=1.0)

    ax.set_xlim(pd.Timestamp(start), pd.Timestamp(as_of) + pd.Timedelta(days=7))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.set_ylabel("% anual")
    ax.set_title(
        f"Fed Funds Target Range & Effective FFR  ·  "
        f"últimos {lookback_days // 30} meses  "
        f"(▲ {hikes} subas  /  ▼ {cuts} cortes en el período)",
        fontsize=12, weight="bold", pad=8,
    )
    ax.legend(loc="upper left", framealpha=0.95, fontsize=9)
    ax.grid(True, alpha=0.3)

    # Panel derecho — snapshot tabla
    ax_table.axis("off")
    snap_rows = [
        ["Target Upper",     f"{snap['target_upper']:.2f}%"],
        ["Target Lower",     f"{snap['target_lower']:.2f}%"],
        ["Target Midpoint",  f"{snap['target_midpoint']:.3f}%"],
        ["Effective FFR",    f"{snap['effective']:.2f}%"],
        ["IORB",             f"{snap['iorb']:.2f}%"],
        ["ON RRP",           f"{snap['on_rrp']:.2f}%"],
    ]
    table = ax_table.table(
        cellText=snap_rows,
        colLabels=["Tasa", "Valor"],
        loc="upper center", cellLoc="left",
        colWidths=[0.55, 0.35],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.7)
    for i in range(len(snap_rows) + 1):
        for j in range(2):
            cell = table[(i, j)]
            if i == 0:
                cell.set_facecolor("#2a6fb3")
                cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#f7fafc")
                if j == 1: cell.set_text_props(weight="bold", ha="right")
    ax_table.set_title("Snapshot al corte", fontsize=11, weight="bold", pad=8)

    # Banner FOMC siguiente
    if fomc_next is not None:
        d, t, est = fomc_next
        days_to = (d - as_of).days
        est_str = f"  ·  estimate {est:.2f}%" if pd.notna(est) else ""
        banner_txt = (f"Próxima decisión FOMC:  "
                       f"{d.strftime('%a %d-%b-%Y')} {t}  "
                       f"(en {days_to} días){est_str}")
        ax_table.text(0.5, -0.12, banner_txt,
                       transform=ax_table.transAxes,
                       ha="center", va="top", fontsize=11, weight="bold",
                       color="white",
                       bbox=dict(boxstyle="round,pad=0.5",
                                  facecolor="#b32a2a", edgecolor="none"))

    fig.suptitle(
        f"Fase 1 USA — Lámina 2: Política monetaria Fed  ·  Corte {as_of}",
        fontsize=14, weight="bold", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
