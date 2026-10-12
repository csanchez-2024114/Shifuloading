// Panel de metricas (solo desarrollo). Reusa la sesion del chat: mismo token y refresh token en localStorage.
const API = "/api/v1";
let token = localStorage.getItem("shifu_token");
const $ = (id) => document.getElementById(id);
// Los comentarios y respuestas son texto del usuario/modelo: siempre escapados antes de ir a innerHTML.
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function refresh() {
  const rt = localStorage.getItem("shifu_refresh");
  if (!rt) return false;
  const r = await fetch(`${API}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) });
  if (!r.ok) return false;
  const j = await r.json();
  token = j.access_token;
  localStorage.setItem("shifu_token", token);
  localStorage.setItem("shifu_refresh", j.refresh_token);
  return true;
}
async function authed(path) {
  const go = () => fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  let r = await go();
  if (r.status === 401 && (await refresh())) r = await go();
  return r;
}

const pct = (v) => (v == null ? "–" : `${v}%`);
const usd = (v) => `$${Number(v).toFixed(4)}`;
const COLS = [
  ["Resp.", (r) => r.replies], ["USD total", (r) => usd(r.usd_total)], ["USD prom.", (r) => usd(r.usd_avg)], ["USD p95", (r) => usd(r.usd_p95)],
  ["Intentos", (r) => r.attempts_avg ?? "–"], ["Rechazo", (r) => pct(r.rejection_rate)], ["Agotadas", (r) => pct(r.exhausted_rate)],
  ["👍", (r) => r.up], ["👎", (r) => r.down], ["% 👍", (r) => pct(r.up_pct)],
  ["Escrituras", (r) => r.writes], ["% ok", (r) => pct(r.writes_ok_pct)], ["Confirm.", (r) => r.confirmed], ["Supuestas", (r) => r.assumed],
  ["Chequeos que fallan", (r) => r.top_failing.map((f) => `${f.name} (${f.count})`).join(", ") || "–", true],
];

function table(el, firstHead, key, rows) {
  if (!rows.length) { el.innerHTML = '<p class="note" style="padding:8px 10px;margin:0">Sin datos en este rango.</p>'; return; }
  const head = `<tr><th>${firstHead}</th>${COLS.map((c) => `<th>${c[0]}</th>`).join("")}</tr>`;
  const body = rows.map((r) => `<tr><td>${esc(r[key])}</td>${COLS.map((c) => `<td${c[2] ? ' class="l"' : ""}>${esc(c[1](r))}</td>`).join("")}</tr>`).join("");
  el.innerHTML = `<table>${head}${body}</table>`;
}

async function load() {
  $("msg").textContent = "Cargando…";
  const r = await authed(`/dev/metrics?days=${$("days").value}`);
  if (r.status === 401) { $("msg").innerHTML = 'Sin sesión: entra primero en <a class="link" href="index.html">el chat</a>.'; return; }
  if (!r.ok) { $("msg").textContent = r.status === 404 ? "Falta SHIFU_DEV_UI=1 en el backend." : `Error ${r.status}`; return; }
  const d = await r.json();
  $("msg").textContent = d.truncated ? "Aviso: se alcanzó el tope de 20.000 documentos; los números son parciales." : "";
  table($("byVersion"), "Versión", "version", d.by_version);
  table($("byDay"), "Día", "day", d.by_day);
  $("down").innerHTML = d.recent_down.length
    ? `<table><tr><th>Fecha</th><th>Versión</th><th>Comentario</th><th>Respuesta</th><th>Conversación</th></tr>${d.recent_down
        .map((x) => `<tr><td>${esc(x.date)}</td><td>${esc(x.version)}</td><td class="l">${esc(x.comment)}</td><td class="l">${esc(x.reply)}</td><td>${esc(x.conversation_id)}</td></tr>`)
        .join("")}</table>`
    : '<p class="note" style="padding:8px 10px;margin:0">Sin 👎 con comentario.</p>';
}

$("days").onchange = load;
load();
