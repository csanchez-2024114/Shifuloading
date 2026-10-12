# Tareas: ClickUp

- **Funciones catalogadas:** 179 · **Hechas:** 0 · **Pendientes:** 179 · **Herramientas viejas a migrar:** 14 (columna "Herramienta vieja")
- **Documentación oficial:** https://developer.clickup.com/reference
- **Fuentes que consultó el catálogo:** https://developer.clickup.com/reference https://developer.clickup.com/docs/authentication https://developer.clickup.com/docs/rate-limits https://consultevo.com/clickup-api-faq-how-to-guide/ https://dev.to/zuplo/clickup-api-a-comprehensive-guide-5b0h
- **Paginación típica:** Page-based, parámetro page comienza en 0; default limit 100 records; respuesta incluye last_page boolean
- **Qué no se pudo verificar:** Scopes OAuth específicos no encontrados en documentación accesible; restricciones de app review no mencionadas; algunos detalles de custom fields y vistas podrían variar según plan
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/clickup/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `clickup`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `clickup` |
| Variables del `.env` que necesitas | CLICKUP_CLIENT_ID, CLICKUP_CLIENT_SECRET, CLICKUP_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/clickup/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `clickup.user.get` |
| Cómo se autentica (según el catálogo) | OAuth2 (Authorization Code) o token personal (pk_*) enviado sin prefijo en Authorization header |
| Duración del token (según el catálogo) | No caduca (indefinido, sujeto a cambios según documentación) |
| Refresco (según el catálogo) | no |
| Permisos (según el catálogo) | Scopes no documentados explícitamente; acceso basado en rol/permisos del usuario dentro del workspace |
| Restricciones de acceso | Rate limits varían por plan (Free/Unlimited/Business: 100 req/min; Business Plus: 1000 req/min; Enterprise: 10000 req/min). Algunas features (Goals, Advanced webhooks, SCIM) son plan-específicas. |
| Límites de ritmo | 100-10000 requests por minuto según plan; respuesta HTTP 429 cuando se excede; headers X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset |
| Notas de esta app | El token se envía crudo en `Authorization`, sin `Bearer` (`scheme=""`). |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/clickup/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> clickup`. | Cuenta con `provider: clickup`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/clickup.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> clickup <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de ClickUp. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/clickup.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### User & Authentication (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.user.get` ★ | read | GET /user | Obtiene información del usuario autenticado actual | — | {id, username, email, role} | — | — | — |
| [ ] | `clickup.user.update` | update | PUT /user/{user_id} | Actualiza nombre y rol del usuario | user_id, name, role | {id, username, email} | — | — | — |
| [ ] | `clickup.user.delete` | delete | DELETE /user/{user_id} | Desactiva usuario del workspace | user_id | confirmación | — | I | — |

### Workspaces & Teams (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.workspaces.list` | read | GET /team | Lista todos los workspaces autorizados del usuario | — | {teams: [{id, name, color}]} | — | — | — |
| [ ] | `clickup.workspace.get_plan` | read | GET /team/{workspace_id}/plan | Obtiene plan y detalles de suscripción del workspace | workspace_id | {plan_name, status, features} | — | — | — |
| [ ] | `clickup.workspace.get_seats` | read | GET /team/{workspace_id}/seat | Verifica asignación de asientos/licencias | workspace_id | {total_seats, used_seats, available} | — | — | — |

### Spaces (Espacios) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.spaces.list` | read | GET /team/{workspace_id}/space | Lista todos los espacios del workspace | workspace_id, page | {spaces: [{id, name, color, private}]} | — | — | list_clickup_spaces |
| [ ] | `clickup.spaces.create` | create | POST /team/{workspace_id}/space | Crea un nuevo espacio | workspace_id, name, color, private | {id, name, color, private} | — | E | — |
| [ ] | `clickup.spaces.get` | read | GET /space/{space_id} | Obtiene detalles de un espacio específico | space_id | {id, name, color, access_type, members} | — | — | — |
| [ ] | `clickup.spaces.update` | update | PUT /space/{space_id} | Actualiza nombre, color o privacidad del espacio | space_id, name, color, private | {id, name, color, private} | — | — | — |
| [ ] | `clickup.spaces.delete` | delete | DELETE /space/{space_id} | Elimina un espacio y su contenido | space_id | confirmación | — | I | — |
| [ ] | `clickup.spaces.get_views` | read | GET /space/{space_id}/view | Lista vistas del espacio (List, Board, Calendar, etc.) | space_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.spaces.create_view` | create | POST /space/{space_id}/view | Crea una nueva vista en el espacio | space_id, name, type, settings | {id, name, type} | — | — | — |

### Folders (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.folders.list` | read | GET /space/{space_id}/folder | Lista carpetas del espacio | space_id, page | {folders: [{id, name, lists_count}]} | — | — | list_clickup_folders |
| [ ] | `clickup.folders.create` | create | POST /space/{space_id}/folder | Crea nueva carpeta en el espacio | space_id, name | {id, name, access_type} | — | — | create_clickup_folder |
| [ ] | `clickup.folders.get` | read | GET /folder/{folder_id} | Obtiene detalles de una carpeta | folder_id | {id, name, lists_count, created_at} | — | — | — |
| [ ] | `clickup.folders.update` | update | PUT /folder/{folder_id} | Actualiza nombre de la carpeta | folder_id, name | {id, name} | — | — | — |
| [ ] | `clickup.folders.delete` | delete | DELETE /folder/{folder_id} | Elimina carpeta | folder_id | confirmación | — | I | — |
| [ ] | `clickup.folders.move` | update | POST /folder/{folder_id}/move | Mueve carpeta a otro espacio | folder_id, target_space_id | {id, name} | — | — | — |
| [ ] | `clickup.folders.get_views` | read | GET /folder/{folder_id}/view | Lista vistas de la carpeta | folder_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.folders.create_view` | create | POST /folder/{folder_id}/view | Crea vista en carpeta | folder_id, name, type | {id, name, type} | — | — | — |
| [ ] | `clickup.folders.get_comments` | read | GET /folder/{folder_id}/comment | Obtiene comentarios de la carpeta | folder_id, page | {comments: [{id, user, text, date}]} | — | — | — |
| [ ] | `clickup.folders.create_from_template` | create | POST /space/{space_id}/folder/from_template | Crea carpeta desde plantilla | space_id, template_id | {id, name, lists: []} | — | — | — |

### Lists (Listas) (14)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.lists.list` | read | GET /folder/{folder_id}/list | Lista listas dentro de una carpeta | folder_id, page | {lists: [{id, name, tasks_count}]} | — | — | list_clickup_lists |
| [ ] | `clickup.lists.list_folderless` | read | GET /space/{space_id}/list | Lista listas sin carpeta en espacio | space_id, page | {lists: [{id, name, tasks_count}]} | — | — | — |
| [ ] | `clickup.lists.create` | create | POST /folder/{folder_id}/list | Crea lista en carpeta | folder_id, name, content, priority, assignee, due_date | {id, name, task_count} | — | — | create_clickup_list |
| [ ] | `clickup.lists.create_folderless` | create | POST /space/{space_id}/list | Crea lista sin carpeta en espacio | space_id, name, content, priority | {id, name, task_count} | — | — | — |
| [ ] | `clickup.lists.get` | read | GET /list/{list_id} | Obtiene detalles de una lista | list_id | {id, name, task_count, access, members} | — | — | — |
| [ ] | `clickup.lists.update` | update | PUT /list/{list_id} | Actualiza propiedades de lista | list_id, name, content | {id, name} | — | — | — |
| [ ] | `clickup.lists.delete` | delete | DELETE /list/{list_id} | Elimina lista | list_id | confirmación | — | I | — |
| [ ] | `clickup.lists.get_members` | read | GET /list/{list_id}/member | Lista miembros explícitos asignados a lista | list_id | {members: [{id, username, email}]} | — | — | — |
| [ ] | `clickup.lists.get_comments` | read | GET /list/{list_id}/comment | Obtiene comentarios de la lista | list_id, page | {comments: [{id, user, text}]} | — | — | — |
| [ ] | `clickup.lists.create_comment` | create | POST /list/{list_id}/comment | Añade comentario a la lista | list_id, comment_text | {id, user, text, created_at} | — | E | — |
| [ ] | `clickup.lists.get_views` | read | GET /list/{list_id}/view | Lista vistas de la lista | list_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.lists.create_view` | create | POST /list/{list_id}/view | Crea vista de lista | list_id, name, type, settings | {id, name, type} | — | — | — |
| [ ] | `clickup.lists.create_from_template` | create | POST /folder/{folder_id}/list/from_template | Crea lista desde plantilla en carpeta | folder_id, template_id | {id, name, tasks: []} | — | — | — |
| [ ] | `clickup.lists.create_from_template_space` | create | POST /space/{space_id}/list/from_template | Crea lista desde plantilla en espacio | space_id, template_id | {id, name, tasks: []} | — | — | — |

### Tasks (Tareas) (18)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.tasks.list` | read | GET /list/{list_id}/task | Lista tareas de una lista | list_id, page, statuses, assignees | {tasks: [{id, name, status, priority}]} | — | — | list_clickup_tasks |
| [ ] | `clickup.tasks.list_workspace` | read | GET /team/{workspace_id}/task | Lista tareas filtradas del workspace | workspace_id, statuses, assignees, page, date_range | {tasks: [{id, name, list_id}]} | — | — | — |
| [ ] | `clickup.tasks.get` | read | GET /task/{task_id} | Obtiene detalles completos de tarea | task_id, include_subtasks | {id, name, status, assignees, due_date, description, checklists} | — | — | get_clickup_task |
| [ ] | `clickup.tasks.create` | create | POST /list/{list_id}/task | Crea nueva tarea | list_id, name, description, assignees, due_date, priority, tags, custom_fields | {id, name, status, created_at} | — | — | create_clickup_task |
| [ ] | `clickup.tasks.update` | update | PUT /task/{task_id} | Actualiza propiedades de tarea | task_id, name, description, status, priority, due_date, assignees | {id, name, updated_at} | — | — | — |
| [ ] | `clickup.tasks.delete` | delete | DELETE /task/{task_id} | Elimina tarea | task_id | confirmación | — | I | — |
| [ ] | `clickup.tasks.assign` | update | POST /task/{task_id}/assignee | Asigna o reasigna tarea a usuario | task_id, user_id | {id, assignees} | — | E | assign_clickup_task |
| [ ] | `clickup.tasks.unassign` | update | DELETE /task/{task_id}/assignee | Desasigna usuario de tarea | task_id, user_id | {id, assignees} | — | — | — |
| [ ] | `clickup.tasks.update_status` | update | PUT /task/{task_id}/status | Cambia estado/status de tarea | task_id, status_id, status_name | {id, status} | — | — | — |
| [ ] | `clickup.tasks.update_priority` | update | PUT /task/{task_id}/priority | Actualiza prioridad de tarea | task_id, priority_level | {id, priority} | — | — | — |
| [ ] | `clickup.tasks.update_due_date` | update | PUT /task/{task_id}/due_date | Cambia fecha de vencimiento | task_id, due_date | {id, due_date} | — | — | update_clickup_due_date |
| [ ] | `clickup.tasks.move` | update | POST /task/{task_id}/move | Mueve tarea a otra lista | task_id, list_id | {id, name} | — | — | — |
| [ ] | `clickup.tasks.add_to_list` | update | POST /task/{task_id}/list | Añade tarea a lista adicional | task_id, list_id | {id, lists: []} | — | — | — |
| [ ] | `clickup.tasks.remove_from_list` | update | DELETE /task/{task_id}/list/{list_id} | Quita tarea de lista secundaria | task_id, list_id | confirmación | — | — | — |
| [ ] | `clickup.tasks.merge` | update | POST /task/{task_id}/merge | Consolida múltiples tareas en una | task_id, source_task_ids | {id, name} | — | I | — |
| [ ] | `clickup.tasks.create_from_template` | create | POST /task/{task_id}/from_template | Genera tarea desde plantilla | task_id, template_id | {id, name} | — | — | — |
| [ ] | `clickup.tasks.search` | read | POST /team/{workspace_id}/task | Búsqueda de tareas con filtros complejos | workspace_id, query, statuses, priority, assignees, tags | {tasks: [{id, name}]} | — | — | — |
| [ ] | `clickup.tasks.get_time_in_status` | read | GET /task/{task_id}/time_in_status | Tiempo empleado en cada estado de tarea | task_id | {time_spent_per_status: [{status, seconds}]} | — | — | — |

### Dependencies & Links (Dependencias y Enlaces) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.tasks.create_dependency` | create | POST /task/{task_id}/dependency | Establece dependencia entre tareas | task_id, depends_on_task_id, dependency_type | {id, dependencies} | — | — | — |
| [ ] | `clickup.tasks.delete_dependency` | delete | DELETE /task/{task_id}/dependency | Elimina dependencia de tarea | task_id, dependency_task_id | confirmación | — | — | — |
| [ ] | `clickup.tasks.create_link` | create | POST /task/{task_id}/link | Crea enlace relacionado entre tareas | task_id, linked_task_id, link_type | {id, links} | — | — | — |
| [ ] | `clickup.tasks.delete_link` | delete | DELETE /task/{task_id}/link | Elimina enlace entre tareas | task_id, linked_task_id | confirmación | — | — | — |

### Checklists (Listas de Verificación) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.checklists.create` | create | POST /task/{task_id}/checklist | Añade checklist a tarea | task_id, name | {id, name, items: []} | — | — | — |
| [ ] | `clickup.checklists.update` | update | PUT /task/{task_id}/checklist/{checklist_id} | Modifica checklist | task_id, checklist_id, name | {id, name} | — | — | — |
| [ ] | `clickup.checklists.delete` | delete | DELETE /task/{task_id}/checklist/{checklist_id} | Elimina checklist | task_id, checklist_id | confirmación | — | I | — |
| [ ] | `clickup.checklist_items.create` | create | POST /task/{task_id}/checklist/{checklist_id}/item | Añade elemento a checklist | task_id, checklist_id, name, assignee | {id, name, resolved} | — | — | — |
| [ ] | `clickup.checklist_items.update` | update | PUT /task/{task_id}/checklist/{checklist_id}/item/{item_id} | Actualiza elemento de checklist | task_id, checklist_id, item_id, name, resolved | {id, name, resolved} | — | — | — |
| [ ] | `clickup.checklist_items.delete` | delete | DELETE /task/{task_id}/checklist/{checklist_id}/item/{item_id} | Elimina elemento de checklist | task_id, checklist_id, item_id | confirmación | — | I | — |

### Comments (Comentarios) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.comments.list` | read | GET /task/{task_id}/comment | Obtiene comentarios de tarea | task_id, page | {comments: [{id, user, text, created_at}]} | — | — | — |
| [ ] | `clickup.comments.create` | create | POST /task/{task_id}/comment | Añade comentario a tarea | task_id, comment_text, assignee | {id, user, text, created_at} | — | E | add_clickup_comment |
| [ ] | `clickup.comments.update` | update | PUT /comment/{comment_id} | Modifica comentario existente | comment_id, text | {id, text, updated_at} | — | — | — |
| [ ] | `clickup.comments.delete` | delete | DELETE /comment/{comment_id} | Elimina comentario | comment_id | confirmación | — | I | — |
| [ ] | `clickup.comments.list_replies` | read | GET /comment/{comment_id}/comment | Obtiene respuestas a comentario | comment_id, page | {replies: [{id, user, text}]} | — | — | — |
| [ ] | `clickup.comments.create_reply` | create | POST /comment/{comment_id}/comment | Crea respuesta a comentario | comment_id, text, assignee | {id, user, text, created_at} | — | E | — |

### Attachments (Adjuntos) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.attachments.upload_task` | create | POST /task/{task_id}/attachment | Sube archivo adjunto a tarea | task_id, file, filename | {id, filename, url, uploaded_at} | — | E | — |
| [ ] | `clickup.attachments.list` | read | GET /{entity_type}/{entity_id}/attachment | Lista adjuntos de entidad | entity_type, entity_id | {attachments: [{id, filename, url, size}]} | — | — | — |
| [ ] | `clickup.attachments.upload_generic` | create | POST /{entity_type}/{entity_id}/attachment | Sube adjunto a entidad genérica | entity_type, entity_id, file | {id, filename, url} | — | E | — |

### Tags (Etiquetas) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.tags.list` | read | GET /space/{space_id}/tag | Lista etiquetas del espacio | space_id | {tags: [{name, color}]} | — | — | — |
| [ ] | `clickup.tags.create` | create | POST /space/{space_id}/tag | Crea etiqueta en espacio | space_id, name, color | {name, color, created_at} | — | — | — |
| [ ] | `clickup.tags.update` | update | PUT /space/{space_id}/tag/{tag_name} | Modifica etiqueta | space_id, tag_name, new_name, color | {name, color} | — | — | — |
| [ ] | `clickup.tags.delete` | delete | DELETE /space/{space_id}/tag/{tag_name} | Elimina etiqueta del espacio | space_id, tag_name | confirmación | — | I | — |
| [ ] | `clickup.tasks.add_tag` | update | POST /task/{task_id}/tag/{tag_name} | Aplica etiqueta a tarea | task_id, tag_name | {id, tags: []} | — | — | — |
| [ ] | `clickup.tasks.remove_tag` | update | DELETE /task/{task_id}/tag/{tag_name} | Quita etiqueta de tarea | task_id, tag_name | {id, tags: []} | — | — | — |

### Custom Fields (Campos Personalizados) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.custom_fields.list_list` | read | GET /list/{list_id}/field | Lista campos personalizados accesibles de lista | list_id | {fields: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.custom_fields.list_folder` | read | GET /folder/{folder_id}/field | Lista campos personalizados de carpeta | folder_id | {fields: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.custom_fields.list_space` | read | GET /space/{space_id}/field | Lista campos personalizados de espacio | space_id | {fields: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.custom_fields.list_workspace` | read | GET /team/{workspace_id}/field | Lista todos los campos personalizados del workspace | workspace_id | {fields: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.custom_fields.set_value` | update | POST /task/{task_id}/field/{field_id} | Asigna valor a campo personalizado de tarea | task_id, field_id, value | {id, fields: [{id, value}]} | — | — | — |
| [ ] | `clickup.custom_fields.delete_value` | delete | DELETE /task/{task_id}/field/{field_id} | Limpia valor de campo personalizado | task_id, field_id | confirmación | — | — | — |

### Custom Items (Tipos de Tarea Personalizados) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.custom_items.list` | read | GET /team/{workspace_id}/custom_item | Obtiene tipos de tarea personalizados del workspace | workspace_id | {custom_items: [{id, name, icon}]} | — | — | — |

### Time Tracking (Seguimiento de Tiempo) (15)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.time_entries.list` | read | GET /time_entries | Obtiene registros de tiempo en rango de fechas | start_date, end_date, workspace_id, user_id, page | {time_entries: [{id, duration, user, date}]} | — | — | — |
| [ ] | `clickup.time_entries.create` | create | POST /time_entries | Crea entrada de tiempo manual | task_id, duration, start_date, user_id | {id, duration, created_at} | — | — | — |
| [ ] | `clickup.time_entries.get` | read | GET /time_entries/{time_entry_id} | Obtiene detalles de entrada de tiempo | time_entry_id | {id, duration, user, task_id, date} | — | — | — |
| [ ] | `clickup.time_entries.update` | update | PUT /time_entries/{time_entry_id} | Actualiza entrada de tiempo | time_entry_id, duration, start_date, description | {id, duration, updated_at} | — | — | — |
| [ ] | `clickup.time_entries.delete` | delete | DELETE /time_entries/{time_entry_id} | Elimina entrada de tiempo | time_entry_id | confirmación | — | I | — |
| [ ] | `clickup.time_entries.get_history` | read | GET /time_entries/{time_entry_id}/history | Obtiene historial de cambios de entrada | time_entry_id | {changes: [{field, old_value, new_value}]} | — | — | — |
| [ ] | `clickup.timer.get_running` | read | GET /user/time_entries/running | Obtiene temporizador activo del usuario | — | {id, task_id, duration_seconds} o null | — | — | — |
| [ ] | `clickup.timer.start` | create | POST /time_entries/{time_entry_id}/start | Inicia temporizador de entrada de tiempo | time_entry_id | {id, status: running} | — | — | — |
| [ ] | `clickup.timer.stop` | update | POST /time_entries/{time_entry_id}/stop | Detiene temporizador activo | time_entry_id | {id, duration} | — | — | — |
| [ ] | `clickup.time_in_status.get_task` | read | GET /task/{task_id}/time_in_status | Tiempo total gastado en cada estado de tarea | task_id | {status: [{status_id, seconds}]} | — | — | — |
| [ ] | `clickup.time_in_status.get_workspace` | read | GET /team/{workspace_id}/task/time_in_status | Tiempo en status para múltiples tareas | workspace_id, statuses, page | {tasks: [{id, time_in_status}]} | — | — | — |
| [ ] | `clickup.time_entries.list_tags` | read | GET /time_entries/tags | Lista todas las etiquetas de entradas de tiempo | — | {tags: [{name, count}]} | — | — | — |
| [ ] | `clickup.time_entries.create_tag` | create | POST /time_entries/tags | Añade etiqueta a entradas de tiempo | tag_name | {name, created_at} | — | — | — |
| [ ] | `clickup.time_entries.update_tag` | update | PUT /time_entries/tags/{tag_name} | Renombra etiqueta de tiempo | tag_name, new_name | {name} | — | — | — |
| [ ] | `clickup.time_entries.delete_tag` | delete | DELETE /time_entries/tags | Elimina etiqueta de entradas de tiempo | tag_name | confirmación | — | I | — |

### Views (Vistas) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.views.list_workspace` | read | GET /team/{workspace_id}/view | Lista vistas a nivel workspace | workspace_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.views.create_workspace` | create | POST /team/{workspace_id}/view | Crea vista a nivel workspace | workspace_id, name, type, settings | {id, name, type} | — | — | — |
| [ ] | `clickup.views.list_space` | read | GET /space/{space_id}/view | Lista vistas de espacio | space_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.views.create_space` | create | POST /space/{space_id}/view | Crea vista de espacio | space_id, name, type, settings | {id, name, type} | — | — | — |
| [ ] | `clickup.views.list_folder` | read | GET /folder/{folder_id}/view | Lista vistas de carpeta | folder_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.views.create_folder` | create | POST /folder/{folder_id}/view | Crea vista de carpeta | folder_id, name, type, settings | {id, name, type} | — | — | — |
| [ ] | `clickup.views.list_list` | read | GET /list/{list_id}/view | Lista vistas de lista | list_id | {views: [{id, name, type}]} | — | — | — |
| [ ] | `clickup.views.create_list` | create | POST /list/{list_id}/view | Crea vista de lista | list_id, name, type, settings | {id, name, type} | — | — | — |
| [ ] | `clickup.views.get` | read | GET /view/{view_id} | Obtiene detalles de vista | view_id | {id, name, type, settings, task_count} | — | — | — |
| [ ] | `clickup.views.update` | update | PUT /view/{view_id} | Modifica configuración de vista | view_id, name, settings | {id, name, updated_at} | — | — | — |
| [ ] | `clickup.views.delete` | delete | DELETE /view/{view_id} | Elimina vista | view_id | confirmación | — | I | — |
| [ ] | `clickup.views.get_tasks` | read | GET /view/{view_id}/task | Obtiene tareas visibles en vista | view_id, page | {tasks: [{id, name}]} | — | — | — |

### Goals & Key Results (Metas y Resultados Clave) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.goals.list` | read | GET /team/{workspace_id}/goal | Lista metas del workspace | workspace_id, page | {goals: [{id, name, status, progress}]} | — | — | — |
| [ ] | `clickup.goals.create` | create | POST /team/{workspace_id}/goal | Crea nueva meta | workspace_id, name, description, target_date | {id, name, created_at} | — | — | — |
| [ ] | `clickup.goals.get` | read | GET /goal/{goal_id} | Obtiene detalles de meta | goal_id | {id, name, description, key_results, progress} | — | — | — |
| [ ] | `clickup.goals.update` | update | PUT /goal/{goal_id} | Actualiza propiedades de meta | goal_id, name, description, status | {id, name, updated_at} | — | — | — |
| [ ] | `clickup.goals.delete` | delete | DELETE /goal/{goal_id} | Elimina meta | goal_id | confirmación | — | I | — |
| [ ] | `clickup.key_results.create` | create | POST /goal/{goal_id}/key_result | Añade resultado clave a meta | goal_id, name, target_value, unit | {id, name, progress} | — | — | — |
| [ ] | `clickup.key_results.update` | update | PUT /key_result/{key_result_id} | Modifica resultado clave | key_result_id, name, target_value, current_value | {id, name, progress} | — | — | — |
| [ ] | `clickup.key_results.delete` | delete | DELETE /key_result/{key_result_id} | Elimina resultado clave | key_result_id | confirmación | — | I | — |

### Members & Groups (Miembros y Grupos) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.members.list` | read | GET /list/{list_id}/member | Lista miembros asignados explícitamente a lista | list_id | {members: [{id, username, email, role}]} | — | — | list_clickup_members |
| [ ] | `clickup.workspace.get_groups` | read | GET /team/{workspace_id}/group | Lista grupos de usuarios del workspace | workspace_id | {groups: [{id, name, members_count}]} | — | — | — |
| [ ] | `clickup.workspace.create_group` | create | POST /team/{workspace_id}/group | Crea nuevo grupo de usuarios | workspace_id, name, members | {id, name, members: []} | — | — | — |
| [ ] | `clickup.workspace.update_group` | update | PUT /team/{workspace_id}/group/{group_id} | Modifica grupo de usuarios | workspace_id, group_id, name, members | {id, name, members} | — | — | — |
| [ ] | `clickup.workspace.delete_group` | delete | DELETE /team/{workspace_id}/group/{group_id} | Elimina grupo de usuarios | workspace_id, group_id | confirmación | — | I | — |
| [ ] | `clickup.workspace.get_roles` | read | GET /team/{workspace_id}/role | Obtiene roles personalizados del workspace | workspace_id | {roles: [{id, name, permissions}]} | — | — | — |

### Guests & Sharing (Invitados y Compartir) (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.workspace.invite_user` | create | POST /team/{workspace_id}/invite_user | Invita usuario al workspace | workspace_id, email, role | {id, email, status: pending} | — | E | — |
| [ ] | `clickup.workspace.invite_guest` | create | POST /team/{workspace_id}/invite_guest | Invita invitado al workspace | workspace_id, email, lists, tasks, can_edit | {id, email, access_level} | — | E | — |
| [ ] | `clickup.guests.get` | read | GET /guest/{guest_id} | Obtiene detalles de invitado | guest_id | {id, email, created_at, access_level} | — | — | — |
| [ ] | `clickup.guests.update` | update | PUT /guest/{guest_id} | Configura opciones de invitado | guest_id, can_edit, can_create | {id, access_updated} | — | — | — |
| [ ] | `clickup.guests.delete` | delete | DELETE /guest/{guest_id} | Revoca acceso de invitado | guest_id | confirmación | — | I | — |
| [ ] | `clickup.tasks.share_with_guest` | update | POST /task/{task_id}/guest/{guest_id} | Comparte tarea con invitado | task_id, guest_id | {id, guests: []} | — | E | — |
| [ ] | `clickup.tasks.unshare_with_guest` | update | DELETE /task/{task_id}/guest/{guest_id} | Quita acceso de invitado a tarea | task_id, guest_id | confirmación | — | — | — |
| [ ] | `clickup.lists.share_with_guest` | update | POST /list/{list_id}/guest/{guest_id} | Comparte lista con invitado | list_id, guest_id | {id, guests: []} | — | E | — |
| [ ] | `clickup.lists.unshare_with_guest` | update | DELETE /list/{list_id}/guest/{guest_id} | Quita acceso de invitado a lista | list_id, guest_id | confirmación | — | — | — |
| [ ] | `clickup.folders.share_with_guest` | update | POST /folder/{folder_id}/guest/{guest_id} | Comparte carpeta con invitado | folder_id, guest_id | {id, guests: []} | — | E | — |
| [ ] | `clickup.folders.unshare_with_guest` | update | DELETE /folder/{folder_id}/guest/{guest_id} | Quita acceso de invitado a carpeta | folder_id, guest_id | confirmación | — | — | — |
| [ ] | `clickup.workspace.get_shared_hierarchy` | read | GET /shared_hierarchy | Obtiene vista de tareas/listas/carpetas compartidas | — | {tasks: [], lists: [], folders: []} | — | — | — |
| [ ] | `clickup.task_members.list` | read | GET /task/{task_id}/member | Lista miembros explícitos asignados a tarea | task_id | {members: [{id, username, email}]} | — | — | — |

### Chat & Channels (Chat y Canales) (20)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.channels.list` | read | GET /team/{workspace_id}/channel | Lista canales del workspace | workspace_id, page | {channels: [{id, name, private, member_count}]} | — | — | — |
| [ ] | `clickup.channels.create_workspace` | create | POST /team/{workspace_id}/channel | Crea canal a nivel workspace | workspace_id, name, private | {id, name, created_at} | — | E | — |
| [ ] | `clickup.channels.create_location` | create | POST /location/{location_type}/{location_id}/channel | Crea canal en ubicación específica | location_type, location_id, name, private | {id, name, created_at} | — | E | — |
| [ ] | `clickup.channels.direct_message` | create | POST /direct_message | Crea conversación de mensaje directo | user_id, initial_message | {id, type: direct, members} | — | E | — |
| [ ] | `clickup.channels.get` | read | GET /channel/{channel_id} | Obtiene detalles de canal | channel_id | {id, name, created_by, member_count} | — | — | — |
| [ ] | `clickup.channels.update` | update | PUT /channel/{channel_id} | Modifica propiedades de canal | channel_id, name, private | {id, name, updated_at} | — | — | — |
| [ ] | `clickup.channels.delete` | delete | DELETE /channel/{channel_id} | Elimina canal | channel_id | confirmación | — | I | — |
| [ ] | `clickup.channels.get_followers` | read | GET /channel/{channel_id}/follower | Lista seguidores del canal | channel_id | {followers: [{id, username}]} | — | — | — |
| [ ] | `clickup.channels.get_members` | read | GET /channel/{channel_id}/member | Lista miembros del canal | channel_id | {members: [{id, username, email}]} | — | — | — |
| [ ] | `clickup.messages.list` | read | GET /channel/{channel_id}/message | Obtiene mensajes del canal | channel_id, page | {messages: [{id, user, text, created_at}]} | — | — | — |
| [ ] | `clickup.messages.send` | create | POST /channel/{channel_id}/message | Envía mensaje al canal | channel_id, text, attachments | {id, user, text, created_at} | — | E | — |
| [ ] | `clickup.messages.update` | update | PUT /message/{message_id} | Edita mensaje | message_id, text | {id, text, updated_at} | — | — | — |
| [ ] | `clickup.messages.delete` | delete | DELETE /message/{message_id} | Elimina mensaje | message_id | confirmación | — | I | — |
| [ ] | `clickup.messages.get_reactions` | read | GET /message/{message_id}/reaction | Obtiene reacciones emoji al mensaje | message_id | {reactions: [{emoji, users}]} | — | — | — |
| [ ] | `clickup.messages.add_reaction` | create | POST /message/{message_id}/reaction | Añade reacción emoji a mensaje | message_id, emoji | {emoji, added_by: user} | — | — | — |
| [ ] | `clickup.messages.remove_reaction` | delete | DELETE /message/{message_id}/reaction | Quita reacción emoji de mensaje | message_id, emoji | confirmación | — | — | — |
| [ ] | `clickup.messages.list_replies` | read | GET /message/{message_id}/reply | Obtiene respuestas a mensaje | message_id, page | {replies: [{id, user, text}]} | — | — | — |
| [ ] | `clickup.messages.create_reply` | create | POST /message/{message_id}/reply | Crea respuesta a mensaje | message_id, text | {id, user, text, created_at} | — | E | — |
| [ ] | `clickup.messages.get_tagged_users` | read | GET /message/{message_id}/tagged_user | Obtiene usuarios mencionados en mensaje | message_id | {tagged_users: [{id, username}]} | — | — | — |
| [ ] | `clickup.workspace.get_post_types` | read | GET /team/{workspace_id}/post_type | Obtiene tipos de post/subtipos disponibles | workspace_id | {post_types: [{id, name}]} | — | — | — |

### Docs (Documentos) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.docs.search` | read | GET /doc | Busca docs en workspace | query, page | {docs: [{id, name, owner, updated_at}]} | — | — | list_clickup_documents_by_name |
| [ ] | `clickup.docs.create` | create | POST /doc | Crea nuevo documento | name, content, space_id, folder_id | {id, name, created_at} | — | — | — |
| [ ] | `clickup.docs.get` | read | GET /doc/{doc_id} | Obtiene información de documento | doc_id | {id, name, owner, content, created_at} | — | — | get_clickup_document |
| [ ] | `clickup.docs.get_pages` | read | GET /doc/{doc_id}/page | Lista páginas del documento | doc_id, page | {pages: [{id, title, order}]} | — | — | — |
| [ ] | `clickup.docs.get_page_listing` | read | GET /doc/{doc_id}/page_listing | Obtiene listado jerárquico de páginas | doc_id | {pages: [{id, title, children}]} | — | — | — |
| [ ] | `clickup.docs.create_page` | create | POST /doc/{doc_id}/page | Crea página en documento | doc_id, title, content, order | {id, title, created_at} | — | — | — |
| [ ] | `clickup.pages.get` | read | GET /page/{page_id} | Obtiene contenido de página | page_id | {id, title, content, created_at} | — | — | — |
| [ ] | `clickup.pages.update` | update | PUT /page/{page_id} | Edita contenido de página | page_id, title, content | {id, title, updated_at} | — | — | — |

### Webhooks (Avanzado) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.webhooks.list` | read | GET /team/{workspace_id}/webhook | Lista webhooks del workspace | workspace_id | {webhooks: [{id, endpoint, events}]} | — | — | — |
| [ ] | `clickup.webhooks.create` | create | POST /team/{workspace_id}/webhook | Configura nuevo webhook | workspace_id, url, events, secret | {id, endpoint, created_at} | — | — | — |
| [ ] | `clickup.webhooks.update` | update | PUT /webhook/{webhook_id} | Modifica webhook | webhook_id, url, events | {id, endpoint, updated_at} | — | — | — |
| [ ] | `clickup.webhooks.delete` | delete | DELETE /webhook/{webhook_id} | Elimina webhook | webhook_id | confirmación | — | I | — |

### Audit Logs (Avanzado) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.audit_logs.create` | read | POST /team/{workspace_id}/audit_log | Crea/registra evento de auditoría | workspace_id, event_type, details | {id, event_type, timestamp} | — | — | — |

### Access Control (Control de Acceso) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.acl.update` | update | PATCH /{object_type}/{object_id}/acl | Actualiza privacidad y configuración de acceso | object_type, object_id, access_level | {id, access_updated} | — | — | — |

### Templates (Plantillas) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `clickup.task_templates.list` | read | GET /team/{workspace_id}/task_template | Lista plantillas de tareas | workspace_id | {templates: [{id, name}]} | — | — | — |
| [ ] | `clickup.tasks.create_from_task_template` | create | POST /task/from_template | Crea tarea desde plantilla | template_id, list_id, custom_fields | {id, name, created_at} | — | — | — |
| [ ] | `clickup.list_templates.list` | read | GET /team/{workspace_id}/list_template | Lista plantillas de listas | workspace_id | {templates: [{id, name}]} | — | — | — |
| [ ] | `clickup.folder_templates.list` | read | GET /team/{workspace_id}/folder_template | Lista plantillas de carpetas | workspace_id | {templates: [{id, name}]} | — | — | — |

## Observaciones de las herramientas viejas

- Varias herramientas viejas reciben lenguaje natural ('Crea una tarea llamada X en mi proyecto Y') y extraen los parametros por dentro. En el estandar nuevo la funcion recibe parametros estructurados; el modelo es quien interpreta el texto.
- `BIGTOOLS_REGISTRY` tiene `clickup: []` (vacio).
- `update_clickup_due_date` interpreta fechas ('manana', 'dd/mm/yyyy'): la funcion nueva recibe una fecha ISO; la interpretacion es del modelo.
