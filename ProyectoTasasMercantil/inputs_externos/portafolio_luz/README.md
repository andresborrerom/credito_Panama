# Portafolio LUZ CAPITAL LTD — input externo

Fuente: Executive Daily Pack enviado a diario por Tesorería Corporativa (CoE),
firmado por Daniela A. Garban M. (Trader).

Cada snapshot diario se guarda en `snapshots/YYYY-MM-DD/` con:
- `holdings.csv` — tabla estructurada (máquina-legible).
- `metadata.md` — resumen ejecutivo del día (transcripción de las cifras del email).
- `raw/` — capturas de pantalla originales si las hay (PNG/JPG).

Convención de actualización: cuando llegue un nuevo pack diario, crear nuevo
folder `snapshots/YYYY-MM-DD/`. NO sobreescribir snapshots previos —
necesitamos la serie histórica para backtest y para detectar cambios de
asignación.

## Snapshots disponibles

| Fecha | Total (USDM) | P&L MTD (USDk) | Archivo |
|---|---|---|---|
| 2026-06-09 | 49.0 | −524.0 | [snapshots/2026-06-09/](snapshots/2026-06-09/) |

## Estructura del portafolio (snapshot 2026-06-09)

Composición a valor de mercado (% del total):

| Tipo | % | USD MM |
|---|---|---|
| Exchange traded fund | 60.8% | 29.8 |
| Bond (US Treasury + corp) | 26.8% | 13.1 |
| TBill | 5.9% | 2.9 |
| Equity (ETF ISHARES 3Y Intl) | 5.9% | 2.9 |
| Fund investment | 0.2% | 0.1 |
| Cash | 0.4% | 0.2 |

Por clasificación liquidez/tesorería (Tabla 4):

| Categoría | % | USD MM |
|---|---|---|
| US Treasury | 45% | 22.1 |
| Corp | 28% | 13.6 |
| MM (money market) | 16% | 8.1 |
| Equity | 10% | 5.0 |
| Options | 0% | 0.0 |
| Cash | 0% | 0.2 |

## Mapeo a modelos del Producto B (preliminar)

Asset classes presentes en LUZ y su correspondencia con los ETFs ya modelados:

| Posición LUZ | Ticker / Proxy | % LUZ | Estado modelo |
|---|---|---|---|
| ISHARES INTERNATIONAL TREASU | IGOV | 9.89% | Pendiente — proxy IGLA en modelos actuales |
| ISHARES IBOXX INVESTMENT GRA | **LQD** | 9.48% | **Iter 6 listo** (forecast_api.py) |
| ISHARES US&INTL HIGH YIELD C | GHYG/HYG-INTL | 8.27% | Pendiente — modelo GHYG planeado |
| INVESCO BULLETSHARES 2026 HY | BSJQ | 6.66% | Pendiente — short-duration HY |
| ISHARES JP MORGAN USD EMERGI | **EMB** | 4.28% | Pendiente — modelo EMB planeado |
| VANGUARD S&P 500 ETF | VOO/VTI | 2.63% | Pendiente — fuera de scope original (equity) |
| INVESCO INTERNATIONAL CORPOR | PICB | 2.61% | Pendiente — IG internacional |
| ISHARES TIPS BOND ETF | TIP | 2.00% | Pendiente — TIPS |
| ISHARES MSCI ACWI ETF | ACWI | 2.00% | Pendiente — global equity (audio lo mencionó) |
| US Treasury bonds (3 directos largos) | UST 2031/2035/2036 | 25.76% | Mapeable vía UST yields (US10Y/US30Y) |
| TBill Nov 26 | UST 1Y | 5.92% | Mapeable vía US1Y |
| ISHARES -3Y INTERNATIONA | ISHG | 5.87% | Pendiente — short-duration intl govies |
| HF SINCLAIR CORP Feb 28 | corp directo | 1.02% | Idiosincrático, modelar como spread+UST |

**Cobertura modelo actual sobre LUZ:** ~9.5% (solo LQD vía Iter 6).

Para llegar a cobertura ≥80% del portafolio necesitamos modelar al menos:
IGOV, GHYG/HYG, EMB, TIP, ACWI + mapeo directo de los 3 UST bonds y 1 TBill.
Eso cubriría ~75-80%. El resto (equity sectorial chico, cash, MM) son ruido en
términos de impacto sobre el retorno esperado.

## Datos no transcritos del pack diario

El email también tiene:
- P&L DTD y MTD desglosado por instrumento (Tablas 2 y 3).
- Histórico P&L mensual 2025-2026 (Gráfica 3).
- Texto editorial del día (transacciones pactadas, comentarios sobre el mercado).
- Sección de "Dividends/Interest/Others".

Cuando se necesite, se puede estructurar también, pero el core para forecast
es la tabla de holdings (instrumento + valor mercado + exposición).
