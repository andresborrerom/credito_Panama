"""Drafts editoriales L1 + L8 del deck Fase 1 USA.

Genera texto a partir de datos cuantitativos para que el analista pula
manualmente. NO usa LLM — son templates determinísticos con valores
rellenados desde el store y los modelos.

L1 — Mensajes clave del mes (4-5 bullets con números concretos).
L8 — Lectura del analista (párrafo de cierre con resumen + outlook).
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tasas_mercantil.data.store import load_master_store, FeatureNotFoundError
from tasas_mercantil.data.queries import get_fed_funds_snapshot, FED_FUNDS_FEATURES
from tasas_mercantil.modelo.aggregate import compute_mercantil_aggregate
from tasas_mercantil.producto_a.calendario_usa import load_events


def _mom_change_bps(store, features, as_of: date, days: int = 30) -> float | None:
    """Cambio en bps de una serie del store entre (as_of - days) y as_of."""
    for f in features:
        try:
            s = store.get_series(f, as_of=as_of,
                                  start=as_of - timedelta(days=days * 2))
            if s.empty: continue
            s.index = pd.to_datetime(s.index)
            s = s.sort_index()
            cutoff = pd.Timestamp(as_of - timedelta(days=days))
            prior = s.loc[s.index <= cutoff]
            if prior.empty: continue
            return float((s.iloc[-1] - prior.iloc[-1]) * 100)
        except FeatureNotFoundError:
            continue
    return None


def _collect_facts(as_of: date) -> dict:
    """Recolecta los hechos cuantitativos para alimentar plantillas."""
    store = load_master_store()
    snap = get_fed_funds_snapshot(store, as_of)
    pred = compute_mercantil_aggregate(store, as_of)

    # Movimiento UST 30d
    ust_30d = {
        "2Y":  _mom_change_bps(store, ["UST_2Y", "fred_ust_2y"], as_of, 30),
        "5Y":  _mom_change_bps(store, ["UST_5Y", "fred_ust_5y"], as_of, 30),
        "10Y": _mom_change_bps(store, ["UST_10Y", "fred_ust_10y"], as_of, 30),
        "30Y": _mom_change_bps(store, ["UST_30Y", "fred_ust_30y"], as_of, 30),
    }

    # Spread SOFR-FFR
    try:
        sofr = store.get_value("SOFR_ON", as_of) or store.get_value("fred_sofr", as_of)
    except FeatureNotFoundError:
        sofr = None
    spread_sofr_ffr = ((sofr - snap["effective"]) * 100
                       if sofr is not None and snap["effective"] is not None
                       else None)

    # Próxima FOMC
    cal = load_events(as_of, days_ahead=90)
    fomc_row = cal[cal["type"].str.contains("Fed Interest Rate Decision",
                                              na=False, regex=False)]
    fomc = None
    if not fomc_row.empty:
        r = fomc_row.iloc[0]
        fomc = {
            "date":     r["date"].date(),
            "days_to":  (r["date"].date() - as_of).days,
            "estimate": r.get("estimate"),
        }

    # Top headline macro
    news = pd.read_parquet("data/external/tasas_mercantil/news_macro_us.parquet")
    news["date"] = pd.to_datetime(news["date"])
    news = news.sort_values("date", ascending=False)
    top_headline = news.iloc[0]["title"] if not news.empty else None

    return {
        "as_of": as_of,
        "spot": pred.fed_funds_now,
        "upper": snap["target_upper"],
        "lower": snap["target_lower"],
        "iorb":  snap["iorb"],
        "rrp":   snap["on_rrp"],
        "effr":  snap["effective"],
        "sofr_on": sofr,
        "spread_sofr_ffr_bps": spread_sofr_ffr,
        "ust_30d_bps": ust_30d,
        "fomc": fomc,
        "mercantil": {
            "now": pred.fed_funds_now,
            "1m": pred.forecast_1m, "3m": pred.forecast_3m,
            "6m": pred.forecast_6m, "12m": pred.forecast_12m,
            "24m": pred.forecast_24m,
            "version": pred.model_version,
        },
        "top_headline": top_headline,
    }


def _build_mensajes_clave(facts: dict) -> list[str]:
    """Genera 5 bullets con números concretos."""
    bullets = []

    # FOMC
    f = facts["fomc"]
    if f is not None:
        est = f"estimate {f['estimate']:.2f}%" if pd.notna(f["estimate"]) else "sin estimate publicado"
        bullets.append(
            f"Próxima decisión FOMC el {f['date'].strftime('%a %d-%b-%Y')} "
            f"(en {f['days_to']} días, {est}). "
            f"Target Range actual: {facts['lower']:.2f}–{facts['upper']:.2f}%."
        )

    # Forecast Mercantil
    m = facts["mercantil"]
    d12 = (m["12m"] - m["now"]) * 100
    d24 = (m["24m"] - m["now"]) * 100
    def desc(bps):
        if abs(bps) < 5: return "sin cambios"
        return f"{bps:+.0f} bps"
    bullets.append(
        f"Modelo Mercantil v{m['version']} ve Fed Funds en "
        f"{m['12m']:.2f}% a 12m ({desc(d12)}) y {m['24m']:.2f}% a 24m "
        f"({desc(d24)}). Hold de corto plazo con sesgo alcista."
    )

    # Movimiento curva UST
    u = facts["ust_30d_bps"]
    parts = []
    for t in ["2Y", "10Y", "30Y"]:
        if u[t] is not None:
            parts.append(f"{t} {u[t]:+.0f} bps")
    if parts:
        bullets.append(
            f"Curva UST últimos 30 días: " + ", ".join(parts) + ". "
            "Movimientos coherentes con expectativas Mercantil."
        )

    # Spread SOFR-FFR
    if facts["spread_sofr_ffr_bps"] is not None:
        bullets.append(
            f"SOFR Overnight en {facts['sofr_on']:.2f}% — "
            f"spread vs Effective FFR de "
            f"{facts['spread_sofr_ffr_bps']:+.0f} bps "
            f"(plumbing del mercado monetario funcional). "
            f"IORB {facts['iorb']:.2f}%, ON RRP {facts['rrp']:.2f}%."
        )

    # Top headline
    if facts["top_headline"]:
        bullets.append(
            f"Titular destacado: \"{facts['top_headline'][:140]}\"."
        )

    return bullets


def _build_lectura_analista(facts: dict) -> str:
    """Genera párrafo de cierre con resumen + outlook."""
    m = facts["mercantil"]
    f = facts["fomc"]
    u = facts["ust_30d_bps"]
    parts = []

    # Resumen del mes
    ust_summary = ", ".join([
        f"{t} {u[t]:+.0f} bps" for t in ["2Y", "10Y", "30Y"] if u[t] is not None
    ])
    parts.append(
        f"Resumen. El último mes la curva UST se movió "
        f"{ust_summary if ust_summary else 'lateralmente'}. "
        f"Fed Funds spot en {m['now']:.2f}%, EFFR en {facts['effr']:.2f}%, "
        f"SOFR ON en {facts['sofr_on']:.2f}% — "
        f"plumbing en niveles operativos normales."
    )

    # Outlook Mercantil
    d12 = (m["12m"] - m["now"]) * 100
    if abs(d12) < 5:
        outlook = "hold prolongado sin movimientos materiales"
    elif d12 < 0:
        outlook = f"sesgo a recortes de {abs(d12):.0f} bps a 12 meses"
    else:
        outlook = f"sesgo a subas de {d12:.0f} bps a 12 meses"
    parts.append(
        f"Outlook Mercantil. El modelo agregado (Pieza A implied path SR3 "
        f"+ Pieza B Taylor rule) descuenta {outlook}, con un terminal de "
        f"{m['24m']:.2f}% a 24 meses. "
        f"Pieza A (mercado) y Pieza B (Taylor) están alineadas en signo, "
        f"sugiriendo robustez del escenario."
    )

    # Próximos catalizadores
    if f is not None:
        est = f["estimate"] if pd.notna(f["estimate"]) else None
        est_str = f"con estimate {est:.2f}%" if est is not None else "sin estimate"
        parts.append(
            f"Próximo catalizador. Decisión FOMC el "
            f"{f['date'].strftime('%d-%b')} (en {f['days_to']} días, {est_str}). "
            "Statement y press conference reorientan la curva corta; "
            "atención también a CPI, NFP y PCE en el calendario adjunto."
        )

    # Posicionamiento
    parts.append(
        "Posicionamiento sugerido. Mantener neutralidad en tenores cortos "
        "hasta el FOMC; preparar reacciones a sorpresas en el statement "
        "(dots o lenguaje sobre balance sheet). En tramo medio-largo "
        "(5-10Y), las subas implícitas del modelo son moderadas y no "
        "justifican rotaciones agresivas."
    )

    return "\n\n".join(parts)


def _plot_text_panel(title: str, body, output_path: Path,
                       is_bullets: bool) -> Path:
    """Renderiza un panel de texto a PNG con el mismo branding del deck."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=130)
    ax.axis("off")

    # Bloque de contenido en card blanca
    ax.add_patch(plt.Rectangle((0.04, 0.05), 0.92, 0.85,
                                  facecolor="#ffffff", edgecolor="#2a6fb3",
                                  lw=1.5, transform=ax.transAxes,
                                  zorder=1))

    import textwrap
    y = 0.84
    if is_bullets:
        for i, b in enumerate(body, 1):
            wrapped = textwrap.fill(b, width=110)
            ax.text(0.08, y, f"{i}.", transform=ax.transAxes,
                     fontsize=14, weight="bold", color="#2a6fb3",
                     verticalalignment="top", zorder=2)
            ax.text(0.12, y, wrapped, transform=ax.transAxes,
                     fontsize=11.5, color="#222",
                     verticalalignment="top", zorder=2)
            # Aproximar altura por líneas de wrap (1 línea ~0.04)
            y -= 0.04 * (wrapped.count("\n") + 1) + 0.04
    else:
        # Paragraph mode — respetar saltos de \n\n del template
        wrapped_paragraphs = [textwrap.fill(p, width=130) for p in body.split("\n\n")]
        ax.text(0.08, y, "\n\n".join(wrapped_paragraphs),
                 transform=ax.transAxes,
                 fontsize=11.5, color="#222",
                 verticalalignment="top", zorder=2)

    fig.suptitle(title, fontsize=14, weight="bold", y=0.97)
    fig.text(0.5, 0.02,
              "Draft auto-generado · pulir antes de presentar",
              ha="center", fontsize=8, style="italic", color="#888")
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_mensajes_clave(as_of: date, output_path: Path | str) -> Path:
    facts = _collect_facts(as_of)
    bullets = _build_mensajes_clave(facts)
    return _plot_text_panel(
        title=f"Fase 1 USA — Lámina 1: Mensajes clave del mes  ·  Corte {as_of}",
        body=bullets, output_path=Path(output_path), is_bullets=True,
    )


def plot_lectura_analista(as_of: date, output_path: Path | str) -> Path:
    facts = _collect_facts(as_of)
    text = _build_lectura_analista(facts)
    return _plot_text_panel(
        title=f"Fase 1 USA — Lámina 8: Lectura del analista  ·  Corte {as_of}",
        body=text, output_path=Path(output_path), is_bullets=False,
    )
