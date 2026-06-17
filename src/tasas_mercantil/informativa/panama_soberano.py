"""L_PA_2 — Curva soberano Panamá + curvas por calificación + forwards implícitos.

Reemplaza el placeholder. Usa datos reales del estudio Panamá:
  - `docs/_data/curva_actual.csv`: yields actuales por instr_group × plazo
    (incluye "Tesoro Panamá" — la curva soberano local).
  - `docs/_data/bancos_curva_tier.csv`: yields por calificación T1-T5.

¿Existen forwards de tasas Panamá? NO existen futuros de tasas como SR3 en
USA. PERO podemos construir FORWARDS IMPLÍCITOS desde la curva soberano
spot — exactamente la misma matemática que para los forwards SOFR
(L_USA_3 panel 4), pero aplicada a la curva del Tesoro panameño.

Frontera honesta: la curva soberano Panamá tiene 6 puntos (0.5y, 2y, 4y,
6y, 8.5y, 12y) — bootstrap interno simple, no es el implícito de un
mercado de futuros líquido.

CDS Panamá sigue pendiente (requiere plantilla BBG v0.3 con CPAN CDS).
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CURVA_CSV = Path("docs/_data/curva_actual.csv")
BANCOS_CURVA_CSV = Path("docs/_data/bancos_curva_tier.csv")
BLOOMBERG_PARQUET = Path("data/external/tasas_mercantil/bloomberg_historico.parquet")

UST_PILLARS = [("UST_1Y", 1.0), ("UST_2Y", 2.0), ("UST_3Y", 3.0),
               ("UST_5Y", 5.0), ("UST_7Y", 7.0), ("UST_10Y", 10.0),
               ("UST_20Y", 20.0), ("UST_30Y", 30.0)]

RATING_LABELS = {"T1": "AAA Panamá", "T2": "AA Panamá",
                 "T3": "A Panamá",   "T4": "BBB Panamá",
                 "T5": "BB / sin calif."}
RATING_COLORS = {"T1": "#0d1b2a", "T2": "#1a3a5c",
                 "T3": "#2a6fb3", "T4": "#7aa9d2", "T5": "#aac6e3"}

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")


def _ust_curve(as_of: date) -> dict[float, float]:
    from .data_loader import load_master
    df = load_master()
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    cut = pd.Timestamp(as_of)
    out = {}
    for feat, t in UST_PILLARS:
        sub = df[(df["feature_name"] == feat) & (df["obs_date"] <= cut)]
        if sub.empty:
            continue
        v = float(sub.sort_values("obs_date").iloc[-1]["value"])
        if np.isfinite(v):
            out[t] = v
    return out


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    if not xs: return float("nan")
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    return float(np.interp(x, xs, ys))


def _forwards_implicitos(curva_xs: list[float], curva_ys: list[float],
                         n_years: int = 5) -> tuple[list[float], list[float]]:
    """Forwards anuales implícitos de una curva spot.

    Devuelve (xs, fwd_pct) donde fwd_pct[k] es la tasa anualizada implícita
    entre el año k y el k+1 según la curva spot (composición continua aprox).
    Para cada k: F(k, k+1) ≈ (k+1)·z(k+1) − k·z(k).
    """
    fwd_xs, fwd_ys = [], []
    for k in range(n_years):
        z_k1 = _interp(k + 1, curva_xs, curva_ys)
        z_k = _interp(k, curva_xs, curva_ys) if k > 0 else _interp(0.5, curva_xs, curva_ys)
        if np.isfinite(z_k1) and np.isfinite(z_k):
            f = (k + 1) * z_k1 - k * z_k if k > 0 else z_k1
            fwd_xs.append(k + 0.5)
            fwd_ys.append(f)
    return fwd_xs, fwd_ys


def aggregate(as_of: date) -> dict:
    curva = pd.read_csv(CURVA_CSV)
    bancos = pd.read_csv(BANCOS_CURVA_CSV)
    ust = _ust_curve(as_of)

    soberano = curva[curva["instr_group"] == "Tesoro Panamá"].sort_values("x_years")
    sob_xs = soberano["x_years"].tolist()
    sob_ys = soberano["yld_pct"].tolist()
    fwd_xs, fwd_ys = _forwards_implicitos(sob_xs, sob_ys, n_years=5)

    # Curva UST como comparable
    ust_xs = sorted(ust.keys()); ust_ys = [ust[x] for x in ust_xs]
    fwd_xs_ust, fwd_ys_ust = _forwards_implicitos(ust_xs, ust_ys, n_years=5)

    # Tabla resumen: curva soberano vs UST + spread por plazo
    summary_rows = []
    for x, y in zip(sob_xs, sob_ys):
        ust_y = _interp(x, ust_xs, ust_ys)
        sp_bp = (y - ust_y) * 100 if np.isfinite(ust_y) else float("nan")
        summary_rows.append({
            "Plazo": _bucket_label(x),
            "Tesoro Panamá": f"{y:.2f}%",
            "Tesoro USA": f"{ust_y:.2f}%" if np.isfinite(ust_y) else "—",
            "Sobreprecio Panamá\n(centésimas)":
                f"{sp_bp:+.0f}" if np.isfinite(sp_bp) else "—",
        })
    summary_df = pd.DataFrame(summary_rows)

    msg = _build_message(sob_xs, sob_ys, ust_xs, ust_ys, fwd_xs, fwd_ys, as_of)

    return {
        "soberano_xs": sob_xs, "soberano_ys": sob_ys,
        "ust_xs": ust_xs, "ust_ys": ust_ys,
        "fwd_xs": fwd_xs, "fwd_ys": fwd_ys,
        "fwd_xs_ust": fwd_xs_ust, "fwd_ys_ust": fwd_ys_ust,
        "bancos": bancos, "summary_df": summary_df,
        "message": msg,
    }


def _bucket_label(x_years: float) -> str:
    if x_years < 1: return "Menos de 1 año"
    if x_years < 3: return "1 a 3 años"
    if x_years < 5: return "3 a 5 años"
    if x_years < 7: return "5 a 7 años"
    if x_years < 10: return "7 a 10 años"
    return "Más de 10 años"


def _build_message(sob_xs, sob_ys, ust_xs, ust_ys, fwd_xs, fwd_ys, as_of) -> str:
    parts = []
    if sob_xs and ust_xs:
        # spread mediano
        spreads_bp = []
        for x, y in zip(sob_xs, sob_ys):
            ust_y = _interp(x, ust_xs, ust_ys)
            if np.isfinite(ust_y):
                spreads_bp.append((y - ust_y) * 100)
        if spreads_bp:
            mediana_pp = np.median(spreads_bp) / 100
            parts.append(
                f"El bono soberano de Panamá paga en promedio "
                f"{mediana_pp:.2f} puntos porcentuales más que el bono del "
                f"Tesoro USA del mismo plazo"
            )
        # Slope
        if len(sob_ys) >= 2:
            slope = sob_ys[-1] - sob_ys[0]
            parts.append(
                f"la curva soberana panameña está creciente: del "
                f"{sob_ys[0]:.2f}% en plazos cortos sube a {sob_ys[-1]:.2f}% "
                f"en los plazos más largos ({slope:+.2f} puntos)"
            )
    if fwd_xs and fwd_ys:
        f0 = fwd_ys[0]; f4 = fwd_ys[-1]
        if abs(f4 - f0) > 0.3:
            verb = "suban" if f4 > f0 else "bajen"
            parts.append(
                f"los forwards implícitos sugieren que las tasas panameñas "
                f"{verb} de {f0:.2f}% en el primer año a {f4:.2f}% en el año 5"
            )
        else:
            parts.append(
                f"los forwards implícitos sugieren tasas panameñas "
                f"relativamente estables (~{np.mean(fwd_ys):.2f}%) "
                f"en los próximos 5 años"
            )
    return ". ".join(parts) + "." if parts else f"Curvas soberanas al {as_of}."


# ---------------------------------------------------------------------------
def build_msg_l_pa_2(as_of: date) -> str:
    return aggregate(as_of)["message"]


def plot_l_pa_2(as_of: date, output_path: Path | str,
                figsize=(15, 9), dpi=130,
                show_message_banner: bool = False) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    a = aggregate(as_of)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    if show_message_banner:
        gs = fig.add_gridspec(3, 2, height_ratios=[0.22, 1.10, 1.10],
                              width_ratios=[1.0, 1.0], hspace=0.45, wspace=0.22)
        ax_msg = fig.add_subplot(gs[0, :]); ax_msg.axis("off")
        ax_sob = fig.add_subplot(gs[1, 0])
        ax_fwd = fig.add_subplot(gs[1, 1])
        ax_tier = fig.add_subplot(gs[2, 0])
        ax_tbl = fig.add_subplot(gs[2, 1])
        ax_msg.text(0.5, 0.5, a["message"],
                    ha="center", va="center", fontsize=11.0,
                    color="#0d1b2a", wrap=True,
                    bbox=dict(boxstyle="round,pad=0.7", facecolor="#fff5e6",
                              edgecolor="#b32a2a", linewidth=1.6))
    else:
        gs = fig.add_gridspec(2, 2, height_ratios=[1.10, 1.10],
                              width_ratios=[1.0, 1.0], hspace=0.45, wspace=0.22)
        ax_sob = fig.add_subplot(gs[0, 0])
        ax_fwd = fig.add_subplot(gs[0, 1])
        ax_tier = fig.add_subplot(gs[1, 0])
        ax_tbl = fig.add_subplot(gs[1, 1])
    ax_tbl.axis("off")

    # Panel 1: Curva soberano Panamá vs UST
    ax_sob.plot(a["ust_xs"], a["ust_ys"], color="#888888", lw=2.2,
                marker="o", ms=5, label="Tesoro USA (referencia)")
    ax_sob.plot(a["soberano_xs"], a["soberano_ys"], color="#b32a2a", lw=2.4,
                marker="s", ms=6, label="Tesoro Panamá")
    # Sombrear sobreprecio
    if a["soberano_xs"]:
        ust_interp = [_interp(x, a["ust_xs"], a["ust_ys"])
                      for x in a["soberano_xs"]]
        ax_sob.fill_between(a["soberano_xs"], ust_interp, a["soberano_ys"],
                            color="#b32a2a", alpha=0.10,
                            label="Sobreprecio Panamá")
    ax_sob.set_title("Tasa que paga un bono soberano por plazo\n"
                     "(Tesoro Panamá vs Tesoro USA)",
                     fontsize=10.5, weight="bold")
    ax_sob.set_xlabel("Plazo (años)", fontsize=9)
    ax_sob.set_ylabel("Tasa anual (%)", fontsize=9)
    ax_sob.legend(loc="lower right", fontsize=8.5)
    ax_sob.grid(True, alpha=0.3); ax_sob.set_axisbelow(True)

    # Panel 2: Forwards implícitos
    if a["fwd_xs"]:
        x = np.array(a["fwd_xs"])
        w = 0.35
        ax_fwd.bar(x - w/2, a["fwd_ys"], width=w, color="#b32a2a",
                   label="Forwards Panamá", alpha=0.85)
        if a["fwd_xs_ust"]:
            ax_fwd.bar(x + w/2, a["fwd_ys_ust"], width=w, color="#888888",
                       label="Forwards USA (referencia)", alpha=0.85)
        for i, v in enumerate(a["fwd_ys"]):
            ax_fwd.text(x[i] - w/2, v + 0.1, f"{v:.2f}",
                        ha="center", fontsize=7.5, weight="bold",
                        color="#b32a2a")
    ax_fwd.set_title("Qué tasas anticipa el mercado para Panamá\n"
                     "(forwards implícitos de la curva soberana)",
                     fontsize=10.5, weight="bold")
    ax_fwd.set_xlabel("Año adelante", fontsize=9)
    ax_fwd.set_ylabel("Tasa anual implícita (%)", fontsize=9)
    ax_fwd.set_xticks(np.arange(1, 6))
    ax_fwd.set_xticklabels(["Año 1", "Año 2", "Año 3", "Año 4", "Año 5"])
    ax_fwd.legend(loc="best", fontsize=8.5)
    ax_fwd.grid(True, axis="y", alpha=0.3); ax_fwd.set_axisbelow(True)

    # Panel 3: Curvas por rating bancario
    bancos = a["bancos"]
    rating_order = ["T1", "T2", "T3", "T4", "T5"]
    bucket_order = ["0-1y", "1-3y", "3-5y", "5-7y", "7-10y", "10y+"]
    bucket_mids = {"0-1y": 0.5, "1-3y": 2, "3-5y": 4, "5-7y": 6,
                   "7-10y": 8.5, "10y+": 12}
    for tier in rating_order:
        sub = bancos[bancos["rating_tier"] == tier].copy()
        if sub.empty: continue
        sub["mid"] = sub["bucket_plazo"].map(bucket_mids)
        sub = sub.sort_values("mid").dropna(subset=["yld_pct"])
        if sub.empty: continue
        ax_tier.plot(sub["mid"], sub["yld_pct"],
                     color=RATING_COLORS[tier], lw=2.0,
                     marker="o", ms=5,
                     label=RATING_LABELS[tier])
    if a["ust_xs"]:
        ax_tier.plot(a["ust_xs"], a["ust_ys"], color="#1a7a1a", lw=1.6,
                     ls="--", marker="x", ms=5, alpha=0.7,
                     label="Tesoro USA (referencia)")
    ax_tier.set_title("Tasa que paga cada calificación bancaria por plazo\n"
                      "(Panamá local)",
                      fontsize=10.5, weight="bold")
    ax_tier.set_xlabel("Plazo (años)", fontsize=9)
    ax_tier.set_ylabel("Tasa anual (%)", fontsize=9)
    ax_tier.legend(loc="lower right", fontsize=8.0, ncol=2)
    ax_tier.grid(True, alpha=0.3); ax_tier.set_axisbelow(True)

    # Panel 4: Tabla resumen + nota sobre CDS
    ax_tbl.set_title("Resumen curva soberano Panamá vs Tesoro USA",
                     fontsize=10.5, weight="bold")
    cols = list(a["summary_df"].columns)
    cell = a["summary_df"].values.tolist()
    tbl = ax_tbl.table(cellText=cell, colLabels=cols,
                       cellLoc="center", loc="upper center",
                       bbox=[0.0, 0.45, 1.0, 0.52])
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5)
    for j in range(len(cols)):
        tbl[0, j].set_facecolor("#2a6fb3")
        tbl[0, j].set_text_props(color="white", weight="bold")

    ax_tbl.text(0.02, 0.30,
                "Sobre los forwards implícitos:\n"
                "• Panamá no tiene mercado de futuros de tasas como USA.\n"
                "• Estos forwards se calculan a partir de la curva del bono\n"
                "   soberano panameño (qué tasa pide el mercado HOY por\n"
                "   prestarle a Panamá a 1, 2, 3, 4 o 5 años).\n"
                "• El CDS de Panamá (seguro de impago) llegará cuando se\n"
                "   amplíe la plantilla Bloomberg.",
                transform=ax_tbl.transAxes,
                ha="left", va="top", fontsize=8.5, style="italic",
                color="#555",
                bbox=dict(boxstyle="round,pad=0.5",
                          facecolor="#f5f8fb", edgecolor="#aaa"))

    fig.suptitle(f"Bono soberano de Panamá y curvas por calificación bancaria"
                 f" · cierre del {as_of}",
                 fontsize=12.5, weight="bold", y=0.995)
    fig.text(0.5, 0.005, DISCLAIMER, ha="center", fontsize=7.5,
             style="italic", color="#666")
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return output_path
