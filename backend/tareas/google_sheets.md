# Tareas: Google Sheets

- **Funciones catalogadas:** 79 · **Hechas:** 0 · **Pendientes:** 79 · **Herramientas viejas a migrar:** 17 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.google.com/sheets/api/reference/rest
- **Fuentes que consultó el catálogo:** https://developers.google.com/sheets/api/reference/rest https://developers.google.com/sheets/api/guides/batchupdate https://developers.google.com/sheets/api/guides/values https://developers.google.com/sheets/api/guides/create https://developers.google.com/sheets/api/scopes https://developers.google.com/sheets/api/limits https://developers.google.com/identity/protocols/oauth2
- **Paginación típica:** No paginación típica; batchGet devuelve todos los rangos solicitados; para listar spreadsheets el usuario debe usar Drive API con MIME type application/vnd.google-apps.spreadsheet
- **Qué no se pudo verificar:** Algunos detalles de paginación exacta en Drive API search; máximo de células por solicitud no documentado; scopes exactos por operación algunos no especificados explícitamente
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/google_sheets/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `google_sheets`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `google_sheets` |
| Variables del `.env` que necesitas | DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/google/sheets/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `google_sheets.account.whoami` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con authorization code; usuario autoriza app, recibe code, app intercambia code por access_token y refresh_token |
| Duración del token (según el catálogo) | Access token dura limitado (típicamente 1 hora); no especificado en docs |
| Refresco (según el catálogo) | Refresh token dura 6 meses sin uso, máximo 100 por Google Account; se renueva con POST /token si la credencial es válida |
| Permisos (según el catálogo) | spreadsheets (leer, crear, editar, borrar hojas), spreadsheets.readonly (solo leer), drive.file (archivo específico), drive (todos los Drive files), drive.readonly (solo leer Drive) |
| Restricciones de acceso | Requiere que el usuario haya autorizado la app; límite de 100 refresh tokens por client_id; refresh tokens expiran si no se usan en 6 meses o si el usuario cambia contraseña |
| Límites de ritmo | 300 solicitudes/minuto por proyecto, 60/minuto por usuario; requests > 180 segundos timeout; payload <= 2MB recomendado; sin límite diario si respeta por-minuto |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/google/sheets/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> google_sheets`. | Cuenta con `provider: google_sheets`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/google_sheets.account.whoami/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> google_sheets <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Google Sheets. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/google_sheets.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Identidad y Autenticación (Whoami) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.account.whoami` ★ | read | GET /v4/about | Obtiene información de la cuenta y usuario autenticado | — | {displayName, emailAddress, profilePicture} | drive.readonly | — | — |

### Spreadsheets (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.spreadsheets.create` | create | POST /v4/spreadsheets | Crea una hoja de cálculo nueva con título y propiedades | title, locale, autoRecalc | {spreadsheetId, spreadsheetUrl, properties, sheets} | spreadsheets | — | — |
| [ ] | `google_sheets.spreadsheets.get` | read | GET /v4/spreadsheets/{spreadsheetId} | Obtiene metadatos y estructura de una hoja de cálculo | spreadsheetId, fields (opcional) | {spreadsheetId, properties, sheets, namedRanges, developerMetadata} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.spreadsheets.search` | read | Usar Drive API /v3/files/list | Busca hojas de cálculo por nombre o propiedad del usuario | q (query), pageSize | lista de {id, name, mimeType, webViewLink} | spreadsheets.readonly | — | search_sheets_files |
| [ ] | `google_sheets.spreadsheets.batchupdate` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate | Aplica múltiples actualizaciones atómicas a una hoja de cálculo | spreadsheetId, requests (array) | {spreadsheetId, replies (resultados por request)} | spreadsheets | — | — |
| [ ] | `google_sheets.spreadsheets.get_by_datafilter` | read | POST /v4/spreadsheets/{spreadsheetId}:getByDataFilter | Obtiene datos de la hoja según filtro de datos | spreadsheetId, dataFilters | {spreadsheetId, spreadsheetProperties, sheets con datos filtrados} | spreadsheets.readonly | — | — |

### Sheets (Pestañas) (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.tabs.list` | read | GET /v4/spreadsheets/{spreadsheetId} | Lista todas las pestañas (sheets) de una hoja de cálculo | spreadsheetId | {sheets: [{sheetId, title, index, sheetType, gridProperties}]} | spreadsheets.readonly | — | list_sheet_tabs |
| [ ] | `google_sheets.tabs.get` | read | GET /v4/spreadsheets/{spreadsheetId} | Obtiene propiedades de una pestaña específica por ID | spreadsheetId, sheetId | {sheetId, title, index, sheetType, gridProperties, tabColor} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.tabs.create` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddSheetRequest) | Crea una nueva pestaña en la hoja de cálculo | spreadsheetId, title, index (opcional), gridProperties (filas/columnas) | {sheetId, title, index, gridProperties} | spreadsheets | E | create_sheet_tab |
| [ ] | `google_sheets.tabs.rename` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateSheetPropertiesRequest) | Renombra una pestaña existente | spreadsheetId, sheetId, newTitle | {sheetId, title (actualizado)} | spreadsheets | — | rename_sheet_tab |
| [ ] | `google_sheets.tabs.duplicate` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DuplicateSheetRequest) o POST /v4/spreadsheets/{spreadsheetId}/sheets/{sheetId}:copyTo | Duplica una pestaña dentro de la misma o distinta hoja | spreadsheetId, sheetId, insertSheet (índice opcional) | {sheetId (nueva), title (copia de...), gridProperties} | spreadsheets | — | duplicate_sheet_tab |
| [ ] | `google_sheets.tabs.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteSheetRequest) | Elimina una pestaña de la hoja de cálculo | spreadsheetId, sheetId | {} (operación vacía) | spreadsheets | I | — |
| [ ] | `google_sheets.tabs.hide` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateSheetPropertiesRequest) | Oculta una pestaña sin borrarla | spreadsheetId, sheetId, hidden=true | {sheetId, hidden: true} | spreadsheets | — | — |
| [ ] | `google_sheets.tabs.show` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateSheetPropertiesRequest) | Muestra una pestaña oculta | spreadsheetId, sheetId, hidden=false | {sheetId, hidden: false} | spreadsheets | — | — |
| [ ] | `google_sheets.tabs.tab_color` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateSheetPropertiesRequest) | Establece el color de pestaña | spreadsheetId, sheetId, tabColor (RGB) | {sheetId, tabColor} | spreadsheets | — | — |
| [ ] | `google_sheets.sheets.copy_to` | create | POST /v4/spreadsheets/{spreadsheetId}/sheets/{sheetId}:copyTo | Copia una pestaña a otra hoja de cálculo | spreadsheetId, sheetId, destinationSpreadsheetId | {sheetId (en destino), title} | spreadsheets | E | — |

### Valores (Values) (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.read` | read | GET /v4/spreadsheets/{spreadsheetId}/values/{range} | Lee valores de un rango específico (A1 notation) | spreadsheetId, range, valueRenderOption | {range, majorDimension, values (matriz), spreadsheetId} | spreadsheets.readonly | — | read_sheet_range |
| [ ] | `google_sheets.ranges.batchget` | read | GET /v4/spreadsheets/{spreadsheetId}/values:batchGet | Lee múltiples rangos en una sola solicitud | spreadsheetId, ranges (array), valueRenderOption | {spreadsheetId, valueRanges: [{range, values, formattedValues}]} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.ranges.get_by_datafilter` | read | POST /v4/spreadsheets/{spreadsheetId}/values:batchGetByDataFilter | Lee rangos según filtros de datos | spreadsheetId, dataFilters, valueRenderOption | {spreadsheetId, valueRanges con datos filtrados} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.ranges.write` | update | PUT /v4/spreadsheets/{spreadsheetId}/values/{range} | Actualiza valores en un rango | spreadsheetId, range, values, valueInputOption | {spreadsheetId, updatedRange, updatedRows, updatedColumns, updatedCells} | spreadsheets | — | write_sheet_range |
| [ ] | `google_sheets.ranges.batchupdate` | update | POST /v4/spreadsheets/{spreadsheetId}/values:batchUpdate | Actualiza múltiples rangos atómicamente | spreadsheetId, data (array de ValueRange) | {spreadsheetId, responses (por rango actualizado)} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.update_by_datafilter` | update | POST /v4/spreadsheets/{spreadsheetId}/values:batchUpdateByDataFilter | Actualiza rangos que coinciden filtros de datos | spreadsheetId, dataFilters, values | {spreadsheetId, responses} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.append` | create | POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append | Añade nuevas filas o valores al final de una tabla | spreadsheetId, range, values, valueInputOption | {spreadsheetId, updatedRange, updatedRows, updatedColumns, updatedCells} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.clear` | delete | POST /v4/spreadsheets/{spreadsheetId}/values/{range}:clear | Limpia (borra) todos los valores en un rango | spreadsheetId, range | {spreadsheetId, clearedRange} | spreadsheets | I | clear_sheet_range |
| [ ] | `google_sheets.ranges.batchclear` | delete | POST /v4/spreadsheets/{spreadsheetId}/values:batchClear | Limpia múltiples rangos en una operación | spreadsheetId, ranges (array) | {spreadsheetId, clearedRanges (array)} | spreadsheets | I | — |
| [ ] | `google_sheets.ranges.batchclear_by_datafilter` | delete | POST /v4/spreadsheets/{spreadsheetId}/values:batchClearByDataFilter | Limpia rangos según filtros de datos | spreadsheetId, dataFilters | {spreadsheetId, clearedRanges} | spreadsheets | I | — |

### Celdas (Cells) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.cells.get` | read | GET /v4/spreadsheets/{spreadsheetId}/values/{range} | Obtiene valor de una celda específica (A1 notation) | spreadsheetId, cell (e.g., 'Sheet1!A1') | {range, values: [[cellValue]]} | spreadsheets.readonly | — | get_sheet_cell |
| [ ] | `google_sheets.cells.write` | update | PUT /v4/spreadsheets/{spreadsheetId}/values/{cell} | Escribe un valor en una celda | spreadsheetId, cell, value, valueInputOption | {spreadsheetId, updatedRange, updatedCells: 1} | spreadsheets | — | write_sheet_cell |
| [ ] | `google_sheets.cells.list_occupied` | read | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (FindReplaceRequest con búsqueda de regex) | Lista todas las celdas ocupadas (no vacías) en un rango | spreadsheetId, sheetId, searchPattern | celdas con valores encontradas | spreadsheets.readonly | — | get_sheet_occupied_cells |

### Filas (Rows) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.rows.count` | read | GET /v4/spreadsheets/{spreadsheetId}/values/{range} | Cuenta el número de filas con datos en un rango | spreadsheetId, range | {count: número de filas} | spreadsheets.readonly | — | count_sheet_rows |
| [ ] | `google_sheets.rows.get` | read | GET /v4/spreadsheets/{spreadsheetId}/values/{range} (especificando una fila) | Obtiene todos los valores de una fila específica | spreadsheetId, row (rango como 'Sheet1!2:2') | {range, values: [fila_valores]} | spreadsheets.readonly | — | get_sheet_row |
| [ ] | `google_sheets.rows.append` | create | POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append | Añade una nueva fila al final con valores | spreadsheetId, range, values (array con valores), valueInputOption | {updatedRange, updatedRows: 1, updatedColumns, updatedCells} | spreadsheets | — | append_sheet_row |
| [ ] | `google_sheets.rows.insert` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (InsertDimensionRequest) | Inserta una o más filas en posición específica | spreadsheetId, sheetId, insertRange {startIndex, endIndex} | {sheetId, filas insertadas en índices} | spreadsheets | — | — |
| [ ] | `google_sheets.rows.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteDimensionRequest) | Elimina una o más filas | spreadsheetId, sheetId, deleteRange {startIndex, endIndex} | {sheetId, filas eliminadas} | spreadsheets | I | — |

### Columnas (Columns) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.columns.get` | read | GET /v4/spreadsheets/{spreadsheetId}/values/{range} (especificando una columna) | Obtiene todos los valores de una columna | spreadsheetId, column (rango como 'Sheet1!A:A') | {range, values: [columna_valores]} | spreadsheets.readonly | — | get_sheet_column |
| [ ] | `google_sheets.columns.append` | create | POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append (o batchUpdate con InsertDimensionRequest) | Añade una nueva columna al final | spreadsheetId, range, values, valueInputOption | {updatedRange, updatedRows, updatedColumns: 1, updatedCells} | spreadsheets | — | append_sheet_column |
| [ ] | `google_sheets.columns.insert` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (InsertDimensionRequest) | Inserta una o más columnas en posición específica | spreadsheetId, sheetId, insertRange {startIndex, endIndex} | {sheetId, columnas insertadas} | spreadsheets | — | — |
| [ ] | `google_sheets.columns.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteDimensionRequest) | Elimina una o más columnas | spreadsheetId, sheetId, deleteRange {startIndex, endIndex} | {sheetId, columnas eliminadas} | spreadsheets | I | — |

### Búsqueda y Reemplazo (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.values.search` | read | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (FindReplaceRequest) | Busca valores o texto en rangos de la hoja | spreadsheetId, searchTerm, searchRange, matchCase | {occurrences: número, matchedCells: [{row, column, value}]} | spreadsheets.readonly | — | search_sheet_value |
| [ ] | `google_sheets.values.find_replace` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (FindReplaceRequest) | Busca un valor y lo reemplaza por otro | spreadsheetId, find, replacement, range, matchCase | {occurrences, matchedCells} | spreadsheets | — | — |

### Formatos y Estilos (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.format_cells` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (RepeatCellRequest) | Aplica formato a múltiples celdas (negrita, color, alineación) | spreadsheetId, range, format {bold, italic, backgroundColor, textFormat} | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.set_borders` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateBordersRequest) | Establece bordes en rangos de celdas | spreadsheetId, range, borders {style, width, color} | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.merge_cells` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (MergeCellsRequest) | Fusiona celdas en un rango | spreadsheetId, range | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.unmerge_cells` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UnmergeCellsRequest) | Desactiva la fusión de celdas | spreadsheetId, range | {} | spreadsheets | — | — |

### Datos y Validación (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.set_data_validation` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (SetDataValidationRequest) | Establece reglas de validación de datos en un rango | spreadsheetId, range, criteria {type, allowedValues, showDropdown} | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.clear_data_validation` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (SetDataValidationRequest con criteria vacío) | Elimina validación de datos de un rango | spreadsheetId, range | {} | spreadsheets | — | — |

### Formatos Condicionales (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.formatting.add_conditional_rule` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddConditionalFormatRuleRequest) | Añade una regla de formato condicional | spreadsheetId, ranges, condition {type, values}, format | {ruleId} | spreadsheets | — | — |
| [ ] | `google_sheets.formatting.update_conditional_rule` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateConditionalFormatRuleRequest) | Modifica una regla de formato condicional existente | spreadsheetId, ruleId, condition, format | {} | spreadsheets | — | — |
| [ ] | `google_sheets.formatting.delete_conditional_rule` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteConditionalFormatRuleRequest) | Elimina una regla de formato condicional | spreadsheetId, ruleId | {} | spreadsheets | — | — |

### Ordenamiento y Filtros (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.sort` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (SortRangeRequest) | Ordena un rango por columna(s) | spreadsheetId, range, sortSpecs {dimension, sortOrder} | {sortedRange} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.set_basic_filter` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (SetBasicFilterRequest) | Establece un filtro automático en un rango | spreadsheetId, range | {filterId} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.clear_basic_filter` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (SetBasicFilterRequest vacío) | Elimina filtro automático | spreadsheetId, range | {} | spreadsheets | — | — |
| [ ] | `google_sheets.filters.add_filter_view` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddFilterViewRequest) | Crea una vista de filtro guardada | spreadsheetId, range, title | {filterId, title} | spreadsheets | — | — |
| [ ] | `google_sheets.filters.update_filter_view` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateFilterViewRequest) | Modifica propiedades de una vista de filtro | spreadsheetId, filterId, range, criteria | {} | spreadsheets | — | — |
| [ ] | `google_sheets.filters.delete_filter_view` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteFilterViewRequest) | Elimina una vista de filtro | spreadsheetId, filterId | {} | spreadsheets | — | — |

### Tablas Dinámicas (Pivot Tables) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.pivot_tables.create` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddPivotTableRequest) | Crea una tabla dinámica/pivot | spreadsheetId, sourceRange, pivotTable {rows, columns, values} | {pivotTableId} | spreadsheets | — | — |
| [ ] | `google_sheets.pivot_tables.update` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdatePivotTableRequest) | Modifica una tabla dinámica existente | spreadsheetId, pivotTableId, pivotTable | {} | spreadsheets | — | — |
| [ ] | `google_sheets.pivot_tables.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeletePivotTableRequest) | Elimina una tabla dinámica | spreadsheetId, pivotTableId | {} | spreadsheets | — | — |

### Gráficos (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.charts.create` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddChartRequest) | Añade un gráfico a la hoja | spreadsheetId, chartSpec {type, series, title} | {chartId} | spreadsheets | — | — |
| [ ] | `google_sheets.charts.update` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateChartSpecRequest) | Modifica las propiedades de un gráfico | spreadsheetId, chartId, chartSpec | {} | spreadsheets | — | — |
| [ ] | `google_sheets.charts.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteChartRequest) | Elimina un gráfico | spreadsheetId, chartId | {} | spreadsheets | — | — |

### Rangos Nombrados (Named Ranges) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.add_named_range` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddNamedRangeRequest) | Crea un rango con nombre para referencia rápida | spreadsheetId, namedRange {name, range} | {namedRangeId} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.update_named_range` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateNamedRangeRequest) | Modifica propiedades de un rango nombrado | spreadsheetId, namedRangeId, namedRange | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.delete_named_range` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteNamedRangeRequest) | Elimina un rango nombrado | spreadsheetId, namedRangeId | {} | spreadsheets | — | — |

### Protección (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.protect` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AddProtectedRangeRequest) | Protege un rango contra ediciones | spreadsheetId, range, editors {users, groups}, description | {protectedRangeId} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.update_protection` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateProtectedRangeRequest) | Modifica configuración de protección | spreadsheetId, protectedRangeId, protectedRange | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.unprotect` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteProtectedRangeRequest) | Elimina protección de un rango | spreadsheetId, protectedRangeId | {} | spreadsheets | — | — |
| [ ] | `google_sheets.spreadsheets.protect_sheet` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateSheetPropertiesRequest) | Protege la hoja completa | spreadsheetId, sheetId, protectedSheetProperties | {} | spreadsheets | — | — |

### Copiar y Pegar (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.copy_paste` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (CopyPasteRequest) | Copia celdas de un rango y pega en otro | spreadsheetId, source {range}, destination {rowIndex, columnIndex}, pasteType | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.cut_paste` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (CutPasteRequest) | Corta celdas de un rango y pega en otro | spreadsheetId, source {range}, destination {rowIndex, columnIndex}, pasteType | {} | spreadsheets | — | — |

### Utilidades (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.ranges.delete_duplicates` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteDuplicatesRequest) | Elimina filas duplicadas en un rango | spreadsheetId, range, columnIndexes | {duplicatesRemovedCount} | spreadsheets | — | — |
| [ ] | `google_sheets.spreadsheets.append_cells` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (AppendCellsRequest) | Añade celdas al final de una hoja | spreadsheetId, sheetId, data {rows con valores} | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.insert_range` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (InsertRangeRequest) | Inserta celdas en un rango y desplaza otras | spreadsheetId, range, shiftDimension | {} | spreadsheets | — | — |
| [ ] | `google_sheets.ranges.delete_range` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteRangeRequest) | Elimina un rango de celdas y desplaza otras | spreadsheetId, range, shiftDimension | {} | spreadsheets | I | — |

### Metadata del Desarrollador (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `google_sheets.metadata.get` | read | GET /v4/spreadsheets/{spreadsheetId}/developerMetadata/{metadataId} | Obtiene metadatos de desarrollador asignados a la hoja | spreadsheetId, metadataId | {metadataId, metadataKey, metadataValue, location} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.metadata.search` | read | POST /v4/spreadsheets/{spreadsheetId}/developerMetadata:search | Busca metadatos de desarrollador según criterios | spreadsheetId, metadataFilter {metadataKey, visibility} | {results: [{metadataId, metadataKey, metadataValue}]} | spreadsheets.readonly | — | — |
| [ ] | `google_sheets.metadata.create` | create | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (CreateDeveloperMetadataRequest) | Crea metadatos de desarrollador en la hoja | spreadsheetId, metadataKey, metadataValue, location | {metadataId} | spreadsheets | — | — |
| [ ] | `google_sheets.metadata.update` | update | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (UpdateDeveloperMetadataRequest) | Modifica metadatos de desarrollador | spreadsheetId, metadataId, metadataValue | {} | spreadsheets | — | — |
| [ ] | `google_sheets.metadata.delete` | delete | POST /v4/spreadsheets/{spreadsheetId}:batchUpdate (DeleteDeveloperMetadataRequest) | Elimina metadatos de desarrollador | spreadsheetId, metadataId | {} | spreadsheets | — | — |

## Observaciones de las herramientas viejas

- `BIGTOOLS_REGISTRY` lista 15 de las 17 (faltan `get_sheet_occupied_cells` y `duplicate_sheet_tab`).
- `get_sheet_cell`, `get_sheet_row`, `get_sheet_column` y `read_sheet_range` son lecturas de rango con forma distinta; la unificacion es decision del lider.
- `clear_sheet_range` borra datos: `verb=delete`.
