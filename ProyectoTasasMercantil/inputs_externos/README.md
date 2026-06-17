# Inputs externos del proyecto

Carpeta-mailbox donde el owner sube documentos que el agente debe procesar:
transcripts de reuniones, Excels de análisis, notas manuscritas, screenshots
que ya se transcriben, etc.

## Estructura

```
inputs_externos/
└── <descriptor>_<fecha>/
    ├── transcript.txt | .md       (o nombre similar)
    ├── notas.md                   (notas que el owner teclea o pega)
    └── *.xlsx, *.pdf, *.png       (archivos varios)
```

Cuando el owner sube algo nuevo, el agente lee la carpeta y reporta qué
encontró + qué piensa hacer con cada archivo.

## Convención de naming

`<descriptor>_<YYYY-MM-DD>/` donde descriptor describe el evento.

Ejemplos:
- `reunion_alcance_2026-05-29/` — reunión sobre alcance del modelo, mayo 29 2026
- `feedback_jlg_2026-06-15/` — comentarios de JLG sobre el deck
- `bbg_correcciones_antulio_2026-06-01/` — tickers corregidos por Antulio
