# Cortes — estructura

Un subfolder por corte mensual. Convención: `YYYY-MM` (año-mes del cierre).

## Cada corte muestra una ventana de 12 meses corridos

El informe del mes `YYYY-MM` (cierre = último día hábil del mes) muestra:

- **YTD corrido**: 01-ene-YYYY → `as_of_date`.
- **Últimos 12 meses corridos**: (`as_of_date` − 12 meses) → `as_of_date`. Esta es la
  ventana primaria de los gráficos de series temporales.
- **Comparación principal**: vs cierre del mes anterior y vs 31-dic-(YYYY-1).

Esto aplica a todos los cortes — incluido los de backfill. Por ejemplo, el corte
de **enero 2026** muestra gráficos con datos diarios de enero 2025 a enero 2026.
Por eso el pipeline de datos arranca mucho antes que el primer corte publicable
(ver `01_PLAN_Y_FASES.md` § Backfill de datos para el modelo).

## Lifecycle de un corte

```
EN_BACKFILL → EN_CURSO → FIRMADO (inmutable, salvo erratum)
```

- **EN_BACKFILL**: lo construimos retroactivamente para 2026-01 a 2026-04.
- **EN_CURSO**: corte del mes vigente, sigue cambiando.
- **FIRMADO**: Andrés firma, queda inmutable.

## Estructura interna de un corte

```
cortes/YYYY-MM/
├── input/                                  ← lo que sube el analista
│   └── BloombergTemplate_TasasMercantil_<YYYY-MM>.xlsx
├── derived/                                ← calculado por el pipeline
│   ├── deltas.parquet
│   ├── implied_path.parquet
│   ├── fedwatch.parquet
│   ├── modelo_mercantil.parquet
│   └── spreads_corp.parquet
├── narrativa/
│   ├── mensajes_clave.yaml                 ← bullets por lámina
│   └── notas_sesion.md                     ← lo conversado con Claude
├── output/
│   ├── TasasMercantil_<YYYY-MM>.pdf
│   ├── index.html
│   └── figs/*.png
├── cierre.md                               ← obligatorio (ver 05_MEMORIA_DE_SESIONES.md)
└── erratum_*.md                            ← si aplica
```

## `mensajes_clave.yaml` — formato

```yaml
report_month: 2026-05
fase_1_usa:
  lamina_3_politica_y_mercado:
    - autor: claude
      bullet: "Fed mantiene tasa en 4.75–5.00%; SOFR 3M cerró en 4.62%."
    - autor: camilo
      bullet: "Repricing en libros a tasa variable se acelera; impacto neutro en NIM."
  lamina_4_curva_ust:
    - ...
fase_5_venezuela:
  lamina_11:
    - ...
corp:
  lamina_9:
    - ...
```

## ¿Qué archivos van a git y cuáles no?

- ✅ van: `input/`, `narrativa/`, `cierre.md`, `output/*.pdf`, `output/*.html`,
  `output/figs/*.png`.
- ⚠️ con cuidado: `derived/*.parquet` (regenerable; lo mantenemos para
  reproducir el corte exacto sin re-correr Bloomberg).
- ❌ no: nada que contenga datos internos del libro del banco (cuando esos datos
  se incorporen, irán a un repo separado con acceso restringido — ver
  `00_PERMISOS_Y_ALCANCE.md`).

## Cortes planeados

| Carpeta | Tipo | Status | Notas |
|---|---|---|---|
| `2026-01/` | backfill | pendiente | construir tras finalizar pipeline base |
| `2026-02/` | backfill | pendiente | |
| `2026-03/` | backfill | pendiente | |
| `2026-04/` | backfill | pendiente | |
| `2026-05/` | en vivo | próximo | primer corte real |
