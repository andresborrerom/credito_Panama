# 10 · Modelo predictivo — arquitectura

Documento equivalente a `saa-architecture.md` del proyecto hermano. Captura el
stack, la estructura de carpetas, las configuraciones, las dependencias y el
plan de fases del modelo predictivo de tasas Mercantil.

## Stack Python

| Área | Librería | Por qué |
|---|---|---|
| Datos | `pandas`, `numpy` | base |
| FRED ALFRED (vintage) | `fredapi` o REST directo | series macro point-in-time |
| Bloomberg histórico | parsing de xlsx del analista | tasas, swaps, TIPS, breakevens, SR3 futures |
| Estadística | `scipy`, `statsmodels` | Taylor rule, regresiones, tests |
| Bayesiana | `pymc` | Pieza B con priors informados (opcional, segunda iteración) |
| Backtest | implementación propia | walk-forward estricto, bootstrap |
| Config | `pydantic` + YAML | catálogo de instrumentos, features, pesos congelados |
| Testing | `pytest`, `hypothesis` | invariantes (sin look-ahead, calibración) |
| Reportes (bitácora del modelo) | `quarto` | book HTML privado + PDF |
| Gráficos del deck | `plotly` | consistente con `credito_Panama` ya existente |
| Linting / tipos | `ruff`, `mypy` | calidad |

## Estructura de carpetas

```
credito_panama/
├── ProyectoTasasMercantil/           ← documentos vivos del proyecto (este árbol)
├── src/tasas_mercantil/              ← código ejecutable (a construir)
│   ├── __init__.py
│   ├── configs/
│   │   ├── modelo.yaml               ← ventanas, pesos congelados, lista de rivales
│   │   ├── features.yaml             ← qué features, desde cuándo, fuente
│   │   ├── instrumentos.yaml         ← catálogo de tickers (refleja la plantilla BBG)
│   │   └── horizons.yaml             ← {1M, 3M, 6M, 12M}
│   ├── data/
│   │   ├── ingest_bloomberg.py       ← parsea xlsx del analista hacia parquet
│   │   ├── ingest_fred.py            ← ALFRED vintage via REST
│   │   ├── ingest_cme.py             ← SR3 settlements diarios
│   │   ├── ingest_scrapers.py        ← BCV y bolívar paralelo
│   │   ├── snapshot.py               ← API point-in-time (no look-ahead)
│   │   └── validate.py               ← chequeo del xlsx recibido
│   ├── modelo/
│   │   ├── pieces/
│   │   │   ├── implied_path.py       ← Pieza A: implied path SOFR + risk premium
│   │   │   ├── reaction_fn.py        ← Pieza B: Taylor rule bayesiana
│   │   │   ├── ad_hoc.py             ← Pieza C: hipótesis editoriales
│   │   │   └── term_premium.py       ← Pieza D: decomp UST = real + BE + TP
│   │   ├── aggregate.py              ← combinación con pesos congelados
│   │   ├── persist.py                ← guarda con (version_id, snapshot_hash, sha)
│   │   └── interface.py              ← predict(as_of, horizon) → DataFrame
│   ├── rivales/
│   │   ├── rival_implied.py
│   │   ├── rival_fedwatch.py
│   │   ├── rival_taylor_naive.py
│   │   ├── rival_naive.py
│   │   └── rival_dotplot_median.py
│   ├── backtest/
│   │   ├── walk_forward.py           ← rolling 2010-presente
│   │   ├── metrics.py                ← MAE, RMSE, skill, hit rate, PIT, log-score
│   │   ├── bootstrap.py              ← block bootstrap 1000 réplicas
│   │   └── report.py                 ← tabla comparativa por régimen
│   ├── tests/
│   │   ├── test_no_lookahead.py      ← invariante crítico
│   │   ├── test_distribution_calibration.py
│   │   ├── test_aggregation.py
│   │   └── test_idempotency.py
│   ├── narrativa/
│   │   └── render_lamina_5.py        ← lámina del deck con las 3 lecturas
│   └── reportes/
│       ├── render_deck.py            ← PDF del corte mensual
│       └── render_html.py            ← HTML interactivo
├── data/external/tasas_mercantil/    ← parquet del modelo (no en git si pesa)
│   ├── vintage_macro.parquet
│   ├── yield_curve.parquet
│   ├── real_curve.parquet
│   ├── breakeven.parquet
│   ├── swap_curve.parquet
│   ├── sofr_futures.parquet
│   ├── fedwatch.parquet
│   ├── predictions/                  ← una predicción = 1 fila con (version_id, as_of)
│   │   └── predictions_v*.parquet
│   └── backtest/
│       └── results_v*.parquet
└── book/tasas_mercantil/             ← bitácora viva Quarto (a construir)
    ├── _quarto.yml
    ├── index.qmd
    ├── 00-estado.qmd
    ├── 01-alcance-modelo.qmd
    ├── 02-datos-y-vintage.qmd
    ├── 03-piezas-modelo.qmd
    ├── 04-rivales.qmd
    ├── 05-protocolo-backtest.qmd
    ├── 06-resultados-walk-forward.qmd
    ├── 07-calibracion-distribucional.qmd
    ├── 08-regimenes.qmd
    ├── 09-limites.qmd
    ├── 10-gobernanza.qmd
    └── referencias.bib
```

## Decisiones clave congeladas en YAML

Todo lo que cambia entre versiones de modelo (ventanas, pesos, lista de
rivales) vive en `configs/modelo.yaml`. **El código orquesta, el YAML define.**

Ejemplo `configs/modelo.yaml`:

```yaml
version: "0.1.0"

ventanas:
  brutos_desde: "1985-01-01"          # Volcker disinflation post-shock
  calibracion_hp: ["1995-01-01", "2009-12-31"]
  evaluacion_walk_forward_desde: "2010-01-01"
  evaluacion_modernos_desde: "2019-01-01"   # SOFR/SR3/FedWatch reales
  horizontes_meses: [1, 3, 6, 12]
  pre_target_explicito_hasta: "1994-01-31"  # se reporta separadamente

pesos_agregacion:
  w_a: 0.55
  w_b: 0.35
  w_c_max: 0.10
  # tras calibración M-6 estos se sobreescriben con los aprendidos

rivales:
  - rival_implied
  - rival_fedwatch
  - rival_taylor_naive
  - rival_naive
  - rival_dotplot_median

regimenes:
  # Pre-2010: in-training, reportados separadamente con caveat
  - {id: "volcker_disinflation",   from: "1985-01", to: "1987-08", evaluacion: "in_sample"}
  - {id: "greenspan_pre_target",   from: "1987-09", to: "1994-01", evaluacion: "in_sample"}
  - {id: "greenspan_post_target",  from: "1994-02", to: "2005-12", evaluacion: "in_sample"}
  - {id: "bernanke_pre_crisis",    from: "2006-01", to: "2007-12", evaluacion: "in_sample"}
  - {id: "crisis_early_qe",        from: "2008-01", to: "2009-12", evaluacion: "in_sample"}
  # Post-2010: walk-forward genuino
  - {id: "qe_zlb",                 from: "2010-01", to: "2013-04", evaluacion: "walk_forward"}
  - {id: "taper_tantrum",          from: "2013-05", to: "2014-12", evaluacion: "walk_forward"}
  - {id: "normalizacion_yellen",   from: "2015-01", to: "2018-09", evaluacion: "walk_forward"}
  - {id: "hike_powell",            from: "2018-10", to: "2019-06", evaluacion: "walk_forward"}
  - {id: "pivot_cuts",             from: "2019-07", to: "2020-02", evaluacion: "walk_forward"}
  - {id: "covid_zlb",              from: "2020-03", to: "2022-02", evaluacion: "walk_forward"}
  - {id: "hike_agresivo",          from: "2022-03", to: "2023-07", evaluacion: "walk_forward"}
  - {id: "hold",                   from: "2023-08", to: "2024-08", evaluacion: "walk_forward"}
  - {id: "cut_cycle",              from: "2024-09", to: "now",     evaluacion: "walk_forward"}

fail_loud:
  skill_min_rolling24m: 0.05          # vs rival_implied
  coverage_ic80_min: 0.70
  coverage_ic80_max: 0.90
  bias_max_bps_rolling12m: 15
```

## Plan de fases

| Fase | Sesiones | Entregable |
|---|---|---|
| Construcción | M-0 a M-7 | modelo 0.5.0 con backtest robusto |
| Promoción | M-8 a M-10 | modelo 1.0.0 firmado por Andrés |
| Operación recurrente | mensual desde corte 2026-05 | predicciones publicadas en deck + HTML |
| Refinamiento | trimestral | revisión de pesos, nuevos features, evaluación de drift |

## Dónde NO vive el modelo

- En las hojas del Excel del analista (eso es solo input).
- En `mercantil-planner` ni `mercantil-saa` (read-only).
- En `credito_panama/src/etl|analytics|app/` (el código del proyecto Panamá
  legacy se mantiene separado; sólo importamos lo que ya está y es estable).

## Dependencias entre componentes

```
plantilla_bloomberg.xlsx (analista)
        │
        ▼
src/tasas_mercantil/data/ingest_bloomberg.py
        │
        ▼ (junto a ingest_fred, ingest_cme, ingest_scrapers)
data/external/tasas_mercantil/*.parquet
        │
        ▼
src/tasas_mercantil/data/snapshot.py  (point-in-time)
        │
        ├──► src/tasas_mercantil/modelo/pieces/*
        │           │
        │           ▼
        │      modelo/aggregate.py  → modelo/persist.py
        │
        ├──► src/tasas_mercantil/rivales/*
        │
        └──► src/tasas_mercantil/backtest/walk_forward.py
                    │
                    ▼
            backtest/report.py  →  book/tasas_mercantil/06-resultados-walk-forward.qmd
```

## Notas de portabilidad

- Toda lógica vintage-aware se concentra en `data/snapshot.py`. Si algún día
  cambiamos de FRED ALFRED a Refinitiv DataStream vintage, solo ese módulo se
  toca.
- Los modelos rivales son archivos independientes. Agregar un rival nuevo (ej.
  un consenso de Wall Street vía Bloomberg ECFC) es un archivo nuevo en
  `rivales/` + una línea en `configs/modelo.yaml`.
