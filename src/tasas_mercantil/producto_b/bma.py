"""Bayesian Model Averaging (BMA) iterativo para Producto B.

Iter 1: equal weights — valida arquitectura.
Iter 2: + shrinkage Bayesiano (α calibrado por CV anidada).
Iter 3: + estabilidad temporal (ρ smoothing mes-a-mes).
Iter 4: + bootstrap pesos para pruning.
Iter 5: agregar modelos validados (sentiment moduladores).
Iter 6: validación final (DM-test, calibración).

Cada iteración tiene gate de aprobación. Ver 11_MODELO_ROBUSTEZ.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


# ============================================================================
# Tipos de datos
# ============================================================================
@dataclass
class ModelForecast:
    """Forecast de UN modelo para UN (as_of, horizon)."""
    model_name: str
    as_of: date
    horizon_months: int
    samples: np.ndarray              # MC samples del forecast distribution
    center: float                    # punto central (mean del HDI)


@dataclass
class BMAWeights:
    """Pesos calibrados de los M modelos para un horizonte."""
    horizon_months: int
    weights: dict[str, float]        # {model_name: weight}
    iteration: int                   # qué iteración del calibrado generó esto
    method: str                      # "equal" | "shrinkage" | "stable" | etc.


# ============================================================================
# Iter 1: BMA equal weights
# ============================================================================
def bma_equal_weights(model_names: list[str], horizon_months: int) -> BMAWeights:
    """Pesos triviales: 1/M para todos."""
    w = 1.0 / len(model_names)
    return BMAWeights(
        horizon_months=horizon_months,
        weights={m: w for m in model_names},
        iteration=1,
        method="equal",
    )


# ============================================================================
# Combinar predicciones según pesos
# ============================================================================
def combine_forecasts(
    forecasts: dict[str, ModelForecast],
    weights: BMAWeights,
) -> np.ndarray:
    """Mezcla MC: para cada sim_i del output, samplear un modelo según weights
    y tomar un sample de ese modelo.

    Output: array de samples combinados.
    """
    rng = np.random.default_rng(42)
    n_target = max(len(f.samples) for f in forecasts.values())
    combined = np.zeros(n_target)
    model_names = list(weights.weights.keys())
    w_array = np.array([weights.weights[m] for m in model_names])
    w_array = w_array / w_array.sum()
    # Para cada sample del output, elegir modelo y muestrear de él
    model_choices = rng.choice(model_names, size=n_target, p=w_array)
    for i, m in enumerate(model_choices):
        if m in forecasts:
            samples = forecasts[m].samples
            combined[i] = rng.choice(samples)
    return combined


def combine_centers(
    forecasts: dict[str, ModelForecast],
    weights: BMAWeights,
) -> float:
    """Center del ensemble = weighted average de centers."""
    total_w = 0.0
    weighted_sum = 0.0
    for m, w in weights.weights.items():
        if m in forecasts:
            weighted_sum += w * forecasts[m].center
            total_w += w
    return weighted_sum / total_w if total_w > 0 else float("nan")


# ============================================================================
# Iter 2: shrinkage Bayesiano hacia equal weights
# ============================================================================
def bma_shrinkage(
    data_weights: dict[str, float],
    alpha: float = 0.5,
) -> dict[str, float]:
    """Mezcla equal (1/M) con weights data-driven, ponderada por α.

    w_final = (1 - α) · 1/M + α · w_data
    α=0 → equal, α=1 → puro data-driven.
    """
    M = len(data_weights)
    w_equal = 1.0 / M
    w_final = {}
    for m, w_data in data_weights.items():
        w_final[m] = (1 - alpha) * w_equal + alpha * w_data
    # Renormalizar
    total = sum(w_final.values())
    return {m: w / total for m, w in w_final.items()}


# ============================================================================
# Iter 2-3: pesos data-driven basados en log-score histórico
# ============================================================================
def compute_log_scores_per_model(
    forecasts_train: list[dict[str, ModelForecast]],
    realized_train: np.ndarray,
) -> dict[str, float]:
    """Log score por modelo. Mayor = mejor.

    Para predicciones MC: estimar densidad y evaluar log(densidad(realized)).
    Aproximación simple: usar fracción de samples dentro de ε del realizado.
    """
    log_scores = {m: 0.0 for m in forecasts_train[0].keys()}
    counts = {m: 0 for m in log_scores}
    epsilon = 0.005  # 0.5% en retorno
    for fdict, real in zip(forecasts_train, realized_train):
        for m, f in fdict.items():
            within = np.mean(np.abs(f.samples - real) < epsilon)
            # Evitar log(0) con piso
            ls = np.log(max(within, 1e-6))
            log_scores[m] += ls
            counts[m] += 1
    # Normalizar
    avg = {m: log_scores[m] / counts[m] for m in log_scores if counts[m] > 0}
    return avg


def bma_log_score_weights(log_scores: dict[str, float]) -> dict[str, float]:
    """Convertir log scores a pesos: w_i ∝ exp(LS_i)."""
    # Stabilizar exponente
    max_ls = max(log_scores.values())
    exps = {m: np.exp(ls - max_ls) for m, ls in log_scores.items()}
    total = sum(exps.values())
    return {m: e / total for m, e in exps.items()}


# ============================================================================
# Iter 3: estabilidad temporal
# ============================================================================
def apply_temporal_smoothing(
    weights_t: dict[str, float],
    weights_t_minus_1: dict[str, float] | None,
    rho: float = 0.8,
) -> dict[str, float]:
    """w(t) = ρ · w(t-1) + (1-ρ) · w_data(t)."""
    if weights_t_minus_1 is None:
        return weights_t.copy()
    smoothed = {}
    for m, w in weights_t.items():
        prev = weights_t_minus_1.get(m, 1.0 / len(weights_t))
        smoothed[m] = rho * prev + (1 - rho) * w
    # Renormalizar
    total = sum(smoothed.values())
    return {m: w / total for m, w in smoothed.items()}


# ============================================================================
# Walk-forward BMA — Iter 1 (equal weights)
# ============================================================================
def walk_forward_bma_equal(
    forecasts_per_date: list[dict[str, ModelForecast]],
    realized: list[float],
) -> pd.DataFrame:
    """Walk-forward con equal weights (iter 1, baseline)."""
    if not forecasts_per_date:
        return pd.DataFrame()
    model_names = list(forecasts_per_date[0].keys())
    h = forecasts_per_date[0][model_names[0]].horizon_months
    weights = bma_equal_weights(model_names, h)

    rows = []
    for fdict, real in zip(forecasts_per_date, realized):
        as_of = list(fdict.values())[0].as_of
        # Predicción del ensemble
        ensemble_samples = combine_forecasts(fdict, weights)
        ensemble_center = combine_centers(fdict, weights)
        # HDI 50% del ensemble
        sorted_e = np.sort(ensemble_samples)
        n = len(sorted_e); window = int(np.ceil(n * 0.50))
        widths = sorted_e[window:] - sorted_e[:n - window]
        j = int(np.argmin(widths))
        hdi_low, hdi_high = float(sorted_e[j]), float(sorted_e[j + window])

        rows.append({
            "as_of": as_of,
            "horizon": h,
            "real": real,
            "ensemble_center": ensemble_center,
            "ensemble_hdi_low": hdi_low,
            "ensemble_hdi_high": hdi_high,
            "in_hdi": hdi_low <= real <= hdi_high,
            "ensemble_iter": 1,
        })
    return pd.DataFrame(rows)
