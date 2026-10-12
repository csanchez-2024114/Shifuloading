# Tareas: HubSpot

- **Funciones catalogadas:** 217 · **Hechas:** 0 · **Pendientes:** 217 · **Herramientas viejas a migrar:** 52 (columna "Herramienta vieja")
- **Documentación oficial:** https://developers.hubspot.com/docs/api/overview
- **Fuentes que consultó el catálogo:** https://developers.hubspot.com/docs/api-reference/latest/crm/understanding-the-crm https://developers.hubspot.com/docs/api-reference/latest/crm/using-object-apis https://developers.hubspot.com/docs/api-reference/latest/crm/search-the-crm https://developers.hubspot.com/docs/api-reference/latest/crm/imports/guide https://developers.hubspot.com/docs/api-reference/latest/crm/exports/guide https://developers.hubspot.com/docs/api-reference/latest/crm/pipelines/guide https://developers.hubspot.com/docs/api-reference/crm-associations-v4/guide https://developers.hubspot.com/docs/api-reference/crm-properties-v3/guide https://developers.hubspot.com/docs/api-reference/legacy/conversations/guide https://developers.hubspot.com/docs/api-reference/legacy/webhooks/guide https://developers.hubspot.com/docs/api-reference/legacy/marketing/campaigns/guide https://developers.hubspot.com/docs/api-reference/marketing-marketing-emails-v3/guide https://developers.hubspot.com/docs/api-reference/legacy/marketing/marketing-events/guide https://developers.hubspot.com/docs/api-reference/2026-09-beta/marketing/forms/guide https://developers.hubspot.com/docs/api-reference/latest/account/audit-logs/guide
- **Paginación típica:** cursor-based (parámetro after) para búsqueda; limit/offset para listados; máx 200 registros por página
- **Qué no se pudo verificar:** Filas del grupo 'Portal, propietarios y otros' agregadas a mano (endpoints /settings/v3 y /crm/v3/owners por verificar); dashboards, resumen CRM e historial de actividades no tienen endpoint publico identificado.
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/hubspot/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `hubspot`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `hubspot` |
| Variables del `.env` que necesitas | HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/hubspot/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `hubspot.account.get` |
| Cómo se autentica (según el catálogo) | OAuth2 código; obtiene access_token (30 min) y refresh_token; renueva con endpoint token cuando caduca |
| Duración del token (según el catálogo) | 30 minutos (access_token); refresh_token no caduca |
| Refresco (según el catálogo) | Sí; POST /oauth/v1/token con grant_type=refresh_token |
| Permisos (según el catálogo) | crm.objects.{tipo}.read/write (contacts, companies, deals, tickets, products, etc.), crm.lists.read/write, crm.import, crm.export, crm.objects.custom.read/write, conversations.read/write, webhooks, marketing.campaigns, marketing.emails, accounting.read/write |
| Restricciones de acceso | Enterprise requiere revisión de la app para nuevas integraciones; algunos scopes son opcionales para Enterprise; revisión de privacidad para acceso a todos los contactos |
| Límites de ritmo | búsqueda 5 req/s por cuenta, máx 10,000 resultados por query, batch limitado a 100-2,000 registros según operación, máx 30 exportaciones en 24h, máx 1,000 asociaciones por cuenta |
| Notas de esta app | El callback viejo escribe también en el almacén legado `oauth_vault`; las funciones nuevas leen solo `user_connected_accounts`. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/hubspot/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> hubspot`. | Cuenta con `provider: hubspot`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/hubspot.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> hubspot <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de HubSpot. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/hubspot.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Account (whoami) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.account.get` ★ | read | GET /account-info/2026-09/details | Obtiene información de la cuenta HubSpot conectada (portal ID, zona horaria, moneda) | — | portalId, timeZone, currency, dataHostLocation | crm.objects.read | — | obtener_informacion_cuenta_hubspot |

### Contacts (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.contacts.list` | read | GET /crm/objects/2026-09/contacts | Lista todos los contactos de la cuenta | — | lista de {id, nombre, email, teléfono, empresa} + siguiente página | crm.objects.contacts.read | — | listar_contactos_hubspot |
| [ ] | `hubspot.contacts.get` | read | GET /crm/objects/2026-09/contacts/{contactId} | Obtiene detalles de un contacto específico | contactId | {id, nombre, email, teléfono, empresa, propiedades personalizadas} | crm.objects.contacts.read | — | buscar_contacto_por_id_hubspot |
| [ ] | `hubspot.contacts.search` | read | POST /crm/objects/2026-09/contacts/search | Busca contactos por propiedades (email, nombre, teléfono, etc.) | filterGroups, query, limit, after | lista de contactos que coinciden + siguiente página | crm.objects.contacts.read | — | — |
| [ ] | `hubspot.contacts.create` | create | POST /crm/objects/2026-09/contacts | Crea un nuevo contacto con propiedades (email, nombre, etc.) | email, firstname, lastname, phone | {id, propiedades creadas} | crm.objects.contacts.write | — | crear_contacto_hubspot |
| [ ] | `hubspot.contacts.update` | update | PATCH /crm/objects/2026-09/contacts/{contactId} | Actualiza propiedades de un contacto existente | contactId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.contacts.write | — | actualizar_contacto_hubspot |
| [ ] | `hubspot.contacts.delete` | delete | DELETE /crm/objects/2026-09/contacts/{contactId} | Elimina (archiva) un contacto | contactId | — | crm.objects.contacts.write | I | — |
| [ ] | `hubspot.contacts.batch_create` | create | POST /crm/objects/2026-09/contacts/batch/create | Crea hasta 100 contactos en una sola llamada | lista de objetos contacto | lista de {id, propiedades} | crm.objects.contacts.write | — | — |
| [ ] | `hubspot.contacts.batch_update` | update | POST /crm/objects/2026-09/contacts/batch/update | Actualiza hasta 100 contactos en una sola llamada | lista de {id, propiedades a cambiar} | lista de {id, propiedades actualizadas} | crm.objects.contacts.write | — | — |
| [ ] | `hubspot.contacts.batch_read` | read | POST /crm/objects/2026-09/contacts/batch/read | Lee detalles de hasta 100 contactos en una sola llamada | lista de ids | lista de contactos con propiedades | crm.objects.contacts.read | — | — |
| [ ] | `hubspot.contacts.batch_archive` | delete | POST /crm/objects/2026-09/contacts/batch/archive | Archiva hasta 100 contactos en una sola llamada | lista de ids | — | crm.objects.contacts.write | I | — |
| [ ] | `hubspot.contacts.batch_upsert` | update | POST /crm/objects/2026-09/contacts/batch/upsert | Crea o actualiza contactos (si existen por email/id) | lista de {id/email, propiedades} | lista de {id, si fue creado o actualizado} | crm.objects.contacts.write | — | — |
| [ ] | `hubspot.contacts.merge` | update | POST /crm/objects/2026-09/contacts/merge | Fusiona dos contactos duplicados | contactIds (lista de 2), mergeMetadata | {contactId fusionado, propiedades unidas} | crm.objects.contacts.write | I | — |

### Companies (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.companies.list` | read | GET /crm/objects/2026-09/companies | Lista todas las empresas de la cuenta | — | lista de {id, nombre, dominio, industria} + siguiente página | crm.objects.companies.read | — | listar_companias_hubspot |
| [ ] | `hubspot.companies.get` | read | GET /crm/objects/2026-09/companies/{companyId} | Obtiene detalles de una empresa específica | companyId | {id, nombre, dominio, industria, propiedades personalizadas} | crm.objects.companies.read | — | buscar_compania_por_id_hubspot |
| [ ] | `hubspot.companies.search` | read | POST /crm/objects/2026-09/companies/search | Busca empresas por propiedades (nombre, dominio, industria, etc.) | filterGroups, query, limit, after | lista de empresas que coinciden + siguiente página | crm.objects.companies.read | — | — |
| [ ] | `hubspot.companies.create` | create | POST /crm/objects/2026-09/companies | Crea una nueva empresa con propiedades (nombre, dominio, etc.) | name, domain, industry | {id, propiedades creadas} | crm.objects.companies.write | — | crear_compania_hubspot |
| [ ] | `hubspot.companies.update` | update | PATCH /crm/objects/2026-09/companies/{companyId} | Actualiza propiedades de una empresa existente | companyId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.companies.write | — | actualizar_compania_hubspot |
| [ ] | `hubspot.companies.delete` | delete | DELETE /crm/objects/2026-09/companies/{companyId} | Elimina (archiva) una empresa | companyId | — | crm.objects.companies.write | I | — |
| [ ] | `hubspot.companies.batch_create` | create | POST /crm/objects/2026-09/companies/batch/create | Crea hasta 100 empresas en una sola llamada | lista de objetos empresa | lista de {id, propiedades} | crm.objects.companies.write | — | — |
| [ ] | `hubspot.companies.batch_update` | update | POST /crm/objects/2026-09/companies/batch/update | Actualiza hasta 100 empresas en una sola llamada | lista de {id, propiedades a cambiar} | lista de {id, propiedades actualizadas} | crm.objects.companies.write | — | — |
| [ ] | `hubspot.companies.batch_read` | read | POST /crm/objects/2026-09/companies/batch/read | Lee detalles de hasta 100 empresas en una sola llamada | lista de ids | lista de empresas con propiedades | crm.objects.companies.read | — | — |
| [ ] | `hubspot.companies.batch_archive` | delete | POST /crm/objects/2026-09/companies/batch/archive | Archiva hasta 100 empresas en una sola llamada | lista de ids | — | crm.objects.companies.write | I | — |
| [ ] | `hubspot.companies.batch_upsert` | update | POST /crm/objects/2026-09/companies/batch/upsert | Crea o actualiza empresas (si existen) | lista de {id/dominio, propiedades} | lista de {id, si fue creado o actualizado} | crm.objects.companies.write | — | — |
| [ ] | `hubspot.companies.merge` | update | POST /crm/objects/2026-09/companies/merge | Fusiona dos empresas duplicadas | companyIds (lista de 2), mergeMetadata | {companyId fusionado, propiedades unidas} | crm.objects.companies.write | I | — |

### Deals (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.deals.list` | read | GET /crm/objects/2026-09/deals | Lista todos los deals de la cuenta | — | lista de {id, dealname, dealstage, amount} + siguiente página | crm.objects.deals.read | — | listar_deals_hubspot |
| [ ] | `hubspot.deals.get` | read | GET /crm/objects/2026-09/deals/{dealId} | Obtiene detalles de un deal específico | dealId | {id, dealname, dealstage, amount, pipeline, propiedades personalizadas} | crm.objects.deals.read | — | buscar_deal_por_id_hubspot |
| [ ] | `hubspot.deals.search` | read | POST /crm/objects/2026-09/deals/search | Busca deals por propiedades (etapa, monto, propietario, etc.) | filterGroups, query, limit, after | lista de deals que coinciden + siguiente página | crm.objects.deals.read | — | — |
| [ ] | `hubspot.deals.create` | create | POST /crm/objects/2026-09/deals | Crea un nuevo deal con propiedades (nombre, etapa, monto, etc.) | dealname, dealstage, amount, pipeline | {id, propiedades creadas} | crm.objects.deals.write | — | crear_deal_hubspot |
| [ ] | `hubspot.deals.update` | update | PATCH /crm/objects/2026-09/deals/{dealId} | Actualiza propiedades de un deal existente | dealId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.deals.write | — | actualizar_deal_hubspot |
| [ ] | `hubspot.deals.delete` | delete | DELETE /crm/objects/2026-09/deals/{dealId} | Elimina (archiva) un deal | dealId | — | crm.objects.deals.write | I | — |
| [ ] | `hubspot.deals.batch_create` | create | POST /crm/objects/2026-09/deals/batch/create | Crea hasta 100 deals en una sola llamada | lista de objetos deal | lista de {id, propiedades} | crm.objects.deals.write | — | — |
| [ ] | `hubspot.deals.batch_update` | update | POST /crm/objects/2026-09/deals/batch/update | Actualiza hasta 100 deals en una sola llamada | lista de {id, propiedades a cambiar} | lista de {id, propiedades actualizadas} | crm.objects.deals.write | — | — |
| [ ] | `hubspot.deals.batch_read` | read | POST /crm/objects/2026-09/deals/batch/read | Lee detalles de hasta 100 deals en una sola llamada | lista de ids | lista de deals con propiedades | crm.objects.deals.read | — | — |
| [ ] | `hubspot.deals.batch_archive` | delete | POST /crm/objects/2026-09/deals/batch/archive | Archiva hasta 100 deals en una sola llamada | lista de ids | — | crm.objects.deals.write | I | — |
| [ ] | `hubspot.deals.batch_upsert` | update | POST /crm/objects/2026-09/deals/batch/upsert | Crea o actualiza deals (si existen) | lista de {id, propiedades} | lista de {id, si fue creado o actualizado} | crm.objects.deals.write | — | — |
| [ ] | `hubspot.deals.merge` | update | POST /crm/objects/2026-09/deals/merge | Fusiona dos deals duplicados | dealIds (lista de 2), mergeMetadata | {dealId fusionado, propiedades unidas} | crm.objects.deals.write | I | — |

### Tickets (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.tickets.list` | read | GET /crm/objects/2026-09/tickets | Lista todos los tickets de la cuenta | — | lista de {id, ticketname, ticketstatus, priority} + siguiente página | crm.objects.tickets.read | — | listar_tickets_hubspot |
| [ ] | `hubspot.tickets.get` | read | GET /crm/objects/2026-09/tickets/{ticketId} | Obtiene detalles de un ticket específico | ticketId | {id, ticketname, ticketstatus, priority, pipeline, propiedades personalizadas} | crm.objects.tickets.read | — | buscar_ticket_por_id_hubspot |
| [ ] | `hubspot.tickets.search` | read | POST /crm/objects/2026-09/tickets/search | Busca tickets por propiedades (estado, prioridad, propietario, etc.) | filterGroups, query, limit, after | lista de tickets que coinciden + siguiente página | crm.objects.tickets.read | — | — |
| [ ] | `hubspot.tickets.create` | create | POST /crm/objects/2026-09/tickets | Crea un nuevo ticket con propiedades (nombre, estado, prioridad, etc.) | ticketname, ticketstatus, priority | {id, propiedades creadas} | crm.objects.tickets.write | — | crear_ticket_hubspot |
| [ ] | `hubspot.tickets.update` | update | PATCH /crm/objects/2026-09/tickets/{ticketId} | Actualiza propiedades de un ticket existente | ticketId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.tickets.write | — | actualizar_ticket_hubspot |
| [ ] | `hubspot.tickets.delete` | delete | DELETE /crm/objects/2026-09/tickets/{ticketId} | Elimina (archiva) un ticket | ticketId | — | crm.objects.tickets.write | I | — |
| [ ] | `hubspot.tickets.batch_create` | create | POST /crm/objects/2026-09/tickets/batch/create | Crea hasta 100 tickets en una sola llamada | lista de objetos ticket | lista de {id, propiedades} | crm.objects.tickets.write | — | — |
| [ ] | `hubspot.tickets.batch_update` | update | POST /crm/objects/2026-09/tickets/batch/update | Actualiza hasta 100 tickets en una sola llamada | lista de {id, propiedades a cambiar} | lista de {id, propiedades actualizadas} | crm.objects.tickets.write | — | — |
| [ ] | `hubspot.tickets.batch_read` | read | POST /crm/objects/2026-09/tickets/batch/read | Lee detalles de hasta 100 tickets en una sola llamada | lista de ids | lista de tickets con propiedades | crm.objects.tickets.read | — | — |
| [ ] | `hubspot.tickets.batch_archive` | delete | POST /crm/objects/2026-09/tickets/batch/archive | Archiva hasta 100 tickets en una sola llamada | lista de ids | — | crm.objects.tickets.write | I | — |
| [ ] | `hubspot.tickets.batch_upsert` | update | POST /crm/objects/2026-09/tickets/batch/upsert | Crea o actualiza tickets (si existen) | lista de {id, propiedades} | lista de {id, si fue creado o actualizado} | crm.objects.tickets.write | — | — |
| [ ] | `hubspot.tickets.merge` | update | POST /crm/objects/2026-09/tickets/merge | Fusiona dos tickets duplicados | ticketIds (lista de 2), mergeMetadata | {ticketId fusionado, propiedades unidas} | crm.objects.tickets.write | I | — |

### Products (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.products.list` | read | GET /crm/objects/2026-09/products | Lista todos los productos de la cuenta | — | lista de {id, sku, nombre, precio} + siguiente página | crm.objects.products.read | — | listar_productos_hubspot |
| [ ] | `hubspot.products.get` | read | GET /crm/objects/2026-09/products/{productId} | Obtiene detalles de un producto específico | productId | {id, sku, nombre, precio, descripción, propiedades personalizadas} | crm.objects.products.read | — | buscar_producto_por_id_hubspot |
| [ ] | `hubspot.products.search` | read | POST /crm/objects/2026-09/products/search | Busca productos por propiedades (SKU, nombre, categoría, etc.) | filterGroups, query, limit, after | lista de productos que coinciden + siguiente página | crm.objects.products.read | — | — |
| [ ] | `hubspot.products.create` | create | POST /crm/objects/2026-09/products | Crea un nuevo producto con propiedades (SKU, nombre, precio, etc.) | sku, name, price | {id, propiedades creadas} | crm.objects.products.write | — | crear_producto_hubspot |
| [ ] | `hubspot.products.update` | update | PATCH /crm/objects/2026-09/products/{productId} | Actualiza propiedades de un producto existente | productId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.products.write | — | actualizar_producto_hubspot |
| [ ] | `hubspot.products.delete` | delete | DELETE /crm/objects/2026-09/products/{productId} | Elimina (archiva) un producto | productId | — | crm.objects.products.write | I | — |
| [ ] | `hubspot.products.batch_create` | create | POST /crm/objects/2026-09/products/batch/create | Crea hasta 100 productos en una sola llamada | lista de objetos producto | lista de {id, propiedades} | crm.objects.products.write | — | — |
| [ ] | `hubspot.products.batch_update` | update | POST /crm/objects/2026-09/products/batch/update | Actualiza hasta 100 productos en una sola llamada | lista de {id, propiedades a cambiar} | lista de {id, propiedades actualizadas} | crm.objects.products.write | — | — |
| [ ] | `hubspot.products.batch_read` | read | POST /crm/objects/2026-09/products/batch/read | Lee detalles de hasta 100 productos en una sola llamada | lista de ids | lista de productos con propiedades | crm.objects.products.read | — | — |
| [ ] | `hubspot.products.batch_archive` | delete | POST /crm/objects/2026-09/products/batch/archive | Archiva hasta 100 productos en una sola llamada | lista de ids | — | crm.objects.products.write | I | — |

### Line Items (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.line_items.list` | read | GET /crm/objects/2026-09/line_items | Lista todos los line items de la cuenta | — | lista de {id, dealId, quantity, amount} + siguiente página | crm.objects.line_items.read | — | listar_items_linea_hubspot |
| [ ] | `hubspot.line_items.get` | read | GET /crm/objects/2026-09/line_items/{lineItemId} | Obtiene detalles de un line item específico | lineItemId | {id, dealId, productId, quantity, amount, propiedades personalizadas} | crm.objects.line_items.read | — | — |
| [ ] | `hubspot.line_items.search` | read | POST /crm/objects/2026-09/line_items/search | Busca line items por propiedades (deal, producto, cantidad, etc.) | filterGroups, query, limit, after | lista de line items que coinciden + siguiente página | crm.objects.line_items.read | — | — |
| [ ] | `hubspot.line_items.create` | create | POST /crm/objects/2026-09/line_items | Crea un nuevo line item con propiedades (deal, producto, cantidad, etc.) | dealId, productId, quantity | {id, propiedades creadas} | crm.objects.line_items.write | — | — |
| [ ] | `hubspot.line_items.update` | update | PATCH /crm/objects/2026-09/line_items/{lineItemId} | Actualiza propiedades de un line item existente | lineItemId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.line_items.write | — | — |
| [ ] | `hubspot.line_items.delete` | delete | DELETE /crm/objects/2026-09/line_items/{lineItemId} | Elimina (archiva) un line item | lineItemId | — | crm.objects.line_items.write | I | — |

### Quotes (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.quotes.list` | read | GET /crm/objects/2026-09/quotes | Lista todas las cotizaciones de la cuenta | — | lista de {id, dealId, expirationDate, totalAmount} + siguiente página | crm.objects.quotes.read | — | listar_cotizaciones_hubspot |
| [ ] | `hubspot.quotes.get` | read | GET /crm/objects/2026-09/quotes/{quoteId} | Obtiene detalles de una cotización específica | quoteId | {id, dealId, expirationDate, totalAmount, lineItems, propiedades personalizadas} | crm.objects.quotes.read | — | — |
| [ ] | `hubspot.quotes.search` | read | POST /crm/objects/2026-09/quotes/search | Busca cotizaciones por propiedades (deal, fecha, monto, etc.) | filterGroups, query, limit, after | lista de cotizaciones que coinciden + siguiente página | crm.objects.quotes.read | — | — |
| [ ] | `hubspot.quotes.create` | create | POST /crm/objects/2026-09/quotes | Crea una nueva cotización con propiedades (deal, expiration, etc.) | dealId, expirationDate | {id, propiedades creadas} | crm.objects.quotes.write | — | — |
| [ ] | `hubspot.quotes.update` | update | PATCH /crm/objects/2026-09/quotes/{quoteId} | Actualiza propiedades de una cotización existente | quoteId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.quotes.write | — | — |
| [ ] | `hubspot.quotes.delete` | delete | DELETE /crm/objects/2026-09/quotes/{quoteId} | Elimina (archiva) una cotización | quoteId | — | crm.objects.quotes.write | I | — |

### Notes (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.notes.list` | read | GET /crm/objects/2026-09/notes | Lista todas las notas de la cuenta | — | lista de {id, hs_note_body, hs_timestamp} + siguiente página | crm.objects.notes.read | — | listar_notas_hubspot |
| [ ] | `hubspot.notes.get` | read | GET /crm/objects/2026-09/notes/{noteId} | Obtiene detalles de una nota específica | noteId | {id, hs_note_body, hs_timestamp, hubspotOwnerId, propiedades personalizadas} | crm.objects.notes.read | — | — |
| [ ] | `hubspot.notes.search` | read | POST /crm/objects/2026-09/notes/search | Busca notas por propiedades (contenido, fecha, propietario, etc.) | filterGroups, query, limit, after | lista de notas que coinciden + siguiente página | crm.objects.notes.read | — | — |
| [ ] | `hubspot.notes.create` | create | POST /crm/objects/2026-09/notes | Crea una nueva nota con contenido y propietario | hs_note_body, hubspotOwnerId | {id, hs_timestamp, propiedades creadas} | crm.objects.notes.write | — | crear_nota_hubspot |
| [ ] | `hubspot.notes.update` | update | PATCH /crm/objects/2026-09/notes/{noteId} | Actualiza propiedades de una nota existente | noteId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.notes.write | — | actualizar_nota_hubspot |
| [ ] | `hubspot.notes.delete` | delete | DELETE /crm/objects/2026-09/notes/{noteId} | Elimina (archiva) una nota | noteId | — | crm.objects.notes.write | I | — |

### Calls (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.calls.list` | read | GET /crm/objects/2026-09/calls | Lista todas las llamadas de la cuenta | — | lista de {id, hs_call_duration, hs_timestamp, hs_call_status} + siguiente página | crm.objects.calls.read | — | listar_llamadas_hubspot |
| [ ] | `hubspot.calls.get` | read | GET /crm/objects/2026-09/calls/{callId} | Obtiene detalles de una llamada específica | callId | {id, hs_call_duration, hs_timestamp, hs_call_status, hubspotOwnerId, propiedades personalizadas} | crm.objects.calls.read | — | — |
| [ ] | `hubspot.calls.search` | read | POST /crm/objects/2026-09/calls/search | Busca llamadas por propiedades (duración, fecha, estado, propietario, etc.) | filterGroups, query, limit, after | lista de llamadas que coinciden + siguiente página | crm.objects.calls.read | — | — |
| [ ] | `hubspot.calls.create` | create | POST /crm/objects/2026-09/calls | Crea un registro de llamada con propiedades (duración, estado, etc.) | hs_call_status, hs_timestamp, hubspotOwnerId | {id, propiedades creadas} | crm.objects.calls.write | — | crear_llamada_hubspot |
| [ ] | `hubspot.calls.update` | update | PATCH /crm/objects/2026-09/calls/{callId} | Actualiza propiedades de una llamada existente | callId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.calls.write | — | — |
| [ ] | `hubspot.calls.delete` | delete | DELETE /crm/objects/2026-09/calls/{callId} | Elimina (archiva) una llamada | callId | — | crm.objects.calls.write | I | — |

### Meetings (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.meetings.list` | read | GET /crm/objects/2026-09/meetings | Lista todas las reuniones de la cuenta | — | lista de {id, hs_meeting_start_time, hs_meeting_end_time} + siguiente página | crm.objects.meetings.read | — | listar_reuniones_hubspot |
| [ ] | `hubspot.meetings.get` | read | GET /crm/objects/2026-09/meetings/{meetingId} | Obtiene detalles de una reunión específica | meetingId | {id, hs_meeting_start_time, hs_meeting_end_time, hs_meeting_title, hubspotOwnerId, propiedades personalizadas} | crm.objects.meetings.read | — | — |
| [ ] | `hubspot.meetings.search` | read | POST /crm/objects/2026-09/meetings/search | Busca reuniones por propiedades (título, fecha, propietario, etc.) | filterGroups, query, limit, after | lista de reuniones que coinciden + siguiente página | crm.objects.meetings.read | — | — |
| [ ] | `hubspot.meetings.create` | create | POST /crm/objects/2026-09/meetings | Crea una nueva reunión con propiedades (título, fechas, etc.) | hs_meeting_title, hs_meeting_start_time, hs_meeting_end_time | {id, propiedades creadas} | crm.objects.meetings.write | — | — |
| [ ] | `hubspot.meetings.update` | update | PATCH /crm/objects/2026-09/meetings/{meetingId} | Actualiza propiedades de una reunión existente | meetingId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.meetings.write | — | — |
| [ ] | `hubspot.meetings.delete` | delete | DELETE /crm/objects/2026-09/meetings/{meetingId} | Elimina (archiva) una reunión | meetingId | — | crm.objects.meetings.write | I | — |

### Emails (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.emails.list` | read | GET /crm/objects/2026-09/emails | Lista todos los emails de la cuenta | — | lista de {id, hs_timestamp, hs_email_subject} + siguiente página | crm.objects.emails.read | — | listar_emails_hubspot |
| [ ] | `hubspot.emails.get` | read | GET /crm/objects/2026-09/emails/{emailId} | Obtiene detalles de un email específico | emailId | {id, hs_timestamp, hs_email_subject, hs_email_from, hs_email_to, propiedades personalizadas} | crm.objects.emails.read | — | — |
| [ ] | `hubspot.emails.search` | read | POST /crm/objects/2026-09/emails/search | Busca emails por propiedades (asunto, remitente, fecha, etc.) | filterGroups, query, limit, after | lista de emails que coinciden + siguiente página | crm.objects.emails.read | — | — |
| [ ] | `hubspot.emails.create` | create | POST /crm/objects/2026-09/emails | Registra un email enviado con propiedades (asunto, from, to, etc.) | hs_email_from, hs_email_to, hs_email_subject | {id, propiedades creadas} | crm.objects.emails.write | — | — |
| [ ] | `hubspot.emails.update` | update | PATCH /crm/objects/2026-09/emails/{emailId} | Actualiza propiedades de un email registrado | emailId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.emails.write | — | — |
| [ ] | `hubspot.emails.delete` | delete | DELETE /crm/objects/2026-09/emails/{emailId} | Elimina (archiva) un email | emailId | — | crm.objects.emails.write | I | — |

### Tasks (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.tasks.list` | read | GET /crm/objects/2026-09/tasks | Lista todas las tareas de la cuenta | — | lista de {id, hs_task_status, hs_task_type, hs_task_subject} + siguiente página | crm.objects.tasks.read | — | — |
| [ ] | `hubspot.tasks.get` | read | GET /crm/objects/2026-09/tasks/{taskId} | Obtiene detalles de una tarea específica | taskId | {id, hs_task_status, hs_task_type, hs_task_subject, hubspotOwnerId, propiedades personalizadas} | crm.objects.tasks.read | — | — |
| [ ] | `hubspot.tasks.search` | read | POST /crm/objects/2026-09/tasks/search | Busca tareas por propiedades (estado, tipo, asunto, propietario, etc.) | filterGroups, query, limit, after | lista de tareas que coinciden + siguiente página | crm.objects.tasks.read | — | — |
| [ ] | `hubspot.tasks.create` | create | POST /crm/objects/2026-09/tasks | Crea una nueva tarea con propiedades (asunto, estado, etc.) | hs_task_subject, hs_task_status, hs_task_type | {id, propiedades creadas} | crm.objects.tasks.write | — | crear_tarea_hubspot |
| [ ] | `hubspot.tasks.update` | update | PATCH /crm/objects/2026-09/tasks/{taskId} | Actualiza propiedades de una tarea existente | taskId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.tasks.write | — | — |
| [ ] | `hubspot.tasks.delete` | delete | DELETE /crm/objects/2026-09/tasks/{taskId} | Elimina (archiva) una tarea | taskId | — | crm.objects.tasks.write | I | — |

### Pipelines (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.pipelines.list` | read | GET /crm/v3/pipelines/{objectType} | Lista todos los pipelines para un tipo de objeto (deals, tickets, etc.) | objectType | lista de {id, label, stages} | crm.objects.deals.read | — | listar_pipelines_hubspot |
| [ ] | `hubspot.pipelines.get` | read | GET /crm/v3/pipelines/{objectType}/{pipelineId} | Obtiene detalles de un pipeline específico | objectType, pipelineId | {id, label, stages, displayOrder, propiedades} | crm.objects.deals.read | — | detalles_pipeline_hubspot |
| [ ] | `hubspot.pipeline_stages.list` | read | GET /crm/v3/pipelines/{objectType}/{pipelineId}/stages | Lista todas las etapas de un pipeline | objectType, pipelineId | lista de {id, label, displayOrder, probability} | crm.objects.deals.read | — | listar_etapas_pipeline_hubspot |
| [ ] | `hubspot.pipeline_stages.get` | read | GET /crm/v3/pipelines/{objectType}/{pipelineId}/stages/{stageId} | Obtiene detalles de una etapa de pipeline específica | objectType, pipelineId, stageId | {id, label, displayOrder, probability} | crm.objects.deals.read | — | — |
| [ ] | `hubspot.pipeline_stages.create` | create | POST /crm/v3/pipelines/{objectType}/{pipelineId}/stages | Crea una nueva etapa en un pipeline | objectType, pipelineId, label | {id, label, displayOrder} | crm.objects.deals.write | — | — |
| [ ] | `hubspot.pipeline_stages.update` | update | PATCH /crm/v3/pipelines/{objectType}/{pipelineId}/stages/{stageId} | Actualiza propiedades de una etapa de pipeline | objectType, pipelineId, stageId, label | {id, label actualizado} | crm.objects.deals.write | — | actualizar_etapa_pipeline_hubspot |
| [ ] | `hubspot.pipeline_stages.delete` | delete | DELETE /crm/v3/pipelines/{objectType}/{pipelineId}/stages/{stageId} | Elimina una etapa de un pipeline | objectType, pipelineId, stageId | — | crm.objects.deals.write | I | — |

### Properties (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.properties.list` | read | GET /crm/v3/properties/{objectType} | Lista todas las propiedades para un tipo de objeto (contacts, companies, deals, etc.) | objectType | lista de {name, label, type, fieldType, groupName} | crm.objects.properties.read | — | listar_propiedades_contactos_hubspot, listar_propiedades_companias_hubspot, listar_propiedades_deals_hubspot, listar_propiedades_tickets_hubspot |
| [ ] | `hubspot.properties.get` | read | GET /crm/v3/properties/{objectType}/{propertyName} | Obtiene detalles de una propiedad específica | objectType, propertyName | {name, label, type, fieldType, groupName, description, options} | crm.objects.properties.read | — | — |
| [ ] | `hubspot.properties.create` | create | POST /crm/v3/properties/{objectType} | Crea una nueva propiedad personalizada para un objeto | objectType, name, label, type, fieldType, groupName | {name, label, type} | crm.objects.properties.write | — | — |
| [ ] | `hubspot.properties.update` | update | PATCH /crm/v3/properties/{objectType}/{propertyName} | Actualiza propiedades de una propiedad personalizada | objectType, propertyName, label, description | {name, label actualizado} | crm.objects.properties.write | — | — |
| [ ] | `hubspot.properties.delete` | delete | DELETE /crm/v3/properties/{objectType}/{propertyName} | Elimina una propiedad personalizada | objectType, propertyName | — | crm.objects.properties.write | I | — |

### Property Groups (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.property_groups.list` | read | GET /crm/v3/properties/{objectType}/groups | Lista todos los grupos de propiedades para un tipo de objeto | objectType | lista de {name, label, displayOrder} | crm.objects.properties.read | — | listar_grupos_propiedades_hubspot |
| [ ] | `hubspot.property_groups.get` | read | GET /crm/v3/properties/{objectType}/groups/{groupName} | Obtiene detalles de un grupo de propiedades | objectType, groupName | {name, label, displayOrder, properties} | crm.objects.properties.read | — | — |
| [ ] | `hubspot.property_groups.create` | create | POST /crm/v3/properties/{objectType}/groups | Crea un nuevo grupo de propiedades | objectType, name, label | {name, label} | crm.objects.properties.write | — | — |
| [ ] | `hubspot.property_groups.update` | update | PATCH /crm/v3/properties/{objectType}/groups/{groupName} | Actualiza propiedades de un grupo de propiedades | objectType, groupName, label | {name, label actualizado} | crm.objects.properties.write | — | — |

### Associations (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.associations.list` | read | POST /crm/v4/associations/{fromObjectType}/{toObjectType}/batch/read | Lee las asociaciones entre dos tipos de objetos (hasta 1000) | fromObjectType, toObjectType, lista de fromIds | lista de {fromId, toIds, associationTypes} | crm.objects.associations.read | — | listar_asociaciones_hubspot |
| [ ] | `hubspot.associations.search` | read | POST /crm/v4/associations/{objectType}/all | Busca todas las asociaciones de un objeto con otros | objectType, objectId | lista de asociaciones por tipo | crm.objects.associations.read | — | buscar_asociaciones_hubspot |
| [ ] | `hubspot.associations.create` | create | POST /crm/v4/associations/{fromObjectType}/{toObjectType}/batch/create | Crea asociaciones con etiqueta entre dos objetos (hasta 2000) | fromObjectType, toObjectType, lista de {fromId, toId, type} | lista de {fromId, toId, type creado} | crm.objects.associations.write | — | asociar_objetos_hubspot |
| [ ] | `hubspot.associations.delete` | delete | POST /crm/v4/associations/{fromObjectType}/{toObjectType}/batch/archive | Elimina asociaciones entre dos objetos | fromObjectType, toObjectType, lista de {fromId, toId} | — | crm.objects.associations.write | I | — |
| [ ] | `hubspot.association_types.list` | read | GET /crm/v4/associations/{fromObjectType}/{toObjectType}/labels | Lista todos los tipos/etiquetas de asociación entre dos tipos de objetos | fromObjectType, toObjectType | lista de {id, label, category, typeId} | crm.objects.associations.read | — | listar_tipos_asociaciones_hubspot |

### Imports (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.imports.start` | create | POST /crm/imports/2026-09 | Inicia una importación de contactos, empresas u otros objetos CRM | archivo CSV/XLS, mapping, objectType | {importId, estado, createdAt} | crm.import | — | — |
| [ ] | `hubspot.imports.list` | read | GET /crm/imports/2026-09 | Lista todas las importaciones activas y completadas | limit, after | lista de {importId, estado, nombre, formato, objectsImported} | crm.import | — | — |
| [ ] | `hubspot.imports.get` | read | GET /crm/imports/2026-09/{importId} | Obtiene detalles de una importación específica | importId | {importId, estado, nombre, objectsImported, createdAt, completedAt} | crm.import | — | — |
| [ ] | `hubspot.imports.cancel` | create | POST /crm/imports/2026-09/{importId}/cancel | Cancela una importación en progreso o en cola | importId | — | crm.import | I | — |
| [ ] | `hubspot.imports.errors` | read | GET /crm/imports/2026-09/{importId}/errors | Obtiene los errores de una importación fallida | importId | lista de {fila, propiedad, errorMessage} | crm.import | — | — |

### Exports (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.exports.start` | create | POST /crm/exports/2026-09/export/async | Inicia una exportación de registros CRM (max 30 en 24h) | objectType, filterGroups, limit, fileFormat | {taskId, estado, createdAt} | crm.export | — | — |
| [ ] | `hubspot.exports.status` | read | GET /crm/exports/2026-09/export/async/tasks/{taskId}/status | Obtiene el estado de una exportación en progreso | taskId | {estado, downloadLink, createdAt, completedAt, fileSize} | crm.export | — | — |

### Leads (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.leads.list` | read | GET /crm/objects/2026-09/leads | Lista todos los leads de la cuenta | — | lista de {id, nombre, email, leadstatus} + siguiente página | crm.objects.leads.read | — | — |
| [ ] | `hubspot.leads.get` | read | GET /crm/objects/2026-09/leads/{leadId} | Obtiene detalles de un lead específico | leadId | {id, nombre, email, leadstatus, propiedades personalizadas} | crm.objects.leads.read | — | — |
| [ ] | `hubspot.leads.search` | read | POST /crm/objects/2026-09/leads/search | Busca leads por propiedades (email, estado, etc.) | filterGroups, query, limit, after | lista de leads que coinciden + siguiente página | crm.objects.leads.read | — | — |
| [ ] | `hubspot.leads.create` | create | POST /crm/objects/2026-09/leads | Crea un nuevo lead | email, firstName, lastName, leadstatus | {id, propiedades creadas} | crm.objects.leads.write | — | — |
| [ ] | `hubspot.leads.update` | update | PATCH /crm/objects/2026-09/leads/{leadId} | Actualiza propiedades de un lead | leadId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.leads.write | — | — |
| [ ] | `hubspot.leads.delete` | delete | DELETE /crm/objects/2026-09/leads/{leadId} | Elimina (archiva) un lead | leadId | — | crm.objects.leads.write | I | — |

### Invoices (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.invoices.list` | read | GET /crm/objects/2026-09/invoices | Lista todas las facturas de la cuenta | — | lista de {id, invoicenumber, amount, duedate} + siguiente página | crm.objects.invoices.read | — | — |
| [ ] | `hubspot.invoices.get` | read | GET /crm/objects/2026-09/invoices/{invoiceId} | Obtiene detalles de una factura específica | invoiceId | {id, invoicenumber, amount, duedate, lineItems, propiedades personalizadas} | crm.objects.invoices.read | — | — |
| [ ] | `hubspot.invoices.search` | read | POST /crm/objects/2026-09/invoices/search | Busca facturas por propiedades (número, monto, fecha, etc.) | filterGroups, query, limit, after | lista de facturas que coinciden + siguiente página | crm.objects.invoices.read | — | — |
| [ ] | `hubspot.invoices.create` | create | POST /crm/objects/2026-09/invoices | Crea una nueva factura | invoicenumber, amount, duedate | {id, propiedades creadas} | crm.objects.invoices.write | — | — |
| [ ] | `hubspot.invoices.update` | update | PATCH /crm/objects/2026-09/invoices/{invoiceId} | Actualiza propiedades de una factura | invoiceId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.invoices.write | — | — |
| [ ] | `hubspot.invoices.delete` | delete | DELETE /crm/objects/2026-09/invoices/{invoiceId} | Elimina (archiva) una factura | invoiceId | — | crm.objects.invoices.write | I | — |

### Orders (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.orders.list` | read | GET /crm/objects/2026-09/orders | Lista todas las órdenes de la cuenta | — | lista de {id, ordernumber, amount, orderdate} + siguiente página | crm.objects.orders.read | — | — |
| [ ] | `hubspot.orders.get` | read | GET /crm/objects/2026-09/orders/{orderId} | Obtiene detalles de una orden específica | orderId | {id, ordernumber, amount, orderdate, lineItems, propiedades personalizadas} | crm.objects.orders.read | — | — |
| [ ] | `hubspot.orders.search` | read | POST /crm/objects/2026-09/orders/search | Busca órdenes por propiedades (número, monto, fecha, etc.) | filterGroups, query, limit, after | lista de órdenes que coinciden + siguiente página | crm.objects.orders.read | — | — |
| [ ] | `hubspot.orders.create` | create | POST /crm/objects/2026-09/orders | Crea una nueva orden | ordernumber, amount, orderdate | {id, propiedades creadas} | crm.objects.orders.write | — | — |
| [ ] | `hubspot.orders.update` | update | PATCH /crm/objects/2026-09/orders/{orderId} | Actualiza propiedades de una orden | orderId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.orders.write | — | — |
| [ ] | `hubspot.orders.delete` | delete | DELETE /crm/objects/2026-09/orders/{orderId} | Elimina (archiva) una orden | orderId | — | crm.objects.orders.write | I | — |

### Appointments (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.appointments.list` | read | GET /crm/objects/2026-09/appointments | Lista todos los appointments de la cuenta | — | lista de {id, hs_timestamp, title} + siguiente página | crm.objects.appointments.read | — | — |
| [ ] | `hubspot.appointments.get` | read | GET /crm/objects/2026-09/appointments/{appointmentId} | Obtiene detalles de un appointment específico | appointmentId | {id, hs_timestamp, title, duration, propiedades personalizadas} | crm.objects.appointments.read | — | — |
| [ ] | `hubspot.appointments.search` | read | POST /crm/objects/2026-09/appointments/search | Busca appointments por propiedades (título, fecha, etc.) | filterGroups, query, limit, after | lista de appointments que coinciden + siguiente página | crm.objects.appointments.read | — | — |
| [ ] | `hubspot.appointments.create` | create | POST /crm/objects/2026-09/appointments | Crea un nuevo appointment | title, hs_timestamp | {id, propiedades creadas} | crm.objects.appointments.write | — | — |
| [ ] | `hubspot.appointments.update` | update | PATCH /crm/objects/2026-09/appointments/{appointmentId} | Actualiza propiedades de un appointment | appointmentId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.appointments.write | — | — |
| [ ] | `hubspot.appointments.delete` | delete | DELETE /crm/objects/2026-09/appointments/{appointmentId} | Elimina (archiva) un appointment | appointmentId | — | crm.objects.appointments.write | I | — |

### Conversations (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.conversations.inboxes_list` | read | GET /conversations/v3/conversations/inboxes | Lista todos los inboxes de conversaciones | limit, after | lista de {id, name, channelId} | conversations.read | — | — |
| [ ] | `hubspot.conversations.inboxes_get` | read | GET /conversations/v3/conversations/inboxes/{inboxId} | Obtiene detalles de un inbox específico | inboxId | {id, name, channelId, channelAccountId} | conversations.read | — | — |
| [ ] | `hubspot.conversations.channels_list` | read | GET /conversations/v3/conversations/channels | Lista todos los canales de conversación conectados (email, chat, etc.) | limit, after | lista de {id, name, type} | conversations.read | — | — |
| [ ] | `hubspot.conversations.threads_list` | read | GET /conversations/v3/conversations/threads | Lista todos los threads de conversación | limit, after, inboxId | lista de {id, subject, status, lastModified} | conversations.read | — | — |
| [ ] | `hubspot.conversations.threads_get` | read | GET /conversations/v3/conversations/threads/{threadId} | Obtiene detalles de un thread específico | threadId | {id, subject, status, assignee, messages, createdAt, lastModified} | conversations.read | — | — |
| [ ] | `hubspot.conversations.threads_update` | update | PATCH /conversations/v3/conversations/threads/{threadId} | Actualiza estado o restaura un thread | threadId, status | {id, status actualizado} | conversations.write | — | — |
| [ ] | `hubspot.conversations.threads_archive` | delete | DELETE /conversations/v3/conversations/threads/{threadId} | Archiva un thread de conversación | threadId | — | conversations.write | I | — |
| [ ] | `hubspot.conversations.messages_list` | read | GET /conversations/v3/conversations/threads/{threadId}/messages | Lista todos los mensajes en un thread | threadId, limit, after | lista de {id, text, sender, timestamp} | conversations.read | — | — |
| [ ] | `hubspot.conversations.messages_get` | read | GET /conversations/v3/conversations/threads/{threadId}/messages/{messageId} | Obtiene detalles de un mensaje específico | threadId, messageId | {id, text, sender, timestamp, attachments} | conversations.read | — | — |
| [ ] | `hubspot.conversations.messages_create` | create | POST /conversations/v3/conversations/threads/{threadId}/messages | Envía un nuevo mensaje o añade comentario a un thread | threadId, text, senderId | {id, timestamp, sender} | conversations.write | E | — |
| [ ] | `hubspot.conversations.threads_assign` | create | POST /conversations/v3/conversations/threads/{threadId}/assignee | Asigna un thread a un usuario específico | threadId, userId | {threadId, assigneeId} | conversations.write | — | — |
| [ ] | `hubspot.conversations.threads_unassign` | delete | DELETE /conversations/v3/conversations/threads/{threadId}/assignee | Desasigna un thread de un usuario | threadId | — | conversations.write | — | — |

### Webhooks (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.webhooks.settings_get` | read | GET /webhooks/v3/{appId}/settings | Obtiene configuración de webhooks (URL destino, concurrencia) | appId | {webhookUrl, maxConcurrentRequests} | webhooks | — | — |
| [ ] | `hubspot.webhooks.settings_update` | update | PUT /webhooks/v3/{appId}/settings | Actualiza URL destino y concurrencia de webhooks | appId, webhookUrl, maxConcurrentRequests | {webhookUrl actualizado, maxConcurrentRequests actualizado} | webhooks | — | — |
| [ ] | `hubspot.webhooks.subscriptions_list` | read | GET /webhooks/v3/{appId}/subscriptions | Lista todas las suscripciones activas a eventos | appId | lista de {id, eventType, propertyName, active} | webhooks | — | — |
| [ ] | `hubspot.webhooks.subscriptions_create` | create | POST /webhooks/v3/{appId}/subscriptions | Crea suscripción a evento (contact.create, contact.update, etc.) | appId, eventType, propertyName opcional | {subscriptionId, eventType, active} | webhooks | — | — |
| [ ] | `hubspot.webhooks.subscriptions_update` | update | PUT /webhooks/v3/{appId}/subscriptions/{subscriptionId} | Activa o pausa una suscripción | appId, subscriptionId, active | {subscriptionId, active actualizado} | webhooks | — | — |
| [ ] | `hubspot.webhooks.subscriptions_delete` | delete | DELETE /webhooks/v3/{appId}/subscriptions/{subscriptionId} | Elimina una suscripción de evento | appId, subscriptionId | — | webhooks | I | — |

### Marketing - Campaigns (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.campaigns.list` | read | GET /marketing/v3/campaigns | Lista todas las campañas de marketing | limit, offset | lista de {id, name, createdAt, status} | marketing.campaigns.read | — | — |
| [ ] | `hubspot.campaigns.get` | read | GET /marketing/v3/campaigns/{campaignId} | Obtiene detalles de una campaña específica | campaignId | {id, name, description, assets, budget, status} | marketing.campaigns.read | — | — |
| [ ] | `hubspot.campaigns.create` | create | POST /marketing/v3/campaigns | Crea una nueva campaña de marketing | name, description, budget | {id, name, createdAt} | marketing.campaigns.write | — | — |
| [ ] | `hubspot.campaigns.update` | update | PATCH /marketing/v3/campaigns/{campaignId} | Actualiza propiedades de una campaña | campaignId, name, description, budget | {id, propiedades actualizadas} | marketing.campaigns.write | — | — |
| [ ] | `hubspot.campaigns.delete` | delete | DELETE /marketing/v3/campaigns/{campaignId} | Elimina una campaña de marketing | campaignId | — | marketing.campaigns.write | I | — |

### Marketing - Emails (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.marketing_emails.list` | read | GET /marketing/v3/emails | Lista todos los emails de marketing | limit, offset | lista de {id, name, subject, createdAt} | marketing.emails.read | — | — |
| [ ] | `hubspot.marketing_emails.get` | read | GET /marketing/v3/emails/{emailId} | Obtiene detalles de un email de marketing | emailId | {id, name, subject, template, previewText, createdAt} | marketing.emails.read | — | — |
| [ ] | `hubspot.marketing_emails.create` | create | POST /marketing/v3/emails | Crea un nuevo email de marketing | name, subject, templatePath | {id, name, createdAt} | marketing.emails.write | E | — |
| [ ] | `hubspot.marketing_emails.update` | update | PATCH /marketing/v3/emails/{emailId} | Actualiza propiedades de un email de marketing | emailId, name, subject, content | {id, propiedades actualizadas} | marketing.emails.write | — | — |
| [ ] | `hubspot.marketing_emails.delete` | delete | DELETE /marketing/v3/emails/{emailId} | Elimina un email de marketing | emailId | — | marketing.emails.write | I | — |
| [ ] | `hubspot.marketing_emails.get_stats` | read | GET /marketing/v3/emails/{emailId}/stats | Obtiene estadísticas de envío de un email (abiertos, clics, etc.) | emailId | {opens, clicks, sends, bounces, delivered} | marketing.emails.read | — | — |

### Marketing - Forms (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.forms.list` | read | GET /marketing/forms/2026-09-beta | Lista todos los formularios de marketing | limit, offset | lista de {id, name, createdAt, submissionCount} | marketing.forms.read | — | — |
| [ ] | `hubspot.forms.get` | read | GET /marketing/forms/2026-09-beta/{formId} | Obtiene detalles de un formulario específico | formId | {id, name, fields, createdAt, updatedAt} | marketing.forms.read | — | — |
| [ ] | `hubspot.forms.create` | create | POST /marketing/forms/2026-09-beta | Crea un nuevo formulario de marketing | name, fields lista | {id, name, createdAt} | marketing.forms.write | E | — |
| [ ] | `hubspot.forms.update` | update | PATCH /marketing/forms/2026-09-beta/{formId} | Actualiza propiedades de un formulario | formId, name, fields | {id, propiedades actualizadas} | marketing.forms.write | — | — |
| [ ] | `hubspot.forms.delete` | delete | DELETE /marketing/forms/2026-09-beta/{formId} | Elimina un formulario de marketing | formId | — | marketing.forms.write | I | — |

### Marketing - Events (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.marketing_events.list` | read | GET /marketing/v3/marketing-events | Lista todos los eventos de marketing | limit, offset | lista de {id, eventName, createdAt} | marketing.events.read | — | — |
| [ ] | `hubspot.marketing_events.get` | read | GET /marketing/v3/marketing-events/{eventId} | Obtiene detalles de un evento de marketing | eventId | {id, eventName, externalEventId, externalAccountId, eventOrganizer, createdAt} | marketing.events.read | — | — |
| [ ] | `hubspot.marketing_events.create` | create | POST /marketing/v3/marketing-events | Crea un nuevo evento de marketing | eventName, externalEventId, externalAccountId, eventOrganizer | {id, eventName, createdAt} | marketing.events.write | E | — |
| [ ] | `hubspot.marketing_events.update` | update | PATCH /marketing/v3/marketing-events/{eventId} | Actualiza propiedades de un evento de marketing | eventId, eventName, eventOrganizer | {id, propiedades actualizadas} | marketing.events.write | — | — |
| [ ] | `hubspot.marketing_events.delete` | delete | DELETE /marketing/v3/marketing-events/{eventId} | Elimina un evento de marketing | eventId | — | marketing.events.write | I | — |

### Account Activity (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.account_activity.audit_logs` | read | GET /account-info/2026-09/activity/audit-logs | Obtiene logs de auditoría de acciones de usuarios (Enterprise) | actingUserId opcional, occurredAfter, occurredBefore | lista de {timestamp, actor, action, objectType, objectId} | account.audit_logs | — | — |
| [ ] | `hubspot.account_activity.login_history` | read | GET /account-info/2026-09/activity/login | Obtiene historial de logins de usuarios | userId opcional, fromTimestamp, toTimestamp | lista de {timestamp, userId, ipAddress, userAgent} | account.audit_logs | — | — |
| [ ] | `hubspot.account_activity.security_activity` | read | GET /account-info/2026-09/activity/security | Obtiene historial de eventos de seguridad | userId opcional, fromTimestamp, toTimestamp | lista de {timestamp, userId, eventType, details} | account.audit_logs | — | — |

### Otros Objetos CRM (Batch básicos) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.carts.list` | read | GET /crm/objects/2026-09/carts | Lista todos los carritos de compra | — | lista de {id, amount, status} + siguiente página | crm.objects.carts.read | — | — |
| [ ] | `hubspot.carts.get` | read | GET /crm/objects/2026-09/carts/{cartId} | Obtiene detalles de un carrito específico | cartId | {id, amount, lineItems, status, propiedades personalizadas} | crm.objects.carts.read | — | — |
| [ ] | `hubspot.discounts.list` | read | GET /crm/objects/2026-09/discounts | Lista todos los descuentos | — | lista de {id, name, percentageDiscount, amount} + siguiente página | crm.objects.discounts.read | — | — |
| [ ] | `hubspot.discounts.get` | read | GET /crm/objects/2026-09/discounts/{discountId} | Obtiene detalles de un descuento específico | discountId | {id, name, percentageDiscount, amount, propiedades personalizadas} | crm.objects.discounts.read | — | — |
| [ ] | `hubspot.payments.list` | read | GET /crm/objects/2026-09/payments | Lista todos los pagos | — | lista de {id, amount, paymentDate} + siguiente página | crm.objects.payments.read | — | — |
| [ ] | `hubspot.payments.get` | read | GET /crm/objects/2026-09/payments/{paymentId} | Obtiene detalles de un pago específico | paymentId | {id, amount, paymentDate, paymentStatus, propiedades personalizadas} | crm.objects.payments.read | — | — |
| [ ] | `hubspot.subscriptions.list` | read | GET /crm/objects/2026-09/subscriptions | Lista todas las suscripciones | — | lista de {id, subscriptionname, subscriptionStatus} + siguiente página | crm.objects.subscriptions.read | — | — |
| [ ] | `hubspot.subscriptions.get` | read | GET /crm/objects/2026-09/subscriptions/{subscriptionId} | Obtiene detalles de una suscripción específica | subscriptionId | {id, subscriptionname, subscriptionStatus, propiedades personalizadas} | crm.objects.subscriptions.read | — | — |

### Custom Objects (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.custom_objects.list` | read | GET /crm/objects/2026-09/{customObjectTypeId} | Lista todos los registros de un objeto personalizado | customObjectTypeId | lista de {id, propiedades} + siguiente página | crm.objects.custom.read | — | — |
| [ ] | `hubspot.custom_objects.get` | read | GET /crm/objects/2026-09/{customObjectTypeId}/{recordId} | Obtiene detalles de un registro de objeto personalizado | customObjectTypeId, recordId | {id, propiedades} | crm.objects.custom.read | — | — |
| [ ] | `hubspot.custom_objects.search` | read | POST /crm/objects/2026-09/{customObjectTypeId}/search | Busca registros de objetos personalizados | customObjectTypeId, filterGroups, query, limit, after | lista de registros que coinciden + siguiente página | crm.objects.custom.read | — | — |
| [ ] | `hubspot.custom_objects.create` | create | POST /crm/objects/2026-09/{customObjectTypeId} | Crea un nuevo registro en un objeto personalizado | customObjectTypeId, propiedades | {id, propiedades creadas} | crm.objects.custom.write | — | — |
| [ ] | `hubspot.custom_objects.update` | update | PATCH /crm/objects/2026-09/{customObjectTypeId}/{recordId} | Actualiza propiedades de un registro personalizado | customObjectTypeId, recordId, propiedades a cambiar | {id, propiedades actualizadas} | crm.objects.custom.write | — | — |
| [ ] | `hubspot.custom_objects.delete` | delete | DELETE /crm/objects/2026-09/{customObjectTypeId}/{recordId} | Elimina un registro de objeto personalizado | customObjectTypeId, recordId | — | crm.objects.custom.write | I | — |

### Portal, propietarios y otros (agregado a mano; por verificar contra la documentacion) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `hubspot.owners.list` | read | GET /crm/v3/owners | Lista los propietarios (owners) del portal | limit, after, email | lista de {id, email, nombre, userId} + siguiente pagina | crm.objects.owners.read | — | listar_owners_hubspot |
| [ ] | `hubspot.users.list` | read | GET /settings/v3/users | Lista los usuarios del portal | limit, after | lista de {id, email, roleId} + siguiente pagina | settings.users.read | — | listar_usuarios_portal_hubspot |
| [ ] | `hubspot.teams.list` | read | GET /settings/v3/users/teams | Lista los equipos del portal | - | lista de {id, name, userIds} | settings.users.teams.read | — | listar_equipos_portal_hubspot |
| [ ] | `hubspot.roles.list` | read | GET /settings/v3/users/roles | Lista los roles del portal (solo cuentas Enterprise, por verificar) | - | lista de {id, name} | settings.users.read | — | listar_roles_portal_hubspot |
| [ ] | `hubspot.owners.update` | update | — | SIN ENDPOINT PROPIO: cambiar el propietario es actualizar la propiedad hubspot_owner_id con las funciones update de cada objeto; decidir si se conserva | objectId, hubspot_owner_id | objeto actualizado | — | — | actualizar_propietario_hubspot |
| [ ] | `hubspot.dashboards.list` | read | — | NO VERIFICADO: no se encontro un endpoint publico para listar dashboards; decidir si se descarta | - | - | — | — | listar_dashboards_hubspot |
| [ ] | `hubspot.crm.get_summary` | read | — | NO ES UN ENDPOINT: resumen que la herramienta vieja calculaba juntando conteos de varios objetos; decidir si se descarta | - | conteos por objeto | — | — | resumen_general_crm_hubspot |
| [ ] | `hubspot.activities.list_history` | read | — | NO ES UN ENDPOINT UNICO: el historial se arma con las funciones de notas, llamadas, reuniones, correos y tareas asociadas; decidir si se descarta | objectId | lista de actividades | — | — | historial_actividades_hubspot |

## Observaciones de las herramientas viejas

- Es la app mas grande: 52 herramientas (31% de las 168). Conviene dividir el trabajo por objeto (contactos, companias, deals, tickets, ...) entre varios juniors.
- Las 4 `listar_propiedades_*` son la misma operacion con `object_type` distinto: candidatas a una sola funcion `hubspot.properties.list` con parametro.
- `buscar_*_por_id` son lecturas por id: en el estandar nuevo se llaman `get`.
- `BIGTOOLS_REGISTRY` tiene `hubspot: []` (vacio): el inspector del agente no conoce ninguna.
- Los objetos de CRM son datos internos del usuario, no salen al exterior; `crear_nota`/`crear_llamada`/`crear_tarea` registran actividad, no envian nada.
