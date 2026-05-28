# 12 · Data audit findings

Bitácora de problemas y decisiones sobre la calidad y cobertura de las fuentes
de datos. Inspirada en `mercantil-saa/data_audit_findings.md`.

**Formato obligatorio por hallazgo:**

```
## YYYY-MM-DD — <título corto>

**Síntoma**: qué se observa, idealmente con números.
**Causa**: qué pasó realmente.
**Impacto en el modelo / reporte**: qué pieza se afecta.
**Mitigación adoptada**: qué hacemos ahora.
**Decisión metodológica**: cómo se documenta en el doc de robustez.
```

---

## 2026-05-28 — Bug "today" en plantilla Bloomberg (heredado de SAA)

**Síntoma**: en el proyecto hermano `mercantil-saa`, las primeras versiones
de las plantillas Bloomberg usaron el literal `"today"` en `=BDH(..., "today",
...)`. Al reabrir el archivo en otra fecha, Bloomberg recalculaba con la
fecha de apertura, mutando el snapshot del cierre de mes.

**Causa**: Bloomberg evalúa el string `"today"` y `=TODAY()` cada vez que se
abre el workbook, no una sola vez al guardar.

**Impacto**: pérdida de reproducibilidad del snapshot. Cualquier predicción o
gráfico derivado del archivo se vuelve no-replicable si el archivo se reabrió
en distinta fecha sin paste-values.

**Mitigación adoptada en `ProyectoTasasMercantil`**:
1. Ninguna celda usa `=TODAY()` ni `"today"` literal.
2. Todas las fórmulas referencian `'01_Parametros'!$B$3` (AS_OF), que es
   input manual fijo.
3. La hoja `00_Instrucciones` exige Paste Special → Values en los pasos 8 y 9
   antes de devolver el archivo.
4. Se registra `FECHA_GUARDADO_VALUES` (input manual) como evidencia de que
   el paste-values se realizó.

**Decisión metodológica**: registrar en `11_MODELO_ROBUSTEZ.md` § 11
(Reproducibilidad) que la plantilla está "frozen by design" y que la
auditoría de un corte verifica que `FECHA_GUARDADO_VALUES` esté presente.

---

## 2026-05-28 — Decisión de ventana histórica del modelo

**Síntoma**: tentación inicial de fijar ventana corta (2020+, 6 años).

**Causa**: arrancar el proyecto con la ventana del backfill de informes (5
cortes mensuales) sin separar el universo del modelo.

**Impacto**: con 6 años, el modelo no ve el régimen 2018 hike Powell, el
pivot dovish 2019, ni 2015-2018 normalización Yellen. Resultado: backtest
muestra al modelo solo en COVID + hike agresivo + hold, lo cual sobreajusta a
un tipo de régimen.

**Mitigación adoptada**: ventanas escalonadas según disponibilidad de feature
(`07_MODELO_PREDICTIVO.md` § 2). Universo de datos brutos desde 1994
(Greenspan target explícito). Calibración de hiperparámetros 2000–2009.
Evaluación walk-forward 2010-presente. Para features modernas (SOFR, SR3,
FedWatch) la evaluación es 2019+ con caveat declarado en el deck.

**Decisión metodológica**: documentar el corte 1994 en `11_MODELO_ROBUSTEZ.md`
§ 3 con la justificación. Régimen pre-1994 se discute cualitativamente en
anexo, no entra al training del modelo productivo.

---

<!-- Espacio reservado para hallazgos futuros. Mantener orden cronológico
inverso (más reciente arriba). -->
