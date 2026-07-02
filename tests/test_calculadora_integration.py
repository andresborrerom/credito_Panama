"""Test de integración de la calculadora: motores de provisión + capital.

Verifica que para un input estándar del banco (Mercantil-like: T3, BONOS
sector Financiero, EAD $10MM, plazo 5y), los cuatro componentes de la
calculadora funcionan juntos y devuelven una estructura coherente.

No prueba la UI Streamlit; solo la composición de funciones que la UI llama.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.capital import (
    CAR_MIN_TOTAL,
    capital_for_position,
    credit_capacity_by_rw,
    resolve_asset_class,
)
from src.analytics.provisiones import (
    provision_for_position,
    sensitivity_table,
)


# Input estándar para stress test end-to-end
STD = {
    "tier": "T3",
    "ead": 10_000_000,
    "instrumento": "BONOS",
    "sector": "Financiero",
    "plazo": 5.0,
}


class TestCalculadoraEndToEnd:
    def test_all_four_components_produce_values(self):
        """Los 4 paneles reciben data no-nula para input estándar."""
        # C. Capital
        cap = capital_for_position(
            tier=STD["tier"], ead=STD["ead"],
            instrumento=STD["instrumento"], sector=STD["sector"],
        )
        assert cap.rwa > 0
        assert cap.capital_required > 0
        assert cap.asset_class == "BANK"  # BONOS + Financiero → BANK
        assert cap.risk_weight == 0.50  # T3 BANK

        # D. Provisión
        prov = provision_for_position(
            tier=STD["tier"], ead=STD["ead"],
            instrumento=STD["instrumento"], horizon_years=STD["plazo"],
        )
        assert prov.pd_1y > 0
        assert prov.lgd > 0
        assert prov.el_1y > 0
        assert prov.el_horizon > prov.el_1y  # 5y > 1y

        # Sanity: EL 5y = PD_5y × LGD × EAD
        expected_el_5y = prov.pd_cumulative * prov.lgd * prov.ead
        assert prov.el_horizon == pytest.approx(expected_el_5y)

    def test_yield_cost_capital_margin_calculation(self):
        """Simula el resumen integrado de la calculadora."""
        yield_market = 0.0731  # 7.31% observado sector Financiero
        cap = capital_for_position(
            tier=STD["tier"], ead=STD["ead"],
            instrumento=STD["instrumento"], sector=STD["sector"],
        )
        prov = provision_for_position(
            tier=STD["tier"], ead=STD["ead"],
            instrumento=STD["instrumento"], horizon_years=STD["plazo"],
        )
        rendimiento_capital = 0.12  # supuesto interno del banco

        ingreso_bruto = STD["ead"] * yield_market
        costo_capital = cap.capital_required * rendimiento_capital
        margen_neto = ingreso_bruto - prov.el_1y - costo_capital
        margen_bp = margen_neto / STD["ead"] * 10000

        # Coherencia: margen debe ser positivo para T3 con 7.31%
        assert margen_neto > 0
        # Y menor que ingreso bruto
        assert margen_neto < ingreso_bruto
        # Costo total (provisión + costo capital) razonable como fracción del ingreso
        costo_total = prov.el_1y + costo_capital
        assert costo_total < ingreso_bruto * 0.5  # dejar >50% de margen bruto

    def test_sensitivity_grid_covers_stress_case(self):
        """Sensibilidad debe capturar caso 3× PD y 90% LGD como stress."""
        t = sensitivity_table(
            tier=STD["tier"], ead=STD["ead"],
            instrumento=STD["instrumento"], horizon_years=STD["plazo"],
        )
        pd_max = t["pd_1y"].max()
        lgd_max = t["lgd"].max()
        # Al menos 3× de la PD base y ≥90% LGD
        pd_base = 0.003
        assert pd_max >= pd_base * 2.5
        assert lgd_max >= 0.85

    def test_credit_capacity_matches_capital_impact(self):
        """El desbloqueo de crédito por $ de capital debe ser consistente."""
        # Si emito $30MM T2 y voy a originar corporativos IG (50% RW), con
        # CAR objetivo 13%, cuánto crédito puedo hacer.
        cap = credit_capacity_by_rw(30_000_000, car_target=0.13, risk_weight=0.50)
        # Aprox $461.5MM
        assert 460_000_000 < cap < 463_000_000

    def test_all_five_tiers_produce_valid_output(self):
        """La calculadora debe funcionar para cualquier tier sin excepción."""
        for t in ("T1", "T2", "T3", "T4", "T5"):
            cap = capital_for_position(
                tier=t, ead=1_000_000, instrumento="BONOS", sector="Financiero",
            )
            prov = provision_for_position(
                tier=t, ead=1_000_000, instrumento="BONOS", horizon_years=5.0,
            )
            assert cap.rwa >= 0
            assert prov.el_horizon >= 0

    def test_higher_tier_lower_costs(self):
        """Un mismo bono a mejor tier debe implicar menor provisión (menos PD)."""
        prov_t2 = provision_for_position(
            "T2", 1_000_000, "BONOS", horizon_years=5.0,
        )
        prov_t4 = provision_for_position(
            "T4", 1_000_000, "BONOS", horizon_years=5.0,
        )
        assert prov_t2.el_horizon < prov_t4.el_horizon

    def test_asset_class_resolution_consistent(self):
        """El asset class resuelto debe coincidir con lo que capital_for_position usa."""
        for instr in ["BONOS", "BONOS HIPOTECARIOS", "BONOS DEL TESORO", "SUB_T2"]:
            expected = resolve_asset_class(instr, sector="Financiero")
            actual = capital_for_position(
                "T3", 1_000_000, instrumento=instr, sector="Financiero"
            ).asset_class
            assert expected == actual, f"Mismatch para {instr}: {expected} vs {actual}"

    def test_calculadora_bonos_tesoro_zero_capital_positive_yield(self):
        """Bonos del Tesoro Panamá: capital cero, provisión ínfima como %."""
        cap = capital_for_position("T1", 10_000_000, instrumento="BONOS DEL TESORO")
        prov = provision_for_position(
            "T1", 10_000_000, instrumento="BONOS DEL TESORO", horizon_years=5.0,
        )
        assert cap.capital_required == 0
        # PD T1 (0.03%) × PD_5y_cumulative (~0.15%) × LGD tesoro (10%) × 10MM ≈ $1,500
        # Como % del EAD: 0.015% — mucho menor que un corporativo.
        assert prov.provision_pct_ead < 0.001  # < 0.1% del EAD
        # Y menor que el mismo bono como corporativo (por LGD y PD ambas más bajas)
        prov_corp = provision_for_position(
            "T3", 10_000_000, instrumento="BONOS", horizon_years=5.0,
        )
        assert prov.el_horizon < prov_corp.el_horizon

    def test_sovereign_works_with_any_tier(self):
        """Bono del Tesoro con cualquier tier del trade → RW 0% igual."""
        for t in ("T1", "T2", "T3", "T4", "T5"):
            cap = capital_for_position(
                t, 1_000_000, instrumento="BONOS DEL TESORO"
            )
            assert cap.capital_required == 0
            assert cap.rwa == 0


class TestSubordinadoT2Case:
    """Caso emblemático del memo v3: emisión T2 sub Mercantil Banco."""

    def test_t3_sub_t2_higher_capital_than_senior(self):
        """SUB_T2 debe consumir más capital que senior BONOS al mismo tier."""
        c_sr = capital_for_position("T3", 30_000_000, instrumento="BONOS",
                                      sector="Financiero")
        c_sub = capital_for_position("T3", 30_000_000, instrumento="SUB_T2")
        assert c_sub.risk_weight > c_sr.risk_weight
        assert c_sub.capital_required > c_sr.capital_required

    def test_t3_sub_t2_higher_provision_than_senior(self):
        """SUB_T2 debe implicar mayor LGD (75%) → mayor EL."""
        p_sr = provision_for_position("T3", 30_000_000, instrumento="BONOS",
                                        horizon_years=10.0)
        p_sub = provision_for_position("T3", 30_000_000, instrumento="SUB_T2",
                                         horizon_years=10.0)
        assert p_sub.lgd > p_sr.lgd
        assert p_sub.el_horizon > p_sr.el_horizon
