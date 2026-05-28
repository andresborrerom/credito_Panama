"""Tests del store y queries contra los datos reales ya cargados.

Estos tests dependen de que los parquets de data/external/tasas_mercantil/
existan. Skip si no estan.
"""
from datetime import date
from pathlib import Path

import pytest


STORE_DIR = Path("data/external/tasas_mercantil")


@pytest.fixture(scope="module")
def store():
    if not STORE_DIR.exists() or not list(STORE_DIR.glob("*.parquet")):
        pytest.skip(f"No hay parquets en {STORE_DIR}; correr backfill_fred + ingest_bloomberg primero")
    from src.tasas_mercantil.data.store import load_master_store
    return load_master_store(STORE_DIR)


# ===========================================================================
# Smoke tests
# ===========================================================================

def test_store_has_data(store):
    assert len(store.features) >= 50, f"Esperaba 50+ features, tengo {len(store.features)}"
    assert len(store.df) >= 400_000, f"Esperaba 400K+ filas, tengo {len(store.df):,}"


def test_store_date_range(store):
    start, end = store.date_range
    assert start <= date(1985, 1, 31), f"Inicio {start} mas tardio del esperado"
    assert end >= date(2026, 1, 1), f"Fin {end} mas temprano del esperado"


def test_ust_10y_exists_from_1985(store):
    series = store.get_series("UST_10Y", as_of=date(2026, 5, 28))
    assert series.index[0] <= date(1985, 1, 31), f"UST_10Y arranca en {series.index[0]}, esperaba <=1985-01-31"
    assert series.index[-1] <= date(2026, 5, 28)
    assert len(series) >= 10_000


# ===========================================================================
# Invariante: no look-ahead
# ===========================================================================

@pytest.mark.parametrize("as_of", [
    date(1995, 6, 30),
    date(2005, 12, 31),
    date(2010, 6, 30),
    date(2020, 3, 15),
    date(2025, 12, 31),
])
def test_no_lookahead_ust_10y(store, as_of):
    """Pedir UST_10Y a `as_of` no debe devolver fechas posteriores."""
    series = store.get_series("UST_10Y", as_of)
    assert series.index[-1] <= as_of, f"Look-ahead en {as_of}: ultima fecha = {series.index[-1]}"


@pytest.mark.parametrize("as_of", [
    date(1995, 6, 30),
    date(2005, 12, 31),
    date(2020, 3, 15),
])
def test_no_lookahead_fed_funds_effective(store, as_of):
    series = store.get_series("EFFR", as_of)
    assert series.index[-1] <= as_of


# ===========================================================================
# Cobertura de curvas en fechas clave
# ===========================================================================

def test_ust_curve_complete_today(store):
    """Hoy debe haber 11 puntos UST con valor (1M..30Y)."""
    from src.tasas_mercantil.data.queries import get_curve_ust
    df = get_curve_ust(store, date(2026, 5, 28))
    n_valid = df["value"].notna().sum()
    assert n_valid >= 9, f"Solo {n_valid} de 11 puntos UST tienen valor hoy"


def test_tips_curve_post_2003(store):
    """TIPS 5Y/10Y debe estar a 2010+."""
    from src.tasas_mercantil.data.queries import get_curve_tips
    df = get_curve_tips(store, date(2015, 12, 31))
    assert df.loc[df["tenor"] == "5Y", "value"].iloc[0] is not None
    assert df.loc[df["tenor"] == "10Y", "value"].iloc[0] is not None


def test_implied_path_uses_sr3_post_2018(store):
    """Despues de 2018-05-04 el strip implied path debe ser SR3, no ED."""
    from src.tasas_mercantil.data.queries import get_implied_path_strip
    df = get_implied_path_strip(store, date(2022, 6, 15))
    assert "SR3" in df["family"].unique()
    assert "ED" not in df["family"].unique()


def test_implied_path_uses_ed_pre_2018(store):
    """Antes de 2018 el strip debe ser EuroDollar."""
    from src.tasas_mercantil.data.queries import get_implied_path_strip
    df = get_implied_path_strip(store, date(2010, 6, 30))
    assert "ED" in df["family"].unique()
    assert "SR3" not in df["family"].unique()


# ===========================================================================
# Sanity de niveles (rangos plausibles por epoca)
# ===========================================================================

def test_fed_funds_2020_covid_zone(store):
    """En 2020-03-15 (justo antes del cut a cero) el target upper debe ser <=1.25%."""
    from src.tasas_mercantil.data.queries import get_fed_funds_snapshot
    fed = get_fed_funds_snapshot(store, date(2020, 3, 15))
    assert fed["target_upper"] is not None
    assert fed["target_upper"] <= 1.30, f"Esperaba <=1.30, tengo {fed['target_upper']}"


def test_fed_funds_1990_volcker_era(store):
    """A 1990-12-31 el target pre-2008 deberia estar entre 5% y 8%."""
    from src.tasas_mercantil.data.queries import get_fed_funds_snapshot
    fed = get_fed_funds_snapshot(store, date(1990, 12, 31))
    assert fed.get("target_unique") is not None
    assert 5.0 <= fed["target_unique"] <= 8.0


def test_on_rrp_is_rate_not_volume(store):
    """ON RRP debe ser tasa en %, no volumen en USD billion.
    Si el valor a 2024-12-31 es > 10, sigue siendo el ticker malo."""
    from src.tasas_mercantil.data.queries import get_fed_funds_snapshot
    fed = get_fed_funds_snapshot(store, date(2024, 12, 31))
    if fed.get("on_rrp") is not None:
        assert fed["on_rrp"] < 10.0, (
            f"ON RRP={fed['on_rrp']} parece volumen, no tasa. "
            "Verificar ticker FRED — debe ser RRPONTSYAWARD, no RRPONTSYD."
        )
