"""Motor de adecuación de capital para renta fija bancaria en Panamá.

Calcula requerimiento de capital sobre exposiciones individuales o portafolios
bajo el enfoque estándar (Standardised Approach) de la SBP, definido en:

  - Acuerdo 1-2015 (Adecuación de Capital, texto único 2020)
  - Acuerdo 3-2016 (Ponderaciones de riesgo — Standardised Approach)

Fórmula base:

  RWA = EAD × Risk Weight(rating, asset_class)
  Requerimiento capital = RWA × CAR_min   (CAR_min = 8% bajo SBP)

Los risk weights por rating y tipo de activo están anotados con procedencia
en RISK_WEIGHTS_SBP. Los defaults son parámetros editables (para sensibilidad
o para calibración cuando se dispone del mapeo interno rating→RW del banco).

Los tiers T1..T5 son los definidos en src/analytics/ratings.py y su mapeo a
rating externo aproximado:
  T1 (AAA(pan))  → RW soberano/AAA
  T2 (AA/A+(pan)) → RW banco/corp AA-A+
  T3 (A(pan))    → RW banco/corp A
  T4 (BBB(pan))  → RW corp BBB
  T5 (BB(pan)/NR) → RW corp BB o unrated
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# --------------------------------------------------------------------- #
# Constantes regulatorias — SBP Acuerdo 1-2015
# --------------------------------------------------------------------- #
# Coeficiente mínimo total de adecuación de capital (Art. 4).
# Fuente: Acuerdo 1-2015 SBP, texto único 2020, Art. 4.
CAR_MIN_TOTAL = 0.08

# Coeficiente mínimo primario (CET1 + AT1) (Art. 4).
CAR_MIN_PRIMARIO = 0.04

# Tope T2 = 100% del capital primario (Art. 6 y 7 del Acuerdo 1-2015).
T2_CAP_MAX_PCT_PRIMARIO = 1.0

# Step-down T2: 20% anual en los últimos 5 años de vida del instrumento.
T2_STEP_DOWN_PCT_ANNUAL = 0.20
T2_STEP_DOWN_YEARS = 5


# --------------------------------------------------------------------- #
# Tabla de risk weights — anclada en Acuerdo 3-2016 (Standardised Approach)
# --------------------------------------------------------------------- #
# Estructura: (asset_class, tier) → dict con rw y procedencia.
#
# asset_class válidos:
#   "SOVEREIGN_PAN"    — Bono/Nota/Letra Tesoro Panamá
#   "SOVEREIGN_OECD"   — Soberano OCDE (referencia)
#   "BANK"             — Exposición a banco
#   "CORPORATE"        — Exposición a corporativo (bono senior estándar)
#   "MORTGAGE_BACKED"  — Bono hipotecario
#   "SUBORDINATED"     — Subordinado T2
#   "AT1"              — Additional Tier 1
#
# Los RW son "sin haircut", aplican sobre EAD directamente.
RISK_WEIGHTS_SBP: dict[tuple[str, str], dict] = {
    # --- Soberano Panamá ---
    # Acuerdo 3-2016: exposiciones al soberano panameño en USD/PAB → RW 0%
    # (Panamá dolarizada, sin riesgo cambiario para deuda local).
    ("SOVEREIGN_PAN", "T1"): {
        "rw": 0.00,
        "source": "SBP Acuerdo 3-2016 — exposiciones al soberano Panamá en USD/PAB",
        "confidence": "alta",
        "note": "Bonos/Notas/Letras del Tesoro panameño.",
    },
    # --- Bancos ---
    # Acuerdo 3-2016: exposiciones a bancos por rating externo.
    # AA- o mejor: 20%; A: 50%; BBB: 50%; BB: 100%; peor: 150%.
    ("BANK", "T1"): {
        "rw": 0.20,
        "source": "SBP Acuerdo 3-2016 — bancos rating AAA/AA (equiv AAA(pan))",
        "confidence": "alta",
        "note": "Top banco sistémico local.",
    },
    ("BANK", "T2"): {
        "rw": 0.20,
        "source": "SBP Acuerdo 3-2016 — bancos rating AA/A+ (equiv AA(pan)/A+(pan))",
        "confidence": "alta",
        "note": "Bancos grandes establecidos.",
    },
    ("BANK", "T3"): {
        "rw": 0.50,
        "source": "SBP Acuerdo 3-2016 — bancos rating A (equiv A(pan))",
        "confidence": "alta",
        "note": "Bancos medianos.",
    },
    ("BANK", "T4"): {
        "rw": 0.50,
        "source": "SBP Acuerdo 3-2016 — bancos rating BBB (equiv BBB(pan))",
        "confidence": "media",
        "note": "Financieras y hipotecarias con rating BBB.",
    },
    ("BANK", "T5"): {
        "rw": 1.00,
        "source": "SBP Acuerdo 3-2016 — bancos rating BB o unrated (equiv BB(pan)/NR)",
        "confidence": "media",
        "note": "Small caps bancarios / unrated — asumido investment grade límite.",
    },
    # --- Corporativos (bono senior estándar) ---
    # Acuerdo 3-2016: exposiciones corporativas por rating externo.
    # AAA-AA: 20%; A: 50%; BBB-BB: 100%; peor BB-: 150%.
    ("CORPORATE", "T1"): {
        "rw": 0.20,
        "source": "SBP Acuerdo 3-2016 — corporativos rating AAA/AA",
        "confidence": "alta",
        "note": "Corporativo top tier (raro localmente).",
    },
    ("CORPORATE", "T2"): {
        "rw": 0.20,
        "source": "SBP Acuerdo 3-2016 — corporativos rating AA",
        "confidence": "alta",
        "note": "Corporativos grandes AA(pan).",
    },
    ("CORPORATE", "T3"): {
        "rw": 0.50,
        "source": "SBP Acuerdo 3-2016 — corporativos rating A",
        "confidence": "alta",
        "note": "Corporativos establecidos A(pan).",
    },
    ("CORPORATE", "T4"): {
        "rw": 1.00,
        "source": "SBP Acuerdo 3-2016 — corporativos rating BBB",
        "confidence": "alta",
        "note": "BBB(pan) — investment grade límite.",
    },
    ("CORPORATE", "T5"): {
        "rw": 1.00,
        "source": "SBP Acuerdo 3-2016 — corporativos rating BB o unrated (RW 100% base)",
        "confidence": "media",
        "note": "BB(pan)/NR. RW 100% base; algunos supervisores exigen 150% para claramente sub-IG.",
    },
    # --- Bonos hipotecarios ---
    # Acuerdo 3-2016: hipotecario respaldado por inmuebles residenciales → 35%.
    # Bonos hipotecarios corporativos con cartera hipotecaria subyacente aplican
    # típicamente el look-through al RW del pool subyacente (35% residencial).
    ("MORTGAGE_BACKED", "T1"): {
        "rw": 0.35,
        "source": "SBP Acuerdo 3-2016 — hipotecas residenciales look-through",
        "confidence": "media (look-through simplificado)",
        "note": "Bono hipotecario emisor top.",
    },
    ("MORTGAGE_BACKED", "T2"): {
        "rw": 0.35,
        "source": "SBP Acuerdo 3-2016 — hipotecas residenciales look-through",
        "confidence": "media",
        "note": "Bono hipotecario emisor grande.",
    },
    ("MORTGAGE_BACKED", "T3"): {
        "rw": 0.50,
        "source": "SBP Acuerdo 3-2016 — hipotecas residenciales look-through + spread crediticio emisor",
        "confidence": "media",
        "note": "Bono hipotecario emisor mediano.",
    },
    ("MORTGAGE_BACKED", "T4"): {
        "rw": 0.75,
        "source": "SBP Acuerdo 3-2016 — hipotecas + spread crediticio emisor BBB",
        "confidence": "media",
        "note": "Hipotecaria establecida BBB(pan).",
    },
    ("MORTGAGE_BACKED", "T5"): {
        "rw": 1.00,
        "source": "SBP Acuerdo 3-2016 — hipotecas + spread crediticio emisor BB/NR",
        "confidence": "media (podría requerir look-through detallado)",
        "note": "Hipotecaria pequeña/unrated.",
    },
    # --- Subordinado T2 ---
    # Acuerdo 3-2016: exposiciones subordinadas a bancos → RW típicamente 150%.
    # Basilea III finalización 2017 estableció RW subordinado = 150% ante los holders.
    ("SUBORDINATED", "T1"): {
        "rw": 1.00,
        "source": "SBP inferido de Basilea III finalización 2017 — sub bancario rating top",
        "confidence": "media",
        "note": "Sub T2 emitido por top banco (raro).",
    },
    ("SUBORDINATED", "T2"): {
        "rw": 1.50,
        "source": "SBP inferido de Basilea III — subordinado bancario AA/A+",
        "confidence": "media",
        "note": "T2 sub emitido por banco AA(pan)/A+(pan).",
    },
    ("SUBORDINATED", "T3"): {
        "rw": 1.50,
        "source": "SBP inferido de Basilea III — subordinado bancario A",
        "confidence": "media",
        "note": "T2 sub emitido por banco A(pan) (Mercantil target).",
    },
    ("SUBORDINATED", "T4"): {
        "rw": 1.50,
        "source": "SBP inferido de Basilea III — subordinado BBB",
        "confidence": "media",
        "note": "T2 sub BBB(pan) — más raro.",
    },
    ("SUBORDINATED", "T5"): {
        "rw": 1.50,
        "source": "SBP inferido de Basilea III — subordinado BB o menor",
        "confidence": "baja",
        "note": "Sub emitido por nombre small — poco líquido.",
    },
    # --- AT1 (equity holdings de otros bancos) ---
    # Acuerdo 3-2016 y BCBS: holdings de equity de otros bancos → 250% o
    # deducción total según normativa. En SBP típicamente deducción de capital.
    ("AT1", "T1"): {
        "rw": 2.50,
        "source": "BCBS finalización 2017 — equity holdings de otros bancos",
        "confidence": "media",
        "note": "Puede estar sujeto a deducción directa del capital según Art. 12 SBP.",
    },
    ("AT1", "T2"): {"rw": 2.50, "source": "BCBS 2017", "confidence": "media", "note": ""},
    ("AT1", "T3"): {"rw": 2.50, "source": "BCBS 2017", "confidence": "media", "note": ""},
    ("AT1", "T4"): {"rw": 2.50, "source": "BCBS 2017", "confidence": "media", "note": ""},
    ("AT1", "T5"): {"rw": 2.50, "source": "BCBS 2017", "confidence": "media", "note": ""},
}


# --------------------------------------------------------------------- #
# Mapeo instrumento Latinex → asset_class regulatoria
# --------------------------------------------------------------------- #
INSTRUMENT_TO_ASSET_CLASS: dict[str, str] = {
    "BONOS DEL TESORO": "SOVEREIGN_PAN",
    "NOTAS DEL TESORO": "SOVEREIGN_PAN",
    "LETRAS DEL TESORO": "SOVEREIGN_PAN",
    "BONOS": "CORPORATE",  # default; se ajusta si sector = Financiero → BANK
    "NOTAS CORPORATIVAS": "CORPORATE",
    "VALORES COMERCIALES NEGOCIABLES": "CORPORATE",
    "BONOS HIPOTECARIOS": "MORTGAGE_BACKED",
    "SUB_T2": "SUBORDINATED",
    "AT1": "AT1",
}


def resolve_asset_class(instrumento: str, sector: Optional[str] = None) -> str:
    """Mapea instrumento (+ sector opcional) a asset_class regulatoria.

    Regla clave: bonos senior corporativos emitidos por bancos (sector
    Financiero) usan la ponderación BANK, no CORPORATE.
    """
    base = INSTRUMENT_TO_ASSET_CLASS.get(instrumento, "CORPORATE")
    if base == "CORPORATE" and sector and sector.strip().upper() == "FINANCIERO":
        return "BANK"
    return base


# --------------------------------------------------------------------- #
# Núcleo de cálculo
# --------------------------------------------------------------------- #
@dataclass(frozen=True)
class CapitalResult:
    """Resultado del cálculo de capital para una posición individual."""

    tier: str
    asset_class: str
    risk_weight: float
    ead: float
    rwa: float
    capital_required: float
    car_min: float
    rw_source: str

    def as_dict(self) -> dict:
        return {
            "tier": self.tier,
            "asset_class": self.asset_class,
            "risk_weight_pct": round(self.risk_weight * 100, 1),
            "ead": round(self.ead, 2),
            "rwa": round(self.rwa, 2),
            "capital_required": round(self.capital_required, 2),
            "car_min_pct": round(self.car_min * 100, 2),
            "rw_source": self.rw_source,
        }


def get_risk_weight(
    tier: str,
    asset_class: str,
    rw_override: Optional[float] = None,
) -> tuple[float, str]:
    """Devuelve (risk_weight, source) para (tier, asset_class).

    Si `rw_override` se pasa, se usa en lugar del default. Retorna source
    "override" en ese caso.
    """
    if rw_override is not None:
        if rw_override < 0 or rw_override > 12.5:  # 12.5 = deducción total (1/8%)
            raise ValueError(
                f"rw_override fuera de rango razonable [0, 12.5], recibido {rw_override}"
            )
        return rw_override, "override manual (usuario)"

    key = (asset_class, tier)
    if key not in RISK_WEIGHTS_SBP:
        raise ValueError(
            f"No hay risk weight definido para asset_class={asset_class}, tier={tier}. "
            f"Válidos asset_class: {sorted({k[0] for k in RISK_WEIGHTS_SBP})}."
        )
    row = RISK_WEIGHTS_SBP[key]
    return row["rw"], row["source"]


def rwa(ead: float, risk_weight: float) -> float:
    """Risk-Weighted Assets = EAD × RW."""
    if ead < 0:
        raise ValueError(f"EAD debe ser no negativo, recibido {ead}")
    if risk_weight < 0:
        raise ValueError(f"risk_weight debe ser no negativo, recibido {risk_weight}")
    return ead * risk_weight


def capital_requirement(rwa_value: float, car_min: float = CAR_MIN_TOTAL) -> float:
    """Requerimiento de capital = RWA × CAR_min. Default CAR_min = 8% (SBP)."""
    if rwa_value < 0:
        raise ValueError(f"RWA debe ser no negativo, recibido {rwa_value}")
    if car_min <= 0 or car_min > 1:
        raise ValueError(f"car_min debe estar en (0, 1], recibido {car_min}")
    return rwa_value * car_min


def capital_for_position(
    tier: str,
    ead: float,
    instrumento: str = "BONOS",
    sector: Optional[str] = None,
    car_min: float = CAR_MIN_TOTAL,
    rw_override: Optional[float] = None,
    asset_class_override: Optional[str] = None,
) -> CapitalResult:
    """Calcula RWA y capital requerido para una posición individual.

    Args:
        tier: T1..T5
        ead: exposición al default
        instrumento: nombre del instrumento en catálogo Latinex
        sector: opcional; si es 'Financiero' cambia CORPORATE→BANK
        car_min: coeficiente mínimo (default 8% SBP)
        rw_override: fuerza un RW manual (para calibración interna del banco)
        asset_class_override: fuerza asset_class específica
    """
    asset_class = asset_class_override or resolve_asset_class(instrumento, sector)
    rw, source = get_risk_weight(tier, asset_class, rw_override=rw_override)
    rwa_val = rwa(ead, rw)
    cap = capital_requirement(rwa_val, car_min=car_min)
    return CapitalResult(
        tier=tier,
        asset_class=asset_class,
        risk_weight=rw,
        ead=ead,
        rwa=rwa_val,
        capital_required=cap,
        car_min=car_min,
        rw_source=source,
    )


def portfolio_rwa(
    portfolio_df: pd.DataFrame,
    tier_col: str = "rating_tier",
    ead_col: str = "ead",
    instrumento_col: str = "instrumento",
    sector_col: Optional[str] = "sector",
    car_min: float = CAR_MIN_TOTAL,
) -> pd.DataFrame:
    """Aplica cálculo de RWA a un portafolio completo."""
    if portfolio_df.empty:
        return portfolio_df.copy()

    for col in (tier_col, ead_col, instrumento_col):
        if col not in portfolio_df.columns:
            raise KeyError(f"columna '{col}' no está en el DataFrame")

    rows = []
    for _, r in portfolio_df.iterrows():
        try:
            sector_val = r[sector_col] if (sector_col and sector_col in r) else None
            res = capital_for_position(
                tier=r[tier_col],
                ead=float(r[ead_col]),
                instrumento=r[instrumento_col],
                sector=sector_val,
                car_min=car_min,
            )
            rows.append(res.as_dict())
        except (ValueError, KeyError):
            rows.append({
                "tier": r[tier_col],
                "asset_class": None,
                "risk_weight_pct": None,
                "ead": r[ead_col],
                "rwa": None,
                "capital_required": None,
                "car_min_pct": car_min * 100,
                "rw_source": "error",
            })

    # Concatenar sin duplicar columnas
    original_cols = [c for c in portfolio_df.columns if c not in {"tier", "ead"}]
    result = pd.concat(
        [portfolio_df[original_cols].reset_index(drop=True), pd.DataFrame(rows)],
        axis=1,
    )
    return result


def credit_capacity_by_rw(
    delta_capital: float,
    car_target: float = CAR_MIN_TOTAL,
    risk_weight: float = 0.50,
) -> float:
    """Cuánta exposición adicional se puede originar con un delta de capital dado.

    Fórmula: nueva_EAD = delta_capital / (car_target × risk_weight)

    Ejemplo: con $30MM adicionales de capital, CAR_target=13% y RW=50%
    (corporativo IG), se pueden originar 30 / (0.13 × 0.5) = $461.5MM.
    """
    if delta_capital < 0:
        raise ValueError(f"delta_capital debe ser no negativo, recibido {delta_capital}")
    if car_target <= 0 or car_target > 1:
        raise ValueError(f"car_target debe estar en (0, 1], recibido {car_target}")
    if risk_weight <= 0:
        raise ValueError(f"risk_weight debe ser positivo, recibido {risk_weight}")
    return delta_capital / (car_target * risk_weight)


def capital_impact(
    monto_emision: float,
    capital_actual: float,
    apr_actual: float,
    car_target_post: Optional[float] = None,
    rw_originacion: float = 0.50,
) -> dict:
    """Generaliza mercantil.capital_sizing_analysis para inputs arbitrarios.

    Args:
        monto_emision: monto de la nueva emisión (aumenta capital)
        capital_actual: capital regulatorio actual del banco
        apr_actual: APR actual
        car_target_post: si se pasa, calcula cuánta APR puede crecer para llegar
                          al CAR objetivo (default: mantener CAR actual)
        rw_originacion: RW promedio esperado de la originación adicional
    """
    if apr_actual <= 0:
        raise ValueError(f"apr_actual debe ser positivo, recibido {apr_actual}")

    car_pre = capital_actual / apr_actual
    capital_post = capital_actual + monto_emision
    car_post_sin_crecer = capital_post / apr_actual

    car_target = car_target_post if car_target_post is not None else car_pre
    if car_target <= 0 or car_target > 1:
        raise ValueError(f"car_target debe estar en (0, 1], recibido {car_target}")

    apr_max_at_target = capital_post / car_target
    apr_headroom = apr_max_at_target - apr_actual
    credito_capacity = apr_headroom / rw_originacion if rw_originacion > 0 else 0.0

    return {
        "monto_emision": monto_emision,
        "capital_pre": capital_actual,
        "capital_post": capital_post,
        "apr_pre": apr_actual,
        "car_pre_pct": round(car_pre * 100, 3),
        "car_post_sin_crecer_pct": round(car_post_sin_crecer * 100, 3),
        "delta_car_bp": round((car_post_sin_crecer - car_pre) * 10000, 1),
        "car_target_pct": round(car_target * 100, 3),
        "apr_headroom": round(apr_headroom, 2),
        "rw_originacion_pct": round(rw_originacion * 100, 1),
        "credito_capacity_adicional": round(credito_capacity, 2),
    }
