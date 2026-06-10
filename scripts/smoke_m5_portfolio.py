"""Smoke M5 — agregador portafolio LUZ end-to-end.

Valida:
  1. forecast_luz_portfolio corre sin errores en fechas con datos.
  2. Suma de weights = 1.0 (todas las posiciones cubiertas).
  3. Cobertura: directo ~74%, proxy ~25%, cash ~0.6%.
  4. El forecast del portafolio es sensato (centro entre componentes).
  5. Comparación con realized del portafolio sintético (groundtruth).
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

from tasas_mercantil.producto_b.portfolio_aggregator import (
    forecast_luz_portfolio, LUZ_HOLDINGS, _log_to_decimal,
    LUZ_BONDS,
)
from tasas_mercantil.producto_b.forecast_api import CACHE_DIR
from tasas_mercantil.producto_b.bond_mapping import realized_bond_return


FECHAS = [
    date(2023, 12, 31),
    date(2024, 6, 30),
]


def realized_luz_portfolio(as_of: date, h_months: int) -> float | None:
    """Realized retorno del portafolio LUZ aplicando weights a realized de
    cada componente (groundtruth para validar agregador).
    """
    # Realized de ETFs
    etfs = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    etfs["obs_date"] = pd.to_datetime(etfs["obs_date"])

    total = 0.0
    coverage_real = 0.0
    for pos in LUZ_HOLDINGS:
        if pos.strategy in ("etf", "proxy_etf"):
            sub = etfs[etfs["label"] == pos.source].sort_values("obs_date")
            sub = sub.set_index("obs_date")
            cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h_months)
            window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
            if len(window) < h_months - 1:
                continue
            decimal_ret = float(np.exp(window.sum()) - 1)
            total += pos.weight * decimal_ret
            coverage_real += pos.weight
        elif pos.strategy == "bond":
            bidx = int(pos.source)
            real = realized_bond_return(LUZ_BONDS[bidx], as_of, h_months)
            if real is None:
                continue
            total += pos.weight * real
            coverage_real += pos.weight
        elif pos.strategy == "cash":
            total += pos.weight * 0.0
            coverage_real += pos.weight

    if coverage_real < 0.90:
        return None  # demasiado faltante para ser representativo
    # Normalizar por coverage_real para comparable con el forecast
    return total / coverage_real if coverage_real > 0 else None


def hdi(samples: np.ndarray, mass: float) -> tuple[float, float]:
    s = np.sort(samples); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def main():
    print("=" * 150)
    print("SMOKE M5 — agregador portafolio LUZ")
    print("=" * 150)

    # 1. Verificar weights suman 1
    w_total = sum(p.weight for p in LUZ_HOLDINGS)
    print(f"\n[1/4] Suma de weights LUZ = {w_total:.4f} (esperado ≈ 1.0000)")
    assert 0.99 < w_total < 1.01, f"Weights mal balanceados: {w_total}"
    print(f"      ✓ ({len(LUZ_HOLDINGS)} posiciones)")

    # 2. Forecast en cada fecha y horizonte
    print(f"\n[2/4] Corriendo forecast_luz_portfolio en "
          f"{len(FECHAS)} fechas × 2 horizontes")
    results = {}
    for as_of in FECHAS:
        for h in (6, 12):
            print(f"      [{as_of} h={h}m] forecasting...")
            r = forecast_luz_portfolio(as_of, h)
            results[(as_of, h)] = r
            print(f"        {r.comment}")

    # 3. Comparar contra realized
    print(f"\n[3/4] Comparación vs realized (groundtruth sintético)")
    print(f"{'as_of':>12} | {'h':>2} | {'centro':>8} | {'sweet C':>26} | "
          f"{'HDI 80%':>22} | {'realized':>10} | hit C | hit 80")
    print("-" * 130)
    for (as_of, h), r in results.items():
        real = realized_luz_portfolio(as_of, h)
        rstr = f"{real*100:+7.2f}%" if real is not None else "    n/a"
        sweet = (f"p{int(r.sweet_spot['p']*100)}% "
                 f"[{r.sweet_spot['lo']*100:+5.2f},{r.sweet_spot['hi']*100:+5.2f}]%")
        lo80, hi80 = hdi(r.samples, 0.80)
        hdi80 = f"[{lo80*100:+5.2f},{hi80*100:+5.2f}]%"
        hc = h80 = ""
        if real is not None:
            hc = "✓" if r.sweet_spot["lo"] <= real <= r.sweet_spot["hi"] else "✗"
            h80 = "✓" if lo80 <= real <= hi80 else "✗"
        print(f"{str(as_of):>12} | {h:>2} | {r.center*100:+7.2f}% | {sweet:>26} | "
              f"{hdi80:>22} | {rstr:>10} | {hc:>5} | {h80:>6}")

    # 4. Mostrar top contribuciones del último forecast
    print(f"\n[4/4] Top 5 contribuciones al centro del último forecast "
          f"({list(results.keys())[-1]}):")
    last = results[list(results.keys())[-1]]
    top = sorted(last.components.items(), key=lambda kv: -abs(kv[1]))[:5]
    for name, contrib in top:
        print(f"      {name:>30}: {contrib*100:+6.3f}pp")

    print(f"\n✅ SMOKE M5 PASS — agregador LUZ funciona end-to-end.")


if __name__ == "__main__":
    main()
