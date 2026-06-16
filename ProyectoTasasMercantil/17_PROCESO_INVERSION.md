# 17 · Proceso de inversión Mercantil — pieza por pieza

Este documento articula **qué tenemos construido a la fecha** (2026-06-16) y
**cómo encaja en el proceso de inversión integral del grupo**. Es el índice
ejecutivo: si el lector quiere el detalle de implementación de cada pieza, los
docs específicos están enlazados.

---

## Mapa de productos

| Pieza | Audiencia | Pregunta que responde | Estado |
|---|---|---|---|
| **Producto A** — Reporte mensual de tasas | Comité | "¿Dónde están las tasas USA y qué nos dice el modelo predictivo?" | ✅ operativo, corte 2026-05 cerrado |
| **Producto B** — Retornos esperados LUZ | Mesa de tesorería | "Dado LUZ, ¿qué retorno esperar a 12 meses y cómo se compara con la historia?" | ✅ demo presentable (M1–M9), en HOLD |
| **Pieza informativa** — Contexto global + Panamá | Comité ejecutivo | "¿Qué dicen los dot-plots, los analistas y el mercado?" | 🚧 por arrancar (siguiente sprint) |
| **CDS Panamá + descomposición** | Comité ejecutivo | "¿Cuánto del spread Panamá es factor USA y cuánto es idiosincrático?" | ❌ pendiente |
| **Caso Banesco — perpetuo 7% USD** | Tesorería | "¿Es oportunidad de fondeo proactivo?" | ❌ pendiente |

---

## Producto A — Reporte mensual de tasas USA

**Doc maestro**: `01_PLAN_Y_FASES.md` Fase 1.
**Código**: `src/tasas_mercantil/producto_a/`.
**Entregable**: `deck_fase1_usa_<as_of>.pptx` — 9 slides (portada + 8 láminas).

Piezas vivas:

| Lámina | Pieza analítica |
|---|---|
| L1 Mensajes clave | Resumen del mes |
| L2 Política Fed | Implied path SOFR + dot plot histórico |
| L3 SOFR | Tasas de mercado |
| L4 Curva UST 3 cortes | Spot vs hace 1m vs hace 12m |
| L5 Expectativas Fed (modelo Mercantil) | **Modelo BMA propio** — diferencia bps vs forward neutral. Quick-win de la reunión: línea 13 de Antulio. |
| L6 Calendario USA | Eventos macro próximos 30-60 días |
| L7 Destacados del mes | Sorpresas |
| L8 Lectura del analista | Texto narrativo |

**Lo que NO está**: factor de **oferta de deuda** USA (subastas, QRA, déficit, maturity wall). Detectado el 2026-06-16. Lugar natural: `implied_path.py` v0.2.0 (term premium Cieslak-Povala).

---

## Producto B — Retornos esperados del portafolio LUZ

**Docs**: `16_PRODUCTO_B_RETORNOS_ESPERADOS.md` (scope), `docs/producto_b/ROADMAP_LUZ.md` (hitos), `docs/producto_b/BITACORA_CONSTRUCCION.md` (decisiones).
**Código**: `src/tasas_mercantil/producto_b/` (15 módulos).
**Entregable**: `deck_producto_b_<fecha>.pptx`.

### Cadena analítica

```
Snapshot LUZ (38 posiciones)
        ↓
forecast_etf × 7 ETFs (cached)        forecast_bond_A_AR1 × 4 UST/TBill
        ↓                                       ↓
        portfolio_aggregator (suma ponderada de samples)
        ↓
        PortfolioForecast — nube MC del portafolio
        ↓
   ┌────┼─────────────────────┬──────────────────────┐
   ↓    ↓                     ↓                      ↓
Output 3:  Output 1:      Output 2:           Output 3 (M7):
mensaje    7 vistas       histograma          comparación FDP
ejecutivo  de bandas      rico (KDE)          predictiva vs histórica
                                              + veredicto automático
                                              (5 zonas peras-con-peras)
```

### Las 5 zonas (framework de partición de la FDP)

| Zona | Cálculo |
|---|---|
| Riesgo (cola izq) | cola 2.5% fija |
| Bajista | masa empírica entre cola izq y HDI 50% low |
| **Esperado** | **HDI 50% — único rango optimizado (más angosto que contiene 50%)** |
| Alcista | masa empírica entre HDI 50% high y cola der |
| Sorpresa | cola 2.5% fija |

Esa partición se aplica idéntica a la **FDP predictiva (nube MC)** y a la **FDP histórica descriptiva** (retornos h-meses observados, mismo mix de hoy) → señal por activo (5 índices) y por portafolio.

### Veredicto automático

3 ejes → 1 etiqueta:
- **Dirección** = signo de (mediana pred − mediana hist).
- **Magnitud** = |Δ bps| → neutral (<50) / leve (<150) / moderada (<300) / fuerte (≥300).
- **Confianza** = ancho HDI50 pred / hist (×0.85↓ más confianza / ×1.15↑ más incertidumbre).
- **Cola** = Δ media zona Riesgo.

Resultado: `"POSITIVA fuerte. Centro +381 bps vs historia; más confianza (×0.74); menor riesgo de cola (+707 bps)"`.

### Validación

10 walk-forward del portafolio (M6): Vista B 9/10 = 90%. Validación cualitativa M7: el modelo señaló **NEGATIVA fuerte** en los 2 cortes de 2022 (bear market de bonos) y POSITIVA / NEUTRAL en 2024 (recuperación).

### Estado HOLD

Lo cerrado al 2026-06-16 está en `ROADMAP_LUZ.md` (M1–M9 ✅). Los próximos pasos están en la sección HOLD del mismo doc, priorizados.

---

## Pieza informativa (contexto global + Panamá) — POR ARRANCAR

Este es el siguiente sprint que arranca después del HOLD del Producto B.

Propósito: traer al deck mensual el **contexto de mercado** que hoy se mira en pantallas dispersas (Bloomberg, EODHD, prensa) y dejarlo automatizado.

Alcance pedido:
- Dot plot Fed (SEP) y su evolución
- Sentiment de analistas — opinión cualitativa
- Probabilidades de analistas para movimientos Fed (vs CME FedWatch ya ingestado)
- FX G10: EUR, GBP, JPY, CHF, DXY (spot + 5y + forwards trimestrales)
- Panamá: spreads por rating × plazo × sector, CDS

Diseño: ver propuesta separada (el doc se anexa cuando se apruebe la arquitectura).

---

## Disclaimer compliance

Todos los entregables del proceso llevan la línea:

> **"Documento informativo con fines analíticos. No constituye recomendación de inversión."**

Implementado en:
- `comparacion_historica.plot_comparacion` — footer de cada PNG.
- `deck.py` (Producto B) — slide Compliance + footer de cada slide narrativa.
- (Pendiente en Producto A: añadir a `executive_summary` y portada deck Fase 1.)

---

## Bitácora de actualizaciones de este doc

- **2026-06-16**: creación. Producto B pasa a HOLD post-M9; arranca el alcance de la pieza informativa.
