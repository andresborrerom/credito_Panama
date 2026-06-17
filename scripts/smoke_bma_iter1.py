"""Smoke test BMA Iter 1: equal weights sobre 3 modelos para LQD horizonte 6m.

Modelos:
  M1: NN baseline K=10
  M2: NN baseline K=20
  M3: Naive carry (último retorno mensual × horizonte)

Test dates: 2023-01-31 a 2024-12-31 (24 meses), realizado disponible hasta jun-2025.

Gate Iter 1: BMA-equal debe ser ≥ que el peor modelo individual (validar arquitectura).
Si BMA-equal ≥ mediana de modelos individuales → pasa; si ≥ mejor individual → óptimo.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.producto_b.nearest_neighbors import (
    build_macro_history,
    find_neighbors,
    compute_forward_returns,
    macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    ModelForecast,
    bma_equal_weights,
    combine_forecasts,
    combine_centers,
    walk_forward_bma_equal,
)
from tasas_mercantil.producto_b.evaluation import (
    crps_batch,
    coverage_hdi,
    sharpness_mean,
    skill_score,
    bias,
)


ETF_LABEL = "LQD"
HORIZON = 6
TEST_START = date(2023, 1, 31)
TEST_END = date(2024, 12, 31)


def _hdi(samples: np.ndarray, mass: float = 0.50) -> tuple[float, float]:
    s = np.sort(samples)
    n = len(s)
    w = int(np.ceil(n * mass))
    if w >= n:
        return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def model_nn(target_state, macro_hist, etf_ret, K, h, exclude_w=7):
    nr = find_neighbors(target_state, macro_hist, K=K, exclude_window_months=exclude_w)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(), etf_ret, h, ETF_LABEL)
    if len(fwd) < 3:
        return None
    return ModelForecast(
        model_name=f"NN_K{K}",
        as_of=target_state.as_of,
        horizon_months=h,
        samples=fwd,
        center=float(np.median(fwd)),
    )


def model_naive(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub[sub.index <= cut]["return_log"].dropna()
    if len(history) < 12:
        return None
    # Bootstrap del último año, escala = h meses
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=h, replace=True).sum() for _ in range(500)])
    return ModelForecast(
        model_name="Naive_boot",
        as_of=as_of,
        horizon_months=h,
        samples=sims,
        center=float(np.median(sims)),
    )


def realized_return(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF_LABEL].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    end = cut + pd.DateOffset(months=h)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    if len(window) < max(1, h - 1):
        return None
    return float(window.sum())


def evaluate_per_model_table(model_name, forecasts, realized):
    samples_list = [f.samples for f in forecasts]
    centers = np.array([f.center for f in forecasts])
    real = np.array(realized)
    hdi_pairs = [_hdi(f.samples, 0.50) for f in forecasts]
    lows = np.array([p[0] for p in hdi_pairs])
    highs = np.array([p[1] for p in hdi_pairs])
    crps = crps_batch(samples_list, real)
    cov = coverage_hdi(lows, highs, real)
    sharp = sharpness_mean(lows, highs)
    b = bias(centers, real)
    naive_pred = np.zeros_like(real)  # carry = 0 baseline trivial
    skill = skill_score(centers, real, naive_pred) if not np.all(naive_pred == centers) else float("nan")
    return {
        "model": model_name,
        "n": len(real),
        "CRPS": round(crps, 5),
        "Cobertura HDI50 (%)": round(cov * 100, 1),
        "Sharpness": round(sharp, 4),
        "Sesgo": round(b, 4),
        "MAE_vs_zero": round(np.mean(np.abs(centers - real)), 4),
    }


def main():
    print(f"=== Smoke test BMA Iter 1 — {ETF_LABEL} h={HORIZON} ===\n")
    print("Cargando store...")
    store = load_master_store()
    print("Construyendo macro history...")
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=TEST_END)
    print(f"  macro_hist: {len(macro_hist)} meses ({macro_hist['as_of'].min()} → {macro_hist['as_of'].max()})")
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")

    test_dates = pd.date_range(TEST_START, TEST_END, freq="ME").date.tolist()
    print(f"  test_dates: {len(test_dates)} ({test_dates[0]} → {test_dates[-1]})\n")

    forecasts_per_date = []  # list[dict[model_name → ModelForecast]]
    realized_list = []
    skipped = 0
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None:
            skipped += 1; continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None:
            skipped += 1; continue
        m1 = model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON)
        m2 = model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON)
        m3 = model_naive(d, etf_ret, HORIZON)
        if any(m is None for m in [m1, m2, m3]):
            skipped += 1; continue
        forecasts_per_date.append({"NN_K10": m1, "NN_K20": m2, "Naive_boot": m3})
        realized_list.append(real)

    print(f"Forecasts construidos: {len(forecasts_per_date)} (saltados {skipped})\n")

    if not forecasts_per_date:
        print("[FAIL] No hay forecasts.")
        return

    # Evaluar cada modelo individual
    print("=== Métricas por modelo individual ===")
    rows = []
    for m_name in ["NN_K10", "NN_K20", "Naive_boot"]:
        forecasts = [d[m_name] for d in forecasts_per_date]
        rows.append(evaluate_per_model_table(m_name, forecasts, realized_list))
    df_models = pd.DataFrame(rows)
    print(df_models.to_string(index=False))

    # BMA equal weights
    print("\n=== BMA Iter 1 (equal weights 1/3) ===")
    df_bma = walk_forward_bma_equal(forecasts_per_date, realized_list)
    print(df_bma[["as_of", "real", "ensemble_center", "ensemble_hdi_low",
                  "ensemble_hdi_high", "in_hdi"]].round(4).to_string(index=False))

    # Métricas globales del ensemble
    samples_ens = []
    centers_ens = []
    lows_ens = []
    highs_ens = []
    weights = bma_equal_weights(["NN_K10", "NN_K20", "Naive_boot"], HORIZON)
    for fdict in forecasts_per_date:
        s = combine_forecasts(fdict, weights)
        samples_ens.append(s)
        centers_ens.append(combine_centers(fdict, weights))
        lo, hi = _hdi(s, 0.50)
        lows_ens.append(lo); highs_ens.append(hi)
    centers_ens = np.array(centers_ens)
    lows_ens = np.array(lows_ens); highs_ens = np.array(highs_ens)
    real_arr = np.array(realized_list)

    ens_row = {
        "model": "BMA_equal",
        "n": len(real_arr),
        "CRPS": round(crps_batch(samples_ens, real_arr), 5),
        "Cobertura HDI50 (%)": round(coverage_hdi(lows_ens, highs_ens, real_arr) * 100, 1),
        "Sharpness": round(sharpness_mean(lows_ens, highs_ens), 4),
        "Sesgo": round(bias(centers_ens, real_arr), 4),
        "MAE_vs_zero": round(np.mean(np.abs(centers_ens - real_arr)), 4),
    }
    df_all = pd.concat([df_models, pd.DataFrame([ens_row])], ignore_index=True)
    print("\n=== Comparación final ===")
    print(df_all.to_string(index=False))

    # Gate Iter 1
    crps_models = df_models["CRPS"].values
    crps_bma = ens_row["CRPS"]
    best = float(np.min(crps_models)); worst = float(np.max(crps_models)); med = float(np.median(crps_models))
    print(f"\n=== Gate Iter 1 ===")
    print(f"  CRPS modelos: best={best:.5f}, median={med:.5f}, worst={worst:.5f}")
    print(f"  CRPS BMA-equal: {crps_bma:.5f}")
    if crps_bma <= worst:
        print(f"  [PASS] BMA ≤ peor individual.")
    else:
        print(f"  [FAIL] BMA peor que el peor individual.")
    if crps_bma <= med:
        print(f"  [PASS+] BMA ≤ mediana de modelos.")
    if crps_bma <= best:
        print(f"  [PASS++] BMA ≤ mejor individual (diversificación neta).")
    else:
        print(f"  Gap vs mejor: +{(crps_bma - best)*100:.2f} bps de CRPS.")

    # Guardar
    out = Path("data/external/tasas_mercantil/bma_iter1_smoke.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df_all.to_parquet(out, index=False)
    print(f"\n[OK] guardado: {out}")


if __name__ == "__main__":
    main()
