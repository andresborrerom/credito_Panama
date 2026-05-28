"""Queries canonicas del modelo (ver ProyectoTasasMercantil/02_MODELO_DATOS.md).

Cada query recibe `as_of_date` y nunca lee del futuro. Construidas sobre la
API de `store.MasterStore`.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .store import MasterStore, FeatureNotFoundError


# Mapeos canonicos de curvas. Privilegia Bloomberg cuando esta disponible;
# fallback a FRED para los gaps (IORB, ON_RRP) o cross-check.

UST_TENOR_TO_FEATURE = {
    "1M": "UST_1M",
    "3M": "UST_3M",
    "6M": "UST_6M",
    "1Y": "UST_1Y",
    "2Y": "UST_2Y",
    "3Y": "UST_3Y",
    "5Y": "UST_5Y",
    "7Y": "UST_7Y",
    "10Y": "UST_10Y",
    "20Y": "UST_20Y",
    "30Y": "UST_30Y",
}

TIPS_TENOR_TO_FEATURE = {
    "5Y": "TIPS_5Y",
    "10Y": "TIPS_10Y",
    "20Y": "TIPS_20Y",
    "30Y": "TIPS_30Y",
}

BREAKEVEN_TENOR_TO_FEATURE = {
    "2Y": "BE_2Y",
    "5Y": "BE_5Y",
    "10Y": "BE_10Y",
    "30Y": "BE_30Y",
}

SOFR_OIS_TENOR_TO_FEATURE = {
    "2Y": "SOFR_OIS_2Y",
    "5Y": "SOFR_OIS_5Y",
    "10Y": "SOFR_OIS_10Y",
    "30Y": "SOFR_OIS_30Y",
}

SR3_FUTURES_FEATURES = [f"SR3_{n}Q" for n in range(1, 9)]
EURODOLLAR_FUTURES_FEATURES = [f"ED_{n}Q" for n in range(1, 9)]

# Politica monetaria: BBG por default, FRED como fallback
FED_FUNDS_FEATURES = {
    "upper":       ["FED_FUNDS_UPPER", "fred_fed_funds_target_upper"],
    "lower":       ["FED_FUNDS_LOWER", "fred_fed_funds_target_lower"],
    "pre2008":     ["FED_FUNDS_TARGET_PRE2008", "fred_fed_funds_target_pre2008"],
    "effective":   ["EFFR", "fred_fed_funds_effective"],
    "iorb":        ["fred_iorb", "fred_ioer_legacy", "IORB"],  # BBG IORB es sospechoso
    "on_rrp":      ["fred_on_rrp_award", "ON_RRP"],  # tasa en %, no volumen
}


def _try_features(store: MasterStore, features: list[str], as_of: date) -> tuple[str, float | None]:
    """Intenta features en orden de preferencia. Devuelve (feature_usado, valor)."""
    for fname in features:
        try:
            v = store.get_value(fname, as_of)
            if v is not None and not pd.isna(v):
                return (fname, v)
        except FeatureNotFoundError:
            continue
    return (features[0], None)


# ============================================================================
# QUERIES
# ============================================================================

def get_curve_ust(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Curva UST nominal a `as_of`. DataFrame con [tenor, value, obs_date_effective]."""
    df = store.get_curve("UST", UST_TENOR_TO_FEATURE, as_of)
    df["curve_id"] = "UST"
    df["currency"] = "USD"
    df["country"] = "US"
    df["yield_type"] = "nominal"
    return df


def get_curve_tips(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Curva real TIPS."""
    df = store.get_curve("TIPS", TIPS_TENOR_TO_FEATURE, as_of)
    df["curve_id"] = "TIPS"
    df["currency"] = "USD"
    df["country"] = "US"
    df["yield_type"] = "real"
    return df


def get_curve_breakevens(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Curva de breakevens (inflacion implicita)."""
    df = store.get_curve("BE", BREAKEVEN_TENOR_TO_FEATURE, as_of)
    df["curve_id"] = "BE"
    df["currency"] = "USD"
    df["country"] = "US"
    df["yield_type"] = "breakeven"
    return df


def get_curve_sofr_ois(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Curva swap SOFR OIS."""
    df = store.get_curve("SOFR_OIS", SOFR_OIS_TENOR_TO_FEATURE, as_of)
    df["curve_id"] = "SOFR_OIS"
    df["currency"] = "USD"
    df["country"] = "US"
    df["yield_type"] = "swap_ois"
    return df


def get_fed_funds_snapshot(store: MasterStore, as_of: date) -> dict:
    """Snapshot de tasas Fed a `as_of`. Maneja el cambio de regimen 2008."""
    snap = {"as_of": as_of}
    is_post_2008 = as_of >= date(2008, 12, 16)

    if is_post_2008:
        feat_u, snap["target_upper"] = _try_features(store, FED_FUNDS_FEATURES["upper"], as_of)
        feat_l, snap["target_lower"] = _try_features(store, FED_FUNDS_FEATURES["lower"], as_of)
        snap["target_midpoint"] = (
            (snap["target_upper"] + snap["target_lower"]) / 2
            if (snap["target_upper"] is not None and snap["target_lower"] is not None)
            else None
        )
        snap["target_source"] = f"{feat_u} / {feat_l}"
    else:
        feat_t, snap["target_unique"] = _try_features(store, FED_FUNDS_FEATURES["pre2008"], as_of)
        snap["target_source"] = feat_t

    feat_e, snap["effective"] = _try_features(store, FED_FUNDS_FEATURES["effective"], as_of)
    feat_i, snap["iorb"] = _try_features(store, FED_FUNDS_FEATURES["iorb"], as_of)
    feat_r, snap["on_rrp"] = _try_features(store, FED_FUNDS_FEATURES["on_rrp"], as_of)

    return snap


def get_sr3_strip(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Strip SR3 a `as_of`. Devuelve DataFrame con [contract_id, price, implied_rate]."""
    rows = []
    for fname in SR3_FUTURES_FEATURES:
        try:
            v = store.get_value(fname, as_of)
            if v is not None and not pd.isna(v):
                rows.append({
                    "contract_id": fname,
                    "n": int(fname.replace("SR3_", "").replace("Q", "")),
                    "price": v,
                    "implied_rate": 100.0 - v,
                })
        except FeatureNotFoundError:
            pass
    return pd.DataFrame(rows).sort_values("n").reset_index(drop=True) if rows else pd.DataFrame()


def get_eurodollar_strip(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Strip EuroDollar pre-SOFR. Mismo formato que SR3."""
    rows = []
    for fname in EURODOLLAR_FUTURES_FEATURES:
        try:
            v = store.get_value(fname, as_of)
            if v is not None and not pd.isna(v):
                rows.append({
                    "contract_id": fname,
                    "n": int(fname.replace("ED_", "").replace("Q", "")),
                    "price": v,
                    "implied_rate": 100.0 - v,
                })
        except FeatureNotFoundError:
            pass
    return pd.DataFrame(rows).sort_values("n").reset_index(drop=True) if rows else pd.DataFrame()


def get_implied_path_strip(store: MasterStore, as_of: date) -> pd.DataFrame:
    """Devuelve el strip de futuros vigente a `as_of`.

    - Post 2018-05-04: SR3.
    - Pre 2018-05-04: EuroDollar.
    - Solapamiento 2018-05 a 2021: ambos disponibles; preferimos SR3.
    """
    cutoff = date(2018, 5, 4)
    if as_of >= cutoff:
        df = get_sr3_strip(store, as_of)
        df["family"] = "SR3"
    else:
        df = get_eurodollar_strip(store, as_of)
        df["family"] = "ED"
    return df
