# 15 · Lecciones de interacción con Claude en este proyecto

> Curso vivo. Cada vez que la conversación previene un error costoso o
> revela un patrón útil, se anota acá. Inspirado en
> `mercantil-saa/learnings/curso-saa-con-claude.md` (que el agente puede
> leer pero no editar — este es nuestro espacio paralelo).

---

## Lección 01 · 2026-05-28 — Pregunta crítica antes del mensaje fuerte

### Lo que pasó

El agente armó el deck del corte 2026-05 y propuso el mensaje principal:

> "El mercado descuenta tasas estables a alcistas (3.85% en 24M). Nuestro
> modelo Mercantil dice tasas bajando (3.36%). Gap –49 bps. Confianza Media."

El usuario respondió:

> "Explícame a fondo la tesis. Cómo llegamos a ella. Quiero ver qué tan
> robustos hemos sido. Es un mensaje fuerte vs consensus lo que me gusta,
> pero los mensajes fuertes se estudian a fondo."

Al pedir el desarmado matemático, el agente detectó **su propio error**:

- El **3.36%** era la **Pieza B Taylor sola**, sin smoothing fino.
- El **agregado real** (lo que defendemos públicamente como modelo
  Mercantil v0.3.0) es **3.62%**.
- El gap real es **–25 bps**, no –49 bps. La mitad.

Si el deck hubiera salido con el número equivocado, el primer comité
técnico que validara los números (banco PA, casa de bolsa, riesgos del
grupo) habría encontrado la inconsistencia. Costo en reputación alto.

### Por qué pasó

El agente arrastró el número de la Pieza B (3.36%) al mensaje narrativo
porque era visualmente más impactante. **No validó que la cifra del
mensaje coincidiera con la cifra del modelo agregado publicado.**

Es un error de integración entre la narrativa y el modelo — el modelo
estaba bien, la narrativa lo citó mal.

### Cómo lo previno la interacción

La pregunta del owner es específica y exigente:
1. *"Explícame a fondo la tesis"* — fuerza al agente a desarmar la lógica.
2. *"Cómo llegamos a ella"* — pide la cadena de cálculo, no el resumen.
3. *"Qué tan robustos hemos sido"* — invita a la auditoría honesta, no a la defensa.

Esa estructura es replicable. Antes de firmar **cualquier mensaje
cuantitativo contrarian** del deck, el owner debe preguntar:

```
Explícame a fondo el número [X] del mensaje [Y].
¿Cómo se construye paso a paso?
¿Qué tan robusto es? ¿Dónde NO hemos testeado?
```

### Patrón a internalizar (para el agente)

Antes de proponer un mensaje cuantitativo:
1. **Identificar el modelo que firma la cifra**: agregado, Pieza A sola, Pieza B sola, otro.
2. **Verificar consistencia con el modelo publicado**: si el modelo Mercantil v0.3.0 dice 3.62%, el mensaje no puede decir 3.36% sin explicarlo.
3. **Auto-pregunta antes de mandar**: "¿defendería yo este número si JLG me lo cuestiona?". Si no, parar.
4. **Reportar de doble vía**: lo que dice cada componente del modelo + lo que dice el agregado, con etiquetas claras.

---

## Lección 02 · 2026-05-28 — Estilo editorial: traducción técnica → narrativa

### Lo que pasó

El usuario me dejó la instrucción permanente:

> "No soy economista. Me tienes que hablar menos técnico en términos
> económicos con buena narrativa para no aburrirme. En data science y math
> sí puedes ser técnico pero soy malo para traducir entonces me muestras
> técnico y me dices cómo decirlo fácil."

Ese sesgo del agente — usar jerga económica como term premium, NAIRU, R*,
sin traducción — había estado todo el proyecto.

### Patrón a internalizar

Cuando hablo de un concepto económico que entrará al deck o al chat:

**Bad**:

> "El term premium del UST 10Y se expandió +26 bps YTD, validando una
> tesis de reversion to mean."

**Good (doble salida)**:

> 🔧 **Técnico**: UST 10Y term premium = +83 bps (Kim-Wright), +26 bps YTD.
> 📣 **Para repetir**: "El bono de 10 años de USA paga 83 puntos básicos
> de prima por la incertidumbre de los próximos años. Esa prima creció
> 26 puntos en lo que va del año. Si vuelve a su promedio histórico,
> ganamos plata por tener el bono."

Y luego cuando el deck tiene la cifra, va en la versión técnica con
nota al pie en lenguaje accesible.

### Aplicación operativa

- Toda **lámina con tabla densa** lleva editorial 4Ws que es la versión
  fácil-de-repetir.
- Toda **respuesta de chat** con cifra económica lleva la doble salida
  cuando el owner va a transmitir a alguien externo.
- El **ABOUT_ME.md** del proyecto guarda esta regla para que cualquier
  sesión nueva la lea al arrancar.

---

## Lección 03 · pendiente — Patrón de validación post-modelo

(Reservado para cuando implementemos bootstrap + sensibilidad. Voy a
documentar acá el flujo "predicción → validación cuantitativa → narrativa"
que separa modelo Mercantil de Apollo Daily Spark genérico.)

---

## Cómo leer este curso

- **Una lección por error material o patrón útil**. No relleno.
- **Cada lección tiene 4 secciones fijas**:
  1. Lo que pasó (con cifras reales).
  2. Por qué pasó (causa raíz, sin culpa).
  3. Cómo lo previno la interacción (qué pregunta o instrucción del owner).
  4. Patrón a internalizar (para futuras sesiones del agente y del owner).
- **Las lecciones son inmutables una vez firmadas** (fecha + autor).
  Si después se invalidan, se agrega una lección nueva que las complementa.
