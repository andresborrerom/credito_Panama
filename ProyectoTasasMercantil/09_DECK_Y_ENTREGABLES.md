# 09 · Deck y entregables

> Spec actualizada al **deck v1.0** según `13b_BENCHMARK_REPORTES.md` (9 láminas, modelo Apollo+PIMCO+BlackRock).

## Lo que producimos cada mes

| Entregable | Formato | Destino |
|---|---|---|
| Deck ejecutivo (interno grupo) | PDF 16:9, 9 láminas, ≤5 MB | Correo a directivos |
| Sitio interactivo | HTML estático con Plotly + apéndice de tablas | GitHub Pages privado |
| Plantilla Bloomberg con valores | XLSX | archivo en repo (`cortes/YYYY-MM/input/`) |
| Cierre del corte | Markdown | repo + lectura del próximo mes |

El **deck interno** es el entregable canónico. El HTML es el apéndice para
quien quiera profundizar — tablas, series, descargas CSV.

## Decisiones de voz, conviction y forks

1. **Voz: primera persona del plural del grupo** — "creemos que…",
   "vigilamos…", "rotamos…". Camilo + Andrés son los dueños editoriales del
   reporte. Tercera persona neutral ("el mercado descuenta…") solo para
   data factual.
2. **Conviction tags obligatorios** en cada vista táctica y en cada mensaje del TL;DR:
   `Alta` / `Media` / `Baja`. Esto distingue opinión calibrada de
   recomendación y protege parcialmente del riesgo regulatorio.
3. **Fork "Wealth Management" — en roadmap, no en v1.0**. Cuando se decida
   distribuir externamente a clientes, no basta suavizar la voz: hay que
   **filtrar toda la estrategia del grupo** (lámina 8 Impacto Mercantil
   completa, conviction Alta que pueda interpretarse como recomendación a
   un cliente específico, mención a posición propia/tesorería). Son
   prácticamente dos documentos distintos con el mismo dataset.

## Estructura del deck v1.0 — 9 láminas

| # | Título | 4Ws entregados (mínimo 2 por lámina) |
|---|---|---|
| 1 | **TL;DR · 3 mensajes del mes + conviction tags** | WHAT (todos) |
| 2 | **Tactical View Table** | WHAT + TRIGGER |
| 3 | **Fed + curva UST** (dot plot vs OIS implícito + sweet spot) | WHAT IF RIGHT |
| 4 | **Spreads corporativos IG/HY + EMBI** | WHAT IF WRONG (widening +50 bps) |
| 5 | **Global** — BCE/BoE + DXY | TRIGGER (próxima reunión) |
| 6 | **Panamá** soberana + corporativos locales | WHAT IF RIGHT/WRONG por tesorería PA |
| 7 | **Venezuela** — BCV vs paralelo + bonos | TRIGGER (eventos políticos/sanciones) |
| 8 | **Impacto Grupo Mercantil** por unidad | WHAT IF RIGHT + WHAT IF WRONG por unidad |
| 9 | **Calendario + qué nos haría cambiar de opinión** | TRIGGER explícito |

**Vs borrador inicial de 13 láminas**: eliminadas portada (mata el TL;DR),
apéndice descriptivo (vive como HTML); fusionadas mensajes clave + lectura
(→ lámina 1), tres lecturas Fed dentro de Fed+curva (→ lámina 3). 30%
menos volumen, 100% del valor accionable preservado.

## Patrones obligatorios (de `13b_BENCHMARK_REPORTES.md`)

1. **Una idea por lámina.** Si no tiene una frase que empiece "creemos que…", se borra o se fusiona.
2. **Sweet spot explícito** con nivel/target ("2-5Y UST target 4.20-4.50%"), no vaguedades como "favorecemos duración".
3. **Definición operativa antes de la opinión** ("definimos shock al spread como ampliación >50 bps en 30 días").
4. **Trigger calendar al inicio** (lámina 1-2), no al final.
5. **Conviction Alta/Media/Baja** explícito en cada vista táctica y en cada bullet del TL;DR.

## Anti-patrones prohibidos

1. **Apéndice descriptivo** sin lectura (típico LatAm). Vive como HTML, no en el PDF.
2. **"Por un lado / por otro lado"** sin cerrar. Balanceo institucional = ruido.
3. **Recapitular noticias** del mes. El directivo ya las leyó en Bloomberg.
4. **Portada decorativa** que ocupa lámina entera.
5. **Más de 2 tipografías o 4 colores** institucionales. Plantilla genérica = pérdida de credibilidad antes del primer dato.

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
