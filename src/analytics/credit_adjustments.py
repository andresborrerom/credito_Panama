"""Ajustes crediticios al modelo base PD × LGD × EAD.

Complementa src/analytics/provisiones.py con dos mecánicas que la calculadora
base no captura y que aparecen en la mayoría de casos reales corporativos:

1. **Ajuste de LGD por garantías** (Credit Risk Mitigation, Basilea III):
   - Corporate guarantee: reduce LGD proporcional al ratio (cobertura efectiva
     del garantor / exposición) y a la calidad crediticia del garantor.
   - Personal guarantee: SBP / Basilea no permite reducción de LGD por personal
     guarantee de personas físicas para efectos regulatorios. Se puede modelar
     como "cushion informal" pero NO reduce el capital regulatorio.
   - Colateral real (efectivo, valores IG): reduce LGD según haircut regulatorio.

2. **Multiplicador de PD por señales cualitativas** (Pillar 2 SBP):
   Cuando el rating externo "promedia" señales que sugieren mayor PD real:
   - Cobertura FCO / Servicio deuda < 1.0x
   - Deuda financiera / EBITDA > 6.0x
   - Concentración de ingresos en un único cliente
   - Ausencia de EEFF consolidados auditados del garantor/grupo
   - Estructura SPV con dependencia de rollover

Todas las tablas y multiplicadores tienen procedencia explícita. Los defaults
son editables por el analista.

Referencia principal:
- Basilea III Standardised Approach for Credit Risk Mitigation (BCBS 2017,
  sections CRE22 y CRE23).
- SBP Acuerdo 3-2016 no describe explícitamente reducciones por garantías
  corporativas — se aplica la lógica Basilea análoga.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# --------------------------------------------------------------------- #
# LGD adjustments by guarantee
# --------------------------------------------------------------------- #

# Haircut aplicado al valor de la corporate guarantee según rating del garantor.
# Fuente: BCBS 2017 CRE22 (SA-CCR) — ajustado para escala local Panamá.
# Interpretación: fracción del valor de la garantía que efectivamente cuenta
# como cobertura. Un garantor T3 A(pan) da 80% de cobertura efectiva;
# garantor T4 BBB solo 60%; T5 unrated solo 30%.
GUARANTOR_HAIRCUT_BY_TIER: dict[str, dict] = {
    "T1": {"haircut": 0.05, "cobertura_efectiva": 0.95, "source": "BCBS 2017 CRE22 — garantor AAA/soberano"},
    "T2": {"haircut": 0.10, "cobertura_efectiva": 0.90, "source": "BCBS 2017 CRE22 — garantor AA/A+"},
    "T3": {"haircut": 0.20, "cobertura_efectiva": 0.80, "source": "BCBS 2017 CRE22 — garantor A"},
    "T4": {"haircut": 0.40, "cobertura_efectiva": 0.60, "source": "BCBS 2017 CRE22 — garantor BBB"},
    "T5": {"haircut": 0.70, "cobertura_efectiva": 0.30, "source": "BCBS 2017 CRE22 — garantor BB o unrated (aplicar con cautela)"},
}

# Reglas de admisibilidad de garantías
GUARANTEE_ELIGIBILITY = {
    "corporate": {
        "eligible": True,
        "note": "Corporate guarantee de una entidad legal identificable con EEFF disponibles.",
    },
    "corporate_no_audited": {
        "eligible": False,
        "note": (
            "Corporate guarantee de entidad sin EEFF consolidados auditados: "
            "SBP/Basilea aceptan solo si el garantor está en el mismo mercado regulado. "
            "Sin auditoría no hay base para haircut. Se recomienda NO descontar LGD."
        ),
    },
    "personal": {
        "eligible": False,
        "note": (
            "Personal guarantee (persona física): NO admitida como CRM para efectos "
            "de LGD regulatoria bajo BCBS 2017. Puede documentarse como 'cushion informal' "
            "pero NO reduce el capital requerido."
        ),
    },
    "cash_collateral": {
        "eligible": True,
        "note": "Efectivo o equivalentes en la misma moneda: haircut 0% (BCBS CRE22).",
    },
    "government_securities": {
        "eligible": True,
        "note": "Valores soberanos AAA: haircut 0.5-4% según plazo residual (BCBS CRE22).",
    },
}


def adjust_lgd_by_guarantees(
    lgd_base: float,
    ead: float,
    corporate_guarantee_amount: float = 0.0,
    corporate_guarantee_tier: Optional[str] = None,
    corporate_guarantee_audited: bool = True,
    personal_guarantee: bool = False,
    cash_collateral_amount: float = 0.0,
) -> dict:
    """Ajusta la LGD base por garantías reconocidas.

    Args:
        lgd_base: LGD sin garantía (0-1)
        ead: exposición
        corporate_guarantee_amount: monto USD de garantía corporativa
        corporate_guarantee_tier: tier T1..T5 del garantor
        corporate_guarantee_audited: si el garantor tiene EEFF auditados consolidados
        personal_guarantee: si hay garantía personal (informativo, no reduce LGD)
        cash_collateral_amount: efectivo pledged (reduce LGD 1:1)

    Returns:
        dict con lgd_ajustada, cobertura efectiva, procedencia y notes.
    """
    if lgd_base < 0 or lgd_base > 1:
        raise ValueError(f"lgd_base debe estar en [0,1], recibido {lgd_base}")
    if ead <= 0:
        raise ValueError(f"ead debe ser positivo, recibido {ead}")

    notes = []

    # ---- Corporate guarantee ----
    corp_covered_effective = 0.0
    if corporate_guarantee_amount > 0:
        if not corporate_guarantee_audited:
            notes.append(
                "Corporate guarantee IGNORADA para efectos de LGD: garantor sin "
                "EEFF consolidados auditados (BCBS 2017 requiere transparencia)."
            )
        elif corporate_guarantee_tier is None:
            notes.append(
                "Corporate guarantee IGNORADA: falta el rating del garantor."
            )
        elif corporate_guarantee_tier not in GUARANTOR_HAIRCUT_BY_TIER:
            notes.append(
                f"Corporate guarantee IGNORADA: tier '{corporate_guarantee_tier}' no reconocido."
            )
        else:
            haircut = GUARANTOR_HAIRCUT_BY_TIER[corporate_guarantee_tier]["haircut"]
            corp_covered_effective = min(
                corporate_guarantee_amount * (1 - haircut),
                ead,
            )
            notes.append(
                f"Corporate guarantee tier {corporate_guarantee_tier}: "
                f"${corporate_guarantee_amount:,.0f} × (1 - {haircut*100:.0f}% haircut) "
                f"= ${corp_covered_effective:,.0f} cobertura efectiva."
            )

    # ---- Personal guarantee ----
    if personal_guarantee:
        notes.append(
            "Personal guarantee registrada pero NO se descuenta de LGD "
            "(no admitida como CRM bajo BCBS 2017 / SBP)."
        )

    # ---- Cash collateral ----
    cash_covered = min(cash_collateral_amount, ead)
    if cash_covered > 0:
        notes.append(f"Cash collateral: ${cash_covered:,.0f} cobertura 1:1 (haircut 0%).")

    # ---- Cálculo LGD efectiva ----
    # La cobertura total no puede exceder EAD.
    cobertura_total = min(corp_covered_effective + cash_covered, ead)
    fraccion_cubierta = cobertura_total / ead if ead > 0 else 0.0
    # Sobre la parte cubierta LGD → 0 (recuperación via garantía).
    # Sobre la parte NO cubierta se mantiene LGD base.
    lgd_ajustada = lgd_base * (1 - fraccion_cubierta)

    return {
        "lgd_base": lgd_base,
        "lgd_ajustada": lgd_ajustada,
        "cobertura_efectiva_usd": cobertura_total,
        "fraccion_cubierta": fraccion_cubierta,
        "reduccion_lgd_pp": (lgd_base - lgd_ajustada) * 100,
        "corp_effective_coverage": corp_covered_effective,
        "cash_coverage": cash_covered,
        "personal_guarantee_flagged": personal_guarantee,
        "notes": notes,
    }


# --------------------------------------------------------------------- #
# PD adjustment by qualitative signals (Pillar 2)
# --------------------------------------------------------------------- #

# Multiplicadores de PD por señal cualitativa. Fuente: benchmark de la literatura
# de credit risk (Standard & Poor's Credit Ratings Methodology, Moody's KMV
# structural model). Ajustables por el analista.
PD_QUALITATIVE_SIGNALS: dict[str, dict] = {
    "fco_cover_below_1x": {
        "multiplier": 2.0,
        "trigger": "FCO / Servicio de la deuda < 1.0x",
        "source": "Benchmark bank internal ratings — cover ratio < 1 duplica PD histórica",
        "confidence": "media",
    },
    "d_ebitda_above_6x": {
        "multiplier": 1.5,
        "trigger": "Deuda financiera / EBITDA > 6.0x",
        "source": "S&P Corporate Rating Methodology — leverage cap",
        "confidence": "media",
    },
    "revenue_concentration_single_client": {
        "multiplier": 1.3,
        "trigger": "≥ 80% de ingresos con un único cliente",
        "source": "Moody's Rating Methodology — customer concentration risk",
        "confidence": "media",
    },
    "no_consolidated_audited_financials": {
        "multiplier": 1.5,
        "trigger": "Ausencia de EEFF consolidados auditados del grupo garantor",
        "source": "Opacidad → información asimétrica → PD implícita mayor",
        "confidence": "media",
    },
    "spv_rollover_dependent": {
        "multiplier": 1.2,
        "trigger": "Estructura SPV que depende de rollover recurrente",
        "source": "Moody's project finance methodology — refinance risk",
        "confidence": "media",
    },
    "spot_price_exposure": {
        "multiplier": 1.2,
        "trigger": "Ingresos 100% a precio spot (sin PPA / hedge)",
        "source": "Basilea — mercado volátil → mayor PD",
        "confidence": "media",
    },
}


def adjust_pd_by_qualitative_signals(
    pd_base: float,
    active_signals: list[str],
    custom_multipliers: Optional[dict[str, float]] = None,
) -> dict:
    """Multiplica PD por combinación de señales cualitativas activas.

    Args:
        pd_base: PD anual base (del rating externo)
        active_signals: lista de claves de PD_QUALITATIVE_SIGNALS activas
        custom_multipliers: override para multiplicadores específicos

    Regla de composición: los multiplicadores se aplican multiplicativamente
    pero se aplica un cap para que la PD ajustada no exceda el multiplicador
    total de 5× (razonable — más allá de eso conviene degradar el tier).
    """
    if pd_base < 0 or pd_base > 1:
        raise ValueError(f"pd_base debe estar en [0,1], recibido {pd_base}")

    total_multiplier = 1.0
    applied = []
    for sig in active_signals:
        if sig not in PD_QUALITATIVE_SIGNALS:
            raise ValueError(f"señal '{sig}' no reconocida. Válidas: {list(PD_QUALITATIVE_SIGNALS)}")
        m = (custom_multipliers or {}).get(sig, PD_QUALITATIVE_SIGNALS[sig]["multiplier"])
        total_multiplier *= m
        applied.append({"signal": sig, "multiplier": m,
                         "trigger": PD_QUALITATIVE_SIGNALS[sig]["trigger"]})

    # Cap a 5× para evitar valores absurdos
    capped = False
    if total_multiplier > 5.0:
        total_multiplier = 5.0
        capped = True

    pd_ajustada = min(pd_base * total_multiplier, 1.0)

    return {
        "pd_base": pd_base,
        "pd_ajustada": pd_ajustada,
        "total_multiplier": total_multiplier,
        "cap_reached": capped,
        "applied_signals": applied,
        "n_signals": len(applied),
    }


# --------------------------------------------------------------------- #
# Combined adjustment
# --------------------------------------------------------------------- #

@dataclass(frozen=True)
class AdjustedCredit:
    """Resultado del ajuste combinado PD + LGD."""

    pd_base: float
    pd_ajustada: float
    lgd_base: float
    lgd_ajustada: float
    ead: float
    horizon_years: float
    el_base: float
    el_ajustada: float
    delta_el_pct: float
    active_signals: list[str]
    guarantee_notes: list[str]

    def as_dict(self) -> dict:
        return {
            "pd_base_pct": round(self.pd_base * 100, 4),
            "pd_ajustada_pct": round(self.pd_ajustada * 100, 4),
            "lgd_base_pct": round(self.lgd_base * 100, 2),
            "lgd_ajustada_pct": round(self.lgd_ajustada * 100, 2),
            "ead": round(self.ead, 2),
            "horizon_years": self.horizon_years,
            "el_base": round(self.el_base, 2),
            "el_ajustada": round(self.el_ajustada, 2),
            "delta_el_pct": round(self.delta_el_pct, 1),
            "active_signals": self.active_signals,
            "guarantee_notes": self.guarantee_notes,
        }


def compute_adjusted_credit(
    pd_base: float,
    lgd_base: float,
    ead: float,
    horizon_years: float = 1.0,
    active_signals: Optional[list[str]] = None,
    corporate_guarantee_amount: float = 0.0,
    corporate_guarantee_tier: Optional[str] = None,
    corporate_guarantee_audited: bool = True,
    personal_guarantee: bool = False,
    cash_collateral_amount: float = 0.0,
) -> AdjustedCredit:
    """Aplica ajustes PD (señales cualitativas) + LGD (garantías) al EL base."""
    from src.analytics.provisiones import cumulative_pd, expected_loss

    active_signals = active_signals or []

    # Ajuste PD
    pd_adj_res = adjust_pd_by_qualitative_signals(pd_base, active_signals)
    pd_ajustada = pd_adj_res["pd_ajustada"]

    # Ajuste LGD
    lgd_adj_res = adjust_lgd_by_guarantees(
        lgd_base=lgd_base, ead=ead,
        corporate_guarantee_amount=corporate_guarantee_amount,
        corporate_guarantee_tier=corporate_guarantee_tier,
        corporate_guarantee_audited=corporate_guarantee_audited,
        personal_guarantee=personal_guarantee,
        cash_collateral_amount=cash_collateral_amount,
    )
    lgd_ajustada = lgd_adj_res["lgd_ajustada"]

    # EL base vs ajustada
    el_base = expected_loss(pd_base, lgd_base, ead, horizon_years=horizon_years)
    el_ajustada = expected_loss(pd_ajustada, lgd_ajustada, ead, horizon_years=horizon_years)
    delta_pct = ((el_ajustada - el_base) / el_base * 100) if el_base > 0 else 0.0

    return AdjustedCredit(
        pd_base=pd_base,
        pd_ajustada=pd_ajustada,
        lgd_base=lgd_base,
        lgd_ajustada=lgd_ajustada,
        ead=ead,
        horizon_years=horizon_years,
        el_base=el_base,
        el_ajustada=el_ajustada,
        delta_el_pct=delta_pct,
        active_signals=active_signals,
        guarantee_notes=lgd_adj_res["notes"],
    )
