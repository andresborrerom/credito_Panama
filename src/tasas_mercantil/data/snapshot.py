"""Point-in-time snapshot API. Invariante: NUNCA devolver datos que no
existian a `as_of_date`.

Reglas:
1. Para features con `vintage_aware: false` (tasas de mercado), basta filtrar
   `obs_date <= as_of_date`.
2. Para features con `vintage_aware: true` (macro), filtrar
   `obs_date <= as_of_date AND vintage_date <= as_of_date + 3 dias habiles`.
3. Features con `available_from > as_of_date` se devuelven como NaN (no
   inventar). El caller decide si fallar o seguir con caveat.

Este modulo es el ANCLA del modelo. Cualquier bug aqui contamina todo el
backtest. Cubierto por `tests/test_no_lookahead.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source_kind: str
    available_from: date
    vintage_aware: bool
    units: str | None = None
    freq: str | None = None


class FeatureCatalog:
    """Carga `configs/features.yaml` y expone lookup tipado."""

    def __init__(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f)
        self._features: dict[str, FeatureSpec] = {}
        for name, cfg in raw.get("features", {}).items():
            self._features[name] = FeatureSpec(
                name=name,
                source_kind=cfg["source_kind"],
                available_from=date.fromisoformat(cfg["available_from"]),
                vintage_aware=bool(cfg.get("vintage_aware", False)),
                units=cfg.get("units"),
                freq=cfg.get("freq"),
            )

    def get(self, name: str) -> FeatureSpec:
        return self._features[name]

    def available_at(self, name: str, as_of: date) -> bool:
        return self._features[name].available_from <= as_of

    def __iter__(self) -> Iterable[FeatureSpec]:
        return iter(self._features.values())


def get_point_in_time(
    feature_name: str,
    as_of: date,
    catalog: FeatureCatalog,
    store: pd.DataFrame,
    presentation_window_days: int = 3,
) -> pd.Series:
    """Devuelve la serie temporal del feature *como se conocia* a `as_of`.

    Args:
        feature_name: nombre del feature en el catalogo.
        as_of: fecha del corte (ultimo dia habil del mes objetivo).
        catalog: FeatureCatalog cargado.
        store: DataFrame con columnas [feature_name, obs_date, value,
            vintage_date]. Para features no-vintage, vintage_date == obs_date.
        presentation_window_days: dias habiles que permitimos despues de as_of
            (T+3 estandar del reporte).

    Returns:
        Serie con index=obs_date y values=value, restringida a lo que se
        conocia legitimamente a as_of + presentation_window.

    Raises:
        ValueError: si el feature no existe en el catalogo.
        FeatureNotAvailableError: si as_of < available_from del feature.
    """
    if feature_name not in {f.name for f in catalog}:
        raise ValueError(f"Feature desconocido: {feature_name}")

    spec = catalog.get(feature_name)
    if as_of < spec.available_from:
        raise FeatureNotAvailableError(
            f"{feature_name} no esta disponible a {as_of}. "
            f"Disponible desde {spec.available_from}."
        )

    cutoff_vintage = as_of + timedelta(days=presentation_window_days)
    sub = store[store["feature_name"] == feature_name]

    if spec.vintage_aware:
        # Tomar el ultimo vintage conocido a cutoff_vintage para cada obs_date
        sub = sub[sub["vintage_date"] <= cutoff_vintage]
        sub = sub.sort_values(["obs_date", "vintage_date"])
        sub = sub.groupby("obs_date", as_index=False).last()
    else:
        # Series no revisables: solo obs_date <= as_of
        sub = sub[sub["obs_date"] <= as_of]

    return sub.set_index("obs_date")["value"]


class FeatureNotAvailableError(Exception):
    """Feature solicitado en una fecha anterior a su available_from."""
