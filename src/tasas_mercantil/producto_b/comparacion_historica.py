"""Output (3) — Comparación FDP predictiva vs FDP histórica descriptiva.

Para LUZ habíamos construido la partición en 5 zonas de la FDP (Riesgo /
Bajista / Esperado HDI 50% / Alcista / Sorpresa). Lo que faltaba era el
contraste: poner al lado la **FDP predictiva del modelo** (nube MC) y la
**FDP histórica descriptiva** (retornos h-meses solapados realmente
observados, a las MISMAS ponderaciones actuales del portafolio) y leer la
señal:

  - ¿El modelo ve el escenario Esperado por ENCIMA o por DEBAJO de la
    historia? (señal de retorno)
  - ¿La FDP predictiva es más ANGOSTA o más ANCHA que la histórica?
    (confianza vs dispersión típica del activo)
  - ¿El modelo ve más masa en la cola izquierda (más riesgo) o derecha?
    (asimetría / skew frente a la historia)

Se aplica el MISMO framework de 5 zonas a ambas distribuciones (reusa
`build_scenarios`), de modo que la comparación es peras-con-peras zona a
zona, y se emite un veredicto interpretable.

Funciona a dos niveles:
  - Índices principales de LUZ (LQD, IGOV, GHYG, EMB, ACWI, ...).
  - Portafolio LUZ agregado.

Unidades: TODO en retorno decimal h-meses. Los ETFs vienen en log h-meses
(predictivo `bma_samples` e histórico rolling) → se convierten con exp(x)-1.
El portafolio ya está en decimal en ambos lados.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .forecast_api import CACHE_DIR
from .nearest_neighbors import build_scenarios, ScenarioSet
from .portfolio_aggregator import LUZ_HOLDINGS

ETF_PARQUET = Path("data/external/tasas_mercantil/etfs_producto_b.parquet")

# Proxy histórico para los bonos UST de LUZ (no hay serie de ETF del bono
# individual): los 3 cupones UST intermedios → AGG (US Aggregate Bond, mezcla
# treasuries + IG, duración intermedia); el TBill 0% → BIL (T-Bill ETF).
# Es una reconstrucción descriptiva de "cómo se habría comportado este
# asset-class históricamente", no un re-pricing del bono.
_BOND_HIST_PROXY = {"0": "AGG", "1": "AGG", "2": "AGG", "3": "BIL"}


# ---------------------------------------------------------------------------
# Series históricas de retornos h-meses (decimal)
# ---------------------------------------------------------------------------
def _log_to_decimal(x: np.ndarray) -> np.ndarray:
    return np.exp(np.asarray(x, dtype=float)) - 1.0


def _rolling_h_log_series(etf_df: pd.DataFrame, label: str, h_months: int,
                          as_of: date) -> pd.Series:
    """Serie (indexada por fecha) de retornos LOG h-meses solapados, causal."""
    sub = etf_df[etf_df["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    s = sub.loc[sub.index <= pd.Timestamp(as_of), "return_log"].dropna()
    rolling = s.rolling(window=h_months).sum().dropna()
    return rolling


def historical_h_returns_etf(label: str, h_months: int, as_of: date,
                             lookback_years: int = 7,
                             etf_df: pd.DataFrame | None = None) -> np.ndarray:
    """FDP histórica descriptiva de un índice: retornos h-meses decimales."""
    if etf_df is None:
        etf_df = pd.read_parquet(ETF_PARQUET)
    rolling = _rolling_h_log_series(etf_df, label, h_months, as_of)
    if lookback_years and len(rolling) > lookback_years * 12:
        rolling = rolling.iloc[-lookback_years * 12:]
    return _log_to_decimal(rolling.values)


def historical_h_returns_portfolio(as_of: date, h_months: int,
                                   lookback_years: int = 7,
                                   etf_df: pd.DataFrame | None = None
                                   ) -> np.ndarray:
    """FDP histórica del portafolio LUZ a ponderaciones ACTUALES.

    Reconstruye la serie de retornos h-meses del portafolio sumando, en cada
    fecha, el retorno decimal h-meses de la fuente de cada posición ponderado
    por su peso actual en LUZ. Bonos vía proxy de asset-class (AGG / BIL);
    cash = 0. Alineado por intersección de fechas.
    """
    if etf_df is None:
        etf_df = pd.read_parquet(ETF_PARQUET)

    # serie decimal por fuente requerida
    series: dict[str, pd.Series] = {}

    def _get_source_series(label: str) -> pd.Series:
        if label not in series:
            rolling = _rolling_h_log_series(etf_df, label, h_months, as_of)
            series[label] = pd.Series(_log_to_decimal(rolling.values),
                                      index=rolling.index)
        return series[label]

    weighted: list[tuple[float, pd.Series]] = []
    for pos in LUZ_HOLDINGS:
        if pos.strategy in ("etf", "proxy_etf"):
            src = pos.source
        elif pos.strategy == "bond":
            src = _BOND_HIST_PROXY[pos.source]
        else:  # cash → retorno 0, no aporta a la dispersión
            continue
        weighted.append((pos.weight, _get_source_series(src)))

    # intersección de fechas (ventana donde TODAS las fuentes tienen dato)
    common = None
    for _, s in weighted:
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) == 0:
        return np.array([])
    common = common.sort_values()

    port = np.zeros(len(common))
    for w, s in weighted:
        port += w * s.reindex(common).values

    port = pd.Series(port, index=common)
    if lookback_years and len(port) > lookback_years * 12:
        port = port.iloc[-lookback_years * 12:]
    return port.values


# ---------------------------------------------------------------------------
# Comparación 5 zonas predictiva vs histórica
# ---------------------------------------------------------------------------
@dataclass
class Comparison:
    label: str
    h_months: int
    as_of: date
    pred: ScenarioSet
    hist: ScenarioSet
    pred_samples: np.ndarray
    hist_samples: np.ndarray
    # headline deltas (predictivo − histórico)
    center_delta_bps: float          # mediana pred − mediana hist
    expected_delta_bps: float        # media zona Esperado pred − hist
    downside_delta_bps: float        # media zona Riesgo pred − hist (cola izq)
    upside_delta_bps: float          # media zona Sorpresa pred − hist (cola der)
    width50_ratio: float             # ancho HDI50 pred / hist
    skew_pred: float                 # P(Alcista) − P(Bajista) predictivo
    skew_hist: float                 # idem histórico
    verdict: str                     # "POSITIVA moderada", etc.
    verdict_reason: str

    def zone_table(self) -> pd.DataFrame:
        rows = []
        names = ["Riesgo", "Bajista", "Esperado", "Alcista", "Sorpresa"]
        for nm, sp, sh in zip(names, self.pred.all_scenarios(),
                              self.hist.all_scenarios()):
            rows.append({
                "Zona": nm,
                "P_pred": f"{sp.prob*100:.0f}%",
                "P_hist": f"{sh.prob*100:.0f}%",
                "μ_pred": f"{sp.mean*100:+.1f}",
                "μ_hist": f"{sh.mean*100:+.1f}",
                "Δ_bps": round((sp.mean - sh.mean) * 10000, 0),
            })
        return pd.DataFrame(rows)


def _verdict(center_bps: float, downside_bps: float, width_ratio: float
             ) -> tuple[str, str]:
    """Clasifica la señal a partir de centro, cola izquierda y ancho."""
    a = abs(center_bps)
    if a < 50:
        mag = "neutral"
    elif a < 150:
        mag = "leve"
    elif a < 300:
        mag = "moderada"
    else:
        mag = "fuerte"

    if mag == "neutral":
        direction = "NEUTRAL"
    else:
        direction = "POSITIVA" if center_bps > 0 else "NEGATIVA"

    conf = ("más confianza" if width_ratio < 0.85
            else "más incertidumbre" if width_ratio > 1.15
            else "dispersión similar")
    tail = ("menor riesgo de cola" if downside_bps > 30
            else "mayor riesgo de cola" if downside_bps < -30
            else "cola izquierda similar")
    verdict = f"{direction} {mag}".strip()
    reason = (f"Centro {center_bps:+.0f} bps vs historia; "
              f"{conf} (ancho HDI50 ×{width_ratio:.2f}); {tail} "
              f"({downside_bps:+.0f} bps en zona Riesgo).")
    return verdict, reason


def compare(pred_samples: np.ndarray, hist_samples: np.ndarray,
            label: str, h_months: int, as_of: date) -> Comparison | None:
    """Compara la FDP predictiva (nube MC) vs la histórica (h-meses observados).

    Ambos arrays en retorno DECIMAL h-meses. Aplica el mismo framework de 5
    zonas a las dos y emite veredicto.
    """
    if len(pred_samples) < 5 or len(hist_samples) < 5:
        return None
    pred = build_scenarios(np.asarray(pred_samples), label, h_months, K=0)
    hist = build_scenarios(np.asarray(hist_samples), label, h_months, K=0)
    if pred is None or hist is None:
        return None

    center_bps = (float(np.median(pred_samples)) -
                  float(np.median(hist_samples))) * 10000
    expected_bps = (pred.expected.mean - hist.expected.mean) * 10000
    downside_bps = (pred.risk.mean - hist.risk.mean) * 10000
    upside_bps = (pred.upside.mean - hist.upside.mean) * 10000

    pred_w = pred.expected.high - pred.expected.low
    hist_w = hist.expected.high - hist.expected.low
    width_ratio = pred_w / hist_w if hist_w > 0 else float("nan")

    skew_pred = pred.bullish.prob - pred.bearish.prob
    skew_hist = hist.bullish.prob - hist.bearish.prob

    verdict, reason = _verdict(center_bps, downside_bps, width_ratio)

    return Comparison(
        label=label, h_months=h_months, as_of=as_of,
        pred=pred, hist=hist,
        pred_samples=np.asarray(pred_samples),
        hist_samples=np.asarray(hist_samples),
        center_delta_bps=center_bps, expected_delta_bps=expected_bps,
        downside_delta_bps=downside_bps, upside_delta_bps=upside_bps,
        width50_ratio=width_ratio, skew_pred=skew_pred, skew_hist=skew_hist,
        verdict=verdict, verdict_reason=reason,
    )


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
_DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
               "recomendación de inversión.")


def plot_comparacion(cmp: Comparison, output_path: Path | str,
                     title_suffix: str = "", figsize=(13, 7.5), dpi=130) -> Path:
    """PNG: KDE histórica vs predictiva superpuestas + tabla de zonas + veredicto."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pred_pct = cmp.pred_samples * 100
    hist_pct = cmp.hist_samples * 100

    fig, (ax, axt) = plt.subplots(
        1, 2, figsize=figsize, dpi=dpi,
        gridspec_kw={"width_ratios": [2.4, 1.0]})

    lo = min(pred_pct.min(), hist_pct.min())
    hi = max(pred_pct.max(), hist_pct.max())
    xs = np.linspace(lo, hi, 400)

    def _kde(data, color, label, fill):
        try:
            from scipy.stats import gaussian_kde
            k = gaussian_kde(data)
            ax.plot(xs, k(xs), color=color, lw=2.2, label=label)
            if fill:
                ax.fill_between(xs, k(xs), color=color, alpha=0.12)
        except Exception:
            ax.hist(data, bins=40, density=True, color=color, alpha=0.3,
                    label=label)

    _kde(hist_pct, "#888888", "FDP histórica (observada)", True)
    _kde(pred_pct, "#2a6fb3", "FDP predictiva (modelo)", True)

    # medianas
    mh, mp = np.median(hist_pct), np.median(pred_pct)
    ax.axvline(mh, color="#555555", ls="--", lw=1.5,
               label=f"Mediana hist {mh:+.2f}%")
    ax.axvline(mp, color="#1a3a5c", ls="-", lw=1.8,
               label=f"Mediana modelo {mp:+.2f}%")
    ax.axvline(0, color="black", lw=0.5, alpha=0.4)

    # zona Esperado (HDI 50%) de cada distribución como banda
    ax.axvspan(cmp.hist.expected.low * 100, cmp.hist.expected.high * 100,
               color="#888888", alpha=0.10)
    ax.axvspan(cmp.pred.expected.low * 100, cmp.pred.expected.high * 100,
               color="#2a6fb3", alpha=0.10)

    arrow = "▲" if cmp.center_delta_bps > 0 else "▼" if cmp.center_delta_bps < 0 else "■"
    vcolor = ("#1a7a1a" if cmp.verdict.startswith("POSITIVA")
              else "#a11" if cmp.verdict.startswith("NEGATIVA") else "#555")
    ax.set_title(
        f"{cmp.label} — modelo vs historia · retorno {cmp.h_months}m "
        f"(as_of {cmp.as_of})" + (f"  ·  {title_suffix}" if title_suffix else ""),
        fontsize=12, weight="bold")
    ax.set_xlabel("Retorno h-meses (%)", fontsize=10)
    ax.set_ylabel("Densidad", fontsize=10)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(True, alpha=0.25)
    ax.set_axisbelow(True)

    # banner veredicto
    ax.text(0.98, 0.97, f"SEÑAL: {arrow} {cmp.verdict}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=12, weight="bold", color="white",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=vcolor, alpha=0.95))
    ax.text(0.98, 0.88, cmp.verdict_reason, transform=ax.transAxes,
            ha="right", va="top", fontsize=7.5, style="italic",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#bbb", alpha=0.9), wrap=True)

    # tabla de zonas a la derecha
    axt.axis("off")
    df = cmp.zone_table()
    tbl = axt.table(
        cellText=df.values, colLabels=df.columns,
        cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.0)
    tbl.scale(1.0, 1.35)
    for j in range(len(df.columns)):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")
    # colorear Δmedia
    dcol = list(df.columns).index("Δ_bps")
    for i, v in enumerate(df["Δ_bps"].values, start=1):
        tbl[i, dcol].set_facecolor("#dff0df" if v > 0 else "#f6dede" if v < 0 else "#f0f0f0")
    axt.set_title("Zonas FDP: predictivo vs histórico", fontsize=9, weight="bold")

    fig.text(0.5, 0.01, _DISCLAIMER, ha="center", fontsize=6.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
