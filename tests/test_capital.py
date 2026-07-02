"""Tests para src/analytics/capital.py — motor de RWA y requerimiento de capital."""

from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.capital import (
    CAR_MIN_PRIMARIO,
    CAR_MIN_TOTAL,
    RISK_WEIGHTS_SBP,
    T2_CAP_MAX_PCT_PRIMARIO,
    T2_STEP_DOWN_PCT_ANNUAL,
    T2_STEP_DOWN_YEARS,
    CapitalResult,
    capital_for_position,
    capital_impact,
    capital_requirement,
    credit_capacity_by_rw,
    get_risk_weight,
    portfolio_rwa,
    resolve_asset_class,
    rwa,
)


class TestConstants:
    def test_car_min_total_is_8pct(self):
        assert CAR_MIN_TOTAL == 0.08

    def test_car_min_primario_is_4pct(self):
        assert CAR_MIN_PRIMARIO == 0.04

    def test_t2_cap_max_100pct_primario(self):
        assert T2_CAP_MAX_PCT_PRIMARIO == 1.0

    def test_step_down_matches_basilea(self):
        assert T2_STEP_DOWN_PCT_ANNUAL == 0.20
        assert T2_STEP_DOWN_YEARS == 5


class TestRiskWeightsTable:
    def test_all_tiers_covered_for_each_class(self):
        classes = {"SOVEREIGN_PAN", "BANK", "CORPORATE", "MORTGAGE_BACKED",
                   "SUBORDINATED", "AT1"}
        for c in classes:
            for t in ("T1", "T2", "T3", "T4", "T5"):
                if c == "SOVEREIGN_PAN" and t != "T1":
                    continue  # Soberano solo aplica a T1 en nuestra convención
                assert (c, t) in RISK_WEIGHTS_SBP, f"Falta ({c}, {t})"

    def test_all_entries_have_source(self):
        for k, v in RISK_WEIGHTS_SBP.items():
            assert "source" in v and v["source"], f"{k} sin source"
            assert "confidence" in v, f"{k} sin confidence"

    def test_sovereign_pan_zero_rw(self):
        assert RISK_WEIGHTS_SBP[("SOVEREIGN_PAN", "T1")]["rw"] == 0.0

    def test_bank_rw_monotonic_across_tiers(self):
        """RW banco aumenta (no decrece) al bajar rating."""
        prev = -1
        for t in ("T1", "T2", "T3", "T4", "T5"):
            rw = RISK_WEIGHTS_SBP[("BANK", t)]["rw"]
            assert rw >= prev, f"RW banco no monótono en T{t}"
            prev = rw

    def test_subordinated_rw_higher_than_senior_at_same_tier(self):
        """Subordinated debe tener RW > Corporate senior a mismo tier."""
        for t in ("T2", "T3", "T4"):
            sub = RISK_WEIGHTS_SBP[("SUBORDINATED", t)]["rw"]
            sen = RISK_WEIGHTS_SBP[("CORPORATE", t)]["rw"]
            assert sub >= sen, f"Subordinated RW no superior a Corporate para {t}"

    def test_mortgage_backed_at_top_tiers_is_favorable(self):
        """Bono hipotecario T1/T2 con look-through residencial → RW 35% (favorable)."""
        assert RISK_WEIGHTS_SBP[("MORTGAGE_BACKED", "T1")]["rw"] == 0.35
        assert RISK_WEIGHTS_SBP[("MORTGAGE_BACKED", "T2")]["rw"] == 0.35


class TestGetRiskWeight:
    def test_default_bank_t3(self):
        rw, src = get_risk_weight("T3", "BANK")
        assert rw == 0.50
        assert "Acuerdo 3-2016" in src

    def test_override_used(self):
        rw, src = get_risk_weight("T3", "BANK", rw_override=1.00)
        assert rw == 1.00
        assert "override" in src.lower()

    def test_invalid_pair_raises(self):
        with pytest.raises(ValueError):
            get_risk_weight("T3", "NON_EXISTENT_CLASS")

    def test_override_out_of_range_raises(self):
        with pytest.raises(ValueError):
            get_risk_weight("T3", "BANK", rw_override=-0.1)
        with pytest.raises(ValueError):
            get_risk_weight("T3", "BANK", rw_override=15.0)

    def test_sovereign_pan_falls_back_to_t1_regardless_of_tier(self):
        """Soberano Panamá siempre RW 0% independientemente del tier del trade."""
        for t in ("T1", "T2", "T3", "T4", "T5"):
            rw, src = get_risk_weight(t, "SOVEREIGN_PAN")
            assert rw == 0.0, f"Soberano Panamá con tier {t} debería tener RW 0%, tuvo {rw}"


class TestRwaAndCapitalReq:
    def test_rwa_reference(self):
        """RWA(100MM, 50%) = 50MM"""
        assert rwa(100_000_000, 0.50) == 50_000_000

    def test_rwa_zero_ead(self):
        assert rwa(0, 0.50) == 0

    def test_rwa_zero_rw(self):
        assert rwa(100, 0.0) == 0

    def test_rwa_negative_ead_raises(self):
        with pytest.raises(ValueError):
            rwa(-100, 0.5)

    def test_capital_req_reference(self):
        """Capital(RWA=100, CAR=8%) = 8"""
        assert capital_requirement(100, car_min=0.08) == pytest.approx(8.0)

    def test_capital_req_uses_default_8pct(self):
        assert capital_requirement(1000) == pytest.approx(80.0)

    def test_capital_req_negative_rwa_raises(self):
        with pytest.raises(ValueError):
            capital_requirement(-100)

    def test_capital_req_invalid_car_raises(self):
        with pytest.raises(ValueError):
            capital_requirement(100, car_min=0.0)
        with pytest.raises(ValueError):
            capital_requirement(100, car_min=1.5)


class TestResolveAssetClass:
    def test_tesoro_maps_to_sovereign(self):
        assert resolve_asset_class("BONOS DEL TESORO") == "SOVEREIGN_PAN"
        assert resolve_asset_class("NOTAS DEL TESORO") == "SOVEREIGN_PAN"
        assert resolve_asset_class("LETRAS DEL TESORO") == "SOVEREIGN_PAN"

    def test_bonos_default_corporate(self):
        assert resolve_asset_class("BONOS") == "CORPORATE"

    def test_bonos_financiero_becomes_bank(self):
        assert resolve_asset_class("BONOS", sector="Financiero") == "BANK"
        assert resolve_asset_class("BONOS", sector="FINANCIERO") == "BANK"

    def test_hipotecario(self):
        assert resolve_asset_class("BONOS HIPOTECARIOS") == "MORTGAGE_BACKED"

    def test_sub_and_at1(self):
        assert resolve_asset_class("SUB_T2") == "SUBORDINATED"
        assert resolve_asset_class("AT1") == "AT1"

    def test_unknown_falls_back_to_corporate(self):
        assert resolve_asset_class("XYZ") == "CORPORATE"


class TestCapitalForPosition:
    def test_treasury_position_zero_capital(self):
        """Tesoro Panamá → RW 0 → capital 0"""
        r = capital_for_position("T1", 10_000_000, instrumento="BONOS DEL TESORO")
        assert r.risk_weight == 0.0
        assert r.rwa == 0.0
        assert r.capital_required == 0.0

    def test_bono_corp_a_pan(self):
        """T3 corporate BONO $10MM → RW 50% → RWA 5MM → Cap 400k"""
        r = capital_for_position("T3", 10_000_000, instrumento="BONOS")
        assert r.asset_class == "CORPORATE"
        assert r.risk_weight == 0.50
        assert r.rwa == 5_000_000
        assert r.capital_required == 400_000

    def test_bono_banco_financiero_a_pan(self):
        """T3 con sector Financiero → asset class BANK → RW también 50%"""
        r = capital_for_position("T3", 10_000_000, instrumento="BONOS", sector="Financiero")
        assert r.asset_class == "BANK"
        assert r.risk_weight == 0.50

    def test_sub_t2_mercantil_tier_a(self):
        """T3 SUB_T2 → asset class SUBORDINATED → RW 150% → RWA 15MM → Cap 1.2MM sobre 10MM EAD"""
        r = capital_for_position("T3", 10_000_000, instrumento="SUB_T2")
        assert r.asset_class == "SUBORDINATED"
        assert r.risk_weight == 1.50
        assert r.rwa == 15_000_000
        assert r.capital_required == 1_200_000

    def test_bono_hipotecario_a_pan(self):
        """T3 hipotecario → RW 50% mediano → Cap 400k sobre 10MM"""
        r = capital_for_position("T3", 10_000_000, instrumento="BONOS HIPOTECARIOS")
        assert r.asset_class == "MORTGAGE_BACKED"
        assert r.risk_weight == 0.50

    def test_bono_hipotecario_top_tier(self):
        """T2 hipotecario → RW 35% (residencial look-through)"""
        r = capital_for_position("T2", 10_000_000, instrumento="BONOS HIPOTECARIOS")
        assert r.risk_weight == 0.35
        assert r.rwa == 3_500_000

    def test_rw_override_used(self):
        r = capital_for_position("T3", 100, instrumento="BONOS", rw_override=1.00)
        assert r.risk_weight == 1.00
        assert r.rwa == 100
        assert r.capital_required == 8

    def test_custom_car_min(self):
        """Con CAR objetivo 13% (interno banco), capital sobre RWA sube."""
        r = capital_for_position("T3", 10_000_000, instrumento="BONOS", car_min=0.13)
        assert r.capital_required == pytest.approx(5_000_000 * 0.13)

    def test_returns_capital_result(self):
        r = capital_for_position("T2", 1_000_000, instrumento="BONOS")
        assert isinstance(r, CapitalResult)
        d = r.as_dict()
        assert "risk_weight_pct" in d and "rwa" in d and "capital_required" in d
        assert "rw_source" in d


class TestPortfolioRwa:
    def test_empty_portfolio(self):
        df = pd.DataFrame(columns=["rating_tier", "ead", "instrumento"])
        result = portfolio_rwa(df)
        assert result.empty

    def test_portfolio_computed(self):
        df = pd.DataFrame({
            "rating_tier": ["T1", "T3", "T3", "T4"],
            "ead": [10_000_000, 5_000_000, 2_000_000, 1_000_000],
            "instrumento": ["BONOS DEL TESORO", "BONOS", "BONOS", "BONOS HIPOTECARIOS"],
            "sector": ["Gobierno", "Financiero", "Industriales", "Financiero"],
        })
        result = portfolio_rwa(df)
        assert len(result) == 4
        # Tesoro → 0
        assert result.iloc[0]["capital_required"] == 0.0
        # Banco T3 senior → RW 50% → RWA 2.5MM → cap 200k
        assert result.iloc[1]["capital_required"] == 200_000
        # Corp T3 senior → RW 50% → RWA 1MM → cap 80k
        assert result.iloc[2]["capital_required"] == 80_000

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"tier": ["T2"], "monto": [100]})
        with pytest.raises(KeyError):
            portfolio_rwa(df)

    def test_original_columns_preserved(self):
        df = pd.DataFrame({
            "nemotecnico": ["ABC001"],
            "rating_tier": ["T3"],
            "ead": [1_000_000],
            "instrumento": ["BONOS"],
            "sector": ["Industriales"],
        })
        result = portfolio_rwa(df)
        assert "nemotecnico" in result.columns
        assert result.iloc[0]["nemotecnico"] == "ABC001"


class TestCreditCapacity:
    def test_reference_case(self):
        """$30MM cap, CAR 13%, RW 50% → capacidad ~$461.5MM"""
        cap = credit_capacity_by_rw(30_000_000, car_target=0.13, risk_weight=0.50)
        assert cap == pytest.approx(30_000_000 / (0.13 * 0.50))
        assert 460_000_000 < cap < 462_000_000

    def test_lower_rw_more_capacity(self):
        low = credit_capacity_by_rw(1_000_000, car_target=0.13, risk_weight=0.20)
        high = credit_capacity_by_rw(1_000_000, car_target=0.13, risk_weight=1.00)
        assert low > high

    def test_higher_car_less_capacity(self):
        c8 = credit_capacity_by_rw(1_000_000, car_target=0.08)
        c13 = credit_capacity_by_rw(1_000_000, car_target=0.13)
        assert c8 > c13

    def test_zero_delta_zero_capacity(self):
        assert credit_capacity_by_rw(0) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            credit_capacity_by_rw(-1)

    def test_invalid_rw_raises(self):
        with pytest.raises(ValueError):
            credit_capacity_by_rw(100, risk_weight=0)
        with pytest.raises(ValueError):
            credit_capacity_by_rw(100, risk_weight=-0.5)


class TestCapitalImpact:
    def test_reference_case_matches_mercantil_v3(self):
        """Reproduce el ejemplo del memo v3: $30MM T2, cap $450MM, APR $3.5bn, CAR 13%"""
        r = capital_impact(
            monto_emision=30, capital_actual=450, apr_actual=3500,
            car_target_post=0.13, rw_originacion=0.50,
        )
        assert r["car_pre_pct"] == pytest.approx((450/3500) * 100, abs=0.02)
        assert r["car_post_sin_crecer_pct"] == pytest.approx((480/3500) * 100, abs=0.02)
        assert r["delta_car_bp"] > 80  # aprox +85 bp con CAR pre = 12.86%
        # capacidad ≈ (480/0.13 - 3500) / 0.5
        expected_cap = (480/0.13 - 3500) / 0.50
        assert r["credito_capacity_adicional"] == pytest.approx(expected_cap, rel=0.01)

    def test_higher_emisión_more_capital(self):
        r30 = capital_impact(30, 450, 3500, 0.13, 0.5)
        r60 = capital_impact(60, 450, 3500, 0.13, 0.5)
        assert r60["capital_post"] > r30["capital_post"]
        assert r60["credito_capacity_adicional"] > r30["credito_capacity_adicional"]

    def test_car_target_none_uses_current(self):
        r = capital_impact(30, 450, 3500)  # sin car_target_post
        assert r["car_target_pct"] == r["car_pre_pct"]

    def test_zero_apr_raises(self):
        with pytest.raises(ValueError):
            capital_impact(30, 450, 0)
