"""L_USA_3 — Estructura temporal de tasas USA.

4 paneles:
  1. Curva UST nominal (3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y)
     hoy / hace 1 mes / hace 12 meses.
  2. Curva TIPS real (5Y, 10Y, 20Y, 30Y) hoy / 1m / 12m.
  3. Breakeven inflation (2Y, 5Y, 10Y, 30Y) hoy / 1m / 12m.
  4. Forwards SOFR 1Q–20Q (5 años) hoy.

Fuente: `data/external/tasas_mercantil/bloomberg_historico.parquet`
(features UST_*, TIPS_*, BE_*, SR3_*, SOFR_OIS_*).

Forwards 1Q–8Q salen directos del strip SR3 (futures SOFR 3M, primeros 8
vencimientos). Forwards 9Q–20Q se construyen interpolando spots OIS y
derivando forwards trimestrales — bootstrap interno simple. Se mejora cuando
la plantilla v0.3 agregue swap OIS 1Y y 3Y.

Compliance: footer "Documento informativo. No constituye recomendación".
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import date2num

CACHE = Path("data/external/tasas_mercantil/bloomberg_historico.parquet")

# ---------------------------------------------------------------------------
# Catálogos de tenors
# ---------------------------------------------------------------------------
UST_TENORS = [
    ("UST_1M",  1/12),   ("UST_3M",  0.25),  ("UST_6M",  0.50),
    ("UST_1Y",  1.0),    ("UST_2Y",  2.0),   ("UST_3Y",  3.0),
    ("UST_5Y",  5.0),    ("UST_7Y",  7.0),   ("UST_10Y", 10.0),
    ("UST_20Y", 20.0),   ("UST_30Y", 30.0),
]
TIPS_TENORS = [("TIPS_5Y", 5.0), ("TIPS_10Y", 10.0),
               ("TIPS_20Y", 20.0), ("TIPS_30Y", 30.0)]
BE_TENORS = [("BE_2Y", 2.0), ("BE_5Y", 5.0),
             ("BE_10Y", 10.0), ("BE_30Y", 30.0)]
SR3_FEATURES = [f"SR3_{i}Q" for i in range(1, 9)]      # 8 trimestres directos
OIS_PILLARS = [("SOFR_OIS_2Y", 2.0), ("SOFR_OIS_5Y", 5.0),
               ("SOFR_OIS_10Y", 10.0), ("SOFR_OIS_30Y", 30.0)]

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_master(parquet_path: Path | None = None) -> pd.DataFrame:
    """Loader unificado BBG + FRED. parquet_path se ignora (compatibilidad)."""
    from .data_loader import load_master
    return load_master()


def _last_on_or_before(df: pd.DataFrame, feature: str,
                      cut: pd.Timestamp) -> float | None:
    """Último valor de `feature` en o antes de `cut`. None si no hay dato."""
    sub = df[(df["feature_name"] == feature) & (df["obs_date"] <= cut)]
    if sub.empty:
        return None
    row = sub.sort_values("obs_date").iloc[-1]
    return float(row["value"])


def load_curve(df: pd.DataFrame, tenors: list[tuple[str, float]],
               as_of: date) -> dict[float, float]:
    """{tenor_years: yield_%} a la última obs ≤ as_of, omitiendo faltantes."""
    cut = pd.Timestamp(as_of)
    out: dict[float, float] = {}
    for feat, t in tenors:
        v = _last_on_or_before(df, feat, cut)
        if v is not None and np.isfinite(v):
            out[t] = v
    return out


# ---------------------------------------------------------------------------
# Bootstrap de forwards SOFR trimestrales 1Q–20Q
# ---------------------------------------------------------------------------
def _sr3_implied_rate(price_or_rate: float | None) -> float | None:
    """SR3 viene como PRECIO del futuro (≈94-97). implied_rate = 100 − price.

    Defensa: si el valor está claramente en escala de tasa (< 20), se asume
    que ya viene como rate y se devuelve tal cual.
    """
    if price_or_rate is None or not np.isfinite(price_or_rate):
        return None
    return float(price_or_rate) if price_or_rate < 20 else 100.0 - float(price_or_rate)


def _quarterly_zero_curve(df: pd.DataFrame, as_of: date,
                          n_quarters: int = 20) -> np.ndarray:
    """Zero rates anualizadas (%) por trimestre 1..n_quarters.

    Estrategia:
      - Q1..Q8: SR3 strip (precio → implied rate) como forwards 3M; el zero
        del trimestre k es el promedio de los primeros k forwards (composición
        contínua aprox).
      - Q9..Q20: interpolar lineal el zero rate OIS entre 2Y/5Y/10Y/30Y.
    """
    cut = pd.Timestamp(as_of)
    z = np.full(n_quarters, np.nan)

    sr3_rates = np.array([_sr3_implied_rate(_last_on_or_before(df, f, cut))
                          for f in SR3_FEATURES], dtype=float)
    valid = np.isfinite(sr3_rates)
    if valid.any():
        cum_sum = np.cumsum(np.where(valid, sr3_rates, 0.0))
        cum_n = np.cumsum(valid.astype(float))
        with np.errstate(invalid="ignore", divide="ignore"):
            z[:8] = np.where(cum_n > 0, cum_sum / cum_n, np.nan)

    pillars: list[tuple[float, float]] = []
    for feat, t in OIS_PILLARS:
        v = _last_on_or_before(df, feat, cut)
        if v is not None:
            pillars.append((t, v))
    if len(pillars) >= 2:
        pillars.sort()
        xs = np.array([p[0] for p in pillars])
        ys = np.array([p[1] for p in pillars])
        for q in range(8, n_quarters):
            t_years = (q + 1) / 4.0
            if t_years < xs[0]:
                z[q] = ys[0]
            elif t_years > xs[-1]:
                z[q] = ys[-1]
            else:
                z[q] = float(np.interp(t_years, xs, ys))
    return z


def forwards_quarterly(df: pd.DataFrame, as_of: date,
                       n_quarters: int = 20) -> np.ndarray:
    """Forwards 3M trimestrales (%): F(Q_k, Q_{k+1}) implícitos en la curva.

    Para Q1..Q8 devuelve directamente los SR3 implied rates (= 100 − precio).
    Para Q9..Q20 deriva forwards desde la curva zero:
        F_q ≈ q · z_q − (q−1) · z_{q−1}

    En el salto Q8→Q9 reusa el último forward conocido como continuación
    suave si la primera diferencia daría un salto > 100bps (artefacto del
    bootstrap simple sin pillares cercanos).
    """
    cut = pd.Timestamp(as_of)
    f = np.full(n_quarters, np.nan)

    sr3_rates = [_sr3_implied_rate(_last_on_or_before(df, x, cut))
                 for x in SR3_FEATURES]
    for i, v in enumerate(sr3_rates):
        if v is not None and np.isfinite(v):
            f[i] = v

    z = _quarterly_zero_curve(df, as_of, n_quarters)
    for q in range(8, n_quarters):
        if np.isfinite(z[q]) and np.isfinite(z[q - 1]):
            raw = (q + 1) * z[q] - q * z[q - 1]
            # smoothing del salto bootstrap: si la primera derivación es
            # inconsistente vs el último forward conocido (>100bps salto),
            # interpolar suavemente desde el último SR3 hacia el zero OIS
            if q == 8 and np.isfinite(f[7]) and abs(raw - f[7]) > 1.0:
                # transición lineal en 4 trimestres desde f[7] hacia z[12]
                end_z = z[min(12, n_quarters - 1)]
                f[q] = f[7] + (end_z - f[7]) * 0.25
            else:
                f[q] = raw
    return f


# ---------------------------------------------------------------------------
# Plot 4 paneles
# ---------------------------------------------------------------------------
def _shifts(as_of: date) -> tuple[date, date, date]:
    """Devuelve (as_of, as_of-1m, as_of-12m) usando fin-de-mes anterior."""
    ts = pd.Timestamp(as_of)
    one_m = (ts - pd.offsets.MonthEnd(1)).date()
    twelve_m = (ts - pd.offsets.MonthEnd(12)).date()
    return as_of, one_m, twelve_m


def _plot_curve(ax, df, tenors, as_of, title, ylabel, ymin=None, ymax=None):
    d0, d1, d12 = _shifts(as_of)
    c_now = load_curve(df, tenors, d0)
    c_1m = load_curve(df, tenors, d1)
    c_12m = load_curve(df, tenors, d12)

    def _xy(c):
        if not c:
            return [], []
        ks = sorted(c)
        return ks, [c[k] for k in ks]

    x12, y12 = _xy(c_12m)
    x1, y1 = _xy(c_1m)
    x0, y0 = _xy(c_now)

    if x12:
        ax.plot(x12, y12, color="#aaaaaa", lw=1.6,
                marker="o", ms=4, label=f"Hace 12 meses")
    if x1:
        ax.plot(x1, y1, color="#7aa9d2", lw=1.8,
                marker="o", ms=4, label=f"Hace 1 mes")
    if x0:
        ax.plot(x0, y0, color="#1a3a5c", lw=2.4,
                marker="o", ms=5, label=f"Hoy")

    ax.set_title(title, fontsize=11, weight="bold")
    ax.set_xlabel("Tenor (años)", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xscale("log")
    ax.set_xticks([0.25, 0.5, 1, 2, 5, 10, 30])
    ax.set_xticklabels(["3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"], fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc="best", fontsize=7.5, framealpha=0.9)
    if ymin is not None or ymax is not None:
        ax.set_ylim(ymin, ymax)

    # Tabla compacta de deltas
    if c_now and c_1m:
        common = sorted(set(c_now) & set(c_1m))
        delta_1m = [(c_now[t] - c_1m[t]) * 100 for t in common]
        max_d, min_d = max(delta_1m), min(delta_1m)
        ax.text(0.02, 0.02,
                f"Cambio vs hace 1 mes: máx {max_d:+.0f} · "
                f"mín {min_d:+.0f} centésimas",
                transform=ax.transAxes, fontsize=7.5, style="italic",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor="#bbb", alpha=0.85))


def _plot_forwards(ax, df, as_of):
    n_q = 20
    fwd = forwards_quarterly(df, as_of, n_q)
    qs = np.arange(1, n_q + 1)
    valid = np.isfinite(fwd)

    direct = valid & (qs <= 8)
    boot = valid & (qs > 8)
    ax.bar(qs[direct], fwd[direct], width=0.8,
           color="#1a3a5c", label="Próximos 2 años (de futuros directos)")
    ax.bar(qs[boot], fwd[boot], width=0.8,
           color="#7aa9d2", label="Años 3 a 5 (de swaps)")

    cut = pd.Timestamp(as_of)
    sofr_on = _last_on_or_before(df, "SOFR_ON", cut)
    if sofr_on is not None:
        ax.axhline(sofr_on, color="#b32a2a", ls="--", lw=1.4,
                   label=f"Tasa overnight hoy: {sofr_on:.2f}%")

    ax.set_title("Tasa de corto plazo que el mercado anticipa\n"
                 "para cada trimestre de los próximos 5 años",
                 fontsize=10.5, weight="bold")
    ax.set_xlabel("Trimestre adelante", fontsize=9)
    ax.set_ylabel("Tasa anual esperada (%)", fontsize=9)
    ax.set_xticks(np.arange(1, n_q + 1, 2))
    ax.set_xticklabels([f"{(q+1)/4:.1f} años" if q % 4 == 3 else f"T{q+1}"
                        for q in range(0, n_q, 2)], fontsize=7.5)
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_axisbelow(True)
    ax.legend(loc="best", fontsize=7.5, framealpha=0.9)

    # Marcador del primer trimestre donde el forward cruza X bps debajo
    # del SOFR ON spot — "donde empieza a descontar cuts"
    if sofr_on is not None:
        cut_threshold = 25  # bps
        cross = np.where(valid & (fwd < sofr_on - cut_threshold / 100))[0]
        if len(cross) > 0:
            first_q = cross[0] + 1
            yrs = (first_q + 1) / 4.0
            ax.annotate(f"El mercado espera que la Fed\n"
                        f"baje tasas a partir de\n"
                        f"unos {yrs:.1f} años desde hoy",
                        xy=(first_q, fwd[first_q - 1]),
                        xytext=(first_q + 2, sofr_on + 0.3),
                        fontsize=7.5,
                        arrowprops=dict(arrowstyle="->", color="#b32a2a",
                                        lw=1.0),
                        bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="#fff5e6", edgecolor="#b32a2a",
                                  alpha=0.95))


def _build_curvas_message(df: pd.DataFrame, as_of: date) -> str:
    """Mensaje principal en castellano descriptivo."""
    cut = pd.Timestamp(as_of)
    ust_now = load_curve(df, UST_TENORS, as_of)
    parts = []
    if ust_now and 2.0 in ust_now and 10.0 in ust_now:
        y2 = ust_now[2.0]; y10 = ust_now[10.0]
        s = y10 - y2
        if s > 0.5:
            shape = (f"está empinada: el bono a 10 años paga {s:.2f} puntos "
                     f"más que el de 2 años ({y10:.2f}% vs {y2:.2f}%)")
        elif s < -0.1:
            shape = (f"está invertida: el bono a 2 años paga más que el de "
                     f"10 años ({y2:.2f}% vs {y10:.2f}%)")
        else:
            shape = (f"está casi plana: el bono a 10 años paga apenas "
                     f"{s:.2f} puntos más que el de 2 años "
                     f"({y10:.2f}% vs {y2:.2f}%)")
        parts.append(f"La curva de tasas del Tesoro USA {shape}")

    # Forwards
    sofr_on = _last_on_or_before(df, "SOFR_ON", cut)
    fwd = forwards_quarterly(df, as_of, 20)
    if sofr_on and np.isfinite(sofr_on):
        cross_idx = np.where(np.isfinite(fwd) & (fwd < sofr_on - 0.25))[0]
        if len(cross_idx) > 0:
            q = cross_idx[0] + 1
            yrs = (q + 1) / 4.0
            parts.append(
                f"el mercado descuenta que la Fed bajará tasas en cerca de "
                f"{yrs:.1f} años desde hoy"
            )
        else:
            parts.append(
                "el mercado no anticipa bajadas importantes de tasas en "
                "los próximos 5 años (espera que la Fed mantenga el nivel actual)"
            )

    # Breakeven
    be_now = load_curve(df, BE_TENORS, as_of)
    if be_now and 2.0 in be_now and 30.0 in be_now:
        be2 = be_now[2.0]; be30 = be_now[30.0]
        if be30 < be2 - 0.1:
            parts.append(
                f"la inflación esperada baja con el plazo: para los próximos "
                f"2 años el mercado descuenta {be2:.2f}% anual, pero para los "
                f"próximos 30 años descuenta {be30:.2f}% (la Fed lograría su meta)"
            )
        elif be30 > be2 + 0.1:
            parts.append(
                f"la inflación esperada sube con el plazo: {be2:.2f}% a 2 años "
                f"vs {be30:.2f}% a 30 años (el mercado anticipa que la Fed "
                f"no controlará la inflación a largo plazo)"
            )
    return ". ".join(parts) + "." if parts else "Estado de la curva de tasas USA."


def build_msg_l_usa_3(as_of: date) -> str:
    return _build_curvas_message(_load_master(), as_of)


def plot_curvas_usa(as_of: date, output_path: Path | str,
                    parquet_path: Path | None = None,
                    figsize=(14, 8.5), dpi=130,
                    show_message_banner: bool = False) -> Path:
    """PNG con los 4 paneles + (opcional) mensaje principal."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = _load_master(parquet_path)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    if show_message_banner:
        msg = _build_curvas_message(df, as_of)
        gs = fig.add_gridspec(3, 2, height_ratios=[0.18, 1.0, 1.0],
                              hspace=0.42, wspace=0.20)
        ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
        ax_msg.text(0.5, 0.5, msg,
                    ha="center", va="center", fontsize=11.0,
                    color="#0d1b2a", wrap=True,
                    bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                              edgecolor="#b32a2a", linewidth=1.6))
        axes = np.array([[fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])],
                         [fig.add_subplot(gs[2, 0]), fig.add_subplot(gs[2, 1])]])
    else:
        axes = np.empty((2, 2), dtype=object)
        for i in range(2):
            for j in range(2):
                axes[i, j] = fig.add_subplot(2, 2, i * 2 + j + 1)
    _plot_curve(axes[0, 0], df, UST_TENORS, as_of,
                "Tasas del Tesoro USA por plazo",
                "Tasa (%)")
    _plot_curve(axes[0, 1], df, TIPS_TENORS, as_of,
                "Tasas REALES del Tesoro (descontando inflación)",
                "Tasa real (%)")
    _plot_curve(axes[1, 0], df, BE_TENORS, as_of,
                "Inflación esperada por el mercado, por plazo",
                "Inflación anual (%)")
    _plot_forwards(axes[1, 1], df, as_of)

    fig.suptitle(
        f"Cómo está la curva de tasas USA · cierre del {as_of}",
        fontsize=14, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
