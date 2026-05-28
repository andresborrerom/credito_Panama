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

Se entrega al analista cada mes con la `as_of_date` fijada. El analista la corre
en una terminal con Bloomberg API conectado, guarda los valores y devuelve el
archivo por correo (lo subimos a `cortes/YYYY-MM/input/`).

### Estructura de hojas

| Hoja | Propósito | Tipo de fórmula |
|---|---|---|
| `00_Parametros` | celdas únicas: `AS_OF`, `MES_ANT`, `YE_ANTERIOR` | manual |
| `01_USA_Policy` | Fed Funds upper/lower, IORB, ON RRP | `=BDP` para spot + `=BDH` para serie diaria |
| `02_USA_SOFR_UST` | SOFR ON/1M/3M/6M/12M y UST 1M..30Y para 3 fechas | `=BDP` + `=BDH` |
| `03_USA_SOFR_Futures` | strip de SR3 próximos 8 vencimientos, precio + implied rate | `=BDP` |
| `04_USA_FedWatch` | tabla cruzada meetings × decisions con probs | `=BDP("...","WIRP_...")` o tabla manual |
| `05_Global_Policy` | tasas política BCE/BoE/BoJ/PBoC/BCB/Banxico/BanRep | `=BDP` |
| `06_Global_Curves` | curva 10Y de 7 países | `=BDP` |
| `07_FX` | G10 + LatAm spot y NDF | `=BDP` |
| `08_EMBI` | índices y subíndices | `=BDP` |
| `09_Corp_Indices` | ICE BofA + CEMBI por rating y plazo | `=BDP` |
| `10_VEN_FX` | Tipo de cambio oficial BCV (referencial si BBG lo tiene) | `=BDP` o manual |
| `99_Output_LongFormat` | resultado consolidado pivot, una fila por (tabla, instrument, tenor, as_of_date, value) | fórmula |

La hoja `99_Output_LongFormat` es lo que parsea el pipeline. Los analistas solo
revisan que `=BDP` no haya devuelto `#N/A` y guardan.

**Nota:** los datos del BCV (Fase 5) **no** vienen por Bloomberg. Tienen un
extractor web separado que corre automático (ver `04_PLAYBOOK_MENSUAL.md`).

### Convenciones de campos Bloomberg

- Tasas: `PX_LAST` para spot; `LAST_PRICE` para algunos índices.
- Yields de UST: usamos `BLP` constant maturity (`USGG2YR Index ... PX_LAST`).
- Para histórico: `=BDH("USGG10YR Index","PX_LAST", as_of_date, as_of_date)`.
- Para FedWatch: la analítica WIRP devuelve la tabla. Si la versión de Excel del
  cliente no soporta WIRP, el analista paste-as-values desde la pantalla WIRP.

### Spec del archivo de output que el analista devuelve

El analista nos devuelve el `.xlsx` con valores cuajados (no fórmulas). Solo
necesitamos que la hoja `99_Output_LongFormat` esté completa. Esquema de columnas:

```
table_name | country | instrument | tenor_label | tenor_years | as_of_date | value | unit | notes
```

Ejemplo de fila válida:
```
yield_curve | US | UST | 10Y | 10.0 | 2026-01-30 | 4.18 | percent |
sofr_futures | US | SR3M6 | — | 0.25 | 2026-01-30 | 96.05 | price |
fx_rates | — | EURUSD | SPOT | 0.0 | 2026-01-30 | 1.0823 | rate |
```

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
