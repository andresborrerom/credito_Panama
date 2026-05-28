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
