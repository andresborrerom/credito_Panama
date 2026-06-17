# 04 · Playbook mensual

Receta paso a paso para producir un corte mensual una vez el pipeline está
construido. Sirve para sesiones recurrentes desde el corte 2026-05 en adelante
(2026-01 a 2026-04 son backfill, con su propio flujo).

## Timeline estándar de un corte

Sea **M** el mes a reportar y **T0** = último día hábil del mes M.

| Día | Hora | Quién | Acción |
|---|---|---|---|
| T0 | EOD | Analista | Recibe la plantilla Bloomberg con `as_of_date = T0` ya seteada; corre `=BDP` y guarda valores |
| T0+1 | mañana | Analista | Envía el `.xlsx` por correo o lo sube a `cortes/YYYY-MM/input/` |
| T0+1 | mañana | Pipeline automático | Scraper BCV + paralelo Venezuela + FRED de respaldo corren solos en CI |
| T0+1 | tarde | Andrés + Camilo + Claude | Sesión 1: revisión de datos, narrativa preliminar |
| T0+2 | mañana | Claude | Genera deck draft + HTML draft |
| T0+2 | tarde | Andrés + Camilo + Claude | Sesión 2: ajuste de mensajes, lectura final |
| T0+3 | mañana | Andrés | Firma el corte (status → FIRMADO) |
| T0+3 | tarde | Distribución | Correo + GH Pages privado actualizado |

## Cómo arrancar la sesión 1 del mes (la línea exacta)

Abrir una sesión nueva en este repo y mandar:

```
Lee:
- ProyectoTasasMercantil/README.md
- ProyectoTasasMercantil/04_PLAYBOOK_MENSUAL.md
- ProyectoTasasMercantil/05_MEMORIA_DE_SESIONES.md
- ProyectoTasasMercantil/cortes/<MES_ANTERIOR>/cierre.md
- ProyectoTasasMercantil/cortes/<MES_ANTERIOR-1>/cierre.md  (opcional, contexto extra)

Vamos a armar el corte <YYYY-MM>. El analista ya subió input/.
Empezá por:
1. Validar que el input está completo (todos los campos clave presentes y dentro de rangos sanos).
2. Cargar los datos a la base.
3. Mostrame el resumen de movimientos del mes que tenés (top 5 deltas relevantes vs mes anterior).
```

Esto es **suficiente** para que Claude retome el hilo. El `cierre.md` del mes
anterior tiene "qué quedó pendiente" y "qué hay que observar este mes".

## Pasos en detalle

### Paso 1 — Validar input

```bash
python -m src.tasas_mercantil.validate \
    --input cortes/2026-05/input/BloombergTemplate_TasasMercantil_2026-05.xlsx \
    --as-of 2026-05-29
```

Chequeos automáticos:
- Todos los `instrument` esperados presentes.
- `value` dentro de rangos razonables (Fed Funds entre 0% y 10%, etc.).
- `as_of_date` en todas las filas = `T0` esperado.
- No hay `#N/A` ni vacíos en celdas críticas.

Si falla, paramos y notificamos al analista.

### Paso 2 — Cargar a la base

```bash
python -m src.tasas_mercantil.ingest \
    --corte 2026-05 \
    --bloomberg cortes/2026-05/input/BloombergTemplate_TasasMercantil_2026-05.xlsx
```

Idempotente. Detecta corte previo y respeta inmutabilidad.

### Paso 3 — Scrapers públicos (autom. en CI pero correr manual si falla)

```bash
python -m src.tasas_mercantil.scrape_bcv --as-of 2026-05-29
python -m src.tasas_mercantil.scrape_paralelo --as-of 2026-05-29 --avg
python -m src.tasas_mercantil.scrape_fred --as-of 2026-05-29 --crosscheck
```

### Paso 4 — Recalcular derivadas

```bash
python -m src.tasas_mercantil.derive --corte 2026-05
```

Calcula:
- Deltas (mes ant., 12M, vs cierre año anterior).
- Pendientes de curva (2s10s, 3m10y).
- Implied path SOFR.
- Probabilidades FedWatch por reunión.
- Predicción del modelo Mercantil (ver `07_MODELO_PREDICTIVO.md`).
- Percentiles 5Y de spreads.

### Paso 5 — Sesión narrativa con Claude

Discutimos los movimientos, redactamos los `report_messages` por lámina.
Claude propone el primer borrador siguiendo el patrón de `05_MEMORIA_DE_SESIONES.md`.
Iteramos.

### Paso 6 — Render

```bash
python -m src.tasas_mercantil.render \
    --corte 2026-05 \
    --output-deck cortes/2026-05/output/TasasMercantil_2026-05.pdf \
    --output-html cortes/2026-05/output/index.html
```

Render usa Plotly + WeasyPrint para PDF, Plotly + HTML estándar para el sitio.
Reaprovecha `src/app/build_pdf.py` cuando se pueda.

### Paso 7 — Cerrar el corte

1. Andrés revisa, marca `cortes.status = FIRMADO` en la base.
2. Claude actualiza `cortes/2026-05/cierre.md` con:
   - Resumen ejecutivo de 3 bullets.
   - Qué quedó pendiente.
   - Qué hay que observar el próximo mes.
3. Commit con mensaje: `corte(2026-05): firma final + cierre`.
4. Push a `claude/tasas-mercantil-report-Q8sFt`.

## Cuándo NO seguir este playbook

- **Mes con cambio de política Fed importante (cut/hike sorpresa):** sesión 1 se
  hace el mismo día del cambio, no esperar T0.
- **Devaluación de bolívar > 10% en el mes o intervención BCV:** lámina Venezuela
  se trabaja específicamente.
- **Mes con publicación del dot plot SEP:** lámina extra dedicada al cambio en el dot.

## Estructura de un corte

```
cortes/2026-05/
├── input/                                  ← lo que sube el analista
│   └── BloombergTemplate_TasasMercantil_2026-05.xlsx
├── derived/                                ← resultado del paso 4
│   ├── deltas.parquet
│   ├── implied_path.parquet
│   ├── fedwatch.parquet
│   └── modelo_mercantil.parquet
├── narrativa/
│   ├── mensajes_clave.yaml                 ← report_messages del mes
│   └── notas_sesion.md                     ← lo conversado en la sesión 1/2
├── output/
│   ├── TasasMercantil_2026-05.pdf
│   ├── index.html
│   └── figs/*.png
├── cierre.md                               ← lo que el próximo mes debe leer
└── erratum_*.md                            ← solo si aplica
```

Detalle de cada archivo en `cortes/README.md`.
