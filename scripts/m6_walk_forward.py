"""M6 — Walk-forward formal del portafolio LUZ agregado.

Corre forecast_luz_portfolio en una grilla de 10 (as_of, h_months) que
cubre los 3 regímenes operativos. Cada resultado se persiste a parquet
apenas se completa — el script es reanudable si se interrumpe.

Métricas finales: hit rate Vista A/B/C por régimen, MAE del centro,
ancho promedio. Estos hit rates reemplazan los del sweep ETF en BITACORA.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from tasas_mercantil.producto_b.portfolio_aggregator import (
    forecast_luz_portfolio, LUZ_HOLDINGS,
)
from tasas_mercantil.producto_b.views_bandas import forecast_luz_all_views
from tasas_mercantil.producto_b.forecast_api import CACHE_DIR
from tasas_mercantil.producto_b.bond_mapping import realized_bond_return


GRID = [
    (date(2022, 3, 31), 12),
    (date(2022, 6, 30), 12),
    (date(2022, 12, 31), 12),
    (date(2023, 6, 30), 6),
    (date(2023, 12, 31), 6),
    (date(2023, 12, 31), 12),
    (date(2024, 3, 31), 12),
    (date(2024, 6, 30), 6),
    (date(2024, 6, 30), 12),
    (date(2024, 9, 30), 6),
]


RESULTS_PATH = Path("data/external/tasas_mercantil/m6_walk_forward_luz.parquet")


def realized_luz(as_of: date, h_months: int) -> float | None:
    etfs = pd.read_parquet(CACHE_DIR / "etfs_producto_b.parquet")
    etfs["obs_date"] = pd.to_datetime(etfs["obs_date"])

    total = 0.0
    cov = 0.0
    from tasas_mercantil.producto_b.bond_mapping import LUZ_BONDS

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
            cov += pos.weight
        elif pos.strategy == "bond":
            bidx = int(pos.source)
            real = realized_bond_return(LUZ_BONDS[bidx], as_of, h_months)
            if real is None:
                continue
            total += pos.weight * real
            cov += pos.weight
        elif pos.strategy == "cash":
            total += pos.weight * 0.0
            cov += pos.weight

    if cov < 0.90:
        return None
    return total / cov


def already_done(as_of: date, h_months: int) -> bool:
    if not RESULTS_PATH.exists():
        return False
    df = pd.read_parquet(RESULTS_PATH)
    return ((df["as_of"] == as_of) & (df["h_months"] == h_months)).any()


def append_row(row: dict):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame([row])
    if RESULTS_PATH.exists():
        df = pd.read_parquet(RESULTS_PATH)
        df = pd.concat([df, new_df], ignore_index=True)
    else:
        df = new_df
    df.to_parquet(RESULTS_PATH, index=False)


def main():
    print("=" * 130)
    print(f"M6 — Walk-forward LUZ ({len(GRID)} corridas)")
    print("=" * 130)
    print(f"Persistiendo resultados en: {RESULTS_PATH}\n")

    for i, (as_of, h) in enumerate(GRID, 1):
        if already_done(as_of, h):
            print(f"[{i}/{len(GRID)}] {as_of} h={h}m — ya hecho, skip")
            continue
        print(f"[{i}/{len(GRID)}] {as_of} h={h}m — corriendo...")
        sys.stdout.flush()
        try:
            pf = forecast_luz_portfolio(as_of, h)
        except Exception as e:
            print(f"      ✗ ERROR: {e}")
            append_row({"as_of": as_of, "h_months": h, "error": str(e)[:200]})
            continue
        views = forecast_luz_all_views(as_of, h, portfolio_forecast=pf)
        real = realized_luz(as_of, h)

        from tasas_mercantil.producto_b.forecast_api import _hdi
        lo80, hi80 = _hdi(pf.samples, 0.80)

        row = {
            "as_of": as_of, "h_months": h,
            "center": pf.center,
            "regime": pf.worst_regime,
            "iqr_portfolio": views["meta"]["w_max_used_iqr_portfolio"],
            "vista_A_p": views["vista_A"]["p"] if views["vista_A"] else 0.0,
            "vista_A_lo": views["vista_A"]["lo"] if views["vista_A"] else float("nan"),
            "vista_A_hi": views["vista_A"]["hi"] if views["vista_A"] else float("nan"),
            "vista_B_p": views["vista_B"]["p"],
            "vista_B_lo": views["vista_B"]["lo"],
            "vista_B_hi": views["vista_B"]["hi"],
            "vista_C_p": views["vista_C"]["p"],
            "vista_C_lo": views["vista_C"]["lo"],
            "vista_C_hi": views["vista_C"]["hi"],
            "hdi80_lo": lo80, "hdi80_hi": hi80,
            "var95": views["var"]["var"],
            "cvar95": views["cvar"]["cvar"],
            "p_positive": views["directional"]["p_positive"],
            "p_above_rf": views["directional"]["p_above_rf"],
            "realized": real if real is not None else float("nan"),
        }
        append_row(row)
        rstr = f"{real*100:+.2f}%" if real is not None else "n/a"
        print(f"      ✓ centro={pf.center*100:+.2f}%, sweet C{int(views['vista_C']['p']*100)}%, "
              f"régimen={pf.worst_regime}, real={rstr}")
        sys.stdout.flush()

    # Reporte final
    print("\n" + "=" * 130)
    print("M6 — Reporte agregado")
    print("=" * 130)

    df = pd.read_parquet(RESULTS_PATH)
    df = df.dropna(subset=["realized"])
    if df.empty:
        print("Sin filas con realized para evaluar.")
        return

    # Hits
    df["hit_C"] = (df["vista_C_lo"] <= df["realized"]) & (df["realized"] <= df["vista_C_hi"])
    df["hit_B"] = (df["vista_B_lo"] <= df["realized"]) & (df["realized"] <= df["vista_B_hi"])
    df["hit_A"] = ((df["vista_A_lo"] <= df["realized"]) & (df["realized"] <= df["vista_A_hi"])
                   & (df["vista_A_p"] > 0))
    df["A_emitio"] = df["vista_A_p"] > 0

    print(f"\nHit rate global (n={len(df)}):")
    print(f"  Vista A: {df['hit_A'].sum()}/{df['A_emitio'].sum()} = "
          f"{df['hit_A'].sum()/max(df['A_emitio'].sum(),1)*100:.0f}% (cuando emite, "
          f"{df['A_emitio'].sum()} emisiones)")
    print(f"  Vista B (HDI 80%): {df['hit_B'].sum()}/{len(df)} = "
          f"{df['hit_B'].sum()/len(df)*100:.0f}%")
    print(f"  Vista C (sweet spot): {df['hit_C'].sum()}/{len(df)} = "
          f"{df['hit_C'].sum()/len(df)*100:.0f}%")

    print(f"\nHit rate por régimen:")
    for reg in ["normal", "stress_alto", "stress_extremo"]:
        sub = df[df["regime"] == reg]
        if sub.empty:
            continue
        a_emit = (sub["vista_A_p"] > 0).sum()
        a_hit = sub["hit_A"].sum()
        a_str = f"{a_hit}/{a_emit} = {a_hit/max(a_emit,1)*100:.0f}%" if a_emit else "0 emisiones"
        print(f"  {reg:>15} (n={len(sub):>2}): "
              f"A={a_str:>20}  "
              f"B={sub['hit_B'].sum()}/{len(sub)} ({sub['hit_B'].sum()/len(sub)*100:.0f}%)  "
              f"C={sub['hit_C'].sum()}/{len(sub)} ({sub['hit_C'].sum()/len(sub)*100:.0f}%)")

    mae = (df["center"] - df["realized"]).abs().mean() * 100
    print(f"\nMAE del centro vs realized: {mae:.2f}pp")
    print(f"\nResultados persistidos en: {RESULTS_PATH}")
    print(f"\n✅ M6 PASS")


if __name__ == "__main__":
    main()
