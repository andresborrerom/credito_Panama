"""Motor de provisiones potenciales por calificación crediticia.

Calcula pérdida esperada (Expected Loss, EL) siguiendo la fórmula estándar de
Basilea IRB: EL = PD × LGD × EAD.

  PD (Probability of Default): probabilidad de default en horizonte de 1 año.
  LGD (Loss Given Default): fracción de pérdida sobre EAD si ocurre default.
  EAD (Exposure at Default): monto expuesto al momento del default.

TODOS los parámetros de PD y LGD tienen procedencia explícita anotada en su
entrada del diccionario correspondiente ("source" y "confidence"). Ninguna cifra
está inventada sin marca.

Convenciones internas:
- PD y LGD se expresan como FRACCIONES (0.01 = 1%), no como porcentaje.
- EAD y EL se expresan en la misma moneda/unidad (típicamente USD).
- El horizonte por defecto es 1 año; para plazos > 1y se usa multi-year cumulative
  PD asumiendo default como proceso poisson (aproximación estándar).

Los tiers T1..T5 son los definidos en src/analytics/ratings.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------- #
# Tabla PD por tier — cada entrada anotada con procedencia
# --------------------------------------------------------------------- #
# Referencias:
# 1) Basel Committee "International Convergence of Capital Measurement and
#    Capital Standards" (Basilea II/III) — matriz IRB Foundation de PD por
#    grado crediticio. Los valores públicos típicos por rating de Moody's/S&P:
#      AAA  ~0.01-0.03%
#      AA   ~0.03-0.10%
#      A    ~0.10-0.30%
#      BBB  ~0.30-1.00%
#      BB   ~1.00-3.00%
#      B    ~3.00-8.00%
#    Fuente: BIS, "Studies on the Validation of Internal Rating Systems",
#    Working Paper No. 14 (Anexo B, tablas de PD por rating externo).
# 2) Moody's Annual Default Study — data histórica largo plazo (1970-2023).
#    Para escala nacional Panamá (sufijo (pan)) NO existe estudio equivalente
#    público; los valores adoptados son extrapolación conservadora.
# 3) Superintendencia de Bancos de Panamá NO publica una tabla oficial de PD
#    por rating. Ajustar cuando esté disponible.
PD_BY_TIER: dict[str, dict] = {
    "T1": {
        "pd_1y": 0.0003,  # 3 bp — AAA(pan) / soberano
        "source": "Basel IRB Foundation (Moody's histórico 1y default AAA/Aaa)",
        "confidence": "media (rating externo internacional, no específico Panamá)",
        "note": "Aplicable a soberano Panamá + top bancos sistémicos.",
    },
    "T2": {
        "pd_1y": 0.0010,  # 10 bp — AA/A+(pan)
        "source": "Basel IRB Foundation (Moody's histórico 1y default AA)",
        "confidence": "media",
        "note": "Bancos grandes establecidos, utilities reguladas.",
    },
    "T3": {
        "pd_1y": 0.0030,  # 30 bp — A(pan)
        "source": "Basel IRB Foundation (Moody's histórico 1y default A)",
        "confidence": "media",
        "note": "Bancos medianos, corporativos establecidos.",
    },
    "T4": {
        "pd_1y": 0.0100,  # 100 bp — BBB(pan)
        "source": "Basel IRB Foundation (Moody's histórico 1y default BBB)",
        "confidence": "media",
        "note": "Fideicomisos hipotecarios, financieras especializadas.",
    },
    "T5": {
        "pd_1y": 0.0300,  # 300 bp — BB(pan)/NR
        "source": "Basel IRB Foundation (Moody's histórico 1y default BB) — extrapolación conservadora para NR",
        "confidence": "baja (mezcla BB con NR; NR podría tener PD mucho mayor)",
        "note": "Small caps, real estate, VCN pequeños, unrated.",
    },
}


# --------------------------------------------------------------------- #
# Tabla LGD por tipo de instrumento — con procedencia
# --------------------------------------------------------------------- #
# Referencias:
# 4) Basilea III IRB Foundation LGD estándar:
#      Senior unsecured no financial: 45%
#      Senior secured: 25-40% (según colateral)
#      Subordinated: 75%
#    Fuente: BCBS "Basel III: Finalising post-crisis reforms" (2017), sección
#    Standardised Approach LGD tables.
# 5) SBP Panamá — no publica LGD específica. Se usa proxy Basilea III.
LGD_BY_INSTRUMENT: dict[str, dict] = {
    "BONOS": {
        "lgd": 0.45,
        "source": "Basel III Foundation IRB — senior unsecured 45%",
        "confidence": "alta",
        "note": "Bono corporativo estándar, senior no garantizado.",
    },
    "NOTAS CORPORATIVAS": {
        "lgd": 0.45,
        "source": "Basel III Foundation IRB — senior unsecured 45%",
        "confidence": "alta",
        "note": "Equivalente funcional a bono senior.",
    },
    "VALORES COMERCIALES NEGOCIABLES": {
        "lgd": 0.40,
        "source": "Basel III Foundation IRB — senior corto plazo (ligeramente mejor recovery)",
        "confidence": "media (VCN suele resolverse rápido en default)",
        "note": "Papel comercial, plazo corto, mejor prioridad efectiva.",
    },
    "BONOS HIPOTECARIOS": {
        "lgd": 0.25,
        "source": "Basel III Foundation IRB — senior secured hipotecas 25%",
        "confidence": "alta",
        "note": "Respaldo colateral inmobiliario reduce LGD significativamente.",
    },
    "BONOS DEL TESORO": {
        "lgd": 0.10,
        "source": "Convención: soberano panameño (recuperación asumida alta post-restructuring)",
        "confidence": "media (Panamá nunca ha defaulteado; asumido paralelo a soberanos LatAm IG)",
        "note": "Casi cero riesgo en Panamá dolarizado.",
    },
    "NOTAS DEL TESORO": {
        "lgd": 0.10,
        "source": "Convención: soberano panameño",
        "confidence": "media",
        "note": "Igual que Bonos del Tesoro.",
    },
    "LETRAS DEL TESORO": {
        "lgd": 0.05,
        "source": "Convención: soberano corto plazo",
        "confidence": "alta (plazo <1y minimiza recovery risk)",
        "note": "Muy corto plazo, riesgo mínimo.",
    },
    # Instrumentos subordinados (T2 sub, AT1) — LGD mayor por subordinación
    "SUB_T2": {
        "lgd": 0.75,
        "source": "Basel III — deuda subordinada Tier 2 estándar",
        "confidence": "alta",
        "note": "Subordinado a depositantes y senior debt; usar para T2 sub 10y bullet.",
    },
    "AT1": {
        "lgd": 1.00,
        "source": "Basel III — AT1 write-down/conversión a equity",
        "confidence": "alta",
        "note": "Loss-absorption casi total en resolución bancaria.",
    },
    "DEFAULT": {
        "lgd": 0.45,
        "source": "Basel III Foundation IRB — genérico senior unsecured",
        "confidence": "media",
        "note": "Usar cuando instrumento no matchea ninguna de las categorías anteriores.",
    },
}


@dataclass(frozen=True)
class ProvisionResult:
    """Resultado del cálculo de pérdida esperada para una posición individual."""

    tier: str
    pd_1y: float
    lgd: float
    ead: float
    horizon_years: float
    pd_cumulative: float
    el_1y: float
    el_horizon: float
    provision_pct_ead: float

    def as_dict(self) -> dict:
        return {
            "tier": self.tier,
            "pd_1y_pct": round(self.pd_1y * 100, 4),
            "lgd_pct": round(self.lgd * 100, 2),
            "ead": round(self.ead, 2),
            "horizon_years": self.horizon_years,
            "pd_cumulative_pct": round(self.pd_cumulative * 100, 4),
            "el_1y": round(self.el_1y, 2),
            "el_horizon": round(self.el_horizon, 2),
            "provision_pct_ead": round(self.provision_pct_ead * 100, 4),
        }


def cumulative_pd(pd_1y: float, horizon_years: float) -> float:
    """PD acumulada asumiendo default como proceso independiente año a año.

    P(default en horizon) = 1 − (1 − PD_1y)^horizon

    Para horizon fraccional (ej. 0.5y), se usa aproximación por ley de escalado
    exponencial: PD_h ≈ 1 − (1 − PD_1y)^h.
    """
    if pd_1y < 0 or pd_1y > 1:
        raise ValueError(f"pd_1y debe estar en [0, 1], recibido {pd_1y}")
    if horizon_years <= 0:
        raise ValueError(f"horizon_years debe ser positivo, recibido {horizon_years}")
    return 1.0 - (1.0 - pd_1y) ** horizon_years


def expected_loss(
    pd_1y: float,
    lgd: float,
    ead: float,
    horizon_years: float = 1.0,
) -> float:
    """Pérdida esperada (Expected Loss).

    Fórmula: EL = PD_cumulative(horizon) × LGD × EAD

    Args:
        pd_1y: probabilidad de default anual, fracción [0, 1]
        lgd: loss given default, fracción [0, 1]
        ead: exposición al default, en unidades monetarias
        horizon_years: horizonte del cálculo en años (default 1)
    """
    if lgd < 0 or lgd > 1:
        raise ValueError(f"lgd debe estar en [0, 1], recibido {lgd}")
    if ead < 0:
        raise ValueError(f"ead debe ser no negativo, recibido {ead}")
    pd_h = cumulative_pd(pd_1y, horizon_years)
    return pd_h * lgd * ead


def provision_for_position(
    tier: str,
    ead: float,
    instrumento: str = "BONOS",
    horizon_years: float = 1.0,
    pd_override: Optional[float] = None,
    lgd_override: Optional[float] = None,
) -> ProvisionResult:
    """Calcula la provisión esperada de una posición dado tier, EAD, instrumento
    y horizonte.

    Los overrides permiten al usuario ingresar PD/LGD custom (para sensibilidad
    o para posiciones con calificación específica no cubierta por el proxy).
    """
    if tier not in PD_BY_TIER:
        raise ValueError(f"tier '{tier}' no reconocido. Válidos: {list(PD_BY_TIER)}")

    pd_1y = pd_override if pd_override is not None else PD_BY_TIER[tier]["pd_1y"]
    lgd_row = LGD_BY_INSTRUMENT.get(instrumento, LGD_BY_INSTRUMENT["DEFAULT"])
    lgd = lgd_override if lgd_override is not None else lgd_row["lgd"]

    pd_h = cumulative_pd(pd_1y, horizon_years)
    el_1y = expected_loss(pd_1y, lgd, ead, horizon_years=1.0)
    el_h = expected_loss(pd_1y, lgd, ead, horizon_years=horizon_years)

    return ProvisionResult(
        tier=tier,
        pd_1y=pd_1y,
        lgd=lgd,
        ead=ead,
        horizon_years=horizon_years,
        pd_cumulative=pd_h,
        el_1y=el_1y,
        el_horizon=el_h,
        provision_pct_ead=(el_h / ead) if ead > 0 else 0.0,
    )


def provision_by_rating(
    portfolio_df: pd.DataFrame,
    tier_col: str = "rating_tier",
    ead_col: str = "ead",
    instrumento_col: str = "instrumento",
    horizon_col: Optional[str] = None,
    horizon_default: float = 1.0,
) -> pd.DataFrame:
    """Aplica el cálculo de provisión a un portafolio completo.

    Args:
        portfolio_df: DataFrame con al menos columnas tier, EAD, instrumento
        horizon_col: si se pasa, se usa por-fila; si None, se usa horizon_default

    Returns:
        DataFrame con columnas agregadas: pd_1y, lgd, pd_cumulative, el_1y,
        el_horizon, provision_pct_ead.
    """
    if portfolio_df.empty:
        return portfolio_df.copy()

    for col in (tier_col, ead_col, instrumento_col):
        if col not in portfolio_df.columns:
            raise KeyError(f"columna '{col}' no está en el DataFrame")

    rows = []
    for _, r in portfolio_df.iterrows():
        h = float(r[horizon_col]) if (horizon_col and horizon_col in r) else horizon_default
        try:
            res = provision_for_position(
                tier=r[tier_col],
                ead=float(r[ead_col]),
                instrumento=r[instrumento_col],
                horizon_years=h,
            )
            rows.append(res.as_dict())
        except (ValueError, KeyError):
            # Tier no reconocido u otra data invalida — pasar fila con NaN
            rows.append({
                "tier": r[tier_col],
                "pd_1y_pct": np.nan,
                "lgd_pct": np.nan,
                "ead": r[ead_col],
                "horizon_years": h,
                "pd_cumulative_pct": np.nan,
                "el_1y": np.nan,
                "el_horizon": np.nan,
                "provision_pct_ead": np.nan,
            })

    result = pd.concat([portfolio_df.reset_index(drop=True),
                          pd.DataFrame(rows).drop(columns=["tier", "ead", "horizon_years"])],
                        axis=1)
    return result


def sensitivity_table(
    tier: str,
    ead: float,
    instrumento: str = "BONOS",
    horizon_years: float = 1.0,
    pd_grid: Optional[list[float]] = None,
    lgd_grid: Optional[list[float]] = None,
) -> pd.DataFrame:
    """Matriz de sensibilidad de EL sobre grids de PD y LGD.

    Útil para la vista de sensibilidad de la calculadora.
    """
    base_pd = PD_BY_TIER[tier]["pd_1y"]
    base_lgd = LGD_BY_INSTRUMENT.get(instrumento, LGD_BY_INSTRUMENT["DEFAULT"])["lgd"]

    if pd_grid is None:
        pd_grid = [base_pd * m for m in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)]
    if lgd_grid is None:
        lgd_grid = [0.20, 0.30, 0.45, 0.60, 0.75, 0.90]

    rows = []
    for pd_v in pd_grid:
        for lgd_v in lgd_grid:
            el = expected_loss(pd_v, lgd_v, ead, horizon_years=horizon_years)
            rows.append({
                "pd_1y": pd_v,
                "lgd": lgd_v,
                "el": el,
                "el_pct_ead": el / ead if ead > 0 else 0.0,
            })
    return pd.DataFrame(rows)
