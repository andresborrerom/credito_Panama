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

## 2026-05-28 — Mensaje narrativo citó cifra de Pieza B sola en lugar del agregado

**Síntoma**: el agente propuso para el TL;DR del corte 2026-05 el mensaje
"modelo Mercantil dice 3.36% en 24M vs mercado 3.85%, gap –49 bps". Al
verificar contra el código, el agregado v0.3.0 a 24M es **3.62%**, no 3.36%.
El 3.36% corresponde a la Pieza B (Taylor) sola. Gap real: **–25 bps**.

**Causa**: error de integración entre la narrativa y el modelo. El agente
arrastró el número visualmente más impactante (Pieza B) sin verificar
que coincidiera con el modelo agregado que se publica como Mercantil v0.3.0.
La cadena de cálculo en el código estaba correcta; la cita narrativa estaba mal.

**Impacto potencial**: si el deck hubiera salido con "–49 bps" como mensaje
ALTA convicción, el primer comité técnico que cruzara los números (banco
Panamá, riesgos del grupo) habría detectado la inconsistencia. Costo de
reputación significativo para un mensaje contrarian.

**Mitigación adoptada**: la pregunta crítica del owner ("explícame a fondo
la tesis, qué tan robustos hemos sido") forzó al agente a desarmar el
cálculo y detectar el error antes de que saliera. Sin esa pregunta, el
error habría llegado al PDF firmado.

**Decisión metodológica**:
1. **Patrón obligatorio del agente**: antes de proponer un mensaje
   cuantitativo contrarian al consenso, validar que la cifra del mensaje
   coincida con la cifra del modelo agregado publicado. Si no, parar.
2. **Patrón obligatorio del owner**: antes de firmar cualquier mensaje
   contrarian del TL;DR, preguntar "explícame a fondo cómo se construye
   este número y qué tan robusto es". Documentado en
   `15_LECCIONES_INTERACCION_CON_CLAUDE.md` lección 01.
3. **Doc actualizado**: `narrativa.yaml` del corte 2026-05 corregido para
   reflejar gap –25 bps y convicción Baja-Media (en lugar de Media) hasta
   que se complete bootstrap + sensibilidad R\*.

---

## 2026-05-29 — Audit no look-ahead + re-backfill vintage mensual

**Síntoma**: el usuario pidió auditoría explícita de que el backtest no
usaba info futura. El audit reveló que el backfill vintage inicial era
trimestral (`freq=QE`), que dejaba huecos en fechas justo post-release.

**Comportamiento observado**:
- El store **filtra correctamente** por `vintage_date <= as_of + T3` (T3
  = ventana de presentación del reporte).
- Pero con vintage trimestral, en `as_of=2022-07-31` no había PCE jun-22
  disponible (la primera vintage capturada para esa observación era
  2022-09-30, posterior a as_of+T3). El modelo entonces caía a el último
  PCE conocido, que era mayo 2022.

**Causa**: backfill `freq=QE` por velocidad (~13 min en lugar de ~40 min).
Decisión correcta para arrancar; **incorrecta para auditoría rigurosa**.

**Mitigación adoptada**:
- Re-backfill mensual `freq=ME` desde 2018-01-01 hasta 2026-05-29.
- Resultado: 23,650 filas con vintages mensuales. En cada `as_of` el
  modelo ve el dato del día del release.
- Re-bootstrap del modelo: skill scores marginalmente mejores
  (+0.5 a +1.7 pp). P(pasa fail-loud) en horizonte 3M sube de 91% a 98%.

**Verificación empírica**:
Caso PCE core jun-22 visto desde distintas as_of:

| as_of | Vintage efectivo | Valor |
|---|---|---:|
| 2022-07-31 | 2022-07-31 (primer release) | **122.948** |
| 2022-09-30 | 2022-09-30 (1ra revisión) | 123.258 |
| 2024-01-31 (post BEA re-anchor) | 2024-01-31 | **114.297** |
| Hoy 2026-05-28 | 2026-04-30 | 114.376 |

El número que ve el modelo cambia con la fecha del corte. Confirma que
el store respeta el vintage point-in-time.

**Decisión metodológica**: backfill vintage `freq=ME` queda como estándar
para el período SOFR (2018+). Para épocas anteriores (pre-2018) podemos
seguir con `QE` porque el régimen monetario era distinto y la
sensibilidad del modelo Pieza B al primer release vs revisiones es
menor (la inflación pre-COVID se revisaba con menos magnitud).

---

## 2026-05-29 — Audit primera carga histórica Bloomberg (Antulio)

**Síntoma**: recibido `BloombergHistorico_TasasMercantil_FULL_2026-05-29.xlsx`
(4.4 MB, 11 hojas, 56 instrumentos). Audit con pandas detectó 3 tickers
problemáticos + 1 issue de parser. El resto (53 instrumentos) cargó limpio.

**Carga global**:
- ✅ Paste Special → Values aplicado (sin fórmulas vivas).
- ✅ `Dts=S` funcionó (fechas visibles).
- ✅ 0 `#N/A` en valores de los 53 instrumentos OK.
- ✅ UST 3M/2Y/5Y/10Y/30Y desde 1985-01-02 con 99% cobertura — backbone completo.
- ✅ TIPS, Breakevens, SR3 futures, EuroDollar futures completos.
- ✅ Antulio dejó notas detalladas con las sustituciones que hizo.

**Issues a regresar a Antulio (3)**:

1. **`IORB`** — Antulio sustituyó mi `FRRRIORB Index` (propuesta inicial) por
   `IORB Index`. Pero los valores devueltos son 104.5 / 104.83 / 105.17 — eso
   parece índice/precio, no la tasa real (que debería ser ~5% hoy, ~0.25% en
   2013). Hipótesis: `IORB Index` en BBG no es una tasa. Acción: pedir a
   Antulio que valide en `DES <GO>` cuál ticker da la tasa IORB (probable
   `FRRRIORB Index` original o `IOER Index`).

2. **`ON_RRP`** — Antulio probó `RRPONRAT Index` y devolvió
   `#N/A Invalid Security`. Acción: pedirle el ticker correcto del Overnight
   Reverse Repurchase Award Rate.

3. **`TERM_SOFR_6M`** — Antulio sustituyó `USOSFR6Z BGN Curncy` por
   `TSFR12M Index` — pero ese es 12 meses, no 6. La hoja `TERM_SOFR_6M`
   contiene en realidad la serie de 12M (1169 obs desde 2021-09-21).
   Posible confusión. Acción: confirmar si existe `TSFR6M Index`; alternativa
   es derivarlo del strip SR3 o reportar solo 1M/3M/12M.

**Mitigación inmediata sin esperar a Antulio**: IORB y ON RRP se pueden bajar
de FRED (series `IORB` y `RRPONTSYD`) — endpoint CSV público, sin key.
Term SOFR 6M se deriva del SR3 o se omite. Bloqueo cero para el avance del
modelo y del deck.

**Issue de parser (no del dato)**:

- **`FED_FUNDS_TARGET_PRE2008`**: el dato vino correcto (8.25% en 1985, etc.)
  pero las fechas vinieron como números enteros sin formato date (31048,
  31049, ...). Estos son serial dates de Excel. Mi audit con pandas las
  rechazó. Fix en parser: detectar enteros en columnas de fecha y convertir
  con `pd.to_datetime(serial, origin='1899-12-30', unit='D')`.

**Limitaciones esperadas (no son bugs)**:
- `UST_1M` desde 2001-07: el instrumento se introdujo ese año.
- `UST_20Y` desde 2020-05: Treasury suspendió 1986-2020.
- `UST_7Y` cobertura 61%: descontinuado 1993-2009.
- `USSW2/5/10/30_LIBOR` solo 2009-2023: limitación de ticker continuous + cessation LIBOR.
- `SOFR_OIS` desde 2007: Bloomberg back-fillea sintéticamente pre-2018 desde Fed Funds OIS. Útil pero etiquetar.

**Decisión metodológica**: documentar en `11_MODELO_ROBUSTEZ.md` § 3 (Universo
de datos) la procedencia híbrida Bloomberg + FRED para tasas Fed
(FF/EFFR/IORB/ONRRP) y la convención de back-fill sintético en SOFR OIS
pre-2018. Cuando Antulio reporte tickers corregidos, regenerar plantillas y
actualizar `instrumentos.yaml`.

**Resumen CSV**: `/tmp/audit_bloomberg_historico.csv` con una fila por
instrumento × {inicio, fin, n_obs, n_nan_val, cobertura_pct}.

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
