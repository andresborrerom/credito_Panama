# 01 · Plan y fases del reporte

El reporte mensual cubre **5 fases temáticas** + un **capítulo transversal de spreads
corporativos**. Desde el primer corte el deck debe esbozar las 5 (aunque sea con 1
lámina cada una) y profundizar fase por fase en cortes siguientes.

## Principios de construcción

- **Ventana temporal estándar por corte:** últimos 12 meses corridos + cierre del mes
  anterior + 31-dic del año anterior. Comparación principal vs **mes anterior** y
  contexto vs **12M**.
- **Sin look-ahead:** todo dato presentado en el corte de un mes M debe ser conocible
  a T+3 del cierre de M. Ver `02_MODELO_DATOS.md` § *Backtesting honesto*.
- **1 idea = 1 lámina.** Cada lámina lleva: dato, gráfico, mensaje (bullet de 1 línea).
- **Mensajes clave los escribimos Andrés + Camilo + Claude.** Los analistas no redactan
  narrativa; solo aportan datos.

---

## Fase 1 · USA (tasa de referencia mundial)

Esta fase es la columna vertebral del reporte. Desde el draft 1 va completa.

**Láminas previstas:**

| # | Título | Contenido | Datos | Comparativa |
|---|---|---|---|---|
| 1 | Mensajes clave del mes | 3–5 bullets editoriales | manual | — |
| 2 | Política monetaria USA | Fed Funds target, IORB, ON RRP, BCV decisiones del mes | FRED + Fed | mes ant. + 12M |
| 3 | Tasas de mercado USA | SOFR ON/3M/6M/12M; UST 2y/5y/10y/30y | Bloomberg / FRED | mes ant. + 12M + 31-dic |
| 4 | Curva UST | curva entera 1M–30Y, 3 trazas (cierre año anterior, mes anterior, mes en curso) | US Treasury XML | — |
| 5 | Expectativas Fed | (a) implied path SOFR futures, (b) CME FedWatch por reunión, (c) modelo Mercantil | CME + Bloomberg + modelo propio | mes anterior |
| 6 | Lectura / Implicaciones | narrativa | manual | — |

**Datos no negociables:** Fed Funds upper/lower, SOFR (ON, 3M, 6M, 12M), UST (2y,5y,10y), futuros SR3 (próximos 8 vencimientos), CME FedWatch para las próximas 4 reuniones, próxima reunión FOMC (fecha + consenso).

---

## Fase 2 · Global

**Láminas previstas:** 2–3 láminas resumen.

- Tasas de política de **BCE, BoE, BoJ, PBoC, BCB (Brasil), BanRep (Colombia), Banxico**.
- Curva soberana 10Y de **Alemania, UK, Japón, Brasil, México, Colombia**.
- **FX G10 + LatAm**: EUR, GBP, JPY, BRL, MXN, COP, CLP vs USD; movimiento mes y 12M.
- **EMBI Global + EMBI LatAm** y subíndices (Panamá, Venezuela, Colombia, México).

Énfasis: cómo se compara EM USD vs UST y qué hizo el dólar.

---

## Fase 3 · Panamá

**Láminas previstas:** 2–3 láminas.

Conexión directa con lo ya construido en `credito_Panama` (curva soberana Panamá,
VCN, Letras del Tesoro, hipotecarios, corporativos locales). Reusar:

- `src/analytics/curves.py` para la curva soberana Panamá.
- `src/analytics/ratings.py` para proxy de crédito.
- `data/processed/curves_monthly.parquet` para la serie mensual.

**Métricas que el deck debe mostrar:**
- Curva soberana Panamá (corte año anterior, mes anterior, mes en curso).
- **Spread Panamá 10Y vs UST 10Y** y su percentil histórico 5Y.
- VCN 0–1Y, Letras del Tesoro 0–1Y, prima entre ambos.
- Bonos hipotecarios mediana yield, prima vs Tesoro Panamá.
- Hechos relevantes del mes en Latinex (top 5 por monto/tipo).

---

## Fase 4 · Impactos para el Grupo Mercantil

**Láminas previstas:** 1 lámina resumen + 1 lámina por unidad relevante.

Aquí está la traducción "qué significa esto para nosotros". Las unidades del grupo a
considerar (ver `06_GRUPO_MERCANTIL.md` para el mapa completo):

- **Banco Mercantil Venezuela** — costo de fondeo en bolívares, encaje, repricing de
  cartera, FX position.
- **Mercantil Banco Panamá** — costo de fondeo en USD (depósitos a término vs SOFR
  3M), libro de inversiones (sensitivity vs UST 5Y), spread comercial.
- **Mercantil Seguros** — yield del portafolio de inversiones, ALM (duración pasivos
  vs duración portafolio).
- **Wealth Management / Casa de Bolsa** — atractivo relativo de UST vs locales vs EM
  USD para clientes; recomendación de duración.
- **Posición propia / Tesorería del grupo** — hedge book, repricing de activos a tasa
  variable.

**Por ahora no se cargan datos internos.** Esta fase se trabaja con análisis cualitativo
estilo "si UST 10Y subió X bps, el libro de inversiones de la aseguradora con duración
~D sufre ~D·X bps de pérdida de valor". Cuando se autorice cargar datos internos, se
sustituye lo cualitativo por números reales del libro.

---

## Fase 5 · Venezuela

**Láminas previstas:** 2 láminas.

- **Tasas BCV:** tasa de política, encaje, tasa activa / pasiva máxima permitida,
  intervención cambiaria.
- **FX:** Tipo de cambio oficial BCV vs **paralelo** (Monitor Dólar / EnParaleloVzla
  / DolarToday — promedio). Brecha en %, evolución 12M.
- **Liquidez monetaria:** M2, base monetaria.
- **Bonos soberanos VEN/PDVSA defaulteados:** precio de mercado (referencia), no como
  yield porque están en default.

Disclaimer explícito: la tasa paralela no es oficial; se incluye como referencia
de mercado por su uso por parte del sector corporativo.

---

## Capítulo transversal · Spreads corporativos

Pedido adicional. Es una **tabla compacta + 2 gráficos**, recurrente cada mes.

**Estructura de la tabla (1 lámina, formato condensado):**

| Región / Mercado | Calificación | Plazo bucket | Yield (mediana) | Spread vs benchmark | Percentil hist. 5Y |
|---|---|---|---|---|---|
| USA IG | A | 3–5Y | ... | ... | ... |
| USA IG | BBB | 3–5Y | ... | ... | ... |
| USA HY | BB | 3–5Y | ... | ... | ... |
| USA HY | B | 3–5Y | ... | ... | ... |
| EM USD | BBB | 5–10Y | ... | ... | ... |
| EM USD | BB | 5–10Y | ... | ... | ... |
| Panamá | (proxy AAA-Sov) | 5–10Y | ... | ... | ... |
| Panamá | (proxy BBB-Corp) | 3–5Y | ... | ... | ... |
| LatAm USD | varios | 5–10Y | ... | ... | ... |

**Buckets de plazo:** 0–1Y, 1–3Y, 3–5Y, 5–10Y, 10Y+.

**Buckets de rating:** AA+/AAA, A, BBB, BB, B / CCC.

**Fuentes:**
- USA IG/HY: índices ICE BofA (BBG: C0A0, H0A0 y subíndices por rating/plazo).
- EM USD: JPMorgan EMBI, CEMBI; alternativa Bloomberg EM USD Aggregate.
- Panamá: lo nuestro (`curves_monthly`, `trades`).
- LatAm USD: subíndices CEMBI Latam.

Detalle metodológico completo en `08_CORPORATIVAS_SPREADS.md`.

---

## Roadmap de cortes

| Corte | Tipo | Foco principal |
|---|---|---|
| 2026-01 | backfill de informe | construir Fase 1 USA completa; placeholders 2–5 + corporativas |
| 2026-02 | backfill de informe | profundizar Fase 2 Global |
| 2026-03 | backfill de informe | profundizar Fase 3 Panamá |
| 2026-04 | backfill de informe | profundizar Fase 4 Mercantil (cualitativo) |
| 2026-05 | en vivo | primer corte "real" — todas las fases con cierre at-mes |
| 2026-06+ | recurrente | ciclo mensual estable |

Los backfills 2026-01 a 2026-04 son críticos para tener **histórico publicable
del informe** y poder mostrar la ventana 12M completa desde el primer corte
publicado.

## Backfill de DATOS para el modelo (≠ backfill de informes)

**El modelo predictivo se entrena con una serie histórica mucho más larga que
los 5 cortes mensuales del informe**. Esta es una distinción importante:

| | Backfill de informes | Backfill de datos para el modelo |
|---|---|---|
| Propósito | publicar cortes mensuales retroactivos | entrenar y backtestear el modelo Mercantil |
| Ventana | ene 2026 → hoy (5 meses) | **desde 2010 o 2015 → hoy** (10–16 años) |
| Granularidad | mensual (1 snapshot por mes) | diaria |
| Fuente | Bloomberg (plantilla del analista) + scrapers | FRED + ALFRED (vintage) + Bloomberg histórico |
| Almacenamiento | un folder por corte | tablas en `data/external/tasas_mercantil/*.parquet` |

El modelo predictivo necesita **vintage data**: lo que se sabía en cada `as_of_date`
pasada. Eso lo provee FRED ALFRED para macro (CPI, payrolls, GDP) y Bloomberg
histórico para tasas (que **no** se revisan, por lo que el price observable hoy
para una fecha pasada == lo que se observaba ese día). Ver `02_MODELO_DATOS.md`
§ Backtesting honesto y `07_MODELO_PREDICTIVO.md`.

## Ventana temporal por corte (lectura del informe)

Cada corte publicado muestra los siguientes ejes temporales:

- **Year-to-date corrido** — desde 01-ene del año hasta `as_of_date`.
- **Últimos 12 meses corridos** — desde `as_of_date - 12 meses` hasta `as_of_date`. Esta es la ventana principal de los gráficos de series.
- **Comparación con mes anterior** — `as_of_date(mes_anterior)` como referencia para tabla de deltas.
- **Comparación con cierre del año anterior** — 31-dic-(YYYY-1) como referencia para curva (cierre año / mes anterior / mes en curso).

Por lo tanto, para publicar el corte de mayo 2026 necesitamos serie diaria al
menos desde mayo 2025 para los gráficos. El backfill de datos lo provee.
