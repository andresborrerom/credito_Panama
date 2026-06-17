"""Producto B — Nearest Neighbors histórico para escenarios de retornos.

Para una as_of_date dada:
1. Construir vector macro state (PCE YoY, U-3, BE 5Y, Fed Funds, curva 2s10s).
2. Buscar los K meses históricos más similares (distancia euclidiana estandarizada).
3. Para cada match, computar retornos forward N meses por asset class.
4. Particionar la distribución en 4 escenarios fijos:
     - Esperado (50%): Highest Density Interval — rango más angosto con 50% masa.
     - Bajista (20%): masa entre cola izquierda y límite inferior del Esperado.
     - Alcista (20%): masa entre límite superior del Esperado y cola derecha.
     - Riesgo (10%): colas extremas combinadas.
5. Aplicar a portafolio LUZ dado allocation.

Permite optimizar K por horizonte vía walk-forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.store import MasterStore


HORIZONS_DEFAULT = [1, 3, 6, 12]

ETF_FEATURES = ["BIL", "IGLA", "LQD", "GHYG", "EMB", "ACWI", "AGG"]

# Features del macro state que usamos para encontrar vecinos
MACRO_FEATURES = ["pce_yoy", "u3", "be5y", "fed_funds", "slope_2s10s"]


# ============================================================================
# Macro state vector
# ============================================================================
@dataclass
class MacroState:
    as_of: date
    pce_yoy: float
    u3: float
    be5y: float
    fed_funds: float
    slope_2s10s: float  # UST 10Y - UST 2Y

    def vector(self) -> np.ndarray:
        return np.array([self.pce_yoy, self.u3, self.be5y, self.fed_funds, self.slope_2s10s])


def _pce_yoy(store: MasterStore, as_of: date) -> float | None:
    """PCE core YoY a as_of (vintage point-in-time)."""
    try:
        s = store.get_series("fred_pce_core", as_of)
    except Exception:
        return None
    if s.empty:
        return None
    last = s.iloc[-1]
    target = pd.Timestamp(as_of) - pd.DateOffset(months=12)
    older = s[s.index <= target.date()]
    if older.empty:
        return None
    return float((last / older.iloc[-1] - 1) * 100)


def _safe(store: MasterStore, features: list[str], as_of: date) -> float | None:
    for f in features:
        try:
            v = store.get_value(f, as_of)
            if v is not None and not pd.isna(v):
                return float(v)
        except Exception:
            continue
    return None


def macro_state_at(store: MasterStore, as_of: date) -> MacroState | None:
    """Construye MacroState a una fecha. None si falta cualquier feature."""
    pce = _pce_yoy(store, as_of)
    u3 = _safe(store, ["fred_unemployment"], as_of)
    be5 = _safe(store, ["BE_5Y", "fred_be_5y"], as_of)
    ff = _safe(store, ["FED_FUNDS_UPPER", "fred_fed_funds_target_upper", "EFFR", "fred_fed_funds_effective"], as_of)
    ust2 = _safe(store, ["UST_2Y", "fred_ust_2y"], as_of)
    ust10 = _safe(store, ["UST_10Y", "fred_ust_10y"], as_of)
    if any(x is None for x in [pce, u3, be5, ff, ust2, ust10]):
        return None
    return MacroState(
        as_of=as_of,
        pce_yoy=pce, u3=u3, be5y=be5, fed_funds=ff,
        slope_2s10s=ust10 - ust2,
    )


def build_macro_history(
    store: MasterStore,
    start: date = date(2018, 1, 1),
    end: date | None = None,
) -> pd.DataFrame:
    """DataFrame mensual con [as_of, *MACRO_FEATURES]."""
    end = end or date.today()
    dates = pd.date_range(start, end, freq="ME").date
    rows = []
    for d in dates:
        s = macro_state_at(store, d)
        if s is None:
            continue
        rows.append({
            "as_of": s.as_of,
            "pce_yoy": s.pce_yoy,
            "u3": s.u3,
            "be5y": s.be5y,
            "fed_funds": s.fed_funds,
            "slope_2s10s": s.slope_2s10s,
        })
    return pd.DataFrame(rows)


# ============================================================================
# Nearest neighbors
# ============================================================================
@dataclass
class NeighborResult:
    target_date: date
    target_state: MacroState
    K: int
    neighbors: pd.DataFrame  # columnas: as_of, dist + macro features
    std_used: np.ndarray     # std de cada feature en la historia


def find_neighbors(
    target: MacroState,
    history: pd.DataFrame,
    K: int = 15,
    exclude_window_months: int = 0,
) -> NeighborResult:
    """Top-K meses históricos más similares al target.

    exclude_window_months: descarta meses entre [target-N, target+N] para
    evitar look-ahead en walk-forward.
    """
    hist = history.copy()
    # Excluir ventana cercana al target (para validación honesta)
    if exclude_window_months > 0:
        floor = pd.Timestamp(target.as_of) - pd.DateOffset(months=exclude_window_months)
        ceil  = pd.Timestamp(target.as_of) + pd.DateOffset(months=exclude_window_months)
        hist = hist[~((hist["as_of"] >= floor.date()) & (hist["as_of"] <= ceil.date()))]

    X = hist[MACRO_FEATURES].values
    std = X.std(axis=0, ddof=1)
    std[std == 0] = 1.0  # evitar /0
    X_std = (X - X.mean(axis=0)) / std
    t_std = (target.vector() - X.mean(axis=0)) / std

    dist = np.linalg.norm(X_std - t_std, axis=1)
    idx = np.argsort(dist)[:K]
    out = hist.iloc[idx].copy()
    out["dist"] = dist[idx]
    out = out.sort_values("dist")
    return NeighborResult(
        target_date=target.as_of,
        target_state=target,
        K=K,
        neighbors=out,
        std_used=std,
    )


# ============================================================================
# Forward returns y escenarios
# ============================================================================
def compute_forward_returns(
    neighbor_dates: list[date],
    etf_returns_long: pd.DataFrame,
    horizon_months: int,
    label: str,
) -> np.ndarray:
    """Para cada vecino, suma de log returns en los siguientes horizon_months para el ETF label.

    etf_returns_long: DataFrame de etfs_producto_b.parquet (long format).
    """
    sub = etf_returns_long[etf_returns_long["label"] == label].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")

    out = []
    for d in neighbor_dates:
        d_ts = pd.Timestamp(d)
        # ventana (d, d+horizon]
        window_end = d_ts + pd.DateOffset(months=horizon_months)
        window = sub[(sub.index > d_ts) & (sub.index <= window_end)]["return_log"]
        window = window.dropna()
        if len(window) >= max(1, horizon_months - 1):  # tolerar 1 mes faltante
            out.append(float(window.sum()))
    return np.array(out)


def hdi_interval(values: np.ndarray, mass: float = 0.50) -> tuple[float, float]:
    """Highest density interval: rango más angosto que contiene `mass` de los datos.

    Para muestras pequeñas, usamos approach por sliding window sobre los datos ordenados.
    """
    if len(values) == 0:
        return (float("nan"), float("nan"))
    sorted_v = np.sort(values)
    n = len(sorted_v)
    window = int(np.ceil(n * mass))
    if window >= n:
        return (float(sorted_v[0]), float(sorted_v[-1]))
    widths = sorted_v[window:] - sorted_v[:n - window]
    j = int(np.argmin(widths))
    return (float(sorted_v[j]), float(sorted_v[j + window]))


@dataclass
class Scenario:
    name: str
    prob: float
    low: float
    high: float
    mean: float
    n_obs: int


@dataclass
class ScenarioSet:
    label: str
    horizon_months: int
    K: int
    n_neighbors_with_returns: int
    raw_returns: np.ndarray
    risk: Scenario          # cola izq extrema (cutoff fijo)
    bearish: Scenario       # entre risk y HDI low (empírica)
    expected: Scenario      # HDI 50% (optimizado)
    bullish: Scenario       # entre HDI high y upside (empírica)
    upside: Scenario        # cola der extrema (cutoff fijo)

    def all_scenarios(self) -> list[Scenario]:
        return [self.risk, self.bearish, self.expected, self.bullish, self.upside]


def build_scenarios(
    returns: np.ndarray, label: str, horizon_months: int, K: int,
    tail_mass: float = 0.025,
) -> ScenarioSet | None:
    """Particiona los retornos en 5 escenarios con framework simétrico:

    1. **Riesgo** (cola izquierda): peor `tail_mass` (default 2.5%) por percentil fijo.
    2. **Bajista**: entre Riesgo y HDI low. Probabilidad empírica.
    3. **Esperado (HDI 50%)**: rango más angosto que contiene 50% de la masa. ÚNICO optimizado.
    4. **Alcista**: entre HDI high y Sorpresa positiva. Probabilidad empírica.
    5. **Sorpresa positiva** (cola derecha): mejor `tail_mass` por percentil fijo.

    Suma: 2.5% + Bajista + 50% + Alcista + 2.5% = 100%.
    Bajista + Alcista = 45% empíricamente distribuido — su diferencia es skewness real
    (peras con peras, simétrico en los cutoffs).
    """
    if len(returns) < 5:
        return None

    sorted_r = np.sort(returns)
    n = len(sorted_r)

    # 1. HDI 50%
    window = int(np.ceil(n * 0.50))
    if window >= n:
        hdi_low, hdi_high = float(sorted_r[0]), float(sorted_r[-1])
    else:
        widths = sorted_r[window:] - sorted_r[:n - window]
        j = int(np.argmin(widths))
        hdi_low, hdi_high = float(sorted_r[j]), float(sorted_r[j + window])

    # 2. Cutoffs colas simétricos
    tail_idx_left = max(1, int(np.round(tail_mass * n)))
    risk_cutoff = float(sorted_r[tail_idx_left - 1])

    tail_idx_right = max(1, int(np.round(tail_mass * n)))
    upside_cutoff = float(sorted_r[-tail_idx_right])

    # 3. Particionar
    risk_returns    = returns[returns <= risk_cutoff]
    bear_returns    = returns[(returns > risk_cutoff) & (returns < hdi_low)]
    exp_returns     = returns[(returns >= hdi_low) & (returns <= hdi_high)]
    bull_returns    = returns[(returns > hdi_high) & (returns < upside_cutoff)]
    upside_returns  = returns[returns >= upside_cutoff]

    def _sc(name, arr):
        prob = len(arr) / n
        if len(arr) == 0:
            return Scenario(name=name, prob=prob, low=float("nan"), high=float("nan"),
                            mean=float("nan"), n_obs=0)
        return Scenario(name=name, prob=prob, low=float(arr.min()), high=float(arr.max()),
                        mean=float(arr.mean()), n_obs=int(len(arr)))

    return ScenarioSet(
        label=label,
        horizon_months=horizon_months,
        K=K,
        n_neighbors_with_returns=n,
        raw_returns=returns,
        risk=_sc("Riesgo (cola izq 2.5%)", risk_returns),
        bearish=_sc("Bajista", bear_returns),
        expected=_sc("Esperado (HDI 50%)", exp_returns),
        bullish=_sc("Alcista", bull_returns),
        upside=_sc("Sorpresa positiva (cola der 2.5%)", upside_returns),
    )


# ============================================================================
# Pipeline end-to-end
# ============================================================================
def predict_scenarios_for_etf(
    store: MasterStore,
    as_of: date,
    label: str,
    K: int = 15,
    horizon_months: int = 6,
    macro_history: pd.DataFrame | None = None,
    etf_returns: pd.DataFrame | None = None,
    exclude_window_months: int = 0,
) -> ScenarioSet | None:
    """Calcula los 4 escenarios para un ETF dado as_of, K, horizonte."""
    target = macro_state_at(store, as_of)
    if target is None:
        return None
    if macro_history is None:
        macro_history = build_macro_history(store, end=as_of)
    if etf_returns is None:
        etf_returns = pd.read_parquet(Path("data/external/tasas_mercantil/etfs_producto_b.parquet"))

    nr = find_neighbors(target, macro_history, K=K, exclude_window_months=exclude_window_months)
    neighbor_dates = nr.neighbors["as_of"].tolist()
    fwd_returns = compute_forward_returns(neighbor_dates, etf_returns, horizon_months, label)
    return build_scenarios(fwd_returns, label, horizon_months, K)


def predict_portfolio_scenarios(
    store: MasterStore,
    as_of: date,
    allocation: dict,           # {label: weight}, debe sumar 1.0
    K: int = 15,
    horizon_months: int = 6,
    macro_history: pd.DataFrame | None = None,
    etf_returns: pd.DataFrame | None = None,
    exclude_window_months: int = 0,
) -> dict:
    """Aplica nearest neighbors a cada ETF y combina con allocation."""
    if abs(sum(allocation.values()) - 1.0) > 0.01:
        raise ValueError(f"Allocation no suma 1.0: {sum(allocation.values())}")
    if macro_history is None:
        macro_history = build_macro_history(store, end=as_of)
    if etf_returns is None:
        etf_returns = pd.read_parquet(Path("data/external/tasas_mercantil/etfs_producto_b.parquet"))

    # Para cada ETF, get los retornos forward de los vecinos comunes
    target = macro_state_at(store, as_of)
    if target is None:
        return {}
    nr = find_neighbors(target, macro_history, K=K, exclude_window_months=exclude_window_months)
    neighbor_dates = nr.neighbors["as_of"].tolist()

    # Calcular retorno de portafolio en cada vecino (sumando pondedrado)
    portfolio_returns = np.zeros(len(neighbor_dates))
    valid_mask = np.ones(len(neighbor_dates), dtype=bool)

    for label, weight in allocation.items():
        fwd = compute_forward_returns(neighbor_dates, etf_returns, horizon_months, label)
        # alinear índices: si compute_forward_returns descarta algunos, hay que rehacer
        # Para simplicidad, recalculamos por ETF de forma manual
        sub = etf_returns[etf_returns["label"] == label].set_index("obs_date").sort_index()
        for i, d in enumerate(neighbor_dates):
            d_ts = pd.Timestamp(d)
            window_end = d_ts + pd.DateOffset(months=horizon_months)
            w = sub.loc[
                (sub.index > d_ts.date()) & (sub.index <= window_end.date()),
                "return_log",
            ].dropna()
            if len(w) >= max(1, horizon_months - 1):
                portfolio_returns[i] += weight * float(w.sum())
            else:
                valid_mask[i] = False

    portfolio_returns = portfolio_returns[valid_mask]

    scenarios = build_scenarios(portfolio_returns, "PORTAFOLIO", horizon_months, K)
    return {
        "as_of": as_of,
        "K": K,
        "horizon_months": horizon_months,
        "n_neighbors_used": len(portfolio_returns),
        "neighbors_dates": [d for d, v in zip(neighbor_dates, valid_mask) if v],
        "scenarios": scenarios,
        "allocation": allocation,
        "target_state": target,
    }


# ============================================================================
# Optimización de K via walk-forward
# ============================================================================
def optimize_k_walk_forward(
    store: MasterStore,
    etf_label: str,
    horizon_months: int,
    K_grid: list[int] = (5, 10, 15, 20, 30),
    test_dates: list[date] | None = None,
    macro_history: pd.DataFrame | None = None,
    etf_returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Walk-forward: para cada test date, predice con diferentes K, compara con realizado.

    Métricas reportadas por K:
    - cobertura_Esperado: % de realizados que cayeron en el rango Esperado (debería ~50%)
    - amplitud_Esperado_pct: ancho promedio del rango Esperado
    - sesgo: realizado − mediana Esperado (sesgo direccional)
    """
    if macro_history is None:
        macro_history = build_macro_history(store, end=date(2026, 5, 31))
    if etf_returns is None:
        etf_returns = pd.read_parquet(Path("data/external/tasas_mercantil/etfs_producto_b.parquet"))

    if test_dates is None:
        # Default: fechas mensuales 2020-01 a 2025-12 (suficiente para realizado)
        test_dates = pd.date_range("2020-01-31", "2025-04-30", freq="ME").date.tolist()

    rows = []
    for K in K_grid:
        covered = []
        widths = []
        biases = []
        for test_d in test_dates:
            target = macro_state_at(store, test_d)
            if target is None:
                continue
            # Excluir window de horizonte completo para no contaminar
            nr = find_neighbors(target, macro_history, K=K,
                                exclude_window_months=horizon_months + 1)
            neighbor_dates = nr.neighbors["as_of"].tolist()
            preds = compute_forward_returns(neighbor_dates, etf_returns, horizon_months, etf_label)
            ss = build_scenarios(preds, etf_label, horizon_months, K)
            if ss is None:
                continue
            # Realizado
            sub = etf_returns[etf_returns["label"] == etf_label].set_index("obs_date").sort_index()
            test_ts = pd.Timestamp(test_d)
            window_end = test_ts + pd.DateOffset(months=horizon_months)
            realized_window = sub.loc[
                (sub.index > test_ts.date()) & (sub.index <= window_end.date()),
                "return_log",
            ].dropna()
            if len(realized_window) < max(1, horizon_months - 1):
                continue
            realized = float(realized_window.sum())
            covered.append(1 if ss.expected.low <= realized <= ss.expected.high else 0)
            widths.append(ss.expected.high - ss.expected.low)
            biases.append(realized - (ss.expected.low + ss.expected.high) / 2)
        if covered:
            rows.append({
                "etf": etf_label,
                "horizon": horizon_months,
                "K": K,
                "n_tests": len(covered),
                "cobertura_Esperado_pct": np.mean(covered) * 100,
                "amplitud_Esperado_pct": np.mean(widths) * 100,
                "sesgo_pct": np.mean(biases) * 100,
                "calibracion_error_pct": abs(np.mean(covered) * 100 - 50),
            })
    return pd.DataFrame(rows)
