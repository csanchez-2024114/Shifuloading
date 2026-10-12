# Tareas: Gmail

- **Funciones catalogadas:** 76 · **Hechas:** 0 · **Pendientes:** 76 · **Herramientas viejas a migrar:** 13 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.google.com/gmail/api/reference/rest
- **Fuentes que consultó el catálogo:** https://developers.google.com/gmail/api/reference/rest https://developers.google.com/gmail/api/auth/scopes https://developers.google.com/gmail/api/reference/quota https://developers.google.com/gmail/api/reference/rest/v1/users.messages/list https://developers.google.com/gmail/api/reference/rest/v1/users.messages/send https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get https://developers.google.com/gmail/api/reference/rest/v1/users.messages/batchDelete https://developers.google.com/gmail/api/reference/rest/v1/users.threads/list https://developers.google.com/gmail/api/reference/rest/v1/users.history/list https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/create https://developers.google.com/gmail/api/reference/rest/v1/users/watch https://developers.google.com/gmail/api/reference/rest/v1/users.settings/updateVacation https://developers.google.com/gmail/api/reference/rest/v1/users.settings/updateAutoForwarding https://developers.google.com/gmail/api/reference/rest/v1/users.settings.filters/create https://developers.google.com/gmail/api/reference/rest/v1/users.settings.forwardingAddresses/create https://developers.google.com/gmail/api/reference/rest/v1/users.settings.delegates https://developers.google.com/gmail/api/reference/rest/v1/users.settings.delegates/create https://developers.google.com/gmail/api/reference/rest/v1/users.settings.sendAs https://developers.google.com/gmail/api/reference/rest/v1/users.settings.sendAs/create https://developers.google.com/gmail/api/reference/rest/v1/users.settings.sendAs/patch
- **Paginación típica:** Por token: parámetros maxResults (por defecto 100, máx. 500 en messages/threads/history) y pageToken; la respuesta trae nextPageToken y resultSizeEstimate. Las listas de messages/threads devuelven solo ids (hay que llamar a get para el detalle).
- **Qué no se pudo verificar:** Scopes exactos aceptados por: messages.modify/trash/untrash/batchModify, messages.delete, messages.import/insert, threads.get/modify/trash/untrash/delete, drafts.get/list/update/send/delete, labels.* , attachments.get, filters.list/get/delete, settings get/update de language/imap/pop/vacation, sendAs.list/get/verify, smimeInfo.*, getProfile, stop (se infieren del patrón de scopes de las páginas consultadas, no se abrió cada página). Si forwardingAddresses.get/list, autoForwarding.get, delegates.get/list, sendAs.delete/verify y smimeInfo.* tienen también la restricción de cuenta de servicio no se confirmó. Valores de format de messages.get (minimal, full, raw, metadata), límite de tamaño de mensaje (25 MB en envío) y vida del access token/refresh no se leyeron en esta sesión. Se excluyó a propósito la gestión de cifrado del lado del cliente (users.settings.cse.identities y cse.keypairs: create, delete, get, list, patch, enable, disable, obliterate) por ser administrativa y solo de Workspace Enterprise; si se quiere, agregar después. Los ids de las dos filas del grupo de disparadores (gmail.triggers.*) son inventados por este catálogo porque la lista vieja los marca "sin id".
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/gmail/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `gmail`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `gmail` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/gmail/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `gmail.profile.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización (Google); el usuario concede scopes y se obtiene access token + refresh token. En todas las rutas {userId} se usa el literal `me` (cuenta conectada). Base: https://gmail.googleapis.com |
| Duración del token (según el catálogo) | Access token de Google: 3600 s (1 hora) (dato general de Google, no consultado en esta sesión). |
| Refresco (según el catálogo) | Sí, refresh token (grant_type=refresh_token contra https://oauth2.googleapis.com/token); el refresh puede revocarse si el usuario retira el acceso, cambia contraseña con scopes de Gmail, o si la app está en modo Testing (caduca a los 7 días) (dato general de Google, no consultado en esta sesión). |
| Permisos (según el catálogo) | gmail.readonly (leer correos y ajustes); gmail.send (solo enviar); gmail.compose (borradores y enviar); gmail.modify (leer, etiquetar, papelera, borradores, enviar; sin borrado definitivo); mail.google.com (todo, incluye borrado definitivo); gmail.labels (solo etiquetas); gmail.metadata (cabeceras sin cuerpo, sin parámetro q); gmail.insert (insertar/importar); gmail.settings.basic (filtros, vacation, firma/alias, imap, pop, idioma); gmail.settings.sharing (reenvío, delegados, alias nuevos). |
| Restricciones de acceso | Scopes RESTRINGIDOS (readonly, modify, compose, insert, metadata, settings.basic, settings.sharing, mail.google.com) exigen verificación de la app y evaluación de seguridad anual (CASA) de Google para uso en producción; gmail.send y gmail.labels son sensibles/no sensibles (más fáciles). La documentación indica que forwardingAddresses.create, updateAutoForwarding, delegates.create y sendAs.create SOLO están disponibles para clientes de cuenta de servicio con delegación de dominio (Google Workspace); no funcionan con el OAuth normal de usuario. Delegados exigen mismo dominio Workspace. Cuentas Gmail personales funcionan para lo demás. |
| Límites de ritmo | 1,200,000 unidades por minuto por proyecto; 6,000 unidades por minuto por usuario por proyecto; umbral diario 80,000,000 unidades por proyecto. Costo por método: messages.send y drafts.send 100; threads.get 40; messages.get 20; labels.list y profile.get 1. Máximo 500 destinatarios por mensaje. Máximo 1,000 filtros por cuenta. Error de cuota: reintentar con backoff exponencial truncado. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/gmail/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> gmail`. | Cuenta con `provider: gmail`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/gmail.profile.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> gmail <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Gmail. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/gmail.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Perfil (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.profile.get` ★ | read | GET /gmail/v1/users/me/profile | Obtiene el correo de la cuenta conectada y contadores del buzón (sirve para verificar identidad). | (ninguna) | {emailAddress, messagesTotal, threadsTotal, historyId} | gmail.readonly | — | — |

### Mensajes (19)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.messages.list` | read | GET /gmail/v1/users/me/messages | Lista ids de mensajes del buzón, opcionalmente filtrados por etiqueta o consulta. | maxResults, pageToken, labelIds, q, includeSpamTrash | lista de {id, threadId} + nextPageToken + resultSizeEstimate | gmail.readonly | — | listar_correos |
| [ ] | `gmail.messages.search` | read | GET /gmail/v1/users/me/messages | Busca mensajes con la sintaxis de búsqueda de Gmail (from:, subject:, is:unread, has:attachment, fechas...). | q, maxResults, pageToken, includeSpamTrash | lista de {id, threadId} + nextPageToken | gmail.readonly | — | buscar_correo |
| [ ] | `gmail.messages.search_by_sender` | read | GET /gmail/v1/users/me/messages | Busca mensajes de un remitente (arma q=from:<remitente>); misma llamada que search con filtro fijo. | sender, maxResults, pageToken | lista de {id, threadId} + nextPageToken | gmail.readonly | — | buscar_correos_por_remitente |
| [ ] | `gmail.messages.list_by_label` | read | GET /gmail/v1/users/me/messages | Lista mensajes que tienen las etiquetas indicadas (ids de etiqueta). | labelIds, maxResults, pageToken | lista de {id, threadId} + nextPageToken | gmail.readonly | — | listar_correos_por_label |
| [ ] | `gmail.messages.search_by_subject` | read | GET /gmail/v1/users/me/messages | Busca mensajes por asunto (arma q=subject:<texto>); misma llamada que search con filtro fijo. | subject, maxResults, pageToken | lista de {id, threadId} + nextPageToken | gmail.readonly | — | buscar_correo_por_asunto |
| [ ] | `gmail.messages.get` | read | GET /gmail/v1/users/me/messages/{id} | Obtiene un mensaje completo: cabeceras, cuerpo, etiquetas y lista de adjuntos. | id, format, metadataHeaders | {id, threadId, labelIds, snippet, headers, cuerpo, adjuntos[{attachmentId, nombre, tipo}]} | gmail.readonly | — | — |
| [ ] | `gmail.messages.send` | create | POST /gmail/v1/users/me/messages/send | Envía un correo (destinatarios To/Cc/Bcc, asunto, cuerpo, adjuntos opcionales, o responde dentro de un hilo con threadId). | to, subject, body, cc, bcc, attachments, threadId | {id, threadId, labelIds} | gmail.send | E, I | enviar_correo |
| [ ] | `gmail.messages.modify` | update | POST /gmail/v1/users/me/messages/{id}/modify | Agrega o quita etiquetas de un mensaje (base de leer, destacar, archivar, mover). | id, addLabelIds, removeLabelIds | {id, threadId, labelIds} | gmail.modify | — | — |
| [ ] | `gmail.messages.move` | update | POST /gmail/v1/users/me/messages/{id}/modify | Mueve un mensaje a una etiqueta/carpeta (agrega la etiqueta destino y quita la de origen, p. ej. INBOX). | id, addLabelIds, removeLabelIds | {id, threadId, labelIds} | gmail.modify | — | mover_correo_por_asunto |
| [ ] | `gmail.messages.mark_unread` | update | POST /gmail/v1/users/me/messages/{id}/modify | Marca un mensaje como no leído (agrega la etiqueta UNREAD). | id | {id, labelIds} | gmail.modify | — | marcar_como_no_leido |
| [ ] | `gmail.messages.mark_read` | update | POST /gmail/v1/users/me/messages/{id}/modify | Marca un mensaje como leído (quita la etiqueta UNREAD). | id | {id, labelIds} | gmail.modify | — | — |
| [ ] | `gmail.messages.archive` | update | POST /gmail/v1/users/me/messages/{id}/modify | Archiva un mensaje (quita la etiqueta INBOX). | id | {id, labelIds} | gmail.modify | — | — |
| [ ] | `gmail.messages.trash` | update | POST /gmail/v1/users/me/messages/{id}/trash | Envía un mensaje a la papelera (recuperable unos 30 días). | id | {id, labelIds} | gmail.modify | — | — |
| [ ] | `gmail.messages.untrash` | update | POST /gmail/v1/users/me/messages/{id}/untrash | Saca un mensaje de la papelera. | id | {id, labelIds} | gmail.modify | — | — |
| [ ] | `gmail.messages.delete` | delete | DELETE /gmail/v1/users/me/messages/{id} | Borra un mensaje de forma definitiva, sin pasar por la papelera. | id | vacío (éxito) | mail.google.com | I | — |
| [ ] | `gmail.messages.batch_modify` | update | POST /gmail/v1/users/me/messages/batchModify | Agrega o quita etiquetas a muchos mensajes de una vez. | ids, addLabelIds, removeLabelIds | vacío (éxito) | gmail.modify | — | — |
| [ ] | `gmail.messages.batch_delete` | delete | POST /gmail/v1/users/me/messages/batchDelete | Borra definitivamente muchos mensajes por id; no garantiza que existieran. | ids | vacío (éxito) | mail.google.com | I | — |
| [ ] | `gmail.messages.import` | create | POST /gmail/v1/users/me/messages/import | Importa un mensaje al buzón con la fecha y etiquetas dadas (como una migración, pasa filtros de spam). | raw, labelIds, internalDateSource, neverMarkSpam | {id, threadId, labelIds} | gmail.insert | — | — |
| [ ] | `gmail.messages.insert` | create | POST /gmail/v1/users/me/messages | Inserta un mensaje directamente en el buzón sin enviarlo (no pasa por el envío SMTP). | raw, labelIds, internalDateSource | {id, threadId, labelIds} | gmail.insert | — | — |

### Adjuntos (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.attachments.get` | read | GET /gmail/v1/users/me/messages/{messageId}/attachments/{id} | Descarga el contenido de un adjunto de un mensaje. | messageId, id (attachmentId) | {size, data en base64url} | gmail.readonly | — | — |

### Hilos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.threads.list` | read | GET /gmail/v1/users/me/threads | Lista hilos de conversación, con filtro por etiqueta o consulta. | maxResults, pageToken, labelIds, q, includeSpamTrash | lista de {id, snippet, historyId} + nextPageToken | gmail.readonly | — | — |
| [ ] | `gmail.threads.get` | read | GET /gmail/v1/users/me/threads/{id} | Obtiene un hilo con todos sus mensajes. | id, format, metadataHeaders | {id, historyId, messages[]} | gmail.readonly | — | — |
| [ ] | `gmail.threads.modify` | update | POST /gmail/v1/users/me/threads/{id}/modify | Agrega o quita etiquetas a todos los mensajes de un hilo. | id, addLabelIds, removeLabelIds | {id, messages[]} | gmail.modify | — | — |
| [ ] | `gmail.threads.trash` | update | POST /gmail/v1/users/me/threads/{id}/trash | Envía un hilo completo a la papelera. | id | {id, messages[]} | gmail.modify | — | — |
| [ ] | `gmail.threads.untrash` | update | POST /gmail/v1/users/me/threads/{id}/untrash | Saca un hilo completo de la papelera. | id | {id, messages[]} | gmail.modify | — | — |
| [ ] | `gmail.threads.delete` | delete | DELETE /gmail/v1/users/me/threads/{id} | Borra un hilo completo de forma definitiva. | id | vacío (éxito) | mail.google.com | I | — |

### Borradores (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.drafts.list` | read | GET /gmail/v1/users/me/drafts | Lista los borradores del buzón. | maxResults, pageToken, q, includeSpamTrash | lista de {id, message{id, threadId}} + nextPageToken | gmail.readonly | — | — |
| [ ] | `gmail.drafts.get` | read | GET /gmail/v1/users/me/drafts/{id} | Obtiene un borrador con su mensaje. | id, format | {id, message} | gmail.readonly | — | — |
| [ ] | `gmail.drafts.create` | create | POST /gmail/v1/users/me/drafts | Crea un borrador (destinatarios, asunto, cuerpo, adjuntos opcionales) con la etiqueta DRAFT. | to, subject, body, cc, bcc, attachments, threadId | {id, message{id, threadId}} | gmail.compose | — | crear_borrador |
| [ ] | `gmail.drafts.update` | update | PUT /gmail/v1/users/me/drafts/{id} | Reemplaza el contenido de un borrador existente. | id, to, subject, body, cc, bcc, attachments | {id, message} | gmail.compose | — | — |
| [ ] | `gmail.drafts.send` | create | POST /gmail/v1/users/me/drafts/send | Envía un borrador existente por su id (el borrador desaparece al enviarse). La búsqueda del borrador por asunto se hace con drafts.list. | id | {id, threadId, labelIds} del mensaje enviado | gmail.compose | E, I | enviar_borrador_por_asunto |
| [ ] | `gmail.drafts.delete` | delete | DELETE /gmail/v1/users/me/drafts/{id} | Borra un borrador de forma definitiva. | id | vacío (éxito) | gmail.compose | I | — |

### Etiquetas (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.labels.list` | read | GET /gmail/v1/users/me/labels | Lista todas las etiquetas (del sistema y del usuario). | (ninguna) | lista de {id, name, type} | gmail.labels | — | — |
| [ ] | `gmail.labels.get` | read | GET /gmail/v1/users/me/labels/{id} | Obtiene una etiqueta con sus contadores de mensajes e hilos. | id | {id, name, type, messagesTotal, messagesUnread, threadsTotal, threadsUnread, color} | gmail.labels | — | — |
| [ ] | `gmail.labels.create` | create | POST /gmail/v1/users/me/labels | Crea una etiqueta nueva. | name, labelListVisibility, messageListVisibility, color | {id, name, type} | gmail.labels | — | crear_etiqueta |
| [ ] | `gmail.labels.update` | update | PATCH /gmail/v1/users/me/labels/{id} | Cambia nombre, visibilidad o color de una etiqueta (PATCH parcial; existe también PUT). | id, name, labelListVisibility, messageListVisibility, color | {id, name, type} | gmail.labels | — | — |
| [ ] | `gmail.labels.delete` | delete | DELETE /gmail/v1/users/me/labels/{id} | Borra una etiqueta del usuario y la quita de todos los mensajes que la tenían. | id | vacío (éxito) | gmail.labels | I | — |

### Filtros (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.filters.list` | read | GET /gmail/v1/users/me/settings/filters | Lista los filtros automáticos de la cuenta. | (ninguna) | lista de {id, criteria, action} | gmail.settings.basic | — | — |
| [ ] | `gmail.filters.get` | read | GET /gmail/v1/users/me/settings/filters/{id} | Obtiene un filtro por id. | id | {id, criteria, action} | gmail.settings.basic | — | — |
| [ ] | `gmail.filters.create` | create | POST /gmail/v1/users/me/settings/filters | Crea un filtro (criterios como from, to, subject, query y acciones como etiquetar, archivar, reenviar a dirección verificada). Máx. 1,000 por cuenta. | criteria, action | {id, criteria, action} | gmail.settings.basic | — | — |
| [ ] | `gmail.filters.delete` | delete | DELETE /gmail/v1/users/me/settings/filters/{id} | Borra un filtro. | id | vacío (éxito) | gmail.settings.basic | — | — |

### Configuración (firma, respuesta automática, alias) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.vacation.get` | read | GET /gmail/v1/users/me/settings/vacation | Lee la respuesta automática (vacation responder). | (ninguna) | {enableAutoReply, responseSubject, responseBodyHtml, startTime, endTime, restrictToContacts, restrictToDomain} | gmail.settings.basic | — | — |
| [ ] | `gmail.vacation.update` | update | PUT /gmail/v1/users/me/settings/vacation | Activa, desactiva o cambia la respuesta automática; Gmail responderá a quienes escriban (acción visible a terceros). | enableAutoReply, responseSubject, responseBodyHtml, startTime, endTime, restrictToContacts, restrictToDomain | VacationSettings actualizado | gmail.settings.basic | E | — |
| [ ] | `gmail.language.get` | read | GET /gmail/v1/users/me/settings/language | Lee el idioma de la interfaz de Gmail. | (ninguna) | {displayLanguage} | gmail.settings.basic | — | — |
| [ ] | `gmail.language.update` | update | PUT /gmail/v1/users/me/settings/language | Cambia el idioma de la interfaz de Gmail. | displayLanguage | {displayLanguage} | gmail.settings.basic | — | — |
| [ ] | `gmail.imap.get` | read | GET /gmail/v1/users/me/settings/imap | Lee la configuración de acceso IMAP. | (ninguna) | {enabled, autoExpunge, expungeBehavior, maxFolderSize} | gmail.settings.basic | — | — |
| [ ] | `gmail.imap.update` | update | PUT /gmail/v1/users/me/settings/imap | Cambia la configuración de acceso IMAP. | enabled, autoExpunge, expungeBehavior, maxFolderSize | ImapSettings actualizado | gmail.settings.basic | — | — |
| [ ] | `gmail.pop.get` | read | GET /gmail/v1/users/me/settings/pop | Lee la configuración de acceso POP. | (ninguna) | {accessWindow, disposition} | gmail.settings.basic | — | — |
| [ ] | `gmail.pop.update` | update | PUT /gmail/v1/users/me/settings/pop | Cambia la configuración de acceso POP. | accessWindow, disposition | PopSettings actualizado | gmail.settings.basic | — | — |
| [ ] | `gmail.send_as.list` | read | GET /gmail/v1/users/me/settings/sendAs | Lista las direcciones "enviar como" (alias) con su firma y estado de verificación. | (ninguna) | lista de {sendAsEmail, displayName, signature, isDefault, isPrimary, verificationStatus} | gmail.settings.basic | — | — |
| [ ] | `gmail.send_as.get` | read | GET /gmail/v1/users/me/settings/sendAs/{sendAsEmail} | Obtiene un alias, incluida su firma HTML (así se lee la firma). | sendAsEmail | {sendAsEmail, displayName, replyToAddress, signature, isDefault, treatAsAlias, verificationStatus} | gmail.settings.basic | — | — |
| [ ] | `gmail.send_as.update` | update | PATCH /gmail/v1/users/me/settings/sendAs/{sendAsEmail} | Cambia nombre visible, reply-to, firma HTML o alias por defecto (así se cambia la firma; PATCH parcial, existe también PUT). | sendAsEmail, signature, displayName, replyToAddress, isDefault | SendAs actualizado | gmail.settings.basic | — | — |
| [ ] | `gmail.send_as.verify` | create | POST /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/verify | Reenvía el correo de verificación a un alias pendiente (le llega un correo a esa dirección). | sendAsEmail | vacío (éxito) | gmail.settings.basic | E | — |

### Historial y notificaciones (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.history.list` | read | GET /gmail/v1/users/me/history | Lista los cambios del buzón desde un historyId (mensajes añadidos, borrados, etiquetas añadidas o quitadas). El historyId vale al menos una semana; si caduca devuelve 404. | startHistoryId, maxResults, pageToken, labelId, historyTypes | {history[], nextPageToken, historyId} | gmail.readonly | — | — |

### Avanzado (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.mailbox.watch` | create | POST /gmail/v1/users/me/watch | Activa notificaciones push del buzón hacia un tema Pub/Sub de Google Cloud (requiere el tema ya creado y renovar antes de expirar). | topicName, labelIds, labelFilterBehavior | {historyId, expiration} | gmail.readonly | — | — |
| [ ] | `gmail.mailbox.stop_watch` | delete | POST /gmail/v1/users/me/stop | Detiene las notificaciones push del buzón. | (ninguna) | vacío (éxito) | gmail.readonly | — | — |

### Avanzado: solo cuenta de servicio con delegación de dominio (Workspace); no funcionan con OAuth normal de usuario (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.forwarding_addresses.list` | read | GET /gmail/v1/users/me/settings/forwardingAddresses | Lista las direcciones de reenvío registradas. | (ninguna) | lista de {forwardingEmail, verificationStatus} | gmail.settings.sharing | — | — |
| [ ] | `gmail.forwarding_addresses.get` | read | GET /gmail/v1/users/me/settings/forwardingAddresses/{forwardingEmail} | Obtiene una dirección de reenvío y su estado de verificación. | forwardingEmail | {forwardingEmail, verificationStatus} | gmail.settings.sharing | — | — |
| [ ] | `gmail.forwarding_addresses.create` | create | POST /gmail/v1/users/me/settings/forwardingAddresses | Registra una dirección de reenvío; puede enviar un correo de verificación a esa dirección. | forwardingEmail | {forwardingEmail, verificationStatus} | gmail.settings.sharing | E | — |
| [ ] | `gmail.forwarding_addresses.delete` | delete | DELETE /gmail/v1/users/me/settings/forwardingAddresses/{forwardingEmail} | Elimina una dirección de reenvío. | forwardingEmail | vacío (éxito) | gmail.settings.sharing | — | — |
| [ ] | `gmail.auto_forwarding.get` | read | GET /gmail/v1/users/me/settings/autoForwarding | Lee el reenvío automático de la cuenta. | (ninguna) | {enabled, emailAddress, disposition} | gmail.settings.sharing | — | — |
| [ ] | `gmail.auto_forwarding.update` | update | PUT /gmail/v1/users/me/settings/autoForwarding | Activa o cambia el reenvío automático de todo el correo entrante a una dirección verificada (envía copias a terceros). | enabled, emailAddress, disposition | AutoForwarding actualizado | gmail.settings.sharing | E | — |
| [ ] | `gmail.delegates.list` | read | GET /gmail/v1/users/me/settings/delegates | Lista los delegados con acceso al buzón. | (ninguna) | lista de {delegateEmail, verificationStatus} | gmail.settings.sharing | — | — |
| [ ] | `gmail.delegates.get` | read | GET /gmail/v1/users/me/settings/delegates/{delegateEmail} | Obtiene un delegado y su estado. | delegateEmail | {delegateEmail, verificationStatus} | gmail.settings.sharing | — | — |
| [ ] | `gmail.delegates.create` | create | POST /gmail/v1/users/me/settings/delegates | Da a otro usuario del mismo dominio Workspace acceso para leer, enviar y borrar correo de la cuenta. | delegateEmail | {delegateEmail, verificationStatus} | gmail.settings.sharing | E | — |
| [ ] | `gmail.delegates.delete` | delete | DELETE /gmail/v1/users/me/settings/delegates/{delegateEmail} | Quita un delegado y revoca su acceso. | delegateEmail | vacío (éxito) | gmail.settings.sharing | — | — |
| [ ] | `gmail.send_as.create` | create | POST /gmail/v1/users/me/settings/sendAs | Crea un alias "enviar como" personalizado, con SMTP opcional; puede enviar correo de verificación. | sendAsEmail, displayName, replyToAddress, signature, smtpMsa, treatAsAlias | SendAs creado | gmail.settings.sharing | E | — |
| [ ] | `gmail.send_as.delete` | delete | DELETE /gmail/v1/users/me/settings/sendAs/{sendAsEmail} | Elimina un alias "enviar como" personalizado. | sendAsEmail | vacío (éxito) | gmail.settings.sharing | I | — |
| [ ] | `gmail.smime_info.list` | read | GET /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/smimeInfo | Lista los certificados S/MIME de un alias. | sendAsEmail | lista de {id, issuerCn, isDefault, expiration} | gmail.settings.basic | — | — |
| [ ] | `gmail.smime_info.get` | read | GET /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/smimeInfo/{id} | Obtiene un certificado S/MIME de un alias. | sendAsEmail, id | {id, issuerCn, isDefault, expiration, pem} | gmail.settings.basic | — | — |
| [ ] | `gmail.smime_info.insert` | create | POST /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/smimeInfo | Sube un certificado S/MIME (PKCS12) para un alias. | sendAsEmail, pkcs12, encryptedKeyPassword | SmimeInfo creado | gmail.settings.basic | — | — |
| [ ] | `gmail.smime_info.delete` | delete | DELETE /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/smimeInfo/{id} | Elimina un certificado S/MIME de un alias. | sendAsEmail, id | vacío (éxito) | gmail.settings.basic | I | — |
| [ ] | `gmail.smime_info.set_default` | update | POST /gmail/v1/users/me/settings/sendAs/{sendAsEmail}/smimeInfo/{id}/setDefault | Marca un certificado S/MIME como el predeterminado del alias. | sendAsEmail, id | vacío (éxito) | gmail.settings.basic | — | — |

### Disparadores de workflow (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `gmail.triggers.activate` | update | — | No es una operación de Gmail: activa un disparador de workflow que reacciona a correos nuevos (herramienta interna; id propuesto por este catálogo). | (según la herramienta vieja) | estado del disparador | gmail.readonly | — | gmail_reactivo |
| [ ] | `gmail.triggers.deactivate` | update | — | No es una operación de Gmail: desactiva el disparador de workflow de correos nuevos (herramienta interna; id propuesto por este catálogo). | (según la herramienta vieja) | estado del disparador | — | — | gmail_desactivar |

## Observaciones de las herramientas viejas

- `buscar_correo`, `buscar_correos_por_remitente`, `buscar_correo_por_asunto` y `listar_correos_por_label` son la misma operacion con filtros distintos. Proponer **una** funcion de busqueda con filtros opcionales es decision del lider: se deja una fila por herramienta vieja hasta que se decida.
- `enviar_correo` y `enviar_borrador_por_asunto` salen al exterior y no se pueden deshacer: `exits_outside=True`, `reversible=False`.
- `gmail_reactivo` y `gmail_desactivar` no son llamadas a la API de Gmail: activan/desactivan un disparador de workflow. No son funciones de app; se deciden junto con las internas (`internas.md`).
- Varias herramientas viejas trabajan `por_asunto`: la funcion nueva debe recibir ids y la busqueda por asunto es otra funcion (o la misma de busqueda).
