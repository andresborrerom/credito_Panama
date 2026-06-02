# 16 · Producto B — Modelo de Retornos Esperados de Portafolio

> Nuevo en el alcance tras reunión 2026-06-01 (Camilo Forero, Antulio Moya,
> Alfonso Brandini, Andrés Borrero). Toma como base el Excel
> `Ret esperados.xlsx` que Antulio ya construyó y lo sofistica con escenarios
> probabilísticos.

## Para qué sirve

Para que la tesorería del grupo + la mesa LUZ + gerencia banco PA tengan
**retornos esperados de portafolio** con dos componentes:

1. **Punto central**: el retorno esperado para el horizonte (resto del año,
   p.ej. JUN-DIC 2026 + anualizado).
2. **Distribución**: 3-4 escenarios con probabilidad asignada, y para cada
   uno la sensibilidad del portafolio.

Esto reemplaza la práctica actual de "carry actual + ajuste subjetivo +
sensación de gut".

## Universo (asset classes)

Las 6 del Excel actual de Antulio + global de bonos pedido en reunión:

| Asset class | ETF de referencia | Componentes de retorno |
|---|---|---|
| Treasury Bills (cash) | BIL US Equity | Carry + delta tasas corto |
| Treasury Notes | IGLA LN Equity | Carry + duración × delta tasas |
| Investment-Grade Bonds | LQD US Equity | Carry + duración + spread |
| High-Yield Bonds | GHYG US Equity | Carry + duración + spread + default |
| EM USD Bonds | EMB US Equity | Carry + duración + spread + soberano EM |
| Global Equity | ACWI US Equity | Div yield + earnings growth + ΔP/E |
| Global Bond Index | AGG / LEGATRUU (a confirmar) | Carry + duración × tasas globales |

## Metodología

### v1.0 (lo que Antulio ya tiene)

`Expected Return RF = carry + duración × Δ tasas + Δ spread`

Donde `Δ tasas` viene de la **opinión editorial** de la mesa (perilla en
línea 13 del Excel: "Variación tasas 2H 2026 vs WIRP"). Hoy ese input es
−10 bps por intuición de Camilo.

**Limitación**: la perilla es subjetiva, no validada cuantitativamente.

### v1.1 (quick win cerrado el 2026-06-02)

Sustituimos la perilla editorial por el **delta cuantitativo del modelo
Mercantil v0.3.0**. Cálculo:

```
delta_2h_2026 = avg(forecast_modelo(jun..dic 2026)) - avg(WIRP(jun..dic 2026))
```

Hoy: **−9.6 bps**. Coincide con la intuición de Camilo (−10 bps). El modelo
valida; no contradice. Documentado en
`cortes/2026-05/output_v10/sugerencia_input_mercantil_v0.3.0.md`.

### v2.0 (objetivo, sesión M-3+)

**Distribución de probabilidad de escenarios**. En lugar de un único delta,
generar 3-4 escenarios con probabilidad asignada:

| Escenario | Path Fed Funds 2H 2026 | P(ocurre) | Retorno portafolio |
|---|---|---:|---|
| Cut continuado (Mercantil base) | −10 bps vs WIRP | ~40% | calculado por modelo |
| Consenso WIRP | 0 bps vs WIRP | ~35% | calculado por modelo |
| Hawkish (CPI sorpresa al alza) | +25 bps vs WIRP | ~20% | calculado por modelo |
| Cola dovish (recesión rápida) | −50 bps vs WIRP | ~5% | calculado por modelo |

Las probabilidades vienen de:
- (a) distribución empírica del modelo Mercantil (bootstrap de errores).
- (b) ajuste editorial de la mesa según contexto del mes.

### Metodologías candidatas para v2.0

Camilo pidió en la reunión: *"deben haber mil [metodologías], se puede poner a competir entre ellas"*. Sí:

| # | Método | Para qué |
|---|---|---|
| 1 | **Nearest neighbors histórico** | Buscar meses pasados con macro similar (PCE, U-3, BE5Y) y reportar distribución de retornos realizados |
| 2 | **Simulación Monte Carlo** | Sobre el modelo Mercantil con incertidumbre en R\*, π, U-3 |
| 3 | **Block bootstrap del backtest** | Lo que ya tenemos para skill score, extender a retornos |
| 4 | **Bayesian model averaging** | Combinar varios modelos rivales con pesos derivados del backtest |

Plan: implementar **(1) y (3) primero**, decidir si (2) y (4) agregan valor en función de los resultados.

## Output esperado

Una hoja Excel + un PDF con dos páginas:

**Página 1 — Retornos esperados por asset class**:
- Tabla con punto central + IC 80% para cada asset class.
- Resultado total del portafolio dado el allocation actual.
- Comparativa vs Excel anterior (delta de retorno esperado).

**Página 2 — Escenarios + sensibilidad**:
- 3-4 escenarios con probabilidad.
- Para cada escenario: retorno del portafolio.
- Identificación de qué escenario "rompe" el budget anual y qué probabilidad tiene.

## Dependencias

1. **Modelo Mercantil v0.3.0** ✅ (existe).
2. **Excel `Ret esperados.xlsx`** ✅ (Antulio lo tiene).
3. **Allocation del portafolio LUZ** ✅ (está en el Excel: BIL 5%, IGLA 45%, GHYG 20%, LQD 10%, EMB 10%, ACWI 10%).
4. **Histórico de retornos mensuales por ETF** 🟡 — falta ingesta. Puede venir del Excel de Antulio en versiones futuras o directo de Bloomberg/Yahoo.
5. **Modelo Pieza E (spread credit)** 🟡 — para descomponer HY/IG/EM, hoy spread es input editorial. Pendiente.

## Roadmap por sesión

| Sesión | Foco | Entregable |
|---|---|---|
| M-3.1 (ya) | Quick win: input cuantitativo Mercantil → Excel | Excel derivado + sugerencia |
| M-3.2 | Histórico de retornos mensuales por ETF (ingesta) | Parquet con returns BIL/IGLA/etc. desde 2018 |
| M-3.3 | Nearest neighbors histórico para distribución | Notebook + tabla de escenarios |
| M-3.4 | Excel v2.0 con 3-4 escenarios + sensibilidad | XLSX listo para Antulio |
| M-3.5 | Validación con Camilo + integración al deck (lámina nueva) | Lámina escenarios en el deck mensual |

## Tensiones a resolver

1. **Producto B vs Lámina 8 del deck**: la Lámina 8 "Impacto Mercantil" en
   su forma actual (5 unidades × what-if-right/wrong) **pierde sentido**
   tras la reunión. Lo accionable está en el Producto B (escenarios +
   sensibilidad del portafolio). Decisión: Lámina 8 se reemplaza por
   "Escenarios + portafolio" cuando v2.0 esté listo.
2. **Frecuencia**: Excel Antulio es mensual; deck también es mensual.
   Coordinar timing T0 + T+3.
3. **Allocation tactical vs strategic**: el modelo dice retorno esperado
   dado un allocation. Si la mesa cambia allocation, los retornos cambian
   trivialmente. ¿El modelo también sugiere allocation óptimo? Por ahora NO
   — Camilo fue claro: "informativo, no recomendación".
