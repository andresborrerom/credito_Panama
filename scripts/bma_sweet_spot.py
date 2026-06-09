"""Sprint 1: Sweet Spot del stress signal — métrica de calidad informativa.

Objetivo: para cada mes, calcular qué tan ACCIONABLE es el output del sistema
operativo Iter 6, combinando confianza (U) y compacidad (rango/W_max).

Métrica SSIQ (Sweet Spot Informational Quality), ∈ [0, 100]:
  SSIQ = U% × (W_max − ancho) / W_max
  - U=70%, ancho 4pp, W_max 10pp → 70 × 0.6 = 42 (excelente)
  - U=50%, ancho 9pp, W_max 10pp → 50 × 0.1 = 5  (marginal)
  - U=0  → 0 (no informativo)

Clasificación cualitativa (para reporte gerencial):
  GREEN  (informativo): U ≥ 60% AND ancho ≤ 7pp
  YELLOW (medio):       U ≥ 50% AND ancho ≤ 9pp Y NO GREEN
  GREY   (no usable):   resto (U=0 o ancho alto a confianza baja)

Validación de honestidad por categoría: la cobertura empírica del HDI declarado
debe ser ≥ U declarado en cada categoría.
"""
from __future__ import annotations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

W_MAX = 0.10
SSIQ_GREEN_U = 0.50   # confianza minima
SSIQ_GREEN_W = 0.05   # ancho ≤ 5pp = afirmación realmente acotada
SSIQ_YELLOW_U = 0.50
SSIQ_YELLOW_W = 0.08  # ancho 5-8pp = afirmación útil pero ancha

CACHE_DIR = Path("data/external/tasas_mercantil")


def categorize(U_pct, width, regime):
    """Sweet spot honesto: GREEN solo en régimen normal. En stress alto el
    rango angosto es señal de complacencia residual del ensemble, no de
    información real (validado empíricamente: GREEN-en-stress cobertura 0%)."""
    if U_pct == 0: return "GREY"
    U = U_pct / 100
    if regime != "normal":
        if U >= SSIQ_YELLOW_U and width <= SSIQ_YELLOW_W:
            return "YELLOW"
        return "GREY"
    if U >= SSIQ_GREEN_U and width <= SSIQ_GREEN_W: return "GREEN"
    if U >= SSIQ_YELLOW_U and width <= SSIQ_YELLOW_W: return "YELLOW"
    return "GREY"


def main():
    df = pd.read_parquet(CACHE_DIR / "bma_iter6_gate_breakeven.parquet")
    df["as_of"] = pd.to_datetime(df["as_of"]).dt.date
    df["ancho"] = df["HDI_gat_hi"] - df["HDI_gat_lo"]
    df["SSIQ"] = np.where(
        df["U_gat"] == 0, 0,
        df["U_gat"] * (W_MAX - df["ancho"]).clip(lower=0) / W_MAX,
    )
    df["categoria"] = [categorize(u, w, r)
                       for u, w, r in zip(df["U_gat"], df["ancho"], df["regime"])]

    print("=== Distribución por categoría ===")
    dist = df["categoria"].value_counts()
    for c in ["GREEN", "YELLOW", "GREY"]:
        n = int(dist.get(c, 0))
        print(f"  {c:>6}: {n:>2}/{len(df)} = {100*n/len(df):.1f}%")

    print("\n=== SSIQ por categoría (estadísticas) ===")
    for c in ["GREEN", "YELLOW", "GREY"]:
        sub = df[df["categoria"] == c]
        if len(sub) == 0: continue
        ssiq = sub["SSIQ"]
        ancho = sub["ancho"]
        u = sub["U_gat"]
        print(f"  {c}: SSIQ mean={ssiq.mean():.1f}, min={ssiq.min():.1f}, "
              f"max={ssiq.max():.1f}  |  ancho mean={ancho.mean():.3f}  |  "
              f"U mean={u.mean():.1f}")

    print("\n=== Validación honestidad por categoría ===")
    print("  (cobertura empírica del HDI declarado debe ser ≥ U declarado)")
    for c in ["GREEN", "YELLOW", "GREY"]:
        sub = df[df["categoria"] == c]
        if len(sub) == 0: continue
        emp = 100 * sub["real_in_HDI"].mean()
        u_decl = sub["U_gat"].mean()
        veredicto = "OK" if emp >= u_decl else "SOBREESTIMA"
        print(f"  {c:>6} (n={len(sub):>2}): U_decl≈{u_decl:.0f}%, "
              f"cobertura empírica={emp:.1f}%  →  {veredicto}")

    print("\n=== Meses GREEN (sweet spot informativo) ===")
    green = df[df["categoria"] == "GREEN"][
        ["as_of", "U_gat", "ancho", "SSIQ", "HDI_gat_lo", "HDI_gat_hi",
         "realized", "real_in_HDI", "regime"]
    ].copy()
    green["ancho_pp"] = (green["ancho"] * 100).round(1)
    green["SSIQ"] = green["SSIQ"].round(1)
    green["lo_pct"] = (green["HDI_gat_lo"] * 100).round(1)
    green["hi_pct"] = (green["HDI_gat_hi"] * 100).round(1)
    green["realized_pct"] = (green["realized"] * 100).round(1)
    print(green[["as_of", "U_gat", "ancho_pp", "SSIQ", "lo_pct", "hi_pct",
                 "realized_pct", "real_in_HDI", "regime"]].to_string(index=False))

    # Plot
    fig, axes = plt.subplots(3, 1, figsize=(13, 10),
                              gridspec_kw={"height_ratios": [1.3, 1.3, 1]})
    dts = pd.to_datetime(df["as_of"])
    colors_cat = {"GREEN": "#27ae60", "YELLOW": "#f1c40f", "GREY": "#95a5a6"}
    cat_colors = [colors_cat[c] for c in df["categoria"]]

    # Panel A: SSIQ time series
    ax = axes[0]
    ax.bar(dts, df["SSIQ"], color=cat_colors, edgecolor="black", linewidth=0.4)
    ax.set_ylabel("SSIQ (0-100)")
    ax.set_title("Sweet Spot Informational Quality (SSIQ) mensual — LQD Iter 6")
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(15, color="#f1c40f", ls="--", lw=0.7, alpha=0.6, label="umbral YELLOW")
    ax.axhline(30, color="#27ae60", ls="--", lw=0.7, alpha=0.6, label="umbral GREEN")
    ax.legend(loc="upper right", fontsize=8)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    # Panel B: confianza vs ancho (scatter), coloreado por categoría
    ax = axes[1]
    for c in ["GREEN", "YELLOW", "GREY"]:
        sub = df[df["categoria"] == c]
        if len(sub) == 0: continue
        ax.scatter(sub["ancho"] * 100, sub["U_gat"],
                   color=colors_cat[c], s=60, alpha=0.75, edgecolor="black",
                   linewidth=0.5, label=f"{c} (n={len(sub)})")
    # Zonas
    ax.axvline(SSIQ_GREEN_W * 100, color="#27ae60", ls=":", lw=1, alpha=0.5)
    ax.axhline(SSIQ_GREEN_U * 100, color="#27ae60", ls=":", lw=1, alpha=0.5)
    ax.axvline(SSIQ_YELLOW_W * 100, color="#f1c40f", ls=":", lw=1, alpha=0.5)
    ax.set_xlabel("Ancho HDI gated (pp)"); ax.set_ylabel("U gated (%)")
    ax.set_title("Espacio confianza × compacidad — sweet spot = arriba-izquierda")
    ax.legend(loc="lower right"); ax.grid(alpha=0.3)
    ax.set_xlim(0, 11); ax.set_ylim(-5, 100)

    # Panel C: realizado con categoría color-coded
    ax = axes[2]
    ax.plot(dts, df["realized"] * 100, color="#34495e", lw=0.8, alpha=0.5)
    ax.scatter(dts, df["realized"] * 100, color=cat_colors, s=50,
               edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="grey", lw=0.7)
    ax.set_ylabel("Retorno LQD 6m realizado (%)")
    ax.set_title("Realizado coloreado por categoría informativa")
    ax.grid(alpha=0.3)
    ax.axvspan(pd.Timestamp("2021-07-01"), pd.Timestamp("2022-03-31"),
               color="grey", alpha=0.12)

    fig.tight_layout()
    out = CACHE_DIR / "bma_sweet_spot.png"
    fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
    df.to_parquet(CACHE_DIR / "bma_sweet_spot.parquet", index=False)
    print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()
