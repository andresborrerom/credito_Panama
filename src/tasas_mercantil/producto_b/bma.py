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
# Iter 2: calibración de α por walk-forward causal
# ============================================================================
def _log_scores_up_to(
    forecasts_per_date: list[dict[str, ModelForecast]],
    realized: list[float],
    upto_idx: int,
    epsilon: float = 0.005,
) -> dict[str, float]:
    """Log scores acumulados usando SOLO fechas con idx < upto_idx (no look-ahead).

    Si upto_idx == 0, devuelve dict vacío → caller usa equal.
    """
    if upto_idx <= 0:
        return {}
    train = forecasts_per_date[:upto_idx]
    train_real = realized[:upto_idx]
    log_scores = {m: 0.0 for m in train[0].keys()}
    counts = {m: 0 for m in log_scores}
    for fdict, real in zip(train, train_real):
        for m, f in fdict.items():
            within = np.mean(np.abs(f.samples - real) < epsilon)
            ls = np.log(max(within, 1e-6))
            log_scores[m] += ls
            counts[m] += 1
    return {m: log_scores[m] / counts[m] for m in log_scores if counts[m] > 0}


def _crps_scores_up_to(
    forecasts_per_date: list[dict[str, ModelForecast]],
    realized: list[float],
    upto_idx: int,
) -> dict[str, float]:
    """CRPS histórico por modelo (causal): score = -CRPS (mayor = mejor)."""
    from .evaluation import crps_sample
    if upto_idx <= 0:
        return {}
    train = forecasts_per_date[:upto_idx]
    train_real = realized[:upto_idx]
    crps_acc = {m: 0.0 for m in train[0].keys()}
    counts = {m: 0 for m in crps_acc}
    for fdict, real in zip(train, train_real):
        for m, f in fdict.items():
            crps_acc[m] += crps_sample(f.samples, real)
            counts[m] += 1
    # score = -CRPS_promedio (queremos maximizar score)
    return {m: -crps_acc[m] / counts[m] for m in crps_acc if counts[m] > 0}


def bma_crps_score_weights(crps_scores: dict[str, float],
                           temperature: float = 50.0) -> dict[str, float]:
    """Convertir scores a pesos: w_i ∝ exp(score_i · temperature).

    temperature controla la sharpness. Mayor T → pesos más concentrados.
    Para CRPS típico ~ 0.025, T=50 → diferencias de 5 bps en CRPS dan factor ~e^0.25 ≈ 1.28.
    """
    if not crps_scores:
        return {}
    max_s = max(crps_scores.values())
    exps = {m: np.exp((s - max_s) * temperature) for m, s in crps_scores.items()}
    total = sum(exps.values())
    return {m: e / total for m, e in exps.items()}


def calibrate_alpha_walkforward(
    forecasts_per_date: list[dict[str, ModelForecast]],
    realized: list[float],
    alpha_grid: tuple = (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0),
    warmup: int = 6,
    score_method: str = "crps",
    temperature: float = 50.0,
) -> tuple[float, pd.DataFrame]:
    """Walk-forward causal: para cada t > warmup, score histórico con datos t' < t,
    se aplica shrinkage(α), mide CRPS de la mezcla en t. Promedia → α*.

    score_method:
      "crps" — usa -CRPS histórico como score (recomendado).
      "epsilon" — fracción de samples cerca del realizado (legacy, sensible a horizonte).
    """
    from .evaluation import crps_sample
    model_names = list(forecasts_per_date[0].keys())
    rows = []
    for alpha in alpha_grid:
        crps_list = []
        for t in range(warmup, len(forecasts_per_date)):
            if score_method == "crps":
                scores = _crps_scores_up_to(forecasts_per_date, realized, t)
                w_data = (bma_crps_score_weights(scores, temperature=temperature)
                          if scores else {m: 1.0 / len(model_names) for m in model_names})
            else:
                ls = _log_scores_up_to(forecasts_per_date, realized, t)
                w_data = (bma_log_score_weights(ls) if ls
                          else {m: 1.0 / len(model_names) for m in model_names})
            w_shrunk = bma_shrinkage(w_data, alpha=alpha)
            bw = BMAWeights(
                horizon_months=forecasts_per_date[t][model_names[0]].horizon_months,
                weights=w_shrunk, iteration=2, method="shrinkage",
            )
            ens_samples = combine_forecasts(forecasts_per_date[t], bw)
            crps_list.append(crps_sample(ens_samples, realized[t]))
        rows.append({"alpha": alpha, "CRPS_mean": float(np.mean(crps_list)),
                     "n_test": len(crps_list)})
    df = pd.DataFrame(rows).sort_values("CRPS_mean").reset_index(drop=True)
    return float(df.iloc[0]["alpha"]), df


# ============================================================================
# Walk-forward BMA Iter 2 — shrinkage Bayesiano con α óptimo
# ============================================================================
def walk_forward_bma_shrinkage(
    forecasts_per_date: list[dict[str, ModelForecast]],
    realized: list[float],
    alpha: float,
    warmup: int = 6,
    score_method: str = "crps",
    temperature: float = 50.0,
) -> pd.DataFrame:
    """Walk-forward con shrinkage. Antes de `warmup`: equal weights."""
    if not forecasts_per_date:
        return pd.DataFrame()
    model_names = list(forecasts_per_date[0].keys())
    h = forecasts_per_date[0][model_names[0]].horizon_months
    rows = []
    for t, (fdict, real) in enumerate(zip(forecasts_per_date, realized)):
        if t < warmup:
            bw = bma_equal_weights(model_names, h)
            method = "equal_warmup"
        else:
            if score_method == "crps":
                scores = _crps_scores_up_to(forecasts_per_date, realized, t)
                w_data = (bma_crps_score_weights(scores, temperature=temperature)
                          if scores else {m: 1.0 / len(model_names) for m in model_names})
            else:
                ls = _log_scores_up_to(forecasts_per_date, realized, t)
                w_data = (bma_log_score_weights(ls) if ls
                          else {m: 1.0 / len(model_names) for m in model_names})
            w_shrunk = bma_shrinkage(w_data, alpha=alpha)
            bw = BMAWeights(horizon_months=h, weights=w_shrunk,
                            iteration=2, method=f"shrinkage_a{alpha:.2f}_{score_method}")
            method = bw.method
        ens_samples = combine_forecasts(fdict, bw)
        ens_center = combine_centers(fdict, bw)
        s = np.sort(ens_samples)
        n = len(s); window = int(np.ceil(n * 0.50))
        widths = s[window:] - s[:n - window]
        j = int(np.argmin(widths))
        hdi_low, hdi_high = float(s[j]), float(s[j + window])
        as_of = list(fdict.values())[0].as_of
        rows.append({
            "as_of": as_of, "horizon": h, "real": real,
            "ensemble_center": ens_center,
            "ensemble_hdi_low": hdi_low, "ensemble_hdi_high": hdi_high,
            "in_hdi": hdi_low <= real <= hdi_high,
            "method": method,
            **{f"w_{m}": bw.weights[m] for m in model_names},
        })
    return pd.DataFrame(rows)


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
