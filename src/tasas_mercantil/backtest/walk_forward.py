"""Walk-forward backtest del modelo y rivales.

Para cada as_of_date en la ventana:
1. Generar prediccion del modelo y de cada rival.
2. Avanzar el calendario por cada horizonte {1M, 3M, 6M, 12M}.
3. Lookup del "realizado" (effective fed funds promediado en el horizonte).
4. Calcular metricas.

Salida: DataFrame con (as_of, model, horizon, forecast, realized, error_bps,
abs_error_bps).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import pandas as pd

from ..data.store import MasterStore
from ..modelo.pieces.implied_path import compute_implied_path


HORIZONS_MONTHS = [1, 3, 6, 12]


def _add_months(d: date, months: int) -> date:
    """Suma `months` calendar meses a `d`."""
    y, m = d.year, d.month + months
    while m > 12:
        m -= 12
        y += 1
    # Clamp dia (ej. enero 31 + 1 mes -> feb 28/29)
    try:
        return date(y, m, d.day)
    except ValueError:
        return date(y, m, 28)


def realized_fed_funds_average(
    store: MasterStore,
    horizon_start: date,
    horizon_end: date,
) -> float | None:
    """Promedio de Effective Fed Funds (EFFR) en el rango [start, end].

    Realizacion de la prediccion. Si no hay datos completos, devuelve None.
    """
    try:
        series = store.get_series("EFFR", as_of=date.today())
    except Exception:
        try:
            series = store.get_series("fred_fed_funds_effective", as_of=date.today())
        except Exception:
            return None
    sub = series[(series.index >= horizon_start) & (series.index <= horizon_end)]
    if sub.empty:
        return None
    return float(sub.mean())


@dataclass
class BacktestResult:
    as_of: date
    model: str
    model_version: str
    horizon_months: int
    forecast: float | None
    realized: float | None
    error_bps: float | None  # forecast - realized (signed)


def backtest_implied_path(
    store: MasterStore,
    as_of_dates: list[date],
    horizons: list[int] = HORIZONS_MONTHS,
) -> pd.DataFrame:
    """Mini-backtest de la Pieza A (implied path puro) en N fechas."""
    rows = []
    for as_of in as_of_dates:
        try:
            pred = compute_implied_path(store, as_of)
        except Exception as e:
            print(f"  [{as_of}] FALLO compute_implied_path: {e}")
            continue

        # Mapeo horizonte_meses -> atributo de pred
        forecasts = {
            1:  pred.forecast_1m,
            3:  pred.forecast_3m,
            6:  pred.forecast_6m,
            12: pred.forecast_12m,
            24: pred.forecast_24m,
        }

        for h in horizons:
            horizon_end = _add_months(as_of, h)
            # Para el horizonte de 1M, "realized" = avg EFFR en el mes posterior.
            # Para 3M = avg EFFR en mes [+3, +3] (un solo mes en ese punto).
            # Por simplicidad arrancamos con una ventana de +/- 15 dias alrededor del centro.
            window = timedelta(days=15)
            realized = realized_fed_funds_average(
                store,
                horizon_start=horizon_end - window,
                horizon_end=horizon_end + window,
            )

            f = forecasts.get(h)
            err = (f - realized) * 100 if (f is not None and realized is not None) else None

            rows.append({
                "as_of": as_of,
                "model": "rival_implied",
                "model_version": pred.model_version,
                "horizon_months": h,
                "forecast": f,
                "realized": realized,
                "error_bps": err,
                "abs_error_bps": abs(err) if err is not None else None,
                "family": pred.family,
            })

    return pd.DataFrame(rows)


def backtest_taylor(
    store: MasterStore,
    as_of_dates: list[date],
    horizons: list[int] = HORIZONS_MONTHS,
) -> pd.DataFrame:
    """Backtest Pieza B Taylor rule en N fechas."""
    from ..modelo.pieces.reaction_fn import compute_taylor_rule

    rows = []
    for as_of in as_of_dates:
        try:
            pred = compute_taylor_rule(store, as_of)
        except Exception as e:
            print(f"  [{as_of}] FALLO compute_taylor_rule: {e}")
            continue

        forecasts = {
            1: pred.forecast_1m, 3: pred.forecast_3m,
            6: pred.forecast_6m, 12: pred.forecast_12m,
            24: pred.forecast_24m,
        }
        for h in horizons:
            horizon_end = _add_months(as_of, h)
            window = timedelta(days=15)
            realized = realized_fed_funds_average(
                store, horizon_end - window, horizon_end + window,
            )
            f = forecasts.get(h)
            err = (f - realized) * 100 if (f is not None and realized is not None) else None
            rows.append({
                "as_of": as_of, "model": "modelo_taylor_b",
                "model_version": pred.model_version, "horizon_months": h,
                "forecast": f, "realized": realized,
                "error_bps": err, "abs_error_bps": abs(err) if err is not None else None,
                "family": "taylor_rule",
            })
    return pd.DataFrame(rows)


def backtest_naive(
    store: MasterStore,
    as_of_dates: list[date],
    horizons: list[int] = HORIZONS_MONTHS,
) -> pd.DataFrame:
    """Naive baseline: forecast = tasa actual proyectada plana."""
    from ..data.queries import get_fed_funds_snapshot

    rows = []
    for as_of in as_of_dates:
        fed = get_fed_funds_snapshot(store, as_of)
        current = (fed.get("target_midpoint") or
                   fed.get("target_unique") or
                   fed.get("effective"))

        for h in horizons:
            horizon_end = _add_months(as_of, h)
            window = timedelta(days=15)
            realized = realized_fed_funds_average(
                store, horizon_end - window, horizon_end + window
            )
            err = (current - realized) * 100 if (current is not None and realized is not None) else None
            rows.append({
                "as_of": as_of,
                "model": "rival_naive",
                "model_version": "0.1.0",
                "horizon_months": h,
                "forecast": current,
                "realized": realized,
                "error_bps": err,
                "abs_error_bps": abs(err) if err is not None else None,
                "family": "naive_flat",
            })

    return pd.DataFrame(rows)
