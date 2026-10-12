# Tareas: Facebook

- **Funciones catalogadas:** 70 · **Hechas:** 0 · **Pendientes:** 70 · **Herramientas viejas a migrar:** 1 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.facebook.com/docs/graph-api
- **Fuentes que consultó el catálogo:** https://developers.facebook.com/docs/graph-api https://developers.facebook.com/docs/graph-api/reference/user https://developers.facebook.com/docs/graph-api/reference/page https://developers.facebook.com/docs/graph-api/reference/post https://developers.facebook.com/docs/graph-api/reference/photo https://developers.facebook.com/docs/graph-api/reference/video https://developers.facebook.com/docs/graph-api/reference/comment https://developers.facebook.com/docs/graph-api/reference/conversation https://developers.facebook.com/docs/graph-api/reference/message https://developers.facebook.com/docs/graph-api/reference/event https://developers.facebook.com/docs/graph-api/reference/album https://developers.facebook.com/docs/graph-api/reference/insights https://developers.facebook.com/docs/graph-api/reference/object/likes https://developers.facebook.com/docs/permissions/reference https://developers.facebook.com/docs/facebook-login/access-tokens
- **Paginación típica:** cursor-based (cursor, after, before). Parámetros: limit (por defecto 25), fields, date_format.
- **Qué no se pudo verificar:** Refresco exacto de access tokens de página (documentación dice "no vencen" pero proceso no está claro); estructura exacta de reset de permisos por token; algunos endpoints de draft/versioning en Posts; datos completos de rate limit a nivel de usuario.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/facebook/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `facebook`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `facebook` |
| Variables del `.env` que necesitas | FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, FACEBOOK_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/facebook/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `facebook.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 de Meta: el usuario autoriza la app y recibe un code, que se intercambia por access token (bearer); tokens cortos (1-2 horas) o largos (60 días) según flujo. |
| Duración del token (según el catálogo) | Tokens cortos: 1-2 horas; tokens largos: ~60 días; pueden expirar sin aviso. Los de página no vencen si se obtienen de un token de usuario largo. |
| Refresco (según el catálogo) | Sí. GET /me/permissions con el token actual para refrescar; o hacer login de nuevo. Los SDKs de móvil obtienen tokens largos automáticamente. |
| Permisos (según el catálogo) | public_profile (perfil básico, auto), pages_show_list (listar páginas), pages_manage_posts (crear/editar posts), pages_read_engagement (leer interacciones), pages_read_user_content (leer contenido de usuarios), pages_manage_engagement (gestionar comentarios/reacciones), pages_manage_metadata (webhooks/ajustes), pages_messaging (mensajes Messenger), read_insights (analítica), email (correo principal). Muchos requieren app review. |
| Restricciones de acceso | Desarrollo: modo sandbox con test-users y datos limitados. Producción: app review obligatorio para scopes sensibles (pages_manage_posts, pages_messaging, etc.). Business Verification requerido para publish. Webhooks requieren HTTPS. Límites por plan de acceso (Limited/Standard/Full). Algunos permisos ya retirados (user_actions:news, user_subscriptions). |
| Límites de ritmo | Platform Rate Limits: 200 × DAU (usuarios activos diarios) por hora a nivel de app; no publicado a nivel de usuario. Marketing API: 100,000 por hora si Full Access, 300 si Dev tier, + 40 × anuncios activos. |
| Notas de esta app | Token largo de Meta (no se renueva solo). |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/facebook/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> facebook`. | Cuenta con `provider: facebook`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/facebook.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> facebook <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Facebook. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/facebook.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### User / Perfil (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.user.get` ★ | read | GET /me | Obtiene datos del perfil del usuario autenticado | (ninguno; usa token) | {id, name, email, picture, locale, timezone, friends} | public_profile | — | get_account_details_facebook |
| [ ] | `facebook.user_accounts.list` | read | GET /me/accounts | Lista todas las páginas y aplicaciones que gestiona el usuario | (ninguno; usa token) | lista de {id, name, access_token, category, category_list} | pages_show_list | — | — |
| [ ] | `facebook.user_picture.get` | read | GET /{user_id}/picture | Obtiene foto de perfil del usuario en tamaño especificado | size (small, normal, large, square) | {height, width, is_silhouette, url} | public_profile | — | — |
| [ ] | `facebook.user_permissions.list` | read | GET /me/permissions | Lista permisos otorgados a la app por el usuario | (ninguno) | lista de {permission, status} | (ninguno) | — | — |

### Pages / Páginas (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.page.get` | read | GET /{page_id} | Obtiene información de una página de Facebook | page_id | {id, name, about, category, website, phone, email, followers_count, fan_count, link} | (ninguno) | — | — |
| [ ] | `facebook.page.update` | update | POST /{page_id} | Actualiza detalles de una página (nombre, descripción, contacto, horarios) | name, about, phone, website, city, state, zip, country, description | {success: true} o id | pages_manage_metadata | — | — |
| [ ] | `facebook.page_conversations.list` | read | GET /{page_id}/conversations | Lista todas las conversaciones de Messenger de la página | limit, fields | lista de {id, name, participants, updated_time, message_count} | pages_messaging | — | — |
| [ ] | `facebook.page_roles.list` | read | GET /{page_id}/roles | Lista todos los usuarios con rol en la página (admin, editor, moderator, analyst) | (ninguno) | lista de {user: {id, name}, role} | pages_manage_metadata | — | — |
| [ ] | `facebook.page_assigned_users.list` | read | GET /{page_id}/assigned_users | Lista usuarios asignados a la página | (ninguno) | lista de {id, name, role} | pages_manage_metadata | — | — |
| [ ] | `facebook.page_settings.list` | read | GET /{page_id}/settings | Obtiene ajustes de la página (notificaciones, mensajes, etc.) | (ninguno) | lista de {setting_key, value} | pages_manage_metadata | — | — |

### Feed / Publicaciones (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.feed.list` | read | GET /{page_id}/feed | Lista posts publicados en el feed de una página | page_id, limit, fields, after | lista de {id, message, created_time, from, permalink_url, likes.summary(true), comments.summary(true)} | pages_read_engagement | — | — |
| [ ] | `facebook.feed.create` | create | POST /{page_id}/feed | Publica un nuevo post en el feed de la página | message, link, picture, name, description, scheduled_publish_time | {id, success: true} | pages_manage_posts | E, I | — |
| [ ] | `facebook.feed_user.list` | read | GET /{user_id}/feed | Lista posts en el timeline del usuario | user_id, limit, fields | lista de {id, message, created_time, type, permalink_url} | (ninguno/user_posts) | — | — |
| [ ] | `facebook.post.get` | read | GET /{post_id} | Obtiene información de un post específico | post_id, fields | {id, message, created_time, from, link, type, status_type, attachments} | (ninguno) | — | — |
| [ ] | `facebook.post.update` | update | POST /{post_id} | Actualiza un post (solo mensaje, no multimedia; o es un post de empresa) | post_id, message | {success: true} | pages_manage_posts | — | — |
| [ ] | `facebook.post.delete` | delete | DELETE /{post_id} | Elimina un post | post_id | {success: true} | pages_manage_posts | I | — |
| [ ] | `facebook.story.create` | create | POST /{page_id}/feed | Publica una historia/story (similar a post, formato especial) | media_source o video_data, message | {id, success: true} | pages_manage_posts | E, I | — |

### Photos / Fotos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.photo.list` | read | GET /{page_id}/photos | Lista todas las fotos en el álbum de la página o subidas | page_id, album_id, limit, fields | lista de {id, name, picture, created_time, height, width, images} | (ninguno) | — | — |
| [ ] | `facebook.photo.get` | read | GET /{photo_id} | Obtiene detalles de una foto individual | photo_id, fields | {id, name, picture, created_time, height, width, source, images, likes, comments} | (ninguno) | — | — |
| [ ] | `facebook.photo.create` | create | POST /{page_id}/photos | Sube una foto a la página (max 10MB; PNG, JPG, GIF) | photo_data o file, message, caption, place | {id, post_id} | pages_manage_posts | E | — |
| [ ] | `facebook.photo.delete` | delete | DELETE /{photo_id} | Elimina una foto | photo_id | {success: true} | pages_manage_posts | I | — |
| [ ] | `facebook.photo_like.create` | create | POST /{photo_id}/likes | Da like a una foto | photo_id | {success: true} | pages_manage_engagement | E | — |
| [ ] | `facebook.photo_like.delete` | delete | DELETE /{photo_id}/likes | Quita el like propio de una foto | photo_id | {success: true} | pages_manage_engagement | — | — |

### Videos / Videos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.video.list` | read | GET /{page_id}/videos | Lista todos los videos en la página | page_id, limit, fields | lista de {id, description, created_time, source, thumbnail, embed_html} | (ninguno) | — | — |
| [ ] | `facebook.video.get` | read | GET /{video_id} | Obtiene detalles de un video individual | video_id, fields | {id, name, description, created_time, source, updated_time, thumbnail, format, embed_html} | (ninguno) | — | — |
| [ ] | `facebook.video.create` | create | POST /{page_id}/videos | Sube un video a la página (máximo según plan, típicamente 4GB) | video_data o file, title, description, scheduled_publish_time | {id, post_id} | publish_video | E | — |
| [ ] | `facebook.video.delete` | delete | DELETE /{video_id} | Elimina un video | video_id | {success: true} | publish_video | I | — |
| [ ] | `facebook.video_live.create` | create | POST /{page_id}/live_videos | Inicia una transmisión en vivo | title, description, live_audience | {id, stream_url, secure_stream_url, video_id} | publish_video | E, I | — |
| [ ] | `facebook.video_like.create` | create | POST /{video_id}/likes | Da like a un video | video_id | {success: true} | pages_manage_engagement | E | — |

### Comments / Comentarios (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.comment.list` | read | GET /{post_id}/comments | Lista comentarios en un post | post_id, limit, fields, after | lista de {id, message, created_time, from, user_likes, object} | pages_read_engagement | — | — |
| [ ] | `facebook.comment.get` | read | GET /{comment_id} | Obtiene detalles de un comentario individual | comment_id, fields | {id, message, created_time, from, attachment, user_likes, private_reply_conversation} | pages_read_engagement | — | — |
| [ ] | `facebook.comment.create` | create | POST /{post_id}/comments | Crea un nuevo comentario en un post (solo texto o con adjuntos) | post_id, message, attachment_id | {id, success: true} | pages_manage_engagement | E | — |
| [ ] | `facebook.comment.update` | update | POST /{comment_id} | Actualiza el contenido de un comentario existente | comment_id, message | {success: true} | pages_manage_engagement | — | — |
| [ ] | `facebook.comment.delete` | delete | DELETE /{comment_id} | Elimina un comentario | comment_id | {success: true} | pages_manage_engagement | I | — |
| [ ] | `facebook.comment.hide` | update | POST /{comment_id} | Oculta un comentario a los demás usuarios | comment_id, is_hidden | {success: true} | pages_manage_engagement | — | — |
| [ ] | `facebook.comment_like.create` | create | POST /{comment_id}/likes | Da like a un comentario | comment_id | {success: true} | pages_manage_engagement | E | — |
| [ ] | `facebook.comment_like.delete` | delete | DELETE /{comment_id}/likes | Quita el like propio de un comentario | comment_id | {success: true} | pages_manage_engagement | — | — |

### Conversations / Conversaciones (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.conversation.list` | read | GET /{page_id}/conversations | Lista conversaciones de Messenger | page_id, limit, fields, after, user_id | lista de {id, name, updated_time, can_reply, participants, message_count} | pages_messaging | — | — |
| [ ] | `facebook.conversation.get` | read | GET /{conversation_id} | Obtiene información de una conversación específica | conversation_id, fields | {id, name, is_owner, participants, updated_time, message_count, snippet} | pages_messaging | — | — |
| [ ] | `facebook.conversation_messages.list` | read | GET /{conversation_id}/messages | Lista mensajes en una conversación | conversation_id, limit, fields, after | lista de {id, message, created_time, from, story, attachments} | pages_messaging | — | — |

### Messages / Mensajes (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.message.get` | read | GET /{message_id} | Obtiene detalles de un mensaje individual | message_id, fields | {id, message, created_time, from, to, attachments, shares, reactions, tags} | pages_messaging | — | — |
| [ ] | `facebook.message.create` | create | POST /{conversation_id}/messages | Envía un mensaje en una conversación (requiere use Messenger Send API en realidad) | conversation_id, message, attachment_id | {success: true, job_id} | pages_messaging | E | — |
| [ ] | `facebook.messenger.send` | create | POST /me/messages | Envía mensaje a usuario/conversación (Messenger Send API) | recipient, message, attachment, quick_replies | {recipient_id, message_id} | pages_messaging | E | — |

### Reactions / Reacciones (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.reaction.list` | read | GET /{object_id}/reactions | Lista reacciones (emoji) en un objeto (post, foto, video) | object_id, type (LIKE, LOVE, WOW, HAHA, SAD, ANGRY, THANKFUL), limit | lista de {id, name, type} | pages_read_engagement | — | — |
| [ ] | `facebook.like.create` | create | POST /{object_id}/likes | Da like a un objeto (post, comentario, foto, video) | object_id | {success: true} | pages_manage_engagement | E | — |
| [ ] | `facebook.like.delete` | delete | DELETE /{object_id}/likes | Quita el like propio de un objeto | object_id | {success: true} | pages_manage_engagement | — | — |

### Events / Eventos (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.event.list` | read | GET /{page_id}/events | Lista eventos asociados a una página | page_id, limit, fields, after | lista de {id, name, description, start_time, end_time, place} | pages_read_engagement | — | — |
| [ ] | `facebook.event.get` | read | GET /{event_id} | Obtiene detalles de un evento individual | event_id, fields | {id, name, description, category, start_time, end_time, place, timezone, interested_count, attending_count, declined_count} | (ninguno) | — | — |
| [ ] | `facebook.event_attending.list` | read | GET /{event_id}/attending | Lista usuarios que asisten al evento | event_id, limit, fields | lista de {id, name, picture} | (ninguno) | — | — |
| [ ] | `facebook.event_interested.list` | read | GET /{event_id}/interested | Lista usuarios interesados en el evento | event_id, limit, fields | lista de {id, name, picture} | (ninguno) | — | — |

### Albums / Álbumes (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.album.list` | read | GET /{page_id}/albums | Lista álbumes de fotos en la página | page_id, limit, fields | lista de {id, name, created_time, updated_time, count, cover_photo, type} | (ninguno) | — | — |
| [ ] | `facebook.album.get` | read | GET /{album_id} | Obtiene información de un álbum específico | album_id, fields | {id, name, description, created_time, updated_time, count, can_upload, cover_photo, type} | (ninguno) | — | — |
| [ ] | `facebook.album_photos.list` | read | GET /{album_id}/photos | Lista fotos en un álbum | album_id, limit, fields | lista de {id, name, picture, created_time, height, width} | (ninguno) | — | — |

### Insights / Analítica (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.insight.list` | read | GET /{page_id}/insights | Obtiene métricas analíticas de la página (alcance, impresiones, fans, etc.) | page_id, metric, period (day, week, month, lifetime), fields | lista de {name, period, values: {value, end_time}} | read_insights | — | — |
| [ ] | `facebook.insight.get` | read | GET /{page_id}/insights/{metric} | Obtiene una métrica analítica específica (ej: page_views, page_fans_online) | page_id, metric, period | {name, period, values: [{value, end_time}]} | read_insights | — | — |
| [ ] | `facebook.insight_post.list` | read | GET /{post_id}/insights | Obtiene analítica de un post (alcance, impresiones, reacciones, clics) | post_id, metric | lista de {name, period, values} | read_insights | — | — |
| [ ] | `facebook.insight_video.list` | read | GET /{video_id}/insights | Obtiene analítica de un video (vistas totales, duración promedio, finalización) | video_id, metric | lista de {name, period, values} | read_insights | — | — |

### Search / Búsqueda (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.search.global` | read | GET /search | Busca objetos públicos por término: usuarios, páginas, eventos, lugares | q, type (USER, PAGE, EVENT, PLACE, PLACETOPIC), limit, fields | lista de {id, name, picture, type} | public_profile | — | — |
| [ ] | `facebook.user.search` | read | GET /search | Busca usuarios por nombre o email | q, type: USER, limit | lista de {id, name, picture} | public_profile | — | — |
| [ ] | `facebook.page.search` | read | GET /search | Busca páginas públicas por nombre | q, type: PAGE, limit | lista de {id, name, picture, category} | public_profile | — | — |
| [ ] | `facebook.event.search` | read | GET /search | Busca eventos públicos por nombre o ubicación | q, type: EVENT, center, distance, limit | lista de {id, name, start_time, place} | (ninguno) | — | — |
| [ ] | `facebook.place.search` | read | GET /search | Busca ubicaciones (restaurantes, comercios, etc.) por nombre o coordenadas | q, type: PLACE, center, distance, limit | lista de {id, name, category, location, picture} | (ninguno) | — | — |

### Avanzado / Webhooks y Configuración (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `facebook.webhook.subscribe` | create | POST /{app_id}/subscriptions | Suscribe la app a webhooks de eventos de la página (posts, comentarios, mensajes) | object, fields, callback_url, verify_token | {success: true, subscription_id} | pages_manage_metadata | — | — |
| [ ] | `facebook.webhook.list` | read | GET /{page_id}/subscribed_apps | Lista webhooks suscritos en la página | page_id | lista de {id, name, supported_fields} | pages_manage_metadata | — | — |
| [ ] | `facebook.webhook.unsubscribe` | delete | DELETE /{page_id}/subscribed_apps | Desuscribe un webhook | page_id, app_id | {success: true} | pages_manage_metadata | — | — |
| [ ] | `facebook.leadgen_form.list` | read | GET /{page_id}/leadgen_forms | Lista formularios de generación de leads (Lead Ads) | page_id | lista de {id, name, created_time, status} | pages_read_engagement | — | — |
| [ ] | `facebook.leadgen_form_leads.list` | read | GET /{form_id}/leads | Obtiene respuestas de un formulario de leads | form_id, limit | lista de {id, created_time, field_data} | leads_retrieval | — | — |
| [ ] | `facebook.call_to_action.update` | update | POST /{page_id}/call_to_action | Actualiza botón de acción (ContactUs, LearnMore, ShopNow, etc.) | call_to_action_type, call_to_action_payload | {success: true} | pages_manage_cta | — | — |
| [ ] | `facebook.auth.revoke` | delete | DELETE /{user_id}/permissions | Revoca permisos y desconecta la app | user_id, permission | {success: true} | (ninguno) | — | — |
| [ ] | `facebook.token.debug` | read | GET /debug_token | Obtiene información sobre un access token (usuario, app, scopes, vencimiento) | input_token, access_token | {data: {app_id, application, expires_at, is_valid, scopes, user_id}} | (ninguno) | — | — |

## Observaciones de las herramientas viejas

- Es la unica herramienta de Facebook y solo lee el perfil. Todo lo demas (paginas, publicaciones, mensajes) esta por definir con el producto.
- Es buena candidata a `whoami` de la app.
