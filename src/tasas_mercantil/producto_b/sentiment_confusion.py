"""Análisis de matriz de confusión: ¿sentiment es detector ASIMÉTRICO de meses negativos?

Hipótesis del owner: sentiment puede ser útil para detectar escenarios negativos
aunque sea débil para predecir retorno medio.

Output: parquet con TP/FP/TN/FN + precision/recall/specificity/F1/lift por
(ETF objetivo, sentiment_symbol, threshold).
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def confusion_metrics(signal_neg: np.ndarray, real_neg: np.ndarray) -> dict:
    """Calcula matriz + métricas. signal_neg = alerta del modelo. real_neg = realizado negativo."""
    TP = int(np.sum(signal_neg & real_neg))
    FP = int(np.sum(signal_neg & ~real_neg))
    TN = int(np.sum(~signal_neg & ~real_neg))
    FN = int(np.sum(~signal_neg & real_neg))
    n = TP + FP + TN + FN
    precision = TP / (TP + FP) if (TP + FP) > 0 else float("nan")
    recall = TP / (TP + FN) if (TP + FN) > 0 else float("nan")
    specificity = TN / (TN + FP) if (TN + FP) > 0 else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else float("nan"))
    neg_rate = (TP + FN) / n if n > 0 else 0
    lift = precision / neg_rate if neg_rate > 0 else float("nan")
    return {
        "n": n, "TP": TP, "FP": FP, "TN": TN, "FN": FN,
        "precision": precision, "recall": recall,
        "specificity": specificity, "f1": f1,
        "neg_rate": neg_rate, "random_precision": neg_rate,
        "lift_vs_random": lift,
    }


def analyze_pair(
    etf_label: str,
    sentiment_symbol: str,
    sent_pivot: pd.DataFrame,
    ret_monthly: pd.DataFrame,
    neg_quantile: float = 0.30,
    sent_thresholds: tuple = (0.3, 0.4, 0.5, 0.6, 0.7),
) -> pd.DataFrame | None:
    """Para un (ETF, sentiment), analiza varios thresholds.

    Output: DataFrame con métricas por threshold.
    """
    if sentiment_symbol not in sent_pivot.columns:
        return None
    rets = ret_monthly[ret_monthly["label"] == etf_label].set_index("yyyymm")["return_log"]
    sigs = sent_pivot[sentiment_symbol].dropna()
    # Sentiment en t vs retorno en t+1 (predicción adelantada)
    aligned = pd.concat([
        sigs.rename("sent_t"),
        rets.shift(-1).rename("ret_next"),
    ], axis=1, sort=True).dropna()
    if len(aligned) < 12:
        return None
    neg_cutoff = aligned["ret_next"].quantile(neg_quantile)
    real_neg = (aligned["ret_next"] <= neg_cutoff).values
    rows = []
    for th in sent_thresholds:
        signal_neg = (aligned["sent_t"] <= th).values
        cm = confusion_metrics(signal_neg, real_neg)
        cm["etf"] = etf_label
        cm["sentiment_symbol"] = sentiment_symbol
        cm["threshold"] = th
        rows.append(cm)
    return pd.DataFrame(rows)


def main():
    sent = pd.read_parquet("data/external/tasas_mercantil/news_sentiment_monthly.parquet")
    sent["yyyymm"] = pd.to_datetime(sent["yyyymm"])
    etfs = pd.read_parquet("data/external/tasas_mercantil/etfs_producto_b.parquet")
    etfs["yyyymm"] = pd.to_datetime(etfs["obs_date"]).dt.to_period("M").dt.to_timestamp()
    ret_monthly = etfs.groupby(["label", "yyyymm"])["return_log"].sum().reset_index()
    sent_pivot = sent.pivot_table(index="yyyymm", columns="symbol", values="sentiment_mean")

    mapping = {
        "ACWI": "SPY.US", "AGG": "LQD.US", "BIL": "LQD.US",
        "EMB": "EMB.US", "GHYG": "HYG.US", "IGLA": "TLT.US", "LQD": "LQD.US",
    }
    all_rows = []
    for etf, sym in mapping.items():
        df = analyze_pair(etf, sym, sent_pivot, ret_monthly)
        if df is not None:
            all_rows.append(df)
    if not all_rows:
        print("Sin data")
        return
    out = pd.concat(all_rows, ignore_index=True)
    out_path = Path("data/external/tasas_mercantil/sentiment_confusion_matrix.parquet")
    out.to_parquet(out_path, index=False)
    print(f"[OK] {out_path}  ({len(out):,} filas)")

    # Reporte: top combos
    print("\n=== Pares (ETF, sentiment) con lift > 1.2x ===")
    top = out[out["lift_vs_random"] > 1.2].sort_values("lift_vs_random", ascending=False)
    if top.empty:
        print("(ninguno)")
    else:
        print(top[["etf", "sentiment_symbol", "threshold", "n", "precision",
                   "recall", "specificity", "lift_vs_random"]].round(2).to_string(index=False))

    print("\n=== Pares con lift < 1.0 (sentiment CONTRAPRODUCENTE) ===")
    bad = out[out["lift_vs_random"] < 1.0].sort_values("lift_vs_random")
    if not bad.empty:
        print(bad[["etf", "sentiment_symbol", "threshold", "n",
                   "lift_vs_random"]].round(2).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
