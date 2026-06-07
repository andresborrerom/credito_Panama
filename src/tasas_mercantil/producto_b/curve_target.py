"""Predicción directa de la curva Treasury — target alternativo a retornos LQD.

Razón: LQD es proxy del segmento medio-largo IG. El driver fundamental es la
curva Treasury (US2Y, US5Y, US10Y, US30Y) y la trayectoria Fed. Predecir
yields directamente es accionable y deja de necesitar gates parchados —
la incertidumbre del propio yield es la métrica natural.

Target: Δyield_h(t) = yield(t+h) - yield(t)   en puntos porcentuales (pp).
Convertible a retorno aproximado de un instrumento de duración D:
  return ≈ -D · Δyield + carry
"""
from __future__ import annotations
from datetime import date

import numpy as np
import pandas as pd

from .bma import ModelForecast


def compute_forward_yield_changes(
    neighbor_dates: list[date],
    yield_series: pd.Series,
    h_months: int,
) -> np.ndarray:
    """Para cada fecha vecina, retorna Δyield_h observado (post-fecha).

    yield_series: pd.Series indexada por DatetimeIndex (end of month).
    """
    out = []
    for d in neighbor_dates:
        d_ts = pd.Timestamp(d)
        before = yield_series.loc[yield_series.index <= d_ts]
        if len(before) == 0: continue
        y_now = before.iloc[-1]
        future_cut = d_ts + pd.DateOffset(months=h_months)
        future = yield_series.loc[(yield_series.index > d_ts) &
                                   (yield_series.index <= future_cut)]
        if len(future) < max(1, h_months - 1): continue
        y_future = future.iloc[-1]
        out.append(float(y_future - y_now))
    return np.array(out)


def realized_yield_change(as_of: date, yield_series: pd.Series, h: int) -> float | None:
    cut = pd.Timestamp(as_of)
    before = yield_series.loc[yield_series.index <= cut]
    if len(before) == 0: return None
    y_now = before.iloc[-1]
    future = yield_series.loc[(yield_series.index > cut) &
                               (yield_series.index <= cut + pd.DateOffset(months=h))]
    if len(future) < max(1, h - 1): return None
    return float(future.iloc[-1] - y_now)


def model_nn_yield(target, macro_hist, yield_series, find_neighbors,
                   K: int, h: int, label: str = "US10Y"):
    """NN sobre macro state, target = Δyield_h."""
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=h + 1)
    fwd = compute_forward_yield_changes(
        nr.neighbors["as_of"].tolist(), yield_series, h
    )
    if len(fwd) < 3: return None
    return ModelForecast(
        model_name=f"NN_K{K}", as_of=target.as_of, horizon_months=h,
        samples=fwd, center=float(np.median(fwd)),
    )


def model_naive_yield(as_of: date, yield_series: pd.Series, h: int,
                      lookback_months: int = 12, n_sims: int = 1000,
                      seed: int | None = None):
    """Bootstrap de Δyield mensuales recientes; suma h muestras."""
    cut = pd.Timestamp(as_of)
    history = yield_series.loc[yield_series.index <= cut].dropna()
    if len(history) < lookback_months + 1: return None
    monthly_dy = history.diff().iloc[-lookback_months:].values
    rng = np.random.default_rng(seed if seed is not None else int(as_of.toordinal()))
    sims = np.array([rng.choice(monthly_dy, size=h, replace=True).sum()
                     for _ in range(n_sims)])
    return ModelForecast(
        model_name="Naive_boot", as_of=as_of, horizon_months=h,
        samples=sims, center=float(np.median(sims)),
    )


def model_ar1_yield(as_of: date, yield_series: pd.Series, h: int,
                    n_sims: int = 1000, seed: int | None = None):
    """AR(1) sobre Δyield mensual, MC h-step."""
    cut = pd.Timestamp(as_of)
    history = yield_series.loc[yield_series.index <= cut].dropna()
    if len(history) < 24: return None
    dy = history.diff().dropna().values
    y_arr = dy[1:]; x_arr = dy[:-1]
    if len(y_arr) < 12: return None
    xm = x_arr.mean(); ym = y_arr.mean()
    cov = np.sum((x_arr - xm) * (y_arr - ym))
    var = np.sum((x_arr - xm) ** 2)
    phi = cov / var if var > 0 else 0.0
    c = ym - phi * xm
    resid = y_arr - (c + phi * x_arr)
    sigma = float(np.std(resid, ddof=2)) if len(resid) > 2 else float(np.std(resid))
    last = float(dy[-1])
    rng = np.random.default_rng(seed if seed is not None else int(as_of.toordinal()))
    sims = np.zeros(n_sims)
    for i in range(n_sims):
        prev = last; total = 0.0
        for _ in range(h):
            r_t = c + phi * prev + rng.normal(0, sigma)
            total += r_t; prev = r_t
        sims[i] = total
    return ModelForecast(
        model_name="AR1", as_of=as_of, horizon_months=h,
        samples=sims, center=float(np.median(sims)),
    )
