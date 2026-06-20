"""Generador del site estático con operación end-to-end vía GitHub API.

Todo se opera desde el site:
  - Refresh de datos (dispara workflow refresh-informativa.yml)
  - Edición de mensajes (autosave en localStorage)
  - Guardar textos editados (commit messages.json al repo)
  - Generar PPT final (dispara workflow build-deck.yml)
  - Descargar PPT (link directo a GitHub Pages, sin auth)

Requiere PAT del usuario con scopes `repo` + `workflow`, guardado en
localStorage del browser. Setup una sola vez.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json

from .messages import SLUG_ORDER, SLUG_TITLES


ROOT_HTML = Path("docs/informativa/index.html")

REPO_OWNER = "andresborrerom"
REPO_NAME = "credito_Panama"
BRANCH = "claude/tasas-mercantil-report-Q8sFt"


_PAGE_CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0; padding: 0; background: #f5f8fb; color: #0d1b2a;
}
header.topbar {
  background: #2a6fb3; color: white; padding: 14px 24px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1); flex-wrap: wrap; gap: 12px;
}
header.topbar h1 { margin: 0; font-size: 19px; font-weight: 600; }
header.topbar .meta { font-size: 12px; opacity: 0.85; margin-top: 2px; }
header.topbar .auth { font-size: 12px; display: flex; align-items: center; gap: 8px; }
header.topbar .auth .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
header.topbar .auth .dot.ok { background: #4ade80; }
header.topbar .auth .dot.no { background: #f87171; }
header.topbar .auth button {
  background: rgba(255,255,255,0.18); color: white; border: 1px solid rgba(255,255,255,0.4);
  padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer;
}
header.topbar .auth button:hover { background: rgba(255,255,255,0.3); }
.container { max-width: 1180px; margin: 24px auto; padding: 0 24px 120px; }
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
  font-size: 13px; color: #555; margin-bottom: 8px; white-space: pre-wrap;
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
  border-top: 2px solid #2a6fb3; padding: 14px 24px;
  display: flex; gap: 10px; align-items: center;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.1); flex-wrap: wrap;
}
button.btn {
  background: #2a6fb3; color: white; border: none;
  padding: 10px 18px; border-radius: 4px; font-size: 14px;
  cursor: pointer; font-weight: 600;
}
button.btn:hover:not(:disabled) { background: #1a3a5c; }
button.btn:disabled { background: #aaa; cursor: not-allowed; }
button.btn.secondary { background: white; color: #2a6fb3; border: 2px solid #2a6fb3; }
button.btn.secondary:hover:not(:disabled) { background: #e8eff7; }
button.btn.success { background: #16a34a; }
button.btn.success:hover:not(:disabled) { background: #15803d; }
.note { font-size: 12px; color: #666; margin-left: auto; }
.disclaimer { text-align: center; font-size: 11px; font-style: italic; color: #888; padding: 18px; }
.diff { color: #b32a2a; font-weight: 600; margin-top: 6px; font-size: 12px; }

/* Modal */
.modal-bg {
  display: none; position: fixed; top:0; left:0; right:0; bottom:0;
  background: rgba(0,0,0,0.5); z-index: 1000; align-items: center; justify-content: center;
}
.modal-bg.open { display: flex; }
.modal {
  background: white; border-radius: 8px; padding: 28px;
  max-width: 560px; width: 90%; max-height: 86vh; overflow-y: auto;
}
.modal h2 { margin-top: 0; color: #1a3a5c; }
.modal h3 { font-size: 14px; color: #1a3a5c; margin: 14px 0 6px; }
.modal ol { padding-left: 20px; font-size: 14px; line-height: 1.6; }
.modal code {
  background: #f0f0f0; padding: 2px 6px; border-radius: 3px;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px;
}
.modal input[type=password], .modal input[type=text] {
  width: 100%; padding: 10px; border: 2px solid #ccc; border-radius: 4px;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px;
  margin-top: 8px;
}
.modal .actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 18px; }
.modal .error { color: #b32a2a; font-size: 13px; margin-top: 8px; }
.modal .success { color: #16a34a; font-size: 13px; margin-top: 8px; }

/* Status banner */
.status-banner {
  background: #fff5e6; border: 2px solid #f59e0b; padding: 14px 18px;
  border-radius: 6px; margin-bottom: 18px; font-size: 14px;
  display: flex; align-items: center; gap: 10px;
}
.status-banner.success { background: #dcfce7; border-color: #16a34a; }
.status-banner.error { background: #fee2e2; border-color: #b32a2a; }
.status-banner .spinner {
  width: 16px; height: 16px; border: 2px solid #f59e0b;
  border-top-color: transparent; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

ul.cortes { list-style: none; padding: 0; }
ul.cortes li {
  padding: 14px 18px; background: white; margin-bottom: 8px;
  border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  display: flex; justify-content: space-between; align-items: center;
}
ul.cortes li a {
  color: #1a3a5c; font-weight: 600; text-decoration: none; font-size: 16px;
}
ul.cortes li a:hover { color: #2a6fb3; }
ul.cortes li .meta { font-size: 12px; color: #888; }
"""


# JavaScript común para todas las páginas: cliente GitHub API + modal del PAT
_COMMON_JS = """
const REPO_OWNER = "__REPO_OWNER__";
const REPO_NAME = "__REPO_NAME__";
const BRANCH = "__BRANCH__";
const API = "https://api.github.com";
const PAGES = `https://${REPO_OWNER}.github.io/${REPO_NAME}/informativa`;
const TOKEN_KEY = "informativa:gh_token";

const GH = {
  token: () => localStorage.getItem(TOKEN_KEY),
  setToken: (t) => localStorage.setItem(TOKEN_KEY, t),
  clearToken: () => localStorage.removeItem(TOKEN_KEY),

  async _req(method, path, body) {
    const t = GH.token();
    if (!t) throw new Error("No hay token configurado. Click en \\"Configurar GitHub\\" arriba.");
    const headers = {
      "Authorization": `Bearer ${t}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (body) headers["Content-Type"] = "application/json";
    const res = await fetch(`${API}${path}`, {
      method, headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) throw new Error("Token inválido o expirado.");
    if (res.status === 403) throw new Error("Sin permisos. Verificá scopes 'repo' y 'workflow' del token.");
    if (res.status === 404 && method === "GET") return null;
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`API ${res.status}: ${txt.slice(0, 200)}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  },

  async testAuth() {
    const u = await GH._req("GET", "/user");
    return u && u.login;
  },

  async triggerWorkflow(workflow_id, inputs) {
    return GH._req(
      "POST",
      `/repos/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${workflow_id}/dispatches`,
      { ref: BRANCH, inputs: inputs || {} },
    );
  },

  async getLatestRun(workflow_id) {
    const j = await GH._req(
      "GET",
      `/repos/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${workflow_id}/runs?per_page=1&branch=${BRANCH}`,
    );
    return j && j.workflow_runs && j.workflow_runs[0];
  },

  async getFile(path) {
    return GH._req("GET", `/repos/${REPO_OWNER}/${REPO_NAME}/contents/${path}?ref=${BRANCH}`);
  },

  async putFile(path, content, message, sha) {
    return GH._req("PUT", `/repos/${REPO_OWNER}/${REPO_NAME}/contents/${path}`, {
      message, content, sha: sha || undefined, branch: BRANCH,
    });
  },
  async putFileBinary(path, base64content, message, sha) {
    return GH._req("PUT", `/repos/${REPO_OWNER}/${REPO_NAME}/contents/${path}`, {
      message, content: base64content, sha: sha || undefined, branch: BRANCH,
    });
  },
};

function updateAuthUI() {
  const dot = document.getElementById("auth-dot");
  const txt = document.getElementById("auth-txt");
  const btn = document.getElementById("auth-btn");
  if (!dot) return;
  if (GH.token()) {
    dot.className = "dot ok";
    txt.textContent = "GitHub conectado";
    btn.textContent = "Cambiar token";
  } else {
    dot.className = "dot no";
    txt.textContent = "Sin token GitHub";
    btn.textContent = "Configurar GitHub";
  }
}

function openAuthModal() {
  const m = document.getElementById("auth-modal");
  if (m) {
    m.classList.add("open");
    const input = document.getElementById("pat-input");
    if (input) { input.value = GH.token() || ""; input.focus(); }
    const result = document.getElementById("auth-result");
    if (result) result.innerHTML = "";
  }
}
function closeAuthModal() {
  const m = document.getElementById("auth-modal");
  if (m) m.classList.remove("open");
}

async function saveToken() {
  const v = document.getElementById("pat-input").value.trim();
  const r = document.getElementById("auth-result");
  if (!v) {
    r.className = "error"; r.textContent = "Pegá el token primero."; return;
  }
  GH.setToken(v);
  r.className = ""; r.textContent = "Validando…";
  try {
    const user = await GH.testAuth();
    r.className = "success";
    r.textContent = `Conectado como ${user} ✓`;
    updateAuthUI();
    setTimeout(closeAuthModal, 1200);
  } catch (e) {
    GH.clearToken(); updateAuthUI();
    r.className = "error"; r.textContent = e.message;
  }
}

function clearToken() {
  if (confirm("¿Eliminar el token guardado en este navegador?")) {
    GH.clearToken(); updateAuthUI(); closeAuthModal();
  }
}

function _authModalHTML() {
  return `
<div class="modal-bg" id="auth-modal" onclick="if(event.target===this)closeAuthModal()">
  <div class="modal">
    <h2>Conectar con GitHub</h2>
    <p>Necesitás un Personal Access Token (PAT) para que el site pueda
    disparar workflows y guardar tus textos editados. Una sola configuración
    por dispositivo/navegador.</p>
    <h3>Cómo crear el token (3 pasos):</h3>
    <ol>
      <li>Abrí <a href="https://github.com/settings/tokens/new?scopes=repo,workflow&description=Informativa%20site"
        target="_blank">esta página</a> (los scopes <code>repo</code> y
        <code>workflow</code> ya vienen pre-seleccionados).</li>
      <li>Expiration: elegí lo que prefieras (90 días o "No expiration").</li>
      <li>Click "Generate token" abajo, copiá el token (empieza con <code>ghp_…</code>).</li>
    </ol>
    <h3>Pegá tu token acá:</h3>
    <input type="password" id="pat-input" placeholder="ghp_..." autocomplete="off">
    <div id="auth-result"></div>
    <div class="actions">
      <button class="btn secondary" onclick="clearToken()">Borrar token</button>
      <button class="btn secondary" onclick="closeAuthModal()">Cancelar</button>
      <button class="btn" onclick="saveToken()">Guardar</button>
    </div>
    <p style="font-size:11px; color:#888; margin-top:14px;">
      El token se guarda en localStorage de este navegador. Nunca se
      envía a otro lado. Si compartís el dispositivo, usá "Borrar token"
      al terminar.</p>
  </div>
</div>
  `;
}

function _topbar(title, sub) {
  return `
<header class="topbar">
  <div>
    <h1>${title}</h1>
    <div class="meta">${sub}</div>
  </div>
  <div class="auth">
    <span id="auth-dot" class="dot no"></span>
    <span id="auth-txt">…</span>
    <button id="auth-btn" onclick="openAuthModal()">…</button>
  </div>
</header>
  `;
}
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

    page_js = _COMMON_JS.replace("__REPO_OWNER__", REPO_OWNER) \
                       .replace("__REPO_NAME__", REPO_NAME) \
                       .replace("__BRANCH__", BRANCH)
    site_js = """
const AS_OF = "__AS_OF__";
const SLUGS = __SLUGS__;
const LSK = `informativa:${AS_OF}:edits`;
const MSG_PATH = `docs/informativa/outputs/${AS_OF}/messages.json`;

function loadEdits() {
  try { return JSON.parse(localStorage.getItem(LSK) || "{}"); }
  catch { return {}; }
}
function saveEdits(e) { localStorage.setItem(LSK, JSON.stringify(e)); }

function setStatus(html, kind) {
  const b = document.getElementById("status-banner");
  if (!html) { b.style.display = "none"; return; }
  b.style.display = "flex";
  b.className = "status-banner" + (kind ? " " + kind : "");
  b.innerHTML = (kind === "in_progress" ? '<div class="spinner"></div>' : "") + html;
}

document.addEventListener("DOMContentLoaded", () => {
  updateAuthUI();
  const edits = loadEdits();
  SLUGS.forEach(slug => {
    const ta = document.getElementById("edit-" + slug);
    if (!ta) return;
    if (edits[slug]) ta.value = edits[slug];
    ta.addEventListener("input", () => {
      const e = loadEdits(); e[slug] = ta.value; saveEdits(e);
      setStatus(`Cambios guardados en este navegador a las ${new Date().toLocaleTimeString()}`, "");
    });
  });
});

async function saveToGitHub() {
  if (!GH.token()) { openAuthModal(); return; }
  setStatus("Guardando textos en GitHub…", "in_progress");
  try {
    // 1) Leer messages.json actual + SHA
    const cur = await GH.getFile(MSG_PATH);
    if (!cur) throw new Error("No se encontró messages.json en el repo");
    const blobOld = JSON.parse(atob(cur.content.replace(/\\s/g, "")));
    const edits = loadEdits();
    const newBlob = {
      as_of: blobOld.as_of,
      slides: blobOld.slides.map(s => ({
        slug: s.slug, title: s.title, proposed: s.proposed,
        edited: edits[s.slug] || s.edited || null,
      })),
    };
    const newContent = btoa(unescape(encodeURIComponent(
      JSON.stringify(newBlob, null, 2))));
    // 2) Verificar si hubo cambios reales
    if (newContent === cur.content.replace(/\\s/g, "")) {
      setStatus("No hay cambios para guardar.", "success");
      return;
    }
    // 3) PUT
    await GH.putFile(MSG_PATH, newContent,
      `Informativa: editar textos del corte ${AS_OF}`, cur.sha);
    setStatus(`Textos guardados en GitHub ✓`, "success");
  } catch (e) {
    setStatus(`Error guardando: ${e.message}`, "error");
  }
}

async function buildDeck() {
  if (!GH.token()) { openAuthModal(); return; }
  if (!confirm(`Esto va a:\\n1) Guardar tus textos editados en GitHub.\\n2) Disparar el workflow que regenera el PPT.\\nTarda ~30s. ¿Seguir?`)) return;
  setStatus("Guardando textos antes de compilar…", "in_progress");
  try {
    await saveToGitHub();
    setStatus("Disparando workflow Build deck…", "in_progress");
    await GH.triggerWorkflow("build-deck.yml", { as_of: AS_OF });
    setStatus("Workflow disparado. Esperando que termine…", "in_progress");
    pollRun("build-deck.yml", "PPT regenerado", "Build falló");
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  }
}

async function pollRun(workflow_id, okMsg, failMsg) {
  let last = await GH.getLatestRun(workflow_id);
  const startedAt = Date.now();
  const initialId = last && last.id;
  const tick = async () => {
    try {
      const r = await GH.getLatestRun(workflow_id);
      if (!r) return setTimeout(tick, 4000);
      // Esperar a que aparezca el run NUEVO (id distinto del inicial)
      if (r.id === initialId && Date.now() - startedAt < 30000) {
        return setTimeout(tick, 3000);
      }
      if (r.status !== "completed") {
        setStatus(`${workflow_id} ${r.status}…`, "in_progress");
        return setTimeout(tick, 5000);
      }
      if (r.conclusion === "success") {
        const url = `${PAGES}/outputs/${AS_OF}/deck_informativa_${AS_OF}.pptx`;
        setStatus(`${okMsg} ✓ &nbsp; <a href="${url}" target="_blank" style="color:#16a34a; font-weight:bold;">Descargar PPT ⬇</a>`,
                  "success");
      } else {
        setStatus(`${failMsg}: ${r.conclusion}. <a href="${r.html_url}" target="_blank">Ver logs</a>`, "error");
      }
    } catch (e) {
      setStatus(`Error consultando estado: ${e.message}`, "error");
    }
  };
  setTimeout(tick, 5000);
}

function resetEdits() {
  if (!confirm("¿Restaurar TODOS los textos propuestos y descartar tus ediciones locales?")) return;
  localStorage.removeItem(LSK);
  location.reload();
}
"""
    site_js = site_js.replace("__AS_OF__", str(as_of)) \
                     .replace("__SLUGS__", json.dumps(slugs))

    page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informativa · corte {as_of}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
{_topbar_html(f"Pieza informativa · corte {as_of}",
              f"Revisá las {len(slides_html)} láminas · editá los textos · generá el PPT desde acá")}
<div class="container">
  <div id="status-banner" class="status-banner" style="display:none"></div>
  <div style="margin-bottom: 14px;">
    <a href="../../" style="color:#2a6fb3; font-size:13px;">← Volver a cortes</a> &nbsp;|&nbsp;
    <a href="deck_informativa_{as_of}.pptx" style="color:#2a6fb3; font-size:13px;">⬇ Descargar PPT actual</a>
  </div>
  {''.join(slides_html)}
</div>
<div class="controls">
  <button class="btn" onclick="buildDeck()">⚡ Generar PPT con estos textos</button>
  <button class="btn secondary" onclick="saveToGitHub()">💾 Solo guardar textos en GitHub</button>
  <button class="btn secondary" onclick="resetEdits()">↺ Restaurar propuestos</button>
  <div class="note">Tus cambios se guardan automáticamente en el navegador</div>
</div>
<div class="disclaimer">Documento informativo con fines analíticos. No constituye recomendación de inversión.</div>
{_AUTH_MODAL_HTML_PLACEHOLDER}
<script>{page_js}
{site_js}
</script>
</body>
</html>"""

    out = base / "site.html"
    out.write_text(page, encoding="utf-8")
    return out


# Helpers para componer HTML reutilizable
def _topbar_html(title: str, sub: str) -> str:
    return f"""
<header class="topbar">
  <div>
    <h1>{title}</h1>
    <div class="meta">{sub}</div>
  </div>
  <div class="auth">
    <span id="auth-dot" class="dot no"></span>
    <span id="auth-txt">…</span>
    <button id="auth-btn" onclick="openAuthModal()">…</button>
  </div>
</header>
""".strip()


_AUTH_MODAL_HTML_PLACEHOLDER = """
<div class="modal-bg" id="auth-modal" onclick="if(event.target===this)closeAuthModal()">
  <div class="modal">
    <h2>Conectar con GitHub</h2>
    <p>Necesitás un Personal Access Token (PAT) para que el site pueda
    disparar workflows y guardar tus textos editados. Una sola configuración
    por dispositivo/navegador.</p>
    <h3>Cómo crear el token (3 pasos):</h3>
    <ol>
      <li>Abrí <a href="https://github.com/settings/tokens/new?scopes=repo,workflow&description=Informativa%20site"
        target="_blank">esta página</a> (los scopes <code>repo</code> y
        <code>workflow</code> ya vienen pre-seleccionados).</li>
      <li>Expiration: elegí lo que prefieras (90 días o "No expiration").</li>
      <li>Click "Generate token" abajo, copiá el token (empieza con <code>ghp_…</code>).</li>
    </ol>
    <h3>Pegá tu token acá:</h3>
    <input type="password" id="pat-input" placeholder="ghp_..." autocomplete="off">
    <div id="auth-result"></div>
    <div class="actions">
      <button class="btn secondary" onclick="clearToken()">Borrar token</button>
      <button class="btn secondary" onclick="closeAuthModal()">Cancelar</button>
      <button class="btn" onclick="saveToken()">Guardar</button>
    </div>
    <p style="font-size:11px; color:#888; margin-top:14px;">
      El token se guarda en localStorage de este navegador. Nunca se
      envía a otro lado. Si compartís el dispositivo, usá "Borrar token"
      al terminar.</p>
  </div>
</div>
""".strip()


def render_index() -> Path:
    outputs_dir = Path("docs/informativa/outputs")
    cortes = []
    if outputs_dir.exists():
        for d in sorted(outputs_dir.iterdir(), reverse=True):
            if d.is_dir() and (d / "site.html").exists():
                cortes.append(d.name)

    cards = "\n".join(
        f'<li><a href="outputs/{c}/site.html">Corte {c}</a><span class="meta">→ revisar</span></li>'
        for c in cortes
    ) or "<li><em>Sin cortes disponibles. Click \"Actualizar datos ahora\" arriba.</em></li>"

    page_js = _COMMON_JS.replace("__REPO_OWNER__", REPO_OWNER) \
                       .replace("__REPO_NAME__", REPO_NAME) \
                       .replace("__BRANCH__", BRANCH)
    index_js = """
function setStatus(html, kind) {
  const b = document.getElementById("status-banner");
  if (!html) { b.style.display = "none"; return; }
  b.style.display = "flex";
  b.className = "status-banner" + (kind ? " " + kind : "");
  b.innerHTML = (kind === "in_progress" ? '<div class="spinner"></div>' : "") + html;
}

document.addEventListener("DOMContentLoaded", () => {
  updateAuthUI();
  const input = document.getElementById("bbg-upload-input");
  const btn = document.getElementById("bbg-upload-btn");
  if (input && btn) {
    input.addEventListener("change", () => {
      btn.disabled = !input.files || input.files.length === 0;
    });
  }
});

async function uploadBloomberg() {
  if (!GH.token()) { openAuthModal(); return; }
  const input = document.getElementById("bbg-upload-input");
  if (!input || !input.files || input.files.length === 0) return;
  const f = input.files[0];
  if (!f.name.endsWith(".xlsx")) {
    setStatus("El archivo debe ser .xlsx (la plantilla Bloomberg).", "error");
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  const path = `ProyectoTasasMercantil/cortes/${today}/BloombergTemplate.xlsx`;
  setStatus(`Subiendo ${f.name} a ${path}…`, "in_progress");
  try {
    // Leer archivo como base64
    const base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        // result es data URL: "data:...;base64,XXX..."
        const b64 = result.split(",")[1];
        resolve(b64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(f);
    });
    // Si existe ya, necesitamos el SHA
    let sha = undefined;
    try {
      const cur = await GH.getFile(path);
      if (cur) sha = cur.sha;
    } catch {}
    await GH.putFileBinary(path, base64,
      `Bloomberg: subir Excel mensual del corte ${today}`, sha);
    setStatus("Excel subido ✓ Disparando workflow refresh para procesarlo…",
              "in_progress");
    await GH.triggerWorkflow("refresh-informativa.yml", { as_of: today });
    setStatus("Workflow disparado. Esperando ~2 minutos…", "in_progress");
    pollRunIndex("refresh-informativa.yml");
  } catch (e) {
    setStatus(`Error subiendo Excel: ${e.message}`, "error");
  }
}

async function refreshData() {
  if (!GH.token()) { openAuthModal(); return; }
  if (!confirm("Esto dispara el workflow que descarga datos frescos\\n(FRED, EODHD, SEP Fed) y regenera todas las láminas.\\nTarda ~2 minutos. ¿Seguir?")) return;
  setStatus("Disparando workflow Refresh informativa…", "in_progress");
  try {
    await GH.triggerWorkflow("refresh-informativa.yml", { as_of: "" });
    setStatus("Workflow disparado. Esperando ~2 minutos…", "in_progress");
    pollRunIndex("refresh-informativa.yml");
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  }
}

async function pollRunIndex(workflow_id) {
  let initial = await GH.getLatestRun(workflow_id);
  const initialId = initial && initial.id;
  const startedAt = Date.now();
  const tick = async () => {
    try {
      const r = await GH.getLatestRun(workflow_id);
      if (!r || r.id === initialId) {
        if (Date.now() - startedAt > 30000)
          return setStatus("Esperando que el workflow arranque…", "in_progress");
        return setTimeout(tick, 3000);
      }
      if (r.status !== "completed") {
        setStatus(`${workflow_id} ${r.status}…`, "in_progress");
        return setTimeout(tick, 6000);
      }
      if (r.conclusion === "success") {
        setStatus(`Refresh completado ✓ &nbsp; <a href="javascript:location.reload()" style="color:#16a34a; font-weight:bold;">Recargar página</a> para ver el nuevo corte`, "success");
      } else {
        setStatus(`Refresh falló: ${r.conclusion}. <a href="${r.html_url}" target="_blank">Ver logs</a>`, "error");
      }
    } catch (e) {
      setStatus(`Error consultando estado: ${e.message}`, "error");
    }
  };
  setTimeout(tick, 5000);
}
"""

    page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pieza informativa Mercantil</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
{_topbar_html("Pieza informativa Mercantil",
              "Refresh de datos · revisión · edición · armado del PPT — todo desde acá")}
<div class="container">
  <div id="status-banner" class="status-banner" style="display:none"></div>

  <div class="card">
    <h2>1 · Actualizar datos automáticos</h2>
    <p style="font-size: 14px; color:#555;">
    Descarga los últimos datos PÚBLICOS (FRED, EODHD, último SEP de la Fed)
    y regenera todas las láminas, mensajes propuestos y el deck. Tarda ~2
    minutos. También corre automáticamente el día 1° de cada mes a las 7 AM
    Colombia.</p>
    <button class="btn success" onclick="refreshData()">⚡ Actualizar datos ahora</button>
  </div>

  <div class="card">
    <h2>2 · Subir Excel Bloomberg (opcional)</h2>
    <p style="font-size: 14px; color:#555;">
    Para enriquecer las láminas con datos que <b>no están en FRED ni EODHD</b>
    (forwards FX 5 años, CDS Panamá, swap OIS 1Y/3Y, encuesta economistas),
    correr la plantilla
    <a href="https://github.com/{REPO_OWNER}/{REPO_NAME}/raw/{BRANCH}/ProyectoTasasMercantil/plantilla_bloomberg/BloombergTemplate_TasasMercantil.xlsx"
       target="_blank">BloombergTemplate_TasasMercantil.xlsx</a> en
    Bloomberg, guardarla con valores, y subirla acá. Se procesa y dispara
    refresh automático. <b>Operación 1 vez al mes</b>.</p>
    <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
      <input type="file" id="bbg-upload-input" accept=".xlsx"
             style="font-size: 14px;">
      <button class="btn" id="bbg-upload-btn" onclick="uploadBloomberg()" disabled>
        📥 Subir y procesar
      </button>
    </div>
  </div>

  <div class="card">
    <h2>3 · Cortes disponibles para revisar y armar PPT</h2>
    <ul class="cortes">{cards}</ul>
  </div>

</div>
<div class="disclaimer">Documento informativo con fines analíticos. No constituye recomendación de inversión.</div>
{_AUTH_MODAL_HTML_PLACEHOLDER}
<script>{page_js}
{index_js}
</script>
</body>
</html>"""

    ROOT_HTML.parent.mkdir(parents=True, exist_ok=True)
    ROOT_HTML.write_text(page, encoding="utf-8")
    return ROOT_HTML
