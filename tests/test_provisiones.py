"""Tests para src/analytics/provisiones.py — motor de pérdida esperada."""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.provisiones import (
    LGD_BY_INSTRUMENT,
    PD_BY_TIER,
    ProvisionResult,
    cumulative_pd,
    expected_loss,
    provision_by_rating,
    provision_for_position,
    sensitivity_table,
)


# ------------------------------------------------------------------- #
# Fórmula base — casos de referencia con números redondos
# ------------------------------------------------------------------- #
class TestExpectedLoss:
    def test_reference_case_1pct_45pct_100(self):
        """EL(PD=1%, LGD=45%, EAD=100, H=1y) = 0.45"""
        assert expected_loss(0.01, 0.45, 100, horizon_years=1.0) == pytest.approx(0.45)

    def test_reference_case_pd_zero_gives_zero(self):
        assert expected_loss(0.0, 0.5, 100) == 0.0

    def test_reference_case_ead_zero_gives_zero(self):
        assert expected_loss(0.05, 0.5, 0) == 0.0

    def test_lgd_zero_gives_zero(self):
        assert expected_loss(0.05, 0.0, 100) == 0.0

    def test_lgd_100pct_full_loss_on_default(self):
        """Con LGD=1, EL = PD × EAD"""
        assert expected_loss(0.02, 1.0, 100) == pytest.approx(2.0)

    def test_invalid_pd_raises(self):
        with pytest.raises(ValueError):
            expected_loss(-0.01, 0.45, 100)
        with pytest.raises(ValueError):
            expected_loss(1.5, 0.45, 100)

    def test_invalid_lgd_raises(self):
        with pytest.raises(ValueError):
            expected_loss(0.01, -0.1, 100)
        with pytest.raises(ValueError):
            expected_loss(0.01, 1.1, 100)

    def test_invalid_ead_raises(self):
        with pytest.raises(ValueError):
            expected_loss(0.01, 0.45, -100)


# ------------------------------------------------------------------- #
# PD acumulada — proceso independiente año a año
# ------------------------------------------------------------------- #
class TestCumulativePD:
    def test_one_year_equals_input(self):
        assert cumulative_pd(0.03, 1.0) == pytest.approx(0.03)

    def test_multi_year_monotonic(self):
        """PD 5y > PD 3y > PD 1y para misma PD anual."""
        pd1 = cumulative_pd(0.01, 1.0)
        pd3 = cumulative_pd(0.01, 3.0)
        pd5 = cumulative_pd(0.01, 5.0)
        assert pd1 < pd3 < pd5

    def test_10y_pd_1pct_matches_formula(self):
        """PD_10y(1%) = 1 - 0.99^10 = 0.09562 aprox."""
        expected = 1.0 - 0.99**10
        assert cumulative_pd(0.01, 10.0) == pytest.approx(expected)

    def test_zero_pd_stays_zero(self):
        assert cumulative_pd(0.0, 100.0) == 0.0

    def test_pd_one_stays_one(self):
        """Si PD=1 (default seguro), sigue siendo 1 en cualquier horizonte."""
        assert cumulative_pd(1.0, 5.0) == 1.0

    def test_horizon_zero_raises(self):
        with pytest.raises(ValueError):
            cumulative_pd(0.01, 0.0)

    def test_fractional_horizon(self):
        """PD 6m = 1 - (1 - PD_1y)^0.5"""
        pd6m = cumulative_pd(0.04, 0.5)
        assert pd6m == pytest.approx(1.0 - math.sqrt(1.0 - 0.04))


# ------------------------------------------------------------------- #
# Tablas de default: procedencia
# ------------------------------------------------------------------- #
class TestTableIntegrity:
    def test_all_tiers_have_pd(self):
        for t in ("T1", "T2", "T3", "T4", "T5"):
            assert t in PD_BY_TIER
            assert 0 <= PD_BY_TIER[t]["pd_1y"] <= 1

    def test_pd_monotonic_across_tiers(self):
        """T1 (mejor rating) tiene menor PD que T5 (peor)."""
        pds = [PD_BY_TIER[t]["pd_1y"] for t in ("T1", "T2", "T3", "T4", "T5")]
        assert pds == sorted(pds), f"PDs no son monótonos crecientes: {pds}"

    def test_all_pd_entries_have_source(self):
        for t, row in PD_BY_TIER.items():
            assert "source" in row and row["source"], f"Tier {t} no tiene source anotado"
            assert "confidence" in row, f"Tier {t} no tiene confidence anotado"

    def test_lgd_entries_have_source(self):
        for k, row in LGD_BY_INSTRUMENT.items():
            assert "source" in row and row["source"], f"Instrumento {k} sin source"
            assert 0 <= row["lgd"] <= 1

    def test_sub_t2_lgd_higher_than_senior(self):
        """Subordinado T2 debe tener LGD mayor que senior unsecured."""
        assert LGD_BY_INSTRUMENT["SUB_T2"]["lgd"] > LGD_BY_INSTRUMENT["BONOS"]["lgd"]

    def test_at1_lgd_highest(self):
        """AT1 = loss-absorption casi total."""
        assert LGD_BY_INSTRUMENT["AT1"]["lgd"] >= 0.9

    def test_secured_lgd_lower(self):
        """Bonos hipotecarios (garantizados) tienen LGD menor que senior unsecured."""
        assert LGD_BY_INSTRUMENT["BONOS HIPOTECARIOS"]["lgd"] < LGD_BY_INSTRUMENT["BONOS"]["lgd"]


# ------------------------------------------------------------------- #
# provision_for_position — end to end
# ------------------------------------------------------------------- #
class TestProvisionForPosition:
    def test_t3_bono_10mm_1y(self):
        """T3 (A(pan)) PD=0.30%, LGD=45% BONOS, EAD=10MM, 1y → EL = 13,500"""
        res = provision_for_position("T3", ead=10_000_000, instrumento="BONOS", horizon_years=1.0)
        assert res.el_horizon == pytest.approx(0.003 * 0.45 * 10_000_000)
        assert res.el_1y == pytest.approx(res.el_horizon)  # horizon=1y

    def test_returns_provision_result(self):
        res = provision_for_position("T2", ead=1_000_000, instrumento="BONOS")
        assert isinstance(res, ProvisionResult)
        d = res.as_dict()
        assert "pd_1y_pct" in d and "el_horizon" in d and "provision_pct_ead" in d

    def test_horizon_10y_increases_provision(self):
        r1 = provision_for_position("T3", ead=100, instrumento="BONOS", horizon_years=1.0)
        r10 = provision_for_position("T3", ead=100, instrumento="BONOS", horizon_years=10.0)
        assert r10.el_horizon > r1.el_horizon

    def test_pd_override_used(self):
        res = provision_for_position("T3", ead=100, instrumento="BONOS", pd_override=0.10)
        assert res.pd_1y == 0.10
        # EL should use overridden PD
        assert res.el_1y == pytest.approx(0.10 * 0.45 * 100)

    def test_lgd_override_used(self):
        res = provision_for_position("T3", ead=100, instrumento="BONOS", lgd_override=0.90)
        assert res.lgd == 0.90

    def test_invalid_tier_raises(self):
        with pytest.raises(ValueError):
            provision_for_position("T99", ead=100)

    def test_unknown_instrumento_falls_back_to_default(self):
        res = provision_for_position("T3", ead=100, instrumento="FOOBAR")
        assert res.lgd == LGD_BY_INSTRUMENT["DEFAULT"]["lgd"]

    def test_sub_t2_higher_provision_than_bonos(self):
        r_sr = provision_for_position("T3", ead=100, instrumento="BONOS")
        r_sub = provision_for_position("T3", ead=100, instrumento="SUB_T2")
        assert r_sub.el_horizon > r_sr.el_horizon

    def test_higher_tier_lower_provision(self):
        """T1 debe tener provisión menor que T5 para misma exposición."""
        r_t1 = provision_for_position("T1", ead=100, instrumento="BONOS", horizon_years=5.0)
        r_t5 = provision_for_position("T5", ead=100, instrumento="BONOS", horizon_years=5.0)
        assert r_t1.el_horizon < r_t5.el_horizon


# ------------------------------------------------------------------- #
# provision_by_rating — portafolio
# ------------------------------------------------------------------- #
class TestProvisionByRating:
    def test_empty_portfolio_returns_empty(self):
        df = pd.DataFrame(columns=["rating_tier", "ead", "instrumento"])
        result = provision_by_rating(df)
        assert result.empty

    def test_missing_column_raises(self):
        df = pd.DataFrame({"tier": ["T2"], "ead": [100]})
        with pytest.raises(KeyError):
            provision_by_rating(df)

    def test_portfolio_computed(self):
        df = pd.DataFrame({
            "rating_tier": ["T2", "T3", "T4"],
            "ead": [1_000_000, 2_000_000, 500_000],
            "instrumento": ["BONOS", "BONOS", "BONOS HIPOTECARIOS"],
        })
        result = provision_by_rating(df)
        assert len(result) == 3
        assert "el_horizon" in result.columns
        assert "provision_pct_ead" in result.columns
        # T4 with lower LGD (hipotecario 25%) can beat T3 with senior 45%, but
        # let's just check no NaN
        assert result["el_horizon"].notna().all()

    def test_horizon_column_used(self):
        df = pd.DataFrame({
            "rating_tier": ["T3", "T3"],
            "ead": [100, 100],
            "instrumento": ["BONOS", "BONOS"],
            "horizon_years": [1.0, 10.0],
        })
        result = provision_by_rating(df, horizon_col="horizon_years")
        # 10y > 1y
        assert result.iloc[1]["el_horizon"] > result.iloc[0]["el_horizon"]

    def test_invalid_tier_produces_nan_not_crash(self):
        df = pd.DataFrame({
            "rating_tier": ["T3", "INVALID"],
            "ead": [100, 100],
            "instrumento": ["BONOS", "BONOS"],
        })
        result = provision_by_rating(df)
        assert result.iloc[0]["el_horizon"] > 0
        assert np.isnan(result.iloc[1]["el_horizon"])


# ------------------------------------------------------------------- #
# sensitivity_table
# ------------------------------------------------------------------- #
class TestSensitivityTable:
    def test_default_grid_shape(self):
        t = sensitivity_table("T3", ead=1_000_000, instrumento="BONOS")
        # 6 PD levels × 6 LGD levels = 36 filas
        assert len(t) == 36
        assert set(t.columns) == {"pd_1y", "lgd", "el", "el_pct_ead"}

    def test_el_monotonic_in_pd(self):
        """A LGD fija, EL crece con PD."""
        t = sensitivity_table("T3", ead=100, instrumento="BONOS")
        for lgd_val in t["lgd"].unique():
            sub = t[t["lgd"] == lgd_val].sort_values("pd_1y")
            els = sub["el"].tolist()
            assert els == sorted(els), f"EL no monótono en PD para LGD={lgd_val}"

    def test_el_monotonic_in_lgd(self):
        """A PD fija, EL crece con LGD."""
        t = sensitivity_table("T3", ead=100, instrumento="BONOS")
        for pd_val in t["pd_1y"].unique():
            sub = t[t["pd_1y"] == pd_val].sort_values("lgd")
            els = sub["el"].tolist()
            assert els == sorted(els), f"EL no monótono en LGD para PD={pd_val}"

    def test_custom_grid(self):
        t = sensitivity_table(
            "T3", ead=100, instrumento="BONOS",
            pd_grid=[0.01, 0.05],
            lgd_grid=[0.30, 0.60],
        )
        assert len(t) == 4
