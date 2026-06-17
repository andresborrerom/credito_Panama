"""Lámina 6 del deck Fase 1 USA — Calendario macro próximos 30-60 días.

Lee los parquets mensuales en data/external/tasas_mercantil/economic_events_us/
y arma una tabla de los eventos macro-relevantes que vienen, clasificados
por importancia visual:

  ALTA   — FOMC decision, Press Conf, Economic Projections, Minutes,
           NFP, CPI, PCE, Powell Speech, Beige Book
  MEDIA  — Fed speakers (no Powell), ISM, Retail Sales, GDP, jobless,
           housing starts, sentiment, balance of trade
  BAJA   — Treasury auctions, Fed Balance Sheet (no se renderiza por
           default para no saturar)
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import re

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


CACHE = Path("data/external/tasas_mercantil/economic_events_us")

# Clasificación por patrón en el "type"
HIGH = [
    r"^Fed Interest Rate Decision",
    r"^Fed Press Conference",
    r"^FOMC Economic Projections",
    r"^FOMC Minutes",
    r"^Fed Beige Book", r"^Beige Book",
    r"^Fed Chair Powell Speech", r"^Fed Powell Speech",
    r"^Nonfarm Payrolls(?! Private)",
    r"^Unemployment Rate$",
    r"^CPI$", r"^Core CPI$",
    r"^PCE Price Index$", r"^Core PCE Price Index$",
    r"^GDP Growth Rate",
]
MEDIUM = [
    r"^Fed \w+ Speech",   # otros Fed speakers
    r"^ISM .*PMI",
    r"^S&P Global .*PMI",
    r"^Retail Sales$",
    r"^Initial Jobless Claims$",
    r"^Continuing Jobless Claims$",
    r"^Housing Starts$",
    r"^Building Permits",
    r"^Michigan Consumer Sentiment",
    r"^CB Consumer Confidence",
    r"^Philadelphia Fed Manufacturing Index",
    r"^Empire State Manufacturing",
    r"^Chicago PMI",
    r"^Durable Goods",
    r"^Balance of Trade",
    r"^Treasury Refunding Announcement",
]
LOW = [
    r"Note Auction$", r"Bond Auction$", r"Bill Auction$",
    r"TIPS Auction$", r"FRN Auction$",
    r"^Fed Balance Sheet$",
]


def classify(event_type: str) -> str | None:
    """Devuelve 'ALTA' / 'MEDIA' / 'BAJA' o None si no es macro-relevante."""
    for pat in HIGH:
        if re.search(pat, event_type): return "ALTA"
    for pat in MEDIUM:
        if re.search(pat, event_type): return "MEDIA"
    for pat in LOW:
        if re.search(pat, event_type): return "BAJA"
    return None


def load_events(as_of: date, days_ahead: int = 60) -> pd.DataFrame:
    """Carga eventos USA desde as_of hasta as_of+days_ahead. Filtra macro."""
    end = as_of + timedelta(days=days_ahead)
    months_needed = set()
    cur = date(as_of.year, as_of.month, 1)
    while cur <= end:
        months_needed.add(cur.strftime("%Y-%m"))
        # Avanzar a primer día del próximo mes
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    parts = []
    for ym in sorted(months_needed):
        p = CACHE / f"{ym}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p))
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= pd.Timestamp(as_of))
            & (df["date"] <= pd.Timestamp(end))]
    df["priority"] = df["type"].apply(classify)
    df = df[df["priority"].notna()].copy()
    df = df.sort_values("date").reset_index(drop=True)
    return df


def plot_calendario_usa(as_of: date, output_path: Path | str,
                          days_ahead: int = 60,
                          include_low: bool = False) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = load_events(as_of, days_ahead)
    if not include_low:
        df = df[df["priority"] != "BAJA"]

    # Próxima FOMC decision para banner
    fomc = df[df["type"].str.contains("Fed Interest Rate Decision",
                                         na=False, regex=False)]
    next_fomc = fomc.iloc[0] if not fomc.empty else None

    # Layout: header (banner FOMC) + tabla
    fig = plt.figure(figsize=(14, max(9, 0.32 * len(df) + 3)), dpi=130)
    gs = fig.add_gridspec(2, 1, height_ratios=[0.12, 1])
    ax_banner = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    # Banner FOMC
    ax_banner.axis("off")
    if next_fomc is not None:
        days = (next_fomc["date"].date() - as_of).days
        est = next_fomc.get("estimate")
        est_str = f"  ·  estimate {est:.2f}%" if pd.notna(est) else ""
        banner = (f"  PRÓXIMA DECISIÓN FOMC  →  "
                  f"{next_fomc['date'].strftime('%a %d-%b-%Y %H:%M UTC')}  "
                  f"(en {days} días){est_str}")
        ax_banner.text(0.0, 0.5, banner,
                        transform=ax_banner.transAxes,
                        fontsize=14, weight="bold", color="white",
                        verticalalignment="center",
                        bbox=dict(boxstyle="round,pad=0.6",
                                   facecolor="#b32a2a", edgecolor="none"))
    else:
        ax_banner.text(0.0, 0.5,
                        f"  Calendario USA — próximos {days_ahead} días "
                        f"desde {as_of}",
                        transform=ax_banner.transAxes,
                        fontsize=13, weight="bold", color="#222",
                        verticalalignment="center")

    # Tabla
    ax_table.axis("off")
    rows = []
    colors = []
    for _, r in df.iterrows():
        d = r["date"]
        est = r.get("estimate")
        prev = r.get("previous")
        est_str = f"{est:.2f}" if pd.notna(est) else "—"
        prev_str = f"{prev:.2f}" if pd.notna(prev) else "—"
        rows.append([
            d.strftime("%a %d-%b"),
            d.strftime("%H:%M"),
            r["type"][:55],
            r["priority"],
            est_str,
            prev_str,
        ])
        if r["priority"] == "ALTA": colors.append("#fde8e8")
        elif r["priority"] == "MEDIA": colors.append("#fff8e1")
        else: colors.append("#f0f4f8")

    if not rows:
        ax_table.text(0.5, 0.5,
                       "Sin eventos macro-relevantes en el período.",
                       ha="center", va="center", fontsize=12)
    else:
        table = ax_table.table(
            cellText=rows,
            colLabels=["Fecha", "Hora UTC", "Evento", "Prio.",
                        "Estimate", "Previous"],
            loc="upper center", cellLoc="left",
            colWidths=[0.11, 0.08, 0.50, 0.08, 0.11, 0.11],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.4)
        for i in range(len(rows) + 1):
            for j in range(6):
                cell = table[(i, j)]
                if i == 0:
                    cell.set_facecolor("#2a6fb3")
                    cell.set_text_props(color="white", weight="bold")
                else:
                    cell.set_facecolor(colors[i - 1])
                    if j == 3:
                        prio = rows[i - 1][3]
                        c = {"ALTA": "#b32a2a", "MEDIA": "#b3892a",
                              "BAJA": "#666"}[prio]
                        cell.set_text_props(color=c, weight="bold")
        ax_table.set_title(
            f"Eventos macro USA próximos {days_ahead}d "
            f"(filtrados: ALTA + MEDIA, {len(rows)} eventos)",
            fontsize=11, weight="bold", pad=8,
        )

    fig.suptitle(
        f"Fase 1 USA — Lámina 6: Calendario  ·  Corte {as_of}",
        fontsize=14, weight="bold", y=0.995,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
