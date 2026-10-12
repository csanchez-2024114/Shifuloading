# Tareas: Notion

- **Funciones catalogadas:** 61 · **Hechas:** 0 · **Pendientes:** 61 · App sin herramientas viejas
- **Documentación oficial:** https://developers.notion.com/reference
- **Fuentes que consultó el catálogo:** https://developers.notion.com/reference https://developers.notion.com/llms.txt https://developers.notion.com/docs/authorization https://developers.notion.com/docs/create-a-notion-integration https://developers.notion.com/reference/request-limits https://developers.notion.com/reference/capabilities https://developers.notion.com/reference/get-user https://developers.notion.com/reference
- **Paginación típica:** Cursor-based con campos has_more (boolean), next_cursor (string), results (array)
- **Qué no se pudo verificar:** Tiempo exacto de expiración del access token OAuth; mapeo granular de capabilities a operaciones específicas; si hay más endpoints de admin para el usuario final; detalles exactos de webhook registration
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/notion/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `notion`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `notion` |
| Variables del `.env` que necesitas | NOTION_CLIENT_ID, NOTION_CLIENT_SECRET, NOTION_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/notion/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `notion.user.get_me` |
| Cómo se autentica (según el catálogo) | OAuth2 código (public integration) con intercambio Basic Auth; también soporta Personal Access Tokens (PAT) estáticos e Internal Connections (API token estático) |
| Duración del token (según el catálogo) | No verificado; para PATs y Internal Connections parece ser indefinido; para OAuth se menciona refresh token pero sin especificar expiration del access token |
| Refresco (según el catálogo) | Sí, POST /v1/oauth2/token/refresh con grant_type="refresh_token" genera nuevo access y refresh token |
| Permisos (según el catálogo) | Capacidades: Read content (leer existente), Update content (actualizar), Insert content (crear), Read comments, Insert comments, User information (sin email, con email, o ninguna) |
| Restricciones de acceso | Integración debe ser compartida explícitamente en páginas por el usuario; sin revisión de la app mencionada; planes Business/Enterprise tienen rate limits más altos que otros |
| Límites de ritmo | 180 req/min (avg 3/seg) otros planes, 600 req/min (avg 10/seg) Business/Enterprise; 2000 caracteres texto/URLs, 200 email/teléfono, 100 max multi-select/related/people, 1000 bloques y 500KB payload máximo |
| Notas de esta app | El usuario debe compartir cada página con la integración; sin eso devuelve `not_found`. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/notion/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> notion`. | Cuenta con `provider: notion`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/notion.user.get_me/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> notion <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Notion. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/notion.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Users (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.user.get_me` ★ | read | GET /v1/users/me | Obtiene el usuario bot autenticado (whoami) | ninguno | bot_id, name, workspace_id, workspace_name | ninguno | — | — |
| [ ] | `notion.user.get` | read | GET /v1/users/{user_id} | Obtiene detalles de un usuario específico | user_id | id, name, avatar_url, email (si disponible), email_verified | ninguno | — | — |
| [ ] | `notion.user.list` | read | GET /v1/users | Lista todos los usuarios del workspace | ninguno | lista de {id, name, avatar_url, email}, has_more, next_cursor | ninguno | — | — |

### Pages (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.page.create` | create | POST /v1/pages | Crea una nueva página | parent, properties, icon, cover, children | page_id, title, created_time, last_edited_time, archived | Insert content | — | — |
| [ ] | `notion.page.get` | read | GET /v1/pages/{page_id} | Obtiene detalles y metadatos de una página | page_id | id, properties, icon, cover, created_time, last_edited_time, archived | Read content | — | — |
| [ ] | `notion.page.get_property` | read | GET /v1/pages/{page_id}/properties/{property_id} | Obtiene el valor de una propiedad específica de página | page_id, property_id | property_id, type, values (según tipo) | Read content | — | — |
| [ ] | `notion.page.update` | update | PATCH /v1/pages/{page_id} | Actualiza propiedades y metadatos de una página | page_id, properties, archived, icon, cover | id, updated_time, properties | Update content | — | — |
| [ ] | `notion.page.move` | update | PUT /v1/pages/{page_id} | Mueve una página a otro parent (cambiar ubicación en jerarquía) | page_id, parent | id, parent, last_edited_time | Update content | — | — |
| [ ] | `notion.page.archive` | delete | DELETE /v1/pages/{page_id} | Marca una página como archivada (movimiento a papelera) | page_id | id, archived=true | Update content | I | — |
| [ ] | `notion.page.get_markdown` | read | GET /v1/pages/{page_id}/markdown | Obtiene el contenido de una página en formato Markdown | page_id | markdown_content | Read content | — | — |
| [ ] | `notion.page.update_markdown` | update | PATCH /v1/pages/{page_id}/markdown | Actualiza el contenido de una página usando Markdown | page_id, markdown | id, updated_time | Update content | — | — |

### Blocks (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.block.get` | read | GET /v1/blocks/{block_id} | Obtiene detalles de un bloque | block_id | id, type, content_object, created_time, last_edited_time | Read content | — | — |
| [ ] | `notion.block.get_children` | read | GET /v1/blocks/{block_id}/children | Lista bloques hijos de un bloque padre (paginado) | block_id, page_size, start_cursor | lista de blocks, has_more, next_cursor | Read content | — | — |
| [ ] | `notion.block.create_child` | create | POST /v1/blocks/{block_id}/children | Añade bloques hijos a un bloque padre | block_id, children | results, next_cursor | Insert content | — | — |
| [ ] | `notion.block.update` | update | PATCH /v1/blocks/{block_id} | Actualiza propiedades de un bloque | block_id, type_specific_props | id, updated_time | Update content | — | — |
| [ ] | `notion.block.delete` | delete | DELETE /v1/blocks/{block_id} | Borra un bloque | block_id | confirmación | Update content | I | — |

### Databases (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.database.create` | create | POST /v1/databases | Crea una nueva base de datos | parent, properties, title, icon, cover | database_id, properties, title, created_time | Insert content | — | — |
| [ ] | `notion.database.get` | read | GET /v1/databases/{database_id} | Obtiene estructura y propiedades de una base de datos | database_id | id, title, properties (schema), created_time, last_edited_time | Read content | — | — |
| [ ] | `notion.database.update` | update | PATCH /v1/databases/{database_id} | Actualiza metadatos de la base de datos | database_id, title, icon, cover | id, updated_time | Update content | — | — |
| [ ] | `notion.database.query` | read | POST /v1/databases/{database_id}/query | Consulta registros de una base de datos con filtros y sort | database_id, filter, sorts, page_size, start_cursor | results (lista de pages), has_more, next_cursor | Read content | — | — |
| [ ] | `notion.database.update_properties` | update | POST /v1/databases/{database_id}/properties | Actualiza esquema de propiedades de la base de datos | database_id, properties | schema actualizado | Update content | — | — |

### Views (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.view.create` | create | POST /v1/databases/{database_id}/views | Crea una nueva vista (tabla, galería, kanban, calendario, etc.) | database_id, name, view_type, filter, sorts | view_id, name, type, created_time | Insert content | — | — |
| [ ] | `notion.view.get` | read | GET /v1/views/{view_id} | Obtiene configuración de una vista | view_id | id, name, type, filter, sorts, properties | Read content | — | — |
| [ ] | `notion.view.list` | read | GET /v1/databases/{database_id}/views | Lista todas las vistas de una base de datos | database_id, page_size, start_cursor | results (lista de views), has_more, next_cursor | Read content | — | — |
| [ ] | `notion.view.update` | update | PATCH /v1/views/{view_id} | Actualiza configuración de una vista | view_id, name, filter, sorts | id, updated_time | Update content | — | — |
| [ ] | `notion.view.delete` | delete | DELETE /v1/views/{view_id} | Borra una vista | view_id | confirmación | Update content | I | — |
| [ ] | `notion.view.query` | read | POST /v1/views/{view_id}/query | Ejecuta una consulta sobre una vista con cache | view_id, filter, sorts | results, query_id, has_more, next_cursor | Read content | — | — |
| [ ] | `notion.view.query_paginate` | read | GET /v1/views/{view_id}/query/{query_id} | Pagina a través de resultados de query en caché | view_id, query_id, page_size, start_cursor | results, has_more, next_cursor | Read content | — | — |
| [ ] | `notion.view.query_delete` | delete | DELETE /v1/views/{view_id}/query/{query_id} | Limpia caché de una query | view_id, query_id | confirmación | Update content | — | — |

### Comments (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.comment.create` | create | POST /v1/comments | Crea un comentario en una página o bloque | object (page_id o block_id), rich_text | comment_id, created_by, created_time, content | Insert comments | E | — |
| [ ] | `notion.comment.get` | read | GET /v1/comments/{comment_id} | Obtiene detalles de un comentario | comment_id | id, created_by, created_time, updated_time, content | Read comments | — | — |
| [ ] | `notion.comment.list` | read | GET /v1/blocks/{block_id}/comments | Lista comentarios de un bloque o página (paginado) | block_id, page_size, start_cursor | results (lista de comments), has_more, next_cursor | Read comments | — | — |
| [ ] | `notion.comment.update` | update | PATCH /v1/comments/{comment_id} | Actualiza contenido de un comentario | comment_id, rich_text | id, updated_time | Update content | — | — |
| [ ] | `notion.comment.delete` | delete | DELETE /v1/comments/{comment_id} | Borra un comentario | comment_id | confirmación | Update content | I | — |

### Files and Uploads (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.file.create_session` | create | POST /v1/files | Crea una sesión de carga de archivo para upload | file_name, file_size, mime_type | file_upload_id, upload_url, expiry_time | Insert content | — | — |
| [ ] | `notion.file.upload` | create | PUT /v1/files/{file_upload_id} | Envía contenido de archivo en partes o completo | file_upload_id, file_data, content_type | confirmación de bytes cargados | Insert content | — | — |
| [ ] | `notion.file.complete_upload` | create | POST /v1/files/{file_upload_id}/complete | Finaliza un upload multi-part | file_upload_id | file_url, file_size | Insert content | — | — |
| [ ] | `notion.file.get` | read | GET /v1/files/{file_upload_id} | Obtiene detalles y estado de una carga de archivo | file_upload_id | file_upload_id, file_name, size, upload_status | Read content | — | — |
| [ ] | `notion.file.list` | read | GET /v1/files | Lista archivos cargados recientemente en el workspace | page_size, start_cursor | results (lista de files), has_more, next_cursor | Read content | — | — |

### Data Sources (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.datasource.create` | create | POST /v1/data_sources | Crea una nueva fuente de datos | name, source_type, config | datasource_id, name, source_type, created_time | Insert content | — | — |
| [ ] | `notion.datasource.get` | read | GET /v1/data_sources/{data_source_id} | Obtiene configuración de una fuente de datos | data_source_id | id, name, source_type, config, created_time | Read content | — | — |
| [ ] | `notion.datasource.update` | update | PATCH /v1/data_sources/{data_source_id} | Actualiza configuración de una fuente de datos | data_source_id, name, config | id, updated_time | Update content | — | — |
| [ ] | `notion.datasource.query` | read | POST /v1/data_sources/{data_source_id}/query | Consulta una fuente de datos externa | data_source_id, query_params | results, metadata | Read content | — | — |
| [ ] | `notion.datasource.update_properties` | update | PATCH /v1/data_sources/{data_source_id}/properties | Actualiza propiedades/mapeo de una fuente de datos | data_source_id, properties | schema actualizado | Update content | — | — |
| [ ] | `notion.datasource.get_templates` | read | GET /v1/data_sources/{data_source_id}/templates | Lista plantillas disponibles para la fuente de datos | data_source_id, page_size, start_cursor | templates, has_more, next_cursor | Read content | — | — |

### Search (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.search.search` | read | POST /v1/search | Busca páginas y bases de datos en el workspace | query, sort, filter, page_size, start_cursor | results (lista de {id, type, title}), has_more, next_cursor | Read content | — | — |

### Meeting Notes (Avanzado) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.meeting.create` | create | POST /v1/meeting_notes | Crea notas de reunión con resumen por IA | recording_url, transcript_text, participants, title | meeting_id, summary, key_points, action_items, created_time | Insert content | E | — |
| [ ] | `notion.meeting.list` | read | GET /v1/meeting_notes | Lista notas de reuniones generadas | filter, page_size, start_cursor | results (lista de meetings), has_more, next_cursor | Read content | — | — |

### Agents (Avanzado) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.agent.list` | read | GET /v1/agents | Lista agentes Notion disponibles en el workspace | page_size, start_cursor | results (lista de agents), has_more, next_cursor | Read content | — | — |
| [ ] | `notion.agent.get` | read | GET /v1/agents/{agent_id} | Obtiene detalles de un agente Notion | agent_id | id, name, description, status, created_time | Read content | — | — |
| [ ] | `notion.agent.get_insights` | read | GET /v1/agents/{agent_id}/insights | Obtiene insights y métricas de un agente | agent_id | usage_stats, performance_metrics | Read content | — | — |
| [ ] | `notion.agent.update_status` | update | PATCH /v1/agents/{agent_id}/status | Habilita o deshabilita un agente | agent_id, enabled | id, status, updated_time | Update content | — | — |
| [ ] | `notion.agent.update_credit_limit` | update | PATCH /v1/agents/{agent_id}/credit_limit | Actualiza el límite de créditos de un agente | agent_id, credit_limit | id, credit_limit, updated_time | Update content | — | — |
| [ ] | `notion.agent.delete` | delete | DELETE /v1/agents/{agent_id} | Soft-delete de un agente (lo marca como borrado) | agent_id | confirmación | Update content | I | — |
| [ ] | `notion.agent.batch_manage` | create | POST /v1/agents/batch | Operación batch para gestionar múltiples agentes | operations (array de operaciones create/update/delete) | results (array con éxito/error por operación) | Update content | — | — |

### Sessions (Avanzado) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.session.create` | create | POST /v1/sessions | Crea o actualiza una sesión de agente, o envía mensaje | agent_id, session_data, message | session_id, status, response, created_time | Insert content | E | — |
| [ ] | `notion.session.get` | read | GET /v1/sessions/{session_id} | Obtiene estado y detalles de una sesión | session_id | id, status, agent_id, created_time, last_message_time | Read content | — | — |
| [ ] | `notion.session.list` | read | GET /v1/sessions | Lista sesiones en el workspace | filter, page_size, start_cursor | results (lista de sessions), has_more, next_cursor | Read content | — | — |
| [ ] | `notion.session.get_events` | read | GET /v1/sessions/{session_id}/events | Lista eventos de una sesión (mensaje, estado, etc.) | session_id, page_size, start_cursor | events (lista de {timestamp, type, data}), has_more, next_cursor | Read content | — | — |
| [ ] | `notion.session.cancel` | delete | DELETE /v1/sessions/{session_id} | Cancela una sesión activa | session_id | confirmación, session_id | Update content | I | — |

### Async Tasks (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `notion.async_task.get` | read | GET /v1/async_tasks/{async_task_id} | Obtiene el estado y resultado de una tarea asincrónica | async_task_id | task_id, status (processing/completed/failed), result, error | Read content | — | — |
