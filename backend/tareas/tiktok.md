# Tareas: TikTok

- **Funciones catalogadas:** 20 · **Hechas:** 0 · **Pendientes:** 20 · App sin herramientas viejas
- **Documentación oficial:** https://developers.tiktok.com/doc/overview
- **Fuentes que consultó el catálogo:** https://developers.tiktok.com/docs/en/tiktok-api-v2-introduction https://developers.tiktok.com/docs/en/display-api-overview https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content https://developers.tiktok.com/docs/en/login-kit-qr-code-authorization https://developers.tiktok.com/docs/en/login-kit-manage-user-access-tokens https://developers.tiktok.com/docs/en/tiktok-api-v2-rate-limit https://developers.tiktok.com/docs/en/tiktok-api-scopes https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info https://developers.tiktok.com/doc/about-research-api/
- **Paginación típica:** cursor; /v2/video/list y /v2/video/query devuelven cursor en respuesta para siguiente página
- **Qué no se pudo verificar:** endpoint exacto y parámetros de /v2/post/publish/status/fetch (documentación menciona que existe pero detalles limitados); si existe Analytics API oficial para cuentas personales (Research API tiene /analytics pero solo para investigadores); operaciones de comentarios/me gusta en Display API (no confirmado que existan para usuarios regulares); embargo si Research API endpoints exactos diferenciados (/videos/list vs /videos/query vs otros)
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/tiktok/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `tiktok`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `tiktok` |
| Variables del `.env` que necesitas | TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/tiktok/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `tiktok.user_info.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código (Login Kit QR); intercambia código por access_token y refresh_token usando client_key |
| Duración del token (según el catálogo) | 86400 segundos (24 horas); crítico: las integraciones fallan si no se implementa refresco automático |
| Refresco (según el catálogo) | sí, refresh_token dura 365 días (31536000 segundos); se renueva con grant_type=refresh_token en POST /v2/oauth/token/; si expira o revoca el usuario, requiere reautenticación |
| Permisos (según el catálogo) | user.info.basic (perfil básico: ID, avatar, display_name), user.info.profile (bio, enlaces, verificación), user.info.stats (conteos: seguidores, me gusta), video.list (videos públicos), video.publish (publicar directo), video.upload (crear borradores), research.data.basic (datos públicos para investigación académica) |
| Restricciones de acceso | video.publish requiere auditoría completa de la app (2-4 semanas, demostración, política de privacidad, verificación de dominio). Sin auditoría, contenido se restringe a privado. Research API solo para instituciones académicas/nonprofits aprobadas. Cuentas de usuario solo; no personas jurídicas. |
| Límites de ritmo | Display API: 600 req/min (/v2/user/info, /v2/video/list, /v2/video/query). Content Posting: 6 req/min para video/photo init (video.publish/upload), 20 req/min para creator_info query, 30 req/min para status/fetch. Máx. 25 videos por 24h por cuenta. Ventana de cálculo: 1 minuto deslizante (rolling window). |
| Notas de esta app | Usa `client_key` (no `client_id`). |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/tiktok/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> tiktok`. | Cuenta con `provider: tiktok`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/tiktok.user_info.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> tiktok <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de TikTok. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/tiktok.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Usuario y Autenticación (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.user_info.get` ★ | read | GET /v2/user/info/ | Obtiene perfil básico del usuario autenticado | none | {open_id, display_name, avatar_url, profile_deep_link, bio_description} | user.info.basic | — | — |
| [ ] | `tiktok.user_info.profile` | read | GET /v2/user/info/ | Obtiene información extendida de perfil (bio, enlaces, verificación) | none | {open_id, display_name, avatar_url, bio, links, verified} | user.info.profile | — | — |
| [ ] | `tiktok.user.stats` | read | GET /v2/user/info/ | Obtiene estadísticas de la cuenta (seguidores, seguidos, me gusta, videos) | none | {follower_count, following_count, likes_count, video_count} | user.info.stats | — | — |

### Creador e Información de Publicación (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.creator_info.get` | read | POST /v2/post/publish/creator_info/query/ | Obtiene información de perfil y permisos de creador para renderizar opciones de privacidad y configuración de interacción | none | {creator_avatar_url, creator_username, creator_nickname, privacy_level_options, comment_disabled, duet_disabled, stitch_disabled, max_video_duration} | video.publish | — | — |

### Videos: Lectura y Listado (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.video.list` | read | POST /v2/video/list/ | Lista videos recientes del usuario autenticado ordenados por fecha de creación descendente | max_count,cursor | {videos:[{id, title, description, duration, cover_image_url, share_url, create_time}], cursor} | video.list | — | — |
| [ ] | `tiktok.video.query` | read | POST /v2/video/query/ | Obtiene metadatos de videos específicos por IDs (hasta 20 a la vez) | video_ids | {videos:[{id, title, description, duration, cover_image_url, share_url, create_time, play_count, like_count, comment_count, share_count}]} | video.list | — | — |

### Videos: Publicación Directa (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.video.publish` | create | POST /v2/post/publish/video/init/ | Publica video directamente a la cuenta del usuario desde URL o archivo; aparece en su feed al instante | source_info,post_info | {publish_id, upload_url} | video.publish | I | — |
| [ ] | `tiktok.video.publish_with_url` | create | POST /v2/post/publish/video/init/ | Publica video directamente desde URL verificada (PULL_FROM_URL) | video_url,title,privacy_level,post_info | {publish_id} | video.publish | I | — |
| [ ] | `tiktok.video.publish_from_file` | create | POST /v2/post/publish/video/init/ | Publica video directamente desde archivo local con carga chunked | video_file,title,privacy_level,post_info | {publish_id, upload_url} | video.publish | I | — |

### Videos: Carga a Borrador (Draft) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.video.upload` | create | POST /v2/post/publish/inbox/video/init/ | Carga video a borrador para que usuario lo edite y publique en TikTok; notifica usuario en inbox | source_info,video_size,chunk_size | {publish_id, upload_url, expiration_timestamp} | video.upload | — | — |
| [ ] | `tiktok.video.upload_chunk` | create | PUT {upload_url} | Envía fragmento de video al servidor durante carga chunked | chunk_data,content_range | {publish_id} | video.upload | — | — |
| [ ] | `tiktok.video.status` | read | POST /v2/post/publish/status/fetch/ | Consulta estado de video publicado/cargado (procesamiento, completado, fallido) | publish_id | {status, error_code, error_message} | video.publish,video.upload | — | — |

### Fotos: Publicación Directa (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.photo.publish` | create | POST /v2/post/publish/content/init/ | Publica fotos directamente a la cuenta (hasta 35 imágenes); aparecen en feed al instante | source_info,post_info,media_type | {publish_id} | video.publish | I | — |
| [ ] | `tiktok.photo.publish_direct` | create | POST /v2/post/publish/content/init/ | Publica foto directamente con post_mode=DIRECT_POST | photo_urls,title,privacy_level,post_info | {publish_id} | video.publish | I | — |

### Fotos: Carga a Borrador (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.photo.upload` | create | POST /v2/post/publish/content/init/ | Carga fotos a borrador con post_mode=MEDIA_UPLOAD para que usuario las edite en TikTok | source_info,photo_urls,post_info | {publish_id} | video.upload | — | — |

### Investigación (Académica/Nonprofit - Acceso Restringido) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `tiktok.research_videos.list` | read | GET /research/2024-06/videos | Lista videos públicos con datos de engagement (asignado a investigadores aprobados) | keywords,region,count,cursor | {videos:[{id, title, description, create_time, play_count, like_count, comment_count}], cursor} | research.data.basic | — | — |
| [ ] | `tiktok.research_videos.query` | read | POST /research/2024-06/videos/query | Obtiene metadatos de videos específicos con restricciones de privacidad respetadas | video_ids | {videos:[{id, title, captions, create_time, play_count, like_count, comment_count}]} | research.data.basic | — | — |
| [ ] | `tiktok.research_comments.list` | read | GET /research/2024-06/comments | Lista comentarios públicos de videos | video_id,count,cursor | {comments:[{id, text, create_time, like_count, reply_count}], cursor} | research.data.basic | — | — |
| [ ] | `tiktok.research_accounts.list` | read | GET /research/2024-06/accounts | Lista cuentas públicas con datos de perfil agregados | username,region,count,cursor | {accounts:[{open_id, display_name, follower_count, following_count, video_count, like_count}], cursor} | research.data.basic | — | — |
| [ ] | `tiktok.research_accounts.search` | read | GET /research/2024-06/accounts/search | Busca cuentas públicas por criterios | query,region,count | {accounts:[{open_id, username, display_name, follower_count, bio}]} | research.data.basic | — | — |
