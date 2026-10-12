# Tareas: Google Drive

- **Funciones catalogadas:** 79 · **Hechas:** 0 · **Pendientes:** 79 · **Herramientas viejas a migrar:** 9 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.google.com/drive/api/reference/rest/v3
- **Fuentes que consultó el catálogo:** https://developers.google.com/drive/api/reference/rest/v3 https://developers.google.com/drive/api/guides/about-auth https://developers.google.com/drive/api/guides/limits https://developers.google.com/drive/api/reference/rest/v3/files/list https://developers.google.com/workspace/docs/api/how-tos/batch
- **Paginación típica:** pageToken/nextPageToken con pageSize (max 1000); nextPageToken ausente al final
- **Qué no se pudo verificar:** Detalle de Approvals y Access Proposals (endpoints confirmados, poca documentacion); operaciones asincronas; scopes por operacion no revisados uno a uno.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/google_drive/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `google_drive`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `google_drive` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/drive/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `google_drive.account.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con authorization code, acceso tokens cortos (1 hora aprox.) y refresh tokens de larga vida (validos indefinidamente si se usan regularmente) |
| Duración del token (según el catálogo) | ~1 hora (access token); refresh token no caduca si se usa regularmente |
| Refresco (según el catálogo) | Si, usar refresh token para obtener nuevos access tokens indefinidamente sin volver a pedir consentimiento |
| Permisos (según el catálogo) | drive (acceso completo), drive.readonly (lectura), drive.file (crear/modificar solo lo compartido con la app), drive.appdata (config de app), drive.apps.readonly (ver apps), drive.metadata (metadata y actividad) |
| Restricciones de acceso | Requiere aplicacion registrada en Google Cloud Console; scopes sensibles/restringidos pueden necesitar verificacion adicional; limites por usuario y proyecto |
| Límites de ritmo | 1M quota units/min por proyecto, 325K/min por usuario/proyecto, 1TB data egress/dia; lectura=5 units, listado=100, descarga=200, edicion=50; operaciones batch limitas a 100 requests/batch |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/drive/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> google_drive`. | Cuenta con `provider: google_drive`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/google_drive.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> google_drive <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Google Drive. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/google_drive.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Cuenta y sistema (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.account.get` ★ | read | GET /drive/v3/about | Obtener info de cuenta, usuario y cuota de almacenamiento | — | {user, storageQuota, appInstalled, importFormats, exportFormats} | — | — | — |
| [ ] | `google_drive.export_formats.list` | read | GET /drive/v3/about | Listar formatos de exportacion disponibles | — | {exportFormats} | drive.readonly | — | — |
| [ ] | `google_drive.import_formats.list` | read | GET /drive/v3/about | Listar formatos de importacion disponibles | — | {importFormats} | — | — | — |

### Archivos y carpetas (14)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.files.list` | read | GET /drive/v3/files | Listar archivos y carpetas del usuario | q, pageSize, pageToken, orderBy, spaces | {files[], nextPageToken, incompleteSearch} | drive.readonly | — | list_drive_files |
| [ ] | `google_drive.files.search` | read | GET /drive/v3/files | Buscar archivos por nombre, tipo o propiedades | q, pageSize, pageToken | {files[], nextPageToken} | drive.readonly | — | find_drive_file |
| [ ] | `google_drive.files.get` | read | GET /drive/v3/files/{fileId} | Obtener metadata de un archivo | fileId, fields | {id, name, mimeType, parents, webViewLink, createdTime, modifiedTime, size, owners, permissions} | drive.readonly | — | — |
| [ ] | `google_drive.files.create` | create | POST /drive/v3/files | Crear un archivo o carpeta | name, mimeType, parents, description | {id, name, mimeType, parents, webViewLink} | drive | — | — |
| [ ] | `google_drive.files.update` | update | PATCH /drive/v3/files/{fileId} | Actualizar metadata de archivo (nombre, descripcion, padres) | fileId, name, description, parents, properties | {id, name, description, modifiedTime} | drive | — | — |
| [ ] | `google_drive.files.upload` | create | POST /upload/drive/v3/files | Crear archivo subiendo contenido | name, mimeType, parents | {id, name, mimeType, size} | drive | — | — |
| [ ] | `google_drive.files.upload_update` | update | PATCH /upload/drive/v3/files/{fileId} | Actualizar contenido de archivo existente | fileId, mimeType | {id, name, modifiedTime, size} | drive | — | — |
| [ ] | `google_drive.files.delete` | delete | DELETE /drive/v3/files/{fileId} | Mover archivo a papelera (no es borrado permanente) | fileId | — | drive | I | delete_drive_file |
| [ ] | `google_drive.files.purge` | delete | DELETE /drive/v3/files/{fileId}?supportsAllDrives=true | Borrar archivo definitivamente de papelera | fileId | — | drive | I | — |
| [ ] | `google_drive.files.copy` | create | POST /drive/v3/files/{fileId}/copy | Copiar archivo con opcion de cambiar nombre/padres | fileId, name, parents | {id, name, mimeType, parents, webViewLink} | drive | — | — |
| [ ] | `google_drive.files.move` | update | PATCH /drive/v3/files/{fileId} | Mover archivo a otra carpeta (cambiar parents) | fileId, parents | {id, parents} | drive | — | move_drive_file |
| [ ] | `google_drive.files.rename` | update | PATCH /drive/v3/files/{fileId} | Renombrar archivo (cambiar name) | fileId, name | {id, name} | drive | — | rename_drive_file |
| [ ] | `google_drive.trash.empty` | delete | DELETE /drive/v3/files/trash | Vaciar papelera del usuario | — | — | drive | I | — |
| [ ] | `google_drive.files.watch` | create | POST /drive/v3/files/{fileId}/watch | Suscribirse a cambios en archivo (webhook) | fileId, address, expiration | {id, resourceId, resourceUri, expiration} | drive.readonly | — | — |

### Descargar y exportar (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.files.download` | read | GET /drive/v3/files/{fileId}?alt=media | Descargar contenido del archivo | fileId, range | contenido binario | drive.readonly | — | — |
| [ ] | `google_drive.files.export` | read | GET /drive/v3/files/{fileId}/export?mimeType=<type> | Exportar documento Google a otro formato (PDF, DOCX, XLSX, etc.) | fileId, mimeType | contenido en formato solicitado | drive.readonly | — | — |
| [ ] | `google_drive.files.generate_ids` | read | GET /drive/v3/files/generateIds | Generar IDs de archivo para usar en operaciones posteriores | count, space | {ids[]} | — | — | — |

### Carpetas y unidades compartidas (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.folders.create` | create | POST /drive/v3/files | Crear carpeta (archivo con mimeType folder) | name, parents, description | {id, name, mimeType, parents, webViewLink} | drive | — | create_drive_folder |
| [ ] | `google_drive.drives.list` | read | GET /drive/v3/drives | Listar unidades compartidas (Team Drives) | pageSize, pageToken, useDomainAdminAccess | {drives[], nextPageToken} | drive.readonly | — | — |
| [ ] | `google_drive.drives.get` | read | GET /drive/v3/drives/{driveId} | Obtener metadata de unidad compartida | driveId, useDomainAdminAccess | {id, name, createdTime, kind, colorRgb, backgroundImageFile, orgUnitId} | drive.readonly | — | — |
| [ ] | `google_drive.drives.create` | create | POST /drive/v3/drives | Crear unidad compartida nueva | name, requestId | {id, name, createdTime, kind} | drive | — | — |
| [ ] | `google_drive.drives.update` | update | PATCH /drive/v3/drives/{driveId} | Actualizar metadata de unidad compartida (nombre, color, imagen) | driveId, name, colorRgb, backgroundImageFile, useDomainAdminAccess | {id, name, colorRgb} | drive | — | — |
| [ ] | `google_drive.drives.delete` | delete | DELETE /drive/v3/drives/{driveId} | Eliminar unidad compartida permanentemente | driveId, useDomainAdminAccess | — | drive | I | — |
| [ ] | `google_drive.drives.hide` | update | POST /drive/v3/drives/{driveId}/hide | Ocultar unidad compartida del usuario | driveId, useDomainAdminAccess | {id, hidden} | drive | — | — |
| [ ] | `google_drive.drives.unhide` | update | POST /drive/v3/drives/{driveId}/unhide | Mostrar unidad compartida oculta | driveId, useDomainAdminAccess | {id, hidden} | drive | — | — |

### Permisos y compartir (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.permissions.list` | read | GET /drive/v3/files/{fileId}/permissions | Listar permisos (quien tiene acceso a un archivo) | fileId, pageSize, pageToken, useDomainAdminAccess, supportsAllDrives | {permissions[], nextPageToken} | drive.readonly | — | — |
| [ ] | `google_drive.permissions.get` | read | GET /drive/v3/files/{fileId}/permissions/{permissionId} | Obtener detalles de un permiso | fileId, permissionId, useDomainAdminAccess, supportsAllDrives | {id, type, role, emailAddress, domain, kind, displayName, pendingOwner} | drive.readonly | — | — |
| [ ] | `google_drive.permissions.create` | create | POST /drive/v3/files/{fileId}/permissions | Compartir archivo (crear permiso; envía notificacion) | fileId, type, role, emailAddress, domain, notificationEmail, sendNotificationEmail | {id, type, role, emailAddress, kind} | drive | E | — |
| [ ] | `google_drive.permissions.update` | update | PATCH /drive/v3/files/{fileId}/permissions/{permissionId} | Cambiar rol de permiso (viewer->editor, etc.) | fileId, permissionId, role, useDomainAdminAccess, supportsAllDrives | {id, type, role} | drive | — | — |
| [ ] | `google_drive.permissions.delete` | delete | DELETE /drive/v3/files/{fileId}/permissions/{permissionId} | Revocar acceso a un archivo | fileId, permissionId, useDomainAdminAccess, supportsAllDrives | — | drive | — | — |
| [ ] | `google_drive.permissions.transfer_ownership` | update | PATCH /drive/v3/files/{fileId}/permissions/{permissionId} | Transferir propiedad del archivo (cambiar role a owner) | fileId, permissionId, transferOwnership | {id, type, role} | drive | I | — |

### Comentarios (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.comments.list` | read | GET /drive/v3/files/{fileId}/comments | Listar comentarios en archivo | fileId, pageSize, pageToken, includeDeleted | {comments[], nextPageToken} | drive.readonly | — | — |
| [ ] | `google_drive.comments.get` | read | GET /drive/v3/files/{fileId}/comments/{commentId} | Obtener detalles de comentario | fileId, commentId, includeDeleted | {id, content, author, createdTime, modifiedTime, quotedFileContent, replies} | drive.readonly | — | — |
| [ ] | `google_drive.comments.create` | create | POST /drive/v3/files/{fileId}/comments | Crear comentario en archivo | fileId, content, quotedFileContent, anchor | {id, content, author, createdTime} | drive | E | — |
| [ ] | `google_drive.comments.update` | update | PATCH /drive/v3/files/{fileId}/comments/{commentId} | Editar contenido de comentario | fileId, commentId, content | {id, content, modifiedTime} | drive | — | — |
| [ ] | `google_drive.comments.delete` | delete | DELETE /drive/v3/files/{fileId}/comments/{commentId} | Borrar comentario | fileId, commentId | — | drive | I | — |

### Respuestas a comentarios (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.replies.list` | read | GET /drive/v3/files/{fileId}/comments/{commentId}/replies | Listar respuestas a un comentario | fileId, commentId, pageSize, pageToken, includeDeleted | {replies[], nextPageToken} | drive.readonly | — | — |
| [ ] | `google_drive.replies.get` | read | GET /drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId} | Obtener detalles de respuesta | fileId, commentId, replyId, includeDeleted | {id, content, author, createdTime, modifiedTime} | drive.readonly | — | — |
| [ ] | `google_drive.replies.create` | create | POST /drive/v3/files/{fileId}/comments/{commentId}/replies | Responder a un comentario | fileId, commentId, content | {id, content, author, createdTime} | drive | E | — |
| [ ] | `google_drive.replies.update` | update | PATCH /drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId} | Editar respuesta | fileId, commentId, replyId, content | {id, content, modifiedTime} | drive | — | — |
| [ ] | `google_drive.replies.delete` | delete | DELETE /drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId} | Borrar respuesta | fileId, commentId, replyId | — | drive | I | — |

### Versiones y revisiones (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.revisions.list` | read | GET /drive/v3/files/{fileId}/revisions | Listar versiones anteriores de un archivo | fileId, pageSize, pageToken, supportsAllDrives | {revisions[], nextPageToken} | drive.readonly | — | — |
| [ ] | `google_drive.revisions.get` | read | GET /drive/v3/files/{fileId}/revisions/{revisionId} | Obtener metadata o descargar version anterior | fileId, revisionId, supportsAllDrives, alt | {id, mimeType, modifiedTime, publishedOutsideDrive, keepForever} | drive.readonly | — | — |
| [ ] | `google_drive.revisions.update` | update | PATCH /drive/v3/files/{fileId}/revisions/{revisionId} | Marcar version como importante (keepForever=true) | fileId, revisionId, keepForever, supportsAllDrives | {id, keepForever} | drive | — | — |
| [ ] | `google_drive.revisions.delete` | delete | DELETE /drive/v3/files/{fileId}/revisions/{revisionId} | Eliminar version anterior | fileId, revisionId, supportsAllDrives | — | drive | I | — |

### Etiquetas (Labels) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.labels.list` | read | GET /drive/v3/files/{fileId}/listLabels | Obtener etiquetas aplicadas a un archivo | fileId, maxResults | {labels[]} | drive.readonly | — | — |
| [ ] | `google_drive.labels.modify` | update | POST /drive/v3/files/{fileId}/modifyLabels | Aplicar o quitar etiquetas de un archivo | fileId, labels | {modifiedLabels[]} | drive | — | — |

### Cambios y notificaciones (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.changes.list` | read | GET /drive/v3/changes | Obtener cambios realizados en Drive desde un token | pageToken, pageSize, includeCorpusRemovals, includeItemsFromAllDrives, spaces, restrictToMyDrive, supportsAllDrives | {changes[], nextPageToken, newStartPageToken, largestChangeId} | drive.readonly | — | — |
| [ ] | `google_drive.changes.watch` | create | POST /drive/v3/changes/watch | Suscribirse a notificaciones de cambios (webhook) | pageToken, addresses, expiration, includeCorpusRemovals | {id, resourceId, resourceUri, expiration} | drive.readonly | — | — |
| [ ] | `google_drive.changes.get_start_page_token` | read | GET /drive/v3/changes/startPageToken | Obtener token para comenzar a recibir cambios futuros | supportsAllDrives, supportsTeamDrives, pageToken | {startPageToken} | drive.readonly | — | — |

### Apps instaladas (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.apps.list` | read | GET /drive/v3/apps | Listar apps autorizadas instaladas | appFilter, languageCode, pageSize, pageToken | {apps[], kind, nextPageToken} | drive.apps.readonly | — | — |
| [ ] | `google_drive.apps.get` | read | GET /drive/v3/apps/{appId} | Obtener detalles de una app instalada | appId, languageCode | {id, name, shortDescription, longDescription, icons[], supported_mimetypes[]} | drive.apps.readonly | — | — |

### Autoaprovación y flujos de aprobacion (Avanzado) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.approval.start` | create | POST /drive/v3/files/{fileId}/approvals:start | Iniciar flujo de aprobacion para archivo | fileId, approvers, message | {id, approvers[], createdTime, state} | drive | E | — |
| [ ] | `google_drive.approval.list` | read | GET /drive/v3/files/{fileId}/approvals | Listar aprobaciones en un archivo | fileId, pageSize, pageToken | {approvals[], nextPageToken} | drive | — | — |
| [ ] | `google_drive.approval.get` | read | GET /drive/v3/files/{fileId}/approvals/{approvalId} | Obtener detalles de una aprobacion | fileId, approvalId | {id, approvers[], state, createdTime, modifiedTime} | drive | — | — |
| [ ] | `google_drive.approval.approve` | update | POST /drive/v3/files/{fileId}/approvals/{approvalId}:approve | Aprobar un documento | fileId, approvalId, comment | {id, state, modifiedTime} | drive | E | — |
| [ ] | `google_drive.approval.decline` | update | POST /drive/v3/files/{fileId}/approvals/{approvalId}:decline | Rechazar una aprobacion | fileId, approvalId, comment | {id, state, modifiedTime} | drive | E | — |
| [ ] | `google_drive.approval.cancel` | update | POST /drive/v3/files/{fileId}/approvals/{approvalId}:cancel | Cancelar un flujo de aprobacion | fileId, approvalId | {id, state} | drive | — | — |
| [ ] | `google_drive.approval.reassign` | update | POST /drive/v3/files/{fileId}/approvals/{approvalId}:reassign | Reasignar aprobadores de un documento | fileId, approvalId, newApprovers | {id, approvers[]} | drive | E | — |
| [ ] | `google_drive.approval.comment` | create | POST /drive/v3/files/{fileId}/approvals/{approvalId}:comment | Agregar comentario a una aprobacion | fileId, approvalId, comment | {id, comments[]} | drive | E | — |

### Propuestas de acceso (Avanzado) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.access_proposal.list` | read | GET /drive/v3/files/{fileId}/accessproposals | Listar propuestas de acceso pendientes | fileId, pageSize, pageToken | {accessProposals[], nextPageToken} | drive | — | — |
| [ ] | `google_drive.access_proposal.get` | read | GET /drive/v3/files/{fileId}/accessproposals/{proposalId} | Obtener detalles de propuesta de acceso | fileId, proposalId | {id, requestedRole, requestingUser, createdTime, expirationTime} | drive | — | — |
| [ ] | `google_drive.access_proposal.resolve` | update | POST /drive/v3/files/{fileId}/accessproposals/{proposalId}:resolve | Aprobar o rechazar una propuesta de acceso | fileId, proposalId, action | {id, state} | drive | — | — |

### Datos de aplicacion (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.appdata.get` | read | GET /drive/v3/files/{fileId}?spaces=appDataFolder | Leer datos persistentes de app (config, cache) | fileId | {id, name, mimeType, webViewLink} | drive.appdata | — | — |
| [ ] | `google_drive.appdata.create` | create | POST /drive/v3/files?spaces=appDataFolder | Crear archivo en carpeta privada appDataFolder | name, mimeType, parents | {id, name, mimeType} | drive.appdata | — | — |

### Operaciones asincronas (Avanzado) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.operations.get` | read | GET /drive/v3/operations/{name} | Obtener estado de operacion asincrona (copiar, mover archivos grandes) | name | {name, done, error, response} | — | — | — |

### Canales y webhooks (Avanzado) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.channels.stop` | delete | POST /drive/v3/channels/stop | Detener suscripcion webhook activa | id, resourceId | — | — | — | — |

### Tipos de contenido especiales (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_drive.docs.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.document | Crear documento de Google Docs desde Drive | name, parents | {id, name, mimeType, webViewLink, owners} | drive | — | create_drive_doc |
| [ ] | `google_drive.sheets.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.spreadsheet | Crear hoja de Google Sheets desde Drive | name, parents | {id, name, mimeType, webViewLink, owners} | drive | — | create_drive_sheet |
| [ ] | `google_drive.slides.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.presentation | Crear presentacion de Google Slides desde Drive | name, parents | {id, name, mimeType, webViewLink, owners} | drive | — | create_drive_slide |
| [ ] | `google_drive.form.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.form | Crear formulario de Google Forms desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |
| [ ] | `google_drive.drawing.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.drawing | Crear dibujo de Google Drawing desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |
| [ ] | `google_drive.sites.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.sites | Crear sitio de Google Sites desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |
| [ ] | `google_drive.mymap.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.map | Crear mapa de Google My Maps desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |
| [ ] | `google_drive.script.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.script | Crear proyecto de Google Apps Script desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |
| [ ] | `google_drive.jamboard.create` | create | POST /drive/v3/files?mimeType=application/vnd.google-apps.jam | Crear Jamboard desde Drive | name, parents | {id, name, mimeType, webViewLink} | drive | — | — |

## Observaciones de las herramientas viejas

- `create_drive_doc`, `create_drive_sheet` y `create_drive_slide` crean archivos de Google desde Drive. Se solapan con `google_docs.documents.create`, `google_sheets...` y `google_slides.presentations.create`: decidir si se conservan o se dejan solo en cada app.
- `delete_drive_file`: `verb=delete`, pregunta siempre. Verificar si manda a la papelera (reversible) o borra definitivamente.
