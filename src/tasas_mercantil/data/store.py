"""Store unificado que junta las fuentes Bloomberg y FRED en una sola
vista canonica. Es la API que el modelo y los renderers consultan.

Esquema canonico:
    feature_name (str)    nombre del modelo
    ticker (str)          ticker original de la fuente (BBG o FRED series_id)
    obs_date (date)       fecha de observacion
    value (float)         valor en unidades naturales (% para tasas, etc.)
    vintage_date (date)   fecha del vintage (=obs_date si no se revisa)
    source (str)          'bloomberg' | 'fred' | 'fred_alfred'
    sheet (str)           hoja de origen (BBG) o categoria (FRED)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


DEFAULT_STORE_DIR = Path("data/external/tasas_mercantil")

# Solo estos parquets son fuentes canónicas del MasterStore (formato long
# con feature_name + vintage_date). El resto del directorio son outputs
# de procesos (BMA, ETF returns, news sentiment, FX, etc.) que viven al
# lado pero no son features de mercado consultadas por el modelo.
CANONICAL_PARQUETS = [
    "bloomberg_historico.parquet",
    "fred_curvas_usa.parquet",
    "fred_non_vintage.parquet",
    "fred_vintage_macro.parquet",
]


@dataclass
class MasterStore:
    """Wrapper alrededor del concat de los parquets."""

    df: pd.DataFrame
    presentation_window_days: int = 3  # T+3 estandar del reporte

    @property
    def features(self) -> list[str]:
        return sorted(self.df["feature_name"].unique().tolist())

    @property
    def date_range(self) -> tuple[date, date]:
        return (self.df["obs_date"].min(), self.df["obs_date"].max())

    def get_series(
        self,
        feature_name: str,
        as_of: date,
        start: date | None = None,
    ) -> pd.Series:
        """Devuelve la serie historica de `feature_name` *como se conocia* a `as_of`.

        Reglas:
        - Para no-vintage (vintage_date == obs_date): filtra obs_date <= as_of.
        - Para vintage: toma el ultimo vintage con vintage_date <= as_of + T3.
        """
        cutoff_vintage = as_of + timedelta(days=self.presentation_window_days)
        sub = self.df[self.df["feature_name"] == feature_name]
        if sub.empty:
            raise FeatureNotFoundError(f"Feature '{feature_name}' no esta en el store")

        # Detectar si es vintage (cualquier obs_date con > 1 vintage_date distinto)
        is_vintage = (
            sub.groupby("obs_date")["vintage_date"].nunique().max() > 1
        )

        if is_vintage:
            sub = sub[sub["vintage_date"] <= cutoff_vintage]
            # Por cada obs_date, quedarse con el ultimo vintage conocido
            sub = sub.sort_values(["obs_date", "vintage_date"])
            sub = sub.groupby("obs_date", as_index=False).last()
        else:
            sub = sub[sub["obs_date"] <= as_of]

        if start is not None:
            sub = sub[sub["obs_date"] >= start]

        return sub.set_index("obs_date")["value"].sort_index()

    def get_value(self, feature_name: str, as_of: date) -> float | None:
        """Devuelve el valor de `feature_name` en `as_of` con fill backward.
        Si la fecha es feriado, devuelve el valor del ultimo dia habil previo.
        """
        series = self.get_series(feature_name, as_of)
        if series.empty:
            return None
        return float(series.iloc[-1])

    def get_curve(
        self,
        feature_prefix: str,
        tenor_to_feature: dict[str, str],
        as_of: date,
    ) -> pd.DataFrame:
        """Devuelve curva entera a una fecha. Cada fila = un tenor.

        Args:
            feature_prefix: namespace para el log/error.
            tenor_to_feature: dict {tenor_label: feature_name}
                ej. {'2Y': 'UST_2Y', '5Y': 'UST_5Y', '10Y': 'UST_10Y'}

        Returns: DataFrame con columnas [tenor, value, obs_date_effective].
        """
        rows = []
        for tenor, fname in tenor_to_feature.items():
            try:
                series = self.get_series(fname, as_of)
                if series.empty:
                    rows.append({"tenor": tenor, "value": None, "obs_date_effective": None})
                else:
                    rows.append({
                        "tenor": tenor,
                        "value": float(series.iloc[-1]),
                        "obs_date_effective": series.index[-1],
                    })
            except FeatureNotFoundError:
                rows.append({"tenor": tenor, "value": None, "obs_date_effective": None})
        df = pd.DataFrame(rows)
        df["feature_prefix"] = feature_prefix
        return df


class FeatureNotFoundError(KeyError):
    pass


def load_master_store(
    store_dir: Path = DEFAULT_STORE_DIR,
    presentation_window_days: int = 3,
) -> MasterStore:
    """Carga y junta los parquets CANÓNICOS del directorio en un MasterStore.

    Solo concatena los parquets listados en CANONICAL_PARQUETS (formato
    long con feature_name + vintage_date). Los demás parquets del
    directorio son outputs de procesos auxiliares y se ignoran.
    """
    parquets = [store_dir / name for name in CANONICAL_PARQUETS
                if (store_dir / name).exists()]
    if not parquets:
        raise FileNotFoundError(
            f"No hay parquets canónicos en {store_dir}. "
            f"Esperaba alguno de: {CANONICAL_PARQUETS}"
        )
    frames = [pd.read_parquet(p) for p in parquets]
    df = pd.concat(frames, ignore_index=True)

    # Normalizar dtypes
    df["obs_date"] = pd.to_datetime(df["obs_date"]).dt.date
    df["vintage_date"] = pd.to_datetime(df["vintage_date"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return MasterStore(df=df, presentation_window_days=presentation_window_days)
