# Tareas: Salesforce

- **Funciones catalogadas:** 110 · **Hechas:** 0 · **Pendientes:** 110 · App sin herramientas viejas
- **Documentación oficial:** https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_rest.htm
- **Fuentes que consultó el catálogo:** https://getknit.dev/blog/salesforce-api-directory https://developer.salesforce.com/docs/atlas.en-us.236.0.api_rest.meta/api/resources_list.htm https://developer.salesforce.com/docs/atlas.en-us.264.0.api.meta/api/sforce_api_calls_getuserinfo.htm https://resources.docs.salesforce.com/262/latest/en-us/sfdc/pdf/salesforce_soql_sosl.pdf https://developer.salesforce.com/docs/atlas.en-us.262.0.api_rest.meta/api/using_composite_resources.htm https://developer.salesforce.com/docs/atlas.en-us.240.0.api_rest.meta/api/resources_sobject_upsert.htm
- **Paginación típica:** Parámetro offset/limit (p.ej. ?offset=0&limit=200) o nextRecordsUrl para queries grandes; composite batch permite hasta 25 subrequests por llamada
- **Qué no se pudo verificar:** Scopes específicos por grupo de operaciones; restricciones de acceso por tipo de lista/dashboard; endpoints de webhooks y Apex REST custom; algunos campos de respuesta pueden variar según la configuración de la organización
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/salesforce/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `salesforce`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **OAuth 2 con refresh token**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `salesforce` |
| Variables del `.env` que necesitas | SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET, SALESFORCE_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/salesforce/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `salesforce.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización y refresh token; el usuario se autentica en Salesforce, la aplicación recibe un código que se intercambia por access_token y refresh_token |
| Duración del token (según el catálogo) | Access token dura ~2 horas por seguridad |
| Refresco (según el catálogo) | Sí, refresh token; se solicita enviando refresh_token al endpoint /services/oauth2/token con grant_type=refresh_token para obtener nuevo access_token |
| Permisos (según el catálogo) | api (permite acceso a datos vía API), refresh_token (permite renovar tokens en cualquier momento), otros scopes específicos por objeto/servicio |
| Restricciones de acceso | Acceso requiere una edición de Salesforce que tenga API habilitada; algunas operaciones restringidas a tipos de cuenta específicos (Developer, Sandbox, Production); rate limits según el plan |
| Límites de ritmo | 15.000 llamadas API por usuario por día en edición Professional; 10.000 en edición Standard; algunos endpoints con límites adicionales (p.ej. search limitado a 2.000 resultados) |
| Notas de esta app | La API vive en el `instance_url` que devuelve el login: verifica dónde lo guarda el callback. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/salesforce/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> salesforce`. | Cuenta con `provider: salesforce`, `account_id` real, `status: active` y `refresh_token` presente (`<cifrado>`) | |
| [ ] | **C3 Funciona** | `POST /internal/functions/salesforce.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> salesforce <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `ok: true` y `last_refreshed_at` nuevo en `ver` (la conexión renovó el token sola) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Salesforce. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/salesforce.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Usuario (Información del Usuario Conectado) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.user.get` ★ | read | GET /services/data/v62.0/chatter/users/me | Obtiene el perfil del usuario actual incluyendo Id, email, nombre, rol, organización | — | {id, email, firstName, lastName, address, phoneNumbers, manager, displayName} | api | — | — |

### Usuario (General) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.user.describe` | read | GET /services/data/v62.0/chatter/users | Lista todos los usuarios disponibles con sus perfiles | search | {users[], totalSize} | api | — | — |
| [ ] | `salesforce.user.search` | read | GET /services/data/v62.0/chatter/users?q={search_term} | Busca usuarios por nombre, email o atributo | search_term | {users[], totalSize} | api | — | — |
| [ ] | `salesforce.user.get_by_id` | read | GET /services/data/v62.0/chatter/users/{user_id} | Obtiene detalles de un usuario específico | user_id | {id, email, firstName, lastName, about, title, department, manager} | api | — | — |

### Cuenta (Account) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.account.list` | read | GET /services/data/v62.0/sobjects/Account | Lista todas las cuentas de la organización | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.account.get` | read | GET /services/data/v62.0/sobjects/Account/{account_id} | Obtiene detalles de una cuenta específica | account_id | {Id, Name, BillingAddress, ShippingAddress, Phone, Website, Industry, AnnualRevenue} | api | — | — |
| [ ] | `salesforce.account.search` | read | GET /services/data/v62.0/sobjects/Account?fields=Name,Phone&Name={search} | Busca cuentas por nombre u otro criterio | Name, Phone, search | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.account.create` | create | POST /services/data/v62.0/sobjects/Account | Crea una nueva cuenta | Name, BillingAddress, Phone, Website | {id, success, errors} | api | — | — |
| [ ] | `salesforce.account.update` | update | PATCH /services/data/v62.0/sobjects/Account/{account_id} | Actualiza los datos de una cuenta existente | account_id, Name, Phone, BillingAddress, Industry | {success, errors} | api | — | — |
| [ ] | `salesforce.account.delete` | delete | DELETE /services/data/v62.0/sobjects/Account/{account_id} | Elimina una cuenta (si no tiene datos vinculados) | account_id | {success} | api | I | — |
| [ ] | `salesforce.account.upsert` | update | PATCH /services/data/v62.0/sobjects/Account/{external_id_field}/{external_id_value} | Crea o actualiza una cuenta basándose en una clave externa | external_id_field, external_id_value, fields | {id, created, success} | api | — | — |

### Contacto (Contact) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.contact.list` | read | GET /services/data/v62.0/sobjects/Contact | Lista todos los contactos | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.contact.get` | read | GET /services/data/v62.0/sobjects/Contact/{contact_id} | Obtiene detalles de un contacto específico | contact_id | {Id, FirstName, LastName, Email, Phone, AccountId, Title} | api | — | — |
| [ ] | `salesforce.contact.search` | read | GET /services/data/v62.0/sobjects/Contact?LastName={name} | Busca contactos por nombre, email o cuenta | LastName, Email, AccountId | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.contact.create` | create | POST /services/data/v62.0/sobjects/Contact | Crea un nuevo contacto | FirstName, LastName, Email, Phone, AccountId | {id, success, errors} | api | — | — |
| [ ] | `salesforce.contact.update` | update | PATCH /services/data/v62.0/sobjects/Contact/{contact_id} | Actualiza los datos de un contacto | contact_id, FirstName, LastName, Email, Phone | {success, errors} | api | — | — |
| [ ] | `salesforce.contact.delete` | delete | DELETE /services/data/v62.0/sobjects/Contact/{contact_id} | Elimina un contacto | contact_id | {success} | api | I | — |
| [ ] | `salesforce.contact.upsert` | update | PATCH /services/data/v62.0/sobjects/Contact/{external_id_field}/{external_id_value} | Crea o actualiza un contacto por clave externa | external_id_field, external_id_value | {id, created, success} | api | — | — |

### Oportunidad (Lead) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.lead.list` | read | GET /services/data/v62.0/sobjects/Lead | Lista todos los prospectos | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.lead.get` | read | GET /services/data/v62.0/sobjects/Lead/{lead_id} | Obtiene detalles de un prospecto específico | lead_id | {Id, FirstName, LastName, Email, Phone, Company, Status, Rating} | api | — | — |
| [ ] | `salesforce.lead.search` | read | GET /services/data/v62.0/sobjects/Lead?Email={email} | Busca prospectos por email, empresa o criterio | Email, Company, Status | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.lead.create` | create | POST /services/data/v62.0/sobjects/Lead | Crea un nuevo prospecto | FirstName, LastName, Email, Company | {id, success, errors} | api | — | — |
| [ ] | `salesforce.lead.update` | update | PATCH /services/data/v62.0/sobjects/Lead/{lead_id} | Actualiza los datos de un prospecto | lead_id, Status, Rating, Email | {success, errors} | api | — | — |
| [ ] | `salesforce.lead.delete` | delete | DELETE /services/data/v62.0/sobjects/Lead/{lead_id} | Elimina un prospecto | lead_id | {success} | api | I | — |
| [ ] | `salesforce.lead.upsert` | update | PATCH /services/data/v62.0/sobjects/Lead/{external_id_field}/{external_id_value} | Crea o actualiza un prospecto por clave externa | external_id_field, external_id_value | {id, created, success} | api | — | — |

### Oportunidad (Opportunity) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.opportunity.list` | read | GET /services/data/v62.0/sobjects/Opportunity | Lista todas las oportunidades | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.opportunity.get` | read | GET /services/data/v62.0/sobjects/Opportunity/{opportunity_id} | Obtiene detalles de una oportunidad | opportunity_id | {Id, Name, StageName, Amount, CloseDate, AccountId, OwnerId} | api | — | — |
| [ ] | `salesforce.opportunity.search` | read | GET /services/data/v62.0/sobjects/Opportunity?StageName={stage} | Busca oportunidades por etapa, monto, cuenta | StageName, Amount, AccountId | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.opportunity.create` | create | POST /services/data/v62.0/sobjects/Opportunity | Crea una nueva oportunidad | Name, AccountId, StageName, CloseDate | {id, success, errors} | api | — | — |
| [ ] | `salesforce.opportunity.update` | update | PATCH /services/data/v62.0/sobjects/Opportunity/{opportunity_id} | Actualiza una oportunidad existente | opportunity_id, StageName, Amount, CloseDate | {success, errors} | api | — | — |
| [ ] | `salesforce.opportunity.delete` | delete | DELETE /services/data/v62.0/sobjects/Opportunity/{opportunity_id} | Elimina una oportunidad | opportunity_id | {success} | api | I | — |
| [ ] | `salesforce.opportunity.upsert` | update | PATCH /services/data/v62.0/sobjects/Opportunity/{external_id_field}/{external_id_value} | Crea o actualiza una oportunidad por clave externa | external_id_field, external_id_value | {id, created, success} | api | — | — |

### Caso (Case) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.case.list` | read | GET /services/data/v62.0/sobjects/Case | Lista todos los casos | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.case.get` | read | GET /services/data/v62.0/sobjects/Case/{case_id} | Obtiene detalles de un caso específico | case_id | {Id, CaseNumber, Subject, Description, Status, Priority, ContactId, AccountId} | api | — | — |
| [ ] | `salesforce.case.search` | read | GET /services/data/v62.0/sobjects/Case?Status={status} | Busca casos por estado, prioridad o contacto | Status, Priority, ContactId | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.case.create` | create | POST /services/data/v62.0/sobjects/Case | Crea un nuevo caso | Subject, Description, ContactId, AccountId | {id, success, errors} | api | — | — |
| [ ] | `salesforce.case.update` | update | PATCH /services/data/v62.0/sobjects/Case/{case_id} | Actualiza un caso existente | case_id, Status, Priority, Subject | {success, errors} | api | — | — |
| [ ] | `salesforce.case.delete` | delete | DELETE /services/data/v62.0/sobjects/Case/{case_id} | Elimina un caso | case_id | {success} | api | I | — |
| [ ] | `salesforce.case.upsert` | update | PATCH /services/data/v62.0/sobjects/Case/{external_id_field}/{external_id_value} | Crea o actualiza un caso por clave externa | external_id_field, external_id_value | {id, created, success} | api | — | — |

### Tarea (Task) (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.task.list` | read | GET /services/data/v62.0/sobjects/Task | Lista todas las tareas | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.task.get` | read | GET /services/data/v62.0/sobjects/Task/{task_id} | Obtiene detalles de una tarea | task_id | {Id, Subject, Status, Priority, DueDate, WhoId, WhatId, OwnerId} | api | — | — |
| [ ] | `salesforce.task.create` | create | POST /services/data/v62.0/sobjects/Task | Crea una nueva tarea | Subject, Status, DueDate, WhoId, WhatId | {id, success, errors} | api | — | — |
| [ ] | `salesforce.task.update` | update | PATCH /services/data/v62.0/sobjects/Task/{task_id} | Actualiza una tarea existente | task_id, Status, DueDate, Subject | {success, errors} | api | — | — |
| [ ] | `salesforce.task.delete` | delete | DELETE /services/data/v62.0/sobjects/Task/{task_id} | Elimina una tarea | task_id | {success} | api | I | — |
| [ ] | `salesforce.task.mark_completed` | update | PATCH /services/data/v62.0/sobjects/Task/{task_id} | Marca una tarea como completada | task_id | {success} | api | — | — |

### Evento (Event) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.event.list` | read | GET /services/data/v62.0/sobjects/Event | Lista todos los eventos del calendario | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.event.get` | read | GET /services/data/v62.0/sobjects/Event/{event_id} | Obtiene detalles de un evento | event_id | {Id, Subject, StartDateTime, EndDateTime, WhoId, WhatId, OwnerId, Location} | api | — | — |
| [ ] | `salesforce.event.create` | create | POST /services/data/v62.0/sobjects/Event | Crea un nuevo evento de calendario | Subject, StartDateTime, EndDateTime, WhoId, WhatId | {id, success, errors} | api | — | — |
| [ ] | `salesforce.event.update` | update | PATCH /services/data/v62.0/sobjects/Event/{event_id} | Actualiza un evento existente | event_id, StartDateTime, EndDateTime, Subject | {success, errors} | api | — | — |
| [ ] | `salesforce.event.delete` | delete | DELETE /services/data/v62.0/sobjects/Event/{event_id} | Elimina un evento | event_id | {success} | api | I | — |

### Campaña (Campaign) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.campaign.list` | read | GET /services/data/v62.0/sobjects/Campaign | Lista todas las campañas | limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.campaign.get` | read | GET /services/data/v62.0/sobjects/Campaign/{campaign_id} | Obtiene detalles de una campaña | campaign_id | {Id, Name, Status, StartDate, EndDate, BudgetedCost, ActiveCampaignMembers} | api | — | — |
| [ ] | `salesforce.campaign.create` | create | POST /services/data/v62.0/sobjects/Campaign | Crea una nueva campaña | Name, Status, StartDate, BudgetedCost | {id, success, errors} | api | — | — |
| [ ] | `salesforce.campaign.update` | update | PATCH /services/data/v62.0/sobjects/Campaign/{campaign_id} | Actualiza una campaña existente | campaign_id, Status, BudgetedCost, EndDate | {success, errors} | api | — | — |
| [ ] | `salesforce.campaign.delete` | delete | DELETE /services/data/v62.0/sobjects/Campaign/{campaign_id} | Elimina una campaña | campaign_id | {success} | api | I | — |

### Nota (Note) (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.note.create` | create | POST /services/data/v62.0/sobjects/Note | Adjunta una nota a un registro | Title, Body, ParentId | {id, success, errors} | api | — | — |
| [ ] | `salesforce.note.get` | read | GET /services/data/v62.0/sobjects/Note/{note_id} | Obtiene una nota específica | note_id | {Id, Title, Body, ParentId, CreatedDate, CreatedById} | api | — | — |
| [ ] | `salesforce.note.update` | update | PATCH /services/data/v62.0/sobjects/Note/{note_id} | Actualiza una nota existente | note_id, Title, Body | {success, errors} | api | — | — |
| [ ] | `salesforce.note.delete` | delete | DELETE /services/data/v62.0/sobjects/Note/{note_id} | Elimina una nota | note_id | {success} | api | I | — |

### sObject Genérico (Operaciones Base) (12)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.sobject.describe_global` | read | GET /services/data/v62.0/sobjects | Describe todos los sObjects disponibles en la organización | — | {sobjects[], encoding, maxBatchSize} | api | — | — |
| [ ] | `salesforce.sobject.describe` | read | GET /services/data/v62.0/sobjects/{sobject_type}/describe | Describe completamente un sObject incluyendo campos y relaciones | sobject_type | {name, fields[], recordTypeInfos[], childRelationships[]} | api | — | — |
| [ ] | `salesforce.sobject.get_metadata` | read | GET /services/data/v62.0/sobjects/{sobject_type} | Obtiene metadatos básicos de un sObject | sobject_type | {objectDescribe, recentItems[], urls} | api | — | — |
| [ ] | `salesforce.sobject.list_by_type` | read | GET /services/data/v62.0/sobjects/{sobject_type}?limit={limit} | Lista registros de un sObject genérico | sobject_type, limit, offset | {records[], totalSize} | api | — | — |
| [ ] | `salesforce.sobject.get_by_type` | read | GET /services/data/v62.0/sobjects/{sobject_type}/{record_id} | Obtiene un registro de un sObject genérico | sobject_type, record_id | {Id, fields...} | api | — | — |
| [ ] | `salesforce.sobject.get_by_external_id` | read | GET /services/data/v62.0/sobjects/{sobject_type}/{external_id_field}/{external_id_value} | Obtiene un registro por clave externa | sobject_type, external_id_field, external_id_value | {Id, fields...} | api | — | — |
| [ ] | `salesforce.sobject.create_by_type` | create | POST /services/data/v62.0/sobjects/{sobject_type} | Crea un registro de un sObject genérico | sobject_type, fields | {id, success, errors} | api | — | — |
| [ ] | `salesforce.sobject.update_by_type` | update | PATCH /services/data/v62.0/sobjects/{sobject_type}/{record_id} | Actualiza un registro de un sObject genérico | sobject_type, record_id, fields | {success, errors} | api | — | — |
| [ ] | `salesforce.sobject.delete_by_type` | delete | DELETE /services/data/v62.0/sobjects/{sobject_type}/{record_id} | Elimina un registro de un sObject genérico | sobject_type, record_id | {success} | api | I | — |
| [ ] | `salesforce.sobject.upsert_by_type` | update | PATCH /services/data/v62.0/sobjects/{sobject_type}/{external_id_field}/{external_id_value} | Crea o actualiza un registro por clave externa | sobject_type, external_id_field, external_id_value | {id, created, success} | api | — | — |
| [ ] | `salesforce.sobject.get_deleted` | read | GET /services/data/v62.0/sobjects/{sobject_type}/deleted | Obtiene los Ids de registros eliminados en un período | sobject_type, start, end | {deletedRecords[], ids[]} | api | — | — |
| [ ] | `salesforce.sobject.get_updated` | read | GET /services/data/v62.0/sobjects/{sobject_type}/updated | Obtiene los Ids de registros actualizados en un período | sobject_type, start, end | {ids[], timestamp} | api | — | — |

### SOQL - Consultas (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.soql.query` | read | GET /services/data/v62.0/query?q={soql_query} | Ejecuta una consulta SOQL que devuelve resultados | soql_query | {records[], totalSize, done, nextRecordsUrl} | api | — | — |
| [ ] | `salesforce.soql.query_more` | read | GET /services/data/v62.0/query/{query_locator} | Obtiene más resultados de una consulta anterior usando el localizador | query_locator | {records[], totalSize, done, nextRecordsUrl} | api | — | — |
| [ ] | `salesforce.soql.query_all` | read | GET /services/data/v62.0/queryAll?q={soql_query} | Ejecuta una consulta SOQL incluyendo registros eliminados | soql_query | {records[], totalSize, done, nextRecordsUrl} | api | — | — |

### SOSL - Búsqueda (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.sosl.search` | read | GET /services/data/v62.0/search?q={sosl_query} | Ejecuta una búsqueda SOSL por texto contra el índice | sosl_query | {searchRecords[], objectSearchResult[]} | api | — | — |
| [ ] | `salesforce.sosl.search_parameterized` | read | GET /services/data/v62.0/parameterizedSearch | Ejecuta una búsqueda parametrizada con filtros complejos | search, searchType, fields, where | {searchRecords[], objectSearchResult[]} | api | — | — |

### Operaciones Compuestas y Batch (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.composite.batch` | create | POST /services/data/v62.0/composite/batch | Ejecuta hasta 25 solicitudes distintas en una llamada | batchRequests[], allOrNone | {hasErrors, results[]} | api | — | — |
| [ ] | `salesforce.composite.tree` | create | POST /services/data/v62.0/composite/tree/{sobject_type} | Crea registros anidados (árbol) de múltiples sObjects en una llamada | sobject_type, records[] | {hasErrors, results[], id} | api | — | — |
| [ ] | `salesforce.composite.multisob` | create | POST /services/data/v62.0/composite | Ejecuta consultas dependientes donde cada subrequesta usa resultados de otra | compositeRequest[] | {compositeResponse[]} | api | — | — |

### Chatter (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.chatter.feeds` | read | GET /services/data/v62.0/chatter/feeds/news | Obtiene los feeds de noticias del usuario | limit | {items[], currentPageUrl, nextPageUrl, previousPageUrl} | api | — | — |
| [ ] | `salesforce.chatter.post` | create | POST /services/data/v62.0/chatter/feeds/news/feed_items | Publica en el feed de noticias | body, feedItemType | {id, success, createdDate} | api | E | — |
| [ ] | `salesforce.chatter.comment` | create | POST /services/data/v62.0/chatter/feed_items/{feed_item_id}/comments | Comenta en un elemento del feed | feed_item_id, body | {id, createdDate, createdBy} | api | E | — |
| [ ] | `salesforce.chatter.groups` | read | GET /services/data/v62.0/chatter/groups | Lista los grupos de Chatter disponibles | limit | {groups[], currentPageUrl} | api | — | — |
| [ ] | `salesforce.chatter.group_get` | read | GET /services/data/v62.0/chatter/groups/{group_id} | Obtiene detalles de un grupo Chatter | group_id | {id, name, description, memberCount, owner} | api | — | — |

### Analytics - Reportes y Dashboards (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.analytics.reports_list` | read | GET /services/data/v62.0/analytics/reports | Lista todos los reportes disponibles | limit, offset | {reports[], totalSize} | api | — | — |
| [ ] | `salesforce.analytics.report_get` | read | GET /services/data/v62.0/analytics/reports/{report_id} | Obtiene detalles y datos de un reporte específico | report_id | {reportMetadata{}, factMap{}, groupingsDown[], groupingsAcross[]} | api | — | — |
| [ ] | `salesforce.analytics.report_run` | read | POST /services/data/v62.0/analytics/reports/{report_id}/instances | Ejecuta un reporte con parámetros opcionales | report_id, reportMetadata | {id, instanceUrl, success} | api | — | — |
| [ ] | `salesforce.analytics.dashboards_list` | read | GET /services/data/v62.0/analytics/dashboards | Lista todos los dashboards disponibles | limit, offset | {dashboards[], totalSize} | api | — | — |
| [ ] | `salesforce.analytics.dashboard_get` | read | GET /services/data/v62.0/analytics/dashboards/{dashboard_id} | Obtiene detalles de un dashboard | dashboard_id | {id, title, description, components[], lastModifiedDate} | api | — | — |
| [ ] | `salesforce.analytics.dashboard_component` | read | GET /services/data/v62.0/analytics/dashboards/{dashboard_id}/dashboard_components/{component_id} | Obtiene los datos de un componente del dashboard | dashboard_id, component_id | {componentData[], config} | api | — | — |

### Límites y Uso (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.limits.get` | read | GET /services/data/v62.0/limits | Obtiene los límites de la organización y su uso actual | — | {Api_Calls{}, Daily_API_Calls{}, Batch_Apex_Execution_Minutes{}} | api | — | — |

### Elementos Recientes (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.recent.get` | read | GET /services/data/v62.0/recent | Obtiene los elementos visualizados recientemente por el usuario | limit | {records[], currentPageUrl} | api | — | — |

### Vistas de Lista (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.list_views.describe` | read | GET /services/data/v62.0/sobjects/{sobject_type}/listviews | Obtiene las vistas de lista disponibles para un sObject | sobject_type | {listviews[], currentPageUrl} | api | — | — |
| [ ] | `salesforce.list_views.run` | read | GET /services/data/v62.0/sobjects/{sobject_type}/listviews/{list_view_id}/results | Ejecuta una vista de lista y obtiene sus resultados | sobject_type, list_view_id | {records[], totalSize, currentPageUrl} | api | — | — |

### Tipos de Registro (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.record_type.get` | read | GET /services/data/v62.0/sobjects/{sobject_type}/describe/recordTypes | Obtiene los tipos de registro disponibles para un sObject | sobject_type | {recordTypes[]} | api | — | — |

### Listas Desplegables (Picklists) (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.picklist.get` | read | GET /services/data/v62.0/sobjects/{sobject_type}/describe | Obtiene los valores de listas desplegables desde descripción | sobject_type, field_name | {fields[].picklistValues[]} | api | — | — |

### Metadatos y Tooling (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.metadata.describe` | read | GET /services/data/v62.0/metadata | Accede a los recursos de metadatos de la API Metadata | — | {metadata resources} | api | — | — |
| [ ] | `salesforce.tooling.describe` | read | GET /services/data/v62.0/tooling | Accede a los recursos de la Tooling API | — | {tooling resources} | api | — | — |

### Datos (Sincronización y Acceso) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.data.version` | read | GET /services/data | Lista las versiones disponibles de la API REST | — | {version[], label, urls} | api | — | — |
| [ ] | `salesforce.data.version_resources` | read | GET /services/data/v62.0 | Lista los recursos disponibles en una versión específica | version | {sobjects, query, queryAll, search, limits, recent, tooling} | api | — | — |

### Bulk API 2.0 (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.bulk.job_create` | create | POST /services/data/v62.0/jobs/ingest | Crea un trabajo de carga masiva | object, operation | {id, state, createdDate} | api | — | — |
| [ ] | `salesforce.bulk.job_get` | read | GET /services/data/v62.0/jobs/ingest/{job_id} | Obtiene el estado de un trabajo de carga masiva | job_id | {id, state, numberBatchesQueued, numberBatchesInProgress, numberBatchesFailed} | api | — | — |
| [ ] | `salesforce.bulk.file_upload` | create | PUT /services/data/v62.0/jobs/ingest/{job_id}/batches | Sube datos en formato CSV para procesar en lotes | job_id, csv_data | {numberBatchesQueued, numberRecordsProcessed} | api | — | — |
| [ ] | `salesforce.bulk.job_run` | create | PATCH /services/data/v62.0/jobs/ingest/{job_id} | Ejecuta o cancela un trabajo de carga masiva | job_id, state | {id, state} | api | — | — |

### Bulk Query 2.0 (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.bulk_query.create` | create | POST /services/data/v62.0/jobs/query | Crea un trabajo de consulta masiva | query, object | {id, state, createdDate} | api | — | — |
| [ ] | `salesforce.bulk_query.get` | read | GET /services/data/v62.0/jobs/query/{job_id} | Obtiene el estado de un trabajo de consulta masiva | job_id | {id, state, numberBatchesQueued, numberRecordsProcessed} | api | — | — |
| [ ] | `salesforce.bulk_query.results` | read | GET /services/data/v62.0/jobs/query/{job_id}/results | Descarga los resultados de una consulta masiva | job_id | {csv_data} | api | — | — |

### Acciones Invocables (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `salesforce.actions.standard_list` | read | GET /services/data/v62.0/actions/standard | Lista las acciones estándar disponibles | — | {actions[]} | api | — | — |
| [ ] | `salesforce.actions.custom_list` | read | GET /services/data/v62.0/actions/custom | Lista las acciones personalizadas disponibles | — | {actions[]} | api | — | — |
| [ ] | `salesforce.actions.invoke` | create | POST /services/data/v62.0/actions/custom/{action_name} | Invoca una acción personalizada | action_name, inputs | {success, outputs[], errors[]} | api | E | — |
