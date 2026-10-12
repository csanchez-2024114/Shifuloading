# Tareas: Slack

- **Funciones catalogadas:** 282 · **Hechas:** 0 · **Pendientes:** 282 · App sin herramientas viejas
- **Documentación oficial:** https://docs.slack.dev/apis/web-api
- **Fuentes que consultó el catálogo:** https://docs.slack.dev/reference/methods https://docs.slack.dev/apis/web-api https://api.slack.com/authentication/token-types https://docs.slack.dev/reference/methods/oauth.v2.access.md
- **Paginación típica:** cursor-based (limit, cursor, next_cursor); algunos métodos usan offset (deprecated)
- **Qué no se pudo verificar:** endpoints exactos para GraphQL (si existen), límites específicos por plan de workspace, scopes no documentados en detalle para cada método
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/slack/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `slack`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `slack` |
| Variables del `.env` que necesitas | SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/slack/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `slack.auth.test` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con authorization code: usuario autoriza app, se redirige a callback con código, app canjea código por access_token (xoxb- para bot) + refresh_token + user_token (xoxp-) |
| Duración del token (según el catálogo) | Access tokens sin expiración explícita (o 12 horas en implementaciones con refresh); refresh tokens duran 12 meses |
| Refresco (según el catálogo) | Sí; POST oauth.v2.access con refresh_token devuelve nuevo access_token |
| Permisos (según el catálogo) | Scopes por grupo de operaciones (chat:write para postMessage, reactions:write para reactions.add, etc.); se solicitan en OAuth y se validan por token |
| Restricciones de acceso | App requiere instalación en workspace y permisos aprobados; token revocable en cualquier momento; algunos métodos admin requieren admin/propietario de workspace |
| Límites de ritmo | 20 requests por segundo promedio, picos hasta 50/seg; buckets por método; rate limits en headers X-Rate-Limit-* |
| Notas de esta app | Token de bot (`xoxb-`); algunas operaciones exigen token de usuario. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/slack/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> slack`. | Cuenta con `provider: slack`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/slack.auth.test/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> slack <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Slack. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/slack.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Authentication (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.auth.test` ★ | read | POST /auth.test | Verifica credenciales de token e identidad del usuario conectado | — | {user_id, team_id, team_name, user} | — | — | — |
| [ ] | `slack.auth.revoke` | delete | POST /auth.revoke | Revoca un token de acceso invalidándolo | token | {revoked} | — | — | — |
| [ ] | `slack.auth_teams.list` | read | POST /auth.teams.list | Lista todos los workspaces en los que la app está instalada | — | {teams} | — | — | — |

### OAuth (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.oauth.access` | create | POST /oauth.v2.access | Canjea código de autorización por access_token y refresh_token | code, client_id, client_secret | {access_token, token_type, scope, bot_user_id, app_id, team, authed_user} | — | I | — |
| [ ] | `slack.oauth.v2_access` | create | POST /oauth.v2.access | Versión 2 de canje OAuth: intercambia código por token expirable | code, client_id, client_secret | {access_token, refresh_token, expires_in, token_type, scope, ...} | — | I | — |
| [ ] | `slack.oauth.v2_user_access` | create | POST /oauth.v2.user.access | Obtiene token de usuario específico en OAuth 2 flow | code, client_id, client_secret | {access_token, token_type, scope, user_id} | — | I | — |
| [ ] | `slack.oauth.v2_exchange` | create | POST /oauth.v2.exchange | Convierte token de acceso heredado a nuevo token expirable | client_id, client_secret, token | {access_token, refresh_token, expires_in} | — | — | — |
| [ ] | `slack.oauth.v2_begin_token_rotation` | create | POST /oauth.v2.beginShortTokenRotation | Inicia rotación de secreto en tokens API heredados | token | {rotation_token_expires_at} | — | I | — |
| [ ] | `slack.oauth.v2_complete_token_rotation` | create | POST /oauth.v2.completeShortTokenRotation | Completa rotación de secreto en tokens API heredados | token, rotation_token | {access_token} | — | I | — |
| [ ] | `slack.openid_connect.token` | create | POST /openid.connect.token | Canjea código OAuth de Sign in with Slack por token OpenID | code, client_id, client_secret | {access_token, id_token, token_type} | — | — | — |
| [ ] | `slack.openid_connect.userinfo` | read | GET /openid.connect.userInfo | Obtiene identidad de usuario de token Sign in with Slack | access_token | {sub, user_id, email, name, picture} | — | — | — |

### Conversations (Channels & Direct Messages) (29)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.conversations.list` | read | POST /conversations.list | Lista todos los canales, DMs y grupo DMs en el workspace | limit, cursor, types, exclude_archived | {channels, response_metadata} | conversations:read | — | — |
| [ ] | `slack.conversations.get_info` | read | POST /conversations.info | Obtiene detalles de un canal o DM (topic, purpose, members, etc.) | channel | {channel} | conversations:read | — | — |
| [ ] | `slack.conversations.create` | create | POST /conversations.create | Crea un nuevo canal público o privado | name, is_private, team_id | {channel} | conversations:manage | E | — |
| [ ] | `slack.conversations.delete` | delete | POST /conversations.delete | Elimina un canal | channel | {ok} | conversations:manage | I | — |
| [ ] | `slack.conversations.rename` | update | POST /conversations.rename | Renombra un canal | channel, name | {channel} | conversations:manage | — | — |
| [ ] | `slack.conversations.set_purpose` | update | POST /conversations.setPurpose | Establece la descripción de un canal | channel, purpose | {channel} | conversations:manage | — | — |
| [ ] | `slack.conversations.set_topic` | update | POST /conversations.setTopic | Establece el tema/asunto de un canal | channel, topic | {channel} | conversations:manage | — | — |
| [ ] | `slack.conversations.archive` | update | POST /conversations.archive | Archiva un canal (no se borra, solo oculta) | channel | {ok} | conversations:manage | — | — |
| [ ] | `slack.conversations.unarchive` | update | POST /conversations.unarchive | Desarchiva un canal | channel | {ok} | conversations:manage | — | — |
| [ ] | `slack.conversations.invite` | create | POST /conversations.invite | Invita usuarios a un canal | channel, users | {channel} | conversations:manage | E | — |
| [ ] | `slack.conversations.kick` | delete | POST /conversations.kick | Expulsa un usuario de un canal | channel, user | {ok} | conversations:manage | E | — |
| [ ] | `slack.conversations.leave` | update | POST /conversations.leave | El usuario autenticado se sale de un canal | channel | {not_in_channel, ok} | conversations:write | — | — |
| [ ] | `slack.conversations.join` | create | POST /conversations.join | El usuario autenticado se une a un canal | channel | {channel} | conversations:write | E | — |
| [ ] | `slack.conversations.open` | create | POST /conversations.open | Abre o retoma un DM o grupo DM | users, channel, prevent_creation | {channel} | conversations:write | E | — |
| [ ] | `slack.conversations.close` | update | POST /conversations.close | Cierra un DM o grupo DM | channel | {no_error, not_open} | conversations:write | — | — |
| [ ] | `slack.conversations.mark` | update | POST /conversations.mark | Establece el cursor de lectura en un canal | channel, ts | {ok} | conversations:write | — | — |
| [ ] | `slack.conversations.history` | read | POST /conversations.history | Obtiene el historial de mensajes de un canal | channel, latest, oldest, limit, cursor, inclusive | {messages, has_more, pin_count, response_metadata} | conversations:history | — | — |
| [ ] | `slack.conversations.replies` | read | POST /conversations.replies | Obtiene los mensajes en un hilo de un canal | channel, ts, limit, cursor | {messages, has_more, response_metadata} | conversations:history | — | — |
| [ ] | `slack.conversations.members` | read | POST /conversations.members | Lista los miembros de un canal | channel, limit, cursor | {members, response_metadata} | conversations:read | — | — |
| [ ] | `slack.conversations.invite_shared` | create | POST /conversations.inviteShared | Envía invitación de canal compartido (Slack Connect) | channel, emails | {invite_id} | conversations:manage | E | — |
| [ ] | `slack.conversations.accept_shared_invite` | create | POST /conversations.acceptSharedInvite | Acepta una invitación de canal compartido (Slack Connect) | invite_id, team_id | {channel} | conversations:manage | E | — |
| [ ] | `slack.conversations.decline_shared_invite` | update | POST /conversations.declineSharedInvite | Rechaza una invitación de canal compartido | invite_id, team_id | {ok} | conversations:manage | — | — |
| [ ] | `slack.conversations.approve_shared_invite` | create | POST /conversations.approveSharedInvite | Aprueba una invitación de canal compartido (solo admins) | invite_id, team_id | {approved_by, invite_id} | conversations:manage,admin | E | — |
| [ ] | `slack.conversations.list_connect_invites` | read | POST /conversations.listConnectInvites | Lista invitaciones pendientes de canal compartido | team_id, limit, cursor | {invites, response_metadata} | conversations:read | — | — |
| [ ] | `slack.conversations.request_shared_invite_approve` | create | POST /conversations.requestSharedInvite.approve | Aprueba solicitud de usuario externo para acceso a canal | request_id, team_id | {ok} | conversations:manage,admin | E | — |
| [ ] | `slack.conversations.request_shared_invite_deny` | update | POST /conversations.requestSharedInvite.deny | Rechaza solicitud de usuario externo para acceso a canal | request_id, team_id | {ok} | conversations:manage | — | — |
| [ ] | `slack.conversations.request_shared_invite_list` | read | POST /conversations.requestSharedInvite.list | Lista solicitudes de usuarios externos para acceso a canales | team_id, limit, cursor | {requests, response_metadata} | conversations:read | — | — |
| [ ] | `slack.conversations.external_invite_permissions_set` | update | POST /conversations.externalInvitePermissions.set | Modifica permisos para invitar usuarios externos al canal | channel, level | {channel} | conversations:manage | — | — |
| [ ] | `slack.conversations.canvas_create` | create | POST /conversations.canvases.create | Crea un lienzo de canal | channel, document_content | {canvas_id} | conversations:manage | E | — |

### Chat (Messaging) (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.chat.post_message` | create | POST /chat.postMessage | Envía un mensaje a un canal | channel, text, blocks, thread_ts, reply_broadcast | {ok, channel, ts, message} | chat:write | E | — |
| [ ] | `slack.chat.post_ephemeral` | create | POST /chat.postEphemeral | Envía un mensaje efímero visible solo para un usuario | channel, user, text, blocks | {ok, message_ts} | chat:write | E | — |
| [ ] | `slack.chat.update` | update | POST /chat.update | Edita un mensaje existente | channel, ts, text, blocks | {ok, channel, ts} | chat:write | — | — |
| [ ] | `slack.chat.delete` | delete | POST /chat.delete | Borra un mensaje | channel, ts | {ok, channel, ts} | chat:write | I | — |
| [ ] | `slack.chat.schedule_message` | create | POST /chat.scheduleMessage | Programa un mensaje para ser enviado en el futuro | channel, post_at, text, blocks | {ok, scheduled_message_id} | chat:write | — | — |
| [ ] | `slack.chat.delete_scheduled_message` | delete | POST /chat.deleteScheduledMessage | Borra un mensaje programado de la cola | channel, scheduled_message_id | {ok} | chat:write | I | — |
| [ ] | `slack.chat.get_permalink` | read | POST /chat.getPermalink | Obtiene la URL permanente de un mensaje | channel, message_ts | {channel, permalink} | chat:read | — | — |
| [ ] | `slack.chat.me_message` | create | POST /chat.meMessage | Envía un mensaje de acción "/me" a un canal | channel, text | {ok, channel, ts} | chat:write | E | — |
| [ ] | `slack.chat.unfurl` | update | POST /chat.unfurl | Proporciona comportamiento de despliegue personalizado para URLs | channel, ts, unfurls | {ok} | chat:write | — | — |
| [ ] | `slack.chat.start_stream` | create | POST /chat.startStream | Inicia una conversación de streaming | channel, stream_usage | {ok, stream_id} | chat:write | — | — |
| [ ] | `slack.chat.stop_stream` | update | POST /chat.stopStream | Detiene una conversación de streaming | channel, stream_id | {ok} | chat:write | — | — |
| [ ] | `slack.chat.append_stream` | update | POST /chat.appendStream | Añade texto a una conversación de streaming existente | channel, stream_id, text | {ok} | chat:write | — | — |
| [ ] | `slack.chat.scheduled_messages_list` | read | POST /chat.scheduledMessages.list | Lista los mensajes programados | channel, limit, cursor | {scheduled_messages, response_metadata} | chat:read | — | — |

### Reactions (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.reactions.add` | create | POST /reactions.add | Añade una reacción emoji a un elemento (mensaje, archivo, etc.) | name, channel, timestamp | {ok} | reactions:write | — | — |
| [ ] | `slack.reactions.remove` | delete | POST /reactions.remove | Quita una reacción emoji de un elemento | name, channel, timestamp | {ok} | reactions:write | — | — |
| [ ] | `slack.reactions.get` | read | POST /reactions.get | Obtiene las reacciones en un elemento específico | channel, timestamp, full | {type, message, file} | reactions:read | — | — |
| [ ] | `slack.reactions.list` | read | POST /reactions.list | Lista las reacciones hechas por el usuario autenticado | user, limit, cursor, full | {items, response_metadata} | reactions:read | — | — |

### Pins (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.pins.add` | create | POST /pins.add | Fija (pins) un elemento a un canal | channel, timestamp | {ok} | pins:write | — | — |
| [ ] | `slack.pins.remove` | delete | POST /pins.remove | Quita una fijación de un elemento en un canal | channel, timestamp | {ok} | pins:write | — | — |
| [ ] | `slack.pins.list` | read | POST /pins.list | Lista los elementos fijados en un canal | channel, limit, cursor | {items, response_metadata} | pins:read | — | — |

### Stars (Saved Items) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.stars.add` | create | POST /stars.add | Guarda un elemento para después (antiguo sistema de estrellas) | channel, timestamp | {ok} | stars:write | — | — |
| [ ] | `slack.stars.remove` | delete | POST /stars.remove | Quita un elemento guardado | channel, timestamp | {ok} | stars:write | — | — |
| [ ] | `slack.stars.list` | read | POST /stars.list | Lista elementos guardados del usuario autenticado | user, limit, cursor | {items, response_metadata} | stars:read | — | — |

### Bookmarks (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.bookmarks.add` | create | POST /bookmarks.add | Añade un marcador a un canal | channel, title, link, emoji, entity_id | {id} | bookmarks:write | — | — |
| [ ] | `slack.bookmarks.edit` | update | POST /bookmarks.edit | Edita un marcador existente | channel, bookmark_id, title, link, emoji | {bookmark} | bookmarks:write | — | — |
| [ ] | `slack.bookmarks.remove` | delete | POST /bookmarks.remove | Quita un marcador de un canal | channel, bookmark_id | {ok} | bookmarks:write | — | — |
| [ ] | `slack.bookmarks.list` | read | POST /bookmarks.list | Lista los marcadores de un canal | channel | {bookmarks} | bookmarks:read | — | — |

### Files (15)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.files.upload` | create | POST /files.upload | Sube o crea un archivo | channels, file, filename, filetype, title, initial_comment | {file} | files:write | E | — |
| [ ] | `slack.files.delete` | delete | POST /files.delete | Borra un archivo | file | {ok} | files:write | I | — |
| [ ] | `slack.files.get_info` | read | POST /files.info | Obtiene información de un archivo | file, count, page | {file, comments, paging} | files:read | — | — |
| [ ] | `slack.files.list` | read | POST /files.list | Lista archivos en el workspace, canal o de un usuario | channel, user, ts_from, ts_to, types, count, page, cursor | {files, response_metadata} | files:read | — | — |
| [ ] | `slack.files_remote.add` | create | POST /files.remote.add | Añade un archivo desde un servicio remoto a Slack | external_id, external_url, title, mimetype, size | {file} | files:write | E | — |
| [ ] | `slack.files_remote.info` | read | POST /files.remote.info | Obtiene información de un archivo remoto | external_id, file | {file} | files:read | — | — |
| [ ] | `slack.files_remote.list` | read | POST /files.remote.list | Lista archivos remotos añadidos a Slack | channel, ts_from, ts_to, limit, cursor | {files, response_metadata} | files:read | — | — |
| [ ] | `slack.files_remote.update` | update | POST /files.remote.update | Actualiza metadatos de un archivo remoto | external_id, title, mimetype | {file} | files:write | — | — |
| [ ] | `slack.files_remote.remove` | delete | POST /files.remote.remove | Quita un archivo remoto de Slack | external_id, file | {ok} | files:write | I | — |
| [ ] | `slack.files_remote.share` | create | POST /files.remote.share | Comparte un archivo remoto en un canal | channels, external_id, file | {file} | files:write | E | — |
| [ ] | `slack.files.shared_public_url` | update | POST /files.sharedPublicURL | Activa compartición pública/externa de un archivo | file | {file} | files:write | E | — |
| [ ] | `slack.files.revoke_public_url` | update | POST /files.revokePublicURL | Revoca acceso público/externo de un archivo | file | {file} | files:write | — | — |
| [ ] | `slack.files_comments.delete` | delete | POST /files.comments.delete | Borra un comentario en un archivo | file, id | {ok} | files:write | I | — |
| [ ] | `slack.files.get_upload_url_external` | read | POST /files.getUploadURLExternal | Obtiene URL para subida de archivo externo | filename, length | {upload_url, file_id} | files:write | — | — |
| [ ] | `slack.files.complete_upload_external` | create | POST /files.completeUploadExternal | Completa una subida iniciada con getUploadURLExternal | files | {files} | files:write | — | — |

### Users (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.users.list` | read | POST /users.list | Lista todos los usuarios del workspace | limit, cursor, include_locale | {members, response_metadata} | users:read | — | — |
| [ ] | `slack.users.get_info` | read | POST /users.info | Obtiene detalles de un usuario específico | user, include_locale | {user} | users:read | — | — |
| [ ] | `slack.users.identity` | read | POST /users.identity | Obtiene la identidad del usuario autenticado (requiere token de usuario) | — | {user_id, team_id, team_name} | users:read | — | — |
| [ ] | `slack.users.lookup_by_email` | read | POST /users.lookupByEmail | Busca un usuario por dirección de correo | email | {user} | users:read | — | — |
| [ ] | `slack.users.get_presence` | read | POST /users.getPresence | Obtiene el estado de presencia de un usuario | user | {presence, online, auto_away, manual_away} | users:read | — | — |
| [ ] | `slack.users.set_presence` | update | POST /users.setPresence | Establece manualmente el estado de presencia | presence | {ok} | users:write | — | — |
| [ ] | `slack.users_profile.get` | read | POST /users.profile.get | Obtiene el perfil de un usuario (incluido estado personalizado) | user, include_labels | {profile, cache_ts} | users:read | — | — |
| [ ] | `slack.users_profile.set` | update | POST /users.profile.set | Establece información del perfil de un usuario (estado, etc.) | user, profile | {profile} | users:write | — | — |
| [ ] | `slack.users.set_photo` | update | POST /users.setPhoto | Establece la foto de perfil del usuario autenticado | image, crop_w, crop_x, crop_y | {ok} | users:write | — | — |
| [ ] | `slack.users.delete_photo` | delete | POST /users.deletePhoto | Borra la foto de perfil del usuario autenticado | — | {ok} | users:write | I | — |
| [ ] | `slack.users.conversations` | read | POST /users.conversations | Lista conversaciones (canales/DMs) en las que el usuario está | user, exclude_archived, limit, cursor, types | {channels, response_metadata} | conversations:read | — | — |
| [ ] | `slack.users_discoverable_contacts.lookup` | read | POST /users.discoverableContacts.lookup | Busca si un correo es descubrible en Slack | email | {user_id, email, name} | users:read | — | — |

### Reminders (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.reminders.add` | create | POST /reminders.add | Crea un recordatorio | text, time, user | {reminder} | reminders:write | E | — |
| [ ] | `slack.reminders.list` | read | POST /reminders.list | Lista los recordatorios del usuario o para el usuario | user | {reminders} | reminders:read | — | — |
| [ ] | `slack.reminders.get_info` | read | POST /reminders.info | Obtiene detalles de un recordatorio específico | reminder | {reminder} | reminders:read | — | — |
| [ ] | `slack.reminders.complete` | update | POST /reminders.complete | Marca un recordatorio como completado | reminder | {ok} | reminders:write | — | — |
| [ ] | `slack.reminders.delete` | delete | POST /reminders.delete | Borra un recordatorio | reminder | {ok} | reminders:write | I | — |

### Team (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.team.get_info` | read | POST /team.info | Obtiene información del workspace actual | team | {team} | team:read | — | — |
| [ ] | `slack.team.access_logs` | read | POST /team.accessLogs | Obtiene el registro de accesos del workspace | count, page | {logins, paging} | team:read,admin | — | — |
| [ ] | `slack.team.integration_logs` | read | POST /team.integrationLogs | Obtiene el registro de integraciones del workspace | count, page, change_type, service_id, user, app_id | {logs, paging} | team:read,admin | — | — |
| [ ] | `slack.team.billable_info` | read | POST /team.billableInfo | Obtiene información de usuarios facturables del workspace | user | {billable_info} | team:read,admin | — | — |
| [ ] | `slack.team.billing_info` | read | POST /team.billing.info | Obtiene información del plan de facturación del workspace | — | {billing_active, plan_name, plan_type} | team:read,admin | — | — |
| [ ] | `slack.team.profile_get` | read | POST /team.profile.get | Obtiene el perfil del workspace | visibility | {profile} | team:read | — | — |
| [ ] | `slack.team.preferences_list` | read | POST /team.preferences.list | Obtiene las preferencias del workspace | — | {preferences} | team:read,admin | — | — |
| [ ] | `slack.team_external_teams.list` | read | POST /team.externalTeams.list | Lista equipos/workspaces externos conectados | limit, cursor | {external_teams, response_metadata} | team:read | — | — |
| [ ] | `slack.team.external_teams_disconnect` | update | POST /team.externalTeams.disconnect | Desconecta un equipo externo del workspace | external_team_id | {ok} | team:write | — | — |

### DND (Do Not Disturb) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.dnd.info` | read | POST /dnd.info | Obtiene el estado DND del usuario autenticado | user | {dnd_enabled, next_dnd_start_ts, next_dnd_end_ts} | dnd:read | — | — |
| [ ] | `slack.dnd.set_snooze` | update | POST /dnd.setSnooze | Activa DND (No Molestar) por un tiempo especificado | num_minutes | {snooze_enabled, snooze_remaining} | dnd:write | — | — |
| [ ] | `slack.dnd.end_dnd` | update | POST /dnd.endDnd | Termina la sesión DND actual del usuario | — | {dnd_enabled} | dnd:write | — | — |
| [ ] | `slack.dnd.end_snooze` | update | POST /dnd.endSnooze | Termina el modo snooze del usuario | — | {snooze_enabled} | dnd:write | — | — |
| [ ] | `slack.dnd.team_info` | read | POST /dnd.teamInfo | Obtiene el estado DND de hasta 50 usuarios del workspace | users | {users} | dnd:read,users:read | — | — |

### Emoji (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.emoji.list` | read | POST /emoji.list | Lista los emojis personalizados del workspace | — | {emoji} | emoji:read | — | — |
| [ ] | `slack.admin_emoji.add` | create | POST /admin.emoji.add | Añade un emoji personalizado (solo admins enterprise) | name, url, alias | {ok} | admin.emoji:write | — | — |
| [ ] | `slack.admin_emoji.add_alias` | create | POST /admin.emoji.addAlias | Crea un alias de emoji (solo admins enterprise) | name, alias_for | {ok} | admin.emoji:write | — | — |
| [ ] | `slack.admin_emoji.list` | read | POST /admin.emoji.list | Lista emojis de la organización enterprise | limit, cursor | {emoji, response_metadata} | admin.emoji:read | — | — |
| [ ] | `slack.admin_emoji.remove` | delete | POST /admin.emoji.remove | Quita un emoji de la organización enterprise | name | {ok} | admin.emoji:write | I | — |
| [ ] | `slack.admin_emoji.rename` | update | POST /admin.emoji.rename | Renombra un emoji en la organización enterprise | name, new_name | {ok} | admin.emoji:write | — | — |

### Search (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.search.messages` | read | POST /search.messages | Busca mensajes en el workspace | query, sort, sort_dir, highlight, count, page | {messages, paging, response_metadata} | search:read | — | — |
| [ ] | `slack.search.files` | read | POST /search.files | Busca archivos en el workspace | query, sort, sort_dir, highlight, count, page | {files, paging, response_metadata} | search:read | — | — |
| [ ] | `slack.search.all` | read | POST /search.all | Busca mensajes y archivos en el workspace | query, sort, sort_dir, highlight, count, page | {messages, files, paging, response_metadata} | search:read | — | — |
| [ ] | `slack.assistant_search.context` | read | POST /assistant.search.context | Busca en mensajes, archivos, canales y usuarios de la organización | query, focus, limit | {results} | assistant:read | — | — |
| [ ] | `slack.assistant_search.info` | read | POST /assistant.search.info | Obtiene capacidades de búsqueda del workspace | — | {search_capabilities} | assistant:read | — | — |

### Views (Modals & Home Tabs) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.views.open` | create | POST /views.open | Abre una vista modal para un usuario | trigger_id, view | {view} | views:write | E | — |
| [ ] | `slack.views.push` | create | POST /views.push | Apila una vista sobre la vista raíz (navegación en modales) | trigger_id, view | {view} | views:write | — | — |
| [ ] | `slack.views.update` | update | POST /views.update | Actualiza una vista existente | view | {view} | views:write | — | — |
| [ ] | `slack.views.publish` | update | POST /views.publish | Publica una vista estática en la pestaña Home del usuario | user_id, view, hash | {view} | views:write | — | — |

### Blocks (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.blocks.validate` | read | POST /blocks.validate | Valida estructura JSON de bloques (Block Kit) | blocks | {ok, error} | — | — | — |

### Usergroups (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.usergroups.create` | create | POST /usergroups.create | Crea un grupo de usuarios | name, handle, description | {usergroup} | usergroups:write | — | — |
| [ ] | `slack.usergroups.list` | read | POST /usergroups.list | Lista todos los grupos de usuarios del workspace | include_count, include_disabled | {usergroups} | usergroups:read | — | — |
| [ ] | `slack.usergroups.update` | update | POST /usergroups.update | Actualiza propiedades de un grupo de usuarios | usergroup, name, handle, description, include_count | {usergroup} | usergroups:write | — | — |
| [ ] | `slack.usergroups.enable` | update | POST /usergroups.enable | Habilita un grupo de usuarios deshabilitado | usergroup, include_count | {usergroup} | usergroups:write | — | — |
| [ ] | `slack.usergroups.disable` | update | POST /usergroups.disable | Deshabilita un grupo de usuarios | usergroup, include_count | {usergroup} | usergroups:write | — | — |
| [ ] | `slack.usergroups_users.list` | read | POST /usergroups.users.list | Lista usuarios en un grupo de usuarios | usergroup, include_disabled | {users} | usergroups:read | — | — |
| [ ] | `slack.usergroups_users.update` | update | POST /usergroups.users.update | Actualiza la lista de usuarios en un grupo | usergroup, users | {usergroup} | usergroups:write | — | — |

### Workflows (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.workflows_featured.list` | read | POST /workflows.featured.list | Lista workflows destacados en canales especificados | channels | {workflows} | workflows:read | — | — |
| [ ] | `slack.workflows_featured.set` | update | POST /workflows.featured.set | Establece workflows destacados para un canal | channel, workflow_ids | {ok} | workflows:write | — | — |
| [ ] | `slack.workflows_featured.add` | create | POST /workflows.featured.add | Añade workflows destacados a un canal | channel, workflow_ids | {ok} | workflows:write | — | — |
| [ ] | `slack.workflows_featured.remove` | delete | POST /workflows.featured.remove | Quita workflows destacados de un canal | channel, workflow_ids | {ok} | workflows:write | — | — |
| [ ] | `slack.workflows_triggers_permissions.list` | read | POST /workflows.triggers.permissions.list | Lista permisos de triggers de workflows | — | {permissions} | workflows:read | — | — |
| [ ] | `slack.workflows_triggers_permissions.add` | create | POST /workflows.triggers.permissions.add | Añade permiso de acceso a un trigger | workflow_step_id, entity_ids | {ok} | workflows:write | — | — |
| [ ] | `slack.workflows_triggers_permissions.remove` | delete | POST /workflows.triggers.permissions.remove | Quita permiso de acceso a un trigger | workflow_step_id, entity_ids | {ok} | workflows:write | — | — |
| [ ] | `slack.workflows_triggers_permissions.set` | update | POST /workflows.triggers.permissions.set | Establece el tipo de permiso para un trigger | workflow_step_id, permission_type, entity_ids | {ok} | workflows:write | — | — |

### Canvases (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.canvases.create` | create | POST /canvases.create | Crea un lienzo para un usuario | channel_id, is_empty | {canvas_id, is_empty} | canvas:write | — | — |
| [ ] | `slack.canvases.edit` | update | POST /canvases.edit | Actualiza el contenido de un lienzo existente | canvas_id, changes | {canvas_id} | canvas:write | — | — |
| [ ] | `slack.canvases.delete` | delete | POST /canvases.delete | Borra un lienzo | canvas_id | {ok} | canvas:write | I | — |
| [ ] | `slack.canvases.get_content` | read | POST /canvases.getContent | Obtiene el contenido de un lienzo como markdown o HTML | canvas_id, format | {markdown, html} | canvas:read | — | — |
| [ ] | `slack.canvases_sections.lookup` | read | POST /canvases.sections.lookup | Busca secciones en un lienzo por criterios | canvas_id, criteria | {sections} | canvas:read | — | — |
| [ ] | `slack.canvases_access.set` | update | POST /canvases.access.set | Establece el nivel de acceso a un lienzo | canvas_id, access_level, user_ids, group_ids | {ok} | canvas:write | — | — |
| [ ] | `slack.canvases_access.delete` | delete | POST /canvases.access.delete | Quita acceso a un lienzo | canvas_id, user_ids, group_ids | {ok} | canvas:write | — | — |

### Lists (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.slacklists.create` | create | POST /slackLists.create | Crea una lista | name, team_id | {list_id, name} | lists:write | — | — |
| [ ] | `slack.slacklists.update` | update | POST /slackLists.update | Actualiza una lista | list_id, name, description | {list_id} | lists:write | — | — |
| [ ] | `slack.slacklists_items.create` | create | POST /slackLists.items.create | Añade un nuevo elemento a una lista | list_id, values | {item} | lists:write | — | — |
| [ ] | `slack.slacklists_items.list` | read | POST /slackLists.items.list | Obtiene elementos de una lista | list_id, limit, cursor | {items, response_metadata} | lists:read | — | — |
| [ ] | `slack.slacklists_items.get_info` | read | POST /slackLists.items.info | Obtiene un elemento específico de una lista | list_id, item_id | {item} | lists:read | — | — |
| [ ] | `slack.slacklists_items.update` | update | POST /slackLists.items.update | Actualiza celdas en una lista | list_id, item_id, updates | {item} | lists:write | — | — |
| [ ] | `slack.slacklists_items.delete` | delete | POST /slackLists.items.delete | Borra un elemento de una lista | list_id, item_id | {ok} | lists:write | I | — |
| [ ] | `slack.slacklists_items.delete_multiple` | delete | POST /slackLists.items.deleteMultiple | Borra múltiples elementos de una lista | list_id, item_ids | {ok} | lists:write | I | — |
| [ ] | `slack.slacklists_download.start` | create | POST /slackLists.download.start | Inicia un job para exportar contenido de una lista | list_id | {job_id} | lists:read | — | — |
| [ ] | `slack.slacklists_download.get` | read | POST /slackLists.download.get | Obtiene URL de descarga de un export de lista | job_id | {download_url} | lists:read | — | — |
| [ ] | `slack.slacklists_access.set` | update | POST /slackLists.access.set | Establece nivel de acceso a una lista | list_id, access_level, user_ids, group_ids | {ok} | lists:write | — | — |
| [ ] | `slack.slacklists_access.delete` | delete | POST /slackLists.access.delete | Quita acceso a una lista | list_id, user_ids, group_ids | {ok} | lists:write | — | — |

### Assistant (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.assistant_threads.set_title` | update | POST /assistant.threads.setTitle | Establece o renombra un hilo de asistente de IA | channel_id, thread_id, title | {ok} | assistant:write | — | — |
| [ ] | `slack.assistant_threads.set_status` | update | POST /assistant.threads.setStatus | Establece el estado del ciclo de vida de un hilo | channel_id, thread_id, status | {ok} | assistant:write | — | — |
| [ ] | `slack.assistant_threads.set_suggested_prompts` | update | POST /assistant.threads.setSuggestedPrompts | Establece prompts sugeridos para un hilo | channel_id, thread_id, prompts | {ok} | assistant:write | — | — |

### Admin: Apps Management (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_apps.approve` | create | POST /admin.apps.approve | Aprueba la instalación de una app en el workspace (solo admins) | app_id, request_id, team_id | {ok} | admin.apps:write | E | — |
| [ ] | `slack.admin_apps.restrict` | create | POST /admin.apps.restrict | Restringe la instalación de una app en el workspace | app_id, request_id, team_id | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps.uninstall` | delete | POST /admin.apps.uninstall | Desinstala una app de workspaces o toda la organización | app_id, enterprise_id, team_ids | {ok} | admin.apps:write | I | — |
| [ ] | `slack.admin_apps_approved.list` | read | POST /admin.apps.approved.list | Lista apps aprobadas en org/workspace | limit, cursor, enterprise_id, team_id | {apps, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_restricted.list` | read | POST /admin.apps.restricted.list | Lista apps restringidas en org/workspace | limit, cursor, enterprise_id, team_id | {apps, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_activities.list` | read | POST /admin.apps.activities.list | Obtiene logs de actividad de apps en un equipo | team_id, limit, cursor | {activities, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_requests.list` | read | POST /admin.apps.requests.list | Lista solicitudes de instalación de apps en team/workspace | team_id, limit, cursor | {app_requests, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_requests.cancel` | delete | POST /admin.apps.requests.cancel | Cancela solicitud de instalación de app para un equipo | app_id, request_id, team_id | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps_permissions.list` | read | POST /admin.apps.permissions.list | Lista permisos asignados a una app | app_id | {permissions} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_permissions.add` | create | POST /admin.apps.permissions.add | Asigna permisos de app a entidades | app_id, entity_ids, permission_scopes | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps_permissions.remove` | delete | POST /admin.apps.permissions.remove | Revoca permiso de app de entidades | app_id, entity_ids, permission_scopes | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps_permissions.set` | update | POST /admin.apps.permissions.set | Establece tipo de permiso para acceso a app | app_id, permission_type | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps_config.lookup` | read | POST /admin.apps.config.lookup | Busca config de app para conectores por IDs | app_ids | {config_lookup_results} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_config.set` | update | POST /admin.apps.config.set | Establece config de app para un conector | app_id, domain_restrictions, oauth_config | {ok} | admin.apps:write | — | — |
| [ ] | `slack.admin_apps_mcp_servers.list` | read | POST /admin.apps.mcp.servers.list | Lista servidores MCP de apps de terceros aprobadas | org_id, limit, cursor | {mcp_servers, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_mcp_servers_permissions.list` | read | POST /admin.apps.mcp.servers.permissions.list | Lista servidores MCP de una app con permisos de control de acceso | app_id, limit, cursor | {permissions, response_metadata} | admin.apps:read | — | — |
| [ ] | `slack.admin_apps_mcp_servers_permissions.set` | update | POST /admin.apps.mcp.servers.permissions.set | Establece permiso de control de acceso para uso de servidor MCP | app_id, mcp_server_id, permission_level | {ok} | admin.apps:write | — | — |

### Admin: Authentication Policies (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_auth_policy.assign_entities` | create | POST /admin.auth.policy.assignEntities | Asigna entidades a una política de autenticación | policy_id, entity_type, entity_ids | {ok} | admin.auth_policies:write | — | — |
| [ ] | `slack.admin_auth_policy.get_entities` | read | POST /admin.auth.policy.getEntities | Obtiene entidades asignadas a una política de autenticación | policy_id, limit, cursor | {entities, response_metadata} | admin.auth_policies:read | — | — |
| [ ] | `slack.admin_auth_policy.remove_entities` | delete | POST /admin.auth.policy.removeEntities | Quita entidades de una política de autenticación | policy_id, entity_type, entity_ids | {ok} | admin.auth_policies:write | — | — |

### Admin: Information Barriers (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_barriers.create` | create | POST /admin.barriers.create | Crea una barrera de información (aislamiento entre grupos) | barriered_from_usergroup_ids, restricted_subjects, primary_usergroup_id | {barrier} | admin.barriers:write | — | — |
| [ ] | `slack.admin_barriers.list` | read | POST /admin.barriers.list | Lista todas las barreras de información en la organización | limit, cursor | {barriers, response_metadata} | admin.barriers:read | — | — |
| [ ] | `slack.admin_barriers.update` | update | POST /admin.barriers.update | Actualiza una barrera de información existente | barrier_id, barriered_from_usergroup_ids, restricted_subjects | {barrier} | admin.barriers:write | — | — |
| [ ] | `slack.admin_barriers.delete` | delete | POST /admin.barriers.delete | Borra una barrera de información | barrier_id | {ok} | admin.barriers:write | I | — |

### Admin: Conversations (Channels) (30)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_conversations.list` | read | POST /admin.conversations.lookup | Busca canales en un equipo con filtros | team_id, limit, cursor, sort_by, sort_direction | {channels, response_metadata} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations.create` | create | POST /admin.conversations.create | Crea un canal público o privado (solo admin) | team_id, name, is_private, description | {channel} | admin.conversations:write | E | — |
| [ ] | `slack.admin_conversations.delete` | delete | POST /admin.conversations.delete | Borra un canal (solo admin) | channel_id | {ok} | admin.conversations:write | I | — |
| [ ] | `slack.admin_conversations.archive` | update | POST /admin.conversations.archive | Archiva un canal (solo admin) | channel_id | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.unarchive` | update | POST /admin.conversations.unarchive | Desarchiva un canal (solo admin) | channel_id | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.rename` | update | POST /admin.conversations.rename | Renombra un canal (solo admin) | channel_id, name | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.convert_to_private` | update | POST /admin.conversations.convertToPrivate | Convierte un canal público a privado (solo admin) | channel_id | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.convert_to_public` | update | POST /admin.conversations.convertToPublic | Convierte un canal privado a público (solo admin) | channel_id | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.invite` | create | POST /admin.conversations.invite | Invita usuario a un canal (solo admin) | channel_id, user_ids | {channel} | admin.conversations:write | E | — |
| [ ] | `slack.admin_conversations.bulk_archive` | update | POST /admin.conversations.bulkArchive | Archiva múltiples canales en lote | channel_ids | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.bulk_delete` | delete | POST /admin.conversations.bulkDelete | Borra múltiples canales en lote (solo admin) | channel_ids | {ok} | admin.conversations:write | I | — |
| [ ] | `slack.admin_conversations.bulk_move` | update | POST /admin.conversations.bulkMove | Mueve múltiples canales entre workspaces en lote | channel_ids, team_id | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.bulk_set_exclude_from_slack_ai` | update | POST /admin.conversations.bulkSetExcludeFromSlackAi | Excluye múltiples canales de Slack AI en lote | channel_ids, exclude | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.bulk_set_properties` | update | POST /admin.conversations.bulkSetProperties | Establece propiedades en múltiples canales en lote | channel_ids, properties | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.search` | read | POST /admin.conversations.search | Busca canales públicos/privados en toda la organización | team_id, query, limit, cursor, search_channel_types | {channels, response_metadata} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations.set_conversation_prefs` | update | POST /admin.conversations.setConversationPrefs | Establece permisos de publicación de un canal | channel_id, prefs | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.get_conversation_prefs` | read | POST /admin.conversations.getConversationPrefs | Obtiene preferencias de un canal | channel_id | {prefs} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations.set_custom_retention` | update | POST /admin.conversations.setCustomRetention | Establece política de retención personalizada para canal | channel_id, duration_days | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.get_custom_retention` | read | POST /admin.conversations.getCustomRetention | Obtiene política de retención personalizada de canal | channel_id | {retention_duration_days} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations.remove_custom_retention` | delete | POST /admin.conversations.removeCustomRetention | Quita política de retención personalizada de canal | channel_id | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.set_teams` | update | POST /admin.conversations.setTeams | Establece workspaces conectados a un canal en enterprise | channel_id, team_ids, org_channel | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.get_teams` | read | POST /admin.conversations.getTeams | Obtiene todos los workspaces conectados a un canal | channel_id | {teams} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations.disconnect_shared` | update | POST /admin.conversations.disconnectShared | Desconecta un canal conectado de workspaces | channel_id | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations_restrict_access.add_group` | create | POST /admin.conversations.restrictAccess.addGroup | Añade grupos IDP a lista blanca de acceso a canal | channel_id, group_ids | {channel} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations_restrict_access.list_groups` | read | POST /admin.conversations.restrictAccess.listGroups | Lista grupos IDP vinculados a canal | channel_id | {groups} | admin.conversations:read | — | — |
| [ ] | `slack.admin_conversations_restrict_access.remove_group` | delete | POST /admin.conversations.restrictAccess.removeGroup | Quita grupo IDP de acceso a canal | channel_id, group_ids | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.link_objects` | create | POST /admin.conversations.linkObjects | Vincula registro Salesforce a un canal (solo Slack Connect) | channel_id, object_ids | {ok} | admin.conversations:write | E | — |
| [ ] | `slack.admin_conversations.unlink_objects` | delete | POST /admin.conversations.unlinkObjects | Desvincula registro Salesforce de un canal | channel_id, object_ids | {ok} | admin.conversations:write | — | — |
| [ ] | `slack.admin_conversations.create_for_objects` | create | POST /admin.conversations.createForObjects | Crea canal Salesforce para objeto correspondiente | team_id, object_ids | {channels} | admin.conversations:write | E | — |
| [ ] | `slack.admin_conversations_ekm.list_original_connected_channel_info` | read | POST /admin.conversations.ekm.listOriginalConnectedChannelInfo | Lista canales desconectados con IDs de canal original para revocación EKM | — | {channels} | admin.conversations:read | — | — |

### Admin: Users (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_users.list` | read | POST /admin.users.list | Lista usuarios en un workspace (solo admin) | team_id, limit, cursor, include_deactivated | {users, response_metadata} | admin.users:read | — | — |
| [ ] | `slack.admin_users.assign` | create | POST /admin.users.assign | Asigna usuario enterprise a un workspace | user_id, team_id | {ok} | admin.users:write | E | — |
| [ ] | `slack.admin_users.remove` | delete | POST /admin.users.remove | Quita usuario de un workspace (solo admin) | user_id, team_id | {ok} | admin.users:write | I | — |
| [ ] | `slack.admin_users.invite` | create | POST /admin.users.invite | Invita usuario a un workspace (solo admin) | team_id, email, restrict_user | {ok} | admin.users:write | E | — |
| [ ] | `slack.admin_users.set_admin` | update | POST /admin.users.setAdmin | Convierte usuario en admin de workspace (solo admin) | user_id, team_id | {ok} | admin.users:write | — | — |
| [ ] | `slack.admin_users.set_owner` | update | POST /admin.users.setOwner | Convierte usuario en propietario de workspace (solo admin) | user_id, team_id | {ok} | admin.users:write | — | — |
| [ ] | `slack.admin_users.set_regular` | update | POST /admin.users.setRegular | Convierte usuario en usuario regular (solo admin) | user_id, team_id | {ok} | admin.users:write | — | — |
| [ ] | `slack.admin_users.get_expiration` | read | POST /admin.users.getExpiration | Obtiene tiempo de expiración de invitado | user_id, team_id | {expiration_ts} | admin.users:read | — | — |
| [ ] | `slack.admin_users.set_expiration` | update | POST /admin.users.setExpiration | Establece tiempo de expiración para usuario invitado | user_id, team_id, expiration_ts | {ok} | admin.users:write | — | — |
| [ ] | `slack.admin_users_session.list` | read | POST /admin.users.session.list | Lista sesiones activas de usuarios en la organización | limit, cursor | {sessions, response_metadata} | admin.users:read,admin.users.sessions:read | — | — |
| [ ] | `slack.admin_users_session.invalidate` | delete | POST /admin.users.session.invalidate | Revoca una sesión específica de usuario | user_id, session_id | {ok} | admin.users:write,admin.users.sessions:write | — | — |
| [ ] | `slack.admin_users_session.reset` | update | POST /admin.users.session.reset | Borra todas las sesiones válidas de un usuario en todos los dispositivos | user_id | {ok} | admin.users:write,admin.users.sessions:write | I | — |
| [ ] | `slack.admin_users_session.reset_bulk` | update | POST /admin.users.session.resetBulk | Encola job asincrónico para borrar sesiones de múltiples usuarios | user_ids | {job_id} | admin.users:write,admin.users.sessions:write | I | — |
| [ ] | `slack.admin_users_session.get_settings` | read | POST /admin.users.session.getSettings | Obtiene configuración de sesión específica de usuario | user_ids | {user_session_settings} | admin.users:read,admin.users.sessions:read | — | — |
| [ ] | `slack.admin_users_session.set_settings` | update | POST /admin.users.session.setSettings | Configura settings de sesión a nivel de usuario | user_ids, settings | {ok} | admin.users:write,admin.users.sessions:write | — | — |
| [ ] | `slack.admin_users_session.clear_settings` | delete | POST /admin.users.session.clearSettings | Limpia configuración de sesión específica de usuario | user_ids, setting_names | {ok} | admin.users:write,admin.users.sessions:write | — | — |
| [ ] | `slack.admin_users_unsupported_versions.export` | read | POST /admin.users.unsupportedVersions.export | Exporta lista de miembros usando software no soportado | team_id | {export_url} | admin.users:read | — | — |

### Admin: User Groups (Enterprise) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_usergroups.create` | create | POST /admin.usergroups.create | Crea nuevo grupo de usuarios a nivel organización | name, handle, description, auto_type | {usergroup} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.list` | read | POST /admin.usergroups.list | Lista grupos de usuarios a nivel organización | limit, cursor | {usergroups, response_metadata} | admin.usergroups:read | — | — |
| [ ] | `slack.admin_usergroups.fetch` | read | POST /admin.usergroups.fetch | Obtiene detalles de grupo de usuarios enterprise | usergroup_id | {usergroup} | admin.usergroups:read | — | — |
| [ ] | `slack.admin_usergroups.update` | update | POST /admin.usergroups.update | Actualiza propiedades de grupo de usuarios enterprise | usergroup_id, name, handle, description | {usergroup} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.add_users` | create | POST /admin.usergroups.addUsers | Añade miembros a grupo de usuarios enterprise | usergroup_id, user_ids | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.remove_users` | delete | POST /admin.usergroups.removeUsers | Quita miembros de grupo de usuarios enterprise | usergroup_id, user_ids | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.upload_users` | update | POST /admin.usergroups.uploadUsers | Añade miembros a grupo enterprise en lote vía CSV | usergroup_id, users_file_csv | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.add_channels` | create | POST /admin.usergroups.addChannels | Añade hasta 100 canales default a grupo IDP | usergroup_id, channel_ids | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.remove_channels` | delete | POST /admin.usergroups.removeChannels | Quita canales default de grupo IDP | usergroup_id, channel_ids | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.list_channels` | read | POST /admin.usergroups.listChannels | Lista canales vinculados a grupo IDP a nivel org | usergroup_id | {channels} | admin.usergroups:read | — | — |
| [ ] | `slack.admin_usergroups.add_teams` | create | POST /admin.usergroups.addTeams | Asocia workspaces default con grupo IDP a nivel org | usergroup_id, team_ids | {ok} | admin.usergroups:write | — | — |
| [ ] | `slack.admin_usergroups.remove_teams` | delete | POST /admin.usergroups.removeTeams | Quita workspaces default de grupo IDP a nivel org | usergroup_id, team_ids | {ok} | admin.usergroups:write | — | — |

### Admin: Roles (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_roles.add_assignments` | create | POST /admin.roles.addAssignments | Añade miembros a rol especificado con scopes especificados | role_ids, entity_ids, entity_type, scopes | {ok} | admin.roles:write | — | — |
| [ ] | `slack.admin_roles.remove_assignments` | delete | POST /admin.roles.removeAssignments | Quita usuarios de rol para scopes y entidades | role_ids, entity_ids, entity_type, scopes | {ok} | admin.roles:write | — | — |
| [ ] | `slack.admin_roles.list_assignments` | read | POST /admin.roles.listAssignments | Lista asignaciones de todos los roles en entidades | limit, cursor | {assignments, response_metadata} | admin.roles:read | — | — |

### Admin: Teams/Workspaces (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_teams.list` | read | POST /admin.teams.list | Lista todos los equipos/workspaces en la organización enterprise | limit, cursor | {teams, response_metadata} | admin.teams:read | — | — |
| [ ] | `slack.admin_teams.create` | create | POST /admin.teams.create | Crea nuevo equipo enterprise | name, description | {team} | admin.teams:write | E | — |
| [ ] | `slack.admin_teams_settings.info` | read | POST /admin.teams.settings.info | Obtiene información de configuración de workspace | team_id | {team, settings} | admin.teams:read | — | — |
| [ ] | `slack.admin_teams_settings.set_name` | update | POST /admin.teams.settings.setName | Establece el nombre de un workspace | team_id, name | {ok} | admin.teams:write | — | — |
| [ ] | `slack.admin_teams_settings.set_description` | update | POST /admin.teams.settings.setDescription | Establece la descripción de un workspace | team_id, description | {ok} | admin.teams:write | — | — |
| [ ] | `slack.admin_teams_settings.set_icon` | update | POST /admin.teams.settings.setIcon | Establece el icono de un workspace | team_id, icon_url | {ok} | admin.teams:write | — | — |
| [ ] | `slack.admin_teams_settings.set_default_channels` | update | POST /admin.teams.settings.setDefaultChannels | Establece canales default de un workspace | team_id, channel_ids | {ok} | admin.teams:write | — | — |
| [ ] | `slack.admin_teams_settings.set_discoverability` | update | POST /admin.teams.settings.setDiscoverability | Establece descubribilidad de un workspace | team_id, discoverability | {ok} | admin.teams:write | — | — |
| [ ] | `slack.admin_teams_admins.list` | read | POST /admin.teams.admins.list | Lista todos los admins en un workspace | team_id, limit, cursor | {admins, response_metadata} | admin.teams:read | — | — |
| [ ] | `slack.admin_teams_owners.list` | read | POST /admin.teams.owners.list | Lista todos los propietarios en un workspace | team_id, limit, cursor | {owners, response_metadata} | admin.teams:read | — | — |

### Admin: Workflows (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_workflows.search` | read | POST /admin.workflows.search | Busca workflows en team o enterprise | query, limit, cursor | {workflows, response_metadata} | admin.workflows:read | — | — |
| [ ] | `slack.admin_workflows.unpublish` | update | POST /admin.workflows.unpublish | Despublica workflows en team o enterprise | workflow_ids | {ok} | admin.workflows:write | — | — |
| [ ] | `slack.admin_workflows_collaborators.add` | create | POST /admin.workflows.collaborators.add | Añade colaboradores a workflows en team o enterprise | workflow_ids, user_ids | {ok} | admin.workflows:write | — | — |
| [ ] | `slack.admin_workflows_collaborators.remove` | delete | POST /admin.workflows.collaborators.remove | Quita colaboradores de workflows en team o enterprise | workflow_ids, user_ids | {ok} | admin.workflows:write | — | — |
| [ ] | `slack.admin_workflows_permissions.lookup` | read | POST /admin.workflows.permissions.lookup | Obtiene permisos de conjunto de workflows | workflow_ids | {permissions} | admin.workflows:read | — | — |
| [ ] | `slack.admin_workflows_triggers_types_permissions.lookup` | read | POST /admin.workflows.triggers.types.permissions.lookup | Lista permisos para cada tipo de trigger de workflow | — | {permissions} | admin.workflows:read | — | — |
| [ ] | `slack.admin_workflows_triggers_types_permissions.set` | update | POST /admin.workflows.triggers.types.permissions.set | Establece permisos para uso de tipo de trigger | trigger_type, permission_type | {ok} | admin.workflows:write | — | — |

### Admin: Functions (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_functions.list` | read | POST /admin.functions.list | Busca funciones Slack por conjunto de apps | app_ids, limit, cursor | {functions, response_metadata} | admin.functions:read | — | — |
| [ ] | `slack.admin_functions_permissions.lookup` | read | POST /admin.functions.permissions.lookup | Obtiene visibilidad de múltiples funciones Slack | function_ids | {permissions} | admin.functions:read | — | — |
| [ ] | `slack.admin_functions_permissions.set` | update | POST /admin.functions.permissions.set | Establece visibilidad de una función Slack | function_ids, permission_type | {ok} | admin.functions:write | — | — |

### Admin: Invite Requests (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_invite_requests.list` | read | POST /admin.inviteRequests.list | Lista todas las solicitudes pendientes de invitación a workspace | limit, cursor | {invite_requests, response_metadata} | admin.invite_requests:read | — | — |
| [ ] | `slack.admin_invite_requests_approved.list` | read | POST /admin.inviteRequests.approved.list | Lista todas las solicitudes de invitación aprobadas | limit, cursor | {invite_requests, response_metadata} | admin.invite_requests:read | — | — |
| [ ] | `slack.admin_invite_requests_denied.list` | read | POST /admin.inviteRequests.denied.list | Lista todas las solicitudes de invitación denegadas | limit, cursor | {invite_requests, response_metadata} | admin.invite_requests:read | — | — |
| [ ] | `slack.admin_invite_requests.approve` | create | POST /admin.inviteRequests.approve | Aprueba solicitud de invitación a workspace | invite_request_id, team_id | {ok} | admin.invite_requests:write | E | — |
| [ ] | `slack.admin_invite_requests.deny` | delete | POST /admin.inviteRequests.deny | Deniega solicitud de invitación a workspace | invite_request_id, team_id | {ok} | admin.invite_requests:write | — | — |

### Admin: Analytics (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_analytics.get_file` | read | POST /admin.analytics.getFile | Obtiene datos de análisis de fecha específica como JSON comprimido | date, type | {url, expires_at} | admin.analytics:read | — | — |
| [ ] | `slack.admin_analytics_messages.activity` | read | POST /admin.analytics.messages.activity | Obtiene métricas de actividad de mensajes de canal | channel, limit, cursor | {results} | admin.analytics:read | — | — |
| [ ] | `slack.admin_analytics_messages.metadata` | read | POST /admin.analytics.messages.metadata | Obtiene metadatos de lista de mensajes de canal | channel, limit, cursor | {results} | admin.analytics:read | — | — |

### Admin: Audit & Anomalies (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `slack.admin_audit_anomaly_allow.get_item` | read | POST /admin.audit.anomaly.allow.getItem | Lee lista blanca de bloques IP y ASNs de config enterprise | — | {allow_list} | admin.audit:read | — | — |
| [ ] | `slack.admin_audit_anomaly_allow.update_item` | update | POST /admin.audit.anomaly.allow.updateItem | Escribe/sobrescribe lista blanca de bloques IP y ASNs | allow_list | {ok} | admin.audit:write | — | — |
