# Plantillas Bloomberg

Tres archivos viven en este folder:

| Archivo | Cuándo se corre | Rango temporal |
|---|---|---|
| `BloombergTemplate_TasasMercantil.xlsx` | **Cada mes**, recurrente | Spots a 4 fechas (AS_OF, mes anterior, 31-dic año anterior, 12M atrás) |
| `historico/BloombergHistorico_TasasMercantil_FULL.xlsx` | **Una sola vez**, al arrancar el proyecto | Diario 1985-01-01 → cierre del mes actual |
| `historico/BloombergHistorico_TasasMercantil_ALT_20Y.xlsx` | **Plan B** si el FULL se traba | Diario 2006-01-01 → cierre del mes actual |

El histórico alimenta el backtest del modelo predictivo (1985+) y los gráficos
de 12M corridos. Es una sola pasada. La plantilla mensual es la que se corre
recurrente cada cierre de mes.

## Cómo regenerar las plantillas

```bash
cd credito_Panama
python3 ProyectoTasasMercantil/plantilla_bloomberg/build_bloomberg_template.py
python3 ProyectoTasasMercantil/plantilla_bloomberg/build_bloomberg_historico_template.py
```

Se regeneran si cambia el catálogo de instrumentos o las fórmulas. Antes de
correr el script histórico, ajustar el `to_date_text` en `main()` para
reflejar el cierre vigente.

## Estructura del archivo mensual

| Hoja | Propósito |
|---|---|
| `00_Instrucciones` | Cómo correr la plantilla |
| `01_Parametros` | Fechas del corte (analista solo edita `AS_OF`) |
| `02_Datos` | Spots a 4 fechas (AS_OF, mes anterior, cierre año anterior, inicio 12M) — formato long, 76 instrumentos |
| `03_SOFR_Futures` | Strip de SR3 próximos 8 vencimientos |
| `04_FedWatch` | Paste manual de WIRP (no hay fórmulas BDP confiables para esto) |
| `05_Notas_Analista` | Tickers que fallaron + eventos + sugerencias |
| `99_Envio` | Instrucciones de cómo devolver el archivo |

## Estructura del archivo histórico

| Hoja | Contenido |
|---|---|
| `00_Instrucciones` | Carga única, qué hacer si se traba (usar el ALT_20Y) |
| `01_Parametros` | `FROM_DATE`, `TO_DATE` ya fijados literal (NO `=TODAY()`); analista llena nombre y fechas de carga |
| `UST_Nominal` | UST 1M–30Y diario |
| `TIPS_Real` | TIPS 5Y/10Y/20Y/30Y diario |
| `Breakevens` | BE 2Y/5Y/10Y/30Y diario |
| `Swap_SOFR_OIS` | SOFR OIS 2/5/10/30Y diario |
| `Swap_USD_Clasico_LIBOR` | USD swap 2/5/10/30Y LIBOR-based (proxy pre-SOFR) |
| `SOFR_Money_Market` | SOFR ON/avg + term SOFR 1M/3M/6M/12M |
| `FedFunds_Policy` | FF target upper/lower, target pre-2008, EFFR, IORB, ON RRP |
| `EuroDollar_Futures_Proxy_PreSOFR` | ED1–ED8 continuous para reconstruir implied path pre-2018 |
| `SR3_SOFR_Futures` | SFR1–SFR8 continuous post-2018 |
| `05_Notas_Analista` | igual que la mensual |
| `99_Envio` | Subir a `historico/` |

**Total: 56 instrumentos**. Cada uno ocupa 2 columnas (fecha + valor) con
fórmula `=BDH(...)` que se desborda hacia abajo. Para 40 años son ~10,000
filas hábiles por instrumento.

## Convenciones de las fórmulas

Cada celda de valor usa:

```excel
=IFERROR(
   INDEX(BDH(ticker, field, fecha, fecha, "Days=A", "Fill=B", "Dir=H"), 1, 2),
   BDH(ticker, field, fecha, fecha, "Days=A", "Fill=B")
)
```

- `BDH` con `start=end=fecha` devuelve el valor de un solo día.
- `Days=A` = días calendario (no solo trading days), permite extraer fines de semana con fill backward.
- `Fill=B` = backward fill (si la fecha es feriado, toma el dato del día hábil anterior).
- El `INDEX(..., 1, 2)` extrae el valor (la columna 1 es la fecha; la columna 2 es el valor).
- El `IFERROR(..., BDH(...))` es fallback para versiones de Excel donde el BDH no devuelve array.

## Versión y mantenimiento

- **v0.2** (2026-05-28) — agregadas TIPS (4), breakevens (4), SOFR OIS swap (4).
  76 instrumentos totales. Fix del bug "today"/`=TODAY()` heredado de la lección
  de `mercantil-saa`: la hoja de instrucciones ahora exige Paste Special → Values
  antes de devolver el archivo, y `FECHA_CARGA`/`FECHA_GUARDADO_VALUES` son
  inputs manuales.
- v0.1 (2026-05-28) — primera versión. 64 instrumentos.

Tickers marcados con "— confirmar" en la columna `nota` deben validarse con el
primer analista que corra la plantilla; cualquier ticker corregido se actualiza
en el script `build_bloomberg_template.py` y se regenera el xlsx.

## Regla operativa crítica

**El archivo se entrega con valores cuajados, no con fórmulas vivas.** Después
de cargar los datos, el analista debe hacer Paste Special → Values en las
hojas `02_Datos`, `03_SOFR_Futures` y `04_FedWatch`. Razón: si no, al reabrir
el archivo sin Bloomberg, las celdas muestran `#N/A Requesting Data` y se
pierde el snapshot. Lección heredada del proyecto `mercantil-saa`.
