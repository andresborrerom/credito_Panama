# Correo al analista — primera carga (mensual + histórico)

Plantilla del correo de **arranque del proyecto**. Después de esta carga, los
cortes mensuales recurrentes usan una versión más corta (sección al final).

Reemplazar los campos `<...>` antes de enviar.

---

**Asunto:** Tasas Mercantil — Arranque del proyecto: carga mensual + backfill histórico Bloomberg

Hola <Nombre>,

Espero estés muy bien. Te escribo para pedirte un favor importante para arrancar el reporte mensual de tasas que estamos armando para los directivos del Grupo Mercantil. Adjunto **tres archivos** que necesito que corras en Bloomberg:

1. **`BloombergTemplate_TasasMercantil.xlsx`** — la plantilla del corte mensual (carga del cierre de mes vigente).
2. **`BloombergHistorico_TasasMercantil_FULL.xlsx`** — backfill histórico completo desde **1985-01-01 hasta 2026-05-29**. Es una sola pasada, no es recurrente.
3. **`BloombergHistorico_TasasMercantil_ALT_20Y.xlsx`** — **plan B** del histórico, con rango más corto (20 años, 2006-01-01 → 2026-05-29).

## Paso 1 · Plantilla mensual (la del corte vigente)

Esta es la que vamos a correr cada mes a partir de ahora. Va siempre primero porque es rápida y desbloquea el reporte del mes.

1. **Abrir** el archivo en Excel con Bloomberg add-in activo.
2. En la hoja `01_Parametros`, en la celda **B3 (AS_OF)**, escribir la fecha **<viernes 29 de mayo de 2026>** (último día hábil del mes).
3. Llenar también tu nombre (B8) y la fecha en que lo corres (B9).
4. **Esperar a que Bloomberg resuelva las fórmulas** (30–90 segundos la primera vez).
5. Ir a la hoja `04_FedWatch` y pegar manualmente la tabla de probabilidades de la pantalla **WIRP** para las próximas 6 reuniones FOMC (esto es lo único que no resuelve solo).
6. **Crítico — Paste Special → Values**: una vez resueltas todas las fórmulas, en cada hoja de datos (`02_Datos`, `03_SOFR_Futures`, `04_FedWatch`) hacer `Ctrl+A → Ctrl+C → Edit → Paste Special → Values`. Esto reemplaza las fórmulas por sus valores literales y congela el snapshot. Sin este paso, cuando alguien abra el archivo sin Bloomberg verá `#N/A` en todas las celdas.
7. Escribir en B10 (`FECHA_GUARDADO_VALUES`) la fecha del paso 6.
8. Guardar como `BloombergTemplate_TasasMercantil_2026-05.xlsx`.

## Paso 2 · Histórico — empezar con `FULL`

Una vez termines el corte mensual, abrí el archivo `BloombergHistorico_TasasMercantil_FULL.xlsx`:

1. **No hace falta editar fechas** — el rango ya está fijado (1985-01-01 a 2026-05-29).
2. En `01_Parametros` solo llenar tu nombre (B5) y la fecha de carga (B6).
3. **Esperar la carga.** Esto sí puede tardar 10–20 minutos porque son ~56 series × 40 años de datos diarios. Sugerencia: cerrar el resto de aplicaciones pesadas, dejar correr y volver.
4. **Si el archivo se traba** (Excel no responde, Bloomberg se cuelga, o pasa una hora sin terminar): **cerrar Excel sin guardar** y pasar al **plan B** (paso 3).
5. Si termina bien: hacer `Paste Special → Values` en cada hoja de datos, escribir `FECHA_GUARDADO_VALUES` (B7), y guardar como `BloombergHistorico_TasasMercantil_FULL_2026-05-29.xlsx`.

## Paso 3 · Plan B — `ALT_20Y` (solo si el FULL se traba)

Mismo proceso que el FULL, pero con rango 2006-2026 (más liviano, ~5 min de carga). Si llegaste aquí porque el FULL no terminó, déjame nota en la hoja `05_Notas_Analista` indicando aproximadamente dónde se trabó (qué hoja, cuánto tiempo pasó) — me ayuda a saber si vale la pena dividir el FULL en bloques más chicos para una próxima.

## Validación adicional — solo en esta primera carga

Hay algunos tickers en la columna `nota` de la plantilla mensual marcados con la frase *"— confirmar ticker"*. Son tickers que inferí pero no pude validar contra una terminal Bloomberg. Si alguno te devuelve `#N/A Invalid Security`, ¿podrías:

- Buscar el ticker correcto vía `SECF <GO>` o el subscreen apropiado, y
- Apuntármelo en la hoja `05_Notas_Analista` (sección "Tickers fallidos / corregidos") con el ticker correcto?

Los tickers que más me importa validar son:

- `USGGT05Y/10Y/20Y/30Y Index` (curva real de TIPS constant maturity)
- `USOSFR2/5/10/30 BGN Curncy` (curva swap SOFR OIS) y `USSW2/5/10/30 Curncy` (swap clásico LIBOR-based)
- `JPEIDIVR Index`, `JPEMLAT Index`, `JPGCPANS Index`, `JPGCVENS Index` (subíndices EMBI)
- `JPCBBRDF Index`, `JPCBLATS Index` (CEMBI)
- `FDFD Index` (Fed Funds lower bound), `FEDFUND Index` (Fed Funds target único pre-2008)
- `GMXN10YR Index`, `COGR10Y Index`, `GEBR10Y Index` (curvas 10Y México, Colombia, Brasil)
- `CHRR7TR Index` (PBoC 7-day reverse repo)

Si encuentras tickers más estándar o convenciones distintas en tu instalación, **tu criterio manda** — anótalo y los actualizamos en la plantilla.

## Para devolver los archivos

Tres opciones (cualquiera me sirve):

1. Subir directo a GitHub al repo `andresborrerom/credito_Panama`:
   - El **mensual** va a `ProyectoTasasMercantil/cortes/2026-05/input/`.
   - Los **históricos** van a `ProyectoTasasMercantil/plantilla_bloomberg/historico/`.
   - Instrucciones detalladas en la hoja `99_Envio` de cada archivo.
2. Enviarme los `.xlsx` por correo a esta misma dirección.
3. Dejarlos en la carpeta OneDrive compartida <link a definir>.

Si te trabas en cualquier paso, escríbeme y lo resolvemos. Para próximos cortes el proceso será mucho más rápido — solo la plantilla mensual, cambiando la fecha del paso 2 cada mes. El histórico es una sola vez.

Mil gracias por el apoyo, este arranque es la parte más pesada y después se vuelve rutina.

Un abrazo,
Andrés

---

## Correo recurrente mensual (a partir del corte 2026-06)

Versión corta para cortes posteriores. Solo la plantilla mensual.

> **Asunto:** Tasas Mercantil — Carga mensual Bloomberg, corte <MES YYYY>
>
> Hola <Nombre>,
>
> Adjunto la plantilla del corte de <MES YYYY>. Mismo procedimiento de siempre:
> AS_OF = <fecha último día hábil>, FedWatch pegado desde WIRP, Paste Special → Values
> antes de guardar como `BloombergTemplate_TasasMercantil_<YYYY-MM>.xlsx`, y subir
> a `ProyectoTasasMercantil/cortes/<YYYY-MM>/input/`.
>
> Si algún ticker da `#N/A`, lo anotas en `05_Notas_Analista`. Cualquier tema, me escribes.
>
> Gracias!
> Andrés

---

## Notas operativas (no van al correo)

- A partir del **segundo corte** se elimina el bloque "Validación adicional" del correo recurrente.
- Si el corte es de **backfill histórico** de informes (no del histórico de datos del modelo), agregar línea: *"Este es un corte retroactivo: la fecha AS_OF es <YYYY-MM-DD> aunque hoy estemos a <YYYY-MM-DD>. Bloomberg devolverá los datos históricos correctos a esa fecha."*
- Si hay **cambios en la plantilla** (nuevos instrumentos, tickers corregidos), adjuntar la versión nueva y mencionarlo brevemente.
