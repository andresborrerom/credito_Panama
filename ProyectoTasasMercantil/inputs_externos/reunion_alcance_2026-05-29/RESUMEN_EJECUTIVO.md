# Resumen ejecutivo · Reunión alcance modelo · 2026-06-01

Procesado el 2026-06-02 por Claude a partir del audio (transcripción Whisper
local) + 2 Excels + notas del owner.

## Participantes identificados

- **Camilo Forero** — coordinador, contraste con la mesa
- **Antulio Moya** — analista que construye los Excels
- **Alfonso Brandini** — mini-prototipo del reporte mensual
- **Andrés Borrero** — owner del proyecto / tesorero corporativo
- **Juan LaGreca (JLG)** — sponsor del reporte, mencionado en transcript
- Otros mencionados: Alejandra, Ricardo, Julio

## Las 8 decisiones que se tomaron en la reunión

1. **Dos productos, no uno**. Reporte de tasas (lo que ya teníamos) + Modelo
   de retornos esperados (sofisticación del Excel de Antulio).
2. **3-4 escenarios con probabilidad** en vez de un único forecast.
3. **USA fuerte, Panamá específico, Venezuela parqueada, Europa fuera**.
4. **Es informativo, no recomendación**. Reiterado dos veces. Compliance.
5. **CDS Panamá + descomposición de correlación con USA** como pieza nueva.
6. **Nearest neighbors y/o varios modelos compitiendo** para sofisticar.
7. **Caso Banesco** (bonos perpetuos 7% USD 60M Panamá) como ejemplo de
   estudio proactivo de oportunidades de fondeo.
8. **Timing**: la presentación se hace la semana siguiente al cierre de
   mes. Junio cierre → presentar primera semana de julio.

## Ideas exploratorias del owner (notas)

- NLP de discursos Fed como input.
- Noticias como data alternativa.
- Otros datos macro que la Fed usa (no solo CPI/PCE/U-3/Payrolls).
- Acwi global de bonos para predicción de retornos a horizonte mensual.

## Quick wins inmediatos

✅ **Hecho 2026-06-02**: input cuantitativo del modelo Mercantil v0.3.0
para la línea 13 del Excel `Ret esperados`. Resultado: −9.6 bps, valida
intuición editorial actual de −10 bps. Ver
`cortes/2026-05/output_v10/sugerencia_input_mercantil_v0.3.0.md`.

## Próximos pasos por prioridad

1. **Producto B v2.0** — 3-4 escenarios con probabilidad + sensibilidad del
   portafolio LUZ. Ver `16_PRODUCTO_B_RETORNOS_ESPERADOS.md` para el
   roadmap detallado.
2. **CDS Panamá** + descomposición correlación → enriquecer Lámina 6.
3. **Histórico de retornos mensuales por ETF** — ingesta nueva (BIL, IGLA,
   GHYG, LQD, EMB, ACWI, AGG).
4. **(Exploratorio, fase 2+)** NLP discursos Fed, news, datos macro alt.

## Lo que ya NO va en el alcance

- Europa del análisis global (Andrés explícito: "yo no incluiría").
- Pretensión de UN único forecast de tasas.
- Lámina 8 "Impacto Mercantil por unidad" en su forma anterior — se
  reemplaza por la nueva "Escenarios + portafolio".

## Archivos relevantes (referencia)

- `transcript.txt` — transcripción Whisper del audio (26K chars, 619 segmentos).
- `Reporte mensual de tasas.xlsx` — Excel de Alfonso (avance del producto A).
- `Ret esperados.xlsx` — Excel de Antulio (base del producto B).
- `NOTAS PARA PROYECTO DE TASAS EN MER.txt` — notas del owner.
