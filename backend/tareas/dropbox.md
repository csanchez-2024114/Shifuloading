# Tareas: Dropbox

- **Funciones catalogadas:** 127 · **Hechas:** 3 · **Pendientes:** 124 · **Herramientas viejas a migrar:** 11 (columna "Herramienta vieja")
- **Documentación oficial:** https://www.dropbox.com/developers/documentation/http/documentation
- **Fuentes que consultó el catálogo:** https://dropbox-sdk-python.readthedocs.io/en/latest/ https://github.com/dropbox/dropbox-api-spec https://www.dropbox.com/developers/documentation/http/documentation https://www.educative.io/courses/getting-started-with-dropbox-api-in-javascript/
- **Paginación típica:** Cursor-based con campos has_more (bool) y cursor (string); endpoints con /continue para obtener siguiente página
- **Qué no se pudo verificar:** Rate limits exactos por endpoint, scopes exactos por operación (algunos inferidos de fuentes educativas), deprecación completa de Paper endpoints
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/dropbox/` ([plantilla](../app/functions/apps/_template/README.md)) (**ya existe**).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `dropbox`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `dropbox` |
| Variables del `.env` que necesitas | DROPBOX_CLIENT_ID, DROPBOX_CLIENT_SECRET, DROPBOX_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/dropbox/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `dropbox.account.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización, access token, y refresh token de larga duración (sin expiración definida según algunos clientes) |
| Duración del token (según el catálogo) | Access token: 4 horas (típicamente); refresh token: no caduca (larga duración) |
| Refresco (según el catálogo) | Sí, con refresh token. Endpoint POST /oauth2/token con grant_type=refresh_token |
| Permisos (según el catálogo) | files.metadata.read (leer metadatos), files.content.read (descargar), files.content.write (subir/modificar), sharing.read (leer enlaces), sharing.write (crear enlaces), account_info.read (info de cuenta), team.info.read (info de equipo, solo empresa) |
| Restricciones de acceso | OAuth requiere developer app en Dropbox Console. Algunos endpoints (team, legal holds) solo para cuentas de empresa. Paper endpoints deprecated; usar files + sharing en su lugar. |
| Límites de ritmo | 300 requests/minuto por usuario (rate limit típico); upload/download sin límite específico documentado; batch operations máximo 25 items; search v2 máximo 1000 resultados por página |
| Notas de esta app | Ya hay 3 funciones nuevas (marca D) y su prueba en `test/functions/apps/test_dropbox.py`. Dropbox devuelve `missing_scope` como HTTP 401: está cubierto por `scope_error_marker`. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/dropbox/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> dropbox`. | Cuenta con `provider: dropbox`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/dropbox.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> dropbox <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Dropbox. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/dropbox.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Account (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [x] | `dropbox.account.get` ★ | read | POST /users/get_current_account | Obtiene información de la cuenta del usuario autenticado | — | account_id, name, email, email_verified, profile_photo_url, disabled | account_info.read | — | — |
| [ ] | `dropbox.account.get_space_usage` | read | POST /users/get_space_usage | Obtiene uso de espacio total y disponible de la cuenta | — | used, allocation (individual o team) | account_info.read | — | get_dropbox_space |
| [ ] | `dropbox.account.get_features` | read | POST /users/features_get_values_batch | Obtiene características habilitadas para la cuenta (Paper, file locking, team shared dropbox, etc.) | features_requested (list) | features activos y sus valores | account_info.read | — | — |
| [ ] | `dropbox.account.get_batch` | read | POST /users/get_account_batch | Obtiene información de múltiples cuentas por ID | account_ids (list, máximo sin límite especificado) | list de accounts | account_info.read | — | — |

### Files (39)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [x] | `dropbox.files.list` | read | POST /files/list_folder | Lista archivos y carpetas en una ruta, con recursión opcional | path, recursive, include_deleted, include_has_explicit_shared_members | entries (list de {name, path_lower, id, size, is_file, is_folder}), cursor, has_more | files.metadata.read | D | list_dropbox_files |
| [ ] | `dropbox.files.list_continue` | read | POST /files/list_folder/continue | Continúa listado de carpeta con cursor anterior | cursor | entries, cursor, has_more | files.metadata.read | — | — |
| [ ] | `dropbox.files.get_metadata` | read | POST /files/get_metadata | Obtiene metadatos de un archivo o carpeta (tamaño, fecha, etiquetas, etc.) | path, include_media_info, include_deleted, include_has_explicit_shared_members | id, name, path_lower, client_modified, server_modified, rev, size, media_info (video/photo), content_hash, is_symlink | files.metadata.read | — | get_dropbox_file_details |
| [x] | `dropbox.files.search` | read | POST /files/search_v2 | Busca archivos y carpetas por nombre y contenido con filtros avanzados | query, path, max_results, start, query_mode (filename, filename_and_content, deleted_filename), file_categories, file_extensions | matches (list de {metadata, match_type}), cursor, has_more | files.metadata.read | D | search_dropbox_folder_and_list_files |
| [ ] | `dropbox.files.search_v1` | read | POST /files/search | Búsqueda de archivos v1 (anterior a search_v2) | path, query, start, max_results, mode | matches, start | files.metadata.read | — | — |
| [ ] | `dropbox.files.upload` | create | POST /files/upload (content endpoint) | Sube un archivo nuevo o sobrescribe existente | path, mode (add/overwrite/update), autorename, client_modified, mute | metadata (id, name, path_lower, size, rev, content_hash) | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_start` | create | POST /files/upload_session/start (content endpoint) | Inicia sesión de carga para archivos grandes | upload_session_type (sequential/concurrent) | session_id | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_append` | create | POST /files/upload_session/append (content endpoint) | Agrega datos a una sesión de carga existente | session_id, offset | — | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_finish` | create | POST /files/upload_session/finish (content endpoint) | Finaliza sesión de carga y persiste el archivo | session_id, cursor, commit_info (path, mode, etc.) | metadata, cursor | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_start_batch` | create | POST /files/upload_session/start_batch | Inicia múltiples sesiones de carga simultáneamente | num_sessions, upload_session_type | session_ids (list) | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_append_batch` | create | POST /files/upload_session/append_batch | Agrega datos a múltiples sesiones | entries (session_id, offset, list de binarios) | — | files.content.write | — | — |
| [ ] | `dropbox.files.upload_session_finish_batch` | create | POST /files/upload_session/finish_batch | Finaliza múltiples sesiones de carga de forma asincrónica | entries (session_id, cursor, commit_info) | entries, job_status (complete/failed) | files.content.write | — | — |
| [ ] | `dropbox.files.download` | read | POST /files/download (content endpoint) | Descarga contenido de un archivo | path, rev | archivo binario en respuesta, metadatos en header Dropbox-API-Result | files.content.read | — | — |
| [ ] | `dropbox.files.download_zip` | read | POST /files/download_zip (content endpoint) | Descarga una carpeta empaquetada como ZIP | path | archivo ZIP | files.content.read | — | — |
| [ ] | `dropbox.files.export` | read | POST /files/export (content endpoint) | Exporta archivo en formato específico (HTML, markdown, JSON para Paper docs) | path, export_format (HTML/Markdown/JSON) | archivo en formato solicitado | files.content.read | — | — |
| [ ] | `dropbox.files.create_folder` | create | POST /files/create_folder | Crea una nueva carpeta | path, autorename | metadata (id, name, path_lower) | files.content.write | — | create_dropbox_folder |
| [ ] | `dropbox.files.create_folder_batch` | create | POST /files/create_folder_batch | Crea múltiples carpetas de forma asincrónica | paths (list) | job_status, entries | files.content.write | — | — |
| [ ] | `dropbox.files.move` | update | POST /files/move | Mueve o renombra archivo/carpeta | from_path, to_path, autorename, allow_ownership_transfer | metadata (nuevo path, id, etc.) | files.content.write | — | move_dropbox_file |
| [ ] | `dropbox.files.move_batch` | update | POST /files/move_batch | Mueve múltiples archivos/carpetas de forma asincrónica | entries (from_path, to_path, autorename, allow_ownership_transfer) | job_status | files.content.write | — | — |
| [ ] | `dropbox.files.copy` | create | POST /files/copy | Copia archivo o carpeta (sin contenido recursivo) | from_path, to_path, autorename | metadata | files.content.write | — | copy_dropbox_file |
| [ ] | `dropbox.files.copy_batch` | create | POST /files/copy_batch | Copia múltiples archivos/carpetas de forma asincrónica | entries (from_path, to_path, autorename) | job_status | files.content.write | — | — |
| [ ] | `dropbox.files.delete` | delete | POST /files/delete_v2 | Elimina archivo o carpeta (y contenido recursivamente) | path, parent_rev | metadata (con deleted=true) | files.content.write | I | delete_dropbox_item |
| [ ] | `dropbox.files.delete_batch` | delete | POST /files/delete_batch | Elimina múltiples archivos/carpetas de forma asincrónica | entries (path, parent_rev) | job_status, entries (deleted) | files.content.write | I | — |
| [ ] | `dropbox.files.get_copy_reference` | read | POST /files/get_copy_reference | Genera referencia de copia para archivo/carpeta (reutilizable después) | path | copy_reference (string), metadata | files.metadata.read | — | — |
| [ ] | `dropbox.files.save_copy_reference` | create | POST /files/save_copy_reference | Guarda/restaura un archivo desde una referencia de copia anterior | copy_reference, path | metadata | files.content.write | — | — |
| [ ] | `dropbox.files.save_url` | create | POST /files/save_url | Descarga archivo de URL externa y lo guarda en Dropbox | path, url, autorename | metadata | files.content.write | E | — |
| [ ] | `dropbox.files.get_temporary_link` | read | POST /files/get_temporary_link | Genera enlace temporal (4 horas) para descargar archivo sin autenticación | path | link (URL temporal) | files.content.read | — | — |
| [ ] | `dropbox.files.list_revisions` | read | POST /files/list_revisions | Lista todas las revisiones de un archivo (historial de versiones) | path, limit, mode (all/deleted_only) | is_deleted, entries (list de revisiones con rev, size, server_modified) | files.metadata.read | — | get_dropbox_versions |
| [ ] | `dropbox.files.restore` | update | POST /files/restore | Restaura un archivo a una revisión anterior | path, rev | metadata | files.content.write | — | — |
| [ ] | `dropbox.files.get_thumbnail` | read | POST /files/get_thumbnail (content endpoint) | Genera y descarga miniatura de imagen/video | path, format (jpeg/png/webp), size (32x32 a 2048x1536), mode (strict/bestfit/fitone_bestfit/original) | imagen miniatura | files.content.read | — | — |
| [ ] | `dropbox.files.get_thumbnail_batch` | read | POST /files/get_thumbnail_batch (content endpoint) | Genera miniaturas para múltiples archivos | entries (path, format, size, mode) | entries (thumbnail base64, metadata) | files.content.read | — | — |
| [ ] | `dropbox.files.add_tag` | create | POST /files/tags/add | Agrega etiqueta (tag) personalizada a archivo/carpeta | path, tag_text | — | files.content.write | — | — |
| [ ] | `dropbox.files.remove_tag` | delete | POST /files/tags/remove | Elimina etiqueta de archivo/carpeta | path, tag_text | — | files.content.write | — | — |
| [ ] | `dropbox.files.get_tags` | read | POST /files/tags/get | Obtiene todas las etiquetas de un archivo/carpeta | path | tags (list de {tag_text, added_by, added_at}) | files.metadata.read | — | — |
| [ ] | `dropbox.files.get_content_sync_setting` | read | POST /files/get_content_sync_setting | Obtiene configuración de sincronización de archivo/carpeta (si está en sincronización selectiva) | path | setting (synced/not_synced), tag | files.metadata.read | — | — |
| [ ] | `dropbox.files.lock_file` | create | POST /files/lock_file | Bloquea archivo para prevenir modificaciones concurrentes | path, lock_type (app_specific) | lock_metadata (lock_holder_account_id, lock_holder_name, created_at) | files.content.write | — | — |
| [ ] | `dropbox.files.lock_file_batch` | create | POST /files/lock_file_batch | Bloquea múltiples archivos de forma asincrónica | entries (path, lock_type) | job_status | files.content.write | — | — |
| [ ] | `dropbox.files.unlock_file` | update | POST /files/unlock_file | Desbloquea archivo | path | — | files.content.write | — | — |
| [ ] | `dropbox.files.unlock_file_batch` | update | POST /files/unlock_file_batch | Desbloquea múltiples archivos de forma asincrónica | entries (path) | job_status | files.content.write | — | — |

### Sharing (26)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `dropbox.sharing.create_shared_link` | create | POST /sharing/create_shared_link | Crea enlace compartido para archivo/carpeta | path, short_url | url (enlace público) | sharing.write | E | get_dropbox_shared_links |
| [ ] | `dropbox.sharing.create_shared_link_with_settings` | create | POST /sharing/create_shared_link_with_settings | Crea enlace compartido con configuración avanzada (expiración, contraseña, permisos) | path, requested_visibility (public/password/team_only), link_password, expires, requested_access_level (viewer/editor) | url, name, path_lower, expires, link_permissions (requested_visibility, resolved_visibility, can_revoke) | sharing.write | E | — |
| [ ] | `dropbox.sharing.list_shared_links` | read | POST /sharing/list_shared_links | Lista enlaces compartidos existentes de usuario | path, cursor | links (list de {url, name, expires, link_permissions, created}), cursor, has_more | sharing.read | — | get_dropbox_shared_links |
| [ ] | `dropbox.sharing.list_shared_links_continue` | read | POST /sharing/list_shared_links/continue | Continúa listado de enlaces compartidos | cursor | links, cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.get_shared_link_metadata` | read | POST /sharing/get_shared_link_metadata | Obtiene metadatos de enlace compartido específico | url | url, name, path_lower, expires, link_permissions, created, access | sharing.read | — | — |
| [ ] | `dropbox.sharing.update_shared_link_settings` | update | POST /sharing/update_shared_link_settings | Actualiza configuración de enlace (expiración, contraseña, visibilidad, acceso) | url, settings (link_password, expires, requested_access_level, requested_visibility) | url, name, expires, link_permissions, created, access | sharing.write | — | — |
| [ ] | `dropbox.sharing.remove_shared_link` | delete | POST /sharing/remove_shared_link | Revoca enlace compartido | url | — | sharing.write | I | — |
| [ ] | `dropbox.sharing.add_file_member` | create | POST /sharing/add_file_member | Agrega miembro a archivo compartido (requiere crear enlace primero) | file, members (list de {email/dropbox_id}, access_level) | — | sharing.write | E | — |
| [ ] | `dropbox.sharing.remove_file_member` | delete | POST /sharing/remove_file_member | Elimina miembro de archivo compartido | file, member | — | sharing.write | I | — |
| [ ] | `dropbox.sharing.list_file_members` | read | POST /sharing/list_file_members | Lista miembros que tienen acceso a archivo | file, actions, include_inherited, limit | users (list de {account_id, email, display_name, access_type}), cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.list_file_members_continue` | read | POST /sharing/list_file_members/continue | Continúa listado de miembros del archivo | cursor | users, cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.change_file_member_access` | update | POST /sharing/change_file_member_access | Cambia nivel de acceso de miembro del archivo | file, member, new_member_access_level (viewer/editor/owner) | — | sharing.write | — | — |
| [ ] | `dropbox.sharing.add_folder_member` | create | POST /sharing/add_folder_member | Agrega miembro a carpeta compartida (envía invitación) | shared_folder_id, members (list de {email/dropbox_id}, access_level), quiet_mode | — | sharing.write | E | — |
| [ ] | `dropbox.sharing.update_folder_member` | update | POST /sharing/update_folder_member | Actualiza permiso de miembro en carpeta compartida | shared_folder_id, member, new_access_level (viewer/editor/owner) | — | sharing.write | — | — |
| [ ] | `dropbox.sharing.remove_folder_member` | delete | POST /sharing/remove_folder_member | Elimina miembro de carpeta compartida | shared_folder_id, member, leave_a_copy | job_status | sharing.write | I | — |
| [ ] | `dropbox.sharing.list_folder_members` | read | POST /sharing/list_folder_members | Lista miembros de carpeta compartida | shared_folder_id, actions, limit | users (list de {email, account_id, access_type, is_owner, same_team}), cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.list_folder_members_continue` | read | POST /sharing/list_folder_members/continue | Continúa listado de miembros de carpeta | cursor | users, cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.get_folder_metadata` | read | POST /sharing/get_folder_metadata | Obtiene metadatos de carpeta compartida (access, policy, members) | shared_folder_id, actions | shared_folder_id, name, path_lower, access_type, owner, members, team_id, policy (member_policy, acl_update_policy, shared_link_policy) | sharing.read | — | — |
| [ ] | `dropbox.sharing.update_folder_policy` | update | POST /sharing/update_folder_policy | Actualiza política de carpeta (quién puede agregar miembros, crear enlaces, etc.) | shared_folder_id, member_policy, acl_update_policy, shared_link_policy, force_async | job_status | sharing.write | — | — |
| [ ] | `dropbox.sharing.list_folders` | read | POST /sharing/list_folders | Lista carpetas compartidas accesibles por usuario | limit, actions | entries (list de shared_folder_metadata), cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.list_folders_continue` | read | POST /sharing/list_folders/continue | Continúa listado de carpetas compartidas | cursor | entries, cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.sharing.get_folder_by_shared_folder_id` | read | POST /sharing/get_folder_by_shared_folder_id | Obtiene información de carpeta compartida por su ID | shared_folder_id, actions | shared_folder_metadata | sharing.read | — | — |
| [ ] | `dropbox.sharing.mount_folder` | create | POST /sharing/mount_folder | Monta carpeta compartida (la hace visible en el namespace del usuario) | shared_folder_id | metadata (shared_folder_id, name, path_lower) | sharing.write | — | — |
| [ ] | `dropbox.sharing.unmount_folder` | delete | POST /sharing/unmount_folder | Desmonta carpeta compartida del namespace | shared_folder_id | — | sharing.write | — | — |
| [ ] | `dropbox.sharing.relinquish_folder_membership` | delete | POST /sharing/relinquish_folder_membership | Sale de carpeta compartida | shared_folder_id | — | sharing.write | — | — |
| [ ] | `dropbox.sharing.check_share_compliance` | read | POST /sharing/check_share_compliance | Verifica si contenido puede ser compartido según políticas de equipo (enterprise) | path_or_id, team_member_id | result (compliant, non_compliant_shared_uris) | sharing.read | — | — |

### File Requests (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `dropbox.file_requests.create` | create | POST /file_requests/create | Crea solicitud de archivo para recibir uploads de otros | title, destination, deadline, open, description, video_project_id | file_request_id, title, destination, deadline, open, created, updated, url | files.content.write | E | — |
| [ ] | `dropbox.file_requests.get` | read | POST /file_requests/get | Obtiene detalles de solicitud de archivo por ID | id | id, title, destination, deadline, open, created, updated, url | files.metadata.read | — | — |
| [ ] | `dropbox.file_requests.list` | read | POST /file_requests/list | Lista todas las solicitudes de archivo del usuario | limit | entries (list de solicitudes), cursor | files.metadata.read | — | — |
| [ ] | `dropbox.file_requests.list_continue` | read | POST /file_requests/list/continue | Continúa listado de solicitudes de archivo | cursor | entries, cursor | files.metadata.read | — | — |
| [ ] | `dropbox.file_requests.update` | update | POST /file_requests/update | Actualiza solicitud (título, descripción, deadline, estado abierto/cerrado) | id, title, destination, deadline, open, description, video_project_id | file_request_id, title, destination, deadline, open, created, updated, url | files.content.write | — | — |
| [ ] | `dropbox.file_requests.delete` | delete | POST /file_requests/delete | Elimina solicitud de archivo | ids (list) | — | files.content.write | I | — |
| [ ] | `dropbox.file_requests.delete_all_closed` | delete | POST /file_requests/delete_all_closed | Elimina todas las solicitudes cerradas del usuario | — | file_request_ids (list de eliminadas) | files.content.write | I | — |
| [ ] | `dropbox.file_requests.count` | read | POST /file_requests/count | Obtiene cantidad total de solicitudes de archivo del usuario | — | count | files.metadata.read | — | — |

### Paper (Deprecated) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `dropbox.paper.create` | create | POST /paper/docs/create | Crea documento Dropbox Paper (deprecated: usar /files + /sharing) | import_format (markdown/html/plain_text), parent_folder_id, data (contenido) | doc_id, folder_id, revision | files.content.write | — | create_dropbox_paper_doc |
| [ ] | `dropbox.paper.update` | update | POST /paper/docs/update | Actualiza contenido de documento Paper | doc_id, revision, doc_update_policy (append/prepend/overwrite), data | doc_id, revision | files.content.write | — | — |
| [ ] | `dropbox.paper.get_metadata` | read | POST /paper/docs/get_metadata | Obtiene metadatos de documento Paper | doc_id, file_id | doc_id, title, revision, mime_type, created_at, last_updated_at, status, owner, is_archived, folder_name | files.metadata.read | — | — |
| [ ] | `dropbox.paper.export` | read | POST /paper/docs/download (content endpoint) | Exporta documento Paper en formato especificado | doc_id, export_format (html/markdown) | documento en formato solicitado | files.content.read | — | — |
| [ ] | `dropbox.paper.list` | read | POST /paper/docs/list | Lista documentos Paper | folder_id, sort_by, sort_order, limit, filter_by (active/archived/deleted) | doc_ids (list), cursor, has_more | files.metadata.read | — | — |
| [ ] | `dropbox.paper.list_continue` | read | POST /paper/docs/list/continue | Continúa listado de documentos Paper | cursor | doc_ids, cursor, has_more | files.metadata.read | — | — |
| [ ] | `dropbox.paper.add_member` | create | POST /paper/docs/sharing_policy/users/add | Agrega usuario colaborador a documento Paper | doc_id, members (list de {email/dropbox_id}, permission_level) | — | sharing.write | E | — |
| [ ] | `dropbox.paper.remove_member` | delete | POST /paper/docs/sharing_policy/users/remove | Elimina colaborador de documento Paper | doc_id, member | — | sharing.write | I | — |
| [ ] | `dropbox.paper.list_members` | read | POST /paper/docs/sharing_policy/users/list | Lista colaboradores de documento Paper | doc_id, limit | users (list de {email, account_id, permission_level}), cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.paper.list_members_continue` | read | POST /paper/docs/sharing_policy/users/list/continue | Continúa listado de colaboradores | cursor | users, cursor, has_more | sharing.read | — | — |
| [ ] | `dropbox.paper.create_folder` | create | POST /paper/folders/create | Crea carpeta en Dropbox Paper (deprecated) | name, is_private | folder_id, name, is_private, created_at | files.content.write | — | — |
| [ ] | `dropbox.paper.list_folder_members` | read | POST /paper/folders/users/list | Lista usuarios en carpeta Paper | folder_id, limit | users (list), cursor, has_more | sharing.read | — | — |

### Team (Enterprise) (37)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `dropbox.team.members_list` | read | POST /team/members/list | Lista miembros del equipo | limit, include_removed | members (list de {profile, role, status}), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.members_list_continue` | read | POST /team/members/list/continue | Continúa listado de miembros | cursor | members, cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.members_get_info` | read | POST /team/members/get_info | Obtiene información de miembros específicos | user_ids (list) | members_info (list de {team_member_id, profile, role}), user_count, error_count | team.info.read | — | — |
| [ ] | `dropbox.team.members_set_admin_permissions` | update | POST /team/members/set_admin_permissions | Asigna rol administrativo a miembro | user, new_admin_role (team_admin/user_management_admin/support_admin/member_only) | profile, role | team.info.write | — | — |
| [ ] | `dropbox.team.members_add_secondary_email` | create | POST /team/members/secondary_emails/add | Agrega correo secundario a miembro del equipo | user, secondary_email | — | team.info.write | — | — |
| [ ] | `dropbox.team.members_remove_secondary_email` | delete | POST /team/members/secondary_emails/remove | Elimina correo secundario de miembro | user, secondary_email | — | team.info.write | — | — |
| [ ] | `dropbox.team.members_get_secondary_emails` | read | POST /team/members/secondary_emails/get | Obtiene correos secundarios de miembro | user | secondary_emails (list) | team.info.read | — | — |
| [ ] | `dropbox.team.members_set_custom_quota` | update | POST /team/members/set_custom_quota | Establece cuota de almacenamiento personalizado para miembro | user, quota_gb | — | team.info.write | — | — |
| [ ] | `dropbox.team.members_get_custom_quota` | read | POST /team/members/get_custom_quota | Obtiene cuota personalizada de miembro | user | quota_gb (opcional) | team.info.read | — | — |
| [ ] | `dropbox.team.members_remove_custom_quota` | delete | POST /team/members/remove_custom_quota | Elimina cuota personalizado de miembro (vuelve a cuota global) | user | — | team.info.write | — | — |
| [ ] | `dropbox.team.groups_create` | create | POST /team/groups/create | Crea grupo en equipo | group_name, group_external_id, management_type (user_managed/company_managed) | group_id, group_name, group_management_type, created, member_count, external_id | team.info.write | — | — |
| [ ] | `dropbox.team.groups_delete` | delete | POST /team/groups/delete | Elimina grupo del equipo | group_id | group_id, async_job_id | team.info.write | I | — |
| [ ] | `dropbox.team.groups_list` | read | POST /team/groups/list | Lista grupos del equipo | limit | groups (list), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.groups_list_continue` | read | POST /team/groups/list/continue | Continúa listado de grupos | cursor | groups, cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.groups_get_info` | read | POST /team/groups/get_info | Obtiene información de grupo específico | group_ids (list) | groups (list de {group_id, group_name, group_external_id, member_count}), user_count, error_count | team.info.read | — | — |
| [ ] | `dropbox.team.groups_members_add` | create | POST /team/groups/members/add | Agrega miembro a grupo | group_id, members (list de {user, access_type}) | — | team.info.write | E | — |
| [ ] | `dropbox.team.groups_members_remove` | delete | POST /team/groups/members/remove | Elimina miembro de grupo | group_id, user | — | team.info.write | — | — |
| [ ] | `dropbox.team.groups_members_list` | read | POST /team/groups/members/list | Lista miembros de grupo | group_id, limit | members (list de {profile, access_type}), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.groups_members_list_continue` | read | POST /team/groups/members/list/continue | Continúa listado de miembros de grupo | cursor | members, cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.groups_members_set_access_type` | update | POST /team/groups/members/set_access_type | Cambia tipo de acceso de miembro en grupo | group_id, user, access_type (member/owner) | — | team.info.write | — | — |
| [ ] | `dropbox.team.linked_apps_list` | read | POST /team/linked_apps/list | Lista aplicaciones de terceros vinculadas por miembro | team_member_id, cursor | linked_apps (list), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.linked_apps_list_members_linked_apps` | read | POST /team/linked_apps/list_members_linked_apps | Lista aplicaciones vinculadas de múltiples miembros | team_member_ids (list) | member_linked_apps (list) | team.info.read | — | — |
| [ ] | `dropbox.team.devices_list` | read | POST /team/devices/list | Lista dispositivos activos del equipo | team_member_id, cursor, include_web_sessions, include_desktop_clients, include_mobile_clients | devices (list), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.devices_list_continue` | read | POST /team/devices/list/continue | Continúa listado de dispositivos | cursor | devices, cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.devices_revoke` | delete | POST /team/devices/revoke | Revoca sesión/dispositivo activo de miembro | device_id, team_member_id, keep_account | — | team.info.write | I | — |
| [ ] | `dropbox.team.devices_revoke_batch` | delete | POST /team/devices/revoke_batch | Revoca múltiples dispositivos/sesiones | entries (device_id, team_member_id, keep_account) | entries (error/success) | team.info.write | I | — |
| [ ] | `dropbox.team.activity_get_events` | read | POST /team_log/get_events | Obtiene eventos de actividad del equipo (auditoría) | limit, cursor | events (list de {timestamp, event_type, event_category, user, details}), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.activity_get_events_continue` | read | POST /team_log/get_events/continue | Continúa listado de eventos de actividad | cursor | events, cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.reports_get_membership` | read | POST /team_log/get_membership | Obtiene reporte de membresía del equipo (agrégated) | — | member_counts (active, invitations, suspended, removed) | team.info.read | — | — |
| [ ] | `dropbox.team.reports_get_device_security` | read | POST /team_log/get_device_security | Obtiene reporte de seguridad de dispositivos (tipos activos, SO) | — | active_windows, active_macos, active_linux, active_ios, active_android, active_web_sessions | team.info.read | — | — |
| [ ] | `dropbox.team.reports_get_storage` | read | POST /team_log/get_storage | Obtiene reporte de almacenamiento del equipo (uso agregado) | — | total_usage, by_category (file, user_shared_dropbox, team_shared_dropbox) | team.info.read | — | — |
| [ ] | `dropbox.team.legal_holds_create_policy` | create | POST /team_log/legal_holds/create_policy | Crea política de retención legal (hold) para datos del equipo (enterprise) | display_name, description | legal_hold_id, display_name, status (new/activating/active/releasing/released) | team.info.write | — | — |
| [ ] | `dropbox.team.legal_holds_list_policies` | read | POST /team_log/legal_holds/list_policies | Lista políticas de retención legal del equipo | — | policies (list de {id, display_name, status, created_at, updated_at}), cursor, has_more | team.info.read | — | — |
| [ ] | `dropbox.team.legal_holds_get_policy` | read | POST /team_log/legal_holds/get_policy | Obtiene detalles de política de retención legal | id | id, display_name, description, status, created_at, updated_at, members | team.info.read | — | — |
| [ ] | `dropbox.team.legal_holds_update_policy` | update | POST /team_log/legal_holds/update_policy | Actualiza política de retención legal | id, display_name, description | id, status, created_at, updated_at | team.info.write | — | — |
| [ ] | `dropbox.team.legal_holds_release_policy` | delete | POST /team_log/legal_holds/release_policy | Libera (cierra) política de retención legal | id | id, status (releasing) | team.info.write | I | — |
| [ ] | `dropbox.team.legal_holds_list_held_revisions` | read | POST /team_log/legal_holds/list_held_revisions | Lista revisiones de archivo retenidas por política de legal hold | id, cursor | entries (list de revisiones), cursor, has_more | team.info.read | — | — |

### Contacts (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `dropbox.contacts.delete_manual_contacts` | delete | POST /contacts/delete_manual_contacts | Elimina contactos añadidos manualmente de la lista de contactos | email_addresses (list) | — | — | I | — |

## Observaciones de las herramientas viejas

- Hecho en el sistema nuevo: `dropbox.account.get` (es el `whoami`, no equivale a ninguna herramienta vieja), `dropbox.files.list` y `dropbox.files.search`.
- `search_dropbox_folder_and_list_files` hace dos cosas (buscar carpeta y listar con enlaces temporales): separar en `files.search` (hecha) y una funcion de enlace temporal.
- `get_dropbox_space` puede no estar cubierta por `dropbox.account.get`: verificar si esa funcion devuelve el uso de espacio; si no, es una funcion aparte.
- `delete_dropbox_item` y `move_dropbox_file`: pregunta antes (`delete` y movimientos que cambian rutas que otros usan).
- No verificado contra la API real: scope de `list_folder` y la etiqueta `.tag` (ver `doc/funciones/README.md`).
