"""Construcción de curvas y métricas para visualización y reporte."""

from __future__ import annotations

import pathlib

import duckdb
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
TRADES_PQ = ROOT / "data" / "processed" / "trades.parquet"
UST_PQ = ROOT / "data" / "processed" / "ust_yields.parquet"
INST_PQ = ROOT / "data" / "processed" / "instruments.parquet"

YIELD_FLOOR = 0.005   # 0.5% mínimo creíble
YIELD_CEILING = 0.40  # 40% máximo creíble

BUCKET_ORDER = ["0-1y", "1-3y", "3-5y", "5-7y", "7-10y", "10y+"]
BUCKET_MIDPOINTS = {"0-1y": 0.5, "1-3y": 2, "3-5y": 4, "5-7y": 6, "7-10y": 8.5, "10y+": 12}

INSTR_GROUPS = {
    "Tesoro Panamá": ["LETRAS DEL TESORO", "NOTAS DEL TESORO", "BONOS DEL TESORO"],
    "Bonos Corp.": ["BONOS"],
    "Bonos Hipotecarios": ["BONOS HIPOTECARIOS"],
    "VCN": ["VALORES COMERCIALES NEGOCIABLES"],
    "Notas Corp.": ["NOTAS CORPORATIVAS"],
}


def con():
    c = duckdb.connect()
    # Cast fecha_d a DATE para soportar aritmética de intervalos
    c.execute(
        f"""CREATE VIEW trades AS
        SELECT * EXCLUDE (fecha_d), CAST(fecha_d AS DATE) AS fecha_d
        FROM read_parquet('{TRADES_PQ}')"""
    )
    c.execute(
        f"""CREATE VIEW ust AS
        SELECT * EXCLUDE (fecha_d), CAST(fecha_d AS DATE) AS fecha_d
        FROM read_parquet('{UST_PQ}')"""
    )
    c.execute(f"CREATE VIEW instruments AS SELECT * FROM read_parquet('{INST_PQ}')")
    return c


def latest_curve(c, window_days: int = 365) -> pd.DataFrame:
    """Curva actual: mediana por (bucket_plazo × instrumento_clase) en ventana reciente."""
    q = f"""
    SELECT bucket_plazo, instrumento_clase, sector,
           COUNT(*) n,
           MEDIAN(ytm_calc) yld,
           QUANTILE_CONT(ytm_calc, 0.25) p25,
           QUANTILE_CONT(ytm_calc, 0.75) p75,
           SUM(monto) volumen_usd
    FROM trades
    WHERE ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{window_days}' DAY FROM trades)
      AND es_tasa_fija = TRUE
      AND bucket_plazo IS NOT NULL
    GROUP BY 1, 2, 3
    """
    return c.execute(q).df()


def monthly_yields(c) -> pd.DataFrame:
    """Mediana mensual por (bucket × instrumento) para histórico."""
    q = f"""
    SELECT
        STRFTIME(fecha_d, '%Y-%m') AS yyyymm,
        DATE_TRUNC('month', fecha_d) AS month_dt,
        bucket_plazo,
        instrumento_clase,
        sector,
        MEDIAN(ytm_calc) yld_median,
        COUNT(*) n
    FROM trades
    WHERE ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
      AND es_tasa_fija = TRUE
      AND bucket_plazo IS NOT NULL
    GROUP BY 1, 2, 3, 4, 5
    HAVING COUNT(*) >= 2
    """
    return c.execute(q).df()


def quarterly_yields(c) -> pd.DataFrame:
    """Mediana trimestral más estable para series largas."""
    q = f"""
    SELECT
        DATE_TRUNC('quarter', fecha_d) AS quarter_dt,
        bucket_plazo,
        instrumento_clase,
        sector,
        MEDIAN(ytm_calc) yld_median,
        COUNT(*) n
    FROM trades
    WHERE ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
      AND es_tasa_fija = TRUE
      AND bucket_plazo IS NOT NULL
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) >= 3
    """
    return c.execute(q).df()


def ust_monthly(c) -> pd.DataFrame:
    q = """
    SELECT
        DATE_TRUNC('month', CAST(fecha_d AS DATE)) AS month_dt,
        AVG(BC_3MONTH) BC_3M,
        AVG(BC_1YEAR) BC_1Y,
        AVG(BC_2YEAR) BC_2Y,
        AVG(BC_5YEAR) BC_5Y,
        AVG(BC_7YEAR) BC_7Y,
        AVG(BC_10YEAR) BC_10Y,
        AVG(BC_30YEAR) BC_30Y
    FROM ust
    WHERE fecha_d IS NOT NULL
    GROUP BY 1
    ORDER BY 1
    """
    return c.execute(q).df()


def percentile_position(c, sector: str | None = None, lookback_days: int = 1825) -> pd.DataFrame:
    """Para cada bucket × instrumento, ¿en qué percentil de la distribución 5y está el yield actual?"""
    where_sector = f"AND sector = '{sector.replace(chr(39), chr(39)*2)}'" if sector else ""
    q = f"""
    WITH hist AS (
        SELECT bucket_plazo, instrumento_clase, ytm_calc, fecha_d
        FROM trades
        WHERE ytm_calc IS NOT NULL
          AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
          AND es_tasa_fija = TRUE
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
          {where_sector}
    ),
    current AS (
        SELECT bucket_plazo, instrumento_clase, MEDIAN(ytm_calc) AS yld_now
        FROM trades
        WHERE ytm_calc IS NOT NULL
          AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
          AND es_tasa_fija = TRUE
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '90' DAY FROM trades)
          {where_sector}
        GROUP BY 1, 2
    )
    SELECT c.bucket_plazo, c.instrumento_clase, c.yld_now,
           QUANTILE_CONT(h.ytm_calc, 0.10) p10,
           QUANTILE_CONT(h.ytm_calc, 0.25) p25,
           QUANTILE_CONT(h.ytm_calc, 0.50) p50,
           QUANTILE_CONT(h.ytm_calc, 0.75) p75,
           QUANTILE_CONT(h.ytm_calc, 0.90) p90,
           COUNT(*) n_hist
    FROM current c
    JOIN hist h USING (bucket_plazo, instrumento_clase)
    GROUP BY 1, 2, 3
    HAVING COUNT(*) >= 20
    """
    return c.execute(q).df()


def percentile_position_spread(
    c,
    sector: str | None = None,
    lookback_days: int = 1825,
    by: str = "rating_tier",  # 'rating_tier' o 'instrumento_clase'
    extra_dim: str = "bucket_plazo",
) -> pd.DataFrame:
    """Versión spread: percentil del SPREAD actual vs distribución 5y."""
    where_sector = f"AND sector = '{sector.replace(chr(39), chr(39)*2)}'" if sector else ""
    q = f"""
    WITH hist AS (
        SELECT {extra_dim}, {by}, spread_bp, fecha_d
        FROM trades
        WHERE spread_bp IS NOT NULL
          AND spread_bp BETWEEN -200 AND 3000
          AND es_tasa_fija = TRUE
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
          {where_sector}
    ),
    current AS (
        SELECT {extra_dim}, {by}, MEDIAN(spread_bp) AS spread_now
        FROM trades
        WHERE spread_bp IS NOT NULL
          AND spread_bp BETWEEN -200 AND 3000
          AND es_tasa_fija = TRUE
          AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '90' DAY FROM trades)
          {where_sector}
        GROUP BY 1, 2
    )
    SELECT c.{extra_dim}, c.{by}, c.spread_now,
           QUANTILE_CONT(h.spread_bp, 0.10) p10,
           QUANTILE_CONT(h.spread_bp, 0.25) p25,
           QUANTILE_CONT(h.spread_bp, 0.50) p50,
           QUANTILE_CONT(h.spread_bp, 0.75) p75,
           QUANTILE_CONT(h.spread_bp, 0.90) p90,
           COUNT(*) n_hist
    FROM current c
    JOIN hist h USING ({extra_dim}, {by})
    GROUP BY 1, 2, 3
    HAVING COUNT(*) >= 20
    """
    return c.execute(q).df()


def cross_ref_matrix(c, lookback_days: int = 90) -> pd.DataFrame:
    """Matriz (rating_tier × bucket_plazo) → spread y yield actuales para bancos."""
    q = f"""
    SELECT rating_tier, bucket_plazo,
           COUNT(*) n,
           MEDIAN(ytm_calc) yld,
           MEDIAN(spread_bp) spread,
           COUNT(DISTINCT emisor) n_emisores
    FROM trades
    WHERE sector = 'Financiero'
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN {YIELD_FLOOR} AND {YIELD_CEILING}
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    """
    return c.execute(q).df()


def universe_summary(c) -> dict:
    n_inst = c.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    n_trades = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    n_ytm = c.execute("SELECT COUNT(*) FROM trades WHERE ytm_calc IS NOT NULL").fetchone()[0]
    date_min, date_max = c.execute(
        "SELECT MIN(fecha_d), MAX(fecha_d) FROM trades"
    ).fetchone()
    n_emisores = c.execute("SELECT COUNT(DISTINCT emisor) FROM instruments").fetchone()[0]
    n_sectores = c.execute(
        "SELECT COUNT(DISTINCT sector) FROM instruments WHERE sector IS NOT NULL"
    ).fetchone()[0]
    return {
        "n_instruments": n_inst,
        "n_trades": n_trades,
        "n_ytm": n_ytm,
        "date_min": str(date_min),
        "date_max": str(date_max),
        "n_emisores": n_emisores,
        "n_sectores": n_sectores,
    }
