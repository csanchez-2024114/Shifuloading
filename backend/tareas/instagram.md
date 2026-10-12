# Tareas: Instagram

- **Funciones catalogadas:** 57 · **Hechas:** 0 · **Pendientes:** 57 · **Herramientas viejas a migrar:** 23 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.facebook.com/docs/instagram
- **Fuentes que consultó el catálogo:** https://developers.facebook.com/docs/instagram https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/ https://developers.facebook.com/docs/instagram-platform/content-publishing/ https://developers.facebook.com/docs/instagram-platform/insights/ https://developers.facebook.com/docs/instagram-platform/reference/access_token/ https://developers.facebook.com/docs/instagram-api/reference/hashtag/recent-media https://developers.facebook.com/docs/instagram-api/reference/ig-user/recently_searched_hashtags https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api
- **Paginación típica:** Cursor-based: respuesta incluye {data: [...], paging: {cursors: {before, after}, next}}
- **Qué no se pudo verificar:** Endpoints de comentarios mapeados desde Facebook Graph API: confirmar en la documentacion especifica de Instagram.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/instagram/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `instagram`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `instagram` |
| Variables del `.env` que necesitas | INSTAGRAM_CLIENT_ID, INSTAGRAM_CLIENT_SECRET, INSTAGRAM_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/instagram/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `instagram.account.get` |
| Cómo se autentica (según el catálogo) | OAuth 2 de Meta (Instagram Login o Facebook Login for Business): usuario autoriza, obtiene código, se intercambia por token corto (1h) que se renueva a token largo |
| Duración del token (según el catálogo) | Token largo vive 60 días; token corto 1 hora |
| Refresco (según el catálogo) | POST /oauth/access_token con grant_type=ig_exchange_token, access_token corto y client_secret para obtener token largo (60d) |
| Permisos (según el catálogo) | instagram_basic (Instagram Login); instagram_business_basic (Facebook Login); igb_manage_messages (DMs); igb_manage_content (publicar); igb_manage_comments (comentarios); igb_get_recommendations (recomendaciones); igb_manage_hashtag_research (búsqueda hashtags) |
| Restricciones de acceso | Requiere Professional Account (Creador o Negocios) o estar vinculado a Página Facebook; App Review necesaria para algunos scopes; cuentas con <100 seguidores no acceden a insights; límite 100 publicaciones/24h |
| Límites de ritmo | Rate limiting: 200 llamadas/hora por token; publicaciones 100/24h; búsqueda hashtags 30 únicos/7d; ventana 24h para responder DMs; búsqueda media reciente limitada a 24h |
| Notas de esta app | Token largo de Meta; requiere cuenta profesional de Instagram. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/instagram/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> instagram`. | Cuenta con `provider: instagram`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/instagram.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> instagram <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Instagram. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/instagram.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Perfil y Cuenta (Operaciones de usuario) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.account.get` ★ | read | GET /me | Obtiene perfil básico: id, username, account_type de la cuenta conectada | — | {id, username, account_type} | instagram_basic | — | get_user_profile |
| [ ] | `instagram.account.get_details` | read | GET /me | Obtiene perfil completo: id, username, bio, followers, media_count, verificación, website | — | {id, username, biography, followers_count, follows_count, media_count, name, verified, website, profile_picture_url, ig_id} | instagram_basic | — | get_extended_profile |
| [ ] | `instagram.account.get_followers` | read | GET /me | Obtiene cantidad de seguidores | — | {followers_count, username} | instagram_basic | — | get_followers_count |
| [ ] | `instagram.account.update_bio` | update | POST /me | Actualiza la biografía del perfil | biography (máx 150 caracteres) | {success} | igb_manage_content | — | update_bio |
| [ ] | `instagram.account.update_profile_picture` | update | POST /me | Actualiza foto de perfil desde URL o ID de media existente | profile_picture_url | {success} | igb_manage_content | — | — |

### Media (Publicaciones, Reels, Historias, Carruseles) (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.media.list` | read | GET /me/media | Lista todas las publicaciones de la cuenta con paginación | — | {data: [{id, caption, media_type, timestamp, permalink, comments_count, like_count}], paging} | instagram_basic | — | get_media_from_account |
| [ ] | `instagram.media.get` | read | GET /{media_id} | Obtiene detalles de una publicación: tipo, caption, URL, timestamp, métricas | media_id | {id, caption, media_type, permalink, timestamp, username, like_count, comments_count, view_count, media_url, thumbnail_url} | instagram_basic | — | get_media_details |
| [ ] | `instagram.media.search` | read | GET /{user_id}/media | Busca media de otro usuario por tipo o rango de fecha | user_id, media_type (CAROUSEL, IMAGE, VIDEO, REELS, STORIES) | {data: [{id, caption, media_type, timestamp}], paging} | instagram_business_basic | — | — |
| [ ] | `instagram.media.delete` | delete | DELETE /{media_id} | Elimina una publicación (post, reel, story, carrusel) | media_id | {success} | igb_manage_content | I | — |
| [ ] | `instagram.media.update_comment_enabled` | update | POST /{media_id} | Habilita o deshabilita comentarios en una publicación | comment_enabled (true/false) | {success} | igb_manage_content | — | — |
| [ ] | `instagram.media.like` | create | POST /{media_id}/likes | Da me gusta a una publicación | media_id | {success} | igb_manage_content | — | like_media |
| [ ] | `instagram.media.unlike` | delete | DELETE /{media_id}/likes | Quita me gusta de una publicación | media_id | {success} | igb_manage_content | — | unlike_media |
| [ ] | `instagram.media.pin` | create | POST /{media_id}/ig_pin | Fija una publicación en el feed (solo 3 máximo) | media_id | {success} | igb_manage_content | — | — |
| [ ] | `instagram.media.unpin` | delete | DELETE /{media_id}/ig_pin | Quita publicación fija del feed | media_id | {success} | igb_manage_content | — | — |

### Contenido: Crear y Publicar (Containers, Carruseles, Publicación) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.media.create_container` | create | POST /{user_id}/media | Crea contenedor para imagen, video, reel, story o carrusel; devuelve container_id para publicar después | image_url / video_url, media_type (IMAGE, VIDEO, REELS, STORIES, CAROUSEL), caption, user_tags (menciones) | {id: container_id} | igb_manage_content | — | — |
| [ ] | `instagram.media.create_carousel_container` | create | POST /{user_id}/media | Crea contenedor de carrusel con 2-10 items (imágenes/videos) | children (array de container_ids), caption | {id: carousel_container_id} | igb_manage_content | — | — |
| [ ] | `instagram.media.publish_container` | create | POST /{user_id}/media_publish | Publica un contenedor ya creado (image, video, carousel, story, reel) | creation_id (container_id) | {media_id} | igb_manage_content | I | — |
| [ ] | `instagram.media.upload_video_resumable` | create | POST rupload.facebook.com | Carga un video usando resumable upload (para archivos >8MB) | video_file_path, upload_session_id | {upload_session_id, video_data} | igb_manage_content | — | — |

### Comentarios (Listar, crear, responder, editar, eliminar, ocultar) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.comments.list` | read | GET /{media_id}/comments | Lista comentarios en una publicación con paginación | media_id | {data: [{id, text, username, timestamp, like_count}], paging} | instagram_basic | — | get_comments |
| [ ] | `instagram.comments.get` | read | GET /{comment_id} | Obtiene detalles de un comentario | comment_id | {id, text, username, timestamp, hidden, like_count} | instagram_basic | — | — |
| [ ] | `instagram.comments.create` | create | POST /{media_id}/comments | Publica un comentario en una publicación | media_id, message (máx 2200 caracteres) | {id} | igb_manage_comments | E | create_comment |
| [ ] | `instagram.comments.reply` | create | POST /{comment_id}/replies | Responde a un comentario existente | comment_id, message | {id} | igb_manage_comments | E | reply_comment |
| [ ] | `instagram.comments.update` | update | POST /{comment_id} | Edita el texto de un comentario propio | comment_id, message | {success} | igb_manage_comments | — | update_comment |
| [ ] | `instagram.comments.delete` | delete | DELETE /{comment_id} | Elimina un comentario propio | comment_id | {success} | igb_manage_comments | I | delete_comment |
| [ ] | `instagram.comments.hide` | update | POST /{comment_id} | Oculta un comentario de terceros (spam, ofensivo) | comment_id, hidden (true/false) | {success} | igb_manage_comments | — | — |
| [ ] | `instagram.comments.get_replies` | read | GET /{comment_id}/replies | Lista respuestas a un comentario | comment_id | {data: [{id, text, username, timestamp}], paging} | instagram_basic | — | — |

### Insights (Métricas de cuenta y media) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.account.insights` | read | GET /{user_id}/insights | Obtiene métricas de cuenta: impresiones, alcance, vistas de perfil, visitas del sitio web, clics en contacto | metric (impressions, reach, profile_views, website_clicks, phone_call_clicks, text_message_clicks, email_clicks, get_directions_clicks, phone_call_clicks_by_button_type) | {data: [{title, description, values: [{value, end_time}]}]} | instagram_basic | — | — |
| [ ] | `instagram.media.insights` | read | GET /{media_id}/insights | Obtiene métricas de media: impresiones, alcance, engagement, guardados, interacciones, descargas | metric (impressions, reach, engagement, saved, engagement_rate, like_count, comments_count, total_interactions, video_views, video_play_actions, replies, reposts, shares) | {data: [{title, description, values: [{value}]}]} | instagram_basic | — | get_insights |
| [ ] | `instagram.stories.insights` | read | GET /{story_id}/insights | Obtiene métricas de story: impresiones, alcance, retorno, repuestas, taps forward/back (solo mientras la story esté activa, 24h) | metric (impressions, reach, exits, replies, taps_forward, taps_back, navigation_click_forward, navigation_click_back) | {data: [{title, description, values: [{value}]}]} | instagram_basic | — | get_story_insights |
| [ ] | `instagram.media.insights_values` | read | GET /{media_id}/insights?metric=name_action,name_profile_visits | Obtiene acciones específicas: clics en nombre, visitas de perfil, botón contacto | media_id, metric (name_profile_visits, website_clicks, phone_call_clicks, text_message_clicks, email_clicks) | {data: [{name, values: [{value, end_time}]}]} | instagram_basic | — | — |

### Menciones (Media donde fue mencionado el usuario) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.mentions.list` | read | GET /me/mentioned_media | Lista publicaciones donde la cuenta ha sido mencionada | — | {data: [{id, caption, media_type, permalink, timestamp, username}], paging} | instagram_basic | — | get_mentions |
| [ ] | `instagram.mentions.get_notifications` | read | GET /{user_id}/mentioned_comment_threads | Obtiene notificaciones de menciones en comentarios | user_id | {data: [{id, comment_id, media_id, username, timestamp}], paging} | instagram_basic | — | — |

### Hashtags (Buscar, obtener info, media reciente, historial) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.hashtags.search` | read | GET /ig_hashtag_search | Busca un hashtag por nombre y devuelve su ID | q (nombre del hashtag sin #), user_id (requerido) | {data: [{id, name}]} | instagram_business_basic | — | — |
| [ ] | `instagram.hashtags.get` | read | GET /{hashtag_id} | Obtiene información de un hashtag: nombre, ID | hashtag_id | {id, name} | instagram_business_basic | — | get_hashtag_info |
| [ ] | `instagram.hashtags.recent_media` | read | GET /{hashtag_id}/recent_media | Lista media publicada con un hashtag en las últimas 24h | hashtag_id, user_id (requerido), fields (id, caption, media_type) | {data: [{id, caption, media_type, timestamp}], paging} | instagram_business_basic | — | — |
| [ ] | `instagram.hashtags.recently_searched` | read | GET /{user_id}/recently_searched_hashtags | Obtiene hashtags buscados por el usuario en los últimos 7 días | user_id | {data: [{id, name, search_count}]} | instagram_business_basic | — | — |

### Mensajes Directos (DM, Conversaciones, Mensajes, Auto-respuesta) (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.messages.list_conversations` | read | GET /me/conversations | Lista conversaciones activas (chats) con paginación | — | {data: [{id, participants: [{id, username}], updated_time, senders, snippet}], paging} | igb_manage_messages | — | get_conversations |
| [ ] | `instagram.messages.list` | read | GET /{conversation_id}/messages | Lista todos los mensajes de una conversación | conversation_id, fields (id, from, to, message, created_time, type, media_product_type) | {data: [{id, from: {id, email, name}, to: {data: [{id}]}, message, created_time}], paging} | igb_manage_messages | — | get_messages |
| [ ] | `instagram.messages.get` | read | GET /{message_id} | Obtiene detalles de un mensaje | message_id | {id, from, to, message, created_time, status_type} | igb_manage_messages | — | — |
| [ ] | `instagram.messages.send` | create | POST /me/messages | Envía un mensaje de texto a un usuario (solo en ventana 24h después de que el usuario iniciara contacto) | recipient_id, message (máx 1000 bytes, UTF-8) | {message_id} | igb_manage_messages | E | send_message |
| [ ] | `instagram.messages.send_with_media` | create | POST /me/messages | Envía un mensaje con imagen/video/audio/PDF (hasta 10 imágenes o 1 archivo por mensaje) | recipient_id, image_url / video_url / file_url / audio_url | {message_id} | igb_manage_messages | E | — |
| [ ] | `instagram.messages.send_with_sticker` | create | POST /me/messages | Envía un sticker de corazón o emoji reaction | recipient_id, sticker_emoji | {message_id} | igb_manage_messages | E | — |
| [ ] | `instagram.messages.send_media_share` | create | POST /me/messages | Comparte una publicación propia de Instagram en DM | recipient_id, media_id | {message_id} | igb_manage_messages | E | — |
| [ ] | `instagram.messages.mark_read` | update | POST /me/messages | Marca una conversación o mensaje como leído | conversation_id o recipient_id, sender_action=mark_seen | {success} | igb_manage_messages | — | mark_message_read |
| [ ] | `instagram.messages.reply` | create | POST /me/messages | Envía una respuesta dentro de una conversación existente | conversation_id, message | {message_id} | igb_manage_messages | E | reply_message |
| [ ] | `instagram.messages.get_typing_indicator` | read | GET /{user_id}/typing_indicator | Obtiene si un usuario está escribiendo en la conversación | user_id | {is_typing} | igb_manage_messages | — | — |
| [ ] | `instagram.messages.set_typing_indicator` | update | POST /me/messages | Muestra al otro usuario que estás escribiendo | recipient_id, sender_action=typing_on / typing_off | {success} | igb_manage_messages | — | — |
| [ ] | `instagram.messages.auto_reply` | create | POST /me/message_auto_replies | Configura respuesta automática para DMs (activa automáticamente fuera de horario/ventana 24h) | message (texto de respuesta), enabled (true/false) | {success} | igb_manage_messages | — | set_auto_reply |
| [ ] | `instagram.messages.auto_reply_get` | read | GET /me/message_auto_replies | Obtiene configuración actual de respuesta automática | — | {data: [{message, enabled}]} | igb_manage_messages | — | — |

### Seguidores y Relaciones (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.account.followers_get` | read | GET /{user_id}/followers | Obtiene lista de seguidores (solo info pública: ID, username) | user_id | {data: [{id, username}], paging} | instagram_business_basic | — | — |
| [ ] | `instagram.account.follows_get` | read | GET /{user_id}/follows | Obtiene lista de cuentas que sigue | user_id | {data: [{id, username}], paging} | instagram_business_basic | — | — |

### Búsqueda y Descubrimiento (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.media.search_by_location` | read | GET /{location_id}/media | Obtiene media publicada en una ubicación | location_id | {data: [{id, caption, media_type, timestamp}], paging} | instagram_business_basic | — | — |
| [ ] | `instagram.media.search_hashtag_media` | read | GET /{hashtag_id}/recent_media | Busca media reciente de un hashtag específico (últimas 24h) | hashtag_id, user_id | {data: [{id, caption, media_type, timestamp}], paging} | instagram_business_basic | — | — |
| [ ] | `instagram.hashtags.top_media` | read | GET /{hashtag_id}/top_media | Obtiene media más popular de un hashtag en los últimos 7 días | hashtag_id, user_id | {data: [{id, caption, like_count, comments_count}], paging} | instagram_business_basic | — | — |

### Avanzado: Webhooks y Configuración (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `instagram.webhooks.subscribe` | create | POST /{app_id}/subscriptions | Suscribe la app a webhooks de Instagram (comentarios, mensajes, menciones) | object (instagram), callback_url, fields (comments, messages, mentions) | {success} | igb_manage_content | — | — |
| [ ] | `instagram.webhooks.unsubscribe` | delete | DELETE /{app_id}/subscriptions | Desuscribe la app de webhooks | object, callback_url | {success} | igb_manage_content | — | — |
| [ ] | `instagram.webhooks.verify` | read | GET /webhook | Verifica webhook callbacks (verifica challenge token) | hub.challenge, hub.verify_token | {hub.challenge} | igb_manage_content | — | — |
