"""Cálculo de YTM bullet con frecuencia y base de día.

Trade-off declarado: asumimos bullet (sin call/put/sinking fund) salvo evidencia.
Bonos a tasa variable se etiquetan pero se excluyen de las curvas FIJA.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import numpy as np

FREQ_MAP = {
    "MENSUAL": 12,
    "BIMENSUAL": 6,
    "TRIMESTRAL": 4,
    "CUATRIMESTRAL": 3,
    "SEMESTRAL": 2,
    "ANUAL": 1,
    "AL VENCIMIENTO": 0,
    "CERO": 0,
    "": 2,  # default semestral si missing
    None: 2,
}

BASE_DAYS = {
    "30/360": 360.0,
    "ACT/360": 360.0,
    "365/360": 360.0,
    "ACT/365": 365.0,
    "ACT/ACT": 365.25,
    "": 365.0,
    None: 365.0,
}


def parse_fecha(x) -> date | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if isinstance(x, (date, datetime)):
        return x.date() if isinstance(x, datetime) else x
    s = str(x).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def years_between(d1: date, d2: date, day_basis: float = 365.0) -> float:
    return (d2 - d1).days / day_basis


def cashflows(
    settle: date,
    maturity: date,
    coupon_rate: float,
    freq_per_year: int,
    face: float = 100.0,
    day_basis: float = 365.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Genera (tiempos en años desde settle, montos) para un bono bullet.
    Cero cupón si freq_per_year == 0 o coupon_rate == 0.
    """
    if maturity <= settle:
        return np.array([]), np.array([])

    if freq_per_year == 0 or coupon_rate == 0:
        t = np.array([years_between(settle, maturity, day_basis)])
        amt = np.array([face])
        return t, amt

    coupon_amt = face * coupon_rate / freq_per_year
    step_days = int(round(365.25 / freq_per_year))

    dates = []
    d = maturity
    while d > settle:
        dates.append(d)
        # backward stepping en días aproximados
        d = date.fromordinal(d.toordinal() - step_days)
    dates = sorted(dates)

    t = np.array([years_between(settle, dt, day_basis) for dt in dates])
    amt = np.full(len(dates), coupon_amt)
    amt[-1] += face
    mask = t > 0
    return t[mask], amt[mask]


def ytm_from_price(
    price_clean: float,
    settle: date,
    maturity: date,
    coupon_rate: float,
    freq_per_year: int,
    face: float = 100.0,
    day_basis: float = 365.0,
) -> float | None:
    """Resuelve YTM por bisección con compounding anual continuo discretizado."""
    if price_clean is None or price_clean <= 0:
        return None
    t, amt = cashflows(settle, maturity, coupon_rate, freq_per_year, face, day_basis)
    if t.size == 0:
        return None

    def pv(y: float) -> float:
        return float(np.sum(amt / (1 + y) ** t)) - price_clean

    lo, hi = -0.5, 2.0
    if pv(lo) * pv(hi) > 0:
        # Expand range si no hay cambio de signo
        for hi_try in (5.0, 10.0):
            if pv(lo) * pv(hi_try) <= 0:
                hi = hi_try
                break
        else:
            return None

    for _ in range(100):
        mid = (lo + hi) / 2
        v = pv(mid)
        if abs(v) < 1e-7:
            return mid
        if pv(lo) * v < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def coupon_to_decimal(raw) -> float:
    """Latinex reporta tasas como porcentaje en algunos casos (e.g. 4.5) y en otros como decimal.
    Heurística: si > 1 → asumir % y dividir.
    """
    if raw is None:
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v > 1:
        return v / 100.0
    return v


def freq_int(raw) -> int:
    if raw is None:
        return 2
    return FREQ_MAP.get(str(raw).upper().strip(), 2)


def base_days(raw) -> float:
    if raw is None:
        return 365.0
    return BASE_DAYS.get(str(raw).upper().strip(), 365.0)
