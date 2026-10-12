# Tareas: Google Docs

- **Funciones catalogadas:** 62 · **Hechas:** 0 · **Pendientes:** 62 · **Herramientas viejas a migrar:** 15 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.google.com/docs/api/reference/rest
- **Fuentes que consultó el catálogo:** https://developers.google.com/docs/api/reference/rest https://developers.google.com/docs/api/reference/rest/v1/documents https://developers.google.com/docs/api/reference/rest/v1/documents/batchUpdate https://developers.google.com/docs/api/auth https://developers.google.com/docs/api/limits
- **Paginación típica:** No en Docs API; Drive API (para búsqueda) usa pageToken/nextPageToken
- **Qué no se pudo verificar:** Detalles exactos de campos en comment replies y content ranges; documentación completa de sugerencias
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/google_docs/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `google_docs`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `google_docs` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/docs/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `google_docs.user.get_info` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización y refresh token (Google; flujo estándar) |
| Duración del token (según el catálogo) | 1 hora (se renueva automáticamente con refresh token) |
| Refresco (según el catálogo) | Sí, usando refresh token con scope openid |
| Permisos (según el catálogo) | documents (crear/editar Docs), documents.readonly (solo lectura), drive (gestionar Drive), drive.readonly (solo lectura Drive), drive.file (acceso solo a archivos usados), userinfo.profile (perfil del usuario), userinfo.email (email del usuario) |
| Restricciones de acceso | Revisión requerida para alcance sensitive (documents, documents.readonly); se necesita oauth2 scope para userinfo; Drive API requerida para listar/buscar/eliminar documentos |
| Límites de ritmo | 300 lecturas por minuto, 60 escrituras por minuto (por usuario por proyecto) |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/docs/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> google_docs`. | Cuenta con `provider: google_docs`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/google_docs.user.get_info/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> google_docs <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Google Docs. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/google_docs.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### User (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.user.get_info` ★ | read | GET /oauth2/v2/userinfo | Obtiene la información del usuario autenticado | — | {id, email, name, picture, verified_email} | userinfo.profile, userinfo.email | — | — |

### Documents (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.documents.create` | create | POST /v1/documents | Crea un nuevo documento en blanco o con contenido inicial | title, tabs, body | {documentId, title, body, revisionId} | documents | — | create_doc |
| [ ] | `google_docs.documents.get_content` | read | GET /v1/documents/{documentId} | Obtiene el contenido completo del documento | documentId | {documentId, title, body, tabs, revisionId} | documents, documents.readonly, drive, drive.readonly, drive.file | — | get_doc_content |
| [ ] | `google_docs.documents.get_info` | read | GET /v1/documents/{documentId} | Obtiene metadatos del documento (título, revisor, creador, fechas) | documentId | {documentId, title, revisionId, suggestionsViewMode, createdTime, modifiedTime} | documents, documents.readonly, drive, drive.readonly, drive.file | — | get_doc_info |
| [ ] | `google_docs.documents.get_with_suggestions` | read | GET /v1/documents/{documentId}?suggestionsViewMode=SUGGESTIONS_INLINE | Obtiene documento con cambios sugeridos visibles | documentId, suggestionsViewMode | {documentId, title, body, suggestions} | documents, documents.readonly, drive, drive.readonly, drive.file | — | get_doc_with_suggestions |
| [ ] | `google_docs.documents.find_by_name` | read | GET /drive/v3/files?q=name contains '...' and mimeType='application/vnd.google-apps.document' | Busca documentos por nombre exacto o parcial | name | {files: [{id, name, modifiedTime, mimeType}], nextPageToken} | drive, drive.readonly, drive.file | — | find_doc_by_name |
| [ ] | `google_docs.documents.list_by_names` | read | GET /drive/v3/files?q=name in (...) and mimeType=... | Busca múltiples documentos por sus nombres | names | {files: [{id, name, modifiedTime}], nextPageToken} | drive, drive.readonly, drive.file | — | list_docs_by_names |
| [ ] | `google_docs.documents.find_by_author` | read | GET /drive/v3/files?q=createdBy=... and mimeType=... | Busca documentos creados por un usuario específico | ownerEmail | {files: [{id, name, owners, createdTime}], nextPageToken} | drive, drive.readonly, drive.file | — | find_docs_by_author |
| [ ] | `google_docs.documents.find_by_date_range` | read | GET /drive/v3/files?q=createdTime>='...' and createdTime<='...' and mimeType=... | Busca documentos modificados en un rango de fechas | startDate, endDate | {files: [{id, name, modifiedTime, createdTime}], nextPageToken} | drive, drive.readonly, drive.file | — | find_docs_by_date_range |
| [ ] | `google_docs.documents.list_recent` | read | GET /drive/v3/files?orderBy=modifiedTime desc&mimeType=application/vnd.google-apps.document | Lista documentos recientes ordenados por fecha de modificación | pageSize, pageToken | {files: [{id, name, modifiedTime}], nextPageToken} | drive, drive.readonly, drive.file | — | — |

### Text Operations (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.text.insert` | update | POST /v1/documents/{documentId}:batchUpdate (InsertTextRequest) | Inserta texto en una posición específica | documentId, text, index | {documentId, replies: [{insertText: {textLength}}]} | documents, drive | — | insert_text_in_doc |
| [ ] | `google_docs.text.replace_all` | update | POST /v1/documents/{documentId}:batchUpdate (ReplaceAllTextRequest) | Reemplaza todas las instancias de un texto por otro | documentId, findText, replaceText | {documentId, replies: [{replaceAllText: {occurrencesChanged}}]} | documents, drive | — | replace_doc_text |
| [ ] | `google_docs.text.delete_by_range` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteContentRangeRequest) | Elimina contenido entre dos posiciones | documentId, startIndex, endIndex | {documentId, replies: [{deleteContentRange}]} | documents, drive | I | delete_doc_text_by_content |
| [ ] | `google_docs.text.update_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateTextStyleRequest) | Modifica el estilo de texto (negrita, cursiva, color, tamaño, fuente) | documentId, startIndex, endIndex, textStyle | {documentId, replies: [{updateTextStyle}]} | documents, drive | — | — |

### Paragraph Operations (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.paragraph.update_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateParagraphStyleRequest) | Modifica el estilo de párrafos (alineación, espaciado, sangría) | documentId, startIndex, endIndex, paragraphStyle | {documentId, replies: [{updateParagraphStyle}]} | documents, drive | — | — |
| [ ] | `google_docs.paragraph.create_bullets` | update | POST /v1/documents/{documentId}:batchUpdate (CreateParagraphBulletsRequest) | Añade viñetas a párrafos específicos | documentId, startIndex, endIndex, bulletPreset | {documentId, replies: [{createParagraphBullets}]} | documents, drive | — | — |
| [ ] | `google_docs.paragraph.delete_bullets` | update | POST /v1/documents/{documentId}:batchUpdate (DeleteParagraphBulletsRequest) | Elimina viñetas de párrafos específicos | documentId, startIndex, endIndex | {documentId, replies: [{deleteParagraphBullets}]} | documents, drive | — | — |

### Tables (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.table.insert` | create | POST /v1/documents/{documentId}:batchUpdate (InsertTableRequest) | Inserta una tabla con número especificado de filas y columnas | documentId, rows, columns, location | {documentId, replies: [{insertTable: {objectId}}]} | documents, drive | — | insert_table_in_doc |
| [ ] | `google_docs.table.insert_row` | update | POST /v1/documents/{documentId}:batchUpdate (InsertTableRowRequest) | Añade una fila a una tabla existente | documentId, tableId, insertionIndex | {documentId, replies: [{insertTableRow}]} | documents, drive | — | — |
| [ ] | `google_docs.table.insert_column` | update | POST /v1/documents/{documentId}:batchUpdate (InsertTableColumnRequest) | Añade una columna a una tabla existente | documentId, tableId, insertionIndex | {documentId, replies: [{insertTableColumn}]} | documents, drive | — | — |
| [ ] | `google_docs.table.delete_row` | update | POST /v1/documents/{documentId}:batchUpdate (DeleteTableRowRequest) | Elimina una fila de una tabla | documentId, tableId, rowIndex | {documentId, replies: [{deleteTableRow}]} | documents, drive | — | — |
| [ ] | `google_docs.table.delete_column` | update | POST /v1/documents/{documentId}:batchUpdate (DeleteTableColumnRequest) | Elimina una columna de una tabla | documentId, tableId, columnIndex | {documentId, replies: [{deleteTableColumn}]} | documents, drive | — | — |
| [ ] | `google_docs.table.merge_cells` | update | POST /v1/documents/{documentId}:batchUpdate (MergeTableCellsRequest) | Fusiona celdas de tabla en una sola celda | documentId, tableId, cellRange | {documentId, replies: [{mergeTableCells: {mergedCell}}]} | documents, drive | — | — |
| [ ] | `google_docs.table.unmerge_cells` | update | POST /v1/documents/{documentId}:batchUpdate (UnmergeTableCellsRequest) | Divide celdas fusionadas en celdas separadas | documentId, tableId, cellRange | {documentId, replies: [{unmergeTableCells: {unmercedCells}}]} | documents, drive | — | — |
| [ ] | `google_docs.table.update_cell_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateTableCellStyleRequest) | Modifica el estilo de celdas de tabla (color de fondo, bordes) | documentId, tableId, cellRange, tableCellStyle | {documentId, replies: [{updateTableCellStyle}]} | documents, drive | — | — |
| [ ] | `google_docs.table.update_row_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateTableRowStyleRequest) | Modifica el estilo de filas de tabla | documentId, tableId, rowIndices, tableRowStyle | {documentId, replies: [{updateTableRowStyle}]} | documents, drive | — | — |
| [ ] | `google_docs.table.update_column_properties` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateTableColumnPropertiesRequest) | Modifica propiedades de columnas de tabla (ancho) | documentId, tableId, columnIndices, tableColumnProperties | {documentId, replies: [{updateTableColumnProperties}]} | documents, drive | — | — |
| [ ] | `google_docs.table.pin_header_rows` | update | POST /v1/documents/{documentId}:batchUpdate (PinTableHeaderRowsRequest) | Fija filas de encabezado en la parte superior de tabla | documentId, tableId, pinnedHeaderRowsCount | {documentId, replies: [{pinTableHeaderRows}]} | documents, drive | — | — |
| [ ] | `google_docs.table.fill` | update | POST /v1/documents/{documentId}:batchUpdate (InsertTextRequest x múltiples) | Llena celdas de tabla con contenido de texto | documentId, tableId, cellData | {documentId, replies: [{insertText}]} | documents, drive | — | fill_table_in_doc |

### Images & Media (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.image.insert_inline` | create | POST /v1/documents/{documentId}:batchUpdate (InsertInlineImageRequest) | Inserta una imagen en línea en el documento | documentId, imageUri, index | {documentId, replies: [{insertInlineImage: {objectId}}]} | documents, drive | E | — |
| [ ] | `google_docs.image.replace` | update | POST /v1/documents/{documentId}:batchUpdate (ReplaceImageRequest) | Reemplaza el contenido de una imagen existente | documentId, imageObjectId, imageUri | {documentId, replies: [{replaceImage}]} | documents, drive | — | — |
| [ ] | `google_docs.object.delete_positioned` | delete | POST /v1/documents/{documentId}:batchUpdate (DeletePositionedObjectRequest) | Elimina objetos posicionados (imágenes, dibujos) | documentId, objectId | {documentId, replies: [{deletePositionedObject}]} | documents, drive | I | — |

### Headers & Footers (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.header.create` | create | POST /v1/documents/{documentId}:batchUpdate (CreateHeaderRequest) | Crea un encabezado en el documento | documentId, sectionId | {documentId, replies: [{createHeader: {headerId}}]} | documents, drive | — | — |
| [ ] | `google_docs.footer.create` | create | POST /v1/documents/{documentId}:batchUpdate (CreateFooterRequest) | Crea un pie de página en el documento | documentId, sectionId | {documentId, replies: [{createFooter: {footerId}}]} | documents, drive | — | — |
| [ ] | `google_docs.header.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteHeaderRequest) | Elimina el encabezado de una sección | documentId, headerId, sectionId | {documentId, replies: [{deleteHeader}]} | documents, drive | — | — |
| [ ] | `google_docs.footer.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteFooterRequest) | Elimina el pie de página de una sección | documentId, footerId, sectionId | {documentId, replies: [{deleteFooter}]} | documents, drive | — | — |

### Section Operations (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.section.insert_break` | create | POST /v1/documents/{documentId}:batchUpdate (InsertSectionBreakRequest) | Inserta un salto de sección | documentId, index, sectionStyle | {documentId, replies: [{insertSectionBreak: {sectionId}}]} | documents, drive | — | — |
| [ ] | `google_docs.section.update_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateSectionStyleRequest) | Modifica el estilo de una sección (columnas, márgenes) | documentId, sectionId, sectionStyle | {documentId, replies: [{updateSectionStyle}]} | documents, drive | — | — |

### Page Operations (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.page.insert_break` | create | POST /v1/documents/{documentId}:batchUpdate (InsertPageBreakRequest) | Inserta un salto de página | documentId, index | {documentId, replies: [{insertPageBreak}]} | documents, drive | — | — |

### Comments (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.comment.insert` | create | POST /v1/documents/{documentId}:batchUpdate (InsertCommentRequest) | Inserta un comentario en una posición del documento | documentId, index, content, quotedText | {documentId, replies: [{insertComment: {commentId}}]} | documents, drive | E | — |
| [ ] | `google_docs.comment.list` | read | GET /v1/documents/{documentId} (con commentsViewMode=COMMENTS_VIEW_MODE_EXISTING) | Obtiene todos los comentarios del documento | documentId, commentsViewMode | {documentId, suggestedDocumentStyle: {comments}} | documents, documents.readonly, drive, drive.readonly, drive.file | — | get_doc_comments |
| [ ] | `google_docs.comment.add_reply` | create | POST /v1/documents/{documentId}:batchUpdate (AddCommentReplyRequest) | Añade una respuesta a un comentario existente | documentId, commentId, content | {documentId, replies: [{addCommentReply: {replyId}}]} | documents, drive | E | — |
| [ ] | `google_docs.comment.update_post` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateCommentPostRequest) | Modifica el contenido de un comentario | documentId, commentId, content | {documentId, replies: [{updateCommentPost}]} | documents, drive | — | — |
| [ ] | `google_docs.comment.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteCommentRequest) | Elimina un comentario del documento | documentId, commentId | {documentId, replies: [{deleteComment}]} | documents, drive | I | — |
| [ ] | `google_docs.comment.delete_reply` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteCommentReplyRequest) | Elimina una respuesta de un comentario | documentId, commentId, replyId | {documentId, replies: [{deleteCommentReply}]} | documents, drive | I | — |

### Suggestions (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.suggestion.accept` | update | POST /v1/documents/{documentId}:batchUpdate (AcceptSuggestionRequest) | Acepta un cambio sugerido | documentId, suggestionId | {documentId, replies: [{acceptSuggestion}], suggestionResponses: [{acceptedSuggestion}]} | documents, drive | — | — |
| [ ] | `google_docs.suggestion.reject` | update | POST /v1/documents/{documentId}:batchUpdate (RejectSuggestionRequest) | Rechaza un cambio sugerido | documentId, suggestionId | {documentId, replies: [{rejectSuggestion}], suggestionResponses: [{rejectedSuggestion}]} | documents, drive | — | — |
| [ ] | `google_docs.suggestion.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteSuggestionRequest) | Elimina un cambio sugerido del documento | documentId, suggestionId | {documentId, replies: [{deleteSuggestion}]} | documents, drive | I | — |

### Named Ranges & References (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.named_range.create` | create | POST /v1/documents/{documentId}:batchUpdate (CreateNamedRangeRequest) | Crea un rango con nombre para referencia | documentId, name, startIndex, endIndex | {documentId, replies: [{createNamedRange: {namedRangeId}}]} | documents, drive | — | — |
| [ ] | `google_docs.named_range.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteNamedRangeRequest) | Elimina un rango con nombre | documentId, namedRangeId | {documentId, replies: [{deleteNamedRange}]} | documents, drive | — | — |
| [ ] | `google_docs.named_range.replace_content` | update | POST /v1/documents/{documentId}:batchUpdate (ReplaceNamedRangeContentRequest) | Reemplaza el contenido dentro de un rango con nombre | documentId, namedRangeId, text | {documentId, replies: [{replaceNamedRangeContent}]} | documents, drive | — | — |

### Document Structure (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.document.rename` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateDocumentStyleRequest con title) | Cambia el título/nombre del documento | documentId, title | {documentId, replies: [{updateDocumentStyle}]} | documents, drive | — | change_doc_title |
| [ ] | `google_docs.document.update_style` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateDocumentStyleRequest) | Modifica el estilo del documento (márgenes, página, idioma) | documentId, documentStyle | {documentId, replies: [{updateDocumentStyle}]} | documents, drive | — | — |
| [ ] | `google_docs.tab.add` | create | POST /v1/documents/{documentId}:batchUpdate (AddDocumentTabRequest) | Añade una pestaña nueva al documento | documentId, title | {documentId, replies: [{addDocumentTab: {tabId}}]} | documents, drive | — | — |
| [ ] | `google_docs.tab.delete` | delete | POST /v1/documents/{documentId}:batchUpdate (DeleteTabRequest) | Elimina una pestaña del documento | documentId, tabId | {documentId, replies: [{deleteTab}]} | documents, drive | — | — |
| [ ] | `google_docs.tab.update_properties` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateDocumentTabPropertiesRequest) | Modifica las propiedades de una pestaña (título, posición) | documentId, tabId, title | {documentId, replies: [{updateDocumentTabProperties}]} | documents, drive | — | — |

### Styling & Named Styles (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.style.update_named` | update | POST /v1/documents/{documentId}:batchUpdate (UpdateNamedStyleRequest) | Modifica una definición de estilo nombrado | documentId, styleName, namedStyleProperties | {documentId, replies: [{updateNamedStyle}]} | documents, drive | — | — |

### Advanced Features (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_docs.element.insert_person` | create | POST /v1/documents/{documentId}:batchUpdate (InsertPersonRequest) | Inserta una referencia a una persona con información de contacto | documentId, index, personName, personEmail | {documentId, replies: [{insertPerson: {objectId}}]} | documents, drive | E | — |
| [ ] | `google_docs.element.insert_rich_link` | create | POST /v1/documents/{documentId}:batchUpdate (InsertRichLinkRequest) | Inserta un enlace enriquecido (preview) en el documento | documentId, index, url, title | {documentId, replies: [{insertRichLink: {objectId}}]} | documents, drive | — | — |
| [ ] | `google_docs.element.insert_date` | create | POST /v1/documents/{documentId}:batchUpdate (InsertDateRequest) | Inserta la fecha actual o especificada en formato personalizado | documentId, index, dateFormat | {documentId, replies: [{insertDate: {objectId}}]} | documents, drive | — | — |
| [ ] | `google_docs.footnote.create` | create | POST /v1/documents/{documentId}:batchUpdate (CreateFootnoteRequest) | Crea una nota al pie en el documento | documentId, index | {documentId, replies: [{createFootnote: {footnoteId}}]} | documents, drive | — | — |
| [ ] | `google_docs.batch.apply` | update | POST /v1/documents/{documentId}:batchUpdate | Aplica múltiples actualizaciones en una sola llamada (batching) | documentId, requests, writeControl | {documentId, replies: [], writeControl, commentUpdateState} | documents, drive | — | — |

## Observaciones de las herramientas viejas

- `BIGTOOLS_REGISTRY` solo lista 9 de las 15 (faltan los `get_doc_info`, `get_doc_with_suggestions`, `get_doc_comments`, `find_docs_by_author`, `find_docs_by_date_range`, `fill_table_in_doc`); el inspector del agente no las conoce.
- `delete_doc_text_by_content` borra contenido: `verb=delete`. Docs guarda historial de versiones, pero la funcion no lo restaura: marcar `reversible` con criterio.
- Las salidas de contenido de documento pueden ser enormes: recortar el modelo de salida.
