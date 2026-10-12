# Tareas: Asana

- **Funciones catalogadas:** 244 · **Hechas:** 0 · **Pendientes:** 244 · **Herramientas viejas a migrar:** 21 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.asana.com/reference
- **Fuentes que consultó el catálogo:** https://developers.asana.com/reference https://developers.asana.com/docs/oauth-scopes https://developers.asana.com/docs/authentication https://developers.asana.com/llms.txt
- **Paginación típica:** Cursor-based con offset/limit opcional. Respuesta incluye next_page (URL completa) o está ausente si es última página.
- **Qué no se pudo verificar:** Límites exactos de rate limiting no documentados públicamente; scopes específicos requeridos por cada endpoint; restricciones de revisión de app; campo ID exacto en respuestas (asume "gid")
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/asana/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `asana`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `asana` |
| Variables del `.env` que necesitas | ASANA_CLIENT_ID, ASANA_CLIENT_SECRET, ASANA_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/asana/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `asana.users.get` |
| Cómo se autentica (según el catálogo) | OAuth 2 con código de autorización y refresh token. POST https://app.asana.com/-/oauth_token para intercambiar código por access_token. Revocación con POST https://app.asana.com/-/oauth_revoke. |
| Duración del token (según el catálogo) | No especificado en documentación; descrito como "long-lived token" |
| Refresco (según el catálogo) | Sí, se incluye refresh_token en la respuesta OAuth; usar para renovar access_token sin re-autorización |
| Permisos (según el catálogo) | Scopes con formato resource:action. Principales: tasks:read/write/delete, projects:read/write/delete, portfolios:read/write/delete, goals:read/write/delete, teams:read/write, users:read, custom_fields:read/write, attachments:read/write/delete, tags:read/write, time_tracking:read/write |
| Restricciones de acceso | View-only license users tienen acceso limitado. Service Accounts solo en Enterprise. La app debe tener revisión de Asana para ciertas operaciones. SCIM disponible para Enterprise. |
| Límites de ritmo | API con rate limiting (documentación no especifica límites exactos); usar sync tokens para sincronización eficiente de cambios |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/asana/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> asana`. | Cuenta con `provider: asana`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/asana.users.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> asana <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Asana. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/asana.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Users (Usuarios) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.users.get` ★ | read | GET /users/{user_gid} | Obtiene detalles de un usuario (whoami si user_gid=me) | user_gid | {gid, name, email, photo, workspaces} | users:read | — | obtener_informacion_usuario_asana |
| [ ] | `asana.users.list` | read | GET /users | Lista usuarios del workspace | workspace_gid, limit, offset | lista de {gid, name, email} + next_page | users:read | — | listar_usuarios_asana |
| [ ] | `asana.users.update` | update | PUT /users/{user_gid} | Actualiza perfil de usuario | user_gid, name, email, photo | {gid, name, email, photo} | users:write | — | — |
| [ ] | `asana.users.list_favorites` | read | GET /users/{user_gid}/favorites | Lista objetos favoritos del usuario | user_gid | lista de {gid, resource_type, name} | users:read | — | — |
| [ ] | `asana.users.get_workspace` | read | GET /workspaces/{workspace_gid}/users/{user_gid} | Obtiene usuario en workspace específico | workspace_gid, user_gid | {gid, name, email, role} | users:read | — | — |
| [ ] | `asana.users.update_workspace` | update | PUT /workspaces/{workspace_gid}/users/{user_gid} | Actualiza usuario en workspace | workspace_gid, user_gid, role | {gid, name, role} | users:write | — | — |

### Tasks (Tareas) (33)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.tasks.list` | read | GET /tasks | Lista tareas con filtros | workspace_gid, assignee, completed_since, modified_since, limit | lista de {gid, name, assignee, due_on, completed} + next_page | tasks:read | — | listar_tareas_asana |
| [ ] | `asana.tasks.create` | create | POST /tasks | Crea nueva tarea | workspace_gid, name, projects, assignee, due_on | {gid, name, assignee, due_on, created_at} | tasks:write | — | crear_tarea_asana |
| [ ] | `asana.tasks.get` | read | GET /tasks/{task_gid} | Obtiene detalles completos de tarea | task_gid | {gid, name, description, assignee, due_on, completed, projects, tags, dependencies} | tasks:read | — | obtener_detalle_tarea_por_nombre_asana |
| [ ] | `asana.tasks.update` | update | PUT /tasks/{task_gid} | Actualiza tarea (nombre, descripción, estado, etc.) | task_gid, name, description, completed, due_on, assignee | {gid, name, description, completed, assignee} | tasks:write | — | actualizar_estado_tarea_por_nombre_asana |
| [ ] | `asana.tasks.delete` | delete | DELETE /tasks/{task_gid} | Elimina tarea permanentemente | task_gid | — | tasks:write | I | — |
| [ ] | `asana.tasks.duplicate` | create | POST /tasks/{task_gid}/duplicate | Duplica tarea con subtareas y adjuntos | task_gid, name, include_subtasks | {gid, name, assignee, due_on, parent} | tasks:write | — | duplicar_tarea_por_nombre_asana |
| [ ] | `asana.tasks.list_project_tasks` | read | GET /projects/{project_gid}/tasks | Lista tareas de un proyecto | project_gid, limit, offset | lista de {gid, name, assignee, due_on, completed} | tasks:read | — | — |
| [ ] | `asana.tasks.list_section_tasks` | read | GET /sections/{section_gid}/tasks | Lista tareas de una sección | section_gid, limit, offset | lista de {gid, name, assignee, due_on} | tasks:read | — | — |
| [ ] | `asana.tasks.list_tag_tasks` | read | GET /tags/{tag_gid}/tasks | Lista tareas con una etiqueta | tag_gid, limit, offset | lista de {gid, name, assignee} | tasks:read | — | listar_tareas_por_etiqueta_asana |
| [ ] | `asana.tasks.list_user_task_list` | read | GET /user_task_lists/{user_task_list_gid}/tasks | Lista tareas de la lista personal de usuario | user_task_list_gid, limit | lista de {gid, name, due_on, completed} | tasks:read | — | — |
| [ ] | `asana.tasks.list_completed` | read | GET /tasks | Lista tareas completadas (completed_on>0) | workspace_gid, completed_since, limit | lista de {gid, name, completed_at} | tasks:read | — | listar_tareas_completadas_asana |
| [ ] | `asana.tasks.list_incomplete` | read | GET /tasks | Lista tareas no completadas (completed_on=null) | workspace_gid, completed=false, limit | lista de {gid, name, due_on, assignee} | tasks:read | — | listar_tareas_no_completadas_asana |
| [ ] | `asana.tasks.search` | read | GET /workspaces/{workspace_gid}/tasks/search | Busca tareas por texto en workspace | workspace_gid, text, limit | lista de {gid, name, assignee, due_on} | tasks:read | — | — |
| [ ] | `asana.tasks.get_by_custom_id` | read | GET /workspaces/{workspace_gid}/tasks/customId/{custom_id} | Obtiene tarea por ID personalizado | workspace_gid, custom_id | {gid, name, custom_id, assignee} | tasks:read | — | — |
| [ ] | `asana.tasks.add_project` | update | POST /tasks/{task_gid}/addProject | Agrega tarea a un proyecto | task_gid, project | {} | tasks:write | — | — |
| [ ] | `asana.tasks.remove_project` | update | POST /tasks/{task_gid}/removeProject | Quita tarea de un proyecto | task_gid, project | {} | tasks:write | — | — |
| [ ] | `asana.tasks.add_tag` | update | POST /tasks/{task_gid}/addTag | Agrega etiqueta a tarea | task_gid, tag | {} | tasks:write | — | agregar_etiqueta_a_tarea_por_nombre_asana |
| [ ] | `asana.tasks.remove_tag` | update | POST /tasks/{task_gid}/removeTag | Quita etiqueta de tarea | task_gid, tag | {} | tasks:write | — | — |
| [ ] | `asana.tasks.add_followers` | update | POST /tasks/{task_gid}/addFollowers | Agrega seguidores a tarea | task_gid, followers | {gid, followers} | tasks:write | — | — |
| [ ] | `asana.tasks.remove_followers` | update | POST /tasks/{task_gid}/removeFollowers | Quita seguidores de tarea | task_gid, followers | {} | tasks:write | — | — |
| [ ] | `asana.tasks.set_parent` | update | PUT /tasks/{task_gid}/setParent | Establece tarea padre (crea subtarea) | task_gid, parent, insert_before, insert_after | {gid, parent, created_at} | tasks:write | — | — |
| [ ] | `asana.tasks.list_subtasks` | read | GET /tasks/{task_gid}/subtasks | Lista subtareas de una tarea | task_gid, limit | lista de {gid, name, assignee, due_on} | tasks:read | — | — |
| [ ] | `asana.tasks.create_subtask` | create | POST /tasks/{task_gid}/subtasks | Crea subtarea | task_gid, name, assignee, due_on | {gid, name, parent, created_at} | tasks:write | — | — |
| [ ] | `asana.tasks.list_dependencies` | read | GET /tasks/{task_gid}/dependencies | Lista dependencias (tareas que bloquean esta) | task_gid | lista de {gid, name} | tasks:read | — | — |
| [ ] | `asana.tasks.add_dependencies` | update | POST /tasks/{task_gid}/addDependencies | Agrega dependencias | task_gid, dependencies | {gid, dependencies} | tasks:write | — | — |
| [ ] | `asana.tasks.remove_dependencies` | update | POST /tasks/{task_gid}/removeDependencies | Quita dependencias | task_gid, dependencies | {} | tasks:write | — | — |
| [ ] | `asana.tasks.list_dependents` | read | GET /tasks/{task_gid}/dependents | Lista tareas que dependen de esta | task_gid | lista de {gid, name} | tasks:read | — | — |
| [ ] | `asana.tasks.add_dependents` | update | POST /tasks/{task_gid}/addDependents | Agrega tareas dependientes | task_gid, dependents | {gid, dependents} | tasks:write | — | — |
| [ ] | `asana.tasks.remove_dependents` | update | POST /tasks/{task_gid}/removeDependents | Quita tareas dependientes | task_gid, dependents | {} | tasks:write | — | — |
| [ ] | `asana.tasks.rollup_dates` | create | POST /tasks/{task_gid}/rollup | Propaga fechas de subtareas a tarea padre | task_gid | — | tasks:write | — | — |
| [ ] | `asana.tasks.list_projects` | read | GET /tasks/{task_gid}/projects | Lista proyectos donde aparece tarea | task_gid | lista de {gid, name} | tasks:read | — | — |
| [ ] | `asana.tasks.assign` | update | POST /tasks/{task_gid} (assignee field in body) | Asigna tarea a usuario | task_gid, assignee | {gid, assignee, name} | tasks:write | E | asignar_tarea_a_usuario_por_nombre_asana |
| [ ] | `asana.tasks.update_description` | update | PUT /tasks/{task_gid} (description field) | Actualiza descripción de tarea | task_gid, description | {gid, description} | tasks:write | — | actualizar_descripcion_tarea_por_nombre_asana |

### Projects (Proyectos) (19)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.projects.list` | read | GET /projects | Lista proyectos | workspace_gid, limit, offset | lista de {gid, name, owner, due_on} + next_page | projects:read | — | listar_proyectos_asana |
| [ ] | `asana.projects.create` | create | POST /projects | Crea proyecto | workspace_gid, name, team, is_template | {gid, name, owner, created_at} | projects:write | — | — |
| [ ] | `asana.projects.get` | read | GET /projects/{project_gid} | Obtiene detalles de proyecto | project_gid | {gid, name, owner, due_on, description, archived, members, custom_fields} | projects:read | — | obtener_resumen_proyecto_asana |
| [ ] | `asana.projects.update` | update | PUT /projects/{project_gid} | Actualiza proyecto | project_gid, name, description, owner, due_on, archived | {gid, name, description, archived} | projects:write | — | — |
| [ ] | `asana.projects.delete` | delete | DELETE /projects/{project_gid} | Elimina proyecto | project_gid | — | projects:write | I | — |
| [ ] | `asana.projects.duplicate` | create | POST /projects/{project_gid}/duplicate | Duplica proyecto con tareas y configuración | project_gid, name, team, scheduled_for | {gid, name, owner, created_at} | projects:write | — | — |
| [ ] | `asana.projects.list_team_projects` | read | GET /teams/{team_gid}/projects | Lista proyectos de un equipo | team_gid, limit | lista de {gid, name, owner} | projects:read | — | — |
| [ ] | `asana.projects.create_team_project` | create | POST /teams/{team_gid}/projects | Crea proyecto en equipo | team_gid, name, is_template | {gid, name, owner, team} | projects:write | — | — |
| [ ] | `asana.projects.list_workspace_projects` | read | GET /workspaces/{workspace_gid}/projects | Lista proyectos en workspace | workspace_gid, limit, offset | lista de {gid, name, owner} | projects:read | — | — |
| [ ] | `asana.projects.create_workspace_project` | create | POST /workspaces/{workspace_gid}/projects | Crea proyecto en workspace | workspace_gid, name, is_template | {gid, name, owner} | projects:write | — | — |
| [ ] | `asana.projects.search` | read | GET /workspaces/{workspace_gid}/projects/search | Busca proyectos por nombre en workspace | workspace_gid, text, limit | lista de {gid, name, owner} | projects:read | — | — |
| [ ] | `asana.projects.get_task_counts` | read | GET /projects/{project_gid}/taskCounts | Obtiene conteos de tareas en proyecto | project_gid | {gid, num_tasks, num_completed_tasks} | projects:read | — | — |
| [ ] | `asana.projects.add_members` | update | POST /projects/{project_gid}/addMembers | Agrega miembros a proyecto | project_gid, members | {gid, members} | projects:write | E | — |
| [ ] | `asana.projects.remove_members` | update | POST /projects/{project_gid}/removeMembers | Quita miembros de proyecto | project_gid, members | {} | projects:write | — | — |
| [ ] | `asana.projects.add_followers` | update | POST /projects/{project_gid}/addFollowers | Agrega seguidores a proyecto | project_gid, followers | {gid, followers} | projects:write | E | — |
| [ ] | `asana.projects.remove_followers` | update | POST /projects/{project_gid}/removeFollowers | Quita seguidores de proyecto | project_gid, followers | {} | projects:write | — | — |
| [ ] | `asana.projects.save_as_template` | create | POST /projects/{project_gid}/saveAsTemplate | Guarda proyecto como plantilla | project_gid, name | {gid, name, resource_type} | projects:write | — | — |
| [ ] | `asana.projects.add_custom_field` | update | POST /projects/{project_gid}/addCustomFieldSetting | Agrega campo personalizado al proyecto | project_gid, custom_field | {gid, custom_field} | projects:write | — | — |
| [ ] | `asana.projects.remove_custom_field` | update | POST /projects/{project_gid}/removeCustomFieldSetting | Quita campo personalizado del proyecto | project_gid, custom_field | {} | projects:write | — | — |

### Sections (Secciones) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.sections.list` | read | GET /projects/{project_gid}/sections | Lista secciones de proyecto | project_gid | lista de {gid, name, created_at} | sections:read | — | — |
| [ ] | `asana.sections.create` | create | POST /projects/{project_gid}/sections | Crea sección en proyecto | project_gid, name | {gid, name, project, created_at} | sections:write | — | — |
| [ ] | `asana.sections.get` | read | GET /sections/{section_gid} | Obtiene detalles de sección | section_gid | {gid, name, project, created_at} | sections:read | — | — |
| [ ] | `asana.sections.update` | update | PUT /sections/{section_gid} | Actualiza sección | section_gid, name | {gid, name} | sections:write | — | — |
| [ ] | `asana.sections.delete` | delete | DELETE /sections/{section_gid} | Elimina sección | section_gid | — | sections:write | I | — |
| [ ] | `asana.sections.add_task` | update | POST /sections/{section_gid}/addTask | Mueve tarea a sección | section_gid, task, insert_before, insert_after | {gid, task} | sections:write | — | — |
| [ ] | `asana.sections.move` | update | POST /projects/{project_gid}/sections/insert | Reordena secciones | project_gid, section_gid, insert_before, insert_after | {} | sections:write | — | — |

### Tags (Etiquetas) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.tags.list` | read | GET /tags | Lista etiquetas | workspace_gid, limit | lista de {gid, name, color} + next_page | tags:read | — | listar_etiquetas_asana |
| [ ] | `asana.tags.create` | create | POST /tags | Crea etiqueta | workspace_gid, name, color | {gid, name, color, created_at} | tags:write | — | — |
| [ ] | `asana.tags.get` | read | GET /tags/{tag_gid} | Obtiene detalles de etiqueta | tag_gid | {gid, name, color, workspace} | tags:read | — | — |
| [ ] | `asana.tags.update` | update | PUT /tags/{tag_gid} | Actualiza etiqueta | tag_gid, name, color | {gid, name, color} | tags:write | — | — |
| [ ] | `asana.tags.delete` | delete | DELETE /tags/{tag_gid} | Elimina etiqueta | tag_gid | — | tags:write | I | — |
| [ ] | `asana.tags.list_task_tags` | read | GET /tasks/{task_gid}/tags | Lista etiquetas de una tarea | task_gid | lista de {gid, name, color} | tags:read | — | — |
| [ ] | `asana.tags.list_workspace_tags` | read | GET /workspaces/{workspace_gid}/tags | Lista etiquetas en workspace | workspace_gid, limit | lista de {gid, name, color} | tags:read | — | — |
| [ ] | `asana.tags.create_workspace_tag` | create | POST /workspaces/{workspace_gid}/tags | Crea etiqueta en workspace | workspace_gid, name, color | {gid, name, color} | tags:write | — | — |

### Stories & Comments (Historias y Comentarios) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.stories.list_task_stories` | read | GET /tasks/{task_gid}/stories | Lista comentarios/historias de tarea | task_gid, limit | lista de {gid, type, created_by, text, created_at} | tasks:read | — | listar_comentarios_tarea_por_nombre_asana |
| [ ] | `asana.stories.create_task_story` | create | POST /tasks/{task_gid}/stories | Crea comentario en tarea | task_gid, text, created_by | {gid, type, text, created_by, created_at} | tasks:write | E | crear_comentario_tarea_asana |
| [ ] | `asana.stories.get` | read | GET /stories/{story_gid} | Obtiene detalles de comentario | story_gid | {gid, type, text, created_by, created_at, task} | tasks:read | — | — |
| [ ] | `asana.stories.update` | update | PUT /stories/{story_gid} | Actualiza comentario | story_gid, text | {gid, text, created_at} | tasks:write | — | — |
| [ ] | `asana.stories.delete` | delete | DELETE /stories/{story_gid} | Elimina comentario | story_gid | — | tasks:write | I | — |
| [ ] | `asana.stories.list_goal_stories` | read | GET /goals/{goal_gid}/stories | Lista comentarios/historias de goal | goal_gid | lista de {gid, type, text, created_by, created_at} | goals:read | — | — |
| [ ] | `asana.stories.create_goal_story` | create | POST /goals/{goal_gid}/stories | Crea comentario en goal | goal_gid, text, created_by | {gid, type, text, created_by, created_at} | goals:write | E | — |

### Attachments (Adjuntos) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.attachments.list` | read | GET /{parent_type}/{parent_gid}/attachments | Lista adjuntos de objeto | parent_type, parent_gid, limit | lista de {gid, name, url, created_at} | attachments:read | — | — |
| [ ] | `asana.attachments.upload` | create | POST /{parent_type}/{parent_gid}/attachments | Sube adjunto a objeto | parent_type, parent_gid, file, connect_to_app | {gid, name, url, size, created_at} | attachments:write | — | — |
| [ ] | `asana.attachments.get` | read | GET /attachments/{attachment_gid} | Obtiene detalles de adjunto | attachment_gid | {gid, name, url, size, created_at, parent} | attachments:read | — | — |
| [ ] | `asana.attachments.delete` | delete | DELETE /attachments/{attachment_gid} | Elimina adjunto | attachment_gid | — | attachments:write | I | — |

### Custom Fields (Campos Personalizados) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.custom_fields.list` | read | GET /workspaces/{workspace_gid}/custom_fields | Lista campos personalizados de workspace | workspace_gid, limit | lista de {gid, name, type, enum_options} | custom_fields:read | — | — |
| [ ] | `asana.custom_fields.create` | create | POST /custom_fields | Crea campo personalizado | workspace_gid, name, type, enum_options | {gid, name, type, enum_options, created_at} | custom_fields:write | — | — |
| [ ] | `asana.custom_fields.get` | read | GET /custom_fields/{custom_field_gid} | Obtiene detalles de campo personalizado | custom_field_gid | {gid, name, type, enum_options, workspace} | custom_fields:read | — | — |
| [ ] | `asana.custom_fields.update` | update | PUT /custom_fields/{custom_field_gid} | Actualiza campo personalizado | custom_field_gid, name, enum_options | {gid, name, enum_options} | custom_fields:write | — | — |
| [ ] | `asana.custom_fields.delete` | delete | DELETE /custom_fields/{custom_field_gid} | Elimina campo personalizado | custom_field_gid | — | custom_fields:write | I | — |
| [ ] | `asana.custom_fields.create_enum_option` | create | POST /custom_fields/{custom_field_gid}/enum_options | Agrega opción a campo enum | custom_field_gid, name, color | {gid, name, color, enum_options} | custom_fields:write | — | — |
| [ ] | `asana.custom_fields.update_enum_option` | update | PUT /enum_options/{enum_option_gid} | Actualiza opción enum | enum_option_gid, name, color | {gid, name, color} | custom_fields:write | — | — |
| [ ] | `asana.custom_fields.reorder_enum_options` | update | PUT /custom_fields/{custom_field_gid}/enum_options/{enum_option_gid}/insert | Reordena opciones enum | custom_field_gid, enum_option_gid, insert_before, insert_after | {} | custom_fields:write | — | — |

### Custom Field Settings (Configuración de Campos Personalizados) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.custom_field_settings.list_project` | read | GET /projects/{project_gid}/custom_field_settings | Lista campos de proyecto | project_gid | lista de {gid, custom_field, is_important} | custom_fields:read | — | — |
| [ ] | `asana.custom_field_settings.list_portfolio` | read | GET /portfolios/{portfolio_gid}/custom_field_settings | Lista campos de portfolio | portfolio_gid | lista de {gid, custom_field, is_important} | custom_fields:read | — | — |
| [ ] | `asana.custom_field_settings.list_team` | read | GET /teams/{team_gid}/custom_field_settings | Lista campos de equipo | team_gid | lista de {gid, custom_field} | custom_fields:read | — | — |
| [ ] | `asana.custom_field_settings.list_goal` | read | GET /goals/{goal_gid}/custom_field_settings | Lista campos de goal | goal_gid | lista de {gid, custom_field} | custom_fields:read | — | — |

### Teams (Equipos) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.teams.create` | create | POST /teams | Crea equipo | workspace_gid, name, organization | {gid, name, workspace, members} | teams:write | — | — |
| [ ] | `asana.teams.get` | read | GET /teams/{team_gid} | Obtiene detalles de equipo | team_gid | {gid, name, workspace, members, created_at} | teams:read | — | — |
| [ ] | `asana.teams.update` | update | PUT /teams/{team_gid} | Actualiza equipo | team_gid, name, description | {gid, name, description} | teams:write | — | — |
| [ ] | `asana.teams.list_workspace` | read | GET /workspaces/{workspace_gid}/teams | Lista equipos en workspace | workspace_gid, limit | lista de {gid, name, member_count} | teams:read | — | listar_equipos_asana |
| [ ] | `asana.teams.list_user_teams` | read | GET /users/{user_gid}/teams | Lista equipos del usuario | user_gid, limit | lista de {gid, name, organization} | teams:read | — | — |
| [ ] | `asana.teams.add_user` | update | POST /teams/{team_gid}/addUser | Agrega usuario a equipo | team_gid, user | {gid, user} | teams:write | E | — |
| [ ] | `asana.teams.remove_user` | update | POST /teams/{team_gid}/removeUser | Quita usuario de equipo | team_gid, user | {} | teams:write | — | — |

### Team Memberships (Membresías de Equipo) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.team_memberships.get` | read | GET /team_memberships/{membership_gid} | Obtiene membresía de equipo | membership_gid | {gid, user, team, role, created_at} | teams:read | — | — |
| [ ] | `asana.team_memberships.list` | read | GET /team_memberships | Lista membresías de equipo | limit, offset | lista de {gid, user, team, role} | teams:read | — | listar_miembros_proyecto_asana |
| [ ] | `asana.team_memberships.list_team` | read | GET /teams/{team_gid}/memberships | Lista membresías de un equipo | team_gid, limit | lista de {gid, user, team, role} | teams:read | — | — |
| [ ] | `asana.team_memberships.list_user` | read | GET /users/{user_gid}/team_memberships | Lista membresías del usuario | user_gid, limit | lista de {gid, user, team, role} | teams:read | — | — |

### Project Memberships (Membresías de Proyecto) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.project_memberships.get` | read | GET /project_memberships/{membership_gid} | Obtiene membresía de proyecto | membership_gid | {gid, user, project, role} | projects:read | — | — |
| [ ] | `asana.project_memberships.list_project` | read | GET /projects/{project_gid}/memberships | Lista membresías de proyecto | project_gid, limit | lista de {gid, user, project, role} | projects:read | — | listar_miembros_proyecto_asana |
| [ ] | `asana.project_memberships.list` | read | GET /project_memberships | Lista membresías de proyecto | limit, offset | lista de {gid, user, project, role} | projects:read | — | — |

### Workspaces (Espacios de Trabajo) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.workspaces.list` | read | GET /workspaces | Lista espacios de trabajo del usuario | limit | lista de {gid, name, is_organization} | workspaces:read | — | — |
| [ ] | `asana.workspaces.get` | read | GET /workspaces/{workspace_gid} | Obtiene detalles de workspace | workspace_gid | {gid, name, is_organization, members, created_at} | workspaces:read | — | — |
| [ ] | `asana.workspaces.update` | update | PUT /workspaces/{workspace_gid} | Actualiza workspace | workspace_gid, name | {gid, name} | workspaces:write | — | — |
| [ ] | `asana.workspaces.add_user` | update | POST /workspaces/{workspace_gid}/addUser | Agrega usuario a workspace | workspace_gid, user, type | {gid, user, role} | workspaces:write | E | — |
| [ ] | `asana.workspaces.remove_user` | update | POST /workspaces/{workspace_gid}/removeUser | Quita usuario de workspace | workspace_gid, user | {} | workspaces:write | — | — |
| [ ] | `asana.workspaces.get_events` | read | GET /workspaces/{workspace_gid}/events | Obtiene eventos de workspace | workspace_gid, sync_token, limit | lista de {gid, type, resource, created_at, resource_type} | workspaces:read | — | listar_eventos_asana |

### Workspace Memberships (Membresías de Workspace) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.workspace_memberships.get` | read | GET /workspace_memberships/{membership_gid} | Obtiene membresía de workspace | membership_gid | {gid, user, workspace, role} | workspaces:read | — | — |
| [ ] | `asana.workspace_memberships.list` | read | GET /workspaces/{workspace_gid}/workspace_memberships | Lista membresías de workspace | workspace_gid, limit | lista de {gid, user, workspace, role} | workspaces:read | — | — |
| [ ] | `asana.workspace_memberships.list_user` | read | GET /users/{user_gid}/workspace_memberships | Lista membresías del usuario | user_gid | lista de {gid, user, workspace, role} | workspaces:read | — | — |

### Portfolios (Portafolios) (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.portfolios.list` | read | GET /portfolios | Lista portafolios | workspace_gid, owner, limit | lista de {gid, name, owner, created_at} | portfolios:read | — | — |
| [ ] | `asana.portfolios.create` | create | POST /portfolios | Crea portafolio | workspace_gid, name, owner | {gid, name, owner, created_at} | portfolios:write | — | — |
| [ ] | `asana.portfolios.get` | read | GET /portfolios/{portfolio_gid} | Obtiene detalles de portafolio | portfolio_gid | {gid, name, owner, members, items, created_at} | portfolios:read | — | — |
| [ ] | `asana.portfolios.update` | update | PUT /portfolios/{portfolio_gid} | Actualiza portafolio | portfolio_gid, name, owner, description | {gid, name, owner, description} | portfolios:write | — | — |
| [ ] | `asana.portfolios.delete` | delete | DELETE /portfolios/{portfolio_gid} | Elimina portafolio | portfolio_gid | — | portfolios:write | I | — |
| [ ] | `asana.portfolios.list_items` | read | GET /portfolios/{portfolio_gid}/items | Lista items del portafolio | portfolio_gid, limit | lista de {gid, name, resource_type} | portfolios:read | — | — |
| [ ] | `asana.portfolios.add_item` | update | POST /portfolios/{portfolio_gid}/addItem | Agrega item (proyecto/goal) a portafolio | portfolio_gid, item | {gid, item} | portfolios:write | — | — |
| [ ] | `asana.portfolios.remove_item` | update | POST /portfolios/{portfolio_gid}/removeItem | Quita item de portafolio | portfolio_gid, item | {} | portfolios:write | — | — |
| [ ] | `asana.portfolios.add_members` | update | POST /portfolios/{portfolio_gid}/addMembers | Agrega miembros a portafolio | portfolio_gid, members | {gid, members} | portfolios:write | E | — |
| [ ] | `asana.portfolios.remove_members` | update | POST /portfolios/{portfolio_gid}/removeMembers | Quita miembros de portafolio | portfolio_gid, members | {} | portfolios:write | — | — |
| [ ] | `asana.portfolios.add_custom_field` | update | POST /portfolios/{portfolio_gid}/addCustomFieldSetting | Agrega campo personalizado a portafolio | portfolio_gid, custom_field | {gid, custom_field} | portfolios:write | — | — |
| [ ] | `asana.portfolios.remove_custom_field` | update | POST /portfolios/{portfolio_gid}/removeCustomFieldSetting | Quita campo personalizado de portafolio | portfolio_gid, custom_field | {} | portfolios:write | — | — |
| [ ] | `asana.portfolios.duplicate` | create | POST /portfolios/{portfolio_gid}/duplicate | Duplica portafolio | portfolio_gid, name | {gid, name, owner, created_at} | portfolios:write | — | — |

### Portfolio Memberships (Membresías de Portafolio) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.portfolio_memberships.list` | read | GET /portfolio_memberships | Lista membresías de portafolio | limit, offset | lista de {gid, user, portfolio, role} | portfolios:read | — | — |
| [ ] | `asana.portfolio_memberships.get` | read | GET /portfolio_memberships/{membership_gid} | Obtiene membresía de portafolio | membership_gid | {gid, user, portfolio, role} | portfolios:read | — | — |
| [ ] | `asana.portfolio_memberships.list_portfolio` | read | GET /portfolios/{portfolio_gid}/memberships | Lista membresías de un portafolio | portfolio_gid, limit | lista de {gid, user, portfolio, role} | portfolios:read | — | — |

### Goals (Objetivos) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.goals.list` | read | GET /goals | Lista goals | workspace_gid, team_id, limit | lista de {gid, name, owner, due_on, status} | goals:read | — | — |
| [ ] | `asana.goals.create` | create | POST /goals | Crea goal | workspace_gid, name, owner, team, due_on | {gid, name, owner, team, due_on, created_at} | goals:write | — | — |
| [ ] | `asana.goals.get` | read | GET /goals/{goal_gid} | Obtiene detalles de goal | goal_gid | {gid, name, owner, team, due_on, status, metrics, supporting_goals} | goals:read | — | — |
| [ ] | `asana.goals.update` | update | PUT /goals/{goal_gid} | Actualiza goal | goal_gid, name, status, due_on, owner | {gid, name, status, due_on, owner} | goals:write | — | — |
| [ ] | `asana.goals.delete` | delete | DELETE /goals/{goal_gid} | Elimina goal | goal_gid | — | goals:write | I | — |
| [ ] | `asana.goals.create_metric` | create | POST /goals/{goal_gid}/metrics | Crea métrica para goal | goal_gid, resource_subtype, unit, current_number_value, target_number_value | {gid, goal, resource_subtype, current_number_value, target_number_value} | goals:write | — | — |
| [ ] | `asana.goals.update_metric` | update | PUT /goals/{goal_gid}/metrics | Actualiza métrica de goal | goal_gid, current_number_value, target_number_value | {} | goals:write | — | — |
| [ ] | `asana.goals.list_parent_goals` | read | GET /goals/{goal_gid}/parentGoals | Lista goals padre | goal_gid | lista de {gid, name, owner, due_on} | goals:read | — | — |
| [ ] | `asana.goals.add_collaborators` | update | POST /goals/{goal_gid}/addFollowers | Agrega colaboradores a goal | goal_gid, followers | {gid, followers} | goals:write | E | — |
| [ ] | `asana.goals.remove_collaborators` | update | POST /goals/{goal_gid}/removeFollowers | Quita colaboradores de goal | goal_gid, followers | {} | goals:write | — | — |
| [ ] | `asana.goals.add_custom_field` | update | POST /goals/{goal_gid}/addCustomFieldSetting | Agrega campo personalizado a goal | goal_gid, custom_field | {gid, custom_field} | goals:write | — | — |
| [ ] | `asana.goals.remove_custom_field` | update | POST /goals/{goal_gid}/removeCustomFieldSetting | Quita campo personalizado de goal | goal_gid, custom_field | {} | goals:write | — | — |

### Goal Relationships (Relaciones de Goals) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.goal_relationships.list` | read | GET /goal_relationships | Lista relaciones entre goals | limit, offset | lista de {gid, goal, resource_subtype, supporting_goal} | goals:read | — | — |
| [ ] | `asana.goal_relationships.get` | read | GET /goal_relationships/{goal_relationship_gid} | Obtiene relación entre goals | goal_relationship_gid | {gid, goal, resource_subtype, supporting_goal} | goals:read | — | — |
| [ ] | `asana.goal_relationships.add_supporting_goal` | create | POST /goals/{goal_gid}/addSupportingRelationship | Agrega goal de apoyo | goal_gid, goal_relationship_resource_subtype, supporting_goal | {gid, goal, supporting_goal} | goals:write | — | — |
| [ ] | `asana.goal_relationships.remove_supporting_goal` | update | POST /goals/{goal_gid}/removeSupportingRelationship | Quita goal de apoyo | goal_gid, supporting_goal | {} | goals:write | — | — |
| [ ] | `asana.goal_relationships.update` | update | PUT /goal_relationships/{goal_relationship_gid} | Actualiza relación entre goals | goal_relationship_gid, goal_relationship_resource_subtype | {gid, resource_subtype} | goals:write | — | — |

### Project Templates (Plantillas de Proyecto) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.project_templates.list` | read | GET /project_templates | Lista plantillas de proyecto | limit, offset | lista de {gid, name, team, created_at} | project_templates:read | — | — |
| [ ] | `asana.project_templates.get` | read | GET /project_templates/{template_gid} | Obtiene detalles de plantilla | template_gid | {gid, name, team, description, created_at} | project_templates:read | — | — |
| [ ] | `asana.project_templates.list_team` | read | GET /teams/{team_gid}/project_templates | Lista plantillas de equipo | team_gid, limit | lista de {gid, name, team} | project_templates:read | — | — |
| [ ] | `asana.project_templates.delete` | delete | DELETE /project_templates/{template_gid} | Elimina plantilla de proyecto | template_gid | — | project_templates:write | I | — |
| [ ] | `asana.project_templates.instantiate` | create | POST /project_templates/{template_gid}/instantiate | Crea proyecto desde plantilla | template_gid, name, team, is_strict | {gid, name, owner, created_at} | projects:write | — | — |

### Task Templates (Plantillas de Tarea) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.task_templates.list` | read | GET /task_templates | Lista plantillas de tarea | limit, offset | lista de {gid, name, created_at} | task_templates:read | — | — |
| [ ] | `asana.task_templates.get` | read | GET /task_templates/{template_gid} | Obtiene plantilla de tarea | template_gid | {gid, name, description, created_at} | task_templates:read | — | — |
| [ ] | `asana.task_templates.delete` | delete | DELETE /task_templates/{template_gid} | Elimina plantilla de tarea | template_gid | — | task_templates:write | I | — |
| [ ] | `asana.task_templates.instantiate` | create | POST /task_templates/{template_gid}/instantiate | Crea tarea desde plantilla | template_gid, name, project, assignee | {gid, name, project, created_at} | tasks:write | — | — |

### Status Updates (Actualizaciones de Estado) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.status_updates.list` | read | GET /{resource_type}/{resource_gid}/status_updates | Lista actualizaciones de estado | resource_type, resource_gid, limit | lista de {gid, title, html_text, created_by, created_at} | status_updates:read | — | — |
| [ ] | `asana.status_updates.create` | create | POST /{resource_type}/{resource_gid}/status_updates | Crea actualización de estado | resource_type, resource_gid, title, html_text, status_type | {gid, title, html_text, created_by, created_at} | status_updates:write | E | — |
| [ ] | `asana.status_updates.get` | read | GET /status_updates/{status_update_gid} | Obtiene actualización de estado | status_update_gid | {gid, title, html_text, created_by, created_at, resource} | status_updates:read | — | — |
| [ ] | `asana.status_updates.delete` | delete | DELETE /status_updates/{status_update_gid} | Elimina actualización de estado | status_update_gid | — | status_updates:write | I | — |

### Memberships (Membresías Generales) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.memberships.list` | read | GET /memberships | Lista membresías de objeto (proyecto/portfolio/etc) | parent_gid, parent_resource_type, limit | lista de {gid, user, parent, role} | memberships:read | — | — |
| [ ] | `asana.memberships.create` | create | POST /memberships | Crea membresía | parent_gid, parent_resource_type, user, role | {gid, user, parent, role} | memberships:write | E | — |
| [ ] | `asana.memberships.get` | read | GET /memberships/{membership_gid} | Obtiene membresía | membership_gid | {gid, user, parent, role} | memberships:read | — | — |
| [ ] | `asana.memberships.update` | update | PUT /memberships/{membership_gid} | Actualiza membresía (rol) | membership_gid, role | {gid, role} | memberships:write | — | — |
| [ ] | `asana.memberships.delete` | delete | DELETE /memberships/{membership_gid} | Elimina membresía | membership_gid | — | memberships:write | — | — |

### Time Tracking (Seguimiento de Tiempo) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.time_tracking_entries.list_task` | read | GET /tasks/{task_gid}/time_tracking_entries | Lista entradas de tiempo de tarea | task_gid, limit | lista de {gid, task, user, duration_minutes, created_at} | time_tracking:read | — | — |
| [ ] | `asana.time_tracking_entries.create` | create | POST /tasks/{task_gid}/time_tracking_entries | Crea entrada de tiempo | task_gid, user, duration_minutes, spent_at, created_by | {gid, task, user, duration_minutes, created_at} | time_tracking:write | — | — |
| [ ] | `asana.time_tracking_entries.get` | read | GET /time_tracking_entries/{entry_gid} | Obtiene entrada de tiempo | entry_gid | {gid, task, user, duration_minutes, spent_at, created_at} | time_tracking:read | — | — |
| [ ] | `asana.time_tracking_entries.update` | update | PUT /time_tracking_entries/{entry_gid} | Actualiza entrada de tiempo | entry_gid, duration_minutes, spent_at | {gid, duration_minutes, spent_at} | time_tracking:write | — | — |
| [ ] | `asana.time_tracking_entries.delete` | delete | DELETE /time_tracking_entries/{entry_gid} | Elimina entrada de tiempo | entry_gid | — | time_tracking:write | I | — |
| [ ] | `asana.time_tracking_entries.list` | read | GET /time_tracking_entries | Lista múltiples entradas de tiempo | user_gid, from, to, limit | lista de {gid, task, user, duration_minutes} | time_tracking:read | — | — |
| [ ] | `asana.time_tracking_categories.list` | read | GET /workspaces/{workspace_gid}/time_tracking_categories | Lista categorías de tiempo | workspace_gid, limit | lista de {gid, name, enabled} | time_tracking:read | — | — |
| [ ] | `asana.time_tracking_categories.create` | create | POST /workspaces/{workspace_gid}/time_tracking_categories | Crea categoría de tiempo | workspace_gid, name | {gid, name, enabled, created_at} | time_tracking:write | — | — |
| [ ] | `asana.time_tracking_categories.get` | read | GET /time_tracking_categories/{category_gid} | Obtiene categoría de tiempo | category_gid | {gid, name, enabled, created_at} | time_tracking:read | — | — |
| [ ] | `asana.time_tracking_categories.update` | update | PUT /time_tracking_categories/{category_gid} | Actualiza categoría de tiempo | category_gid, name, enabled | {gid, name, enabled} | time_tracking:write | — | — |
| [ ] | `asana.time_tracking_categories.delete` | delete | DELETE /time_tracking_categories/{category_gid} | Elimina categoría de tiempo | category_gid | — | time_tracking:write | I | — |
| [ ] | `asana.time_tracking_categories.list_entries` | read | GET /time_tracking_categories/{category_gid}/time_tracking_entries | Lista entradas de categoría | category_gid, limit | lista de {gid, time_tracking_entry, user} | time_tracking:read | — | — |

### Webhooks (Webhooks) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.webhooks.list` | read | GET /webhooks | Lista webhooks | workspace_gid, resource_gid, limit | lista de {gid, resource, filters, url, active} | webhooks:read | — | — |
| [ ] | `asana.webhooks.create` | create | POST /webhooks | Crea webhook | workspace_gid, resource_gid, url, filters | {gid, resource, filters, url, active, created_at} | webhooks:write | — | — |
| [ ] | `asana.webhooks.get` | read | GET /webhooks/{webhook_gid} | Obtiene detalles de webhook | webhook_gid | {gid, resource, filters, url, active, created_at} | webhooks:read | — | — |
| [ ] | `asana.webhooks.update` | update | PUT /webhooks/{webhook_gid} | Actualiza webhook | webhook_gid, filters, url | {gid, filters, url, active} | webhooks:write | — | — |
| [ ] | `asana.webhooks.delete` | delete | DELETE /webhooks/{webhook_gid} | Elimina webhook | webhook_gid | — | webhooks:write | I | — |

### Audit Log & Organization (Auditoría y Organización) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.audit_log.list` | read | GET /workspaces/{workspace_gid}/audit_log_events | Obtiene eventos de auditoría de workspace | workspace_gid, limit, offset | lista de {gid, event_type, actor, resource, created_at} | audit_log:read | — | — |
| [ ] | `asana.organization_exports.create` | create | POST /organization_exports | Inicia exportación de organización | workspace_gid | — | organization_exports:write | — | — |
| [ ] | `asana.organization_exports.get` | read | GET /organization_exports/{export_gid} | Obtiene detalles de exportación | export_gid | {gid, state, url, download_url, created_at} | organization_exports:read | — | — |

### Advanced (Avanzado) (54)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `asana.batch.execute` | create | POST /batch | Ejecuta múltiples llamadas en paralelo | requests (array) | array de {body, status_code, headers} | (según operaciones) | — | — |
| [ ] | `asana.typeahead.search` | read | GET /workspaces/{workspace_gid}/typeahead | Busca objetos por autocompletado | workspace_gid, type, query, count | lista de {gid, name, resource_type} | (según tipo) | — | — |
| [ ] | `asana.events.list` | read | GET /{resource_path}/events | Obtiene eventos de cambios en recurso | resource_path, sync_token, limit | lista de {type, action, resource, created_at} | (según recurso) | — | listar_eventos_asana |
| [ ] | `asana.reactions.list` | read | GET /{resource_path}/reactions | Lista reacciones con emoji en objeto | resource_path, emoji | lista de {gid, user, emoji} | reactions:read | — | — |
| [ ] | `asana.allocations.get` | read | GET /allocations/{allocation_gid} | Obtiene asignación de recurso | allocation_gid | {gid, resource, from, to, effort} | allocations:read | — | — |
| [ ] | `asana.allocations.list` | read | GET /allocations | Lista asignaciones de recursos | user_gid, project_gid, limit | lista de {gid, resource, from, to, effort} | allocations:read | — | — |
| [ ] | `asana.allocations.create` | create | POST /allocations | Crea asignación de recurso | resource_gid, from, to, effort | {gid, resource, from, to, effort, created_at} | allocations:write | — | — |
| [ ] | `asana.allocations.update` | update | PUT /allocations/{allocation_gid} | Actualiza asignación | allocation_gid, effort, from, to | {gid, effort, from, to} | allocations:write | — | — |
| [ ] | `asana.allocations.delete` | delete | DELETE /allocations/{allocation_gid} | Elimina asignación | allocation_gid | — | allocations:write | I | — |
| [ ] | `asana.project_briefs.get` | read | GET /project_briefs/{brief_gid} | Obtiene resumen de proyecto | brief_gid | {gid, project, html_text, created_at} | project_briefs:read | — | — |
| [ ] | `asana.project_briefs.create` | create | POST /projects/{project_gid}/project_briefs | Crea resumen de proyecto | project_gid, html_text | {gid, project, html_text, created_at} | project_briefs:write | — | — |
| [ ] | `asana.project_briefs.update` | update | PUT /project_briefs/{brief_gid} | Actualiza resumen de proyecto | brief_gid, html_text | {gid, html_text} | project_briefs:write | — | — |
| [ ] | `asana.project_briefs.delete` | delete | DELETE /project_briefs/{brief_gid} | Elimina resumen de proyecto | brief_gid | — | project_briefs:write | I | — |
| [ ] | `asana.project_portfolio_settings.get` | read | GET /project_portfolio_settings/{setting_gid} | Obtiene configuración de proyecto en portfolio | setting_gid | {gid, project, portfolio, custom_field} | project_portfolio_settings:read | — | — |
| [ ] | `asana.project_portfolio_settings.update` | update | PUT /project_portfolio_settings/{setting_gid} | Actualiza configuración | setting_gid, template, is_sample | {gid, template, is_sample} | project_portfolio_settings:write | — | — |
| [ ] | `asana.project_portfolio_settings.list_project` | read | GET /projects/{project_gid}/project_portfolio_settings | Lista configuraciones para proyecto | project_gid, limit | lista de {gid, project, portfolio} | project_portfolio_settings:read | — | — |
| [ ] | `asana.project_portfolio_settings.list_portfolio` | read | GET /portfolios/{portfolio_gid}/project_portfolio_settings | Lista configuraciones para portfolio | portfolio_gid, limit | lista de {gid, project, portfolio} | project_portfolio_settings:read | — | — |
| [ ] | `asana.ooo_entries.get` | read | GET /ooo_entries/{ooo_entry_gid} | Obtiene entrada de ausencia | ooo_entry_gid | {gid, user, start_on, end_on, resource_type} | ooo:read | — | — |
| [ ] | `asana.ooo_entries.list` | read | GET /users/{user_gid}/ooo_entries | Lista ausencias del usuario | user_gid | lista de {gid, user, start_on, end_on} | ooo:read | — | — |
| [ ] | `asana.ooo_entries.create` | create | POST /users/{user_gid}/ooo_entries | Crea entrada de ausencia | user_gid, start_on, end_on, name | {gid, user, start_on, end_on, created_at} | ooo:write | — | — |
| [ ] | `asana.ooo_entries.update` | update | PUT /ooo_entries/{ooo_entry_gid} | Actualiza entrada de ausencia | ooo_entry_gid, start_on, end_on | {gid, start_on, end_on} | ooo:write | — | — |
| [ ] | `asana.ooo_entries.delete` | delete | DELETE /ooo_entries/{ooo_entry_gid} | Elimina entrada de ausencia | ooo_entry_gid | — | ooo:write | I | — |
| [ ] | `asana.rates.list` | read | GET /rates | Lista tasas de facturación | limit, offset | lista de {gid, name, rate} | rates:read | — | — |
| [ ] | `asana.rates.create` | create | POST /rates | Crea tasa de facturación | name, rate, currency | {gid, name, rate, currency, created_at} | rates:write | — | — |
| [ ] | `asana.rates.get` | read | GET /rates/{rate_gid} | Obtiene tasa de facturación | rate_gid | {gid, name, rate, currency} | rates:read | — | — |
| [ ] | `asana.rates.update` | update | PUT /rates/{rate_gid} | Actualiza tasa de facturación | rate_gid, name, rate | {gid, name, rate} | rates:write | — | — |
| [ ] | `asana.rates.delete` | delete | DELETE /rates/{rate_gid} | Elimina tasa de facturación | rate_gid | — | rates:write | I | — |
| [ ] | `asana.roles.list` | read | GET /roles | Lista roles RBAC | workspace_gid, limit | lista de {gid, name, description} | roles:read | — | — |
| [ ] | `asana.roles.create` | create | POST /roles | Crea rol RBAC | workspace_gid, name, permissions | {gid, name, permissions, created_at} | roles:write | — | — |
| [ ] | `asana.roles.get` | read | GET /roles/{role_gid} | Obtiene detalles de rol | role_gid | {gid, name, permissions, description} | roles:read | — | — |
| [ ] | `asana.roles.update` | update | PUT /roles/{role_gid} | Actualiza rol RBAC | role_gid, permissions | {gid, permissions} | roles:write | — | — |
| [ ] | `asana.roles.delete` | delete | DELETE /roles/{role_gid} | Elimina rol RBAC | role_gid | — | roles:write | I | — |
| [ ] | `asana.access_requests.list` | read | GET /access_requests | Lista solicitudes de acceso pendientes | limit, offset | lista de {gid, resource, requester, status} | access_requests:read | — | — |
| [ ] | `asana.access_requests.submit` | create | POST /access_requests | Envía solicitud de acceso a recurso privado | resource_gid, resource_type, comment | {gid, resource, requester, status} | access_requests:write | E | — |
| [ ] | `asana.access_requests.approve` | update | PUT /access_requests/{access_request_gid}/approve | Aprueba solicitud de acceso | access_request_gid | {gid, status} | access_requests:write | — | — |
| [ ] | `asana.access_requests.reject` | update | PUT /access_requests/{access_request_gid}/reject | Rechaza solicitud de acceso | access_request_gid | {gid, status} | access_requests:write | — | — |
| [ ] | `asana.jobs.get` | read | GET /jobs/{job_gid} | Obtiene estado de operación asíncrona | job_gid | {gid, resource_type, state, started_at, completed_at} | jobs:read | — | — |
| [ ] | `asana.agents.list` | read | GET /workspaces/{workspace_gid}/agents | Lista agentes IA en workspace | workspace_gid, limit | lista de {gid, name, resource_type} | agents:read | — | — |
| [ ] | `asana.agents.get` | read | GET /agents/{agent_gid} | Obtiene detalles de agente IA | agent_gid | {gid, name, description, created_at} | agents:read | — | — |
| [ ] | `asana.ai_studio_usage.get_runs` | read | GET /workspaces/{workspace_gid}/ai_studio_runs | Obtiene historial de uso de AI Studio | workspace_gid, limit | lista de {gid, type, created_at, credits_used} | ai_studio_usage:read | — | — |
| [ ] | `asana.ai_studio_usage.get_seats` | read | GET /workspaces/{workspace_gid}/ai_studio_seats | Obtiene asignación de plazas de AI Studio | workspace_gid | {gid, workspace, total_seats, used_seats} | ai_studio_usage:read | — | — |
| [ ] | `asana.time_periods.get` | read | GET /time_periods/{time_period_gid} | Obtiene período de tiempo | time_period_gid | {gid, start_on, end_on, period_type} | time_periods:read | — | — |
| [ ] | `asana.time_periods.list` | read | GET /time_periods | Lista períodos de tiempo | limit, offset | lista de {gid, start_on, end_on} | time_periods:read | — | — |
| [ ] | `asana.timesheet_approval_statuses.get` | read | GET /timesheet_approval_statuses/{status_gid} | Obtiene estado de aprobación de timesheet | status_gid | {gid, user, state, created_at} | timesheet_approval_statuses:read | — | — |
| [ ] | `asana.timesheet_approval_statuses.list` | read | GET /timesheet_approval_statuses | Lista estados de aprobación de timesheet | limit, offset | lista de {gid, user, state} | timesheet_approval_statuses:read | — | — |
| [ ] | `asana.timesheet_approval_statuses.create` | create | POST /timesheet_approval_statuses | Crea estado de aprobación | user_gid, state, period_from, period_to | {gid, user, state, created_at} | timesheet_approval_statuses:write | — | — |
| [ ] | `asana.timesheet_approval_statuses.update` | update | PUT /timesheet_approval_statuses/{status_gid} | Actualiza estado de aprobación | status_gid, state | {gid, state} | timesheet_approval_statuses:write | — | — |
| [ ] | `asana.custom_types.list` | read | GET /custom_types | Lista tipos personalizados de objeto | limit, offset | lista de {gid, name, description} | custom_types:read | — | — |
| [ ] | `asana.custom_types.get` | read | GET /custom_types/{custom_type_gid} | Obtiene tipo personalizado | custom_type_gid | {gid, name, description, created_at} | custom_types:read | — | — |
| [ ] | `asana.user_task_lists.get` | read | GET /user_task_lists/{user_task_list_gid} | Obtiene lista de tareas de usuario | user_task_list_gid | {gid, user, name} | user_task_lists:read | — | — |
| [ ] | `asana.user_task_lists.get_user` | read | GET /users/{user_gid}/user_task_list | Obtiene lista de tareas de usuario específico | user_gid | {gid, user, name} | user_task_lists:read | — | — |
| [ ] | `asana.rules.trigger` | create | POST /rules/{rule_gid}/trigger | Dispara acción de regla manual | rule_gid, resource_gid | {} | rules:write | — | — |
| [ ] | `asana.exports.graph` | create | POST /graph_exports | Inicia exportación de grafo de workspace | workspace_gid | — | exports:write | — | — |
| [ ] | `asana.exports.resource` | create | POST /resource_exports | Inicia exportación de recursos | workspace_gid, resource_type, filters | {} | exports:write | — | — |

## Observaciones de las herramientas viejas

- Casi todas las herramientas viejas reciben **nombres** (`..._por_nombre`) y resuelven el id dentro. En el estandar nuevo la funcion recibe el id y la busqueda por nombre es otra funcion; hay que decidir como se resuelve (lo hace el modelo encadenando funciones).
- `listar_tareas_completadas`, `listar_tareas_no_completadas` y `listar_tareas_por_etiqueta` son filtros de `listar_tareas`.
- Asignar una tarea o comentar notifica a otras personas: revisar `exits_outside`.
- `BIGTOOLS_REGISTRY` tiene `asana: []` (vacio): el inspector del agente dice 'tools not yet implemented'.
