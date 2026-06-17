# Sugerencia de input cuantitativo para el modelo de retornos esperados

> Corte 2026-05 · Modelo Mercantil v0.3.0 · Generado: 2026-06-02

## TL;DR

El modelo Mercantil v0.3.0 **valida cuantitativamente** la intuición editorial actual del Excel `Ret esperados`. La línea 13 ("Variación tasas 2H 2026 vs WIRP") cotiza −10 bps por opinión de la mesa; el modelo calcula **-9.6 bps**. **Diferencia: ~0.4 bps (ruido de redondeo)**. Por primera vez, la perilla editorial tiene defensa cuantitativa que no contradice la intuición.

## Cómo se calcula el delta

Path Fed Funds esperado por el modelo Mercantil v0.3.0 (junio → diciembre 2026):

| Mes (post may-26) | Fed Funds esperado |
|---|---:|
| jun (+1M) | 3.663% |
| jul (+2M) | 3.670% |
| ago (+3M) | 3.677% |
| sep (+4M) | 3.687% |
| oct (+5M) | 3.697% |
| nov (+6M) | 3.707% |
| dic (+7M) | 3.727% |
| **Promedio 2H 2026** | **3.689%** |

Comparación:
- Promedio Mercantil 2H 2026: **3.689%**
- Promedio WIRP 2H 2026: **3.785%** (+10 bps sobre hoy según Excel original)
- **Delta Mercantil vs WIRP: -9.6 bps**

## Cómo se construye el modelo Mercantil v0.3.0

- 55% × Pieza A (implied path SR3, lo que cotiza el mercado de futuros)
- 45% × Pieza B (Taylor rule con R\* dinámico de Cleveland Fed)
- Pesos calibrados en backtest 2022-2025, pasan fail-loud en todos los horizontes
- Bootstrap del backtest da P(skill positivo) ≥ 99% en todos los horizontes

## Validación del backtest

| Horizonte | Skill mediano vs naive | IC 80% |
|---|---:|---|
| 1M | +18.1% | [+7.3%, +33.4%] |
| 3M | +12.3% | [+6.9%, +22.5%] |
| 6M | +24.5% | [+21.5%, +28.7%] |
| 12M | +46.0% | [+40.4%, +52.4%] |

## Qué hacer con esto

**Opción A — Aceptar el delta cuantitativo (sugerido)**:
- Cambiar línea 13 col C en el Excel a `-0.00096`.
- Mantener todo lo demás del Excel intacto.
- El cambio en los retornos esperados es marginal (~0.4 bps de diferencia con el -10 bps actual).

**Opción B — Mantener el input editorial actual**:
- Argumento válido: la diferencia es ruido y la mesa ya tiene la intuición correcta.
- Documentar que el modelo coincide.

**Recomendación**: Opción A para construir disciplina futura. Los meses donde modelo e intuición discrepen serán los más informativos.

## Archivo derivado

`Ret_esperados_con_mercantil_v0.3.0.xlsx` (en este mismo directorio): copia del original con la línea 13 ajustada según el modelo. **Para revisión, no para sustituir el original**.
