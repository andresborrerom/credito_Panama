"""Agregación del modelo Mercantil — Pieza A + Pieza B con pesos congelados.

v0.3.0: agregación A (implied path SR3) + B (Taylor rule). Pesos calibrados
en backtest 12 fechas hike+hold+cut cycle 2022-2025. Pasa fail-loud (>5%
skill vs naive) en todos los horizontes.

Pesos congelados: w_A=0.55, w_B=0.45.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..data.store import MasterStore
from .pieces.implied_path import compute_implied_path, ImpliedPathPrediction
from .pieces.reaction_fn import compute_taylor_rule, TaylorPrediction


MODEL_VERSION = "0.3.0"
W_A_DEFAULT = 0.55  # Pieza A — implied path
W_B_DEFAULT = 0.45  # Pieza B — Taylor rule


@dataclass
class MercantilPrediction:
    """Forecast modelo Mercantil agregado para `as_of`."""
    as_of: date
    fed_funds_now: float
    forecast_1m: float
    forecast_3m: float
    forecast_6m: float
    forecast_12m: float
    forecast_24m: float
    pieza_a: ImpliedPathPrediction
    pieza_b: TaylorPrediction
    w_a: float
    w_b: float
    model_version: str = MODEL_VERSION


def compute_mercantil_aggregate(
    store: MasterStore,
    as_of: date,
    w_a: float = W_A_DEFAULT,
    w_b: float = W_B_DEFAULT,
) -> MercantilPrediction:
    """Forecast Mercantil = w_a * Pieza A + w_b * Pieza B en cada horizonte."""
    pred_a = compute_implied_path(store, as_of)
    pred_b = compute_taylor_rule(store, as_of)

    def _agg(va, vb):
        if va is None and vb is None: return None
        if va is None: return vb
        if vb is None: return va
        return w_a * va + w_b * vb

    return MercantilPrediction(
        as_of=as_of,
        fed_funds_now=pred_a.fed_funds_now,
        forecast_1m=_agg(pred_a.forecast_1m, pred_b.forecast_1m),
        forecast_3m=_agg(pred_a.forecast_3m, pred_b.forecast_3m),
        forecast_6m=_agg(pred_a.forecast_6m, pred_b.forecast_6m),
        forecast_12m=_agg(pred_a.forecast_12m, pred_b.forecast_12m),
        forecast_24m=_agg(pred_a.forecast_24m, pred_b.forecast_24m),
        pieza_a=pred_a,
        pieza_b=pred_b,
        w_a=w_a,
        w_b=w_b,
    )
