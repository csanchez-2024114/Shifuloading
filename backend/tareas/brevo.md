# Tareas: Brevo

- **Funciones catalogadas:** 289 · **Hechas:** 3 · **Pendientes:** 286 · App sin herramientas viejas
- **Documentación oficial:** https://developers.brevo.com/reference
- **Fuentes que consultó el catálogo:** https://developers.brevo.com/reference https://developers.brevo.com/llms-full.txt https://developers.brevo.com/docs/how-it-works https://developers.brevo.com/reference/get-account https://developers.brevo.com/reference/get-contacts https://developers.brevo.com/reference/create-email-campaign
- **Paginación típica:** limit (defecto 50, máx 1000) y offset; algunos endpoints devuelven campo `count` y `next`
- **Qué no se pudo verificar:** Scopes OAuth exactos, límites de ritmo específicos por endpoint, duración exacta access token
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/brevo/` ([plantilla](../app/functions/apps/_template/README.md)) (**ya existe**).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `brevo`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **clave de API**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `brevo` |
| Variables del `.env` que necesitas | (ninguna: la clave la pone el usuario) |
| Conectar (caso C1) | `POST /api/v1/integrations/brevo/key   con cuerpo {"api_key": "<clave de tu cuenta de prueba de Brevo>"}` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `brevo.account.get` |
| Cómo se autentica (según el catálogo) | API key en header `api-key` o OAuth 2.0 (token tipo portador) |
| Duración del token (según el catálogo) | API key permanente (no caduca); access token OAuth: duración no especificada en docs |
| Refresco (según el catálogo) | Para OAuth 2.0, usar refresh token (flujo no detallado en docs públicos) |
| Permisos (según el catálogo) | API key otorga acceso completo; OAuth 2.0 usa scopes (no listados en docs públicos) |
| Restricciones de acceso | Revisión de aplicación requerida para OAuth; planes de pago influyen en características disponibles (eCommerce, CRM, etc.) |
| Límites de ritmo | Límites de ritmo no especificados en docs públicos; paginación máx 1000 registros por página |
| Notas de esta app | Ya hay 3 funciones nuevas (marca D) y su prueba en `test/functions/apps/test_brevo.py`. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Obtener una API key de tu cuenta de prueba de Brevo (panel de Brevo → SMTP y API). | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `POST /api/v1/integrations/brevo/key   con cuerpo {"api_key": "<clave de tu cuenta de prueba de Brevo>"}` con el JWT. | 200 y la cuenta guardada; con una clave inventada debe rechazarla | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> brevo`. | Cuenta con `provider: brevo`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/brevo.account.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> brevo <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de Brevo. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/brevo.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Cuenta (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [x] | `brevo.account.get` ★ | read | GET /v3/account | Obtiene detalles de cuenta: organización, usuario, plan, créditos | (ninguno) | id_org, id_usuario, empresa, plan, créditos, relay, CRM, enterprise | (ninguno) | — | brevo.account.get |

### Correo transaccional (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.smtp_email.send` | create | POST /v3/smtp/email | Envía un email transaccional con contenido estático o dinámico | to, subject, htmlContent o templateId | message_id, uuid | (ninguno) | E | — |
| [ ] | `brevo.smtp_email.send_batch` | create | POST /v3/smtp/email | Envía hasta 1000 emails personalizados en una llamada (batch) | messageVersions (array) | lista de message_ids | (ninguno) | E | — |
| [ ] | `brevo.smtp_email.list` | read | GET /v3/smtp/email | Lista emails transaccionales enviados con filtros | limit, offset, email_filter | lista de emails + count + next_page | (ninguno) | — | — |
| [ ] | `brevo.smtp_email.get` | read | GET /v3/smtp/email/{id} | Obtiene contenido personalizado de un email enviado | id | contenido, variables, variables_by_template | (ninguno) | — | — |
| [ ] | `brevo.smtp_email.delete_scheduled` | delete | DELETE /v3/smtp/email/{id} | Elimina emails programados por id de batch o mensaje | batch_id o message_id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.smtp_email.get_scheduled` | read | GET /v3/smtp/email/scheduled/{id} | Obtiene detalles de emails programados | id | scheduled_date, subject, to | (ninguno) | — | — |
| [ ] | `brevo.smtp_hardbounces.delete` | delete | DELETE /v3/smtp/hardbounces | Elimina registros de hardbounce | (ninguno) | count_deleted | (ninguno) | — | — |

### Plantillas transaccionales (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [x] | `brevo.templates.list` | read | GET /v3/smtp/templates | Lista plantillas de email transaccional | limit, offset, sort | lista de {id, nombre, estado} + count | (ninguno) | — | brevo.templates.list |
| [ ] | `brevo.templates.create` | create | POST /v3/smtp/templates | Crea nueva plantilla transaccional | name, subject, htmlContent | template_id | (ninguno) | — | — |
| [ ] | `brevo.templates.get` | read | GET /v3/smtp/templates/{id} | Obtiene detalles de plantilla | id | nombre, subject, html, estado, creado_en | (ninguno) | — | — |
| [ ] | `brevo.templates.update` | update | PUT /v3/smtp/templates/{id} | Actualiza plantilla existente | id, subject, htmlContent | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.templates.delete` | delete | DELETE /v3/smtp/templates/{id} | Elimina plantilla inactiva | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.templates.preview` | read | POST /v3/smtp/templates/{id}/preview | Genera vista previa renderizada de plantilla | id, variables | html_renderizado | (ninguno) | — | — |
| [ ] | `brevo.templates.send_test` | create | POST /v3/smtp/templates/{id}/sendTest | Envía plantilla a lista de prueba | id, emails | test_sent | (ninguno) | E | — |

### Estadísticas correo transaccional (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.smtp_stats.events` | read | GET /v3/smtp/statistics/events | Obtiene eventos transaccionales sin agregar (individual) | startDate, endDate, limit, offset | lista de eventos {timestamp, type, email, bounce_type} | (ninguno) | — | — |
| [ ] | `brevo.smtp_stats.aggregated` | read | GET /v3/smtp/statistics/aggregated | Obtiene estadísticas agregadas por rango de tiempo | startDate, endDate, days | sent, bounce, complaint, unsubscribe, clicked, opened | (ninguno) | — | — |
| [ ] | `brevo.smtp_stats.report` | read | GET /v3/smtp/statistics/report | Obtiene datos agregados diarios de email transaccional | startDate, endDate | datos diarios: sent, bounce, spam, etc | (ninguno) | — | — |
| [ ] | `brevo.smtp_log.delete` | delete | DELETE /v3/smtp/log/{id} | Elimina entrada individual de log SMTP | id | (vacío) | (ninguno) | — | — |

### Contactos bloqueados (transaccional) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.smtp_blocked_contacts.list` | read | GET /v3/smtp/blockedContacts | Obtiene lista de contactos bloqueados o desuscr. transaccional | (ninguno) | lista de {email, blocked_reason, blocked_date} | (ninguno) | — | — |
| [ ] | `brevo.smtp_blocked_contacts.unblock` | update | PUT /v3/smtp/blockedContacts/{email} | Desbloquea o resuscribe contacto transaccional | email | (vacío) | (ninguno) | — | — |

### Dominios bloqueados (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.smtp_blocked_domains.list` | read | GET /v3/smtp/blockedDomains | Obtiene lista de dominios bloqueados | (ninguno) | lista de dominios | (ninguno) | — | — |
| [ ] | `brevo.smtp_blocked_domains.add` | create | POST /v3/smtp/blockedDomains | Agrega dominio a lista bloqueada | domain | (vacío) | (ninguno) | E | — |
| [ ] | `brevo.smtp_blocked_domains.delete` | delete | DELETE /v3/smtp/blockedDomains/{domain} | Desbloquea dominio | domain | (vacío) | (ninguno) | — | — |

### Correo inbound (recibido) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.inbound_events.list` | read | GET /v3/inbound/events | Obtiene lista de eventos para emails recibidos | (ninguno) | lista de eventos con uuid, timestamp, from, to | (ninguno) | — | — |
| [ ] | `brevo.inbound_events.get` | read | GET /v3/inbound/events/{uuid} | Obtiene historial de eventos para email recibido específico | uuid | eventos con detalles: timestamp, type, from, to | (ninguno) | — | — |
| [ ] | `brevo.inbound_attachment.download` | read | GET /v3/inbound/attachment/{token} | Descarga adjunto recibido con token | token | archivo binario | (ninguno) | — | — |

### SMS transaccional (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.sms_transactional.send` | create | POST /v3/transactionalSMS/sms | Envía SMS a número móvil de forma asincrónica | to, content, sender | message_id | (ninguno) | E | — |
| [ ] | `brevo.sms_transactional_stats.events` | read | GET /v3/transactionalSMS/statistics/events | Obtiene eventos SMS individuales | startDate, endDate, limit, offset | lista de eventos {timestamp, type, phone, status} | (ninguno) | — | — |
| [ ] | `brevo.sms_transactional_stats.report` | read | GET /v3/transactionalSMS/statistics/report | Obtiene resumen diario SMS | startDate, endDate | datos diarios: sent, bounce, unsubscribe, etc | (ninguno) | — | — |
| [ ] | `brevo.sms_transactional_stats.aggregated` | read | GET /v3/transactionalSMS/statistics/aggregated | Obtiene estadísticas SMS agregadas | startDate, endDate, days | sent, bounce, complaint, unsubscribe, clicked | (ninguno) | — | — |

### WhatsApp transaccional (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.whatsapp_transactional.send` | create | POST /v3/whatsapp/sendMessage | Envía mensaje WhatsApp | to, content o templateId | message_id | (ninguno) | E | — |
| [ ] | `brevo.whatsapp_transactional_stats.events` | read | GET /v3/whatsapp/statistics/events | Obtiene eventos WhatsApp sin agregar | startDate, endDate, limit, offset | lista de eventos {timestamp, type, phone, status} | (ninguno) | — | — |

### Campañas email (13)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.campaigns_email.list` | read | GET /v3/emailCampaigns | Obtiene todas las campañas email creadas | limit, offset, sort, status | lista de {id, nombre, estado, created} + count | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.create` | create | POST /v3/emailCampaigns | Crea nueva campaña email | name, sender, htmlContent o htmlUrl o templateId | campaign_id | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.get` | read | GET /v3/emailCampaigns/{id} | Obtiene detalles de campaña email | id | nombre, estado, html, recipientes, estadísticas | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.update` | update | PUT /v3/emailCampaigns/{id} | Modifica campaña email | id, name, subject, etc | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.delete` | delete | DELETE /v3/emailCampaigns/{id} | Elimina campaña email | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.campaigns_email.send_now` | create | POST /v3/emailCampaigns/{id}/sendNow | Envía campaña email inmediatamente | id | send_date | (ninguno) | E, I | — |
| [ ] | `brevo.campaigns_email.send_test` | create | POST /v3/emailCampaigns/{id}/sendTest | Envía campaña a lista de prueba | id, emails | test_sent | (ninguno) | E | — |
| [ ] | `brevo.campaigns_email.update_status` | update | PUT /v3/emailCampaigns/{id}/status | Modifica estado de campaña | id, status | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.get_report` | read | GET /v3/emailCampaigns/{id}/report | Obtiene estadísticas de campaña | id | sent, opened, clicked, bounce, unsubscribe | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.send_report` | create | POST /v3/emailCampaigns/{id}/report/send | Envía reporte de campaña | id, to | report_sent | (ninguno) | E | — |
| [ ] | `brevo.campaigns_email.get_share_link` | read | POST /v3/emailCampaigns/{id}/shareLink | Obtiene URL compartida de plantilla | id | share_link | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.export_recipients` | create | POST /v3/emailCampaigns/{id}/exportRecipients | Exporta destinatarios de campaña | id | export_task_id | (ninguno) | — | — |
| [ ] | `brevo.campaigns_email.get_ab_test_results` | read | GET /v3/emailCampaigns/{id}/abTestResults | Obtiene resultados de test A/B | id | winner_variant, stats_A, stats_B | (ninguno) | — | — |

### Campañas SMS (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.campaigns_sms.list` | read | GET /v3/smsCampaigns | Obtiene información de todas las campañas SMS | limit, offset, sort | lista de {id, nombre, estado} + count | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.create` | create | POST /v3/smsCampaigns | Crea campaña SMS | name, content, recipients | campaign_id | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.get` | read | GET /v3/smsCampaigns/{id} | Obtiene detalles de campaña SMS | id | nombre, contenido, estado, estadísticas | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.update` | update | PUT /v3/smsCampaigns/{id} | Modifica campaña SMS | id, name, content, etc | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.delete` | delete | DELETE /v3/smsCampaigns/{id} | Elimina campaña SMS | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.campaigns_sms.send_now` | create | POST /v3/smsCampaigns/{id}/sendNow | Envía campaña SMS inmediatamente | id | send_date | (ninguno) | E, I | — |
| [ ] | `brevo.campaigns_sms.update_status` | update | PUT /v3/smsCampaigns/{id}/status | Modifica estado de campaña SMS | id, status | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.send_test` | create | POST /v3/smsCampaigns/{id}/sendTest | Envía SMS de prueba | id, phones | test_sent | (ninguno) | E | — |
| [ ] | `brevo.campaigns_sms.export_recipients` | create | POST /v3/smsCampaigns/{id}/exportRecipients | Exporta destinatarios de campaña SMS | id | export_task_id | (ninguno) | — | — |
| [ ] | `brevo.campaigns_sms.send_report` | create | POST /v3/smsCampaigns/{id}/report/send | Envía reporte de campaña SMS | id, to | report_sent | (ninguno) | E | — |

### Campañas WhatsApp (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.campaigns_whatsapp.list` | read | GET /v3/whatsappCampaigns | Obtiene todas las campañas WhatsApp creadas | limit, offset | lista de campañas | (ninguno) | — | — |
| [ ] | `brevo.campaigns_whatsapp.create` | create | POST /v3/whatsappCampaigns | Crea y envía campaña WhatsApp | name, content, recipients | campaign_id | (ninguno) | E | — |
| [ ] | `brevo.campaigns_whatsapp.get` | read | GET /v3/whatsappCampaigns/{id} | Obtiene detalles de campaña WhatsApp | id | nombre, contenido, estado, estadísticas | (ninguno) | — | — |
| [ ] | `brevo.campaigns_whatsapp.update` | update | PUT /v3/whatsappCampaigns/{id} | Modifica campaña WhatsApp | id, name, content, etc | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.campaigns_whatsapp.delete` | delete | DELETE /v3/whatsappCampaigns/{id} | Elimina campaña WhatsApp | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.templates_whatsapp.list` | read | GET /v3/whatsappTemplates | Obtiene todas las plantillas WhatsApp | limit, offset | lista de plantillas | (ninguno) | — | — |
| [ ] | `brevo.templates_whatsapp.create` | create | POST /v3/whatsappTemplates | Crea plantilla WhatsApp | name, content, category | template_id | (ninguno) | — | — |
| [ ] | `brevo.templates_whatsapp.send_for_approval` | create | POST /v3/whatsappTemplates/{id}/approval | Envía plantilla WhatsApp para aprobación | id | approval_submitted | (ninguno) | E | — |
| [ ] | `brevo.whatsapp_config.get` | read | GET /v3/whatsapp/config | Obtiene información de cuenta WhatsApp API | (ninguno) | phone_number_id, business_account_id, status | (ninguno) | — | — |

### Imágenes (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.gallery_images.upload` | create | POST /v3/gallery/images | Carga imagen a galería | image (archivo) | image_id, image_url | (ninguno) | — | — |

### Atributos de contactos (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.contacts_attributes.list` | read | GET /v3/contacts/attributes | Lista todos los atributos de contacto | (ninguno) | lista de atributos {nombre, tipo, enumeración} | (ninguno) | — | — |
| [ ] | `brevo.contacts_attributes.create` | create | POST /v3/contacts/attributes | Crea atributo de contacto | name, type, enumeration (si aplica) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.contacts_attributes.update` | update | PUT /v3/contacts/attributes/{name} | Actualiza atributo de contacto | name, label, enumeration | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.contacts_attributes.delete` | delete | DELETE /v3/contacts/attributes/{name} | Elimina atributo | name | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.contacts_attributes.delete_option` | delete | DELETE /v3/contacts/attributes/{name}/options/{value} | Elimina opción de atributo multivalor | name, value | (vacío) | (ninguno) | I | — |

### Listas de contactos (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.contacts_lists.list` | read | GET /v3/contacts/lists | Obtiene todas las listas de contactos | limit, offset | lista de {id, nombre, count, created} + count | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.create` | create | POST /v3/contacts/lists | Crea nueva lista de contactos | name, folderId (opt) | list_id | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.get` | read | GET /v3/contacts/lists/{id} | Obtiene detalles de lista | id | nombre, folder_id, count, creado_en | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.update` | update | PUT /v3/contacts/lists/{id} | Modifica lista de contactos | id, name | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.delete` | delete | DELETE /v3/contacts/lists/{id} | Elimina lista de contactos | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.contacts_lists.get_contacts` | read | GET /v3/contacts/lists/{id}/contacts | Obtiene contactos de una lista | id, limit, offset | lista de {email, nombre, atributos} | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.add_contacts` | create | POST /v3/contacts/lists/{id}/contacts | Agrega contactos existentes a lista | id, emails | count_added | (ninguno) | — | — |
| [ ] | `brevo.contacts_lists.delete_contact` | delete | DELETE /v3/contacts/lists/{id}/contacts/{email} | Elimina contacto de lista | id, email | (vacío) | (ninguno) | — | — |

### Carpetas de contactos (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.contacts_folders.list` | read | GET /v3/contacts/folders | Obtiene todas las carpetas | (ninguno) | lista de {id, nombre} | (ninguno) | — | — |
| [ ] | `brevo.contacts_folders.create` | create | POST /v3/contacts/folders | Crea carpeta de listas | name | folder_id | (ninguno) | — | — |
| [ ] | `brevo.contacts_folders.get` | read | GET /v3/contacts/folders/{id} | Obtiene detalles de carpeta | id | nombre, listas_adentro | (ninguno) | — | — |
| [ ] | `brevo.contacts_folders.update` | update | PUT /v3/contacts/folders/{id} | Modifica carpeta | id, name | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.contacts_folders.delete` | delete | DELETE /v3/contacts/folders/{id} | Elimina carpeta (y todas sus listas) | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.contacts_folders.get_lists` | read | GET /v3/contacts/folders/{id}/lists | Obtiene listas dentro de carpeta | id, limit, offset | lista de listas | (ninguno) | — | — |

### Contactos (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [x] | `brevo.contacts.list` | read | GET /v3/contacts | Obtiene todos los contactos | limit, offset, listIds, segmentId, modifiedSince, email_filter | lista de {email, nombre, atributos, fechas} | (ninguno) | — | brevo.contacts.list |
| [ ] | `brevo.contacts.create` | create | POST /v3/contacts | Crea nuevo contacto | email, attributes (opt), listIds (opt) | contact_id | (ninguno) | — | — |
| [ ] | `brevo.contacts.create_doi` | create | POST /v3/contacts/doubleOptIn | Crea contacto con flujo Double-Opt-In | email, attributes (opt), listIds (opt), redirectionUrl | confirmation_sent | (ninguno) | E | — |
| [ ] | `brevo.contacts.get` | read | GET /v3/contacts/{email} | Obtiene detalles de contacto | email | email, nombre, atributos, listas, histórico | (ninguno) | — | — |
| [ ] | `brevo.contacts.update` | update | PUT /v3/contacts/{email} | Modifica contacto | email, attributes, listIds | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.contacts.delete` | delete | DELETE /v3/contacts/{email} | Elimina contacto | email | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.contacts.get_campaign_stats` | read | GET /v3/contacts/{email}/campaignStats | Obtiene estadísticas de campañas para contacto | email | lista de {campaign_id, opened, clicked, sent} | (ninguno) | — | — |
| [ ] | `brevo.contacts.import` | create | POST /v3/contacts/import | Importa contactos en lote | file o newContacts (array) | import_task_id, count_processed | (ninguno) | — | — |
| [ ] | `brevo.contacts.export` | create | POST /v3/contacts/export | Exporta contactos | filtros (listIds, segmentId, etc) | export_task_id, download_url (luego) | (ninguno) | — | — |
| [ ] | `brevo.contacts.search` | read | GET /v3/contacts | Busca contactos (alias a list con filtros) | email, listIds, segmentId, modifiedSince | lista de contactos coincidentes | (ninguno) | — | — |

### Segmentos (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.contacts_segments.list` | read | GET /v3/contacts/segments | Obtiene todos los segmentos | (ninguno) | lista de {id, nombre, count} | (ninguno) | — | — |

### Grupos de consentimiento (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.consent_groups.list` | read | GET /v3/consentGroups | Lista todos los grupos de consentimiento | (ninguno) | lista de {id, nombre, created} | (ninguno) | — | — |
| [ ] | `brevo.consent_groups.create` | create | POST /v3/consentGroups | Crea grupo de consentimiento | name, description (opt) | group_id | (ninguno) | — | — |
| [ ] | `brevo.consent_groups.get` | read | GET /v3/consentGroups/{id} | Obtiene detalles de grupo | id | nombre, descripción, created | (ninguno) | — | — |
| [ ] | `brevo.consent_groups.update` | update | PUT /v3/consentGroups/{id} | Modifica grupo de consentimiento | id, name, description | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.consent_groups.delete` | delete | DELETE /v3/consentGroups/{id} | Elimina grupo de consentimiento | id | (vacío) | (ninguno) | I | — |

### Eventos (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.events.list` | read | GET /v3/events | Obtiene eventos de seguimiento | (ninguno) | lista de eventos | (ninguno) | — | — |
| [ ] | `brevo.events.create` | create | POST /v3/events | Crea evento personalizado | email, eventName, data (opt) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.events.create_batch` | create | POST /v3/events/batch | Crea eventos en lote | events (array) | count_created | (ninguno) | — | — |

### Objetos personalizados (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.custom_objects_records.create_bulk` | create | POST /v3/customObjects/{objectName}/records | Crea/actualiza registros de objeto en lote | objectName, records (array) | count_created | (ninguno) | — | — |
| [ ] | `brevo.custom_objects_records.list` | read | GET /v3/customObjects/{objectName}/records | Obtiene lista de registros de objeto | objectName, limit, offset | lista de registros + count_total | (ninguno) | — | — |
| [ ] | `brevo.custom_objects_records.delete_bulk` | delete | DELETE /v3/customObjects/{objectName}/records | Elimina múltiples registros (hasta 1000) async | objectName, ids (array) | delete_task_id | (ninguno) | I | — |
| [ ] | `brevo.custom_objects_records.get_associated` | read | GET /v3/customObjects/{objectName}/records/{id}/associated | Obtiene registros asociados | objectName, id | lista de registros asociados | (ninguno) | — | — |

### Remitentes (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.senders.list` | read | GET /v3/senders | Obtiene remitentes de email | (ninguno) | lista de {id, nombre, email, verified} | (ninguno) | — | — |
| [ ] | `brevo.senders.create` | create | POST /v3/senders | Crea remitente de email | name, email, ipDomain (opt) | sender_id | (ninguno) | — | — |
| [ ] | `brevo.senders.update` | update | PUT /v3/senders/{id} | Actualiza remitente | id, name, email | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.senders.delete` | delete | DELETE /v3/senders/{id} | Elimina remitente | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.senders.validate` | create | POST /v3/senders/{id}/validate | Valida remitente usando OTP | id, code | validated | (ninguno) | — | — |
| [ ] | `brevo.senders.get_ips` | read | GET /v3/senders/ips | Obtiene todas las IPs dedicadas | (ninguno) | lista de {ip, warm, reputation} | (ninguno) | — | — |
| [ ] | `brevo.senders.get_ips_for_sender` | read | GET /v3/senders/{id}/ips | Obtiene IPs dedicadas de remitente | id | lista de IPs | (ninguno) | — | — |

### Dominios de remitente (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.domains.list` | read | GET /v3/domains | Obtiene lista de dominios de remitente | (ninguno) | lista de {dominio, verified, mx, dkim, dmarc} | (ninguno) | — | — |
| [ ] | `brevo.domains.create` | create | POST /v3/domains | Crea dominio de remitente | name, domainName (opt) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.domains.get` | read | GET /v3/domains/{domain} | Obtiene configuración de dominio | domain | records, verificación_status | (ninguno) | — | — |
| [ ] | `brevo.domains.delete` | delete | DELETE /v3/domains/{domain} | Elimina dominio de remitente | domain | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.domains.authenticate` | create | POST /v3/domains/{domain}/authenticate | Autentica dominio de remitente | domain | authenticated | (ninguno) | — | — |

### Webhooks (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.webhooks.list` | read | GET /v3/webhooks | Obtiene todos los webhooks | (ninguno) | lista de {id, url, events, created} | (ninguno) | — | — |
| [ ] | `brevo.webhooks.create` | create | POST /v3/webhooks | Crea webhook | url, events, authorization_header (opt) | webhook_id | (ninguno) | — | — |
| [ ] | `brevo.webhooks.get` | read | GET /v3/webhooks/{id} | Obtiene detalles de webhook | id | url, events, creado_en | (ninguno) | — | — |
| [ ] | `brevo.webhooks.update` | update | PUT /v3/webhooks/{id} | Modifica webhook | id, url, events | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.webhooks.delete` | delete | DELETE /v3/webhooks/{id} | Elimina webhook | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.webhooks.get_history` | read | GET /v3/webhooks/{id}/history | Exporta historial de webhook | id | lista de eventos + export_url | (ninguno) | — | — |

### Cuenta maestra (Enterprise) (26)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.master_account.get` | read | GET /v3/master-account | Obtiene detalles de cuenta maestra | (ninguno) | id_maestro, nombre, plan, fecha_creacion | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.list` | read | GET /v3/master-account/sub-accounts | Obtiene lista de sub-cuentas | (ninguno) | lista de {id, nombre, plan, created} | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.create` | create | POST /v3/master-account/sub-accounts | Crea sub-cuenta bajo maestra | name, email, plan, language | sub_account_id | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.get` | read | GET /v3/master-account/sub-accounts/{id} | Obtiene detalles de sub-cuenta | id | nombre, email, plan, creado_en | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.delete` | delete | DELETE /v3/master-account/sub-accounts/{id} | Elimina sub-cuenta | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.master_account_sub_accounts.update_plan` | update | PUT /v3/master-account/sub-accounts/{id}/plan | Actualiza plan de sub-cuenta | id, plan | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.bulk_update_plan` | update | PUT /v3/master-account/sub-accounts/plan | Actualiza plan de múltiples sub-cuentas | sub_account_ids (array), plan | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_sso.admin` | create | POST /v3/master-account/sso/admin | Genera token SSO para admin maestra | (ninguno) | sso_token, sso_url | (ninguno) | — | — |
| [ ] | `brevo.master_account_sso.sub_account` | create | POST /v3/master-account/sso/sub-account/{id} | Genera token SSO para sub-cuenta | id | sso_token, sso_url | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.create_api_key` | create | POST /v3/master-account/sub-accounts/{id}/api-key | Crea API key para sub-cuenta | id | api_key | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_accounts.update_applications` | update | PUT /v3/master-account/sub-accounts/{id}/applications | Habilita/deshabilita aplicaciones | id, applications (array) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_account_groups.create` | create | POST /v3/master-account/sub-account-groups | Crea grupo de sub-cuentas | name, sub_account_ids (array) | group_id | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_account_groups.list` | read | GET /v3/master-account/sub-account-groups | Obtiene lista de grupos | (ninguno) | lista de grupos | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_account_groups.get` | read | GET /v3/master-account/sub-account-groups/{id} | Obtiene detalles de grupo | id | nombre, sub_account_ids | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_account_groups.update` | update | PUT /v3/master-account/sub-account-groups/{id} | Modifica grupo de sub-cuentas | id, name, sub_account_ids | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_sub_account_groups.delete` | delete | DELETE /v3/master-account/sub-account-groups/{id} | Elimina grupo | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.master_account_sub_account_groups.delete_sub_account` | delete | DELETE /v3/master-account/sub-account-groups/{id}/sub-accounts | Elimina sub-cuenta de grupo | id, sub_account_ids | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_admin_users.invite` | create | POST /v3/master-account/admin-users/invite | Invita usuario admin | email, role | invite_sent | (ninguno) | E | — |
| [ ] | `brevo.master_account_admin_users.resend_cancel` | create | POST /v3/master-account/admin-users/{id}/resend-cancel | Reenvía/cancela invitación admin | id, action | (vacío) | (ninguno) | E | — |
| [ ] | `brevo.master_account_admin_users.delete` | delete | DELETE /v3/master-account/admin-users/{id} | Revoca usuario admin | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.master_account_admin_users.list` | read | GET /v3/master-account/admin-users | Obtiene lista de usuarios admin | (ninguno) | lista de {id, email, role, estado} | (ninguno) | — | — |
| [ ] | `brevo.master_account_admin_users.get_permission` | read | GET /v3/master-account/admin-users/{id}/permission | Verifica permisos de usuario admin | id | permisos (array) | (ninguno) | — | — |
| [ ] | `brevo.master_account_admin_users.update_permission` | update | PUT /v3/master-account/admin-users/{id}/permission | Modifica permisos de usuario admin | id, permissions (array) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_ips.list` | read | GET /v3/master-account/ips | Obtiene lista de todas las IPs | (ninguno) | lista de {ip, warm, reputation} | (ninguno) | — | — |
| [ ] | `brevo.master_account_ips.associate` | create | POST /v3/master-account/ips/sub-accounts | Asocia IP a sub-cuentas | ips (array), sub_account_ids (array) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.master_account_ips.disassociate` | delete | DELETE /v3/master-account/ips/sub-accounts | Desasocia IP de sub-cuentas | ips (array), sub_account_ids (array) | (vacío) | (ninguno) | — | — |

### Usuarios (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.users.list` | read | GET /v3/users | Obtiene lista de todos los usuarios | (ninguno) | lista de {id, email, role, created} | (ninguno) | — | — |
| [ ] | `brevo.users.invite` | create | POST /v3/users/invite | Envía invitación a usuario | email, role, permissions (opt) | invite_sent | (ninguno) | E | — |
| [ ] | `brevo.users.get_permission` | read | GET /v3/users/{id}/permission | Verifica permisos de usuario | id | permisos (array) | (ninguno) | — | — |
| [ ] | `brevo.users.update_permission` | update | PUT /v3/users/{id}/permission | Actualiza permisos de usuario | id, permissions (array) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.users.delete_permission` | delete | DELETE /v3/users/{id}/permission | Revoca permisos de usuario | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.users.resend_cancel` | create | POST /v3/users/{id}/resend-cancel | Reenvía/cancela invitación | id, action | (vacío) | (ninguno) | E | — |

### Procesos (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.processes.list` | read | GET /v3/processes | Obtiene procesos en segundo plano | (ninguno) | lista de {id, tipo, estado, progreso} | (ninguno) | — | — |
| [ ] | `brevo.processes.get` | read | GET /v3/processes/{id} | Obtiene detalles de proceso | id | tipo, estado, progreso, resultado | (ninguno) | — | — |

### Feeds externos (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.feeds.list` | read | GET /v3/feeds | Obtiene todos los feeds externos | (ninguno) | lista de feeds | (ninguno) | — | — |
| [ ] | `brevo.feeds.create` | create | POST /v3/feeds | Crea feed externo | name, url, authType (opt) | feed_id | (ninguno) | — | — |
| [ ] | `brevo.feeds.get` | read | GET /v3/feeds/{uuid} | Obtiene detalles de feed | uuid | nombre, url, status | (ninguno) | — | — |
| [ ] | `brevo.feeds.update` | update | PUT /v3/feeds/{uuid} | Modifica feed externo | uuid, name, url | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.feeds.delete` | delete | DELETE /v3/feeds/{uuid} | Elimina feed externo | uuid | (vacío) | (ninguno) | I | — |

### CRM - Empresas (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.crm_companies.list` | read | GET /v3/crm/companies | Obtiene todas las empresas | limit, offset | lista de {id, nombre, industry, revenue} | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.create` | create | POST /v3/crm/companies | Crea empresa | name, industry (opt), revenue (opt), attributes | company_id | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.get` | read | GET /v3/crm/companies/{id} | Obtiene detalles de empresa | id | nombre, industry, revenue, contactos, deals | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.update` | update | PUT /v3/crm/companies/{id} | Modifica empresa | id, name, industry, revenue, attributes | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.delete` | delete | DELETE /v3/crm/companies/{id} | Elimina empresa | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.crm_companies_attributes.list` | read | GET /v3/crm/companies/attributes | Obtiene atributos de empresa | (ninguno) | lista de atributos | (ninguno) | — | — |
| [ ] | `brevo.crm_companies_attributes.create` | create | POST /v3/crm/companies/attributes | Crea atributo empresa/deal | name, label, type | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.link` | create | POST /v3/crm/companies/{id}/link | Vincula/desvincula empresa con contacto y deal | id, contacts, deals | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_companies.import` | create | POST /v3/crm/companies/import | Importa empresas (crear/actualizar) | companies (array) | import_task_id, count_processed | (ninguno) | — | — |

### CRM - Deals (11)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.crm_pipelines.list` | read | GET /v3/crm/pipelines | Obtiene todos los pipelines | (ninguno) | lista de {id, nombre, etapas} | (ninguno) | — | — |
| [ ] | `brevo.crm_pipelines.get` | read | GET /v3/crm/pipelines/{id} | Obtiene detalles de pipeline | id | nombre, etapas, deals | (ninguno) | — | — |
| [ ] | `brevo.crm_pipelines.get_stages` | read | GET /v3/crm/pipelines/{id}/stages | Obtiene etapas de pipeline | id | lista de {id, nombre, orden} | (ninguno) | — | — |
| [ ] | `brevo.crm_deals_attributes.list` | read | GET /v3/crm/deals/attributes | Obtiene atributos de deal | (ninguno) | lista de atributos | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.list` | read | GET /v3/crm/deals | Obtiene todos los deals | limit, offset, pipelineId (opt) | lista de {id, nombre, valor, etapa} | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.create` | create | POST /v3/crm/deals | Crea deal | name, pipelineId, stageId, value (opt), company, contacts | deal_id | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.get` | read | GET /v3/crm/deals/{id} | Obtiene detalles de deal | id | nombre, valor, etapa, empresa, contactos | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.update` | update | PUT /v3/crm/deals/{id} | Modifica deal | id, name, stageId, value, attributes | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.delete` | delete | DELETE /v3/crm/deals/{id} | Elimina deal | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.crm_deals.link` | create | POST /v3/crm/deals/{id}/link | Vincula/desvincula deal con contactos y empresas | id, contacts, companies | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_deals.import` | create | POST /v3/crm/deals/import | Importa deals (crear/actualizar) | deals (array) | import_task_id, count_processed | (ninguno) | — | — |

### CRM - Tareas (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.crm_tasks_types.list` | read | GET /v3/crm/tasks/types | Obtiene tipos de tarea | (ninguno) | lista de tipos | (ninguno) | — | — |
| [ ] | `brevo.crm_tasks.list` | read | GET /v3/crm/tasks | Obtiene todas las tareas | limit, offset, status (opt) | lista de {id, nombre, tipo, fechavencimiento} | (ninguno) | — | — |
| [ ] | `brevo.crm_tasks.create` | create | POST /v3/crm/tasks | Crea tarea | name, taskType, dueDate, contacts (opt), companies (opt) | task_id | (ninguno) | — | — |
| [ ] | `brevo.crm_tasks.get` | read | GET /v3/crm/tasks/{id} | Obtiene detalles de tarea | id | nombre, tipo, vencimiento, estado, contactos | (ninguno) | — | — |
| [ ] | `brevo.crm_tasks.update` | update | PUT /v3/crm/tasks/{id} | Modifica tarea | id, name, taskType, dueDate, status | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_tasks.delete` | delete | DELETE /v3/crm/tasks/{id} | Elimina tarea | id | (vacío) | (ninguno) | I | — |

### CRM - Notas (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.crm_notes.list` | read | GET /v3/crm/notes | Obtiene todas las notas | limit, offset | lista de {id, texto, creado_en} | (ninguno) | — | — |
| [ ] | `brevo.crm_notes.create` | create | POST /v3/crm/notes | Crea nota | text, contacts (opt), companies (opt) | note_id | (ninguno) | — | — |
| [ ] | `brevo.crm_notes.get` | read | GET /v3/crm/notes/{id} | Obtiene detalles de nota | id | texto, creado_en, modificado_en | (ninguno) | — | — |
| [ ] | `brevo.crm_notes.update` | update | PUT /v3/crm/notes/{id} | Modifica nota | id, text | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.crm_notes.delete` | delete | DELETE /v3/crm/notes/{id} | Elimina nota | id | (vacío) | (ninguno) | I | — |

### CRM - Archivos (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.crm_files.list` | read | GET /v3/crm/files | Obtiene todos los archivos | limit, offset | lista de {id, nombre, tipo, creado_en} | (ninguno) | — | — |
| [ ] | `brevo.crm_files.upload` | create | POST /v3/crm/files | Carga archivo | file (multipart), contacts (opt), companies (opt) | file_id, file_url | (ninguno) | — | — |
| [ ] | `brevo.crm_files.get` | read | GET /v3/crm/files/{id} | Obtiene detalles de archivo | id | nombre, tipo, size, creado_en | (ninguno) | — | — |
| [ ] | `brevo.crm_files.download` | read | GET /v3/crm/files/{id}/download | Descarga archivo | id | contenido binario | (ninguno) | — | — |
| [ ] | `brevo.crm_files.delete` | delete | DELETE /v3/crm/files/{id} | Elimina archivo | id | (vacío) | (ninguno) | I | — |

### Conversaciones - Mensajes (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.conversations_messages.send` | create | POST /v3/conversations/messages | Envía mensaje como agente | visitorId, message, type (opt) | message_id | (ninguno) | E | — |
| [ ] | `brevo.conversations_messages.get` | read | GET /v3/conversations/messages/{id} | Obtiene mensaje | id | texto, autor, timestamp, visitorId | (ninguno) | — | — |
| [ ] | `brevo.conversations_messages.update` | update | PUT /v3/conversations/messages/{id} | Actualiza mensaje de agente | id, message | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.conversations_messages.delete` | delete | DELETE /v3/conversations/messages/{id} | Elimina mensaje de agente | id | (vacío) | (ninguno) | I | — |

### Conversaciones - Mensajes automáticos (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.conversations_automated_messages.send` | create | POST /v3/conversations/automatedMessages | Envía mensaje automático a visitante | visitorId, message, type (opt) | message_id | (ninguno) | E | — |
| [ ] | `brevo.conversations_automated_messages.get` | read | GET /v3/conversations/automatedMessages/{id} | Obtiene mensaje automático | id | contenido, status, creado_en | (ninguno) | — | — |
| [ ] | `brevo.conversations_automated_messages.update` | update | PUT /v3/conversations/automatedMessages/{id} | Modifica mensaje automático | id, message | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.conversations_automated_messages.delete` | delete | DELETE /v3/conversations/automatedMessages/{id} | Elimina mensaje automático | id | (vacío) | (ninguno) | I | — |

### Conversaciones - Estado (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.conversations_status.set_online` | create | POST /v3/conversations/status | Establece estado de agente online | (ninguno) | online_duration | (ninguno) | — | — |

### Conversaciones - Visitantes (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.conversations_visitors.assign_group` | create | POST /v3/conversations/visitors/{id}/group | Asigna grupo a visitante | id, group_id | (vacío) | (ninguno) | — | — |

### eCommerce - Órdenes (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_orders.create` | create | POST /v3/ecommerce/orders | Crea/gestiona estado de orden | order_id, status, amount, items | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_orders.create_batch` | create | POST /v3/ecommerce/orders/batch | Crea órdenes en lote | orders (array) | count_created | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_orders.list` | read | GET /v3/ecommerce/orders | Obtiene detalles de órdenes | (ninguno) | lista de órdenes | (ninguno) | — | — |

### eCommerce - Productos (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_products.list` | read | GET /v3/ecommerce/products | Obtiene todos los productos | limit, offset | lista de {id, nombre, precio, url} | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_products.create_update` | create | POST /v3/ecommerce/products | Crea/actualiza producto | product_id, name, price, description (opt), images (opt) | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_products.get` | read | GET /v3/ecommerce/products/{id} | Obtiene detalles de producto | id | nombre, precio, categoría, descripción, url | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_products.create_batch` | create | POST /v3/ecommerce/products/batch | Crea productos en lote | products (array) | count_created | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_products.create_alert` | create | POST /v3/ecommerce/products/{id}/alerts | Crea alerta de producto para contacto | id, contact_email | alert_created | (ninguno) | E | — |

### eCommerce - Categorías (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_categories.list` | read | GET /v3/ecommerce/categories | Obtiene todas las categorías | limit, offset | lista de {id, nombre} | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_categories.create_update` | create | POST /v3/ecommerce/categories | Crea/actualiza categoría | category_id, name | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_categories.get` | read | GET /v3/ecommerce/categories/{id} | Obtiene detalles de categoría | id | nombre, productos | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_categories.create_batch` | create | POST /v3/ecommerce/categories/batch | Crea categorías en lote | categories (array) | count_created | (ninguno) | — | — |

### eCommerce - Atribución de ingresos (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_attribution.get_campaign` | read | GET /v3/ecommerce/attribution/{campaignId} | Obtiene métricas de atribución para campaña | campaignId | revenue, conversions, roas | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_attribution.get_campaign_products` | read | GET /v3/ecommerce/attribution/{campaignId}/products | Obtiene productos atribuidos a campaña | campaignId | lista de {product_id, revenue, conversions} | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_attribution.get_multiple` | read | POST /v3/ecommerce/attribution | Obtiene atribución para múltiples campañas | campaign_ids (array) | lista de métricas por campaña | (ninguno) | — | — |

### eCommerce - Configuración (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_config.activate` | create | POST /v3/ecommerce/activate | Activa la aplicación eCommerce | (ninguno) | activated | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_currencies.list` | read | GET /v3/ecommerce/currencies | Obtiene código de divisa ISO 4217 | (ninguno) | currency_code | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_currencies.update` | update | PUT /v3/ecommerce/currencies | Establece código de divisa ISO 4217 | currency_code | (vacío) | (ninguno) | — | — |

### eCommerce - Cupones (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_coupons.list` | read | GET /v3/ecommerce/coupons | Obtiene todas las colecciones de cupones | (ninguno) | lista de {id, nombre} | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_coupons.create` | create | POST /v3/ecommerce/coupons | Crea colección de cupones | name, codes (opt) | coupon_collection_id | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_coupons.get` | read | GET /v3/ecommerce/coupons/{id} | Obtiene detalles de colección | id | nombre, códigos, count | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_coupons.update` | update | PUT /v3/ecommerce/coupons/{id} | Actualiza colección de cupones | id, name, codes | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_coupons.create_codes` | create | POST /v3/ecommerce/coupons/{id}/codes | Crea cupones para colección | id, codes (array) | count_created | (ninguno) | — | — |

### eCommerce - Pagos (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.ecommerce_payments.create` | create | POST /v3/ecommerce/payments | Crea solicitud de pago | amount, currency, description (opt) | payment_id, payment_url | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_payments.get` | read | GET /v3/ecommerce/payments/{id} | Obtiene detalles de solicitud de pago | id | monto, estado, creado_en | (ninguno) | — | — |
| [ ] | `brevo.ecommerce_payments.delete` | delete | DELETE /v3/ecommerce/payments/{id} | Elimina solicitud de pago | id | (vacío) | (ninguno) | I | — |

### Lealtad - Programas (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_programs.list` | read | GET /v3/loyalty/programs | Obtiene lista de programas de lealtad | (ninguno) | lista de programas | (ninguno) | — | — |
| [ ] | `brevo.loyalty_programs.create` | create | POST /v3/loyalty/programs | Crea programa de lealtad | name, tier_type, reward_rules | program_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_programs.get` | read | GET /v3/loyalty/programs/{id} | Obtiene información de programa | id | nombre, tiers, recompensas | (ninguno) | — | — |
| [ ] | `brevo.loyalty_programs.update` | update | PUT /v3/loyalty/programs/{id} | Actualiza programa de lealtad | id, name, settings | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_programs.partial_update` | update | PATCH /v3/loyalty/programs/{id} | Actualiza parcialmente programa | id, campos_parciales | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_programs.delete` | delete | DELETE /v3/loyalty/programs/{id} | Elimina programa de lealtad | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_programs.publish` | create | POST /v3/loyalty/programs/{id}/publish | Publica programa de lealtad | id | published | (ninguno) | — | — |

### Lealtad - Suscripciones (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_subscriptions.create` | create | POST /v3/loyalty/subscriptions | Crea suscripción | program_id, contact_id | subscription_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_subscriptions.get` | read | GET /v3/loyalty/subscriptions/{id} | Obtiene datos de suscripción | id | program_id, balance, tiers | (ninguno) | — | — |
| [ ] | `brevo.loyalty_subscriptions.delete` | delete | DELETE /v3/loyalty/subscriptions/{id} | Elimina suscripción | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_subscriptions.create_member` | create | POST /v3/loyalty/subscriptions/{id}/members | Crea miembro de suscripción | id, contact_id | member_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_subscriptions.delete_member` | delete | DELETE /v3/loyalty/subscriptions/{id}/members/{contactId} | Elimina miembro de suscripción | id, contactId | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_subscriptions.get_balances` | read | GET /v3/loyalty/subscriptions/{id}/balances | Obtiene saldos de suscripción | id | lista de {balance_type, amount} | (ninguno) | — | — |
| [ ] | `brevo.loyalty_subscriptions.create_balances` | create | POST /v3/loyalty/subscriptions/{id}/balances | Crea saldos de suscripción | id, balances (array) | count_created | (ninguno) | — | — |
| [ ] | `brevo.loyalty_subscriptions.assign_tier` | create | POST /v3/loyalty/subscriptions/{id}/tiers | Asigna nivel a suscripción | id, tier_id | (vacío) | (ninguno) | — | — |

### Lealtad - Recompensas (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_rewards.create` | create | POST /v3/loyalty/rewards | Crea recompensa | name, type, value | reward_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_rewards.get` | read | GET /v3/loyalty/rewards/{id} | Obtiene información de recompensa | id | nombre, tipo, valor, estado | (ninguno) | — | — |
| [ ] | `brevo.loyalty_rewards.validate` | create | POST /v3/loyalty/rewards/{id}/validate | Valida recompensa | id | validated | (ninguno) | — | — |
| [ ] | `brevo.loyalty_rewards.get_page` | read | GET /v3/loyalty/rewards/page | Obtiene página de recompensas | (ninguno) | lista de recompensas | (ninguno) | — | — |

### Lealtad - Vales (6)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_vouchers.create` | create | POST /v3/loyalty/vouchers | Crea vale | reward_id, codes (array) | voucher_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_vouchers.get` | read | GET /v3/loyalty/vouchers/{contactId} | Obtiene vales para contacto | contactId | lista de vales | (ninguno) | — | — |
| [ ] | `brevo.loyalty_vouchers.redeem_request` | create | POST /v3/loyalty/vouchers/{id}/redeem | Crea solicitud de canje de vale | id | redeem_request_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_vouchers.redeem_complete` | create | POST /v3/loyalty/vouchers/{id}/complete | Completa canje de vale | id | redeemed | (ninguno) | — | — |
| [ ] | `brevo.loyalty_vouchers.revoke` | delete | DELETE /v3/loyalty/vouchers | Revoca vales | voucher_ids (array) | count_revoked | (ninguno) | I | — |
| [ ] | `brevo.loyalty_vouchers.get_code_count` | read | GET /v3/loyalty/vouchers/codes/count | Obtiene conteo de códigos de vale | (ninguno) | code_count | (ninguno) | — | — |

### Lealtad - Balances (16)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_balances_definitions.list` | read | GET /v3/loyalty/balances/definitions | Obtiene lista de definiciones de balance | (ninguno) | lista de definiciones | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_definitions.create` | create | POST /v3/loyalty/balances/definitions | Crea definición de balance | name, type | definition_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_definitions.get` | read | GET /v3/loyalty/balances/definitions/{id} | Obtiene definición de balance | id | nombre, tipo, metadata | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_definitions.update` | update | PUT /v3/loyalty/balances/definitions/{id} | Actualiza definición de balance | id, name, type | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_definitions.delete` | delete | DELETE /v3/loyalty/balances/definitions/{id} | Elimina definición de balance | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_balances_limits.create` | create | POST /v3/loyalty/balances/limits | Crea límites de balance | balance_definition_id, limit_value | limit_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_limits.list` | read | GET /v3/loyalty/balances/limits | Obtiene límites de balance | (ninguno) | lista de límites | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_limits.update` | update | PUT /v3/loyalty/balances/limits/{id} | Actualiza límite de balance | id, limit_value | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances_limits.delete` | delete | DELETE /v3/loyalty/balances/limits/{id} | Elimina límite de balance | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_balances.get` | read | GET /v3/loyalty/balances/{contactId} | Obtiene lista de balances | contactId | lista de {definition_id, amount} | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances.create_transaction` | create | POST /v3/loyalty/balances/transactions | Crea nueva transacción | balance_definition_id, amount, contact_id | transaction_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances.complete_transaction` | update | PATCH /v3/loyalty/balances/transactions/{id} | Completa transacción | id | completed | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances.cancel_transaction` | delete | DELETE /v3/loyalty/balances/transactions/{id} | Cancela transacción | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_balances.create_order` | create | POST /v3/loyalty/balances/orders | Crea orden de balance | contact_id, amount, definition_id | order_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances.get_active` | read | GET /v3/loyalty/balances/active | Obtiene balances activos | (ninguno) | lista de balances activos | (ninguno) | — | — |
| [ ] | `brevo.loyalty_balances.get_transaction_history` | read | GET /v3/loyalty/balances/transactions/history | Obtiene historial de transacciones | (ninguno) | lista de transacciones | (ninguno) | — | — |

### Lealtad - Niveles (9)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.loyalty_tiers_groups.create` | create | POST /v3/loyalty/tiers/groups | Crea grupo de niveles | name, tiers (array) | group_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers_groups.list` | read | GET /v3/loyalty/tiers/groups | Obtiene lista de grupos de niveles | (ninguno) | lista de grupos | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers_groups.get` | read | GET /v3/loyalty/tiers/groups/{id} | Obtiene grupo de niveles | id | nombre, niveles | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers_groups.update` | update | PUT /v3/loyalty/tiers/groups/{id} | Actualiza grupo de niveles | id, name | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers_groups.delete` | delete | DELETE /v3/loyalty/tiers/groups/{id} | Elimina grupo de niveles | id | (vacío) | (ninguno) | I | — |
| [ ] | `brevo.loyalty_tiers_groups.get_tiers` | read | GET /v3/loyalty/tiers/groups/{id}/tiers | Obtiene niveles del grupo | id | lista de niveles | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers.create` | create | POST /v3/loyalty/tiers | Crea nivel | name, level, requirements (opt) | tier_id | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers.update` | update | PUT /v3/loyalty/tiers/{id} | Actualiza nivel | id, name, level | (vacío) | (ninguno) | — | — |
| [ ] | `brevo.loyalty_tiers.delete` | delete | DELETE /v3/loyalty/tiers/{id} | Elimina nivel | id | (vacío) | (ninguno) | I | — |

### Billetera - Pases (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.wallet_passes.get` | read | GET /v3/wallet/passes/{contactId} | Obtiene URL de instalación de pase | contactId | pass_installation_url | (ninguno) | — | — |

### Actividad (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `brevo.account_activity.list` | read | GET /v3/account/activity | Obtiene logs de actividad de usuario | (ninguno) | lista de {timestamp, usuario, acción, recurso} | (ninguno) | — | — |

## Observaciones de las herramientas viejas

- Hecho: `brevo.account.get` (`whoami`), `brevo.contacts.list`, `brevo.templates.list` (todas de lectura y en estado `draft`).
- Las funciones nuevas de Brevo (crear contacto, enviar campana, etc.) no estan definidas: se deciden con el producto.
