"""Invariante critico del proyecto: ninguna query point-in-time devuelve
datos posteriores a as_of_date.

Si este test falla, NADA del backtest es valido. Es el test que mas atencion
debe recibir.
"""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.tasas_mercantil.data.snapshot import (
    FeatureCatalog,
    FeatureNotAvailableError,
    get_point_in_time,
)


CONFIG_PATH = Path(__file__).parent.parent / "configs" / "features.yaml"


@pytest.fixture
def catalog() -> FeatureCatalog:
    return FeatureCatalog(CONFIG_PATH)


@pytest.fixture
def fake_store_non_vintage() -> pd.DataFrame:
    """Tasas de mercado (no se revisan)."""
    dates = pd.date_range("2020-01-01", "2026-05-30", freq="D")
    n = len(dates)
    return pd.DataFrame({
        "feature_name": ["ust_10y"] * n,
        "obs_date": dates.date,
        "value": [3.5] * n,
        "vintage_date": dates.date,
    })


@pytest.fixture
def fake_store_vintage() -> pd.DataFrame:
    """Macro con revisiones (vintage data simulada)."""
    rows = []
    for obs in pd.date_range("2024-01-01", "2024-12-01", freq="MS"):
        # Tres vintages por observacion (publicacion inicial + 2 revisiones)
        for delay_days in [30, 90, 180]:
            rows.append({
                "feature_name": "cpi_core_yoy",
                "obs_date": obs.date(),
                "value": 3.0 + 0.1 * delay_days / 30,
                "vintage_date": (obs + timedelta(days=delay_days)).date(),
            })
    return pd.DataFrame(rows)


def test_non_vintage_respects_as_of(catalog, fake_store_non_vintage):
    """Para series no-revisables: solo obs_date <= as_of."""
    as_of = date(2024, 6, 30)
    series = get_point_in_time("ust_10y", as_of, catalog, fake_store_non_vintage)
    assert series.index.max() <= as_of, "Filtro temporal no se respeta"


def test_vintage_respects_publication_window(catalog, fake_store_vintage):
    """Para series vintage: la revision usada debe ser la conocida a as_of+T3."""
    as_of = date(2024, 4, 15)
    series = get_point_in_time(
        "cpi_core_yoy",
        as_of,
        catalog,
        fake_store_vintage,
        presentation_window_days=3,
    )
    # CPI de enero 2024 se publica ~feb 2024 (delay_days=30 en el fake).
    # A as_of=2024-04-15 ya se sabia el primer vintage (delay_days=30).
    # No deberiamos ver vintages con vintage_date > 2024-04-18.
    assert "cpi_core_yoy" in catalog._features  # noqa: SLF001 (test)
    # El valor para obs_date=2024-01-01 corresponde al vintage delay=30 (no 90 ni 180)
    # value esperado = 3.0 + 0.1 * 30 / 30 = 3.1
    val = series.loc[date(2024, 1, 1)]
    assert abs(val - 3.1) < 1e-6, f"Vintage equivocado: {val}"


def test_feature_not_available_raises(catalog, fake_store_non_vintage):
    """Pedir un feature antes de su available_from debe fallar loud."""
    # TIPS no existe pre-2003. Si pedimos a 2002-01-01 debe fallar.
    with pytest.raises(FeatureNotAvailableError):
        get_point_in_time(
            "tips_10y",
            date(2002, 1, 1),
            catalog,
            fake_store_non_vintage,
        )


def test_unknown_feature_raises(catalog, fake_store_non_vintage):
    with pytest.raises(ValueError):
        get_point_in_time(
            "feature_inventado",
            date(2024, 1, 1),
            catalog,
            fake_store_non_vintage,
        )
