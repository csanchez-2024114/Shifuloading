# Tareas: Google Slides

- **Funciones catalogadas:** 66 · **Hechas:** 0 · **Pendientes:** 66 · **Herramientas viejas a migrar:** 15 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.google.com/slides/api/reference/rest
- **Fuentes que consultó el catálogo:** https://developers.google.com/slides/api/reference/rest https://slides.googleapis.com/$discovery/rest?version=v1 https://developers.google.com/slides/api/guides/comments https://developers.google.com/slides/api/scopes https://developers.google.com/workspace/slides/limits
- **Paginación típica:** Google Slides API no utiliza paginación estándar; los datos se devuelven completos en presentaciones.get. Para listar presentaciones se debe usar Google Drive API con pageSize y pageToken.
- **Qué no se pudo verificar:** presentations.list (no existe en Slides API; requiere Drive API bajo capó). presentations.find_by_name (búsqueda implementada a nivel de cliente). share_presentation (no hay endpoint en Slides API; requiere Drive API o permisos de Drive). Algunos tipos de request en batchUpdate (GroupObjects, UngroupObjects, RerouteLine, UpdateLineCategory, ReplaceAllShapesWithImage, ReplaceAllShapesWithSheetsChart) no están explícitamente documentados con ejemplos en la guía oficial pero sí en el schema discovery.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/google_slides/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `google_slides`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `google_slides` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/slides/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `google_slides.presentations.list` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización y refresh token (Google) |
| Duración del token (según el catálogo) | Access token caduca en 1 hora (3600 segundos); refresh token válido hasta 6 meses si se usa, o 7 días en ambiente de prueba |
| Refresco (según el catálogo) | Sí, refresh token incluido en respuesta inicial; se renueva sin límite mientras se use dentro de 6 meses |
| Permisos (según el catálogo) | presentations (crear, editar, eliminar presentaciones), presentations.readonly (solo lectura), drive.file (archivos creados o abiertos explícitamente), drive (acceso amplio a Drive), drive.readonly (solo lectura de Drive) |
| Restricciones de acceso | Scopes presentations y presentations.readonly son sensibles y requieren verificación de la aplicación. Límite de 50 refresh tokens por cuenta por client_id. |
| Límites de ritmo | Lecturas: 3000/min (proyecto), 600/min (usuario). Lecturas costosas (getThumbnail): 300/min (proyecto), 60/min (usuario). Escrituras: 600/min (proyecto), 60/min (usuario). |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/slides/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> google_slides`. | Cuenta con `provider: google_slides`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/google_slides.presentations.list/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> google_slides <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Google Slides. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/google_slides.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Presentaciones (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.presentations.list` ★ | read | GET /drive/v3/files (consulta mimeType) | Lista todas las presentaciones del usuario | mimeType, pageSize, pageToken | lista de {id, name, webViewLink}, página siguiente | presentations.readonly o drive.file | — | list_presentations |
| [ ] | `google_slides.presentations.get` | read | GET /v1/presentations/{presentationId} | Obtiene el contenido completo de una presentación | presentationId, commentsViewMode | {id, name, slides, title, pageSize, comments si se solicita} | presentations.readonly | — | get_presentation_content |
| [ ] | `google_slides.presentations.get_info` | read | GET /v1/presentations/{presentationId} | Obtiene metadatos de una presentación sin todas las diapositivas | presentationId | {id, name, title, locale, revisionId, suggestionsViewMode} | presentations.readonly | — | get_presentation_info |
| [ ] | `google_slides.presentations.find_by_name` | read | GET /drive/v3/files (con búsqueda) | Busca una presentación por nombre usando Drive API | name, exactMatch | {id, name, webViewLink} | presentations.readonly o drive.file | — | find_presentation_by_name |
| [ ] | `google_slides.presentations.create` | create | POST /v1/presentations | Crea una nueva presentación en blanco | title | {id, name, title, revisionId, suggestionsViewMode} | presentations | — | create_presentation |
| [ ] | `google_slides.presentations.rename` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdatePagePropertiesRequest) | Cambia el título/nombre de una presentación | presentationId, title | {replies} | presentations | — | change_presentation_title |
| [ ] | `google_slides.presentations.share` | update | — | Comparte una presentación con otros usuarios | presentationId, email, role | confirmación de acceso | presentations o drive | E | share_presentation |

### Diapositivas (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.slides.list` | read | GET /v1/presentations/{presentationId} | Lista todos los IDs y propiedades de diapositivas | presentationId | lista de {objectId, name, layoutProperties} | presentations.readonly | — | get_presentation_slide_ids |
| [ ] | `google_slides.slides.get_page` | read | GET /v1/presentations/{presentationId}/pages/{pageObjectId} | Obtiene el contenido de una diapositiva específica | presentationId, pageObjectId, commentsViewMode | {objectId, name, shapes, tables, images, videos, comments si se solicita} | presentations.readonly | — | — |
| [ ] | `google_slides.slides.get_thumbnail` | read | GET /v1/presentations/{presentationId}/pages/{pageObjectId}/thumbnail | Genera una miniatura de una diapositiva | presentationId, pageObjectId, thumbnailSize, mimeType | {contentUri (URL de imagen PNG/JPG)} | presentations.readonly | — | — |
| [ ] | `google_slides.slides.add` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateSlideRequest) | Agrega una nueva diapositiva al final o posición especificada | presentationId, layoutId (opcional), insertionIndex (opcional) | {replies[0].createSlide.objectId} | presentations | — | add_slide |
| [ ] | `google_slides.slides.duplicate` | create | POST /v1/presentations/{presentationId}:batchUpdate (DuplicateObjectRequest) | Duplica una diapositiva existente | presentationId, objectId | {replies[0].duplicateObject.objectId} | presentations | — | duplicate_slide |
| [ ] | `google_slides.slides.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina una diapositiva de la presentación | presentationId, objectId | {replies} | presentations | I | — |
| [ ] | `google_slides.slides.reorder` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateSlidesPositionRequest) | Cambia el orden de las diapositivas | presentationId, slideObjectIds, insertionIndex | {replies} | presentations | — | — |
| [ ] | `google_slides.slides.update_properties` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateSlidePropertiesRequest) | Modifica propiedades de una diapositiva (fondo, layout, etc.) | presentationId, objectId, properties | {replies} | presentations | — | — |

### Formas/Shapes (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.shapes.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateShapeRequest) | Crea una forma geométrica en una diapositiva | presentationId, pageObjectId, shapeType, elementProperties | {replies[0].createShape.objectId} | presentations | — | create_shape |
| [ ] | `google_slides.shapes.update` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateShapePropertiesRequest) | Modifica propiedades de una forma (color, tamaño, posición) | presentationId, objectId, shapeProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.shapes.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina una forma de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |
| [ ] | `google_slides.shapes.group` | create | POST /v1/presentations/{presentationId}:batchUpdate (GroupObjectsRequest) | Agrupa múltiples formas en un grupo | presentationId, objectIds | {replies[0].groupObjects.objectId} | presentations | — | — |
| [ ] | `google_slides.shapes.ungroup` | update | POST /v1/presentations/{presentationId}:batchUpdate (UngroupObjectsRequest) | Desagrupa un grupo de formas | presentationId, objectId | {replies} | presentations | — | — |

### Líneas/Conectores (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.lines.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateLineRequest) | Crea una línea o conector entre elementos | presentationId, pageObjectId, lineCategory, elementProperties | {replies[0].createLine.objectId} | presentations | — | — |
| [ ] | `google_slides.lines.update` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateLinePropertiesRequest) | Modifica propiedades de una línea (color, grosor, estilo) | presentationId, objectId, lineProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.lines.update_category` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateLineCategoryRequest) | Cambia el tipo de línea (recta, codo, curva) | presentationId, objectId, lineCategory | {replies} | presentations | — | — |
| [ ] | `google_slides.lines.reroute` | update | POST /v1/presentations/{presentationId}:batchUpdate (RerouteLineRequest) | Recalcula el enrutamiento automático de una línea conectora | presentationId, objectId | {replies} | presentations | — | — |
| [ ] | `google_slides.lines.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina una línea de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |

### Texto (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.text.insert` | create | POST /v1/presentations/{presentationId}:batchUpdate (InsertTextRequest) | Inserta texto en una forma o tabla | presentationId, objectId, text, insertionIndex (opcional) | {replies[0].insertText.text} | presentations | — | insert_text_in_presentation |
| [ ] | `google_slides.text.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteTextRequest) | Elimina un rango de texto de una forma | presentationId, objectId, textRange | {replies} | presentations | I | — |
| [ ] | `google_slides.text.replace` | update | POST /v1/presentations/{presentationId}:batchUpdate (ReplaceAllTextRequest) | Busca y reemplaza todo el texto en la presentación | presentationId, containsText, replaceText | {replies[0].replaceAllText.occurrencesChanged} | presentations | — | replace_text_in_presentation |
| [ ] | `google_slides.text.update_style` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateTextStyleRequest) | Modifica el formato de texto (fuente, tamaño, color, negrita, etc.) | presentationId, objectId, textRange, textStyle | {replies} | presentations | — | — |
| [ ] | `google_slides.text.update_paragraph_style` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateParagraphStyleRequest) | Modifica estilos de párrafo (alineación, espaciado, sangría) | presentationId, objectId, textRange, paragraphStyle | {replies} | presentations | — | — |
| [ ] | `google_slides.text.create_bullets` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateParagraphBulletsRequest) | Agrega formato de lista/viñetas a párrafos | presentationId, objectId, textRange, bulletPreset | {replies} | presentations | — | — |
| [ ] | `google_slides.text.delete_bullets` | update | POST /v1/presentations/{presentationId}:batchUpdate (DeleteParagraphBulletsRequest) | Elimina el formato de viñetas de párrafos | presentationId, objectId, textRange | {replies} | presentations | — | — |

### Tablas (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.tables.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateTableRequest) | Crea una tabla en una diapositiva | presentationId, pageObjectId, rows, columns, elementProperties | {replies[0].createTable.objectId} | presentations | — | create_table |
| [ ] | `google_slides.tables.insert_rows` | create | POST /v1/presentations/{presentationId}:batchUpdate (InsertTableRowsRequest) | Agrega filas a una tabla existente | presentationId, tableObjectId, rowIndex, number | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.insert_columns` | create | POST /v1/presentations/{presentationId}:batchUpdate (InsertTableColumnsRequest) | Agrega columnas a una tabla existente | presentationId, tableObjectId, columnIndex, number | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.delete_row` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteTableRowRequest) | Elimina una fila de una tabla | presentationId, tableObjectId, rowIndex | {replies} | presentations | I | — |
| [ ] | `google_slides.tables.delete_column` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteTableColumnRequest) | Elimina una columna de una tabla | presentationId, tableObjectId, columnIndex | {replies} | presentations | I | — |
| [ ] | `google_slides.tables.update_cell` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateTableCellPropertiesRequest) | Modifica propiedades de celdas (color, contenido, alineación) | presentationId, tableObjectId, rowIndex, columnIndex, tableCellProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.update_row` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateTableRowPropertiesRequest) | Modifica propiedades de una fila (altura, color de fondo) | presentationId, tableObjectId, rowIndex, tableRowProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.update_column` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateTableColumnPropertiesRequest) | Modifica propiedades de una columna (ancho) | presentationId, tableObjectId, columnIndex, tableColumnProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.update_border` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateTableBorderPropertiesRequest) | Modifica bordes de tabla (color, grosor, estilo) | presentationId, tableObjectId, borderProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.merge_cells` | update | POST /v1/presentations/{presentationId}:batchUpdate (MergeTableCellsRequest) | Combina celdas en una tabla | presentationId, tableObjectId, cellRange | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.unmerge_cells` | update | POST /v1/presentations/{presentationId}:batchUpdate (UnmergeTableCellsRequest) | Separa celdas combinadas en una tabla | presentationId, tableObjectId, cellRange | {replies} | presentations | — | — |
| [ ] | `google_slides.tables.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina una tabla completa de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |

### Imágenes (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.images.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateImageRequest) | Inserta una imagen en una diapositiva | presentationId, pageObjectId, url (o Drive fileId), elementProperties | {replies[0].createImage.objectId} | presentations | — | — |
| [ ] | `google_slides.images.replace` | update | POST /v1/presentations/{presentationId}:batchUpdate (ReplaceImageRequest) | Reemplaza el contenido de una imagen existente | presentationId, imageObjectId, imageUrl (o Drive fileId) | {replies} | presentations | — | — |
| [ ] | `google_slides.images.replace_all` | update | POST /v1/presentations/{presentationId}:batchUpdate (ReplaceAllShapesWithImageRequest) | Reemplaza todas las formas con una imagen específica | presentationId, containsText (opcional), imageUrl (o Drive fileId) | {replies[0].replaceAllShapesWithImage.occurrencesChanged} | presentations | — | — |
| [ ] | `google_slides.images.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina una imagen de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |

### Videos (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.videos.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateVideoRequest) | Inserta un video de YouTube en una diapositiva | presentationId, pageObjectId, videoSourceUrl, elementProperties | {replies[0].createVideo.objectId} | presentations | — | — |
| [ ] | `google_slides.videos.update` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateVideoPropertiesRequest) | Modifica propiedades de un video (tamaño, posición, autoplay) | presentationId, videoObjectId, videoProperties | {replies} | presentations | — | — |
| [ ] | `google_slides.videos.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina un video de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |

### Gráficos (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.charts.create_sheets_chart` | create | POST /v1/presentations/{presentationId}:batchUpdate (CreateSheetsChartRequest) | Inserta un gráfico desde Google Sheets en una diapositiva | presentationId, pageObjectId, sheetsChartId, elementProperties | {replies[0].createSheetsChart.objectId} | presentations, spreadsheets.readonly | — | — |
| [ ] | `google_slides.charts.refresh_sheets_chart` | update | POST /v1/presentations/{presentationId}:batchUpdate (RefreshSheetsChartRequest) | Actualiza un gráfico de Sheets a los datos más recientes | presentationId, chartObjectId | {replies} | presentations, spreadsheets.readonly | — | — |
| [ ] | `google_slides.charts.replace_all_with_sheets_chart` | update | POST /v1/presentations/{presentationId}:batchUpdate (ReplaceAllShapesWithSheetsChartRequest) | Reemplaza todas las formas con un gráfico de Sheets | presentationId, containsText (opcional), sheetsChartId | {replies[0].replaceAllShapesWithSheetsChart.occurrencesChanged} | presentations, spreadsheets.readonly | — | — |
| [ ] | `google_slides.charts.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteObjectRequest) | Elimina un gráfico de la diapositiva | presentationId, objectId | {replies} | presentations | I | — |

### Comentarios (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.comments.list` | read | GET /v1/presentations/{presentationId} (con commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED) | Lista todos los comentarios en una presentación | presentationId | {comments[].id, content, author, createTime, anchor} | presentations.readonly | — | get_presentation_comments |
| [ ] | `google_slides.comments.get_page_comments` | read | GET /v1/presentations/{presentationId}/pages/{pageObjectId} (con commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED) | Obtiene comentarios de una diapositiva específica | presentationId, pageObjectId | {comments[].id, content, author, createTime, anchor} | presentations.readonly | — | — |
| [ ] | `google_slides.comments.create` | create | POST /v1/presentations/{presentationId}:batchUpdate (InsertCommentRequest) | Crea un nuevo hilo de comentario en una ubicación | presentationId, anchor (objectId o cell), content, assignee (opcional) | {replies[0].insertComment.commentId} | presentations | E | — |
| [ ] | `google_slides.comments.reply` | create | POST /v1/presentations/{presentationId}:batchUpdate (AddCommentReplyRequest) | Agrega una respuesta a un hilo de comentario existente | presentationId, commentId, content, commentAction (opcional) | {replies[0].addCommentReply.replyId} | presentations | E | — |
| [ ] | `google_slides.comments.update` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdateCommentPostRequest) | Modifica el contenido de un comentario o respuesta | presentationId, commentId, postId, content | {replies} | presentations | — | — |
| [ ] | `google_slides.comments.delete` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteCommentRequest) | Elimina un hilo de comentario completo | presentationId, commentId | {replies} | presentations | I | — |
| [ ] | `google_slides.comments.delete_reply` | delete | POST /v1/presentations/{presentationId}:batchUpdate (DeleteCommentReplyRequest) | Elimina una respuesta individual de un comentario | presentationId, commentId, replyId | {replies} | presentations | I | — |

### Elementos de Página (transformación y propiedades) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.page_elements.update_transform` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdatePageElementTransformRequest) | Modifica posición, tamaño, rotación de un elemento | presentationId, objectId, transform | {replies} | presentations | — | — |
| [ ] | `google_slides.page_elements.update_z_order` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdatePageElementsZOrderRequest) | Cambia el orden de apilamiento (adelante/atrás) de elementos | presentationId, pageElementProperties, operation (BRING_TO_FRONT, SEND_TO_BACK, etc.) | {replies} | presentations | — | — |
| [ ] | `google_slides.page_elements.update_alt_text` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdatePageElementAltTextRequest) | Define texto alternativo para accesibilidad | presentationId, objectId, description, title | {replies} | presentations | — | — |

### Páginas/Diapositivas (propiedades) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_slides.pages.update_properties` | update | POST /v1/presentations/{presentationId}:batchUpdate (UpdatePagePropertiesRequest) | Modifica propiedades de página (fondo, color, esquema) | presentationId, pageObjectId, pageProperties | {replies} | presentations | — | — |

## Observaciones de las herramientas viejas

- `BIGTOOLS_REGISTRY` lista 10 de las 15 (faltan `get_presentation_info`, `get_presentation_comments`, `get_presentation_slide_ids`, `change_presentation_title`, `create_shape`).
- `share_presentation` da acceso a otras personas: sale al exterior y puede exponer informacion; pedir confirmacion.
