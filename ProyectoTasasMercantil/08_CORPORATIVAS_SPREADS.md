# 08 · Estudio mensual de spreads corporativos

Capítulo transversal al reporte. Lo agregaste como punto importante: para
directivos del grupo, **dónde están los spreads corporativos** es tan relevante
como la curva soberana. Aquí está más resumido que el estudio standalone de
Panamá (que sigue existiendo en `credito_Panama`), pero cubriendo más regiones.

## Pregunta que debe responder cada mes

> "¿Cómo cotizan los spreads corporativos hoy por región, calificación y plazo,
> y dónde está cada bucket vs su historia 5Y?"

## Entregable

**1 lámina** dentro del deck principal + **sección con tabla pivot interactiva**
en el HTML.

### Tabla canónica del deck

| Región | Rating | Plazo | Yield mediana | Spread vs benchmark (bps) | Percentil 5Y | Movimiento mes (bps) |
|---|---|---|---:|---:|---:|---:|
| USA IG | A | 3–5Y | x.xx% | xxx | p_xx | ±xx |
| USA IG | BBB | 3–5Y | | | | |
| USA HY | BB | 3–5Y | | | | |
| USA HY | B | 3–5Y | | | | |
| EM USD | BBB | 5–10Y | | | | |
| EM USD | BB | 5–10Y | | | | |
| LatAm USD | BBB | 5–10Y | | | | |
| LatAm USD | BB | 5–10Y | | | | |
| Panamá | (proxy AAA-Sov) | 5–10Y | | | | |
| Panamá | (proxy BBB-Corp) | 3–5Y | | | | |

Color: verde si percentil > 75 (caro vs historia), rojo si percentil < 25
(barato vs historia), gris medio si 25–75.

### Plus gráficos (1–2 por mes)

- **Heat map** región × rating con percentil.
- **Time series** 12 meses de los 2–3 buckets que más se movieron este mes.

## Dimensiones

**Regiones / mercados cubiertos:**
- USA IG (Investment Grade) — índice referente: ICE BofA C0A0 y subíndices.
- USA HY (High Yield) — índice ICE BofA H0A0 y subíndices.
- EM USD Aggregate — JPMorgan EMBI Global Diversified / CEMBI Broad.
- LatAm USD — subíndices CEMBI Latam.
- Panamá — construido en `credito_Panama` (Latinex), enchufado.
- (Opcional Fase 5+) Venezuela USD — bonos VEN/PDVSA en default, no se reporta
  yield, solo price.

**Buckets de calificación:**
- AAA/AA+, AA, A, BBB, BB, B, CCC.
- Para Panamá usamos los proxies de crédito ya construidos.

**Buckets de plazo:**
- 0–1Y, 1–3Y, 3–5Y, 5–10Y, 10Y+.

**Benchmark para el spread:**
- USA: UST mismo plazo.
- EM USD: UST mismo plazo.
- LatAm USD: UST mismo plazo.
- Panamá local: para deuda en USD también vs UST; para deuda en balboas/USD
  panameño usamos curva Panamá soberano.

## Mecánica de cálculo

Para cada `(region, rating_bucket, tenor_bucket, as_of_date)`:

1. Tomar **yield** de la fuente principal (índice si existe, agregado de bonos si
   tenemos universe).
2. Tomar **yield benchmark** (UST mismo plazo).
3. `spread_bps = (yield − yield_benchmark) × 100`.
4. Para el **percentil**: usar serie histórica de 5 años (1,260 días hábiles) del
   `spread_bps` del mismo `(region, rating, plazo)`. Si la serie no tiene 5 años
   completos, declarar "n días" en nota.
5. `movimiento_mes_bps = spread_bps(t) - spread_bps(t-1m)`.

## Reglas de transparencia

Cada celda en la tabla del deck linkea (en el HTML) a:
- Fuente exacta del yield (índice o cálculo).
- Número de instrumentos detrás del agregado.
- Si la celda tiene `n < umbral` (ej. < 5 bonos para EM custom), se sombrea y
  pone `(n=X)` al lado.

## Pendientes operativos

Para que la tabla esté lista en el primer corte (2026-01 backfill):

- [ ] Confirmar acceso vía Bloomberg a los subíndices ICE BofA por rating y
      plazo (la mayoría son `=BDP("C0A1 Index","INDEX_YIELD_TO_WORST")`).
- [ ] Confirmar acceso a CEMBI subindices (si no, usar Bloomberg EM USD
      Aggregate como sustituto).
- [ ] Construir la tabla `credit_spreads` (ver `02_MODELO_DATOS.md`) y
      pipeline de carga desde la plantilla Bloomberg.
- [ ] Hardcode de los benchmarks UST por bucket de plazo (matching nominal:
      0–1Y → UST 1Y; 1–3Y → UST 2Y; 3–5Y → UST 5Y; 5–10Y → UST 7Y o 10Y;
      10Y+ → UST 30Y — a confirmar convención).

## Diferencia con el estudio standalone de Panamá

| | Estudio Panamá (existente) | Capítulo Corporativas (este) |
|---|---|---|
| Universo | bonos individuales Panamá Latinex | índices agregados multi-región |
| Granularidad | trade-by-trade YTM | yield mediano del índice |
| Frecuencia | diaria | mensual |
| Audiencia | analista de renta fija | directivo |
| Tamaño en deck | reporte standalone PDF | 1 lámina |

El estudio Panamá sigue vivo y se actualiza independiente. La lámina corporativa
del reporte mensual **referencia** sus números (en la fila "Panamá") sin
duplicar cálculo.
