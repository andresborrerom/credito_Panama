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

# (feature, label panel, cómo leer la dirección)
PAIRS = [
    ("fx_eurusd", "EUR/USD",  "EUR fuerte ↑"),
    ("fx_gbpusd", "GBP/USD",  "GBP fuerte ↑"),
    ("fx_usdjpy", "USD/JPY",  "USD fuerte ↑"),
    ("fx_usdchf", "USD/CHF",  "USD fuerte ↑"),
    ("fx_dxy",    "DXY",      "USD fuerte ↑"),
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
               label=f"IQR 5y [{p25:.2f}, {p75:.2f}]")
    ax.axhline(snap["median_5y"], color="#1a3a5c", ls="--", lw=1.0,
               alpha=0.7, label=f"Mediana {snap['median_5y']:.2f}")
    # Punto actual
    last_d = s.index[-1]
    ax.scatter([last_d], [snap["value"]], color="#b32a2a", s=55, zorder=5,
               edgecolor="white", linewidth=1.2,
               label=f"Hoy {snap['value']:.2f} (p{snap['percentile_5y']:.0f})")

    ax.set_title(f"{label} · {hint}", fontsize=11, weight="bold")
    ax.grid(True, alpha=0.3); ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(loc="best", fontsize=7.0, framealpha=0.9)

    # caja con cambios
    txt = (f"Δ1m {snap['d1m_pct']:+.1f}%\n"
           f"Δ3m {snap['d3m_pct']:+.1f}%\n"
           f"Δ12m {snap['d12m_pct']:+.1f}%")
    color = ("#1a7a1a" if snap["d12m_pct"] > 0 else "#b32a2a"
             if snap["d12m_pct"] < 0 else "#666")
    ax.text(0.02, 0.97, txt, transform=ax.transAxes,
            ha="left", va="top", fontsize=8.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor=color, linewidth=1.4, alpha=0.92))


def _build_fx_message(df: pd.DataFrame, as_of: date) -> str:
    """Mensaje principal: pares en zona extrema (p<10 o p>90)."""
    extremes = []
    for feat, lab, _ in PAIRS:
        s = fx_snapshot(df, feat, as_of)
        if not np.isfinite(s["percentile_5y"]):
            continue
        p = s["percentile_5y"]
        if p > 90:
            extremes.append(f"{lab} en p{p:.0f}/5y ({s['value']:.3f}, {s['d12m_pct']:+.1f}% 12m)")
        elif p < 10:
            extremes.append(f"{lab} en p{p:.0f}/5y ({s['value']:.3f}, {s['d12m_pct']:+.1f}% 12m)")
    if not extremes:
        snap_dxy = fx_snapshot(df, "fx_dxy", as_of)
        return f"FX G10 sin extremos vs 5 años · DXY {snap_dxy['value']:.1f} (p{snap_dxy['percentile_5y']:.0f})"
    return "Zonas extremas vs 5 años: " + " · ".join(extremes)


def plot_l_fx_1(as_of: date, output_path: Path | str,
                figsize=(14, 9.5), dpi=130) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = _load()

    msg = _build_fx_message(df, as_of)
    fig = plt.figure(figsize=figsize, dpi=dpi)
    gs = fig.add_gridspec(3, 3, height_ratios=[0.18, 1.0, 1.0],
                          hspace=0.42, wspace=0.30)
    ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
    ax_msg.text(0.5, 0.5, "MENSAJE PRINCIPAL · " + msg,
                ha="center", va="center", fontsize=11.5, weight="bold",
                color="#0d1b2a", wrap=True,
                bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                          edgecolor="#b32a2a", linewidth=1.6))
    axes = np.array([[fig.add_subplot(gs[1, j]) for j in range(3)],
                     [fig.add_subplot(gs[2, j]) for j in range(3)]])
    for ax, (feat, lab, hint) in zip(axes.flat[:5], PAIRS):
        _plot_panel(ax, df, feat, lab, hint, as_of)
    axes.flat[5].axis("off")

    # Síntesis cualitativa en el panel libre
    df_local = df
    summary_lines = ["Síntesis hoy vs últimos 5 años:"]
    for feat, lab, _ in PAIRS:
        snap = fx_snapshot(df_local, feat, as_of)
        if not np.isfinite(snap["percentile_5y"]):
            continue
        p = snap["percentile_5y"]
        if p > 80:
            tag = "alto vs hist (p" + f"{p:.0f}" + ")"
        elif p > 60:
            tag = "arriba mediana (p" + f"{p:.0f}" + ")"
        elif p < 20:
            tag = "bajo vs hist (p" + f"{p:.0f}" + ")"
        elif p < 40:
            tag = "abajo mediana (p" + f"{p:.0f}" + ")"
        else:
            tag = "neutral (p" + f"{p:.0f}" + ")"
        summary_lines.append(f"  • {lab:8s} {snap['value']:>8.3f}  {tag}")
    axes.flat[5].text(0.02, 0.95, "\n".join(summary_lines),
                      ha="left", va="top", fontsize=10, family="monospace",
                      transform=axes.flat[5].transAxes,
                      bbox=dict(boxstyle="round,pad=0.5",
                                facecolor="#f5f8fb", edgecolor="#aaa"))
    axes.flat[5].text(0.02, 0.18,
                      "Convención EODHD:\n"
                      "  EUR/USD, GBP/USD → USD por unidad foránea\n"
                      "  USD/JPY, USD/CHF → unidad foránea por USD\n"
                      "  DXY = índice ponderado dólar (ICE)",
                      ha="left", va="top", fontsize=8,
                      style="italic", color="#666",
                      transform=axes.flat[5].transAxes)

    fig.suptitle(f"FX G10 — spots, evolución y posición vs 5 años "
                 f"· corte {as_of}", fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
