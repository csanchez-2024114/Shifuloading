# Tareas: Threads

- **Funciones catalogadas:** 23 · **Hechas:** 0 · **Pendientes:** 23 · App sin herramientas viejas
- **Documentación oficial:** https://developers.facebook.com/docs/threads
- **Fuentes que consultó el catálogo:** https://developers.facebook.com/docs/threads/posts/ https://developers.facebook.com/documentation/threads/threads-profiles https://developers.facebook.com/documentation/threads/keyword-search https://developers.facebook.com/docs/threads/insights/ https://developers.facebook.com/documentation/threads/reply-management https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/replies-and-conversations https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens.md https://developers.facebook.com/docs/threads/create-posts/location-tagging https://developers.facebook.com/docs/threads/tools-and-resources/embed-a-threads-post https://developers.facebook.com/docs/threads/posts/delete-posts https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts https://developers.facebook.com/documentation/threads/posts/quote-posts https://developers.facebook.com/documentation/threads/create-posts/spoilers https://developers.facebook.com/documentation/threads/create-posts/polls https://developers.facebook.com/docs/threads/overview
- **Paginación típica:** Cursor-based. GET devuelve {data: [...], paging: {cursors: {before, after}}}. Parámetros limit (default 25, max 100) y before/after para navegar.
- **Qué no se pudo verificar:** Comportamiento exacto de refresco de token en perfiles privados (docs vague). Si existen endpoints para ghost_posts realmente como GET (no encontré detalles). Exacta validez de tokens cortos no especificada.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/threads/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `threads`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `threads` |
| Variables del `.env` que necesitas | THREADS_CLIENT_ID, THREADS_CLIENT_SECRET, THREADS_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/threads/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `threads.user.get_me` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con authorization code flow. El cliente obtiene código, lo intercambia por access token corto, y luego obtiene token largo con app secret. |
| Duración del token (según el catálogo) | Access tokens cortos: duración no especificada en docs (parece ser de horas). Access tokens largos: 60 días válidos, renovables cada 24+ horas; para perfiles privados: 90 días válidos. |
| Refresco (según el catálogo) | Sí. GET /access_token con grant_type=th_exchange_token (token corto a largo). GET /refresh_access_token con grant_type=th_refresh_token (renueva token largo, válido otros 60 días). Solo en servidor (incluye app secret). |
| Permisos (según el catálogo) | threads_basic (requerido para toda solicitud), threads_content_publish (crear/publicar), threads_read_replies (leer respuestas), threads_manage_replies (ocultar/aprobar respuestas), threads_manage_insights (leer analytics), threads_keyword_search (buscar por palabra clave), threads_profile_discovery (leer perfiles públicos), threads_location_tagging (buscar y etiquetar ubicaciones), threads_delete (borrar posts). |
| Restricciones de acceso | La app debe pasar revisión de Meta. Token largo válido solo 60 días (90 para perfiles privados). Perfiles privados no pueden renovar tokens vencidos y requieren volver a autorizar. Requiere OAuth 2 y almacenamiento seguro del app secret en servidor. |
| Límites de ritmo | 250 posts publicados por API en 24h. 1000 respuestas en 24h. 100 borrados en 24h. 500 búsquedas de ubicación en 24h. Rate limit dinámico: 4800 * impresiones en 24h. Keyword search: máx 100 resultados por página. oEmbed: 1000 requests/hora. Profile lookup: máx 1000 requests/24h con mín 100 seguidores. Carouseles: 2-20 items, máx 20 imágenes/vídeos. |
| Notas de esta app | Token largo de Meta. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/threads/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> threads`. | Cuenta con `provider: threads`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/threads.user.get_me/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> threads <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Threads. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/threads.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Perfil de Usuario (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.user.get_me` ★ | read | GET /v1.0/me | Obtener perfil del usuario autenticado (whoami) | fields (opcional: id, username, name, threads_profile_picture_url, threads_biography, is_verified) | {id, username, name, profile_picture_url, biography, is_verified, ...} | threads_basic | — | — |
| [ ] | `threads.user.lookup` | read | GET /v1.0/profile_lookup | Buscar perfil público por nombre de usuario exacto | username (requerido, búsqueda exacta) | {id, username, name, profile_picture_url, biography, is_verified, follower_count, likes_count, quotes_count, reposts_count, views_count} | threads_basic, threads_profile_discovery | — | — |
| [ ] | `threads.user.get_posts` | read | GET /{threads-user-id}/threads | Obtener posts del usuario autenticado con paginación | fields (opcional), limit (default 25, max 100), after (cursor) | {data: [{id, media_type, text, timestamp, permalink, username, ...}], paging: {cursors}} | threads_basic | — | — |
| [ ] | `threads.user.get_ghost_posts` | read | GET /{threads-user-id}/ghost_posts | Obtener posts fantasma (borradores no publicados) del usuario autenticado | fields (opcional), limit, after | {data: [{id, media_type, text, ...}], paging} | threads_basic | — | — |
| [ ] | `threads.user.get_publishing_limit` | read | GET /{threads-user-id}/threads_publishing_limit | Obtener uso actual de cuota de publicación y límites del usuario | ninguno | {quota_usage, reply_quota_usage, delete_quota_usage, location_search_quota_usage} | threads_basic, threads_content_publish | — | — |
| [ ] | `threads.profile.get_posts` | read | GET /profile_posts | Obtener posts públicos de un perfil (mín 100 seguidores) | username (requerido, búsqueda exacta), fields (opcional), limit, after | {data: [{id, media_type, text, ...}], paging} | threads_basic, threads_profile_discovery | — | — |

### Posts (Crear y Publicar) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.post.create_media` | create | POST /{threads-user-id}/threads | Crear contenedor de media (paso 1 de publicación). Soporta texto, imagen, vídeo, carrusel, quote posts, con opcionales spoilers, poll, link attachment, gif | media_type (requerido: TEXT/IMAGE/VIDEO/CAROUSEL), text (para TEXT/image_url/video_url para media), image_url, video_url, is_carousel_item, children (para CAROUSEL), text_entities (spoilers), is_spoiler_media, poll_attachment, link_attachment, gif_attachment, topic_tag, quote_post_id, reply_control (everyone/accounts_you_follow/mentioned_only/parent_post_author_only/followers_only) | {creation_id, media_type, ...} | threads_content_publish | I | — |
| [ ] | `threads.post.publish` | create | POST /{threads-user-id}/threads_publish | Publicar contenedor de media (paso 2). Recomendado esperar 30s después de crear | creation_id (requerido) | {id, creation_id, media_type, ...} | threads_content_publish | E, I | — |
| [ ] | `threads.post.get_by_id` | read | GET /{threads-media-id} | Obtener detalles de un post por su ID de media | fields (opcional: id, media_type, text, timestamp, permalink, username, children, poll_attachment, is_quote_post, quoted_post, is_spoiler_media, text_attachment, topic_tag, is_verified, hide_status, root_post, replied_to, is_reply, gif_url, ...) | {id, media_type, text, timestamp, permalink, username, ...} | threads_basic | — | — |
| [ ] | `threads.post.delete` | delete | DELETE /{threads-media-id} | Borrar un post creado por el usuario autenticado (límite 100 borrados/24h) | ninguno | {success: true, deleted_id} | threads_delete | I | — |
| [ ] | `threads.post.create_quote` | create | POST /{threads-user-id}/threads | Crear quote post (cita de otro post). Usa endpoint crear media con quote_post_id adicional | quote_post_id (requerido: ID del post a citar), media_type, text (opcional), access_token | {creation_id, media_type, ...} | threads_content_publish | — | — |

### Búsqueda de Posts (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.media.search_keyword` | read | GET /keyword_search | Buscar posts públicos por palabra clave o etiqueta de tema. Devuelve resultados más populares o recientes | q (requerido), search_type (TOP/RECENT, default TOP), search_mode (KEYWORD/TAG, default KEYWORD), media_type (TEXT/IMAGE/VIDEO), since (unix timestamp), until (unix timestamp), limit (25-100, default 25), author_username (filtro), after (cursor) | {data: [{id, text, media_type, permalink, timestamp, username, has_replies, is_quote_post, is_reply, ...}], paging: {cursors}} | threads_basic, threads_keyword_search | — | — |
| [ ] | `threads.user.get_recent_searches` | read | GET /v1.0/me | Obtener palabras clave buscadas recientemente por el usuario | fields=recently_searched_keywords (requerido) | {recently_searched_keywords: [{query, timestamp}, ...]} | threads_basic | — | — |

### Respuestas y Conversaciones (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.reply.list_replies` | read | GET /{threads-media-id}/replies | Obtener respuestas de nivel superior de un post con paginación | reverse (boolean, default true: orden inverso), limit, after (cursor) | {data: [{id, text, username, timestamp, media_type, media_url, has_replies, replied_to, is_reply, hide_status, ...}], paging: {cursors}} | threads_basic | — | — |
| [ ] | `threads.reply.get_conversation` | read | GET /{threads-media-id}/conversation | Obtener todas las respuestas de un post aplanadas (incluye anidadas) sin jerarquía | reverse (default true), limit, after | {data: [{id, text, username, timestamp, media_type, root_post, replied_to, is_reply, has_replies, hide_status, ...}], paging: {cursors}} | threads_basic | — | — |
| [ ] | `threads.reply.list_pending` | read | GET /{threads-media-id}/pending_replies | Obtener respuestas pendientes de aprobación/ignoradas (si hay moderación activa) | reverse (default true), approval_status (pending/ignored), limit, after | {data: [{id, text, username, timestamp, reply_approval_status, ...}], paging: {cursors}} | threads_manage_replies | — | — |
| [ ] | `threads.reply.hide` | update | POST /{threads-reply-id}/manage_reply | Ocultar o mostrar una respuesta (ocultar también oculta anidadas automáticamente) | hide (boolean, requerido: true/false) | {success: true} | threads_manage_replies | I | — |
| [ ] | `threads.reply.manage_pending` | update | POST /{threads-reply-id}/manage_pending_reply | Aprobar o ignorar una respuesta pendiente de moderación | approve (boolean, requerido: true=aprobar, false=ignorar) | {success: true} | threads_manage_replies | — | — |

### Ubicaciones (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.location.search` | read | GET /location_search | Buscar ubicaciones por nombre o coordenadas para etiquetar en posts | q (búsqueda por nombre) O latitude + longitude (búsqueda por coordenadas), limit | {data: [{id, address, name, city, country, latitude, longitude, ...}]} | threads_basic, threads_location_tagging | — | — |
| [ ] | `threads.location.get_by_id` | read | GET /{location-id} | Obtener detalles de una ubicación por su ID | fields (opcional: id, address, name, city, country, latitude, longitude, postal_code) | {id, address, name, city, country, latitude, longitude, postal_code} | threads_basic, threads_location_tagging | — | — |

### Analytics (Insights) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.media.get_insights` | read | GET /{threads-media-id}/insights | Obtener métricas de un post: vistas, likes, respuestas, reposts, citas, comparticiones | metric (requerido, valores: views,likes,replies,reposts,quotes,shares, separados por coma) | {data: [{name, period, values: [{value}], title, description, id}]} | threads_manage_insights | — | — |
| [ ] | `threads.user.get_insights` | read | GET /{threads-user-id}/threads_insights | Obtener analytics de la cuenta del usuario: vistas, engagement, seguidores, demografía de audiencia | metric (requerido: views,likes,replies,reposts,quotes,followers_count,follower_demographics,clicks, separados por coma), since (unix timestamp, min 1712991600), until (unix timestamp), breakdown (para demografía) | {data: [{name, period, values: [{value}], title, id} O {values: [{link, click_count}]} O {follower_demographics: {country: {...}, city: {...}, age: {...}, gender: {...}}}]} | threads_manage_insights | — | — |

### oEmbed / Embed (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `threads.embed.get_oembed` | read | GET /oembed | Obtener código HTML para incrustar un post de Threads en un sitio web | url (requerido: permalink del post), maxwidth (opcional: 320-658 px) | {type: rich, version: 1.0, html: <blockquote...>, provider_name: Threads, provider_url, width} | — | — | — |
