# Tareas: Microsoft Teams

- **Funciones catalogadas:** 133 · **Hechas:** 0 · **Pendientes:** 133 · App sin herramientas viejas
- **Documentación oficial:** https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview
- **Fuentes que consultó el catálogo:** https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview https://learn.microsoft.com/en-us/graph/api/resources/team https://learn.microsoft.com/en-us/graph/api/resources/channel https://learn.microsoft.com/en-us/graph/api/resources/chatmessage https://learn.microsoft.com/en-us/graph/api/resources/chat https://learn.microsoft.com/en-us/graph/api/resources/onlinemeeting https://learn.microsoft.com/en-us/graph/api/resources/presence https://learn.microsoft.com/en-us/graph/api/resources/teamstab https://learn.microsoft.com/en-us/graph/api/resources/teamsappinstallation https://learn.microsoft.com/en-us/graph/api/resources/conversationmember https://learn.microsoft.com/en-us/graph/api/resources/teamworktag https://learn.microsoft.com/en-us/graph/auth-v2-user https://learn.microsoft.com/en-us/graph/throttling
- **Paginación típica:** OData: $skip, $top (default 20, máx 999), $filter, $expand, $select. Respuestas incluyen @odata.nextLink si hay más resultados. No hay cursor pagination, solo skip/top.
- **Qué no se pudo verificar:** Scopes delegados exactos de algunos endpoints menos comunes; parametros avanzados de reuniones (broadcast, deprecado).
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/teams/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `teams`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `teams` |
| Variables del `.env` que necesitas | TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_REDIRECT_URI, SECRET_KEY, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/teams/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `teams.user.get` |
| Cómo se autentica (según el catálogo) | OAuth2 con código de autorización y refresh token. Microsoft Entra (delegados). Cliente redirige a /authorize, user consiente, recibe code, intercambia por access_token + refresh_token en /token. |
| Duración del token (según el catálogo) | Access token caduca en ~1 hora (3600 segundos típicamente), refresh token es de larga duración (hasta 90 días inactividad). |
| Refresco (según el catálogo) | Si, hay refresh token. Se obtiene en la respuesta /token con scope offline_access. Se renueva enviando refresh_token a POST /token con grant_type=refresh_token. |
| Permisos (según el catálogo) | Permisos delegados por grupo: Chat.Read, Chat.ReadWrite (chats); Team.ReadBasic.All, Team.Read.All, Team.ReadWrite.All (equipos); Channel.ReadBasic.All, Channel.Read.All, Channel.ReadWrite.All (canales); ChatMessage.Read (mensajes); OnlineMeetings.Read, OnlineMeetings.ReadWrite (reuniones); Presence.Read, Presence.ReadWrite (presencia); TeamsTab.Read.All, TeamsTab.ReadWrite.All (pestañas); TeamsAppInstallation.Manage.All (apps); TeamworkTag.ReadWrite (etiquetas). |
| Restricciones de acceso | Requiere cuenta Microsoft 365 / Azure AD. Algunos endpoints solo para aplicaciones o con permisos protegidos. Listados frecuentes limitados (máx 1/día). Necesita suscripción de Teams activa en el tenant. |
| Límites de ritmo | Rate limit: 10,000 solicitudes/hora por app. Throttling: HTTP 429 si se excede. Retry-After header en respuestas. Máx 100 miembros en bulk operations. Máx 50 caracteres en nombre de canal. Máx 1024 en descripción de team. Paginación: $skip, $top (máx 999). Mensajes: máx 28 días en búsqueda delta. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/teams/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> teams`. | Cuenta con `provider: teams`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/teams.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> teams <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Microsoft Teams. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/teams.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Información de Presencia del Usuario (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.user.get` ★ | read | GET /me | Obtener perfil y id del usuario autenticado (whoami) | {} | {id, email, displayName, userPrincipalName, jobTitle} | Presence.Read | — | — |
| [ ] | `teams.user.list_chats` | read | GET /me/chats | Listar todos los chats del usuario | {$top, $filter, $expand} | lista de {id, topic, chatType, createdDateTime} | Chat.Read | — | — |

### Equipos (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.team.list` | read | GET /me/joinedTeams | Listar equipos a los que el usuario pertenece | {$top, $skip} | lista de {id, displayName, visibility, createdDateTime} | Team.ReadBasic.All | — | — |
| [ ] | `teams.team.list_all` | read | GET /teams | Listar todos los equipos de la organización | {$top, $skip, $filter} | lista de {id, displayName, visibility, description} | Team.Read.All | — | — |
| [ ] | `teams.team.get` | read | GET /teams/{team_id} | Obtener propiedades de un equipo | {team_id} | {id, displayName, description, visibility, createdDateTime, isArchived, webUrl, tenantId} | Team.ReadBasic.All | — | — |
| [ ] | `teams.team.create` | create | POST /teams | Crear un nuevo equipo | {displayName, description, visibility, allowGuestCreateUpdateChannels, allowGuestDeleteChannels} | {teamsAsyncOperation id para seguimiento} | Team.Create | — | — |
| [ ] | `teams.team.create_from_group` | create | PUT /groups/{group_id}/team | Crear equipo a partir de grupo M365 existente | {group_id, allowGuestCreateUpdateChannels, allowGuestDeleteChannels} | {id, displayName, description} | TeamSettings.ReadWrite.All | — | — |
| [ ] | `teams.team.update` | update | PATCH /teams/{team_id} | Actualizar propiedades del equipo | {team_id, displayName, description, funSettings, messagingSettings, guestSettings, memberSettings} | {id, displayName, description, visibility} | Team.ReadWrite.All | — | — |
| [ ] | `teams.team.delete` | delete | DELETE /groups/{group_id} | Eliminar equipo (tambien grupo) | {team_id} | {} | TeamSettings.ReadWrite.All | I | — |
| [ ] | `teams.team.archive` | create | POST /teams/{team_id}/archive | Archivar equipo (solo lectura) | {team_id, shouldSetSpoSiteReadOnlyForMembers} | {teamsAsyncOperation para seguimiento} | Team.ReadWrite.All | I | — |
| [ ] | `teams.team.unarchive` | update | POST /teams/{team_id}/unarchive | Desarchivar equipo | {team_id} | {teamsAsyncOperation para seguimiento} | Team.ReadWrite.All | — | — |
| [ ] | `teams.team.clone` | create | POST /teams/{team_id}/clone | Clonar equipo con canales y apps | {team_id, displayName, description, partsToClone, visibility} | {teamsAsyncOperation para seguimiento} | Team.Create | I | — |
| [ ] | `teams.team.complete_migration` | update | POST /teams/{team_id}/completeMigration | Finalizar modo migracion | {team_id} | {id, displayName, migrationMode} | Team.ReadWrite.All | — | — |

### Canales (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.channel.list` | read | GET /teams/{team_id}/channels | Listar canales del equipo | {team_id, $top, $skip} | lista de {id, displayName, description, createdDateTime, membershipType} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.list_all` | read | GET /teams/{team_id}/allChannels | Listar todos los canales (internos y compartidos) | {team_id, $top, $skip} | lista de {id, displayName, description, membershipType} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.list_incoming` | read | GET /teams/{team_id}/incomingChannels | Listar canales compartidos que llegaron a este equipo | {team_id, $top, $skip} | lista de {id, displayName, membershipType} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.get` | read | GET /teams/{team_id}/channels/{channel_id} | Obtener propiedades del canal | {team_id, channel_id} | {id, displayName, description, createdDateTime, webUrl, membershipType} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.get_primary` | read | GET /teams/{team_id}/primaryChannel | Obtener canal general del equipo | {team_id} | {id, displayName, createdDateTime} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.create` | create | POST /teams/{team_id}/channels | Crear nuevo canal | {team_id, displayName, description, membershipType, isFavoriteByDefault} | {id, displayName, createdDateTime, webUrl} | Channel.Create | — | — |
| [ ] | `teams.channel.update` | update | PATCH /teams/{team_id}/channels/{channel_id} | Actualizar propiedades del canal | {team_id, channel_id, displayName, description} | {id, displayName, description, webUrl} | Channel.ReadWrite.All | — | — |
| [ ] | `teams.channel.delete` | delete | DELETE /teams/{team_id}/channels/{channel_id} | Eliminar canal | {team_id, channel_id} | {} | Channel.Delete.All | I | — |
| [ ] | `teams.channel.archive` | create | POST /teams/{team_id}/channels/{channel_id}/archive | Archivar canal (solo lectura) | {team_id, channel_id} | {} | Channel.ReadWrite.All | I | — |
| [ ] | `teams.channel.unarchive` | update | POST /teams/{team_id}/channels/{channel_id}/unarchive | Desarchivar canal | {team_id, channel_id} | {} | Channel.ReadWrite.All | — | — |
| [ ] | `teams.channel.start_migration` | create | POST /teams/{team_id}/channels/{channel_id}/startMigration | Habilitar modo migracion en canal | {team_id, channel_id} | {id, migrationMode} | Channel.ReadWrite.All | — | — |
| [ ] | `teams.channel.complete_migration` | update | POST /teams/{team_id}/channels/{channel_id}/completeMigration | Finalizar modo migracion en canal | {team_id, channel_id} | {id, migrationMode} | Channel.ReadWrite.All | — | — |
| [ ] | `teams.channel.provision_email` | create | POST /teams/{team_id}/channels/{channel_id}/provisionEmail | Crear direccion email para el canal | {team_id, channel_id} | {smtpAddress} | Channel.ReadWrite.All | — | — |
| [ ] | `teams.channel.remove_email` | delete | DELETE /teams/{team_id}/channels/{channel_id}/removeEmail | Eliminar direccion email del canal | {team_id, channel_id} | {} | Channel.ReadWrite.All | I | — |
| [ ] | `teams.channel.get_files_folder` | read | GET /teams/{team_id}/channels/{channel_id}/filesFolder | Obtener carpeta de archivos del canal en SharePoint | {team_id, channel_id} | {id, name, webUrl, createdDateTime} | Files.Read.All | — | — |
| [ ] | `teams.channel.unshare` | delete | DELETE /teams/{team_id}/channels/{channel_id}/sharedWithTeams/{team_id} | Dejar de compartir canal con otro equipo | {team_id, channel_id, shared_with_team_id} | {} | Channel.ReadWrite.All | — | — |

### Miembros de Equipo (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.member.list` | read | GET /teams/{team_id}/members | Listar miembros del equipo | {team_id, $top, $skip, $expand} | lista de {id, displayName, roles, userId, email} | TeamMember.Read.All | — | — |
| [ ] | `teams.member.get` | read | GET /teams/{team_id}/members/{member_id} | Obtener miembro especifico del equipo | {team_id, member_id} | {id, displayName, roles, userId, email, tenantId} | TeamMember.Read.All | — | — |
| [ ] | `teams.member.add` | create | POST /teams/{team_id}/members | Agregar miembro al equipo | {team_id, userId, roles} | {id, displayName, roles} | TeamMember.ReadWrite.All | E | — |
| [ ] | `teams.member.add_bulk` | create | POST /conversationMembers/add | Agregar multiples miembros en un request | {team_id, values: [{userId, roles}]} | {value: [{id, @odata.type, roles}]} | TeamMember.ReadWrite.All | E | — |
| [ ] | `teams.member.update` | update | PATCH /teams/{team_id}/members/{member_id} | Cambiar rol del miembro (owner/member) | {team_id, member_id, roles} | {id, displayName, roles} | TeamMember.ReadWrite.All | — | — |
| [ ] | `teams.member.remove` | delete | DELETE /teams/{team_id}/members/{member_id} | Remover miembro del equipo | {team_id, member_id} | {} | TeamMember.ReadWrite.All | I | — |
| [ ] | `teams.member.remove_bulk` | delete | POST /conversationMembers/remove | Remover multiples miembros en un request | {team_id, values: [member_id]} | {value: [{id, @odata.type}]} | TeamMember.ReadWrite.All | I | — |

### Miembros de Canal (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.channel_member.list` | read | GET /teams/{team_id}/channels/{channel_id}/members | Listar miembros del canal (privado/compartido) | {team_id, channel_id, $top, $skip} | lista de {id, displayName, roles, userId, email} | ChannelMember.Read.All | — | — |
| [ ] | `teams.channel_member.list_all` | read | GET /teams/{team_id}/channels/{channel_id}/allMembers | Listar todos los miembros incluyendo heredados | {team_id, channel_id, $top, $skip} | lista de {id, displayName, roles} | ChannelMember.Read.All | — | — |
| [ ] | `teams.channel_member.get` | read | GET /teams/{team_id}/channels/{channel_id}/members/{member_id} | Obtener miembro especifico del canal | {team_id, channel_id, member_id} | {id, displayName, roles, userId, email} | ChannelMember.Read.All | — | — |
| [ ] | `teams.channel_member.add` | create | POST /teams/{team_id}/channels/{channel_id}/members | Agregar miembro a canal privado/compartido | {team_id, channel_id, userId, roles} | {id, displayName, roles} | ChannelMember.ReadWrite.All | E | — |
| [ ] | `teams.channel_member.update` | update | PATCH /teams/{team_id}/channels/{channel_id}/members/{member_id} | Cambiar rol del miembro en canal | {team_id, channel_id, member_id, roles} | {id, displayName, roles} | ChannelMember.ReadWrite.All | — | — |
| [ ] | `teams.channel_member.remove` | delete | DELETE /teams/{team_id}/channels/{channel_id}/members/{member_id} | Remover miembro de canal privado/compartido | {team_id, channel_id, member_id} | {} | ChannelMember.ReadWrite.All | I | — |

### Mensajes de Canal (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.channel_message.list` | read | GET /teams/{team_id}/channels/{channel_id}/messages | Listar mensajes del canal | {team_id, channel_id, $top, $skip, $filter} | lista de {id, body, from, createdDateTime, lastEditedDateTime} | ChatMessage.Read | — | — |
| [ ] | `teams.channel_message.get` | read | GET /teams/{team_id}/channels/{channel_id}/messages/{message_id} | Obtener mensaje especifico del canal | {team_id, channel_id, message_id} | {id, body, from, createdDateTime, attachments, mentions, reactions} | ChatMessage.Read | — | — |
| [ ] | `teams.channel_message.get_all` | read | GET /teams/{team_id}/channels/getAllMessages | Obtener todos los mensajes de todos los canales del usuario | {team_id, $top, $skip} | lista de {id, body, from, createdDateTime} + siguiente pagina | ChatMessage.Read | — | — |
| [ ] | `teams.channel_message.get_all_retained` | read | GET /teams/{team_id}/channels/getAllRetainedMessages | Obtener mensajes retenidos (cumplimiento) | {team_id, $top, $skip} | lista de {id, body, createdDateTime} | ChatMessage.Read | — | — |
| [ ] | `teams.channel_message.send` | create | POST /teams/{team_id}/channels/{channel_id}/messages | Enviar mensaje al canal | {team_id, channel_id, body, attachments, mentions, importance} | {id, body, from, createdDateTime, webUrl} | ChatMessage.Send | E | — |
| [ ] | `teams.channel_message.reply` | create | POST /teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies | Responder a mensaje en canal | {team_id, channel_id, message_id, body, attachments, mentions} | {id, body, from, createdDateTime, replyToId} | ChatMessage.Send | E | — |
| [ ] | `teams.channel_message.list_replies` | read | GET /teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies | Listar respuestas a un mensaje | {team_id, channel_id, message_id, $top, $skip} | lista de {id, body, from, createdDateTime} | ChatMessage.Read | — | — |
| [ ] | `teams.channel_message.update` | update | PATCH /teams/{team_id}/channels/{channel_id}/messages/{message_id} | Actualizar mensaje (solo policyViolation) | {team_id, channel_id, message_id, policyViolation} | {id, body, policyViolation} | ChatMessage.ReadWrite | — | — |
| [ ] | `teams.channel_message.delete` | delete | DELETE /teams/{team_id}/channels/{channel_id}/messages/{message_id} | Suavemente eliminar mensaje del canal | {team_id, channel_id, message_id} | {} | ChatMessage.Delete | I | — |
| [ ] | `teams.channel_message.undelete` | update | POST /teams/{team_id}/channels/{channel_id}/messages/{message_id}/undoSoftDelete | Deshacer borrado suave | {team_id, channel_id, message_id} | {id, body, deletedDateTime} | ChatMessage.Delete | — | — |
| [ ] | `teams.channel_message.set_reaction` | create | POST /teams/{team_id}/channels/{channel_id}/messages/{message_id}/setReaction | Agregar reaccion emoji al mensaje | {team_id, channel_id, message_id, reactionType} | {} | ChatMessage.ReadWrite | E | — |
| [ ] | `teams.channel_message.unset_reaction` | delete | DELETE /teams/{team_id}/channels/{channel_id}/messages/{message_id}/unsetReaction | Remover reaccion del mensaje | {team_id, channel_id, message_id, reactionType} | {} | ChatMessage.ReadWrite | — | — |

### Miembros de Chat (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.chat_member.list` | read | GET /chats/{chat_id}/members | Listar miembros del chat (1:1, grupo, reunión) | {chat_id, $top, $skip} | lista de {id, displayName, roles, userId, email} | ChatMember.Read | — | — |
| [ ] | `teams.chat_member.get` | read | GET /chats/{chat_id}/members/{member_id} | Obtener miembro especifico del chat | {chat_id, member_id} | {id, displayName, roles, userId, email} | ChatMember.Read | — | — |
| [ ] | `teams.chat_member.add` | create | POST /chats/{chat_id}/members | Agregar miembro a chat 1:1 o grupo | {chat_id, userId, roles, visibleHistoryStartDateTime} | {} | ChatMember.ReadWrite | E | — |
| [ ] | `teams.chat_member.remove` | delete | DELETE /chats/{chat_id}/members/{member_id} | Remover miembro del chat | {chat_id, member_id} | {} | ChatMember.ReadWrite | I | — |

### Chats (1:1, Grupo, Reunión) (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.chat.list` | read | GET /me/chats | Listar chats del usuario | {$top, $skip, $filter, $expand} | lista de {id, chatType, topic, createdDateTime, lastUpdatedDateTime} | Chat.ReadBasic | — | — |
| [ ] | `teams.chat.get` | read | GET /chats/{chat_id} | Obtener propiedades del chat | {chat_id, $expand} | {id, chatType, topic, createdDateTime, webUrl, onlineMeetingInfo} | Chat.ReadBasic | — | — |
| [ ] | `teams.chat.create` | create | POST /chats | Crear nuevo chat 1:1 o grupo | {chatType, members: [{userId, roles}], topic} | {id, chatType, createdDateTime} | Chat.Create | E | — |
| [ ] | `teams.chat.update` | update | PATCH /chats/{chat_id} | Actualizar chat (topic) | {chat_id, topic} | {id, topic, lastUpdatedDateTime} | Chat.ReadWrite | — | — |
| [ ] | `teams.chat.delete` | delete | DELETE /chats/{chat_id} | Eliminar chat | {chat_id} | {} | Chat.Manage.Chat | I | — |
| [ ] | `teams.chat.start_migration` | create | POST /chats/{chat_id}/startMigration | Habilitar modo migracion en chat | {chat_id} | {id, migrationMode} | Chat.ReadWrite | — | — |
| [ ] | `teams.chat.complete_migration` | update | POST /chats/{chat_id}/completeMigration | Finalizar modo migracion | {chat_id} | {id, migrationMode} | Chat.ReadWrite | — | — |
| [ ] | `teams.chat.remove_all_access` | delete | POST /chats/{chat_id}/removeAllAccessForUser | Remover acceso del usuario al chat | {chat_id, userId} | {} | Chat.Manage.Chat | I | — |
| [ ] | `teams.chat.get_all_messages` | read | GET /chats/getAllMessages | Obtener todos los mensajes de todos los chats del usuario | {$top, $skip, $filter} | lista de {id, body, from, createdDateTime} | ChatMessage.Read | — | — |
| [ ] | `teams.chat.get_all_retained_messages` | read | GET /chats/getAllRetainedMessages | Obtener mensajes retenidos en todos los chats | {$top, $skip} | lista de {id, body, createdDateTime} | ChatMessage.Read | — | — |

### Mensajes de Chat (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.chat_message.list` | read | GET /chats/{chat_id}/messages | Listar mensajes del chat | {chat_id, $top, $skip, $filter} | lista de {id, body, from, createdDateTime} | ChatMessage.Read | — | — |
| [ ] | `teams.chat_message.get` | read | GET /chats/{chat_id}/messages/{message_id} | Obtener mensaje especifico del chat | {chat_id, message_id} | {id, body, from, createdDateTime, attachments, mentions, reactions} | ChatMessage.Read | — | — |
| [ ] | `teams.chat_message.delta` | read | GET /chats/{chat_id}/messages/delta | Obtener cambios en mensajes (delta query) | {chat_id, $deltatoken} | lista de {id, body, createdDateTime} + deltaLink | ChatMessage.Read | — | — |
| [ ] | `teams.chat_message.send` | create | POST /chats/{chat_id}/messages | Enviar mensaje en chat 1:1 o grupo | {chat_id, body, attachments, mentions, importance} | {id, body, from, createdDateTime} | ChatMessage.Send | E | — |
| [ ] | `teams.chat_message.update` | update | PATCH /chats/{chat_id}/messages/{message_id} | Actualizar mensaje (solo policyViolation) | {chat_id, message_id, policyViolation} | {id, body, policyViolation} | ChatMessage.ReadWrite | — | — |
| [ ] | `teams.chat_message.delete` | delete | DELETE /chats/{chat_id}/messages/{message_id} | Suavemente eliminar mensaje del chat | {chat_id, message_id} | {} | ChatMessage.Delete | I | — |
| [ ] | `teams.chat_message.undelete` | update | POST /chats/{chat_id}/messages/{message_id}/undoSoftDelete | Deshacer borrado suave | {chat_id, message_id} | {id, body} | ChatMessage.Delete | — | — |
| [ ] | `teams.chat_message.set_reaction` | create | POST /chats/{chat_id}/messages/{message_id}/setReaction | Agregar reaccion al mensaje | {chat_id, message_id, reactionType} | {} | ChatMessage.ReadWrite | E | — |
| [ ] | `teams.chat_message.unset_reaction` | delete | DELETE /chats/{chat_id}/messages/{message_id}/unsetReaction | Remover reaccion del mensaje | {chat_id, message_id, reactionType} | {} | ChatMessage.ReadWrite | — | — |
| [ ] | `teams.chat_message.reply_with_quote` | create | POST /chats/{chat_id}/messages/{message_id}/replieswithquote | Responder con quote a uno o multiples mensajes | {chat_id, message_id, body, attachments} | {id, body, replyToId} | ChatMessage.Send | E | — |

### Pestañas (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.channel_tab.list` | read | GET /teams/{team_id}/channels/{channel_id}/tabs | Listar pestañas del canal | {team_id, channel_id, $expand} | lista de {id, displayName, webUrl, configuration} | TeamsTab.Read.All | — | — |
| [ ] | `teams.channel_tab.get` | read | GET /teams/{team_id}/channels/{channel_id}/tabs/{tab_id} | Obtener pestana especifica | {team_id, channel_id, tab_id} | {id, displayName, webUrl, configuration, teamsApp} | TeamsTab.Read.All | — | — |
| [ ] | `teams.channel_tab.add` | create | POST /teams/{team_id}/channels/{channel_id}/tabs | Agregar pestaña a canal | {team_id, channel_id, displayName, teamsAppId, configuration} | {id, displayName, webUrl, teamsApp} | TeamsTab.ReadWrite.All | E | — |
| [ ] | `teams.channel_tab.update` | update | PATCH /teams/{team_id}/channels/{channel_id}/tabs/{tab_id} | Actualizar propiedades de pestaña | {team_id, channel_id, tab_id, displayName, configuration} | {id, displayName, webUrl, configuration} | TeamsTab.ReadWrite.All | — | — |
| [ ] | `teams.channel_tab.remove` | delete | DELETE /teams/{team_id}/channels/{channel_id}/tabs/{tab_id} | Remover pestaña del canal | {team_id, channel_id, tab_id} | {} | TeamsTab.ReadWrite.All | I | — |
| [ ] | `teams.chat_tab.list` | read | GET /chats/{chat_id}/tabs | Listar pestañas del chat | {chat_id, $expand} | lista de {id, displayName, webUrl, configuration} | TeamsTab.Read.All | — | — |
| [ ] | `teams.chat_tab.get` | read | GET /chats/{chat_id}/tabs/{tab_id} | Obtener pestaña especifica del chat | {chat_id, tab_id} | {id, displayName, webUrl, configuration, teamsApp} | TeamsTab.Read.All | — | — |
| [ ] | `teams.chat_tab.add` | create | POST /chats/{chat_id}/tabs | Agregar pestaña a chat | {chat_id, displayName, teamsAppId, configuration} | {id, displayName, webUrl, teamsApp} | TeamsTab.ReadWrite.All | E | — |
| [ ] | `teams.chat_tab.update` | update | PATCH /chats/{chat_id}/tabs/{tab_id} | Actualizar pestaña del chat | {chat_id, tab_id, displayName, configuration} | {id, displayName, webUrl, configuration} | TeamsTab.ReadWrite.All | — | — |
| [ ] | `teams.chat_tab.remove` | delete | DELETE /chats/{chat_id}/tabs/{tab_id} | Remover pestaña del chat | {chat_id, tab_id} | {} | TeamsTab.ReadWrite.All | I | — |

### Apps en Equipos y Canales (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.team_app.list` | read | GET /teams/{team_id}/installedApps | Listar apps instaladas en equipo | {team_id, $expand} | lista de {id, teamsApp, consentedPermissionSet} | TeamsAppInstallation.Read.All | — | — |
| [ ] | `teams.team_app.get` | read | GET /teams/{team_id}/installedApps/{app_id} | Obtener app instalada en equipo | {team_id, app_id} | {id, teamsApp, teamsAppDefinition} | TeamsAppInstallation.Read.All | — | — |
| [ ] | `teams.team_app.add` | create | POST /teams/{team_id}/installedApps | Instalar app en equipo | {team_id, teamsAppId} | {} | TeamsAppInstallation.ReadWrite.All | E | — |
| [ ] | `teams.team_app.upgrade` | update | POST /teams/{team_id}/installedApps/{app_id}/upgrade | Actualizar app instalada en equipo | {team_id, app_id} | {} | TeamsAppInstallation.ReadWrite.All | — | — |
| [ ] | `teams.team_app.remove` | delete | DELETE /teams/{team_id}/installedApps/{app_id} | Desinstalar app del equipo | {team_id, app_id} | {} | TeamsAppInstallation.ReadWrite.All | I | — |
| [ ] | `teams.channel_app.list` | read | GET /teams/{team_id}/channels/{channel_id}/enabledApps | Listar apps habilitadas en canal | {team_id, channel_id} | lista de {id, teamsApp} | TeamsAppInstallation.Read.All | — | — |
| [ ] | `teams.channel_app.add` | create | POST /teams/{team_id}/channels/{channel_id}/enabledApps | Habilitar app en canal | {team_id, channel_id, teamsAppId} | {} | TeamsAppInstallation.ReadWrite.All | E | — |
| [ ] | `teams.channel_app.remove` | delete | DELETE /teams/{team_id}/channels/{channel_id}/enabledApps/{app_id} | Deshabilitar app en canal | {team_id, channel_id, app_id} | {} | TeamsAppInstallation.ReadWrite.All | I | — |
| [ ] | `teams.chat_app.list` | read | GET /chats/{chat_id}/installedApps | Listar apps instaladas en chat | {chat_id, $expand} | lista de {id, teamsApp} | TeamsAppInstallation.Read.All | — | — |
| [ ] | `teams.chat_app.get` | read | GET /chats/{chat_id}/installedApps/{app_id} | Obtener app instalada en chat | {chat_id, app_id} | {id, teamsApp, teamsAppDefinition} | TeamsAppInstallation.Read.All | — | — |
| [ ] | `teams.chat_app.add` | create | POST /chats/{chat_id}/installedApps | Instalar app en chat | {chat_id, teamsAppId} | {} | TeamsAppInstallation.ReadWrite.All | E | — |
| [ ] | `teams.chat_app.upgrade` | update | POST /chats/{chat_id}/installedApps/{app_id}/upgrade | Actualizar app en chat | {chat_id, app_id} | {} | TeamsAppInstallation.ReadWrite.All | — | — |
| [ ] | `teams.chat_app.remove` | delete | DELETE /chats/{chat_id}/installedApps/{app_id} | Desinstalar app del chat | {chat_id, app_id} | {} | TeamsAppInstallation.ReadWrite.All | I | — |

### Reuniones en Línea (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.meeting.create` | create | POST /me/onlineMeetings | Crear reunión en línea | {subject, startDateTime, endDateTime, participants, allowAttendeeToEnableMic, allowAttendeeToEnableCamera, allowMeetingChat} | {id, joinWebUrl, videoTeleconferenceId, createdDateTime} | OnlineMeetings.ReadWrite | E | — |
| [ ] | `teams.meeting.create_or_get` | create | POST /me/onlineMeetings/createOrGet | Crear o recuperar reunión con id externo | {subject, startDateTime, endDateTime, externalId, participants} | {id, joinWebUrl, createdDateTime} | OnlineMeetings.ReadWrite | — | — |
| [ ] | `teams.meeting.get` | read | GET /me/onlineMeetings/{meeting_id} | Obtener propiedades de reunion | {meeting_id} | {id, subject, startDateTime, endDateTime, joinWebUrl, participants, allowRecording} | OnlineMeetings.Read | — | — |
| [ ] | `teams.meeting.update` | update | PATCH /me/onlineMeetings/{meeting_id} | Actualizar reunion (fechas, opciones, participantes) | {meeting_id, subject, startDateTime, endDateTime, allowMeetingChat, allowRecording, recordAutomatically} | {id, subject, startDateTime, endDateTime, joinWebUrl} | OnlineMeetings.ReadWrite | — | — |
| [ ] | `teams.meeting.delete` | delete | DELETE /me/onlineMeetings/{meeting_id} | Eliminar reunion | {meeting_id} | {} | OnlineMeetings.ReadWrite | I | — |
| [ ] | `teams.meeting.list_transcripts` | read | GET /me/onlineMeetings/{meeting_id}/transcripts | Listar transcripciones de reunion | {meeting_id, $top, $skip} | lista de {id, createdDateTime, content} | OnlineMeetings.Read | — | — |
| [ ] | `teams.meeting.list_recordings` | read | GET /me/onlineMeetings/{meeting_id}/recordings | Listar grabaciones de reunion | {meeting_id, $top, $skip} | lista de {id, createdDateTime, recordingContentUrl} | OnlineMeetings.Read | — | — |
| [ ] | `teams.meeting.get_attendance_report` | read | GET /me/onlineMeetings/{meeting_id}/attendanceReports | Obtener reportes de asistencia | {meeting_id} | lista de {id, totalParticipantCount, totalAttendeeCount, attendanceRecords} | OnlineMeetings.Read | — | — |

### Presencia (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.presence.get` | read | GET /me/presence | Obtener presencia del usuario autenticado | {} | {availability, activity, statusMessage, workLocation, sequenceNumber} | Presence.Read | — | — |
| [ ] | `teams.presence.get_user` | read | GET /users/{user_id}/presence | Obtener presencia de otro usuario | {user_id} | {availability, activity, statusMessage, sequenceNumber} | Presence.Read | — | — |
| [ ] | `teams.presence.get_multiple` | read | POST /communications/getPresencesByUserId | Obtener presencia de multiples usuarios | {ids: [user_ids]} | lista de {id, availability, activity} | Presence.Read | — | — |
| [ ] | `teams.presence.set` | create | POST /me/presence/setPresence | Establecer presencia en aplicacion | {availability, activity, expirationDuration} | {} | Presence.ReadWrite | — | — |
| [ ] | `teams.presence.clear` | delete | POST /me/presence/clearPresence | Limpiar presencia de aplicacion | {} | {} | Presence.ReadWrite | — | — |
| [ ] | `teams.presence.set_preferred` | update | POST /me/presence/setUserPreferredPresence | Establecer presencia preferida del usuario | {availability, activity, expirationDuration} | {} | Presence.ReadWrite | — | — |
| [ ] | `teams.presence.clear_preferred` | delete | POST /me/presence/clearUserPreferredPresence | Limpiar presencia preferida | {} | {} | Presence.ReadWrite | — | — |
| [ ] | `teams.presence.set_status_message` | create | POST /me/presence/setStatusMessage | Establecer mensaje de estado personal | {statusMessage, expirationTime} | {} | Presence.ReadWrite | — | — |
| [ ] | `teams.presence.set_work_location` | update | POST /me/presence/setWorkLocation | Establecer ubicacion de trabajo manual | {workLocation} | {} | Presence.ReadWrite | — | — |

### Etiquetas (Tags) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.tag.list` | read | GET /teams/{team_id}/tags | Listar etiquetas del equipo | {team_id, $top, $skip} | lista de {id, displayName, description, memberCount, teamId} | TeamworkTag.Read.All | — | — |
| [ ] | `teams.tag.get` | read | GET /teams/{team_id}/tags/{tag_id} | Obtener etiqueta especifica | {team_id, tag_id} | {id, displayName, description, memberCount, tagType, teamId} | TeamworkTag.Read.All | — | — |
| [ ] | `teams.tag.create` | create | POST /teams/{team_id}/tags | Crear nueva etiqueta | {team_id, displayName, description} | {id, displayName, description, memberCount, tagType} | TeamworkTag.ReadWrite | E | — |
| [ ] | `teams.tag.update` | update | PATCH /teams/{team_id}/tags/{tag_id} | Actualizar etiqueta | {team_id, tag_id, displayName, description} | {id, displayName, description, memberCount} | TeamworkTag.ReadWrite | — | — |
| [ ] | `teams.tag.delete` | delete | DELETE /teams/{team_id}/tags/{tag_id} | Eliminar etiqueta | {team_id, tag_id} | {} | TeamworkTag.ReadWrite | I | — |
| [ ] | `teams.tag_member.list` | read | GET /teams/{team_id}/tags/{tag_id}/members | Listar miembros asignados a etiqueta | {team_id, tag_id, $top, $skip} | lista de {id, displayName, userId} | TeamworkTag.Read.All | — | — |
| [ ] | `teams.tag_member.add` | create | POST /teams/{team_id}/tags/{tag_id}/members | Agregar miembro a etiqueta | {team_id, tag_id, userId} | {} | TeamworkTag.ReadWrite | E | — |
| [ ] | `teams.tag_member.remove` | delete | DELETE /teams/{team_id}/tags/{tag_id}/members/{member_id} | Remover miembro de etiqueta | {team_id, tag_id, member_id} | {} | TeamworkTag.ReadWrite | I | — |

### Mensajes Pinados (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.chat_pinned_message.list` | read | GET /chats/{chat_id}/pinnedMessages | Listar mensajes pinados en chat | {chat_id} | lista de {id, pinnedDateTime, message} | ChatMessage.Read | — | — |
| [ ] | `teams.chat_pinned_message.pin` | create | POST /chats/{chat_id}/pinnedMessages | Pinar mensaje en chat | {chat_id, message_id} | {id, message, pinnedDateTime} | ChatMessage.ReadWrite | E | — |
| [ ] | `teams.chat_pinned_message.unpin` | delete | DELETE /chats/{chat_id}/pinnedMessages/{pinned_message_id} | Despinar mensaje | {chat_id, pinned_message_id} | {} | ChatMessage.ReadWrite | — | — |

### Permisos y Restricciones Especiales (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `teams.team.list_permission_grants` | read | GET /teams/{team_id}/permissionGrants | Listar permisos otorgados a apps en equipo | {team_id} | lista de {id, clientAppId, resourceSpecificPermissions} | DelegatedPermissionGrant.Read.All | — | — |
| [ ] | `teams.channel.list_allowed_members` | read | GET /teams/{team_id}/channels/{channel_id}/sharedWithTeams/{team_id}/allowedMembers | Listar miembros permitidos en canal compartido | {team_id, channel_id, team_id} | lista de {id, displayName, roles} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.channel.check_user_access` | read | GET /teams/{team_id}/channels/{channel_id}/doesUserHaveAccess | Verificar si usuario puede acceder canal compartido | {team_id, channel_id, user_id} | {value: true/false} | Channel.ReadBasic.All | — | — |
| [ ] | `teams.team.list_shared_channels` | read | GET /teams/{team_id}/channels/{channel_id}/sharedWithTeams | Listar equipos que comparten este canal | {team_id, channel_id} | lista de {id, tenantId, teamId, displayName} | Channel.ReadBasic.All | — | — |
