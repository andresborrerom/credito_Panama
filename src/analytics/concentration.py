"""Recargo de capital por concentración (Pillar 2 SBP / Basilea).

Cuando una posición individual o la exposición a un grupo económico excede
umbrales prudenciales, la SBP y las mejores prácticas internas exigen un
recargo de capital SOBRE el requerimiento base del Pillar 1.

Fuentes:
- SBP Acuerdo 8-2018 (Riesgo de concentración)
- BCBS Principles for the Management of Credit Risk (2000), sección
  "Concentration risk in banking books"
- Reguladores prudenciales suelen imponer recargos 10-50% del capital base
  cuando la exposición individual > 10% del capital regulatorio.

Los umbrales por defecto son referenciales — cada banco tiene sus propios
límites internos aprobados por su ALCO.
"""

from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------- #
# Umbrales por defecto
# --------------------------------------------------------------------- #

# Nivel de exposición como % del capital regulatorio del banco y su recargo.
# Fuente: SBP Acuerdo 8-2018 marca límite "individual" en 25% del capital
# primario, pero los recargos internos se aplican ANTES de llegar a ese cap.
CONCENTRATION_CHARGE_TABLE_INDIVIDUAL: list[dict] = [
    {"threshold_pct_capital": 0.05, "charge_pct": 0.00,
     "label": "≤ 5% capital: sin recargo",
     "source": "buenas prácticas ALCO"},
    {"threshold_pct_capital": 0.10, "charge_pct": 0.15,
     "label": "5-10% capital: recargo 15%",
     "source": "Pillar 2 Basilea — concentration risk"},
    {"threshold_pct_capital": 0.15, "charge_pct": 0.25,
     "label": "10-15% capital: recargo 25%",
     "source": "Pillar 2 Basilea"},
    {"threshold_pct_capital": 0.20, "charge_pct": 0.50,
     "label": "15-20% capital: recargo 50%",
     "source": "SBP Acuerdo 8-2018 — proximidad al límite regulatorio (25%)"},
    {"threshold_pct_capital": 1.00, "charge_pct": 1.00,
     "label": "> 20% capital: recargo 100% (revisión ALCO obligatoria)",
     "source": "SBP Acuerdo 8-2018 — cerca del cap prudencial"},
]

# Exposición agregada al mismo grupo económico
CONCENTRATION_CHARGE_TABLE_GROUP: list[dict] = [
    {"threshold_pct_capital": 0.10, "charge_pct": 0.00,
     "label": "≤ 10% capital al grupo: sin recargo",
     "source": "buenas prácticas ALCO"},
    {"threshold_pct_capital": 0.20, "charge_pct": 0.15,
     "label": "10-20% capital al grupo: recargo 15%",
     "source": "Pillar 2"},
    {"threshold_pct_capital": 0.30, "charge_pct": 0.30,
     "label": "20-30% capital al grupo: recargo 30%",
     "source": "Pillar 2"},
    {"threshold_pct_capital": 1.00, "charge_pct": 0.75,
     "label": "> 30% capital al grupo: recargo 75%",
     "source": "SBP Acuerdo 8-2018 — grupo económico"},
]

# Concentración sectorial (no ligada al capital sino al portafolio total).
CONCENTRATION_CHARGE_SECTORIAL: list[dict] = [
    {"threshold_pct_portafolio": 0.15, "charge_pct": 0.00, "label": "≤ 15% sector: sin recargo"},
    {"threshold_pct_portafolio": 0.25, "charge_pct": 0.10, "label": "15-25% sector: recargo 10%"},
    {"threshold_pct_portafolio": 0.40, "charge_pct": 0.25, "label": "25-40% sector: recargo 25%"},
    {"threshold_pct_portafolio": 1.00, "charge_pct": 0.50, "label": "> 40% sector: recargo 50%"},
]


def _find_bucket(value: float, table: list[dict], key: str = "threshold_pct_capital") -> dict:
    """Encuentra el bucket aplicable en una tabla ordenada por threshold ascendente."""
    for row in table:
        if value <= row[key]:
            return row
    return table[-1]


@dataclass(frozen=True)
class ConcentrationResult:
    """Resultado del cálculo de recargo por concentración."""

    exposure_individual: float
    exposure_group_total: float
    capital_regulatorio_banco: float
    portafolio_total_banco: float
    pct_capital_individual: float
    pct_capital_group: float
    pct_portafolio_sector: float
    charge_individual: float
    charge_group: float
    charge_sectorial: float
    charge_total: float
    capital_base: float
    capital_with_concentration: float
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "exposure_individual": round(self.exposure_individual, 2),
            "exposure_group_total": round(self.exposure_group_total, 2),
            "pct_capital_individual_pct": round(self.pct_capital_individual * 100, 2),
            "pct_capital_group_pct": round(self.pct_capital_group * 100, 2),
            "pct_portafolio_sector_pct": round(self.pct_portafolio_sector * 100, 2),
            "charge_individual_pct": round(self.charge_individual * 100, 1),
            "charge_group_pct": round(self.charge_group * 100, 1),
            "charge_sectorial_pct": round(self.charge_sectorial * 100, 1),
            "charge_total_pct": round(self.charge_total * 100, 1),
            "capital_base": round(self.capital_base, 2),
            "capital_with_concentration": round(self.capital_with_concentration, 2),
            "delta_capital": round(self.capital_with_concentration - self.capital_base, 2),
            "notes": self.notes,
        }


def concentration_charge(
    exposure_individual: float,
    capital_base: float,
    capital_regulatorio_banco: float,
    exposure_group_total: float = 0.0,
    portafolio_total_banco: float = 0.0,
    exposure_sector: float = 0.0,
) -> ConcentrationResult:
    """Calcula el recargo total por concentración sobre el capital base.

    Los tres recargos se aplican de forma multiplicativa (no aditiva):
        capital_final = capital_base × (1 + charge_ind) × (1 + charge_grp) × (1 + charge_sec)

    Esto es más conservador que sumar y refleja que las concentraciones se
    componen (mismo emisor + mismo grupo + mismo sector = triple riesgo).

    Args:
        exposure_individual: exposición a esta posición individual
        capital_base: capital base calculado por Pillar 1 (RWA × 8%)
        capital_regulatorio_banco: capital regulatorio total del banco
        exposure_group_total: exposición total al grupo económico
                              (incluye esta posición + otras existentes)
        portafolio_total_banco: exposición total del portafolio
        exposure_sector: exposición total al sector (incluye esta)
    """
    if capital_regulatorio_banco <= 0:
        raise ValueError("capital_regulatorio_banco debe ser positivo")
    if capital_base < 0:
        raise ValueError("capital_base debe ser no negativo")

    # --- Individual ---
    pct_ind = exposure_individual / capital_regulatorio_banco
    row_ind = _find_bucket(pct_ind, CONCENTRATION_CHARGE_TABLE_INDIVIDUAL)
    ch_ind = row_ind["charge_pct"]

    # --- Group ---
    pct_grp = exposure_group_total / capital_regulatorio_banco if exposure_group_total > 0 else 0.0
    row_grp = _find_bucket(pct_grp, CONCENTRATION_CHARGE_TABLE_GROUP)
    ch_grp = row_grp["charge_pct"]

    # --- Sectorial ---
    pct_sec = 0.0
    ch_sec = 0.0
    if portafolio_total_banco > 0 and exposure_sector > 0:
        pct_sec = exposure_sector / portafolio_total_banco
        row_sec = _find_bucket(pct_sec, CONCENTRATION_CHARGE_SECTORIAL,
                                key="threshold_pct_portafolio")
        ch_sec = row_sec["charge_pct"]

    # --- Composición multiplicativa ---
    multiplier = (1 + ch_ind) * (1 + ch_grp) * (1 + ch_sec)
    charge_total = multiplier - 1

    capital_final = capital_base * multiplier

    notes = [
        f"Individual: {pct_ind*100:.2f}% del capital → {row_ind['label']}",
    ]
    if exposure_group_total > 0:
        notes.append(f"Grupo económico: {pct_grp*100:.2f}% → {row_grp['label']}")
    if portafolio_total_banco > 0 and exposure_sector > 0:
        notes.append(f"Sector: {pct_sec*100:.2f}% → {row_sec['label']}")
    notes.append(
        f"Recargo total (multiplicativo): +{charge_total*100:.1f}% → "
        f"capital: ${capital_base:,.0f} → ${capital_final:,.0f}"
    )

    return ConcentrationResult(
        exposure_individual=exposure_individual,
        exposure_group_total=exposure_group_total,
        capital_regulatorio_banco=capital_regulatorio_banco,
        portafolio_total_banco=portafolio_total_banco,
        pct_capital_individual=pct_ind,
        pct_capital_group=pct_grp,
        pct_portafolio_sector=pct_sec,
        charge_individual=ch_ind,
        charge_group=ch_grp,
        charge_sectorial=ch_sec,
        charge_total=charge_total,
        capital_base=capital_base,
        capital_with_concentration=capital_final,
        notes=notes,
    )
