# Tareas: Outlook

- **Funciones catalogadas:** 99 · **Hechas:** 0 · **Pendientes:** 99 · App sin herramientas viejas
- **Documentación oficial:** https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview
- **Fuentes que consultó el catálogo:** https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview https://learn.microsoft.com/en-us/graph/api/resources/message https://learn.microsoft.com/en-us/graph/api/resources/mailfolder https://learn.microsoft.com/en-us/graph/api/resources/attachment https://learn.microsoft.com/en-us/graph/api/resources/calendar https://learn.microsoft.com/en-us/graph/api/resources/event https://learn.microsoft.com/en-us/graph/api/resources/contact https://learn.microsoft.com/en-us/graph/api/resources/messagerule https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory https://learn.microsoft.com/en-us/graph/api/resources/user
- **Paginación típica:** OData v4; parámetro $skip y $top; propiedad @odata.nextLink para páginas sucesivas; por defecto 10 resultados
- **Qué no se pudo verificar:** El soporte exacto para asignar permisos a carpetas compartidas (delegate) se menciona en documentación pero detalles de endpoints incompletos; fechas de expiración de refresh token varían según configuración; algunos campos extendidos requieren header Prefer: outlook.body-content-type
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/outlook/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `outlook`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `outlook` |
| Variables del `.env` que necesitas | OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/outlook/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `outlook.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2 con código de autorización y refresh token de Microsoft; permisos delegados al usuario |
| Duración del token (según el catálogo) | Access token: 1 hora (3600 segundos); refresh token: 180 días (reutilizable hasta revocación) |
| Refresco (según el catálogo) | Sí, refresh token en respuesta inicial; se renueva automáticamente; la aplicación debe mantenerlo |
| Permisos (según el catálogo) | Mail.Read, Mail.ReadWrite, Mail.Send, Calendar.Read, Calendar.ReadWrite, Contacts.Read, Contacts.ReadWrite, MailboxSettings.Read, MailboxSettings.ReadWrite |
| Restricciones de acceso | Solo cuentas de Microsoft 365 (trabajo, escuela) u Outlook.com; cuentas Exchange on-premises con soporte híbrido; requiere autenticación MFA |
| Límites de ritmo | 2000 mensajes/carpeta por solicitud; 50 eventos por solicitud; throttling: 10.000 solicitudes/minuto por app; 4 MB máximo por mensaje; 150 MB con sesión de carga |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/outlook/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> outlook`. | Cuenta con `provider: outlook`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/outlook.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> outlook <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Outlook. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/outlook.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Perfil (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.user.get` ★ | read | GET /me | Obtener perfil del usuario conectado | — | {id, displayName, mail, userPrincipalName, jobTitle, mobilePhone, officeLocation} | Mail.Read | — | — |

### Correo - Mensajes (18)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.message.list` | read | GET /me/messages | Listar todos los mensajes en el buzón | $filter, $search, $orderby, $select | lista de {id, subject, from, toRecipients, receivedDateTime, isRead} + paginación | Mail.Read | — | — |
| [ ] | `outlook.message.get` | read | GET /me/messages/{id} | Obtener detalles de un mensaje | — | {id, subject, body, from, toRecipients, ccRecipients, bccRecipients, receivedDateTime, sentDateTime, isRead, hasAttachments, categories} | Mail.Read | — | — |
| [ ] | `outlook.message.search` | read | GET /me/messages | Buscar mensajes por filtro/búsqueda | $search, $filter, $orderby | lista filtrada de mensajes | Mail.Read | — | — |
| [ ] | `outlook.message.create` | create | POST /me/messages | Crear un borrador de mensaje | subject, bodyPreview, toRecipients | {id, isDraft} | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.update` | update | PATCH /me/messages/{id} | Actualizar un mensaje (solo borradores) | isRead, categories, flag | mensaje actualizado | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.delete` | delete | DELETE /me/messages/{id} | Eliminar un mensaje | — | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.send` | create | POST /me/messages/{id}/send | Enviar un borrador | — | — | Mail.Send | E, I | — |
| [ ] | `outlook.message.reply` | create | POST /me/messages/{id}/reply | Responder a un mensaje | comment, toRecipients | mensaje de respuesta en borrador | Mail.Send | E | — |
| [ ] | `outlook.message.reply_all` | create | POST /me/messages/{id}/replyall | Responder a todos en un mensaje | comment | mensaje de respuesta en borrador | Mail.Send | E | — |
| [ ] | `outlook.message.forward` | create | POST /me/messages/{id}/createforward | Crear borrador para reenviar | comment, toRecipients | mensaje reenviado en borrador | Mail.Send | E | — |
| [ ] | `outlook.message.move` | update | POST /me/messages/{id}/move | Mover a otra carpeta | destinationId | mensaje movido | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.copy` | create | POST /me/messages/{id}/copy | Copiar a otra carpeta | destinationId | copia creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.mark_as_read` | update | PATCH /me/messages/{id} | Marcar como leído | isRead=true | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.mark_as_unread` | update | PATCH /me/messages/{id} | Marcar como no leído | isRead=false | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.flag` | update | PATCH /me/messages/{id} | Marcar con bandera para seguimiento | flag.flagStatus | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.categorize` | update | PATCH /me/messages/{id} | Asignar categorías | categories | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.message.permanently_delete` | delete | DELETE /me/messages/{id} | Eliminar permanentemente de Elementos Recuperables | — | — | Mail.ReadWrite | I | — |
| [ ] | `outlook.message.delta` | read | GET /me/messages/delta() | Obtener cambios incrementales en mensajes | — | cambios agregados, actualizados o eliminados | Mail.Read | — | — |

### Correo - Carpetas (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.folder.list` | read | GET /me/mailFolders | Listar todas las carpetas de correo | $filter, $select | lista de {id, displayName, parentFolderId, totalItemCount, unreadItemCount} | Mail.Read | — | — |
| [ ] | `outlook.folder.get` | read | GET /me/mailFolders/{id} | Obtener detalles de una carpeta | — | {id, displayName, isHidden, childFolderCount, totalItemCount, unreadItemCount} | Mail.Read | — | — |
| [ ] | `outlook.folder.create` | create | POST /me/mailFolders | Crear una nueva carpeta | displayName | carpeta creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.update` | update | PATCH /me/mailFolders/{id} | Actualizar propiedades de carpeta | displayName, isHidden | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.delete` | delete | DELETE /me/mailFolders/{id} | Eliminar carpeta | — | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.move` | update | POST /me/mailFolders/{id}/move | Mover carpeta a otra ubicación | parentFolderId | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.copy` | create | POST /me/mailFolders/{id}/copy | Copiar carpeta a otro destino | parentFolderId | carpeta copiada | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.child_list` | read | GET /me/mailFolders/{id}/childFolders | Listar subcarpetas | — | lista de carpetas hijas | Mail.Read | — | — |
| [ ] | `outlook.folder.child_create` | create | POST /me/mailFolders/{id}/childFolders | Crear una subcarpeta | displayName | subcarpeta creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.folder.permanently_delete` | delete | DELETE /me/mailFolders/{id} | Eliminar carpeta de forma permanente | — | — | Mail.ReadWrite | I | — |
| [ ] | `outlook.folder.messages_list` | read | GET /me/mailFolders/{id}/messages | Listar mensajes en una carpeta específica | $filter, $search, $orderby | lista de mensajes en carpeta | Mail.Read | — | — |
| [ ] | `outlook.folder.delta` | read | GET /me/mailFolders/delta() | Obtener cambios incrementales en carpetas | — | cambios en carpetas | Mail.Read | — | — |

### Correo - Adjuntos (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.attachment.list` | read | GET /me/messages/{messageId}/attachments | Listar adjuntos de un mensaje | — | lista de {id, name, contentType, size, isInline} | Mail.Read | — | — |
| [ ] | `outlook.attachment.get` | read | GET /me/messages/{messageId}/attachments/{id} | Obtener detalles de un adjunto | — | {id, name, contentType, size, lastModifiedDateTime} | Mail.Read | — | — |
| [ ] | `outlook.attachment.add` | create | POST /me/messages/{messageId}/attachments | Agregar un adjunto (< 3 MB) | file, name, contentType | adjunto creado | Mail.ReadWrite | — | — |
| [ ] | `outlook.attachment.delete` | delete | DELETE /me/messages/{messageId}/attachments/{id} | Eliminar un adjunto | — | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.attachment.upload_session` | create | POST /me/messages/{messageId}/attachments/createUploadSession | Crear sesión para archivo grande (3-150 MB) | attachmentItem | {uploadUrl, expirationDateTime} | Mail.ReadWrite | — | — |

### Correo - Reglas de Bandeja (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.rule.list` | read | GET /me/mailFolders/inbox/messageRules | Listar reglas de bandeja de entrada | — | lista de {id, displayName, isEnabled, sequence} | Mail.Read | — | — |
| [ ] | `outlook.rule.get` | read | GET /me/mailFolders/inbox/messageRules/{id} | Obtener detalles de una regla | — | {id, displayName, conditions, actions, isEnabled} | Mail.Read | — | — |
| [ ] | `outlook.rule.create` | create | POST /me/mailFolders/inbox/messageRules | Crear una nueva regla | displayName, conditions, actions, isEnabled | regla creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.rule.update` | update | PATCH /me/mailFolders/inbox/messageRules/{id} | Actualizar una regla existente | displayName, actions, conditions | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.rule.delete` | delete | DELETE /me/mailFolders/inbox/messageRules/{id} | Eliminar una regla | — | — | Mail.ReadWrite | — | — |

### Correo - Categorías (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.category.list` | read | GET /me/outlook/masterCategories | Listar todas las categorías | — | lista de {displayName, color} | Mail.Read | — | — |
| [ ] | `outlook.category.get` | read | GET /me/outlook/masterCategories/{id} | Obtener detalles de una categoría | — | {displayName, color, id} | Mail.Read | — | — |
| [ ] | `outlook.category.create` | create | POST /me/outlook/masterCategories | Crear una nueva categoría | displayName, color | categoría creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.category.update` | update | PATCH /me/outlook/masterCategories/{id} | Actualizar color de categoría | color | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.category.delete` | delete | DELETE /me/outlook/masterCategories/{id} | Eliminar una categoría | — | — | Mail.ReadWrite | — | — |

### Correo - Configuración (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.settings.get` | read | GET /me/mailboxSettings | Obtener configuración de buzón | — | {automaticRepliesSetting, locale, timeZone, workingHours} | MailboxSettings.Read | — | — |
| [ ] | `outlook.settings.update` | update | PATCH /me/mailboxSettings | Actualizar configuración de buzón | automaticRepliesSetting, timeZone, locale | — | MailboxSettings.ReadWrite | — | — |
| [ ] | `outlook.inbox_override.list` | read | GET /me/inferenceClassification/overrides | Listar excepciones de Bandeja Prioritaria | — | lista de remitentes y clasificación | Mail.Read | — | — |
| [ ] | `outlook.inbox_override.create` | create | POST /me/inferenceClassification/overrides | Crear excepción de Bandeja Prioritaria | senderEmailAddress, classifyAs | excepción creada | Mail.ReadWrite | — | — |
| [ ] | `outlook.inbox_override.delete` | delete | DELETE /me/inferenceClassification/overrides/{id} | Eliminar excepción de Bandeja Prioritaria | — | — | Mail.ReadWrite | — | — |
| [ ] | `outlook.mail.tips` | read | POST /me/getMailTips | Obtener MailTips (estado especial de destinatarios) | recipients | {mailTips para cada destinatario} | Mail.Read | — | — |
| [ ] | `outlook.reply.auto_set` | update | PATCH /me/mailboxSettings | Configurar respuesta automática | automaticRepliesSetting.externalAudience | — | MailboxSettings.ReadWrite | E | — |

### Calendario - Calendarios (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.calendar.list` | read | GET /me/calendars | Listar todos los calendarios del usuario | — | lista de {id, name, color, isDefaultCalendar, owner} | Calendar.Read | — | — |
| [ ] | `outlook.calendar.get` | read | GET /me/calendars/{id} | Obtener detalles de un calendario | — | {id, name, color, canEdit, canShare, owner} | Calendar.Read | — | — |
| [ ] | `outlook.calendar.create` | create | POST /me/calendars | Crear un nuevo calendario | name | calendario creado | Calendar.ReadWrite | — | — |
| [ ] | `outlook.calendar.update` | update | PATCH /me/calendars/{id} | Actualizar propiedades del calendario | name, color | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.calendar.delete` | delete | DELETE /me/calendars/{id} | Eliminar un calendario | — | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.calendar.permanently_delete` | delete | POST /me/calendars/{id}/permanentDelete | Eliminar calendario de forma permanente | — | — | Calendar.ReadWrite | I | — |

### Calendario - Grupos de Calendarios (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.calendar_group.list` | read | GET /me/calendarGroups | Listar grupos de calendarios | — | lista de {id, name, changeKey} | Calendar.Read | — | — |
| [ ] | `outlook.calendar_group.get` | read | GET /me/calendarGroups/{id} | Obtener detalles de un grupo | — | {id, name, changeKey} | Calendar.Read | — | — |
| [ ] | `outlook.calendar_group.create` | create | POST /me/calendarGroups | Crear un nuevo grupo de calendarios | name | grupo creado | Calendar.ReadWrite | — | — |
| [ ] | `outlook.calendar_group.update` | update | PATCH /me/calendarGroups/{id} | Actualizar grupo de calendarios | name | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.calendar_group.delete` | delete | DELETE /me/calendarGroups/{id} | Eliminar grupo de calendarios | — | — | Calendar.ReadWrite | — | — |

### Calendario - Eventos (15)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.event.list` | read | GET /me/events | Listar todos los eventos del usuario | $filter, $orderby, $select | lista de {id, subject, start, end, organizer, attendees, isOrganizer} | Calendar.Read | — | — |
| [ ] | `outlook.event.get` | read | GET /me/events/{id} | Obtener detalles de un evento | — | {id, subject, body, start, end, location, attendees, isOnlineMeeting, onlineMeetingUrl} | Calendar.Read | — | — |
| [ ] | `outlook.event.create` | create | POST /me/events | Crear un nuevo evento | subject, start, end, attendees | evento creado | Calendar.ReadWrite | — | — |
| [ ] | `outlook.event.update` | update | PATCH /me/events/{id} | Actualizar un evento existente | subject, start, end, body, location | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.event.delete` | delete | DELETE /me/events/{id} | Eliminar un evento | — | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.event.accept` | update | POST /me/events/{id}/accept | Aceptar invitación de reunión | comment | — | Calendar.ReadWrite | E | — |
| [ ] | `outlook.event.tentatively_accept` | update | POST /me/events/{id}/tentativelyAccept | Aceptar tentativamente invitación | comment | — | Calendar.ReadWrite | E | — |
| [ ] | `outlook.event.decline` | update | POST /me/events/{id}/decline | Rechazar invitación de reunión | comment | — | Calendar.ReadWrite | E | — |
| [ ] | `outlook.event.forward` | update | POST /me/events/{id}/forward | Reenviar evento a otra persona | comment, toRecipients | — | Calendar.ReadWrite | E | — |
| [ ] | `outlook.event.cancel` | update | POST /me/events/{id}/cancel | Cancelar una reunión | comment | — | Calendar.ReadWrite | E, I | — |
| [ ] | `outlook.event.snooze_reminder` | update | POST /me/events/{id}/snoozeReminder | Posponer recordatorio de evento | newReminderMinutes | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.event.dismiss_reminder` | update | POST /me/events/{id}/dismissReminder | Descartar recordatorio de evento | — | — | Calendar.ReadWrite | — | — |
| [ ] | `outlook.event.permanently_delete` | delete | DELETE /me/events/{id} | Eliminar evento de forma permanente | — | — | Calendar.ReadWrite | I | — |
| [ ] | `outlook.event.instances_list` | read | GET /me/events/{id}/instances | Listar instancias de evento recurrente | $filter, $select | lista de instancias | Calendar.Read | — | — |
| [ ] | `outlook.event.delta` | read | GET /me/calendarview/delta() | Obtener cambios incrementales de eventos en rango | startDateTime, endDateTime | cambios en eventos | Calendar.Read | — | — |

### Calendario - Vistas Calendario (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.calendar_view.list` | read | GET /me/calendarview | Listar eventos en rango de fechas | startDateTime, endDateTime, $orderby | lista de eventos en rango | Calendar.Read | — | — |
| [ ] | `outlook.calendar_view.calendar` | read | GET /me/calendars/{id}/calendarview | Listar eventos de un calendario específico | startDateTime, endDateTime | lista de eventos | Calendar.Read | — | — |
| [ ] | `outlook.reminder.view` | read | GET /me/reminderview | Obtener recordatorios dentro de rango | startDateTime, endDateTime | lista de recordatorios | Calendar.Read | — | — |

### Calendario - Disponibilidad y Reuniones (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.schedule.get` | read | POST /me/calendar/getSchedule | Obtener disponibilidad (libre/ocupado) de usuarios | items (emails), startTime, endTime | {availabilityView, scheduleItems} | Calendar.Read | — | — |
| [ ] | `outlook.meeting_times.find` | read | POST /me/findMeetingTimes | Encontrar horarios para reunión | attendees, timeSlotDuration, minimumAttendeePercentage | {meetingTimeSuggestions, isLocationRequired} | Calendar.Read | — | — |

### Contactos - Contactos (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.contact.list` | read | GET /me/contacts | Listar todos los contactos | $filter, $search, $orderby | lista de {id, displayName, emailAddresses, phoneNumbers} | Contacts.Read | — | — |
| [ ] | `outlook.contact.get` | read | GET /me/contacts/{id} | Obtener detalles de un contacto | — | {id, displayName, emailAddresses, phoneNumbers, businessPhones, mobilePhone, homeAddress, businessAddress, jobTitle, companyName} | Contacts.Read | — | — |
| [ ] | `outlook.contact.create` | create | POST /me/contacts | Crear un nuevo contacto | displayName, emailAddresses | contacto creado | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact.update` | update | PATCH /me/contacts/{id} | Actualizar información del contacto | displayName, emailAddresses, phoneNumbers, jobTitle, companyName | — | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact.delete` | delete | DELETE /me/contacts/{id} | Eliminar un contacto | — | — | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact.permanently_delete` | delete | DELETE /me/contacts/{id} | Eliminar contacto de forma permanente | — | — | Contacts.ReadWrite | I | — |
| [ ] | `outlook.contact.delta` | read | GET /me/contacts/delta() | Obtener cambios incrementales en contactos | — | cambios en contactos | Contacts.Read | — | — |
| [ ] | `outlook.contact.set_photo` | create | PUT /me/contacts/{id}/photo/$value | Establecer foto de contacto | binary file | — | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact.get_photo` | read | GET /me/contacts/{id}/photo/$value | Obtener foto de contacto | — | imagen binaria | Contacts.Read | — | — |

### Contactos - Carpetas de Contactos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `outlook.contact_folder.list` | read | GET /me/contactFolders | Listar todas las carpetas de contactos | — | lista de {id, displayName, parentFolderId} | Contacts.Read | — | — |
| [ ] | `outlook.contact_folder.get` | read | GET /me/contactFolders/{id} | Obtener detalles de una carpeta de contactos | — | {id, displayName, parentFolderId, childFolderCount} | Contacts.Read | — | — |
| [ ] | `outlook.contact_folder.create` | create | POST /me/contactFolders | Crear una nueva carpeta de contactos | displayName | carpeta creada | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact_folder.update` | update | PATCH /me/contactFolders/{id} | Actualizar carpeta de contactos | displayName | — | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact_folder.delete` | delete | DELETE /me/contactFolders/{id} | Eliminar carpeta de contactos | — | — | Contacts.ReadWrite | — | — |
| [ ] | `outlook.contact_folder.contacts_list` | read | GET /me/contactFolders/{id}/contacts | Listar contactos en una carpeta | — | lista de contactos en carpeta | Contacts.Read | — | — |
