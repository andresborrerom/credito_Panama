"""L_FX_1 — FX G10 + DXY: spots, evolución y posición vs histórico.

Para cada par (EUR/USD, GBP/USD, USD/JPY, USD/CHF, DXY):
  - Serie diaria últimos 5 años.
  - Marcador del valor hoy.
  - Tabla con cambios 1m / 3m / 12m en %.
  - Posición en percentil vs ventana 5y (info de "qué tan extremo").
  - Banda mediana histórica.

L_FX_2 (forwards FX trimestrales 5y) queda como slide placeholder hasta
que la plantilla BBG v0.3 traiga los forwards desde Antulio. EODHD no
publica forwards FX.

Fuente: `data/external/tasas_mercantil/fx_g10.parquet` (ingest_a2_eodhd_fx.py).
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

FX_PARQUET = Path("data/external/tasas_mercantil/fx_g10.parquet")

# (feature, label panel, hint)
PAIRS = [
    ("fx_eurusd", "Euro · dólares por euro",       "sube si el euro se fortalece"),
    ("fx_gbpusd", "Libra · dólares por libra",      "sube si la libra se fortalece"),
    ("fx_usdjpy", "Yen · yenes por dólar",          "sube si el dólar se fortalece"),
    ("fx_usdchf", "Franco · francos por dólar",     "sube si el dólar se fortalece"),
    ("fx_dxy",    "Índice del dólar (DXY)",          "sube si el dólar se fortalece"),
]

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load(parquet: Path | None = None) -> pd.DataFrame:
    df = pd.read_parquet(parquet or FX_PARQUET)
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    return df


def _series(df: pd.DataFrame, feature: str, as_of: date,
            lookback_years: int = 5) -> pd.Series:
    cut = pd.Timestamp(as_of)
    sub = df[(df["feature_name"] == feature) & (df["obs_date"] <= cut)]
    sub = sub.sort_values("obs_date")
    if sub.empty:
        return pd.Series(dtype=float)
    s = sub.set_index("obs_date")["close"].astype(float)
    start = cut - pd.DateOffset(years=lookback_years)
    return s[s.index >= start]


def _value_at_or_before(s: pd.Series, when: pd.Timestamp) -> float:
    h = s[s.index <= when]
    return float(h.iloc[-1]) if not h.empty else float("nan")


# ---------------------------------------------------------------------------
# Snapshot por par
# ---------------------------------------------------------------------------
def fx_snapshot(df: pd.DataFrame, feature: str, as_of: date,
                lookback_years: int = 5) -> dict:
    s = _series(df, feature, as_of, lookback_years)
    out = {"value": np.nan, "d1m_pct": np.nan, "d3m_pct": np.nan,
           "d12m_pct": np.nan, "percentile_5y": np.nan,
           "median_5y": np.nan, "min_5y": np.nan, "max_5y": np.nan,
           "n_obs": 0}
    if s.empty:
        return out
    cut = pd.Timestamp(as_of)
    v = _value_at_or_before(s, cut)
    v1 = _value_at_or_before(s, cut - pd.DateOffset(months=1))
    v3 = _value_at_or_before(s, cut - pd.DateOffset(months=3))
    v12 = _value_at_or_before(s, cut - pd.DateOffset(months=12))

    def pct(curr, prev):
        return (curr / prev - 1) * 100 if (prev and np.isfinite(prev)) else np.nan

    sorted_vals = np.sort(s.values)
    pctile = float(np.searchsorted(sorted_vals, v) / len(sorted_vals) * 100)
    out.update({
        "value": v, "d1m_pct": pct(v, v1), "d3m_pct": pct(v, v3),
        "d12m_pct": pct(v, v12), "percentile_5y": pctile,
        "median_5y": float(np.median(s.values)),
        "min_5y": float(np.min(s.values)),
        "max_5y": float(np.max(s.values)),
        "n_obs": int(len(s)),
    })
    return out


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def _plot_panel(ax, df, feature, label, hint, as_of):
    s = _series(df, feature, as_of, lookback_years=5)
    snap = fx_snapshot(df, feature, as_of, lookback_years=5)
    if s.empty:
        ax.text(0.5, 0.5, f"{label}\nsin datos", ha="center", va="center",
                transform=ax.transAxes)
        ax.set_title(label, fontsize=11, weight="bold")
        return

    ax.plot(s.index, s.values, color="#2a6fb3", lw=1.4, alpha=0.85)
    # Banda intercuartil
    p25, p75 = np.percentile(s.values, [25, 75])
    ax.axhspan(p25, p75, color="#7aa9d2", alpha=0.12,
               label=f"Rango medio últimos 5 años")
    ax.axhline(snap["median_5y"], color="#1a3a5c", ls="--", lw=1.0,
               alpha=0.7, label=f"Promedio 5 años: {snap['median_5y']:.2f}")
    # Punto actual
    last_d = s.index[-1]
    ax.scatter([last_d], [snap["value"]], color="#b32a2a", s=55, zorder=5,
               edgecolor="white", linewidth=1.2,
               label=f"Hoy: {snap['value']:.2f}")

    ax.set_title(f"{label}", fontsize=10.5, weight="bold")
    ax.text(0.5, 1.02, hint, transform=ax.transAxes, ha="center",
            fontsize=7.5, style="italic", color="#666")
    ax.grid(True, alpha=0.3); ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(loc="best", fontsize=7.0, framealpha=0.9)

    # caja con cambios
    txt = (f"Hace 1 mes:  {snap['d1m_pct']:+.1f}%\n"
           f"Hace 3 meses: {snap['d3m_pct']:+.1f}%\n"
           f"Hace 12 meses: {snap['d12m_pct']:+.1f}%")
    color = ("#1a7a1a" if snap["d12m_pct"] > 0 else "#b32a2a"
             if snap["d12m_pct"] < 0 else "#666")
    ax.text(0.02, 0.97, txt, transform=ax.transAxes,
            ha="left", va="top", fontsize=8.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor=color, linewidth=1.4, alpha=0.92))


def _build_fx_message(df: pd.DataFrame, as_of: date) -> str:
    """Mensaje principal en castellano descriptivo."""
    NAMES = {
        "fx_eurusd": "el euro vs dólar",
        "fx_gbpusd": "la libra vs dólar",
        "fx_usdjpy": "el dólar vs yen",
        "fx_usdchf": "el dólar vs franco suizo",
        "fx_dxy":    "el índice del dólar",
    }
    extremes = []
    for feat, _, _ in PAIRS:
        s = fx_snapshot(df, feat, as_of)
        if not np.isfinite(s["percentile_5y"]):
            continue
        p = s["percentile_5y"]
        name = NAMES.get(feat, feat)
        if p > 90:
            extremes.append(
                f"{name} está en niveles muy altos vs los últimos 5 años "
                f"(más alto que el {p:.0f}% de las observaciones recientes)"
            )
        elif p < 10:
            extremes.append(
                f"{name} está en niveles muy bajos vs los últimos 5 años "
                f"(más bajo que el {100-p:.0f}% de las observaciones recientes)"
            )
    if not extremes:
        snap_dxy = fx_snapshot(df, "fx_dxy", as_of)
        return (f"Los principales tipos de cambio están en niveles normales "
                f"vs los últimos 5 años. El índice del dólar está en "
                f"{snap_dxy['value']:.1f}.")
    return "Niveles extremos vs los últimos 5 años: " + ". ".join(extremes) + "."


def build_msg_l_fx_1(as_of: date) -> str:
    return _build_fx_message(_load(), as_of)


def plot_l_fx_1(as_of: date, output_path: Path | str,
                figsize=(14, 8.5), dpi=130,
                show_message_banner: bool = False) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _load()

    fig = plt.figure(figsize=figsize, dpi=dpi)
    if show_message_banner:
        msg = _build_fx_message(df, as_of)
        gs = fig.add_gridspec(3, 3, height_ratios=[0.18, 1.0, 1.0],
                              hspace=0.42, wspace=0.30)
        ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
        ax_msg.text(0.5, 0.5, msg,
                    ha="center", va="center", fontsize=11.0,
                    color="#0d1b2a", wrap=True,
                    bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                              edgecolor="#b32a2a", linewidth=1.6))
        axes = np.array([[fig.add_subplot(gs[1, j]) for j in range(3)],
                         [fig.add_subplot(gs[2, j]) for j in range(3)]])
    else:
        axes = np.empty((2, 3), dtype=object)
        for i in range(2):
            for j in range(3):
                axes[i, j] = fig.add_subplot(2, 3, i * 3 + j + 1)
    for ax, (feat, lab, hint) in zip(axes.flat[:5], PAIRS):
        _plot_panel(ax, df, feat, lab, hint, as_of)
    axes.flat[5].axis("off")

    # Síntesis cualitativa en el panel libre, en castellano
    NAMES_SHORT = {
        "fx_eurusd": "Euro",
        "fx_gbpusd": "Libra",
        "fx_usdjpy": "Yen",
        "fx_usdchf": "Franco",
        "fx_dxy":    "DXY (índice del dólar)",
    }
    df_local = df
    summary_lines = ["Cómo están hoy vs los últimos 5 años:"]
    for feat, lab, _ in PAIRS:
        snap = fx_snapshot(df_local, feat, as_of)
        if not np.isfinite(snap["percentile_5y"]):
            continue
        p = snap["percentile_5y"]
        short = NAMES_SHORT.get(feat, lab)
        if p > 80:
            tag = "MUY alto vs los últimos 5 años"
        elif p > 60:
            tag = "arriba del promedio"
        elif p < 20:
            tag = "MUY bajo vs los últimos 5 años"
        elif p < 40:
            tag = "abajo del promedio"
        else:
            tag = "en niveles normales"
        summary_lines.append(f"  • {short:<22s} {snap['value']:>8.3f}  →  {tag}")
    axes.flat[5].text(0.02, 0.95, "\n".join(summary_lines),
                      ha="left", va="top", fontsize=9.5, family="monospace",
                      transform=axes.flat[5].transAxes,
                      bbox=dict(boxstyle="round,pad=0.5",
                                facecolor="#f5f8fb", edgecolor="#aaa"))
    axes.flat[5].text(0.02, 0.20,
                      "Cómo leer:\n"
                      "  • Euro y Libra: cuántos dólares cuesta una unidad\n"
                      "  • Yen y Franco: cuántas unidades cuesta un dólar\n"
                      "  • DXY: índice ponderado del dólar vs principales monedas",
                      ha="left", va="top", fontsize=8,
                      style="italic", color="#666",
                      transform=axes.flat[5].transAxes)

    fig.suptitle(f"Principales tipos de cambio: dónde están hoy "
                 f"vs los últimos 5 años · cierre del {as_of}",
                 fontsize=12.5, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
