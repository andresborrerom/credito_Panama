# 00 · Permisos y alcance

Este documento es vinculante para cualquier agente o sesión que trabaje en este proyecto.
Léase **antes** de cualquier escritura.

## Repos en este entorno

| Repo | Permiso | Uso en este proyecto |
|---|---|---|
| `andresborrerom/credito_panama` | **lectura y escritura** | aquí vive `ProyectoTasasMercantil/` |
| `andresborrerom/mercantil-planner` | **solo lectura** | referencia conceptual; **no escribir** |
| `andresborrerom/mercantil-saa` | **solo lectura** | referencia conceptual; **no escribir** |

## Reglas de escritura

1. **Solo escribimos dentro de `credito_panama/ProyectoTasasMercantil/`** (este árbol)
   y, cuando se justifique, dentro de `credito_panama/data/external/tasas_mercantil/`
   para datasets compartidos. Cualquier otra ruta es de solo lectura para este proyecto.
2. **Nunca** modificar archivos en `mercantil-planner/` ni `mercantil-saa/`. Si se necesita
   información de ahí, copiarla a `credito_panama/data/external/tasas_mercantil/` con
   atribución en el README del corte.
3. **No tocar el resto de `credito_panama/`** (los módulos `src/etl`, `src/analytics`,
   `src/app`, `docs/`, `data/` raíz) salvo que se agregue código nuevo bajo
   `src/tasas_mercantil/` y se acuerde explícitamente en la sesión.
4. Cualquier script ejecutable del proyecto vive bajo
   `credito_panama/src/tasas_mercantil/` (no creado todavía) y se importa como
   `src.tasas_mercantil.*`.

## Branch de desarrollo

- **Branch designado:** `claude/tasas-mercantil-report-Q8sFt`
- Todo el trabajo se commitea y pushea ahí. No abrir PR sin pedido explícito del usuario.
- Si se hace merge a `main`, lo decide Andrés.

## Manejo de datos sensibles

- **Datos internos del Grupo Mercantil** (tasas activas/pasivas reales del libro,
  NIM, posición propia) **no entran a este repo por ahora**. Cuando se incorporen
  (Fase 4 avanzada), se decidirá un mecanismo aparte (probablemente repo privado
  separado o cifrado at-rest). Mientras tanto, el reporte usa solo datos públicos /
  Bloomberg estándar.
- **Bolívar paralelo:** se incluye como referencia de mercado. Se etiqueta explícitamente
  como no oficial. Fuente y metodología documentadas en `03_FUENTES_Y_BLOOMBERG.md`.
- **Archivos input de los analistas** (Excel devuelto con datos de Bloomberg) sí pueden
  ir al repo bajo `cortes/YYYY-MM/input/`; no contienen información cliente, solo
  precios de mercado.

## Publicación

- El reporte se distribuye **por correo** (PDF y, opcionalmente, link al HTML).
- El HTML interactivo se hospeda en **GitHub Pages privado** del propio repo
  `credito_panama`. El acceso se limita a una allowlist de correos definida en
  Settings → Pages → Visibility (requiere plan apropiado de GitHub) o por una capa
  de auth simple sobre Pages.
- **Nunca** indexar el HTML públicamente (`robots.txt` + `<meta name="robots" content="noindex">` en los renders).

## Versionado del reporte

- Cada corte queda como **inmutable** una vez firmado: `cortes/YYYY-MM/` no se
  modifica retroactivamente sin acuerdo. Si se descubre un error, se publica un
  `cortes/YYYY-MM/erratum_YYYY-MM-DD.md`.
- El histórico se conserva en `git` y en el folder de cortes, no se sobreescribe.
