
## Regla permanente: conservar documentos subidos
Todo documento que el usuario suba a la sesión (PDF, Excel, teaser, informe de
calificación, prospecto, etc.) se copia de inmediato a `data/external/` dentro
del repo y se commitea, con un `index.md` que registre nombre, fuente y fecha.
Motivo: el contenedor de la sesión es efímero; las subidas en
`/root/.claude/uploads/` se pierden al reiniciarse. Solo lo que está en git
sobrevive. Instrucción dada por el usuario el 2026-10-22 ("siempre").
