# Tareas: X (Twitter)

- **Funciones catalogadas:** 79 · **Hechas:** 0 · **Pendientes:** 79 · App sin herramientas viejas
- **Documentación oficial:** https://docs.x.com/x-api/introduction
- **Fuentes que consultó el catálogo:** https://docs.x.com/x-api/users/get-my-user.md https://docs.x.com/x-api/posts/timelines https://docs.x.com/x-api/users/follows https://docs.x.com/x-api/users/mutes https://docs.x.com/x-api/posts/bookmarks https://docs.x.com/x-api/posts/likes https://docs.x.com/x-api/posts/retweets https://docs.x.com/x-api/lists/manage-lists https://docs.x.com/x-api/direct-messages https://docs.x.com/x-api/media/introduction.md https://docs.x.com/x-api/spaces/lookup https://docs.x.com/x-api/posts/search/introduction https://docs.x.com/x-api/posts/hide-replies/introduction https://docs.x.com/x-api/communities/lookup https://docs.x.com/x-api/fundamentals/rate-limits https://docs.x.com/x-api/migrate/x-api-endpoint-map
- **Paginación típica:** Pagination tokens en meta.next_token; max_results parámetro por endpoint
- **Qué no se pudo verificar:** Endpoints específicos de Enterprise (blocks, algunos streams de volumen) no completamente verificados en documentación estándar; endpoint de trends GET /2/trends no encontrado en búsqueda pero mencionado en resumen; algunos parámetros de expansión y campos pueden variar según plan de pago; límites de rate exactos pueden cambiar según plan y autenticación
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/twitter/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `twitter`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `twitter` |
| Variables del `.env` que necesitas | TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/twitter/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `twitter.user.me` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 código de autorización con PKCE; refresh token con scope offline.access |
| Duración del token (según el catálogo) | Access token válido 2 horas sin offline.access; sin límite con offline.access y refresh token |
| Refresco (según el catálogo) | Sí, incluir scope offline.access; solicitar con grant_type=refresh_token a POST /oauth2/token |
| Permisos (según el catálogo) | tweet.read, tweet.write, users.read, mute.read, mute.write, bookmark.read, bookmark.write, like.read, like.write, follows.read, follows.write, offline.access (para refresh token) |
| Restricciones de acceso | Revisión de aplicación requerida; planes de pago para full-archive search y streams de volumen; cuentas de empresa para algunas features |
| Límites de ritmo | Posts lookup 3500/app o 5000/usuario por 15min; crear posts 10000/24h app o 100/15min usuario; follows 50/15min; bookmarks, likes 50/15min; DMs 15/15min lectura 1440/24h envío; media init 180000/24h app; batch compliance job (1 concurrente por tipo) |
| Notas de esta app | OAuth 2 con PKCE; el access token dura 2 h y necesita `offline.access` para el refresh. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/twitter/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> twitter`. | Cuenta con `provider: twitter`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/twitter.user.me/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> twitter <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de X (Twitter). (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/twitter.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Users (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.user.me` ★ | read | GET /2/users/me | Obtener usuario actual autenticado | user.fields, expansions | {id, username, name, created_at, public_metrics, ...} | tweet.read,users.read | — | — |
| [ ] | `twitter.user.get` | read | GET /2/users/:id | Obtener usuario por ID | id, user.fields, expansions | {id, username, name, created_at, public_metrics} | tweet.read,users.read | — | — |
| [ ] | `twitter.user.by_username` | read | GET /2/users/by/username/:username | Obtener usuario por nombre de usuario | username, user.fields, expansions | {id, username, name, created_at} | tweet.read,users.read | — | — |
| [ ] | `twitter.user.lookup` | read | GET /2/users | Obtener múltiples usuarios por IDs | ids, user.fields, expansions | Lista de user objects | tweet.read,users.read | — | — |

### Followers and Following (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.follower.list` | read | GET /2/users/:id/followers | Listar seguidores del usuario | id, max_results, pagination_token, user.fields, expansions | Lista de {id, username} + pagination | users.read | — | — |
| [ ] | `twitter.following.list` | read | GET /2/users/:id/following | Listar usuarios que sigue | id, max_results, pagination_token, user.fields, expansions | Lista de {id, username} + pagination | users.read | — | — |
| [ ] | `twitter.follow.create` | create | POST /2/users/:id/following | Seguir a un usuario | target_user_id | {following: true, pending_follow: false} | follows.write | E | — |
| [ ] | `twitter.follow.delete` | delete | DELETE /2/users/:source_user_id/following/:target_user_id | Dejar de seguir a un usuario | source_user_id, target_user_id | {following: false} | follows.write | I | — |

### Blocks and Mutes (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.block.list` | read | GET /2/users/:id/blocking | Listar usuarios bloqueados | id, max_results, pagination_token, user.fields | Lista de usuarios bloqueados | users.read | — | — |
| [ ] | `twitter.block.create` | create | POST /2/users/:id/blocking | Bloquear a un usuario | target_user_id | {blocking: true} | follows.write | E | — |
| [ ] | `twitter.block.delete` | delete | DELETE /2/users/:source_user_id/blocking/:target_user_id | Desbloquear a un usuario | source_user_id, target_user_id | {blocking: false} | follows.write | I | — |
| [ ] | `twitter.mute.list` | read | GET /2/users/:id/muting | Listar usuarios silenciados | id, max_results, pagination_token, user.fields | Lista de usuarios silenciados | mute.read | — | — |
| [ ] | `twitter.mute.create` | create | POST /2/users/:id/muting | Silenciar a un usuario | target_user_id | {muting: true} | mute.write | E | — |
| [ ] | `twitter.mute.delete` | delete | DELETE /2/users/:source_user_id/muting/:target_user_id | Dejar de silenciar a un usuario | source_user_id, target_user_id | {muting: false} | mute.write | I | — |

### Posts (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.post.create` | create | POST /2/tweets | Crear un nuevo tweet | text, reply_settings, quote_tweet_id, media.media_ids, poll.duration_minutes | {data: {id, text}} | tweet.write | E, I | — |
| [ ] | `twitter.post.delete` | delete | DELETE /2/tweets/:id | Borrar un tweet (solo propio) | id | {data: {deleted: true}} | tweet.write | I | — |
| [ ] | `twitter.post.get` | read | GET /2/tweets/:id | Obtener tweet por ID | id, tweet.fields, expansions | {id, text, created_at, public_metrics, author_id, ...} | tweet.read | — | — |
| [ ] | `twitter.post.lookup` | read | GET /2/tweets | Obtener múltiples tweets por IDs | ids, tweet.fields, expansions, media.fields | Lista de tweets | tweet.read | — | — |

### Post Search (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.post.search_recent` | read | GET /2/tweets/search/recent | Buscar tweets de últimos 7 días | query, max_results, start_time, end_time, tweet.fields | Lista de {id, text, created_at, public_metrics} + pagination | tweet.read | — | — |
| [ ] | `twitter.post.search_archive` | read | GET /2/tweets/search/all | Buscar tweets en archivo completo (desde 2006) | query, max_results, start_time, end_time, tweet.fields | Lista de tweets + pagination | tweet.read | — | — |

### Timelines (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.timeline.user` | read | GET /2/users/:id/tweets | Obtener timeline de un usuario (tweets propios) | id, max_results, exclude, start_time, end_time, tweet.fields | Lista de tweets del usuario + pagination | tweet.read | — | — |
| [ ] | `twitter.timeline.mentions` | read | GET /2/users/:id/mentions | Obtener menciones al usuario | id, max_results, start_time, end_time, tweet.fields, expansions | Lista de tweets que mencionan al usuario | tweet.read | — | — |
| [ ] | `twitter.timeline.home` | read | GET /2/users/:id/timelines/reverse_chronological | Obtener timeline principal del usuario autenticado | id, max_results, tweet.fields, expansions | Lista de tweets del feed principal | tweet.read | — | — |

### Likes (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.like.create` | create | POST /2/users/:id/likes | Marcar tweet como favorito (like) | tweet_id | {data: {liked: true}} | like.write | E | — |
| [ ] | `twitter.like.delete` | delete | DELETE /2/users/:id/likes/:tweet_id | Remover like de un tweet | id, tweet_id | {data: {liked: false}} | like.write | I | — |
| [ ] | `twitter.like.lookup` | read | GET /2/tweets/:id/liking_users | Obtener usuarios que likearon un tweet | id, max_results, user.fields, expansions | Lista de usuarios + pagination | like.read | — | — |
| [ ] | `twitter.like.by_user` | read | GET /2/users/:id/liked_tweets | Obtener tweets likeados por usuario | id, max_results, tweet.fields, expansions | Lista de tweets likeados + pagination | like.read | — | — |

### Reposts (Retweets) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.repost.create` | create | POST /2/users/:id/retweets | Retweetear un tweet | tweet_id | {data: {retweeted: true}} | tweet.write | E | — |
| [ ] | `twitter.repost.delete` | delete | DELETE /2/users/:id/retweets/:tweet_id | Remover retweet | id, tweet_id | {data: {retweeted: false}} | tweet.write | I | — |
| [ ] | `twitter.repost.lookup` | read | GET /2/tweets/:id/retweeted_by | Obtener usuarios que retweetearon un tweet | id, max_results, user.fields, expansions | Lista de usuarios que retweetearon | tweet.read | — | — |
| [ ] | `twitter.repost.by_user` | read | GET /2/users/:id/retweets | Obtener retweets de un usuario | id, max_results, tweet.fields, expansions | Lista de retweets del usuario | tweet.read | — | — |

### Bookmarks (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.bookmark.list` | read | GET /2/users/:id/bookmarks | Obtener bookmarks del usuario | id, max_results, tweet.fields, expansions | Lista de tweets guardados + pagination | bookmark.read | — | — |
| [ ] | `twitter.bookmark.create` | create | POST /2/users/:id/bookmarks | Guardar un tweet en bookmarks | tweet_id | {data: {bookmarked: true}} | bookmark.write | E | — |
| [ ] | `twitter.bookmark.delete` | delete | DELETE /2/users/:id/bookmarks/:tweet_id | Remover bookmark de un tweet | id, tweet_id | {data: {bookmarked: false}} | bookmark.write | I | — |

### Lists (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.list.create` | create | POST /2/lists | Crear una lista | name, description, private | {data: {id, name}} | tweet.write | — | — |
| [ ] | `twitter.list.update` | update | PUT /2/lists/:id | Actualizar detalles de una lista | id, name, description, private | {data: {updated: true}} | tweet.write | — | — |
| [ ] | `twitter.list.delete` | delete | DELETE /2/lists/:id | Borrar una lista (solo propia) | id | {data: {deleted: true}} | tweet.write | I | — |
| [ ] | `twitter.list.get` | read | GET /2/lists/:id | Obtener detalles de una lista | id, list.fields, expansions | {id, name, description, owner_id, member_count} | tweet.read | — | — |
| [ ] | `twitter.list.owned` | read | GET /2/users/:id/owned_lists | Obtener listas creadas por usuario | id, max_results, list.fields, expansions | Lista de listas del usuario + pagination | tweet.read | — | — |
| [ ] | `twitter.list.member_add` | create | POST /2/lists/:id/members | Agregar miembro a una lista | user_id | {data: {is_member: true}} | tweet.write | E | — |
| [ ] | `twitter.list.member_remove` | delete | DELETE /2/lists/:id/members/:user_id | Remover miembro de una lista | id, user_id | {data: {is_member: false}} | tweet.write | I | — |
| [ ] | `twitter.list.members` | read | GET /2/lists/:id/members | Obtener miembros de una lista | id, max_results, user.fields, expansions | Lista de miembros + pagination | tweet.read | — | — |
| [ ] | `twitter.list.member_of` | read | GET /2/users/:id/list_memberships | Obtener listas en las que el usuario es miembro | id, max_results, list.fields, expansions | Lista de listas en las que es miembro | tweet.read | — | — |
| [ ] | `twitter.list.follow_create` | create | POST /2/users/:id/followed_lists | Seguir una lista | list_id | {data: {following: true}} | tweet.write | E | — |
| [ ] | `twitter.list.follow_delete` | delete | DELETE /2/users/:id/followed_lists/:list_id | Dejar de seguir una lista | id, list_id | {data: {following: false}} | tweet.write | I | — |
| [ ] | `twitter.list.followed` | read | GET /2/users/:id/followed_lists | Obtener listas que sigue el usuario | id, max_results, list.fields, expansions | Lista de listas seguidas + pagination | tweet.read | — | — |
| [ ] | `twitter.list.followers` | read | GET /2/lists/:id/followers | Obtener seguidores de una lista | id, max_results, user.fields, expansions | Lista de seguidores de la lista | tweet.read | — | — |
| [ ] | `twitter.list.pin_create` | create | POST /2/users/:id/pinned_lists | Fijar una lista | list_id | {data: {pinned: true}} | tweet.write | E | — |
| [ ] | `twitter.list.pin_delete` | delete | DELETE /2/users/:id/pinned_lists/:list_id | Desfijar una lista | id, list_id | {data: {pinned: false}} | tweet.write | I | — |
| [ ] | `twitter.list.pinned` | read | GET /2/users/:id/pinned_lists | Obtener listas fijadas del usuario | id, max_results, list.fields, expansions | Lista de listas fijadas | tweet.read | — | — |

### Direct Messages (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.dm.send` | create | POST /2/dm_conversations/with/:participant_id/messages | Enviar mensaje directo a un usuario | participant_id, text | {data: {dm_conversation_id, dm_event_id}} | tweet.write | E, I | — |
| [ ] | `twitter.dm.conversation_get` | read | GET /2/dm_conversations/:conversation_id/dm_events | Obtener mensajes de una conversación | conversation_id, max_results, dm_event.fields, expansions | Lista de dm_event objects + pagination | tweet.read | — | — |
| [ ] | `twitter.dm.with_user` | read | GET /2/dm_conversations/with/:participant_id/dm_events | Obtener mensajes con un usuario específico | participant_id, max_results, dm_event.fields | Lista de mensajes de la conversación | tweet.read | — | — |
| [ ] | `twitter.dm.list` | read | GET /2/dm_events | Obtener eventos de DM del usuario | max_results, dm_event.fields, event_types | Lista de dm_events relacionados al usuario | tweet.read | — | — |

### Media (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.media.upload` | create | POST /2/media/upload | Subir archivo de media (imagen, video, GIF) | media_data, media_category | {media_id, size, expires_after_secs, media_key} | tweet.write | E | — |
| [ ] | `twitter.media.metadata_add` | create | POST /2/media/:media_id/metadata | Agregar metadata (alt text) a media subido | media_id, alt_text | {media: {media_id, alt_text}} | tweet.write | — | — |

### Spaces (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.space.get` | read | GET /2/spaces/:id | Obtener detalles de un space (audio en vivo) | id, space.fields, expansions, user.fields | {id, state, title, host_ids, created_at, participant_count} | tweet.read | — | — |
| [ ] | `twitter.space.lookup` | read | GET /2/spaces | Obtener múltiples spaces por IDs | ids, space.fields, expansions, user.fields | Lista de space objects | tweet.read | — | — |
| [ ] | `twitter.space.search` | read | GET /2/spaces/search | Buscar spaces | query, max_results, space.fields, state, expansions | Lista de spaces que coinciden con búsqueda | tweet.read | — | — |
| [ ] | `twitter.space.by_creator` | read | GET /2/spaces/by/creator_ids | Obtener spaces por ID de creador | creator_ids, max_results, space.fields, expansions | Lista de spaces creados por usuario/es | tweet.read | — | — |

### Filtered Stream (Real-time) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.stream_filtered.connect` | read | GET /2/tweets/search/stream | Conectar a stream de tweets filtrado en tiempo real | Conexión persistente | Stream de tweets que coinciden con reglas | tweet.read | — | — |
| [ ] | `twitter.stream_filtered.rule_add` | create | POST /2/tweets/search/stream/rules | Agregar regla de filtro al stream | value, tag | {data: [{id, value, tag}]} | tweet.write | — | — |
| [ ] | `twitter.stream_filtered.rule_delete` | delete | DELETE /2/tweets/search/stream/rules | Eliminar regla de filtro | id | {data: {deleted: true}} | tweet.write | I | — |
| [ ] | `twitter.stream_filtered.rule_get` | read | GET /2/tweets/search/stream/rules | Obtener reglas de filtro actuales | max_results | {data: [{id, value, tag}]} | tweet.read | — | — |

### Volume Stream (Enterprise) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.stream_sampled.connect` | read | GET /2/tweets/sample/stream | Conectar a stream muestreado (1% de tweets públicos) | Conexión persistente | Stream de tweets al 1% | tweet.read | — | — |
| [ ] | `twitter.stream_decahose.connect` | read | GET /2/tweets/decahose/stream | Conectar a stream decahose (10% de tweets públicos) | Conexión persistente | Stream de tweets al 10% | tweet.read | — | — |
| [ ] | `twitter.stream_firehose.connect` | read | GET /2/tweets/firehose/stream | Conectar a stream firehose (100% de tweets públicos) | Conexión persistente | Stream de todos los tweets públicos | tweet.read | — | — |

### Communities (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.community.get` | read | GET /2/communities/:id | Obtener detalles de una comunidad | id, community.fields, expansions, user.fields | {id, name, description, created_at, member_count, private} | tweet.read | — | — |
| [ ] | `twitter.community.lookup` | read | GET /2/communities | Obtener múltiples comunidades por IDs | ids, community.fields, expansions, user.fields | Lista de community objects | tweet.read | — | — |
| [ ] | `twitter.community.search` | read | GET /2/communities/search | Buscar comunidades por palabra clave | query, max_results, community.fields, expansions | Lista de comunidades encontradas | tweet.read | — | — |

### Post Utilities (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.post.hide_reply` | update | PUT /2/tweets/:id/hidden | Ocultar o mostrar una respuesta a un tweet propio | id, hidden | {data: {hidden: boolean}} | tweet.write | — | — |
| [ ] | `twitter.post.quote_lookup` | read | GET /2/tweets/:id/quote_tweets | Obtener quote tweets de un tweet | id, max_results, tweet.fields, expansions | Lista de tweets que citan el tweet original | tweet.read | — | — |
| [ ] | `twitter.post.reply_lookup` | read | GET /2/tweets/:id/in_reply_to_tweets | Obtener tuits a los que el tweet responde | id, tweet.fields, expansions | Tweet o tweets a los que responde | tweet.read | — | — |

### Compliance (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `twitter.compliance.create_job` | create | POST /2/compliance/tweets | Crear job de compliance para verificar estado de tweets | type | {data: {id, type, status, upload_url}} | tweet.read | — | — |
| [ ] | `twitter.compliance.upload` | create | POST /2/compliance/jobs/:id/upload | Subir dataset de IDs a job de compliance | job_id, tweet_ids (archivo) | {data: {upload_url: string}} | tweet.read | — | — |
| [ ] | `twitter.compliance.job_status` | read | GET /2/compliance/jobs/:id | Obtener estado de un job de compliance | id | {data: {id, status, download_url, created_at}} | tweet.read | — | — |
| [ ] | `twitter.compliance.users_create_job` | create | POST /2/compliance/users | Crear job de compliance para usuarios | type | {data: {id, type, status, upload_url}} | users.read | — | — |
| [ ] | `twitter.compliance.users_upload` | create | POST /2/compliance/users/:id/upload | Subir dataset de IDs de usuarios a job | job_id, user_ids (archivo) | {data: {upload_url: string}} | users.read | — | — |
| [ ] | `twitter.compliance.users_job_status` | read | GET /2/compliance/users/:id | Obtener estado de job de compliance de usuarios | id | {data: {id, status, download_url}} | users.read | — | — |
