# Estudio de Renta Fija de Panamá — Latinex

> **Niveles actuales vs historia** por plazo, sector, tipo de instrumento y proxy de crédito.
> Base de datos completa + sitio interactivo mobile-friendly + PDF descargable.

**🌐 Sitio publicado (GitHub Pages):** se activa al hacer push a `main` o a esta rama.
La URL será `https://andresborrerom.github.io/credito_Panama/` una vez habilitado Pages
en *Settings → Pages → Source: GitHub Actions*.

**🛠 Herramienta interactiva (Streamlit Cloud):** entra a [share.streamlit.io](https://share.streamlit.io)
con tu cuenta de GitHub → **New app** → repo `andresborrerom/credito_Panama` → branch
`claude/pensive-carson-shPap` (o `main` después del merge) → archivo `src/app/streamlit_app.py` → Deploy.
La URL quedará tipo `https://<algo>.streamlit.app` y es accesible desde cualquier dispositivo,
sin instalación, con todos los filtros cruzados (rating, sector, plazo, emisor, período) en tiempo real.

**📄 Entregables:**
- `docs/index.html` — herramienta interactiva (sitio estático, Plotly)
- `docs/estudio_renta_fija_panama.pdf` — reporte ejecutivo
- `data/panama_fixed_income.sqlite` — base completa (8 tablas)
- `data/processed/*.parquet` — formato analítico
- `src/app/streamlit_app.py` — herramienta interactiva con filtros completos (local)

**🧮 Calculadora (nueva pestaña Streamlit):**
Para un instrumento hipotético (rating, plazo, monto, instrumento, sector), muestra en paralelo:
1. **Diferencial de yield** (spread mediano observado en trades del mismo bucket).
2. **Diferencial de crédito por rating** (curva de spread por tier en el bucket).
3. **Adecuación de capital** (RWA, capital requerido, con RW por Acuerdo 3-2016 SBP).
4. **Provisión esperada** (EL = PD × LGD × EAD, con horizonte al plazo elegido).

Incluye resumen integrado (margen neto = yield − provisión − costo de capital),
procedencia expandible de PD/LGD/RW, y sub-vista de sensibilidad con sliders
para PD/LGD/RW y heatmap de EL sobre grid.

Motores nuevos:
- `src/analytics/provisiones.py` — tablas PD_BY_TIER, LGD_BY_INSTRUMENT ancladas
  en Basilea III Foundation IRB con procedencia explícita; función `expected_loss`.
- `src/analytics/capital.py` — tabla RISK_WEIGHTS_SBP (Acuerdo 3-2016 + BCBS 2017)
  para SOVEREIGN_PAN / BANK / CORPORATE / MORTGAGE_BACKED / SUBORDINATED / AT1
  por tier; funciones `rwa`, `capital_requirement`, `capital_for_position`.
- `src/analytics/credit_adjustments.py` — ajuste de LGD por garantías (corp
  auditada / personal / cash collateral) siguiendo BCBS CRE22, y multiplicador
  de PD por señales cualitativas del rating report (FCO cover, D/EBITDA,
  concentración ingresos, opacidad EEFF, SPV rollover, exposición spot).
- `src/analytics/concentration.py` — recargo Pillar 2 SBP por concentración
  individual, de grupo económico y sectorial (composición multiplicativa).
- Tests: 131 nuevos, todos verdes.

**Caso trabajado: MASPV Serie B (BBB-.pa, 10.25% × 18m).**
Aparece como preset en la Calculadora. Veredicto con la herramienta:
- Escenario base (rating externo tal cual): margen neto anualizado **8.84%**.
- Escenario con ajustes completos (5 señales cualitativas + garantías
  inadmisibles + concentración): margen neto **7.07%** anualizado.
- **Supera el yield risk-free (Tesoro Panamá 1.5y ~5%) por 200 bp incluso ajustado.**
- Si Tesorería rechaza SOLO por adecuación de capital + provisión regulatoria,
  probablemente exagera: el spread positivo compensa todos los ajustes cuantificables.
- Razones LEGÍTIMAS que Tesorería podría estar considerando y que NO son
  puramente "capital/provisión": conflicto de interés (Mercantil IB es
  structurer + Mercantil Tesorería compra el mismo bono), limites internos
  no expuestos, apetito estratégico por energía renovable LatAm.

---

## 1. Lo que la base de datos cubre

| Tabla | Filas | Contenido |
|---|---:|---|
| `instruments` | 2,573 | Universo de emisiones vigentes (ISIN, nemotécnico, emisor, sector, instrumento, base, emisión, vencimiento, frecuencia, **cupón**, tipo tasa, monto serie/colocado) |
| `trades` | 84,191 | Tape de operaciones 10 años con **YTM calculado** trade por trade (18,210 con YTM válido), plazo residual, bucket, sector enriquecido, proxy de crédito |
| `curves_monthly` | 1,734 | Yields mediana / p25 / p75 por (mes × sector × bucket × instrumento) |
| `sector_monthly` | 588 | Mediana de yield por (mes × sector) |
| `volumen_emisor` | 6 | Volumen anual primario/secundario/recompras |
| `quotes_live` | 10 | Ofertas vivas (bid/ask, snapshot) |
| `hechos_relevantes` | 8,783 | Eventos corporativos |
| `ust_yields` | 2,849 | US Treasury daily yield curve (2015 → 2026) |

Cobertura temporal: **2019-01 a 2026-05**.

## 2. Hallazgos automáticos del corte actual

Generados desde la base. La página `index.html` y el PDF los muestran al tope.

- **Pendiente Tesoro Panamá:** curva empinada en ~105 pb entre 0-3y (4.70%) y 7y+ (5.75%).
- **Prima VCN sobre Letras del Tesoro (0-1y):** 69 pb (VCN 5.37% vs Letras 4.68%).
- **Bonos Hipotecarios:** yield mediano 8.33%, prima ~313 pb sobre Tesoro Panamá.
- **Spread Panamá 10y vs UST 10y:** 135 pb hoy vs mediana histórica 240 pb → **COMPRIMIDO** vs media 5y.
- **Más barato vs historia 5y:** Notas Corporativas 0-1y en percentil 95 (8.91% vs mediana 6.26%).
- **Más caro vs historia 5y:** Notas del Tesoro 3-5y en percentil 5 (5.25% vs mediana 6.90%).

Cada hallazgo es reproducible aplicando los filtros equivalentes en la herramienta.

## 3. Cómo se construyó

### Fuentes
- **Latinex** — API JSON pública (no documentada). Reverse-engineered del bundle JS del sitio. Base: `https://www.latinexbolsa.com`. Endpoints clave: `/emisor/emisiones/activas/all`, `/emisor/transacciones/mercado?rango=10Y`, `/emisor/detalle/instrumento/*`. Sin auth, sin rate-limit detectado.
- **US Treasury** — feed XML público (sin key) en `home.treasury.gov` para curva UST diaria.

### Cálculo de YTM
Para cada trade de bono fija con info completa, se reconstruyen los flujos hasta vencimiento (cupón × frecuencia + amortización bullet) y se resuelve por **bisección** la tasa que iguala el VP de flujos al precio limpio negociado.

Bases soportadas: 30/360, ACT/360, 365/360, ACT/365, ACT/ACT.

### Proxy de crédito (limitación declarada)
Sin feed pago de calificaciones, se construye un proxy por sector + tipo de instrumento (`AAA-PAN-Sov`, `BBB-Bank`, `BBB-Corp`, `BB-Corp`, `BB-RealEstate`). El **spread negociado vs Tesoro mismo bucket** funciona como medida *revealed-market* del riesgo crediticio.

### Sobre la ventana de 10 años
La profundidad por bucket **no se pierde al ampliar la ventana** — lo que cambia es la *densidad de trades* por año. Antes de 2020, los bonos hipotecarios y notas corporativas tenían menos liquidez registrada. Por eso:
- Curvas **actuales** = últimos 90 días.
- Series temporales agregadas a **trimestral** (con mínimo 3 trades por celda) para suavizar.
- Percentiles históricos sobre **5 años** (1,825 días) para tener n estadísticamente válido.

## 4. Cómo correrlo

```bash
# Instalar deps
pip install -r requirements.txt   # o pip install -e .

# Pipeline completo (≈2 min)
./scripts/run_all.sh

# Equivale a:
python -m src.etl.extract        # baja raw JSON de Latinex + UST
python -m src.etl.transform      # normaliza, calcula YTM, escribe DB
python -m src.app.build_site     # genera docs/ (HTML estático para GH Pages)
python -m src.app.build_pdf      # genera docs/estudio_renta_fija_panama.pdf

# Herramienta interactiva con filtros completos:
streamlit run src/app/streamlit_app.py
```

## 5. Estructura del repo

```
credito_Panama/
├── README.md
├── pyproject.toml
├── data/
│   ├── raw/                   ← JSON crudos descargados
│   ├── processed/             ← parquet limpios
│   └── panama_fixed_income.sqlite
├── src/
│   ├── etl/
│   │   ├── endpoints.py       ← catálogo de URLs de Latinex
│   │   ├── extract.py         ← descarga + reintentos
│   │   └── transform.py       ← normaliza, calcula YTM, escribe DB
│   ├── analytics/
│   │   ├── ytm.py             ← bisección + flujos
│   │   └── curves.py          ← queries DuckDB
│   └── app/
│       ├── build_site.py      ← genera docs/ (GH Pages)
│       ├── build_pdf.py       ← genera PDF + HTML imprimible
│       └── streamlit_app.py   ← herramienta interactiva local
├── docs/                      ← sitio publicable
│   ├── index.html
│   ├── curvas.html
│   ├── historia.html
│   ├── universo.html
│   ├── metodologia.html
│   ├── estudio_renta_fija_panama.pdf
│   └── figs_pdf/
├── scripts/run_all.sh
└── .github/workflows/pages.yml ← deploy automático a GH Pages
```

## 6. Habilitar GitHub Pages (una sola vez)

Settings → Pages → Source: **GitHub Actions**. El workflow `.github/workflows/pages.yml` ya está incluido y se dispara en cada push que toque `docs/`.

## 7. Próximos pasos sugeridos

### Bloomberg query — para ejecutar mañana cuando tengas terminal disponible

Copia/pega este pedazo en Bloomberg (BFLD `<GO>` para BSRCH + screen, o vía API):

```
# 1) Lista de bonos panameños (universo a contrastar)
SRCH <GO>
  Country/Region of Risk: Panama
  Security Type: Govt + Corp Bonds
  Amount Outstanding > 1MM USD
  Maturity > today

# 2) Export con campos:
CUSIP, ISIN, ISSUER_NAME, COUPON, MATURITY, AMT_OUTSTANDING,
ISSUER_INDUSTRY_SECTOR, BB_COMPOSITE, RTG_FITCH, RTG_MOODY, RTG_SP,
YLD_YTM_MID, PX_LAST, Z_SPRD_MID, ASW_SPREAD,
GOVT_BENCHMARK_YLD, OAS_SPREAD_BID

# 3) Para curva soberana Panamá:
GOVT C20 <GO>  → exportar PANAMA SOVEREIGN CURVE (PANG) histórica
              o ticker: GTPAB10Y Govt para benchmark 10y

# 4) Bulk via Excel API (=BDP / =BDS):
=BDS("PANG Curncy", "CURVE_TENOR_RATES")
=BDP("PANAMA 6.7 01/26/36 Govt", "YLD_YTM_MID")
```

Cuando tengas el archivo, lo cargo a `data/raw/bloomberg_*.csv` y enriquezco la tabla `instruments` con `ISIN ↔ rating + Z-spread`, lo que nos permite cambiar el proxy de crédito por ratings reales.

### Otras mejoras pendientes
- Scraping de calificaciones de Equilibrium / PCR / Fitch Centroamérica (públicas pero detrás de PDF).
- Endpoint `/emisor/detalle/instrumento/pago` para detectar bonos con call/put → ajustar tratamiento bullet.
- Bonos a tasa variable: análisis separado con curva de la referencia (LIBOR/SOFR/PRIME) implícita.
- Bid/ask snapshot diario → calidad de mercado y liquidez por instrumento.

---

**Datos:** [latinexbolsa.com](https://www.latinexbolsa.com) (API JSON pública) · [home.treasury.gov](https://home.treasury.gov) (UST daily curve).
**Estudio informativo. No constituye recomendación de inversión.**
