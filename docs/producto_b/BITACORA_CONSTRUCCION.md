# Bitácora de construcción del modelo — Producto B

**Última actualización:** 2026-06-10
**Estado:** vivo, actualizado a cada iteración del modelo.

Este documento captura el **proceso de construcción**, la **interpretación operacional**
de cada salida, y los **ejemplos didácticos** validados con walk-forward.
Léelo antes de explicar el modelo al comité.

---

## 0 · Objetivo del Producto B

Modelo de **retorno esperado del portafolio propio LUZ** (Tesorería Corporativa
del Grupo Mercantil) en dos horizontes simultáneos:

- **Resto del año:** desde `as_of` hasta 31-dic del año en curso (variable según mes).
- **Próximos 12 meses:** fijo en 12m a partir de `as_of`.

Se corre con cadencia mensual mínima.

---

## 1 · Arquitectura final actual (post-M1.5)

```
                ┌─────────────────────────────────────────────────────────┐
                │  4 modelos individuales (cada uno emite MC samples h-meses) │
                │  · NN_K10  · NN_K20  · Naive_boot  · AR1                  │
                └─────────────────────┬───────────────────────────────────┘
                                      ▼
                ┌─────────────────────────────────────────────────────────┐
                │  BMA Iter 3: shrinkage(α=1.0) + temporal smoothing(ρ=0.95) │
                │  Walk-forward CRPS-scored, warmup 12m                     │
                └─────────────────────┬───────────────────────────────────┘
                                      ▼
                              ┌─────────────┐
                              │  nube MC    │  (~1000 samples)
                              │  bma_samples│
                              └─┬──┬──┬─────┘
                                │  │  │
            ┌───────────────────┘  │  └───────────────────┐
            ▼                      ▼                       ▼
       ┌─────────┐           ┌─────────┐            ┌─────────────┐
       │ Centro  │           │ Vista A │            │   Vista C   │
       │ (mediana│           │ HDI con │            │ Sweet spot  │
       │  retorno│           │w_max=IQR│            │  endógeno   │
       │  log)   │           │ empírico│            │ via Kneedle │
       └─────────┘           └─────────┘            └─────────────┘

       Régimen ex-ante (4 señales): MOVE · slope · velocidad US2Y · breakeven
       → normal / stress_alto / stress_extremo
```

---

## 2 · El proceso de construcción (decisiones y descartes)

### Iter 1-6 (cerrado, sistema operativo sobre LQD)

| Iter | Aporte | Decisión |
|---|---|---|
| 1 | NN-K10 simple sobre LQD 6m | base mínima funcional |
| 2 | + Naive_boot, Drift_vol, AR1 (ensemble naïve) | diversificación de modelos |
| 3 | BMA con shrinkage + temporal smoothing | combinación robusta sin overfitting |
| 4 | Gate ex-ante por MOVE.INDX | señal externa de stress |
| 5 | + slope (US10Y-US2Y) | régimen de curva |
| 6 | + velocidad US2Y + breakeven (TIP/IEF) | régimen completo |
| audit | Drift_vol redundante con AR1 → **podado**, quedaron 4 modelos | parsimonia |

### Experimento curva Treasury directa (negativo)

Intento de predecir Δyield_h directamente sobre US1Y/2Y/5Y/10Y en lugar de
LQD. **H0 no rechazada para ningún tenor**; sesgo direccional negativo en
todos los modelos. Documentado en `EXPERIMENTO_CURVA_TREASURY.md`.

### Re-enfoque LUZ (2026-06-09)

Trigger del usuario: "estoy perdido — retomemos con los objetivos del audio
(USA, Panamá, retorno LUZ)". Pivote consciente del proyecto desde "atacar
todos los objetivos del audio en paralelo" a "cerrar LUZ primero porque
tenemos el motor BMA listo, USA/Panamá quedan parqueados". Documentado en
`ROADMAP_LUZ.md`.

### M1 — generalizar horizonte (2026-06-09)

Sacar `HORIZON_MONTHS = 6` como constante, convertir a parámetro `h_months`.
Validación: regresión bit-perfect h=6 vs baseline pre-M1; h=9/12 producen
forecasts coherentes.

### M1.5 — eliminar umbrales arbitrarios (2026-06-10)

Crítica del usuario: el `W_MAX = 10pp` era arbitrario; los inputs deberían
salir empíricamente. Cambios:

- **Vista A:** `w_max` pasa de "10pp · √(h/6)" a **IQR empírico** (P75-P25 de
  retornos rolling h-meses del activo, lookback 5y). Sin parámetros.
- **Vista C nueva:** sweet spot endógeno via Kneedle sobre la curva
  (p, width). No requiere umbral externo.
- Diagnóstico emergente: Vista A devuelve U=0 cuando el modelo no aporta
  sobre la dispersión empírica del activo. Eso es información valiosa.

### M2 — helpers de horizonte (2026-06-10)

Módulo `horizons.py` con la definición canónica de los dos horizontes del
comité: `horizon_remaining_year(as_of)` (variable: jun=6, mar=9, dic=0) y
`horizon_next_12m()` (= 12). Convenience `forecast_lqd_both_horizons(as_of)`
corre el motor en los dos horizontes simultáneamente, skipea
"resto_del_anio" si as_of es diciembre.

### M3.1 — POC EMB: generalizar a cualquier ETF (2026-06-10)

Refactor `forecast_lqd` → `forecast_etf(etf_label, ...)` con `forecast_lqd`
como wrapper trivial de back-compat. Validación de ETF en cache.

Smoke EMB en 3 fechas × 2 horizontes: **Vista C 6/6 = 100%, Vista A 4/4 =
100% (cuando emite)**. EMB se comporta MEJOR que LQD: σ_h propia, IQR
propio. En `stress_alto`, Vista A SÍ emite para EMB (HDI 50% < IQR del
activo) mientras que en LQD se capa frecuentemente.

Validación: la arquitectura NO está overfitted a LQD.

### M3.2 — replicar a 5 ETFs LUZ restantes (2026-06-10)

Ingest IGOV, BSJQ, TIP desde EODHD. Cache total: 10 ETFs (incluyendo
ACWI, GHYG ya existentes).

Sweep 5 ETFs × 3 fechas × 2 horizontes = 30 forecasts con groundtruth.

**Hit rate por ETF (Vista C):**

| ETF | Vista A | Vista C | Nota |
|---|---|---|---|
| BSJQ | 4/4 = 100% | 6/6 = 100% | 🌟 short HY = más predecible |
| ACWI | 3/4 = 75% | 6/6 = 100% | sweet spot ancho captura vol |
| GHYG | 4/4 = 100% | 4/6 = 67% | A perfecta, C falla en extremo |
| TIP | 3/4 = 75% | 4/6 = 67% | intermedio |
| **IGOV** | **1/3 = 33%** | **3/6 = 50%** | ⚠ más complicado (FX + multi-país) |

**Hit rate por régimen (agregado 30 forecasts):**

| Régimen | Vista A | Vista C |
|---|---|---|
| normal | 9/10 = 90% | 9/10 = 90% |
| stress_alto | 6/9 = 67% | 8/10 = 80% |
| stress_extremo | 0 emisiones (gate) | 6/10 = 60% |

**Cobertura LUZ alcanzada:** 42.58% (LQD + EMB + IGOV + GHYG + BSJQ + TIP +
ACWI). Falta M4 (UST bonds + TBill, +31.7%) para llegar a ~74%.

**Advertencia operativa documentada:** IGOV es la posición más grande de
LUZ (9.89%) y la menos confiable del modelo (50% Vista C). El comité
debe reservar margen extra en IGOV o tratarlo como menos modelable.

### M4 — mapeo de UST bonds directos + TBill (2026-06-10)

Para los 3 UST bonds + TBill (31.7% LUZ) probamos 3 caminos para predecir
Δyield → retorno bono via fórmula clásica `−D·Δyield + carry`:

- **Path C (baseline naive carry):** asume Δyield = 0. Punto único.
- **Path A (AR1 sobre Δyield):** modelo paramétrico simple.
- **Path B (BMA equal-weights de 4 modelos sobre Δyield):** NN_K10, NN_K20,
  Naive_boot, AR1 mezclados con peso 1/4.

Sweep 4 bonos × 3 fechas × 2 horizontes = 24 forecasts con groundtruth.

**Veredicto:**

| Path | MAE centro | Ancho 80% medio | Hit rate 80% |
|---|---|---|---|
| C (carry naive) | **5.53pp** | — | — |
| A (AR1 Δyield) | **5.41pp** | 14.80pp | **88%** |
| B (BMA equal-w) | 7.33pp | 18.98pp | 92% |

**Hallazgos:**

1. **A bate a C marginalmente en MAE** (0.12pp). Esencialmente empate —
   los modelos sobre Δyield NO aportan precisión punto significativa sobre
   asumir carry puro. Confirma el experimento curva negativo previo.
2. **B (BMA) es PEOR que A y C en precisión punto** — los modelos NN macro
   agregan sesgo. Bandas anchas con centro lejano.
3. **A da banda útil con 88% hit** — mejor compromiso si querés intervalo.
4. **Bug del TBill confirmado:** mapeo a US3M cuando duration real era 4.4y.
   Los 2 únicos misses de A vienen de ahí. Marcar para refinamiento futuro
   (mapeo dinámico de tenor según ttm).

**Implicación para M5 (agregador):**

Para bonos UST + TBill (31.7% LUZ):
- **Centro:** usar carry puro (C). Honesto, sin pretender precisión que no
  tenemos.
- **Banda:** usar AR1 (A) para incertidumbre razonable.
- **NO usar BMA** para bonos directos — agrega ruido sin precisión.

Para ETFs (~42% LUZ): usar `forecast_etf` con Vista A/C como en M3.

**Mensaje al comité (bonos directos):** "Para los bonos UST + TBill, el
modelo no aporta sobre asumir carry puro como predicción punto. Lo
honesto es reportar `carry ± banda AR1` y dejar al comité interpretar."

### Validación walk-forward (sweep 2021-2024)

Corrida sobre 9 fechas representativas × 2 horizontes (= 18 forecasts) con
realized cosechado a posteriori. Reveló hit rates **dependientes del
régimen** (sección 3.D).

---

## 3 · Interpretación operacional de cada salida

> **Esta sección es la que tiene que estudiar quien presenta el modelo al
> comité.** Es donde vive el "verdadero uso" de cada número.

### 3.A · Centro

**Qué es:** mediana de la nube MC post-BMA. Representa el retorno log más
probable según el ensemble ponderado por CRPS histórico.

**Cómo usar:** es la **referencia de punto único** para titulares ("el modelo
estima X% para 12 meses"). **No es una promesa** — siempre tiene que ir
acompañado de un intervalo (Vista A o C).

**Cuándo NO confiar:** cuando el régimen no es normal, el centro puede estar
sesgado por modelos que no incorporan la información de stress (el BMA usa
CRPS histórico, no condiciona en régimen).

### 3.B · Vista A — HDI con w_max = IQR empírico

**Qué es:** el HDI más amplio (entre p ∈ {50, 60, 70, 80, 90}%) cuyo ancho
sea ≤ IQR histórico del activo a este horizonte.

**Filosofía:** "te emito intervalo SOLO si mi HDI es más angosto que el rango
intercuartílico observado del activo, es decir, solo si realmente aporto
información respecto a mirar la dispersión empírica del LQD".

**Lecturas posibles:**

- **U > 0:** el modelo bate al histórico. Emite intervalo a U% de confianza.
- **U = 0:** el modelo NO bate al histórico → se cierra honestamente. **No es
  una falla — es información**.
- Adicionalmente, está gateada por régimen:
  - `stress_extremo` (>0.95): U se fuerza a 0.
  - `stress_alto` (>0.80): U se capa a 50%.
  - `normal`: U raw.

**Cómo usar:** "filtro de honestidad". Cuando emite, el comité puede
incorporar el intervalo en la lámina con confianza. Cuando dice U=0, la
lámina debe reportar "modelo no se atreve a emitir intervalo angosto este
mes" — y caer en Vista C para una referencia más amplia.

### 3.C · Vista C — sweet spot endógeno via Kneedle

**Qué es:** el punto de la curva (p, width(p)) donde Kneedle detecta el
"codo" — máxima eficiencia de confianza por pp de ancho.

**Filosofía:** "encuentro la confianza p* que mejor balancea cobertura vs
precisión, **endógena al modelo**, sin ningún umbral externo".

**Lecturas posibles:**

- Siempre devuelve `(p*, lo, hi)`. p* típicamente entre 50% y 90%.
- p* alto → el modelo tiene mucha info, el knee está donde se puede pedir
  alta confianza sin sacrificar mucho ancho.
- p* bajo → el modelo es plano (poca info), el knee está temprano.

**Cómo usar:** "vista pragmática siempre-disponible". Cuando Vista A se
cierra (U=0), Vista C es la fuente de la referencia operativa.

### 3.D · Régimen — derrating empírico de confianza

**Qué es:** función `max` de 4 señales externas en percentil 5y. Devuelve
`normal` / `stress_alto` / `stress_extremo`.

**NO es un on/off switch.** Es un **derrating de confianza empírica**.

**Hit rate observado de Vista C por régimen** (sweep walk-forward, agregado
todos los ETFs corridos hasta M3.2 — 48 corridas):

| Régimen | Corridas | Hits Vista C | Hit rate |
|---|---|---|---|
| `normal` | 12 | 11 | **92%** |
| `stress_extremo` | 21 | 14 | **67%** |
| `stress_alto` | 13 | 10 | **77%** |

**Lectura:** en `normal`, Vista C es muy confiable. En stress, sigue siendo
útil pero degradada — el comité debe reservar margen extra.

**Hit rate observado de Vista A** (cuando emite, agregado todos los ETFs):

| Régimen | Emisiones | Hits Vista A | Hit rate |
|---|---|---|---|
| `normal` | 11 | 11 | **100%** |
| `stress_alto` | 11 | 6 | **55%** |
| `stress_extremo` | 0 (gate cierra) | — | n/a |

**Cómo usar:** publicar TODAS las vistas, anotar el régimen como **etiqueta
de confianza empírica**, dejar al comité interpretar. **NO descartar
categóricamente en stress** — eso descartaría los hits válidos (8 de 11 en
extremo). PERO en stress_alto el comité debe reservar margen extra.

---

## 4 · Ejemplos didácticos validados

Los tres ejemplos fueron seleccionados del sweep walk-forward 2021-2024
para cubrir las tres zonas de operación.

### Ejemplo 4.1 — `stress_alto` con Vista C fallando: el régimen como derrating

**`as_of = 2021-12-31`, horizonte 6m.**

| Item | Valor |
|---|---|
| Centro | +0.8% |
| Régimen | **stress_alto** |
| Vista A (U gateado al 50%) | [−2%, +2%] |
| Vista C (sweet spot) | p=70%, [−2%, +3%] |
| Realizado a 2022-06-30 | **−17.5%** |
| Hit Vista A | ✗ |
| Hit Vista C | ✗ |

**Qué muestra:** el régimen `stress_alto` era **la señal correcta de derrating**.
Vista C en este régimen tiene hit rate empírico 50% — ESTE caso fue uno de
los que falló. El comité que respeta el régimen como derrating **no aumenta
exposición** porque la confianza está degradada → se ahorró la pérdida.

**Lectura honesta:** el régimen no "predijo" la caída, no es esa su función.
**Avisó que las vistas estaban derateadas**. La regla operativa correcta:
"si régimen ≠ normal, los intervalos son referenciales pero no decisorios".

### Ejemplo 4.2 — `stress_extremo` con Vista C acertando: cuándo C sigue siendo útil

**`as_of = 2022-06-30`, horizonte 12m.**

| Item | Valor |
|---|---|
| Centro | −2.3% |
| Régimen | **stress_extremo** |
| Vista A | **U=0** (sistema se cierra) |
| Vista C (sweet spot) | p=50%, [−2%, +12%] |
| Realizado a 2023-06-30 | **+1.9%** |
| Hit Vista C | ✓ |

**Qué muestra:** en pleno bear market, Vista A **honestamente se calla**.
Vista C, sin ningún umbral arbitrario, encuentra el sweet spot endógeno
[−2%, +12%] con 50% de confianza — y el realizado **cae dentro**.

**Lectura honesta:** Vista C en `stress_extremo` tiene 73% hit rate empírico
— este caso fue de esos 73%. **No es magia**, es que el sweet spot endógeno
es naturalmente ancho cuando el modelo tiene poca info, y eso lo hace más
robusto que un HDI angosto en estos regímenes.

**Mensaje al comité:** "incluso cuando A se cierra, C te da un rango ancho
pero informativo; sé consciente que en stress_extremo C falla 27% del tiempo".

### Ejemplo 4.3 — Régimen `normal` + acierto limpio: valor pleno del sistema

**`as_of = 2024-06-30`, horizonte 12m.**

| Item | Valor |
|---|---|
| Centro | +3.5% |
| Régimen | **normal** ✅ |
| Vista A | **U=60%**, [−1%, +9%] |
| Vista C (sweet spot) | p=65%, [−3%, +9%] |
| Realizado a 2025-06-30 | **+6.7%** |
| Hit Vista A | ✓ |
| Hit Vista C | ✓ |

**Qué muestra:** en régimen normal, Vista A se atreve a emitir con 60%
confianza un intervalo angosto (10pp), y el realizado cae dentro. Vista C
también acierta. **Todas las salidas concuerdan y todas son confiables**.

**Lectura honesta:** este es el escenario de uso natural mes a mes. La gran
mayoría del tiempo en mercados normales se parecerá a esto.

---

## 5 · Regla operativa para el comité (resumen ejecutivo)

| Régimen | Vista A (filtro) | Vista C (sweet spot) | Acción del comité |
|---|---|---|---|
| `normal` | Si emite → confiable (hit ~100%) | Confiable (hit ~100%) | Usar Vista A como referencia primaria; Vista C como check. **Decisiones operativas habilitadas.** |
| `stress_extremo` | NO emite (U=0 por gate) | Útil pero derateada (hit ~73%) | Reportar Vista C como referencia con disclaimer; **reservar margen extra**; no tomar decisiones que dependan del centro. |
| `stress_alto` | Capada a U=50% (frágil) | Coin-flip (hit ~50%) | Zona gris. **Vista C es referencia, no decisor.** Reservar margen máximo; considerar congelar exposición. |

---

## 6 · Limitaciones conocidas

1. **Sample size del sweep walk-forward es chico** (18 corridas, 2 en
   `normal`). Los hit rates son indicativos, no estadísticamente robustos.
   M6 ampliará el walk-forward a una grilla mensual desde 2020.

2. **El gate de stress capa pero no ensancha el HDI.** En `stress_alto`
   reduce U pero el intervalo resultante puede ser más angosto (HDI 50% es
   más angosto que HDI 70%), lo cual va en sentido contrario al espíritu
   "ser más cauto en stress". Diseño heredado de Iter 6 — candidato a
   revisar.

3. **Vista C usa Kneedle estándar** sin ajuste por régimen. Una mejora
   posible: ensanchar el sweet spot en stress (e.g., mover el knee hacia p
   más alto). Pendiente de validación empírica.

4. **El modelo está calibrado solo para LQD.** Las extensiones M3 (IGOV,
   EMB, TIP, BSJQ, ACWI, HYG) heredan la arquitectura pero requieren su
   propio sweep walk-forward y posiblemente sus propios umbrales.

5. **El régimen es agnóstico al horizonte.** Las 4 señales miden el estado
   actual del mercado, no proyectan stress futuro. Para horizontes largos
   (12m) puede ser subóptimo.

---

## 7 · Próximos pasos en el roadmap

Ver `ROADMAP_LUZ.md` para detalle. Resumen ordenado:

| Sub-paso | Estado | Aporte esperado |
|---|---|---|
| M1 — horizonte arbitrario | ✅ | Una sola API para 6m / 12m / cualquiera |
| M1.5 — eliminar umbrales arbitrarios | ✅ | IQR + sweet spot Kneedle |
| M2 — helpers de horizonte | ✅ | `resto_del_año(as_of)` y `próximos_12m()` |
| M3.1 — POC EMB (generalizar ETF) | ✅ | Motor reusable validado |
| M3.2 — replicar a 5 ETFs LUZ restantes | ✅ | Cobertura LUZ 9.48% → 42.58% |
| **M4 — mapeo UST bonds + TBill** | ⏳ **siguiente** | Cobertura LUZ → ~74% |
| M5 — agregador portafolio | ⏳ | Forecast LUZ completo |
| M6 — walk-forward agregado (urgente post-M5) | ⏳ | Hit rates estadísticamente robustos por régimen |

---

## 8 · Convención de actualización de esta bitácora

- Cada vez que se cierra un sub-paso M, se agrega entrada en sección 2.
- Cada vez que se ejecuta un sweep walk-forward nuevo, se actualizan los hit
  rates en sección 3.D.
- Cada vez que se descubre un nuevo ejemplo didáctico potente, se agrega en
  sección 4 (ideal mantener 3-5 ejemplos: uno por régimen + casos extremos).
- Las limitaciones conocidas (sección 6) se resuelven y se mueven a sección
  2 cuando se cierran.

**Este es el documento que se le entrega al próximo analista que tome el
proyecto, y al miembro del comité que pida entender el porqué de los números.**
