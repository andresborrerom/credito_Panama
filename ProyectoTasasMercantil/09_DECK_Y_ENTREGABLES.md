# 09 · Deck y entregables

## Lo que producimos cada mes

| Entregable | Formato | Destino |
|---|---|---|
| Deck ejecutivo | PDF (16:9) | Correo a directivos |
| Sitio interactivo | HTML estático con gráficos Plotly | GitHub Pages privado |
| Plantilla Bloomberg con valores | XLSX | archivo en repo (`cortes/YYYY-MM/input/`) |
| Cierre del corte | Markdown | repo + lectura del próximo mes |

El **deck** es el entregable canónico. El HTML es el "estudio detrás del deck"
para quien quiera profundizar.

## Estructura del deck (Fase 1 completa + esbozos 2–5 + corporativas)

| # | Lámina | Tiempo de lectura |
|---|---|---|
| 1 | Portada — `Reporte de Tasas · MM YYYY · Mercantil SFI` | — |
| 2 | Mensajes clave del mes (3–5 bullets) | 30s |
| 3 | **Fase 1 USA** — Política monetaria + mercado: Fed Funds, IORB, SOFR, UST 2/5/10 | 60s |
| 4 | **Fase 1 USA** — Curva UST: cierre año anterior + mes anterior + mes en curso | 60s |
| 5 | **Fase 1 USA** — Tres lecturas de expectativas Fed (implied / FedWatch / modelo Mercantil) | 90s |
| 6 | **Fase 1 USA** — Lectura e implicaciones | 60s |
| 7 | **Fase 2 Global** — Tasas política + curvas 10Y + FX | 60s |
| 8 | **Fase 3 Panamá** — Curva soberana + spread vs UST + corporativos locales | 60s |
| 9 | **Capítulo Corporativas** — Tabla regiones × ratings × plazos | 90s |
| 10 | **Fase 4 Mercantil** — Impactos por unidad (cualitativo inicialmente) | 90s |
| 11 | **Fase 5 Venezuela** — BCV + FX oficial vs paralelo + brecha | 60s |
| 12 | Calendario del próximo mes (FOMC, BCE, CPI, etc.) | 30s |
| 13 | Apéndice / Disclaimers | — |

≈ 12 minutos de lectura completa. Cada lámina lleva: título → gráfico/tabla
principal → 1 bullet de conclusión.

## Reglas gráficas

- **1 idea = 1 lámina.** Si una lámina tiene dos mensajes, partirla en dos.
- **Color institucional:** paleta Mercantil SFI (Andrés provee).
- **Tipografía:** una sola familia (a definir cuando llegue la guía).
- **Anotaciones sobre datos:** sí (deltas mes anterior arriba de la barra/punto).
- **Footnote por lámina** con fuente y fecha del dato.
- **Sin logotipos de terceros** en las láminas (Bloomberg/FRED van en disclaimers).

## Renderer

Stack propuesto:
- **Gráficos**: Plotly (consistente con lo existente en `credito_Panama`).
- **HTML**: Plotly + plantilla Jinja → estático.
- **PDF**: dos opciones según necesidad:
  - **WeasyPrint** sobre el HTML del deck (más rápido, menos control fino).
  - **python-pptx** → PPT → export PDF (más control, slower).
  - Decisión: WeasyPrint primero; si las directivas piden PPT editable, mover a python-pptx.

## Naming convention

- Deck PDF: `TasasMercantil_<YYYY-MM>.pdf`
- HTML: `cortes/<YYYY-MM>/output/index.html` (servido desde `/cortes/<YYYY-MM>/` en GH Pages)
- Figuras: `cortes/<YYYY-MM>/output/figs/<lamina>_<id>.png`
- Versión ejecutiva (para externos, sin Fase 4 Mercantil): `TasasMercantil_<YYYY-MM>_external.pdf`
  → este se decide caso por caso si se distribuye fuera.

## Sitio HTML interactivo

- Lista navegable de cortes en el índice: `cortes/index.html` (auto-generado).
- Por corte:
  - Misma narrativa del deck.
  - Gráficos Plotly con tooltip, zoom y leyenda interactiva.
  - **Tabla pivot** del capítulo corporativas.
  - Botones de "ver datos de origen" → exportar CSV.
- `<meta name="robots" content="noindex">` en cada página.

## GitHub Pages privado

- Setting: **Settings → Pages → Visibility: Private** (requiere plan org).
- Allowlist gestionada por Andrés.
- Si la cuenta no soporta Pages privado, fallback: hospedar en un subdominio
  detrás de Cloudflare Access con allowlist de correos. Decisión a tomar cuando
  arme el primer release.

## Manejo de versiones del deck

- Una vez firmado, el PDF de un corte es inmutable. Si se descubre error,
  publicamos `TasasMercantil_<YYYY-MM>_corrected_<YYYY-MM-DD>.pdf` + `erratum.md`.
- Los analistas y la gente que recibe el correo necesita saber que el corte
  original quedó marcado como obsoleto: el correo de corrección lo dice y el
  HTML privado muestra banner.

## Vista externa (para empresas del grupo)

Según conversación de arranque, las "empresas" son las propias unidades del
grupo Mercantil (Banco VE, Banco PA, Aseguradora, WM, etc.), por lo tanto la
vista externa es **el mismo deck** distribuido por canal interno del grupo. No
hay un PDF "comercial neutro" aparte por ahora.

Si en el futuro se decide distribuir a clientes finales del grupo, partimos del
deck y removemos la lámina 10 (Fase 4 Mercantil — Impactos) que es interna.
