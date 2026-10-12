# Tareas: LinkedIn

- **Funciones catalogadas:** 80 · **Hechas:** 0 · **Pendientes:** 80 · App sin herramientas viejas
- **Documentación oficial:** https://learn.microsoft.com/en-us/linkedin/
- **Fuentes que consultó el catálogo:** https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2 https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-lookup-api https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads/getting-started
- **Paginación típica:** Cursor-based (start, count, links) para listas; cursor en response para siguiente página; limit típico 10 elementos
- **Qué no se pudo verificar:** Endpoints exactos para update/delete de posts en /rest/posts; operaciones GraphQL disponibles; limite de ritmo exacto por endpoint específico; disponibilidad de Video API endpoints; detalles de Poll API y MultiImage API endpoints; algunos endpoints legacy (v2/) y nuevos (rest/) compatibilidad cruzada
- **Origen de esta lista:** generada por IA (modelo pequeño) leyendo la documentación oficial el 2026-10-07; ver la advertencia de la Fase B. Las herramientas viejas salen de `app/agent/shared/tools/providers/`.

## Tareas comunes de la app (una sola vez)

- [ ] Copiar `app/functions/apps/_template/` a `app/functions/apps/linkedin/` ([plantilla](../app/functions/apps/_template/README.md)).
- [ ] `app_spec.py`: nombre, `provider_keys` (= `linkedin`) y `AuthSpec` según la Fase A. Si hace falta una estrategia no implementada, avisar al líder.
- [ ] Terminar la **Fase A** con una cuenta real antes de programar las funciones.
- [ ] Por cada función: handler, modelos Pydantic, descripción en inglés, ejemplo, prueba con HTTP simulado ([guía](../doc/funciones/GUIA_JUNIOR.md)) y la lista "listo cuando…" de la plantilla.
- [ ] Probar por API cada función (una o varias cuentas) y registrar en Postman ([guía](../doc/funciones/POSTMAN.md)); `python scripts/export_postman.py`.
- [ ] `python scripts/publish_functions.py` sin conflicto.

## Fase A · Probar la autenticación (hacer PRIMERO)

Protocolo y script en [`PROBAR_AUTH.md`](PROBAR_AUTH.md) (lee las secciones 0 a 3 antes). Lo que sigue son los valores de **esta** app. Tipo: **token largo, sin refresh**.

| Dato | Valor |
|---|---|
| `provider` que debe quedar guardado (verifícalo con `ver`) | `linkedin` |
| Variables del `.env` que necesitas | LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI, FRONTEND_REDIRECT_URL |
| Conectar (caso C1) | `GET /api/v1/integrations/linkedin/login` (confirma la ruta exacta en `http://localhost:5001/docs`) |
| Función para verificar identidad (`FUNCION_WHOAMI`) | `linkedin.user.get` |
| Cómo se autentica (según el catálogo) | OAuth 2.0 con código de autorización (3-legged); usuario acepta permisos en LinkedIn, recibe código que se intercambia por access token |
| Duración del token (según el catálogo) | 60 días (access token); refresh tokens solo para programas aprobados |
| Refresco (según el catálogo) | Disponible pero solo para partners aprobados con acceso programmatic refresh tokens; redirección para refresco automático si usuario sigue autenticado en LinkedIn |
| Permisos (según el catálogo) | openid (OIDC), profile (perfil lite), email (email), r_liteprofile (perfil lite legacy), r_emailaddress (email legacy), w_member_social (crear posts personales), w_organization_social (crear posts de organización), r_ads (leer ads), rw_ads (crear/actualizar ads/campañas), r_basicprofile (perfil básico), r_compliance (auditoría/cumplimiento) |
| Restricciones de acceso | API pública con restricciones por producto (Sign In with LinkedIn, Share on LinkedIn, Posts API, Marketing Developer Platform, Community Management). Sin aprobación especial: perfil público, userinfo, crear posts personales con alcance limitado, comentarios/reacciones en páginas propias, datos organizacionales si es admin. Con aprobación: full Posts API, Lead Gen, Ads Manager, Programmatic Refresh Tokens. Cuentas de empresa pueden tener restricciones adicionales. Límites de ritmo varían por endpoint. |
| Límites de ritmo | Rate limits por aplicación y por miembro por día (24h UTC), no publicados; disponibles en Developer Portal tras hacer 1 request al endpoint. Share on LinkedIn: 150 req/día por miembro, 100,000 req/día por app. Típicamente 300+ miembros en audiencia para campañas; límites mínimos y máximos de bid y presupuesto. |
| Notas de esta app | El refresh solo existe para programas aprobados: verifica en el catálogo. |

> Los datos "según el catálogo" los extrajo una IA de la documentación oficial y **no están verificados por una persona**: confírmalos en la documentación de la app antes de darlos por buenos y corrige este archivo si algo difiere.

### Tareas de autenticación

Marca cada casilla cuando el resultado obtenido coincida con el esperado. Si no coincide, escribe lo que pasó y avisa; no lo arregles dentro de una función. Si no se pudo hacer, marca `N/A` y la razón.

| Hecho | Caso | Qué hacer exactamente | Resultado esperado | Resultado obtenido |
|---|---|---|---|---|
| [ ] | **A0 Preparar** | Crear tu app de desarrollador en la plataforma y llenar el `.env` (nunca al repo). Registrar la URI de redirección **idéntica** a la del `.env`. Si la app está en modo desarrollo, añadir tu cuenta de prueba como probadora. | Variables llenas; la plataforma muestra tu app creada | |
| [ ] | **A1 JWT** | `POST /api/v1/auth/login` con tu usuario de Shifu; guardar `access_token` y `user.id` (ver `PROBAR_AUTH.md` §1). | 200 con `access_token` y `user.id` | |
| [ ] | **C1 Conectar** | `GET /api/v1/integrations/linkedin/login` con el JWT; abrir la URL que devuelve y aceptar los permisos. | Vuelve al front sin `error=` en la URL | |
| [ ] | **C2 Guardada** | `GET /api/v1/accounts/` y `python cuenta_prueba.py ver <user_id> linkedin`. | Cuenta con `provider: linkedin`, `account_id` real, `status: active` | |
| [ ] | **C3 Funciona** | `POST /internal/functions/linkedin.user.get/test` con `{"input": {}, "account_ids": [], "allow_write": false}`. | `ok: true`, `data.account_id` igual al guardado, `identity.match: true` | |
| [ ] | **C4 Respaldar** | `python cuenta_prueba.py respaldar <user_id> linkedin <account_id>`. | Crea `respaldo_cuenta.json` | |
| [ ] | **C5 Token vencido** | `romper_access` y repetir C3. | `error.code = auth_expired` y la cuenta pasa a `status: expired` (esta app no tiene refresh) | |
| [ ] | **C6 Todo vencido** | `restaurar`, luego `romper_todo` y repetir C3. | `error.code = auth_expired`; `status: expired` solo en esa cuenta | |
| [ ] | **C7 Cuenta inexistente** | Tras `restaurar`, C3 con `"account_ids": ["no-existe"]`. | `error.code = missing_connection` | |
| [ ] | **C8 Sin conexión** | C3 con otro usuario de Shifu que no tenga esta app conectada. | `error.code = missing_connection` | |
| [ ] | **C9 Dos cuentas** | Conectar una 2ª cuenta de LinkedIn. (a) C3 sin `account_ids`; (b) con `["A","B"]`; (c) `romper_todo` solo de A y repetir (b). | (a) `account_selection_required`; (b) dos `ok` con `identity.match: true`; (c) A `auth_expired` y **B sigue `ok`** | |
| [ ] | **C10 Permiso faltante** | Quitar un permiso a la conexión (o conectar con menos) y ejecutar una función que lo necesite. | `error.code = missing_scope` y la cuenta **no** se marca vencida (o `N/A` si no se puede forzar) | |
| [ ] | **C11 Revocado** | Revocar el acceso desde el panel de la app externa y repetir C3. | `error.code = auth_expired` | |
| [ ] | **C12 Registro** | Exportar la colección de Postman de la app (`doc/postman/linkedin.json`) y completar esta tabla. | Colección en el repo; todas las filas completas | |

## Fase B · Funciones de la app

Una fila = una función = una tarea. **Resultado** es lo que debe devolver la función (el `output_schema` real lo defines tú con la documentación). ★ = la función `whoami`. `E` = sale al exterior, `I` = irreversible, `D` = ya implementada.
Propuesta generada por IA desde la documentación oficial: **verifica endpoint, parámetros y permiso en la documentación antes de programar**, y escribe la descripción en inglés y completa (≥ 200 caracteres).

### Autenticación y Usuario (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.user.get` ★ | read | GET /v2/userinfo | Obtener perfil del usuario autenticado con OpenID Connect | openid,profile,email | {sub, name, given_name, family_name, picture, email, email_verified} | openid,profile,email | — | — |
| [ ] | `linkedin.user.list_orgs` | read | GET /rest/organizations?q=administrators | Listar organizaciones que administra el usuario autenticado | ninguno | lista de organizaciones administradas con id, name, vanityName | rw_organization_admin | — | — |

### Posts Personales (UGC - User Generated Content) (8)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.post.create` | create | POST /rest/posts | Crear nuevo post personal de texto, imagen, vídeo o artículo | author,content,visibility,mediaCategory | post URN, id en header X-RestLi-Id | w_member_social | E, I | — |
| [ ] | `linkedin.post.create_text` | create | POST /rest/posts | Crear post personal solo texto | author,text,visibility | post URN, id en header X-RestLi-Id | w_member_social | E, I | — |
| [ ] | `linkedin.post.create_with_image` | create | POST /rest/posts | Crear post personal con imagen adjunta | author,text,image,visibility | post URN, id en header X-RestLi-Id | w_member_social | E, I | — |
| [ ] | `linkedin.post.create_with_video` | create | POST /rest/posts | Crear post personal con vídeo | author,text,video,visibility | post URN, id en header X-RestLi-Id | w_member_social | E, I | — |
| [ ] | `linkedin.post.create_with_article` | create | POST /rest/posts | Crear post personal compartiendo artículo con URL | author,text,articleUrl,title,description | post URN, id en header X-RestLi-Id | w_member_social | E, I | — |
| [ ] | `linkedin.post.create_legacy` | create | POST /v2/ugcPosts | Crear post personal (API legacy, aún funciona) | author,lifecycleState,visibility,shareContent | post URN | w_member_social | E, I | — |
| [ ] | `linkedin.post.batch_get` | read | GET /rest/posts | Obtener múltiples posts por sus IDs/URNs | ids | lista de posts con metadata | w_member_social | E | — |
| [ ] | `linkedin.post.get` | read | GET /rest/posts/{postUrn} | Obtener un post individual | postUrn | post con campos id, author, created, visibility, content | w_member_social | E | — |

### Posts de Organización (Company Pages) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.organization_post.create` | create | POST /rest/posts | Crear post en página de organización | author(orgURN),content,visibility | post URN, id en header X-RestLi-Id | w_organization_social | E, I | — |
| [ ] | `linkedin.organization_post.create_text` | create | POST /rest/posts | Crear post solo texto en página organización | author(orgURN),text,visibility | post URN, id en header | w_organization_social | E, I | — |
| [ ] | `linkedin.organization_post.create_with_image` | create | POST /rest/posts | Crear post con imagen en página organización | author(orgURN),text,image,visibility | post URN, id en header | w_organization_social | E, I | — |
| [ ] | `linkedin.organization_post.create_with_video` | create | POST /rest/posts | Crear post con vídeo en página organización | author(orgURN),text,video | post URN, id en header | w_organization_social | E, I | — |
| [ ] | `linkedin.organization_post.create_with_article` | create | POST /rest/posts | Crear post compartiendo artículo en página organización | author(orgURN),text,articleUrl,title | post URN | w_organization_social | E, I | — |

### Encuestas (Poll Posts) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.poll.create` | create | POST /rest/posts | Crear encuesta en post | author,question,options,visibility | post URN con poll | w_member_social,w_organization_social | E, I | — |
| [ ] | `linkedin.poll.get` | read | GET /rest/posts/{postUrn} | Obtener encuesta y resultados | postUrn | post con opciones y conteo votos | w_member_social,w_organization_social | — | — |

### Imágenes y Medios (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.media.register_upload` | create | POST /v2/assets?action=registerUpload | Registrar imagen/vídeo para subir antes de crear post | owner,recipes,serviceRelationships | uploadUrl, asset URN | w_member_social,w_organization_social | I | — |
| [ ] | `linkedin.media.upload` | create | POST (upload URL) | Subir binario de imagen/vídeo a LinkedIn | archivo binario | confirmación de carga | w_member_social,w_organization_social | — | — |
| [ ] | `linkedin.image.create_legacy` | create | POST /v2/images | Crear y subir imagen (API legacy) | owner,document | image URN | w_member_social | I | — |

### Organizaciones (10)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.organization.get` | read | GET /rest/organizations/{orgId} | Obtener información de organización por ID (requiere ser admin) | organizationId | {id, name, vanityName, localizedName, logoV2, description, website, locations} | rw_organization_admin | — | — |
| [ ] | `linkedin.organization.batch_get` | read | GET /rest/organizations?ids=List(...) | Obtener múltiples organizaciones (requiere ser admin en todas) | ids | mapa de organizaciones con metadata | rw_organization_admin | — | — |
| [ ] | `linkedin.organization.lookup` | read | GET /rest/organizationsLookup?ids=List(...) | Obtener organizaciones sin requerir admin (datos públicos limitados) | ids | id, name, vanityName, logoV2 | r_basicprofile | — | — |
| [ ] | `linkedin.organization.search_by_vanity` | read | GET /rest/organizations?q=vanityName&vanityName=... | Buscar organización por nombre vanity | vanityName | organización con id, name, primaryOrganizationType | r_basicprofile | — | — |
| [ ] | `linkedin.organization.search_by_name` | read | GET /rest/organizations?q=name&keywords=... | Buscar organizaciones por nombre | keywords | lista de organizaciones coincidentes | r_basicprofile | — | — |
| [ ] | `linkedin.organization.get_by_parent` | read | GET /rest/organizations?q=parentOrganization&parent={orgURN} | Obtener marcas/suborganizaciones de una organización padre | parentOrganizationUrn | lista de organizaciones hijo que administra | rw_organization_admin | — | — |
| [ ] | `linkedin.organization.get_followers` | read | GET /rest/networkSizes/{orgURN}?edgeType=COMPANY_FOLLOWED_BY_MEMBER | Obtener número de seguidores de organización | organizationUrn | {firstDegreeSize: count} | r_basicprofile | — | — |
| [ ] | `linkedin.organization.get_statistics` | read | GET /rest/organizationFollowerStatistics | Obtener estadísticas de seguidores detalladas por período | organizationUrn,startDate,endDate | {timeRange, organizationalFollowerCount, pageViewCount} | rw_organization_admin | — | — |
| [ ] | `linkedin.organization.get_share_statistics` | read | GET /rest/organizationShareStatistics | Obtener estadísticas de posts: impresiones, clics, reacciones | organizationUrn,shareUrn | {shareCount, impressionCount, clickCount, likeCount, commentCount} | rw_organization_admin | — | — |
| [ ] | `linkedin.organization.get_page_statistics` | read | GET /rest/organizationPageStatistics | Obtener estadísticas generales de página | organizationUrn,startDate,endDate | {pageViewCount, uniquePageViewsByCountry, uniquePageViewsByTitle} | rw_organization_admin | — | — |

### Reacciones y Comentarios en Posts (4)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.social_action.like` | create | POST /rest/socialActions | Dar like a un post | target (postUrn) | confirmación | w_member_social | E | — |
| [ ] | `linkedin.social_action.unlike` | delete | DELETE /rest/socialActions | Quitar like de un post | target (postUrn) | confirmación | w_member_social | — | — |
| [ ] | `linkedin.social_action.comment` | create | POST /rest/socialActions | Comentar en un post | target (postUrn), text | comment URN | w_member_social | E | — |
| [ ] | `linkedin.social_action.get_comments` | read | GET /rest/socialActions?q=target&target={postUrn} | Obtener comentarios de un post | postUrn | lista de comentarios con autores y timestamps | r_basicprofile | — | — |

### Anuncios y Campañas (Ads Manager) (17)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.ads.create_account` | create | POST /rest/adAccounts | Crear cuenta de publicidad | currency,name,type,notifiedOn* | account URN, id en X-Restli-Id | rw_ads | — | — |
| [ ] | `linkedin.ads.get_account` | read | GET /rest/adAccounts/{adAccountId} | Obtener cuenta publicitaria | adAccountId | cuenta con presupuesto, estado, información contacto | r_ads | — | — |
| [ ] | `linkedin.ads.list_accounts` | read | GET /rest/adAccounts | Listar cuentas publicitarias del usuario | ninguno | lista de cuentas | r_ads | — | — |
| [ ] | `linkedin.ads.create_campaign_group` | create | POST /rest/adAccounts/{adAccountId}/adCampaignGroups | Crear grupo de campañas | name,runSchedule,totalBudget | campaign group URN | rw_ads | I | — |
| [ ] | `linkedin.ads.list_campaign_groups` | read | GET /rest/adAccounts/{adAccountId}/adCampaignGroups | Listar grupos de campañas | adAccountId | lista de grupos con presupuesto y estado | r_ads | — | — |
| [ ] | `linkedin.ads.create_campaign` | create | POST /rest/adAccounts/{adAccountId}/adCampaigns | Crear campaña de publicidad (TEXT_AD, SPONSORED_UPDATES, etc) | name,type,dailyBudget,runSchedule,targetingCriteria | campaign URN, id en header | rw_ads | I | — |
| [ ] | `linkedin.ads.get_campaign` | read | GET /rest/adCampaigns/{campaignId} | Obtener detalles de campaña | campaignId | campaña con estado, presupuesto, targeting, tipo | r_ads | — | — |
| [ ] | `linkedin.ads.list_campaigns` | read | GET /rest/adCampaigns | Listar campañas por cuenta | accountId, filters | lista de campañas | r_ads | — | — |
| [ ] | `linkedin.ads.update_campaign` | update | PATCH /rest/adCampaigns/{campaignId} | Actualizar campaña (estado, presupuesto, targeting) | campaignId, fields | campaña actualizada | rw_ads | I | — |
| [ ] | `linkedin.ads.create_creative` | create | POST /rest/adAccounts/{adAccountId}/creatives | Crear creativo publicitario (texto, imagen, vídeo) | campaign,type,variables,status | creative URN, id en header | rw_ads | I | — |
| [ ] | `linkedin.ads.get_creative` | read | GET /rest/creatives/{creativeId} | Obtener detalles de creativo | creativeId | creativo con campos variables según tipo | r_ads | — | — |
| [ ] | `linkedin.ads.list_creatives` | read | GET /rest/creatives | Listar creativos por cuenta/campaña | accountId, campaignId, filters | lista de creativos | r_ads | — | — |
| [ ] | `linkedin.ads.update_creative` | update | PATCH /rest/creatives/{creativeId} | Actualizar creativo | creativeId, variables, status | creativo actualizado | rw_ads | I | — |
| [ ] | `linkedin.ads.get_targeting_facets` | read | GET /rest/adTargetingFacets | Obtener tipos de targeting disponibles | ninguno | lista de facets: locations, industries, seniorities, etc | rw_ads | — | — |
| [ ] | `linkedin.ads.get_targeting_entities` | read | GET /rest/adTargetingEntities?q=adTargetingFacet&facet=... | Obtener valores de targeting (ubicaciones, industrias, seniorities) | facetUrn | lista de entidades targetables con URN y nombre | rw_ads | — | — |
| [ ] | `linkedin.ads.get_audience_count` | read | GET /rest/audienceCounts?q=targetingCriteria&target... | Estimar tamaño de audiencia con targeting | includedTargetingFacets, excludingTargetingFacets | {total, active} miembros | rw_ads | — | — |
| [ ] | `linkedin.ads.get_budget_pricing` | read | GET /rest/adBudgetPricing?q=criteria&... | Obtener sugerencias de bid y límites de presupuesto | targetingCriteria, bidType, dailyBudget | suggestedBid, dailyBudgetLimits, bidLimits con min/max | rw_ads | — | — |

### Analytics y Reporting (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.analytics.get_campaign_analytics` | read | GET /rest/adAnalyticsReporting | Obtener métricas de campaña (impresiones, clics, conversiones) | campaignId, dateRange, granularity | impresiones, clics, conversiones, CPC, CTR | r_ads | — | — |
| [ ] | `linkedin.analytics.get_account_analytics` | read | GET /rest/adAccountsAnalyticsReporting | Obtener métricas agregadas de cuenta | accountId, dateRange | gasto, impresiones, clics totales | r_ads | — | — |

### Lead Gen (Formularios) (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.leads.get_form` | read | GET /rest/leadGenForms/{formId} | Obtener definición de formulario de lead gen | formId | campos, preguntas, configuración de privacidad | rw_ads | — | — |
| [ ] | `linkedin.leads.list_forms` | read | GET /rest/leadGenForms | Listar formularios de lead gen de la cuenta | accountId | lista de formularios con metadatos | rw_ads | — | — |
| [ ] | `linkedin.leads.get_submissions` | read | GET /rest/leadGenSubmissions?q=form&form={formId} | Obtener respuestas a formulario de lead gen | formId, dateRange | lista de leads con respuestas, emails, timestamps | r_compliance | — | — |

### Audiencias Matched (DMP) (7)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.audience.create_segment` | create | POST /rest/dmpSegments | Crear audiencia/segmento para targeting | name,description,rules | segment URN | rw_ads | I | — |
| [ ] | `linkedin.audience.list_segments` | read | GET /rest/dmpSegments | Listar segmentos DMP | accountId | lista de segmentos con tamaño | rw_ads | — | — |
| [ ] | `linkedin.audience.add_users_to_segment` | create | POST /rest/dmpSegmentUsers | Añadir usuarios/contactos a segmento | segmentUrn, users (emails/hashes) | confirmación | rw_ads | I | — |
| [ ] | `linkedin.audience.remove_users_from_segment` | delete | DELETE /rest/dmpSegmentUsers | Quitar usuarios/contactos de segmento | segmentUrn, users | confirmación | rw_ads | — | — |
| [ ] | `linkedin.audience.create_list_upload` | create | POST /rest/dmpSegmentListUploads | Subir lista de contactos CSV para segmento | segmentUrn, csvFile | upload URN | rw_ads | I | — |
| [ ] | `linkedin.audience.get_predictive_audiences` | read | GET /rest/predictiveAudiences | Obtener audiencias predictivas disponibles | ninguno | lista de audiencias: job changers, high intent, etc | rw_ads | — | — |
| [ ] | `linkedin.audience.create_website_retargeting_pixel` | create | POST /rest/conversionTrackers | Crear pixel de retargeting para sitio web | name, redirectUrl | pixel id | rw_ads | I | — |

### Eventos (Event Management) (5)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.event.create` | create | POST /rest/events | Crear evento en LinkedIn | name,startDate,endDate,description,registrationUrl | event URN, id | w_organization_social | E, I | — |
| [ ] | `linkedin.event.get` | read | GET /rest/events/{eventId} | Obtener detalles de evento | eventId | evento con fecha, descripción, asistentes | r_basicprofile | — | — |
| [ ] | `linkedin.event.list` | read | GET /rest/events | Listar eventos de organización | organizationUrn, dateRange | lista de eventos | r_basicprofile | — | — |
| [ ] | `linkedin.event.update` | update | PATCH /rest/events/{eventId} | Actualizar evento | eventId, fields | evento actualizado | w_organization_social | I | — |
| [ ] | `linkedin.event.get_registrations` | read | GET /rest/eventRegistrations | Obtener registros a evento | eventId | lista de miembros registrados | w_organization_social | — | — |

### Menciones y Monitoreo de Marca (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.brand_monitoring.search_mentions` | read | GET /rest/socialMentions?q=keywords&organization={orgUrn} | Buscar menciones de marca en LinkedIn | keywords, organizationUrn, timeRange | posts con menciones, autores, timestamps | rw_organization_admin | — | — |
| [ ] | `linkedin.brand_monitoring.get_notifications` | read | GET /rest/organizationSocialActionNotifications | Obtener notificaciones de menciones/reacciones | organizationUrn, filters | menciones, comentarios, likes por período | rw_organization_admin | — | — |

### Perfiles y Conexiones (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.member.get_lite_profile` | read | GET /v2/liteProfiles | Obtener perfil lite del usuario (legacy) | user_id | perfil con firstName, lastName, profilePicture | r_liteprofile | — | — |
| [ ] | `linkedin.member.get_email` | read | GET /v2/emailAddress | Obtener email del usuario autenticado (legacy) | ninguno | {elements: [{handle, handle~: {emailAddress}}} | r_emailaddress | — | — |

### Seguidores (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.follower.follow_organization` | create | POST /rest/follows | Seguir organización | targetUrn (organization) | confirmación | w_member_social | E | — |
| [ ] | `linkedin.follower.unfollow_organization` | delete | DELETE /rest/follows | Dejar de seguir organización | targetUrn | confirmación | w_member_social | — | — |

### Búsqueda e Inteligencia (1)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.search.company_intelligence` | read | GET /rest/companyIntelligence | Obtener datos de inteligencia empresarial (impresiones, clicks, leads) | organizationUrn, timeRange, filters | engagement score, paid impressions, organic impressions | r_ads | — | — |

### Media Planning (3)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.media_plan.create` | create | POST /rest/mediaPlans | Crear plan de medios para campaign | name, budget, dateRange, targetingCriteria | media plan URN | rw_ads | I | — |
| [ ] | `linkedin.media_plan.get` | read | GET /rest/mediaPlans/{planId} | Obtener plan de medios | planId | plan con presupuesto, targeting, performance | rw_ads | — | — |
| [ ] | `linkedin.media_plan.list` | read | GET /rest/mediaPlans | Listar planes de medios | accountId | lista de planes | rw_ads | — | — |

### Conversiones (Pixel de Conversión) (2)

| Hecho | Id | Verbo | Endpoint | Qué hace | Entrada | Resultado | Permiso | Marcas | Herramienta vieja |
|---|---|---|---|---|---|---|---|---|---|
| [ ] | `linkedin.conversion.send_event` | create | POST /rest/conversions | Enviar evento de conversión desde sitio web | conversionId, user, value, timestamp | confirmación | rw_ads | I | — |
| [ ] | `linkedin.conversion.get_tracker` | read | GET /rest/conversionTrackers | Obtener conversión tracker/pixel | trackerId | configuración del pixel | rw_ads | — | — |
