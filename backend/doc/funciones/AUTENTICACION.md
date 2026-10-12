# Autenticación y conexiones

El mercado no es solo OAuth 2.0: hay claves de API, tokens largos, usuario y clave, varios campos (Trello), firmas OAuth 1, credenciales de servidor...
Por eso la autenticación es un **registro de estrategias** (`app/functions/auth/`): una clase por método, y cada app declara cuál usa en su `AuthSpec`.

## Estrategias

| `AuthType` | Cómo aplica la credencial | Refresca | Estado | Ejemplo |
|---|---|---|---|---|
| `oauth2_code` | `Authorization: Bearer <access_token>` (configurable con `header_name` y `scheme`) | sí, con `refresh_token`, `token_url` y las variables `client_id_env` / `client_secret_env` | **implementada** | Dropbox, Google, Asana, HubSpot |
| `bearer` | Token largo en un header (`scheme=None` → `Bearer`; `""` → crudo; `"Bot"`...) | no | **implementada** | ClickUp (`scheme=""`), Notion, Slack bot |
| `api_key` | Una clave en un header (`header_name`) o en la query (`placement="query"`, `param_names[0]`) | no | **implementada** | Brevo (`api-key`) |
| `basic` | `Authorization: Basic base64(username:password)` (campos `username` y `password`) | no | **implementada** | APIs con usuario y clave |
| `custom_params` | Varios campos (`param_names`) en headers o query según `placement` | no | **implementada** | Trello (`key` + `token` en la query) |
| `none` | Nada | — | **implementada** | APIs públicas |
| `oauth2_client_credentials` | — | — | **declarada, sin implementar** | PedidosYa (servidor a servidor) |
| `oauth1` (firma) | — | — | **declarada, sin implementar** | OAuth 1 con firma real (hoy ningún proveedor del repo firma) |
| `hmac_signature` | — | — | **declarada, sin implementar** | Webhooks y APIs con firma HMAC |

Una app con un tipo sin implementar **no pasa** `validate_registry()` (falla en voz alta al cargar); no se salta en silencio.

### Cómo agregar un método nuevo

1. En `app/functions/auth/strategies.py` (o un archivo nuevo importado en `auth/__init__.py`), una clase que herede de `AuthStrategy`, con `apply(req, creds, spec)`
   (y `refresh(...)` + `can_refresh = True` si el método renueva credenciales), decorada con `@register_auth(AuthType.xxx)`.
2. Si hace falta algún dato de configuración nuevo, un campo opcional en `AuthSpec` (`spec.py`).
3. Pruebas en `test/functions/test_auth.py` (y, si refresca, en `test_connections.py`). Actualizar `implemented_types()` en esa prueba.
4. Actualizar esta tabla y `CHANGELOG.md`.

## Dónde se guardan las credenciales

**Un solo almacén: `user_connected_accounts`** (decisión del plan maestro). Clave única lógica: `user_id + provider + account_id`.

| Campo | Uso |
|---|---|
| `access_token` | Credencial de **un solo campo** (token o API key), cifrada con `encrypt_data` (Fernet, `ENCRYPTION_KEY`) |
| `refresh_token` | Cifrado, o `n/a` / vacío si no hay |
| `credentials_enc` | **Nuevo, opcional:** credenciales de **varios campos** como JSON cifrado con el mismo Fernet (`{"key": "...", "token": "..."}`, o `username` + `password`). Si existe, manda sobre `access_token` |
| `status` | `active`, `needs_refresh` (usables), `expired`, `revoked` |
| `account_id` | Id de la cuenta en la app (correo, id de cuenta...) |

Reglas de la conexión (`get_connection`):

- **Descifrado estricto:** si no descifra, la función devuelve `auth_expired`; **nunca** se manda el texto cifrado como si fuera un token ni se marca la cuenta como vencida.
- **Una cuenta usable** → se usa. **Ninguna** → `missing_connection`. **Varias sin `account_id`** → `account_selection_required`. Con `account_id` → esa; si existe pero está vencida → `auth_expired`.
- **Refresco y marcado de "vencida" se hacen por el `_id` exacto del documento**, nunca por usuario+proveedor (en el código viejo, `refresh_google_token_v2` y el health check sí lo hacen por proveedor y pueden cruzar cuentas).
- Un `401` definitivo marca **esa** cuenta como `expired`. Si la app dice que falta un permiso con un 401 (Dropbox: `missing_scope`), se declara en `AuthSpec.scope_error_marker`
  y se devuelve `missing_scope` **sin** refrescar y **sin** marcar la cuenta.
- No se registran tokens ni cabeceras de petición. El mensaje de error de una función incluye los primeros 200 caracteres de la respuesta de error de la app (puede traer datos de la app; no son nuestras credenciales).

> **Brecha conocida:** hoy **nada escribe `credentials_enc`**. Una app tipo Trello necesita un endpoint de conexión que lo guarde; falta construirlo.
> Las apps de un solo campo (OAuth2, Brevo) ya tienen su flujo: callbacks de `app/integrations/providers/*` y `POST /api/v1/integrations/` (`add_integration`).

## Apps actuales por método (leído del código, **no ejecutado**)

| Método | Apps (`app/integrations/providers/`) |
|---|---|
| OAuth 2 con código y refresco | Google (gmail, drive, docs, sheets, slides, calendar), Asana, HubSpot, Dropbox, Jira (cloud_id), Teams, Outlook, OneDrive, Discord, LinkedIn, Monday, Salesforce, TikTok, Uber Eats |
| OAuth 2 + PKCE | Twitter, Kick |
| OAuth 2 sin refresco (token largo) | ClickUp (token crudo, sin `Bearer`), Notion (Basic al pedir el token), Slack (bot), Facebook / Instagram / Threads (token largo de Meta), Mailchimp (`Authorization: OAuth <token>`, deshabilitado) |
| API key | Brevo (`/key`), y las de `APIKEY_APPS`: openai, anthropic, huggingface, replicate (se conectan por `/api/v1/me/secrets`) |
| Clave de app + token del usuario | Trello (`key` + `token` en la query; `OAUTH1_APPS` lo marca como OAuth1 pero no hay firma) |
| Servidor a servidor | PedidosYa (`client_credentials`, escribe en `oauth_vault`) |
| Sin credencial de usuario utilizable | Telegram (widget con HMAC, guarda solo metadata), WhatsApp (webhook, token global por entorno), OnlyFans (solo redirección) |

## Deuda detectada en el código antiguo (no se corrige aquí)

`_normalize_integrations(raw, source, email)` recibe `correo=` en `providers/{dropbox,facebook,hubspot,jira}.py` y `providers/google/{docs,drive,sheets,slides}.py` (`TypeError`);
`hubspotTool.py` y `facebookTool.py` llaman a funciones de credenciales que no existen; `refreshTokens.py:118` desempaqueta como tupla lo que devuelve un dict;
solo las herramientas de Google leen `user_connected_accounts` (Asana, ClickUp, HubSpot, Facebook y Dropbox leen el legado `oauth_vault`); `handle_tool_error=True` convierte los
errores de las herramientas en texto normal, así que el ejecutor de workflows no los cuenta como fallo; `oauth_shared.py:89` registra tokens descifrados a nivel debug.
Por eso las funciones nuevas **no reutilizan** los conectores viejos. Detalle y plan de migración en el plan maestro (F1, F5).
