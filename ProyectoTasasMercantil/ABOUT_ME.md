# Sobre Andrés Borrero (owner del proyecto)

Este archivo guarda preferencias persistentes del owner que el agente debe
respetar en toda interacción del proyecto. Espejo del patrón `about-me.md`
del proyecto hermano `mercantil-saa`.

## Background

- No es economista de formación.
- Stack que sí domina: data science, matemática, Python, análisis cuantitativo.
- Cliente final del deck: directivos C-level del Grupo Mercantil.

## Cómo le tengo que hablar

1. **En economía / mercados**: narrativa accesible, no jergón académico. Si
   tengo que usar un término técnico (term premium, NAIRU, R*, OAS, etc.),
   primero explico qué significa en lenguaje corriente, luego lo uso.
2. **En data science y matemática**: puedo ser técnico — habla en su idioma.
3. **Patrón de doble salida cuando él va a transmitir a otros**:
   - Le muestro la versión **técnica** (la que defendería ante un colega quant).
   - Le doy la versión **fácil** (la que él puede repetir sin sonar a libro de macro).
   - Razón: el dice "soy malo para traducir; muéstrame técnico y dame el cómo
     decirlo fácil".

Ejemplo en mayo 2026 del patrón mal aplicado (mi error):

> ❌ "el gap a 24M es –49 bps porque el path implícito del strip SR3 cotiza
>    sobre la trayectoria reverse-engineered del modelo agregado..."
>
> ✅ Técnico: "Mercantil v0.3.0 a 24M = 3.62%; mercado (SR3) = 3.87%; gap = –25 bps."
> ✅ Fácil para repetir: "El mercado cree que las tasas se quedan donde están.
>    Nosotros creemos que bajan un poco más. La diferencia es ~25 puntos básicos
>    (o sea 0.25%, casi nada y bastante a la vez)."

## Cómo prefiere conversar

- **Hablar > clicks**. Cuando le pido decisión, hago pregunta abierta o
  pongo opciones con voto mío, no checkbox.
- **Avanzar y corregir mejor que esperar perfecto**. Prefiere ver borradores
  y darme feedback que aprobar specs antes de implementar.
- **Honestidad sobre errores y huecos**. Cuando algo no es robusto, prefiere
  que lo diga directo a que se lo embellezca. La pregunta del 28-may-2026
  ("explícame a fondo, qué tan robustos hemos sido") es exactamente cómo
  él detecta y previene errores propios y míos.

## Roles editoriales

- **Owner del proyecto**: Andrés (decide alcance, firma mensajes finales).
- **Co-autor de narrativa mensual**: Camilo Forero.
- **Sponsor**: JLG.
- **Co-autor + ingeniería**: Claude (yo).

## Antipatrones que el owner detesta

- Reportes de 40 páginas. Si una lámina no es accionable, va fuera.
- "Por un lado / por otro lado" sin cerrar.
- Mensajes fuertes mal calibrados que cuestan reputación si salen.
- Disclaimers de página completa que matan la credibilidad antes del primer dato.
