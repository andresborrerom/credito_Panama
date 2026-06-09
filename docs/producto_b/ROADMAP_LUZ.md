# Roadmap del Producto B — re-enfoque sobre portafolio LUZ

**Fecha del re-enfoque:** 2026-06-09
**Branch:** `claude/tasas-mercantil-report-Q8sFt`

---

## Contexto

Tras explorar BMA sobre LQD (Iter 1-6, sistema cerrado) y experimento de
curva Treasury directa (negativo, documentado en
`EXPERIMENTO_CURVA_TREASURY.md`), se re-enfocó el trabajo hacia el objetivo
real del Producto B: **modelo de retornos esperados del portafolio LUZ**
para tesorería del grupo.

El portafolio LUZ fue subido en
`ProyectoTasasMercantil/inputs_externos/portafolio_luz/`. Snapshot inicial
2026-06-09: USD 49.0 MM, 38 posiciones, cobertura modelo actual **9.5%**
(solo LQD vía Iter 6).

## Horizontes operativos (recurrentes)

El motor debe responder en DOS horizontes simultáneos:

1. **"Resto del año"** — desde `as_of` hasta 31-dic del año en curso.
   Variable según mes (al cierre de junio = 6m, al cierre de septiembre = 3m).
2. **"Próximos 12 meses"** — siempre 12m a partir de `as_of`. Fijo.

Esto se corre **regularmente** (cadencia mensual, mínimo) y debe estar
empotrado en el API.

## Outputs acordados (3 niveles complementarios)

### Output (3) — Mensaje de primera diapositiva

1-2 frases para el comité ejecutivo, por horizonte:

> "Retorno esperado de LUZ al cierre 2026 (X meses): centro Y%,
> con 60% de confianza entre A% y B%. Cobertura modelo Z% del portafolio."

### Output (1) — Bandas de confianza flexibles (7 vistas)

Todas computadas de la misma nube MC; el comité elige cuál ve en cada lámina.

| # | Forma | Lo que dice |
|---|---|---|
| 1 | Fijar rango, max confianza (= U actual) | "Con X% confianza, retorno entre A y B" |
| 2 | Fijar confianza, min rango (HDI nivel fijo) | "Al 80% confianza, retorno entre A y B" |
| 3 | Fan chart multi-banda (HDI 50/80/95) | Bandas superpuestas estilo BoE |
| 4 | Probabilidades direccionales | "P(retorno > 0%) = X%; P(> tasa lib. riesgo) = Y%" |
| 5 | Value at Risk (VaR 95) | "95% del tiempo no perdés más de X%" |
| 6 | Expected Shortfall (CVaR 95) | "Si te toca el peor 5%, perdés ~X%" |
| 7 | Cuantiles fijos (P5/P25/P50/P75/P95) | Tabla 5 puntos |

### Output (2) — Histograma completo del portafolio

Distribución MC completa del retorno LUZ, visualizada. Util para tesorería
y para enseñar al comité a leer probabilísticamente. Lectura del usuario:
"el más útil de todos pero requiere educación del consumidor".

## Plan de construcción (en este orden, una entrega a la vez con revisión)

### Paso M — Motor común (prerequisito de todo)

**M1.** Generalizar `src/tasas_mercantil/producto_b/forecast_api.py` para aceptar
horizonte arbitrario `h_months: int`. Hoy está hardcodeado a 6. Validar con
LQD a 6m, 9m, 12m que sigue funcionando.

**M2.** Helpers de horizonte:
- `horizon_remaining_year(as_of) -> int` (meses al 31-dic del año en curso).
- `horizon_next_12m() -> int = 12`.

**M3.** Replicar Iter 6 a las top 5 posiciones de LUZ que faltan:
- IGOV (ISHARES International Treasuries) — 9.89% LUZ
- HYG / GHYG (US&Intl High Yield) — 8.27% LUZ
- BulletShares 2026 HY (BSJQ) — 6.66% LUZ
- EMB (JP Morgan EM USD) — 4.28% LUZ
- TIP (TIPS Bond ETF) — 2.00% LUZ
- ACWI (MSCI ACWI) — 2.00% LUZ

Por cada uno: descargar serie en EODHD, validar Iter 6 funciona, métricas
walk-forward, ajustes mínimos si hace falta.

**M4.** Mapeo de los 3 UST bonds directos y TBill vía duration + Δyield del
plazo correspondiente (US10Y/US30Y/US1Y). Esto cubre 31.7% adicional sin
necesidad de un modelo ETF.

**M5.** Agregador a nivel portafolio LUZ:
- Para cada posición cubierta: nube MC × peso de la posición.
- Sumar las nubes ponderadas → nube agregada del portafolio.
- Asumir correlación implícita (no factor model formal — primer aproach).
- Para posiciones NO cubiertas (~20%): asumir retorno 0 ± vol histórica de
  la asset class.

**M6.** Métricas walk-forward del agregado vs realized portfolio return
(reconstruible de los snapshots históricos cuando los tengamos).

### Paso (3) — Mensaje primera diapo

Extraer del motor `M` por horizonte. Una función:
`compose_executive_summary(as_of) -> dict` que retorna el dict para los 2
horizontes con texto listo.

### Paso (1) — Bandas flexibles

Implementar las 7 views (utility functions sobre samples).
API: `forecast_luz_all_views(as_of, horizon) -> dict[view_name, value]`.

### Paso (2) — Histograma del portafolio

Visualización rica con matplotlib (KDE + HDIs marcados + VaR + ES anotados).
Persistir como PNG por (as_of × horizonte). Útil para enseñanza y reporte.

## Método

- **Ground truth + walk-forward causal** en todo. No fit-on-fly.
- **Una entrega por vez**, revisión del usuario antes de la siguiente.
- Cada entrega tiene su smoke test reproducible en `scripts/`.

## Lo que queda explícitamente fuera de este sprint

- Producto A (reporte mensual lectura editorial con escenarios formales).
- LLM Fedspeak / News sentiment.
- Modelos fundamentales (Taylor rule, factor model curva).
- Fase 3 del plan original (Panamá específicamente).
- Venezuela.

Registrado para sprints futuros.

## Estado al cierre del re-enfoque

| Artefacto | Estado | Path |
|---|---|---|
| Iter 6 LQD (sistema operativo) | ✅ Cerrado | `src/tasas_mercantil/producto_b/forecast_api.py` |
| Demo API Iter 6 | ✅ | `scripts/demo_forecast_api.py` |
| Experimento curva | ✅ Cerrado (negativo) | `docs/producto_b/EXPERIMENTO_CURVA_TREASURY.md` |
| Snapshot LUZ 2026-06-09 | ✅ | `ProyectoTasasMercantil/inputs_externos/portafolio_luz/snapshots/2026-06-09/` |
| **M1 — horizonte arbitrario en forecast_api** | ✅ Cerrado | `src/tasas_mercantil/producto_b/forecast_api.py` + `scripts/smoke_m1_horizons.py` |
| M2 — helpers `horizon_remaining_year` / `horizon_next_12m` | ⏳ Siguiente | — |
| M3 — replicar Iter 6 a 6 ETFs LUZ | ⏳ | — |
| M4 — mapeo UST bonds + TBill | ⏳ | — |
| M5 — agregador portafolio | ⏳ | — |
| M6 — walk-forward agregado | ⏳ | — |
| Output (3) mensaje 1ra diapo | ⏳ | — |
| Output (1) bandas flexibles | ⏳ | — |
| Output (2) histograma | ⏳ | — |

## Nota M1 (2026-06-09)

Cambios respecto al diseño original:
- `W_MAX` global → `DEFAULT_W_MAX_6M = 0.10` + `_default_w_max(h) = 0.10·√(h/6)`. Mantiene U comparable entre horizontes.
- `exclude_window_months` en NN escala a `max(7, h+1)` para protección look-ahead.
- Walk-forward ahora descarta fechas sin realized completo (afecta solo a horizontes largos cerca del límite de datos). Antes se imputaban como 0, contaminando los pesos BMA.
- Validación: regresión h=6 bit-perfect contra baseline pre-M1; h=9 y h=12 producen forecasts coherentes (centro y vol monótonos crecientes; AR1 toma la delantera a h=12).
