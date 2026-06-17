"""Block bootstrap del backtest del modelo agregado vs naive.

Reporta intervalos del skill score con stationary block bootstrap (block_size
mensual). Justificación del block: las predicciones consecutivas comparten
fuente macro y régimen Fed, no son iid.

Convención:
    skill_score = 1 - MAE_modelo / MAE_naive
    > 0 → mejor que naive
    < 0 → peor que naive
    > 0.05 → pasa fail-loud (regla 11_MODELO_ROBUSTEZ.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class BootstrapResult:
    horizon_months: int
    n_obs: int
    n_replicas: int
    block_size_months: int
    median_skill: float
    p10_skill: float
    p90_skill: float
    p05_skill: float
    p95_skill: float
    mean_skill: float
    std_skill: float
    prob_positive: float
    prob_pass_fail_loud: float  # skill > 0.05


def block_bootstrap_skill(
    df_model: pd.DataFrame,
    df_naive: pd.DataFrame,
    horizon: int,
    n_replicas: int = 1000,
    block_size_months: int = 6,
    seed: int = 42,
) -> BootstrapResult:
    """Bootstrap del skill score modelo vs naive a un horizonte.

    Args:
        df_model: DataFrame con columnas [as_of, horizon_months, abs_err]
        df_naive: DataFrame con columnas [as_of, horizon_months, abs_error_bps]
        horizon: meses
        n_replicas: número de réplicas bootstrap
        block_size_months: tamaño del bloque (preserva correlación temporal)
        seed: semilla

    Returns:
        BootstrapResult con percentiles del skill score.
    """
    rng = np.random.default_rng(seed)

    err_m = df_model[df_model["horizon_months"] == horizon].sort_values("as_of")["abs_err"].values
    err_n_col = "abs_error_bps" if "abs_error_bps" in df_naive.columns else "abs_err"
    err_n = df_naive[df_naive["horizon_months"] == horizon].sort_values("as_of")[err_n_col].values

    n_obs = min(len(err_m), len(err_n))
    err_m = err_m[:n_obs]
    err_n = err_n[:n_obs]

    if n_obs < block_size_months * 2:
        raise ValueError(f"n_obs={n_obs} muy pequeño para block_size={block_size_months}")

    skills = []
    n_blocks_needed = int(np.ceil(n_obs / block_size_months))
    max_start = n_obs - block_size_months

    for _ in range(n_replicas):
        # Block bootstrap: seleccionar arranques de bloque con reemplazo
        block_starts = rng.integers(0, max_start + 1, size=n_blocks_needed)
        indices = np.concatenate([
            np.arange(s, s + block_size_months) for s in block_starts
        ])[:n_obs]
        mae_m = err_m[indices].mean()
        mae_n = err_n[indices].mean()
        if mae_n > 0:
            skills.append(1 - mae_m / mae_n)

    skills = np.asarray(skills)
    return BootstrapResult(
        horizon_months=horizon,
        n_obs=n_obs,
        n_replicas=n_replicas,
        block_size_months=block_size_months,
        median_skill=float(np.median(skills)),
        p10_skill=float(np.percentile(skills, 10)),
        p90_skill=float(np.percentile(skills, 90)),
        p05_skill=float(np.percentile(skills, 5)),
        p95_skill=float(np.percentile(skills, 95)),
        mean_skill=float(np.mean(skills)),
        std_skill=float(np.std(skills)),
        prob_positive=float(np.mean(skills > 0)),
        prob_pass_fail_loud=float(np.mean(skills > 0.05)),
    )


def report_table(results: list[BootstrapResult]) -> pd.DataFrame:
    """Reporta resultados en tabla legible."""
    rows = []
    for r in results:
        rows.append({
            "horizonte": f"{r.horizon_months}M",
            "n_obs": r.n_obs,
            "skill_median": f"{r.median_skill:+.1%}",
            "skill_p10": f"{r.p10_skill:+.1%}",
            "skill_p90": f"{r.p90_skill:+.1%}",
            "P(skill>0)": f"{r.prob_positive:.0%}",
            "P(pasa fail-loud)": f"{r.prob_pass_fail_loud:.0%}",
        })
    return pd.DataFrame(rows)
