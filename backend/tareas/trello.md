# Tareas: Trello

- **Funciones catalogadas:** 250 · **Hechas:** 0 · **Pendientes:** 250 · App sin herramientas viejas
- **Documentación oficial:** https://developer.atlassian.com/cloud/trello/rest/
- **Fuentes que consultó el catálogo:** https://developer.atlassian.com/cloud/trello/rest/ https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization https://developer.atlassian.com/cloud/trello/guides/rest-api/rate-limits/
- **Paginación típica:** limit y offset en query params; algunos endpoints devuelven limite implícito
- **Qué no se pudo verificar:** nada
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/trello/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `trello`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `trello` |
| Variables del `.env` que necesitas | TRELLO_API_KEY, TRELLO_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/trello/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `trello.member.whoami` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con Authorization Code Grant; API key (público, obtenido en https://trello.com/app-key) + token de usuario (generado con response_type=token, puede ser never expiration) |
| Duración del token (según el catálogo) | Configurable: 1 hour, 1 day, 30 days, o never (sin expiración); OAuth2: access token 1 hora, refresh token 30 días |
| Refresco (según el catálogo) | OAuth2 con refresh token; tokens tradicionales: sin refresh, revienta a expiración configurada |
| Permisos (según el catálogo) | read:board:trello (lectura tableros), write:board:trello (escritura tableros), account (emails), read:organization:trello, write:organization:trello, write:member:trello (modificar notificaciones) |
| Restricciones de acceso | API key + token por query/header/body; OAuth2 apps ≠ Forge apps; endpoints /members, /membersSearch, /search tienen límites especiales |
| Límites de ritmo | 300 req/10s por API key, 100 req/10s por token, 100 req/900s para /members/*; usa webhooks en lugar de polling |
| Notas de esta app | La clave de la app es del servidor; el token es del usuario y se guarda con `POST /api/v1/integrations/trello/token`. **Brecha:** el modo `custom_params` (varios campos) pide `credentials_enc` y nada lo escribe todavía: consúltalo con el líder antes de la primera función. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/trello/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> trello`. | Cuenta con `provider: trello`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/trello.member.whoami/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> trello <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Trello. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/trello.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Cuenta del usuario (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.member.whoami` ★ | read | GET /members/me | Obtener identidad y datos del usuario conectado | ninguno | {id, username, fullName, email, initials, avatarUrl} | account | — | — |

### Tableros (Boards) (42)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.board.list` | read | GET /members/me/boards | Listar todos los tableros del usuario | filter (open, closed, all) | lista de {id, name, closed, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.board.get` | read | GET /boards/{id} | Obtener datos completos de un tablero | id | {id, name, desc, closed, idOrganization, members, prefs} | read:board:trello | — | — |
| [ ] | `trello.board.create` | create | POST /boards | Crear un nuevo tablero | name, idOrganization, defaultLabels, defaultLists | {id, name, desc, closed, idOrganization} | write:board:trello | — | — |
| [ ] | `trello.board.update` | update | PUT /boards/{id} | Actualizar propiedades de un tablero | id, name, desc, closed, idOrganization, prefs | {id, name, desc, closed, idOrganization} | write:board:trello | — | — |
| [ ] | `trello.board.delete` | delete | DELETE /boards/{id} | Eliminar un tablero | id | — | write:board:trello | I | — |
| [ ] | `trello.board.get_field` | read | GET /boards/{id}/{field} | Obtener un campo específico del tablero | id, field (name, desc, closed, etc.) | valor del campo | read:board:trello | — | — |
| [ ] | `trello.board.list_actions` | read | GET /boards/{id}/actions | Listar todas las acciones en un tablero | id, limit, filter | lista de {id, type, date, memberCreator} | read:board:trello | — | — |
| [ ] | `trello.board.list_board_stars` | read | GET /boards/{id}/boardStars | Obtener estrellas otorgadas al tablero | id | lista de {id, idMember, pos, idBoard} | read:board:trello | — | — |
| [ ] | `trello.board.list_checklists` | read | GET /boards/{id}/checklists | Listar todos los checklists del tablero | id | lista de {id, name, cards} | read:board:trello | — | — |
| [ ] | `trello.board.list_cards` | read | GET /boards/{id}/cards | Listar todas las tarjetas del tablero | id, filter (open, closed, visible, all) | lista de {id, name, idList, closed, due} | read:board:trello | — | — |
| [ ] | `trello.board.list_cards_filtered` | read | GET /boards/{id}/cards/{filter} | Listar tarjetas con filtro específico | id, filter | lista de tarjetas filtradas | read:board:trello | — | — |
| [ ] | `trello.board.list_custom_fields` | read | GET /boards/{id}/customFields | Listar campos personalizados del tablero | id | lista de {id, name, type, options} | read:board:trello | — | — |
| [ ] | `trello.board.list_labels` | read | GET /boards/{id}/labels | Listar etiquetas del tablero | id | lista de {id, name, color} | read:board:trello | — | — |
| [ ] | `trello.board.create_label` | create | POST /boards/{id}/labels | Crear nueva etiqueta en el tablero | id, name, color | {id, name, color, idBoard} | write:board:trello | — | — |
| [ ] | `trello.board.list_lists` | read | GET /boards/{id}/lists | Listar las listas del tablero | id, filter (open, closed, all) | lista de {id, name, closed, pos} | read:board:trello | — | — |
| [ ] | `trello.board.create_list` | create | POST /boards/{id}/lists | Crear nueva lista en el tablero | id, name, pos, idListSource | {id, name, closed, pos, idBoard} | write:board:trello | — | — |
| [ ] | `trello.board.list_lists_filtered` | read | GET /boards/{id}/lists/{filter} | Listar listas con filtro | id, filter | lista de listas filtradas | read:board:trello | — | — |
| [ ] | `trello.board.list_members` | read | GET /boards/{id}/members | Listar miembros del tablero | id, filter | lista de {id, username, fullName, avatar} | read:board:trello | — | — |
| [ ] | `trello.board.add_member_email` | create | PUT /boards/{id}/members | Invitar miembro por email | id, email | miembro añadido | write:board:trello | E | — |
| [ ] | `trello.board.add_member` | create | PUT /boards/{id}/members/{idMember} | Añadir miembro existente al tablero | id, idMember, type (normal, admin, observer) | miembro añadido | write:board:trello | E | — |
| [ ] | `trello.board.remove_member` | delete | DELETE /boards/{id}/members/{idMember} | Remover miembro del tablero | id, idMember | — | write:board:trello | — | — |
| [ ] | `trello.board.update_membership` | update | PUT /boards/{id}/memberships/{idMembership} | Actualizar permisos de membresía | id, idMembership, type, memberType, deactivated | membresía actualizada | write:board:trello | — | — |
| [ ] | `trello.board.list_memberships` | read | GET /boards/{id}/memberships | Obtener información de membresías | id | lista de {id, idMember, memberType, deactivated} | read:board:trello | — | — |
| [ ] | `trello.board.set_email_position` | update | PUT /boards/{id}/myPrefs/emailPosition | Configurar posición de notificaciones email | id, emailPosition (top, bottom) | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.set_email_list` | update | PUT /boards/{id}/myPrefs/idEmailList | Configurar lista para emails de tarjetas | id, idEmailList | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.set_sidebar_visibility` | update | PUT /boards/{id}/myPrefs/showSidebar | Mostrar u ocultar barra lateral | id, showSidebar (true/false) | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.set_sidebar_activity` | update | PUT /boards/{id}/myPrefs/showSidebarActivity | Control visibilidad actividad en sidebar | id, showSidebarActivity | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.set_sidebar_board_actions` | update | PUT /boards/{id}/myPrefs/showSidebarBoardActions | Control visibilidad acciones tablero en sidebar | id, showSidebarBoardActions | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.set_sidebar_members` | update | PUT /boards/{id}/myPrefs/showSidebarMembers | Mostrar u ocultar lista de miembros | id, showSidebarMembers | preferencia actualizada | write:board:trello | — | — |
| [ ] | `trello.board.list_board_plugins` | read | GET /boards/{id}/boardPlugins | Listar power-ups habilitados | id | lista de {id, idPlugin} | read:board:trello | — | — |
| [ ] | `trello.board.enable_plugin` | create | POST /boards/{id}/boardPlugins | Activar un power-up | id, idPlugin | power-up activado | write:board:trello | — | — |
| [ ] | `trello.board.disable_plugin` | delete | DELETE /boards/{id}/boardPlugins/{idPlugin} | Desactivar un power-up | id, idPlugin | — | write:board:trello | — | — |
| [ ] | `trello.board.list_plugins` | read | GET /boards/{id}/plugins | Listar power-ups disponibles para el tablero | id | lista de power-ups disponibles | read:board:trello | — | — |
| [ ] | `trello.board.export_create` | create | POST /boards/{id}/exports | Iniciar exportación del tablero | id, format (csv, json), attachments | {id, status, progress} | write:board:trello | — | — |
| [ ] | `trello.board.export_get` | read | GET /boards/{id}/exports/{idExport} | Obtener estado de exportación | id, idExport | {id, status, progress, download} | read:board:trello | — | — |
| [ ] | `trello.board.export_cancel` | delete | DELETE /boards/{id}/exports/{idExport} | Cancelar una exportación | id, idExport | — | write:board:trello | — | — |
| [ ] | `trello.board.export_download` | read | GET /boards/{id}/exports/{idExport}/download | Descargar datos exportados | id, idExport | archivo descargable | read:board:trello | — | — |
| [ ] | `trello.board.export_most_recent` | read | GET /boards/{id}/exports/mostRecent | Obtener exportación más reciente | id | {id, status, download} | read:board:trello | — | — |
| [ ] | `trello.board.generate_calendar_key` | create | POST /boards/{id}/calendarKey/generate | Generar clave para integración de calendario | id | {calendarKey} | write:board:trello | — | — |
| [ ] | `trello.board.generate_email_key` | create | POST /boards/{id}/emailKey/generate | Crear clave para integración por email | id | {emailKey} | write:board:trello | — | — |
| [ ] | `trello.board.add_tag` | create | POST /boards/{id}/idTags | Añadir etiqueta al tablero | id, tag | etiqueta añadida | write:board:trello | — | — |
| [ ] | `trello.board.mark_viewed` | create | POST /boards/{id}/markAsViewed | Marcar tablero como visto recientemente | id | — | write:board:trello | — | — |

### Tarjetas (Cards) (41)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.card.create` | create | POST /cards | Crear nueva tarjeta | name, idList, desc, due, idMembers, idLabels | {id, name, idList, closed, due, pos} | write:board:trello | — | — |
| [ ] | `trello.card.get` | read | GET /cards/{id} | Obtener datos completos de una tarjeta | id | {id, name, desc, closed, due, idList, idMembers, idLabels, attachments} | read:board:trello | — | — |
| [ ] | `trello.card.update` | update | PUT /cards/{id} | Actualizar propiedades de una tarjeta | id, name, desc, closed, due, idList, pos | tarjeta actualizada | write:board:trello | — | — |
| [ ] | `trello.card.delete` | delete | DELETE /cards/{id} | Eliminar una tarjeta | id | — | write:board:trello | I | — |
| [ ] | `trello.card.get_field` | read | GET /cards/{id}/{field} | Obtener campo específico de la tarjeta | id, field (name, desc, due, etc.) | valor del campo | read:board:trello | — | — |
| [ ] | `trello.card.list_actions` | read | GET /cards/{id}/actions | Listar acciones en la tarjeta | id, filter, limit | lista de {id, type, date, memberCreator} | read:board:trello | — | — |
| [ ] | `trello.card.list_attachments` | read | GET /cards/{id}/attachments | Listar archivos adjuntos | id | lista de {id, name, url, bytes, date} | read:board:trello | — | — |
| [ ] | `trello.card.add_attachment` | create | POST /cards/{id}/attachments | Adjuntar archivo | id, file, url, name | {id, name, url} | write:board:trello | — | — |
| [ ] | `trello.card.get_attachment` | read | GET /cards/{id}/attachments/{idAttachment} | Obtener datos del adjunto | id, idAttachment | {id, name, url, bytes, date} | read:board:trello | — | — |
| [ ] | `trello.card.delete_attachment` | delete | DELETE /cards/{id}/attachments/{idAttachment} | Remover adjunto | id, idAttachment | — | write:board:trello | — | — |
| [ ] | `trello.card.get_board` | read | GET /cards/{id}/board | Obtener tablero padre | id | {id, name, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.card.list_check_item_states` | read | GET /cards/{id}/checkItemStates | Listar estados de items de checklist | id | lista de {idCheckItem, state} | read:board:trello | — | — |
| [ ] | `trello.card.list_checklists` | read | GET /cards/{id}/checklists | Listar checklists de la tarjeta | id | lista de {id, name, items} | read:board:trello | — | — |
| [ ] | `trello.card.create_checklist` | create | POST /cards/{id}/checklists | Crear nuevo checklist en la tarjeta | id, name, idChecklistSource | {id, name, items, pos} | write:board:trello | — | — |
| [ ] | `trello.card.get_check_item` | read | GET /cards/{id}/checkItem/{idCheckItem} | Obtener item específico del checklist | id, idCheckItem | {id, name, state, pos} | read:board:trello | — | — |
| [ ] | `trello.card.update_check_item` | update | PUT /cards/{id}/checkItem/{idCheckItem} | Actualizar item del checklist | id, idCheckItem, name, state (complete/incomplete, pos) | item actualizado | write:board:trello | — | — |
| [ ] | `trello.card.delete_check_item` | delete | DELETE /cards/{id}/checkItem/{idCheckItem} | Eliminar item del checklist | id, idCheckItem | — | write:board:trello | — | — |
| [ ] | `trello.card.get_list` | read | GET /cards/{id}/list | Obtener lista padre | id | {id, name, closed, idBoard} | read:board:trello | — | — |
| [ ] | `trello.card.list_members` | read | GET /cards/{id}/members | Listar miembros asignados | id | lista de {id, username, fullName, avatar} | read:board:trello | — | — |
| [ ] | `trello.card.list_voted_members` | read | GET /cards/{id}/membersVoted | Listar miembros que votaron | id | lista de {id, username, fullName} | read:board:trello | — | — |
| [ ] | `trello.card.add_vote` | create | POST /cards/{id}/membersVoted | Añadir voto del miembro actual | id | — | write:board:trello | — | — |
| [ ] | `trello.card.remove_vote` | delete | DELETE /cards/{id}/membersVoted/{idMember} | Remover voto | id, idMember | — | write:board:trello | — | — |
| [ ] | `trello.card.get_plugin_data` | read | GET /cards/{id}/pluginData | Obtener datos de plugin | id | plugin data | read:board:trello | — | — |
| [ ] | `trello.card.list_stickers` | read | GET /cards/{id}/stickers | Listar stickers | id | lista de {id, image, top, left, zIndex} | read:board:trello | — | — |
| [ ] | `trello.card.add_sticker` | create | POST /cards/{id}/stickers | Añadir sticker | id, image, top, left, zIndex, rotate | {id, image, pos} | write:board:trello | — | — |
| [ ] | `trello.card.get_sticker` | read | GET /cards/{id}/stickers/{idSticker} | Obtener sticker específico | id, idSticker | {id, image, top, left, zIndex} | read:board:trello | — | — |
| [ ] | `trello.card.update_sticker` | update | PUT /cards/{id}/stickers/{idSticker} | Actualizar posición/rotación de sticker | id, idSticker, top, left, rotate, zIndex | sticker actualizado | write:board:trello | — | — |
| [ ] | `trello.card.delete_sticker` | delete | DELETE /cards/{id}/stickers/{idSticker} | Remover sticker | id, idSticker | — | write:board:trello | — | — |
| [ ] | `trello.card.add_comment` | create | POST /cards/{id}/actions/comments | Añadir comentario | id, text | {id, type, date, memberCreator, data} | write:board:trello | E | — |
| [ ] | `trello.card.update_comment` | update | PUT /cards/{id}/actions/{idAction}/comments | Editar comentario | id, idAction, text | comentario actualizado | write:board:trello | — | — |
| [ ] | `trello.card.delete_comment` | delete | DELETE /cards/{id}/actions/{idAction}/comments | Eliminar comentario | id, idAction | — | write:board:trello | — | — |
| [ ] | `trello.card.list_custom_field_items` | read | GET /cards/{id}/customFieldItems | Listar valores de campos personalizados | id | lista de {idCustomField, value} | read:board:trello | — | — |
| [ ] | `trello.card.update_custom_field` | update | PUT /cards/{idCard}/customField/{idCustomField}/item | Actualizar valor de campo personalizado | idCard, idCustomField, value | campo actualizado | write:board:trello | — | — |
| [ ] | `trello.card.update_custom_fields` | update | PUT /cards/{idCard}/customFields | Actualizar múltiples campos personalizados | idCard, campos y valores | campos actualizados | write:board:trello | — | — |
| [ ] | `trello.card.add_label` | create | POST /cards/{id}/idLabels | Asignar etiqueta existente | id, idLabel | etiqueta añadida | write:board:trello | — | — |
| [ ] | `trello.card.create_and_add_label` | create | POST /cards/{id}/labels | Crear y asignar nueva etiqueta | id, color, name | {id, name, color} | write:board:trello | — | — |
| [ ] | `trello.card.remove_label` | delete | DELETE /cards/{id}/idLabels/{idLabel} | Remover etiqueta | id, idLabel | — | write:board:trello | — | — |
| [ ] | `trello.card.add_member` | create | POST /cards/{id}/idMembers | Asignar miembro | id, idMember | {id, username, fullName} | write:board:trello | E | — |
| [ ] | `trello.card.remove_member` | delete | DELETE /cards/{id}/idMembers/{idMember} | Desasignar miembro | id, idMember | — | write:board:trello | — | — |
| [ ] | `trello.card.mark_notifications_read` | create | POST /cards/{id}/markAssociatedNotificationsRead | Marcar notificaciones como leídas | id | — | write:member:trello | — | — |
| [ ] | `trello.card.delete_checklist` | delete | DELETE /cards/{id}/checklists/{idChecklist} | Eliminar checklist completo | id, idChecklist | — | write:board:trello | — | — |

### Listas (Lists) (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.list.get` | read | GET /lists/{id} | Obtener información de una lista | id | {id, name, closed, pos, idBoard} | read:board:trello | — | — |
| [ ] | `trello.list.update` | update | PUT /lists/{id} | Actualizar propiedades de lista | id, name, closed, pos, idBoard | lista actualizada | write:board:trello | — | — |
| [ ] | `trello.list.create` | create | POST /lists | Crear nueva lista | name, idBoard, pos, idListSource | {id, name, closed, pos, idBoard} | write:board:trello | — | — |
| [ ] | `trello.list.update_field` | update | PUT /lists/{id}/{field} | Actualizar campo específico | id, field, value | campo actualizado | write:board:trello | — | — |
| [ ] | `trello.list.archive_all_cards` | create | POST /lists/{id}/archiveAllCards | Archivar todas las tarjetas | id | — | write:board:trello | — | — |
| [ ] | `trello.list.move_all_cards` | create | POST /lists/{id}/moveAllCards | Mover todas las tarjetas a otra lista | id, idBoard, idList | tarjetas movidas | write:board:trello | — | — |
| [ ] | `trello.list.set_closed` | update | PUT /lists/{id}/closed | Archivar o restaurar lista | id, closed (true/false) | lista actualizada | write:board:trello | — | — |
| [ ] | `trello.list.set_board` | update | PUT /lists/{id}/idBoard | Mover lista a otro tablero | id, idBoard | lista movida | write:board:trello | — | — |
| [ ] | `trello.list.list_actions` | read | GET /lists/{id}/actions | Listar acciones en la lista | id, limit, filter | lista de acciones | read:board:trello | — | — |
| [ ] | `trello.list.get_board` | read | GET /lists/{id}/board | Obtener tablero padre | id | {id, name, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.list.list_cards` | read | GET /lists/{id}/cards | Listar tarjetas de la lista | id, filter | lista de tarjetas | read:board:trello | — | — |

### Acciones (Actions) (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.action.get` | read | GET /actions/{id} | Obtener información de una acción | id | {id, type, date, memberCreator, data} | read:board:trello | — | — |
| [ ] | `trello.action.update` | update | PUT /actions/{id} | Actualizar acción (solo comentarios) | id, text | acción actualizada | write:board:trello | — | — |
| [ ] | `trello.action.delete` | delete | DELETE /actions/{id} | Eliminar acción (solo comentarios) | id | — | write:board:trello | I | — |
| [ ] | `trello.action.get_field` | read | GET /actions/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:board:trello | — | — |
| [ ] | `trello.action.get_board` | read | GET /actions/{id}/board | Obtener tablero asociado | id | {id, name, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.action.get_card` | read | GET /actions/{id}/card | Obtener tarjeta asociada | id | {id, name, idList} | read:board:trello | — | — |
| [ ] | `trello.action.get_list` | read | GET /actions/{id}/list | Obtener lista asociada | id | {id, name, closed} | read:board:trello | — | — |
| [ ] | `trello.action.get_member` | read | GET /actions/{id}/member | Obtener miembro (no creador) | id | {id, username, fullName} | read:board:trello | — | — |
| [ ] | `trello.action.get_member_creator` | read | GET /actions/{id}/memberCreator | Obtener miembro que creó | id | {id, username, fullName} | read:board:trello | — | — |
| [ ] | `trello.action.get_organization` | read | GET /actions/{id}/organization | Obtener organización asociada | id | {id, name} | read:board:trello | — | — |
| [ ] | `trello.action.update_comment_text` | update | PUT /actions/{id}/text | Actualizar texto de comentario | id, text | comentario actualizado | write:board:trello | — | — |
| [ ] | `trello.action.list_reactions` | read | GET /actions/{idAction}/reactions | Listar reacciones en una acción | idAction | lista de {id, idMember, emoji} | read:board:trello | — | — |
| [ ] | `trello.action.add_reaction` | create | POST /actions/{idAction}/reactions | Añadir reacción | idAction, emoji | {id, idMember, emoji} | write:board:trello | — | — |
| [ ] | `trello.action.get_reaction` | read | GET /actions/{idAction}/reactions/{id} | Obtener reacción específica | idAction, id | {id, idMember, emoji} | read:board:trello | — | — |
| [ ] | `trello.action.delete_reaction` | delete | DELETE /actions/{idAction}/reactions/{id} | Remover reacción | idAction, id | — | write:board:trello | — | — |
| [ ] | `trello.action.list_reactions_summary` | read | GET /actions/{idAction}/reactionsSummary | Obtener resumen de reacciones | idAction | resumen de reacciones por emoji | read:board:trello | — | — |

### Organizaciones (29)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.organization.create` | create | POST /organizations | Crear nueva organización | name, displayName, desc, website | {id, name, displayName, website} | write:organization:trello | — | — |
| [ ] | `trello.organization.get` | read | GET /organizations/{id} | Obtener datos de organización | id | {id, name, displayName, desc, website, members} | read:organization:trello | — | — |
| [ ] | `trello.organization.update` | update | PUT /organizations/{id} | Actualizar propiedades | id, name, displayName, desc, website, prefs | organización actualizada | write:organization:trello | — | — |
| [ ] | `trello.organization.delete` | delete | DELETE /organizations/{id} | Eliminar organización | id | — | write:organization:trello | I | — |
| [ ] | `trello.organization.get_field` | read | GET /organizations/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:organization:trello | — | — |
| [ ] | `trello.organization.list_actions` | read | GET /organizations/{id}/actions | Listar acciones de la organización | id, limit, filter | lista de acciones | read:organization:trello | — | — |
| [ ] | `trello.organization.list_boards` | read | GET /organizations/{id}/boards | Listar tableros de la organización | id, filter | lista de tableros | read:organization:trello | — | — |
| [ ] | `trello.organization.list_exports` | read | GET /organizations/{id}/exports | Listar exportaciones | id | lista de {id, status} | read:organization:trello | — | — |
| [ ] | `trello.organization.create_export` | create | POST /organizations/{id}/exports | Crear exportación de organización | id, format, attachments | {id, status, progress} | write:organization:trello | — | — |
| [ ] | `trello.organization.list_members` | read | GET /organizations/{id}/members | Listar miembros de la organización | id, filter | lista de miembros | read:organization:trello | — | — |
| [ ] | `trello.organization.update_members` | update | PUT /organizations/{id}/members | Actualizar miembros (invitar/remover) | id, idMembers | miembros actualizados | write:organization:trello | E | — |
| [ ] | `trello.organization.list_memberships` | read | GET /organizations/{id}/memberships | Listar membresías | id | lista de membresías | read:organization:trello | — | — |
| [ ] | `trello.organization.get_membership` | read | GET /organizations/{id}/memberships/{idMembership} | Obtener membresía específica | id, idMembership | {id, idMember, memberType} | read:organization:trello | — | — |
| [ ] | `trello.organization.get_plugin_data` | read | GET /organizations/{id}/pluginData | Obtener datos de plugin | id | plugin data | read:organization:trello | — | — |
| [ ] | `trello.organization.list_tags` | read | GET /organizations/{id}/tags | Listar etiquetas de la organización | id | lista de etiquetas | read:organization:trello | — | — |
| [ ] | `trello.organization.create_tag` | create | POST /organizations/{id}/tags | Crear etiqueta en organización | id, name | {id, name} | write:organization:trello | — | — |
| [ ] | `trello.organization.update_member` | update | PUT /organizations/{id}/members/{idMember} | Actualizar miembro específico | id, idMember, fullName, email | miembro actualizado | write:organization:trello | — | — |
| [ ] | `trello.organization.remove_member` | delete | DELETE /organizations/{id}/members/{idMember} | Remover miembro | id, idMember | — | write:organization:trello | — | — |
| [ ] | `trello.organization.remove_member_all_boards` | delete | DELETE /organizations/{id}/members/{idMember}/all | Remover de org y todos sus tableros | id, idMember | — | write:organization:trello | I | — |
| [ ] | `trello.organization.set_member_deactivated` | update | PUT /organizations/{id}/members/{idMember}/deactivated | Desactivar o reactivar miembro | id, idMember, deactivated | miembro actualizado | write:organization:trello | — | — |
| [ ] | `trello.organization.set_admin` | create | PUT /organizations/{id}/admins/{idMember} | Asignar rol de administrador | id, idMember | miembro promocionado | write:organization:trello | — | — |
| [ ] | `trello.organization.update_logo` | update | POST /organizations/{id}/logo | Actualizar logo | id, file | logo actualizado | write:organization:trello | — | — |
| [ ] | `trello.organization.delete_logo` | delete | DELETE /organizations/{id}/logo | Eliminar logo | id | — | write:organization:trello | — | — |
| [ ] | `trello.organization.delete_tag` | delete | DELETE /organizations/{id}/tags/{idTag} | Eliminar etiqueta | id, idTag | — | write:organization:trello | — | — |
| [ ] | `trello.organization.get_new_billable_guests` | read | GET /organizations/{id}/newBillableGuests/{idBoard} | Obtener nuevos invitados facturables | id, idBoard | lista de invitados | read:organization:trello | — | — |
| [ ] | `trello.organization.remove_associated_domain` | delete | DELETE /organizations/{id}/prefs/associatedDomain | Remover dominio Google Apps | id | — | write:organization:trello | — | — |
| [ ] | `trello.organization.remove_invite_restriction` | delete | DELETE /organizations/{id}/prefs/orgInviteRestrict | Eliminar restricción de dominio | id | — | write:organization:trello | — | — |
| [ ] | `trello.organization.list_claimable_orgs` | read | GET /organizations/{id}/claimableOrganizations | Listar organizaciones reclamables | id | lista de org | read:organization:trello | — | — |
| [ ] | `trello.organization.list_pending_orgs` | read | GET /organizations/{id}/pendingOrganizations | Listar organizaciones pendientes | id | lista de org | read:organization:trello | — | — |

### Checklists (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.checklist.create` | create | POST /checklists | Crear nuevo checklist | name, idCard, pos | {id, name, items, pos} | write:board:trello | — | — |
| [ ] | `trello.checklist.get` | read | GET /checklists/{id} | Obtener datos del checklist | id | {id, name, items, idCard, pos} | read:board:trello | — | — |
| [ ] | `trello.checklist.update` | update | PUT /checklists/{id} | Actualizar checklist | id, name, pos | checklist actualizado | write:board:trello | — | — |
| [ ] | `trello.checklist.delete` | delete | DELETE /checklists/{id} | Eliminar checklist | id | — | write:board:trello | I | — |
| [ ] | `trello.checklist.get_field` | read | GET /checklists/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:board:trello | — | — |
| [ ] | `trello.checklist.update_field` | update | PUT /checklists/{id}/{field} | Actualizar campo específico | id, field, value | campo actualizado | write:board:trello | — | — |
| [ ] | `trello.checklist.get_board` | read | GET /checklists/{id}/board | Obtener tablero asociado | id | {id, name, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.checklist.get_card` | read | GET /checklists/{id}/cards | Obtener tarjeta asociada | id | {id, name, idList} | read:board:trello | — | — |
| [ ] | `trello.checklist.list_check_items` | read | GET /checklists/{id}/checkItems | Listar items del checklist | id | lista de {id, name, state, pos} | read:board:trello | — | — |
| [ ] | `trello.checklist.create_check_item` | create | POST /checklists/{id}/checkItems | Crear item en checklist | id, name, pos, checked | {id, name, state, pos} | write:board:trello | — | — |
| [ ] | `trello.checklist.get_check_item` | read | GET /checklists/{id}/checkItems/{idCheckItem} | Obtener item específico | id, idCheckItem | {id, name, state, pos} | read:board:trello | — | — |
| [ ] | `trello.checklist.delete_check_item` | delete | DELETE /checklists/{id}/checkItems/{idCheckItem} | Eliminar item | id, idCheckItem | — | write:board:trello | — | — |

### Campos Personalizados (CustomFields) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.custom_field.create` | create | POST /customFields | Crear nuevo campo personalizado | name, type, idModel, pos, options | {id, name, type, idModel, pos} | write:board:trello | — | — |
| [ ] | `trello.custom_field.get` | read | GET /customFields/{id} | Obtener datos del campo | id | {id, name, type, idModel, options} | read:board:trello | — | — |
| [ ] | `trello.custom_field.update` | update | PUT /customFields/{id} | Actualizar campo personalizado | id, name, pos, options | campo actualizado | write:board:trello | — | — |
| [ ] | `trello.custom_field.delete` | delete | DELETE /customFields/{id} | Eliminar campo personalizado | id | — | write:board:trello | I | — |
| [ ] | `trello.custom_field.list_options` | read | GET /customFields/{id}/options | Listar opciones (dropdown) | id | lista de {id, value, color, pos} | read:board:trello | — | — |
| [ ] | `trello.custom_field.add_option` | create | POST /customFields/{id}/options | Añadir opción a dropdown | id, value, color, pos | {id, value, color, pos} | write:board:trello | — | — |
| [ ] | `trello.custom_field.get_option` | read | GET /customFields/{id}/options/{idCustomFieldOption} | Obtener opción específica | id, idCustomFieldOption | {id, value, color, pos} | read:board:trello | — | — |
| [ ] | `trello.custom_field.delete_option` | delete | DELETE /customFields/{id}/options/{idCustomFieldOption} | Eliminar opción | id, idCustomFieldOption | — | write:board:trello | — | — |

### Etiquetas (Labels) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.label.get` | read | GET /labels/{id} | Obtener datos de etiqueta | id | {id, name, color, idBoard} | read:board:trello | — | — |
| [ ] | `trello.label.update` | update | PUT /labels/{id} | Actualizar etiqueta | id, name, color, idBoard | etiqueta actualizada | write:board:trello | — | — |
| [ ] | `trello.label.delete` | delete | DELETE /labels/{id} | Eliminar etiqueta | id | — | write:board:trello | I | — |
| [ ] | `trello.label.update_field` | update | PUT /labels/{id}/{field} | Actualizar campo específico | id, field, value | campo actualizado | write:board:trello | — | — |
| [ ] | `trello.label.create` | create | POST /labels | Crear nueva etiqueta | name, color, idBoard | {id, name, color, idBoard} | write:board:trello | — | — |

### Webhooks (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.webhook.create` | create | POST /webhooks | Crear nuevo webhook | callbackURL, idModel, description, active | {id, callbackURL, idModel, active} | write:board:trello | — | — |
| [ ] | `trello.webhook.get` | read | GET /webhooks/{id} | Obtener datos de webhook | id | {id, callbackURL, idModel, active, description} | read:board:trello | — | — |
| [ ] | `trello.webhook.update` | update | PUT /webhooks/{id} | Actualizar webhook | id, callbackURL, idModel, description, active | webhook actualizado | write:board:trello | — | — |
| [ ] | `trello.webhook.delete` | delete | DELETE /webhooks/{id} | Eliminar webhook | id | — | write:board:trello | — | — |
| [ ] | `trello.webhook.get_field` | read | GET /webhooks/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:board:trello | — | — |

### Búsqueda (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.search.query` | read | GET /search | Buscar en Trello | query, idBoards, modelTypes, cards_limit, boards_limit, organizations_limit, members_limit | lista de {boards, cards, organizations, members} | read:board:trello | — | — |
| [ ] | `trello.search.members` | read | GET /search/members | Buscar miembros | query, limit, idBoard, onlyOrgMembers | lista de {id, username, fullName, avatar} | read:board:trello | — | — |

### Miembros (Members) (32)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.member.get` | read | GET /members/{id} | Obtener datos de miembro | id | {id, username, fullName, email, initials, avatar} | read:board:trello | — | — |
| [ ] | `trello.member.update` | update | PUT /members/{id} | Actualizar datos de miembro | id, fullName, initials, bio, avatarSource | miembro actualizado | write:member:trello | — | — |
| [ ] | `trello.member.get_field` | read | GET /members/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:board:trello | — | — |
| [ ] | `trello.member.list_actions` | read | GET /members/{id}/actions | Listar acciones del miembro | id, limit, filter | lista de acciones | read:board:trello | — | — |
| [ ] | `trello.member.list_notifications` | read | GET /members/{id}/notifications | Listar notificaciones | id, filter, limit, read | lista de notificaciones | read:board:trello | — | — |
| [ ] | `trello.member.list_tokens` | read | GET /members/{id}/tokens | Listar tokens del miembro | id | lista de tokens | read:board:trello | — | — |
| [ ] | `trello.member.list_boards` | read | GET /members/{id}/boards | Listar tableros del miembro | id, filter | lista de tableros | read:board:trello | — | — |
| [ ] | `trello.member.list_boards_invited` | read | GET /members/{id}/boardsInvited | Listar invitaciones a tableros | id, filter | lista de tableros | read:board:trello | — | — |
| [ ] | `trello.member.list_cards` | read | GET /members/{id}/cards | Listar tarjetas del miembro | id, filter | lista de tarjetas | read:board:trello | — | — |
| [ ] | `trello.member.list_board_stars` | read | GET /members/{id}/boardStars | Listar tableros con estrella | id | lista de stars | read:board:trello | — | — |
| [ ] | `trello.member.create_board_star` | create | POST /members/{id}/boardStars | Añadir estrella a tablero | id, idBoard, pos | {id, idBoard, pos} | write:board:trello | — | — |
| [ ] | `trello.member.update_board_star` | update | PUT /members/{id}/boardStars/{idStar} | Actualizar posición de estrella | id, idStar, pos | star actualizada | write:board:trello | — | — |
| [ ] | `trello.member.remove_board_star` | delete | DELETE /members/{id}/boardStars/{idStar} | Remover estrella | id, idStar | — | write:board:trello | — | — |
| [ ] | `trello.member.list_board_backgrounds` | read | GET /members/{id}/boardBackgrounds | Listar fondos personalizados | id | lista de fondos | read:board:trello | — | — |
| [ ] | `trello.member.create_board_background` | create | POST /members/{id}/boardBackgrounds | Subir fondo personalizado | id, file, name, tile | {id, name, url, tile} | write:board:trello | — | — |
| [ ] | `trello.member.get_board_background` | read | GET /members/{id}/boardBackgrounds/{idBackground} | Obtener fondo específico | id, idBackground | {id, name, url, tile} | read:board:trello | — | — |
| [ ] | `trello.member.update_board_background` | update | PUT /members/{id}/boardBackgrounds/{idBackground} | Actualizar fondo | id, idBackground, name, tile, brightness | fondo actualizado | write:board:trello | — | — |
| [ ] | `trello.member.delete_board_background` | delete | DELETE /members/{id}/boardBackgrounds/{idBackground} | Eliminar fondo | id, idBackground | — | write:board:trello | — | — |
| [ ] | `trello.member.list_organizations` | read | GET /members/{id}/organizations | Listar organizaciones del miembro | id, filter | lista de organizaciones | read:organization:trello | — | — |
| [ ] | `trello.member.list_organizations_invited` | read | GET /members/{id}/organizationsInvited | Listar invitaciones a organizaciones | id | lista de org | read:organization:trello | — | — |
| [ ] | `trello.member.list_custom_emoji` | read | GET /members/{id}/customEmoji | Listar emojis personalizados | id | lista de emojis | read:board:trello | — | — |
| [ ] | `trello.member.create_custom_emoji` | create | POST /members/{id}/customEmoji | Crear emoji personalizado | id, name, file | {id, name, url} | write:board:trello | — | — |
| [ ] | `trello.member.list_custom_stickers` | read | GET /members/{id}/customStickers | Listar stickers personalizados | id | lista de stickers | read:board:trello | — | — |
| [ ] | `trello.member.create_custom_sticker` | create | POST /members/{id}/customStickers | Crear sticker personalizado | id, file, name | {id, name, url} | write:board:trello | — | — |
| [ ] | `trello.member.list_notification_channel_settings` | read | GET /members/{id}/notificationChannelSettings | Obtener preferencias de notificaciones | id | {email, push, etc.} | read:board:trello | — | — |
| [ ] | `trello.member.update_notification_channel_settings` | update | PUT /members/{id}/notificationChannelSettings | Actualizar preferencias | id, channel, enabled, frequency | preferencias actualizadas | write:member:trello | — | — |
| [ ] | `trello.member.upload_avatar` | create | POST /members/{id}/avatar | Subir avatar | id, file | {avatar} | write:member:trello | — | — |
| [ ] | `trello.member.dismiss_message` | create | POST /members/{id}/oneTimeMessagesDismissed | Descartar notificación | id, message | mensaje descartado | write:member:trello | — | — |
| [ ] | `trello.member.list_saved_searches` | read | GET /members/{id}/savedSearches | Listar búsquedas guardadas | id | lista de búsquedas | read:board:trello | — | — |
| [ ] | `trello.member.create_saved_search` | create | POST /members/{id}/savedSearches | Crear búsqueda guardada | id, name, query, pos | {id, name, query} | write:board:trello | — | — |
| [ ] | `trello.member.update_saved_search` | update | PUT /members/{id}/savedSearches/{idSearch} | Actualizar búsqueda guardada | id, idSearch, name, query, pos | búsqueda actualizada | write:board:trello | — | — |
| [ ] | `trello.member.delete_saved_search` | delete | DELETE /members/{id}/savedSearches/{idSearch} | Eliminar búsqueda guardada | id, idSearch | — | write:board:trello | — | — |

### Notificaciones (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.notification.get` | read | GET /notifications/{id} | Obtener notificación | id | {id, type, unread, date, memberCreator} | read:board:trello | — | — |
| [ ] | `trello.notification.update` | update | PUT /notifications/{id} | Marcar como leída | id, unread (false) | notificación actualizada | write:member:trello | — | — |
| [ ] | `trello.notification.get_field` | read | GET /notifications/{id}/{field} | Obtener campo específico | id, field | valor del campo | read:board:trello | — | — |
| [ ] | `trello.notification.mark_all_read` | create | POST /notifications/all/read | Marcar todas como leídas | — | — | write:member:trello | — | — |
| [ ] | `trello.notification.set_unread` | update | PUT /notifications/{id}/unread | Marcar como no leída | id, unread (true) | notificación actualizada | write:member:trello | — | — |
| [ ] | `trello.notification.get_board` | read | GET /notifications/{id}/board | Obtener tablero asociado | id | {id, name, idOrganization} | read:board:trello | — | — |
| [ ] | `trello.notification.get_card` | read | GET /notifications/{id}/card | Obtener tarjeta asociada | id | {id, name, idList} | read:board:trello | — | — |
| [ ] | `trello.notification.get_list` | read | GET /notifications/{id}/list | Obtener lista asociada | id | {id, name, closed} | read:board:trello | — | — |
| [ ] | `trello.notification.get_member` | read | GET /notifications/{id}/member | Obtener miembro referenciado | id | {id, username, fullName} | read:board:trello | — | — |
| [ ] | `trello.notification.get_member_creator` | read | GET /notifications/{id}/memberCreator | Obtener miembro creador | id | {id, username, fullName} | read:board:trello | — | — |
| [ ] | `trello.notification.get_organization` | read | GET /notifications/{id}/organization | Obtener organización asociada | id | {id, name} | read:board:trello | — | — |

### Tokens (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.token.get` | read | GET /tokens/{token} | Obtener información del token | token | {id, idMember, idAppKey, dateCreated, dateExpires} | read:board:trello | — | — |
| [ ] | `trello.token.delete` | delete | DELETE /tokens/{token} | Revocar token | token | — | write:member:trello | I | — |
| [ ] | `trello.token.get_member` | read | GET /tokens/{token}/member | Obtener propietario del token | token | {id, username, fullName, email} | read:board:trello | — | — |
| [ ] | `trello.token.list_webhooks` | read | GET /tokens/{token}/webhooks | Listar webhooks del token | token | lista de {id, callbackURL, idModel} | read:board:trello | — | — |
| [ ] | `trello.token.create_webhook` | create | POST /tokens/{token}/webhooks | Crear webhook con token | token, callbackURL, idModel, description | {id, callbackURL, idModel} | write:board:trello | — | — |
| [ ] | `trello.token.get_webhook` | read | GET /tokens/{token}/webhooks/{idWebhook} | Obtener webhook específico | token, idWebhook | {id, callbackURL, idModel, active} | read:board:trello | — | — |
| [ ] | `trello.token.update_webhook` | update | PUT /tokens/{token}/webhooks/{idWebhook} | Actualizar webhook | token, idWebhook, callbackURL, description, active | webhook actualizado | write:board:trello | — | — |
| [ ] | `trello.token.delete_webhook` | delete | DELETE /tokens/{token}/webhooks/{idWebhook} | Eliminar webhook | token, idWebhook | — | write:board:trello | — | — |

### Plugins (Power-Ups) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.plugin.get` | read | GET /plugins/{id} | Obtener información de plugin | id | {id, name, url, icon} | read:organization:trello | — | — |
| [ ] | `trello.plugin.update` | update | PUT /plugins/{id} | Actualizar plugin | id, name, url, icon | plugin actualizado | write:organization:trello | — | — |
| [ ] | `trello.plugin.create_listing` | create | POST /plugins/{idPlugin}/listings | Crear listado de plugin | idPlugin, name, desc, url | {id, name, desc} | write:organization:trello | — | — |
| [ ] | `trello.plugin.update_listing` | update | PUT /plugins/{idPlugin}/listings/{idListing} | Actualizar listado | idPlugin, idListing, name, desc, url | listado actualizado | write:organization:trello | — | — |
| [ ] | `trello.plugin.get_member_privacy_compliance` | read | GET /plugins/{id}/compliance/memberPrivacy | Obtener cumplimiento privacidad miembros | id | compliance data | read:organization:trello | — | — |

### Aplicaciones (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.application.get_compliance` | read | GET /applications/{key}/compliance | Obtener datos de cumplimiento | key | compliance data | read:organization:trello | — | — |

### Empresas (Enterprises) (19)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.enterprise.get` | read | GET /enterprises/{id} | Obtener datos de empresa | id | {id, name, ssoActivationUrl} | read:organization:trello | — | — |
| [ ] | `trello.enterprise.list_admins` | read | GET /enterprises/{id}/admins | Listar administradores | id | lista de {id, username, fullName} | read:organization:trello | — | — |
| [ ] | `trello.enterprise.list_members` | read | GET /enterprises/{id}/members | Listar miembros | id, query, limit | lista de miembros | read:organization:trello | — | — |
| [ ] | `trello.enterprise.get_member` | read | GET /enterprises/{id}/members/{idMember} | Obtener miembro específico | id, idMember | {id, username, fullName, email} | read:organization:trello | — | — |
| [ ] | `trello.enterprise.search_members` | read | GET /enterprises/{id}/members/query | Buscar miembros | id, query, limit | lista de miembros | read:organization:trello | — | — |
| [ ] | `trello.enterprise.list_organizations` | read | GET /enterprises/{id}/organizations | Listar organizaciones | id | lista de organizaciones | read:organization:trello | — | — |
| [ ] | `trello.enterprise.list_pending_organizations` | read | GET /enterprises/{id}/pendingOrganizations | Listar org pendientes | id | lista de org | read:organization:trello | — | — |
| [ ] | `trello.enterprise.list_claimable_organizations` | read | GET /enterprises/{id}/claimableOrganizations | Listar org reclamables | id | lista de org | read:organization:trello | — | — |
| [ ] | `trello.enterprise.accept_organizations_bulk` | create | POST /enterprises/{id}/organizations/bulk/{idOrganizations} | Aceptar múltiples org | id, idOrganizations | orgs aceptadas | write:organization:trello | — | — |
| [ ] | `trello.enterprise.transfer_organization` | create | PUT /enterprises/{id}/organizations | Transferir org a empresa | id, idOrganizations | org transferida | write:organization:trello | — | — |
| [ ] | `trello.enterprise.set_member_licensed` | update | PUT /enterprises/{id}/members/{idMember}/licensed | Asignar licencia | id, idMember, licensed | miembro actualizado | write:organization:trello | — | — |
| [ ] | `trello.enterprise.set_member_deactivated` | update | PUT /enterprises/{id}/members/{idMember}/deactivated | Desactivar miembro | id, idMember, deactivated | miembro actualizado | write:organization:trello | — | — |
| [ ] | `trello.enterprise.set_admin` | create | PUT /enterprises/{id}/admins/{idMember} | Asignar admin | id, idMember | admin asignado | write:organization:trello | — | — |
| [ ] | `trello.enterprise.remove_admin` | delete | DELETE /enterprises/{id}/admins/{idMember} | Remover admin | id, idMember | — | write:organization:trello | — | — |
| [ ] | `trello.enterprise.remove_organization` | delete | DELETE /enterprises/{id}/organizations/{idOrg} | Remover org de empresa | id, idOrg | — | write:organization:trello | — | — |
| [ ] | `trello.enterprise.get_audit_log` | read | GET /enterprises/{id}/auditlog | Obtener log de auditoría | id, limit, offset | lista de eventos | read:organization:trello | — | — |
| [ ] | `trello.enterprise.get_signup_url` | read | GET /enterprises/{id}/signupUrl | Obtener URL de registro | id | {url} | read:organization:trello | — | — |
| [ ] | `trello.enterprise.get_transferrable_organization` | read | GET /enterprises/{id}/transferrable/organization/{idOrganization} | Verificar transferibilidad org | id, idOrganization | {transferrable, reason} | read:organization:trello | — | — |
| [ ] | `trello.enterprise.get_transferrable_organizations_bulk` | read | GET /enterprises/{id}/transferrable/bulk/{idOrganizations} | Verificar transferibilidad múltiples | id, idOrganizations | lista de resultados | read:organization:trello | — | — |

### Emoji (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.emoji.list` | read | GET /emoji | Listar emojis disponibles | locale, spritesheets | lista de {code, name, native, shortName, category} | read:board:trello | — | — |

### Lote (Batch) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `trello.batch.get` | read | GET /batch | Ejecutar hasta 10 GET en una llamada | urls | lista de resultados de cada URL | read:board:trello | — | — |
