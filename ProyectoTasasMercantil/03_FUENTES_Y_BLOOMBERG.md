# 03 · Fuentes y plantilla Bloomberg

## Filosofía

1. **Bloomberg es la fuente primaria** de datos de mercado (tasas, futuros, FX,
   índices de crédito). El analista corre una plantilla Excel `=BDP/=BDS/=BDH` y la
   devuelve.
2. **FRED + US Treasury + CME público** son la fuente de **respaldo** y la fuente
   exclusiva para el backfill de los meses anteriores a que tengamos acceso a
   Bloomberg corriendo el pipeline. Sirven también para cross-check.
3. **BCV y fuentes paralelo Venezuela** se scrapean directo de web (no hay
   alternativa).
4. **Bolívar paralelo:** promediamos al menos 3 fuentes públicas para reducir el
   riesgo de manipulación por una sola.

## Mapa de fuentes por fase

| Fase | Categoría | Fuente principal | Respaldo |
|---|---|---|---|
| 1 | Fed Funds, IORB, ON RRP | BBG (`FDTR Index`, `IOER Index`) / FRED (DFF, IORB) | FRED |
| 1 | SOFR ON/term | BBG (`SOFRRATE Index`, `SOFR1M Index`...) / FRED (SOFR, SOFR30DAYAVG) | FRED |
| 1 | UST curve | BBG (`USGG2YR Index`, ... `USGG30YR`) / US Treasury XML | US Treasury |
| 1 | SOFR futures (SR3) | BBG (`SFRM6 Comdty`, `SFRU6`...) | CME daily settlements (public CSV) |
| 1 | FedWatch implied probs | BBG (`WIRP` analytics) | CME FedWatch website (HTML scrape) |
| 1 | Dot plot SEP | Fed website (PDF cada cuatrimestre) | — |
| 2 | Tasas política globales | BBG | sitios bancos centrales |
| 2 | Curvas soberanas G7/EM | BBG (`GDBR10 Index`, `GUKG10`, `GJGB10`, `GBTPGR10`, ...) | tradingeconomics (último recurso) |
| 2 | FX G10 + LatAm | BBG (`EURUSD Curncy`, `USDBRL`, ...) | FRED H.10 |
| 2 | EMBI / CEMBI | BBG (`JPMECCRE Index`, `JPMCBGBL`, subíndices `JPEIPADV`...) | — |
| 3 | Panamá soberano | ya construido en `credito_Panama` (Latinex) | — |
| 3 | Bonos panameños USD | BBG (`PANAMA X.X MM/YY Govt`) si se requiere precio Bloomberg | Latinex |
| 4 | Datos internos del grupo | **fuera de alcance por ahora** | — |
| 5 | BCV tasas y FX oficial | scraper web BCV | — |
| 5 | Bolívar paralelo | promedio Monitor Dólar VE + EnParaleloVzla + DolarToday | — |
| 5 | Bonos VEN/PDVSA precio | BBG si disponible | dealer runs |
| CORP | ICE BofA indices USA | BBG (`C0A0`, `C0A1`, `C0A2`, `C0A3`, `H0A1`, `H0A2`, `H0A3`) | — |
| CORP | EM USD corporate | BBG CEMBI subindices | — |

## Plantilla Bloomberg `BloombergTemplate_TasasMercantil.xlsx`

✅ **Archivo generado.** Vive en `plantilla_bloomberg/BloombergTemplate_TasasMercantil.xlsx`.
Regenerable corriendo `python3 plantilla_bloomberg/build_bloomberg_template.py`.

Se entrega al analista cada mes. El analista edita una sola celda (`AS_OF` en la
hoja `01_Parametros`), espera que Bloomberg resuelva, y devuelve el `.xlsx` con
valores (ver `99_Envio` adentro del archivo).

**Versión actual:** v0.2 — **76 instrumentos** + 8 futuros SOFR + FedWatch (paste manual). Cambios vs v0.1:
- Agregadas curvas **TIPS real (5Y/10Y/20Y/30Y)** — 4 instrumentos.
- Agregados **breakevens (2Y/5Y/10Y/30Y)** — 4 instrumentos.
- Agregada **curva SOFR OIS swap (2Y/5Y/10Y/30Y)** — 4 instrumentos.
- Fix bug "today" / `=TODAY()`: `FECHA_CARGA` y `FECHA_GUARDADO_VALUES` ahora son input manual; hoja de instrucciones exige Paste Special → Values antes de devolver el archivo.

### Estructura final (implementada en v0.1)

Se simplificó a un **único formato long en la hoja `02_Datos`** en vez de hojas
por categoría. Razón: más fácil de parsear, más fácil de mantener el catálogo,
menos sitios donde el analista puede equivocarse.

| Hoja | Propósito |
|---|---|
| `00_Instrucciones` | Cómo correr la plantilla (texto para el analista) |
| `01_Parametros` | `AS_OF` (input), demás fechas se calculan solas |
| `02_Datos` | Una fila por instrumento × ticker; columnas con valores a `AS_OF`, `MES_ANT`, `YE_ANT`, `INI_12M`. **64 instrumentos** cubriendo Fases 1–5 + capítulo corporativo |
| `03_SOFR_Futures` | Strip SR3 próximos 8 vencimientos (continuous tickers `SFR1` ... `SFR8`) |
| `04_FedWatch` | Paste manual desde pantalla WIRP (no hay BDP confiable para esto) |
| `05_Notas_Analista` | Tickers que fallaron + eventos + sugerencias |
| `99_Envio` | Instrucciones de cómo devolver el archivo |

**Categorías cubiertas en `02_Datos`:**
- `policy` — Fed, ECB, BoE, BoJ, PBoC, BCB, Banxico, BanRep (8 instrumentos)
- `money_market` — SOFR ON / averages / term (7 instrumentos)
- `yield_curve` — UST 1M–30Y nominal + Bund/Gilt/JGB/BR/MX/CO 10Y (17 instrumentos)
- `real_curve` — TIPS 5Y/10Y/20Y/30Y (4 instrumentos)
- `breakeven` — US 2Y/5Y/10Y/30Y inflación esperada (4 instrumentos)
- `swap_curve` — SOFR OIS 2Y/5Y/10Y/30Y (4 instrumentos)
- `fx` — G10 + LatAm + USDVES oficial (10 instrumentos)
- `credit_index` — EMBI/CEMBI subíndices + ICE BofA IG y HY por rating (16 instrumentos)

Total: **76 instrumentos**. La descomposición *nominal = real + breakeven + term
premium* (que alimenta la Pieza D del modelo predictivo, ver
`07_MODELO_PREDICTIVO.md`) requiere las 3 curvas TIPS/BE/swap a los mismos
tenors. Por eso se incluyen explícitamente en la plantilla del analista.

**Nota:** los datos del BCV (Fase 5) y bolívar paralelo **no** vienen por Bloomberg.
Tienen extractores web separados (ver `04_PLAYBOOK_MENSUAL.md`).

### Convenciones de fórmulas implementadas

Cada celda de valor en `02_Datos` usa:

```excel
=IFERROR(
   INDEX(BDH(ticker, field, fecha, fecha, "Days=A", "Fill=B", "Dir=H"), 1, 2),
   BDH(ticker, field, fecha, fecha, "Days=A", "Fill=B")
)
```

- `BDH` con `start=end=fecha` para un solo día.
- `Days=A` + `Fill=B` para tomar día hábil anterior si la fecha es feriado.
- `INDEX(..., 1, 2)` extrae solo el valor (la primera columna del array es la fecha).
- `IFERROR` con fallback para versiones de Excel sin dynamic arrays.

Detalle completo en `plantilla_bloomberg/README.md`.

### Spec del archivo que el analista devuelve

El analista devuelve el `.xlsx` con valores cargados (las fórmulas se vuelven
valores al guardar si la conexión BBG funcionó). El parser lee `02_Datos`
columnas `[#, categoria, region, instrument, tenor_label, tenor_years, ticker,
field, unit, val_AS_OF, val_MES_ANT, val_YE_ANT, val_INI_12M, nota]` directamente
— no necesita una hoja "pivot long format" aparte porque `02_Datos` ya es long.

## Fuentes públicas para backfill

Estas no necesitan Bloomberg; las podemos correr nosotros directamente:

| Fuente | URL / Endpoint | Cobertura |
|---|---|---|
| FRED API | `https://api.stlouisfed.org/fred/series/observations?series_id=...` | Fed Funds, SOFR, IORB, EFFR, CPI, employment, etc. (requiere API key gratuita) |
| US Treasury XML | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-yield-curve-rates` | UST curve diaria — ya integrado en `credito_Panama` |
| CME SR3 daily settlements | `https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/...?fut=...` | SOFR futures históricos |
| CME FedWatch | `https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html` (HTML) | probabilidades por reunión (scrape) |
| BCB Brasil (SGS) | API pública | SELIC y curvas |
| BCV Venezuela | `https://www.bcv.org.ve/estadisticas` (HTML/PDF) | tasas y FX oficial |
| Monitor Dólar VE | sitios públicos varios | paralelo (requiere acordar lista) |

## API keys que necesitamos en `secrets`

- `FRED_API_KEY` (gratuita en https://fredaccount.stlouisfed.org/apikey)
- (cuando se requiera) `BBG_REFINITIV_*` para cross-check si tenemos terminal disponible
- Sin keys: US Treasury, CME, BCV.

Guardar las keys como **secrets del entorno de ejecución** (no en repo).

## Backfill plan (ene–abr 2026 desde cero)

Para cada mes M ∈ {ene, feb, mar, abr} de 2026:
1. Bajar de FRED las series con `as_of_date <= último_día_hábil(M)`.
2. Bajar de US Treasury la curva del día.
3. Bajar de CME los settlements de SR3 del día (CSV histórico disponible).
4. Para FedWatch histórico: la página actual no muestra histórico. Alternativa:
   reconstruirlo desde precios históricos de SR3 + tasa vigente Fed Funds (la lógica
   pública del FedWatch está documentada). Esto se hace en `src/tasas_mercantil/fedwatch.py`.
5. Curvas globales y FX: FRED H.10 + sitios bancos centrales.
6. BCV: snapshot estimado desde Wayback Machine si no tenemos histórico interno.
7. Bolívar paralelo histórico: complicado. Esfuerzo de búsqueda en Wayback +
   posibles APIs (DolarToday tiene histórico parcial vía Twitter feed). Si no se
   logra reconstruir limpio, **se marca el dato como N/A en los cortes históricos**
   y se documenta — preferible eso que un dato malo.
