"""Output (2) — Histograma rico del portafolio LUZ.

Visualización matplotlib de la nube MC del portafolio agregado con:
  - Histograma + KDE de la distribución de retornos
  - HDIs anidados (50% / 80% / 95%) sombreados como fan chart vertical
  - Línea vertical en el centro (mediana)
  - Marcadores de VaR 95 y CVaR 95
  - Marcador de tasa libre de riesgo
  - Anotaciones con probabilidades direccionales

Lectura por el usuario:
  "el más útil de todos los outputs pero requiere educación del consumidor".
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .views_bandas import forecast_luz_all_views


def plot_luz_histograma(
    as_of: date,
    h_months: int,
    output_path: Path | str,
    views: dict | None = None,
    figsize: tuple = (12, 7),
    dpi: int = 130,
) -> Path:
    """Genera PNG del histograma rico del portafolio LUZ.

    Args:
        as_of, h_months: pasados a forecast_luz_all_views si views es None.
        output_path: ruta de salida del PNG.
        views: dict de forecast_luz_all_views precomputado (ahorra ~15 min).

    Returns:
        Path donde se guardó el PNG.
    """
    if views is None:
        views = forecast_luz_all_views(as_of, h_months)

    samples_pct = np.asarray(views["meta"]["samples_pct"]) if "samples_pct" in views["meta"] else None
    # Necesitamos samples del portafolio. forecast_luz_all_views no los expone
    # en meta — los obtenemos via el portfolio forecast. Aquí los re-obtenemos
    # via percentil reverso si fuera necesario. Más limpio: aceptar samples.
    # Por ahora, reconstruir desde quantiles + fan_chart no es viable. Trabajo
    # alternativo: agregar samples explícito a views["meta"].
    raise NotImplementedError("Use forecast_luz_all_views + pass samples explicitly")


def plot_from_samples(
    samples: np.ndarray,
    views: dict,
    output_path: Path | str,
    title_suffix: str = "",
    figsize: tuple = (12, 7),
    dpi: int = 130,
) -> Path:
    """Genera el histograma directamente desde los samples del portafolio.

    Args:
        samples: nube MC del portafolio (decimal retornos).
        views: dict de forecast_luz_all_views (para HDIs, VaR, CVaR, etc).
        output_path: ruta del PNG.
        title_suffix: texto adicional para el título.

    Returns:
        Path del PNG guardado.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    samples_pct = samples * 100   # convertir a %
    meta = views["meta"]
    center_pct = meta["center"] * 100

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    # Histograma + KDE
    n_bins = 50
    counts, bin_edges, _ = ax.hist(
        samples_pct, bins=n_bins, density=True,
        color="#2a6fb3", alpha=0.35, edgecolor="white", linewidth=0.5,
        label="Distribución MC",
    )

    # KDE manual con gaussian_kde (sin dependencia de scipy si está disponible)
    try:
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(samples_pct)
        xs = np.linspace(samples_pct.min(), samples_pct.max(), 400)
        ax.plot(xs, kde(xs), color="#1a3a5c", linewidth=2.0, label="KDE")
    except ImportError:
        pass

    # Fan chart vertical: HDIs anidados como bandas sombreadas
    colors_hdi = {"hdi_95": "#aac6e3", "hdi_80": "#7aa9d2", "hdi_50": "#4a8bbf"}
    labels_hdi = {"hdi_95": "HDI 95%", "hdi_80": "HDI 80%", "hdi_50": "HDI 50%"}
    y_max = ax.get_ylim()[1]
    for key in ["hdi_95", "hdi_80", "hdi_50"]:
        v = views["fan_chart"][key]
        ax.axvspan(v["lo"] * 100, v["hi"] * 100,
                   alpha=0.18, color=colors_hdi[key], label=labels_hdi[key])

    # Línea del centro (mediana)
    ax.axvline(center_pct, color="#b32a2a", linestyle="-", linewidth=2.2,
               label=f"Mediana {center_pct:+.2f}%")

    # VaR 95 marker
    var_pct = views["var"]["var"] * 100
    ax.axvline(var_pct, color="#5e3a82", linestyle="--", linewidth=1.5,
               label=f"VaR 95 {var_pct:+.2f}%")
    # CVaR/ES marker
    cvar_pct = views["cvar"]["cvar"] * 100
    ax.axvline(cvar_pct, color="#8b1a1a", linestyle=":", linewidth=1.8,
               label=f"CVaR 95 {cvar_pct:+.2f}%")

    # Tasa libre marker
    rf_pct = views["directional"]["rf_rate"] * 100
    ax.axvline(rf_pct, color="#2a6e2a", linestyle="-.", linewidth=1.3,
               label=f"Tasa libre {rf_pct:+.2f}%")

    # Línea cero referencia
    ax.axvline(0, color="black", linestyle="-", linewidth=0.5, alpha=0.4)

    # Anotaciones de probabilidades direccionales
    d = views["directional"]
    text_box = (
        f"P(retorno > 0)        = {d['p_positive']*100:5.1f}%\n"
        f"P(retorno > tasa libre) = {d['p_above_rf']*100:5.1f}%\n"
        f"\n"
        f"VaR 95  = {abs(views['var']['var'])*100:.2f}% (pérdida máxima 95%)\n"
        f"CVaR 95 = {abs(views['cvar']['cvar'])*100:.2f}% (pérdida media peor 5%)"
    )
    ax.text(0.02, 0.98, text_box, transform=ax.transAxes,
            fontsize=9, family="monospace",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#888", alpha=0.92))

    # Cobertura + régimen abajo a la derecha
    cov_directa = meta["coverage_directa"] * 100
    cov_total = (meta["coverage_directa"] + meta["coverage_proxy"]) * 100
    foot_box = (
        f"Cobertura modelo: {cov_directa:.0f}% directo · {cov_total:.0f}% incluyendo proxies\n"
        f"Régimen agregado: {meta['worst_regime']}"
    )
    ax.text(0.98, 0.02, foot_box, transform=ax.transAxes,
            fontsize=8, family="monospace",
            verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f5f5",
                      edgecolor="#aaa", alpha=0.92))

    # Estética
    title_main = (f"Portafolio LUZ — distribución MC retorno {meta['h_months']}m "
                  f"(as_of {meta['as_of']})")
    if title_suffix:
        title_main += f"  ·  {title_suffix}"
    ax.set_title(title_main, fontsize=12, weight="bold")
    ax.set_xlabel("Retorno del portafolio (%)", fontsize=10)
    ax.set_ylabel("Densidad", fontsize=10)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.25)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return output_path
