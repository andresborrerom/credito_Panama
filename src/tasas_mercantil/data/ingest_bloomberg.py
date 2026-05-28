"""Parser del Excel historico Bloomberg -> parquet.

Lee BloombergHistorico_TasasMercantil_FULL_<fecha>.xlsx, normaliza a formato
long con columnas [feature_name, ticker, obs_date, value, vintage_date,
source, sheet], y guarda en data/external/tasas_mercantil/bloomberg_historico.parquet.

Maneja:
- Fechas como serial integers de Excel (caso FED_FUNDS_TARGET_PRE2008).
- Strings '#N/A Invalid Security' como NaN.
- Filas vacias y fila 5 con metadata "Ticker: ..." que estorba.

Uso:
    python -m src.tasas_mercantil.data.ingest_bloomberg historico \\
        --input ProyectoTasasMercantil/plantilla_bloomberg/historico/BloombergHistorico_TasasMercantil_FULL_2026-05-29.xlsx \\
        --output data/external/tasas_mercantil/bloomberg_historico.parquet
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


DATA_SHEETS = [
    "UST_Nominal",
    "TIPS_Real",
    "Breakevens",
    "Swap_SOFR_OIS",
    "Swap_USD_Clasico_LIBOR",
    "SOFR_Money_Market",
    "FedFunds_Policy",
    "EuroDollar_Futures_Proxy_PreSOF",
    "SR3_SOFR_Futures",
]

EXCEL_DATE_ORIGIN = datetime(1899, 12, 30)


def _coerce_to_date(value):
    """Acepta datetime, date, serial int (Excel), o NaN. Devuelve date o NaT."""
    if value is None or pd.isna(value):
        return pd.NaT
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month"):
        return value  # date
    if isinstance(value, (int, float)):
        # Serial date de Excel (numero de dias desde 1899-12-30)
        try:
            return (EXCEL_DATE_ORIGIN + timedelta(days=float(value))).date()
        except (ValueError, OverflowError):
            return pd.NaT
    if isinstance(value, str):
        # Intentar parsear como fecha
        try:
            return pd.to_datetime(value).date()
        except (ValueError, TypeError):
            return pd.NaT
    return pd.NaT


def _coerce_to_float(value):
    """Acepta numero o string. Devuelve float o NaN. '#N/A' -> NaN."""
    if value is None or pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or "#" in s or "N/A" in s or s.lower() == "nan":
            return float("nan")
        try:
            return float(s)
        except ValueError:
            return float("nan")
    return float("nan")


def parse_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Parse one sheet. Cada par de columnas = (fecha, valor) de un instrumento.

    Header esta en fila 3 (index 2).
    Fila 5 (index 1 desde fila 4) tiene "Ticker: X" en col fecha y desc en col valor.
    Filas 4 en adelante (con la fila 5 que ignoramos) son datos del BDH spilled.
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=2, engine="openpyxl")
    cols = raw.columns.tolist()
    rows = []
    for c in range(0, len(cols), 2):
        if c + 1 >= len(cols):
            break
        col_fecha = cols[c]
        col_valor = cols[c + 1]
        instrument = str(col_fecha).replace(" — fecha", "").strip()

        # Tomar las dos columnas del instrumento
        sub = raw[[col_fecha, col_valor]].copy()
        sub.columns = ["raw_date", "raw_value"]

        # Detectar fila con "Ticker: ..." en raw_date (es string, no fecha)
        ticker = None
        for _, r in sub.iterrows():
            rd = r["raw_date"]
            if isinstance(rd, str) and rd.startswith("Ticker:"):
                ticker = rd.replace("Ticker:", "").strip()
                break

        # Convertir fechas y valores
        sub["obs_date"] = sub["raw_date"].map(_coerce_to_date)
        sub["value"] = sub["raw_value"].map(_coerce_to_float)
        sub = sub.dropna(subset=["obs_date"])
        # No filtramos NaN en valor — los conservamos por trazabilidad

        sub["feature_name"] = instrument
        sub["ticker"] = ticker
        sub["sheet"] = sheet
        sub["source"] = "bloomberg"
        sub["vintage_date"] = sub["obs_date"]  # tasas de mercado, no se revisan

        rows.append(sub[["feature_name", "ticker", "obs_date", "value", "vintage_date", "source", "sheet"]])

    if not rows:
        return pd.DataFrame(columns=["feature_name", "ticker", "obs_date", "value", "vintage_date", "source", "sheet"])
    return pd.concat(rows, ignore_index=True)


def parse_historico(path: Path) -> pd.DataFrame:
    """Parse todas las hojas de datos."""
    all_frames = []
    for sheet in DATA_SHEETS:
        df = parse_sheet(path, sheet)
        print(f"  [{sheet}] {len(df):,} filas, {df['feature_name'].nunique()} instrumentos")
        all_frames.append(df)
    out = pd.concat(all_frames, ignore_index=True)
    out = out.sort_values(["feature_name", "obs_date"]).reset_index(drop=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kind", choices=["historico"])
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    print(f"Parseando {args.input}...")
    df = parse_historico(args.input)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)

    print(f"\n[OK] {args.output}")
    print(f"     Total filas: {len(df):,}")
    print(f"     Instrumentos: {df['feature_name'].nunique()}")
    print(f"     Rango fechas: {df['obs_date'].min()} → {df['obs_date'].max()}")
    print(f"     NaN en valor: {df['value'].isna().sum():,} ({df['value'].isna().mean() * 100:.1f}%)")


if __name__ == "__main__":
    main()
