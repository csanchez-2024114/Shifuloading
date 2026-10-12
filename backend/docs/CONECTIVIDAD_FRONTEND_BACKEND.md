# Plan v1: Nomenclatura única de endpoints + conectar todas las pantallas

## Context

La plataforma va a publicar su **v1**. Hoy la superficie HTTP es inconsistente y
eso se arrastraría a la versión pública:

- **6+ prefijos distintos**: `/api/v1`, `/api/v2`, `/api/v3`, `/api/v4`, `/api/users`,
  `/api/agent`, `/api/accounts`, `/api/catalog`, `/auth/*`, y rutas **en la raíz**
  (`/rewards`, `/admin/rewards`, `/challenges/...`).
- **Case mezclado**: `snake_case` (`get_integrations`, `forgot_password`,
  `catalog_apps`, `ultimos_mensajes`) junto a `kebab-case` (`use-case`,
  `action-history`, `audit-log`).
- **Verbos RPC en el path**: `get_user`, `add_integration`,
  `delete_integration/{name}`, `disconnect_account/...`, `mark_as_viewed`.
- **3 bugs de doble-prefix** (Blog, Cloudinary, Referrals) que producen rutas como
  `/api/v2/blog/api/v2/blog`.
- Rutas duplicadas (`conversations/conversations`) y routers montados pero
  **inalcanzables** (Secretary).

Además, ~55 de los 94 endpoints que una pantalla debe consumir **no están
conectados** (36 con backend listo, 19 sin backend).

**Objetivo:** congelar una nomenclatura única para v1, migrar todo hacia ella, y
conectar cada pantalla contra la ruta canónica. El renombrado se hace **antes**
de conectar las pantallas mock, para no cablear el frontend dos veces.

**Decisiones del usuario:**
1. Todo bajo **`/api/v1`** (se eliminan v2/v3/v4 y los prefijos sueltos).
2. **kebab-case** en los paths.
3. **REST puro**: recurso en plural + verbo en el método HTTP.
4. **Migrar también los OAuth** a `/api/v1/auth/{provider}` (incluye callbacks).

Este documento es también el **rastreador de progreso**: se actualiza marcando
casillas `- [ ]` → `- [x]` a medida que cada endpoint queda renombrado, probado
y consumido por su pantalla.

---

## ⚠️ REGLAS DE EJECUCIÓN — obligatorias para cualquier agente/dev que trabaje este plan

Estas reglas **no son sugerencias**. Si no se cumplen, detener el trabajo y
corregir antes de seguir.

1. **Gate por endpoint — no se avanza al siguiente sin cerrar el actual.**
   Para cada endpoint de la lista de abajo, el ciclo completo es:
   `renombrar/crear en backend` → `probar el endpoint solo (curl/HTTPie/pytest)`
   → `actualizar el consumidor en frontend` → `probar el flujo end-to-end en el
   navegador` → `marcar la casilla [x]`. **No se toca el siguiente endpoint de la
   lista hasta que el actual esté marcado.**
2. **"Probado" tiene una definición concreta, no es opinión:**
   - Backend: una llamada real (curl/HTTPie/Postman/pytest) contra el endpoint
     nuevo devuelve el status y shape esperados. Si el endpoint toca datos
     (crea/borra), se verifica el efecto en la base (Mongo) o en un `GET`
     posterior.
   - Frontend: la pantalla que lo consume se abre en el navegador con un
     usuario real, la pestaña Network muestra la llamada al path v1 (no al
     legacy, no a un mock), y el dato se ve correctamente en la UI.
   - Si el endpoint es solo backend (sin pantalla todavía, ej. Fase 3 antes de
     cablear el frontend), el criterio de "probado" es solo el punto backend, y
     el checkbox de frontend se marca aparte cuando se cablee.
3. **Un endpoint migrado no queda en dos formas a la vez** salvo que esté
   explícitamente listado en la §4 (consumidor externo). Si se crea la ruta
   nueva, la vieja se elimina en el mismo cambio — no se dejan los dos paths
   sirviendo lo mismo "por si acaso".
4. **No se migran en lote sin probar.** Renombrar 10 rutas de un router en un
   solo commit sin correr nada es lo que este plan busca evitar. Migrar de una
   en una (o en grupos pequeños del mismo dominio que se prueban juntos porque
   comparten una sola pantalla), probar, marcar, seguir.
5. **OAuth (§4) tiene un gate extra:** no se retira la ruta vieja de un
   proveedor hasta hacer un login real con ese proveedor específico contra la
   ruta nueva. Un fallo de OAuth es un fallo de producción para usuarios reales
   ya conectados — no se asume que "como los otros 5 proveedores funcionaron,
   este también".
6. **Si un endpoint no se puede probar de inmediato** (falta variable de
   entorno, credencial de sandbox, etc.), no se marca `[x]` y se anota el
   bloqueo al lado de la casilla en una sub-línea `> bloqueado: <motivo>`. No
   se sigue de largo dejando el checklist "medio marcado" sin nota.
7. **Este documento se actualiza en el mismo PR** que el código. Un PR que
   renombra/conecta endpoints sin actualizar las casillas correspondientes
   está incompleto.

---

## 1. Estándar de nomenclatura v1

| Regla | Sí | No |
|---|---|---|
| Prefijo único | `/api/v1/...` | `/api/v2`, `/api/v4`, `/api/users`, raíz |
| Case | `kebab-case` → `/action-history` | `snake_case` → `/action_history` |
| Recurso | plural → `/integrations` | singular / verbo → `/add_integration` |
| Verbo | método HTTP → `DELETE /integrations/{id}` | en el path → `/delete_integration/{id}` |
| Sub-recurso | `/workflows/{id}/runs` | `/get_workflow_runs?id=` |
| Filtros | query string → `/processes?user_id=` | en el path → `/processes/email/{email}` |
| Acción no-CRUD | sub-recurso en plural → `POST /workflows/{id}/runs` | `POST /workflows/{id}/run` |
| Identidad propia | `/api/v1/me/...` | `/users/me` + `/api/v4/me` duplicados |

**Excepción aceptada — verbos de autenticación.** `login`, `logout`, `refresh`,
`forgot-password`, `reset-password` son acciones por naturaleza y se quedan como
verbos. Es la práctica estándar; no forzar REST ahí.

**Excepción aceptada — endpoints con consumidor externo.** Ver §4.

---

## 2. Checklist de migración (marcar al cerrar el gate de la regla #1)

Formato de cada línea: `actual → v1`. Casilla única por endpoint (cubre
backend + frontend, salvo que se anote lo contrario).

### Auth — 0 / 8
- [ ] `POST /api/v{1,2}/auth/login` → `POST /api/v1/auth/login`
- [ ] `POST /api/v{1,2}/auth/register` → `POST /api/v1/auth/register`
- [ ] `POST /api/v{1,2}/auth/refresh` → `POST /api/v1/auth/refresh`
- [ ] `POST /api/v{1,2}/auth/logout` → `POST /api/v1/auth/logout`
- [ ] `GET /api/v2/auth/me` → fusionar en `GET /api/v1/me` (ver bloque Me)
- [ ] `POST /api/users/forgot_password` → `POST /api/v1/auth/forgot-password`
- [ ] `POST /api/users/reset_password` → `POST /api/v1/auth/reset-password`
- [ ] `POST /api/v1/auth/google/login` → sin cambio (verificar consumidor único)

### Me / identidad propia (fusiona `/users/me` + `/api/v4/me`) — 0 / 12
- [ ] `GET /api/v1/users/me` → `GET /api/v1/me`
- [ ] `PATCH /api/users/update_profile` → `PATCH /api/v1/me`
- [ ] `PATCH /api/users/change_password` → `PATCH /api/v1/me/password`
- [ ] `POST {apiUrl}update_profile_image` (roto) → `POST /api/v1/me/avatar`
- [ ] `POST/GET /api/users/set_step_by_step` / `get_step_by_step` → `PATCH/GET /api/v1/me/preferences`
- [ ] `GET /api/users/check_integrations` → `GET /api/v1/me/integrations` (dedupe con integrations)
- [ ] `POST /api/users/refresh_tokens` → `POST /api/v1/me/integrations/refresh`
- [ ] `GET /api/users/get_{app}_chat` (×5 apps) → `GET /api/v1/me/chats/{app}/messages`
- [ ] `/api/v4/me/*` (20 endpoints ya kebab) → `/api/v1/me/*` (solo cambia prefijo)
- [ ] `POST /api/v4/me/action-history/{run_id}/undo` → `POST /api/v1/me/action-history/{run_id}/undo`
- [ ] `GET /api/v1/me/conversations*` → sin cambio, confirmar único path
- [ ] `DELETE /api/v1/me/conversations/{id}` → sin cambio

### Users (admin) / Accounts — 0 / 3
- [ ] `GET /api/users/get_user?id=` → `GET /api/v1/users/{user_id}`
- [ ] `GET /api/accounts/` → `GET /api/v1/accounts`
- [ ] `DELETE /api/accounts/disconnect_account/{provider}/{id}` → `DELETE /api/v1/accounts/{provider}/{account_id}`

### Integrations / Catalog — 0 / 10
- [ ] `GET /api/integrations/get_integrations` → `GET /api/v1/integrations`
- [ ] `POST /api/integrations/add_integration` → `POST /api/v1/integrations`
- [ ] `DELETE /api/integrations/delete_integration/{name}` → `DELETE /api/v1/integrations/{name}`
- [ ] `GET /api/integrations/health_check` → `GET /api/v1/integrations/health`
- [ ] `POST /api/v2/gmail/disable_watch` → `DELETE /api/v1/integrations/gmail/watch`
- [ ] `GET /api/catalog/catalog_apps` → `GET /api/v1/catalog/apps`
- [ ] `POST /api/catalog/catalog_apps` → `POST /api/v1/catalog/apps`
- [ ] `PUT /api/catalog/catalog_apps/{id}` → `PUT /api/v1/catalog/apps/{id}`
- [ ] `PATCH .../catalog_apps/{id}/deactivate` → `PATCH /api/v1/catalog/apps/{id}` (body `{active:false}`)
- [ ] `POST .../catalog_apps/search` → `GET /api/v1/catalog/apps?names=`

### Conversations / Processes / History — 0 / 9
- [ ] `/api/v2/conversations/conversations` (duplicado) → `/api/v1/conversations`
- [ ] `GET .../conversations/user/{user_id}` → `GET /api/v1/conversations?user_id=`
- [ ] `/conversations/{id}/messages` → sin cambio de forma, solo prefijo
- [ ] `GET /api/agent/processes/email/{email}` → `GET /api/v1/me/processes`
- [ ] `GET /api/agent/processes/email/{email}/count` → `GET /api/v1/me/processes/count`
- [ ] `DELETE /api/agent/processes/name/{name}` → `DELETE /api/v1/processes?name=`
- [ ] `DELETE /api/agent/processes/email/{email}` → `DELETE /api/v1/me/processes`
- [ ] `GET/DELETE /api/agent/processes/{id}` → `/api/v1/processes/{id}`
- [ ] `/api/v2/process_history/*` → `/api/v1/process-history/*`

### Billing (antes "stripe") + Analytics — 0 / 14
- [ ] `POST /api/v2/stripe/checkout` → `POST /api/v1/billing/checkout-sessions`
- [ ] `GET /api/v2/stripe/products` / `/{slug}` → `GET /api/v1/billing/products` / `/{slug}`
- [ ] `POST .../products/{slug}/checkout` → `POST /api/v1/billing/products/{slug}/checkout-sessions`
- [ ] `.../products/characteristics/{id}` (×4) → `/api/v1/billing/products/{id}/features` (CRUD)
- [ ] `POST .../products/admin` → `POST /api/v1/billing/products`
- [ ] `DELETE .../products/admin/{slug}` → `DELETE /api/v1/billing/products/{slug}`
- [ ] `GET .../products/{slug}/pay` → `GET /api/v1/billing/products/{slug}/payment-link`
- [ ] `POST /api/v2/stripe/subscription/cancel` → `DELETE /api/v1/billing/subscription`
- [ ] `GET /api/v2/stripe/analytics/{tipo}` (×8) → `GET /api/v1/analytics/{tipo}` (sale de billing)
- [ ] `POST /api/v2/stripe/webhook` → `POST /api/v1/billing/webhook` ⚠ externo, ver §4
- [ ] `GET .../payment/{success,cancel}` → `GET /api/v1/billing/payment/{success,cancel}` ⚠ externo

### Rewards / Challenges / Referrals — 0 / 13
- [ ] `GET /rewards` (declarado 2×, quitar duplicado) → `GET /api/v1/rewards`
- [ ] `POST /rewards/redeem` → `POST /api/v1/rewards/{id}/redemptions`
- [ ] `GET /rewards/history` → `GET /api/v1/me/rewards/redemptions`
- [ ] `GET /rewards-streak` → `GET /api/v1/reward-streaks`
- [ ] `POST/GET /redeemed-reward-streak` → `POST/GET /api/v1/reward-streaks/redemptions`
- [ ] `POST /challenges/{id}/complete` → `POST /api/v1/challenges/{id}/completions`
- [ ] `/admin/rewards*` → `/api/v1/admin/rewards*`
- [ ] `/admin/challenges/*` → `/api/v1/admin/challenges/*`
- [ ] `/admin/streak_stats` → `/api/v1/admin/streak-stats`
- [ ] `/api/referrals/api/v2/referrals/verify/{code}` ⚙️ → `GET /api/v1/referrals/codes/{code}`
- [ ] `.../my-referrals/{user_id}` → `GET /api/v1/me/referrals`
- [ ] `.../generate-code/{user_id}` → `POST /api/v1/me/referrals/code`
- [ ] `POST register_with_referral` (⚙️ sin slash) → confirmar path final tras lo anterior

### News → Announcements — 0 / 5
- [ ] `/api/news/admin/news_features` (CRUD) → `/api/v1/admin/announcements`
- [ ] `GET /api/news/user/news_features` → `GET /api/v1/me/announcements`
- [ ] `GET .../news_features/pending` → `GET /api/v1/me/announcements?status=pending`
- [ ] `POST .../mark_as_viewed` → `POST /api/v1/me/announcements/{id}/view`
- [ ] `POST .../mark_all_as_viewed` → `POST /api/v1/me/announcements/views`

### Uploads / Blog / Contact / Messages / Secretary — 0 / 8
- [ ] `/api/v2/cloudinary/api/v2/uploads/file` ⚙️ → `POST /api/v1/uploads`
- [ ] `.../uploads/file/{public_id}` ⚙️ → `DELETE /api/v1/uploads/{public_id}`
- [ ] `.../uploads/list` ⚙️ → `GET /api/v1/uploads`
- [ ] `/api/v2/blog/api/v2/blog` ⚙️ → `GET/POST /api/v1/blog/posts`
- [ ] `POST /api/v2/contact` → `POST /api/v1/contact`
- [ ] `POST /api/messages/ultimos_mensajes` → `GET /api/v1/messages/latest`
- [ ] Secretary GET `/api/secretary/ultima-notificacion/{provider}` → decidir montar o retirar (ver nota abajo) → si se monta: `GET /api/v1/secretary/notifications/{provider}/latest`
- [ ] Secretary POST `/api/secretary/accion-{provider}` → idem → si se monta: `POST /api/v1/secretary/{provider}/actions`

> ⚠️ Secretary está **muerto**, no solo mal nombrado: `setup_routes_secretary_gets/posts`
> (`app/routes/secretary/secretary*Routes.py`) nunca se invocan, así que
> `/api/secretary/*` está vacío aunque `SecretaryChats.tsx` lo llama. Antes de
> tocar las casillas de arriba, decidir en Fase 0: **montarlas** (llamar los
> `setup_*` en `main.py:669-670`) o **retirar la pantalla**. No se renombra algo
> que no existe todavía.

### OAuth providers (~24) — 0 / 5 patrones × N proveedores
Gate extra por la regla #5: login real por proveedor antes de retirar la ruta vieja.
- [ ] `GET /auth/{provider}/login` → `GET /api/v1/auth/{provider}/login`
- [ ] `GET /auth/{provider}/callback` → `GET /api/v1/auth/{provider}/callback` ⚠ externo, ver §4
- [ ] `GET /auth/{provider}/status` → `GET /api/v1/auth/{provider}/status`
- [ ] `POST /auth/{provider}/disconnect` → `DELETE /api/v1/auth/{provider}`
- [ ] Especiales: `trello/save`→`auth/trello/token`, `brevo/save_key`→`auth/brevo/key`, `telegram/callback`→`auth/telegram/callback`, Google multi-servicio (`gmail/drive/docs/sheets/slides/calendar` login) → `auth/google/login?service={s}`, `whatsapp/webhook`→`/api/v1/webhooks/whatsapp` ⚠ externo

> Migrar proveedor por proveedor (no en lote): Slack, Notion, Trello, ClickUp,
> Dropbox, HubSpot, Jira, Salesforce, Kick, TikTok, Mailchimp, Twitter, Threads,
> UberEats, Facebook, Instagram, Discord, LinkedIn, Teams, OneDrive, Outlook,
> Asana, Telegram, Brevo, OnlyFans, PedidosYa, Google (multi), WhatsApp.
> Cada uno es su propia sub-casilla en la práctica — usar una tabla de trabajo
> aparte (issue/PR) si se necesita más granularidad que este documento.

### Endpoints nuevos — se crean ya en nomenclatura v1 (0 / 19, Fase 3)
- [ ] `GET/POST /api/v1/workflows`
- [ ] `GET/PATCH/DELETE /api/v1/workflows/{id}`
- [ ] `GET/POST /api/v1/workflows/{id}/runs` (POST crea una ejecución)
- [ ] `GET /api/v1/debug/discovery-sessions`
- [ ] `POST /api/v1/debug/discovery-sessions/{id}/abandon`
- [ ] `GET/DELETE /api/v1/debug/discovery-processes[/{id}]`
- [ ] `GET /api/v1/me/chats/{app}/messages` (reemplaza `langgraph/history`)
- [ ] `GET/POST /api/v1/workspaces/{id}/members`
- [ ] `PATCH/DELETE /api/v1/workspaces/{id}/members/{uid}`
- [ ] `GET/POST/DELETE /api/v1/secrets[/{id}]`
- [ ] `WS /api/v1/ws/chat`
- [ ] `WS /api/v1/ws/runs`
- [ ] `WS /api/v1/ws/chat-debug`
- [ ] `GET /health` (sin versionar, convención)

---

## 3. Mecánica de la migración

**Principio rector:** el frontend es el **único consumidor** de casi todo. Para
esos endpoints se renombra y se actualiza el frontend en el mismo PR — sin capa
de compatibilidad, sin deuda. Solo los de **consumidor externo** llevan alias.
Todo esto bajo el gate de la sección de reglas: un endpoint a la vez, probado
antes del siguiente.

1. **Router canónico.** En `main.py` dejar **un solo bloque** de
   `include_router(..., prefix="/api/v1/...")`. Borrar los mounts de
   `/api/v2`, `/api/v3`, `/api/v4`, `/api/agent`, `/api/users`, `/api/catalog`,
   `/api/accounts`, `/api/news`, `/api/referrals` y los de raíz.
   *Esto elimina de raíz los 3 bugs de doble-prefix* — al dejar un solo prefijo,
   se quita el `prefix=` interno de Blog / Cloudinary / Referrals.
2. **Renombrar paths dentro de cada router** (kebab + REST) según §2.
3. **Alias de compatibilidad solo para los externos** (§4), montados detrás de
   un flag `LEGACY_ROUTES_ENABLED=true`, con el middleware `Deprecation`/`Sunset`
   que ya existe en `main.py:518-526`. Se apaga cuando las consolas externas
   estén migradas.
4. **Frontend en lockstep** (mismo PR): actualizar los paths y, de paso,
   arreglar los bugs de cliente (§5).

---

## 4. Endpoints con consumidor externo (cambio coordinado, NO romper)

| Endpoint | Quién lo llama | Qué hay que actualizar además del código |
|---|---|---|
| `POST /api/v1/billing/webhook` | Stripe | URL del webhook en el dashboard de Stripe |
| `GET /api/v1/billing/payment/{success,cancel}` | Stripe (redirect) | `success_url` / `cancel_url` de la sesión |
| `GET /api/v1/auth/{provider}/callback` (×24) | Cada proveedor OAuth | env `{PROVIDER}_REDIRECT_URI` + redirect URI en la consola del proveedor |
| `/api/v1/webhooks/whatsapp` | Meta | URL del webhook en Meta for Developers |
| `POST /api/v1/webhooks/inbound/{token}` | Terceros | URLs ya repartidas a usuarios → mantener alias largo |

**Orden seguro por proveedor:** montar la ruta nueva → registrar el nuevo redirect
URI en la consola (la mayoría acepta varios) → cambiar el env var → verificar un
login real (regla #5) → recién ahí retirar la ruta vieja.

**Buena noticia:** cada proveedor construye su `redirect_uri` desde una env var
(`SLACK_REDIRECT_URI`, `NOTION_REDIRECT_URI`, …), no está hardcodeado. Migrar el
callback = cambiar el **valor del env var** + el redirect URI en la **consola del
proveedor**. No hay que tocar la lógica de cada archivo.

---

## 5. Bugs de cliente que hay que arreglar en el mismo paso

1. **Dos llaves de token**: `src/api/http.ts` lee `access_token`;
   `src/api/apiPrincipal.ts` lee `token`. Un cliente entero manda sin auth.
   → Unificar a una sola llave y colapsar a **un** cliente axios.
2. **URLs sin slash** (`apiUrl` quita el trailing slash → `http://localhost:8000rewards`):
   `src/api/rewards/*.ts`, `src/api/referrals/ReferralsApi.ts`,
   `src/api/auth/updateImgApi.ts`, `src/features/build/components/FlowBuilder.tsx`.
   → Desaparece solo si todo pasa por el cliente único con `baseURL`.
3. **Gemini key vacía** (`const apiKey = ""`) en 4 archivos → las funciones
   "Shifu AI" degradan a mock en silencio. Definir origen (env o proxy backend).
4. **`refreshTokens.py`** nunca se monta; **`/rewards`** declarado dos veces
   (`rewardRoutes.py:371-372`). Limpiar.

---

## 6. Fases de ejecución

- **Fase 0 — Nomenclatura v1 + higiene.** §1–§5. Backend a `/api/v1` canónico,
  frontend en lockstep, alias solo para externos, cliente HTTP unificado.
  *Al terminar: Rewards, Referrals y Blog quedan conectados sin tocar su lógica.*
- **Fase 1 — Conectar mocks con backend listo (sin flujo nuevo).**
  Settings, Payments, Historial, Memory. **18 endpoints.**
- **Fase 2 — Conectar mocks con flujo extra.**
  Resources (uploads), Notifications (announcements), Insights/radar. **~8 endpoints.**
- **Fase 3 — Construir backend faltante.** Router REST de Workflows (sobre los
  servicios/worker existentes) → Tablero + Tasks; router `debug`;
  `/me/chats/{app}/messages`; Workspaces; Secrets. **19 endpoints.**

Cada fase respeta el gate de la sección de reglas: no se pasa al siguiente
endpoint de la lista sin cerrar el ciclo completo del actual.

---

## 7. Progreso global

| # | Grupo | Conectados | Total |
|---|---|---|---|
| **TOTAL** | **Todo** | **0 / 94*** | — |
| Fase 0 | Nomenclatura + higiene | 0 | ~59 renombres + 3 bugs |
| Fase 1 | Mock → real (backend listo) | 0 | 18 |
| Fase 2 | Mock → real (flujo extra) | 0 | ~8 |
| Fase 3 | Backend nuevo | 0 | 19 |

\* El contador vuelve a 0 porque este plan **redefine los paths**; los 39
endpoints que ya estaban conectados con su nombre legacy también deben pasar
por el gate (renombrar → probar → marcar) antes de contar como hechos en v1.

---

## 8. Archivos críticos

- **Montaje de routers (el cambio grande):** `main.py:633-738`; middleware de
  deprecación ya existe en `main.py:518-526`.
- **Routers a renombrar:** `app/routes/**` (auth, users, integrations, catalog,
  billing/stripeRoutes.py, social/rewardRoutes.py, social/newsRoutes.py,
  V2/blog, V2/apis/cloudinary_routes.py, users/referralsRoutes.py,
  V3/agent/me.py, V2/agent/{processes,history}.py).
- **Secretary a montar o retirar:** `app/routes/secretary/secretary{Get,Post}Routes.py`.
- **OAuth (solo prefijo + env):** `app/integrations/providers/*` (~24 archivos) —
  el `redirect_uri` sale de env vars, no del código.
- **Base de Fase 3 (ya existe, falta el router):** `app/services/workflow_service.py`,
  `app/services/workflow_run_service.py`, `app/workers/workflow_worker.py`.
- **Frontend — clientes a unificar:** `src/api/http.ts`, `src/api/apiPrincipal.ts`,
  `src/api/configsApi.ts`.
- **Frontend — mocks a desconectar:** `historial/useHistorial.ts`,
  `settings/settingsApi.ts` (`mockHttp`), `hooks/useResources.ts`,
  `memory/useMemoryGraph.ts`, `redux/slices/paymentsSlice.ts`,
  `hooks/useNotifications.ts`.

---

## 9. Verificación

1. **Inventario automático:** levantar el backend y comparar `GET /openapi.json`
   contra el estándar. Un script corto que falle si alguna ruta: no empieza con
   `/api/v1` (salvo `/health`, `/`, `/docs` y los alias externos), contiene `_`,
   o contiene un verbo (`get_`, `add_`, `delete_`, `_check`).
   Es la red de seguridad de §1 — sin esto, la nomenclatura se erosiona sola.
2. **Sin prefijos duplicados** en `/docs` (`/api/v2/blog/api/v2/blog` debe morir).
3. **OAuth real, uno por uno:** hacer login real con cada proveedor migrado antes
   de retirar su ruta vieja (regla #5). Es el paso con más riesgo de producción.
4. **Stripe:** disparar un evento de prueba desde el dashboard contra
   `/api/v1/billing/webhook` y confirmar 200.
5. **Frontend por pantalla:** abrir con usuario real y confirmar en Network que
   pega al endpoint v1 esperado (no `MOCK_` / `mockHttp` / localStorage).
6. **Grep de sanidad:** sin `MOCK_`, `mockHttp`, `INITIAL_`, `apiKey = ""` en
   vistas ya conectadas; sin `/api/v2`, `/api/v4`, `/api/agent` en el frontend.
