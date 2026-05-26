"""Análisis de pricing y estructuración para emisión de bonos de Mercantil Banco S.A.

Genera las queries y métricas para responder:
- ¿En qué tasa puede emitir Mercantil Banco a distintos plazos?
- ¿Qué monto es realista colocar?
- ¿Es buen momento (ventana de mercado)?
- ¿Qué estructura conviene (bullet, callable, perpetual)?
"""

from __future__ import annotations

import pathlib

import duckdb
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Universo de bancos peer (T1-T3 panameños y extranjeros con presencia local)
PEER_BANKS = [
    "BANISTMO, S.A.",
    "BAC INTERNATIONAL BANK, INC.",
    "MULTIBANK INC.",
    "MERCANTIL BANCO, S.A.",
    "BANCO ALIADO, S.A.",
    "BANCO LAFISE PANAMA, S.A.",
    "GLOBAL BANK CORPORATION",
    "BANESCO (PANAMÁ), S.A.",
    "BANCO GENERAL, S.A.",
    "GRUPO FINANCIERO BG, S.A.",
    "MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.",
    "MERCANTIL SERVICIOS FINANCIEROS INTERNACIONAL, S.A.",
    "BANCO INTERNACIONAL DE COSTA RICA, S.A.",
    "BANCO PANAMA, S.A.",
    "BANCO LA HIPOTECARIA, S.A.",
    "CREDICORP BANK, S.A.",
    "METROBANK, S.A.",
    "TOWERBANK INTERNATIONAL, INC.",
    "BANCO PICHINCHA PANAMA, S.A.",
]

# Mercantil group (3 entidades)
MERCANTIL_GROUP = [
    "MERCANTIL BANCO, S.A.",
    "MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.",
    "MERCANTIL SERVICIOS FINANCIEROS INTERNACIONAL, S.A.",
]

ISSUER_TARGET = "MERCANTIL BANCO, S.A."


def con():
    c = duckdb.connect()
    c.execute(
        f"""CREATE VIEW trades AS
        SELECT * EXCLUDE (fecha_d), CAST(fecha_d AS DATE) AS fecha_d
        FROM read_parquet('{ROOT}/data/processed/trades.parquet')"""
    )
    c.execute(f"CREATE VIEW instruments AS SELECT * FROM read_parquet('{ROOT}/data/processed/instruments.parquet')")
    return c


def primary_market_calendar(c, lookback_days: int = 730) -> pd.DataFrame:
    """Calendario de emisiones primarias de bancos peer en últimos N días.
    Incluye solo bonos de tasa fija (sin VCN cortos para análisis de pricing).
    """
    placeholders = ", ".join(f"'{p}'" for p in PEER_BANKS)
    q = f"""
    SELECT
        emisor, nemotecnico, isin, instrumento,
        fechaEmision_d AS fecha_emision,
        fechaVencimiento_d AS fecha_vencimiento,
        cupon_decimal * 100 AS cupon_pct,
        plazo_original_anos AS plazo,
        montoSerie / 1e6 AS serie_mm,
        montoColocado / 1e6 AS coloc_mm,
        CASE WHEN montoSerie > 0
             THEN montoColocado / montoSerie * 100 ELSE NULL
        END AS pct_coloc,
        frecuencia, tipoTasa
    FROM instruments
    WHERE emisor IN ({placeholders})
      AND es_tasa_fija = TRUE
      AND fechaEmision_d IS NOT NULL
      AND CAST(fechaEmision_d AS DATE) >=
          (CURRENT_DATE - INTERVAL '{lookback_days}' DAY)
      AND instrumento IN ('BONOS', 'NOTAS CORPORATIVAS', 'BONOS HIPOTECARIOS',
                          'VALORES COMERCIALES NEGOCIABLES', 'BONOS DE DESARROLLO INMOBILIARIO')
      AND cupon_decimal > 0  -- excluye placeholders 0%
    ORDER BY fechaEmision_d DESC
    """
    return c.execute(q).df()


def issuer_secondary_curve(c, emisor: str, lookback_days: int = 365) -> pd.DataFrame:
    """Curva en secundario de un emisor (yield medio por bucket de plazo)."""
    q = f"""
    SELECT bucket_plazo,
           COUNT(*) n_trades,
           AVG(plazo_residual_anos) avg_plazo,
           MEDIAN(ytm_calc) yld_median,
           MEDIAN(spread_bp) spread_median,
           SUM(monto) volumen
    FROM trades
    WHERE emisor = '{emisor.replace("'", "''")}'
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN 0.005 AND 0.40
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
    GROUP BY 1
    ORDER BY avg_plazo
    """
    return c.execute(q).df()


def peer_curves(c, lookback_days: int = 365) -> pd.DataFrame:
    """Curva en secundario de cada banco peer."""
    placeholders = ", ".join(f"'{p}'" for p in PEER_BANKS)
    q = f"""
    SELECT emisor, bucket_plazo,
           COUNT(*) n_trades,
           AVG(plazo_residual_anos) avg_plazo,
           MEDIAN(ytm_calc) yld_median,
           MEDIAN(spread_bp) spread_median,
           SUM(monto)/1e6 volumen_mm
    FROM trades
    WHERE emisor IN ({placeholders})
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN 0.005 AND 0.40
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    ORDER BY emisor, avg_plazo
    """
    return c.execute(q).df()


def banesco_perpetual_detail(c) -> pd.DataFrame:
    """Detalle de la emisión perpetua/cuasi-perpetua de Banesco — el anchor citado."""
    q = """
    SELECT nemotecnico, isin, instrumento, fechaEmision_d, fechaVencimiento_d,
           cupon_decimal*100 cupon_pct, tipoTasa, frecuencia,
           montoSerie/1e6 serie_mm, montoColocado/1e6 coloc_mm,
           CASE WHEN montoSerie > 0 THEN montoColocado/montoSerie*100 ELSE NULL END pct_coloc
    FROM instruments
    WHERE emisor = 'BANESCO (PANAMÁ), S.A.'
    ORDER BY fechaVencimiento_d DESC
    """
    return c.execute(q).df()


def issuance_pricing_summary(c) -> pd.DataFrame:
    """Tabla resumen para pricing: (plazo, cupon medio) por bucket."""
    cal = primary_market_calendar(c, lookback_days=730)
    if cal.empty:
        return cal
    cal["plazo_bucket"] = pd.cut(
        cal["plazo"],
        bins=[0, 0.75, 1.25, 2.5, 4, 6, 10, 100],
        labels=["≤0.75y", "~1y", "~2y", "~3y", "5y", "7-10y", "10y+"],
    )
    g = (
        cal.groupby(["plazo_bucket", "instrumento"], observed=True)
        .agg(
            n_emisiones=("nemotecnico", "count"),
            n_emisores=("emisor", "nunique"),
            cupon_min=("cupon_pct", "min"),
            cupon_p25=("cupon_pct", lambda s: s.quantile(0.25)),
            cupon_median=("cupon_pct", "median"),
            cupon_p75=("cupon_pct", lambda s: s.quantile(0.75)),
            cupon_max=("cupon_pct", "max"),
            monto_total_mm=("coloc_mm", "sum"),
            pct_coloc_avg=("pct_coloc", "mean"),
        )
        .reset_index()
    )
    return g.dropna(subset=["plazo_bucket"])


def issuance_window_signal(c) -> dict:
    """¿Es buen momento para emitir? Basado en percentil del spread T2 actual vs historia 5y."""
    q = """
    WITH hist AS (
        SELECT spread_bp FROM trades
        WHERE sector='Financiero'
          AND es_tasa_fija=TRUE
          AND spread_bp IS NOT NULL
          AND spread_bp BETWEEN -200 AND 2000
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '1825' DAY FROM trades)
          AND rating_tier IN ('T2','T3')
    ),
    current AS (
        SELECT MEDIAN(spread_bp) spread_now
        FROM trades
        WHERE sector='Financiero'
          AND es_tasa_fija=TRUE
          AND spread_bp IS NOT NULL
          AND spread_bp BETWEEN -200 AND 2000
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '90' DAY FROM trades)
          AND rating_tier IN ('T2','T3')
    )
    SELECT (SELECT spread_now FROM current) spread_actual,
           QUANTILE_CONT(spread_bp, 0.10) p10,
           QUANTILE_CONT(spread_bp, 0.25) p25,
           QUANTILE_CONT(spread_bp, 0.50) p50,
           QUANTILE_CONT(spread_bp, 0.75) p75,
           QUANTILE_CONT(spread_bp, 0.90) p90,
           COUNT(*) n
    FROM hist
    """
    row = c.execute(q).df().iloc[0]
    sn = row["spread_actual"]
    # interpolar percentil
    breaks = [0.10, 0.25, 0.50, 0.75, 0.90]
    vals = [row["p10"], row["p25"], row["p50"], row["p75"], row["p90"]]
    if sn <= vals[0]:
        pc = 0.05
    elif sn >= vals[-1]:
        pc = 0.95
    else:
        pc = 0.5
        for i in range(4):
            if vals[i] <= sn <= vals[i + 1]:
                denom = vals[i + 1] - vals[i]
                frac = (sn - vals[i]) / denom if denom else 0
                pc = breaks[i] + frac * (breaks[i + 1] - breaks[i])
                break
    interpretacion = (
        "FAVORABLE para emitir (spreads comprimidos vs historia → mercado cobra menos por crédito)"
        if pc <= 0.35
        else "DESFAVORABLE (spreads anchos vs historia → mercado cobra extra por crédito)"
        if pc >= 0.65
        else "NEUTRAL (spreads cerca de la mediana histórica)"
    )
    return {
        "spread_actual_bp": float(sn),
        "p10": float(vals[0]),
        "p50": float(vals[2]),
        "p90": float(vals[-1]),
        "percentil": float(pc),
        "interpretacion": interpretacion,
        "n_hist": int(row["n"]),
    }


def recommend_pricing(c) -> pd.DataFrame:
    """Genera tabla de recomendación de pricing por plazo, anclada en peer pricing."""
    pricing = issuance_pricing_summary(c)
    # Filtrar a bonos largos (>= 2y) y notas corporativas
    long_pricing = pricing[
        pricing["plazo_bucket"].isin(["~2y", "~3y", "5y", "7-10y", "10y+"])
        & pricing["instrumento"].isin(["BONOS", "NOTAS CORPORATIVAS"])
    ]
    return long_pricing


def mercantil_holding_anchor(c) -> pd.DataFrame:
    """Programa de Mercantil Holding (matriz) — bonos 5y al 7% recurrentes."""
    q = """
    SELECT nemotecnico, isin, fechaEmision_d, fechaVencimiento_d,
           cupon_decimal*100 cupon_pct,
           plazo_original_anos plazo,
           montoSerie/1e6 serie_mm, montoColocado/1e6 coloc_mm,
           CASE WHEN montoSerie > 0 THEN montoColocado/montoSerie*100 ELSE NULL END pct_coloc
    FROM instruments
    WHERE emisor = 'MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.'
      AND instrumento = 'BONOS'
      AND es_tasa_fija = TRUE
    ORDER BY fechaEmision_d DESC
    """
    return c.execute(q).df()


def mercantil_vcn_history(c) -> pd.DataFrame:
    """Programa VCN de Mercantil Banco — cómo ha evolucionado el cupón."""
    q = """
    SELECT fechaEmision_d, nemotecnico,
           cupon_decimal*100 cupon_pct,
           plazo_original_anos plazo,
           montoSerie/1e6 serie_mm, montoColocado/1e6 coloc_mm
    FROM instruments
    WHERE emisor = 'MERCANTIL BANCO, S.A.'
      AND es_tasa_fija = TRUE
      AND cupon_decimal > 0
    ORDER BY fechaEmision_d DESC
    """
    return c.execute(q).df()


def issuance_size_distribution(c) -> pd.DataFrame:
    """Distribución de tamaños de emisión de bancos peer en último año por plazo."""
    cal = primary_market_calendar(c, lookback_days=730)
    cal = cal[cal["instrumento"].isin(["BONOS", "NOTAS CORPORATIVAS"])]
    cal["plazo_bucket"] = pd.cut(
        cal["plazo"], bins=[0, 1.5, 2.5, 4, 6, 100],
        labels=["≤1.5y", "~2y", "~3y", "5y", "7y+"],
    )
    g = cal.groupby("plazo_bucket", observed=True).agg(
        n_emisiones=("nemotecnico", "count"),
        n_emisores=("emisor", "nunique"),
        monto_min_mm=("serie_mm", "min"),
        monto_p25_mm=("serie_mm", lambda s: s.quantile(0.25)),
        monto_median_mm=("serie_mm", "median"),
        monto_p75_mm=("serie_mm", lambda s: s.quantile(0.75)),
        monto_max_mm=("serie_mm", "max"),
        monto_total_mm=("serie_mm", "sum"),
    ).reset_index()
    return g
