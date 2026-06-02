# Producto B · Escenarios del Portafolio LUZ · corte mayo 2026

> Generado 2026-06-02 con modelo Nearest Neighbors histórico · datos hasta 2026-05-28.

## TL;DR

- **Retorno esperado del portafolio LUZ a 12 meses**: **+6.11%** (rango Esperado [+4.49%, +7.78%], prob 50%).
- **Riesgo (peor cola 10%)**: retorno entre -7.82% y +2.61%. Media +0.15%.
- **Allocation LUZ**: BIL 5%, IGLA 45%, GHYG 20%, LQD 10%, EMB 10%, ACWI 10%.

## Macro state actual

| Variable | Valor |
|---|---:|
| PCE core YoY (vintage) | 2.77% |
| Unemployment U-3 | 4.30% |
| Breakeven 5Y | 2.56% |
| Fed Funds upper | 3.75% |
| Slope 2s10s | +43 bps |

## Escenarios del portafolio LUZ — los 4 horizontes

| Horizonte | Escenario | Prob | Rango ret % | Mean ret % |
|---|---|---:|---|---:|
| 1M | Esperado | 50% | [-0.12%, +1.27%] | +0.58% |
| 1M | Alcista | 21% | [+1.27%, +3.17%] | +1.80% |
| 1M | Bajista | 19% | [-1.19%, -0.12%] | -0.64% |
| 1M | Riesgo (cola) | 10% | [-3.06%, -1.19%] | -1.63% |
| 3M | Esperado | 50% | [+0.76%, +2.14%] | +1.46% |
| 3M | Alcista | 29% | [+2.14%, +4.99%] | +2.87% |
| 3M | Bajista | 11% | [+0.28%, +0.76%] | +0.54% |
| 3M | Riesgo (cola) | 10% | [-2.68%, +0.28%] | -0.24% |
| 6M | Esperado | 50% | [+1.86%, +4.04%] | +2.96% |
| 6M | Alcista | 24% | [+4.04%, +7.33%] | +4.89% |
| 6M | Bajista | 16% | [+0.76%, +1.86%] | +1.34% |
| 6M | Riesgo (cola) | 10% | [-2.80%, +0.76%] | -0.05% |
| 12M | Esperado | 50% | [+4.49%, +7.78%] | +6.11% |
| 12M | Alcista | 21% | [+7.78%, +11.46%] | +8.78% |
| 12M | Bajista | 19% | [+2.61%, +4.48%] | +3.68% |
| 12M | Riesgo (cola) | 10% | [-7.82%, +2.61%] | +0.15% |

## K óptimo por ETF y horizonte

| ETF | h=1M | h=3M | h=6M | h=12M |
|---|---:|---:|---:|---:|
| ACWI | 30 | 40 | 20 | 40 |
| AGG | 15 | 5 | 5 | 30 |
| BIL | 15 | 5 | 40 | 40 |
| EMB | 30 | 5 | 30 | 5 |
| GHYG | 5 | 40 | 15 | 15 |
| IGLA | 5 | 5 | 15 | 40 |
| LQD | 15 | 40 | 10 | 30 |

## Detalle por ETF — horizonte 12M (con K específico)

| ETF | Weight | K | n_obs | Esperado mean | Bajista mean | Alcista mean | Riesgo mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| BIL | 5% | 40 | 40 | +4.53% | +2.45% | +5.21% | +1.16% |
| IGLA | 45% | 40 | 40 | +4.73% | -0.95% | +8.88% | -8.62% |
| GHYG | 20% | 15 | 15 | +9.12% | +5.89% | +15.01% | +3.37% |
| LQD | 10% | 30 | 30 | +6.46% | +2.54% | +13.36% | -1.40% |
| EMB | 10% | 5 | 5 | +11.86% | — | — | +8.72% |
| ACWI | 10% | 40 | 40 | +16.60% | +4.76% | +25.15% | -9.18% |

## Validación: cobertura del Esperado vs realizado (walk-forward 2020-2025)

Cobertura objetivo = 50%. La columna muestra qué % de los realizados cayeron en el rango Esperado.

| ETF | h=1M | h=3M | h=6M | h=12M |
|---|---:|---:|---:|---:|
| BIL | 47% | 47% | 33% | 22% |
| IGLA | 42% | 38% | 42% | 23% |
| LQD | 41% | 39% | 33% | 33% |
| GHYG | 38% | 36% | 31% | 44% |
| EMB | 41% | 42% | 39% | 50% |
| ACWI | 41% | 38% | 36% | 44% |
| AGG | 42% | 40% | 40% | 27% |

**Lecturas honestas**:
- BIL y EMB tienen mejor calibración en horizontes cortos (~47-50%).
- Horizontes largos (12M) tienden a subcobertura → rangos esperados demasiado angostos.
- Bonos largos (IGLA, LQD, AGG) tienen sesgo positivo sistemático en 12M:
  el modelo es optimista vs realidad porque los vecinos del hike 2022-23 son raros.
- Para deck mensual: declarar caveat de subcobertura en horizonte 12M.

## Metodología

1. **Macro state vector**: 5 features (PCE YoY vintage, U-3, BE 5Y, Fed Funds, 2s10s).
2. **Nearest Neighbors**: top-K meses históricos por distancia euclidiana estandarizada.
3. **K óptimo por (ETF, horizonte)**: walk-forward 2020-2025, score = error_calibración + 0.1·amplitud.
4. **HDI 50%**: highest density interval (rango más angosto que captura 50% masa).
5. **Escenarios**: Esperado 50% / Bajista 20% / Alcista 20% / Riesgo 10% (cola).
6. **Portafolio**: Monte Carlo 5000 sims combinando retornos por ETF según allocation.

## Archivos relacionados

- `producto_b_escenarios_mayo2026.md` (este)
- `producto_b_escenarios_mayo2026.xlsx` (versión Excel para enviar a Antulio)
- `data/external/tasas_mercantil/nn_k_optimization.parquet` (196 filas, optimización K)