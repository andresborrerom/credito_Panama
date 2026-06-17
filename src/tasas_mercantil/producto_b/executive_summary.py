"""Output (3) — Mensaje primera diapositiva para el comité.

Genera 1-2 frases por horizonte (resto del año + próximos 12 meses) listas
para pegar en la primera diapositiva del deck mensual.

Filosofía:
- Una frase corta para "centro + intervalo + cobertura".
- Una frase adicional si el régimen está en alerta (transparencia ex-ante).
- Sin jerga: "retorno esperado", "con X% confianza entre A y B".

Uso:
  >>> from datetime import date
  >>> summary = compose_executive_summary(date(2024, 6, 30))
  >>> print(summary["resto_del_anio"]["message_full"])
  >>> print(summary["proximos_12m"]["message_full"])
"""
from __future__ import annotations
from datetime import date
from typing import Optional

from .horizons import both_horizons
from .portfolio_aggregator import forecast_luz_portfolio, PortfolioForecast


def _horizon_label(name: str, as_of: date, h: int) -> str:
    """Etiqueta humana del horizonte."""
    if name == "resto_del_anio":
        return f"resto del año (cierre {as_of.year}, {h} meses)"
    if name == "proximos_12m":
        return f"próximos 12 meses (cierre {date(as_of.year + 1, as_of.month, 1).strftime('%b %Y')})"
    return name


def _regime_disclaimer(worst_regime: str) -> str:
    if worst_regime == "stress_extremo":
        return ("Régimen de mercado en stress extremo — los componentes ETF "
                "del modelo no emiten intervalo confiable; el rango reportado "
                "viene del sweet spot endógeno con hit rate empírico ~67% en "
                "este régimen. Reservar margen extra en las decisiones.")
    if worst_regime == "stress_alto":
        return ("Régimen de mercado en stress alto — confianza degradada en "
                "el intervalo (hit rate empírico ~77-80%). Tratar como "
                "referencia, no decisor.")
    return ""


def _format_messages(pf: PortfolioForecast, horizon_label: str) -> dict:
    """Genera message_short y message_full para un horizonte."""
    p = int(pf.sweet_spot["p"] * 100)
    center_pct = pf.center * 100
    lo_pct = pf.sweet_spot["lo"] * 100
    hi_pct = pf.sweet_spot["hi"] * 100
    cov_modelado = (pf.coverage_directa + pf.coverage_proxy) * 100
    cov_directa = pf.coverage_directa * 100

    short = (
        f"Retorno esperado de LUZ para {horizon_label}: "
        f"centro {center_pct:+.1f}%, "
        f"con {p}% de confianza entre {lo_pct:+.1f}% y {hi_pct:+.1f}%."
    )
    coverage_line = (
        f"Cobertura modelo: {cov_directa:.0f}% del portafolio modelado "
        f"directamente, {cov_modelado:.0f}% incluyendo proxies por "
        f"asset-class."
    )
    disclaimer = _regime_disclaimer(pf.worst_regime)
    full_parts = [short, coverage_line]
    if disclaimer:
        full_parts.append(disclaimer)

    return {
        "message_short": short,
        "message_full": " ".join(full_parts),
        "coverage_line": coverage_line,
        "regime_disclaimer": disclaimer,
    }


def compose_executive_summary(as_of: date) -> dict:
    """Compila el mensaje de primera diapositiva para los 2 horizontes.

    Args:
        as_of: fecha de corte (recomendado fin de mes).

    Returns:
        dict con claves "resto_del_anio" (si h > 0) y "proximos_12m".
        Cada entrada contiene:
            - horizon_months
            - horizon_label  (texto humano)
            - center, sweet_p, sweet_lo, sweet_hi
            - coverage_directa, coverage_proxy, coverage_cash
            - worst_regime
            - message_short  (1 frase para el titular)
            - message_full   (2-3 frases con cobertura y disclaimer)
            - coverage_line  (frase de cobertura aislada)
            - regime_disclaimer (texto del régimen si aplica, sino "")
    """
    horizons = both_horizons(as_of)
    out: dict = {}
    for name, h in horizons.items():
        if h == 0:
            continue
        pf = forecast_luz_portfolio(as_of, h)
        label = _horizon_label(name, as_of, h)
        msgs = _format_messages(pf, label)
        out[name] = {
            "horizon_months": h,
            "horizon_label": label,
            "center": pf.center,
            "sweet_p": pf.sweet_spot["p"],
            "sweet_lo": pf.sweet_spot["lo"],
            "sweet_hi": pf.sweet_spot["hi"],
            "coverage_directa": pf.coverage_directa,
            "coverage_proxy": pf.coverage_proxy,
            "coverage_cash": pf.coverage_cash,
            "worst_regime": pf.worst_regime,
            **msgs,
        }
    return out
