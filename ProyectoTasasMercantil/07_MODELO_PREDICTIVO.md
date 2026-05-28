# 07 · Modelo predictivo Mercantil de tasas

Modelo propio que el reporte muestra **junto a** las dos referencias de mercado
(implied path SOFR + CME FedWatch). Objetivo: tener una tercera lectura que
podamos defender, backtestear honestamente y mostrar como diferencial Mercantil.

> Este documento es **el contrato técnico del modelo**. Lo que vive aquí es
> autoritativo. Cambios al modelo (especificación, ventana, rivales, métricas)
> se reflejan primero acá, después en el código. Inspirado en el patrón del
> proyecto hermano `mercantil-saa` (ver `saa-instructions.md`,
> `saa-robustness-skeleton.md`).

---

## 0. Principios vinculantes

1. **Cero look-ahead bias.** Cada predicción del modelo en `as_of_date = T`
   usa solo datos con `snapshot_date <= T + 3 días hábiles` (la ventana de
   presentación del reporte). Ver `02_MODELO_DATOS.md` § Backtesting honesto.
2. **Walk-forward estricto**: en cada `T_k` se reentrena con datos hasta `T_k − 1`.
   Nunca con datos posteriores, ni siquiera para tunear hiperparámetros.
3. **Hiperparámetros en ventana separada**: la calibración de hiperparámetros
   ocurre sobre una sub-ventana fija (`2000-01` a `2009-12`). Se congelan
   antes del primer corte de evaluación.
4. **Modelos rivales explícitos**: el modelo Mercantil **debe** publicarse
   junto a los rivales. No tiene sentido publicar "el modelo" sin las
   referencias contra las que se compara.
5. **Métricas duales**: vs benchmark (implied path) **y** absolutas (MAE en bps,
   acierto direccional, calibración distribucional).
6. **Fail loud**: si el modelo no supera al implied path en skill score
   promedio rolling 24M, el deck publica solo implied path + FedWatch y declara
   "modelo en revisión".
7. **Reproducibilidad**: cada predicción se guarda con `model_version_id` (semver),
   `data_snapshot_hash` y commit sha de código.
8. **No usar `=TODAY()` ni "today"** en archivos de input (lección de
   `mercantil-saa`). Las fechas son fijas y manuales.

---

## 1. Lo que el modelo pronostica

| Horizonte | Variable | Forma de salida |
|---|---|---|
| Próxima reunión FOMC | Decisión Fed Funds | Distribución sobre {-50, -25, 0, +25, +50} bps |
| 3 meses | Fed Funds promedio | Punto + IC 80% |
| 6 meses | Fed Funds promedio | Punto + IC 80% |
| 12 meses | Fed Funds promedio | Punto + IC 80% |
| 3, 6, 12 meses | UST 2Y, 5Y, 10Y | Punto + IC 80% |
| 3, 6, 12 meses | TIPS 5Y, 10Y (real) | Punto + IC 80% |
| 3, 6, 12 meses | Breakeven 5Y, 10Y | Punto + IC 80% |
| 3, 6, 12 meses | SOFR OIS 5Y, 10Y (swap) | Punto + IC 80% |

Más adelante (Fase 2+) extensión a ECB y BCV con metodologías análogas.

**Por qué pronosticamos también real y breakeven**: porque la descomposición
"yield nominal = real + breakeven + term premium" es la lente que usan los
fondos de pensión, aseguradoras y el desk de tesorería. Sin esa descomposición
el modelo es un pronóstico de tasa, no un pronóstico de mercado.

---

## 2. Universo de datos — ventanas escalonadas

**Decisión clave:** no usar **una sola ventana** histórica para todo. Cada feature
entra al modelo desde la fecha en que existe con calidad reproducible. Esto
evita el anti-patrón "empujar la ventana porque más historia es mejor" sin
considerar regímenes ni breaks estructurales (lección de SAA).

### Etapas de disponibilidad

| Feature | Disponible desde | Notas |
|---|---|---|
| Effective Fed Funds | 1954-07 | FRED DFF — sin revisiones |
| **Fed Funds target explícito** | **1994-02** | Greenspan formaliza el target tras 1994; antes era discrecional. Régimen pre-1994 NO se usa para training. |
| UST yields constant maturity 1Y–30Y | 1962-01 | FRED DGS* |
| CPI / Core CPI vintage | 1950+ via ALFRED | vintage data |
| Payrolls / U-3 vintage | 1948+ via ALFRED | vintage data |
| GDP nowcast (Atlanta Fed) | 2011-04 | |
| **TIPS yields CMT** | **1997-01** | Auctions arrancan en 1997 |
| **Breakevens** | **1999-01** | Serie completa USGGBE* |
| **5y5y forward BE** | **1999-01** | derivado |
| **EuroDollar futures** | **1981-12** | proxy de implied path **pre-SOFR**, basado en LIBOR |
| **SOFR rate** | **2018-04** | publicación oficial NY Fed |
| **SOFR (SR3) futures** | **2018-05** | CME |
| **CME FedWatch implícito reconstruible** | **2018-05** | desde SR3 prices |
| **Dot plot SEP** | **2012-01** | 4 por año |
| FX major + LatAm | 1971+ post Bretton Woods | |

### Decisión de ventanas

- **Universo de datos brutos**: desde **1994-01** (target Fed Funds explícito).
  16+ años incluso si arrancamos solo macro; los datos pre-1994 los excluimos del
  training porque el régimen de política era distinto. Anexo cualitativo
  describirá cómo "se vería" el modelo en pre-1994 sin meterlo en el motor.
- **Ventana de calibración de hiperparámetros**: **2000-01 a 2009-12**.
  Cubre el cycle dot-com, Greenspan put, 2003 zero-bound suave, 2004-2006 hike,
  2007-2008 crisis. **Se congelan después** y no se vuelven a tunear.
- **Ventana de evaluación walk-forward (rolling)**: **2010-01 a la fecha**.
  Cubre QE, taper tantrum, 2015-2018 normalización, 2018 hike Powell, 2019
  cuts, 2020-2021 COVID, 2022-2023 hike agresivo, 2024 hold, 2025+ cut cycle.
  ~16 años, ~190 cortes mensuales.
- **Para features modernas (SOFR, SR3, FedWatch)**: backtest desde **2019-01**.
  Pre-2018 usamos EuroDollar (LIBOR-based) como proxy con `data_caveat = "libor_proxy"`.
- **Para horizonte 12M con features post-2018**: backtest desde **2020-01**
  para que cada predicción tenga su realización contra-fáctica.

### Regímenes explícitos que el backtest debe segmentar

Reportes separados de skill por cada régimen:
1. **2010–2013** — ZLB + QE.
2. **2013–2014** — taper tantrum.
3. **2015–2018** — normalización lenta Yellen.
4. **2018** — hike cycle Powell.
5. **2019** — pivot dovish + cuts.
6. **2020–2021** — COVID + zero-bound estricto.
7. **2022–2023** — hike agresivo (+525 bps en 16 meses).
8. **2024** — hold.
9. **2025+** — cut cycle.

**Anti-patrón evitado**: reportar solo el agregado. Un modelo puede ganar al
implied path en agregado y perder en 5 de 9 regímenes. Eso lo declaramos.

---

## 3. Arquitectura del modelo

Modelo modular con 3 piezas. La salida final es una agregación con pesos.

### Pieza A · Information del mercado (baseline)

- **Input**: implied path SOFR + CME FedWatch + dot plot vigente.
- **Output**: predicción base = implied path SOFR descontando un **risk premium
  term-structure** estimado vía Cieslak-Povala (2015) o equivalente bayesiano.
- **Función**: referencia mínima. Si el modelo agregado no supera esta sola
  pieza, no publica nada.

### Pieza B · Reaction function de la Fed

- **Input**: nowcast vintage (CPI core, PCE core, U-3, GDPNow, breakeven 5Y5Y).
- **Modelo**: Taylor rule modificada con coeficientes Bayesianos (prior
  centrado en Taylor 1993; updating con verosimilitud histórica 1994+).
  Smoothing parameter para reflejar gradualismo Fed.
- **Output**: tasa "implícita" según función de reacción + IC.

### Pieza C · Señal editorial del mes

- **Input**: una o dos hipótesis condicionales que Andrés/Camilo articulan
  cada mes (ej. "si CPI core junio < 0.2% m/m → prob cut sept > 60%").
- **Output**: ajuste delta sobre la predicción base + B, validado por backtest
  del patrón histórico cuando hubo condicionales similares.
- **Esta pieza es opt-in**: si no hay hipótesis editorial del mes, peso = 0.

### Pieza D · Decomposition / term-premium model

- **Input**: TIPS, breakevens, swap curve.
- **Output**: descomposición de UST 10Y en (real expected + inflation expected
  + term premium). Permite identificar qué pieza explica el movimiento del
  mes. Adusto-King-Wright (ACM) o Kim-Wright como referencia.
- Esta pieza no pronostica directamente — alimenta interpretación y a la
  pieza B (vía la inflación esperada del 5y5y).

### Agregación

```
yhat_aggregate(T) = w_A * yhat_A + w_B * yhat_B + w_C * yhat_C
```

Pesos `(w_A, w_B, w_C)` se determinan con un **meta-modelo** entrenado en la
ventana de calibración (2000-2009). Después se congelan.

Pesos iniciales propuestos (a refinar en calibración):
- `w_A = 0.55` (el mercado es difícil de batir)
- `w_B = 0.35`
- `w_C = 0.10` (max, solo cuando hay hipótesis editorial)

---

## 4. Modelos rivales

Lista explícita. El reporte mensual compara contra **todos** estos:

| ID | Descripción | Por qué importa |
|---|---|---|
| `RIVAL_IMPLIED` | Implied path SOFR puro, sin ajuste de risk premium | Base mínima. Si no le ganamos, no publicamos. |
| `RIVAL_FEDWATCH` | CME FedWatch path mediano por probs | Es lo que mira el mercado retail. |
| `RIVAL_TAYLOR_NAIVE` | Taylor rule clásica con coef. fijos | Lo que enseñan los libros. |
| `RIVAL_NAIVE` | Tasa actual proyectada plana | Sanity check. |
| `RIVAL_DOTPLOT_MEDIAN` | Mediana del SEP más reciente | Lo que dice la Fed |
| **`MODELO_MERCANTIL`** | Agregación A+B+C+D | El nuestro |

**Por qué incluimos el "modelo simple de la industria" como rival** (lección
SAA): si el modelo Mercantil no le gana al **implied path puro**, la
diferenciación es estética. La barra no es "batir buy-and-hold". La barra es
"batir lo que mira todo el mundo".

---

## 5. Backtest — protocolo formal

### 5.1 Procedimiento

Para cada `as_of_date = T_k` en la ventana de evaluación walk-forward:
1. Cargar el snapshot del estado del mundo a `T_k`:
   - FRED ALFRED vintage para macro.
   - Bloomberg histórico para tasas, swaps, TIPS, breakevens, futuros.
   - Dot plot vigente solo si ya se había publicado.
2. Generar predicciones de cada rival.
3. Avanzar el calendario y registrar el realizado en cada horizonte
   {1M, 3M, 6M, 12M}.
4. Calcular métricas.

### 5.2 Métricas reportadas (dual)

**Vs benchmark (`RIVAL_IMPLIED`)**:
- Skill score = `1 − MAE(modelo) / MAE(implied)`.
- Information Ratio del residual.
- Hit rate direccional vs implied (¿el modelo acertó la dirección del miss del mercado?).

**Absolutas**:
- MAE en bps a 1M, 3M, 6M, 12M.
- RMSE en bps.
- Sesgo direccional (¿hawkish o dovish sistemático?).
- Cobertura del IC 80% (debe estar entre 75% y 85%).

**Calibración distribucional**:
- PIT histogram (probability integral transform) — debe ser uniforme [0,1].
- Log-score promedio.
- Brier score para predicciones probabilísticas por reunión FOMC.

### 5.3 Bootstrap del backtest

Para verificar estabilidad del ranking modelo-vs-rivales:
- Block bootstrap (block size = 6 meses) sobre los 190 cortes mensuales.
- 1,000 réplicas.
- Reportar la **distribución** del skill score; el punto único es engañoso.

### 5.4 Reglas de "fail loud"

- Skill score promedio rolling 24M vs `RIVAL_IMPLIED` < +0.05 → **modelo en
  revisión, no se publica**. El deck muestra solo implied + FedWatch.
- Cobertura del IC 80% < 70% o > 90% → **calibración rota, no se publica**.
- Sesgo direccional |bias| > 15 bps promedio rolling 12M → **declarar
  explícitamente** en el deck.
- Peor régimen con skill < −0.25 → **declarar el caveat** en el deck.

---

## 6. Versionado del modelo

Cada cambio bumpea `model_version_id` (semver):

- `0.1.0` — solo Pieza A (implied path puro con shift constante). Baseline.
- `0.2.0` — + Pieza B (Taylor rule simple).
- `0.3.0` — + Pieza B bayesiana.
- `0.4.0` — + Pieza D (descomposición term-premium).
- `0.5.0` — + Pieza C (hipótesis editoriales).
- **`1.0.0`** — primer modelo agregado que pasa el umbral de skill rolling 24M.
- `1.x.y` — refinamientos sin romper interfaz.
- `2.0.0` — extensión a otras central banks (ECB, BCV).

Las predicciones históricas se conservan etiquetadas con la versión que las
generó. Una vez firmadas (corte cerrado), no se reescriben.

---

## 7. Implementación — stack y árbol de archivos

Stack inspirado en `mercantil-saa/saa-architecture.md`:

| Área | Librerías |
|---|---|
| Datos | `pandas`, `numpy`, `fredapi` (ALFRED via REST), `pandas-datareader` |
| Estadística / Bayesiana | `scipy`, `statsmodels`, `pymc` (Pieza B bayesiana) |
| Backtest | implementación propia |
| Config | `pydantic` + YAML |
| Testing | `pytest`; `hypothesis` para tests de propiedad |
| Reportes | `quarto` (bitácora del modelo) + `plotly` |

Estructura de archivos (a construir):

```
credito_panama/src/tasas_mercantil/
├── __init__.py
├── configs/
│   ├── modelo.yaml            ← ventanas, pesos congelados, lista de rivales
│   ├── features.yaml          ← qué features se usan, desde cuándo, fuente
│   └── instrumentos.yaml      ← catálogo (lo mismo que la plantilla BBG)
├── data/
│   ├── ingest_bloomberg.py    ← parsea el xlsx del analista
│   ├── ingest_fred.py         ← ALFRED vintage
│   ├── ingest_cme.py          ← SR3 settlements
│   └── snapshot.py            ← punto-en-el-tiempo, evita look-ahead
├── modelo/
│   ├── pieces/
│   │   ├── implied_path.py    ← Pieza A
│   │   ├── reaction_fn.py     ← Pieza B
│   │   ├── ad_hoc.py          ← Pieza C
│   │   └── term_premium.py    ← Pieza D
│   ├── aggregate.py
│   ├── persist.py             ← guarda con (version_id, snapshot_hash, commit_sha)
│   └── interface.py           ← predict(as_of_date, horizon) → DataFrame
├── rivales/
│   ├── rival_implied.py
│   ├── rival_fedwatch.py
│   ├── rival_taylor_naive.py
│   ├── rival_naive.py
│   └── rival_dotplot_median.py
├── backtest/
│   ├── walk_forward.py
│   ├── metrics.py             ← MAE, RMSE, skill score, hit rate, calibración
│   ├── bootstrap.py
│   └── report.py              ← genera tabla comparativa por régimen
├── tests/
│   ├── test_no_lookahead.py   ← invariante crítico
│   ├── test_distribution_calibration.py
│   └── test_aggregation.py
└── narrativa/
    └── render_lamina_5.py     ← genera la lámina del deck con las 3 lecturas
```

---

## 8. Sesiones de trabajo del modelo (estilo SAA)

El modelo se construye en **sesiones temáticas**, no en una pasada lineal.
Cada sesión deja artefactos verificables. Lista propuesta:

| Sesión | Foco | Artefacto al cierre |
|---|---|---|
| M-0 | Ingesta FRED ALFRED + Bloomberg histórico (1994+) | tabla `vintage_macro` cargada; chequeo de no-revisión |
| M-1 | Pieza A baseline (implied path puro) + backtest 2010-2025 | `model_version_id = 0.1.0` con skill score reportado |
| M-2 | Reaction function clásica (Taylor) | `0.2.0` |
| M-3 | Reaction function bayesiana | `0.3.0` |
| M-4 | Descomposición term-premium (Pieza D) | `0.4.0` |
| M-5 | Hipótesis editorial (Pieza C) | `0.5.0` |
| M-6 | Agregación + calibración pesos sobre 2000-2009 | `0.6.0` |
| M-7 | Walk-forward 2010-presente, 9 regímenes, bootstrap | reporte de robustez |
| M-8 | Lámina del deck (lectura comparada 3 path) | render |
| M-9 | Bitácora del modelo (Quarto) publicada | sitio privado |
| M-10 | Promoción a `1.0.0` si pasa fail-loud | sign-off Andrés |

---

## 9. Pendientes que dejo abiertos para conversar

1. ¿Empezamos en M-0 con backfill **vía pipeline propio** (FRED API directo +
   Bloomberg histórico que el analista nos baje) o **vía equivalente del Excel
   del analista** corriendo iterativamente para cada cierre histórico
   (más manual pero menos riesgo de mismatch)?
2. ¿La pieza Bayesiana de Taylor (Pieza B) la implementamos con `pymc` o con
   regularización ridge sobre statsmodels? Recomendación: arrancar con
   statsmodels + prior implícito; subir a pymc si el bayesiano da más calibración.
3. La ventana de **calibración de hiperparámetros 2000-2009** ¿te parece bien?
   Alternativa: 1994-2003 (incluye Greenspan put pero excluye Bernanke ZLB).
4. ¿Cuándo definimos `RIVAL_DOTPLOT_MEDIAN` exactamente? El SEP no es continuo;
   propongo: "el SEP más reciente publicado antes de `as_of_date`, proyectado
   linealmente entre puntos del calendario SEP".
