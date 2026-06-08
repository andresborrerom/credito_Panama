# Experimento: BMA sobre cambios de yield Treasury (US1Y / US2Y / US5Y / US10Y)

**Fecha:** 2026-06-08 | **Autor:** A. Borrero | **Branch:** `claude/tasas-mercantil-report-Q8sFt`

---

## 1. Motivación

LQD es proxy del segmento medio-largo IG (duration ~8.5y). El driver fundamental
es la curva Treasury y la trayectoria Fed. Hipótesis previa: predecir yields
directamente eliminaría la necesidad de gates parchados (Iter 4-6 sobre LQD).

## 2. Hipótesis científicas

- **H0 (nulo):** el BMA Iter 3 sobre Δyield_6m **no mejora** al baseline trivial
  *Δyield = 0* (mantener el yield actual) en ningún plazo.
- **H1:** existe al menos un plazo donde se cumplen simultáneamente:
  - Δ MAE vs baseline ≤ −10% (margen material)
  - Cobertura HDI50 ∈ [45%, 55%] (calibración honesta)

## 3. Diseño experimental

| Elemento | Especificación |
|---|---|
| Plazos | US1Y, US2Y, US5Y, US10Y (yields EOM, EODHD `*.INDX`) |
| Horizonte | 6 meses |
| Período backtest | 2020-01 a 2024-06 (walk-forward causal, 54 fechas) |
| Modelos | NN_K10, NN_K20, Naive_boot, AR1 (mismos del capítulo LQD) |
| Combinador | BMA Iter 3: shrinkage α=1.0 + smoothing ρ=0.95 |
| Warmup | 12 meses de pesos equal antes de activar shrinkage |
| Baseline | Δyield = 0 (no-change naïf) |
| Métricas | CRPS, MAE, Cobertura HDI50, Sharpness (bps), Sesgo, fracción U=0 |

Target predicho: `Δyield_h(t) = yield(t+h) − yield(t)` en puntos porcentuales.

## 4. Resultados

| Plazo | n | CRPS BMA | MAE BMA | MAE baseline | **Δ MAE (%)** | **Cobertura HDI50** | Sharpness (bps) | Sesgo (pp) | Vol realizada (pp) | Mean realizado (pp) | Frac U=0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US1Y  | 54 | 0.590 | 0.741 | 0.734 | **+1.0%**  | 37.0% | 75 | −0.24 | 0.39 | +1.01 | 81.5% |
| US2Y  | 54 | 0.529 | 0.665 | 0.691 | **−3.8%**  | 42.6% | 76 | −0.22 | 0.37 | +0.89 | 83.3% |
| US5Y  | 54 | 0.410 | 0.560 | 0.583 | **−3.8%**  | 38.9% | 66 | −0.31 | 0.33 | +0.68 | 77.8% |
| US10Y | 54 | 0.392 | 0.557 | 0.527 | **+5.7%**  | 33.3% | 60 | −0.30 | 0.31 | +0.59 | 77.8% |

## 5. Veredicto vs hipótesis

| Plazo | Criterio Δ MAE ≤ −10% | Criterio Cob ∈ [45, 55] | **Veredicto** |
|---|---|---|---|
| US1Y  | NO (+1.0%)  | NO (37%) | FAIL |
| US2Y  | NO (−3.8%)  | NO (42.6%) | FAIL |
| US5Y  | NO (−3.8%)  | NO (38.9%) | FAIL |
| US10Y | NO (+5.7%)  | NO (33.3%) | FAIL |

**Conclusión estadística:** H0 no se rechaza para ningún plazo.
Existe evidencia *débil* de skill en US2Y/US5Y (−3.8% MAE cada uno),
pero ninguno alcanza el margen material exigido.

## 6. Diagnóstico

Tres patrones consistentes en los 4 plazos:

1. **Sesgo direccional negativo (−0.22 a −0.31 pp)** en todos los modelos:
   los 4 modelos predicen sistemáticamente bajadas. El realizado fue
   subidas (mean +0.59 a +1.01 pp). Causa: los modelos están entrenados con
   2010-2020, década de yields a la baja; extrapolan mal el régimen 2022-24.

2. **Sub-cobertura sistemática (33-43%)**: los intervalos son angostos pero
   sesgados — el HDI50 promete cubrir el 50% pero solo cubre 33-43%.
   El sistema declara confianza falsa.

3. **Fracción U=0 entre 77-83%**: con W_max=50 bps, el sistema casi nunca
   puede emitir afirmación útil. La volatilidad realizada del Δyield_6m es
   demasiado alta para el W_max definido.

Patrón unificador: **los modelos no atrapan el cambio de régimen**. Lo mismo
que ocurrió con LQD en jul-2021/mar-2022, pero ahora aplicado a yields
directamente sin posibilidad de mitigar vía gates externos (los gates aquí
serían los mismos del Iter 6 y aplicarían sobre el mismo problema).

## 7. Implicaciones

### Para el sistema operativo

El experimento **no produce un sistema operativo superior** al pipeline LQD
Iter 6. Por lo tanto:

- **Iter 6 sobre LQD se mantiene como el sistema operativo final** del producto B.
- La derivación mecánica `dLQD ≈ −D · Δyield + carry` no es viable como sustituto
  (correlación 0.28 con LQD real, MAE 0.95 log-ret en validación previa).

### Para futuras iteraciones

Quedan documentados los caminos que sí podrían funcionar pero requieren
trabajo no trivial:

1. **Modelos específicos de curva** (Nelson-Siegel-Svensson, dynamic factor
   models): captan la estructura de yield curve completa en lugar de tratar
   cada plazo como serie independiente.
2. **Modelos basados en equilibrium** (Taylor rule, term premium decomposition,
   ACM): rompen el sesgo histórico introduciendo anchoring fundamental.
3. **Horizontes más cortos** (1m o 3m): autocorrelación más fuerte, menos
   afectados por el cambio de régimen lento.
4. **Features macro distintos**: breakeven inflation, Fed Funds Futures
   implied path, NFCI — más leading que los features actuales basados en
   inflación/desempleo realizados.

Estos son sprints completos, no extensiones del approach actual.

## 8. Artefactos generados

- `scripts/smoke_curve_us10y.py` — smoke inicial sobre US10Y.
- `scripts/bma_curve_all_tenors.py` — experimento sistemático 4 plazos.
- `src/tasas_mercantil/producto_b/curve_target.py` — modelos Δyield.
- `data/external/tasas_mercantil/bma_curve_all_tenors.parquet` — métricas.
- `data/external/tasas_mercantil/bma_curve_all_tenors.png` — figura comparativa.
- Yields cacheados: `us1y_eom.parquet`, `us2y_eom.parquet`, `us5y_eom.parquet`,
  `us10y_eom.parquet`.

## 9. Decisión final

**El sistema operativo del Producto B (LQD-gates Iter 6) se cierra como versión
estable**. Pipeline: 4 modelos (NN_K10, NN_K20, Naive_boot, AR1) → BMA con
shrinkage α=1.0 y smoothing ρ=0.95 → score U gated por 4 señales externas
(MOVE, slope, velocidad US2Y, breakeven inflation), W_max=10pp.

El experimento curva queda como **negativo informativo documentado**.
