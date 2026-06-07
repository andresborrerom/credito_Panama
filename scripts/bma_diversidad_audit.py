"""Auditoría de DIVERSIDAD real del ensemble BMA Iter 3.

Pregunta: ¿los 5 modelos realmente aportan señales distintas o son redundantes?

Tres medidas de redundancia:
  1. Correlación de centros (medianas) entre modelos → ¿predicen lo mismo?
  2. Correlación de errores (center - realized) → ¿fallan en la misma dirección?
  3. Correlación de CRPS por fecha → ¿fallan en las mismas fechas?

Análisis ablation drop-one:
  Para cada modelo i, recalcular BMA Iter 3 sin i. Medir Δ CRPS, Δ cobertura,
  Δ sharpness. Si quitar un modelo no empeora (o mejora), no aporta.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tasas_mercantil.data.store import load_master_store
from tasas_mercantil.producto_b.nearest_neighbors import (
    build_macro_history, find_neighbors, compute_forward_returns, macro_state_at,
)
from tasas_mercantil.producto_b.bma import (
    ModelForecast, BMAWeights, combine_forecasts, combine_centers,
    _crps_scores_up_to, bma_crps_score_weights, bma_shrinkage,
    apply_temporal_smoothing,
)
from tasas_mercantil.producto_b.diverse_models import model_ar1, model_drift_vol
from tasas_mercantil.producto_b.evaluation import (
    crps_batch, coverage_hdi, sharpness_mean,
)

ETF = "LQD"; HORIZON = 6; WARMUP = 12; ALPHA = 1.0; RHO = 0.95


def hdi(s, mass=0.5):
    s = np.sort(s); n = len(s); w = int(np.ceil(n * mass))
    if w >= n: return float(s[0]), float(s[-1])
    widths = s[w:] - s[:n - w]
    j = int(np.argmin(widths))
    return float(s[j]), float(s[j + w])


def crps_sample_vs_obs(samples, y):
    samples = np.asarray(samples); n = len(samples)
    term1 = np.mean(np.abs(samples - y))
    s = np.sort(samples)
    term2 = (2.0 / (n * n)) * np.sum((2 * np.arange(1, n + 1) - n - 1) * s)
    return float(term1 - 0.5 * term2)


def model_nn(target, macro_hist, etf_ret, K, h):
    nr = find_neighbors(target, macro_hist, K=K, exclude_window_months=7)
    fwd = compute_forward_returns(nr.neighbors["as_of"].tolist(), etf_ret, h, ETF)
    if len(fwd) < 3: return None
    return ModelForecast(model_name=f"NN_K{K}", as_of=target.as_of,
                         horizon_months=h, samples=fwd, center=float(np.median(fwd)))


def model_naive(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of)
    history = sub[sub.index <= cut]["return_log"].dropna()
    if len(history) < 12: return None
    last_year = history.iloc[-12:].values
    rng = np.random.default_rng(int(as_of.toordinal()))
    sims = np.array([rng.choice(last_year, size=h, replace=True).sum() for _ in range(1000)])
    return ModelForecast(model_name="Naive_boot", as_of=as_of,
                         horizon_months=h, samples=sims, center=float(np.median(sims)))


def realized_return(as_of, etf_ret, h):
    sub = etf_ret[etf_ret["label"] == ETF].copy()
    sub["obs_date"] = pd.to_datetime(sub["obs_date"])
    sub = sub.sort_values("obs_date").set_index("obs_date")
    cut = pd.Timestamp(as_of); end = cut + pd.DateOffset(months=h)
    window = sub.loc[(sub.index > cut) & (sub.index <= end), "return_log"].dropna()
    if len(window) < max(1, h - 1): return None
    return float(window.sum())


def build_all():
    store = load_master_store()
    macro_hist = build_macro_history(store, start=date(2003, 1, 1), end=date(2024, 12, 31))
    etf_ret = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")
    test_dates = pd.date_range(date(2020, 1, 31), date(2024, 12, 31), freq="ME").date.tolist()
    fps, reals, ds = [], [], []
    for d in test_dates:
        target = macro_state_at(store, d)
        if target is None: continue
        real = realized_return(d, etf_ret, HORIZON)
        if real is None: continue
        models = {
            "NN_K10":     model_nn(target, macro_hist, etf_ret, K=10, h=HORIZON),
            "NN_K20":     model_nn(target, macro_hist, etf_ret, K=20, h=HORIZON),
            "Naive_boot": model_naive(d, etf_ret, HORIZON),
            "AR1":        model_ar1(d, etf_ret, ETF, HORIZON, n_sims=1000),
            "Drift_vol":  model_drift_vol(d, etf_ret, ETF, HORIZON, n_sims=1000),
        }
        if any(v is None for v in models.values()): continue
        fps.append(models); reals.append(real); ds.append(d)
    return fps, reals, ds


def run_bma(fps, reals, ds, model_subset=None):
    """Walk-forward BMA Iter 3 sobre un subset de modelos. Devuelve métricas."""
    if model_subset is None:
        model_subset = list(fps[0].keys())
    fps_sub = [{m: fd[m] for m in model_subset} for fd in fps]
    eq_w = {m: 1.0 / len(model_subset) for m in model_subset}
    samples_seq, centers_seq = [], []
    w_prev = None
    for t, fd in enumerate(fps_sub):
        if t < WARMUP:
            w_t = eq_w
        else:
            scores = _crps_scores_up_to(fps_sub, reals, t)
            w_data = (bma_crps_score_weights(scores, temperature=50.0)
                      if scores else eq_w)
            w_t = apply_temporal_smoothing(bma_shrinkage(w_data, alpha=ALPHA),
                                            w_prev, rho=RHO)
        bw = BMAWeights(horizon_months=HORIZON, weights=w_t,
                        iteration=3, method="shrinkage+smoothing")
        samples_seq.append(combine_forecasts(fd, bw))
        centers_seq.append(combine_centers(fd, bw))
        w_prev = w_t
    real_arr = np.array(reals)
    hdi_pairs = [hdi(s, 0.5) for s in samples_seq]
    lows = np.array([p[0] for p in hdi_pairs])
    highs = np.array([p[1] for p in hdi_pairs])
    centers = np.array(centers_seq)
    return {
        "CRPS": crps_batch(samples_seq, real_arr),
        "Cobertura HDI50": coverage_hdi(lows, highs, real_arr) * 100,
        "Sharpness": sharpness_mean(lows, highs),
        "MAE": float(np.mean(np.abs(centers - real_arr))),
        "Sesgo": float(np.mean(centers - real_arr)),
    }


def diversity_matrices(fps, reals):
    """Devuelve 3 matrices NxN de correlación entre los N modelos."""
    names = list(fps[0].keys())
    n = len(names)
    centers = pd.DataFrame({m: [fd[m].center for fd in fps] for m in names})
    errors = pd.DataFrame({m: centers[m] - np.array(reals) for m in names})
    crps_per_date = pd.DataFrame({
        m: [crps_sample_vs_obs(fd[m].samples, y) for fd, y in zip(fps, reals)]
        for m in names
    })
    return {
        "centros": centers.corr(),
        "errores": errors.corr(),
        "CRPS_por_fecha": crps_per_date.corr(),
    }


def plot_heatmaps(mats, out_path):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    titles = {
        "centros": "Correlación de CENTROS\n(¿predicen lo mismo?)",
        "errores": "Correlación de ERRORES\n(¿se equivocan igual?)",
        "CRPS_por_fecha": "Correlación de CRPS por fecha\n(¿fallan los mismos meses?)",
    }
    for ax, (name, M) in zip(axes, mats.items()):
        im = ax.imshow(M.values, cmap="RdYlGn_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(M))); ax.set_yticks(range(len(M)))
        ax.set_xticklabels(M.columns, rotation=45, ha="right")
        ax.set_yticklabels(M.index)
        ax.set_title(titles[name], fontsize=10)
        for i in range(len(M)):
            for j in range(len(M)):
                v = M.values[i, j]
                color = "white" if abs(v) > 0.5 else "black"
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        fontsize=9, color=color)
        plt.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("Diversidad real del ensemble (LQD h=6m, 48 fechas)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    fps, reals, ds = build_all()
    print(f"Forecasts construidos: {len(fps)} fechas\n")

    # 1. Matrices de correlación
    mats = diversity_matrices(fps, reals)
    print("=== 1. CORRELACIÓN DE CENTROS (medianas) ===")
    print(mats["centros"].round(3).to_string())
    print("\n=== 2. CORRELACIÓN DE ERRORES (center - realized) ===")
    print(mats["errores"].round(3).to_string())
    print("\n=== 3. CORRELACIÓN DE CRPS POR FECHA ===")
    print(mats["CRPS_por_fecha"].round(3).to_string())

    out_fig = Path("data/external/tasas_mercantil/bma_diversidad.png")
    plot_heatmaps(mats, out_fig)

    # 2. CRPS individuales
    print("\n=== 4. CRPS individual medio (sobre 48 fechas) ===")
    names = list(fps[0].keys())
    indiv = {}
    for m in names:
        crps_m = np.mean([crps_sample_vs_obs(fd[m].samples, y) for fd, y in zip(fps, reals)])
        indiv[m] = crps_m
    indiv_df = pd.Series(indiv).sort_values()
    print(indiv_df.to_string())

    # 3. Ablation drop-one
    print("\n=== 5. ABLATION drop-one (BMA Iter 3) ===")
    baseline = run_bma(fps, reals, ds)
    print(f"  Baseline (5 modelos):  CRPS={baseline['CRPS']:.5f}  "
          f"Cob={baseline['Cobertura HDI50']:.1f}%  "
          f"Sharp={baseline['Sharpness']:.4f}")
    rows = []
    for m in names:
        sub = [x for x in names if x != m]
        r = run_bma(fps, reals, ds, model_subset=sub)
        d_crps = (r["CRPS"] - baseline["CRPS"]) / baseline["CRPS"] * 100
        d_cob = r["Cobertura HDI50"] - baseline["Cobertura HDI50"]
        d_sh = (r["Sharpness"] - baseline["Sharpness"]) / baseline["Sharpness"] * 100
        rows.append({
            "drop": m,
            "CRPS": round(r["CRPS"], 5),
            "Δ CRPS (%)": round(d_crps, 2),
            "Cobertura": round(r["Cobertura HDI50"], 1),
            "Δ Cob (pp)": round(d_cob, 1),
            "Sharpness": round(r["Sharpness"], 4),
            "Δ Sharp (%)": round(d_sh, 1),
        })
    df_abl = pd.DataFrame(rows).sort_values("Δ CRPS (%)", ascending=False)
    print(df_abl.to_string(index=False))
    print("  Δ CRPS POSITIVO = quitar empeora → modelo aporta. NEGATIVO = quitar mejora → no aporta.")

    # 4. Ensemble podado: si algún drop mejora, probar quitar más
    print("\n=== 6. ENSAYO de ensemble podado ===")
    # Identificar modelo que MENOS aporta (más negativo Δ CRPS o más cercano a 0)
    df_abl_sorted = df_abl.sort_values("Δ CRPS (%)")  # más negativo primero
    worst = df_abl_sorted.iloc[0]["drop"]
    print(f"  Modelo que menos aporta: {worst}  (Δ CRPS al quitarlo: "
          f"{df_abl_sorted.iloc[0]['Δ CRPS (%)']:+.2f}%)")
    sub4 = [x for x in names if x != worst]
    r4 = run_bma(fps, reals, ds, model_subset=sub4)
    print(f"  Ensemble 4 modelos (sin {worst}): "
          f"CRPS={r4['CRPS']:.5f}  Cob={r4['Cobertura HDI50']:.1f}%  "
          f"Sharp={r4['Sharpness']:.4f}")

    # Probar también podar 2: el peor + el más correlacionado con los restantes
    err_corr = mats["errores"].drop(worst, axis=0).drop(worst, axis=1).copy()
    vals = err_corr.values.copy()
    np.fill_diagonal(vals, np.nan)
    err_corr = pd.DataFrame(vals, index=err_corr.index, columns=err_corr.columns)
    avg_corr = err_corr.abs().mean(axis=1).sort_values(ascending=False)
    second_worst = avg_corr.index[0]
    print(f"  Modelo más correlacionado en errores con el resto: {second_worst}")
    sub3 = [x for x in sub4 if x != second_worst]
    r3 = run_bma(fps, reals, ds, model_subset=sub3)
    print(f"  Ensemble 3 modelos (sin {worst}, {second_worst}): "
          f"CRPS={r3['CRPS']:.5f}  Cob={r3['Cobertura HDI50']:.1f}%  "
          f"Sharp={r3['Sharpness']:.4f}")

    print("\n=== RESUMEN ===")
    print(f"  5 modelos:  CRPS={baseline['CRPS']:.5f}  Cob={baseline['Cobertura HDI50']:.1f}%")
    print(f"  4 modelos:  CRPS={r4['CRPS']:.5f}  Cob={r4['Cobertura HDI50']:.1f}%")
    print(f"  3 modelos:  CRPS={r3['CRPS']:.5f}  Cob={r3['Cobertura HDI50']:.1f}%")

    print(f"\n[OK] figura → {out_fig}")
    df_abl.to_parquet(Path("data/external/tasas_mercantil/bma_diversidad_ablation.parquet"),
                       index=False)


if __name__ == "__main__":
    main()
