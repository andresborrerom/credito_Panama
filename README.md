# Estudio de Renta Fija de Panamá (Latinex) — Niveles actuales vs historia

> Objetivo: construir un estudio rápido pero a fondo de las tasas de renta fija negociadas en la Bolsa Latinoamericana de Valores (Latinex), comparando los niveles actuales contra su historia, segmentando por **plazo, sector, tipo de instrumento, emisor y proxy de riesgo de crédito**. Entregables: (1) base de datos completa, (2) herramienta interactiva de visualización, (3) PDF con conclusiones deducibles desde la herramienta.

---

## 1. Fuentes de datos identificadas

### 1.1 Latinex — API JSON pública (no documentada, descubierta por reverse-engineering del front)

Base URL: `https://www.latinexbolsa.com`

| Endpoint | Contenido | Volumen actual | Uso |
|---|---|---|---|
| `/emisor/emisiones/activas/all` | Universo de emisiones vigentes (ISIN, nemotécnico, emisor, sector, instrumento, base, emisión, vencimiento, frecuencia, **tasa cupón**, tipo tasa, monto serie/colocado) | **2,573 emisiones** | Maestro de instrumentos |
| `/emisor/transacciones/mercado?rango={1D,1M,3M,6M,1Y,5Y,10Y}` | Tape de transacciones (fecha, folio, mercado, instrumento, emisor, nemotécnico, **precio**, nominal, monto, moneda, rendimiento) | **84,191 trades** a 10 años | Serie histórica de precios y yields negociados |
| `/emisor/detalle/instrumento/historico?instrumento={nemo}&rango={...}` | OHLC + volumen por instrumento | variable | Series por instrumento individual |
| `/emisor/detalle/instrumento/resumen?instrumento={nemo}` | Ficha del instrumento (último precio, indicadores) | 1 fila/instrumento | Snapshot |
| `/emisor/detalle/instrumento/pago?instrumento={nemo}&rango=1D` | Flujos de pago (cupones, amortización) | variable | Cálculo YTM correcto |
| `/emisor/detalle/emisor?code={code}` + `/cifras` + `/documentos` + `/noticias` | Ficha del emisor + estados financieros | variable | Enriquecimiento crediticio |
| `/volumen/emisor` | Volumen anual primario/secundario/recompras | serie anual | Liquidez |
| `/ofertas/mercado/home` | Ofertas vivas (compra/venta) | snapshot | Bid-ask vigente |
| `/emisor/emisiones/sostenibles` | Bonos verdes/sociales/sostenibles | subset | Segmento ESG |
| `/emisor/emisiones/nuevos/prospectos` + `/tramites` | Pipeline de emisiones | listado | Forward-looking |
| `/ranking/creadores` + `/puesto-bolsa/` | Casas de bolsa y market makers | listado | Microestructura |

Formato uniforme: `{ "order": [columnas], "filters": [...], "data": [filas] }`. Sin autenticación, sin rate limit detectado en pruebas iniciales.

### 1.2 Fuentes complementarias (para enriquecimiento)

- **Bonos soberanos Panamá (USD)** → FRED, World Bank, Investing.com → benchmark de la curva libre de riesgo equivalente.
- **US Treasury curve** → Treasury.gov / FRED → spread vs USD risk-free (Panamá es economía dolarizada, comparación es directa).
- **Superintendencia del Mercado de Valores (SMV) de Panamá** → calificaciones crediticias y prospectos (scraping puntual de emisores).
- **Calificadoras locales** (Fitch Centroamérica, Equilibrium, PCR) → ratings por emisor cuando estén disponibles públicamente.

> **Trade-off explícito:** No vamos a obtener ratings de S&P/Moody's con licencia. Construiremos un **proxy de riesgo de crédito** usando: (a) sector + tipo emisor (gobierno > banco grande > banco mediano > corporativo grande > VCN > real estate / desarrollador), (b) cuando exista, rating local scrapeable, (c) z-score del spread negociado vs curva soberana como medida revealed-market del riesgo.

---

## 2. Arquitectura de la solución

```
[ETL Python]
  ├─ extract.py     → llama a los endpoints, guarda raw JSON con timestamp
  ├─ transform.py   → normaliza, parsea fechas, calcula YTM por trade, asigna buckets
  └─ load.py        → escribe en SQLite + Parquet (DuckDB-friendly)

[Base de datos: SQLite + Parquet]
  Tablas:
    - instruments        (ISIN, nemo, emisor, sector, instrumento, emisión, vencimiento,
                          cupón, tipo_tasa, frecuencia, base, monto_serie, monto_colocado)
    - issuers            (código emisor, nombre, sector, país, cifras financieras flat)
    - trades             (fecha, nemo, ISIN, mercado, precio, nominal, monto, moneda,
                          rendimiento_reportado, ytm_calculado, plazo_residual_años,
                          bucket_plazo, bucket_credito)
    - quotes             (snapshot de ofertas: nemo, bid, ask, fecha_snapshot)
    - issuances_pipeline (nuevas, en trámite, prospectos)
    - curves             (fecha, bucket_plazo, bucket_credito, sector, yield_mediano,
                          yield_p25, yield_p75, n_obs)
    - benchmarks         (fecha, plazo_años, tasa_us_treasury, tasa_pan_sov)

[Análisis: notebooks/análisis.ipynb]
  - Curvas actuales por sector/instrumento/bucket
  - Percentiles históricos por bucket (rich/cheap)
  - Spread vs UST y vs soberano Panamá
  - Evolución temporal de spreads sectoriales
  - Heatmap "dónde estamos vs los últimos 5 años"

[Visualización: app.py — Streamlit]
  - Filtros: rango fechas, sector, emisor, instrumento, bucket plazo, bucket crédito
  - Vistas:
      1. Curva de rendimientos (actual + percentiles históricos sombreados)
      2. Serie temporal de yield/spread por bucket
      3. Scatter (plazo residual vs yield) con tooltip por emisión
      4. Heatmap percentil-histórico por sector × plazo
      5. Tabla de "top 20 ricas / baratas" vs su propia historia
      6. Liquidez: volumen por sector y por emisor en el tiempo
  - Cada gráfico → botón "export PNG" + caption con la conclusión que el PDF replicará

[Reporte: report.py]
  - Renderiza los mismos gráficos a /reports/figs/
  - WeasyPrint o ReportLab → PDF estructurado con conclusiones
  - Cada conclusión apunta al filtro exacto en Streamlit para reproducirla
```

### Stack

- **ETL / análisis:** Python 3.11, `httpx`/`requests`, `pandas`, `numpy`, `numpy-financial` o `QuantLib-Python` para YTM con flujos.
- **Storage:** SQLite (consulta general) + Parquet (analítica). DuckDB opcional para queries ad-hoc.
- **Viz:** Streamlit + Plotly.
- **PDF:** WeasyPrint (HTML→PDF, ideal para gráficos Plotly exportados a PNG).
- **Calidad:** `pytest` mínimo para parsing y cálculo de YTM; `ruff` para lint.

---

## 3. Metodología analítica

### 3.1 Cálculo de yield por transacción

Para cada trade en la tape, dado el cupón y el flujo del instrumento:
1. Reconstruir flujos restantes desde `fecha_trade` hasta `fechaVencimiento` con `frecuencia` y `base` (30/360, ACT/360, ACT/365…).
2. YTM = tasa que iguala VP de flujos al `precio` × `nominal`.
3. Fallback: si no se puede armar flujo (datos faltantes), usar `rendimiento_reportado` del feed cuando esté.
4. Marcar trades dentro de un mismo día/instrumento y consolidar a un mid diario ponderado por nominal.

### 3.2 Buckets

- **Plazo residual:** `[0-1y, 1-3y, 3-5y, 5-7y, 7-10y, 10y+]`.
- **Tipo de instrumento:** Bonos del Tesoro, Notas del Tesoro, Letras del Tesoro, Bonos Corporativos, Notas Corporativas, VCN, Bonos Hipotecarios, Bonos Inmobiliarios, Bonos Cero Cupón.
- **Sector:** el que reporta Latinex (Gobierno, Financiero, Bienes Raíces, Energía, Consumo, Comunicaciones, etc.).
- **Proxy de crédito:** ver §1.2.

### 3.3 Métricas para "actual vs historia"

- Por cada (bucket_plazo, sector) y fecha t: `yield_mediano_t`.
- Comparar `yield_mediano_hoy` contra distribución de los últimos {1y, 3y, 5y, 10y}: percentil actual.
- **Spread**: `yield_corp - yield_tesoro` mismo bucket de plazo → percentil histórico del spread.
- **z-score de spread** por sector vs su propia historia 5y.

### 3.4 Conclusiones que el PDF puede sustentar

Plantillas de hallazgos (a llenar con datos reales):
- "El sector X cotiza a percentil P del spread de los últimos 5 años → barato/caro vs historia".
- "La curva de bonos del Tesoro Panamá está {flat/empinada/invertida} en N pb entre 2y y 10y, vs promedio histórico de M pb".
- "VCN promedio ofrece prima de Q pb sobre Letras del Tesoro de plazo equivalente, vs mediana histórica de R pb".
- "Liquidez 2026-YTD cae/sube X% vs 2025, concentrada en sectores A, B".

Todas serán *deducibles* desde la app: cada conclusión del PDF llevará referencia al filtro Streamlit que la reproduce.

---

## 4. Estructura del repo (a crear)

```
credito_Panama/
├── README.md                ← este archivo
├── pyproject.toml           ← deps + scripts
├── data/
│   ├── raw/                 ← respuestas JSON crudas con timestamp
│   ├── processed/           ← parquet limpios
│   └── panama_fixed_income.sqlite
├── src/
│   ├── etl/
│   │   ├── extract.py
│   │   ├── transform.py
│   │   ├── load.py
│   │   └── endpoints.py     ← catálogo de endpoints
│   ├── analytics/
│   │   ├── ytm.py           ← cálculo de yields
│   │   ├── buckets.py
│   │   ├── curves.py
│   │   └── credit_proxy.py
│   └── app/
│       └── streamlit_app.py
├── notebooks/
│   └── 01_exploracion.ipynb
├── reports/
│   ├── template.html
│   ├── figs/
│   └── estudio_renta_fija_panama.pdf
├── tests/
│   └── test_ytm.py
└── scripts/
    ├── run_etl.sh
    ├── run_app.sh
    └── build_report.sh
```

---

## 5. Roadmap por fases (con trade-off rapidez ↔ profundidad)

### Fase 0 — Setup (≈30 min)
- [ ] Inicializar `pyproject.toml`, crear estructura de carpetas.
- [ ] Configurar deps: `pandas numpy requests httpx tenacity streamlit plotly numpy-financial weasyprint pyarrow duckdb pytest ruff`.
- [ ] Script `extract.py` con reintentos exponenciales y caching local del raw JSON con timestamp.

### Fase 1 — ETL completo (≈1-2h)
- [ ] Bajar `emisiones/activas/all` → tabla `instruments`.
- [ ] Bajar `transacciones/mercado?rango=10Y` (un solo hit, ~24 MB) → tabla `trades`.
- [ ] Bajar `volumen/emisor` y `ofertas/mercado/home`.
- [ ] Para top-N emisores por monto colocado, bajar `cifras`, `documentos`, `noticias` → tabla `issuers`.
- [ ] Parsear fechas (varios formatos), montos, tasas (0.0 = sin coupon → revisar tipo).
- [ ] Cargar a SQLite + Parquet.

### Fase 2 — Cálculo de yields y buckets (≈1-2h)
- [ ] Función `compute_ytm(precio, cupón, frecuencia, base, fecha_trade, fecha_vencimiento)`.
- [ ] Aplicar a la tape completa; auditar dispersión y outliers.
- [ ] Para bonos tasa flotante: marcar y excluir de curvas (analizar separado).
- [ ] Construir `curves` agregada por (fecha, bucket_plazo, sector, instrumento).

### Fase 3 — Benchmarks externos (≈1h)
- [ ] Bajar UST yields históricos (FRED API gratis con key) y Panamá soberano USD (FRED o Investing scrape).
- [ ] Calcular spreads.

### Fase 4 — App Streamlit (≈2-3h)
- [ ] Layout con filtros laterales.
- [ ] 6 vistas descritas en §2.
- [ ] Cache con `@st.cache_data` para que las queries vuelen.

### Fase 5 — PDF de conclusiones (≈1-2h)
- [ ] Template HTML con secciones: resumen ejecutivo, metodología, curva actual, evolución histórica, sectores ricos/baratos, liquidez, apéndice metodológico.
- [ ] Generar PNGs desde Plotly, embedir, renderizar con WeasyPrint.
- [ ] Cada conclusión cita el filtro Streamlit reproducible.

**Total estimado:** 7-11 horas de trabajo dirigido. El trade-off principal es no implementar QuantLib para curva spline + bootstrapping; usar mediana por bucket es suficientemente robusto para el alcance.

---

## 6. Riesgos y limitaciones que el estudio debe declarar

- Los precios negociados pueden venir de operaciones pactadas (no de orden book continuo) → ruido en yields. Mitigamos con mediana por bucket y filtrando trades de monto ínfimo.
- Falta de calificaciones públicas → usamos proxy; el lector debe saberlo.
- Tasas cupón = 0.0 en algunos registros → o son cero-cupón o data missing; tratamiento explícito.
- Panamá es economía dolarizada: no hay riesgo FX, todo el análisis es en USD. Esto SIMPLIFICA y permite comparación directa con UST.
- Algunas emisiones pueden tener call/put options no codificadas en el feed → asumimos bullet salvo evidencia contraria desde `/pago`.

---

## 7. Próximos pasos — qué necesito de ti

1. **Confirmar stack** (Python + Streamlit + SQLite + Parquet + WeasyPrint). Si prefieres otra cosa (R + Shiny, dashboard web alojado, etc.), dime.
2. **¿Quieres que arranque con la Fase 0 + Fase 1 ya** (setup + ETL completo) y te muestre la base de datos cargada antes de seguir, o prefieres que empuje el plan completo de un tirón?
3. **Fuentes externas:** ¿tienes API key de FRED? Si no, la creo y la pongo en `.env`. Para soberano Panamá USD, ¿prefieres FRED, World Bank, o scrape de Investing.com?
4. **Calificaciones crediticias:** ¿tienes acceso a algún feed pago (Bloomberg, Refinitiv) o vamos con proxy + scraping público de calificadoras locales?
5. **Período de estudio:** propongo 10 años (max disponible en API). ¿Confirmas o acotamos a 5y para mayor profundidad por bucket?

Una vez confirmado, sigo con la Fase 0.
