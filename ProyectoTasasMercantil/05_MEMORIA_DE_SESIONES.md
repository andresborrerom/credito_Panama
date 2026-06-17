# 05 · Memoria entre sesiones

Cada corte mensual abre una sesión de chat nueva. La sesión no recuerda nada por
sí sola — la memoria vive en **el repo**. Este documento define cómo escribimos
esa memoria y cómo Claude la lee al abrir la siguiente.

## Principio

> Todo lo que Claude necesita saber para continuar el trabajo del próximo mes está
> escrito en `cortes/<MES_ANTERIOR>/cierre.md` y, si hace falta más historia, en los
> dos cierres anteriores. No hay "memoria" oculta.

Cualquier conclusión, intuición, hipótesis, hallazgo o pendiente que importe para
el próximo mes va en `cierre.md`. Si no está ahí, **no se recordará**.

## Plantilla obligatoria de `cierre.md`

Cada corte termina con un `cortes/YYYY-MM/cierre.md` con esta estructura. Es el
documento más importante del proyecto.

```markdown
# Cierre · Corte YYYY-MM

> Firmado por: <nombre>  ·  Fecha de firma: <YYYY-MM-DD>

## 1. Mensaje del mes en una frase
<una frase, no dos. Lo que cualquier directivo se debe llevar del mes>

## 2. Tres movimientos relevantes
- <movimiento, magnitud, contexto>
- <...>
- <...>

## 3. Cambio de expectativas
- Implied path SOFR: <antes -> ahora, en qué horizonte>
- CME FedWatch (próxima reunión): <antes -> ahora>
- Modelo Mercantil: <antes -> ahora, qué le movió la opinión>

## 4. Comparación de las 3 lecturas de la Fed (mercado vs Mercantil)
- Acuerdos / desacuerdos del mes
- Si el modelo Mercantil divergió, ¿por qué?

## 5. Por fase: estado y hipótesis viva
### Fase 1 — USA
- estado: <breve>
- hipótesis viva: <una o dos frases>

### Fase 2 — Global
### Fase 3 — Panamá
### Fase 4 — Mercantil (impactos)
### Fase 5 — Venezuela
### Corporativas — spreads

## 6. Qué hay que observar el próximo mes
- <item específico y accionable>
- <calendario: próxima reunión Fed, dato de CPI, próximo SEP, etc.>
- <test/refuta: si X sucede, mi hipótesis Y queda confirmada/descartada>

## 7. Datos/herramienta — lo que aprendimos
- <falla o ajuste de pipeline>
- <campos nuevos que vale la pena agregar>
- <cosas que el analista preguntó / corrigió>

## 8. Decisiones pendientes para Andrés / Camilo / JLG
- <decisión, opciones, recomendación>

## 9. Estado del backlog
- ✅ <hecho este mes>
- ⏳ <pendiente que sigue vivo>
- 🆕 <pendiente nuevo identificado este mes>
```

Este formato es **obligatorio**. Cuando Claude cierre un corte sin generar este
archivo, está incumpliendo el contrato del proyecto.

## Cómo arrancar la sesión del mes siguiente

Patrón de prompt estándar (ver también `04_PLAYBOOK_MENSUAL.md`):

```
Lee ProyectoTasasMercantil/README.md y los siguientes cierres:
- cortes/<MES_ANTERIOR>/cierre.md
- cortes/<MES_ANTERIOR-1>/cierre.md   (opcional pero recomendado)

Recuérdame en 5 bullets:
1. La hipótesis viva del último mes en Fase 1 USA
2. Lo que estábamos esperando observar
3. Discrepancias del modelo Mercantil vs mercado
4. Pendientes de pipeline
5. Decisiones que quedaron al aire

Después arrancamos el corte <YYYY-MM>.
```

Claude empieza por leer, resumir, y solo entonces pasa a trabajar el nuevo corte.

## Reglas de escritura del cierre

1. **Específico y trazable.** En vez de "expectativas se ablandaron", escribir
   "implied path SOFR a Dic-2026 cayó de 3.85% a 3.62% (−23 bps)".
2. **Hipótesis falsables.** En vez de "el mercado podría reaccionar a CPI",
   escribir "si CPI core junio sale > 0.3% m/m, la prob. de cut en septiembre debería
   bajar al menos 10 pp; si no, vamos a revisar el modelo Mercantil".
3. **Honestidad sobre errores.** Si el modelo Mercantil falló o si una métrica que
   propusimos no movió la conversación, decirlo. El cierre es el lugar para
   admitirlo, no para barrerlo.
4. **Cortes pasados son inmutables.** Si descubrimos que cierre.md de marzo tenía
   un error, escribimos `erratum_YYYY-MM-DD.md` en el mismo folder; no
   reescribimos cierre.md.

## Memoria larga (>3 meses)

Cada **trimestre** producimos un `cortes/_resumenes/QX_YYYY.md` con:
- Las hipótesis vivas más relevantes del trimestre.
- Aciertos y errores del modelo Mercantil.
- Cambios de tendencia.
- Qué métricas vale la pena seguir, cuáles descartar.

Esto evita que Claude tenga que cargar 12 cierres mensuales para tener visión
de año.

## Bonus: contexto del proyecto que no cambia

Lo que **nunca cambia entre sesiones** (decisiones de fondo, modelo de datos,
permisos) vive en los `.md` 00–09. Claude no necesita memoria propia para esto —
los lee del repo cada vez. Solo lo dinámico (hipótesis, movimientos, pendientes)
va en `cierre.md`.
