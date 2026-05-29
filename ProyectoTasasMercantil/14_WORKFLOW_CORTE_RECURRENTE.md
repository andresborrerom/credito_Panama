# 14 · Workflow del corte recurrente (mensual)

> Cómo producir el deck mensual sin tocar Python. La narrativa editorial
> vive en YAMLs editables por humano. El render automático lee YAMLs +
> datos del store y produce PDF + HTML.

## Resumen del ciclo

```
┌──────────────────────────────────────────────────────────────────┐
│  Día T0 (último día hábil del mes)                                │
│  └→ Analista corre BloombergTemplate y guarda con Paste Values.   │
│                                                                    │
│  Día T+1 mañana                                                    │
│  └→ Analista sube xlsx a cortes/YYYY-MM/input/                    │
│  └→ Pipeline scrapers automáticos (FRED ya actualizado).           │
│                                                                    │
│  Día T+1 tarde                                                     │
│  └→ Andrés + Camilo abren sesión con Claude.                      │
│  └→ Inicializan corte:                                            │
│       python -m src.tasas_mercantil.reportes.init_corte \         │
│           --corte YYYY-MM --as-of YYYY-MM-DD                      │
│  └→ Editan cortes/YYYY-MM/narrativa.yaml con los 3 mensajes,     │
│     vistas tácticas, calendario.                                  │
│  └→ Editan cortes/YYYY-MM/venezuela.yaml con BCV + FX + bonos.   │
│                                                                    │
│  Día T+2                                                           │
│  └→ Render:                                                       │
│       python -m src.tasas_mercantil.reportes.render_deck_v10 \    │
│           --as-of YYYY-MM-DD --corte YYYY-MM                      │
│  └→ Revisión final + ajustes en YAML según feedback.              │
│                                                                    │
│  Día T+3                                                           │
│  └→ Andrés firma. PDF a correo de directivos.                     │
│  └→ Cierre del corte: cortes/YYYY-MM/cierre.md                    │
│  └→ Git commit + push.                                            │
└──────────────────────────────────────────────────────────────────┘
```

## Arrancar un corte nuevo (3 comandos)

```bash
# 1. Crear folder con templates copiados del corte previo
python -m src.tasas_mercantil.reportes.init_corte \
    --corte 2026-06 --as-of 2026-06-30

# 2. Editar a mano los YAMLs (en VSCode, Cursor, lo que sea)
$EDITOR ProyectoTasasMercantil/cortes/2026-06/narrativa.yaml
$EDITOR ProyectoTasasMercantil/cortes/2026-06/venezuela.yaml

# 3. Renderizar el deck
python -m src.tasas_mercantil.reportes.render_deck_v10 \
    --as-of 2026-06-30 --corte 2026-06
```

Eso genera el deck v1.0 en `cortes/2026-06/output_v10/`:
- `index.html` — sitio interactivo navegable
- `TasasMercantil_2026-06_v10.pdf` — deck PDF para correo
- `figs/01_tldr.png` ... `09_calendario.png` — láminas individuales

## Schema de `narrativa.yaml`

```yaml
corte: "YYYY-MM"            # identificador del corte
as_of: "YYYY-MM-DD"          # cierre del mes
autor_principal: "str"       # Camilo + Andrés default

# TL;DR — 3 mensajes (max 3)
tldr_messages:
  - headline: "str"           # 1 frase, empieza con "Creemos que..."
    conviction: "Alta|Media|Baja"
    relevant_unit: "str"      # unidad del grupo a la que más le pega
    trigger: "str"            # evento que confirma o rompe

# Tactical Views — vistas con los 4 Ws
tactical_views:
  - activo: "str"             # ej. "UST 5-10Y"
    direccion: "Overweight|Underweight|Long|Short|Neutral"
    horizonte: "3M|6M|12M"
    conviction: "Alta|Media|Baja"
    what: "str"                # afirmación concreta
    if_right: "str"            # consecuencia upside
    if_wrong: "str"            # costo + mitigación
    trigger: "str"             # condicion de revisión

# Calendario — eventos del próximo mes
calendar:
  - fecha: "YYYY-MM-DD|str"   # fecha o descripción si rango
    evento: "str"              # ej. "FOMC + SEP/dot plot"
    relevante_para: "str"      # mapeo a lámina/vista específica
    importancia: "Alta|Media|Baja"
```

## Schema de `venezuela.yaml`

```yaml
as_of: "YYYY-MM-DD"
fuente: "str"                # ej. "BCV + promedio 3 fuentes paralelo"

# BCV
bcv_tasa_politica_pct: float | null
bcv_encaje_legal_pct: float | null
bcv_tasa_activa_max_pct: float | null
bcv_tasa_pasiva_max_pct: float | null

# FX (VES por USD)
fx_oficial_ves_usd: float | null
fx_paralelo_ves_usd: float | null
fx_oficial_mes_ant: float | null
fx_paralelo_mes_ant: float | null

# Bonos defaulteados (precio)
bono_ven_2027_precio: float | null
bono_pdvsa_2037_precio: float | null
bono_ven_2027_mes_ant: float | null
bono_pdvsa_2037_mes_ant: float | null

m2_bs_billones: float | null
notas_corte: "str"
```

## Datos que llegan automáticos (sin editar YAML)

El render lee del store unificado (`data/external/tasas_mercantil/`):
- **UST nominal + TIPS + Breakevens + Swap SOFR OIS** (Bloomberg histórico).
- **Fed Funds upper/lower, EFFR, IORB, ON RRP, SOFR ON/avg** (BBG + FRED).
- **Curva soberana Panamá + spreads corporativos locales** (credito_Panama).
- **BCE/BoE/BoJ + Bund/Gilt/JGB + DXY** (FRED).
- **Macro vintage USA** para Pieza B Taylor (CPI core, PCE core, U-3, payrolls).
- **SR3 SOFR futures + EuroDollar pre-2018** (implied path).

Refresh de los datos antes de cada corte:

```bash
# FRED non-vintage (rápido, ~30 seg)
python -m src.tasas_mercantil.data.backfill_fred --non-vintage --start 1985-01-01

# FRED vintage macro (lento, ~10-15 min). Correr cada 2-3 meses.
python -m src.tasas_mercantil.data.backfill_fred --vintage --vintage-freq QE

# Ingesta del Excel mensual de Antulio (cuando llegue al corte)
python -m src.tasas_mercantil.data.ingest_bloomberg historico \
    --input ProyectoTasasMercantil/cortes/YYYY-MM/input/BloombergTemplate_*.xlsx \
    --output data/external/tasas_mercantil/bloomberg_mensual_YYYY-MM.parquet
```

## Qué NO está automatizado (todavía)

- **Lámina 4 Spreads corporativos**: requiere subíndices ICE BofA del Excel
  mensual de Antulio. Tickers a confirmar (ver `12_DATA_AUDIT_FINDINGS.md`).
- **Lámina 8 Impacto Mercantil**: sesión narrativa contigo + Camilo para
  mapear 5 unidades del grupo. Eventualmente entra a `narrativa.yaml`.
- **Pieza C (señal editorial mensual)**: hipótesis condicional del mes.
  Cuando se incorpore, va a un campo extra en `narrativa.yaml`.

## Iteración mensual con Claude

Una vez generado el deck:

1. Andrés/Camilo lo revisan.
2. Si algo del mensaje editorial no funciona: editan los YAML y re-renderizan.
3. Si algo de la lectura técnica del modelo falla: abren issue → discutimos.
4. Si todo OK: firmar el corte (`cierre.md`) y distribuir.

El YAML es la fuente de verdad. Git versiona cada corte. Para auditoría,
basta con leer el YAML del mes y comparar con el deck PDF.

## Para una sesión nueva con Claude en un corte recurrente

Prompt sugerido:

```
Sigamos con el corte 2026-06. Status:
- Datos del store actualizados (corre backfill_fred si > 1 semana).
- Excel mensual de Antulio en cortes/2026-06/input/.

Lo que quiero conmigo: validar los 3 mensajes del TL;DR contra el path
Mercantil v0.3.0, ajustar las 4 vistas tácticas si Pieza B cambió de
opinión, y revisar la divergencia mercado vs modelo.

Lee:
- cortes/2026-05/cierre.md (qué quedó pendiente y qué observar).
- ProyectoTasasMercantil/13b_BENCHMARK_REPORTES.md (spec del deck).
- ProyectoTasasMercantil/14_WORKFLOW_CORTE_RECURRENTE.md (este doc).

Y arrancamos.
```
