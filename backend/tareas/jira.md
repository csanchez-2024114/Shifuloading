# Tareas: Jira Cloud

- **Funciones catalogadas:** 206 · **Hechas:** 0 · **Pendientes:** 206 · **Herramientas viejas a migrar:** 5 (columna "Herramienta vieja")
- **Documentación oficial:** https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
- **Fuentes que consultó el catálogo:** https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/ https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/ https://developer.atlassian.com/cloud/jira/platform/rate-limiting/ https://developer.atlassian.com/cloud/jira/software/rest/ https://docs.atlassian.com/jira-software/REST/7.2.3
- **Paginación típica:** Query params startAt y maxResults; offset-based típicamente 0-50 items por página
- **Qué no se pudo verificar:** Detalle de scopes por operacion y limites exactos segun plan (el catalogo los infirio del patron de la documentacion).
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/jira/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `jira`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `jira` |
| Variables del `.env` que necesitas | JIRA_CLIENT_ID, JIRA_CLIENT_SECRET, JIRA_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/jira/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `jira.user.me` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 (3LO) con authorization code grant. URL: https://auth.atlassian.com/authorize con scope, client_id, redirect_uri. Exchange code por access token en POST /oauth/token. |
| Duración del token (según el catálogo) | Access token típicamente dura 1 hora; requiere refresh token offline |
| Refresco (según el catálogo) | Refresh token implementado como rotating token; expira después de 90 días de inactividad (resetea con cada refresco). Incluir offline_access en scope inicial. |
| Permisos (según el catálogo) | read:jira-user (ver profiles), read:jira-work (leer issues/proyectos), write:jira-work (crear/editar issues), manage:jira-project (settings de proyecto), manage:jira-configuration (admin global), manage:jira-webhook (gestionar webhooks) |
| Restricciones de acceso | Requiere cloud_id (obtenible via GET /oauth/token/accessible-resources después de autenticar). Permisos del usuario limitan lo que el app puede hacer. Planes Enterprise requieren conformidad con rate limits por puntos a partir de Marzo 2026. |
| Límites de ritmo | Points-based (base 100k-150k + 10-30 por usuario por hora según plan), Burst per-endpoint (100+ tokens, refill 10+ tokens/seg), Per-issue writes (20 ops/2seg, 100 ops/30seg). Paginación: hasta 50 items por página por defecto. |
| Notas de esta app | Además del token hace falta el `cloud_id` del sitio (accessible-resources); verifica dónde lo guarda el callback. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/jira/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> jira`. | Cuenta con `provider: jira`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/jira.user.me/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> jira <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Jira Cloud. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/jira.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Issues (30)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.issue.create` | create | POST /rest/api/3/issue | Crear nuevo issue/ticket | projectKey, summary, issuetype, priority, description | id, key, url del issue | write:jira-work | — | create_jira_issue |
| [ ] | `jira.issue.get` | read | GET /rest/api/3/issue/{issueIdOrKey} | Obtener detalles completos de un issue | issueIdOrKey | todo: key, summary, status, assignee, priority, description, dates | read:jira-work | — | get_jira_issue |
| [ ] | `jira.issue.list` | read | GET /rest/api/3/issues/search | Buscar issues con JQL | jql, startAt, maxResults | lista de issues con key, summary, status, assignee | read:jira-work | — | search_jira_issues |
| [ ] | `jira.issue.update` | update | PUT /rest/api/3/issue/{issueIdOrKey} | Actualizar campos de un issue | issueIdOrKey, fields a cambiar | confirmación de actualización | write:jira-work | — | — |
| [ ] | `jira.issue.delete` | delete | DELETE /rest/api/3/issue/{issueIdOrKey} | Eliminar issue permanentemente | issueIdOrKey | — | write:jira-work | I | — |
| [ ] | `jira.issue.assign` | update | PUT /rest/api/3/issue/{issueIdOrKey}/assignee | Asignar issue a usuario | issueIdOrKey, assignee (accountId) | issue actualizado con nuevo assignee | write:jira-work | — | — |
| [ ] | `jira.issue.transition` | update | POST /rest/api/3/issue/{issueIdOrKey}/transitions | Cambiar estado de issue (mover en workflow) | issueIdOrKey, transitionId, fields | confirmación de transición aplicada | write:jira-work | — | — |
| [ ] | `jira.issue.get_transitions` | read | GET /rest/api/3/issue/{issueIdOrKey}/transitions | Obtener transiciones disponibles para un issue | issueIdOrKey | lista de transiciones (id, name) | read:jira-work | — | — |
| [ ] | `jira.issue.comment_create` | create | POST /rest/api/3/issue/{issueIdOrKey}/comments | Agregar comentario a issue | issueIdOrKey, body (texto del comentario) | id y contenido del comentario creado | write:jira-work | E | — |
| [ ] | `jira.issue.comment_get` | read | GET /rest/api/3/issue/{issueIdOrKey}/comments | Obtener todos los comentarios de un issue | issueIdOrKey, startAt, maxResults | lista de comentarios con author, timestamp, body | read:jira-work | — | — |
| [ ] | `jira.issue.comment_update` | update | PUT /rest/api/3/issue/{issueIdOrKey}/comments/{commentId} | Editar un comentario existente | issueIdOrKey, commentId, body | comentario actualizado | write:jira-work | — | — |
| [ ] | `jira.issue.comment_delete` | delete | DELETE /rest/api/3/issue/{issueIdOrKey}/comments/{commentId} | Eliminar comentario de issue | issueIdOrKey, commentId | — | write:jira-work | I | — |
| [ ] | `jira.issue.attachment_add` | create | POST /rest/api/3/issue/{issueIdOrKey}/attachments | Adjuntar archivo a issue | issueIdOrKey, file (multipart) | id y URL del attachment | write:jira-work | E | — |
| [ ] | `jira.issue.attachment_list` | read | GET /rest/api/3/issue/{issueIdOrKey} | Listar adjuntos de issue (dentro de details) | issueIdOrKey | lista de attachments con id, filename, size, url | read:jira-work | — | — |
| [ ] | `jira.issue.attachment_delete` | delete | DELETE /rest/api/3/attachments/{attachmentId} | Eliminar adjunto de issue | attachmentId | — | write:jira-work | I | — |
| [ ] | `jira.issue.worklog_add` | create | POST /rest/api/3/issue/{issueIdOrKey}/worklog | Registrar tiempo trabajado en issue | issueIdOrKey, timeSpent, started, comment | id y detalles del worklog creado | write:jira-work | — | — |
| [ ] | `jira.issue.worklog_list` | read | GET /rest/api/3/issue/{issueIdOrKey}/worklog | Obtener registro de tiempos de un issue | issueIdOrKey, startAt, maxResults | lista de worklogs con autor, tiempo, comentario | read:jira-work | — | — |
| [ ] | `jira.issue.worklog_update` | update | PUT /rest/api/3/issue/{issueIdOrKey}/worklog/{worklogId} | Actualizar registro de tiempo | issueIdOrKey, worklogId, timeSpent, started, comment | worklog actualizado | write:jira-work | — | — |
| [ ] | `jira.issue.worklog_delete` | delete | DELETE /rest/api/3/issue/{issueIdOrKey}/worklog/{worklogId} | Eliminar registro de tiempo | issueIdOrKey, worklogId | — | write:jira-work | I | — |
| [ ] | `jira.issue.link_create` | create | POST /rest/api/3/issueLink | Crear enlace entre dos issues | inwardIssue, outwardIssue, linkType | id del link creado | write:jira-work | — | — |
| [ ] | `jira.issue.link_list` | read | GET /rest/api/3/issue/{issueIdOrKey} | Listar enlaces de issue (dentro de details) | issueIdOrKey | lista de links con id, tipo, issue destino | read:jira-work | — | — |
| [ ] | `jira.issue.link_delete` | delete | DELETE /rest/api/3/issueLink/{linkId} | Eliminar enlace entre issues | linkId | — | write:jira-work | — | — |
| [ ] | `jira.issue.link_type_list` | read | GET /rest/api/3/issueLinkType | Obtener tipos de links disponibles | — | lista de linkTypes con id, name, inward, outward | read:jira-work | — | — |
| [ ] | `jira.issue.voter_add` | create | PUT /rest/api/3/issue/{issueIdOrKey}/votes | Votar por un issue | issueIdOrKey | — | write:jira-work | — | — |
| [ ] | `jira.issue.voter_remove` | delete | DELETE /rest/api/3/issue/{issueIdOrKey}/votes | Remover voto de issue | issueIdOrKey | — | write:jira-work | — | — |
| [ ] | `jira.issue.voter_list` | read | GET /rest/api/3/issue/{issueIdOrKey}/votes | Obtener lista de votantes de issue | issueIdOrKey | lista de usuarios que votaron | read:jira-work | — | — |
| [ ] | `jira.issue.watcher_add` | create | PUT /rest/api/3/issue/{issueIdOrKey}/watchers | Agregar usuario como observador de issue | issueIdOrKey, accountId | — | write:jira-work | E | — |
| [ ] | `jira.issue.watcher_remove` | delete | DELETE /rest/api/3/issue/{issueIdOrKey}/watchers | Remover observador de issue | issueIdOrKey, accountId | — | write:jira-work | — | — |
| [ ] | `jira.issue.watcher_list` | read | GET /rest/api/3/issue/{issueIdOrKey}/watchers | Obtener lista de observadores de issue | issueIdOrKey | lista de usuarios observando | read:jira-work | — | — |
| [ ] | `jira.issue.change_log` | read | GET /rest/api/3/issue/{issueIdOrKey}/changelog | Obtener historial de cambios de issue | issueIdOrKey, startAt, maxResults | lista de cambios con autor, fecha, campos modificados | read:jira-work | — | — |

### Projects (23)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.project.list` | read | GET /rest/api/3/project/search | Listar proyectos accesibles | startAt, maxResults | lista de proyectos con key, name, projectType | read:jira-work | — | get_jira_projects |
| [ ] | `jira.project.get` | read | GET /rest/api/3/project/{projectIdOrKey} | Obtener detalles de proyecto | projectIdOrKey | nombre, key, category, tipos de issue, componentes | read:jira-work | — | — |
| [ ] | `jira.project.create` | create | POST /rest/api/3/project | Crear nuevo proyecto | key, name, projectType (software, service_management, business) | id, key, projectId del proyecto nuevo | manage:jira-project | — | — |
| [ ] | `jira.project.update` | update | PUT /rest/api/3/project/{projectIdOrKey} | Actualizar configuración de proyecto | projectIdOrKey, campos a actualizar | proyecto actualizado | manage:jira-project | — | — |
| [ ] | `jira.project.delete` | delete | DELETE /rest/api/3/project/{projectIdOrKey} | Archivar o eliminar proyecto | projectIdOrKey | — | manage:jira-project | I | — |
| [ ] | `jira.project.avatar_list` | read | GET /rest/api/3/project/{projectIdOrKey}/avatars | Obtener avatares disponibles para proyecto | projectIdOrKey | lista de avatares (id, url) | read:jira-work | — | — |
| [ ] | `jira.project.avatar_set` | update | PUT /rest/api/3/project/{projectIdOrKey}/avatar | Cambiar avatar de proyecto | projectIdOrKey, avatarId | confirmación | manage:jira-project | — | — |
| [ ] | `jira.project.issue_type_list` | read | GET /rest/api/3/project/{projectIdOrKey}/issueTypes | Obtener tipos de issue de un proyecto | projectIdOrKey | lista de issue types con id, name, description | read:jira-work | — | — |
| [ ] | `jira.project.component_list` | read | GET /rest/api/3/project/{projectIdOrKey}/components | Listar componentes de proyecto | projectIdOrKey | lista de componentes con id, name, description | read:jira-work | — | — |
| [ ] | `jira.project.component_create` | create | POST /rest/api/3/component | Crear componente en proyecto | projectId, name, description | id y detalles del componente | manage:jira-project | — | — |
| [ ] | `jira.project.component_update` | update | PUT /rest/api/3/component/{componentId} | Actualizar componente de proyecto | componentId, campos a actualizar | componente actualizado | manage:jira-project | — | — |
| [ ] | `jira.project.component_delete` | delete | DELETE /rest/api/3/component/{componentId} | Eliminar componente de proyecto | componentId | — | manage:jira-project | — | — |
| [ ] | `jira.project.version_list` | read | GET /rest/api/3/project/{projectIdOrKey}/versions | Listar versiones de proyecto | projectIdOrKey, startAt, maxResults | lista de versiones con id, name, releaseDate | read:jira-work | — | — |
| [ ] | `jira.project.version_create` | create | POST /rest/api/3/version | Crear versión en proyecto | projectId, name, description, releaseDate | id y detalles de versión | manage:jira-project | — | — |
| [ ] | `jira.project.version_update` | update | PUT /rest/api/3/version/{versionId} | Actualizar versión de proyecto | versionId, campos a actualizar | versión actualizada | manage:jira-project | — | — |
| [ ] | `jira.project.version_release` | update | POST /rest/api/3/version/{versionId}/mergeto | Lanzar o completar versión | versionId, moveUnfixedIssuesTo | confirmación | manage:jira-project | — | — |
| [ ] | `jira.project.version_delete` | delete | DELETE /rest/api/3/version/{versionId} | Eliminar versión de proyecto | versionId | — | manage:jira-project | — | — |
| [ ] | `jira.project.status_list` | read | GET /rest/api/3/project/{projectIdOrKey}/statuses | Obtener estados disponibles en proyecto | projectIdOrKey | lista de estados con id, name, category | read:jira-work | — | — |
| [ ] | `jira.project.permission_list` | read | GET /rest/api/3/project/{projectIdOrKey}/permission | Listar permisos de proyecto | projectIdOrKey | matriz de permisos | manage:jira-project | — | — |
| [ ] | `jira.project.role_list` | read | GET /rest/api/3/project/{projectIdOrKey}/role | Listar roles de proyecto | projectIdOrKey | lista de roles con id, name, members | read:jira-work | — | — |
| [ ] | `jira.project.role_get` | read | GET /rest/api/3/project/{projectIdOrKey}/role/{roleId} | Obtener detalles de rol en proyecto | projectIdOrKey, roleId | miembros del rol | read:jira-work | — | — |
| [ ] | `jira.project.role_add_user` | update | POST /rest/api/3/project/{projectIdOrKey}/role/{roleId} | Agregar usuario a rol de proyecto | projectIdOrKey, roleId, accountIds | confirmación | manage:jira-project | — | — |
| [ ] | `jira.project.role_remove_user` | delete | DELETE /rest/api/3/project/{projectIdOrKey}/role/{roleId} | Remover usuario de rol de proyecto | projectIdOrKey, roleId, accountId | — | manage:jira-project | — | — |

### Users (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.user.me` ★ | read | GET /rest/api/3/myself | Obtener información del usuario actual | — | accountId, email, displayName, timeZone | read:jira-user | — | health_check_jira |
| [ ] | `jira.user.get` | read | GET /rest/api/3/user | Obtener detalles de usuario específico | accountId o username | accountId, email, displayName, avatar, groups | read:jira-user | — | — |
| [ ] | `jira.user.list` | read | GET /rest/api/3/users/search | Buscar usuarios | query, startAt, maxResults | lista de usuarios con accountId, displayName, email | read:jira-user | — | — |
| [ ] | `jira.user.create` | create | POST /rest/api/3/user | Crear nuevo usuario | emailAddress, displayName | accountId y detalles del usuario | manage:jira-configuration | — | — |
| [ ] | `jira.user.update` | update | PUT /rest/api/3/user | Actualizar detalles de usuario | accountId, campos a actualizar | usuario actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.user.delete` | delete | DELETE /rest/api/3/user | Desactivar/eliminar usuario | accountId | — | manage:jira-configuration | I | — |
| [ ] | `jira.user.columns` | read | GET /rest/api/3/user/columns | Obtener columnas preferidas del usuario en table de issues | accountId | lista de columnas (IDs de campos) | read:jira-user | — | — |
| [ ] | `jira.user.columns_set` | update | PUT /rest/api/3/user/columns | Establecer columnas preferidas para table | accountId, columnIds | confirmación | read:jira-user | — | — |
| [ ] | `jira.user.groups` | read | GET /rest/api/3/user/groups | Obtener grupos a los que pertenece usuario | accountId | lista de grupos | read:jira-user | — | — |
| [ ] | `jira.user.bulk_get` | read | GET /rest/api/3/user/bulk | Obtener detalles de múltiples usuarios por accountId | accountIds (lista) | lista de usuarios con detalles | read:jira-user | — | — |
| [ ] | `jira.user.bulk_account_ids` | read | GET /rest/api/3/user/bulk/migration | Obtener account IDs para lista de usernames (legacy) | usernames (lista) | mapeo username -> accountId | read:jira-user | — | — |

### Fields (14)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.field.list` | read | GET /rest/api/3/field | Listar todos los campos (system y custom) | — | lista de campos con id, name, type, schema | read:jira-work | — | — |
| [ ] | `jira.field.get` | read | GET /rest/api/3/field/{fieldId} | Obtener detalles de un campo específico | fieldId | nombre, tipo, descripción, esquema del campo | read:jira-work | — | — |
| [ ] | `jira.field.create` | create | POST /rest/api/3/field | Crear nuevo campo personalizado | name, type, description | fieldId del campo creado | manage:jira-configuration | — | — |
| [ ] | `jira.field.update` | update | PUT /rest/api/3/field/{fieldId} | Actualizar configuración de campo | fieldId, campos a actualizar | campo actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.field.delete` | delete | DELETE /rest/api/3/field/{fieldId} | Eliminar campo personalizado | fieldId | — | manage:jira-configuration | — | — |
| [ ] | `jira.field.option_list` | read | GET /rest/api/3/field/{fieldId}/options | Listar opciones de campo select | fieldId | lista de opciones con id, value | read:jira-work | — | — |
| [ ] | `jira.field.option_create` | create | POST /rest/api/3/field/{fieldId}/option | Agregar opción a campo select | fieldId, value | optionId creado | manage:jira-configuration | — | — |
| [ ] | `jira.field.option_update` | update | PUT /rest/api/3/field/{fieldId}/option/{optionId} | Actualizar opción de campo | fieldId, optionId, value | opción actualizada | manage:jira-configuration | — | — |
| [ ] | `jira.field.option_delete` | delete | DELETE /rest/api/3/field/{fieldId}/option/{optionId} | Eliminar opción de campo | fieldId, optionId | — | manage:jira-configuration | — | — |
| [ ] | `jira.field.context_list` | read | GET /rest/api/3/field/{fieldId}/contexts | Listar contextos (proyectos/types) donde aplica campo | fieldId, startAt, maxResults | lista de contextos | read:jira-work | — | — |
| [ ] | `jira.field.context_create` | create | POST /rest/api/3/field/{fieldId}/contexts | Crear contexto para aplicar campo a proyectos/types | fieldId, projectIds, issueTypeIds | contextId creado | manage:jira-configuration | — | — |
| [ ] | `jira.field.context_update` | update | PUT /rest/api/3/field/{fieldId}/contexts/{contextId} | Actualizar contexto de campo | fieldId, contextId, projectIds, issueTypeIds | contexto actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.field.context_delete` | delete | DELETE /rest/api/3/field/{fieldId}/contexts/{contextId} | Eliminar contexto de campo | fieldId, contextId | — | manage:jira-configuration | — | — |
| [ ] | `jira.field.search_available` | read | GET /rest/api/3/field/search | Buscar campos disponibles | query, startAt, maxResults | lista de campos que coinciden | read:jira-work | — | — |

### Webhooks (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.webhook.list` | read | GET /rest/api/3/webhook | Listar webhooks registrados | startAt, maxResults | lista de webhooks con id, url, events | manage:jira-webhook | — | — |
| [ ] | `jira.webhook.get` | read | GET /rest/api/3/webhook/{webhookId} | Obtener detalles de webhook | webhookId | url, eventos, último disparo | manage:jira-webhook | — | — |
| [ ] | `jira.webhook.create` | create | POST /rest/api/3/webhook | Registrar nuevo webhook | url, events (lista), filters | webhookId creado | manage:jira-webhook | E | — |
| [ ] | `jira.webhook.update` | update | PUT /rest/api/3/webhook/{webhookId} | Actualizar configuración de webhook | webhookId, url, events, filters | webhook actualizado | manage:jira-webhook | — | — |
| [ ] | `jira.webhook.delete` | delete | DELETE /rest/api/3/webhook/{webhookId} | Eliminar webhook | webhookId | — | manage:jira-webhook | — | — |
| [ ] | `jira.webhook.refresh` | update | PUT /rest/api/3/webhook/{webhookId}/refresh | Refrescar token de webhook | webhookId | nuevo token para verificar payload | manage:jira-webhook | — | — |

### Issue Types (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.issue_type.list` | read | GET /rest/api/3/issuetype | Listar tipos de issue globales | — | lista de tipos (Bug, Story, Task, Epic, etc.) | read:jira-work | — | — |
| [ ] | `jira.issue_type.get` | read | GET /rest/api/3/issuetype/{issueTypeId} | Obtener detalles de tipo de issue | issueTypeId | nombre, descripción, campos por defecto | read:jira-work | — | — |
| [ ] | `jira.issue_type.create` | create | POST /rest/api/3/issuetype | Crear tipo de issue personalizado | name, description, type | issueTypeId creado | manage:jira-configuration | — | — |
| [ ] | `jira.issue_type.update` | update | PUT /rest/api/3/issuetype/{issueTypeId} | Actualizar tipo de issue | issueTypeId, name, description | tipo actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.issue_type.delete` | delete | DELETE /rest/api/3/issuetype/{issueTypeId} | Eliminar tipo de issue | issueTypeId, alternativeIssueTypeId | confirmación | manage:jira-configuration | — | — |
| [ ] | `jira.issue_type.field_list` | read | GET /rest/api/3/issuetype/{issueTypeId}/fields | Obtener campos para tipo de issue | issueTypeId | lista de campos requeridos y opcionales | read:jira-work | — | — |

### Priorities (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.priority.list` | read | GET /rest/api/3/priority | Listar todas las prioridades | — | lista de prioridades (Highest, High, Medium, Low, Lowest) | read:jira-work | — | — |
| [ ] | `jira.priority.get` | read | GET /rest/api/3/priority/{priorityId} | Obtener detalles de prioridad | priorityId | nombre, descripción, iconUrl | read:jira-work | — | — |
| [ ] | `jira.priority.create` | create | POST /rest/api/3/priority | Crear prioridad personalizada | name, description, statusColor | priorityId creado | manage:jira-configuration | — | — |
| [ ] | `jira.priority.update` | update | PUT /rest/api/3/priority/{priorityId} | Actualizar prioridad | priorityId, name, description, statusColor | prioridad actualizada | manage:jira-configuration | — | — |
| [ ] | `jira.priority.delete` | delete | DELETE /rest/api/3/priority/{priorityId} | Eliminar prioridad | priorityId, defaultPriorityId | — | manage:jira-configuration | — | — |
| [ ] | `jira.priority.search` | read | GET /rest/api/3/priority/search | Buscar prioridades | query, startAt, maxResults | lista de prioridades que coinciden | manage:jira-configuration | — | — |

### Statuses & Workflows (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.status.list` | read | GET /rest/api/3/status | Listar todos los estados globales | — | lista de estados (Open, In Progress, Done, etc.) | read:jira-work | — | — |
| [ ] | `jira.status.get` | read | GET /rest/api/3/status/{statusId} | Obtener detalles de estado | statusId | nombre, descripción, categoría | read:jira-work | — | — |
| [ ] | `jira.status.create` | create | POST /rest/api/3/status | Crear estado personalizado | name, description, statusCategory | statusId creado | manage:jira-configuration | — | — |
| [ ] | `jira.status.update` | update | PUT /rest/api/3/status/{statusId} | Actualizar estado | statusId, name, description, statusCategory | estado actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.status.delete` | delete | DELETE /rest/api/3/status/{statusId} | Eliminar estado | statusId, statusCategoryId | — | manage:jira-configuration | — | — |
| [ ] | `jira.workflow.list` | read | GET /rest/api/3/workflow/search | Listar workflows | name, startAt, maxResults | lista de workflows con id, nombre, estado | read:jira-work | — | — |
| [ ] | `jira.workflow.get` | read | GET /rest/api/3/workflow | Obtener detalles de workflow (con transiciones) | name | transiciones, estados, validadores | read:jira-work | — | — |
| [ ] | `jira.workflow_scheme.list` | read | GET /rest/api/3/workflowscheme | Listar esquemas de workflow | startAt, maxResults | lista de schemes | manage:jira-configuration | — | — |
| [ ] | `jira.workflow_scheme.get` | read | GET /rest/api/3/workflowscheme/{schemeId} | Obtener detalles de scheme | schemeId | issue types y workflows asociados | manage:jira-configuration | — | — |
| [ ] | `jira.workflow_scheme.create` | create | POST /rest/api/3/workflowscheme | Crear scheme de workflow | name, description, workflows | schemeId creado | manage:jira-configuration | — | — |
| [ ] | `jira.workflow_scheme.update` | update | PUT /rest/api/3/workflowscheme/{schemeId} | Actualizar scheme | schemeId, workflows | scheme actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.workflow_scheme.delete` | delete | DELETE /rest/api/3/workflowscheme/{schemeId} | Eliminar scheme de workflow | schemeId, newSchemeId | — | manage:jira-configuration | — | — |

### Filters & Dashboards (15)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.filter.list` | read | GET /rest/api/3/filter/search | Listar filtros guardados | query, startAt, maxResults | lista de filtros con id, name, owner, jql | read:jira-work | — | — |
| [ ] | `jira.filter.get` | read | GET /rest/api/3/filter/{filterId} | Obtener detalles de filtro | filterId | nombre, propietario, query JQL, descripción | read:jira-work | — | — |
| [ ] | `jira.filter.create` | create | POST /rest/api/3/filter | Crear nuevo filtro guardado | name, description, jql, favourite | filterId creado | write:jira-work | — | — |
| [ ] | `jira.filter.update` | update | PUT /rest/api/3/filter/{filterId} | Actualizar filtro | filterId, name, description, jql | filtro actualizado | write:jira-work | — | — |
| [ ] | `jira.filter.delete` | delete | DELETE /rest/api/3/filter/{filterId} | Eliminar filtro guardado | filterId | — | write:jira-work | — | — |
| [ ] | `jira.filter.share_list` | read | GET /rest/api/3/filter/{filterId}/permission | Listar permisos de filtro | filterId | usuarios/grupos con acceso | read:jira-work | — | — |
| [ ] | `jira.filter.share_add` | create | POST /rest/api/3/filter/{filterId}/permission | Compartir filtro con usuario/grupo | filterId, accountId o groupName | permiso creado | write:jira-work | E | — |
| [ ] | `jira.filter.share_remove` | delete | DELETE /rest/api/3/filter/{filterId}/permission/{permissionId} | Remover acceso a filtro | filterId, permissionId | — | write:jira-work | — | — |
| [ ] | `jira.dashboard.list` | read | GET /rest/api/3/dashboard/search | Listar dashboards accesibles | query, startAt, maxResults | lista de dashboards con id, name, owner | read:jira-work | — | — |
| [ ] | `jira.dashboard.get` | read | GET /rest/api/3/dashboard/{dashboardId} | Obtener detalles de dashboard | dashboardId | nombre, gadgets, propietario, descripción | read:jira-work | — | — |
| [ ] | `jira.dashboard.create` | create | POST /rest/api/3/dashboard | Crear nuevo dashboard | name, description, gadgets | dashboardId creado | write:jira-work | — | — |
| [ ] | `jira.dashboard.update` | update | PUT /rest/api/3/dashboard/{dashboardId} | Actualizar dashboard | dashboardId, name, description, gadgets | dashboard actualizado | write:jira-work | — | — |
| [ ] | `jira.dashboard.delete` | delete | DELETE /rest/api/3/dashboard/{dashboardId} | Eliminar dashboard | dashboardId | — | write:jira-work | — | — |
| [ ] | `jira.dashboard.item_add` | create | POST /rest/api/3/dashboard/{dashboardId}/gadgets | Agregar gadget a dashboard | dashboardId, gadgetId, position | gadget agregado | write:jira-work | — | — |
| [ ] | `jira.dashboard.item_remove` | delete | DELETE /rest/api/3/dashboard/{dashboardId}/gadgets | Remover gadget de dashboard | dashboardId, gadgetId | — | write:jira-work | — | — |

### Resolutions (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.resolution.list` | read | GET /rest/api/3/resolution | Listar resoluciones disponibles | — | lista de resoluciones (Fixed, Won't Fix, Duplicate, etc.) | read:jira-work | — | — |
| [ ] | `jira.resolution.get` | read | GET /rest/api/3/resolution/{resolutionId} | Obtener detalles de resolución | resolutionId | nombre, descripción | read:jira-work | — | — |
| [ ] | `jira.resolution.create` | create | POST /rest/api/3/resolution | Crear resolución personalizada | name, description | resolutionId creado | manage:jira-configuration | — | — |
| [ ] | `jira.resolution.update` | update | PUT /rest/api/3/resolution/{resolutionId} | Actualizar resolución | resolutionId, name, description | resolución actualizada | manage:jira-configuration | — | — |
| [ ] | `jira.resolution.delete` | delete | DELETE /rest/api/3/resolution/{resolutionId} | Eliminar resolución | resolutionId, defaultResolutionId | — | manage:jira-configuration | — | — |

### Groups (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.group.list` | read | GET /rest/api/3/groups/picker | Buscar grupos | query, maxResults | lista de grupos | read:jira-user | — | — |
| [ ] | `jira.group.member_list` | read | GET /rest/api/3/group | Obtener miembros de grupo | groupname, startAt, maxResults | lista de usuarios en el grupo | read:jira-user | — | — |
| [ ] | `jira.group.member_add` | create | POST /rest/api/3/group/user | Agregar usuario a grupo | groupname, accountId | confirmación | manage:jira-configuration | — | — |
| [ ] | `jira.group.member_remove` | delete | DELETE /rest/api/3/group/user | Remover usuario de grupo | groupname, accountId | — | manage:jira-configuration | — | — |
| [ ] | `jira.group.create` | create | POST /rest/api/3/group | Crear nuevo grupo | name | groupname del grupo creado | manage:jira-configuration | — | — |
| [ ] | `jira.group.delete` | delete | DELETE /rest/api/3/group | Eliminar grupo | groupname | — | manage:jira-configuration | — | — |

### Screens & Configuration (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.screen.list` | read | GET /rest/api/3/screens | Listar pantallas de issue | startAt, maxResults | lista de screens con id, name | read:jira-work | — | — |
| [ ] | `jira.screen.get` | read | GET /rest/api/3/screens/{screenId} | Obtener detalles de screen | screenId | campos, tabs, orden | read:jira-work | — | — |
| [ ] | `jira.screen.create` | create | POST /rest/api/3/screens | Crear nueva pantalla | name, description | screenId creado | manage:jira-configuration | — | — |
| [ ] | `jira.screen.update` | update | PUT /rest/api/3/screens/{screenId} | Actualizar screen | screenId, name, description | screen actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.screen.delete` | delete | DELETE /rest/api/3/screens/{screenId} | Eliminar pantalla | screenId | — | manage:jira-configuration | — | — |
| [ ] | `jira.screen.field_add` | create | POST /rest/api/3/screens/{screenId}/fields | Agregar campo a screen | screenId, fieldId | confirmación | manage:jira-configuration | — | — |
| [ ] | `jira.screen.field_remove` | delete | DELETE /rest/api/3/screens/{screenId}/fields/{fieldId} | Remover campo de screen | screenId, fieldId | — | manage:jira-configuration | — | — |
| [ ] | `jira.screen_scheme.list` | read | GET /rest/api/3/screenscheme | Listar screen schemes | startAt, maxResults | lista de schemes | read:jira-work | — | — |
| [ ] | `jira.screen_scheme.get` | read | GET /rest/api/3/screenscheme/{screenSchemeId} | Obtener detalles de scheme | screenSchemeId | screens por operation | read:jira-work | — | — |
| [ ] | `jira.screen_scheme.create` | create | POST /rest/api/3/screenscheme | Crear screen scheme | name, screens | schemeId creado | manage:jira-configuration | — | — |
| [ ] | `jira.screen_scheme.update` | update | PUT /rest/api/3/screenscheme/{screenSchemeId} | Actualizar scheme | screenSchemeId, screens | scheme actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.screen_scheme.delete` | delete | DELETE /rest/api/3/screenscheme/{screenSchemeId} | Eliminar screen scheme | screenSchemeId | — | manage:jira-configuration | — | — |
| [ ] | `jira.notification_scheme.list` | read | GET /rest/api/3/notificationscheme | Listar notification schemes | startAt, maxResults | lista de schemes | read:jira-work | — | — |
| [ ] | `jira.notification_scheme.get` | read | GET /rest/api/3/notificationscheme/{schemeId} | Obtener detalles de scheme | schemeId | eventos y notificaciones | read:jira-work | — | — |
| [ ] | `jira.notification_scheme.create` | create | POST /rest/api/3/notificationscheme | Crear notification scheme | name, description, notificationSchemeEvents | schemeId creado | manage:jira-configuration | — | — |
| [ ] | `jira.notification_scheme.update` | update | PUT /rest/api/3/notificationscheme/{schemeId} | Actualizar notification scheme | schemeId | scheme actualizado | manage:jira-configuration | — | — |
| [ ] | `jira.notification_scheme.delete` | delete | DELETE /rest/api/3/notificationscheme/{schemeId} | Eliminar notification scheme | schemeId | — | manage:jira-configuration | — | — |

### Software (Agile) - Boards & Sprints (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.board.list` | read | GET /rest/agile/1.0/board | Listar tableros (Scrum/Kanban) | projectKeyOrId, startAt, maxResults | lista de tableros con id, name, type | read:jira-work | — | — |
| [ ] | `jira.board.get` | read | GET /rest/agile/1.0/board/{boardId} | Obtener detalles de tablero | boardId | nombre, tipo (Scrum/Kanban), proyecto, columnas | read:jira-work | — | — |
| [ ] | `jira.board.create` | create | POST /rest/agile/1.0/board | Crear nuevo tablero | name, type (scrum/kanban), projectId | boardId creado | write:jira-work | — | — |
| [ ] | `jira.board.update` | update | PUT /rest/agile/1.0/board/{boardId} | Actualizar tablero | boardId, name | tablero actualizado | write:jira-work | — | — |
| [ ] | `jira.board.delete` | delete | DELETE /rest/agile/1.0/board/{boardId} | Eliminar tablero | boardId | — | write:jira-work | — | — |
| [ ] | `jira.board.config_get` | read | GET /rest/agile/1.0/board/{boardId}/configuration | Obtener configuración de tablero | boardId | columnas, estimación, rank | read:jira-work | — | — |
| [ ] | `jira.board.config_update` | update | PUT /rest/agile/1.0/board/{boardId}/configuration | Actualizar configuración de tablero | boardId, columnas | confirmación | write:jira-work | — | — |
| [ ] | `jira.sprint.list` | read | GET /rest/agile/1.0/board/{boardId}/sprint | Listar sprints de tablero | boardId, startAt, maxResults | lista de sprints con id, name, state (active, future, closed) | read:jira-work | — | — |
| [ ] | `jira.sprint.get` | read | GET /rest/agile/1.0/sprint/{sprintId} | Obtener detalles de sprint | sprintId | nombre, fechas, estado, meta | read:jira-work | — | — |
| [ ] | `jira.sprint.create` | create | POST /rest/agile/1.0/board/{boardId}/sprint | Crear nuevo sprint | boardId, name, startDate, endDate | sprintId creado | write:jira-work | — | — |
| [ ] | `jira.sprint.update` | update | PUT /rest/agile/1.0/sprint/{sprintId} | Actualizar sprint | sprintId, name, startDate, endDate, goal | sprint actualizado | write:jira-work | — | — |
| [ ] | `jira.sprint.start` | update | POST /rest/agile/1.0/sprint/{sprintId}/start | Iniciar sprint | sprintId | confirmación | write:jira-work | — | — |
| [ ] | `jira.sprint.end` | update | POST /rest/agile/1.0/sprint/{sprintId}/end | Finalizar sprint | sprintId | confirmación | write:jira-work | — | — |
| [ ] | `jira.sprint.delete` | delete | DELETE /rest/agile/1.0/sprint/{sprintId} | Eliminar sprint | sprintId | — | write:jira-work | — | — |
| [ ] | `jira.sprint.issue_list` | read | GET /rest/agile/1.0/sprint/{sprintId}/issue | Obtener issues de sprint | sprintId, startAt, maxResults | lista de issues en el sprint | read:jira-work | — | — |
| [ ] | `jira.sprint.issue_add` | create | POST /rest/agile/1.0/sprint/{sprintId}/issue | Agregar issues a sprint | sprintId, issues (lista de keys) | confirmación | write:jira-work | — | — |
| [ ] | `jira.sprint.issue_remove` | delete | DELETE /rest/agile/1.0/sprint/{sprintId}/issue | Remover issues de sprint | sprintId, issues | — | write:jira-work | — | — |

### Software (Agile) - Backlog & Epics (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.backlog.list` | read | GET /rest/agile/1.0/board/{boardId}/backlog | Obtener issues en backlog | boardId, startAt, maxResults | lista de issues sin sprint | read:jira-work | — | — |
| [ ] | `jira.backlog.issue_move` | update | POST /rest/agile/1.0/backlog/issue | Mover issue al backlog o de sprint | issues, rankBeforeId, rankAfterId, sprintId | confirmación | write:jira-work | — | — |
| [ ] | `jira.backlog.issue_rank` | update | PUT /rest/agile/1.0/backlog/issue/rank | Cambiar orden (rank) de issues en backlog | issues, rankBeforeId, rankAfterId | confirmación | write:jira-work | — | — |
| [ ] | `jira.epic.list` | read | GET /rest/agile/1.0/board/{boardId}/epic | Listar epics en tablero | boardId, startAt, maxResults | lista de epics | read:jira-work | — | — |
| [ ] | `jira.epic.get` | read | GET /rest/agile/1.0/epic/{epicId} | Obtener detalles de epic | epicId | nombre, estado, issues en epic | read:jira-work | — | — |
| [ ] | `jira.epic.create` | create | POST /rest/agile/1.0/epic | Crear epic | name, key, projectId | epicId creado | write:jira-work | — | — |
| [ ] | `jira.epic.update` | update | PUT /rest/agile/1.0/epic/{epicId} | Actualizar epic | epicId, name, done (completado) | epic actualizado | write:jira-work | — | — |
| [ ] | `jira.epic.delete` | delete | DELETE /rest/agile/1.0/epic/{epicId} | Eliminar epic | epicId | — | write:jira-work | — | — |
| [ ] | `jira.epic.issue_list` | read | GET /rest/agile/1.0/epic/{epicId}/issue | Obtener issues de un epic | epicId, startAt, maxResults | lista de issues en epic | read:jira-work | — | — |
| [ ] | `jira.epic.issue_add` | create | POST /rest/agile/1.0/epic/{epicId}/issue | Agregar issue a epic | epicId, issues (lista) | confirmación | write:jira-work | — | — |
| [ ] | `jira.epic.issue_remove` | delete | DELETE /rest/agile/1.0/epic/{epicId}/issue | Remover issue de epic | epicId, issues | — | write:jira-work | — | — |

### Software (Agile) - Reports (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.sprint.report_burndown` | read | GET /rest/agile/1.0/sprint/{sprintId}/report | Obtener reporte burndown de sprint | sprintId | gráfico burndown, velocidad, datos históricos | read:jira-work | — | — |
| [ ] | `jira.sprint.report_velocity` | read | GET /rest/agile/1.0/board/{boardId}/reports/velocity | Obtener reporte de velocidad | boardId | velocidad por sprint histórica | read:jira-work | — | — |
| [ ] | `jira.sprint.report_cumulative` | read | GET /rest/agile/1.0/board/{boardId}/reports/cumulative | Obtener reporte cumulative flow | boardId | flujo acumulativo de issues | read:jira-work | — | — |

### Advanced Features (24)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `jira.jql.autocomplete_suggestions` | read | GET /rest/api/3/jql/autocompletedata/suggestions | Obtener sugerencias autocomplete para JQL | fieldName, fieldValue | lista de valores sugeridos | read:jira-work | — | — |
| [ ] | `jira.jql.field_autocomplete` | read | GET /rest/api/3/jql/autocompletedata/suggestions | Obtener campos disponibles para JQL | — | lista de nombres de campos para usar en JQL | read:jira-work | — | — |
| [ ] | `jira.jql.validate` | read | GET /rest/api/3/jql/validate | Validar sintaxis de JQL query | jql | validación y mensajes de error | read:jira-work | — | — |
| [ ] | `jira.jql.function` | read | GET /rest/api/3/jql/function | Listar funciones JQL disponibles | — | lista de funciones (currentUser(), now(), etc.) | read:jira-work | — | — |
| [ ] | `jira.custom_field.search` | read | GET /rest/api/3/field/search | Buscar custom fields por nombre | query | lista de custom fields | read:jira-work | — | — |
| [ ] | `jira.permission.list` | read | GET /rest/api/3/permissions | Listar permisos globales de Jira | — | lista de permisos disponibles | read:jira-work | — | — |
| [ ] | `jira.permission.check` | read | GET /rest/api/3/user/permissions | Verificar qué permisos tiene usuario | projectKey, issueKey | permisos que tiene el usuario | read:jira-user | — | — |
| [ ] | `jira.application_role.list` | read | GET /rest/api/3/applicationrole | Listar roles de aplicación | — | lista de roles (Jira Administrators, etc.) | read:jira-user | — | — |
| [ ] | `jira.avatar.global_list` | read | GET /rest/api/3/avatar/issuetype/system | Listar avatares globales | — | lista de avatares disponibles | read:jira-work | — | — |
| [ ] | `jira.settings.get` | read | GET /rest/api/3/settings | Obtener configuración global de Jira | — | — | allowUnassignedIssues, defaultVotingEnabled, timeTracking | read:jira-work | — |
| [ ] | `jira.settings.update` | update | PUT /rest/api/3/settings | Actualizar configuración global | allowUnassignedIssues, defaultVotingEnabled, etc. | confirmación | manage:jira-configuration | — | — |
| [ ] | `jira.audit_record.list` | read | GET /rest/api/3/events | Obtener registros de auditoría | offset, limit, after, filter | eventos y cambios en Jira | manage:jira-configuration | — | — |
| [ ] | `jira.issue.bulk_delete` | delete | POST /rest/api/3/issue/delete | Eliminar múltiples issues en batch | issueIds | confirmación | write:jira-work | I | — |
| [ ] | `jira.issue.bulk_edit` | update | POST /rest/api/3/issue/bulk | Editar múltiples issues simultáneamente | issueIds, fields | confirmación | write:jira-work | — | — |
| [ ] | `jira.issue.bulk_change_assignee` | update | PUT /rest/api/3/issue/bulk/assignee | Reasignar múltiples issues | issueIds, assignee | confirmación | write:jira-work | — | — |
| [ ] | `jira.issue.bulk_move` | update | POST /rest/api/3/issue/bulk/move | Mover múltiples issues (cambiar proyecto) | issueIds, projectId | confirmación | write:jira-work | — | — |
| [ ] | `jira.issue.navigator_default` | read | GET /rest/api/3/issues/navigator/default | Obtener configuración por defecto del navigator | — | columnas por defecto, filtros predeterminados | read:jira-work | — | — |
| [ ] | `jira.issue.navigator_set` | update | PUT /rest/api/3/issues/navigator/default | Establecer configuración default del navigator | columnIds | confirmación | write:jira-work | — | — |
| [ ] | `jira.expression.evaluate` | read | POST /rest/api/3/expression/eval | Evaluar expresión Jira (similar a JQL) | expression, context | resultado de la evaluación | read:jira-work | — | — |
| [ ] | `jira.share.issue_link` | read | GET /rest/api/3/issue/{issueIdOrKey}/remotelink | Obtener remote links de issue (links a systems externos) | issueIdOrKey | lista de links externos | read:jira-work | — | — |
| [ ] | `jira.share.issue_link_create` | create | POST /rest/api/3/issue/{issueIdOrKey}/remotelink | Crear remote link a sistema externo | issueIdOrKey, link object | remoteLink creado | write:jira-work | E | — |
| [ ] | `jira.share.issue_link_delete` | delete | DELETE /rest/api/3/issue/{issueIdOrKey}/remotelink/{remoteLinkId} | Eliminar remote link | issueIdOrKey, remoteLinkId | — | write:jira-work | — | — |
| [ ] | `jira.share.attachment_link` | read | GET /rest/api/3/attachment/{attachmentId} | Obtener detalles de attachment | attachmentId | contenido, metadata, URL de descarga | read:jira-work | — | — |
| [ ] | `jira.permissions.bulk_check` | read | POST /rest/api/3/user/permissions/check | Verificar permisos de usuario en múltiples issues | accountId, permissions, issues | matriz de permisos | read:jira-user | — | — |
