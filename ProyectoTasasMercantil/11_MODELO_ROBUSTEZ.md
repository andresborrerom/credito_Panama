# 11 · Modelo predictivo — esqueleto del documento de robustez

Equivalente a `saa-robustness-skeleton.md` del proyecto hermano. Define el
documento que demuestra que el modelo Mercantil es defendible ante IC, riesgos
y auditoría.

Política: **el documento se actualiza con cada bump de `model_version_id`**.
Lo que aquí esté en estado "pendiente" no se publica del modelo en producción.

---

## Versión Técnica (10–15 pp)

**Audiencia**: comité directivo, comité de riesgos, validación interna, futuras
auditorías regulatorias.

### Índice

1. **Resumen ejecutivo** (½ pp)
   - Conclusión: qué hace el modelo, por qué es robusto, qué no hace.
   - Skill score promedio actual y por régimen.

2. **Objetivo y alcance** (½ pp)
   - Pronóstico de tasas para horizonte ≤ 12 meses; foco en Fed Funds y UST.
   - Lo que el modelo **no** decide: nivel "correcto" de tasas para el negocio,
     decisiones de hedge, allocation táctico.

3. **Universo de datos y ventanas escalonadas** (1 pp)
   - Tabla de disponibilidad por feature (ver `07_MODELO_PREDICTIVO.md` § 2).
   - Justificación de ventana 1994+ (Fed Funds target explícito).
   - Justificación de ventanas modernas 2018+ (SOFR era).
   - Vintage data (FRED ALFRED) y por qué importa.

4. **Marco conceptual** (1 pp)
   - Por qué descomposición nominal = real + breakeven + term premium.
   - Por qué incluir reaction function (no solo implied path).
   - Por qué incluir pieza editorial con backtest condicional.

5. **Especificación del modelo** (2–3 pp)
   - Pieza A: implied path + risk premium term-structure (Cieslak-Povala).
   - Pieza B: Taylor rule bayesiana con prior Taylor 1993, smoothing,
     updating con macro vintage 1994+.
   - Pieza C: hipótesis editoriales con validación por patrón histórico.
   - Pieza D: descomposición term-premium (ACM o Kim-Wright).
   - Agregación con pesos congelados en calibración 2000-2009.

6. **Modelos rivales** (1 pp)
   - Lista completa (5 rivales).
   - Por qué incluir cada uno.
   - Tabla comparativa de qué información aprovecha cada rival.

7. **Protocolo de backtest** (1 pp)
   - Walk-forward estricto.
   - Hiperparámetros en ventana separada congelados antes de evaluación.
   - Point-in-time strict (uso de vintage data).
   - 9 regímenes reportados separadamente.
   - Bootstrap del backtest para estabilidad del ranking.

8. **Resultados** (2 pp)
   - Tabla maestra: skill score por horizonte × régimen × rival.
   - Calibración distribucional: PIT histograms, Brier scores.
   - Sesgo direccional y su evolución temporal.
   - Cobertura empírica del IC 80% por régimen.

9. **Sensibilidades y límites del modelo** (1 pp)
   - Régimen no observado en training (cambio de mandato Fed, dolarización
     en otro contexto, intervención política directa).
   - Dependencia de vintage data de FRED (qué pasa si ALFRED cambia metodología).
   - Calibración fija — no se reentrenan hiperparámetros con cada corte.
   - El modelo **no** captura: shocks no-económicos (guerra, default soberano,
     evento sistémico) — se reportan en lámina aparte sin pretender modelarlos.
   - **Cuándo no usar el modelo**: en los primeros 30 días tras un evento
     extremo no observado en training, mostrar solo implied + FedWatch.

10. **Gobernanza del modelo** (½ pp)
    - Revisión trimestral.
    - Triggers de revisión event-driven:
      - Cambio de chair Fed.
      - Cambio de framework de política monetaria (FAIT, dual mandate refresh).
      - Skill score rolling 24M se cruza por debajo de +0.05.
      - Cualquier rival nuevo lo bate por > 5 pp en 6 meses consecutivos.
    - Sign-off de promoción a `model_version_id` mayor por Andrés.
    - Bitácora de cambios (changelog) en `model_version_id`.

11. **Reproducibilidad y auditoría** (½ pp)
    - Cada predicción guarda `(model_version_id, snapshot_hash, git_sha)`.
    - El backtest entero se puede correr de nuevo con `make backtest` y debe
      dar los mismos números.
    - Tests automáticos: `test_no_lookahead.py`, `test_distribution_calibration.py`.

12. **Referencias bibliográficas**
    - Taylor (1993) — original Taylor rule.
    - Cieslak & Povala (2015) — term premium decomposition.
    - Adrian, Crump & Moench (2013) — ACM model.
    - Kim & Wright (2005) — Kim-Wright term premium.
    - Bauer & Rudebusch (2014) — risk premia en futuros de tasas.
    - Gürkaynak, Sack & Wright (2007) — UST yield curve methodology.
    - Diebold & Mariano (1995) — test de equivalencia predictiva.

---

## Versión Ejecutiva (2 pp)

**Audiencia**: directivos del grupo Mercantil sin background técnico.

### Estructura

**Página 1**
- **Lo que el modelo dice este mes** (3 bullets).
- **Cómo se compara con el mercado** (1 gráfico de las 3 lecturas).
- **Por qué se puede confiar** (3 bullets sobre robustez verificable).

**Página 2**
- **Lo que el modelo NO hace** (3 bullets de límites).
- **Cuándo NO usarlo** (1 párrafo).
- **Próximos pasos del modelo** (cambios planificados).

Lenguaje: cero jerga técnica. "Skill score" se explica como "porcentaje
promedio de mejora vs la lectura que da el mercado". "Calibración" no
aparece; se reemplaza por "cuando el modelo dice 70% de probabilidad, el
evento ocurre ~70% del tiempo".

---

## Apéndice A · Bootstrap del backtest (2026-05-28, modelo v0.3.0, vintage MENSUAL)

Block bootstrap (block_size = 6 meses, 1000 réplicas) sobre 37 fechas
mensuales (2022-04 a 2025-04) que cubren los tres regímenes
hike-agresivo / hold / cut-cycle.

| Horizonte | n_obs | Skill mediano | IC 80% | P(skill>0) | P(pasa fail-loud) |
|---|---:|---:|---|---:|---:|
| 1M  | 37 | +18.1% | [+7.3%, +33.4%] | 99% | 94% |
| 3M  | 37 | +12.3% | [+6.9%, +22.5%] | 100% | 98% |
| 6M  | 37 | +24.5% | [+21.5%, +28.7%] | 100% | **100%** |
| 12M | 37 | +46.0% | [+40.4%, +52.4%] | 100% | **100%** |

**Lectura honesta**:
- **6M y 12M**: certificable. El modelo supera el umbral fail-loud (+5%
  skill vs naive) en el 100% de las réplicas. Mensajes de horizonte
  semestral / anual pueden firmarse con convicción Alta sin caveat.
- **1M y 3M**: ya casi certificable (94% / 98%). Mensajes de horizonte
  corto deben firmarse con convicción Media-Alta, no Alta.
- El régimen actual (cut continuando) es donde el modelo funciona mejor
  según el backtest por régimen, pero la muestra incluye también hike
  rápido 2022-23 donde el modelo apenas supera al naive.

**Audit no look-ahead — verificado empíricamente 2026-05-28**:

| Fecha as_of | Vintage PCE efectivo | Valor PCE jun-22 |
|---|---|---:|
| 2022-07-31 | 2022-07-31 (primer release) | 122.948 |
| 2022-09-30 | 2022-09-30 | 123.258 |
| 2024-01-31 (post BEA re-anchor) | 2024-01-31 | 114.297 |
| Hoy 2026-05-28 | 2026-04-30 | 114.376 |

El número cambia con la fecha del corte porque BEA revisa la serie y
re-anchorea la base. El store nunca usa vintage_date > as_of + T3. El
backtest a 2022-07-31 usó 122.948, no 114.376 (el valor de hoy).

**Backfill mensual vs trimestral — comparativa**:

| Horizonte | Skill mediano QE (antes) | Skill mediano ME (mejorado) |
|---|---:|---:|
| 1M | +17.4% | +18.1% |
| 3M | +10.6% | +12.3% (P(fail-loud) 91% → 98%) |
| 6M | +23.3% | +24.5% |
| 12M | +45.5% | +46.0% |

La diferencia es pequeña pero el cambio metodológico es correcto: en
cada fecha del backtest, el modelo ahora ve el dato del día del release
(no el de 3 meses después). Forma documentada en
`12_DATA_AUDIT_FINDINGS.md` (entrada 2026-05-29).

## Apéndice B · Sensibilidad de la Pieza B a R* y NAIRU (2026-05-28)

Snapshot: mayo 2026, Mercantil v0.3.0 a 24M.

| R* (%) | NAIRU (%) | Taylor en t | Mercantil 24M | Gap vs mercado |
|---:|---:|---:|---:|---:|
| 0.0 | 4.0 | 1.71% | 3.54% | +32 bps |
| **0.5** | **4.0** | **2.21%** | **3.62%** | **+24 bps** (baseline) |
| 1.0 | 4.0 | 2.71% | 3.71% | +16 bps |
| 1.5 | 4.0 | 3.21% | 3.79% | +8 bps |

(NAIRU varía ±0.5% mueve gap solo ±2-3 bps. R* domina.)

**Lectura honesta**:
- Asumimos R* = 0.5% (estimación pre-COVID).
- Holston-Laubach-Williams (NY Fed) sugiere R* ~1.0% post-COVID.
- Summers / Furman argumentan R* ~1.5-2.0% post-COVID.
- Si el consenso académico es R* = 1.0%, **el gap real es +16 bps**, no +25 bps.
- Si R* es 1.5%, **no hay tesis** (gap +8 bps, indistinguible del mercado).
- El mensaje del corte 2026-05 declara explícitamente este caveat.

## Apéndice C · Performance por régimen (backtest 2022-2025)

| Régimen | h | Skill modelo agregado vs naive |
|---|---:|---:|
| Hike agresivo 2022-23 | 1M | **−0.1%** ❌ |
| Hike agresivo 2022-23 | 3M | +2.1% |
| Hike agresivo 2022-23 | 6M | +18.5% |
| Hike agresivo 2022-23 | 12M | +34.4% |
| Hold 2023-24 | 1M | +43.5% ✅ |
| Hold 2023-24 | 3M | +29.4% ✅ |
| Hold 2023-24 | 6M | +23.4% ✅ |
| Hold 2023-24 | 12M | +56.0% ✅ |
| Cut cycle 2024-25 | 1M | +36.4% ✅ |
| Cut cycle 2024-25 | 3M | +34.0% ✅ |
| Cut cycle 2024-25 | 6M | +49.8% ✅ |
| Cut cycle 2024-25 | 12M | +63.0% ✅ |

**Lectura honesta**: el modelo es excelente en hold y cut, débil en hike
sorpresa. El régimen actual (cut continuando) es favorable. **Riesgo asimétrico**:
si la Fed pivotea a hike por shock inflacionario, el modelo no lo detecta
rápido en horizonte 1M.

---

## Política de actualización

| Trigger | Acción |
|---|---|
| Bump de patch (`x.y.Z`) | Notar en changelog, no se re-publica el doc. |
| Bump menor (`x.Y.0`) | Re-render del doc técnico, no del ejecutivo. |
| Bump mayor (`X.0.0`) | Re-render de ambos + revisión de IC. |
| Cambio de régimen detectado | Anexo de régimen agregado a § 9. |
| Fallo del fail-loud | Sección 8 actualizada con análisis post-mortem. |

## Lo que NO va en este documento

- Resultados específicos del corte mensual (eso va al deck).
- Mensajes editoriales del mes (eso va a `mensajes_clave.yaml`).
- Datos internos del libro del banco (eso vive en un repo separado cuando se
  autorice).
