# Cambios del contrato y del sistema de funciones

Cada cambio del **contrato** (`contract_version`) o de las reglas se anota aquí con su fecha y el porqué. Cambios de una función concreta se ven en su `version` y en git.

## contract_version 1 · 2026-10-06, revisión: descripciones para el agente

Pedido del equipo: las descripciones las lee el agente para buscar y elegir funciones, así que deben estar en inglés y ser completas.
- `description` obligatoria **en inglés y de al menos 200 caracteres**; cada campo de **entrada** con `description` en inglés de al menos 10 caracteres. Ambos mínimos son hipótesis (se miden con el selector, T5). El idioma se comprueba con una heurística (`looks_spanish`), que puede dejar pasar español sin tildes.
- La huella `spec_hash` pasa a ser **la del contrato**: ignora `status`, `description`, `examples` y los `description`/`title` de los esquemas. Mejorar el texto ya no pide subir `version`; al republicar se actualiza el texto en Mongo (`functions_text_updated`) sin tocar el `status`.
- Se reescribieron en inglés las descripciones de Brevo, Dropbox y la plantilla (470 a 700 caracteres).
- Sigue en español: los mensajes de `FunctionError` (llegan al agente dentro de `Result.error.message`) y los errores del registro (son para el desarrollador). Decidir si los mensajes de error pasan a inglés.

## contract_version 1 · 2026-10-06 (primera base)

- Ficha `FunctionSpec`, app `AppSpec`/`AuthSpec`, resultado `Result` con `meta`, estados, política de confirmación derivada, huella `spec_hash`.
- **Nueve** códigos de error: los siete del diseño (`auth_expired`, `missing_scope`, `rate_limited`, `not_found`, `invalid_input`, `upstream_changed`, `upstream_down`)
  **más** `missing_connection` y `account_selection_required` (agregados al implementar: cubren "ninguna cuenta" y "varias sin elegir", que antes no tenían código).
- `AuthSpec.scope_error_marker` (agregado al implementar): Dropbox devuelve `missing_scope` como HTTP 401 y sin esto se confundiría con un token vencido.
- Convención `whoami` → campo `account_id` obligatorio (el mismo valor guardado al conectar).
- La salida de toda función se **revalida** en el ejecutor.
- Estrategias implementadas: `none`, `api_key`, `bearer`, `basic`, `custom_params`, `oauth2_code`. Declaradas sin implementar: `oauth1`, `oauth2_client_credentials`, `hmac_signature`.
- Apps de referencia: Brevo (`brevo.account.get`, `brevo.contacts.list`, `brevo.templates.list`) y Dropbox (`dropbox.account.get`, `dropbox.files.list`, `dropbox.files.search`), todas `draft`.
- Endpoints internos `GET /internal/functions`, `GET /internal/functions/{id}`, `POST /internal/functions/{id}/test`.
- Colecciones nuevas `functions` y `function_apps`; campos opcionales nuevos en `user_connected_accounts` (`credentials_enc`, `last_refreshed_at`).

### Limitaciones conocidas de esta versión

- Nada escribe `credentials_enc` todavía; falta el flujo de conexión para credenciales de varios campos.
- Sin canario, sin selector por búsqueda para el agente y sin puente con `WorkflowExecutor`.
- Las colecciones de Postman generadas se sobrescriben al regenerar (se pierden los ejemplos guardados si no se re-exporta desde Postman).
- Sin pruebas contra las APIs reales de Brevo y Dropbox ni contra un Mongo real.
