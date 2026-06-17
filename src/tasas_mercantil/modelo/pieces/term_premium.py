"""Pieza D — Descomposición term premium del UST 10Y.

v0.4.0: dos descomposiciones complementarias.

(1) Identidad Fisher (mercado puro, sin modelo):
    UST_10Y_nominal = TIPS_10Y_real + BE_10Y_inflación_implícita

(2) Kim-Wright (modelo Fed Board):
    UST_10Y = expected_short_rate_avg_10Y + term_premium_10Y
    Donde:
        term_premium = THREEFYTP10 (FRED)
        expected_short_rate = UST_10Y - term_premium

La gracia de la Pieza D no es predecir tasas — es **interpretar** el
movimiento del mes. Permite decir cosas como "UST 10Y subió 15 bps en
mayo: 12 bps vienen del breakeven (inflación esperada al alza) y 3 bps
del real (term premium real). Compatible con vista UST 5-10Y OW".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ...data.store import MasterStore


MODEL_VERSION = "0.4.0"


@dataclass
class TermPremiumDecomposition:
    """Descomposición del UST 10Y para una as_of_date."""
    as_of: date

    # === Fisher (TIPS + BE) ===
    ust_10y_nominal: float
    tips_10y_real: float | None
    be_10y_inflation: float | None
    fisher_residual_bps: float | None  # nominal - (real + BE), debería ser ~0

    # === Kim-Wright (FRED) ===
    kw_yield_10y: float | None         # KW model fit 10Y
    kw_term_premium_10y: float | None  # KW term premium 10Y
    kw_expected_short_rate_10y: float | None  # implicito: UST_10Y - TP

    @property
    def term_premium_fraction(self) -> float | None:
        """Que fracción del UST 10Y es term premium."""
        if self.kw_term_premium_10y is None or self.ust_10y_nominal == 0:
            return None
        return self.kw_term_premium_10y / self.ust_10y_nominal * 100


@dataclass
class TermPremiumDelta:
    """Descomposición del CAMBIO del UST 10Y entre dos fechas."""
    from_date: date
    to_date: date

    delta_ust_10y_bps: float
    delta_tips_10y_real_bps: float | None      # contribución real (Fisher)
    delta_be_10y_inflation_bps: float | None   # contribución inflación (Fisher)
    delta_kw_tp_10y_bps: float | None          # contribución term premium (KW)
    delta_kw_expected_short_bps: float | None  # contribución expectativa (KW)


def _safe_get(store: MasterStore, features: list[str], as_of: date) -> float | None:
    for f in features:
        try:
            v = store.get_value(f, as_of)
            if v is not None and not pd.isna(v):
                return float(v)
        except Exception:
            continue
    return None


def compute_term_premium_decomposition(store: MasterStore, as_of: date) -> TermPremiumDecomposition:
    """Snapshot de la descomposición a `as_of`."""
    ust_10y = _safe_get(store, ["UST_10Y", "fred_ust_10y"], as_of)
    tips_10y = _safe_get(store, ["TIPS_10Y", "fred_tips_10y"], as_of)
    be_10y = _safe_get(store, ["BE_10Y", "fred_be_10y"], as_of)
    kw_yield = _safe_get(store, ["fred_kw_yield_10y"], as_of)
    kw_tp = _safe_get(store, ["fred_kw_tp_10y"], as_of)

    fisher_residual = None
    if ust_10y is not None and tips_10y is not None and be_10y is not None:
        fisher_residual = (ust_10y - tips_10y - be_10y) * 100  # bps

    kw_expected = None
    if ust_10y is not None and kw_tp is not None:
        kw_expected = ust_10y - kw_tp

    return TermPremiumDecomposition(
        as_of=as_of,
        ust_10y_nominal=ust_10y if ust_10y is not None else 0.0,
        tips_10y_real=tips_10y,
        be_10y_inflation=be_10y,
        fisher_residual_bps=fisher_residual,
        kw_yield_10y=kw_yield,
        kw_term_premium_10y=kw_tp,
        kw_expected_short_rate_10y=kw_expected,
    )


def compute_delta_decomposition(
    store: MasterStore, from_date: date, to_date: date
) -> TermPremiumDelta:
    """Descompone el cambio del UST 10Y entre dos fechas en sus componentes."""
    a = compute_term_premium_decomposition(store, from_date)
    b = compute_term_premium_decomposition(store, to_date)

    def d(x, y):
        if x is None or y is None: return None
        return round((y - x) * 100, 1)  # bps

    return TermPremiumDelta(
        from_date=from_date,
        to_date=to_date,
        delta_ust_10y_bps=d(a.ust_10y_nominal, b.ust_10y_nominal) or 0.0,
        delta_tips_10y_real_bps=d(a.tips_10y_real, b.tips_10y_real),
        delta_be_10y_inflation_bps=d(a.be_10y_inflation, b.be_10y_inflation),
        delta_kw_tp_10y_bps=d(a.kw_term_premium_10y, b.kw_term_premium_10y),
        delta_kw_expected_short_bps=d(a.kw_expected_short_rate_10y, b.kw_expected_short_rate_10y),
    )
