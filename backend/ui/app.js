// Cliente minimo del chat: login/registro, lista de conversaciones, /api/v1/chat/stream (SSE por fetch).
const $ = (id) => document.getElementById(id);
const API = "/api/v1";
let registering = false;
let token = localStorage.getItem("shifu_token");
let conv = localStorage.getItem("shifu_conv") || newId();
let convQuality = [];
let convUsage = [];   // gasto real de cada respuesta de la conversacion abierta // calidad de cada respuesta de la conversacion abierta (para el resumen de intentos)

function newId() {
  const id = crypto.randomUUID();
  localStorage.setItem("shifu_conv", id);
  return id;
}

function show() {
  for (const id of ["chat", "trace", "side"]) $(id).hidden = !token;
  $("auth").hidden = !!token;
  if (token) openConv(conv); // carga el historial de la conversacion actual (y refresca la lista)
}

$("toggle").onclick = () => {
  registering = !registering;
  $("nameFields").hidden = !registering;
  $("submitBtn").textContent = registering ? "Registrarme" : "Entrar";
  $("toggle").textContent = registering ? "Ya tengo cuenta" : "Crear cuenta nueva";
};

$("authForm").onsubmit = async (e) => {
  e.preventDefault();
  $("authError").textContent = "";
  const body = { email: $("email").value, password: $("password").value };
  if (registering) Object.assign(body, { name: $("name").value, last_name: $("last_name").value });
  const r = await fetch(`${API}/auth/${registering ? "register" : "login"}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $("authError").textContent = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail || j); return; }
  token = j.access_token;
  localStorage.setItem("shifu_token", token);
  localStorage.setItem("shifu_refresh", j.refresh_token);
  show();
};

// La conversacion guardada es de este usuario: el siguiente que entre empieza una nueva.
$("logout").onclick = () => { localStorage.removeItem("shifu_token"); token = null; conv = newId(); clearPanels(); show(); };

// El access token dura poco: se renueva con el refresh token (que rota en cada uso). Varias peticiones que caducan a la
// vez comparten UNA renovacion: si cada una usaba el refresh token, la primera lo rotaba, las demas recibian 401 y se
// cerraba la sesion.
let refreshing = null;
function refresh() {
  refreshing ??= doRefresh().finally(() => { refreshing = null; });
  return refreshing;
}
async function doRefresh() {
  const rt = localStorage.getItem("shifu_refresh");
  if (!rt) return false;
  const r = await fetch(`${API}/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }),
  });
  if (!r.ok) return false;
  const j = await r.json();
  token = j.access_token;
  localStorage.setItem("shifu_token", token);
  localStorage.setItem("shifu_refresh", j.refresh_token);
  return true;
}

// fetch con el token puesto; si vence, renueva y reintenta una vez.
async function authed(path, init = {}) {
  const go = () => fetch(`${API}${path}`, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${token}` } });
  let r = await go();
  if (r.status === 401 && (await refresh())) r = await go();
  return r;
}

// ── Centinelas (panel derecho) ────────────────────────────────────────────────

const S_ICON = { approved: "✓", retry: "↻", exhausted: "⚠", skipped: "–", blocked: "⛔" };
const S_TEXT = { approved: "aprobó", retry: "rechazó → el agente reformula", exhausted: "rechazó y se agotaron los reintentos (se entregó igual)", skipped: "no evaluó", blocked: "bloqueó el turno" };

// Un centinela = un control que mira el turno y emite veredicto (validadores de apps y evaluador de calidad).
function addSentinel(ev) {
  const d = document.createElement("div");
  d.className = "s " + ev.action;
  const head = document.createElement("b");
  head.textContent = `${S_ICON[ev.action] || "•"} ${ev.node}` + (ev.attempt ? ` · intento ${ev.attempt}/${ev.max_attempts}` : "") + ` — ${S_TEXT[ev.action] || ev.action}`;
  d.append(head);
  const rows = [
    ...(ev.checks || []).map((c) => [c.passed, `${c.name}${c.severity === "minor" ? " (menor, no bloquea)" : ""}: ${c.note}`, c.severity === "minor"]),
    ...(ev.items || []).map((i) => [i.status === "ok", `${i.app}: ${i.status}${i.reason ? " (" + i.reason + ")" : ""}`]),
  ];
  if (rows.length) {
    const ul = document.createElement("ul");
    for (const [ok, text, minor] of rows) {
      const li = document.createElement("li");
      li.className = ok ? "" : "bad";
      li.textContent = (ok ? (minor ? "~ " : "✓ ") : "✗ ") + text;
      ul.append(li);
    }
    d.append(ul);
  }
  for (const [k, label] of [["feedback", "Corrección enviada al agente"], ["reason", "Motivo"]]) {
    if (!ev[k]) continue;
    const p = document.createElement("div");
    p.className = "fb";
    p.textContent = `${label}: ${ev[k]}`;
    d.append(p);
  }
  $("sentinelLog").append(d);
}

function addTrace(ev) {
  const d = document.createElement("details");
  d.className = "t " + ev.kind;
  const s = document.createElement("summary");
  s.innerHTML = `<b></b><span></span><span class="ms"></span>`;
  s.children[0].textContent = ev.kind === "llm" ? "LLM" : "nodo";
  s.children[1].textContent = ev.node || "";
  s.children[2].textContent = `${ev.tokens ? ev.tokens + " tok · " : ""}${ev.ms} ms`;
  d.append(s);
  for (const [k, h] of [["prompt", "Prompt"], ["output", "Salida"]]) {
    if (!ev[k]) continue;
    const p = document.createElement("pre");
    p.dataset.h = h;
    p.textContent = ev[k];
    d.append(p);
  }
  $("traceLog").append(d);
}

// ── Mensajes y calidad por respuesta ──────────────────────────────────────────

function bubble(cls, text = "") {
  const d = document.createElement("div");
  d.className = "m " + cls;
  const t = document.createElement("div");
  t.className = "txt";
  t.textContent = text;
  d.append(t);
  $("log").append(d);
  d.scrollIntoView({ block: "end" });
  return d;
}
const setText = (el, text) => { el.querySelector(".txt").textContent = text; };

// Insignia con los intentos que gasto la respuesta; al hacer clic muestra por que se rechazaron los anteriores.
function addQuality(el, q) {
  if (!q) return;
  const b = document.createElement("details");
  b.className = "q " + (q.final === "exhausted" ? "bad" : q.rejections ? "warn" : "ok");
  const s = document.createElement("summary");
  s.textContent = q.final === "exhausted"
    ? `⚠ ${q.attempts} intentos — se entregó ${q.delivered_attempt && q.delivered_attempt !== q.attempts ? `el intento ${q.delivered_attempt} (el de menos fallas)` : "el último"}, con fallas`
    : q.rejections ? `↻ ${q.attempts} intentos · ${q.rejections} rechazo${q.rejections > 1 ? "s" : ""}` : "✓ 1 intento";
  b.append(s);
  for (const e of q.evals || []) {
    const row = document.createElement("div");
    row.textContent = `Intento ${e.attempt}: ${e.action}` + (e.failed?.length ? " — " + e.failed.map((f) => `${f.name} (${f.note})`).join("; ") : "");
    b.append(row);
  }
  el.append(b);
}

// 👍/👎 por respuesta: POST /me/feedback (votar de nuevo reemplaza el voto). La version sale del usage de esa respuesta.
function addRating(el, text, version) {
  if (!text) return;
  const d = document.createElement("div");
  d.className = "rate";
  for (const [rating, icon] of [["up", "👍"], ["down", "👎"]]) {
    const b = document.createElement("button");
    b.textContent = icon;
    b.title = rating === "up" ? "Buena respuesta" : "Mala respuesta";
    b.onclick = async () => {
      const comment = rating === "down" ? (prompt("¿Qué estuvo mal? (opcional)") || "") : "";
      const r = await authed("/me/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conv, reply: text, rating, comment, agent_version: version || "" }) });
      if (r.ok) { d.querySelectorAll("button").forEach((x) => x.classList.remove("on")); b.classList.add("on"); }
    };
    d.append(b);
  }
  el.append(d);
}

// Gasto real de una peticion (tokens que reporta el proveedor x precios de app/billing/model_prices.json).
function addUsage(el, u) {
  if (!u) return;
  const d = document.createElement("details");
  d.className = "q usage";
  const s = document.createElement("summary");
  s.textContent = `$${u.usd.toFixed(4)} · ${u.calls.length} llamadas · ${(u.input + u.output).toLocaleString()} tokens${u.unpriced ? " · " + u.unpriced + " sin precio" : ""}${u.agent_version ? " · v" + u.agent_version : ""}`;
  d.append(s);
  for (const c of u.calls) {
    const row = document.createElement("div");
    row.textContent = `${c.node || "?"} · ${c.model} · ${c.input.toLocaleString()} in / ${c.output.toLocaleString()} out · ${c.usd == null ? "sin precio" : "$" + c.usd.toFixed(5)}`;
    d.append(row);
  }
  el.append(d);
}

function renderStats() {
  const n = convQuality.length;
  const attempts = convQuality.reduce((a, q) => a + q.attempts, 0);
  const rej = convQuality.reduce((a, q) => a + q.rejections, 0);
  const usd = convUsage.reduce((a, u) => a + u.usd, 0);
  $("convStats").textContent = (n ? `${n} respuesta${n > 1 ? "s" : ""} · ${attempts} intentos · ${rej} rechazo${rej === 1 ? "" : "s"}` : "sin respuestas evaluadas")
    + (convUsage.length ? ` · $${usd.toFixed(4)}` : "");
}

function renderConvHeader() {
  $("convId").textContent = conv;
  renderStats();
}

function clearPanels() {
  $("log").replaceChildren();
  $("sentinelLog").replaceChildren();
  $("traceLog").replaceChildren();
  $("trace").scrollTop = 0;
}

// ── Lista de conversaciones (panel izquierdo) ─────────────────────────────────

$("convId").onclick = () => navigator.clipboard?.writeText(conv);

$("newConv").onclick = () => {
  conv = newId();
  convQuality = [];
  convUsage = [];
  clearPanels();
  renderConvHeader();
  loadList();
};

async function loadList() {
  const r = await authed("/me/conversations?limit=50");
  if (!r.ok) return;
  const rows = (await r.json()).data || [];
  $("convList").replaceChildren(...rows.map((c) => {
    const d = document.createElement("div");
    d.className = "ci" + (c.id === conv ? " on" : "");
    const when = c.updated_at ? new Date(c.updated_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "";
    d.innerHTML = "<b></b><span></span>";
    d.children[0].textContent = c.title || "Conversación";
    d.children[1].textContent = `${c.id.slice(0, 8)} · ${c.message_count} msgs · ${when}`;
    d.title = c.id;
    d.onclick = () => openConv(c.id);
    return d;
  }));
  loadMemories();
  loadNotices();
}

setInterval(() => { if (!$("side").hidden) loadNotices(); }, 30000);  // este repo no monta el WebSocket de eventos: la UI de pruebas sondea

// Avisos (user_notifications): corridas de workflows, disparadores detenidos, compromisos que vencen. Clic = leido.
async function loadNotices() {
  const r = await authed("/me/notifications?limit=8");
  if (!r.ok) return;
  const rows = (await r.json()).notifications;
  $("noticeList").replaceChildren(...(rows.length ? rows.map((n) => {
    const d = document.createElement("div");
    d.className = "mi";
    d.style.opacity = n.read ? 0.5 : 1;
    d.title = n.read ? "Leído" : "Clic para marcar como leído";
    d.textContent = `${n.title}: ${n.message}`;
    d.onclick = async () => { await authed(`/me/notifications/${n.id}/read`, { method: "PATCH" }); loadNotices(); };
    return d;
  }) : [Object.assign(document.createElement("div"), { className: "mi", textContent: "Sin avisos" })]));
}

// Lo que el agente aprendio del usuario (memory_learner); el ✕ lo archiva y deja de usarse desde el siguiente turno.
async function loadMemories() {
  const r = await authed("/me/memories");
  if (!r.ok) return;
  const rows = (await r.json()).memories.filter((m) => m.status === "active");
  $("memList").replaceChildren(...(rows.length ? rows.map((m) => {
    const d = document.createElement("div");
    d.className = "mi";
    d.innerHTML = "<span></span><button class='link' title='Olvidar'>✕</button>";
    d.children[0].textContent = `${m.key}: ${m.value}`;
    d.children[1].onclick = async () => { await authed(`/me/memories/${m.id}`, { method: "DELETE" }); loadMemories(); };
    return d;
  }) : [Object.assign(document.createElement("div"), { className: "mi", textContent: "Nada todavía" })]));
}

async function openConv(id) {
  conv = id;
  localStorage.setItem("shifu_conv", id);
  convQuality = [];
  convUsage = [];
  clearPanels();
  const r = await authed(`/me/conversations/${id}/messages`);
  if (r.ok) {
    const connected = await connectedProviders(); // un boton guardado de una app que ya se conecto sale como "conectada"
    const rows = (await r.json()).data || [];
    if (conv !== id) return; // el usuario ya abrio otra conversacion mientras esto cargaba: no pintar encima
    for (const m of rows) {
      const el = bubble(m.role === "user" ? "me" : "ai", m.content);
      if (m.role !== "user" && m.quality) { addQuality(el, m.quality); convQuality.push(m.quality); }
      if (m.role !== "user" && m.usage) { addUsage(el, m.usage); convUsage.push(m.usage); }
      if (m.role !== "user") renderActions(el, m.ui_actions, connected);
      if (m.role !== "user") addRating(el, m.content, m.usage?.agent_version);
    }
  }
  renderConvHeader();
  loadList();
}

// ── UI actions: el agente pide algo al usuario y la UI lo pinta (hoy: connect_app) ──

const REASON_TEXT = { not_connected: "no está conectada", expired: "la conexión venció", revoked: "se revocó el acceso" };

// Apps con una cuenta usable (misma regla que auth_validator: active / needs_refresh).
async function connectedProviders() {
  const r = await authed("/accounts/");
  if (!r.ok) return new Set();
  return new Set((await r.json()).filter((a) => ["active", "needs_refresh"].includes(a.status)).map((a) => a.provider.toLowerCase()));
}

// `connected`: apps ya conectadas al pintar (historial). En vivo va vacio y el boton aparece pendiente.
function renderActions(el, actions, connected) {
  for (const a of actions || []) {
    if (a.type !== "connect_app") continue; // render_workflow / open_trigger: pendiente
    const card = document.createElement("div");
    card.className = "act";
    el.append(card);
    if (connected.has(a.app.toLowerCase())) { card.classList.add("done"); card.textContent = `✓ ${a.app} conectada`; continue; }
    drawConnectCard(card, a);
  }
}

function drawConnectCard(card, a) {
  card.replaceChildren();
  const msg = document.createElement("div");
  msg.textContent = `${a.app}: ${REASON_TEXT[a.reason] || a.reason}`;
  const row = document.createElement("div");
  row.className = "row";
  const note = document.createElement("div");
  note.className = "note";
  const add = (label, fn, cls) => {
    const b = document.createElement("button");
    b.textContent = label;
    if (cls) b.className = cls;
    b.onclick = async () => { b.disabled = true; note.className = "note"; note.textContent = ""; try { await fn(); } catch (e) { note.className = "note err"; note.textContent = e.message; } b.disabled = false; };
    row.append(b);
  };
  card.append(msg, row, note);

  if (a.auth_type === "apikey") {
    const key = document.createElement("input");
    key.type = "password";
    key.placeholder = "API key";
    row.append(key);
    add("Guardar", async () => {
      const r = await authed("/me/secrets", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `${a.app} (prueba)`, service: a.app, secret_value: key.value }) });
      if (!r.ok) throw new Error(await errText(r));
      connectedNow(card, a);
    });
  } else {
    add(a.reason === "not_connected" ? "Conectar" : "Reconectar", async () => {
      // El agente emite /auth/<app>/login; en este backend la ruta real es /integrations/<app>/login y exige Bearer.
      if (!a.auth_url.startsWith("/auth/")) throw new Error("Esta app no tiene ruta de conexión en este backend.");
      const r = await authed(a.auth_url.replace("/auth/", "/integrations/"));
      if (!r.ok) throw new Error(await errText(r));
      const url = (await r.json()).url;
      if (!url) throw new Error("El backend no devolvió la URL de autorización.");
      const popup = window.open(url, "_blank", "width=520,height=720");
      note.textContent = "Esperando que termines de autorizar…";
      await waitConnected(a.app, popup);
      connectedNow(card, a);
    });
  }
  add("Simular conexión", async () => {
    const r = await authed(`/dev/connect/${encodeURIComponent(a.app.toLowerCase())}`, { method: "POST" });
    if (!r.ok) throw new Error(await errText(r));
    connectedNow(card, a);
  }, "link");
}

async function errText(r) {
  const j = await r.json().catch(() => ({}));
  return typeof j.detail === "string" ? j.detail : `Error ${r.status}`;
}

// Sondea las cuentas hasta que aparezca la app (o se cierre el popup sin conectar).
async function waitConnected(app, popup) {
  const limit = Date.now() + 3 * 60 * 1000;
  while (Date.now() < limit) {
    await new Promise((res) => setTimeout(res, 2000));
    if ((await connectedProviders()).has(app.toLowerCase())) return;
    if (popup?.closed) {
      if ((await connectedProviders()).has(app.toLowerCase())) return;
      throw new Error("Cerraste la ventana sin conectar.");
    }
  }
  throw new Error("Se agotó el tiempo esperando la conexión.");
}

// Conectada en vivo: tarjeta lista y se le avisa al agente para que retome lo pausado.
function connectedNow(card, a) {
  card.className = "act done";
  card.textContent = `✓ ${a.app} conectada`;
  // Redactado como aviso, no como peticion: "Ya conecte gmail" se clasificaba como "quiero conectar otra cuenta" y
  // volvia a salir el boton de conectar.
  send(`[Aviso automático de la interfaz] La cuenta de ${a.app} ya quedó conectada correctamente; no hay que conectar nada más de ${a.app}.`, true);
}

// ── Envio ─────────────────────────────────────────────────────────────────────

// Adjuntos: cada archivo se sube primero (POST /files) y el mensaje lleva solo sus file_id.
let attached = [];
function paintAttached(note = "") {
  $("attached").textContent = attached.map((f) => `📎 ${f.name}`).join("   ") + (note ? `   ${note}` : "");
}
$("attachBtn").onclick = () => $("attach").click();
$("attach").onchange = async () => {
  for (const file of $("attach").files) {
    paintAttached(`subiendo ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    const r = await authed("/files/", { method: "POST", body: form });
    const j = await r.json().catch(() => ({}));
    if (r.ok) attached.push(j);
    paintAttached(r.ok ? "" : `✗ ${file.name}: ${j.detail || r.status}`);
  }
  $("attach").value = "";
};

$("msgForm").onsubmit = (e) => {
  e.preventDefault();
  const text = $("msg").value.trim();
  if (!text) return;
  $("msg").value = "";
  send(text);
};

// silent: evento del sistema (ya conecte X). El agente lo recibe, pero no se pinta ni se guarda como mensaje del usuario.
async function send(text, silent = false) {
  const files = silent ? [] : attached;
  if (!silent) { attached = []; paintAttached(); }
  if (!silent) bubble("me", text + files.map((f) => `\n📎 ${f.name}`).join(""));
  const out = bubble("ai", "…");
  let acc = "";
  $("sentinelLog").replaceChildren();
  $("traceLog").replaceChildren();
  $("trace").scrollTop = 0;
  const r = await authed("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, conversation_id: conv, trace: $("traceOn").checked, hold: $("holdOn").checked, silent, files: files.map((f) => f.file_id) }),
  });
  if (!r.ok) {
    out.className = "m err";
    setText(out, r.status === 401 ? "Sesión vencida, vuelve a entrar." : `Error ${r.status}`);
    if (r.status === 401) $("logout").click();
    if (r.status === 404) { $("newConv").click(); bubble("ai", "Esa conversación no es de tu cuenta; abrí una nueva. Vuelve a enviar tu mensaje."); }
    return;
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const p of parts) {
      if (!p.startsWith("data: ")) continue;
      const ev = JSON.parse(p.slice(6));
      if (ev.type === "token") { acc += ev.text; setText(out, acc); out.scrollIntoView({ block: "end" }); }
      else if (ev.type === "agent_status") $("status").textContent = ev.label;
      else if (ev.type === "done") {
        if (silent && !(ev.text || acc)) { out.remove(); $("status").textContent = ""; continue; } // el agente respeta el turno del usuario: no escribe
        setText(out, ev.text || acc);
        $("status").textContent = "";
        if (ev.quality) { addQuality(out, ev.quality); convQuality.push(ev.quality); }
        if (ev.usage) { addUsage(out, ev.usage); convUsage.push(ev.usage); }
        renderActions(out, ev.ui_actions, new Set());
        addRating(out, ev.text || acc, ev.usage?.agent_version);
        renderStats();
      }
      else if (ev.type === "trace") addTrace(ev);
      else if (ev.type === "sentinel") addSentinel(ev);
      else if (ev.type === "reset") { acc = ""; setText(out, "…"); }
      else if (ev.type === "error") { out.className = "m err"; setText(out, ev.message); }
    }
  }
  loadList();
}

show();
