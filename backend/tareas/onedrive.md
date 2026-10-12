# Tareas: OneDrive

- **Funciones catalogadas:** 54 · **Hechas:** 0 · **Pendientes:** 54 · App sin herramientas viejas
- **Documentación oficial:** https://learn.microsoft.com/en-us/graph/api/resources/onedrive
- **Fuentes que consultó el catálogo:** https://learn.microsoft.com/en-us/graph/api/resources/drive https://learn.microsoft.com/en-us/graph/api/resources/driveitem https://learn.microsoft.com/en-us/graph/api/driveitem-invite https://learn.microsoft.com/en-us/graph/auth/auth-concepts https://learn.microsoft.com/en-us/graph/auth-v2-user https://learn.microsoft.com/en-us/graph/throttling
- **Paginación típica:** OData: @odata.nextLink en respuesta; seguir enlace para próxima página
- **Qué no se pudo verificar:** Permisos exactos por operación (algunos pueden variar entre personal y business); disponibilidad en regiones nacionales; detalles de límites específicos por endpoint
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/onedrive/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `onedrive`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `onedrive` |
| Variables del `.env` que necesitas | ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET, ONEDRIVE_REDIRECT_URI, SECRET_KEY, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/onedrive/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `onedrive.drive.get` |
| Cómo se autentica (según el catálogo) | OAuth 2 con código de autorización; cliente confidencial (app secret) requerido |
| Duración del token (según el catálogo) | 3599 segundos (aproximadamente 1 hora, expires_in: 3599) |
| Refresco (según el catálogo) | Sí, refresh_token se devuelve en respuesta si se solicita scope offline_access; se renueva con POST /{tenant}/oauth2/v2.0/token con grant_type=refresh_token |
| Permisos (según el catálogo) | Files.Read (lectura); Files.ReadWrite (lectura y escritura); Files.ReadWrite.All (toda la organización); Sites.ReadWrite.All (sitios SharePoint) |
| Restricciones de acceso | Requiere que usuario tenga licencia OneDrive; aplicación debe registrarse en Entra ID; permisos sensibles pueden requerir consentimiento admin |
| Límites de ritmo | Throttling con HTTP 429 si se exceden umbrales; Retry-After header indica espera; límites varían por volumen de operaciones (escrituras más restrictivas que lecturas) |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/onedrive/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> onedrive`. | Cuenta con `provider: onedrive`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/onedrive.drive.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> onedrive <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de OneDrive. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/onedrive.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Autenticación y Cuenta (Whoami) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.drive.get` ★ | read | GET /me/drive | Obtiene la unidad OneDrive del usuario autenticado | (ninguna) | {id, driveType, owner{user{id, displayName}}, quota{total, used, remaining}, webUrl} | Files.Read | — | — |

### Unidades (Drives) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.drive.list` | read | GET /me/drives | Lista todas las unidades disponibles para el usuario | (ninguna) | lista de {id, name, driveType, owner, webUrl} + siguiente página | Files.Read | — | — |
| [ ] | `onedrive.drive.list_users` | read | GET /users/{userId}/drive | Obtiene la unidad de otro usuario por su ID | userId | {id, driveType, owner, webUrl} | Files.Read.All | — | — |
| [ ] | `onedrive.drive.list_groups` | read | GET /groups/{groupId}/drive | Obtiene la unidad/biblioteca de documento de un grupo | groupId | {id, name, driveType, webUrl} | Sites.Read.All | — | — |
| [ ] | `onedrive.drive.list_sites` | read | GET /sites/{siteId}/drive | Obtiene la unidad de un sitio SharePoint | siteId | {id, name, driveType, webUrl} | Sites.Read.All | — | — |
| [ ] | `onedrive.drive.get_special_folder` | read | GET /me/drive/special/{specialId} | Accede a carpetas especiales por nombre (Documents, Photos, Music, etc.) | specialId | {id, name, folder, webUrl} | Files.Read | — | — |

### Elementos (Archivos y Carpetas) (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.get` | read | GET /me/drive/items/{itemId} | Obtiene metadatos de un archivo o carpeta | itemId | {id, name, size, createdDateTime, lastModifiedDateTime, file/folder, webUrl} | Files.Read | — | — |
| [ ] | `onedrive.item.get_by_path` | read | GET /me/drive/root:/{path} | Obtiene un archivo o carpeta por su ruta relativa | path | {id, name, size, createdDateTime, webUrl} | Files.Read | — | — |
| [ ] | `onedrive.item.list_children` | read | GET /me/drive/items/{itemId}/children | Lista los archivos y carpetas dentro de una carpeta | itemId | lista de items {id, name, size, createdDateTime} + siguiente página | Files.Read | — | — |
| [ ] | `onedrive.item.list_root_children` | read | GET /me/drive/root/children | Lista archivos y carpetas en la raíz de OneDrive | (ninguna) | lista de items + siguiente página | Files.Read | — | — |
| [ ] | `onedrive.item.create_folder` | create | POST /me/drive/items/{parentId}/children | Crea una nueva carpeta | parentId, name, @microsoft.graph.conflictBehavior | {id, name, folder, webUrl} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.upload` | create | PUT /me/drive/items/{parentId}:/{filename}:/content | Sube un archivo pequeño (< 4MB) | parentId, filename, contenido binario | {id, name, size, file, webUrl} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.upload_session` | create | POST /me/drive/items/{parentId}:/{filename}:/createUploadSession | Crea sesión de carga para archivos grandes (> 4MB) | parentId, filename | {uploadUrl, expirationDateTime} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.download` | read | GET /me/drive/items/{itemId}/content | Descarga el contenido de un archivo | itemId | contenido binario del archivo | Files.Read | — | — |
| [ ] | `onedrive.item.download_format` | read | GET /me/drive/items/{itemId}/content?format={format} | Descarga archivo en formato específico (PDF, etc.) | itemId, format | contenido en formato solicitado | Files.Read | — | — |
| [ ] | `onedrive.item.update` | update | PATCH /me/drive/items/{itemId} | Actualiza propiedades de un archivo o carpeta | itemId, name, description | {id, name, lastModifiedDateTime} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.move` | update | PATCH /me/drive/items/{itemId} | Mueve archivo/carpeta a otra carpeta | itemId, parentReference{id} | {id, parentReference, webUrl} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.copy` | create | POST /me/drive/items/{itemId}/copy | Crea una copia del archivo/carpeta | itemId, name, parentReference{id} | {id, name} + monitor largo plazo | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.search` | read | GET /me/drive/root/microsoft.graph.searchContainer/search | Busca archivos por nombre o contenido | q | lista de items coincidentes {id, name, webUrl} + página | Files.Read | — | — |
| [ ] | `onedrive.item.delete` | delete | DELETE /me/drive/items/{itemId} | Elimina un archivo o carpeta (va a papelera) | itemId | (sin contenido) | Files.ReadWrite | I | — |
| [ ] | `onedrive.item.delete_permanent` | delete | DELETE /me/drive/items/{itemId}?@microsoft.graph.permanent=true | Elimina permanentemente sin pasar por papelera | itemId, @microsoft.graph.permanent=true | (sin contenido) | Files.ReadWrite | I | — |
| [ ] | `onedrive.item.restore` | update | PATCH /me/drive/items/{itemId} | Restaura un archivo de la papelera | itemId, deleted{state: null} | {id, name, webUrl} | Files.ReadWrite | — | — |

### Versiones (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.version.list` | read | GET /me/drive/items/{itemId}/versions | Lista todas las versiones anteriores de un archivo | itemId | lista de {id, lastModifiedDateTime, lastModifiedBy, size} + página | Files.Read | — | — |
| [ ] | `onedrive.version.get` | read | GET /me/drive/items/{itemId}/versions/{versionId} | Obtiene metadatos de una versión específica | itemId, versionId | {id, lastModifiedDateTime, size, file} | Files.Read | — | — |
| [ ] | `onedrive.version.download` | read | GET /me/drive/items/{itemId}/versions/{versionId}/content | Descarga el contenido de una versión anterior | itemId, versionId | contenido binario de esa versión | Files.Read | — | — |

### Control de Versiones (Check-in/Check-out) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.version.checkout` | update | POST /me/drive/items/{itemId}/checkout | Bloquea archivo para edición exclusiva (solo disponible) | itemId | (sin contenido) | Files.ReadWrite | — | — |
| [ ] | `onedrive.version.checkin` | update | POST /me/drive/items/{itemId}/checkin | Comprueba cambios; hace versión visible a otros | itemId, comment, checkInAs | {id, name, webUrl} | Files.ReadWrite | — | — |
| [ ] | `onedrive.version.discard_checkout` | update | POST /me/drive/items/{itemId}/discardCheckout | Descarta cambios pendientes de un checkout | itemId | (sin contenido) | Files.ReadWrite | — | — |

### Cambios e Historial (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.delta` | read | GET /me/drive/root/delta | Obtiene cambios en la unidad desde última sincronización (delta sync) | token | lista de items {id, name, deleted} + deltaLink | Files.Read | — | — |
| [ ] | `onedrive.item.recent` | read | GET /me/drive/recent | Obtiene elementos usados recientemente por el usuario | (ninguna) | lista de {id, name, webUrl} + página | Files.Read | — | — |
| [ ] | `onedrive.item.shared_with_me` | read | GET /me/drive/sharedWithMe | Obtiene elementos compartidos con el usuario | (ninguna) | lista de {id, name, shared{sharedBy}} + página | Files.Read | — | — |
| [ ] | `onedrive.item.get_activities` | read | GET /me/drive/items/{itemId}/activities | Lista actividades recientes en un elemento | itemId | lista de {type, action, actor} + página | Files.Read | — | — |
| [ ] | `onedrive.item.get_analytics` | read | GET /me/drive/items/{itemId}/analytics | Obtiene estadísticas de visualización del elemento | itemId | {lastSevenDays{views, modifiedBy}, lastThirtyDays{views}} | Files.Read | — | — |

### Vista Previa (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.preview` | read | POST /me/drive/items/{itemId}/preview | Obtiene URL embebible para vista previa temporal | itemId, viewer, allowEdit | {getUrl, postParameters} | Files.Read | — | — |

### Miniaturas (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.list_thumbnails` | read | GET /me/drive/items/{itemId}/thumbnails | Lista miniaturas disponibles del elemento | itemId | lista de {id, small{url}, medium{url}, large{url}} | Files.Read | — | — |

### Seguimiento (Follow/Unfollow) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.follow` | update | POST /me/drive/items/{itemId}/follow | Marca un elemento como seguido | itemId | {id, name} | Files.ReadWrite | — | — |
| [ ] | `onedrive.item.unfollow` | update | POST /me/drive/items/{itemId}/unfollow | Deja de seguir un elemento | itemId | (sin contenido) | Files.ReadWrite | — | — |
| [ ] | `onedrive.drive.list_following` | read | GET /me/drive/following | Lista elementos que el usuario está siguiendo | (ninguna) | lista de {id, name, webUrl} + página | Files.Read | — | — |

### Permisos y Compartición (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.permission.list` | read | GET /me/drive/items/{itemId}/permissions | Lista todos los permisos de un elemento | itemId | lista de {id, roles, grantedTo, link} | Files.Read | — | — |
| [ ] | `onedrive.permission.create` | create | POST /me/drive/items/{itemId}/permissions | Crea un nuevo permiso directo | itemId, roles{read/write}, grantedTo{user{email}} | {id, roles, grantedTo} | Files.ReadWrite | — | — |
| [ ] | `onedrive.permission.delete` | delete | DELETE /me/drive/items/{itemId}/permissions/{permissionId} | Elimina un permiso | itemId, permissionId | (sin contenido) | Files.ReadWrite | — | — |
| [ ] | `onedrive.permission.update` | update | PATCH /me/drive/items/{itemId}/permissions/{permissionId} | Actualiza roles de un permiso | itemId, permissionId, roles{read/write} | {id, roles} | Files.ReadWrite | — | — |

### Enlaces de Compartición (Share Links) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.link.create` | create | POST /me/drive/items/{itemId}/createLink | Crea un enlace de compartición (anónimo o específico) | itemId, type{view/edit/embed}, password, expirationDateTime | {id, link{webUrl, type}, hasPassword} | Files.ReadWrite | E | — |
| [ ] | `onedrive.link.invite` | create | POST /me/drive/items/{itemId}/invite | Envía invitación a compartición por correo | itemId, recipients{email}, roles{read/write}, sendInvitation, message | lista de {id, invitation{email}, grantedTo} | Files.ReadWrite | E, I | — |

### Etiquetas de Sensibilidad (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.label.extract` | read | POST /me/drive/items/{itemId}/extractSensitivityLabels | Extrae etiquetas de sensibilidad asignadas | itemId | {labels[{id, name, color}], contentBits} | Files.Read | — | — |
| [ ] | `onedrive.label.assign` | update | POST /me/drive/items/{itemId}/assignSensitivityLabel | Asigna una etiqueta de sensibilidad | itemId, labelId | {sensitivityLabel{id, name}} | Files.ReadWrite | — | — |

### Etiquetas de Retención (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.retention.get` | read | GET /me/drive/items/{itemId}/retentionLabel | Obtiene etiqueta de retención aplicada | itemId | {id, name, isLocked, retentionSettings} | Files.Read | — | — |
| [ ] | `onedrive.retention.set` | update | POST /me/drive/items/{itemId}/setRetentionLabel | Aplica etiqueta de retención a archivo/carpeta | itemId, labelId | {id, name, isLocked} | Files.ReadWrite | — | — |
| [ ] | `onedrive.retention.remove` | update | POST /me/drive/items/{itemId}/removeRetentionLabel | Elimina etiqueta de retención | itemId | (sin contenido) | Files.ReadWrite | — | — |
| [ ] | `onedrive.retention.lock_unlock` | update | POST /me/drive/items/{itemId}/lockOrUnlockRecord | Bloquea o desbloquea registro con etiqueta retención | itemId, shouldLock{true/false} | {id, name, retentionLabel} | Files.ReadWrite | — | — |

### Información de Cuota (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.quota.get` | read | GET /me/drive?$select=quota | Obtiene información de cuota de almacenamiento | (ninguna) | {quota{total, used, remaining, state}} | Files.Read | — | — |

### Enlaces WebDAV y URLs Web (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.get_webdav_url` | read | GET /me/drive/items/{itemId}?$select=webDavUrl | Obtiene URL WebDAV para acceso directo | itemId | {webDavUrl} | Files.Read | — | — |
| [ ] | `onedrive.item.get_web_url` | read | GET /me/drive/items/{itemId}?$select=webUrl | Obtiene URL web del elemento en navegador | itemId | {webUrl} | Files.Read | — | — |

### Conexiones Avanzadas (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `onedrive.item.get_websocket` | read | GET /me/drive/root/subscriptions/socketIo | Obtiene canal WebSocket para notificaciones cerca real-tiempo | (ninguna) | {subscriptionId} | Files.Read | — | — |
