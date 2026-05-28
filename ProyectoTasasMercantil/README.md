# Proyecto Tasas Mercantil — Reporte Mensual de Tasas de Interés

Reporte mensual para directivos del Grupo Mercantil con contexto de tasas, movimientos
del mes y cambios de expectativas. Entregables: **deck PDF** (interno) + **sitio HTML
interactivo** (estudio). Cobertura en 5 fases + un capítulo transversal de spreads
corporativos.

> Solicitud original: JLG, abril 2026. Responsable de la iniciativa: Andrés Borrero.
> Construcción y narrativa mensual: Andrés + Camilo + Claude. Ejecución/actualización
> de datos: equipo de analistas.

---

## Cómo arrancar una sesión mensual (después de construido el pipeline)

1. **Analista** corre la plantilla `BloombergTemplate_TasasMercantil.xlsx` con el
   cierre del último día hábil del mes, y la deja en `cortes/YYYY-MM/input/`.
2. **Andrés/Camilo/Claude** abren una sesión nueva y empiezan con:

   ```
   Lee ProyectoTasasMercantil/README.md, 04_PLAYBOOK_MENSUAL.md y
   ProyectoTasasMercantil/cortes/<MES_ANTERIOR>/cierre.md.
   Vamos a armar el corte <MES_ACTUAL>.
   ```

3. Claude corre el pipeline, regenera lo automático y nos propone borrador de
   mensajes clave por lámina. Iteramos en conversación y cerramos el deck.
4. PDF y HTML quedan en `cortes/YYYY-MM/output/`, listos para correo y GitHub Pages
   privado.

Detalle completo del ciclo en `04_PLAYBOOK_MENSUAL.md`.

---

## Estructura de la carpeta

```
ProyectoTasasMercantil/
├── README.md                          ← este archivo (punto de entrada)
├── 00_PERMISOS_Y_ALCANCE.md           ← qué se puede tocar y qué no
├── 01_PLAN_Y_FASES.md                 ← roadmap de las 5 fases + capítulo corporativo
├── 02_MODELO_DATOS.md                 ← esquema de tablas, snapshots, idempotencia
├── 03_FUENTES_Y_BLOOMBERG.md          ← qué viene de dónde + spec del Excel plug-and-play
├── 04_PLAYBOOK_MENSUAL.md             ← receta paso a paso del corte mensual
├── 05_MEMORIA_DE_SESIONES.md          ← cómo Claude retoma el hilo cada mes
├── 06_GRUPO_MERCANTIL.md              ← mapa del grupo (insumo para Fase 4)
├── 07_MODELO_PREDICTIVO.md            ← contrato técnico del modelo Mercantil
├── 08_CORPORATIVAS_SPREADS.md         ← estudio adicional de spreads por rating/plazo/región
├── 09_DECK_Y_ENTREGABLES.md           ← estructura de láminas + HTML + naming
├── 10_MODELO_ARQUITECTURA.md          ← stack, carpetas, YAML, plan de fases del modelo
├── 11_MODELO_ROBUSTEZ.md              ← esqueleto del doc de robustez (técnico + ejecutivo)
├── 12_DATA_AUDIT_FINDINGS.md          ← bitácora de problemas/decisiones de datos
├── plantilla_bloomberg/               ← Excel plug-and-play para el analista
│   ├── README.md
│   ├── build_bloomberg_template.py    ← script reproducible que genera el xlsx
│   └── BloombergTemplate_TasasMercantil.xlsx
└── cortes/                            ← un subfolder por corte mensual
    ├── README.md                      ← qué hay dentro de un corte
    ├── 2026-01/                       ← primer corte histórico (backfill)
    ├── 2026-02/
    ├── 2026-03/
    ├── 2026-04/
    └── 2026-05/                       ← primer corte "en vivo"
```

---

## Estado actual

| Hito | Estado |
|---|---|
| Estructura del proyecto + docs base | ✅ creada |
| Plantilla Bloomberg `BloombergTemplate_TasasMercantil.xlsx` (v0.2 — 76 instrumentos incluyendo TIPS, breakevens, swaps) | ✅ generada — `plantilla_bloomberg/` |
| Docs estilo SAA: arquitectura del modelo, robustez, data audit | ✅ creados |
| Backfill de datos para modelo (FRED ALFRED + BBG desde 1994) | ⏳ pendiente |
| Pipeline ETL Fase 1 (USA: Fed/SOFR/UST/TIPS/BE/Swap/FedWatch/SR3) | ⏳ pendiente |
| Backfill informes ene–may 2026 (cortes publicables) | ⏳ pendiente |
| Deck Fase 1 publicable | ⏳ pendiente |
| Esbozos Fases 2–5 | ⏳ pendiente |
| Capítulo spreads corporativos | ⏳ pendiente |
| Modelo predictivo Mercantil v0.1→1.0 + backtest robusto | ⏳ pendiente |
| Bitácora Quarto del modelo (HTML privado) | ⏳ pendiente |

---

## Decisiones tomadas (resumen)

- **Cobertura temporal por corte:** 12 meses corridos + comparación vs mes anterior + UST 31-dic año anterior. Cierre = último día hábil del mes; presentación T+3.
- **Backfill arranca enero 2026.** Reconstruimos cortes históricos sin usar información futura (snapshots versionados, ver `02_MODELO_DATOS.md`).
- **Audiencia:** directivos del Grupo Mercantil. "Vista externa" = las propias empresas del grupo (Banco Venezuela, Banco Panamá, Aseguradora, Wealth, posición propia, etc.). Logo: Mercantil SFI.
- **Idioma:** español.
- **Fuente primaria de datos de mercado:** Bloomberg (los analistas corren un Excel plug-and-play). Complemento público: FRED, US Treasury, CME, BCV.
- **Curvas cubiertas:** nominal (UST), **real (TIPS)**, **breakevens** y **swap SOFR OIS** — los 4 a 5Y/10Y/30Y, más curvas de soberanos G7 y EM principales.
- **Venezuela:** se incluye paralelo además del oficial.
- **Expectativas Fed:** se muestran 3 lecturas en paralelo — (a) implied path de futuros SOFR, (b) probabilidades CME FedWatch por reunión, (c) modelo propio Mercantil con backtest honesto.
- **Modelo predictivo:** universo de datos desde 1994 (Fed Funds target explícito); calibración 2000–2009; walk-forward 2010–presente; 9 regímenes evaluados separados; rivales explícitos (implied path, FedWatch, Taylor naive, naive, dot plot mediana). Detalle en `07_MODELO_PREDICTIVO.md`.
- **Distribución:** PDF/slides por correo + GitHub Pages **privado** (acceso por allowlist de correos).

---

## Roles

| Rol | Persona |
|---|---|
| Sponsor del reporte | JLG |
| Responsable de la iniciativa | Andrés Borrero |
| Co-autor de narrativa mensual | Camilo Forero |
| Co-autor de narrativa + ingeniería | Claude (este agente) |
| Ejecución/actualización mensual de datos | Equipo de analistas |

---

## Disclaimers

- Estudio informativo. No constituye recomendación de inversión.
- Bolívar paralelo y otras fuentes no oficiales se reportan como referencia de mercado, no como tasa oficial del grupo.
- Las proyecciones del modelo propio son probabilísticas; el deck siempre las muestra junto a las dos referencias de mercado.
