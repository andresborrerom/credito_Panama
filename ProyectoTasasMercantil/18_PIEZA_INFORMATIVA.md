# 18 · Pieza informativa — diseño y alcance

**Estado**: ✍️ aprobado en arquitectura · arrancando Sprint 1 (USA, 3 slides).
**Owner**: este doc se actualiza por sprint a medida que se cierran slides.
**Audiencia del entregable**: comité ejecutivo.

---

## 1 · Propósito

Traer al deck mensual el **contexto de mercado** que hoy se mira en pantallas dispersas (Bloomberg, EODHD, prensa). Es **informativa**, no recomendativa. Disclaimer compliance obligatorio.

## 2 · Principio rector

**Una sola corrida mensual** dispara TODO. Cero clicks manuales fuera de la plantilla Bloomberg que ya existe. Cuando una fuente falla, el sistema sigue y deja explícita la falla en el footer del slide.

## 3 · Lección de diseño heredada (Mercantil v0.3.0)

El modelo Mercantil v0.3.0 demostró que **nunca un solo predictor**:

- 55% × Pieza A — implied path SR3 (lo que cotiza el mercado de futuros, = WIRP)
- 45% × Pieza B — regla de Taylor con R* dinámico de Cleveland Fed
- Skill mediano vs naive: +18% (1M), +24% (6M), +46% (12M). Bootstrap → P(skill>0) ≥ 99%.

**Aplicación a esta pieza**: en todo bloque donde haya "qué espera X", se traen ≥2 fuentes complementarias (mercado + encuesta + sentiment) y se muestran lado a lado, no una traza. La señal está en los disagreements, no en un consenso forzado.

## 4 · Decisiones de scope (aprobadas 2026-06-16)

| # | Decisión | Implicación |
|---|---|---|
| 1 | **EODHD como fuente preferida**. Lo que no esté ahí, se amplía la plantilla BBG y se la mandamos a Antulio. | Reduce dependencia BBG en lo cotidiano. Plantilla BBG crece para los huecos (forwards FX, CDS Panamá, swap 1y/3y). |
| 2 | **Sentiment dual**: polarity numérico EODHD + clasificación semántica vía LLM. | Más rico que solo polarity; LLM sobre top-N titulares limita costo. |
| 3 | **Forwards FX a la plantilla BBG** (G10 × 8 tenors ≈ 40 instrumentos). | Antulio rellena cuando corre la plantilla. EODHD no tiene forwards FX. |
| 4 | **Dataset interno de Panamá corporate** (rating × plazo × sector) construido desde Latinex / fuentes ya encontradas en proyecto `credito_panama`. NO depende del XLSX del analista. | Más auditable. Trabajo de ingest una vez + refresh mensual. |

## 5 · Bloques del scope total

| Bloque | Qué incluye | Estado |
|---|---|---|
| **USA — Fed projections** | Dot plot SEP + evolución entre SEPs | Sprint 1 |
| **USA — Path multi-fuente** | WIRP + NY Fed PD Survey + ECFC BBG + EODHD polarity + LLM semántico + Mercantil v0.3.0 | Sprint 1 |
| **USA — Estructura temporal** | UST nominal + TIPS real + breakeven + forwards SOFR 5y trimestral | Sprint 1 |
| **FX G10** | EUR/GBP/JPY/CHF + DXY: spot, forwards trimestrales 5y, implied vol 1m/3m/1y | Sprint 2 |
| **Panamá soberano** | Spreads por tenor, EMBI Panamá, CDS 5Y | Sprint 3 |
| **Panamá corporate** | Spreads rating × plazo × sector (dataset interno) | Sprint 3 |

## 6 · Fuentes y plantilla BBG ampliada

Mapeo realista por bloque (con respaldo automático):

| Bloque | Fuente primaria | Respaldo auto | Latencia |
|---|---|---|---|
| Dot plot SEP | Fed website PDF (4/año, calendario fijo) | — | ≤48h post-meeting |
| Implied path | BBG SR3 strip (en plantilla v0.2) | EODHD SR3 futures + CME public CSV | tiempo real |
| NY Fed PD Survey | NY Fed PDF (semestral) | — | ≤72h post-FOMC |
| ECFC | BBG ECFC function — **AGREGAR A PLANTILLA** | — | mensual |
| Sentiment polarity | EODHD `/news?s=SPY,TLT,UST...&from=...` | — | diario |
| Sentiment semántico | LLM sobre top-N titulares EODHD | — | diario |
| UST CMT + TIPS + breakeven | BBG (en plantilla v0.2) | FRED CMT + DGS | mensual |
| Swap OIS 1Y/3Y | **AGREGAR A PLANTILLA** (hoy solo 2Y/5Y/10Y/30Y) | — | mensual |
| Forwards SOFR trimestral | bootstrap interno desde swap + SR3 | — | mensual |
| FX spot G10 + DXY | EODHD `/eod/<PAIR>.FOREX` | BBG (plantilla) | diario |
| Forwards FX 1Q-20Q | BBG — **AGREGAR A PLANTILLA** (40 instr.) | — | mensual |
| Implied vol FX | BBG — agregar a plantilla (opcional) | — | mensual |
| Panamá soberano spread | `credito_panama` existente | BBG `PANAMA Govt` | mensual |
| Panamá EMBI | BBG `JPEIPANE Index` (en plantilla) | — | mensual |
| Panamá CDS 5Y | BBG `CPAN CDS USD SR 5Y Corp` — **AGREGAR A PLANTILLA** | — | mensual |
| Panamá corp | Dataset interno Latinex (a construir) | — | mensual |

### Cambios a la plantilla Bloomberg (acumulados, salen en v0.3)

- **+1** ECFC Fed funds próximas reuniones (consensus economistas)
- **+2** Swap OIS 1Y, 3Y
- **+40** Forwards FX G10: EUR/GBP/JPY/CHF/AUD × {1Q,2Q,3Q,1Y,2Y,3Y,4Y,5Y}
- **+15** Implied vol FX 1M/3M/1Y × 5 pares
- **+1** CDS Panamá soberano 5Y

Total v0.3: ~135 instrumentos (vs 76 en v0.2). El analista sigue editando una sola celda (AS_OF).

## 7 · Pipeline mensual (automático)

```
01.  python scripts/ingest_informativa_monthly.py <as_of>
       ├─ fetch_fed_sep.py         (4/año)
       ├─ fetch_pd_survey.py       (4/año, post FOMC)
       ├─ fetch_eodhd_news.py      (sentiment polarity, diario backfill)
       ├─ fetch_eodhd_fx.py        (spot G10, diario backfill)
       ├─ fetch_panama_latinex.py  (refresh corp + soberano)
       └─ load_bbg_template.py     (plantilla Antulio del mes)

02.  python scripts/build_informativa_views.py <as_of>
       genera PNGs en docs/informativa/outputs/<as_of>/

03.  python -m tasas_mercantil.informativa.deck
       compila PPT auto-descubridor
```

Idempotencia: cada fetch escribe `data/external/informativa/<as_of>/<bloque>.parquet`. No se re-llama si ya existe y no es viernes de cierre.

Failover encadenado: BBG → EODHD/FRED → cache anterior + warning visible en el slide. La slide se construye igual con asterisco si una fuente cayó.

Compliance: disclaimer "Documento informativo con fines analíticos. No constituye recomendación de inversión." en cada slide narrativa + portada del PPT.

## 8 · Sprint 1 — USA (en curso)

3 slides. **Cero duplicación con Producto A** (que ya da implied path y L5 Mercantil v0.3.0).

### L_USA_1 — Dot plot SEP + evolución

- Scatter participante × año + medianas + p25/p75.
- Comparación con dot plot anterior (flechas de revisión).
- Línea implied path SR3 superpuesta → gap Fed-vs-mercado en bps por año.
- Frontera: SEP ~3 años + longer run, no 5y. Documentado en footer.

### L_USA_2 — Path multi-fuente Fed Funds

- 1 gráfico × próximas 6 reuniones: trazas por WIRP / PD Survey / ECFC / EODHD polarity / LLM semántico / Mercantil v0.3.0.
- 1 tabla: P(cut|hold|hike) próxima reunión por fuente.
- Encarna la lección Mercantil v0.3.0: la señal está en los disagreements.

### L_USA_3 — Estructura temporal completa

- 4 paneles: UST nominal, TIPS real, breakeven, forwards SOFR 1Q–20Q (5y).
- Cortes hoy / 1m / 12m para los 3 primeros.
- Bootstrap forwards interno desde swap OIS + SR3 strip.

## 9 · Sprint 2 — FX G10 (pendiente, NO empezar hasta cerrar Sprint 1)

3 slides previstas: spot + forwards 5y por par (EUR/GBP/JPY/CHF/DXY), pivot vs USD, implied vol heatmap.

## 10 · Sprint 3 — Panamá (pendiente)

3 slides previstas: soberano (spread por tenor + EMBI + CDS), corporate (heatmap rating × plazo × sector), evolución spreads 12m.

## 11 · Bitácora

- **2026-06-16**: creación. Arquitectura aprobada. Sprint 1 USA arranca.
