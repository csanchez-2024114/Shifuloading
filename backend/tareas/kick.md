# Tareas: Kick

- **Funciones catalogadas:** 32 · **Hechas:** 0 · **Pendientes:** 32 · App sin herramientas viejas
- **Documentación oficial:** https://docs.kick.com
- **Fuentes que consultó el catálogo:** https://docs.kick.com/apis/users.md https://docs.kick.com/apis/channels.md https://docs.kick.com/apis/chat.md https://docs.kick.com/apis/livestreams.md https://docs.kick.com/apis/categories.md https://docs.kick.com/apis/moderation.md https://docs.kick.com/apis/channel-rewards.md https://docs.kick.com/apis/public-key.md https://docs.kick.com/apis/kicks.md https://docs.kick.com/apis/ads.md https://docs.kick.com/llms-full.txt https://docs.kick.com/getting-started/generating-tokens-oauth2-flow.md https://docs.kick.com/getting-started/scopes.md https://docs.kick.com/events/webhook-security.md https://docs.kick.com/events/event-types.md https://docs.kick.com/drops/public-api.md
- **Paginación típica:** Cursor-based en v2 endpoints (limit + cursor). Offset/page en endpoints deprecated v1. Algunos endpoints sin paginación (limitado a N resultados)
- **Qué no se pudo verificar:** Token introspect en /public/v1/token/introspect marcado como deprecated en docs; no verificamos si /oauth/token/introspect es el reemplazo directo. Drops webhook endpoint descrito en guía pero no confirmamos si admite GET/LIST de webhooks propio (solo menciona POST para claims). No encontramos endpoints para administración de aplicaciones (crear/eliminar apps) en documentación oficial
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/kick/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `kick`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `kick` |
| Variables del `.env` que necesitas | KICK_CLIENT_ID, KICK_CLIENT_SECRET, KICK_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/kick/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `kick.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.1 con PKCE obligatorio. Authorization Code (flujo de usuario con scopes) y Client Credentials (token de app). Redirección a https://id.kick.com/oauth/authorize, intercambio en https://id.kick.com/oauth/token |
| Duración del token (según el catálogo) | Token de acceso caduca en el tiempo indicado por `expires_in` en la respuesta (especifico del token, típicamente corto); requiere refresh token para renovación |
| Refresco (según el catálogo) | Sí. Refresh token devuelto en flujos de Authorization Code y Client Credentials. POST a https://id.kick.com/oauth/token con grant_type=refresh_token |
| Permisos (según el catálogo) | user:read (info usuario), channel:read (info canal), channel:write (actualizar metadata), channel:rewards:read (leer rewards), channel:rewards:write (crear/editar rewards), chat:write (enviar mensajes), streamkey:read (stream key), events:subscribe (webhooks), moderation:ban (baneos), moderation:chat_message:manage (moderar chat), kicks:read (leaderboard), ads:read (info anuncios), ads:write (crear anuncios) |
| Restricciones de acceso | Apps deben estar registradas. Unverified apps limitadas a 1000 suscripciones en chat.message.sent; verified apps hasta 10000. Webhooks se deshabilitan automáticamente tras fallo durante >1 día. Solo organizaciones registradas (email a developers@kick.com) pueden usar Drops API |
| Límites de ritmo | Paginación en endpoints v2 con cursores (típicamente limit 1-1000, default variable). Chat máx 500 caracteres. Bans/timeouts 1-10080 minutos. Channel rewards máx 50. Drops claims update máx 100 por request. Webhooks: firma RSA-SHA256 en header Kick-Event-Signature |
| Notas de esta app | OAuth 2.1 con PKCE. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/kick/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> kick`. | Cuenta con `provider: kick`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/kick.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> kick <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Kick. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/kick.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Users / Usuarios (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.user.get` ★ | read | GET /public/v1/users | Obtener información del usuario autenticado o por array de IDs | (vacío para usuario actual) o id (array) | {user_id, name, email, profile_picture} | user:read | — | — |
| [ ] | `kick.user.introspect` | read | POST /public/v1/token/introspect | Verificar metadatos del token (deprecated) | (vacío, via header) | {active, client_id, token_type, scope, exp} | (ninguno) | — | — |

### Channels / Canales (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.channel.get` | read | GET /public/v1/channels | Obtener info de canales por broadcaster_user_id o slug | broadcaster_user_id o slug (array, máx 50) | {broadcaster_user_id, slug, stream_title, category, is_live, viewer_count, thumbnail} | channel:read | — | — |
| [ ] | `kick.channel.update` | update | PATCH /public/v1/channels | Actualizar metadata del livestream de un canal | stream_title, category_id, custom_tags (opcional) | 204 No Content | channel:write | E | — |

### Chat (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.chat.send` | create | POST /public/v1/chat | Enviar mensaje de chat como usuario o bot | content, type, broadcaster_user_id, reply_to_message_id (opcional) | {message_id, is_sent} | chat:write | E, I | — |
| [ ] | `kick.chat.delete` | delete | DELETE /public/v1/chat/{message_id} | Eliminar un mensaje de chat | message_id (UUID) | 204 No Content | moderation:chat_message:manage | I | — |

### Livestreams / Transmisiones (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.livestream.list` | read | GET /public/v2/livestreams | Listar livestreams activos (paginado) | category_id, language_code, limit, cursor | {livestreams array, cursor} | (ninguno) | — | — |
| [ ] | `kick.livestream.list_legacy` | read | GET /public/v1/livestreams | Listar livestreams por broadcaster/categoría/idioma (deprecated) | broadcaster_user_id, category_id, language, limit, sort | {livestreams array} | (ninguno) | — | — |
| [ ] | `kick.livestream.list_user` | read | GET /public/v1/users/livestreams | Obtener livestreams activos para array de user_id | user_id (array, máx 100) | {livestreams array} | (ninguno) | — | — |
| [ ] | `kick.livestream.get_stats` | read | GET /public/v1/livestreams/stats | Obtener estadísticas de livestreams | (ninguno) | {count} | (ninguno) | — | — |

### Categories / Categorías (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.category.list` | read | GET /public/v2/categories | Listar categorías con filtros y paginación | cursor, limit, name, tag, id (array) | {categories array, cursor} | (ninguno) | — | — |
| [ ] | `kick.category.search` | read | GET /public/v1/categories | Buscar categorías por palabra clave (deprecated) | q (búsqueda), page | {categories array} | (ninguno) | — | — |
| [ ] | `kick.category.get` | read | GET /public/v1/categories/{category_id} | Obtener detalles de una categoría (deprecated) | category_id | {id, name, tags, thumbnail, viewer_count} | (ninguno) | — | — |

### Channel Rewards / Recompensas de Canal (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.channel_reward.list` | read | GET /public/v1/channels/rewards | Listar recompensas de puntos de canal (máx 50) | (ninguno) | {rewards array: id, title, cost, description, is_enabled} | channel:rewards:read | — | — |
| [ ] | `kick.channel_reward.create` | create | POST /public/v1/channels/rewards | Crear nueva recompensa de puntos | title, cost, description (opcional), background_color, is_enabled, is_user_input_required | {id, title, cost, description...} | channel:rewards:write | E | — |
| [ ] | `kick.channel_reward.update` | update | PATCH /public/v1/channels/rewards/{id} | Actualizar configuración de recompensa | reward_id (ULID), title o cost o description o flags | {id, title, cost...} | channel:rewards:write | — | — |
| [ ] | `kick.channel_reward.delete` | delete | DELETE /public/v1/channels/rewards/{id} | Eliminar recompensa de puntos | reward_id (ULID) | 204 No Content | channel:rewards:write | I | — |
| [ ] | `kick.channel_reward.redemption_list` | read | GET /public/v1/channels/rewards/redemptions | Obtener redenciones con filtros y paginación | reward_id, status, id, cursor | {redemptions grouped, redeemer, status} | channel:rewards:read | — | — |
| [ ] | `kick.channel_reward.redemption_accept` | update | POST /public/v1/channels/rewards/redemptions/accept | Aceptar redenciones (máx 25 por request) | ids (array ULID) | {failed redemptions array} | channel:rewards:write | E | — |
| [ ] | `kick.channel_reward.redemption_reject` | update | POST /public/v1/channels/rewards/redemptions/reject | Rechazar redenciones (máx 25 por request) | ids (array ULID) | {failed redemptions array} | channel:rewards:write | — | — |

### Moderation / Moderación (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.moderation.ban` | create | POST /public/v1/moderation/bans | Banear o timeout a usuario | broadcaster_user_id, user_id, duration (minutos 1-10080, opcional), reason | {data} | moderation:ban | E, I | — |
| [ ] | `kick.moderation.unban` | delete | DELETE /public/v1/moderation/bans | Desbanear o remover timeout | broadcaster_user_id, user_id | {data} | moderation:ban | I | — |

### KICKs / Tokens KICK (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.kicks.leaderboard` | read | GET /public/v1/kicks/leaderboard | Obtener leaderboard de KICK regalados | top (1-100, default 10) | {lifetime, month, week arrays: rank, user_id, username, gifted_amount} | kicks:read | — | — |

### Ads / Anuncios (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.ads.ad_break_create` | create | POST /public/v1/ads/ad-break | Crear ad break en canal autenticado | break_duration_seconds (7-90), id (UUID) | 202 Accepted con {id, remaining_ad_breaks} | ads:write | E | — |
| [ ] | `kick.ads.ad_break_status` | read | GET /public/v1/ads/ad-break-status | Obtener estado de ad breaks | (ninguno) | {active_breaks, ads_blocked, auto_ads_active, rate_limits, enrollment_status} | ads:read | — | — |
| [ ] | `kick.ads.enroll` | create | POST /public/v1/ads/enroll | Enrollarse en programa de anuncios | (ninguno) | 200 OK confirmation | ads:write | E | — |

### Public Key / Clave Pública (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.public_key.get` | read | GET /public/v1/public-key | Obtener clave pública para verificar firmas de webhook | (ninguno) | {message, data: {public_key}} | (ninguno) | — | — |

### Events / Eventos y Webhooks (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.event.subscription_list` | read | GET /public/v1/events/subscriptions | Listar suscripciones a eventos | (opcionales filtros broadcaster_user_id) | {subscriptions array} | events:subscribe | — | — |
| [ ] | `kick.event.subscription_create` | create | POST /public/v1/events/subscriptions | Suscribirse a eventos/webhooks | event_type, transport, transport_config (url, headers) | 201 Created con subscription | events:subscribe | E | — |
| [ ] | `kick.event.subscription_delete` | delete | DELETE /public/v1/events/subscriptions | Eliminar suscripción a evento | subscription_id | 204 No Content | events:subscribe | — | — |

### Drops / Campañas de Recompensas (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `kick.drops.claim_list` | read | GET /public/v1/drops/claims | Obtener claims de campañas Drops | campaign_id, limit, cursor, user_id, claim_id, external_status | {claims array, cursor} | (app token de org) | — | — |
| [ ] | `kick.drops.claim_update` | update | PATCH /public/v1/drops/claims | Actualizar external_status de claims (máx 100) | claims array: claim_id, external_status | 204 No Content | (app token de org) | — | — |
