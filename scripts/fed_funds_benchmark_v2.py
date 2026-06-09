"""Sprint 2 v2: dos interpretaciones lado a lado del 'mercado predice Fed'.

INTERPRETACIÓN A — Promedio Fed Funds en próximos 6m:
  predict_A(t)  = US6M.INDX(t)            (yield T-bill 6m hoy)
  realized_A(t) = mean(US3M[t+1..t+6])    (Fed Funds promedio realizado)

  Útil para: ¿qué tasa media voy a pagar/cobrar en los próximos 6 meses?
  (cash management, repricing de portafolios)

INTERPRETACIÓN B — Fed Funds esperado EN el punto t+6m:
  predict_B(t)  = 2·US1Y(t) − US6M(t)     (forward rate implícito 6m-12m)
  realized_B(t) = US3M(t+6m)              (Fed Funds proxy observado en t+6)

  Útil para: ¿dónde va a estar la Fed dentro de 6m exactamente?
  (decisión de duración, timing de hedge)

Resultados: tabla comparativa + figura.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tasas_mercantil.data.ingest_eodhd import fetch_etf_history

CACHE_DIR = Path("data/external/tasas_mercantil")
US3M_CACHE = CACHE_DIR / "us3m_eom.parquet"
US6M_CACHE = CACHE_DIR / "us6m_eom.parquet"
US1Y_CACHE = CACHE_DIR / "us1y_eom.parquet"


def load_yield(ticker, cache_path):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")[df.columns[-1]].sort_index()
    df = fetch_etf_history(ticker, period="d",
                           start=date(2010, 1, 1), end=date(2025, 6, 30))
    df["date"] = pd.to_datetime(df["obs_date"])
    s = df.set_index("date")["close"].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s.index, ticker.replace(".", "_"): s.values})
    out.to_parquet(cache_path, index=False)
    return s


def main():
    print("=== Fed Funds benchmark v2 — dos interpretaciones ===\n")
    us3m = load_yield("US3M.INDX", US3M_CACHE)
    us6m = load_yield("US6M.INDX", US6M_CACHE)
    us1y = load_yield("US1Y.INDX", US1Y_CACHE)
    print(f"US3M: {us3m.index.min().date()} → {us3m.index.max().date()}")
    print(f"US6M: {us6m.index.min().date()} → {us6m.index.max().date()}")
    print(f"US1Y: {us1y.index.min().date()} → {us1y.index.max().date()}\n")

    common = us3m.index.intersection(us6m.index).intersection(us1y.index).sort_values()
    rows = []
    for t in common:
        end_a = t + pd.DateOffset(months=6)
        if end_a > common.max(): break
        # A: promedio
        future_a = us3m.loc[(us3m.index > t) & (us3m.index <= end_a)]
        if len(future_a) < 5: continue
        # B: punto t+6
        idx_b = us3m.index[us3m.index > end_a - pd.DateOffset(days=10)]
        if len(idx_b) == 0: continue
        t_plus_6 = idx_b[0]
        if abs((t_plus_6 - end_a).days) > 35: continue
        realized_b = float(us3m.loc[t_plus_6])

        predict_a = float(us6m.loc[t])
        realized_a = float(future_a.mean())
        predict_b = 2 * float(us1y.loc[t]) - float(us6m.loc[t])  # forward 6m-12m

        rows.append({
            "as_of": t.date(),
            "predict_A_pct": predict_a, "realized_A_pct": realized_a,
            "error_A_pp": predict_a - realized_a,
            "predict_B_pct": predict_b, "realized_B_pct": realized_b,
            "error_B_pp": predict_b - realized_b,
            "fed_now_pct": float(us3m.loc[t]),
            "delta_realized_6m_pp": realized_b - float(us3m.loc[t]),
        })
    df = pd.DataFrame(rows)
    df["abs_err_A_bps"] = (df["error_A_pp"].abs() * 100).round(0)
    df["abs_err_B_bps"] = (df["error_B_pp"].abs() * 100).round(0)
    df["abs_delta_bps"] = (df["delta_realized_6m_pp"].abs() * 100).round(0)

    # Métricas globales lado a lado
    print(f"=== Métricas globales (n={len(df)}) ===")
    print(f"  {'':30}{'Interpretación A':>18}{'Interpretación B':>18}")
    print(f"  {'':30}{'(promedio 6m)':>18}{'(punto t+6m)':>18}")
    print(f"  {'MAE (bps)':30}"
          f"{df['abs_err_A_bps'].mean():>18.1f}{df['abs_err_B_bps'].mean():>18.1f}")
    print(f"  {'Sesgo (bps)':30}"
          f"{df['error_A_pp'].mean()*100:>+18.1f}{df['error_B_pp'].mean()*100:>+18.1f}")
    print(f"  {'RMSE (bps)':30}"
          f"{np.sqrt((df['error_A_pp']**2).mean())*100:>18.1f}"
          f"{np.sqrt((df['error_B_pp']**2).mean())*100:>18.1f}")
    print(f"  {'Vol realizado (bps)':30}"
          f"{df['realized_A_pct'].std()*100:>18.1f}"
          f"{df['realized_B_pct'].std()*100:>18.1f}")

    # Por régimen Fed (mediana de Δ realized 6m)
    med = df["abs_delta_bps"].median()
    df["regimen"] = np.where(df["abs_delta_bps"] <= med, "CALMA", "MOVIMIENTO")
    print(f"\n=== Por régimen Fed (corte = mediana |ΔFed_6m| = {med:.0f} bps) ===")
    print(f"  {'':24}{'MAE_A':>10}{'MAE_B':>10}{'Sesgo_A':>10}{'Sesgo_B':>10}")
    for reg in ["CALMA", "MOVIMIENTO"]:
        sub = df[df["regimen"] == reg]
        print(f"  {reg:>20} (n={len(sub):>3}): "
              f"{sub['abs_err_A_bps'].mean():>9.1f}"
              f"{sub['abs_err_B_bps'].mean():>10.1f}"
              f"{sub['error_A_pp'].mean()*100:>+10.1f}"
              f"{sub['error_B_pp'].mean()*100:>+10.1f}")

    # Por año
    df["ano"] = pd.to_datetime(df["as_of"]).dt.year
    by_year = df.groupby("ano").agg(
        n=("error_A_pp", "size"),
        MAE_A=("abs_err_A_bps", "mean"),
        MAE_B=("abs_err_B_bps", "mean"),
        sesgo_A=("error_A_pp", lambda x: round(x.mean() * 100, 0)),
        sesgo_B=("error_B_pp", lambda x: round(x.mean() * 100, 0)),
    ).round(1)
    print(f"\n=== Por año ===")
    print(by_year.to_string())

    # Foco 2021-2022
    print(f"\n=== Foco 2021-2022 (mes a mes) ===")
    crit = df[(pd.to_datetime(df["as_of"]) >= "2021-01-01") &
              (pd.to_datetime(df["as_of"]) <= "2022-12-31")].copy()
    cols = ["as_of", "fed_now_pct", "predict_A_pct", "realized_A_pct",
            "error_A_pp", "predict_B_pct", "realized_B_pct", "error_B_pp"]
    for c in cols[1:]:
        crit[c] = crit[c].round(2)
    print(crit[cols].to_string(index=False))

    # Plot
    fig, axes = plt.subplots(3, 1, figsize=(13, 11))
    dts = pd.to_datetime(df["as_of"])

    ax = axes[0]
    ax.plot(dts, df["predict_A_pct"], color="#3498db", lw=1.4,
            label="A: Mercado predice promedio 6m (US6M)")
    ax.plot(dts, df["realized_A_pct"], color="#c0392b", lw=1.4,
            label="A: Realizado promedio (US3M[t+1..t+6])")
    ax.fill_between(dts, df["predict_A_pct"], df["realized_A_pct"],
                    color="grey", alpha=0.20)
    ax.set_ylabel("Tasa (%)"); ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    mae_a = df["abs_err_A_bps"].mean(); s_a = df["error_A_pp"].mean() * 100
    ax.set_title(f"Interpretación A — promedio 6m  (MAE {mae_a:.0f}bps, sesgo {s_a:+.0f}bps)")

    ax = axes[1]
    ax.plot(dts, df["predict_B_pct"], color="#9b59b6", lw=1.4,
            label="B: Mercado predice punto t+6 (forward 6m-12m)")
    ax.plot(dts, df["realized_B_pct"], color="#c0392b", lw=1.4,
            label="B: Realizado en t+6 (US3M(t+6))")
    ax.fill_between(dts, df["predict_B_pct"], df["realized_B_pct"],
                    color="grey", alpha=0.20)
    ax.set_ylabel("Tasa (%)"); ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    mae_b = df["abs_err_B_bps"].mean(); s_b = df["error_B_pp"].mean() * 100
    ax.set_title(f"Interpretación B — punto t+6m  (MAE {mae_b:.0f}bps, sesgo {s_b:+.0f}bps)")

    ax = axes[2]
    width = 11; off = pd.Timedelta(days=width / 2)
    ax.bar(dts - off, df["error_A_pp"] * 100, width=width, color="#3498db",
           alpha=0.7, label="Error A", edgecolor="black", linewidth=0.3)
    ax.bar(dts + off, df["error_B_pp"] * 100, width=width, color="#9b59b6",
           alpha=0.7, label="Error B", edgecolor="black", linewidth=0.3)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_ylabel("Error mercado − realizado (bps)")
    ax.set_title("Errores comparados (negativo = mercado subestimó subidas)")
    ax.legend(loc="upper right"); ax.grid(axis="y", alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-01-01"), pd.Timestamp("2022-12-31"),
               color="orange", alpha=0.10)

    fig.tight_layout()
    out = CACHE_DIR / "fed_funds_benchmark_v2.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    df.to_parquet(CACHE_DIR / "fed_funds_benchmark_v2.parquet", index=False)
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
