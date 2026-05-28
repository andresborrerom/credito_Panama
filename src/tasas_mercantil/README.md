# `src/tasas_mercantil/` — codigo del proyecto

Codigo ejecutable del Proyecto Tasas Mercantil. Documentacion viva al lado en
`ProyectoTasasMercantil/`.

## Estado

| Modulo | Estado |
|---|---|
| `__init__.py` | ✅ presente |
| `configs/modelo.yaml` | ✅ v0.1.0 |
| `configs/features.yaml` | ✅ catalogo inicial con ~20 features |
| `data/snapshot.py` | ✅ API point-in-time |
| `data/ingest_fred.py` | 🟡 stub — implementacion en sesion M-0 |
| `data/ingest_bloomberg.py` | ⏳ pendiente |
| `data/ingest_cme.py` | ⏳ pendiente |
| `data/ingest_scrapers.py` | ⏳ pendiente |
| `modelo/pieces/*` | ⏳ pendiente |
| `rivales/*` | ⏳ pendiente |
| `backtest/*` | ⏳ pendiente |
| `tests/test_no_lookahead.py` | ✅ esqueleto |

## Como correr (cuando este implementado)

```bash
# Setup (una vez)
export FRED_API_KEY=...  # https://fredaccount.stlouisfed.org/apikey

# Backfill historico (M-0, primera vez)
python -m src.tasas_mercantil.data.ingest_fred --features all --from 1985-01-01

# Validar un corte mensual recien recibido
python -m src.tasas_mercantil.data.validate \
    --input ProyectoTasasMercantil/cortes/2026-05/input/BloombergTemplate_TasasMercantil_2026-05.xlsx

# Correr backtest del modelo
python -m src.tasas_mercantil.backtest.walk_forward --config configs/modelo.yaml
```

## Tests

```bash
pytest src/tasas_mercantil/tests/ -v
```

El test critico es `test_no_lookahead.py`. Si falla, NADA del backtest es
valido — investigar antes de seguir.
