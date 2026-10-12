# Tareas: Discord

- **Funciones catalogadas:** 75 · **Hechas:** 0 · **Pendientes:** 75 · App sin herramientas viejas
- **Documentación oficial:** https://docs.discord.com/developers
- **Fuentes que consultó el catálogo:** https://docs.discord.com/developers/resources/user https://docs.discord.com/developers/topics/oauth2 https://docs.discord.com/developers/resources/guild https://docs.discord.com/developers/resources/channel https://docs.discord.com/developers/resources/message https://docs.discord.com/developers/resources/webhook https://docs.discord.com/developers/interactions/application-commands https://docs.discord.com/developers/resources/emoji https://docs.discord.com/developers/resources/sticker https://docs.discord.com/developers/resources/audit-log https://docs.discord.com/developers/resources/voice https://docs.discord.com/developers/resources/poll https://docs.discord.com/developers/resources/soundboard https://docs.discord.com/developers/resources/stage-instance https://docs.discord.com/developers/resources/auto-moderation https://docs.discord.com/developers/topics/rate-limits
- **Paginación típica:** Cursor-based con parámetros `before`, `after` (snowflakes) y `limit` (1-100). El resultado es un array + campo `after` para la página siguiente. Para algunos recursos, `limit` puede llegar a 200.
- **Qué no se pudo verificar:** 1) Si un scope no listado en la doc oficial se puede usar con usuario token (ACCOUNT scope existe pero no documentado). 2) Qué scopes exactos exige cada endpoint no siempre está claro en la doc. 3) Endpoints exactos de algunas operaciones de Application (role connection, activity) aún no verificadas. 4) Si POST /users/@me/channels con `nicks` y `access_tokens` (group DM) realmente funciona con user token. 5) Algunos endpoints de Stage y Scheduled Events NO pudieron verificarse (404). 6) No confirmado si GET /users/{id} requiere scope especial o si solo funcion on @me.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/discord/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `discord`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `discord` |
| Variables del `.env` que necesitas | DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/discord/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `discord.user.get_me` |
| Cómo se autentica (según el catálogo) | OAuth 2 con código de autorización. El usuario autoriza una app para acceder a datos específicos vía scopes. Se obtiene access_token (corto plazo) y refresh_token para renovar sin re-autorización. |
| Duración del token (según el catálogo) | El access token dura 604800 segundos (7 días). Sin refresh token no se puede renovar; el usuario debe volver a autorizar. |
| Refresco (según el catálogo) | Sí, hay refresh token. POST /oauth2/token con grant_type=refresh_token, client_id, client_secret, refresh_token devuelve nuevo access_token. |
| Permisos (según el catálogo) | identify (perfil básico), email (email), guilds (servidores del usuario), guilds.join (agregar usuario a servidor), guilds.members.read (info de miembro en servidor), connections (cuentas enlazadas), gdm.join (agregar a group DM), webhook.incoming (crear webhook), role_connections.write (gestionar conexiones de rol), relationships.read (lista amigos bloqueados, SDK Social). |
| Restricciones de acceso | 1) Token de usuario SOLO puede hacer operaciones read-only en la mayoría de recursos. NO puede enviar mensajes, leer contenido de canales, crear roles, webhooks (excepto webhook.incoming) ni gestionar servidores. 2) Bot token accede a muchísimas más operaciones. Este catálogo lista SOLO lo que un token de usuario OAuth2 puede hacer. 3) Algunos scopes (identify.premium, relationships.read) requieren aprobación de Discord. 4) Aplicaciones sin MESSAGE_CONTENT intent no ven contenido de mensajes ni archivos adjuntos. 5) El token caduca cada 7 días sin refresh token. |
| Límites de ritmo | Global: 50 req/seg para todos los clientes. Per-route: varía por endpoint, típicamente 10 req/min a 5 req/seg según operación. IP con >10k req fallidas (401/403/429) en 10 min se bloquea temporalmente. X-RateLimit-Remaining, X-RateLimit-Reset y X-RateLimit-Reset-After en respuesta. |
| Notas de esta app | Es token de usuario OAuth, no de bot: muchas operaciones no están disponibles. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/discord/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> discord`. | Cuenta con `provider: discord`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/discord.user.get_me/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> discord <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Discord. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/discord.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Perfil de Usuario (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `discord.user.get_me` ★ | read | GET /users/@me | Obtiene el perfil completo del usuario conectado | identify | {id, username, email, avatar, locale, verified, mfa_enabled} | identify | — | — |
| [ ] | `discord.user.update_me` | update | PATCH /users/@me | Modifica el perfil (username, avatar, banner) | username, avatar, banner | {id, username, email, avatar} | identify | — | — |
| [ ] | `discord.user.get_user` | read | GET /users/{user.id} | Obtiene perfil público de otro usuario por ID | user.id | {id, username, discriminator, avatar, public_flags} | — | — | — |
| [ ] | `discord.user.get_connections` | read | GET /users/@me/connections | Lista cuentas enlazadas (Steam, Twitch, GitHub, etc.) | identify | [{type, id, name, verified, visibility, revoked}] | connections | — | — |

### Servidores (Lectura) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `discord.guild.list_user_guilds` | read | GET /users/@me/guilds | Lista servidores donde está el usuario (info parcial) | limit, before, after, with_counts | [{id, name, icon, owner, features}] + after | guilds | — | — |
| [ ] | `discord.guild.get_user_guild_member` | read | GET /users/@me/guilds/{guild.id}/member | Obtiene info del usuario en un servidor específico | guild.id | {user, nick, roles, joined_at, premium_since, flags} | guilds.members.read | — | — |
| [ ] | `discord.guild.leave_guild` | delete | DELETE /users/@me/guilds/{guild.id} | El usuario abandona un servidor | guild.id | — | guilds | I | — |
| [ ] | `discord.guild.get_guild` | read | GET /guilds/{guild.id} | Obtiene info del servidor (requiere ser miembro) | guild.id | {id, name, icon, splash, owner_id, features, verification_level} | — | — | — |

### Canales Directos (DMs) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `discord.channel.create_dm` | create | POST /users/@me/channels | Abre DM con usuario o crea group DM | recipient_id (user); access_tokens, nicks (group) | {id, type, recipients} | gdm.join | — | — |
| [ ] | `discord.channel.list_user_channels` | read | GET /users/@me/channels | Lista todos los canales DM abiertos por el usuario | limit, before, after | [{id, type, recipients, last_message_id}] | — | — | — |

### Conexiones de Rol (Role Connections) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `discord.role_connection.get_role_connection` | read | GET /users/@me/applications/{application.id}/role-connection | Lee la conexión de rol actual del usuario | application.id | {platform_name, platform_username, metadata} | role_connections.write | — | — |
| [ ] | `discord.role_connection.update_role_connection` | update | PUT /users/@me/applications/{application.id}/role-connection | Crea o actualiza la conexión de rol del usuario | application.id, platform_name, platform_username, metadata | {platform_name, platform_username, metadata} | role_connections.write | — | — |
| [ ] | `discord.role_connection.delete_role_connection` | delete | DELETE /users/@me/applications/{application.id}/role-connection | Borra la conexión de rol del usuario | application.id | — | role_connections.write | I | — |

### Requiere Bot Token - No accesible con Usuario OAuth2 (62)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `discord.message.list_messages` | read | GET /channels/{channel.id}/messages | Lista mensajes de un canal (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.message.get_message` | read | GET /channels/{channel.id}/messages/{message.id} | Lee un mensaje específico (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.message.create_message` | create | POST /channels/{channel.id}/messages | Envía mensaje a canal (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | E, I | — |
| [ ] | `discord.message.update_message` | update | PATCH /channels/{channel.id}/messages/{message.id} | Edita mensaje (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.message.delete_message` | delete | DELETE /channels/{channel.id}/messages/{message.id} | Borra mensaje (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.message.create_reaction` | create | PUT /channels/{channel.id}/messages/{message.id}/reactions/{emoji}/@me | Añade reacción a mensaje (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.guild.get_guild_channels` | read | GET /guilds/{guild.id}/channels | Lista canales del servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.guild.get_guild_members` | read | GET /guilds/{guild.id}/members | Lista miembros del servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.guild.get_guild_roles` | read | GET /guilds/{guild.id}/roles | Lista roles del servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.channel.create_channel` | create | POST /guilds/{guild.id}/channels | Crea canal en servidor (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.channel.modify_channel` | update | PATCH /channels/{channel.id} | Modifica propiedades de canal (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.channel.delete_channel` | delete | DELETE /channels/{channel.id} | Borra un canal (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.emoji.create_guild_emoji` | create | POST /guilds/{guild.id}/emojis | Sube emoji a servidor (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.emoji.modify_guild_emoji` | update | PATCH /guilds/{guild.id}/emojis/{emoji.id} | Modifica emoji de servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.emoji.delete_guild_emoji` | delete | DELETE /guilds/{guild.id}/emojis/{emoji.id} | Borra emoji de servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.webhook.create_webhook` | create | POST /channels/{channel.id}/webhooks | Crea webhook en canal (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.webhook.list_channel_webhooks` | read | GET /channels/{channel.id}/webhooks | Lista webhooks de canal (requiere bot + permisos) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.webhook.list_guild_webhooks` | read | GET /guilds/{guild.id}/webhooks | Lista todos los webhooks del servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.webhook.modify_webhook` | update | PATCH /webhooks/{webhook.id} | Modifica webhook (requiere bot o token del webhook) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.webhook.delete_webhook` | delete | DELETE /webhooks/{webhook.id} | Borra webhook (requiere bot o token) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.guild.modify_guild` | update | PATCH /guilds/{guild.id} | Modifica configuración del servidor (requiere bot + MANAGE_GUILD) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.guild.prune_members` | delete | POST /guilds/{guild.id}/prune | Expulsa miembros inactivos (requiere bot + KICK_MEMBERS) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.guild.ban_user` | create | PUT /guilds/{guild.id}/bans/{user.id} | Banea usuario de servidor (requiere bot + BAN_MEMBERS) | — | — | REQUIERE BOT TOKEN | I, E | — |
| [ ] | `discord.guild.unban_user` | delete | DELETE /guilds/{guild.id}/bans/{user.id} | Desbanea usuario (requiere bot + BAN_MEMBERS) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.guild.kick_member` | delete | DELETE /guilds/{guild.id}/members/{user.id} | Expulsa miembro de servidor (requiere bot + KICK_MEMBERS) | — | — | REQUIERE BOT TOKEN | I, E | — |
| [ ] | `discord.role.create_role` | create | POST /guilds/{guild.id}/roles | Crea rol en servidor (requiere bot + MANAGE_ROLES) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.role.modify_role` | update | PATCH /guilds/{guild.id}/roles/{role.id} | Modifica rol (requiere bot + MANAGE_ROLES) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.role.delete_role` | delete | DELETE /guilds/{guild.id}/roles/{role.id} | Borra rol (requiere bot + MANAGE_ROLES) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.invite.list_guild_invites` | read | GET /guilds/{guild.id}/invites | Lista invites del servidor (requiere bot + MANAGE_GUILD) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.invite.get_invite` | read | GET /invites/{invite.code} | Lee detalles de invite | — | {code, guild, channel, inviter, uses, created_at} | — | — | — |
| [ ] | `discord.invite.delete_invite` | delete | DELETE /invites/{invite.code} | Borra invite (requiere MANAGE_CHANNELS o MANAGE_GUILD) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.sticker.list_guild_stickers` | read | GET /guilds/{guild.id}/stickers | Lista stickers del servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.sticker.create_guild_sticker` | create | POST /guilds/{guild.id}/stickers | Sube sticker a servidor (requiere bot + CREATE_GUILD_EXPRESSIONS) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.sticker.modify_guild_sticker` | update | PATCH /guilds/{guild.id}/stickers/{sticker.id} | Modifica sticker (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.sticker.delete_guild_sticker` | delete | DELETE /guilds/{guild.id}/stickers/{sticker.id} | Borra sticker (requiere bot) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.voice.get_voice_regions` | read | GET /voice/regions | Lista regiones de voz disponibles | — | [{id, name, optimal, deprecated, custom}] | — | — | — |
| [ ] | `discord.voice.get_user_voice_state` | read | GET /guilds/{guild.id}/voice-states/@me | Lee estado de voz del usuario en canal stage | — | {user_id, guild_id, channel_id, session_id, suppress, request_to_speak_timestamp} | — | — | — |
| [ ] | `discord.voice.get_user_voice_state_other` | read | GET /guilds/{guild.id}/voice-states/{user.id} | Lee estado de voz de otro usuario (requiere VOICE) | — | {user_id, guild_id, suppress, request_to_speak_timestamp} | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.voice.modify_user_voice_state` | update | PATCH /guilds/{guild.id}/voice-states/@me | Modifica voz propia (suppress, request to speak) en stage | — | {suppress, request_to_speak_timestamp} | — | — | — |
| [ ] | `discord.audit_log.list_guild_audit_logs` | read | GET /guilds/{guild.id}/audit-logs | Lista cambios en servidor (requiere bot + VIEW_AUDIT_LOG) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.application.get_current_application` | read | GET /applications/@me | Obtiene info de la aplicación OAuth conectada | — | {id, name, icon, description, bot_public, bot_require_code_grant} | — | — | — |
| [ ] | `discord.auto_moderation.list_rules` | read | GET /guilds/{guild.id}/auto-moderation/rules | Lista reglas de automod (requiere bot + MANAGE_GUILD) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.stage_instance.get_stage_instance` | read | GET /stage-instances/{channel.id} | Lee instancia de stage activa | — | {id, guild_id, channel_id, topic, privacy_level} | — | — | — |
| [ ] | `discord.poll.get_answer_voters` | read | GET /channels/{channel.id}/polls/{message.id}/answers/{answer.id}/voters | Lista usuarios que votaron en encuesta (NO funciona con user token) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.soundboard.list_default_sounds` | read | GET /soundboard/default/sounds | Lista sonidos de soundboard públicos | — | [{sound_id, name, volume, emoji_id, emoji_name}] | — | — | — |
| [ ] | `discord.soundboard.list_guild_sounds` | read | GET /guilds/{guild.id}/soundboard/sounds | Lista sonidos de soundboard del servidor | — | [{sound_id, name, volume, emoji_id}] | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.soundboard.create_guild_sound` | create | POST /guilds/{guild.id}/soundboard/sounds | Sube sonido a soundboard del servidor (requiere bot + MANAGE_GUILD_EXPRESSIONS) | — | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.soundboard.modify_guild_sound` | update | PATCH /guilds/{guild.id}/soundboard/sounds/{sound_id} | Modifica sonido de soundboard (requiere bot) | — | — | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.soundboard.delete_guild_sound` | delete | DELETE /guilds/{guild.id}/soundboard/sounds/{sound_id} | Borra sonido de soundboard (requiere bot) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.soundboard.send_sound` | create | POST /guilds/{guild.id}/voice-states/@me/soundboard | Envía sonido a canal voice donde esté el usuario | sound_id, channel_id | — | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.command.list_global_commands` | read | GET /applications/{application.id}/commands | Lista comandos globales de la app | — | [{id, name, description, type, options}] | — | — | — |
| [ ] | `discord.command.create_global_command` | create | POST /applications/{application.id}/commands | Crea comando global (requiere bot) | — | {id, application_id, name, description, options} | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.command.get_global_command` | read | GET /applications/{application.id}/commands/{command.id} | Lee un comando global específico | — | {id, name, description, type, options} | — | — | — |
| [ ] | `discord.command.modify_global_command` | update | PATCH /applications/{application.id}/commands/{command.id} | Modifica comando global (requiere bot) | — | {name, description, options} | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.command.delete_global_command` | delete | DELETE /applications/{application.id}/commands/{command.id} | Borra comando global (requiere bot) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.command.list_guild_commands` | read | GET /applications/{application.id}/guilds/{guild.id}/commands | Lista comandos de servidor específico | — | [{id, name, description, type}] | — | — | — |
| [ ] | `discord.command.create_guild_command` | create | POST /applications/{application.id}/guilds/{guild.id}/commands | Crea comando para servidor (requiere bot) | — | {id, name, description, options} | REQUIERE BOT TOKEN | E | — |
| [ ] | `discord.command.get_guild_command` | read | GET /applications/{application.id}/guilds/{guild.id}/commands/{command.id} | Lee comando de servidor | — | {id, name, description, type, options} | — | — | — |
| [ ] | `discord.command.modify_guild_command` | update | PATCH /applications/{application.id}/guilds/{guild.id}/commands/{command.id} | Modifica comando de servidor (requiere bot) | — | {name, description, options} | REQUIERE BOT TOKEN | — | — |
| [ ] | `discord.command.delete_guild_command` | delete | DELETE /applications/{application.id}/guilds/{guild.id}/commands/{command.id} | Borra comando de servidor (requiere bot) | — | — | REQUIERE BOT TOKEN | I | — |
| [ ] | `discord.command.list_command_permissions` | read | GET /applications/{application.id}/guilds/{guild.id}/commands/{command.id}/permissions | Lee permisos de comando | — | [{id, type, permission, roles, users}] | — | — | — |
| [ ] | `discord.command.modify_command_permissions` | update | PUT /applications/{application.id}/guilds/{guild.id}/commands/{command.id}/permissions | Cambia permisos de comando (requiere bot) | — | [{id, type, permission}] | REQUIERE BOT TOKEN | — | — |
