"""Transforma raw JSON → DataFrames normalizados → SQLite + Parquet."""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.analytics.ytm import (  # noqa: E402
    base_days,
    coupon_to_decimal,
    freq_int,
    parse_fecha,
    ytm_from_price,
)

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)
DB = ROOT / "data" / "panama_fixed_income.sqlite"


def load_json(name: str):
    return json.loads((RAW / f"{name}.json").read_text())


# ----------------------------- INSTRUMENTOS -------------------------------- #
def build_instruments() -> pd.DataFrame:
    raw = load_json("emisiones_activas")["data"]
    df = pd.DataFrame(raw)
    df["fechaEmision_d"] = df["fechaEmision"].apply(parse_fecha)
    df["fechaVencimiento_d"] = df["fechaVencimiento"].apply(parse_fecha)
    df["cupon_decimal"] = df["tasa"].apply(coupon_to_decimal)
    df["freq_int"] = df["frecuencia"].apply(freq_int)
    df["base_days"] = df["base"].apply(base_days)
    df["es_tasa_fija"] = df["tipoTasa"].fillna("").str.upper().str.contains("FIJA")
    df["es_tesoro"] = df["instrumento"].fillna("").str.contains("TESORO", case=False)
    df["es_vcn"] = df["instrumento"].fillna("").str.contains("VCN", case=False)
    def _plazo_orig(r):
        fv, fe = r["fechaVencimiento_d"], r["fechaEmision_d"]
        if fv is None or fe is None or not hasattr(fv, "toordinal") or not hasattr(fe, "toordinal"):
            return np.nan
        return (fv.toordinal() - fe.toordinal()) / 365.25
    df["plazo_original_anos"] = df.apply(_plazo_orig, axis=1)
    return df


# ----------------------------- TRADES -------------------------------- #
def parse_monto(x):
    """Latinex envía montos como número o string '1,234,567.89'."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


def build_trades(instruments: pd.DataFrame) -> pd.DataFrame:
    raw = load_json("transacciones_10y")["data"]
    df = pd.DataFrame(raw)
    if df.empty:
        return df

    df["fecha_d"] = df["fecha"].apply(parse_fecha)
    df["precio"] = df["precio"].apply(parse_monto)
    df["nominal"] = df["nominal"].apply(parse_monto)
    df["monto"] = df["monto"].apply(parse_monto)
    if "rendimiento" in df.columns:
        df["rendimiento_reportado"] = df["rendimiento"].apply(parse_monto)
    else:
        df["rendimiento_reportado"] = np.nan

    # Merge con instrumentos por nemotecnico (preferred) o ISIN
    inst_cols = [
        "nemotecnico",
        "isin",
        "emisor",
        "sector",
        "instrumento",
        "fechaEmision_d",
        "fechaVencimiento_d",
        "cupon_decimal",
        "freq_int",
        "base_days",
        "es_tasa_fija",
        "es_tesoro",
        "es_vcn",
    ]
    inst = instruments[inst_cols].rename(
        columns={"emisor": "emisor_inst", "sector": "sector_inst", "instrumento": "instrumento_inst"}
    )
    df = df.merge(inst, on="nemotecnico", how="left", suffixes=("", "_inst"))

    # Usa info del instrumento si falta en el trade
    df["sector"] = df.get("sector", pd.Series(np.nan, index=df.index)).fillna(df["sector_inst"])
    df["emisor"] = df.get("emisor", pd.Series(np.nan, index=df.index)).fillna(df["emisor_inst"])
    df["instrumento_clase"] = (
        df.get("instrumentoClase", pd.Series(np.nan, index=df.index)).fillna(df["instrumento_inst"])
    )

    # Plazo residual al momento del trade
    def _residual(r):
        fv, fd = r["fechaVencimiento_d"], r["fecha_d"]
        if fv is None or fd is None or not hasattr(fv, "toordinal") or not hasattr(fd, "toordinal"):
            return np.nan
        return (fv.toordinal() - fd.toordinal()) / 365.25
    df["plazo_residual_anos"] = df.apply(_residual, axis=1)

    # YTM por trade (solo bonos tasa fija con info completa)
    def calc_ytm(r):
        if not r["es_tasa_fija"]:
            return np.nan
        if pd.isna(r["precio"]) or r["precio"] <= 0:
            return np.nan
        if r["fechaVencimiento_d"] is None or r["fecha_d"] is None:
            return np.nan
        if r["plazo_residual_anos"] is None or r["plazo_residual_anos"] <= 0:
            return np.nan
        try:
            return ytm_from_price(
                price_clean=float(r["precio"]),
                settle=r["fecha_d"],
                maturity=r["fechaVencimiento_d"],
                coupon_rate=float(r["cupon_decimal"] or 0),
                freq_per_year=int(r["freq_int"] or 2),
                face=100.0,
                day_basis=float(r["base_days"] or 365.0),
            )
        except Exception:
            return np.nan

    df["ytm_calc"] = df.apply(calc_ytm, axis=1)

    # Yield "best": calc si existe; fallback al reportado
    df["yield_used"] = df["ytm_calc"].fillna(df["rendimiento_reportado"].apply(coupon_to_decimal))

    df["bucket_plazo"] = pd.cut(
        df["plazo_residual_anos"],
        bins=[-0.01, 1, 3, 5, 7, 10, 100],
        labels=["0-1y", "1-3y", "3-5y", "5-7y", "7-10y", "10y+"],
    )
    df["year"] = df["fecha_d"].apply(lambda d: d.year if d else np.nan)
    df["yyyymm"] = df["fecha_d"].apply(lambda d: d.strftime("%Y-%m") if d else None)

    return df


# ----------------------------- VOLUMEN -------------------------------- #
def build_volumen() -> pd.DataFrame:
    raw = load_json("volumen_emisor")["data"]
    return pd.DataFrame(raw)


# ----------------------------- OFERTAS LIVE -------------------------------- #
def build_quotes() -> pd.DataFrame:
    raw = load_json("ofertas_home")["data"]
    df = pd.DataFrame(raw)
    df["snapshot_ts"] = datetime.utcnow().isoformat()
    return df


# ----------------------------- HECHOS RELEVANTES -------------------------------- #
def build_hechos() -> pd.DataFrame:
    raw = load_json("hechos_relevantes")["data"]
    df = pd.DataFrame(raw)
    if "fecha" in df.columns:
        df["fecha_d"] = df["fecha"].apply(parse_fecha)
    return df


# ----------------------------- US TREASURY -------------------------------- #
UST_NAMESPACES = {
    "a": "http://www.w3.org/2005/Atom",
    "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
}


def build_ust() -> pd.DataFrame:
    raw = load_json("ust_yields_raw")
    rows = []
    for year, xml_txt in raw.items():
        try:
            root = ET.fromstring(xml_txt)
        except ET.ParseError:
            continue
        for entry in root.findall("a:entry", UST_NAMESPACES):
            props = entry.find("a:content/m:properties", UST_NAMESPACES)
            if props is None:
                continue
            row = {"year": int(year)}
            for child in props:
                tag = re.sub(r"^\{.*\}", "", child.tag)
                row[tag] = child.text
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "NEW_DATE" in df.columns:
        df["fecha_d"] = pd.to_datetime(df["NEW_DATE"], errors="coerce").dt.date
    # Tenors: BC_1MONTH, BC_3MONTH, BC_6MONTH, BC_1YEAR, BC_2YEAR, BC_3YEAR, BC_5YEAR, BC_7YEAR, BC_10YEAR, BC_20YEAR, BC_30YEAR
    tenor_cols = [c for c in df.columns if c.startswith("BC_")]
    for c in tenor_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ----------------------------- CURVAS AGREGADAS -------------------------------- #
def build_curves(trades: pd.DataFrame) -> pd.DataFrame:
    """Agrega yields por (month, sector, bucket_plazo) → mediana, p25, p75."""
    valid = trades.dropna(subset=["yield_used", "yyyymm", "bucket_plazo"]).copy()
    valid = valid[(valid["yield_used"] > 0) & (valid["yield_used"] < 0.5)]  # filtro sanity
    valid = valid[valid["es_tasa_fija"]]

    g = valid.groupby(["yyyymm", "sector", "bucket_plazo", "instrumento_clase"], observed=True)[
        "yield_used"
    ].agg(["median", lambda s: s.quantile(0.25), lambda s: s.quantile(0.75), "count"])
    g.columns = ["yield_median", "yield_p25", "yield_p75", "n_trades"]
    g = g.reset_index()
    g = g[g["n_trades"] >= 1]
    return g


# ----------------------------- SECTOR-LEVEL (sin bucket) -------------------- #
def build_sector_monthly(trades: pd.DataFrame) -> pd.DataFrame:
    valid = trades.dropna(subset=["yield_used", "yyyymm", "sector"]).copy()
    valid = valid[(valid["yield_used"] > 0) & (valid["yield_used"] < 0.5)]
    valid = valid[valid["es_tasa_fija"]]
    g = valid.groupby(["yyyymm", "sector"], observed=True)["yield_used"].agg(
        ["median", "count"]
    ).reset_index()
    g.columns = ["yyyymm", "sector", "yield_median", "n_trades"]
    return g


# ----------------------------- PROXY DE CRÉDITO -------------------------------- #
CREDIT_TIERS = {
    "Gobierno": "AAA-PAN-Sov",
    "Financiero": "BBB-Bank",
    "Comunicaciones": "BBB-Corp",
    "Energía": "BBB-Corp",
    "Consumo": "BB-Corp",
    "Bienes Raíces": "BB-RealEstate",
    "Industrial": "BB-Corp",
    "Servicios": "BB-Corp",
    "Salud": "BB-Corp",
}


def add_credit_proxy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["credit_proxy"] = df["sector"].map(CREDIT_TIERS).fillna("Unrated")
    # Upgrade Tesoro/Estado independiente del campo sector
    if "instrumento_clase" in df.columns:
        is_govt = df["instrumento_clase"].fillna("").str.contains("Tesoro|Estado", case=False)
        df.loc[is_govt, "credit_proxy"] = "AAA-PAN-Sov"
    return df


# ----------------------------- ESCRITURA -------------------------------- #
def _stringify_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte columnas con date objects a strings ISO para parquet/sqlite."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype != object:
            continue
        col_data = out[col]
        # Detectar si hay algún objeto date/datetime en la columna
        sample = col_data.dropna()
        if sample.empty:
            continue
        has_date = sample.head(20).apply(lambda x: hasattr(x, "isoformat")).any()
        if has_date:
            out[col] = col_data.apply(
                lambda x: x.isoformat() if hasattr(x, "isoformat") else x
            )
    return out


def write_all():
    print(">> Construyendo instruments...")
    instruments = build_instruments()
    print(f"   {len(instruments):,} emisiones activas")

    print(">> Construyendo trades + YTM...")
    trades = build_trades(instruments)
    trades = add_credit_proxy(trades)
    print(f"   {len(trades):,} trades; YTM calculado en {trades['ytm_calc'].notna().sum():,}")

    print(">> Construyendo curvas mensuales...")
    curves = build_curves(trades)
    sector_monthly = build_sector_monthly(trades)
    print(f"   {len(curves):,} celdas (mes×sector×plazo×instr); {len(sector_monthly):,} (mes×sector)")

    print(">> Volúmenes y quotes...")
    volumen = build_volumen()
    quotes = build_quotes()

    print(">> Hechos relevantes...")
    hechos = build_hechos()

    print(">> US Treasury...")
    ust = build_ust()
    print(f"   {len(ust):,} días de UST")

    # Escribir Parquet
    for name, df in [
        ("instruments", instruments),
        ("trades", trades),
        ("curves_monthly", curves),
        ("sector_monthly", sector_monthly),
        ("volumen_emisor", volumen),
        ("quotes_live", quotes),
        ("hechos_relevantes", hechos),
        ("ust_yields", ust),
    ]:
        # Sanitize: parquet no acepta date python puro consistente -> convertir a string ISO
        out = PROC / f"{name}.parquet"
        df2 = _stringify_dates(df)
        try:
            df2.to_parquet(out, index=False)
            print(f"   wrote {out.relative_to(ROOT)} ({len(df):,} rows)")
        except Exception as exc:
            print(f"   [WARN] parquet {name}: {exc}")

    # Escribir SQLite
    con = sqlite3.connect(DB)
    for name, df in [
        ("instruments", instruments),
        ("trades", trades),
        ("curves_monthly", curves),
        ("sector_monthly", sector_monthly),
        ("volumen_emisor", volumen),
        ("quotes_live", quotes),
        ("hechos_relevantes", hechos),
        ("ust_yields", ust),
    ]:
        df2 = _stringify_dates(df)
        df2.to_sql(name, con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_trades_fecha ON trades(fecha_d)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_trades_sector ON trades(sector)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_trades_nemo ON trades(nemotecnico)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_inst_isin ON instruments(isin)")
    con.commit()
    con.close()
    print(f">> SQLite: {DB.relative_to(ROOT)}")

    return {
        "instruments": len(instruments),
        "trades": len(trades),
        "ytm_calc": int(trades["ytm_calc"].notna().sum()),
        "curves_cells": len(curves),
        "ust_days": len(ust),
    }


if __name__ == "__main__":
    print(write_all())
