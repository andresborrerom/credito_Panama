"""Snapshot Venezuela. Por restricciones de acceso desde cloud (BCV 503, Monitor
Dólar DNS bloqueado), los valores entran como input manual del analista cada
mes y se hardcoded para el corte vigente. En el futuro: scraper desde un proxy
del grupo Mercantil.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


@dataclass
class VenezuelaSnapshot:
    """Input manual del corte. Marcamos como placeholder hasta confirmar con analista."""
    as_of: date
    fuente: str  # ej. "Estimación hardcoded — pendiente confirmación"

    # BCV (Banco Central de Venezuela)
    bcv_tasa_politica_pct: float | None
    bcv_encaje_legal_pct: float | None
    bcv_tasa_activa_max_pct: float | None
    bcv_tasa_pasiva_max_pct: float | None

    # FX
    fx_oficial_ves_usd: float | None
    fx_paralelo_ves_usd: float | None  # promedio de fuentes
    fx_oficial_mes_ant: float | None
    fx_paralelo_mes_ant: float | None

    # Bonos VEN / PDVSA (precio, no yield porque están en default)
    bono_ven_2027_precio: float | None
    bono_pdvsa_2037_precio: float | None
    bono_ven_2027_mes_ant: float | None
    bono_pdvsa_2037_mes_ant: float | None

    # M2 / liquidez (opcional)
    m2_bs_billones: float | None = None

    notas_corte: str = ""

    @property
    def fx_brecha_pct(self) -> float | None:
        if self.fx_oficial_ves_usd and self.fx_paralelo_ves_usd:
            return (self.fx_paralelo_ves_usd / self.fx_oficial_ves_usd - 1) * 100
        return None

    @property
    def fx_oficial_delta_mes_pct(self) -> float | None:
        if self.fx_oficial_ves_usd and self.fx_oficial_mes_ant:
            return (self.fx_oficial_ves_usd / self.fx_oficial_mes_ant - 1) * 100
        return None

    @property
    def fx_paralelo_delta_mes_pct(self) -> float | None:
        if self.fx_paralelo_ves_usd and self.fx_paralelo_mes_ant:
            return (self.fx_paralelo_ves_usd / self.fx_paralelo_mes_ant - 1) * 100
        return None


def load_venezuela_snapshot(path: Path) -> VenezuelaSnapshot:
    """Lee venezuela.yaml y devuelve VenezuelaSnapshot tipado."""
    with open(path) as f:
        data = yaml.safe_load(f)
    # as_of viene como string YYYY-MM-DD, convertir a date
    if isinstance(data["as_of"], str):
        data["as_of"] = date.fromisoformat(data["as_of"])
    return VenezuelaSnapshot(**data)


def snapshot_2026_05_placeholder() -> VenezuelaSnapshot:
    """Placeholder para corte mayo 2026.

    Valores ilustrativos para validar layout. Reemplazar con datos reales del
    analista en la sesión narrativa del corte.
    """
    return VenezuelaSnapshot(
        as_of=date(2026, 5, 28),
        fuente="PLACEHOLDER — valores ilustrativos pendientes de confirmación con analista",
        bcv_tasa_politica_pct=58.00,
        bcv_encaje_legal_pct=73.00,
        bcv_tasa_activa_max_pct=58.00,
        bcv_tasa_pasiva_max_pct=25.00,
        fx_oficial_ves_usd=185.50,
        fx_paralelo_ves_usd=225.80,
        fx_oficial_mes_ant=176.20,
        fx_paralelo_mes_ant=212.30,
        bono_ven_2027_precio=14.50,
        bono_pdvsa_2037_precio=8.25,
        bono_ven_2027_mes_ant=13.80,
        bono_pdvsa_2037_mes_ant=8.10,
        notas_corte="Restructuring proceso suspendido. Brecha cambiaria estable.",
    )
