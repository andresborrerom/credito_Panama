"""Lámina 7 del deck Fase 1 USA — Destacados del mes.

Dos paneles:
  Izquierda — Top headlines macro Fed/UST del último mes (filtradas por
              tags relevantes + sentiment polarity).
  Derecha   — Sorpresas macro del último mes (eventos HIGH priority con
              actual vs estimate, ordenados por magnitud de sorpresa).
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tasas_mercantil.producto_a.calendario_usa import load_events


CACHE = Path("data/external/tasas_mercantil")

# Para filtrar headlines: tags macro relevantes
MACRO_TAGS = {"TREASURIES", "RATES", "INFLATION", "MONETARY", "FOMC",
               "FEDERAL RESERVE", "BONDS", "MACRO"}

# Excluir headlines obviamente no-macro
EXCLUDE_TITLE_KEYWORDS = [
    "knicks", "nba", "nfl", "playoff", "dead-cat", "bitcoin", "crypto",
    "earnings beat", "stock split", "dividend",
]


def _as_list(v):
    if v is None: return []
    if hasattr(v, "tolist"): return list(v.tolist())
    return list(v)


def load_top_headlines(as_of: date, days_back: int = 30,
                       limit: int = 8) -> pd.DataFrame:
    """Top headlines macro del último mes."""
    df = pd.read_parquet(CACHE / "news_macro_us.parquet")
    df["date"] = pd.to_datetime(df["date"])
    start = pd.Timestamp(as_of - timedelta(days=days_back), tz="UTC")
    end = pd.Timestamp(as_of, tz="UTC") + pd.Timedelta(days=1)
    df = df[(df["date"] >= start) & (df["date"] <= end)].copy()

    # Score: tags macro count + abs(sentiment.polarity)
    def score_row(r):
        tags = set(_as_list(r.get("tags")))
        macro_tag_hits = len(tags & MACRO_TAGS)
        sent = r.get("sentiment")
        pol = abs((sent or {}).get("polarity", 0.0)) if isinstance(sent, dict) else 0.0
        return macro_tag_hits * 2 + min(pol, 1.0)
    df["_score"] = df.apply(score_row, axis=1)

    # Excluir títulos obviamente no-macro
    title_lower = df["title"].str.lower()
    mask = ~title_lower.apply(
        lambda t: any(k in t for k in EXCLUDE_TITLE_KEYWORDS))
    df = df[mask]

    df = df.sort_values(["_score", "date"], ascending=[False, False])
    df = df.drop_duplicates(subset=["title"]).head(limit).reset_index(drop=True)
    return df


def load_surprises(as_of: date, days_back: int = 35) -> pd.DataFrame:
    """Eventos HIGH priority con actual y estimate, ordenados por |sorpresa|."""
    start = as_of - timedelta(days=days_back)
    df = load_events(start, days_ahead=(as_of - start).days + 1)
    df = df[df["priority"] == "ALTA"].copy()
    df = df.dropna(subset=["actual", "estimate"])
    df["surprise"] = df["actual"] - df["estimate"]
    df["surprise_pct"] = np.where(
        df["estimate"].abs() > 0,
        df["surprise"] / df["estimate"] * 100,
        np.nan,
    )
    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df


def plot_destacados_usa(as_of: date, output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    news = load_top_headlines(as_of, days_back=30, limit=8)
    surp = load_surprises(as_of, days_back=35)

    fig, (ax_news, ax_surp) = plt.subplots(
        1, 2, figsize=(16, 9), dpi=130,
        gridspec_kw={"width_ratios": [1.3, 1]},
    )

    # Panel izquierdo: headlines
    ax_news.axis("off")
    ax_news.set_title(
        f"Top headlines macro USA · últimos 30 días\n"
        f"({len(news)} titulares · ordenados por relevancia)",
        fontsize=12, weight="bold", loc="left", pad=10,
    )
    y_cursor = 0.98
    line_h = 0.115
    for _, r in news.iterrows():
        d = r["date"].strftime("%d-%b")
        title = r["title"][:130]
        sent = r.get("sentiment")
        pol = (sent or {}).get("polarity", 0.0) if isinstance(sent, dict) else 0.0
        if pol > 0.2: indicator, color = "▲", "#1f7a1f"
        elif pol < -0.2: indicator, color = "▼", "#b32a2a"
        else: indicator, color = "•", "#666"
        ax_news.text(0.02, y_cursor, f"{d}  {indicator}",
                      transform=ax_news.transAxes,
                      fontsize=10, weight="bold", color=color,
                      verticalalignment="top", family="monospace")
        ax_news.text(0.13, y_cursor, title,
                      transform=ax_news.transAxes,
                      fontsize=10, color="#222",
                      verticalalignment="top", wrap=True)
        # subtítulo: tags
        tags = _as_list(r.get("tags"))[:4]
        if tags:
            ax_news.text(0.13, y_cursor - 0.045,
                          "  ·  ".join(tags),
                          transform=ax_news.transAxes,
                          fontsize=8, color="#888",
                          verticalalignment="top", style="italic")
        y_cursor -= line_h

    # Panel derecho: sorpresas macro
    ax_surp.axis("off")
    ax_surp.set_title(
        f"Sorpresas macro · últimos 35 días\n"
        f"({len(surp)} releases con actual vs estimate)",
        fontsize=12, weight="bold", loc="left", pad=10,
    )

    if surp.empty:
        ax_surp.text(0.5, 0.5,
                      "Sin releases ALTA con actual + estimate en el período.",
                      ha="center", va="center", fontsize=11, color="#666",
                      transform=ax_surp.transAxes)
    else:
        rows = []
        cell_colors = []
        for _, r in surp.head(12).iterrows():
            est = r["estimate"]
            act = r["actual"]
            s = act - est
            s_str = f"{s:+.2f}"
            if abs(s) > 0.05 * max(abs(est), 1):
                row_color = "#fde8e8" if s > 0 else "#e8f5e8"
            else:
                row_color = "#f8f8f8"
            rows.append([
                r["date"].strftime("%d-%b"),
                r["type"][:35],
                f"{est:.2f}",
                f"{act:.2f}",
                s_str,
            ])
            cell_colors.append(row_color)

        table = ax_surp.table(
            cellText=rows,
            colLabels=["Fecha", "Evento", "Estimate", "Actual", "Sorpresa"],
            loc="upper center", cellLoc="center",
            colWidths=[0.13, 0.45, 0.14, 0.14, 0.14],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.55)
        for i in range(len(rows) + 1):
            for j in range(5):
                cell = table[(i, j)]
                if i == 0:
                    cell.set_facecolor("#2a6fb3")
                    cell.set_text_props(color="white", weight="bold")
                else:
                    cell.set_facecolor(cell_colors[i - 1])
                    if j == 4:  # surprise col
                        s_val = float(rows[i - 1][4])
                        c = "#b32a2a" if s_val > 0 else "#1f7a1f" if s_val < 0 else "#666"
                        cell.set_text_props(color=c, weight="bold")
                    if j == 1:
                        cell.set_text_props(ha="left")

    fig.suptitle(
        f"Fase 1 USA — Lámina 7: Destacados del mes  ·  Corte {as_of}",
        fontsize=14, weight="bold", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
