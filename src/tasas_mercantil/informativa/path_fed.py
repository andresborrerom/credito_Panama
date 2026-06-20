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
def _msg_l_usa_2(merc, sent) -> str:
    """Construye el mensaje en castellano para L_USA_2."""
    spot = merc.fed_funds_now
    pa = merc.pieza_a; pb = merc.pieza_b
    d12m = (merc.forecast_12m - spot) * 100
    d_a = (pa.forecast_12m - spot) * 100
    d_b = (pb.forecast_12m - spot) * 100
    if d12m > 25:
        dir_txt = "subir las tasas"
    elif d12m < -25:
        dir_txt = "bajar las tasas"
    else:
        dir_txt = "mantener las tasas prácticamente sin cambios"
    sent_map = {
        "Muy bullish bonos (>1σ)": "muy optimista sobre los bonos largos",
        "Bullish bonos": "optimista sobre los bonos largos",
        "Muy bearish bonos (<-1σ)": "muy pesimista sobre los bonos largos",
        "Bearish bonos": "pesimista sobre los bonos largos",
        "Neutral": "neutro sobre los bonos largos",
    }
    sent_txt = sent_map.get(sent.get("label", ""), "neutro")
    return (
        f"Nuestro modelo combinado proyecta que en los próximos 12 meses la Fed "
        f"va a {dir_txt} ({d12m:+.0f} centésimas de punto desde el nivel actual "
        f"de {spot:.2f}%). El mercado de futuros descuenta {d_a:+.0f} centésimas, "
        f"la regla de Taylor sugiere {d_b:+.0f} centésimas. El sentimiento de "
        f"noticias sobre bonos del Tesoro largo está {sent_txt}."
    )


def build_msg_l_usa_2(as_of: date) -> str:
    store = load_master_store()
    merc = compute_mercantil_aggregate(store, as_of)
    sent = tlt_sentiment_snapshot(as_of)
    return _msg_l_usa_2(merc, sent)


def plot_path_fed(as_of: date, output_path: Path | str,
                  figsize=(14, 7.5), dpi=130,
                  show_message_banner: bool = False) -> Path:
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

    fig = plt.figure(figsize=figsize, dpi=dpi)
    if show_message_banner:
        msg = _msg_l_usa_2(merc, sent)
        gs = fig.add_gridspec(3, 3, width_ratios=[2.2, 1.1, 1.1],
                              height_ratios=[0.28, 3.0, 0.85],
                              hspace=0.35, wspace=0.28)
        ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
        ax_msg.text(0.5, 0.5, msg,
                    ha="center", va="center", fontsize=11.0,
                    color="#0d1b2a", wrap=True,
                    bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                              edgecolor="#b32a2a", linewidth=1.6))
        ax = fig.add_subplot(gs[1, 0])
        ax_sent = fig.add_subplot(gs[1, 1])
        ax_tbl = fig.add_subplot(gs[1, 2])
        ax_foot = fig.add_subplot(gs[2, :])
    else:
        gs = fig.add_gridspec(2, 3, width_ratios=[2.2, 1.1, 1.1],
                              height_ratios=[3.0, 0.85],
                              hspace=0.35, wspace=0.28)
        ax = fig.add_subplot(gs[0, 0])
        ax_sent = fig.add_subplot(gs[0, 1])
        ax_tbl = fig.add_subplot(gs[0, 2])
        ax_foot = fig.add_subplot(gs[1, :])
    ax_foot.axis("off")

    # Referencia: tasa Fed actual
    ax.axhline(spot, color="black", lw=1.0, alpha=0.6,
               label=f"Tasa Fed hoy: {spot:.2f}%")

    # Mercado de futuros
    ax.plot(xs, a_vals, color="#2a6fb3", lw=1.8, ls=(0,(5,2)),
            marker="o", ms=6,
            label="Lo que descuenta el mercado de futuros (WIRP)")
    # Taylor
    ax.plot(xs, b_vals, color="#b32a2a", lw=1.8, ls=(0,(5,2)),
            marker="s", ms=6,
            label="Lo que dice la regla de Taylor (tasa de equilibrio)")
    # Modelo combinado
    ax.plot(xs, m_vals, color="#0d1b2a", lw=2.8, marker="D", ms=7,
            label="Modelo combinado (las dos fuentes ponderadas)")

    # Próximas mejoras al modelo
    from matplotlib.lines import Line2D
    placeholder_handles = [
        Line2D([], [], color="#cccccc", lw=1.6, ls=":",
               label="Encuesta NY Fed a primary dealers (próxima fuente)"),
        Line2D([], [], color="#cccccc", lw=1.6, ls=":",
               label="Encuesta Bloomberg a economistas (plantilla v0.3)"),
    ]
    handles_main, labels_main = ax.get_legend_handles_labels()
    ax.legend(handles=handles_main + placeholder_handles,
              loc="best", fontsize=8.0, framealpha=0.95)

    ax.set_xticks(xs)
    ax.set_xticklabels(["1 mes", "3 meses", "6 meses", "12 meses", "24 meses"])
    ax.set_xlabel("A cuántos meses adelante miramos", fontsize=10)
    ax.set_ylabel("Tasa Fed proyectada (%)", fontsize=10)
    ax.set_title("Qué van a hacer las tasas de la Fed en los próximos 24 meses\n"
                 "según el mercado, la regla de Taylor y el modelo combinado",
                 fontsize=11, weight="bold")
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    # Panel de sentimiento (lateral) — descriptivo
    ax_sent.axis("off")
    ax_sent.set_title("Sentimiento del mercado sobre\nbonos del Tesoro a largo plazo",
                      fontsize=10.5, weight="bold")
    val = sent["value"]; z = sent["z"]; lbl = sent["label"]
    color_box = ("#1a7a1a" if (z and np.isfinite(z) and z > 0.3)
                 else "#b32a2a" if (z and np.isfinite(z) and z < -0.3) else "#888")
    sent_human = {
        "Muy bullish bonos (>1σ)": "Muy optimista\nsobre bonos largos",
        "Bullish bonos": "Optimista\nsobre bonos largos",
        "Muy bearish bonos (<-1σ)": "Muy pesimista\nsobre bonos largos",
        "Bearish bonos": "Pesimista\nsobre bonos largos",
        "Neutral": "Neutro",
    }
    lectura = sent_human.get(lbl, "Neutro")
    if np.isfinite(val):
        txt = (f"{lectura}\n\n"
               f"Nivel actual: {val:+.2f}\n"
               f"(promedio últimos 24 meses: {sent['mean']:+.2f})\n\n"
               f"Cambio vs hace 3 meses: {sent['delta_3m']:+.2f}")
    else:
        txt = "Sin datos suficientes"
    ax_sent.text(0.5, 0.58, txt, ha="center", va="center",
                 fontsize=9.5,
                 bbox=dict(boxstyle="round,pad=0.7", facecolor="white",
                           edgecolor=color_box, linewidth=2.0))
    ax_sent.text(0.5, 0.04,
                 "Esto es un termómetro cualitativo\n"
                 "de las noticias, no es predicción\n"
                 "directa de las tasas.",
                 ha="center", va="bottom", fontsize=7.5, style="italic",
                 color="#777")

    # Tabla: cambio esperado vs tasa actual (en castellano)
    ax_tbl.axis("off")
    ax_tbl.set_title("Cambio esperado vs tasa actual\n(centésimas de punto)",
                     fontsize=10.5, weight="bold")
    horizons_es = {1: "1 mes", 3: "3 meses", 6: "6 meses",
                   12: "12 meses", 24: "24 meses"}
    rows = [["Plazo", "Mercado", "Taylor", "Combinado"]]
    for i, h in enumerate(xs):
        da = (a_vals[i] - spot) * 100
        db = (b_vals[i] - spot) * 100
        dm = (m_vals[i] - spot) * 100
        rows.append([horizons_es[h], f"{da:+.0f}", f"{db:+.0f}", f"{dm:+.0f}"])
    tbl = ax_tbl.table(cellText=rows[1:], colLabels=rows[0],
                       loc="center", cellLoc="center",
                       bbox=[0.0, 0.05, 1.0, 0.80])
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5)
    for j in range(4):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    for i in range(1, len(rows)):
        v = float(rows[i][3].replace("+", ""))
        c = "#dff0df" if v > 0 else "#f6dede" if v < 0 else "#f0f0f0"
        tbl[i, 3].set_facecolor(c)

    # Pie de página: track record del modelo
    foot = (
        "Track record del modelo combinado en 15 años de pruebas: "
        "tiene un error 18% menor que \"suponer que la tasa no cambia\" a 1 mes vista, "
        "24% menor a 6 meses, y 46% menor a 12 meses. La probabilidad de que sea "
        "casualidad es menor a 1%."
    )
    ax_foot.text(0.5, 0.55, foot, ha="center", va="center",
                 fontsize=9.0, wrap=True,
                 bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f8fb",
                           edgecolor="#aaa", alpha=0.9))

    fig.suptitle("Qué dicen el mercado, la regla de Taylor y el sentimiento "
                 f"sobre las tasas de la Fed · cierre del {as_of}",
                 fontsize=12.5, weight="bold", y=0.995)
    fig.text(0.5, 0.955,
             "PROYECCIÓN: Fed Funds · horizontes 1, 3, 6, 12 y 24 meses · "
             "3 fuentes: mercado de futuros + regla de Taylor + modelo Mercantil v0.3.0",
             ha="center", fontsize=9, style="italic", color="#555")
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
