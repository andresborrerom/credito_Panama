"""Métricas para evaluación de modelos predictivos de retornos / tasas.

Métricas core (las 5 que definimos con AB):
1. CRPS — Continuous Ranked Probability Score (gold standard probabilístico).
2. Calibración HDI 50% — % de realizados dentro del rango Esperado.
3. Sharpness — ancho medio del HDI cuando calibrado.
4. Skill Score — vs benchmark (naive o mercado).
5. Sesgo direccional — mean(realizado − centro_Esperado).

Métricas auxiliares:
6. Calibración cola (Riesgo 2.5%) — % de realizados ≤ risk cutoff.
7. Robustez por régimen — métricas separadas por hike/hold/cut.

Todas funcionan sobre arrays NumPy de predicciones MC + realizados escalares.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


# ============================================================================
# CRPS — Continuous Ranked Probability Score
# ============================================================================
def crps_sample(forecast_samples: np.ndarray, realized: float) -> float:
    """CRPS para forecast distribution dada como muestras (Monte Carlo) vs realizado escalar.

    CRPS = E|X - y| - 0.5 * E|X - X'|
    Para muestras: (1/n) Σ|x_i - y| - (1/(2n²)) Σ_i Σ_j |x_i - x_j|.
    Implementación eficiente vía sort: O(n log n).

    Menor CRPS = mejor. CRPS = 0 → predicción perfecta.
    """
    n = len(forecast_samples)
    if n == 0:
        return float("nan")
    s = np.sort(forecast_samples)
    # Término 1: E|X - y|
    term1 = np.mean(np.abs(s - realized))
    # Término 2: 0.5 E|X - X'| eficiente
    # E|X - X'| = (2/n²) Σ_i (2i - n - 1) * s[i] / n  ... usemos formula directa
    # Para sorted s: Σ_{i<j} (s[j] - s[i]) = Σ_i (n - 1 - 2i) * s[i] * (-1)
    i = np.arange(n)
    term2_sum = np.sum((2 * i - n + 1) * s)
    term2 = term2_sum / (n ** 2)
    return float(term1 - term2)


def crps_batch(forecasts: list[np.ndarray], realized: np.ndarray) -> float:
    """CRPS medio sobre múltiples (forecast, realized) pares."""
    if len(forecasts) != len(realized):
        raise ValueError(f"len mismatch: {len(forecasts)} vs {len(realized)}")
    vals = [crps_sample(f, r) for f, r in zip(forecasts, realized)]
    return float(np.nanmean(vals))


# ============================================================================
# Calibración HDI 50%
# ============================================================================
def coverage_hdi(hdi_lows: np.ndarray, hdi_highs: np.ndarray, realized: np.ndarray) -> float:
    """% de realizados dentro de [hdi_low, hdi_high]. Target = 50%."""
    n = len(realized)
    inside = np.sum((realized >= hdi_lows) & (realized <= hdi_highs))
    return inside / n if n > 0 else float("nan")


def calibration_error_hdi(hdi_lows: np.ndarray, hdi_highs: np.ndarray,
                          realized: np.ndarray, target: float = 0.50) -> float:
    """|cobertura - target|. Menor = mejor calibración."""
    return abs(coverage_hdi(hdi_lows, hdi_highs, realized) - target)


# ============================================================================
# Sharpness
# ============================================================================
def sharpness_mean(hdi_lows: np.ndarray, hdi_highs: np.ndarray) -> float:
    """Ancho promedio del HDI. Menor = mejor (asumiendo calibración OK)."""
    return float(np.mean(hdi_highs - hdi_lows))


# ============================================================================
# Skill Score
# ============================================================================
def mae(predictions: np.ndarray, realized: np.ndarray) -> float:
    return float(np.mean(np.abs(predictions - realized)))


def skill_score(predictions: np.ndarray, realized: np.ndarray,
                benchmark_preds: np.ndarray) -> float:
    """1 - MAE_modelo / MAE_benchmark.

    >0  → modelo mejor que benchmark.
    >0.05 → pasa fail-loud.
    """
    mae_m = mae(predictions, realized)
    mae_b = mae(benchmark_preds, realized)
    if mae_b <= 0:
        return float("nan")
    return 1.0 - mae_m / mae_b


# ============================================================================
# Sesgo direccional
# ============================================================================
def bias(centers: np.ndarray, realized: np.ndarray) -> float:
    """Mean(realized - center). Positivo → modelo subestima sistemáticamente."""
    return float(np.mean(realized - centers))


# ============================================================================
# Calibración cola izquierda (Riesgo 2.5%)
# ============================================================================
def tail_coverage(risk_cutoffs: np.ndarray, realized: np.ndarray,
                  target: float = 0.025) -> dict:
    """% de realizados ≤ risk_cutoff vs target.

    Return dict con coverage_empirical y calibration_error.
    """
    n = len(realized)
    below = np.sum(realized <= risk_cutoffs)
    cov = below / n if n > 0 else float("nan")
    return {
        "tail_coverage": cov,
        "tail_calibration_error": abs(cov - target),
    }


# ============================================================================
# Resumen ejecutivo: todas las métricas en una llamada
# ============================================================================
@dataclass
class ModelEvaluation:
    model_name: str
    horizon_months: int
    n_forecasts: int
    crps_mean: float
    coverage_hdi_50: float
    calibration_error_hdi: float
    sharpness_mean: float
    skill_score_vs_naive: float
    skill_score_vs_market: float | None
    bias_centers: float
    tail_coverage: float
    tail_calibration_error: float
    passes_fail_loud: bool
    passes_calibration: bool

    def to_dict(self) -> dict:
        return {
            "model": self.model_name,
            "horizon": self.horizon_months,
            "n": self.n_forecasts,
            "CRPS": round(self.crps_mean, 4),
            "Cobertura HDI": round(self.coverage_hdi_50 * 100, 1),
            "Calib error HDI": round(self.calibration_error_hdi * 100, 1),
            "Sharpness": round(self.sharpness_mean, 4),
            "Skill vs naive": round(self.skill_score_vs_naive * 100, 1) if self.skill_score_vs_naive else None,
            "Skill vs mercado": round(self.skill_score_vs_market * 100, 1) if self.skill_score_vs_market else None,
            "Sesgo": round(self.bias_centers, 4),
            "Tail cov": round(self.tail_coverage * 100, 1),
            "Tail calib error": round(self.tail_calibration_error * 100, 1),
            "✓ fail-loud": self.passes_fail_loud,
            "✓ calibrado": self.passes_calibration,
        }


def evaluate_model(
    model_name: str,
    horizon_months: int,
    forecasts_samples: list[np.ndarray],
    forecast_centers: np.ndarray,
    hdi_lows: np.ndarray,
    hdi_highs: np.ndarray,
    risk_cutoffs: np.ndarray,
    realized: np.ndarray,
    naive_preds: np.ndarray,
    market_preds: np.ndarray | None = None,
) -> ModelEvaluation:
    """Calcula todas las métricas en una sola pasada."""
    crps = crps_batch(forecasts_samples, realized)
    cov50 = coverage_hdi(hdi_lows, hdi_highs, realized)
    cal_err = calibration_error_hdi(hdi_lows, hdi_highs, realized, target=0.50)
    sharp = sharpness_mean(hdi_lows, hdi_highs)
    skill_naive = skill_score(forecast_centers, realized, naive_preds)
    skill_market = skill_score(forecast_centers, realized, market_preds) if market_preds is not None else None
    bias_v = bias(forecast_centers, realized)
    tail = tail_coverage(risk_cutoffs, realized, target=0.025)

    return ModelEvaluation(
        model_name=model_name,
        horizon_months=horizon_months,
        n_forecasts=len(realized),
        crps_mean=crps,
        coverage_hdi_50=cov50,
        calibration_error_hdi=cal_err,
        sharpness_mean=sharp,
        skill_score_vs_naive=skill_naive,
        skill_score_vs_market=skill_market,
        bias_centers=bias_v,
        tail_coverage=tail["tail_coverage"],
        tail_calibration_error=tail["tail_calibration_error"],
        passes_fail_loud=skill_naive > 0.05,
        passes_calibration=cal_err < 0.10,  # cobertura entre 40-60%
    )


# ============================================================================
# Tabla comparativa
# ============================================================================
def comparative_table(evaluations: list[ModelEvaluation]) -> pd.DataFrame:
    """Tabla con una fila por (modelo, horizonte)."""
    return pd.DataFrame([e.to_dict() for e in evaluations])


# ============================================================================
# Selección de modelo ganador por horizonte
# ============================================================================
def winner_per_horizon(evaluations: list[ModelEvaluation],
                       weights: dict | None = None) -> dict:
    """Selecciona el modelo ganador por horizonte basado en score compuesto.

    weights: pesos para combinar métricas. Default: CRPS 0.4, calibración 0.3, skill 0.3.
    Devuelve {horizon: model_name}.
    """
    weights = weights or {"crps": 0.4, "calibration": 0.3, "skill": 0.3}

    df = comparative_table(evaluations)
    if df.empty:
        return {}

    # Normalizar por horizonte (winsorize + minmax)
    winners = {}
    for h in df["horizon"].unique():
        sub = df[df["horizon"] == h].copy()
        # CRPS: menor es mejor → invertir
        sub["crps_norm"] = 1 - (sub["CRPS"] - sub["CRPS"].min()) / (sub["CRPS"].max() - sub["CRPS"].min() + 1e-9)
        # Calibration error: menor mejor → invertir
        sub["cal_norm"] = 1 - sub["Calib error HDI"] / (sub["Calib error HDI"].max() + 1e-9)
        # Skill: ya >0 es mejor
        sub["skill_norm"] = (sub["Skill vs naive"] - sub["Skill vs naive"].min()) / (sub["Skill vs naive"].max() - sub["Skill vs naive"].min() + 1e-9)
        sub["score_compuesto"] = (
            weights["crps"] * sub["crps_norm"]
            + weights["calibration"] * sub["cal_norm"]
            + weights["skill"] * sub["skill_norm"]
        )
        winner_row = sub.loc[sub["score_compuesto"].idxmax()]
        winners[int(h)] = winner_row["model"]
    return winners
