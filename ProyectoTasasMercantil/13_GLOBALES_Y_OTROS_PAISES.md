# 13 · Tasas globales, otros países y alcance del modelo propio

Decisión sobre qué países / central banks van con **lectura del mercado** (van
al deck pero no se modelan) vs cuáles van con **modelo propio Mercantil** (la
arquitectura completa del documento 07).

## Principio

> Lectura del mercado se hace para todos. Modelo propio solo donde aporta valor
> al negocio del grupo Y donde hay data suficiente para un backtest defendible.

## Niveles de cobertura

### Nivel A — Lectura del mercado (TODOS los países relevantes)

Aplica a todo lo que aparece en la plantilla Bloomberg. Cada mes el deck
reporta:
- Tasa de política y decisión del mes.
- Curva de bonos soberanos (10Y como ancla).
- FX vs USD y movimiento mes / 12M.
- Spread vs UST (para soberanos USD) o EMBI subíndice (para EM).

Esto incluye:
**G7 + relevantes G20:** US, EU, GB, JP, CN, BR, MX, CO, CL, PA, VE.
**Soberanos EM USD:** vía EMBI Panama, Venezuela, Colombia, México.

### Nivel B — Modelo propio Mercantil

Aplica solo a las central banks donde el grupo tiene **exposure material** Y
**data limpia** lo permite. Plan escalonado:

| Banco central | Versión target | Justificación | Riesgos / complejidad |
|---|---|---|---|
| **Fed (USA)** | `v1.0` (M-0 a M-10) | USD = moneda dominante de banco PA, aseguradora, WM, posición propia. Data óptima. | Ninguno técnico. |
| **BCV (Venezuela)** | `v2.0` o `v2.5` | Banco VE depende críticamente. Alta utilidad para directivos del banco VE y aseguradora con activos VES. | Data es la peor del set: publicación con lag, métodos opacos, FX paralelo "no oficial". Requiere diseño aparte, NO copy-paste del Fed. |
| **ECB** | `v3.0` (eventual) | EUR relevante para aseguradora y WM. Data buena (ECB SDW, BBG). Probabilidades implícitas vía €STR futures (jóvenes pero usables desde 2022). | Menos accionable para el grupo que BCV pero más fácil técnicamente. |

### Nivel C — Lectura del mercado únicamente (sin modelo propio)

| Banco central | Por qué no |
|---|---|
| BoE | Exposure marginal del grupo. |
| BoJ | Exposure marginal. |
| PBoC | Exposure marginal. Data adicional limitada en abierto. |
| BCB (Brasil), Banxico, BanRep, BCRP (Perú) | Exposure indirecto via EMBI y FX para clientes. Modelo propio para cada uno = overkill. |

### Caso especial — Panamá

Panamá **no tiene central bank** (es jurisdicción USD). Por lo tanto no hay tasa de política a pronosticar.

**Sin embargo**, hay un equivalente natural a un modelo Mercantil para Panamá: el **spread soberano Panamá vs UST**. Movimientos en ese spread:
- Afectan directamente al **libro de inversiones de banco PA** (que tiene mucho de bonos PAN).
- Afectan al **portafolio de reservas técnicas de aseguradora** si tiene PA USD.
- Son input para el **WM** cuando recomienda Panamá soberano vs UST a clientes.

**Propuesta para Panamá**: modelo de spread crediticio (no de política
monetaria), construido en el **capítulo 08 corporativas**, no en el capítulo
07 modelo Fed. Mismo rigor (walk-forward, rivales, fail-loud) pero distinto
universo de features (spreads históricos, ratings agencias, fundamentales
soberano Panamá, comparables Costa Rica/República Dominicana).

Esto se trabaja como `v2.x_PAN` paralelo al modelo Fed, una vez Fed esté firme.

---

## Orden de construcción

Plan de los próximos 18 meses (asumiendo cadencia mensual):

```
ahora                                      mes +12              +18
 │                                          │                    │
 │  Fed v0.1 → v1.0 (M-0 a M-10)           │  BCV v2.0 piloto   │
 │                                          │  Panamá spread     │
 │                                          │  ECB v3.0 evaluar  │
 ▼                                          ▼                    ▼
[lectura del mercado para todos los demás, recurrente cada corte]
```

**Hito de promoción a v2.x** = Fed v1.0 ya está firme (4–6 cortes mensuales
publicados sin sustos, fail-loud no se activó). Antes de eso no abrimos
trabajo de extensión a otras central banks: el riesgo de hacer mal varios
modelos a la vez es alto.

---

## Cómo se ve el deck con esta estrategia

| Lámina | Quién manda |
|---|---|
| 5 — Tres lecturas de expectativas Fed | implied + FedWatch + **modelo Mercantil USD** (cuando v1.0 publique) |
| 7 — Fase 2 Global | tabla de tasas política y curvas 10Y (lectura del mercado de 6–8 países) |
| 8 — Fase 3 Panamá | curva soberana + spread vs UST + (cuando exista) **modelo Mercantil spread PA** |
| 11 — Fase 5 Venezuela | tasas BCV + FX oficial vs paralelo + (cuando exista) **modelo Mercantil BCV** |

Mientras no haya modelo propio para Vzla o Panamá, esas láminas muestran solo
lectura del mercado. Y eso es perfectamente aceptable — el reporte no se
detiene esperando al modelo.

---

## Pendientes para conversar

1. **Banco VE primero o ECB primero** (cuando Fed v1.0 esté firme)?
   - Mi voto: BCV. Más útil para directivos del grupo aunque sea más difícil técnicamente.
   - Voto alternativo: ECB primero porque la data es limpia y nos permite probar la generalización de la arquitectura antes de meternos con datos sucios.
2. **Para BCV: ¿modelamos también la tasa paralela**, o solo la oficial?
   Recomendación: modelar la oficial (es lo que toma decisiones regulatorias) y reportar la paralela como referencia, no como predicción.
3. **Modelo de spread Panamá**: ¿vale la pena por sí solo, o lo integramos al estudio standalone de Panamá que ya existe en `credito_Panama`?
   Recomendación: integrarlo al estudio existente; el deck mensual usa la lectura agregada del estudio.
