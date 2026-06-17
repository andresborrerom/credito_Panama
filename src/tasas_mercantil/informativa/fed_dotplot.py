"""L_USA_1 — Dot plot de la Fed (SEP) + comparación con anterior + mercado.

Pieza:
  - Scatter "dot plot" reconstruido a partir de la tabla de dots del SEP HTML.
  - Banda central tendency + línea mediana del SEP actual.
  - Marcadores del SEP anterior (mediana) → flecha de revisión por año.
  - Línea horizontal del implied path SR3 al cierre del mes corte → gap
    Fed-vs-mercado en bps por año.

Frontera: SEP cubre años current + 2 + longer run (≈3 años, no 5y). Eso se
documenta en el footer del slide.

Fuente: HTML tabular del Fed.
  URL pattern: https://www.federalreserve.gov/monetarypolicy/fomcprojtabl<YYYYMMDD>.htm
  Cache local: data/external/informativa/sep/<YYYYMMDD>.htm

Fechas SEP: 4 por año en fechas FOMC. Las descubrimos probando el URL,
pero por costo se mantiene una lista de fechas conocidas. Si la Fed
publica un nuevo SEP, agregar la fecha a SEP_DATES (es un calendario
público, no hay sorpresas).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.request import urlopen, Request

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CACHE_DIR = Path("data/external/informativa/sep")
URL_TPL = "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{ymd}.htm"

# Calendario SEP confirmado (probado). 4/año desde 2020. Cuando salga uno
# nuevo, basta añadir la fecha al final.
SEP_DATES: list[date] = [
    date(2024, 3, 20),  date(2024, 6, 12),  date(2024, 9, 18), date(2024, 12, 18),
    date(2025, 3, 19),  date(2025, 6, 18),  date(2025, 9, 17), date(2025, 12, 10),
    date(2026, 3, 18),  date(2026, 6, 17),
]

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


# ---------------------------------------------------------------------------
# Fetch + cache
# ---------------------------------------------------------------------------
def latest_sep_date(as_of: date) -> date | None:
    candidates = [d for d in SEP_DATES if d <= as_of]
    return max(candidates) if candidates else None


def previous_sep_date(sep_date: date) -> date | None:
    earlier = [d for d in SEP_DATES if d < sep_date]
    return max(earlier) if earlier else None


def fetch_sep_html(sep_date: date) -> Path:
    """Descarga (con cache) el HTML del SEP en `sep_date`."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ymd = sep_date.strftime("%Y%m%d")
    out = CACHE_DIR / f"{ymd}.htm"
    if out.exists():
        return out
    url = URL_TPL.format(ymd=ymd)
    req = Request(url, headers={"User-Agent": "MercantilInformativa/1.0"})
    with urlopen(req, timeout=20) as r:
        out.write_bytes(r.read())
    return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
@dataclass
class SEPParsed:
    sep_date: date
    median: dict[str, float]              # {year_label: median}
    ct_lo: dict[str, float]               # central tendency lower
    ct_hi: dict[str, float]               # central tendency upper
    range_lo: dict[str, float]
    range_hi: dict[str, float]
    prev_median: dict[str, float]         # mediana del SEP anterior
    dots: pd.DataFrame                    # rows: nivel; cols: years (con counts)
    year_labels: list[str]                # ["2026","2027","2028","Longer run"]


def _parse_band(s: str) -> tuple[float, float] | None:
    """Convierte '2.6–3.6' o '2.0' a (lo, hi). Acepta '–', '-', en-dash."""
    if pd.isna(s):
        return None
    txt = str(s).replace("–", "-").replace("—", "-").strip()
    if "-" in txt:
        parts = [p.strip() for p in txt.split("-")]
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    try:
        v = float(txt)
        return v, v
    except ValueError:
        return None


def parse_sep_html(html_path: Path, sep_date: date) -> SEPParsed:
    """Extrae mediana + bands + dots de un HTML SEP."""
    tables = pd.read_html(html_path)

    # Tabla 0 = summary. Las cabeceras son MultiIndex (Variable / Median / CT / Range × años).
    summary = tables[0]
    if isinstance(summary.columns, pd.MultiIndex):
        # Aplanar
        summary.columns = [
            f"{a}|{b}" if a and b and "Unnamed" not in str(a) else str(b or a)
            for a, b in summary.columns
        ]
    else:
        summary.columns = list(summary.columns)

    # Encontrar la fila de Fed funds (current SEP) y de previous (la siguiente).
    # En el HTML viene como "Federal funds rate" seguido inmediatamente de
    # "<Month> projection".
    first_col = summary.columns[0]
    rows = summary[first_col].astype(str).str.lower()
    ff_idx = None
    for i, txt in enumerate(rows):
        if "federal funds rate" in txt and i < len(rows) - 1:
            ff_idx = i
            break
    if ff_idx is None:
        raise RuntimeError(f"No encontré 'Federal funds rate' en summary SEP {sep_date}")
    prev_idx = ff_idx + 1   # "<Month> projection"

    # Identificar años / longer run a partir de las columnas
    median_cols = [c for c in summary.columns if c.startswith("Median")]
    ct_cols = [c for c in summary.columns if c.startswith("Central Tendency")]
    range_cols = [c for c in summary.columns if c.startswith("Range")]

    def _year(col):
        return col.split("|", 1)[1].strip() if "|" in col else col

    years = [_year(c) for c in median_cols]

    median = {}
    prev_median = {}
    ct_lo, ct_hi, r_lo, r_hi = {}, {}, {}, {}
    for ym, cm in zip(years, median_cols):
        try:
            median[ym] = float(summary.iloc[ff_idx][cm])
        except (ValueError, TypeError):
            median[ym] = float("nan")
        try:
            prev_median[ym] = float(summary.iloc[prev_idx][cm])
        except (ValueError, TypeError):
            prev_median[ym] = float("nan")
    for ym, cc in zip(years, ct_cols):
        band = _parse_band(summary.iloc[ff_idx][cc])
        ct_lo[ym], ct_hi[ym] = band if band else (float("nan"),)*2
    for ym, cr in zip(years, range_cols):
        band = _parse_band(summary.iloc[ff_idx][cr])
        r_lo[ym], r_hi[ym] = band if band else (float("nan"),)*2

    # Tabla de dots: la encuentro por su primera columna "Midpoint of target..."
    dots_tbl = None
    for t in tables:
        if t.shape[1] >= 3:
            first = str(t.columns[0]).lower()
            if "midpoint" in first and "target" in first:
                dots_tbl = t.copy()
                break
    if dots_tbl is None:
        raise RuntimeError(f"No encontré tabla de dots en SEP {sep_date}")

    dots_tbl.columns = [str(c) for c in dots_tbl.columns]
    # Renombrar primera col a 'level'
    level_col = dots_tbl.columns[0]
    dots_tbl = dots_tbl.rename(columns={level_col: "level"})
    dots_tbl["level"] = pd.to_numeric(dots_tbl["level"], errors="coerce")
    dots_tbl = dots_tbl.dropna(subset=["level"]).reset_index(drop=True)
    for c in dots_tbl.columns[1:]:
        dots_tbl[c] = pd.to_numeric(dots_tbl[c], errors="coerce")

    return SEPParsed(
        sep_date=sep_date,
        median=median, ct_lo=ct_lo, ct_hi=ct_hi,
        range_lo=r_lo, range_hi=r_hi,
        prev_median=prev_median, dots=dots_tbl, year_labels=years,
    )


# ---------------------------------------------------------------------------
# Implied path SR3 → tasa promedio por año
# ---------------------------------------------------------------------------
def implied_path_by_year(as_of: date, years: list[str],
                         bbg_parquet: Path | None = None
                         ) -> dict[str, float]:
    """Promedio de implied SR3 dentro del año calendario."""
    from .curvas_usa import _load_master, _last_on_or_before, _sr3_implied_rate, SR3_FEATURES
    df = _load_master(bbg_parquet)
    cut = pd.Timestamp(as_of)
    rates = []
    for feat in SR3_FEATURES:
        v = _last_on_or_before(df, feat, cut)
        rates.append(_sr3_implied_rate(v))

    # SR3 cubre próximos 8 trimestres ≈ 2 años. Para "longer run" no aplica.
    # Mapeo: trimestre k (1..8) → fecha aproximada cut + k·3 meses.
    out = {y: float("nan") for y in years}
    bucket: dict[str, list[float]] = {y: [] for y in years}
    for k, r in enumerate(rates, start=1):
        if r is None or not np.isfinite(r):
            continue
        target_date = cut + pd.DateOffset(months=3 * k)
        y_label = str(target_date.year)
        if y_label in bucket:
            bucket[y_label].append(r)
    for y, vs in bucket.items():
        if vs:
            out[y] = float(np.mean(vs))
    return out


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
def _dots_for_year(dots: pd.DataFrame, year_col: str) -> list[float]:
    """Lista expandida de proyecciones de un año (un float por participante)."""
    if year_col not in dots.columns:
        return []
    sub = dots[["level", year_col]].dropna()
    levels = []
    for _, row in sub.iterrows():
        n = int(row[year_col])
        levels.extend([float(row["level"])] * n)
    return levels


def _build_dotplot_message(sep: SEPParsed, implied: dict | None) -> str:
    """Mensaje principal en castellano descriptivo."""
    parts = []
    if implied:
        gaps = []
        for y in sep.year_labels:
            m = sep.median.get(y, float("nan"))
            im = implied.get(y, float("nan"))
            if np.isfinite(m) and np.isfinite(im):
                gaps.append((m - im, y, m, im))
        if gaps:
            biggest = max(gaps, key=lambda x: abs(x[0]))
            dgap, y, m, im = biggest
            if dgap > 0:
                parts.append(
                    f"El mercado espera que la Fed baje tasas más rápido "
                    f"de lo que la propia Fed anuncia. Para {y}, los miembros "
                    f"de la Fed proyectan en promedio {m:.2f}%, pero el "
                    f"mercado de futuros descuenta {im:.2f}% (una diferencia "
                    f"de {abs(dgap)*100:.0f} centésimas de punto)"
                )
            else:
                parts.append(
                    f"El mercado espera que la Fed mantenga tasas más altas "
                    f"de lo que ella misma proyecta. Para {y}, los miembros "
                    f"de la Fed proyectan en promedio {m:.2f}%, pero el "
                    f"mercado descuenta {im:.2f}%"
                )

    # Revisiones vs SEP previo
    revisions = []
    for y in sep.year_labels:
        m = sep.median.get(y, float("nan"))
        pm = sep.prev_median.get(y, float("nan"))
        if np.isfinite(m) and np.isfinite(pm) and abs(m - pm) > 0.05:
            d = (m - pm) * 100
            verb = "subió" if d > 0 else "bajó"
            revisions.append(f"para {y} {verb} {abs(d):.0f} centésimas")
    if revisions:
        parts.append("Cambios vs proyección anterior de la Fed: " +
                     ", ".join(revisions))
    return ". ".join(parts) + "." if parts else "Proyecciones de la Fed."


def plot_dotplot(sep: SEPParsed, output_path: Path | str,
                 as_of: date, implied: dict[str, float] | None = None,
                 figsize=(14, 8), dpi=130,
                 show_message_banner: bool = False) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    if show_message_banner:
        msg = _build_dotplot_message(sep, implied)
        gs = fig.add_gridspec(2, 1, height_ratios=[0.20, 1.0], hspace=0.18)
        ax_msg = fig.add_subplot(gs[0, 0]); ax_msg.axis("off")
        ax_msg.text(0.5, 0.5, msg,
                    ha="center", va="center", fontsize=11.0,
                    color="#0d1b2a", wrap=True,
                    bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                              edgecolor="#b32a2a", linewidth=1.6))
        ax = fig.add_subplot(gs[1, 0])
    else:
        ax = fig.add_subplot(1, 1, 1)

    years = sep.year_labels
    x_pos = np.arange(len(years))
    rng = np.random.default_rng(42)

    # Dots scatter
    for xi, y in zip(x_pos, years):
        dots = _dots_for_year(sep.dots, y)
        if not dots:
            continue
        jitter = rng.uniform(-0.18, 0.18, size=len(dots))
        ax.scatter(np.full(len(dots), xi) + jitter, dots,
                   s=42, color="#2a6fb3", alpha=0.65,
                   edgecolors="#1a3a5c", linewidth=0.6, zorder=3)

    # Central tendency band + median (SEP actual)
    for xi, y in zip(x_pos, years):
        lo, hi = sep.ct_lo.get(y, np.nan), sep.ct_hi.get(y, np.nan)
        if np.isfinite(lo) and np.isfinite(hi):
            ax.add_patch(plt.Rectangle((xi - 0.32, lo), 0.64, hi - lo,
                                       facecolor="#7aa9d2", alpha=0.18,
                                       edgecolor="none", zorder=1))
        m = sep.median.get(y, np.nan)
        if np.isfinite(m):
            ax.hlines(m, xi - 0.32, xi + 0.32, color="#b32a2a", lw=2.3,
                      zorder=4)

    # Mediana SEP anterior + flecha de revisión
    prev_label = _format_prev_label(sep)
    for xi, y in zip(x_pos, years):
        pm = sep.prev_median.get(y, np.nan)
        m = sep.median.get(y, np.nan)
        if np.isfinite(pm):
            ax.hlines(pm, xi - 0.22, xi + 0.22, color="#888888",
                      lw=1.6, ls=(0, (4, 2)), zorder=2)
            if np.isfinite(m) and abs(m - pm) > 0.001:
                ax.annotate("", xy=(xi + 0.05, m), xytext=(xi + 0.05, pm),
                            arrowprops=dict(arrowstyle="-|>", color="#444",
                                            lw=1.0, alpha=0.8), zorder=5)

    # Implied path SR3
    if implied:
        impl_ys, impl_xs = [], []
        for xi, y in zip(x_pos, years):
            v = implied.get(y, np.nan)
            if np.isfinite(v):
                impl_xs.append(xi)
                impl_ys.append(v)
                ax.hlines(v, xi - 0.35, xi + 0.35, color="#1a7a1a",
                          lw=1.8, ls="--", alpha=0.85, zorder=2)
        if len(impl_xs) >= 2:
            ax.plot(impl_xs, impl_ys, color="#1a7a1a", lw=1.4, alpha=0.6,
                    zorder=2)

    # Estética
    ax.set_xticks(x_pos)
    ax.set_xticklabels(years, fontsize=11)
    ax.set_xlim(-0.55, len(years) - 0.45)
    ax.set_ylabel("Fed Funds Rate (%)", fontsize=10)

    # Tabla resumen al pie en castellano descriptivo
    summary_rows = [["Año",
                     "Proyección\nFed (mediana)",
                     "Proyección\nFed anterior",
                     "Cambio\n(centésimas)",
                     "Rango donde se\nconcentra la Fed",
                     "Lo que descuenta\nel mercado",
                     "Diferencia\nFed vs mercado\n(centésimas)"]]
    for y in years:
        m = sep.median.get(y, np.nan)
        pm = sep.prev_median.get(y, np.nan)
        lo, hi = sep.ct_lo.get(y, np.nan), sep.ct_hi.get(y, np.nan)
        im = (implied or {}).get(y, np.nan)
        delta_prev = (m - pm) * 100 if np.isfinite(m) and np.isfinite(pm) else np.nan
        gap_mkt = (m - im) * 100 if np.isfinite(m) and np.isfinite(im) else np.nan
        summary_rows.append([
            y,
            f"{m:.2f}%" if np.isfinite(m) else "—",
            f"{pm:.2f}%" if np.isfinite(pm) else "—",
            f"{delta_prev:+.0f}" if np.isfinite(delta_prev) else "—",
            f"{lo:.2f}%–{hi:.2f}%" if np.isfinite(lo) else "—",
            f"{im:.2f}%" if np.isfinite(im) else "n/d",
            f"{gap_mkt:+.0f}" if np.isfinite(gap_mkt) else "n/d",
        ])
    # tabla via ax secundario abajo
    box = ax.table(cellText=summary_rows[1:], colLabels=summary_rows[0],
                   loc="bottom", cellLoc="center", bbox=[0.0, -0.42, 1.0, 0.28])
    box.auto_set_font_size(False); box.set_fontsize(8.5)
    for j in range(len(summary_rows[0])):
        box[0, j].set_facecolor("#2a6fb3")
        box[0, j].set_text_props(color="white", weight="bold")

    # Leyenda inline
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [
        Line2D([], [], color="#b32a2a", lw=2.3,
               label=f"Mediana de las proyecciones (al {sep.sep_date})"),
        Patch(facecolor="#7aa9d2", alpha=0.4,
              label="Rango donde se concentra la mayoría de la Fed"),
        Line2D([], [], color="#2a6fb3", marker="o", lw=0, ms=7,
               markeredgecolor="#1a3a5c",
               label="Cada punto = un miembro de la Fed (FOMC)"),
        Line2D([], [], color="#888888", lw=1.6, ls=(0,(4,2)),
               label="Mediana de la proyección anterior de la Fed"),
        Line2D([], [], color="#1a7a1a", lw=1.8, ls="--",
               label=f"Lo que el mercado de futuros descuenta hoy"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8.5, framealpha=0.95)

    ax.set_title(
        f"Dónde proyecta la Fed sus tasas a futuro y qué descuenta "
        f"el mercado sobre ellas (proyección de la Fed del {sep.sep_date})",
        fontsize=11.5, weight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    fig.text(0.5, 0.005,
             "Las proyecciones de la Fed cubren el año en curso, los 2 siguientes "
             "y un \"largo plazo\" (no llegan a 5 años). " + DISCLAIMER,
             ha="center", fontsize=7.5, style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.subplots_adjust(bottom=0.35)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _format_prev_label(sep: SEPParsed) -> str:
    prev_d = previous_sep_date(sep.sep_date)
    if prev_d:
        return f"Mediana SEP anterior ({prev_d})"
    return "Mediana SEP anterior"


# ---------------------------------------------------------------------------
# Entry point para el deck
# ---------------------------------------------------------------------------
def plot_l_usa_1(as_of: date, output_path: Path | str,
                 show_message_banner: bool = False) -> Path | None:
    """Wrapper de un solo paso: fetch + parse + implied path + PNG."""
    sep_d = latest_sep_date(as_of)
    if sep_d is None:
        return None
    html = fetch_sep_html(sep_d)
    sep = parse_sep_html(html, sep_d)
    impl = implied_path_by_year(as_of, sep.year_labels)
    return plot_dotplot(sep, output_path, as_of=as_of, implied=impl,
                        show_message_banner=show_message_banner)


def build_msg_l_usa_1(as_of: date) -> str:
    sep_d = latest_sep_date(as_of)
    if sep_d is None:
        return "Sin SEP disponible para el corte."
    html = fetch_sep_html(sep_d)
    sep = parse_sep_html(html, sep_d)
    impl = implied_path_by_year(as_of, sep.year_labels)
    return _build_dotplot_message(sep, impl)
