"""Queries para el panorama global (Lámina 5)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .store import MasterStore


# Tabla de bancos centrales / mercados que vamos a reportar
GLOBAL_MARKETS = [
    {
        "country":      "USA",
        "central_bank": "Fed",
        "policy_features":     ["FED_FUNDS_UPPER", "fred_fed_funds_target_upper"],
        "policy_label":        "Target upper",
        "yield_10y_features":  ["UST_10Y"],
        "yield_10y_label":     "UST 10Y",
    },
    {
        "country":      "Euro Area",
        "central_bank": "BCE",
        "policy_features":     ["fred_ecb_dfr"],
        "policy_label":        "DFR (Depo)",
        "yield_10y_features":  ["fred_bund_10y"],
        "yield_10y_label":     "Bund 10Y",
    },
    {
        "country":      "UK",
        "central_bank": "BoE",
        "policy_features":     ["fred_boe_bank_rate"],
        "policy_label":        "Bank Rate",
        "yield_10y_features":  ["fred_gilt_10y"],
        "yield_10y_label":     "Gilt 10Y",
    },
    {
        "country":      "Japón",
        "central_bank": "BoJ",
        "policy_features":     ["fred_boj_call_rate_hist"],  # FRED desactualizado
        "policy_label":        "Call Rate*",
        "yield_10y_features":  ["fred_jgb_10y"],
        "yield_10y_label":     "JGB 10Y",
        "caveat":              "FRED desactualizado (último dato 2023). BoJ rate actual a confirmar manualmente.",
    },
    {
        "country":      "México",
        "central_bank": "Banxico",
        "policy_features":     [],  # no en FRED automatico — pendiente
        "policy_label":        "TIIE 28 (pendiente)",
        "yield_10y_features":  ["fred_mexico_10y"],
        "yield_10y_label":     "Mex 10Y",
    },
]


def _safe_value(store: MasterStore, features: list[str], as_of: date) -> float | None:
    for f in features:
        try:
            v = store.get_value(f, as_of)
            if v is not None and not pd.isna(v):
                return float(v)
        except Exception:
            continue
    return None


@dataclass
class GlobalRow:
    country: str
    central_bank: str
    policy_label: str
    policy_now: float | None
    policy_prev_month: float | None
    yield_10y_label: str
    yield_10y_now: float | None
    yield_10y_prev_month: float | None
    caveat: str = ""

    @property
    def policy_delta_bps(self) -> int | None:
        if self.policy_now is None or self.policy_prev_month is None:
            return None
        return int(round((self.policy_now - self.policy_prev_month) * 100))

    @property
    def yield_10y_delta_bps(self) -> int | None:
        if self.yield_10y_now is None or self.yield_10y_prev_month is None:
            return None
        return int(round((self.yield_10y_now - self.yield_10y_prev_month) * 100))


def get_global_snapshot(store: MasterStore, as_of: date) -> list[GlobalRow]:
    """Snapshot global a `as_of` con tasa política y curva 10Y por mercado."""
    mes_anterior_ts = pd.Timestamp(as_of) - pd.DateOffset(months=1)
    mes_anterior = mes_anterior_ts.date()

    out = []
    for m in GLOBAL_MARKETS:
        row = GlobalRow(
            country=m["country"],
            central_bank=m["central_bank"],
            policy_label=m["policy_label"],
            policy_now=_safe_value(store, m["policy_features"], as_of),
            policy_prev_month=_safe_value(store, m["policy_features"], mes_anterior),
            yield_10y_label=m["yield_10y_label"],
            yield_10y_now=_safe_value(store, m["yield_10y_features"], as_of),
            yield_10y_prev_month=_safe_value(store, m["yield_10y_features"], mes_anterior),
            caveat=m.get("caveat", ""),
        )
        out.append(row)
    return out


def get_policy_history(
    store: MasterStore,
    features_by_label: dict[str, list[str]],
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Devuelve la serie 'as_of' de una colección de features para el plot.

    Output: DataFrame con index=fecha, columnas=labels.
    """
    series_dict = {}
    for label, features in features_by_label.items():
        s = None
        for f in features:
            try:
                s = store.get_series(f, as_of=to_date, start=from_date)
                if s is not None and not s.empty:
                    break
            except Exception:
                continue
        series_dict[label] = s if s is not None else pd.Series(dtype=float)
    df = pd.DataFrame(series_dict).sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def get_dxy_snapshot(store: MasterStore, as_of: date) -> dict:
    """Snapshot DXY (Broad Dollar Index FRED)."""
    mes_anterior_ts = pd.Timestamp(as_of) - pd.DateOffset(months=1)
    ye_anterior = date(as_of.year - 1, 12, 31)

    now = _safe_value(store, ["fred_dxy_broad"], as_of)
    mes = _safe_value(store, ["fred_dxy_broad"], mes_anterior_ts.date())
    ye  = _safe_value(store, ["fred_dxy_broad"], ye_anterior)

    delta_mes = ((now - mes) / mes * 100) if (now and mes) else None
    delta_ytd = ((now - ye) / ye * 100) if (now and ye) else None

    return {
        "value":     now,
        "delta_mes_pct": delta_mes,
        "delta_ytd_pct": delta_ytd,
    }
