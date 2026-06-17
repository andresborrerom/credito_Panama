"""Tipos de datos para narrativa editorial — mensajes del TL;DR y vistas tacticas.

Lo que aqui esta hardcoded es la NARRATIVA del corte (mensajes que Camilo + Andres
deciden cada mes). El render lee de aqui y compone las laminas.

Para cortes recurrentes, esto va a venir de narrativa/mensajes_clave.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Conviction = Literal["Alta", "Media", "Baja"]


from pathlib import Path

import yaml


@dataclass
class Editorial:
    """Bloque al pie de cada lámina con cuatro lecturas estructuradas.

    Patrón Apollo + nuestro: cada lámina aclara qué dice, de dónde sale, qué
    acción dispara, y cómo se lee si hay gráfico. Sin esto la lámina cae en
    la trampa de "interpretar libre".
    """
    que_dice: str        # la conclusión central de la lámina
    por_que: str         # de dónde sale (fuente, cálculo, observación)
    para_que: str        # qué acción concreta dispara
    como_se_lee: str = ""  # explicación del gráfico/tabla — vacío si trivial


@dataclass
class TLDRMessage:
    """Un mensaje del TL;DR. Maximo 3 por corte."""
    headline: str            # 1 frase, max 130 caracteres. Empieza con "Creemos que..."
    conviction: Conviction
    relevant_unit: str       # unidad del grupo a la que principalmente le pega
    trigger: str             # qué dato/evento confirma o refuta


@dataclass
class TacticalView:
    """Una vista tactica. Forma la tabla de la lamina 2."""
    activo: str              # ej. "UST 2-5Y", "TIPS 10Y", "Panamá soberano 10Y"
    direccion: str           # "Overweight" | "Neutral" | "Underweight" | "Long" | "Short"
    horizonte: str           # "3M" | "6M" | "12M"
    conviction: Conviction
    what: str                # afirmacion concreta (1 frase)
    if_right: str            # consecuencia si se cumple
    if_wrong: str            # costo + mitigacion
    trigger: str             # condicion que confirma/refuta


@dataclass
class CalendarItem:
    """Item de la lamina 9 — calendario + condiciones de revision."""
    fecha: str               # "2026-06-11" o "Mid-June 2026"
    evento: str              # "FOMC decision", "CPI Mayo"
    relevante_para: str      # "Lectura modelo Mercantil", "Lamina 1 mensaje 2"
    importancia: Conviction  # cuán importante es revisar el deck post-evento


@dataclass
class Narrativa:
    """Narrativa completa del corte."""
    report_month: str        # "2026-05"
    as_of: str               # "2026-05-29"
    autor_principal: str     # "Camilo + Andres"
    tldr_messages: list[TLDRMessage] = field(default_factory=list)
    tactical_views: list[TacticalView] = field(default_factory=list)
    calendar: list[CalendarItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader desde YAML (workflow recomendado para cortes recurrentes).
# ---------------------------------------------------------------------------
def load_narrativa(path: Path) -> Narrativa:
    """Lee narrativa.yaml y devuelve Narrativa tipada.

    Schema esperado del YAML:
        corte: "YYYY-MM"
        as_of: "YYYY-MM-DD"
        autor_principal: "str"
        tldr_messages:
          - headline / conviction / relevant_unit / trigger
        tactical_views:
          - activo / direccion / horizonte / conviction / what / if_right / if_wrong / trigger
        calendar:
          - fecha / evento / relevante_para / importancia
        venezuela:
          fuente / bcv_tasa_politica_pct / bcv_encaje_legal_pct / ... (campos VenezuelaSnapshot)
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    return Narrativa(
        report_month=data["corte"],
        as_of=data["as_of"],
        autor_principal=data["autor_principal"],
        tldr_messages=[TLDRMessage(**m) for m in data.get("tldr_messages", [])],
        tactical_views=[TacticalView(**v) for v in data.get("tactical_views", [])],
        calendar=[CalendarItem(**c) for c in data.get("calendar", [])],
    )


# ---------------------------------------------------------------------------
# Narrativa hardcoded del corte 2026-05 — usada como fallback / template.
# ---------------------------------------------------------------------------
def narrativa_2026_05() -> Narrativa:
    return Narrativa(
        report_month="2026-05",
        as_of="2026-05-29",
        autor_principal="Camilo Forero + Andrés Borrero",
        tldr_messages=[
            TLDRMessage(
                headline=(
                    "Creemos que el cut cycle Fed terminó: el mercado descuenta tasas estables a "
                    "ligeramente alcistas en los próximos 24 meses (path implícito 3.63→3.85%)."
                ),
                conviction="Media",
                relevant_unit="Tesorería + Banco Panamá",
                trigger="Próximos CPI core y revisión del dot plot SEP de junio.",
            ),
            TLDRMessage(
                headline=(
                    "UST 10Y a 4.45% con curva positivamente inclinada (2s10s +43 bps) ofrece "
                    "carry atractivo vs cash 3.66%. Sweet spot para libros HTM en 5-10Y."
                ),
                conviction="Alta",
                relevant_unit="Aseguradora + Wealth Management",
                trigger="Cierre UST 10Y > 4.70% obligaría revisar duración objetivo.",
            ),
            TLDRMessage(
                headline=(
                    "Breakevens 10Y 2.41% y 5Y 2.56% señalan mercado cómodo con inflación cerca "
                    "del target Fed. Preferimos UST nominales sobre TIPS en horizonte 12M."
                ),
                conviction="Media",
                relevant_unit="Wealth Management",
                trigger="Tres CPI core consecutivos > 0.4% m/m descartaría la vista.",
            ),
        ],
        tactical_views=[
            TacticalView(
                activo="UST 5-10Y",
                direccion="Overweight",
                horizonte="6M",
                conviction="Alta",
                what="Target yield 4.20-4.50% en UST 10Y. Sweet spot risk-reward.",
                if_right="Lock-in carry + duration upside si Fed retoma cortes.",
                if_wrong="Pérdida de MTM acotada (~5% si UST 10Y sube 100 bps). Carry 4.4% mitiga.",
                trigger="UST 10Y > 4.70% o dot plot junio significativamente más hawkish.",
            ),
            TacticalView(
                activo="TIPS 10Y",
                direccion="Neutral",
                horizonte="6M",
                conviction="Media",
                what="Real yield 2.03% atractivo histórico, pero BE 10Y de 2.41% se ve barato.",
                if_right="Captura yield real positivo + protección inflación cola.",
                if_wrong="Si inflación realizada cae a 2%, TIPS underperformeará vs nominales.",
                trigger="Breakeven 10Y > 2.70% inclinaría hacia overweight TIPS.",
            ),
            TacticalView(
                activo="SOFR forwards corto (0-12M)",
                direccion="Short vs mercado",
                horizonte="6M",
                conviction="Baja",
                what="Mercado descuenta path estable; vemos asimetría hacia hike si CPI sorprende.",
                if_right="Ganancia en posiciones short futures SOFR / OIS.",
                if_wrong="Si Fed efectivamente queda en pausa, costo de carry ~10-15 bps.",
                trigger="Dot plot junio si median 2026 sube ≥25 bps confirmaría la vista.",
            ),
            TacticalView(
                activo="Spread Panamá soberano vs UST",
                direccion="Pendiente análisis Panamá (lámina 6)",
                horizonte="3M",
                conviction="Media",
                what="Spread Panamá 10Y vs UST cotiza ~130 bps; mediana 5Y 240 bps.",
                if_right="Si retorna a media, ganancia ~110 bps en bonos PAN largos.",
                if_wrong="Spread puede mantenerse comprimido si calidad crediticia mejora.",
                trigger="Próxima revisión Moody's/S&P de Panamá soberano.",
            ),
        ],
        calendar=[
            CalendarItem(
                fecha="2026-06-11",
                evento="FOMC + SEP/dot plot",
                relevante_para="Lámina 1 mensaje 1 + Lámina 3 + Tactical View 3",
                importancia="Alta",
            ),
            CalendarItem(
                fecha="2026-06-12",
                evento="CPI Mayo 2026",
                relevante_para="Lámina 1 mensaje 3 + Tactical View 2 (TIPS)",
                importancia="Alta",
            ),
            CalendarItem(
                fecha="2026-06-05",
                evento="Nonfarm Payrolls Mayo",
                relevante_para="Reaction function modelo Pieza B (M-2)",
                importancia="Media",
            ),
            CalendarItem(
                fecha="2026-06-04",
                evento="Decisión BCE",
                relevante_para="Lámina 5 — Global",
                importancia="Media",
            ),
            CalendarItem(
                fecha="2026-06-26",
                evento="PCE Core Mayo",
                relevante_para="Tactical View 2 (TIPS)",
                importancia="Media",
            ),
        ],
    )
