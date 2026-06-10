"""Agregador de portafolio LUZ — M5.

Toma cada posición de LUZ, le asigna una estrategia (ETF directo, bond
mapping, proxy asset-class, cash), corre el motor correspondiente, y
agrega las nubes MC ponderadas para producir un forecast del portafolio
completo.

Mapeo basado en snapshot 2026-06-09 (38 posiciones, USD 49 MM).
Cobertura por origen:
  - directo (ETF modelado o bond mapping):  74.3%
  - proxy (mismo asset-class via ETF):       25.1%
  - cash / money market (0 return):           0.6%

Correlación: implícita (samples independientes). Como cada forecast usa
su propio seed, la suma trata componentes como independientes → SUB-estima
la varianza del portafolio real. M6 puede mejorar con matriz de correlación.

Unidades: convertimos log returns de ETFs a decimal antes de sumar. Bond
samples ya están en decimal. Esto es correcto para agregación lineal.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

import numpy as np

from .forecast_api import forecast_etf, usability_sweet_spot
from .bond_mapping import LUZ_BONDS, forecast_bond_A_AR1


N_MC = 1000


@dataclass
class LUZPosition:
    name: str
    weight: float           # peso en LUZ (decimal)
    strategy: str           # "etf" | "bond" | "proxy_etf" | "cash"
    source: str = ""        # label ETF o índice del bond ("0"-"3")


# ---------------------------------------------------------------------------
# Mapeo completo LUZ (snapshot 2026-06-09)
# ---------------------------------------------------------------------------
LUZ_HOLDINGS: list[LUZPosition] = [
    # ETFs modelados directo (M3)
    LUZPosition("LQD (IBOXX IG)",               0.0948, "etf", "LQD"),
    LUZPosition("IGOV (Intl Treasuries)",       0.0989, "etf", "IGOV"),
    LUZPosition("GHYG (US&Intl HY)",            0.0827, "etf", "GHYG"),
    LUZPosition("BSJQ (BulletShares 2026 HY)",  0.0666, "etf", "BSJQ"),
    LUZPosition("EMB (JP Morgan USD EM)",       0.0428, "etf", "EMB"),
    LUZPosition("TIP (TIPS Bond)",              0.0200, "etf", "TIP"),
    LUZPosition("ACWI (MSCI ACWI)",             0.0200, "etf", "ACWI"),
    # Bonds UST + TBill directos (M4, path A AR1)
    LUZPosition("UST Nov-35 4%",                0.0997, "bond", "0"),
    LUZPosition("UST Feb-36 4.125%",            0.0872, "bond", "1"),
    LUZPosition("UST Nov-31 1.375%",            0.0707, "bond", "2"),
    LUZPosition("TBill Nov-26 0%",              0.0592, "bond", "3"),
    # Proxies asset-class
    LUZPosition("BulletShares 2027 HY",         0.0365, "proxy_etf", "BSJQ"),
    LUZPosition("Vanguard S&P 500",             0.0263, "proxy_etf", "ACWI"),
    LUZPosition("Invesco Intl Corp",            0.0261, "proxy_etf", "LQD"),
    LUZPosition("SPDR Short HY",                0.0203, "proxy_etf", "BSJQ"),
    LUZPosition("IEF 7-10y Treasury",           0.0162, "proxy_etf", "LQD"),
    LUZPosition("Vanguard FTSE Developed",      0.0099, "proxy_etf", "ACWI"),
    LUZPosition("iShares 1-3y Intl Treas",      0.0587, "proxy_etf", "IGOV"),
    LUZPosition("HF Sinclair Corp",             0.0102, "proxy_etf", "LQD"),
    # Sector ETFs chicos → ACWI proxy
    LUZPosition("S&P Global Financials",        0.0083, "proxy_etf", "ACWI"),
    LUZPosition("Global Tech",                  0.0077, "proxy_etf", "ACWI"),
    LUZPosition("Global Cons Disc",             0.0052, "proxy_etf", "ACWI"),
    LUZPosition("SPDR EM Equity",               0.0048, "proxy_etf", "ACWI"),
    LUZPosition("Global Industrials",           0.0044, "proxy_etf", "ACWI"),
    LUZPosition("Global Healthcare",            0.0037, "proxy_etf", "ACWI"),
    LUZPosition("Global Comm Services",         0.0033, "proxy_etf", "ACWI"),
    LUZPosition("Expanded Tech-Software",       0.0025, "proxy_etf", "ACWI"),
    LUZPosition("Global Materials",             0.0024, "proxy_etf", "ACWI"),
    LUZPosition("Global Cons Staples",          0.0015, "proxy_etf", "ACWI"),
    LUZPosition("Global Energy",                0.0014, "proxy_etf", "ACWI"),
    LUZPosition("Global Utilities",             0.0012, "proxy_etf", "ACWI"),
    LUZPosition("Global Real Estate",           0.0002, "proxy_etf", "ACWI"),
    # Cash + MM
    LUZPosition("Cash + MM (aprox 0 retorno)",  0.0062, "cash", ""),
]


@dataclass
class PortfolioForecast:
    as_of: date
    h_months: int
    center: float                       # mediana retorno decimal del portafolio
    samples: np.ndarray                 # nube MC del portafolio
    sweet_spot: dict                    # Vista C endógena del portafolio
    coverage_directa: float             # fracción LUZ modelada directo
    coverage_proxy: float               # fracción LUZ via proxy
    coverage_cash: float                # fracción cash
    components: dict                    # {posicion: contribucion_centro_decimal}
    comment: str

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of, "h_months": self.h_months,
            "center": self.center,
            "sweet_p": self.sweet_spot["p"],
            "sweet_lo": self.sweet_spot["lo"],
            "sweet_hi": self.sweet_spot["hi"],
            "coverage_directa": self.coverage_directa,
            "coverage_proxy": self.coverage_proxy,
            "coverage_cash": self.coverage_cash,
            "comment": self.comment,
        }


def _align_samples(samples: np.ndarray, n_target: int = N_MC,
                   seed: int = 42) -> np.ndarray:
    """Lleva samples a tamaño n_target (resample o broadcast)."""
    if len(samples) == n_target:
        return samples
    if len(samples) == 1:
        return np.full(n_target, samples[0])
    rng = np.random.default_rng(seed)
    return rng.choice(samples, size=n_target, replace=True)


def _log_to_decimal(log_samples: np.ndarray) -> np.ndarray:
    """Convierte log returns a decimal returns para agregación lineal correcta."""
    return np.exp(log_samples) - 1.0


def forecast_luz_portfolio(as_of: date, h_months: int) -> PortfolioForecast:
    """Forecast del portafolio LUZ completo agregando 32 posiciones.

    Estrategia por posición:
      - etf:       forecast_etf(label).bma_samples (log returns → decimal)
      - bond:      forecast_bond_A_AR1 (decimal nativo)
      - proxy_etf: forecast_etf(label_proxy).bma_samples (log → decimal)
      - cash:      ceros

    Agrega via suma ponderada de samples (correlación implícita).
    """
    # Cache de forecasts por fuente (evita re-correr el mismo ETF varias veces)
    etf_cache: dict[str, np.ndarray] = {}
    bond_cache: dict[int, np.ndarray] = {}

    component_samples: dict[str, tuple[float, np.ndarray]] = {}
    cov_directa = cov_proxy = cov_cash = 0.0

    for pos in LUZ_HOLDINGS:
        if pos.strategy == "etf":
            if pos.source not in etf_cache:
                r = forecast_etf(pos.source, as_of=as_of, h_months=h_months)
                etf_cache[pos.source] = _log_to_decimal(r.bma_samples)
            s = etf_cache[pos.source]
            cov_directa += pos.weight
        elif pos.strategy == "bond":
            bidx = int(pos.source)
            if bidx not in bond_cache:
                bf = forecast_bond_A_AR1(LUZ_BONDS[bidx], as_of, h_months)
                if bf is None:
                    raise RuntimeError(f"bond_mapping AR1 falló para {LUZ_BONDS[bidx].name}")
                bond_cache[bidx] = bf.samples
            s = bond_cache[bidx]
            cov_directa += pos.weight
        elif pos.strategy == "proxy_etf":
            if pos.source not in etf_cache:
                r = forecast_etf(pos.source, as_of=as_of, h_months=h_months)
                etf_cache[pos.source] = _log_to_decimal(r.bma_samples)
            s = etf_cache[pos.source]
            cov_proxy += pos.weight
        elif pos.strategy == "cash":
            s = np.zeros(N_MC)
            cov_cash += pos.weight
        else:
            raise ValueError(f"Estrategia desconocida: {pos.strategy}")
        component_samples[pos.name] = (pos.weight, _align_samples(s))

    # Agregación: suma ponderada (correlación implícita)
    portfolio = np.zeros(N_MC)
    contribs = {}
    for name, (w, s) in component_samples.items():
        portfolio += w * s
        contribs[name] = float(np.median(s)) * w

    center = float(np.median(portfolio))
    sweet = usability_sweet_spot(portfolio)
    comment = (
        f"[{as_of}] LUZ {h_months}m — Centro {center:+.2%}. "
        f"Vista C (sweet spot {int(sweet['p']*100)}%): "
        f"[{sweet['lo']:+.2%}, {sweet['hi']:+.2%}] ({sweet['width']*100:.1f}pp). "
        f"Cobertura: {cov_directa*100:.0f}% directo + "
        f"{cov_proxy*100:.0f}% proxy + {cov_cash*100:.1f}% cash."
    )
    return PortfolioForecast(
        as_of=as_of, h_months=h_months, center=center,
        samples=portfolio, sweet_spot=sweet,
        coverage_directa=cov_directa, coverage_proxy=cov_proxy,
        coverage_cash=cov_cash,
        components=contribs, comment=comment,
    )
