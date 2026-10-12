# Tareas: Google Calendar

- **Funciones catalogadas:** 39 · **Hechas:** 0 · **Pendientes:** 39 · App sin herramientas viejas
- **Documentación oficial:** https://developers.google.com/calendar/api/v3/reference
- **Fuentes que consultó el catálogo:** https://developers.google.com/calendar/api/v3/reference https://developers.google.com/calendar/api/auth https://developers.google.com/calendar/api/guides/quota https://developers.google.com/calendar/api/v3/reference/events/list https://developers.google.com/calendar/api/v3/reference/events/insert https://developers.google.com/calendar/api/v3/reference/events/move https://developers.google.com/calendar/api/v3/reference/events/import https://developers.google.com/calendar/api/v3/reference/events/instances https://developers.google.com/calendar/api/v3/reference/events/quickAdd https://developers.google.com/calendar/api/v3/reference/events/patch https://developers.google.com/calendar/api/v3/reference/events/delete https://developers.google.com/calendar/api/v3/reference/events/get https://developers.google.com/calendar/api/v3/reference/acl/insert https://developers.google.com/calendar/api/v3/reference/acl/list https://developers.google.com/calendar/api/v3/reference/calendarList/list https://developers.google.com/calendar/api/v3/reference/calendarList/insert https://developers.google.com/calendar/api/v3/reference/settings/list https://developers.google.com/calendar/api/v3/reference/calendars/insert https://developers.google.com/calendar/api/v3/reference/calendars/get https://developers.google.com/calendar/api/v3/reference/calendars/clear https://developers.google.com/calendar/api/v3/reference/calendars/transferOwnership https://developers.google.com/calendar/api/v3/reference/freebusy/query https://developers.google.com/calendar/api/v3/reference/colors/get
- **Paginación típica:** pageToken / nextPageToken con maxResults (events.list por defecto 250, max 2500; calendarList, acl y settings por defecto 100, max 250); sincronizacion incremental con syncToken / nextSyncToken
- **Qué no se pudo verificar:** vida del access token y detalle del refresh (conocimiento general de Google, no leido en las paginas consultadas); permisos exactos de calendars.update/patch/delete, calendarList.get/update/patch/delete, acl.get/update/patch/delete, events.update, settings.get, events.watch y channels.stop (asumidos por analogia con metodos hermanos); campos exactos de respuesta de colors.get, settings.get y acl; las 37 operaciones de la tabla oficial de metodos si estan verificadas; funciones respond, add_attendees y add_meet_link son usos especificos de events.patch (attendees, conferenceData.createRequest con conferenceDataVersion=1), no endpoints propios
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/google_calendar/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `google_calendar`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `google_calendar` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/calendar/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `google_calendar.account.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con codigo de autorizacion (Google); access token Bearer en cabecera Authorization; base https://www.googleapis.com/calendar/v3; para refresh token pedir access_type=offline y prompt=consent |
| Duración del token (según el catálogo) | no verificado en estas paginas (Google normalmente emite access tokens de 3600 s) |
| Refresco (según el catálogo) | si; POST https://oauth2.googleapis.com/token con grant_type=refresh_token, client_id, client_secret y refresh_token (mecanismo estandar de Google, no verificado en las paginas consultadas) |
| Permisos (según el catálogo) | calendar (todo: ver, editar, compartir, borrar); calendar.readonly (solo leer); calendar.events (crear y editar eventos); calendar.events.readonly (leer eventos); calendar.settings.readonly (leer ajustes); calendar.calendarlist(.readonly) (lista de calendarios); calendar.calendars(.readonly) (metadatos y calendarios secundarios); calendar.acls(.readonly) (permisos de comparticion); calendar.freebusy y calendar.events.freebusy (solo disponibilidad); calendar.events.owned(.readonly) (eventos de calendarios propios); calendar.app.created (calendarios creados por la app) |
| Restricciones de acceso | La pagina de scopes marca como restringidos calendar.freebusy, calendar.events.freebusy, calendar.events.owned(.readonly), calendar.acls(.readonly) (la lista agrupa otros como estandar o de gestion; la clasificacion exacta sensible/restringida no esta clara en la pagina); app en produccion con scopes sensibles necesita verificacion de Google; transfer_ownership exige ser administrador de Google Workspace con privilegio Manage Calendars y solo vale para calendarios secundarios de la organizacion; calendars.clear solo vacia el calendario principal |
| Límites de ritmo | 10000 solicitudes por minuto por proyecto y 600 por minuto por usuario y proyecto (ventana deslizante); umbral diario de 1000000 solicitudes por proyecto antes de cobro futuro; exceso devuelve 403 usageLimits o 429; reintentar con backoff exponencial truncado; events.patch consume 3 unidades de cuota (preferir get mas update) |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/calendar/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> google_calendar`. | Cuenta con `provider: google_calendar`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/google_calendar.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> google_calendar <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Google Calendar. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/google_calendar.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Cuenta (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.account.get` ★ | read | GET /calendars/primary | Devuelve la identidad del usuario conectado (id es su correo) y la zona horaria del calendario principal | (ninguna) | {id, summary, timeZone} | calendar.calendars.readonly | — | — |

### Calendarios (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.calendar.get` | read | GET /calendars/{calendarId} | Obtiene los metadatos de un calendario | calendarId | {id, summary, description, location, timeZone} | calendar.calendars.readonly | — | — |
| [ ] | `google_calendar.calendar.create` | create | POST /calendars | Crea un calendario secundario nuevo | summary, description, location, timeZone | calendario creado {id, summary, timeZone} | calendar.calendars | — | — |
| [ ] | `google_calendar.calendar.update` | update | PATCH /calendars/{calendarId} | Cambia titulo, descripcion, ubicacion o zona horaria de un calendario | calendarId, summary, description, location, timeZone | calendario actualizado | calendar.calendars | — | — |
| [ ] | `google_calendar.calendar.delete` | delete | DELETE /calendars/{calendarId} | Elimina un calendario secundario con todos sus eventos | calendarId | confirmacion vacia | calendar.calendars | I | — |
| [ ] | `google_calendar.calendar.clear` | delete | POST /calendars/{calendarId}/clear | Borra todos los eventos del calendario principal de la cuenta | calendarId | confirmacion vacia | calendar.calendars | I | — |
| [ ] | `google_calendar.calendar.transfer_ownership` | update | POST /calendars/{calendarId}/transferOwnership | Transfiere un calendario secundario de la organizacion a otro usuario (solo admin de Workspace) | calendarId, newDataOwner, useAdminAccess=true | confirmacion vacia | calendar.calendars | E, I | — |

### Lista de calendarios (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.calendar_list.list` | read | GET /users/me/calendarList | Lista los calendarios a los que el usuario esta suscrito | maxResults, minAccessRole, showHidden, showDeleted, pageToken | lista de {id, summary, accessRole, primary, colorId} + siguiente pagina | calendar.calendarlist.readonly | — | — |
| [ ] | `google_calendar.calendar_list.get` | read | GET /users/me/calendarList/{calendarId} | Obtiene una entrada de la lista de calendarios con la configuracion del usuario | calendarId | {id, summary, accessRole, colorId, hidden, selected, defaultReminders} | calendar.calendarlist.readonly | — | — |
| [ ] | `google_calendar.calendar_list.add` | create | POST /users/me/calendarList | Suscribe al usuario a un calendario existente | id, colorId, hidden, summaryOverride | entrada de la lista creada | calendar.calendarlist | — | — |
| [ ] | `google_calendar.calendar_list.update` | update | PATCH /users/me/calendarList/{calendarId} | Cambia color, visibilidad, nombre local o recordatorios de un calendario en la lista | calendarId, colorId, hidden, selected, summaryOverride, defaultReminders | entrada actualizada | calendar.calendarlist | — | — |
| [ ] | `google_calendar.calendar_list.remove` | delete | DELETE /users/me/calendarList/{calendarId} | Quita un calendario de la lista del usuario (no borra el calendario) | calendarId | confirmacion vacia | calendar.calendarlist | — | — |

### Eventos (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.events.list` | read | GET /calendars/{calendarId}/events | Lista o busca eventos de un calendario por rango de fechas o texto | calendarId, timeMin, timeMax, q, singleEvents, orderBy, maxResults, pageToken | lista de {id, summary, start, end, attendees, status} + siguiente pagina | calendar.events.readonly | — | — |
| [ ] | `google_calendar.events.get` | read | GET /calendars/{calendarId}/events/{eventId} | Obtiene un evento por id | calendarId, eventId, timeZone | evento completo {id, summary, start, end, attendees, conferenceData} | calendar.events.readonly | — | — |
| [ ] | `google_calendar.events.create` | create | POST /calendars/{calendarId}/events | Crea un evento, con invitados y videollamada opcionales | calendarId, start, end, summary, description, location, attendees, recurrence, reminders, sendUpdates, conferenceDataVersion | evento creado {id, htmlLink} | calendar.events | E | — |
| [ ] | `google_calendar.events.quick_add` | create | POST /calendars/{calendarId}/events/quickAdd | Crea un evento a partir de una frase en lenguaje natural | calendarId, text, sendUpdates | evento creado {id, summary, start, end} | calendar.events | E | — |
| [ ] | `google_calendar.events.update` | update | PATCH /calendars/{calendarId}/events/{eventId} | Modifica solo los campos indicados de un evento (fecha, titulo, lugar, invitados) | calendarId, eventId, campos a cambiar, sendUpdates | evento actualizado | calendar.events | E | — |
| [ ] | `google_calendar.events.replace` | update | PUT /calendars/{calendarId}/events/{eventId} | Reemplaza un evento completo (leer, modificar y reenviar el recurso entero) | calendarId, eventId, evento completo, sendUpdates | evento actualizado | calendar.events | E | — |
| [ ] | `google_calendar.events.delete` | delete | DELETE /calendars/{calendarId}/events/{eventId} | Elimina un evento y avisa a los invitados si se pide | calendarId, eventId, sendUpdates | confirmacion vacia | calendar.events | E | — |
| [ ] | `google_calendar.events.move` | update | POST /calendars/{calendarId}/events/{eventId}/move | Mueve un evento a otro calendario y cambia su organizador | calendarId, eventId, destination, sendUpdates | evento movido | calendar.events | E | — |
| [ ] | `google_calendar.events.import` | create | POST /calendars/{calendarId}/events/import | Importa una copia privada de un evento existente usando su iCalUID | calendarId, iCalUID, start, end, summary | evento importado {id, iCalUID} | calendar.events | — | — |
| [ ] | `google_calendar.events.list_instances` | read | GET /calendars/{calendarId}/events/{eventId}/instances | Lista las ocurrencias de un evento recurrente | calendarId, eventId, timeMin, timeMax, maxResults, pageToken | lista de instancias {id, start, end, status} + siguiente pagina | calendar.events.readonly | — | — |
| [ ] | `google_calendar.events.respond` | update | PATCH /calendars/{calendarId}/events/{eventId} | Responde a una invitacion (acepto, rechazo, tal vez) cambiando el responseStatus propio en attendees | calendarId, eventId, attendees con responseStatus, sendUpdates | evento actualizado | calendar.events | E | — |
| [ ] | `google_calendar.events.add_attendees` | update | PATCH /calendars/{calendarId}/events/{eventId} | Agrega invitados a un evento existente y los notifica | calendarId, eventId, attendees (lista completa), sendUpdates | evento actualizado | calendar.events | E | — |
| [ ] | `google_calendar.events.add_meet_link` | update | PATCH /calendars/{calendarId}/events/{eventId} | Agrega una videollamada de Google Meet a un evento con conferenceData.createRequest | calendarId, eventId, conferenceData.createRequest, conferenceDataVersion=1 | evento con hangoutLink | calendar.events | — | — |

### Disponibilidad (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.freebusy.query` | read | POST /freeBusy | Consulta los intervalos ocupados de uno o varios calendarios | timeMin, timeMax, items (ids), timeZone, calendarExpansionMax | por calendario lista de {start, end} ocupados | calendar.freebusy | — | — |

### Permisos de comparticion (ACL) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.acl.list` | read | GET /calendars/{calendarId}/acl | Lista quien tiene acceso a un calendario y con que rol | calendarId, maxResults, pageToken | lista de {id, role, scope} + siguiente pagina | calendar.acls.readonly | — | — |
| [ ] | `google_calendar.acl.get` | read | GET /calendars/{calendarId}/acl/{ruleId} | Obtiene una regla de acceso concreta | calendarId, ruleId | {id, role, scope} | calendar.acls.readonly | — | — |
| [ ] | `google_calendar.acl.create` | create | POST /calendars/{calendarId}/acl | Comparte un calendario con un usuario, grupo o dominio | calendarId, role, scope.type, scope.value, sendNotifications | regla creada {id, role, scope} | calendar.acls | E | — |
| [ ] | `google_calendar.acl.update` | update | PATCH /calendars/{calendarId}/acl/{ruleId} | Cambia el rol de una regla de acceso | calendarId, ruleId, role | regla actualizada | calendar.acls | E | — |
| [ ] | `google_calendar.acl.delete` | delete | DELETE /calendars/{calendarId}/acl/{ruleId} | Quita el acceso de un usuario o grupo a un calendario | calendarId, ruleId | confirmacion vacia | calendar.acls | — | — |

### Colores (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.colors.get` | read | GET /colors | Devuelve las paletas de colores validas para calendarios y eventos | (ninguna) | {calendar: {id: color}, event: {id: color}} | calendar.calendarlist.readonly | — | — |

### Ajustes (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.settings.list` | read | GET /users/me/settings | Lista los ajustes del usuario (zona horaria, formato de fecha, inicio de semana) | maxResults, pageToken | lista de {id, value} + siguiente pagina | calendar.settings.readonly | — | — |
| [ ] | `google_calendar.settings.get` | read | GET /users/me/settings/{setting} | Obtiene el valor de un ajuste concreto | setting | {id, value} | calendar.settings.readonly | — | — |

### Avanzado (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_calendar.events.watch` | create | POST /calendars/{calendarId}/events/watch | Crea un canal de notificaciones push (webhook) para cambios en eventos | calendarId, id, type=web_hook, address, token, expiration | canal {id, resourceId, expiration} | calendar.events.readonly | — | — |
| [ ] | `google_calendar.acl.watch` | create | POST /calendars/{calendarId}/acl/watch | Crea un canal de notificaciones push para cambios en permisos de un calendario | calendarId, id, type=web_hook, address | canal {id, resourceId, expiration} | calendar.acls.readonly | — | — |
| [ ] | `google_calendar.calendar_list.watch` | create | POST /users/me/calendarList/watch | Crea un canal de notificaciones push para cambios en la lista de calendarios | id, type=web_hook, address | canal {id, resourceId, expiration} | calendar.calendarlist.readonly | — | — |
| [ ] | `google_calendar.settings.watch` | create | POST /users/me/settings/watch | Crea un canal de notificaciones push para cambios en los ajustes | id, type=web_hook, address | canal {id, resourceId, expiration} | calendar.settings.readonly | — | — |
| [ ] | `google_calendar.channels.stop` | delete | POST /channels/stop | Detiene un canal de notificaciones push | id, resourceId | confirmacion vacia | — | — | — |
