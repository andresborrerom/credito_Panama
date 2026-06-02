# Producto B · Escenarios del Portafolio LUZ · corte mayo 2026

> Generado 2026-06-02 · framework riguroso v2 · datos hasta 2026-05-28.

## Framework (corregido tras feedback editorial 2026-06)

1. **Esperado (HDI 50%)**: rango más angosto que contiene 50% de la masa. **Es lo único optimizado**. Tiene libertad para sesgarse según la distribución real (no forzado al centro).
2. **Riesgo**: cola izquierda con masa fija = **5%** (cutoff por percentil P5). Cutoff fijo, no target de probabilidad.
3. **Bajista**: TODO lo que queda entre Riesgo y HDI low. Probabilidad **empírica** — no impuesta.
4. **Alcista**: TODO lo que queda a la derecha del HDI. Probabilidad **empírica**.

**Suma**: 5% + Bajista_p + 50% + Alcista_p = 100% → Bajista_p + Alcista_p = 45%.

Si la distribución es asimétrica, Bajista ≠ Alcista — y eso es información valiosa. Forzar simetría (como hacíamos antes) ocultaba el sesgo de la distribución.

## TL;DR portafolio LUZ

- **Esperado 12M**: retorno en rango **[+4.49%, +7.78%]** (HDI 50%, prob exacta 50.0%).
- **Riesgo 12M (cola P5)**: retorno ≤ +1.56%. Peor mean -1.85%.
- **Sesgo 12M**: Bajista 23.6% vs Alcista 21.4% — distribución levemente bajista.

## Macro state actual

| Variable | Valor |
|---|---:|
| PCE core YoY (vintage) | 2.77% |
| Unemployment U-3 | 4.30% |
| Breakeven 5Y | 2.56% |
| Fed Funds upper | 3.75% |
| Slope 2s10s | +43 bps |

## Escenarios del portafolio LUZ — 4 horizontes

| h | Esperado (HDI 50%) — rango | Bajista (prob, mean) | Alcista (prob, mean) | Riesgo P5 (mean) |
|---|---|---|---|---|
| 1M | [-0.12%, +1.27%] | 24.4% · mean -0.79% | 20.6% · mean +1.80% | -1.91% |
| 3M | [+0.76%, +2.14%] | 16.4% · mean +0.40% | 28.6% · mean +2.87% | -0.56% |
| 6M | [+1.86%, +4.04%] | 20.6% · mean +1.12% | 24.4% · mean +4.89% | -0.54% |
| 12M | [+4.49%, +7.78%] | 23.6% · mean +3.36% | 21.4% · mean +8.78% | -1.85% |

## Lectura editorial de las asimetrías

- **1M**: sesgo bajista leve (Alcista − Bajista = -3.9pp).
- **3M**: **sesgo alcista fuerte** (Alcista − Bajista = +12.2pp).
- **6M**: sesgo alcista leve (Alcista − Bajista = +3.8pp).
- **12M**: sesgo bajista leve (Alcista − Bajista = -2.2pp).

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

## Detalle por ETF · horizonte 12M

| ETF | Weight | K | n_obs | Esp range | Bajista prob/mean | Alcista prob/mean | Riesgo mean |
|---|---:|---:|---:|---|---|---|---:|
| BIL | 5% | 40 | 40 | [+3.96%, +5.09%] | 38% / +2.34% | 5% / +5.21% | +0.72% |
| IGLA | 45% | 40 | 40 | [+1.54%, +7.74%] | 32% / -1.42% | 10% / +8.88% | -13.28% |
| GHYG | 20% | 15 | 15 | [+7.77%, +10.68%] | 27% / +5.38% | 7% / +15.01% | +2.89% |
| LQD | 10% | 30 | 30 | [+4.18%, +8.33%] | 27% / +2.31% | 13% / +13.36% | -2.45% |
| EMB | 10% | 5 | 5 | [+11.11%, +12.98%] | — | — | +8.72% |
| ACWI | 10% | 40 | 40 | [+11.91%, +20.87%] | 32% / +3.01% | 10% / +25.15% | -11.79% |

## Outputs gráficos

- `histograma_portafolio_1M.png` — vista detallada 1M con cutoffs anotados.
- `histograma_portafolio_4horizontes.png` — los 4 horizontes en grid 2x2.

## Metodología

1. **Macro state vector**: PCE YoY vintage, U-3, BE 5Y, Fed Funds, 2s10s (5 features).
2. **Nearest Neighbors**: top-K meses históricos por distancia euclidiana estandarizada.
3. **K óptimo por (ETF, horizonte)**: walk-forward 2020-2025.
4. **HDI 50%**: highest density interval (lo único optimizado en el escenario).
5. **Riesgo cutoff fijo (5%)**: peor 5% de la distribución (cola izquierda).
6. **Bajista / Alcista**: probabilidades empíricas — la asimetría es información.
7. **Portafolio**: Monte Carlo 5000 sims combinando retornos por ETF con allocation.