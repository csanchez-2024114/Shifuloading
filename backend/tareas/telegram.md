# Tareas: Telegram

- **Funciones catalogadas:** 126 · **Hechas:** 0 · **Pendientes:** 126 · App sin herramientas viejas
- **Documentación oficial:** https://core.telegram.org/bots/api
- **Fuentes que consultó el catálogo:** https://core.telegram.org/bots/api https://core.telegram.org/bots/api-changelog https://hackage.haskell.org/package/telegram-bot-simple-0.5.2/docs/Telegram-Bot-API-Methods.html
- **Paginación típica:** Parámetro offset en getUpdates, limit en getChatAdministrators/getUserProfilePhotos. La mayoría no pagina (devuelve array completo)
- **Qué no se pudo verificar:** (1) Exacto comportamiento de deleteMessages/forwardMessages/copyMessages con parámetros arrays (si existen) en endpoint (API reference ambigua). (2) Campos retornados en readBusinessMessage (no encontrado en referencia oficial 2026). (3) Parámetro "allow_write" en /internal/functions/{id}/test: no aplica a Telegram Bot API pública (es para sistema interno de Shifu)
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/telegram/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `telegram`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `telegram` |
| Variables del `.env` que necesitas | TELEGRAM_BOT_TOKEN |
| Conectar (caso C1) | `POST /api/v1/integrations/telegram/callback (widget de Telegram; ver el código de `telegram.py`)` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `telegram.bot.get` |
| Cómo se autentica (según el catálogo) | Tres opciones: (a) Bot API con token del usuario (recomendado): usuario crea bot con @BotFather, obtiene token 46-caracteres (ej: 123456789:ABCdefGhIJKlmNoPQRsTUVwxYZ), se autentica incluyendo en URL de cada request. Token no caduca. (b) Bot global de Shifu: usa TELEGRAM_BOT_TOKEN del servidor, chat_id del usuario. (c) MTProto API (TDLib): requiere biblioteca compilada, maneja state machine complejo, implementación riesgosa. RECOMENDACIÓN: opción (a), la única práctica. |
| Duración del token (según el catálogo) | Token no caduca (indefinido) |
| Refresco (según el catálogo) | No existe refresh token; el token es permanente hasta que el usuario lo revoque con @BotFather |
| Permisos (según el catálogo) | No existen scopes/permisos OAuth. Permisos implícitos según: si el bot está en un chat (permiso para leer msjs), si el usuario lo añadió a grupo (puede escribir ahí), si es admin de grupo (puede gestionar miembros, pins, etc.) El token no limita; la API valida si el bot tiene permiso en el chat destino |
| Restricciones de acceso | (a) Bot API requiere token válido de bot creado con @BotFather. (b) Algunos endpoints requieren que el bot sea admin del chat (p.ej. banChatMember, pinChatMessage). (c) API de usuario (getUserPersonalChatMessages) solo funciona si el bot y usuario son amigos. (d) Pagos (invoices, payments) requieren setup en Telegram @BotFather. (e) Stickers: el bot debe ser el creador del set para editarlo. (f) Sin restricción de revisión de app. Acceso inmediato. |
| Límites de ritmo | 1 msg/seg por chat (error 429 si se excede); 20 msgs/min por grupo; 30 msgs/seg globales para broadcasts; con Telegram Stars premium: hasta 1000 msgs/seg. Límite de grupos: hasta 100 grupos simultáneos por conexión webhook |
| Notas de esta app | Hoy no hay credencial de usuario utilizable (widget con HMAC que solo guarda metadatos). **Las pruebas C5 a C11 no aplican hasta que el líder decida el método** (ver el catálogo). |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `POST /api/v1/integrations/telegram/callback (widget de Telegram; ver el código de `telegram.py`)` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> telegram`. | Cuenta con `provider: telegram`, `account_id` real, `status: active` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> telegram <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/telegram.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Bot (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.bot.get` ★ | read | GET /bot{token}/getMe | Obtiene info del bot autenticado | ninguno | {id, is_bot, first_name, username, can_join_groups, can_read_all_group_messages} | — | — | — |
| [ ] | `telegram.bot.set_name` | update | POST /bot{token}/setMyName | Define nombre visible del bot | language_code, name | {ok: true} | — | — | — |
| [ ] | `telegram.bot.get_name` | read | GET /bot{token}/getMyName | Obtiene nombre del bot | language_code | {name} | — | — | — |
| [ ] | `telegram.bot.set_description` | update | POST /bot{token}/setMyDescription | Establece descripción pública del bot | language_code, description | {ok: true} | — | — | — |
| [ ] | `telegram.bot.get_description` | read | GET /bot{token}/getMyDescription | Obtiene descripción del bot | language_code | {description} | — | — | — |
| [ ] | `telegram.bot.set_short_description` | update | POST /bot{token}/setMyShortDescription | Define descripción corta del bot | language_code, short_description | {ok: true} | — | — | — |
| [ ] | `telegram.bot.get_short_description` | read | GET /bot{token}/getMyShortDescription | Obtiene descripción corta del bot | language_code | {short_description} | — | — | — |
| [ ] | `telegram.bot.set_default_admin_rights` | update | POST /bot{token}/setMyDefaultAdministratorRights | Establece derechos admin predeterminados | rights | {ok: true} | — | — | — |
| [ ] | `telegram.bot.get_default_admin_rights` | read | GET /bot{token}/getMyDefaultAdministratorRights | Obtiene derechos admin predeterminados | for_channels | {administrator_rights} | — | — | — |

### Mensajes de texto y edición (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.message.send` | create | POST /bot{token}/sendMessage | Envía mensaje de texto a un chat | chat_id, text | {message_id, chat, date, text} | — | E | — |
| [ ] | `telegram.message.send_rich` | create | POST /bot{token}/sendRichMessage | Envía mensaje con formato rico e integración de IA | chat_id, text, reply_markup | {message_id, chat, date, text} | — | E | — |
| [ ] | `telegram.message.send_rich_draft` | create | POST /bot{token}/sendRichMessageDraft | Transmite parcialmente mensaje rico en modo stream | chat_id, text | chunks de mensajes parciales | — | E | — |
| [ ] | `telegram.message.edit_text` | update | POST /bot{token}/editMessageText | Modifica texto de un mensaje existente | chat_id, message_id, text | {message_id, chat, date, text} | — | — | — |
| [ ] | `telegram.message.edit_ephemeral_text` | update | POST /bot{token}/editEphemeralMessageText | Modifica texto de mensaje efímero (solo para usuario) | chat_id, message_id, text | {message_id, chat, date, text} | — | — | — |
| [ ] | `telegram.message.delete` | delete | POST /bot{token}/deleteMessage | Elimina un mensaje del chat | chat_id, message_id | {ok: true} | — | I | — |
| [ ] | `telegram.message.delete_ephemeral` | delete | POST /bot{token}/deleteEphemeralMessage | Elimina mensaje efímero (solo visible al usuario) | chat_id, message_id | {ok: true} | — | I | — |
| [ ] | `telegram.message.forward` | create | POST /bot{token}/forwardMessage | Reenvía un mensaje existente a otro chat | chat_id, from_chat_id, message_id | {message_id, chat, date} | — | E | — |
| [ ] | `telegram.message.copy` | create | POST /bot{token}/copyMessage | Copia un mensaje (nuevo, no referencia) a otro chat | chat_id, from_chat_id, message_id | {message_id, chat, date} | — | E | — |
| [ ] | `telegram.message.send_action` | create | POST /bot{token}/sendChatAction | Muestra indicador de escritura/grabación en chat | chat_id, action | {ok: true} | — | — | — |
| [ ] | `telegram.message.set_reaction` | update | POST /bot{token}/setMessageReaction | Añade reacción emoji a un mensaje | chat_id, message_id, reaction | {ok: true} | — | — | — |
| [ ] | `telegram.message.delete_reaction` | delete | POST /bot{token}/deleteMessageReaction | Elimina reacción del usuario en un mensaje | chat_id, message_id, reaction | {ok: true} | — | — | — |
| [ ] | `telegram.message.delete_all_reactions` | delete | POST /bot{token}/deleteAllMessageReactions | Borra todas las reacciones en un mensaje | chat_id, message_id | {ok: true} | — | I | — |

### Medios (fotos, videos, documentos, audio) (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.media.send_photo` | create | POST /bot{token}/sendPhoto | Envía imagen a un chat | chat_id, photo | {message_id, chat, photo:[{file_id, file_unique_id, width, height}]} | — | E | — |
| [ ] | `telegram.media.send_document` | create | POST /bot{token}/sendDocument | Envía archivo (documento) a un chat | chat_id, document | {message_id, chat, document:{file_id, file_unique_id, file_name, mime_type}} | — | E | — |
| [ ] | `telegram.media.send_video` | create | POST /bot{token}/sendVideo | Envía video a un chat | chat_id, video | {message_id, chat, video:{file_id, file_unique_id, width, height, duration}} | — | E | — |
| [ ] | `telegram.media.send_audio` | create | POST /bot{token}/sendAudio | Envía archivo de audio/música a un chat | chat_id, audio | {message_id, chat, audio:{file_id, file_unique_id, duration, performer}} | — | E | — |
| [ ] | `telegram.media.send_animation` | create | POST /bot{token}/sendAnimation | Envía GIF/animación a un chat | chat_id, animation | {message_id, chat, animation:{file_id, file_unique_id, width, height, duration}} | — | E | — |
| [ ] | `telegram.media.send_voice` | create | POST /bot{token}/sendVoice | Envía mensaje de voz a un chat | chat_id, voice | {message_id, chat, voice:{file_id, file_unique_id, duration}} | — | E | — |
| [ ] | `telegram.media.send_video_note` | create | POST /bot{token}/sendVideoNote | Envía video circular/nota de vídeo a un chat | chat_id, video_note | {message_id, chat, video_note:{file_id, file_unique_id, length, duration}} | — | E | — |
| [ ] | `telegram.media.send_live_photo` | create | POST /bot{token}/sendLivePhoto | Envía foto viva (foto + video corto) a un chat | chat_id, photo, video | {message_id, chat, photo, video} | — | E | — |
| [ ] | `telegram.media.send_media_group` | create | POST /bot{token}/sendMediaGroup | Envía múltiples medios juntos (álbum) a un chat | chat_id, media | [{message_id, chat, photo/video/document}] | — | E | — |
| [ ] | `telegram.media.send_sticker` | create | POST /bot{token}/sendSticker | Envía sticker a un chat | chat_id, sticker | {message_id, chat, sticker:{file_id, file_unique_id, type, width, height}} | — | E | — |
| [ ] | `telegram.media.edit_media` | update | POST /bot{token}/editMessageMedia | Reemplaza el medio de un mensaje existente | chat_id, message_id, media | {message_id, chat, media} | — | — | — |
| [ ] | `telegram.media.edit_ephemeral_media` | update | POST /bot{token}/editEphemeralMessageMedia | Modifica medio de mensaje efímero | chat_id, message_id, media | {message_id, chat, media} | — | — | — |
| [ ] | `telegram.media.get_file` | read | GET /bot{token}/getFile | Obtiene información y ruta de descarga de archivo | file_id | {file_id, file_unique_id, file_size, file_path} | — | — | — |
| [ ] | `telegram.media.send_caption` | update | POST /bot{token}/editMessageCaption | Modifica pie de foto/descripción de media | chat_id, message_id, caption | {message_id, chat, caption} | — | — | — |
| [ ] | `telegram.media.edit_ephemeral_caption` | update | POST /bot{token}/editEphemeralMessageCaption | Modifica pie de foto de mensaje efímero | chat_id, message_id, caption | {message_id, chat, caption} | — | — | — |
| [ ] | `telegram.media.upload_sticker` | create | POST /bot{token}/uploadStickerFile | Sube archivo de sticker para crear set nuevo | user_id, sticker | {file_id, file_unique_id, file_size, is_animated, is_video} | — | — | — |

### Ubicación y lugares (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.location.send` | create | POST /bot{token}/sendLocation | Envía coordenadas geográficas a un chat | chat_id, latitude, longitude | {message_id, chat, location:{latitude, longitude}} | — | E | — |
| [ ] | `telegram.location.send_venue` | create | POST /bot{token}/sendVenue | Envía información de lugar (nombre, dirección) a un chat | chat_id, latitude, longitude, title, address | {message_id, chat, venue:{location, title, address}} | — | E | — |
| [ ] | `telegram.location.edit_live` | update | POST /bot{token}/editMessageLiveLocation | Actualiza ubicación en vivo compartida en un mensaje | chat_id, message_id, latitude, longitude | {message_id, chat, location} | — | — | — |
| [ ] | `telegram.location.stop_live` | update | POST /bot{token}/stopMessageLiveLocation | Detiene la compartición de ubicación en vivo | chat_id, message_id | {ok: true} | — | — | — |

### Contactos e información de usuario (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.contact.send` | create | POST /bot{token}/sendContact | Envía tarjeta de contacto (teléfono) a un chat | chat_id, phone_number, first_name | {message_id, chat, contact:{phone_number, first_name}} | — | E | — |
| [ ] | `telegram.user.get_profile_photos` | read | GET /bot{token}/getUserProfilePhotos | Obtiene fotos de perfil de un usuario | user_id, offset, limit | {total_count, photos:[[{file_id, file_unique_id, width, height}]]} | — | — | — |
| [ ] | `telegram.user.get_messages` | read | GET /bot{token}/getUserPersonalChatMessages | Accede al historial de chat privado con el usuario | user_id, offset, limit | {total_count, messages:[]} | — | — | — |

### Encuestas y juegos (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.poll.send` | create | POST /bot{token}/sendPoll | Crea y envía encuesta/quiz a un chat | chat_id, question, options | {message_id, chat, poll:{id, question, options:[{text, voter_count}]}} | — | E | — |
| [ ] | `telegram.dice.send` | create | POST /bot{token}/sendDice | Envía dado/ruleta/dardo con emoji especial | chat_id, emoji | {message_id, chat, dice:{emoji, value}} | — | E | — |
| [ ] | `telegram.checklist.send` | create | POST /bot{token}/sendChecklist | Envía lista de verificación/tareas | chat_id, checklist_items | {message_id, chat, checklist} | — | E | — |
| [ ] | `telegram.checklist.edit` | update | POST /bot{token}/editMessageChecklist | Modifica lista de verificación existente | chat_id, message_id, checklist_items | {message_id, chat, checklist} | — | — | — |
| [ ] | `telegram.game.send` | create | POST /bot{token}/sendGame | Envía juego HTML5 en línea a un chat | chat_id, game_short_name | {message_id, chat, game:{title, description}} | — | E | — |
| [ ] | `telegram.game.set_score` | update | POST /bot{token}/setGameScore | Establece puntuación de juego para un usuario | user_id, score, game_message_id | {ok: true} | — | — | — |
| [ ] | `telegram.game.get_high_scores` | read | GET /bot{token}/getGameHighScores | Obtiene mejores puntuaciones de un juego | user_id, game_message_id | [{position, user, score}] | — | — | — |

### Gestión de chats y miembros (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.chat.get` | read | GET /bot{token}/getChat | Obtiene información completa de un chat/grupo | chat_id | {id, type, title, description, member_count, pinned_message, permissions} | — | — | — |
| [ ] | `telegram.chat.get_member` | read | GET /bot{token}/getChatMember | Obtiene info de un miembro específico del chat | chat_id, user_id | {user, status, custom_title, is_member, can_send_messages} | — | — | — |
| [ ] | `telegram.chat.get_member_count` | read | GET /bot{token}/getChatMemberCount | Obtiene cantidad total de miembros del chat | chat_id | count | — | — | — |
| [ ] | `telegram.chat.get_administrators` | read | GET /bot{token}/getChatAdministrators | Lista todos los administradores del chat | chat_id | [{user, status, custom_title, can_be_edited}] | — | — | — |
| [ ] | `telegram.chat.set_title` | update | POST /bot{token}/setChatTitle | Cambia el título/nombre de un grupo o canal | chat_id, title | {ok: true} | — | — | — |
| [ ] | `telegram.chat.set_description` | update | POST /bot{token}/setChatDescription | Define descripción del chat | chat_id, description | {ok: true} | — | — | — |
| [ ] | `telegram.chat.set_photo` | update | POST /bot{token}/setChatPhoto | Establece foto de perfil del chat | chat_id, photo | {ok: true} | — | — | — |
| [ ] | `telegram.chat.delete_photo` | delete | POST /bot{token}/deleteChatPhoto | Borra foto de perfil del chat | chat_id | {ok: true} | — | — | — |
| [ ] | `telegram.chat.set_permissions` | update | POST /bot{token}/setChatPermissions | Define permisos predeterminados para todos los miembros | chat_id, permissions | {ok: true} | — | — | — |
| [ ] | `telegram.chat.ban_member` | update | POST /bot{token}/banChatMember | Expulsa/bloquea a un usuario del chat/grupo | chat_id, user_id, until_date | {ok: true} | — | I | — |
| [ ] | `telegram.chat.unban_member` | update | POST /bot{token}/unbanChatMember | Revoca expulsión de un usuario | chat_id, user_id | {ok: true} | — | — | — |
| [ ] | `telegram.chat.restrict_member` | update | POST /bot{token}/restrictChatMember | Limita permisos de un miembro (no puede enviar medios, etc.) | chat_id, user_id, permissions | {ok: true} | — | — | — |
| [ ] | `telegram.chat.promote_member` | update | POST /bot{token}/promoteChatMember | Promueve usuario a administrador con permisos específicos | chat_id, user_id, can_manage_chat, can_delete_messages | {ok: true} | — | — | — |
| [ ] | `telegram.chat.set_admin_title` | update | POST /bot{token}/setChatAdministratorCustomTitle | Establece título personalizado para admin | chat_id, user_id, custom_title | {ok: true} | — | — | — |
| [ ] | `telegram.chat.leave` | update | POST /bot{token}/leaveChat | Bot abandona/se retira del chat | chat_id | {ok: true} | — | — | — |
| [ ] | `telegram.chat.approve_join_request` | update | POST /bot{token}/approveChatJoinRequest | Aprueba solicitud de un usuario para unirse al grupo | chat_id, user_id | {ok: true} | — | — | — |
| [ ] | `telegram.chat.decline_join_request` | update | POST /bot{token}/declineChatJoinRequest | Rechaza solicitud de unión de usuario | chat_id, user_id | {ok: true} | — | — | — |

### Mensajes anclados (pins) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.pin.pin_message` | create | POST /bot{token}/pinChatMessage | Ancla un mensaje en la parte superior del chat | chat_id, message_id, disable_notification | {ok: true} | — | E | — |
| [ ] | `telegram.pin.unpin_message` | delete | POST /bot{token}/unpinChatMessage | Desancla un mensaje específico | chat_id, message_id | {ok: true} | — | — | — |
| [ ] | `telegram.pin.unpin_all` | delete | POST /bot{token}/unpinAllChatMessages | Desancla todos los mensajes del chat | chat_id | {ok: true} | — | I | — |

### Enlaces de invitación (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.invite.create` | create | POST /bot{token}/createChatInviteLink | Crea nuevo enlace de invitación para el grupo | chat_id, expire_date, member_limit | {invite_link, creator, creates_join_request} | — | E | — |
| [ ] | `telegram.invite.export` | read | GET /bot{token}/exportChatInviteLink | Obtiene/exporta enlace de invitación primario del chat | chat_id | {invite_link} | — | — | — |
| [ ] | `telegram.invite.edit` | update | POST /bot{token}/editChatInviteLink | Modifica enlace de invitación existente | chat_id, invite_link, expire_date, member_limit | {invite_link, creator, creates_join_request} | — | — | — |
| [ ] | `telegram.invite.revoke` | delete | POST /bot{token}/revokeChatInviteLink | Revoca/invalida un enlace de invitación | chat_id, invite_link | {invite_link, is_revoked} | — | — | — |

### Actualizaciones y webhooks (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.updates.get` | read | GET /bot{token}/getUpdates | Recibe actualizaciones (mensajes, eventos) por long polling | offset, limit, timeout | {update_id, message, callback_query, edited_message} | — | — | — |
| [ ] | `telegram.webhook.set` | create | POST /bot{token}/setWebhook | Configura webhook para recibir actualizaciones | url, certificate, secret_token | {ok: true} | — | — | — |
| [ ] | `telegram.webhook.delete` | delete | POST /bot{token}/deleteWebhook | Elimina webhook y vuelve a polling | — | {ok: true} | — | — | — |
| [ ] | `telegram.webhook.get_info` | read | GET /bot{token}/getWebhookInfo | Obtiene estado/info del webhook actual | — | {url, has_custom_certificate, pending_update_count, last_error_date} | — | — | — |

### Respuestas a callbacks e inline queries (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.callback.answer` | update | POST /bot{token}/answerCallbackQuery | Responde a click de botón (callback) mostrando popup/alerta | callback_query_id, text, show_alert | {ok: true} | — | E | — |
| [ ] | `telegram.inline_query.answer` | update | POST /bot{token}/answerInlineQuery | Proporciona resultados para búsqueda inline del usuario | inline_query_id, results | {ok: true} | — | E | — |
| [ ] | `telegram.guest_query.answer` | update | POST /bot{token}/answerGuestQuery | Responde a consulta de usuario en modo guest (sin cuenta) | guest_user_id, query_payload, results | {ok: true} | — | E | — |
| [ ] | `telegram.join_request.answer` | update | POST /bot{token}/answerChatJoinRequestQuery | Responde a interacción de solicitud de unión | user_id, chat_id, approved | {ok: true} | — | — | — |
| [ ] | `telegram.message.set_reply_markup` | update | POST /bot{token}/editMessageReplyMarkup | Modifica botones/teclado de un mensaje | chat_id, message_id, reply_markup | {message_id, chat, reply_markup} | — | — | — |
| [ ] | `telegram.message.edit_ephemeral_reply_markup` | update | POST /bot{token}/editEphemeralMessageReplyMarkup | Modifica botones de mensaje efímero | chat_id, message_id, reply_markup | {message_id, chat, reply_markup} | — | — | — |

### Comandos del bot (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.command.set` | create | POST /bot{token}/setMyCommands | Registra lista de comandos visibles en menú del bot | commands, language_code, scope | {ok: true} | — | — | — |
| [ ] | `telegram.command.get` | read | GET /bot{token}/getMyCommands | Obtiene lista de comandos registrados del bot | language_code, scope | [{command, description}] | — | — | — |
| [ ] | `telegram.command.delete` | delete | POST /bot{token}/deleteMyCommands | Borra todos los comandos del bot | language_code, scope | {ok: true} | — | — | — |

### Stickers (14)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.sticker.get_set` | read | GET /bot{token}/getStickerSet | Obtiene info de un set de stickers | name | {name, title, sticker_type, is_animated, is_video, stickers:[]} | — | — | — |
| [ ] | `telegram.sticker.upload_file` | create | POST /bot{token}/uploadStickerFile | Sube archivo de sticker para añadir a un set | user_id, sticker, sticker_format | {file_id, file_unique_id, file_size, is_animated} | — | — | — |
| [ ] | `telegram.sticker.create_set` | create | POST /bot{token}/createNewStickerSet | Crea nuevo set de stickers del usuario | user_id, name, title, stickers | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.add_to_set` | update | POST /bot{token}/addStickerToSet | Añade sticker a un set existente | user_id, name, sticker | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_position` | update | POST /bot{token}/setStickerPositionInSet | Cambia orden de un sticker dentro del set | sticker, position | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.delete_from_set` | delete | POST /bot{token}/deleteStickerFromSet | Elimina sticker de un set | sticker | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.replace_in_set` | update | POST /bot{token}/replaceStickerInSet | Reemplaza un sticker en el set | user_id, name, old_sticker, new_sticker | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_emoji_list` | update | POST /bot{token}/setStickerEmojiList | Asigna emojis a un sticker | sticker, emoji_list | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_keywords` | update | POST /bot{token}/setStickerKeywords | Asigna palabras clave de búsqueda a un sticker | sticker, keywords | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_mask_position` | update | POST /bot{token}/setStickerMaskPosition | Configura máscara/posición de sticker de filtro | sticker, mask_position | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_thumbnail` | update | POST /bot{token}/setStickerSetThumbnail | Establece miniatura de un set de stickers | name, user_id, thumbnail | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.set_title` | update | POST /bot{token}/setStickerSetTitle | Cambia título de un set de stickers | name, title | {ok: true} | — | — | — |
| [ ] | `telegram.sticker.delete_set` | delete | POST /bot{token}/deleteStickerSet | Elimina completamente un set de stickers | name | {ok: true} | — | I | — |
| [ ] | `telegram.sticker.get_custom_emoji` | read | GET /bot{token}/getCustomEmojiStickers | Obtiene objetos Sticker de emojis personalizados | custom_emoji_ids | [{file_id, file_unique_id, type, custom_emoji_id}] | — | — | — |

### Pagos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.payment.send_invoice` | create | POST /bot{token}/sendInvoice | Envía factura/solicitud de pago a un usuario | chat_id, title, description, payload, prices | {message_id, chat, invoice:{title, description, currency}} | — | E, I | — |
| [ ] | `telegram.payment.answer_shipping` | update | POST /bot{token}/answerShippingQuery | Responde a consulta de envío en checkout | shipping_query_id, ok, shipping_options | {ok: true} | — | — | — |
| [ ] | `telegram.payment.answer_precheckout` | update | POST /bot{token}/answerPreCheckoutQuery | Confirma/rechaza pago antes de procesar | pre_checkout_query_id, ok | {ok: true} | — | — | — |
| [ ] | `telegram.payment.get_star_balance` | read | GET /bot{token}/getMyStarBalance | Obtiene balance actual de Telegram Stars del bot | — | {star_count} | — | — | — |
| [ ] | `telegram.payment.get_star_transactions` | read | GET /bot{token}/getStarTransactions | Obtiene historial de transacciones de Stars | offset, limit | {transactions:[{id, amount, date, source}], total_count} | — | — | — |
| [ ] | `telegram.payment.refund_star` | update | POST /bot{token}/refundStarPayment | Reembolsa pago en Telegram Stars | user_id, telegram_payment_charge_id | {ok: true} | — | — | — |

### Cuentas de negocio y historias (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.business.set_name` | update | POST /bot{token}/setBusinessAccountName | Establece nombre de cuenta de negocio | name | {ok: true} | — | — | — |
| [ ] | `telegram.business.set_username` | update | POST /bot{token}/setBusinessAccountUsername | Establece username/nombre de usuario de negocio | username | {ok: true} | — | — | — |
| [ ] | `telegram.business.set_bio` | update | POST /bot{token}/setBusinessAccountBio | Establece biografía de cuenta de negocio | bio | {ok: true} | — | — | — |
| [ ] | `telegram.business.set_profile_photo` | update | POST /bot{token}/setBusinessAccountProfilePhoto | Establece foto de perfil de negocio | photo | {ok: true} | — | — | — |
| [ ] | `telegram.business.delete_profile_photo` | delete | POST /bot{token}/removeBusinessAccountProfilePhoto | Elimina foto de perfil de negocio | — | {ok: true} | — | — | — |
| [ ] | `telegram.business.read_message` | read | GET /bot{token}/readBusinessMessage | Lee mensaje privado de negocio | chat_id, message_id | {text, attachments} | — | — | — |
| [ ] | `telegram.business.delete_messages` | delete | POST /bot{token}/deleteBusinessMessages | Borra mensajes privados de negocio | chat_id, message_ids | {ok: true} | — | I | — |
| [ ] | `telegram.story.post` | create | POST /bot{token}/postStory | Publica historia en el perfil de negocio | media, caption | {story_id} | — | E, I | — |
| [ ] | `telegram.story.edit` | update | POST /bot{token}/editStory | Modifica historia publicada | story_id, media, caption | {ok: true} | — | — | — |
| [ ] | `telegram.story.delete` | delete | POST /bot{token}/deleteStory | Elimina historia del perfil | story_id | {ok: true} | — | I | — |
| [ ] | `telegram.story.repost` | create | POST /bot{token}/repostStory | Comparte historia en múltiples perfiles/cuentas | story_id, target_user_id | {ok: true} | — | E | — |
| [ ] | `telegram.gift.send` | create | POST /bot{token}/sendGift | Envía regalo/gifting a un usuario | user_id, gift_id, text | {ok: true} | — | E | — |

### Verificación y acceso (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.user.verify` | update | POST /bot{token}/verifyUser | Verifica identidad de usuario (para cuenta de negocio) | user_id, custom_data | {ok: true} | — | — | — |
| [ ] | `telegram.chat.verify` | update | POST /bot{token}/verifyChat | Verifica identidad de un chat/grupo | chat_id, custom_data | {ok: true} | — | — | — |
| [ ] | `telegram.user.set_emoji_status` | update | POST /bot{token}/setUserEmojiStatus | Establece estado emoji personalizado de usuario | user_id, emoji_status_custom_emoji_id | {ok: true} | — | — | — |

### Acceso de bots gestionados (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `telegram.managed_bot.get_access_settings` | read | GET /bot{token}/getManagedBotAccessSettings | Obtiene configuración de acceso de bot gestionado | managed_user_id | {is_shared, allow_user_chats, allow_bot_chats, allow_group_chats, allow_channel_chats} | — | — | — |
| [ ] | `telegram.managed_bot.set_access_settings` | update | POST /bot{token}/setManagedBotAccessSettings | Configura quién puede acceder a bot gestionado | managed_user_id, is_shared, allow_user_chats | {ok: true} | — | — | — |
