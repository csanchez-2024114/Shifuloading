# Modelo de datos: colecciones ↔ modelos ↔ código

Convención del repo: los modelos Pydantic (`app/models/**`, base `AppBaseModel`) existen para algunas colecciones, pero **casi todas las lecturas son diccionarios
crudos de Motor**. El sistema de funciones sigue eso: **los modelos Pydantic de `app/functions/spec.py` se usan al publicar y en la API**; la lectura de conexiones
trabaja con el diccionario del documento.

Constantes de nombre en `app/core/constants.py` (`Collections`). Se agregaron `FUNCTIONS` y `FUNCTION_APPS`.

## Colecciones nuevas

| Colección | Modelo (código) | Quién escribe | Quién lee | Índice |
|---|---|---|---|---|
| `functions` | `FunctionSpec` (`app/functions/spec.py`) + `spec_hash`, `created_at`, `updated_at` | `publish()` (`scripts/publish_functions.py`): **inserta** versiones nuevas y, si el contrato no cambió, **actualiza solo el texto** (`description`, `examples`, esquemas) de las existentes | `GET /internal/functions` (solo para el `status`) | única `(id, version)` |
| `function_apps` | `AppSpec` + `updated_at`, `created_at` | `publish()`: upsert por `app` | **nadie todavía** (el registro lee del código); queda para el selector y el canario | única `app` |

- Las **fichas viven en el código**; Mongo recibe una copia al publicar. Después de publicar, **`functions.status` es de Mongo** (se cambia sin desplegar) y `publish` no lo pisa.
- Los índices los crea `publish()` (idempotente), igual que `scripts/seed_agent_identity.py`; la app no crea índices al arrancar.

## Colección existente que se usa: `user_connected_accounts`

Clave lógica `(user_id, provider, account_id)`. Documentada en [`AUTENTICACION.md`](AUTENTICACION.md). Campos que usan las funciones:

| Campo | Existía | Notas |
|---|---|---|
| `user_id`, `provider`, `account_id`, `status` | sí | `provider` puede ser uno de varios (`AppSpec.provider_keys`; Google tiene varios) |
| `access_token`, `refresh_token` | sí | cifrados; `refresh_token` puede ser `n/a` |
| `credentials_enc` | **nuevo, opcional** | varios campos; nada lo escribe todavía |
| `last_refreshed_at` | **nuevo** | lo pone el refresco de la conexión |
| `last_health_check` | sí | también lo pone el marcado de "vencida" |
| `metadata` | sí | libre (Brevo guarda `auth_type`) |

Las funciones **escriben** en esta colección solo en dos casos, siempre por `_id`: refresco exitoso (`access_token`/`refresh_token` o `credentials_enc`, `status: active`,
`last_refreshed_at`) y 401 definitivo (`status: expired`, `last_health_check`). Todo documento existente sigue siendo válido (no hay migración).

## Otras colecciones que tocan o rodean al sistema

| Colección | Relación |
|---|---|
| `audit_events` | Cada prueba por API escribe `function_tested` (`extra`: versión, cuentas, ok, simulada, cruces de identidad). Append-only |
| `catalog_apps` | Qué apps existen (`name`, `nameApi`, `active`, `category`...). **No se modificó**; `authType` se deriva al leer de `login_paths.py`. Enlazarla con `function_apps` queda para el selector |
| `app_tools_catalog`, `BIGTOOLS_REGISTRY` | **Legado** (lista de nombres a mano). El catálogo de funciones los reemplazará; nada en el repo escribe `app_tools_catalog` |
| `tool_outcome_log` | Lo escribe `WorkflowExecutor`; las funciones nuevas aún no lo usan (llega con el puente al ejecutor) |
| `oauth_vault`, `users.integrations` | **Legado** de credenciales (clave por correo, una cuenta por proveedor). Las funciones **no los leen**. Plan de migración: F1 del plan maestro |
| `user_secrets` | Secretos personales con otra llave (`SECRETS_ENCRYPTION_KEY`). Las funciones no los leen |

## Qué es de la base de datos y qué es del código

| Dato | Fuente de verdad |
|---|---|
| Ficha (campos, esquemas, ejemplos) | **Código** |
| `status` de una función publicada | **Mongo** |
| Credenciales y estado de la cuenta | **Mongo** (`user_connected_accounts`) |
| Cómo se autentica una app (`AuthSpec`) | **Código** |
| Resultado de las pruebas | Respuesta de la API + `audit_events`; el registro del junior va en Postman |
