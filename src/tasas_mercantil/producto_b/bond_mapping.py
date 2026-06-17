"""Mapeo de bonos UST directos + TBill a retornos esperados (M4).

LUZ tiene 3 UST bonds directos (Nov-35, Feb-36, Nov-31) + 1 TBill (Nov-26),
sumando 31.7% del portafolio. No necesitan un modelo ETF — se mapean
analíticamente vía la fórmula clásica:

    retorno ≈ -D · Δyield + carry

donde D es la duration del bono, Δyield el cambio esperado del yield del
tenor benchmark, y carry = yield × (h_months / 12).

M4 compara TRES caminos para predecir Δyield, después mapea con la fórmula:

  - Path C (baseline naive carry): asume Δyield = 0. Sin banda.
  - Path A (AR1 sobre Δyield): modelo paramétrico simple. Banda chica.
  - Path B (BMA equal-weights de 4 modelos): NN_K10 + NN_K20 + Naive_boot +
    AR1, mezclados con peso 1/4. Banda completa.

A y B deben BATIR a C en MAE del centro o dar bandas útiles para
justificar valor agregado vs el "no pongo opinión" del carry.
"""
from __future__ import annotations
from datetime import date
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .bma import ModelForecast
from .curve_target import (
    model_nn_yield, model_naive_yield, model_ar1_yield, realized_yield_change,
)
from .nearest_neighbors import (
    build_macro_history, find_neighbors, macro_state_at,
)
from tasas_mercantil.data.store import load_master_store


CACHE_DIR = "data/external/tasas_mercantil"


# ---------------------------------------------------------------------------
# Definición de los 4 instrumentos directos en LUZ
# ---------------------------------------------------------------------------
@dataclass
class BondDef:
    name: str
    maturity: date
    coupon_y: float     # cupón anual en decimal (0.04 = 4%)
    tenor_proxy: str    # "US10Y", "US5Y", "US3M"
    weight_luz: float   # peso en LUZ
    yield_cache: str    # nombre del parquet en CACHE_DIR


LUZ_BONDS = [
    BondDef("UST Nov-35 4%",       date(2035, 11, 15), 0.04000,  "US10Y", 0.0997, "us10y_eom"),
    BondDef("UST Feb-36 4.125%",   date(2036, 2, 15),  0.04125,  "US10Y", 0.0872, "us10y_eom"),
    BondDef("UST Nov-31 1.375%",   date(2031, 11, 15), 0.01375,  "US5Y",  0.0707, "us5y_eom"),
    BondDef("TBill Nov-26 0%",     date(2026, 11, 15), 0.00000,  "US3M",  0.0592, "us3m_eom"),
]


def load_yield_series(yield_cache: str) -> pd.Series:
    """Carga serie EOM del tenor. Devuelve pd.Series indexada por date."""
    df = pd.read_parquet(f"{CACHE_DIR}/{yield_cache}.parquet")
    return df.set_index("date").iloc[:, 0].sort_index()


def macaulay_duration(plazo_anos: float, coupon_y: float, yield_y: float) -> float:
    """Macaulay duration aproximación para bono con cupón anual.

    Para zero coupon: D = plazo. Para bono con cupón c y yield y a plazo n:
        D = ((1+y)/y) · (1 - 1/(1+y)^n)    si c=y (par)
        Aproximación razonable para |c - y| chico.
    """
    if plazo_anos <= 0:
        return 0.0
    if coupon_y <= 0 or yield_y <= 0:
        return plazo_anos
    return (1 + yield_y) / yield_y * (1 - (1 + yield_y) ** (-plazo_anos))


def time_to_maturity_years(maturity: date, as_of: date) -> float:
    return (maturity - as_of).days / 365.25


def carry_h_months(yield_now_pp: float, h_months: int) -> float:
    """Carry en decimal para h meses. yield_now en puntos porcentuales."""
    return (yield_now_pp / 100.0) * (h_months / 12.0)


# ---------------------------------------------------------------------------
# Tres paths
# ---------------------------------------------------------------------------
@dataclass
class BondForecast:
    bond: str
    path: str               # "C_naive", "A_AR1", "B_BMA"
    h_months: int
    center: float
    samples: np.ndarray
    duration: float
    yield_at_as_of: float   # en pp
    carry: float            # en decimal


def forecast_bond_C_naive(bond: BondDef, as_of: date, h_months: int) -> BondForecast | None:
    """Path C: carry puro, asume Δyield = 0."""
    ttm = time_to_maturity_years(bond.maturity, as_of)
    if ttm <= 0:
        return None
    ys = load_yield_series(bond.yield_cache)
    hist = ys.loc[ys.index <= pd.Timestamp(as_of)].dropna()
    if hist.empty:
        return None
    y_now = float(hist.iloc[-1])      # en pp
    # Para zero-coupon usar yield directamente; para con-cupón usar cupón del bono
    coupon_pp = bond.coupon_y * 100 if bond.coupon_y > 0 else y_now
    D = macaulay_duration(ttm, coupon_pp / 100.0, y_now / 100.0)
    carry = carry_h_months(coupon_pp, h_months)
    # Δyield = 0 → retorno = carry
    return BondForecast(bond.name, "C_naive", h_months, carry,
                        np.array([carry]), D, y_now, carry)


def forecast_bond_A_AR1(bond: BondDef, as_of: date, h_months: int) -> BondForecast | None:
    """Path A: AR1 sobre Δyield, mapeado a retorno bono."""
    ttm = time_to_maturity_years(bond.maturity, as_of)
    if ttm <= 0:
        return None
    ys = load_yield_series(bond.yield_cache)
    mf = model_ar1_yield(as_of, ys, h_months)
    if mf is None:
        return None
    hist = ys.loc[ys.index <= pd.Timestamp(as_of)].dropna()
    y_now = float(hist.iloc[-1])
    coupon_pp = bond.coupon_y * 100 if bond.coupon_y > 0 else y_now
    D = macaulay_duration(ttm, coupon_pp / 100.0, y_now / 100.0)
    carry = carry_h_months(coupon_pp, h_months)
    # mf.samples está en pp (Δyield en pp). Convertir a decimal y aplicar -D + carry.
    return_samples = -D * (mf.samples / 100.0) + carry
    return BondForecast(bond.name, "A_AR1", h_months,
                        float(np.median(return_samples)),
                        return_samples, D, y_now, carry)


def forecast_bond_B_BMA(bond: BondDef, as_of: date, h_months: int,
                        macro_start: date = date(2003, 1, 1)) -> BondForecast | None:
    """Path B: BMA equal-weights de 4 modelos (NN_K10, NN_K20, Naive_boot, AR1)
    sobre Δyield, mapeado a retorno bono.

    No usa walk-forward CRPS (mantenemos equal weights honestos para POC).
    Si B equal-weights bate a A o C, vale la pena el walk-forward sofisticado.
    """
    ttm = time_to_maturity_years(bond.maturity, as_of)
    if ttm <= 0:
        return None
    ys = load_yield_series(bond.yield_cache)
    store = load_master_store()
    macro_hist = build_macro_history(store, start=macro_start, end=as_of)
    target = macro_state_at(store, as_of)
    if target is None:
        return None
    models = {
        "NN_K10":     model_nn_yield(target, macro_hist, ys, find_neighbors,
                                      K=10, h=h_months, label=bond.tenor_proxy),
        "NN_K20":     model_nn_yield(target, macro_hist, ys, find_neighbors,
                                      K=20, h=h_months, label=bond.tenor_proxy),
        "Naive_boot": model_naive_yield(as_of, ys, h_months),
        "AR1":        model_ar1_yield(as_of, ys, h_months),
    }
    if any(v is None for v in models.values()):
        return None
    # Equal weights: muestrear igual de cada modelo
    n_per = 250
    rng = np.random.default_rng(int(as_of.toordinal()))
    chunks = []
    for mf in models.values():
        idx = rng.choice(len(mf.samples), size=n_per, replace=True)
        chunks.append(mf.samples[idx])
    dy_samples = np.concatenate(chunks)
    hist = ys.loc[ys.index <= pd.Timestamp(as_of)].dropna()
    y_now = float(hist.iloc[-1])
    coupon_pp = bond.coupon_y * 100 if bond.coupon_y > 0 else y_now
    D = macaulay_duration(ttm, coupon_pp / 100.0, y_now / 100.0)
    carry = carry_h_months(coupon_pp, h_months)
    return_samples = -D * (dy_samples / 100.0) + carry
    return BondForecast(bond.name, "B_BMA", h_months,
                        float(np.median(return_samples)),
                        return_samples, D, y_now, carry)


def realized_bond_return(bond: BondDef, as_of: date, h_months: int) -> float | None:
    """Realized del bono via -D · Δyield_realized + carry.

    Usamos Δyield realizado del tenor proxy. No perfecto (el bono específico
    puede diverger del tenor) pero es la aproximación estándar.
    """
    ys = load_yield_series(bond.yield_cache)
    dy = realized_yield_change(as_of, ys, h_months)
    if dy is None:
        return None
    ttm = time_to_maturity_years(bond.maturity, as_of)
    if ttm <= 0:
        return None
    hist = ys.loc[ys.index <= pd.Timestamp(as_of)].dropna()
    y_now = float(hist.iloc[-1])
    coupon_pp = bond.coupon_y * 100 if bond.coupon_y > 0 else y_now
    D = macaulay_duration(ttm, coupon_pp / 100.0, y_now / 100.0)
    carry = carry_h_months(coupon_pp, h_months)
    return -D * (dy / 100.0) + carry
