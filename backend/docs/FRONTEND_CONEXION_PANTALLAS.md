# Frontend — Conectar pantallas: de mock a backend real

> Documento hermano: [`BACKEND_ENDPOINTS_V1.md`](./BACKEND_ENDPOINTS_V1.md)
> — ese cubre la nomenclatura y migración de endpoints. Este cubre **las pantallas**.
>
> Repo: `hyper-shifu-app` (Vite + React 19 + react-router v7, SPA).

## Context

Todas las pantallas del dashboard están construidas, pero **9 de las 10 vistas
vivas corren con datos falsos**. La única que consume backend real es
`InsightsView`. Este documento dice, pantalla por pantalla, **cuál es el mock
exacto** (archivo, línea, nombre de la constante), **qué endpoint v1 debe
consumir**, y **en qué fase** se conecta.

Además hay **8 vistas que no renderiza nadie** — no están en el `viewMap` de
`PlatformRoot.tsx:109-124` ni las importa ningún módulo. Se borran, no se conectan.

Todos los paths destino usan la nomenclatura v1 del documento de backend. Por eso
el renombrado de backend (B0) va **antes** que la conexión de pantallas: si no,
se cablea el frontend dos veces.

---

## ⚠️ REGLAS DE EJECUCIÓN — obligatorias

1. **Gate por pantalla — no se avanza a la siguiente sin cerrar la actual.**
   Ciclo: `borrar el mock` → `cablear el endpoint v1` → `abrir la pantalla en el
   navegador con un usuario real` → `confirmar en la pestaña Network que pega al
   path v1` → `marcar [x]`. **No se empieza la siguiente pantalla sin marcar la
   actual.**
2. **"Conectado" tiene definición concreta:**
   - La pestaña Network muestra la llamada al endpoint v1 (no al legacy, no a un mock).
   - El dato **se ve en la UI**, no solo llega en la respuesta.
   - No queda ningún `MOCK_*`, `INITIAL_*`, `mockHttp`, `setTimeout` de latencia
     falsa, ni `localStorage` usado como base de datos en el archivo tocado.
3. **No se borra un mock sin tener el endpoint funcionando.** Si el backend no
   existe todavía, la pantalla se queda en F3 y **no se toca**. Borrar el mock
   antes deja la pantalla en blanco.
4. **Los tipos TS del mock SON el contrato.** Antes de cablear, comparar el shape
   que devuelve el endpoint real contra el tipo (`ProcessHistoryItem`,
   `WorkspaceMember`, etc.). Si no coinciden, se decide **explícitamente** quién
   cede — no se hace un `as any` para que compile.
5. **Si algo no se puede probar** (falta credencial, endpoint sin desplegar), no
   se marca `[x]`: se anota debajo `> bloqueado: <motivo>`.
6. **Este documento se actualiza en el mismo PR** que el código.

---

## A. Estado de las 10 vistas vivas

`PlatformRoot.tsx` tiene un `viewMap` (líneas 109-124) que es lo único que
renderiza vistas del dashboard. Estas son las 10 que están ahí:

| Vista | Estado | Mock (archivo : línea) | Endpoint v1 destino | Fase |
|---|---|---|---|---|
| `InsightsView` | 🟢 **REAL** | — | `GET /api/v1/analytics/{tipo}` (solo renombre) | B0 |
| `SettingsView` | 🔴 MOCK | `settings/settingsApi.ts:3` `IS_MOCK_ENV=true` | `/api/v1/me`, `/me/password`, `/me/preferences`, `/billing/products` | F1 |
| `HistorialView` | 🔴 MOCK | `historial/historialMockData.ts:8,218,255,285` | `/api/v1/process-history`, `/me/action-history`, `/me/audit-log`, `/conversations` | F1 |
| `MemoryView` | 🔴 MOCK | `memory/memoryMockData.ts:3,13,21` | `/api/v1/me/memories` (razonamiento → F3) | F1 |
| `ResourcesView` | 🔴 MOCK | `resources/resourceMockData.ts:7` | `/api/v1/uploads` | F2 |
| `NotificationsView` | 🔴 MOCK | `notifications/useNotifications.ts:13,18-66,82-89` (única instancia vive en `context/NotificationsContext.tsx`) | `announcements*` + `WS /ws/runs` reales (falta `id`) · `WS /ws/chat-debug` real pero efímero · `integration` sin backend | F2 + F3 |
| `TableroView` | 🔴 MOCK | `dashboard/data/workflow.data.ts:3` | `/api/v1/workflows` | **F3** |
| `TasksView` | 🔴 MOCK | `tasks/tasksMockData.ts:3` | `/api/v1/workflows/{id}/runs` | **F3** |
| `UserView` | 🔴 MOCK | `users/userMockData.ts:48` `MOCK_MEMBERS` | `/api/v1/workspaces/{id}/members*` | **F3** |
| `SecretsView` | 🔴 MOCK | `views/SecretsView.tsx:31` `INITIAL_SECRETS` | `/api/v1/secrets` | **F3** |

**F3 = bloqueado por backend.** Esos 4 endpoints **no existen todavía**. No se
tocan esas pantallas hasta que B2 del documento de backend los cree.

---

## B. Ficha por pantalla

### 1. SettingsView — el mock más barato de quitar
- **Mock:** `settings/settingsApi.ts` es una capa HTTP falsa completa.
  `IS_MOCK_ENV = true` (línea 3) · `mockDb` en memoria (5-43) ·
  `mockHttp<T>()` con `setTimeout(...,300)` (45-90) · `executeRequest` (92-97).
- **Por qué es barato:** `executeRequest` **ya despacha por URL**. El contrato de
  endpoints está escrito. Cambiar `IS_MOCK_ENV` a `false` y conectar `@/api/http`
  es casi todo el trabajo.
- **Consumido por:** `views/SettingsView.tsx:4,56,57` y `settings/PreferencesTab.tsx:32`.
- **Endpoints v1:**
  - `GET /api/v1/me` (era `GET /api/users/me`)
  - `PATCH /api/v1/me` (era `update_profile`)
  - `PATCH /api/v1/me/password` (era `change_password`; el mock valida
    `current_password === "password123"` y nueva ≥ 8 chars — la validación real
    la hace el backend)
  - `GET|PATCH /api/v1/me/preferences` (era `/api/v4/me/preferences`)
  - `GET /api/v1/me/audit-log` (el mock pedía `/api/v4/…`)
  - `GET /api/v1/billing/products` · `DELETE /api/v1/billing/subscription`
- **Shapes:** `UserProfile {id,email,name,last_name,plan,subscription,img,phone,country,description}` ·
  `UserPreferences {transparencyMode,darkMode,performanceMode,language}` (`settingsTypes.ts:52`) ·
  `StripeProduct {id,name,price,interval,features[]}`.
- [ ] Conectado

### 2. HistorialView — el código real ya está escrito, en comentarios
- **Mock:** `MOCK_PROCESSES`, `MOCK_ACTIONS`, `MOCK_AUDITS`, `MOCK_CONVERSATIONS`
  en `historial/historialMockData.ts:8,218,255,285`, consumidos por
  `historial/useHistorial.ts:10-15,30-33`.
- **Latencia falsa:** `setTimeout` 600 ms (`useHistorial.ts:55`), 950 ms (`:116`).
- **Código real ya escrito:** bloque "CÓDIGO DE PRODUCCIÓN" en
  `useHistorial.ts:57-93` y `:118-125`. **Es descomentar y ajustar el path a v1.**
- **Endpoints v1:**
  - `GET /api/v1/process-history?page&limit&status&query` → `{data, meta}`
    (era `GET /api/v2/process_history/`)
  - `GET /api/v1/me/action-history`
  - `GET /api/v1/me/audit-log`
  - `GET /api/v1/conversations?user_id={id}` (era `/conversations/user/{id}`)
  - `POST /api/v1/me/action-history/{run_id}/undo`
- **Shapes:** ver `historialTypes.ts` — `ProcessHistoryItem` (con `steps[]` y
  `sub_steps[]` anidados), `ActionHistoryItem`, `AuditLogEvent`, `ConversationItem`,
  `ProcessHistoryMeta {total,page,limit,total_pages}`.
- [ ] Conectado

### 3. MemoryView — dos trabajos distintos, no uno
- **Mock:** `INITIAL_NODES`, `INITIAL_LINKS`, `CATEGORIES` en
  `memory/memoryMockData.ts:3,13,21` → `memory/useMemoryGraph.ts:11,20-21`.
- **Sync falso:** `setInterval(...,15000)` que alterna `isSyncing` (`:106-114`).
  IDs con `Date.now()` + `Math.random()` (`:285,:352-353,:366`).
- **⚠️ Gemini desde el navegador:** `const apiKey = "";` (`useMemoryGraph.ts:141`),
  usado en `callGemini` (`:142`) por `handleGenerateClusterFromIA` (`:295`),
  `handleExecuteRealReasoning` (`:389`) y `handleOptimizeEmbeddingSemantics` (`:434`).
  **No es una key faltante: es una llamada que debe vivir en el backend.** Poner
  la key ahí la expone a cualquier usuario que abra el DevTools.
- **Se parte en dos:**
  - **F1 — listar/editar facts:** `GET /api/v1/me/memories`,
    `PATCH|DELETE /api/v1/me/memories/{fact_id}`, `GET /api/v1/me/profile`. Existe hoy.
  - **F3 — razonamiento/clustering:** requiere endpoint nuevo en backend.
- **Shape:** `MemoryNode {id,label,category,importance(1-10),confidence(0-1),tags,content,x,y,frozen,archived}` ·
  `MemoryLink {id,source,target}`.
- [ ] F1 — facts conectados
- [ ] F3 — razonamiento movido al backend

### 4. ResourcesView
- **Mock:** `INITIAL_RESOURCES` en `resources/resourceMockData.ts:7` →
  `hooks/useResources.ts:3,31`. El `useEffect` (`:38-40`) es un stub explícito,
  sin red. Puente de estado local en `views/ResourcesView.tsx:19-23`.
- **Endpoints v1:** `GET /api/v1/uploads` · `POST /api/v1/uploads` ·
  `DELETE /api/v1/uploads/{public_id}`.
  Mapear con `mapCloudinaryToResources()` (`useResources.ts:13-26`).
- **Ojo — el backend no cubre todo el shape.** `Resource` incluye `category`,
  `starred`, `aiCompatible`, `tags[]`, `description`, `previewData` que
  **Cloudinary no devuelve**. Decidir antes de cablear: guardarlos en Mongo junto
  al `public_id`, o quitarlos del tipo. No inventar defaults silenciosos.
- [ ] Conectado

### 5. NotificationsView — 3 fuentes reales distintas, un solo mock que las mezcla
- **Mock:** `INITIAL_NOTIFICATIONS` (`notifications/notificationMockData.ts:5`).
- **localStorage como base de datos:** `STORAGE_KEY="hypershifu_notifications"`
  (`useNotifications.ts:13`), carga (`:69-72`), persiste en cada cambio (`:78-80`).
- **Generador aleatorio:** `buildRandomEvent()` (`:18-66`) fabrica los 3 `type` con
  `Math.random()`; `setInterval(...,45000)` inyecta uno cada 45 s (`:82-89`).
- **Consumido por (post-refactor):** el hook ya no se llama directo — vive en
  `context/NotificationsContext.tsx` (una sola instancia, montada en
  `PlatformRoot.tsx`) para no duplicar el `setInterval`/localStorage si dos
  componentes lo leen a la vez. Lo consumen: `index.tsx` (vista completa del
  sidebar), `components/NotificationsModal.tsx` (popup reusable) y el badge de
  la campana en `FlowDesigner/components/FlowDesignerToolbar.tsx:41`.
- **Los 3 `type` del union NO comparten backend — verificado contra el código real:**
  1. **`integration`** (Slack/Gmail/Notion, con `sender`/`snippet`/quick-reply)
     — **no existe nada en el backend.** Sin tabla, sin endpoint, sin poller.
     100% invención del mock. **F3**, no se puede tocar hasta que exista.
  2. **`usage_warning`** — existe, pero no como notificación persistida: es un
     mensaje efímero dentro del WS de chat (`app/routes/ws/debug_ws.py:35`) →
     `{"type":"usage_warning","message":"..."}`, montado en
     `/api/v1/ws/chat-debug?token=&conversation_id=` (`main.py:683`). Se
     dispara una vez por día al cruzar el 80% de cuota, **solo mientras hay una
     conversación de chat abierta** — este componente no se puede suscribir a
     eso de forma standalone. Para conectarlo de verdad, el listener tiene que
     vivir en el cliente WS del chat (`ChatInterface`/`FloatingChat`) y empujar
     el evento a `NotificationsContext` (ej. exponer un `pushLiveNotification()`).
     **F2, pero el trabajo real es en el chat, no en esta pantalla.**
  3. **`proactive_notification`** — existe y es standing:
     `app/workers/proactive_notifier.py` publica a Redis `wf:{user_id}` cada
     30 min (`goal_reminder` / `deadline_alert` / `workflow_failure`), y
     `app/routes/ws/workflow_ws.py` reenvía ese canal por
     `WS /api/v1/ws/runs?token=<JWT>` (`main.py:685`). Shape real
     (`proactive_notifier.py:99-106`):
     ```json
     {"type": "proactive_notification", "category": "goal_reminder",
      "title": "...", "body": "...", "user_id": "...", "timestamp": "2026-07-12T..."}
     ```
     **Falta `id`.** El backend no manda uno y `BaseNotification.id` es
     obligatorio en el frontend (key de React + `toggleReadStatus`). Generarlo
     client-side (ej. `` `proactive-${user_id}-${timestamp}` ``) sirve para la
     key, pero **no persiste leído/no-leído entre sesiones** — si eso importa,
     pedir que el backend agregue un `id` estable. **F2**, listo para cablear
     salvo por esto.
- **La bandeja "histórica"** (lo que se ve al abrir la pantalla sin eventos en
  vivo, hoy `INITIAL_NOTIFICATIONS`) mapea mejor a `announcements`, no a los 3
  tipos de arriba:
  - `GET /api/v1/me/announcements?status=pending&email=` ·
    `GET /api/v1/me/announcements/pending` (real, `app/routes/social/announcements.py:154-200`)
  - `POST /api/v1/me/announcements/{id}/view` `{email, announcement_id}` — marca
    leído (real, `:203-227`)
  - `POST /api/v1/me/announcements/views` `{email}` — marca todo leído, mapea a
    `markAllAsRead` (real, `:230-246`)
  - **Shape real de `Announcement` no calza con `Notification`:**
    `{announcement_id, title, description, short_description, image, video,
    active, created_at, status}` — es un feed de anuncios tipo CMS (con
    imagen/video), sin `type` discriminador ni los campos de
    `IntegrationNotification`/`ProactiveNotification`. Para usarlo hay que
    mapearlo a un 4º `type: "announcement"`, no forzarlo en la unión actual.
  - **Sin backend:** `toggleReadStatus` (volver a no-leído) y
    `deleteNotification` — `me_router` solo tiene `GET` y los dos
    `POST .../view(s)`; ningún `DELETE` ni forma de revertir `status` a
    `"pending"`. Si se necesitan de verdad, hay que pedirlos.
- **`resetDemo`/`clearAll` son solo del modo demo** (`useNotifications.ts:146-157`)
  — se borran junto con el mock, no tienen equivalente real.
- [ ] F2 — `proactive_notification` (agregar `id` estable) + anuncios
      (`GET/POST .../announcements*`, mapear shape a `type: "announcement"`)
- [ ] F2 (fuera de esta pantalla) — `usage_warning` escuchado desde el WS de
      chat, no desde `NotificationsView`
- [ ] F3 — `integration` (Slack/Gmail/Notion + quick reply): no existe backend

### 6. TableroView — 🔴 bloqueado por backend (F3)
- **Mock:** `INITIAL_WORKFLOWS`, `INITIAL_STEPS_BY_WORKFLOW` en
  `dashboard/data/workflow.data.ts:3` → `dashboard/hooks/useWorkflows.ts:3,6,16`.
- **⚠️ Gemini desde el navegador:** `const apiKey = "";` (`useWorkflows.ts:104`).
  Como está vacía, el fetch real (`:129-151`) nunca corre y cae a un generador de
  respuestas enlatadas con `setTimeout(...,1400)` (`:153-173`). Mover al backend.
- **Todo create/edit/delete muta estado local**, IDs con `Date.now()`.
- **Endpoints v1 (a construir en B2):** `GET|POST /api/v1/workflows` ·
  `GET|PATCH|DELETE /api/v1/workflows/{id}` · `POST /api/v1/workflows/{id}/runs`.
- **Shape:** `WorkflowSummary {id,name,description,status,steps_count,trigger_type,frequency_label,created_at,updated_at}` ·
  `WorkflowStep {id,type,title,description,configSummary,position{x,y}}`.
- [ ] Conectado *(no empezar hasta que exista el router de workflows)*

### 7. TasksView — 🔴 bloqueado por backend (F3)
- **Mock:** `workflowsMockData` (`tasks/tasksMockData.ts:3`) → `tasks/useTasks.ts:2,5`.
- **Análisis de error falso:** `analyzeError()` con `setTimeout(...,1600)` que
  devuelve un root-cause hardcodeado (`useTasks.ts:24-33`). El propio comentario
  (`:21-23`) dice que no hay backend.
- **`openWorkflowId` por defecto `"wf-1"`** hardcodeado (`useTasks.ts:6`).
- **Endpoints v1 (a construir):** `GET /api/v1/workflows/{id}/runs` + un endpoint
  de análisis de causa raíz (o reusar el agente).
- [ ] Conectado *(bloqueado)*

### 8. UserView — 🔴 bloqueado por backend (F3), pero el código ya está escrito
- **Mock:** `MOCK_MEMBERS` (`users/userMockData.ts:48`) →
  `users/useWorkspaceMembers.ts:4,18`.
- **Mutaciones locales optimistas** con `setTimeout` (`:17,46,75,92,112`) e IDs
  con `Math.random()` (`:49-50`).
- **`WORKSPACE_ID = "ws_shifu_prod_01"` hardcodeado** en `UserView.tsx:17`.
- **Código real ya escrito en comentarios**, 5 bloques en `useWorkspaceMembers.ts`:
  `:20-29` (GET), `:61-71` (invite), `:79-88` (role), `:98-107` (status),
  `:116-124` (DELETE). Todos ya importan `@/api/http`.
- **Endpoints v1 (a construir en B2):** `GET|POST /api/v1/workspaces/{id}/members` ·
  `PATCH|DELETE /api/v1/workspaces/{id}/members/{uid}`.
- **Shape:** `WorkspaceMember {id,user_id,name,email,role,status,joined_at?,last_active_at?,invited_by?,invited_at?}`.
- [ ] Conectado *(bloqueado)*

### 9. SecretsView — 🔴 bloqueado por backend (F3)
- **Mock:** `INITIAL_SECRETS` local en `views/SecretsView.tsx:31`.
  Nota explícita en `:18` ("wire to real API when secrets backend exists").
- **Solo estado en memoria** (`useState`, `:144`): create/delete mutan el array
  (`:214,:253`). **Se pierde todo al recargar** — ni siquiera hay localStorage.
- **Falsedades a eliminar:** `generateSecureKey()` usa `Math.random()` (`:219-230`),
  `labHash` es un "SHA256" falso con bitwise + `btoa` (`:267-275`), el score
  "98% Seguro" está hardcodeado (`:349-350`).
- **⚠️ Un vault de secretos con `Math.random()` y hash falso no debe llegar a v1.**
  O se construye el backend real (cifrado del lado servidor), o se oculta la vista.
- **Endpoints v1 (a construir):** `GET|POST|DELETE /api/v1/secrets[/{id}]`.
- [ ] Conectado *(bloqueado)*

---

## C. Limpieza — 8 vistas huérfanas (borrar, no conectar)

Ninguna está en el `viewMap` de `PlatformRoot.tsx:109-124` ni la importa nadie.
Verificar con grep antes de borrar (regla: si aparece un import, no es huérfana).

- [ ] `views/Graficas.tsx`
- [ ] `views/Orders.tsx`
- [ ] `views/Preferences.tsx` — SettingsView usa `PreferencesTab`, no esta vista
- [ ] `views/ProfileView.tsx`
- [ ] `views/ReferredView.tsx`
- [ ] `views/RewardsView.tsx`
- [ ] `views/ServiceVew.tsx` — solo la menciona un comentario viejo en `integrationSlice.ts:310`
- [ ] `views/SettingsPlan.tsx` — solo un comentario viejo en `subscriptionSlice.ts:147`
- [ ] `redux/slices/paymentsSlice.ts` — los 5 thunks solo hacen `console.warn("payments are disabled")` y devuelven `{subscription:null}`

**Por qué importa:** el plan anterior contaba los endpoints de Rewards, Referrals
y Payments como "por conectar". No hay pantalla que los consuma. Conectarlos
sería trabajo para nadie.

También: `redux/slices/blogSlice.ts` usa `localStorage` como base de datos
(`:4,24-35`) con 36 posts generados (`:6-22`). El backend de blog existe. Decidir
si el blog entra en v1 o se saca del dashboard.

---

## D. Higiene de cliente HTTP — bloquea todo lo demás

1. **Dos llaves de token distintas.** `src/api/http.ts` lee `access_token`;
   `src/api/apiPrincipal.ts` lee `token`. Según cuál guarde el login,
   **un cliente entero manda las requests sin auth**.
   → Colapsar a **un** cliente axios con `baseURL` e interceptor de refresh.
2. **URLs sin slash.** `apiUrl` quita el trailing slash y estos concatenan sin
   uno → `http://localhost:8000rewards`. Afecta `api/rewards/*.ts`,
   `api/referrals/ReferralsApi.ts`, `api/auth/updateImgApi.ts`,
   `features/build/components/FlowBuilder.tsx`.
   → **Desaparecen solas** al usar el cliente único con `baseURL`.
3. **Los dos `apiKey = ""`** (`useWorkflows.ts:104`, `useMemoryGraph.ts:141`):
   mover la llamada a Gemini al backend. **No poner la key en el frontend.**

- [ ] Cliente axios único
- [ ] Gemini movido al backend

---

## E. Fases (frontend)

| Fase | Qué | Depende de |
|---|---|---|
| **F0** | Borrar las 8 vistas huérfanas + `paymentsSlice`. Unificar cliente axios. | — |
| **F1** | Settings · Historial · Memory (facts) | Backend B0 (renombrado) |
| **F2** | Resources · Notifications | Backend B0 |
| **F3** | Tablero · Tasks · UserView · Secrets · Memory (razonamiento) | **Backend B2** (endpoints nuevos) |

**F0 va primero por una razón concreta:** mientras haya dos clientes axios con
llaves de token distintas, la mitad de las llamadas que cablees en F1 van a
llegar sin autenticación y vas a debuggear el endpoint equivocado.

---

## F. Progreso

| Grupo | Hecho | Total |
|---|---|---|
| Vistas conectadas | 1 / 10 | `InsightsView` es la única real |
| Vistas huérfanas borradas | 0 / 9 | incluye `paymentsSlice` |
| Higiene de cliente | 0 / 2 | axios único · Gemini al backend |
| Bloqueadas por backend | 4 | Tablero, Tasks, UserView, Secrets |

---

## G. Verificación

1. **Por pantalla:** abrir con usuario real, pestaña Network abierta. La llamada
   pega a `/api/v1/...`, el dato se ve en la UI.
2. **Grep de sanidad**, debe dar cero en los archivos ya conectados:
   `MOCK_`, `INITIAL_`, `mockHttp`, `IS_MOCK_ENV`, `apiKey = ""`,
   `Math.random()` usado para generar IDs.
3. **Sin paths legacy en el frontend:** grep de `/api/v2`, `/api/v4`,
   `/api/agent`, `/api/users` → cero resultados.
4. **Recargar la página** en Notifications y Secrets: los datos deben venir del
   backend, no de `localStorage` ni de memoria.
