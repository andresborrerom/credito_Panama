"""Modelos diversos para BMA — Iter 2 extendida (5 modelos en ensemble).

Modelos:
  AR1: autoregresión de orden 1 sobre log returns. Capta momentum/mean-reversion.
  Drift_vol: random walk con drift histórico (hipótesis mercado eficiente).

Cada modelo emite ModelForecast (samples MC + center).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .bma import ModelForecast


def fit_ar1_history(returns_monthly: pd.Series) -> tuple[float, float, float]:
    """Estima OLS: r_t = c + φ · r_{t-1} + ε_t. Devuelve (c, phi, sigma_eps)."""
    r = returns_monthly.dropna().values
    if len(r) < 12:
        return 0.0, 0.0, float(np.std(r) if len(r) > 0 else 0.0)
    y = r[1:]
    x = r[:-1]
    n = len(y)
    x_mean = x.mean(); y_mean = y.mean()
    cov = np.sum((x - x_mean) * (y - y_mean))
    var = np.sum((x - x_mean) ** 2)
    phi = cov / var if var > 0 else 0.0
    c = y_mean - phi * x_mean
    resid = y - (c + phi * x)
    sigma = float(np.std(resid, ddof=2)) if n > 2 else float(np.std(resid))
    return float(c), float(phi), sigma


def model_ar1(
    as_of: date,
    etf_returns: pd.DataFrame,
    label: str,
    horizon_months: int,
    n_sims: int = 1000,
    seed: int | None = None,
) -> ModelForecast | None:
    """AR(1) sobre log returns mensuales. Forecast h-step propagando varianza por MC."""
    sub = etf_returns[etf_returns["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub.loc[sub.index <= cut, "return_log"].dropna()
    if len(history) < 24:
        return None
    c, phi, sigma = fit_ar1_history(history)
    r_last = float(history.iloc[-1])
    rng = np.random.default_rng(seed if seed is not None else int(as_of.toordinal()))
    sims = np.zeros(n_sims)
    for i in range(n_sims):
        r_prev = r_last
        total = 0.0
        for _ in range(horizon_months):
            eps = rng.normal(0, sigma)
            r_t = c + phi * r_prev + eps
            total += r_t
            r_prev = r_t
        sims[i] = total
    return ModelForecast(
        model_name="AR1",
        as_of=as_of,
        horizon_months=horizon_months,
        samples=sims,
        center=float(np.median(sims)),
    )


def model_drift_vol(
    as_of: date,
    etf_returns: pd.DataFrame,
    label: str,
    horizon_months: int,
    n_sims: int = 1000,
    lookback_months: int = 36,
    seed: int | None = None,
) -> ModelForecast | None:
    """Random walk con drift = mean(returns últimos lookback meses), vol = std.

    Forecast h-step: drift · h + N(0, vol · √h).
    """
    sub = etf_returns[etf_returns["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub.loc[sub.index <= cut, "return_log"].dropna()
    if len(history) < lookback_months:
        return None
    recent = history.iloc[-lookback_months:].values
    drift = float(recent.mean())
    vol = float(recent.std(ddof=1))
    rng = np.random.default_rng(seed if seed is not None else int(as_of.toordinal()) + 1)
    sims = rng.normal(
        loc=drift * horizon_months,
        scale=vol * np.sqrt(horizon_months),
        size=n_sims,
    )
    return ModelForecast(
        model_name="Drift_vol",
        as_of=as_of,
        horizon_months=horizon_months,
        samples=sims,
        center=float(np.median(sims)),
    )
