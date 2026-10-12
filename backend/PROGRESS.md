# Progreso de Migración — HyperShifu Backend
**Última actualización:** 2026-06-27 | **Rama activa:** shifu_base_v1

## Estado General

| Fase | Descripción | Estado |
|------|-------------|--------|
| Fase 0 | Seguridad — credenciales | ✅ Completo |
| Fase 1 | Limpieza sin tocar el agente | ✅ Completo (PR pendiente) |
| Fase 2 | Consolidar integraciones | ✅ Completo |
| Fase 3 | Restructurar agente → Shifu Standard v1.0.0 | 🔄 En progreso |
| Fase 4 | API y Workers | ⬜ Sin iniciar |
| Fase 5 | MCP servers (futuro) | ⏳ Pendiente |

> Leyenda: ✅ Completo · 🔄 En progreso · ⬜ Sin iniciar · ❌ Bloqueado · ⏳ Pendiente/Futuro

---

## GitHub Flow — Cómo trabajamos

Cada fase se sube a GitHub siguiendo este flujo:

1. Todas las tareas de la fase marcadas `[x]` en este archivo
2. `git add` de los archivos cambiados en esa fase
3. `git commit` con mensaje `chore(phaseN): <resumen>`
4. `git push origin agente-estable-v3`
5. Abrir PR a `master` con título `Phase N — <nombre de fase>`
6. Merge a `master` solo cuando la fase esté verificada y estable

> **Regla:** Un commit por fase completada. No commitear trabajo a medias.

---

## Fase 0 — Seguridad (INMEDIATO, 1-2 días)

- [x] Verificar si `.env` está en git history: `git log --all --full-history -- .env` — limpio, sin commits
- [x] Si aparece → rotar TODAS las credenciales — N/A, no apareció
- [x] Confirmar `.env` en `.gitignore` — confirmado
- [ ] Mover secretos a variables de entorno en Render (no archivos) — verificar manualmente en el dashboard

### Git — Fase 0
- [ ] `git commit -m "chore(phase0): security audit — .env verified clean, gitignore confirmed"`
- [ ] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 0 — Seguridad_

---

## Fase 1 — Limpieza Sin Tocar el Agente (2-3 semanas)

- [x] Confirmar subdominios en DNS: `hypershifu.com` / `app.hypershifu.com` / `api.hypershifu.com` — confirmado por el equipo
- [x] Eliminar Flask de `requirements.txt` — Flask, Flask-Caching, Flask-Cors, Flask-PyMongo eliminados
- [x] Auditar y eliminar deps pesadas sin uso: `torch`, `transformers`, `ONNX`, `OpenCV` — 27 paquetes ML eliminados
- [x] Agregar LangSmith tracing — `LANGSMITH_API_KEY` + `LANGCHAIN_TRACING_V2` + `LANGCHAIN_PROJECT` configurados en Render
- [x] Agregar OpenTelemetry básico en FastAPI — middleware condicional en `main.py`, activo con `OTEL_EXPORTER_OTLP_ENDPOINT`
- [x] Mover `PLAN_RULES` de `config.py` → `app/billing/plans.py` — `rpm_limit` por plan incluido
- [x] Agregar headers de deprecación en rutas `/api/v2/` y `/api/v3/` — middleware en `main.py`
- [x] Crear `app/core/quota.py` con check Redis RPM/TPM (ventana deslizante 60s) — plan-aware, reemplaza rate limiter local del WS
- ⏳ Configurar LiteLLM proxy — aplazado hasta que se necesiten múltiples modelos por tier

### Git — Fase 1
- [x] `git commit 07236df` — chore(phase1): cleanup
- [x] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 1 — Limpieza_ ← pendiente abrir en GitHub

---

## Fase 2 — Consolidar Integraciones

- [x] Crear `app/integrations/providers/` — con `__init__.py` y subdirectorio `google/`
- [x] **Google** — `auth_google.py` + `gmail.py` + `drive.py` + `docs.py` + `sheets.py` + `slides.py` + `oauth_shared.py` → `integrations/providers/google/`
- [x] **Slack** → `integrations/providers/slack.py`
- [x] **Notion** → `integrations/providers/notion.py`
- [x] **Asana** → `integrations/providers/asana.py`
- [x] **ClickUp** → `integrations/providers/clickup.py`
- [x] **Teams / Discord** → `integrations/providers/teams.py`, `discord.py`
- [x] **WhatsApp / Telegram** → `integrations/providers/whatsapp.py`, `telegram.py`
- [x] **Social / CRM / Marketing** — trello, monday, jira, hubspot, facebook, dropbox, outlook, salesforce, kick, tiktok, brevo, mailchimp, twitter, threads, onlyfans, ubereats, pedidosya, linkedin, instagram, onedrive
- [x] Actualizar imports en `main.py` y agent tools (gmail, drive, docs, sheets, slides, dropbox, jira, hubspot, facebook)
- [x] Limpiar carpetas vacías en `routes/V2/apis/` y `services/`

### Git — Fase 2
- [ ] `git commit -m "feat(phase2): consolidate integrations — 28 providers moved to app/integrations/providers/"`
- [ ] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 2 — Consolidar Integraciones_

---

## Fase 3 — Shifu Standard v1.0.0 (4-6 semanas)

- [x] `git tag shifu-v1.0.0-baseline` antes de mover cualquier archivo — tag `shifu-v1.0.0-baseline` pusheado
- [x] Crear `app/agent/shared/nodes/` y mover los 11 nodos desde `agents/agente_v3/nodes/`
- [x] Crear `app/agent/shared/memory/` — mover 6 helpers de memoria
- [x] Crear `app/agent/shared/context/` — `time_context`, `geo_context`, `timezone_converter`
- [x] Crear `app/agent/shared/tools/providers/` — 18 bigtools
- [x] Crear `app/agent/v1/graph/builder_standard.py` + `state.py` + `tavily_subgraph.py`
- [x] Implementar Multi-Schema State: `ShifuInputState` + `ShifuOutputState` en `state.py`; `V3State` es el estado interno completo; `StateGraph(V3State, input=ShifuInputState, output=ShifuOutputState)`
- [x] Crear `app/agent/v1/registry.py` con `init_v1_graphs()` + `get_v1_graph()` — main.py actualizado
- [x] **Parametrizar nodos via `RunnableConfig`** — `bigtools_inspector` y `response_evaluator` leen `inspector_model`/`eval_model` de `config["configurable"]`; LLM movido dentro de la función
- [x] Crear `app/core/tenant.py` con `TenantConfig` TypedDict (tier, model, inspector_model, eval_model, max_iterations)
- [x] Optimizar checkpoints: `retrieved_research`, `retrieved_sources`, `curated_research` reseteados en `semantic_intake._EMPTY_RESULT` — no persisten entre turnos
- [x] Crear golden dataset en `eval/golden_dataset.json` (22 casos) + `eval/baseline_scores.json` + `eval/run_eval.py`
- [x] Configurar GitHub Actions `cognitive-regression.yml` — corre en PR a master/agente-estable-v3 cuando cambia `app/agent/` o `eval/`
- ⏳ Aplicar `InjectedState` en BigTools — BigTools ya reciben `user_id`/`selected_accounts` via factory args; migración a LangChain `@tool` + `InjectedState` aplazada a Fase 5 (MCP migration)
- ⏳ Auditar prompts hardcodeados en `responder.py` — `_MOOD_DIRECTIVES`, `_EFFORT_DIRECTIVES`, anti-looping rule identificados; migración a MongoDB `agent_identity` aplazada a Fase 4

### Git — Fase 3
- [x] `git tag shifu-v1.0.0-baseline` — pusheado
- [x] `git commit f560f21` — phase-3-shifu-standard: restructura de archivos
- [x] `git merge phase-3-shifu-standard → agente-estable-v3` (commit 211459a)
- [ ] `git commit` — phase-3b-deep-refactor: RunnableConfig, Multi-Schema State, registry, eval ← pendiente
- [ ] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 3 — Shifu Standard v1.0.0_

---

## Fase 4 — API y Workers (2-3 semanas)

- [x] **`/api/v1/` aliases** en `main.py` — auth, users, conversations, processes, catalog, integrations, me, webhooks, ws/chat-debug, ws/runs
- [x] **Frontend migrado** (`hyper-shifu-app`): auth/login, users/me, ws/chat-debug, ws/runs, me/integrations, debug/* → todos apuntan a `/api/v1/`
- [x] **Redis Streams** en `workflow_worker.py` — XREADGROUP, sub-segundo. Fallback polling 60s para runs de trigger/scheduler
- [x] **`workflow_run_service.create_run()`** — publica XADD al stream después de insertar en MongoDB; no-op si Redis no está disponible
- [x] **`app/channels/`** — `ChannelAdapter` (ABC) + `WhatsAppAdapter` (Cloud API, normaliza texto, envía reply)
- [ ] Actualizar redirect URIs OAuth en Google Console, Slack, Notion, etc. → `/api/v1/integrations/{provider}/callback` (tarea externa — requiere acceso consolas)
- [ ] **`/api/v1/chat`** REST endpoint (wrapper no-streaming sobre v3_graph) — `MainChat.tsx` aún llama `/api/v2/agent/langgraph` que no existe; pendiente sprint frontend
- [ ] **Routers con prefix hardcodeado** (`stripeRoutes`, `connected_accounts`, `referralsRoutes`, `cloudinary_routes`, `blogMain`) — no tienen alias v1 aún; requieren edit interno

### Git — Fase 4
- [x] `git commit -m "feat(phase4): API v1 consolidation, Redis Streams worker, channel adapters"` ← pendiente commit
- [ ] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 4 — API y Workers_

---

## Fase 5 — MCP Servers (Futuro)

- [ ] Migrar `app/agent/shared/tools/providers/` → servidores MCP independientes
- [ ] Conectar el agente via transporte MCP (Stdio o HTTP streaming)
- [ ] Eliminar dependencias de SDKs de Google, Slack, Notion del contenedor principal

### Git — Fase 5
- [ ] `git commit -m "feat(phase5): MCP server migration — tools as independent services"`
- [ ] `git push origin agente-estable-v3`
- [ ] PR a `master`: _Phase 5 — MCP Servers_

---

## Fase 6 — Shifu Agent: Lanzamiento Comercial

> **Objetivo:** Graduar `agente_v3` (nombre de desarrollo interno) al **producto comercial** de HyperShifu.
> El agente ya existe y funciona; esta fase lo hace apto para usuarios reales.

### 6.1 — Interfaz de usuario principal
- [x] **`app/routes/V1/chat.py`** — `/ws/chat` (WS) + `/chat/stream` (SSE). Protocolo: `{type:"token"}`, `{type:"done", ui_actions:[...]}`, `{type:"error"}`. Registrado en `main.py` en `/api/v1`.
- [x] **`MainChat.tsx`** migrado de REST (`/api/v2/agent/langgraph`) a SSE (`/api/v1/chat/stream`) — streaming token por token.
- [x] **`ChatInput.tsx`** migrado de `/api/v4/chat/stream` → `/api/v1/chat/stream`.
- [x] **`ChatProcess/index.tsx`** WS migrado de `/api/v4/ws/chat` → `/api/v1/ws/chat`.
- [x] `/debug/agente-v3` ya estaba en sección de rutas protegidas `/debug/` — correcto, sin cambios.
- [x] **Agent status streaming** — `{type:"agent_status", node, label}` emitido por `on_chain_start` en `_ChatStreamer` (SSE) y `_WsChatStreamer` (WS debug). `node_labels.py` mapea nodo → label en español. Frontend: `ShifuDebug.tsx` muestra el label animado mientras el agente procesa; `ChatInput.tsx` lo muestra en `progressText`.

### 6.6 — Requirements Investigator (workflow builder conversacional)
- [x] **`app/agent/shifu_base_v1/graph/req_nodes.py`** — Nuevo nodo `req_investigator_node` con máquina de estados de 4 niveles activos (L1: preguntas entendimiento → L2: plan + gaps → L3: preflight catalog/auth + propuestas → L5: deploy a MongoDB).
- [x] **`state.py`** — +13 campos `req_*` en `ShifuState` (req_level, req_goal, req_plan, req_gaps, req_preflight_passed/failures, req_enhancements, req_accepted_enhancements, req_workflow_id, req_deployed, etc.).
- [x] **`builder_standard.py`** — Nodo `req_investigator` registrado + routing `_route_from_intake` prioriza `req_level is not None` antes del fan-out + edge `req_investigator → responder`.
- [x] **`nodes/semantic_intake.py`** — Skip LLM cuando `req_level` activo (turn pertenece al req_investigator); detecta `intent == "create_workflow"` → sets `req_level=1`.
- [x] **`prompts/semantic_intake.py`** — `create_workflow` agregado como `detected_intent` válido con definición, señales, y ejemplos en múltiples idiomas.
- [x] **`node_labels.py`** — `"req_investigator": "Diseñando tu workflow..."` para agent status streaming.

### 6.2 — Identidad del agente (nombre comercial)
- [x] **`get_shifu_graph()`** alias en `registry.py` (apunta a `get_v1_graph`, alias permanente).
- [x] **MongoDB collections renombradas** en `main.py`: `v3_checkpoints` → `shifu_checkpoints`, `v3_checkpoint_writes` → `shifu_checkpoint_writes`.
- [x] **`scripts/migrate_checkpoints.py`** — migración one-time de datos existentes. Correr con `--dry-run` primero.
- [ ] Ejecutar migración en producción: `python scripts/migrate_checkpoints.py --dry-run` → confirmar → sin `--dry-run`.

### 6.3 — Calidad y certificación
- [ ] **Correr eval completo:** `python -m eval.run_eval --update-baseline` (22 casos golden dataset, meta 100%).
- [ ] **SLOs:** latencia P95 < 8s/turno, evaluator score ≥ 0.85, tasa de error < 1%.
- [ ] **Stress test:** 10 usuarios simultáneos, 20 turnos. Verificar sin race conditions en checkpointer.
- [ ] Revisión y aprobación de **system prompts** (`responder.py`) con equipo de producto.

### 6.4 — Preparación producción
- [x] **`app/core/quota.py`** ya existía con sliding-window RPM por usuario.
- [ ] **Render:** confirmar env vars (`OPENAI_API_KEY`, `MONGO_URI`, `REDIS_URL`, `WEBHOOK_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_TOKEN`, `LANGSMITH_API_KEY`).
- [ ] **Monitoring:** dashboard Render + alertas latencia/error rate. LangSmith tracing activado.
- [ ] **Health check externo:** UptimeRobot sobre `/health` → alerta si 503.

### 6.5 — Limpieza post-lanzamiento
- [ ] Eliminar rutas `/api/v4/` del backend tras confirmar 0 tráfico activo en esas rutas (las páginas de debug v2 aún las usan internamente — no eliminar antes de migrarlas).
- [ ] Tag: `git tag shifu-agent-v1.0.0` en el commit de lanzamiento.
- [ ] PR a `master`: _Fase 6 — Shifu Agent: Lanzamiento Comercial_

### Git — Fase 6
- [x] `git commit` ← pendiente este commit
- [ ] `git push origin agente-estable-v3`
- [ ] `git tag shifu-agent-v1.0.0`

---

## Historial de Cambios

| Fecha | Fase | Commit | Responsable |
|-------|------|--------|-------------|
| 2026-06-20 | Fase 1 | pendiente | Eduardo-45 |
| 2026-06-20 | Fase 2 | pendiente | Eduardo-45 |
| 2026-06-27 | Fase 6.1 | pendiente | Eduardo-45 — agent status streaming (WS + SSE + frontend) |
| 2026-06-27 | Fase 6.6 | pendiente | Eduardo-45 — requirements investigator (6-level workflow builder) |
