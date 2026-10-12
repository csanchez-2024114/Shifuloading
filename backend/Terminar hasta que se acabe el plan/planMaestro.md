Ready for review
Select text to add comments on the plan
Conectar el 100% del dashboard a backend real — sin mocks, sin borrar vistas
Contexto
hyper-shifu-app/docs/FRONTEND_BACKEND_MAP.md (auditoría completa, generada hoy) mapeó cada pantalla del dashboard contra su backend real. Ya se ejecutó un primer batch (10 grupos en paralelo) que resolvió Connectors, Historial, Resources, Settings core, Notifications, Memory, y produjo 3 planes de arquitectura (Workflows router, Secrets vault, Workspace members) que quedaron pendientes de aprobación humana por ser decisiones de diseño (nuevos conceptos de datos, cifrado de credenciales).

El usuario confirmó: quiere toda la app conectada a backend real, sin mocks, y ninguna vista se borra — incluyendo las dos áreas que antes había pedido dejar afuera (Home/Insights analytics y la consolidación de los 4 chats con Gemini roto). Donde el backend no tenga un concepto de datos que matchee 1:1 lo que una vista pide (ej. "ROI de inversión", "tráfico web vs app"), se usa el dato real más cercano que exista y se ajusta el copy/label del chart para que sea honesto, en vez de inventar números falsos.

Decisiones ya tomadas por el usuario en esta sesión:

Secrets vault: clave de cifrado separada (SECRETS_ENCRYPTION_KEY), no reusar la global de OAuth.
Workspace members: un usuario puede pertenecer a varios workspaces (N:N) — requiere selector de workspace en el frontend (no existe hoy).
Home/Insights y chat consolidation: sí, incluir ambas. No borrar ninguna vista, todas se conectan a datos/backend real.
Durante la investigación de esta sesión se encontraron 2 gaps adicionales no listados originalmente en el doc, que quedan dentro de este plan porque bloquean el "sin mocks" real:

settings/utils/settingsApi.ts corre 100% en un mock local (IS_MOCK_ENV = true) — ninguna de las llamadas de Settings pega contra el backend real hoy, a pesar de que el Grupo 3 anterior ya corrigió las URLs (correctas, pero nunca ejecutadas porque el mock las intercepta).
El endpoint real de chat en producción (POST /api/v1/chat/stream, app/routes/chat/chat.py:317) nunca llama a track_daily_tokens/maybe_get_token_warning (app/core/quota.py) — el usage_warning real conectado en el batch anterior solo se dispara desde la consola de debug, nunca desde el chat que usan los usuarios reales.
Seguimiento de progreso (carpeta temporal, se borra al terminar)
Crear una carpeta Hasta que se complete se borra/ en la raíz de backend-hyper-shifu/ (repo principal de esta sesión) con un archivo .md por grupo, cada uno con checklist tipo - [ ] tarea, para que el progreso sobreviva aunque la sesión se corte por límite de tokens/contexto — cualquier sesión nueva puede abrir esta carpeta y saber exactamente qué falta sin tener que releer todo este plan. Cuando un grupo completo esté hecho y verificado, se tilda el archivo entero como listo (no se borra archivo por archivo, se borra toda la carpeta al final cuando los 8 grupos estén 100%).

Archivos a crear:

00-INDICE.md — lista de los 8 grupos con su estado (pendiente / en progreso / hecho) y de qué depende cada uno (el orden de ejecución de abajo).
A-workflows-router.md, B-tasks-flow-designer.md, C-secrets-vault.md, D-workspace-members.md, E-settings-demock.md, F-chat-token-tracking.md, G-home-insights.md, H-chat-consolidation.md — un checklist por grupo con los pasos concretos de la sección correspondiente de este plan.
Nota: el mock de selector de workspace (workspaceSlice.ts, incluye Departamentos) ya existe, construido por otra sesión — no hace falta un handoff de "crear el mock", solo queda wireado al backend real del Grupo D cuando esté listo (ver detalle en Grupo D).
Orden de ejecución
Los grupos A–G son independientes entre sí (archivos disjuntos) y pueden construirse en paralelo. Excepción: Grupo B depende de que A esté terminado (necesita el router de workflows para tener algo real que listar/ejecutar). El sub-ítem de WorkflowBoard dentro del Grupo H depende de que B esté terminado (necesita que el tablero ya use workflows reales, no el mock INITIAL_WORKFLOWS, antes de que el chat inline pueda operar sobre ellos).

A (Workflows router)  ──┬──▶ B (Tasks + Flow Designer execution)  ──▶ H.WorkflowBoard (chat inline)
                         │
C (Secrets vault)        │
D (Workspace members)    │      ← todos estos corren en paralelo con A/B desde el minuto 0
E (settingsApi de-mock)  │
F (chat.py token track)  │
G (Home/Insights)        │
H.resto (FloatingChat, Resources summary, Memory AI)  ← en paralelo, no dependen de B
Grupo A — Workflows REST router (backend)
Basado en el plan ya validado por el agente de arquitectura (investigó workflow_service.py, workflow_run_service.py, workflow_worker.py, workflow_executor.py, webhook_inbound.py como referencia).

Hallazgo clave: el pipeline de ejecución (worker, executor, pub/sub, WS /ws/runs) ya existe y funciona en producción (usado hoy por triggers de webhook/scheduler). Solo falta la superficie HTTP.

Construir app/routes/workflows/workflows.py (nuevo), montado en main.py (prefix="/api/v1/workflows", junto a los otros routers /api/v1/... ~línea 651):

GET /api/v1/workflows → list_user_workflows(), ya matchea WorkflowSummary del frontend 1:1.
POST /api/v1/workflows → nueva función de servicio en workflow_service.py que crea un workflow en blanco sin la semántica de conversation_id/dedup que tiene create_workflow() hoy (esa queda intacta para el flujo de chat con IA). Enforce max_workflows del plan igual que la función existente.
GET /api/v1/workflows/{id} → get_workflow_by_id(), ya scoped por user_id, 404 si None.
PATCH /api/v1/workflows/{id} → nueva update_workflow_fields() en workflow_service.py (mismo patrón que update_workflow_status, scoped por user_id). Si el body incluye steps, validar max_apps_per_workflow del plan (mismo check que ya existe en add_step_to_workflow) antes de persistir.
DELETE /api/v1/workflows/{id} → delete_workflow(), ya existe.
GET /api/v1/workflows/{id}/runs → list_user_runs() necesita un parámetro nuevo workflow_id: Optional[str] para filtrar (hoy solo filtra por user_id).
POST /api/v1/workflows/{id}/runs → copiar el patrón de webhook_inbound.py (fetch workflow → create_run(...) → 202 {run_id}). No copiar la segunda llamada directa asyncio.create_task(WorkflowExecutor(...).execute()) que tiene webhook_inbound.py — es un bug de doble-ejecución preexistente (el worker ya consume el stream solo); dejar que create_run() sea el único disparador. Permitir manual run sin exigir status == "active" (a diferencia del trigger de webhook) — es intención explícita del usuario al hacer clic en "Ejecutar".
Convención a seguir (ver app/routes/me/me.py): Depends(get_current_user), db = request.app.state.db, JSONResponse(jsonable_encoder(...)), sin wrapper {success, data}.

Actualizar docs/BACKEND_ENDPOINTS_V1.md marcando estas 3 filas como resueltas (regla propia del doc).

Grupo B — Tasks + ejecución en Flow Designer (frontend) — ESPERA a Grupo A
WorkflowBoard (features/workflows/components/WorkflowBoard/): reemplazar INITIAL_WORKFLOWS/INITIAL_STEPS_BY_WORKFLOW (mock en utils/workflow.data.ts) por GET/POST/PATCH/DELETE /api/v1/workflows reales.
Flow Designer save (FlowDesigner/index.tsx:145 handleSave, hoy ponytail: no backend save yet) → PATCH /api/v1/workflows/{id}.
Flow Designer tabs/canvas persistence (useFlowTabs.ts, hoy en memoria) → persistir vía el mismo PATCH.
Flow Designer "Ejecutar" (nodes/runFlowSimulation.ts:31) → POST /api/v1/workflows/{id}/runs, luego conectar al socket ya existente WS /api/v1/ws/runs (mismo patrón que ya usa features/debug/pages/WorkflowsDebug.tsx — reusar ese hook/lógica de conexión) para reflejar run_started/step_started/step_completed/.../run_completed en vivo.
Tasks view (features/tasks/, hoy workflowsMockData) → listar desde los mismos endpoints de workflows/runs.
Node palette (nodes/nodeDefaults.ts) queda igual, no es parte de este gap.
Grupo C — Secrets vault (backend nuevo + frontend)
Basado en el plan de arquitectura ya validado (investigó que app/core/security.py ya tiene cifrado Fernet real, patrón me.py de auth/audit, app/core/limiter.py para rate limiting).

Decisión confirmada por el usuario: clave de cifrado separada — nueva env var SECRETS_ENCRYPTION_KEY (no reusar ENCRYPTION_KEY de OAuth), misma mecánica Fernet de app/core/security.py pero una instancia/función distinta que derive de esta env var nueva.

Colección nueva user_secrets (agregar a app/core/constants.py::Collections):

{_id, user_id, name, service, category, description,
 secret_ciphertext,   # Fernet con SECRETS_ENCRYPTION_KEY
 secret_preview,      # últimos 4 chars en claro, para listar sin descifrar
 created_at, updated_at, last_used_at, reveal_count}
Router nuevo app/routes/me/secrets.py, montado prefix="/api/v1/me/secrets":

GET / — lista (nunca incluye el valor, solo secret_preview).
POST / — crea, cifra con la nueva función.
PATCH /{id} — edita metadata; si viene secret_value, rota (re-cifra, resetea reveal_count).
DELETE /{id} — hard delete (la UI dice "eliminar permanentemente").
POST /{id}/reveal — único endpoint que descifra y devuelve el valor real. Rate-limited (@limiter.limit("10/minute"), patrón de app/core/limiter.py). Actualiza last_used_at/reveal_count.
Cada mutación y cada reveal pasan por app.services.audit_service.log_event (nunca loguear el valor, solo metadata).

Frontend features/secrets/index.tsx: reemplazar el useState local + btoa fake por las 5 llamadas reales vía http.ts. El botón "ojo"/"copiar" pasa a disparar POST .../reveal on-demand (ya no viene el valor en el GET de lista) y cachea el resultado en memoria del componente para esa sesión.

Grupo D — Workspace members + Departamentos (backend nuevo + frontend, incluye selector de workspace)
Basado en el plan de arquitectura ya validado. Hallazgo clave: ya existe un embrión — Collections.WORKSPACES y onboardingRoutes.py:192-197 crea un doc {owner_id, workspace_name, created_at} por usuario al completar onboarding, sin miembros/roles.

Actualización importante: el selector de workspace ya tiene un mock frontend construido en hyper-shifu-app/src/redux/slices/workspaceSlice.ts (otra sesión ya lo armó) — más completo de lo que este plan asumía originalmente. Es la referencia de diseño (no un contrato literal a cumplir 1:1), incluye:

SEED_WORKSPACES — el workspace propio (role: "owner") + ejemplos de workspaces ajenos a los que fue invitado (role: "member").
joinWorkspaceByCode(code, name) — unirse a un workspace ajeno vía código de invitación, no email. Guarda en localStorage.
ownInviteCode / regenerateInviteCode() — el dueño del workspace tiene un código propio regenerable para compartir.
Departamentos (Department: {id, name, private}) — sub-grupos dentro del workspace propio del usuario (createDepartment, setActiveDepartmentId). Solo existen dentro de tu propio workspace, no dentro de uno ajeno donde sos member (setActiveWorkspaceId resetea activeDepartmentId a null al cambiar de workspace que no sea el propio).
Decisión confirmada por el usuario (precisada): creación de workspace 1:1, membresía N:N. Cada usuario tiene exactamente un workspace propio — el que ya se crea automáticamente en el onboarding — y no puede crear otro. Pero puede ser invitado y ser miembro de los workspaces de otras personas, así que en total pertenece a varios (el suyo + los compartidos). Requiere selector de workspace activo en el frontend (ya mockeado, ver arriba).

Departamentos — concepto nuevo, confirmado por el usuario: sub-grupos internos dentro del workspace propio de un usuario. No son workspaces independientes — sin billing/plan/miembros propios, heredan todo del workspace dueño. Solo el dueño del workspace los crea. Campos: id, name, private (bool — visibilidad; decorativo en el mock, este plan decide si en real controla algo de permisos: propuesta mínima viable — private=true simplemente lo oculta del listado para miembros que no son el dueño, sin lógica de permisos más profunda por ahora, ya que hoy ninguna entidad real (workflows, resources, tasks, etc.) se filtra por departamento — es un contenedor organizativo vacío, sin nada que proteger todavía). Full libertad de diseño en el schema real, tal como confirmó el usuario.

Colecciones nuevas:

workspace_members: {_id, workspace_id, user_id|null, email, role (owner|admin|member|viewer),
                     status (active|invited|suspended), invited_by, invited_at, joined_at,
                     last_active_at, created_at, updated_at}

workspace_departments: {_id, workspace_id, name, private (bool), created_by, created_at, updated_at}
Extender el doc workspaces existente con invite_code: str (regenerable, para el flujo de joinWorkspaceByCode).

Dos mecanismos de invitación distintos, ambos ya sketcheados por separado en el frontend — el backend soporta los dos:

Join por código (workspaceSlice.ts, self-serve): POST /api/v1/workspaces/join {code} — busca el workspace por invite_code, crea directo un workspace_members con role="member", status="active" (sin paso de invitación pendiente, es auto-servicio).
Invite por email + rol (useWorkspaceMembers.ts, admin-iniciado): POST /{workspace_id}/members/invite {email, role} — crea workspace_members con status="invited", user_id=null, se completa cuando esa persona se registra/loguea (ver flujo de authRoutes.py abajo).
Router nuevo app/routes/workspaces/workspaceRoutes.py, prefix="/api/v1/workspaces" (matchea el TODO ya escrito en docs/BACKEND_ENDPOINTS_V1.md:398-399):

GET / — lista los workspaces a los que pertenece el usuario logueado (propio + compartidos), para poblar el selector. Incluye invite_code solo en el propio (donde es owner).
POST /join — join por código (mecanismo 1 arriba). No hay POST / de creación manual de workspace.
POST /{workspace_id}/invite-code/regenerate — regenerar el código propio (regenerateInviteCode).
GET /{workspace_id}/members, POST /{workspace_id}/members/invite, PATCH /{workspace_id}/members/{member_id}/role, PATCH /.../status, DELETE /.../members/{member_id} — contrato de useWorkspaceMembers.ts:26,67,84,103,121. Solo owner/admin puede invitar/gestionar.
GET /{workspace_id}/departments, POST /{workspace_id}/departments — listar/crear departamentos. Crear es solo del dueño del workspace (no admin, per "solo el dueño los crea"). setActiveDepartmentId del mock queda como estado 100% local del frontend (como activeWorkspaceId), no necesita persistirse en backend.
Autorización: nueva require_workspace_role(workspace_id, actor_user_id, min_role, db) (análoga a verify_admin de rewardRoutes.py pero scoped a workspace — namespace separado de users.rol). Blindar contra remover/degradar al único owner.

En authRoutes.py (register_user/google_login): al crear/loguear, completar cualquier workspace_members pendiente (status="invited", user_id=null, mismo email) → user_id, status="active", joined_at. Único touch point nuevo sobre auth existente.

Frontend:

workspaceSlice.ts deja de ser mock/localStorage y pasa a leer/escribir contra los endpoints de arriba (mismo shape WorkspaceOption/Department, mismos nombres de acciones — el resto de componentes que ya consumen useWorkspace() no deberían necesitar cambios).
features/users/hooks/useWorkspaceMembers.ts: descomentar el bloque CÓDIGO DE PRODUCCIÓN (INTEGRACIÓN FUTURA), usando el workspace_id activo de workspaceSlice.
Nota de desambiguación: nada de esto tiene relación con FlowTabs.tsx/useFlowTabs.ts (los "espacios" dentro del Flow Designer, Grupo B — pestañas de layouts de canvas dentro de un mismo workflow, concepto totalmente distinto). Confirmado leyendo ambos archivos.
Grupo E — Settings de-mock (settingsApi.ts)
hyper-shifu-app/src/features/settings/utils/settingsApi.ts tiene IS_MOCK_ENV = true y un mockHttp completo que intercepta todo — nunca llega a pegarle al backend real a pesar de que las URLs ya están corregidas (Grupo 3 del batch anterior). Cambios:

Borrar IS_MOCK_ENV/mockDb/mockHttp, reemplazar executeRequest por el cliente canónico http.ts.
getProfile: GET /api/v1/me (no /api/users/me, que era el placeholder del mock).
getProducts: apunta hoy a /api/v2/stripe/products (legacy, 404 sin el flag) → cambiar a GET /api/v1/billing/products, que sí existe y devuelve {success, products} (app/routes/billing/billing_routes.py:111) — ajustar el shape de retorno (res.products, no el array directo).
El resto (updateProfile, changePassword, cancelSubscription, getAuditLog) ya tienen la URL correcta del Grupo 3 anterior — solo necesitan dejar de pasar por el mock.
Grupo F — Chat de producción: tracking de tokens real
app/routes/chat/chat.py::chat_stream (línea 317) nunca llama a track_daily_tokens/maybe_get_token_warning (app/core/quota.py), por eso el usage_warning conectado en el batch anterior solo dispara desde la consola de debug. Agregar, en el bloque de éxito de run_graph() (después de save_message, ~línea 377-386):

Contar tokens de la respuesta (buscar si ya hay un contador de tokens expuesto por el callback _ChatStreamer/LangGraph final_state antes de agregar una dependencia nueva; si no hay nada, aproximar con len(accumulated) // 4 como estimador simple — no traer una librería de tokenización nueva solo para esto).
Llamar track_daily_tokens(redis_client, user_id, tokens) y luego maybe_get_token_warning(redis_client, user_id, user_plan, total) (ya devuelve el CTA y publica en wf:{user_id} — no hace falta tocar nada más, ya está conectado al frontend).
Grupo G — Home/Insights: 8 endpoints de analytics
Hallazgo clave del research: existe app/services/workflow_analytics_service.py, ya construido y sin ningún router que lo consuma, con shapes de respuesta que ya matchean el contrato de estos charts — es per-workflow, no cuenta-completa, pero es el precedente de agregación a reusar/extender.

Nuevo router app/routes/me/analytics.py, prefix="/api/v1/me/analytics", mismo patrón que me.py. Por chart:

Endpoint	Fuente real	Nota
GET /gauge	get_daily_tokens_used() + get_plan_rules(plan)["daily_token_limit"] (quota.py/billing/plans.py)	Match directo, cero ambigüedad
GET /files	cloudinary_service.get_user_inventory() (ya usado por GET /api/v1/uploads/)	Reshape directo
GET /pie	intent_outcomes agrupado por tool_used/intent_type	Match directo
GET /line	intent_outcomes/workflow_runs contado por día, últimos 30d	Primer $group/$dateToString por fecha del repo — no hay patrón previo para copiar, escribirlo nuevo pero simple
GET /bar	intent_outcomes agrupado por tool_used: éxitos vs intentos	Repurpose: renombrar el copy del chart de "Alerta de Inventario" (stock/demanda) a algo honesto tipo "Uso de herramientas: éxitos vs intentos" — actualizar title/subtitle/sources hardcodeados en useFetchAnalyticsBar.ts, no solo el data
GET /area	acciones disparadas desde chat vs. desde workflow (intent_outcomes.workflow_id presente/ausente), por día	Repurpose: renombrar de "Tráfico Web vs App" a algo real tipo "Acciones: Chat vs Workflows"
GET /composed	visitas=intentos diarios, conversiones=éxitos diarios, ticket=promedio de execution_time_ms	Repurpose: renombrar de métricas ecommerce a "Intentos / Éxitos / Tiempo promedio"
GET /scatter	workflow_runs.duration_ms (x) vs cantidad de steps (y) vs status (z)	Repurpose fuerte: no hay ningún dato de inversión/ROI en el backend. Renombrar de "Correlación Inversión/ROI" a "Duración vs Complejidad de Runs" — dato real, pero el concepto original del chart no existe y no se va a fabricar
Para los 4 marcados "Repurpose": el trabajo no es solo el endpoint, es también editar el title/subtitle/sources/info.html hardcodeados en cada hook (src/hooks/useFetchAnalytics{Bar,Area,Composed,Scatter}.ts) para que el copy describa lo que el dato real muestra — nunca dejar una etiqueta que promete algo que el número no es.

Frontend: los 8 hooks (src/hooks/useFetchAnalytics*.ts) hoy usan fetch() crudo vía getApiBackend() (bypasea http.ts) — migrar los 8 al cliente canónico http.ts al mismo tiempo que se apunta a los endpoints nuevos.

Grupo H — Consolidación de chat: 4 sitios con Gemini roto → backend real
Ningún sitio se borra. Los 4 apuntan al chat real ya montado (POST /api/v1/chat/stream, SSE) usando el patrón ya probado en src/features/chat/components/ChatInput.tsx (parseo manual de frames SSE) — pero corrigiendo un bug que tiene esa referencia: ChatInput.tsx lee localStorage.getItem("token"), que nadie escribe nunca; el resto de la app (incluido el interceptor de http.ts) usa access_token. Los 4 sitios nuevos deben leer access_token, no copiar ese bug.

FloatingChat (features/chat/components/FloatingChat/) — fit directo: reemplazar fetchGeminiResponse por el fetch SSE a /chat/stream con {conversation_id, text}, acumular tokens en responseText, opcionalmente mapear eventos agent_status/tool_start al agentState que el widget ya tiene.

Resources "Generate AI summary" (resources/index.tsx:44) — fit parcial: no hay extracción de contenido de archivo en el backend, así que el prompt solo puede describir metadata (name/format/size/created_at), no el contenido real del archivo. Construir el text con esa metadata, consumir el SSE hasta done, mostrar text como el resumen. Documentar en el propio código (comentario corto) que es un resumen basado en metadata, no en contenido — para que quede claro que no es una limitación oculta.

Memory graph AI (memory/hooks/useMemoryGraph.ts, 3 sub-features: handleGenerateClusterFromIA, handleExecuteRealReasoning, handleOptimizeEmbeddingSemantics) — el único de los 4 con un mismatch real de arquitectura: chat_stream no tiene modo de salida estructurada (JSON schema), solo prosa libre. Solución mínima viable: instruir al modelo en el propio text a responder ÚNICAMENTE con JSON válido en el shape esperado, y parsear done.text defensivamente (recortar fences de markdown tipo ```json si aparecen, igual que ya hace ChatInput.tsx con otro tipo de formato). Marcar con un comentario ponytail: que esto es un parseo frágil de JSON-en-prosa (no hay modo structured output en el backend hoy) — techo conocido, no ocultarlo.

WorkflowBoard inline chat (WorkflowBoard/index.tsx handleSendMessage) — ESPERA a que el Grupo B termine. Una vez que el tablero use workflows reales (no el mock INITIAL_WORKFLOWS), no hace falta el protocolo casero [UPDATE_STEPS] que parsea JSON del lado cliente para mutar el canvas local: el shifu_graph real ya tiene tools (crear_workflow, agregar_paso_workflow, etc. en app/agent/shared/tools/providers/workflow_bigtools.py) que mutan el workflow directamente en Mongo del lado servidor. Enfoque: mandar el mensaje del usuario a /chat/stream incluyendo el workflow_id actual en el texto (ej. Estoy editando el workflow "{id}"...), mostrar la respuesta en prosa, y refrescar el workflow desde GET /api/v1/workflows/{id} cuando el evento done llega — si el agente usó una tool para mutar el workflow, el refetch trae el cambio real; si no, no pasa nada. Esto es más simple y más "real" que el enfoque original, y elimina el problema de que el protocolo [UPDATE_STEPS] no tiene equivalente en el backend real.

Verificación
Backend: por cada router nuevo, python -c "import main" (o el smoke check ya usado en el batch anterior) para confirmar que registra sin errores; correr los tests existentes si los hay para las colecciones tocadas.
Frontend: npx tsc -b --noEmit y npx eslint sobre los archivos tocados de cada grupo (mismo patrón de verificación que usó cada agente del batch anterior).
Manual/E2E mínimo por grupo (ya que hay UI involucrada): levantar el dev server y probar el flujo principal de cada pantalla tocada (crear/ejecutar un workflow, invitar un miembro, crear un secret y revelarlo, ver los 8 charts de Insights con datos reales, mandar un mensaje en cada uno de los 4 chats) — no asumir que pasar tsc/eslint implica que la feature funciona.
Confirmar que ninguna vista quedó vacía/rota: los charts "repurposed" (Bar/Area/Composed/Scatter) deben mostrar números reales con copy que los describa correctamente, no el copy original inventado.