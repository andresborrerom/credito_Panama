"""Tests para src/analytics/credit_adjustments.py y concentration.py."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.credit_adjustments import (
    GUARANTOR_HAIRCUT_BY_TIER,
    GUARANTEE_ELIGIBILITY,
    PD_QUALITATIVE_SIGNALS,
    AdjustedCredit,
    adjust_lgd_by_guarantees,
    adjust_pd_by_qualitative_signals,
    compute_adjusted_credit,
)
from src.analytics.concentration import (
    CONCENTRATION_CHARGE_TABLE_GROUP,
    CONCENTRATION_CHARGE_TABLE_INDIVIDUAL,
    ConcentrationResult,
    concentration_charge,
)


# =========================================================================
# LGD Adjustments
# =========================================================================
class TestLGDAdjustments:
    def test_no_guarantee_returns_base(self):
        r = adjust_lgd_by_guarantees(lgd_base=0.45, ead=1_000_000)
        assert r["lgd_ajustada"] == 0.45
        assert r["fraccion_cubierta"] == 0.0

    def test_full_cash_collateral_reduces_lgd_to_zero(self):
        """Cash collateral 1:1 con el EAD → LGD ajustada = 0."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000, cash_collateral_amount=1_000_000,
        )
        assert r["lgd_ajustada"] == pytest.approx(0.0, abs=1e-9)
        assert r["fraccion_cubierta"] == 1.0

    def test_half_cash_collateral(self):
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000, cash_collateral_amount=500_000,
        )
        assert r["lgd_ajustada"] == pytest.approx(0.225)  # 0.45 × (1 - 0.5)

    def test_corp_guarantee_tier_a_reduces_lgd(self):
        """Corp guarantee tier T3 (A(pan)): haircut 20% → 80% cobertura."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000,
            corporate_guarantee_amount=1_000_000,
            corporate_guarantee_tier="T3",
            corporate_guarantee_audited=True,
        )
        # 1MM × 0.8 = 800k cobertura efectiva, fracción 0.8
        assert r["fraccion_cubierta"] == pytest.approx(0.8)
        assert r["lgd_ajustada"] == pytest.approx(0.45 * 0.2)

    def test_corp_guarantee_bbb_lower_effectiveness(self):
        """Corp guarantee tier T4 (BBB): haircut 40% → menos cobertura efectiva."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000,
            corporate_guarantee_amount=1_000_000,
            corporate_guarantee_tier="T4",
            corporate_guarantee_audited=True,
        )
        assert r["fraccion_cubierta"] == pytest.approx(0.6)

    def test_corp_guarantee_not_audited_is_ignored(self):
        """SAMDRO caso: garantor sin EEFF consolidados auditados → no cuenta."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000,
            corporate_guarantee_amount=1_000_000,
            corporate_guarantee_tier="T3",
            corporate_guarantee_audited=False,
        )
        assert r["lgd_ajustada"] == 0.45  # ignorado
        assert any("IGNORADA" in n for n in r["notes"])

    def test_personal_guarantee_is_flagged_but_not_credited(self):
        """Personal guarantee: no reduce LGD."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=1_000_000, personal_guarantee=True,
        )
        assert r["lgd_ajustada"] == 0.45
        assert r["personal_guarantee_flagged"] is True
        assert any("Personal guarantee" in n for n in r["notes"])

    def test_over_coverage_capped_at_ead(self):
        """Si garantía > EAD, la cobertura se capea en EAD."""
        r = adjust_lgd_by_guarantees(
            lgd_base=0.45, ead=500_000,
            corporate_guarantee_amount=10_000_000,  # muy grande
            corporate_guarantee_tier="T1",  # muy solvente
            corporate_guarantee_audited=True,
        )
        assert r["cobertura_efectiva_usd"] <= 500_000
        assert r["lgd_ajustada"] == pytest.approx(0.0, abs=1e-9)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            adjust_lgd_by_guarantees(lgd_base=-0.1, ead=100)
        with pytest.raises(ValueError):
            adjust_lgd_by_guarantees(lgd_base=1.1, ead=100)
        with pytest.raises(ValueError):
            adjust_lgd_by_guarantees(lgd_base=0.5, ead=0)


# =========================================================================
# PD Qualitative Adjustments
# =========================================================================
class TestPDQualitative:
    def test_no_signals_returns_base(self):
        r = adjust_pd_by_qualitative_signals(pd_base=0.01, active_signals=[])
        assert r["pd_ajustada"] == 0.01
        assert r["total_multiplier"] == 1.0

    def test_fco_cover_below_1x_doubles_pd(self):
        r = adjust_pd_by_qualitative_signals(
            pd_base=0.01, active_signals=["fco_cover_below_1x"]
        )
        assert r["pd_ajustada"] == pytest.approx(0.02)
        assert r["total_multiplier"] == 2.0

    def test_multiple_signals_multiply(self):
        r = adjust_pd_by_qualitative_signals(
            pd_base=0.01,
            active_signals=["fco_cover_below_1x", "d_ebitda_above_6x"],
        )
        # 2.0 × 1.5 = 3.0
        assert r["total_multiplier"] == pytest.approx(3.0)
        assert r["pd_ajustada"] == pytest.approx(0.03)

    def test_cap_at_5x(self):
        """Con muchas señales el multiplicador se capea en 5×."""
        all_signals = list(PD_QUALITATIVE_SIGNALS.keys())
        r = adjust_pd_by_qualitative_signals(pd_base=0.01, active_signals=all_signals)
        assert r["total_multiplier"] == 5.0
        assert r["cap_reached"] is True

    def test_pd_ajustada_capped_at_1(self):
        """PD ajustada no puede exceder 1.0 (100%)."""
        r = adjust_pd_by_qualitative_signals(
            pd_base=0.5, active_signals=["fco_cover_below_1x", "d_ebitda_above_6x"]
        )
        assert r["pd_ajustada"] <= 1.0

    def test_custom_multipliers(self):
        r = adjust_pd_by_qualitative_signals(
            pd_base=0.01, active_signals=["fco_cover_below_1x"],
            custom_multipliers={"fco_cover_below_1x": 3.0},
        )
        assert r["pd_ajustada"] == pytest.approx(0.03)

    def test_invalid_signal_raises(self):
        with pytest.raises(ValueError):
            adjust_pd_by_qualitative_signals(pd_base=0.01, active_signals=["foo"])

    def test_all_signals_have_source(self):
        for k, row in PD_QUALITATIVE_SIGNALS.items():
            assert row["source"], f"Signal {k} sin source"
            assert row["trigger"], f"Signal {k} sin trigger description"


# =========================================================================
# compute_adjusted_credit
# =========================================================================
class TestComputeAdjustedCredit:
    def test_no_adjustments_matches_base_el(self):
        """Sin señales ni garantías, EL ajustada = EL base."""
        r = compute_adjusted_credit(
            pd_base=0.01, lgd_base=0.45, ead=1_000_000,
            horizon_years=1.0, active_signals=[],
        )
        assert r.el_ajustada == pytest.approx(r.el_base)
        assert r.delta_el_pct == pytest.approx(0.0)

    def test_signals_only_increase_el(self):
        r = compute_adjusted_credit(
            pd_base=0.01, lgd_base=0.45, ead=1_000_000,
            active_signals=["fco_cover_below_1x", "d_ebitda_above_6x"],
        )
        assert r.pd_ajustada > r.pd_base
        assert r.el_ajustada > r.el_base
        assert r.delta_el_pct > 0

    def test_guarantee_decreases_el(self):
        r = compute_adjusted_credit(
            pd_base=0.01, lgd_base=0.45, ead=1_000_000,
            corporate_guarantee_amount=500_000,
            corporate_guarantee_tier="T2",
            corporate_guarantee_audited=True,
        )
        assert r.lgd_ajustada < r.lgd_base
        assert r.el_ajustada < r.el_base
        assert r.delta_el_pct < 0

    def test_maspv_case_scenario(self):
        """MASPV Serie B con todas las señales activas del rating report."""
        # PD base T4 (BBB) = 1.0%, LGD BONOS = 45%
        r = compute_adjusted_credit(
            pd_base=0.01, lgd_base=0.45, ead=2_000_000, horizon_years=1.5,
            active_signals=[
                "fco_cover_below_1x",           # cover 0.5x
                "d_ebitda_above_6x",            # 7.6x
                "no_consolidated_audited_financials",  # SAMDRO no auditado
                "spv_rollover_dependent",       # SB-6 es SPV
                "spot_price_exposure",          # 100% ETESA spot
            ],
            corporate_guarantee_amount=12_500_000,
            corporate_guarantee_tier="T5",  # SAMDRO $14.2MM revenue → tier bajo
            corporate_guarantee_audited=False,  # ausencia EEFF consolidados
            personal_guarantee=True,
        )
        # EL ajustada debe ser significativamente mayor
        assert r.el_ajustada > r.el_base * 3  # PD ×2×1.5×1.5×1.2×1.2 = 6.48× capped
        # LGD no debe reducirse (garantías inadmisibles)
        assert r.lgd_ajustada == 0.45


# =========================================================================
# Concentration
# =========================================================================
class TestConcentration:
    def test_small_exposure_zero_charge(self):
        """Exposición pequeña (< 5% del capital) → sin recargo."""
        r = concentration_charge(
            exposure_individual=1_000_000,
            capital_base=80_000,
            capital_regulatorio_banco=450_000_000,  # $450MM cap → 1MM = 0.22%
        )
        assert r.charge_individual == 0.0
        assert r.capital_with_concentration == r.capital_base

    def test_medium_exposure_gets_charge(self):
        """Exposición 5-10% → recargo 15%."""
        r = concentration_charge(
            exposure_individual=30_000_000,
            capital_base=2_400_000,
            capital_regulatorio_banco=450_000_000,  # 30MM = 6.67% cap
        )
        assert r.charge_individual == 0.15
        assert r.capital_with_concentration == pytest.approx(r.capital_base * 1.15)

    def test_high_exposure_triggers_high_charge(self):
        """> 20% → recargo 100%."""
        r = concentration_charge(
            exposure_individual=120_000_000,
            capital_base=9_600_000,
            capital_regulatorio_banco=450_000_000,  # 26.7% cap
        )
        assert r.charge_individual == 1.0

    def test_group_exposure_layer(self):
        """Exposición grupo 20-30% → 30% charge sobre lo del individual."""
        r = concentration_charge(
            exposure_individual=5_000_000,
            exposure_group_total=100_000_000,  # 22% del capital
            capital_base=400_000,
            capital_regulatorio_banco=450_000_000,
        )
        assert r.charge_group == 0.30

    def test_multiplicative_composition(self):
        """Individual + Grupo + Sectorial se multiplican."""
        r = concentration_charge(
            exposure_individual=30_000_000,  # 6.67% cap → 15% ind
            exposure_group_total=60_000_000,  # 13% cap → 15% grp
            exposure_sector=500_000_000,      # 25% portafolio → 25% sec
            portafolio_total_banco=2_000_000_000,
            capital_base=1_000_000,
            capital_regulatorio_banco=450_000_000,
        )
        expected_multiplier = 1.15 * 1.15 * 1.10  # ind 15% + grp 15% + sec 10%
        # But sector 25% → 15-25% bucket = 10% ✓
        assert r.capital_with_concentration == pytest.approx(
            r.capital_base * expected_multiplier, rel=0.01
        )

    def test_zero_capital_raises(self):
        with pytest.raises(ValueError):
            concentration_charge(
                exposure_individual=100, capital_base=8,
                capital_regulatorio_banco=0,
            )

    def test_notes_populated(self):
        r = concentration_charge(
            exposure_individual=5_000_000, capital_base=400_000,
            capital_regulatorio_banco=450_000_000,
        )
        assert len(r.notes) >= 2  # al menos individual + total
