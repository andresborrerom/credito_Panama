# 02 · Modelo de datos

Una sola base de datos por proyecto, multifuente, idempotente, con snapshots
versionados que permiten reconstruir cualquier corte pasado sin look-ahead bias.

## Decisiones de fondo

1. **Dos fechas por fila, siempre.**
   - `as_of_date`: la fecha a la que se refiere el dato (ej. UST 10Y al cierre del 30-abr-2026).
   - `snapshot_date`: la fecha en que fue extraído de la fuente. Para un dato vivo de hoy son iguales; para un dato histórico cargado retroactivamente, `snapshot_date > as_of_date`.
   - Para **expectativas** (FedWatch, dot plot, futuros SOFR), `as_of_date` es la fecha del trading day y `snapshot_date` es cuándo lo capturamos. La expectativa del 31-ene-2026 sobre el futuro **debe** registrarse con `as_of_date = 2026-01-31`, independientemente de cuándo se capturó.
2. **Unidad básica:** `(country, instrument, tenor, as_of_date)`. Cualquier query del deck se reduce a un join de esto contra el calendario de cortes.
3. **Formato de almacenamiento:** parquet por tabla en `credito_panama/data/external/tasas_mercantil/` + opcionalmente espejo en SQLite si conviene para queries.
4. **Idempotencia:** correr el ETL dos veces con los mismos inputs deja la base igual. Clave única en cada tabla.
5. **Inmutabilidad por corte:** los datos de un corte cerrado no se modifican; las correcciones se publican como nuevas filas con `snapshot_date` posterior y bandera `is_correction = true`.

---

## Tablas

### `rates_policy` — tasas de política monetaria

| col | tipo | notas |
|---|---|---|
| `country` | str | ISO-2: US, EU, GB, JP, CN, BR, MX, CO, PA, VE |
| `central_bank` | str | FED, ECB, BOE, BOJ, PBOC, BCB, BANXICO, BANREP, BCV |
| `rate_name` | str | FED_FUNDS_UPPER, FED_FUNDS_LOWER, IORB, ON_RRP, ECB_DFR, ECB_MRO, BCV_OVN, etc. |
| `as_of_date` | date | día efectivo |
| `value` | float | en porcentaje (5.25, no 0.0525) |
| `source` | str | FRED, BBG, BCV_WEB |
| `snapshot_date` | date | |
| `is_correction` | bool | default false |

PK: `(central_bank, rate_name, as_of_date, snapshot_date)`.

---

### `rates_money_market` — tasas overnight y cortas

| col | tipo |
|---|---|
| `country` | str |
| `instrument` | str (SOFR, EFFR, ESTR, SONIA, TONA, etc.) |
| `tenor_days` | int (1, 30, 90, 180, 365) |
| `tenor_label` | str (ON, 1M, 3M, 6M, 12M) |
| `as_of_date` | date |
| `value` | float |
| `source` | str |
| `snapshot_date` | date |

PK: `(instrument, tenor_days, as_of_date, snapshot_date)`.

---

### `yield_curve` — puntos de curva soberana / corporativa

| col | tipo |
|---|---|
| `curve_id` | str (UST, BUND, GILT, JGB, BRL_GOV, MXN_GOV, COP_GOV, PAN_SOV, EM_USD_BBB, ICE_BOFA_C0A0, ...) |
| `country` | str |
| `currency` | str |
| `tenor_label` | str (1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y, ...) |
| `tenor_years` | float |
| `as_of_date` | date |
| `yield` | float (porcentaje) |
| `source` | str |
| `snapshot_date` | date |

PK: `(curve_id, tenor_label, as_of_date, snapshot_date)`.

Vista materializada por corte: `curve_snapshot_<YYYY-MM>` que contiene las 3 curvas
canónicas (cierre año anterior, cierre mes anterior, cierre mes en curso) por
`curve_id`.

---

### `sofr_futures` — strip de futuros SOFR (CME SR3)

| col | tipo |
|---|---|
| `contract_code` | str (ej. SR3M2026, SR3U2026) |
| `expiry_month` | date (1er día del mes de expiración, IMM date después) |
| `as_of_date` | date |
| `price` | float (100 - implied yield) |
| `implied_rate` | float (porcentaje) |
| `open_interest` | int nullable |
| `source` | str |
| `snapshot_date` | date |

PK: `(contract_code, as_of_date, snapshot_date)`.

Mínimo recomendado: los **próximos 8 vencimientos trimestrales** en cada `as_of_date`.

---

### `policy_expectations` — probabilidades implícitas por reunión

| col | tipo |
|---|---|
| `central_bank` | str (FED, ECB, BOE) |
| `meeting_date` | date |
| `decision_bps` | int (cambio en bps respecto a la tasa vigente: -50, -25, 0, +25, +50) |
| `prob` | float (0–1) |
| `as_of_date` | date |
| `source` | str (CME_FEDWATCH, BBG_WIRP) |
| `snapshot_date` | date |

PK: `(central_bank, meeting_date, decision_bps, as_of_date, snapshot_date)`.

Constraint lógico: sum(prob) ≈ 1 por `(central_bank, meeting_date, as_of_date)`.

---

### `dot_plot` — proyecciones SEP de la Fed

| col | tipo |
|---|---|
| `release_date` | date (4 al año) |
| `horizon` | str (YE_2026, YE_2027, YE_2028, LONGER_RUN) |
| `member_id` | str (anonimizado por SEP) |
| `projected_rate` | float |
| `snapshot_date` | date |

PK: `(release_date, horizon, member_id)`.

---

### `fx_rates`

| col | tipo |
|---|---|
| `pair` | str (EURUSD, USDJPY, USDBRL, USDMXN, USDCOP, USDVES_OFFICIAL, USDVES_PARALELO_AVG, ...) |
| `tenor` | str (SPOT, 1M, 3M, 6M, 1Y, NDF_1M, ...) |
| `as_of_date` | date |
| `value` | float |
| `source` | str |
| `snapshot_date` | date |

PK: `(pair, tenor, as_of_date, snapshot_date)`.

---

### `credit_spreads`

| col | tipo |
|---|---|
| `index_id` | str (EMBI_GLOBAL, EMBI_LATAM, EMBI_PANAMA, CEMBI_LATAM, ICE_C0A0, ICE_C0A1_AA, ICE_C0A2_A, ICE_C0A3_BBB, H0A1_BB, H0A2_B, ...) |
| `tenor_bucket` | str (0_1Y, 1_3Y, 3_5Y, 5_10Y, 10Y_PLUS, ALL) |
| `rating_bucket` | str (AAA, AA, A, BBB, BB, B, CCC, ALL) |
| `as_of_date` | date |
| `yield` | float nullable |
| `spread_bps` | float nullable |
| `source` | str |
| `snapshot_date` | date |

PK: `(index_id, tenor_bucket, rating_bucket, as_of_date, snapshot_date)`.

---

### `venezuela_local` — cifras BCV específicas

| col | tipo |
|---|---|
| `metric` | str (M2_BS, BASE_MONETARIA_BS, ENCAJE_LEGAL_PCT, TASA_ACTIVA_MAX_PCT, TASA_PASIVA_PCT, INTERVENCION_FX_BCV_USD, ...) |
| `as_of_date` | date |
| `value` | float |
| `unit` | str (BS, USD, PCT) |
| `source` | str |
| `snapshot_date` | date |

PK: `(metric, as_of_date, snapshot_date)`.

---

### `report_messages` — mensajes narrativos por lámina

| col | tipo |
|---|---|
| `report_month` | str (YYYY-MM) |
| `fase` | int (1–5) o `'CORP'` |
| `lamina` | int (orden dentro de la fase) |
| `orden_bullet` | int |
| `bullet` | text |
| `autor` | str (ANDRES, CAMILO, CLAUDE, JLG, …) |

PK: `(report_month, fase, lamina, orden_bullet)`.

Este es el insumo "narrativo" que entra al render del deck. Editable por humanos.

---

### `cortes` — calendario de cortes y metadata

| col | tipo |
|---|---|
| `report_month` | str (YYYY-MM), PK |
| `as_of_date` | date (último día hábil del mes) |
| `t_plus_3_date` | date |
| `status` | str (BACKFILL, EN_CURSO, FIRMADO) |
| `signed_by` | str nullable |
| `signed_at` | timestamp nullable |
| `notes` | text |

---

## Backtesting honesto (sin look-ahead bias)

**Problema:** si queremos backtestear el modelo predictivo de tasas, en cada
`as_of_date` el modelo debe ver **exactamente** los datos que existían ese día —
no los datos como se ven hoy.

**Por qué importa para nosotros:**
- Las **revisiones** de Fed Funds, dot plots y SEP son frecuentes.
- Las series de FRED a veces se revisan retroactivamente (ej. estimaciones de
  inflación que se refinan meses después).
- La curva implícita en SOFR futures cambia cada día y no se puede recuperar de
  un snapshot único.

**Cómo lo hacemos:**
1. Para cada `as_of_date` en el backfill, capturamos el snapshot histórico
   apropiado. Bloomberg permite recuperar precios históricos de futuros, tasas
   implícitas y FedWatch del día — usamos eso.
2. Cada fila guarda `(as_of_date, snapshot_date)`. Las queries del modelo se
   hacen siempre con `WHERE snapshot_date <= as_of_date + INTERVAL '3 days'`
   (T+3 es nuestra ventana de presentación, así que ese es el límite legítimo).
3. **Revisiones posteriores se guardan como filas nuevas**, no sobreescriben.
4. Para datos públicos (FRED), preferimos endpoints con `realtime_start /
   realtime_end` para evitar el efecto de revisiones.

**Test mínimo del pipeline antes de cerrar un corte:**
```
SELECT COUNT(*)
FROM yield_curve
WHERE as_of_date = '2026-01-30'
  AND snapshot_date > '2026-02-02'
  AND is_correction = false;
-- debe ser 0 para el corte de enero
```

---

## Reglas de extracción

- Cierre = **último día hábil del mes** (US calendar) → `as_of_date` del corte.
- Si el día cae feriado en alguna jurisdicción específica (ej. Año Nuevo Chino para PBoC), usar último día hábil anterior **de esa jurisdicción**; documentar en `cortes/YYYY-MM/notas.md`.
- Las series intramensuales se almacenan a **frecuencia diaria** (no recortar a fin de mes en la extracción — el recorte se hace al renderizar).

---

## Capa de queries: `src/tasas_mercantil/queries.py`

Funciones canónicas (a implementar):

```
get_curve(curve_id, as_of_date)               -> DataFrame[tenor, yield]
get_rate_series(instrument, from_date, to_date) -> DataFrame[as_of_date, value]
get_policy_path_implied(as_of_date)           -> DataFrame[meeting_date, implied_rate]
get_fedwatch(as_of_date, meeting_date)         -> DataFrame[decision_bps, prob]
get_credit_spread(index_id, rating, tenor, from_date, to_date)
get_fx(pair, from_date, to_date)
get_corte_metadata(report_month)
```

Todas reciben `as_of_date` o `report_month` y nunca leen del futuro.
