"""Loader del Excel devuelto por el analista (plantilla mensual v0.3).

La plantilla `BloombergTemplate_TasasMercantil.xlsx` se entrega cada mes
con la hoja `02_Datos` que el analista resolvió. Este loader parsea esa
hoja + `03_SOFR_Futures` + `04_FedWatch` y persiste a parquet canonical
compatible con MasterStore.

La hoja `02_Datos` tiene 123 instrumentos (v0.3) con columnas:
    #, categoria, region, instrument, tenor_label, tenor_years, ticker,
    field, unit, val_AS_OF, val_MES_ANT, val_YE_ANT, val_INI_12M, nota

El feature_name canonical se construye uniendo instrument + tenor_label
(ej: UST + 10Y → UST_10Y; SOFR_OIS + 1Y → SOFR_OIS_1Y; EURUSD_FWD + 1M
→ EURUSD_FWD_1M).

Output: `data/external/tasas_mercantil/bloomberg_template_v03.parquet`
en formato long compatible con `data_loader.load_master()`.

Uso:
    PYTHONPATH=src python scripts/ingest_bloomberg_template.py \\
        ProyectoTasasMercantil/cortes/<as_of>/BloombergTemplate.xlsx
"""
from __future__ import annotations
import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path("data/external/tasas_mercantil/bloomberg_template_v03.parquet")

# Map de columnas de valor → fechas relativas al as_of de la plantilla.
# El analista resuelve la plantilla a una fecha AS_OF dada (hoja 01_Parametros).
# Las otras columnas son retrocesos: -1m, fin del año anterior, inicio últimos 12m.
VALUE_COLS = {
    "val_AS_OF":   "as_of",       # fecha = AS_OF
    "val_MES_ANT": "mes_ant",     # fecha = AS_OF - 1 mes
    "val_YE_ANT":  "ye_ant",      # fecha = 31-dic año anterior
    "val_INI_12M": "ini_12m",     # fecha = AS_OF - 12 meses
}


def _read_params(path: Path) -> date:
    """Lee la fecha AS_OF de la hoja 01_Parametros."""
    df = pd.read_excel(path, sheet_name="01_Parametros", header=None)
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row.dropna().tolist()]
        for i, v in enumerate(vals):
            if v.upper() in ("AS_OF", "FECHA_AS_OF"):
                if i + 1 < len(vals):
                    return pd.to_datetime(vals[i + 1]).date()
    raise ValueError(f"No encontré AS_OF en hoja 01_Parametros de {path}")


def _shift_date(as_of: date, kind: str) -> date | None:
    ts = pd.Timestamp(as_of)
    if kind == "as_of":   return as_of
    if kind == "mes_ant": return (ts - pd.offsets.MonthEnd(1)).date()
    if kind == "ye_ant":  return date(as_of.year - 1, 12, 31)
    if kind == "ini_12m": return (ts - pd.DateOffset(months=12)).date()
    return None


def _feature_name(instr: str, tenor_label: str) -> str:
    """Compone feature_name canonical."""
    instr = str(instr).strip()
    tenor = str(tenor_label).strip()
    if not tenor or tenor in ("—", "—", "ALL", "SPOT", ""):
        return instr
    if instr.endswith("_INFL") and tenor:
        return f"BE_{tenor}"   # BE_INFL/2Y → BE_2Y para compat con FRED
    return f"{instr}_{tenor}"


def parse_template(path: Path) -> pd.DataFrame:
    """Lee el Excel devuelto y devuelve DataFrame long canonical."""
    as_of = _read_params(path)
    print(f"AS_OF de la plantilla: {as_of}")

    sheets = pd.read_excel(path, sheet_name=None)
    rows = []

    # --- 02_Datos: 123 instrumentos × 4 fechas ---
    if "02_Datos" in sheets:
        df = sheets["02_Datos"]
        df.columns = [str(c).strip() for c in df.columns]
        cols_req = {"instrument", "tenor_label", "ticker", "field"}
        if not cols_req.issubset(df.columns):
            raise RuntimeError(f"02_Datos no tiene columnas {cols_req - set(df.columns)}")
        for _, r in df.iterrows():
            if pd.isna(r.get("instrument")):
                continue
            feature = _feature_name(r["instrument"], r.get("tenor_label", ""))
            ticker = str(r.get("ticker", "")).strip()
            for col, kind in VALUE_COLS.items():
                if col not in df.columns:
                    continue
                v = r.get(col)
                if pd.isna(v):
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                obs_date = _shift_date(as_of, kind)
                rows.append({
                    "feature_name": feature,
                    "ticker": ticker,
                    "obs_date": pd.Timestamp(obs_date),
                    "value": v,
                    "vintage_date": pd.Timestamp(as_of),
                    "source": "bloomberg",
                    "sheet": "02_Datos",
                })

    # --- 03_SOFR_Futures: 8 vencimientos × precio ---
    if "03_SOFR_Futures" in sheets:
        df = sheets["03_SOFR_Futures"]
        df.columns = [str(c).strip() for c in df.columns]
        for _, r in df.iterrows():
            n = r.get("n") if "n" in df.columns else r.get("vencimiento_n")
            ticker = r.get("ticker") if "ticker" in df.columns else r.get("ticker_continuo")
            val = r.get("price") if "price" in df.columns else r.get("PX_LAST")
            if pd.isna(n) or pd.isna(val):
                continue
            try:
                feature = f"SR3_{int(n)}Q"
                rows.append({
                    "feature_name": feature,
                    "ticker": str(ticker or "").strip(),
                    "obs_date": pd.Timestamp(as_of),
                    "value": float(val),
                    "vintage_date": pd.Timestamp(as_of),
                    "source": "bloomberg",
                    "sheet": "03_SOFR_Futures",
                })
            except (TypeError, ValueError):
                continue

    # --- 04_FedWatch / ECFC manual paste ---
    if "04_FedWatch" in sheets:
        df = sheets["04_FedWatch"]
        df.columns = [str(c).strip() for c in df.columns]
        # WIRP / ECFC pasted manually — best-effort: detectamos columnas con
        # rate + probability/consensus por reunión
        for _, r in df.iterrows():
            meeting = r.get("meeting") if "meeting" in df.columns else None
            consensus = r.get("ecfc_consensus") if "ecfc_consensus" in df.columns else None
            if consensus is not None and not pd.isna(consensus):
                try:
                    rows.append({
                        "feature_name": f"ECFC_{str(meeting).strip()}" if meeting else "ECFC_NEXT",
                        "ticker": "ECFC<GO>",
                        "obs_date": pd.Timestamp(as_of),
                        "value": float(consensus),
                        "vintage_date": pd.Timestamp(as_of),
                        "source": "bloomberg",
                        "sheet": "04_FedWatch",
                    })
                except (TypeError, ValueError):
                    continue

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError(f"No se pudo extraer ningún dato de {path}")
    print(f"Extraídos {len(out):,} valores ({out['feature_name'].nunique()} features distintos)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Path al Excel devuelto por el analista")
    ap.add_argument("--output", default=str(OUT))
    args = ap.parse_args()

    df = parse_template(Path(args.input))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"\nGuardado → {out_path}")
    print(df.groupby("sheet").agg(n=("value", "size"),
                                  features=("feature_name", "nunique")).to_string())


if __name__ == "__main__":
    main()
