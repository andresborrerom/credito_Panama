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


# =================== TIER 2 SUB 10Y — NUEVO ANÁLISIS PARA v3 ============== #

def t2_premium_components_estimate() -> dict:
    """Componentes del premium Tier 2 sub 10y vs senior bullet en mercados emergentes.

    Tier 2 es MENOS riesgoso que AT1 (no loss-absorption, no cupón discrecional,
    no perpetuidad), pero MÁS riesgoso que senior (subordinación + plazo más largo).

    ACTUALIZACIÓN: T2 panameño bajo SBP Acuerdo 1-2015 NO requiere write-down
    contractual (solo subordinación legal en liquidación), a diferencia del
    T2 europeo bajo Basilea III estricto. Esto reduce el premium de iliquidez
    y subordinación vs benchmarks internacionales.

    ACTUALIZACIÓN 2: Multibank emitió T2 doméstico 10y bullet en 2022
    (US$28MM, 3 series, vence 2032). Caja de Ahorros emitió subordinado 10y
    AAA(pan) por US$150MM en 2021. Mercantil NO es primer pionero estricto,
    aunque sí en su tier de rating. Premium first-time se reduce.
    """
    return {
        "subordinacion_t2_vs_senior_bp": (80, 150),  # subordinado a senior/sub ordinaria
        "plazo_10y_vs_5y_bp": (50, 100),             # extension premium
        "iliquidez_sub_panama_bp": (30, 80),         # mercado T2 doméstico delgado
        "first_time_t2_local_market_bp": (10, 25),   # actualizado — Multibank y CA tienen precedente
        "total_t2_10y_vs_senior_5y_bp": (170, 355),
        "midpoint_bp": 263,
    }


def t2_local_precedents() -> list[dict]:
    """Precedentes domésticos de T2 / subordinados largos en Panamá identificados."""
    return [
        {
            "emisor": "Multibank Inc.",
            "fecha": "2022 Q4",
            "monto_mm": 28,
            "plazo_anos": 10,
            "vencimiento": "2032",
            "cupon_pct": None,  # no encontrado en investigación
            "estructura": "Tier 2 puro bullet, 3 series",
            "rating_emision": None,
            "reconocido_como": "T2 (capital secundario)",
            "comentario": "Único T2 doméstico bullet 10y identificado en mercado panameño. Monto modesto sugiere placement privado o demanda limitada.",
            "fuente": "EEFF Multibank 2022",
        },
        {
            "emisor": "Caja de Ahorros",
            "fecha": "dic-2021",
            "monto_mm": 150,
            "plazo_anos": 10,
            "vencimiento": "2031",
            "cupon_pct": None,
            "estructura": "Subordinado a término (T2 o T1 — no confirmado oficial)",
            "rating_emision": "AAA(pan) Fitch",
            "reconocido_como": "Subordinado (status T2 vs T1 ambiguo)",
            "comentario": "Caja de Ahorros es banco estatal AAA(pan). Programa hasta $400MM rotativo. Caso más cercano a T2 bullet 10y doméstico por monto.",
            "fuente": "La Estrella Panamá; Caja de Ahorros disclosures",
        },
        {
            "emisor": "Banesco (Panamá), S.A.",
            "fecha": "may-2022",
            "monto_mm": 78,
            "plazo_anos": "Perpetuo",
            "vencimiento": "2099 (≈perpetuo)",
            "cupon_pct": 7.00,
            "estructura": "AT1 perpetual subordinado (NO T2)",
            "rating_emision": "Estimado BBB+(pan) o BBB(pan)",
            "reconocido_como": "AT1 (capital primario adicional)",
            "comentario": "Capital regulatorio, pero estructura distinta a T2. Sirve como anchor conceptual pero NO direct comparable de pricing.",
            "fuente": "IN-A 2025 Banesco; SMV-541-21",
        },
        {
            "emisor": "BAC International Bank",
            "fecha": "may-2020 (autorización)",
            "monto_mm": "8.4 emitidos / 700 programa",
            "plazo_anos": "Perpetuo",
            "vencimiento": "—",
            "cupon_pct": None,
            "estructura": "AT1 perpetual convertible en acciones",
            "rating_emision": None,
            "reconocido_como": "AT1",
            "comentario": "Programa grande pero ejecución mínima ($8.4MM colocados vs $700MM autorizados).",
            "fuente": "BIB IN-T mar-2025",
        },
    ]


def t2_regulatory_rules_sbp() -> dict:
    """Resumen verificado de reglas T2 bajo SBP Acuerdo 1-2015."""
    return {
        "marco_legal": "Ley Bancaria DE 52-2008 + Acuerdo 1-2015 (texto único 2020) + Acuerdo 3-2016",
        "implementacion_basilea": "Híbrido Basilea II 'plus' — NO Basilea III completo (no TLAC, no write-down contractual obligatorio)",
        "capital_secundario_max_pct_primario": 100,  # T2 ≤ 100% T1
        "coeficiente_total_minimo_pct": 8.0,
        "capital_primario_minimo_pct": 4.0,
        "plazo_t2_minimo_anos": 5,
        "plazo_t2_maximo": "Sin máximo regulatorio (típico 7-10y bullet)",
        "subordinacion_requerida": "Contractualmente subordinado a depósitos y acreedores comunes/senior; senior solo a T1/AT1 y acciones",
        "step_down_pct_por_ano": 20,  # últimos 5 años
        "step_down_anos": 5,
        "loss_absorption_contractual": False,  # CRÍTICO — diferencia con Basilea III europea
        "comentario_loss_absorption": (
            "T2 panameño NO requiere cláusula contractual de write-down ni conversión a acciones. "
            "La absorción de pérdidas opera por subordinación legal en liquidación únicamente. "
            "Esto hace T2 panameño MENOS riesgoso para inversores que un T2 europeo estricto bajo Basilea III."
        ),
        "call_emisor": "Requiere autorización previa SBP; típicamente no antes del año 5; ejercicio no puede deteriorar coeficiente adecuación",
        "step_up_post_call": "No se permiten cláusulas step-up agresivas (criterio supervisor)",
        "diferencia_sub_ordinario_vs_t2": (
            "Un bono subordinado solo computa como T2 si la SBP lo aprueba expresamente al momento de emisión, "
            "verificando subordinación, plazo y step-down. Hay subordinados que no computan."
        ),
        "fuente_acuerdo": "https://supervalores.gob.pa/files/Acuerdos/2015/Acuerdo-1-2015-texto-unico3.pdf",
    }


def mercantil_t2_sub_10y_pricing(
    banesco_anchor: dict,
    diferencial_rating_bp: float = 35,
    prima_first_time_issuer_bp: float = 25,
    prima_morosidad_capital_bank_bp: float = 25,
    prima_capital_recognition_step_down_bp: float = 15,  # premio porque el valor regulatorio decae en últimos 5y
) -> dict:
    """Modelo de pricing para Mercantil Banco Tier 2 sub 10y bullet.

    Dos aproximaciones reconciliadas:

    A) Desde Banesco AT1 anchor (más cercano por ser capital regulatorio):
       Banesco AT1 7% (firm-UW) → clearing real ~7.5-8.0%
       - Premium AT1 vs T2 (loss-absorption + discrecional + perpetuidad): -100 a -200 bp
       - Banesco T2 hipotetico 10y: 5.50% - 7.00%
       - + Diferencial rating Mercantil vs Banesco: +25-35 bp
       - + First-time T2 local + morosidad: +50 bp
       - Mercantil T2 10y target via AT1: 6.25% - 7.85%

    B) Desde Mercantil Holding senior 5y como anchor (escalado):
       Holding senior 5y = 7.00%
       - Bank vs Holding (sub jerarquía): -50 bp (bank más arriba estructuralmente)
       - Sub vs senior dentro del banco: +100-150 bp
       - 10y vs 5y term premium: +75-100 bp
       - Mercantil T2 10y target via Holding: 8.25% - 9.00%

    Consenso ponderado: 7.50% - 8.50%, midpoint ~8.00%
    """
    # Approach A — desde Banesco AT1
    banesco_at1_clearing_low, banesco_at1_clearing_high = banesco_anchor["cupon_clearing_natural"]
    # AT1 → T2 diferencial: T2 es menos riesgoso (no LA, no discrecional, no perpetuo)
    at1_to_t2_low, at1_to_t2_high = 100, 200  # bp menos
    banesco_t2_implicito_low = banesco_at1_clearing_low - at1_to_t2_high / 100  # más bajo
    banesco_t2_implicito_high = banesco_at1_clearing_high - at1_to_t2_low / 100
    # Ajustes Mercantil
    adj = (diferencial_rating_bp + prima_first_time_issuer_bp
           + prima_morosidad_capital_bank_bp + prima_capital_recognition_step_down_bp) / 100
    target_via_banesco_low = banesco_t2_implicito_low + adj
    target_via_banesco_high = banesco_t2_implicito_high + adj

    # Approach B — desde Mercantil Holding senior 5y
    holding_5y = 7.00  # cupón observado consistente Mercantil Holding
    bank_vs_holding = -0.50  # banco regulado mejor que holding
    sub_vs_senior_bp = (100, 150)
    term_5y_to_10y_bp = (75, 100)
    target_via_holding_low = holding_5y + bank_vs_holding + sub_vs_senior_bp[0]/100 + term_5y_to_10y_bp[0]/100
    target_via_holding_high = holding_5y + bank_vs_holding + sub_vs_senior_bp[1]/100 + term_5y_to_10y_bp[1]/100

    # Consenso ponderado (50/50)
    consenso_low = (target_via_banesco_low + target_via_holding_low) / 2
    consenso_high = (target_via_banesco_high + target_via_holding_high) / 2

    return {
        "approach_a_via_banesco_at1": {
            "banesco_at1_clearing_natural": (banesco_at1_clearing_low, banesco_at1_clearing_high),
            "at1_to_t2_descuento_bp": (at1_to_t2_low, at1_to_t2_high),
            "banesco_t2_implicito": (round(banesco_t2_implicito_low, 2), round(banesco_t2_implicito_high, 2)),
            "ajustes_mercantil_bp": diferencial_rating_bp + prima_first_time_issuer_bp + prima_morosidad_capital_bank_bp + prima_capital_recognition_step_down_bp,
            "target": (round(target_via_banesco_low, 2), round(target_via_banesco_high, 2)),
        },
        "approach_b_via_mercantil_holding": {
            "holding_senior_5y": holding_5y,
            "bank_vs_holding_bp": bank_vs_holding * 100,
            "sub_vs_senior_bp": sub_vs_senior_bp,
            "term_5y_to_10y_bp": term_5y_to_10y_bp,
            "target": (round(target_via_holding_low, 2), round(target_via_holding_high, 2)),
        },
        "consenso_t2_10y": (round(consenso_low, 2), round(consenso_high, 2)),
        "con_firm_uw_apretado_25_50bp": (round(consenso_low - 0.50, 2), round(consenso_high - 0.25, 2)),
        "midpoint_target": round((consenso_low + consenso_high) / 2, 2),
    }


def capital_sizing_analysis(
    monto_emision_mm: float,
    capital_actual_mm: float = 450,  # estimado para Mercantil Banco ~$10bn activos
    apr_actual_mm: float = 3500,    # APR (activos ponderados por riesgo)
    car_actual_pct: float = 13.0,   # Capital ratio actual estimado
) -> dict:
    """Modela impacto en ratio de capital y capacidad de crecimiento de crédito.

    Asume parámetros típicos para banco mediano panameño:
    - Activos ~$10bn
    - APR ~35% activos = $3.5bn
    - Capital total ~13% APR = $455MM

    Una emisión T2 añade al numerador del CAR.
    """
    capital_post = capital_actual_mm + monto_emision_mm
    car_post = capital_post / apr_actual_mm * 100
    # Capacidad incremental de crédito a 50% risk weight (corporates de buena calidad)
    apr_extra_capacity = (capital_post - capital_actual_mm) / (car_actual_pct/100)  # mismo ratio
    credito_extra_capacity_50rw = apr_extra_capacity / 0.5  # corporativos investment grade
    credito_extra_capacity_100rw = apr_extra_capacity / 1.0  # corporativos genéricos
    return {
        "monto_emision_mm": monto_emision_mm,
        "capital_pre_mm": capital_actual_mm,
        "capital_post_mm": round(capital_post, 1),
        "car_pre_pct": car_actual_pct,
        "car_post_pct": round(car_post, 2),
        "delta_car_bp": round((car_post - car_actual_pct) * 100, 0),
        "credito_extra_capacity_50rw_mm": round(credito_extra_capacity_50rw, 0),
        "credito_extra_capacity_100rw_mm": round(credito_extra_capacity_100rw, 0),
    }


def t2_vs_at1_decision_matrix() -> list[dict]:
    """Tabla de decisión Tier 2 vs AT1 para Mercantil."""
    return [
        {
            "criterio": "Costo (cupón estimado)",
            "t2_sub_10y": "7.50-8.50%",
            "at1_perpetuo": "8.50-9.50%",
            "ganador": "T2",
        },
        {
            "criterio": "Capital regulatorio (qué cuenta)",
            "t2_sub_10y": "Tier 2 (total capital)",
            "at1_perpetuo": "Tier 1 (capital primario)",
            "ganador": "AT1 si necesitan Tier 1 específicamente",
        },
        {
            "criterio": "Loss-absorption / write-down",
            "t2_sub_10y": "No requerido",
            "at1_perpetuo": "Sí — write-down si CET1 baja de trigger",
            "ganador": "T2 (menos riesgo accionistas)",
        },
        {
            "criterio": "Cupón discrecional",
            "t2_sub_10y": "Obligatorio (default si no se paga)",
            "at1_perpetuo": "Discrecional (puede saltarse sin default)",
            "ganador": "AT1 (más flexibilidad para el banco)",
        },
        {
            "criterio": "Deducibilidad fiscal de intereses",
            "t2_sub_10y": "Sí (intereses)",
            "at1_perpetuo": "Discutible (puede ser tratado como dividendo)",
            "ganador": "T2 (mejor tax shield)",
        },
        {
            "criterio": "Step-down de reconocimiento",
            "t2_sub_10y": "Sí — pierde 20%/año en últimos 5y",
            "at1_perpetuo": "No (mientras esté vivo)",
            "ganador": "AT1 (capital permanente)",
        },
        {
            "criterio": "Plazo",
            "t2_sub_10y": "10 años bullet",
            "at1_perpetuo": "Perpetuo con call (típico año 5)",
            "ganador": "T2 (define exit)",
        },
        {
            "criterio": "Base inversora",
            "t2_sub_10y": "AFP, aseguradoras selectas, bancas privadas",
            "at1_perpetuo": "Más restringida (algunas AFP excluyen AT1)",
            "ganador": "T2 (más demanda potencial)",
        },
        {
            "criterio": "Aprobación regulatoria",
            "t2_sub_10y": "Más simple (T2 ordinario)",
            "at1_perpetuo": "Más estricta (revisión SBP sobre triggers)",
            "ganador": "T2 (menos fricción)",
        },
        {
            "criterio": "Mercado doméstico Panamá",
            "t2_sub_10y": "Sin precedente claro (Mercantil pionero)",
            "at1_perpetuo": "Un precedente (Banesco 2022)",
            "ganador": "AT1 (más fácil pre-marketing)",
        },
    ]


def issuance_program_projection(
    monto_total_programa_mm: float = 100,
    monto_serie_a_mm: float = 30,
    frecuencia_meses: int = 4,
    cupon_pct: float = 7.75,
    plazo_anos: int = 10,
) -> dict:
    """Proyecta la cadencia óptima de un programa T2 sub 10y de Mercantil."""
    n_series = int(monto_total_programa_mm // monto_serie_a_mm)
    n_series += 1 if monto_total_programa_mm % monto_serie_a_mm > 0 else 0
    duracion_programa_meses = (n_series - 1) * frecuencia_meses
    interes_anual_serie = monto_serie_a_mm * cupon_pct / 100
    interes_anual_programa_total = monto_total_programa_mm * cupon_pct / 100
    return {
        "monto_total_programa_mm": monto_total_programa_mm,
        "monto_por_serie_mm": monto_serie_a_mm,
        "n_series": n_series,
        "frecuencia_meses_entre_series": frecuencia_meses,
        "duracion_programa_meses": duracion_programa_meses,
        "cupon_pct": cupon_pct,
        "interes_anual_serie_mm": round(interes_anual_serie, 2),
        "interes_anual_programa_total_mm": round(interes_anual_programa_total, 2),
        "intereses_totales_vida_programa_mm": round(interes_anual_programa_total * plazo_anos, 1),
    }

