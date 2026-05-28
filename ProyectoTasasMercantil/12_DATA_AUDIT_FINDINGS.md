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

## 2026-05-28 — BDH con `Dts=H` oculta la columna de fechas (segunda lección heredada de SAA)

**Síntoma**: Antulio, operador Bloomberg de Mercantil, al abrir
`BloombergHistorico_TasasMercantil_FULL.xlsx` (primera versión) preguntó:
*"las fechas están ocultas a propósito o cambio la fórmula para que las
traiga?"*.

**Causa**: la fórmula original era:
```
=BDH(ticker, "PX_LAST", FROM, TO, "Dir=V", "Dts=H", "Fill=B", "cols=2;rows=12000")
```
El parámetro `Dts=H` significa **Dates Hidden** — Bloomberg oculta la
primera columna del array (fechas) y solo desborda los valores. Sin la
columna de fechas, el parser (y el analista) no puede saber a qué `obs_date`
corresponde cada `value`. Convención heredada de SAA (`v1_extraction_spec.md`)
sin reflexión sobre si servía para nuestro caso.

**Impacto en el modelo / reporte**: alto. Si el archivo se hubiera devuelto
con `Dts=H` y valores ya cuajados (post Paste-Special-Values), perderíamos
el alineamiento temporal de la serie y todo el backfill sería inutilizable.

**Mitigación adoptada**: cambio inmediato a `Dts=S` (Dates Shown) en
`build_bloomberg_historico_template.py`. Regeneración de ambos xlsx (FULL y
ALT_20Y). Comentario inline en el script que explica por qué no usar `Dts=H`.

**Decisión metodológica**: agregar al checklist de generación de plantillas
Bloomberg la regla: *si la fórmula es `=BDH` con rango (serie temporal), `Dts`
debe ser `S` o estar ausente (default = Shown)*. Sólo `=BDP` o `=BDH` con
`start=end` y wrap `INDEX(...,1,2)` pueden suprimir la columna de fechas
porque el output es un escalar.

**Receta para arreglar archivos en curso sin rehacer la carga**:
1. Find & Replace en Excel: `Dts=H` → `Dts=S`.
2. Las fórmulas se reevalúan automáticamente, traen ahora las fechas.
3. **Antes** de hacer Paste Special → Values.
Esto salva el trabajo de Bloomberg ya hecho si el analista ya empezó.

---

## 2026-05-28 — FRED y ALFRED accesibles vía CSV público sin API key

**Síntoma**: la documentación inicial del proyecto asumía que `FRED_API_KEY`
era requisito para bajar datos macro de FRED y ALFRED. Eso bloqueaba el
arranque del backfill hasta que un humano registrara una key.

**Causa**: confusión entre la API REST de FRED (`api.stlouisfed.org/fred/*`,
que SÍ requiere key) y los endpoints públicos CSV
(`fred.stlouisfed.org/graph/fredgraph.csv` y
`alfred.stlouisfed.org/graph/alfredgraph.csv`), que NO requieren auth.

**Impacto en el modelo / reporte**: positivo. Toda la ingesta macro y de
tasas FRED se puede automatizar sin intervención humana. Vintage data
(ALFRED) también es accesible vía CSV con parámetro `vintage_date`.

**Mitigación adoptada**: `src/tasas_mercantil/data/ingest_fred.py` implementado
con HTTP GET a los endpoints CSV. Throttle conservador de 1 req/seg para
respetar Terms of Use. `User-Agent` identificado. Probado contra DGS10
(267 KB CSV, ~16,400 filas desde 1962) y CPILFESL con `vintage_date=2010-06-15`
— ambos HTTP 200.

**Decisión metodológica**: documentar en `11_MODELO_ROBUSTEZ.md` que la
ingesta FRED es "self-service sin credenciales". Anotar caveat: si en algún
momento necesitamos metadatos estructurados o búsqueda de series, ahí sí
requeriremos API key — pero no para bajar valores.

URLs verificadas:
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10
- https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPILFESL&vintage_date=2010-06-15

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
