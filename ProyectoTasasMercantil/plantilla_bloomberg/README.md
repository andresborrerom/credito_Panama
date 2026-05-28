# Plantilla Bloomberg

Archivo: `BloombergTemplate_TasasMercantil.xlsx`

Plantilla que se entrega al analista cada mes. El analista solo edita la celda
`AS_OF` en la hoja `01_Parametros` y deja que Bloomberg resuelva las fórmulas.

## Cómo regenerar la plantilla

```bash
cd credito_Panama
python3 ProyectoTasasMercantil/plantilla_bloomberg/build_bloomberg_template.py
```

Se regenera si cambia el catálogo de instrumentos o las fórmulas.

## Estructura del archivo

| Hoja | Propósito |
|---|---|
| `00_Instrucciones` | Cómo correr la plantilla |
| `01_Parametros` | Fechas del corte (analista solo edita `AS_OF`) |
| `02_Datos` | Spots a 4 fechas (AS_OF, mes anterior, cierre año anterior, inicio 12M) — formato long, 64 instrumentos |
| `03_SOFR_Futures` | Strip de SR3 próximos 8 vencimientos |
| `04_FedWatch` | Paste manual de WIRP (no hay fórmulas BDP confiables para esto) |
| `05_Notas_Analista` | Tickers que fallaron + eventos + sugerencias |
| `99_Envio` | Instrucciones de cómo devolver el archivo |

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

- v0.1 — primera versión (mayo 2026). 64 instrumentos + 8 futuros SOFR + FedWatch manual.
- Tickers marcados con "— confirmar" en la columna `nota` deben validarse con el primer
  analista que corra la plantilla; cualquier ticker corregido se actualiza en el script
  `build_bloomberg_template.py` y se regenera el xlsx.
