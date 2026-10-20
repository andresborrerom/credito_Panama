"""Tests de la escala internacional (traducción rating nacional → global)."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.capital import (
    RISK_WEIGHTS_INTL_OVERRIDE,
    RISK_WEIGHTS_SBP,
    capital_for_position,
    get_risk_weight,
)
from src.analytics.provisiones import (
    PD_BY_TIER,
    PD_BY_TIER_INTL,
    pd_table,
    provision_for_position,
    sensitivity_table,
)


class TestPDIntl:
    def test_t4_anchor_is_bank_table_value(self):
        """BBB-.pa ≡ B+ global → PD 1y 1.86% (dato de Riesgos Mercantil)."""
        assert PD_BY_TIER_INTL["T4"]["pd_1y"] == pytest.approx(0.0186)
        assert PD_BY_TIER_INTL["T4"]["equiv_intl"] == "B+"

    def test_intl_pd_higher_than_national_every_tier(self):
        """Traducir a escala global siempre sube la PD (la nacional topea en el soberano)."""
        for t in ("T1", "T2", "T3", "T4", "T5"):
            assert PD_BY_TIER_INTL[t]["pd_1y"] > PD_BY_TIER[t]["pd_1y"], t

    def test_intl_pd_monotonic(self):
        pds = [PD_BY_TIER_INTL[t]["pd_1y"] for t in ("T1", "T2", "T3", "T4", "T5")]
        assert pds == sorted(pds)

    def test_all_entries_have_source_and_equiv(self):
        for t, row in PD_BY_TIER_INTL.items():
            assert row["source"] and row["confidence"] and row["equiv_intl"], t

    def test_pd_table_selector(self):
        assert pd_table("nacional") is PD_BY_TIER
        assert pd_table("internacional") is PD_BY_TIER_INTL
        with pytest.raises(ValueError):
            pd_table("global")

    def test_provision_uses_intl_table(self):
        nac = provision_for_position("T4", 2_000_000, "BONOS", horizon_years=1.5)
        intl = provision_for_position("T4", 2_000_000, "BONOS", horizon_years=1.5,
                                      escala="internacional")
        assert nac.pd_1y == pytest.approx(0.0100)
        assert intl.pd_1y == pytest.approx(0.0186)
        assert intl.el_horizon > nac.el_horizon

    def test_maspv_intl_provision_reference(self):
        """Caso MASPV: $2MM, 1.5y, B+ intl → provisión ≈ $24,993."""
        r = provision_for_position("T4", 2_000_000, "BONOS", horizon_years=1.5,
                                   escala="internacional")
        assert r.el_horizon == pytest.approx(24_993, abs=30)

    def test_sensitivity_table_respects_escala(self):
        t_nac = sensitivity_table("T4", 1_000_000, "BONOS", escala="nacional")
        t_int = sensitivity_table("T4", 1_000_000, "BONOS", escala="internacional")
        assert t_int["pd_1y"].max() > t_nac["pd_1y"].max()

    def test_pd_override_wins_over_escala(self):
        r = provision_for_position("T4", 100, "BONOS", pd_override=0.05, escala="internacional")
        assert r.pd_1y == 0.05


class TestRWIntl:
    def test_corporate_t4_intl_is_150(self):
        rw, src = get_risk_weight("T4", "CORPORATE", escala="internacional")
        assert rw == 1.50
        assert "CRE20" in src

    def test_corporate_t4_national_stays_100(self):
        rw, _ = get_risk_weight("T4", "CORPORATE", escala="nacional")
        assert rw == 1.00

    def test_intl_rw_never_below_national(self):
        """La equivalencia global nunca mejora la ponderación."""
        for key, row in RISK_WEIGHTS_INTL_OVERRIDE.items():
            assert row["rw"] >= RISK_WEIGHTS_SBP[key]["rw"], key

    def test_sovereign_unchanged_in_intl(self):
        rw, _ = get_risk_weight("T4", "SOVEREIGN_PAN", escala="internacional")
        assert rw == 0.0

    def test_asset_class_without_override_falls_back(self):
        """MORTGAGE_BACKED no tiene override intl → usa tabla nacional."""
        rw_i, _ = get_risk_weight("T4", "MORTGAGE_BACKED", escala="internacional")
        rw_n, _ = get_risk_weight("T4", "MORTGAGE_BACKED", escala="nacional")
        assert rw_i == rw_n

    def test_invalid_escala_raises(self):
        with pytest.raises(ValueError):
            get_risk_weight("T4", "CORPORATE", escala="global")

    def test_rw_override_wins_over_escala(self):
        rw, src = get_risk_weight("T4", "CORPORATE", rw_override=0.75, escala="internacional")
        assert rw == 0.75 and "override" in src

    def test_maspv_capital_intl_reference(self):
        """MASPV $2MM corp B+ intl → RW 150% → RWA $3MM → capital $240k."""
        r = capital_for_position("T4", 2_000_000, "BONOS", sector="Energía",
                                 escala="internacional")
        assert r.risk_weight == 1.50
        assert r.rwa == 3_000_000
        assert r.capital_required == 240_000


class TestMASPVFourScenarios:
    """Los cuatro escenarios del estudio actualizado, con margen anualizado."""

    EAD, PLAZO, YIELD, ROE = 2_000_000, 1.5, 0.1025, 0.12

    def _margen(self, escala: str, pd_override=None) -> float:
        cap = capital_for_position("T4", self.EAD, "BONOS", sector="Energía", escala=escala)
        prov = provision_for_position("T4", self.EAD, "BONOS", horizon_years=self.PLAZO,
                                      escala=escala, pd_override=pd_override)
        ingreso = self.EAD * self.YIELD * self.PLAZO
        costo_cap = cap.capital_required * self.ROE * self.PLAZO
        return (ingreso - prov.el_horizon - costo_cap) / self.EAD / self.PLAZO

    def test_nacional_base(self):
        assert self._margen("nacional") == pytest.approx(0.0884, abs=0.0005)

    def test_intl_base(self):
        """B+ con RW 150%: 7.98%."""
        assert self._margen("internacional") == pytest.approx(0.0798, abs=0.0005)

    def test_intl_stress_falls_below_tesoro(self):
        """B+ × señales (cap 5× → PD 9.30%) con RW 150%: 4.72% < Tesoro ~5.03%."""
        m = self._margen("internacional", pd_override=0.0186 * 5)
        assert m == pytest.approx(0.0472, abs=0.0005)
        assert m < 0.0503
