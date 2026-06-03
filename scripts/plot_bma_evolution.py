"""Reconstruye la evolución de las métricas de éxito a lo largo de las
iteraciones del BMA y produce tabla + figura.

Métricas de éxito (definidas en iteraciones previas):
  1. CRPS ≤ mejor individual (debe ganarle al benchmark).
  2. Cobertura HDI50 ≈ 50% (calibración honesta, target ±5pp).
  3. Sharpness (ancho HDI50 medio) bajo.
  4. |Sesgo| pequeño.
  5. Turnover bajo (introducido en Iter 3).

NOTA: cada iteración corrió sobre rangos de fechas distintos (n distinto),
por lo que la comparación absoluta entre iteraciones es ilustrativa.
La comparación rigurosa es dentro de cada experimento (Δ vs benchmark de
esa misma corrida).
"""
from __future__ import annotations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT_FIG = Path("data/external/tasas_mercantil/bma_evolution.png")
OUT_TABLE = Path("data/external/tasas_mercantil/bma_evolution.parquet")


# ===========================================================================
# Tabla unificada de la evolución (extraído de los parquets de cada iter)
# ===========================================================================
ROWS = [
    # Iter 1 (3 modelos: NN_K10, NN_K20, Naive) — n=24 fechas
    {"stage": "Iter 1 — bench NN_K20", "kind": "benchmark",
     "n": 24, "CRPS": 0.02540, "Cobertura": 41.7, "Sharpness": 0.0581,
     "Sesgo": -0.0102, "MAE": 0.0331, "Turnover": np.nan,
     "verdict": "—"},
    {"stage": "Iter 1 — BMA equal (3 modelos hermanos)", "kind": "bma",
     "n": 24, "CRPS": 0.02631, "Cobertura": 41.7, "Sharpness": 0.0591,
     "Sesgo": -0.0016, "MAE": 0.0352, "Turnover": 0.0,
     "verdict": "FAIL: +3.6% peor que benchmark"},

    # Iter 2 (3 modelos hermanos NN_K*) — n=60 fechas
    {"stage": "Iter 2 — BMA equal (3 NN_K)", "kind": "benchmark",
     "n": 60, "CRPS": 0.03668, "Cobertura": 41.7, "Sharpness": 0.0586,
     "Sesgo": -0.0135, "MAE": 0.0457, "Turnover": 0.0,
     "verdict": "—"},
    {"stage": "Iter 2 — BMA shrink α=0.60", "kind": "bma",
     "n": 60, "CRPS": 0.03659, "Cobertura": 46.7, "Sharpness": 0.0587,
     "Sesgo": -0.0135, "MAE": 0.0455, "Turnover": np.nan,
     "verdict": "MARGINAL: −0.25%, pesos casi-equal"},

    # Iter 2 ext (5 modelos diversos: + AR1 + Drift_vol) — n=48 fechas
    {"stage": "Iter 2 ext — bench NN_K20", "kind": "benchmark",
     "n": 48, "CRPS": 0.04205, "Cobertura": 37.5, "Sharpness": 0.0553,
     "Sesgo": -0.0273, "MAE": 0.0503, "Turnover": np.nan,
     "verdict": "—"},
    {"stage": "Iter 2 ext — BMA equal (5 div)", "kind": "bma",
     "n": 48, "CRPS": 0.04134, "Cobertura": 52.1, "Sharpness": 0.0692,
     "Sesgo": -0.0155, "MAE": 0.0530, "Turnover": 0.0,
     "verdict": "PASS: −1.7%, cobertura perfecta"},
    {"stage": "Iter 2 ext — BMA shrink α*=1.0", "kind": "bma",
     "n": 48, "CRPS": 0.04107, "Cobertura": 52.1, "Sharpness": 0.0697,
     "Sesgo": -0.0140, "MAE": 0.0523, "Turnover": 0.0127,
     "verdict": "PASS: −2.3% vs bench"},

    # Iter 3 (5 modelos + smoothing ρ*=0.95) — n=48 fechas
    {"stage": "Iter 3 — + smoothing ρ*=0.95", "kind": "bma",
     "n": 48, "CRPS": 0.04148, "Cobertura": 47.9, "Sharpness": 0.0703,
     "Sesgo": -0.0146, "MAE": 0.0531, "Turnover": 0.0038,
     "verdict": "PASS: −1.4% + turnover −70%"},
]


def build_table():
    df = pd.DataFrame(ROWS)
    # Δ CRPS vs benchmark dentro de cada experimento (mismo n)
    bench_by_n = (
        df[df["kind"] == "benchmark"].groupby("n")["CRPS"].first().to_dict()
    )
    df["bench_CRPS"] = df["n"].map(bench_by_n)
    df["Δ CRPS vs bench (%)"] = (
        (df["CRPS"] - df["bench_CRPS"]) / df["bench_CRPS"] * 100
    ).round(2)
    df["|Cob − 50|"] = (df["Cobertura"] - 50).abs().round(1)
    return df


def plot_evolution(df: pd.DataFrame):
    bma = df[df["kind"] == "bma"].reset_index(drop=True).copy()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    x = np.arange(len(bma))
    labels = [
        "Iter 1\n(3 hermanos)",
        "Iter 2\n(3 hermanos, α*)",
        "Iter 2 ext\n(5 div, equal)",
        "Iter 2 ext\n(5 div, α*=1)",
        "Iter 3\n(5 div, ρ*=.95)",
    ]
    colors = ["#c0392b", "#e67e22", "#f1c40f", "#27ae60", "#2980b9"]
    verdict_color = {"FAIL": "#c0392b", "MARGINAL": "#e67e22", "PASS": "#27ae60"}

    # Panel 1: Δ CRPS vs benchmark
    ax = axes[0, 0]
    deltas = bma["Δ CRPS vs bench (%)"].values
    bar_colors = ["#27ae60" if d < 0 else "#c0392b" for d in deltas]
    ax.bar(x, deltas, color=bar_colors, edgecolor="black")
    ax.axhline(0, color="black", lw=1)
    ax.axhline(-5, color="grey", lw=0.8, ls="--", alpha=0.7, label="gate −5%")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Δ CRPS vs mejor individual (%)\n(negativo = mejor)")
    ax.set_title("1. Predictive skill (vs benchmark)")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(axis="y", alpha=0.3)
    for i, d in enumerate(deltas):
        ax.text(i, d + (0.15 if d >= 0 else -0.4), f"{d:+.2f}%",
                ha="center", fontsize=8, fontweight="bold")

    # Panel 2: Cobertura HDI50 vs target 50%
    ax = axes[0, 1]
    cobs = bma["Cobertura"].values
    bar_colors = ["#27ae60" if abs(c - 50) <= 5 else "#e67e22"
                  if abs(c - 50) <= 10 else "#c0392b" for c in cobs]
    ax.bar(x, cobs, color=bar_colors, edgecolor="black")
    ax.axhline(50, color="black", lw=1.5, label="target 50%")
    ax.axhspan(45, 55, color="grey", alpha=0.15, label="banda ±5pp")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Cobertura HDI 50% (%)")
    ax.set_title("2. Calibración (target 50%)")
    ax.set_ylim(35, 60)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    for i, c in enumerate(cobs):
        ax.text(i, c + 0.5, f"{c:.1f}", ha="center", fontsize=8, fontweight="bold")

    # Panel 3: Sharpness (ancho HDI50)
    ax = axes[1, 0]
    sharps = bma["Sharpness"].values
    ax.plot(x, sharps, "o-", color="#2c3e50", markersize=8, lw=2)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Sharpness (ancho HDI50 medio)")
    ax.set_title("3. Sharpness (intervalos compactos)")
    ax.grid(alpha=0.3)
    for i, s in enumerate(sharps):
        ax.text(i, s + 0.001, f"{s:.4f}", ha="center", fontsize=8)

    # Panel 4: Turnover (pesos estables)
    ax = axes[1, 1]
    tos = bma["Turnover"].values
    ax.bar(x, tos, color="#8e44ad", edgecolor="black")
    ax.axhline(0.02, color="grey", lw=0.8, ls="--", alpha=0.7,
               label="gate ≤ 0.02")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Turnover medio ‖Δw‖₁/2 por mes")
    ax.set_title("4. Estabilidad de pesos (introducido Iter 3)")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    for i, t in enumerate(tos):
        ax.text(i, t + 0.0005, f"{t:.4f}", ha="center", fontsize=8)

    fig.suptitle(
        "BMA — Evolución de métricas de éxito por iteración (LQD, h=6m)",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT_FIG, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    df = build_table()
    cols_show = [
        "stage", "n", "CRPS", "Δ CRPS vs bench (%)",
        "Cobertura", "|Cob − 50|", "Sharpness",
        "Sesgo", "Turnover", "verdict",
    ]
    print("=== Evolución BMA — tabla unificada (LQD, h=6m) ===\n")
    print(df[cols_show].to_string(index=False))

    df.to_parquet(OUT_TABLE, index=False)
    plot_evolution(df)
    print(f"\n[OK] tabla → {OUT_TABLE}")
    print(f"[OK] figura → {OUT_FIG}")


if __name__ == "__main__":
    main()
