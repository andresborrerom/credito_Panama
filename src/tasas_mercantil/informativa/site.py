"""Generador del site estático en docs/informativa/.

Site con dos vistas:
  - Index global (docs/informativa/index.html) — lista de cortes disponibles.
  - Por corte (docs/informativa/outputs/<as_of>/site.html) — galería de
    slides con editor inline de mensajes (persiste en localStorage,
    exporta JSON, descarga PPTX vía workflow GitHub Actions).

El HTML es 100% estático (HTML + CSS + JS vanilla). Compatible con
GitHub Pages. Sin frameworks ni build steps.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json

from .messages import SLUG_ORDER, SLUG_TITLES


ROOT_HTML = Path("docs/informativa/index.html")


_PAGE_CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0; padding: 0; background: #f5f8fb; color: #0d1b2a;
}
header.topbar {
  background: #2a6fb3; color: white; padding: 18px 32px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1);
}
header.topbar h1 { margin: 0; font-size: 22px; font-weight: 600; }
header.topbar .meta { font-size: 13px; opacity: 0.85; }
.container { max-width: 1180px; margin: 24px auto; padding: 0 24px; }
.card {
  background: white; border-radius: 8px; padding: 22px;
  margin-bottom: 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.card h2 { margin: 0 0 6px 0; font-size: 18px; color: #1a3a5c; }
.card .subtitle { color: #777; font-size: 13px; margin-bottom: 14px; }
.card img {
  width: 100%; height: auto; border: 1px solid #e0e6ec;
  border-radius: 4px; margin: 12px 0;
}
.msg-block { margin-top: 14px; }
.msg-block label {
  display: block; font-weight: 600; font-size: 13px;
  color: #1a3a5c; margin-bottom: 6px;
}
.msg-proposed {
  background: #f5f5f5; border-left: 3px solid #888; padding: 10px 14px;
  font-size: 13px; color: #555; margin-bottom: 8px;
  white-space: pre-wrap;
}
.msg-edited {
  width: 100%; min-height: 90px; padding: 12px;
  border: 2px solid #b32a2a; border-radius: 4px;
  font-family: inherit; font-size: 14px; line-height: 1.45;
  background: #fff5e6; color: #0d1b2a; resize: vertical;
}
.msg-edited:focus { outline: none; border-color: #2a6fb3; }
.controls {
  position: sticky; bottom: 0; background: white;
  border-top: 2px solid #2a6fb3; padding: 14px 32px;
  display: flex; gap: 12px; align-items: center;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.1); flex-wrap: wrap;
}
button {
  background: #2a6fb3; color: white; border: none;
  padding: 10px 18px; border-radius: 4px; font-size: 14px;
  cursor: pointer; font-weight: 600;
}
button:hover { background: #1a3a5c; }
button.secondary { background: white; color: #2a6fb3; border: 2px solid #2a6fb3; }
button.secondary:hover { background: #e8eff7; }
.note { font-size: 12px; color: #666; margin-left: auto; }
.disclaimer {
  text-align: center; font-size: 11px; font-style: italic;
  color: #888; padding: 18px;
}
.diff { color: #b32a2a; font-weight: 600; }
"""

_PAGE_JS = """
const SLUGS = __SLUGS__;
const AS_OF = "__AS_OF__";
const LSK = `informativa:${AS_OF}:edits`;

function loadEdits() {
  try { return JSON.parse(localStorage.getItem(LSK) || "{}"); }
  catch { return {}; }
}
function saveEdits(edits) {
  localStorage.setItem(LSK, JSON.stringify(edits));
}

document.addEventListener("DOMContentLoaded", () => {
  const edits = loadEdits();
  SLUGS.forEach(slug => {
    const ta = document.getElementById("edit-" + slug);
    if (!ta) return;
    if (edits[slug]) ta.value = edits[slug];
    ta.addEventListener("input", () => {
      const e = loadEdits();
      e[slug] = ta.value;
      saveEdits(e);
      document.getElementById("status").textContent =
        "Cambios guardados en este navegador";
    });
  });

  document.getElementById("btn-reset").addEventListener("click", () => {
    if (!confirm("¿Restaurar TODOS los textos propuestos y descartar tus ediciones?")) return;
    localStorage.removeItem(LSK);
    location.reload();
  });

  document.getElementById("btn-export").addEventListener("click", () => {
    const edits = loadEdits();
    // Construir messages.json con merge propuesto+edited
    fetch("messages.json").then(r => r.json()).then(blob => {
      const newBlob = {
        as_of: blob.as_of,
        slides: blob.slides.map(s => ({
          slug: s.slug,
          title: s.title,
          proposed: s.proposed,
          edited: edits[s.slug] || s.edited || null,
        })),
      };
      const txt = JSON.stringify(newBlob, null, 2);
      const blob2 = new Blob([txt], {type: "application/json"});
      const url = URL.createObjectURL(blob2);
      const a = document.createElement("a");
      a.href = url; a.download = "messages.json";
      a.click(); URL.revokeObjectURL(url);
      document.getElementById("status").textContent =
        "messages.json descargado · subilo al repo en docs/informativa/outputs/" + AS_OF + "/";
    });
  });

  document.getElementById("btn-pptx").addEventListener("click", () => {
    alert("Para generar el PPT con tus textos:\\n\\n" +
          "1) Click \\"Exportar messages.json\\"\\n" +
          "2) Reemplazá docs/informativa/outputs/" + AS_OF + "/messages.json en el repo\\n" +
          "3) En GitHub: Actions → \\"Build deck\\" → Run workflow (corte=" + AS_OF + ")\\n" +
          "4) El PPT queda como artifact del workflow para descargar.\\n\\n" +
          "Alternativa local:\\n" +
          "  PYTHONPATH=src python -m tasas_mercantil.informativa.deck " + AS_OF);
  });
});
"""


def _render_slide_card(slug: str, title: str, proposed: str, edited: str | None,
                       png_relpath: str) -> str:
    edited_val = (edited or "").replace("&", "&amp;").replace("<", "&lt;")
    proposed_safe = proposed.replace("&", "&amp;").replace("<", "&lt;")
    diff_note = ""
    if edited and edited.strip() != proposed.strip():
        diff_note = '<div class="diff">⚠ Texto modificado respecto a la propuesta</div>'
    return f"""
<section class="card" id="card-{slug}">
  <h2>{title}</h2>
  <div class="subtitle">{slug}</div>
  <img src="{png_relpath}" alt="{slug}" loading="lazy">
  <div class="msg-block">
    <label>Texto propuesto automáticamente (referencia):</label>
    <div class="msg-proposed">{proposed_safe}</div>
    <label>Texto que irá en la presentación (editable):</label>
    <textarea id="edit-{slug}" class="msg-edited"
              placeholder="(vacío = se usa el propuesto)">{edited_val}</textarea>
    {diff_note}
  </div>
</section>
""".strip()


def render_site(as_of: date, base_dir: Path | str | None = None) -> Path:
    base = Path(base_dir) if base_dir else Path(f"docs/informativa/outputs/{as_of}")
    messages_path = base / "messages.json"
    if not messages_path.exists():
        raise FileNotFoundError(f"Falta {messages_path}; correr refresh primero.")
    blob = json.loads(messages_path.read_text(encoding="utf-8"))

    slides_html = []
    slugs = []
    for s in blob.get("slides", []):
        slug = s["slug"]
        png_name = f"{slug}.png"
        if not (base / png_name).exists():
            continue
        slides_html.append(_render_slide_card(
            slug, s["title"], s["proposed"], s.get("edited"), png_name))
        slugs.append(slug)

    page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informativa · corte {as_of}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<header class="topbar">
  <div>
    <h1>Pieza informativa · corte {as_of}</h1>
    <div class="meta">Revisá las {len(slides_html)} láminas · editá los textos propuestos · generá el PPT final</div>
  </div>
  <a href="../../" style="color:white; text-decoration:none; font-size:13px;">← Cortes</a>
</header>
<div class="container">
  {''.join(slides_html)}
</div>
<div class="controls">
  <button id="btn-export">⬇ Exportar messages.json</button>
  <button id="btn-pptx" class="secondary">Generar PPT con estos textos</button>
  <button id="btn-reset" class="secondary">↺ Restaurar propuestos</button>
  <div id="status" class="note">Tus cambios se guardan automáticamente en este navegador</div>
</div>
<div class="disclaimer">Documento informativo con fines analíticos. No constituye recomendación de inversión.</div>
<script>{_PAGE_JS.replace("__SLUGS__", json.dumps(slugs)).replace("__AS_OF__", str(as_of))}</script>
</body>
</html>"""

    out = base / "site.html"
    out.write_text(page, encoding="utf-8")
    return out


def render_index() -> Path:
    """Index global con todos los cortes disponibles."""
    outputs_dir = Path("docs/informativa/outputs")
    cortes = []
    if outputs_dir.exists():
        for d in sorted(outputs_dir.iterdir(), reverse=True):
            if d.is_dir() and (d / "site.html").exists():
                cortes.append(d.name)

    cards = "\n".join(
        f'<li><a href="outputs/{c}/site.html">Corte {c}</a></li>'
        for c in cortes
    ) or "<li><em>Sin cortes disponibles aún. Correr refresh_informativa.py.</em></li>"

    page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pieza informativa</title>
<style>{_PAGE_CSS}
ul {{ list-style: none; padding: 0; }}
ul li {{ padding: 14px 18px; background: white; margin-bottom: 8px;
        border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
ul li a {{ color: #1a3a5c; font-weight: 600; text-decoration: none; font-size: 16px; }}
ul li a:hover {{ color: #2a6fb3; }}
.cta {{ margin-bottom: 18px; }}
.cta a {{ display: inline-block; background: #2a6fb3; color: white;
        padding: 12px 22px; border-radius: 6px; text-decoration: none; font-weight: 600; }}
.cta a:hover {{ background: #1a3a5c; }}
</style>
</head>
<body>
<header class="topbar">
  <div>
    <h1>Pieza informativa · cortes disponibles</h1>
    <div class="meta">Revisá un corte para editar textos y generar el PPT</div>
  </div>
</header>
<div class="container">
  <div class="card">
    <h2>¿Cómo actualizar los datos?</h2>
    <p>Click en el botón de abajo para disparar el workflow que descarga
    los datos más recientes (FRED, EODHD, dot plot Fed) y regenera todas
    las láminas con el corte de hoy.</p>
    <div class="cta">
      <a href="https://github.com/andresborrerom/credito_panama/actions/workflows/refresh-informativa.yml"
         target="_blank">▶ Disparar refresh de datos (GitHub Actions)</a>
    </div>
    <p style="font-size:12px; color:#666; margin-top:6px;">
      En GitHub: Actions → "Refresh informativa" → Run workflow. Tarda ~2 minutos.
    </p>
  </div>
  <div class="card">
    <h2>Cortes históricos</h2>
    <ul>{cards}</ul>
  </div>
</div>
<div class="disclaimer">Documento informativo con fines analíticos. No constituye recomendación de inversión.</div>
</body>
</html>"""

    ROOT_HTML.parent.mkdir(parents=True, exist_ok=True)
    ROOT_HTML.write_text(page, encoding="utf-8")
    return ROOT_HTML
