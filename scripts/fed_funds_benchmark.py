"""Sprint 2: ¿Qué tan bien predice el MERCADO al Fed Funds?

Pregunta: ¿qué tan calibrada está la 'predicción' implícita del mercado vía
US6M Treasury yield (hoy) sobre el Fed Funds realizado en los 6 meses siguientes?

US6M.INDX de hoy ≈ promedio expected del Fed Funds en próximos 6m
                   (más pequeño term premium, ~5-15bps).
Realizado prom (t+1, t+6) = US3M.INDX promediado en esos 6m
                            (US3M ≈ Fed Funds + 5-10bps spread).
(NOTA: FRED rate-limited en sandbox, usamos EODHD US3M/US6M como proxies
de Fed Funds. Idealmente sería EFFR vs DGS6MO directos.)

Métricas:
  MAE  : mean(|predict − realized|)
  Sesgo: mean(predict − realized)  (positivo = mercado descontó demasiada subida)
  RMSE
  Vol  : std del realized (para contexto)

Por régimen Fed (cortando por mediana de |Δ EFFR_6m|):
  CALMA   : meses donde Fed se movió poco
  TIGHTENING/EASING: meses donde Fed se movió fuerte

Este es el BASELINE A BATIR para cualquier modelo futuro de Fed/curva.
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


def load_or_fetch(ticker, cache_path,
                   start=date(2010, 1, 1), end=date(2025, 6, 30)):
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df.set_index("date")[df.columns[-1]]
    print(f"Descargando EODHD {ticker} ...")
    df = fetch_etf_history(ticker, period="d", start=start, end=end)
    df["date"] = pd.to_datetime(df["obs_date"])
    s_eom = df.set_index("date")["close"].resample("ME").last().dropna()
    out = pd.DataFrame({"date": s_eom.index, ticker.replace(".", "_"): s_eom.values})
    out.to_parquet(cache_path, index=False)
    return s_eom


def main():
    print("=== Sprint 2: ¿Qué tan bien predice el mercado al Fed Funds? ===\n")
    effr = load_or_fetch("US3M.INDX", US3M_CACHE)
    dgs6mo = load_or_fetch("US6M.INDX", US6M_CACHE)
    print(f"US3M (proxy Fed Funds realizado): {effr.index.min().date()} → {effr.index.max().date()}")
    print(f"US6M (proxy mercado descuenta):   {dgs6mo.index.min().date()} → {dgs6mo.index.max().date()}\n")

    # Para cada mes t: predict = DGS6MO(t); realized = promedio EFFR(t+1..t+6)
    common = effr.index.intersection(dgs6mo.index).sort_values()
    rows = []
    for t in common:
        if t + pd.DateOffset(months=6) > common.max(): break
        predict = float(dgs6mo.loc[t])
        future = effr.loc[(effr.index > t) &
                          (effr.index <= t + pd.DateOffset(months=6))]
        if len(future) < 5: continue
        realized = float(future.mean())
        delta_effr = float(future.iloc[-1] - effr.loc[t])
        rows.append({
            "as_of": t.date(), "predict_pct": predict, "realized_pct": realized,
            "error_pp": predict - realized,
            "fed_actual_now_pct": float(effr.loc[t]),
            "delta_effr_6m_pp": delta_effr,
        })
    df = pd.DataFrame(rows)
    df["abs_error_pp"] = df["error_pp"].abs()
    df["abs_delta_effr_bps"] = (df["delta_effr_6m_pp"].abs() * 100).round(0)

    # Métricas globales
    print("=== Métricas globales ===")
    mae = df["abs_error_pp"].mean()
    sesgo = df["error_pp"].mean()
    rmse = np.sqrt((df["error_pp"] ** 2).mean())
    vol = df["realized_pct"].std()
    n = len(df)
    print(f"  n meses:                {n}")
    print(f"  MAE (predict − real):   {mae*100:.0f} bps")
    print(f"  Sesgo:                  {sesgo*100:+.0f} bps "
          f"({'mercado descuenta DEMASIADA SUBIDA' if sesgo > 0 else 'mercado SUBESTIMA cambios'})")
    print(f"  RMSE:                   {rmse*100:.0f} bps")
    print(f"  Vol de realized EFFR_6m: {vol*100:.0f} bps")

    # Por régimen Fed (cortar por mediana de |Δ EFFR_6m|)
    mediana_delta = df["abs_delta_effr_bps"].median()
    df["regimen"] = np.where(df["abs_delta_effr_bps"] <= mediana_delta,
                              "CALMA", "MOVIMIENTO_FUERTE")
    print(f"\n=== Métricas por régimen Fed (corte = mediana |Δ EFFR_6m| = {mediana_delta:.0f} bps) ===")
    for reg in ["CALMA", "MOVIMIENTO_FUERTE"]:
        sub = df[df["regimen"] == reg]
        mae_r = sub["abs_error_pp"].mean()
        sesgo_r = sub["error_pp"].mean()
        print(f"  {reg:>18} (n={len(sub):>3}): "
              f"MAE={mae_r*100:.0f} bps, sesgo={sesgo_r*100:+.0f} bps")

    # Foco años clave
    print(f"\n=== Foco años (¿el mercado acertó cada año?) ===")
    df["ano"] = pd.to_datetime(df["as_of"]).dt.year
    by_year = df.groupby("ano").agg(
        n=("error_pp", "size"),
        mae_bps=("abs_error_pp", lambda x: round(x.mean() * 100, 0)),
        sesgo_bps=("error_pp", lambda x: round(x.mean() * 100, 0)),
        realized_avg_pct=("realized_pct", "mean"),
        predict_avg_pct=("predict_pct", "mean"),
    ).round(2)
    print(by_year.to_string())

    # Foco 2021-2022 (el período donde nuestros modelos fallaron)
    print(f"\n=== Foco período crítico 2021-2022 ===")
    crit = df[(pd.to_datetime(df["as_of"]) >= "2021-01-01") &
              (pd.to_datetime(df["as_of"]) <= "2022-12-31")].copy()
    for c in ["predict_pct", "realized_pct", "error_pp",
              "fed_actual_now_pct", "delta_effr_6m_pp"]:
        crit[c] = crit[c].round(2)
    print(crit[["as_of", "fed_actual_now_pct", "predict_pct", "realized_pct",
                "error_pp", "delta_effr_6m_pp"]].to_string(index=False))

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(13, 8))
    dts = pd.to_datetime(df["as_of"])

    ax = axes[0]
    ax.plot(dts, df["predict_pct"], color="#3498db", lw=1.5,
            label="MERCADO descuenta (DGS6MO hoy)")
    ax.plot(dts, df["realized_pct"], color="#c0392b", lw=1.5,
            label="REALIZADO (EFFR prom 6m post)")
    ax.fill_between(dts, df["predict_pct"], df["realized_pct"],
                    color="grey", alpha=0.2, label="error")
    ax.set_ylabel("Tasa (%)"); ax.legend(loc="upper left")
    ax.set_title(f"Mercado vs realizado (Fed Funds 6m forward) — "
                 f"MAE={mae*100:.0f}bps, sesgo={sesgo*100:+.0f}bps")
    ax.grid(alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-01-01"), pd.Timestamp("2022-12-31"),
               color="orange", alpha=0.10, label="período crítico")

    ax = axes[1]
    colors_e = ["#c0392b" if e > 0 else "#27ae60" for e in df["error_pp"]]
    ax.bar(dts, df["error_pp"] * 100, color=colors_e, edgecolor="black",
           linewidth=0.3, width=22)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_ylabel("Error mercado − realizado (bps)")
    ax.set_title("Error del mercado al predecir Fed Funds. Verde=descontó muy poco, "
                 "Rojo=descontó demasiado.")
    ax.grid(axis="y", alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-01-01"), pd.Timestamp("2022-12-31"),
               color="orange", alpha=0.10)

    fig.tight_layout()
    out = CACHE_DIR / "fed_funds_benchmark.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    df.to_parquet(CACHE_DIR / "fed_funds_benchmark.parquet", index=False)
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
