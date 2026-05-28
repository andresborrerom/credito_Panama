# 06 · Grupo Mercantil — mapa de unidades e impactos de tasas

Este documento sirve de **insumo para la Fase 4** del reporte (Impactos al
negocio). Debe completarse y validarse con Andrés/Camilo antes del primer corte.
Lo que está aquí es un esqueleto a confirmar — no se publica nada sin que el
usuario marque cada unidad como verificada.

## Estado del documento

🟡 **En construcción.** Necesita validación de Andrés en la próxima sesión.

## Propuesta inicial de unidades a cubrir

Las unidades que aparecen acá son las que Andrés mencionó en la conversación de
arranque. La lista completa y vinculaciones legales deben confirmarse en la
próxima sesión.

| # | Unidad | Jurisdicción | Moneda funcional principal | Tasa(s) más sensible(s) |
|---|---|---|---|---|
| 1 | Banco Mercantil Venezuela | VE | Bolívar | Tasa BCV, encaje legal, FX VES/USD |
| 2 | Mercantil Banco (Panamá) | PA | USD | SOFR 3M, UST 5Y, costo de fondeo local PA |
| 3 | Mercantil Seguros | VE / regional | mixto | UST 5–10Y (portafolio inversiones), FX |
| 4 | Wealth Management / Casa de Bolsa | regional | USD | UST curve completa, EMBI, EM USD IG/HY |
| 5 | Tesorería / Posición propia | grupo | mixto | Fed Funds, SOFR, UST 10Y, FX |
| ¿? | Otras unidades a confirmar (Mercantil Bank Curaçao? Aliadas?) | — | — | — |

## Por unidad — cómo le pega cada movimiento de tasa

> Lo siguiente es una **plantilla cualitativa**. Sin datos internos del libro no
> se pueden cuantificar. Cuando se autorice cargar datos internos (Fase 4
> avanzada, ver `01_PLAN_Y_FASES.md`), cada subsección se sustituye por números.

### 1) Banco Mercantil Venezuela

**Drivers principales:**
- Tasa de política BCV (transmite a tasas activas máximas y pasivas reguladas).
- Encaje legal (capacidad de prestar y costo de oportunidad).
- FX VES/USD oficial (impacto en capital regulatorio en bolívares; balance dolarizado en la práctica).
- Inflación venezolana (descuenta cualquier tasa nominal).

**Mecánica:**
- Sube la tasa BCV → margen del banco se aprieta si la tasa pasiva ya estaba en el techo.
- Sube el encaje → menos pulmón de liquidez; oportunidad costo alto.
- Devalúa el bolívar → ajuste en patrimonio en bolívares (regulatorio) y en capital reportable en USD.

**Lectura que va al deck:**
- Diferencial tasa BCV vs inflación → tasa real negativa o positiva.
- Brecha FX oficial vs paralelo → presión sobre balance, riesgo regulatorio.

---

### 2) Mercantil Banco (Panamá)

**Drivers principales:**
- SOFR 3M (referencia para libros a tasa variable).
- UST 5Y (referencia para libro de inversiones).
- Spread Panamá soberano vs UST (impacto en valor de bonos panameños en cartera).
- Tasa pasiva local Panamá (depósitos a término — no hay BC propio, sigue tasas USD).

**Mecánica:**
- Sube SOFR 3M → activos a tasa variable repricean al alza inmediato; pasivos a término repricean al vencimiento → ventana de NIM positivo.
- Sube UST 5Y → libro de inversiones pierde valor (MTM); HTM se descuenta.
- Sube spread Panamá vs UST → bonos panameños en cartera pierden valor; nueva emisión Panamá soberana o corporativa local es más cara.

**Lectura que va al deck:**
- ¿Estamos en un régimen donde sube SOFR pero spread Panamá comprime? Beneficio neto a estimar.
- Repricing gap a 3, 6, 12 meses (cualitativo sin datos internos).

---

### 3) Mercantil Seguros

**Drivers principales:**
- UST 5–10Y (portafolio de inversiones de reservas técnicas).
- EM USD IG (proxy para parte del portafolio si tiene bonos LatAm USD).
- FX VES/USD (para reservas en bolívares).
- Duración del pasivo (reservas técnicas) vs duración del activo (portafolio).

**Mecánica:**
- Sube UST → activos pierden valor (MTM); a vencimiento se reinvierte a yield mayor. Si duración activo > duración pasivo → pérdida neta de capital económico.
- Régimen prolongado de tasas altas → mayor yield esperado, favorable para el negocio de largo plazo.

**Lectura que va al deck:**
- Estimación de cambio de valor del portafolio dado el delta del mes en UST 5Y/10Y, asumiendo duración X (Y, Z) — sensibilidad.

---

### 4) Wealth Management / Casa de Bolsa

**Drivers principales:**
- Curva UST entera (para asignación de duración).
- EMBI / CEMBI (oportunidades en EM USD).
- Spreads ICE BofA por rating (atractivo IG vs HY).
- SOFR forward path (oportunidad de instrumentos a tasa variable).

**Mecánica:**
- Define la recomendación de portafolio a clientes (duración, mix IG/HY, peso EM).

**Lectura que va al deck:**
- Atractivo relativo del momento por segmento de cliente (conservador / moderado / agresivo).
- Cambio de recomendación vs mes anterior y justificación.

---

### 5) Tesorería / Posición propia del grupo

**Drivers principales:**
- Fed Funds path (decisión de mantener / hedgear).
- SOFR curve (book de hedges).
- Spreads USD vs locales.
- Cross-currency (si hay funding multi-jurisdicción).

**Mecánica:**
- Si modelo Mercantil discrepa de mercado en path Fed → señal para ajustar hedge book.

**Lectura que va al deck:**
- Una frase: "Modelo Mercantil dice X; mercado dice Y; nuestra posición consistente con Z".

---

## Calendario relevante por unidad

Para el deck conviene tener visible el calendario relevante:

- **FOMC** — afecta a todas las unidades USD.
- **BCE / BoE** — afecta WM/CB y portafolios EUR/GBP.
- **BCV** — afecta Banco Vzla y Aseguradora.
- **SEP de la Fed (4 al año)** — refresco del dot plot.
- **Pago de cupones de bonos Panamá soberano y bonos del Tesoro/VCN locales** — afecta liquidez local.

## Pendientes para validar con Andrés/Camilo

1. ¿Lista completa de unidades del grupo a cubrir? ¿Falta alguna?
2. ¿Hay alguna unidad cuyo nombre/marca difiera de lo que pusimos arriba?
3. Para cada unidad, ¿quién es el referente operativo que firma la "lectura" de impactos cada mes? (CFO de banco PA, CIO de seguros, etc.)
4. ¿Cuándo se autoriza cargar datos internos del libro y cómo?
5. Tono editorial: ¿el deck llama a las unidades por su marca comercial o por código interno?
