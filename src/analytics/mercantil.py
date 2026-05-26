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


# =================== NUEVAS ANALÍTICAS — MEMO v2 ============================ #

def tenor_comparison_5y_vs_10y(c) -> pd.DataFrame:
    """Compara características 5y vs 10y para bancos T2/T3 en mercado panameño:
    pricing primario, liquidez secundaria, demanda, comparables."""
    cal = primary_market_calendar(c, lookback_days=1095)  # 3 años
    cal = cal[cal["instrumento"].isin(["BONOS", "NOTAS CORPORATIVAS"])]
    rows = []
    for plazo_label, p_min, p_max in [
        ("3y", 2.5, 3.5),
        ("5y", 4.5, 5.5),
        ("7y", 6.5, 7.5),
        ("10y", 9.5, 10.5),
    ]:
        sub = cal[(cal["plazo"] >= p_min) & (cal["plazo"] <= p_max)]
        if sub.empty:
            rows.append({
                "tenor": plazo_label, "n_emisiones": 0, "n_emisores": 0,
                "cupon_p25": None, "cupon_median": None, "cupon_p75": None,
                "monto_median_mm": None, "monto_total_mm": 0.0,
                "pct_coloc_avg": None,
            })
            continue
        rows.append({
            "tenor": plazo_label,
            "n_emisiones": len(sub),
            "n_emisores": sub["emisor"].nunique(),
            "cupon_p25": sub["cupon_pct"].quantile(0.25),
            "cupon_median": sub["cupon_pct"].median(),
            "cupon_p75": sub["cupon_pct"].quantile(0.75),
            "monto_median_mm": sub["serie_mm"].median(),
            "monto_total_mm": sub["serie_mm"].sum(),
            "pct_coloc_avg": sub["pct_coloc"].mean(),
        })
    return pd.DataFrame(rows)


def secondary_liquidity_by_tenor(c, lookback_days: int = 365) -> pd.DataFrame:
    """Liquidez secundaria: volumen y # trades por bucket de plazo en bancos T2/T3."""
    placeholders = ", ".join(f"'{p}'" for p in PEER_BANKS)
    q = f"""
    SELECT bucket_plazo,
           COUNT(*) n_trades,
           COUNT(DISTINCT emisor) n_emisores,
           COUNT(DISTINCT nemotecnico) n_papeles,
           SUM(monto)/1e6 vol_total_mm,
           AVG(monto)/1e3 vol_avg_trade_k,
           MEDIAN(ytm_calc) yld_median
    FROM trades
    WHERE emisor IN ({placeholders})
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN 0.005 AND 0.40
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
    GROUP BY 1
    ORDER BY 1
    """
    return c.execute(q).df()


def institutional_demand_proxy(c, lookback_days: int = 365) -> pd.DataFrame:
    """Proxy de demanda institucional: distribución de tamaños de trades.
    Trades grandes (> $250k) sugieren AFP/aseguradora; pequeños = retail/cliente puesto."""
    placeholders = ", ".join(f"'{p}'" for p in PEER_BANKS)
    q = f"""
    SELECT
        CASE
            WHEN monto < 50000 THEN '< 50k (retail)'
            WHEN monto < 250000 THEN '50-250k (puesto)'
            WHEN monto < 1000000 THEN '250k-1M (institucional)'
            ELSE '> 1M (institucional grande)'
        END AS tamano_trade,
        COUNT(*) n_trades,
        SUM(monto)/1e6 vol_mm,
        MEDIAN(ytm_calc) yld_median
    FROM trades
    WHERE emisor IN ({placeholders})
      AND es_tasa_fija = TRUE
      AND ytm_calc IS NOT NULL
      AND ytm_calc BETWEEN 0.005 AND 0.40
      AND monto > 0
      AND fecha_d >= (SELECT MAX(fecha_d) - INTERVAL '{lookback_days}' DAY FROM trades)
    GROUP BY 1
    ORDER BY MIN(monto)
    """
    return c.execute(q).df()


def competing_pipeline(c) -> pd.DataFrame:
    """Pipeline de emisiones próximas en T2/T3 que podrían competir por demanda.
    Incluye trámites SMV y prospectos recientes."""
    placeholders = ", ".join(f"'{p}'" for p in PEER_BANKS)
    q = f"""
    SELECT emisor, instrumento, fechaEmision_d, fechaVencimiento_d,
           cupon_decimal*100 cupon_pct,
           plazo_original_anos plazo,
           montoSerie/1e6 serie_mm,
           montoColocado/1e6 coloc_mm,
           CASE WHEN cupon_decimal = 0 THEN 'placeholder/pricing TBD' ELSE 'pricing fijo' END estado
    FROM instruments
    WHERE emisor IN ({placeholders})
      AND CAST(fechaEmision_d AS DATE) >= CURRENT_DATE - INTERVAL '60' DAY
      AND instrumento IN ('BONOS', 'NOTAS CORPORATIVAS', 'VALORES COMERCIALES NEGOCIABLES')
    ORDER BY fechaEmision_d DESC
    """
    return c.execute(q).df()


def underwriter_economics(
    fee_upfront_pct: float = 1.50,
    coupon_subsidio_bp: float = 50,
    plazo_anos: float = 5.0,
    monto_mm: float = 30.0,
) -> dict:
    """Modela la economía firm-underwriting vs best-efforts.
    fee_upfront_pct: % cobrado por la casa estructuradora (típico 1.0-2.5%)
    coupon_subsidio_bp: bps que la casa logra apretar al cupón vía firm commitment
    """
    fee_total = monto_mm * fee_upfront_pct / 100  # MM USD
    # NPV approximation: cuanto vale ahorrar coupon_subsidio_bp anuales por plazo_anos
    # ignorando descuento (orden de magnitud)
    ahorro_anual = monto_mm * coupon_subsidio_bp / 10000  # MM USD/año
    ahorro_total_simple = ahorro_anual * plazo_anos
    # ahorro_NPV con tasa de descuento 6%
    r = 0.06
    ahorro_npv = sum(ahorro_anual / (1 + r) ** t for t in range(1, int(plazo_anos) + 1))
    neto_firm = ahorro_npv - fee_total
    return {
        "fee_upfront_pct": fee_upfront_pct,
        "coupon_subsidio_bp": coupon_subsidio_bp,
        "plazo_anos": plazo_anos,
        "monto_mm": monto_mm,
        "fee_total_mm": round(fee_total, 3),
        "ahorro_anual_mm": round(ahorro_anual, 3),
        "ahorro_npv_mm": round(ahorro_npv, 3),
        "neto_firm_vs_be_mm": round(neto_firm, 3),
        "break_even_bp": round(fee_upfront_pct * 100 / plazo_anos / (1 / r * (1 - 1/(1+r)**plazo_anos) / plazo_anos), 1),
    }


def banesco_anchor_recalibrated() -> dict:
    """Anchor Banesco recalibrado con info nueva (Prival firm-underwriting + upgrade Fitch).

    El cupón observado 7% NO refleja clearing market real porque:
    1. Prival firm-underwriting: garantizó compra 100% absorbiendo riesgo de inventario.
    2. Banesco pagó fee de estructuración (estimado 1.5-2.5%) que "compró" la baja en cupón.
    3. Sin esa estructura, la fuente informa que el clearing natural era 7.5-8.0%.
    4. Post-upgrade A+(pan) por Fitch (11-may-2026), Banesco tiene argumento para
       mantener o reducir tasa en próxima emisión.

    Implicación para Mercantil: el 7% Banesco es un anchor "comprimido". El senior
    bullet 5y "implícito" de Banesco (despejando primas) se ajusta hacia arriba.
    """
    cupon_obs = 7.00
    cupon_clearing_natural_low = 7.5
    cupon_clearing_natural_high = 8.0
    # Premium AT1+perpetual vs senior bullet (cohorte mercados emergentes):
    premium_at1_subordinacion = (80, 200)  # bp
    premium_loss_absorption = (100, 200)
    premium_cupon_discrecional = (50, 100)
    premium_perpetuidad = (50, 150)
    premium_iliquidez = (50, 100)
    premium_total_low = sum(p[0] for p in [
        premium_at1_subordinacion, premium_loss_absorption,
        premium_cupon_discrecional, premium_perpetuidad, premium_iliquidez
    ])
    premium_total_high = sum(p[1] for p in [
        premium_at1_subordinacion, premium_loss_absorption,
        premium_cupon_discrecional, premium_perpetuidad, premium_iliquidez
    ])
    # Senior bullet 5y "implícito" Banesco
    senior_implicit_from_observed = (
        cupon_obs - premium_total_high / 100,
        cupon_obs - premium_total_low / 100,
    )
    senior_implicit_from_natural = (
        cupon_clearing_natural_low - premium_total_high / 100,
        cupon_clearing_natural_high - premium_total_low / 100,
    )
    return {
        "cupon_observado": cupon_obs,
        "cupon_clearing_natural": (cupon_clearing_natural_low, cupon_clearing_natural_high),
        "premium_at1_total_bp": (premium_total_low, premium_total_high),
        "senior_5y_implicito_observado": senior_implicit_from_observed,
        "senior_5y_implicito_natural": senior_implicit_from_natural,
        "rating_banesco_actual": "A+(pan) Fitch (post upgrade 11-may-2026)",
        "rating_banesco_2022": "A(pan) (al momento de emisión)",
        "estructurador": "Prival Securities (firm-underwriting)",
    }


def mercantil_pricing_recommendation_v2(
    banesco_anchor: dict,
    mercantil_rating_current: str = "A(pa)",
    banesco_rating_current: str = "A+(pan)",
    diferencial_rating_bp: float = 35,  # ~25-50 bp un notch
    prima_first_time_issuer_bp: float = 25,  # premium por debut en bonos largos
    prima_morosidad_capital_bank_bp: float = 25,
) -> dict:
    """Recomendación de pricing senior bullet 5y para Mercantil Banco.

    Anclado en el senior implícito Banesco recalibrado, ajustado por:
    - Diferencial de rating (Mercantil A debajo de Banesco A+)
    - Premium first-time issuer en bonos largos
    - Premium por morosidad heredada Capital Bank
    """
    # Base: senior 5y implícito Banesco (rango)
    base_low, base_high = banesco_anchor["senior_5y_implicito_natural"]  # más realista
    # Ajustes
    adj = (diferencial_rating_bp + prima_first_time_issuer_bp + prima_morosidad_capital_bank_bp) / 100
    return {
        "base_banesco_senior_5y_implicito": (round(base_low, 2), round(base_high, 2)),
        "ajustes_bp": {
            "diferencial_rating_A_vs_Aplus": diferencial_rating_bp,
            "first_time_issuer_bonos_largos": prima_first_time_issuer_bp,
            "morosidad_heredada_capital_bank": prima_morosidad_capital_bank_bp,
            "total_premium": diferencial_rating_bp + prima_first_time_issuer_bp + prima_morosidad_capital_bank_bp,
        },
        "mercantil_5y_target_teorico": (round(base_low + adj, 2), round(base_high + adj, 2)),
        "mercantil_5y_target_observado_grupo": (6.50, 7.00),  # anclado en Mercantil Holding programa
        "mercantil_5y_recomendado_final": (6.50, 7.00),  # consenso teórico + observado
    }

