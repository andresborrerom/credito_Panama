# 07 · Modelo predictivo Mercantil de tasas

Modelo propio que el reporte muestra **junto a** las dos referencias de mercado
(implied path SOFR + CME FedWatch). Objetivo: tener una tercera lectura que
podamos defender, backtestear honestamente y mostrar como diferencial Mercantil.

## Lo no negociable

1. **Cero look-ahead bias.** Cada predicción del modelo en `as_of_date = T` usa
   solo datos con `snapshot_date <= T + 3 días hábiles` (la ventana de presentación
   del reporte). Ver `02_MODELO_DATOS.md` § Backtesting honesto.
2. **Reproducibilidad:** congelar versiones de modelo (`model_version_id`) y de
   datos (`data_snapshot_hash`).
3. **Diferenciable del mercado.** Si el modelo solo replica el implied path, no
   aporta nada. La pregunta clave es siempre: "¿qué información incorporamos que
   el mercado no?" — y debe poder responderse en una frase.
4. **Métricas de honestidad en cada corte:**
   - MAE vs realización a 1M, 3M, 6M y 12M.
   - Calibración de probabilidades (Brier score si trabajamos probabilísticamente).
   - Performance vs implied path (skill score: 1 − MAE_modelo / MAE_implied).
   - Performance vs CME FedWatch en sus horizontes.

## Qué pronostica el modelo

| Horizonte | Variable | Forma de salida |
|---|---|---|
| Próxima reunión FOMC | Decisión Fed Funds | Distribución sobre {-50, -25, 0, +25, +50} bps |
| 3 meses | Fed Funds promedio | Punto + IC 80% |
| 6 meses | Fed Funds promedio | Punto + IC 80% |
| 12 meses | Fed Funds promedio | Punto + IC 80% |
| 3, 6, 12 meses | UST 2Y, 5Y, 10Y | Punto + IC 80% |

Más adelante (Fase 2+) extensión a BCE y BCV con metodologías análogas.

## Arquitectura propuesta

Modelo modular con 3 piezas. La salida final es una **agregación con pesos**.

### Pieza A — Información del mercado (baseline)

- Input: implied path SOFR + CME FedWatch + dot plot vigente.
- Output: predicción base = implied path SOFR descontando un small risk premium
  (Cieslak & Povala-style si se quiere ser estricto, simple linear shift si no).
- Esto es la **referencia mínima** — si el modelo agregado no supera esto, no
  publica nada.

### Pieza B — Reaction function de la Fed

- Input: nowcast de núcleos macroeconómicos (CPI core, PCE core, U-3, Atlanta
  Fed GDPNow, payrolls).
- Modelo: Taylor rule modificada / regresión bayesiana con prior centrado en la
  Taylor rule.
- Output: tasa "implícita" según función de reacción.

Datos disponibles para nowcast: FRED + ALFRED (vintage data, sin look-ahead).

### Pieza C — Señal de hipótesis ad-hoc del mes

- Input: una o dos hipótesis editoriales que Andrés/Camilo decidan articular
  como condicional ("si CPI core junio < 0.2% → cut de 25 en sept con prob > 60%").
- Output: ajuste delta sobre la predicción base + B, validado por backtest del
  patrón histórico de hipótesis similares.

### Agregación

Pesos `w_A`, `w_B`, `w_C` se determinan con un meta-modelo entrenado sobre
backtest. Comenzamos con pesos manuales y los iteramos.

## Backtest honesto — diseño

### Universo de evaluación

- Periodo de prueba: enero 2020 a diciembre 2025 (6 años).
- Granularidad: cierre de cada mes.
- Total de cortes evaluados: ~72.

### Procedimiento

Para cada `as_of_date = T_k` en el universo:
1. Cargar **el snapshot del estado del mundo a `T_k`**:
   - FRED ALFRED para series macro (vintage = lo que se sabía en T_k).
   - Bloomberg histórico de SR3 futures, UST yields, WIRP probs.
   - Dot plot vigente a T_k (solo si ya se había publicado).
2. Generar las predicciones del modelo.
3. Avanzar el calendario y registrar el realizado en cada horizonte.
4. Calcular métricas.

### Métricas clave

- **MAE** del path Fed Funds a 3, 6, 12 meses.
- **Skill score vs implied path**: `1 - MAE_modelo / MAE_implied`. Positivo = ganamos.
- **Skill score vs CME FedWatch** en horizonte de próxima reunión.
- **Calibración**: cuando el modelo dice "70% prob de cut", ¿qué fracción se realiza?
- **Sesgo direccional**: ¿el modelo es sistemáticamente hawkish o dovish?

### Cross-validation

- **Rolling window**: entrenar con datos 2015–T_k−12 meses, evaluar 1 año hacia
  adelante, deslizar. Estándar de finance ML.
- **No usar K-fold tradicional** — las observaciones macro están correlacionadas
  serialmente y partir aleatoriamente filtra futuro.
- **Régimen-test**: separar performance en (a) periodo zero-bound (2020-2021),
  (b) ciclo de hike (2022-2023), (c) hold (2024), (d) ciclo de cut (2025+).
  Si el modelo solo funciona en un régimen, declararlo.

### Reglas de "fail loud"

- Si en backtest 2020–2025 el skill score vs implied path es < 0.05 (5% mejora
  promedio), **el modelo no se publica** — el deck muestra solo implied path +
  FedWatch.
- Si el modelo fue catastrófico en algún régimen (skill < −0.25), declararlo
  explícitamente en el deck — "modelo no diseñado para régimen X".

## Versionado del modelo

Cada cambio del modelo bumpea `model_version_id` (semver). Las predicciones
históricas se conservan etiquetadas con la versión que las generó. Una vez
firmadas, no se reescriben.

- `model_version_id = 0.1.0` — implied path puro (referencia)
- `model_version_id = 0.2.0` — + reaction function (B)
- `model_version_id = 0.3.0` — + señal hipótesis (C)
- `model_version_id = 1.0.0` — primer modelo agregado que pasa el umbral de skill

## Implementación

Skeleton de archivos a crear (en cortes siguientes):

```
src/tasas_mercantil/modelo/
├── __init__.py
├── data.py            ← carga snapshot vintage (no look-ahead)
├── pieces/
│   ├── implied_path.py
│   ├── reaction_fn.py
│   └── ad_hoc.py
├── aggregate.py
├── backtest.py        ← rolling window evaluator
├── metrics.py
└── persist.py         ← guarda predicciones con (model_version_id, snapshot_hash)
```

## Qué presentamos en el deck

Lámina dedicada a las **3 lecturas**:
- (a) Implied path SOFR → traza azul.
- (b) CME FedWatch (path mediano por probs) → traza gris.
- (c) Modelo Mercantil → traza verde + intervalo 80%.

Más una **anotación**: skill score vs implied path en horizonte 6 meses, ventana
rolling 24 meses. Si es positivo se muestra con check; si es negativo, se muestra
con la nota "modelo sin ventaja medible este horizonte".

## Pendientes para la próxima sesión

1. ¿Trabajamos primero el modelo solo en USA, o también en Venezuela (BCV) en
   paralelo? Recomendación: USA primero (datos limpios), Venezuela en Fase 5
   avanzada.
2. ¿Hay preferencia de framework (statsmodels + scikit + bayesian via pymc)?
   Recomendación: stack simple primero (statsmodels + scikit) — bayes solo si
   añade valor mensurable.
3. ¿Qué dataset macro usamos como base? FRED ALFRED es lo más limpio para
   vintage; alternativa Refinitiv si tenemos.
