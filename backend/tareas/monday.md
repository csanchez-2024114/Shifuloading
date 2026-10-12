# Tareas: monday.com

- **Funciones catalogadas:** 133 · **Hechas:** 0 · **Pendientes:** 133 · App sin herramientas viejas
- **Documentación oficial:** https://developer.monday.com/api-reference/reference
- **Fuentes que consultó el catálogo:** https://developer.monday.com/api-reference/reference https://developer.monday.com/api-reference/docs https://developer.monday.com/apps/docs/oauth https://developer.monday.com/api-reference/reference/account https://developer.monday.com/api-reference/reference/boards https://developer.monday.com/api-reference/reference/items https://developer.monday.com/api-reference/reference/columns https://developer.monday.com/api-reference/reference/groups https://developer.monday.com/api-reference/reference/users https://developer.monday.com/api-reference/reference/teams https://developer.monday.com/api-reference/reference/updates https://developer.monday.com/api-reference/reference/docs https://developer.monday.com/api-reference/reference/subitems https://developer.monday.com/api-reference/reference/webhooks https://developer.monday.com/api-reference/reference/workspaces https://developer.monday.com/api-reference/reference/folders https://developer.monday.com/api-reference/reference/notification https://developer.monday.com/api-reference/reference/assets https://developer.monday.com/api-reference/reference/templates https://developer.monday.com/api-reference/reference/form https://developer.monday.com/api-reference/reference/dashboards-and-widgets https://developer.monday.com/api-reference/reference/portfolio https://developer.monday.com/api-reference/docs/searching-across-your-account https://developer.monday.com/api-reference/reference/aggregate https://developer.monday.com/api-reference/reference/audit-logs https://developer.monday.com/api-reference/reference/activity-logs https://developer.monday.com/api-reference/reference/me https://developer.monday.com/api-reference/reference/object-relations https://developer.monday.com/api-reference/reference/ai
- **Paginación típica:** Cursor-based (page, limit); algunos endpoints usan items_page con offset
- **Qué no se pudo verificar:** Nombres exactos de algunos scopes por grupo de operaciones; si hay webhooks_only en create_webhook; parámetros exactos de algunos filtros de queries antiguas (versión 2025-10 vs 2026-07 vs 2026-10); si items_page es una query raíz o anidada; exactitud de límites de ritmo para todas las operaciones
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/monday/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `monday`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `monday` |
| Variables del `.env` que necesitas | MONDAY_CLIENT_ID, MONDAY_CLIENT_SECRET, MONDAY_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/monday/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `monday.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2 con código (auth.monday.com/oauth2/authorize, auth.monday.com/oauth2/token) |
| Duración del token (según el catálogo) | No caduca (válido hasta desinstalación de app; código de autorización válido 10 minutos) |
| Refresco (según el catálogo) | No (no soporta refresh tokens en OAuth legacy; OAuth 2.1 mejorado disponible) |
| Permisos (según el catálogo) | account:read, boards:read, boards:write, columns:read, columns:write, groups:read, groups:write, items:read, items:write, updates:read, updates:write, users:read, users:write, teams:read, teams:write, webhooks:read, webhooks:write, workspaces:read, workspaces:write, docs:read, docs:write, notifications:write, me:read, AI:Consume |
| Restricciones de acceso | Portfolio solo en plan Enterprise; Audit logs solo Enterprise con permiso manage_account_security; algunos endpoints requieren API version 2026-07+ |
| Límites de ritmo | Bulk operations rate limit 40 mutaciones/minuto; activity_logs máximo 10,000; search máximo 20 resultados por tipo; paginación items default 25, máximo 100 |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/monday/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> monday`. | Cuenta con `provider: monday`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/monday.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> monday <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de monday.com. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/monday.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Account (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.account.get` | read | query account | Obtiene metadatos de la cuenta conectada (plan, id, nombre, zona horaria) | — | {id, slug, name, tier, plan, country_code, active_members_count} | account:read | — | — |

### Users (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.user.list` | read | query users | Lista usuarios de la cuenta con filtrado por email, id, nombre, estado | array de {id, email, name, title, department, teams, is_admin} + paginación | users:read | — | — | — |
| [ ] | `monday.user.get` ★ | read | query me | Obtiene perfil del usuario autenticado (identidad verificada) | — | {id, email, name, is_admin, is_guest, account, teams, department, created_at} | me:read | — | — |
| [ ] | `monday.user.add_to_board` | create | mutation add_users_to_board | Agrega usuarios a un tablero con rol (propietario o suscriptor) | user_ids, board_id, kind | array de {user_id, success, errors} | boards:write | — | — |
| [ ] | `monday.user.add_to_workspace` | create | mutation add_users_to_workspace | Incorpora usuarios a un espacio de trabajo | user_ids, workspace_id, kind | array de {user_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.user.add_to_team` | create | mutation add_users_to_team | Agrega usuarios a un equipo | user_ids, team_id | array de {user_id, success, errors} | teams:write | — | — |
| [ ] | `monday.user.update` | update | mutation update_multiple_users | Actualiza atributos de usuario (correo, nombre, departamento, ubicación, teléfono, cumpleaños) | user_ids, field, value | array de {user_id, errors} | users:write | — | — |
| [ ] | `monday.user.update_role` | update | mutation update_user_role | Modifica el rol de usuario (admin o custom) | user_ids, role_id | {success, errors} | users:write | — | — |
| [ ] | `monday.user.activate` | create | mutation activate_users | Activa usuarios desactivados en la cuenta | user_ids | array de {user_id, success, errors} | users:write | — | — |
| [ ] | `monday.user.deactivate` | delete | mutation deactivate_users | Desactiva usuarios de la cuenta (máximo 200) | user_ids | array de {user_id, success, errors} | users:write | — | — |
| [ ] | `monday.user.remove_from_board` | delete | mutation delete_subscribers_from_board | Elimina usuarios de suscriptores de tablero | user_ids, board_id | array de {user_id, success, errors} | boards:write | — | — |
| [ ] | `monday.user.remove_from_team` | delete | mutation remove_users_from_team | Quita usuarios de equipo | user_ids, team_id | array de {user_id, success, errors} | teams:write | — | — |
| [ ] | `monday.user.remove_from_workspace` | delete | mutation delete_users_from_workspace | Elimina usuarios del acceso a espacio de trabajo | user_ids, workspace_id | array de {user_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.user.invite` | create | mutation invite_users | Invita usuarios por correo a unirse a la cuenta | emails | array de {email, success, errors} | users:write | — | — |

### Teams (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.team.list` | read | query teams | Lista equipos de la cuenta con filtrado por ids | array de {id, name, picture_url, owners, users} | teams:read | — | — | — |
| [ ] | `monday.team.create` | create | mutation create_team | Crea un nuevo equipo | name | {id, name, picture_url} | teams:write | — | — |
| [ ] | `monday.team.add_to_board` | create | mutation add_teams_to_board | Agrega equipos a un tablero | team_ids, board_id, kind | array de {team_id, success, errors} | boards:write | — | — |
| [ ] | `monday.team.add_users` | create | mutation add_users_to_team | Incorpora usuarios a un equipo | user_ids, team_id | array de {user_id, success, errors} | teams:write | — | — |
| [ ] | `monday.team.add_to_workspace` | create | mutation add_teams_to_workspace | Incorpora equipos a un espacio de trabajo | team_ids, workspace_id, kind | array de {team_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.team.assign_owners` | update | mutation assign_team_owners | Asigna propietarios a un equipo (máximo 200 usuarios) | user_ids, team_id | {success, errors} | teams:write | — | — |
| [ ] | `monday.team.remove_owners` | update | mutation remove_team_owners | Quita propietarios de un equipo (máximo 200 usuarios) | user_ids, team_id | {success, errors} | teams:write | — | — |
| [ ] | `monday.team.remove_users` | delete | mutation remove_users_from_team | Elimina usuarios de un equipo | user_ids, team_id | array de {user_id, success, errors} | teams:write | — | — |
| [ ] | `monday.team.delete` | delete | mutation delete_team | Elimina un equipo completamente | team_id | {success, errors} | teams:write | — | — |
| [ ] | `monday.team.remove_from_board` | delete | mutation delete_teams_from_board | Quita equipos de un tablero | team_ids, board_id | array de {team_id, success, errors} | boards:write | — | — |
| [ ] | `monday.team.remove_from_workspace` | delete | mutation delete_teams_from_workspace | Elimina equipos del espacio de trabajo | team_ids, workspace_id | array de {team_id, success, errors} | workspaces:write | — | — |

### Boards (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.board.list` | read | query boards | Lista tableros con filtrado por ids, tipo, workspace, estado | array de {id, name, state, board_kind, board_owner_ids, created_at, updated_at, description} + paginación | boards:read | — | — | — |
| [ ] | `monday.board.create` | create | mutation create_board | Crea nuevo tablero en espacio de trabajo | board_name, workspace_id, board_kind, folder_id, template_id | {id, name, state, board_kind, created_at} | boards:write | — | — |
| [ ] | `monday.board.update` | update | mutation update_board | Modifica metadatos del tablero (nombre, descripción, comunicación, terminología items) | board_id, board_attribute, new_value | {id, [attribute]: new_value} | boards:write | — | — |
| [ ] | `monday.board.update_kind` | update | mutation change_board_kind | Cambia privacidad del tablero (privado, público, compartible) | board_id, kind | {id, board_kind} | boards:write | — | — |
| [ ] | `monday.board.update_hierarchy` | update | mutation update_board_hierarchy | Ajusta ubicación del tablero (workspace, carpeta, producto) | board_id, attributes | {id, workspace_id, board_folder_id} | boards:write | — | — |
| [ ] | `monday.board.set_permission` | update | mutation set_board_permission | Establece rol/permisos por defecto del tablero (solo Enterprise) | board_id, basic_role_name | {success} | boards:write | — | — |
| [ ] | `monday.board.duplicate` | create | mutation duplicate_board | Crea copia del tablero con items y grupos | board_id, board_name, folder_id, duplicate_type, keep_subscribers | {id, name, created_at} | boards:write | — | — |
| [ ] | `monday.board.archive` | delete | mutation archive_board | Archiva tablero sin borrarlo permanentemente | board_id | {id, state} | boards:write | — | — |
| [ ] | `monday.board.delete` | delete | mutation delete_board | Borra tablero permanentemente | board_id | {success, errors} | boards:write | I | — |
| [ ] | `monday.board.export` | create | mutation create_board_export | Genera CSV de tablero (Enterprise), retorna descarga o job async | board_id, export_options, time_zone | {job_id} o {url} | boards:write | — | — |
| [ ] | `monday.board.export_status` | read | query get_export_job_status | Obtiene estado de exportación async (Enterprise) | job_id | {status, board_id, created_at, completed_at} | boards:read | — | — |

### Items (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.item.list` | read | query items | Lista items de tableros con filtrado y paginación | array de {id, name, state, created_at, updated_at, subitems, column_values} + paginación | boards:read | — | — | — |
| [ ] | `monday.item.create` | create | mutation create_item | Crea item nuevo en tablero con valores de columna | board_id, item_name, column_values, group_id | {id, name, board_id, created_at} | boards:write | — | — |
| [ ] | `monday.item.update_position` | update | mutation change_item_position | Reposiciona item en tablero (mover entre grupos) | item_id, position_relative_method, relative_to, group_id | {id} | boards:write | — | — |
| [ ] | `monday.item.move_to_group` | update | mutation move_item_to_group | Traslada item y subitems a diferente grupo | item_id, group_id | {id} | boards:write | — | — |
| [ ] | `monday.item.move_to_board` | update | mutation move_item_to_board | Transfiere item a tablero diferente con mapeo de columnas | item_id, board_id, group_id, columns_mapping | {id, board_id} | boards:write | — | — |
| [ ] | `monday.item.update_description` | update | mutation set_item_description_content | Actualiza descripción del item con markdown | item_id, markdown | {id} | boards:write | — | — |
| [ ] | `monday.item.update_assets` | update | mutation update_assets_on_item | Modifica archivos en columna file | board_id, item_id, column_id, files | {id} | boards:write | — | — |
| [ ] | `monday.item.duplicate` | create | mutation duplicate_item | Duplica item con subitems anidados y actualizaciones opcionales | board_id, item_id, with_updates | {id, name, created_at} | boards:write | — | — |
| [ ] | `monday.item.archive` | delete | mutation archive_item | Archiva item y subitems anidados | item_id | {id, state} | boards:write | — | — |
| [ ] | `monday.item.delete` | delete | mutation delete_item | Borra item y subitems permanentemente | item_id | {success, errors} | boards:write | I | — |
| [ ] | `monday.item.clear_updates` | delete | mutation clear_item_updates | Elimina todos los comentarios/actualizaciones de item | item_id | {success} | updates:write | — | — |

### Subitems (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.subitem.list` | read | query subitems (anidada en items) | Lista subitems de item padre con filtrado | array de {id, name, created_at, column_values} | boards:read | — | — | — |
| [ ] | `monday.subitem.create` | create | mutation create_subitem | Crea subitem nuevo bajo item padre | parent_item_id, subitem_name, column_values | {id, name, parent_id, created_at} | boards:write | — | — |

### Columns (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.column.list` | read | query columns (anidada) | Lista columnas del tablero con filtrado por tipo | array de {id, title, type, settings_str, width} | boards:read | — | — | — |
| [ ] | `monday.column.create` | create | mutation create_column | Crea columna nueva en tablero con tipo específico | board_id, column_title, column_type | {id, title, type} | boards:write | — | — |
| [ ] | `monday.column.update` | update | mutation update_column | Modifica propiedades de columna (tipo, descripción, ancho, capacidades) | board_id, column_id, attributes | {id, [attribute]: value} | boards:write | — | — |
| [ ] | `monday.column.update_title` | update | mutation change_column_title | Cambia título de columna | board_id, column_id, title | {id, title} | boards:write | — | — |
| [ ] | `monday.column.update_metadata` | update | mutation change_column_metadata | Actualiza título o descripción de columna | board_id, column_id, property, value | {id} | boards:write | — | — |
| [ ] | `monday.column.change_value` | update | mutation change_column_value | Modifica valor de columna en item con JSON | board_id, item_id, column_id, value | {id} | boards:write | — | — |
| [ ] | `monday.column.change_simple_value` | update | mutation change_simple_column_value | Modifica valor de columna en item con string | board_id, item_id, column_id, value | {id} | boards:write | — | — |
| [ ] | `monday.column.change_multiple_values` | update | mutation change_multiple_column_values | Actualiza múltiples columnas en un item | board_id, item_id, column_values | {id} | boards:write | — | — |
| [ ] | `monday.column.delete` | delete | mutation delete_column | Elimina columna del tablero permanentemente | board_id, column_id | {success, errors} | boards:write | I | — |

### Groups (Secciones) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.group.list` | read | query groups (anidada) | Lista grupos del tablero | array de {id, title, color, position, items_count} | boards:read | — | — | — |
| [ ] | `monday.group.create` | create | mutation create_group | Crea grupo/sección nuevo en tablero | board_id, group_name, color | {id, title, color} | boards:write | — | — |
| [ ] | `monday.group.update` | update | mutation update_group | Modifica propiedades del grupo (título, color, posición) | board_id, group_id, group_name, color, position | {id, title, color} | boards:write | — | — |
| [ ] | `monday.group.duplicate` | create | mutation duplicate_group | Duplica grupo y todos sus items (límite 40 mutaciones/minuto) | board_id, group_id, group_name | {id, title, items_count} | boards:write | — | — |
| [ ] | `monday.group.archive` | delete | mutation archive_group | Archiva grupo y todos sus items sin borrar | board_id, group_id | {id, state} | boards:write | — | — |
| [ ] | `monday.group.delete` | delete | mutation delete_group | Borra grupo y todos sus items permanentemente | board_id, group_id | {success, errors} | boards:write | I | — |

### Updates (Comentarios) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.update.list` | read | query updates | Lista actualizaciones/comentarios de item o tablero en orden cronológico inverso | array de {id, text, user_id, created_at, updated_at, replies} + paginación | updates:read | — | — | — |
| [ ] | `monday.update.create` | create | mutation create_update | Agrega comentario/actualización a item con menciones opcionales | item_id, body | {id, text, user_id, created_at} | updates:write | E | — |
| [ ] | `monday.update.edit` | update | mutation edit_update | Modifica contenido de actualización existente | update_id, body | {id, text, updated_at} | updates:write | — | — |
| [ ] | `monday.update.like` | create | mutation like_update | Agrega reacción "me gusta" a actualización | update_id | {id, liked_by} | updates:write | — | — |
| [ ] | `monday.update.unlike` | delete | mutation unlike_update | Quita reacción "me gusta" de actualización | update_id | {id, liked_by} | updates:write | — | — |
| [ ] | `monday.update.pin` | create | mutation pin_to_top | Fija actualización al tope de item | update_id | {id, pinned} | updates:write | — | — |
| [ ] | `monday.update.unpin` | delete | mutation unpin_from_top | Quita actualización del tope | update_id | {id, pinned} | updates:write | — | — |
| [ ] | `monday.update.delete` | delete | mutation delete_update | Elimina actualización/comentario | update_id | {success, errors} | updates:write | I | — |

### Documents (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.doc.list` | read | query docs | Lista documentos de espacio de trabajo con filtrado | array de {id, name, owner_id, created_at, updated_at} + paginación | docs:read | — | — | — |
| [ ] | `monday.doc.create` | create | mutation create_doc | Crea documento nuevo en espacio de trabajo o columna | parent_id, parent_type, doc_name | {id, name, created_at} | docs:write | — | — |
| [ ] | `monday.doc.add_markdown` | create | mutation add_content_to_doc_from_markdown | Agrega contenido markdown a documento (convierte a bloques) | doc_id, markdown | {id, content_count} | docs:write | — | — |
| [ ] | `monday.doc.import_html` | create | mutation import_doc_from_html | Importa contenido HTML a documento nuevo (convierte a bloques) | name, html, parent_id | {id, name, created_at} | docs:write | — | — |
| [ ] | `monday.doc.update_name` | update | mutation update_doc_name | Cambia título/nombre de documento | doc_id, title | {id, title} | docs:write | — | — |
| [ ] | `monday.doc.duplicate` | create | mutation duplicate_doc | Crea copia exacta de documento con contenido completo | doc_id | {id, name, created_at} | docs:write | — | — |
| [ ] | `monday.doc.delete` | delete | mutation delete_doc | Elimina documento permanentemente | doc_id | {success, errors} | docs:write | I | — |
| [ ] | `monday.doc.version_history` | read | query doc_version_history | Obtiene snapshots de cambios de documento agrupados en intervalos 5 minutos | doc_id, from, to | array de {timestamp, user_id, changes} | docs:read | — | — |
| [ ] | `monday.doc.version_diff` | read | query doc_version_diff | Muestra bloques añadidos, eliminados o modificados entre versiones | doc_id, from_version, to_version | array de {block_id, type, change} | docs:read | — | — |

### Webhooks (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.webhook.list` | read | query webhooks | Lista webhooks de tablero (filtrar si pertenecen a app) | board_id, app_webhooks_only | array de {id, board_id, url, event, config} | webhooks:read | — | — |
| [ ] | `monday.webhook.create` | create | mutation create_webhook | Crea suscripción webhook para evento en tablero (endpoint debe pasar verificación) | board_id, url, event, config | {id, url, state} | webhooks:write | — | — |
| [ ] | `monday.webhook.delete` | delete | mutation delete_webhook | Elimina webhook para que URL no reciba notificaciones | webhook_id | {success, errors} | webhooks:write | — | — |

### Workspaces (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.workspace.list` | read | query workspaces | Lista espacios de trabajo con filtrado por ids, tipo, estado | array de {id, name, kind, state, created_at, updated_at} + paginación | workspaces:read | — | — | — |
| [ ] | `monday.workspace.create` | create | mutation create_workspace | Crea nuevo espacio de trabajo | workspace_name, workspace_kind, description | {id, name, kind, created_at} | workspaces:write | — | — |
| [ ] | `monday.workspace.update` | update | mutation update_workspace | Modifica atributos de espacio de trabajo (nombre, descripción) | workspace_id, attributes | {id, [attribute]: value} | workspaces:write | — | — |
| [ ] | `monday.workspace.add_teams` | create | mutation add_teams_to_workspace | Incorpora equipos a espacio de trabajo con roles | team_ids, workspace_id, kind | array de {team_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.workspace.add_users` | create | mutation add_users_to_workspace | Incorpora usuarios a espacio de trabajo | user_ids, workspace_id, kind | array de {user_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.workspace.delete` | delete | mutation delete_workspace | Elimina espacio de trabajo completamente | workspace_id | {success, errors} | workspaces:write | I | — |
| [ ] | `monday.workspace.remove_teams` | delete | mutation delete_teams_from_workspace | Quita equipos de espacio de trabajo | team_ids, workspace_id | array de {team_id, success, errors} | workspaces:write | — | — |
| [ ] | `monday.workspace.remove_users` | delete | mutation delete_users_from_workspace | Elimina usuarios del acceso a espacio de trabajo | user_ids, workspace_id | array de {user_id, success, errors} | workspaces:write | — | — |

### Folders (Carpetas) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.folder.list` | read | query folders | Lista carpetas de espacio de trabajo con filtrado | array de {id, name, parent_id, color, position, workspace_id} + paginación | workspaces:read | — | — | — |
| [ ] | `monday.folder.create` | create | mutation create_folder | Crea carpeta nueva en espacio de trabajo | workspace_id, folder_name, color, parent_id | {id, name, color, workspace_id} | workspaces:write | — | — |
| [ ] | `monday.folder.update` | update | mutation update_folder | Modifica propiedades de carpeta (nombre, color, posición, padre) | folder_id, attributes | {id, [attribute]: value} | workspaces:write | — | — |
| [ ] | `monday.folder.delete` | delete | mutation delete_folder | Borra carpeta y todo su contenido permanentemente | folder_id | {success, errors} | workspaces:write | I | — |

### Notifications (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.notification.list` | read | query notifications | Lista notificaciones del usuario autenticado | limit, cursor, filter_read, since | array de {id, text, title, read, created_at, board, item, update} | (ninguno) | — | — |
| [ ] | `monday.notification.create` | create | mutation create_notification | Envía notificación al ícono de campana (puede disparar email) | user_id, target_id, target_type, text | {success} | notifications:write | E | — |

### Files/Assets (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.file.add` | create | mutation add_file_to_column | Agrega archivo a columna files (multipart form, no reemplaza) | board_id, item_id, column_id, file | {id, files: [{name, size, url}]} | boards:write | — | — |
| [ ] | `monday.file.clear` | delete | mutation change_column_value | Limpia todos los archivos de columna files | board_id, item_id, column_id | {id} | boards:write | — | — |
| [ ] | `monday.file.clear_multiple` | delete | mutation change_multiple_column_values | Limpia archivos de múltiples columnas files en un item | board_id, item_id, column_values | {id} | boards:write | — | — |

### Templates (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.template.install` | create | mutation use_template | Inicia instalación async de template en espacio de trabajo | workspace_id, template_id | {process_id} | workspaces:write | — | — |
| [ ] | `monday.template.install_status` | read | query template_installation_status | Obtiene estado de instalación async de template | process_id | {status, board_ids, board_mappings, completed_at} | workspaces:read | — | — |

### Forms (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.form.get` | read | query form | Obtiene metadatos de formulario (solo raíz, no anidada) | form_id | {id, title, description, questions, board_id} | (ninguno) | — | — |
| [ ] | `monday.form.create` | create | mutation create_form | Crea formulario nuevo | board_id, form_title | {id, form_token, board_id} | boards:write | — | — |
| [ ] | `monday.form.activate` | update | mutation activate_form | Hace formulario visible y habilita nuevas presentaciones | form_id | {id, active} | boards:write | — | — |
| [ ] | `monday.form.deactivate` | update | mutation deactivate_form | Oculta formulario y previene nuevas presentaciones | form_id | {id, active} | boards:write | — | — |
| [ ] | `monday.form.update` | update | mutation update_form | Modifica título, descripción o reordena preguntas | form_id, attributes | {id, [attribute]: value} | boards:write | — | — |
| [ ] | `monday.form.set_password` | update | mutation set_form_password | Habilita protección con contraseña (mínimo 1 carácter) | form_id, password | {id} | boards:write | — | — |
| [ ] | `monday.form.shorten_url` | create | mutation shorten_form_url | Genera y almacena URL acortada para formulario | form_id | {short_url} | boards:write | — | — |
| [ ] | `monday.form.add_question` | create | mutation create_form_question | Agrega pregunta nueva a formulario | form_id, question_text, question_type | {id, question_id} | boards:write | — | — |
| [ ] | `monday.form.update_question` | update | mutation update_form_question | Modifica propiedades de pregunta | form_id, question_id, attributes | {id, question_id} | boards:write | — | — |
| [ ] | `monday.form.delete_question` | delete | mutation delete_question | Elimina pregunta (permanente, no recuperable) | form_id, question_id | {success, errors} | boards:write | I | — |
| [ ] | `monday.form.add_tag` | create | mutation create_form_tag | Crea tag de seguimiento (nombre único dentro formulario) | form_id, tag_name | {id, tag_id} | boards:write | — | — |
| [ ] | `monday.form.delete_tag` | delete | mutation delete_form_tag | Elimina tag del formulario | form_id, tag_id, delete_associated_column | {success, errors} | boards:write | — | — |

### Dashboards (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.dashboard.create` | create | mutation create_dashboard | Crea dashboard nuevo con tableros especificados | dashboard_name, boards, workspace_id | {id, name, workspace_id, created_at} | boards:write | — | — |
| [ ] | `monday.dashboard.update` | update | mutation update_dashboard | Modifica propiedades de dashboard (título, visibilidad, ubicación) | dashboard_id, attributes | {id, [attribute]: value} | boards:write | — | — |
| [ ] | `monday.dashboard.update_hierarchy` | update | mutation update_overview_hierarchy | Ajusta posición o ubicación de dashboard en workspace | dashboard_id, workspace_id, position | {id} | boards:write | — | — |
| [ ] | `monday.dashboard.delete` | delete | mutation delete_dashboard | Elimina dashboard completamente | dashboard_id | {success, errors} | boards:write | I | — |
| [ ] | `monday.dashboard.add_widget` | create | mutation create_widget | Agrega widget nuevo a dashboard con tipo específico | dashboard_id, widget_type, widget_config | {id, widget_id} | boards:write | — | — |
| [ ] | `monday.dashboard.delete_widget` | delete | mutation delete_widget | Elimina widget de dashboard | widget_id | {success, errors} | boards:write | — | — |

### Portfolio (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.portfolio.create` | create | mutation create_portfolio | Crea tablero portfolio nuevo (solo Enterprise) | portfolio_name, workspace_id, kind | {id, name, process_id} | boards:write | — | — |
| [ ] | `monday.portfolio.create_project` | create | mutation create_project | Crea tablero de proyecto nuevo (v2026-04+, solo Enterprise) | project_name, workspace_id, kind | {id, name, process_id} | boards:write | — | — |
| [ ] | `monday.portfolio.convert_board` | update | mutation convert_board_to_project | Transforma tablero en tablero de proyecto con mapeo de columnas | board_id, column_mappings | {id, process_id} | boards:write | — | — |
| [ ] | `monday.portfolio.connect_project` | create | mutation connect_project_to_portfolio | Conecta tablero proyecto a portfolio (límite 40/minuto) | portfolio_id, project_id | {id, connected_at} | boards:write | — | — |

### Search (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.search.query` | read | query search | Busca items, tableros, documentos, espacios en cuenta completa | query, limit, board_ids, workspace_ids, strategy | {items: [{id, name, url}], boards: [...], docs: [...], workspaces: [...]} | boards:read, docs:read | — | — |

### Aggregate (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.aggregate.calculate` | read | query aggregate | Calcula resúmenes agrupados con funciones de agregación (COUNT, SUM, AVERAGE, etc.) | from, select, group_by, query | array de {group_key, calculated_fields} | boards:read | — | — |

### Activity Logs (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.activity.list_board` | read | query activity_logs (anidada en boards) | Lista cambios de actividad en tablero en orden cronológico inverso | board_id, from, to, limit, page | array de {id, event, user_id, created_at, data} | boards:read | — | — |

### Audit Logs (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.audit.list` | read | query audit_logs | Lista eventos de seguridad de cuenta (solo Enterprise admin) | limit, page, from, to, events, ip_address | array de {id, event_type, user_id, created_at, ip, details} | (requires manage_account_security) | — | — |

### Object Relations (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.object_relation.list` | read | query object_relations | Obtiene relaciones de objeto (alias, dependencias) | object_id, kind, direction | array de {id, source_object_id, target_id, target_object_type, kind} | (ninguno) | — | — |
| [ ] | `monday.object_relation.create` | create | mutation create_object_relations | Establece conexiones entre objetos (v2026-04+) | source_object_id, relations | array de {id, source_object_id, target_id} | (ninguno) | — | — |
| [ ] | `monday.object_relation.delete` | delete | mutation delete_object_relation | Quita relaciones de objeto (específica o todas) | source_object_id, relation_id, delete_all | {deleted_count} | (ninguno) | — | — |

### AI (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `monday.ai.run_prompt` | create | mutation run_prompt | Ejecuta prompt contra modelo IA alojado (v2026-10+) | prompt, model, system_prompt, temperature, max_tokens | {content} | AI:Consume | — | — |
