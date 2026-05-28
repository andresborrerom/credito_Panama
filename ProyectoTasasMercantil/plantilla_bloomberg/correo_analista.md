# Correo al analista — carga mensual Bloomberg

Plantilla del correo que se envía al analista cada mes pidiendo la carga.
Reemplazar los campos `<...>` antes de enviar.

---

**Asunto:** Tasas Mercantil — Carga mensual Bloomberg, corte <MES YYYY>

Hola <Nombre>,

Espero estés muy bien. Te escribo para pedirte un favor importante para el reporte mensual de tasas que estamos armando para los directivos del Grupo Mercantil. Necesitamos correr la carga de datos de Bloomberg para el cierre del mes.

**El archivo que adjunto** (`BloombergTemplate_TasasMercantil.xlsx`) es una plantilla auto-contenida: tú solo editas una celda (la fecha de cierre) y todas las fórmulas `=BDH(...)` se actualizan solas. Cuando lo abras vas a ver una hoja `00_Instrucciones` con el paso a paso completo, pero te resumo lo principal:

1. **Abrir el archivo** en Excel con Bloomberg add-in activo.
2. En la hoja `01_Parametros`, en la celda **B3 (AS_OF)**, escribir la fecha **<viernes DD de <mes> de YYYY>** (último día hábil del mes).
3. Llenar también tu nombre (B8) y la fecha en que lo corres (B9).
4. **Esperar a que Bloomberg resuelva las fórmulas** (30–90 segundos la primera vez).
5. Ir a la hoja `04_FedWatch` y pegar manualmente la tabla de probabilidades de la pantalla **WIRP** para las próximas 6 reuniones FOMC (esto es lo único que no resuelve solo).
6. **Crítico — Paste Special → Values**: una vez resueltas todas las fórmulas, en cada hoja de datos (`02_Datos`, `03_SOFR_Futures`, `04_FedWatch`) hacer `Ctrl+A → Ctrl+C → Edit → Paste Special → Values`. Esto reemplaza las fórmulas por sus valores literales y congela el snapshot del cierre. Sin este paso, cuando alguien abra el archivo sin Bloomberg verá `#N/A` en todas las celdas y se pierde la foto del mes.
7. Escribir en B10 (`FECHA_GUARDADO_VALUES`) la fecha del paso 6.
8. Guardar como `BloombergTemplate_TasasMercantil_<YYYY-MM>.xlsx`.

**Validación adicional que necesito de tu parte (favor especial — solo en la primera carga):**

Hay algunos tickers en la columna `nota` de la hoja `02_Datos` marcados con la frase *"— confirmar ticker"*. Son tickers que inferí pero no pude validar contra una terminal Bloomberg. Si alguno de ellos te devuelve `#N/A Invalid Security`, ¿podrías:

- Buscar el ticker correcto vía `SECF <GO>` o el subscreen apropiado, y
- Apuntármelo en la hoja `05_Notas_Analista` (sección "Tickers fallidos / corregidos") con el ticker correcto?

Los tickers críticos que más me importa validar son:

- `USGGT05Y/10Y/20Y/30Y Index` (curva real de TIPS constant maturity)
- `USOSFR2/5/10/30 BGN Curncy` (curva swap SOFR OIS)
- `JPEIDIVR Index`, `JPEMLAT Index`, `JPGCPANS Index`, `JPGCVENS Index` (subíndices EMBI)
- `JPCBBRDF Index`, `JPCBLATS Index` (CEMBI)
- `FDFD Index` (Fed Funds lower bound)
- `GMXN10YR Index`, `COGR10Y Index`, `GEBR10Y Index` (curvas 10Y México, Colombia, Brasil)
- `CHRR7TR Index` (PBoC 7-day reverse repo)

Si encuentras tickers más estándar o convenciones distintas en tu instalación, **tu criterio manda** — anótalo y los actualizamos en la plantilla.

**Para devolverme el archivo** tienes tres opciones (cualquiera me sirve):

1. Subirlo directo a GitHub al repo `andresborrerom/credito_Panama` en la carpeta `ProyectoTasasMercantil/cortes/<YYYY-MM>/input/` (instrucciones detalladas en la hoja `99_Envio` del archivo).
2. Enviarme el `.xlsx` por correo a esta misma dirección.
3. Dejarlo en la carpeta OneDrive compartida <link a definir>.

Si te trabas en cualquier paso, escríbeme y lo resolvemos. Para próximos cortes el proceso será idéntico (solo cambia la fecha del paso 2), así que vale la pena dejarlo bien aceitado en esta primera vuelta.

Mil gracias por el apoyo.

Un abrazo,
Andrés

---

## Notas operativas (no van al correo)

- A partir del **segundo corte** se puede simplificar el correo eliminando el bloque "Validación adicional" (los tickers ya estarán confirmados).
- Si el corte es de **backfill histórico**, agregar línea: *"Este es un corte retroactivo: la fecha AS_OF es <YYYY-MM-DD> aunque hoy estemos a <YYYY-MM-DD>. Bloomberg devolverá los datos históricos correctos a esa fecha."*
- Si hay **cambios en la plantilla** (nuevos instrumentos, tickers corregidos), adjuntar la versión nueva y mencionarlo: *"Adjunto la versión <vX.Y> de la plantilla; incluye <breve resumen del cambio>."*
