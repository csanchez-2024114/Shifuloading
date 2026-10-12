# Grupo C — Secrets vault (dual: conector real vs secreto personal)

- [x] Colección nueva `user_secrets` en `app/core/constants.py::Collections`
- [x] Env var nueva `SECRETS_ENCRYPTION_KEY` + función Fernet separada (no reusar `encrypt_data` global)
- [x] Router nuevo `app/routes/me/secrets.py`, `prefix="/api/v1/me/secrets"`
- [x] `POST /`: resolver si `service` matchea catálogo `authType="apikey"` → delega en lógica de `add_integration()`; si no → cifra con `SECRETS_ENCRYPTION_KEY` y crea en `user_secrets`
- [x] `GET /`: lista unificada (user_connected_accounts filtrado por APIKEY_APPS + user_secrets), marcada `is_connector`, solo `secret_preview`
- [x] `PATCH /{id}`, `DELETE /{id}` (rutea según prefijo sintético del id), `POST /{id}/reveal` (rate-limited, actualiza last_used_at/reveal_count)
- [x] Audit log en cada mutación/reveal, nunca loguear el valor
- [x] Frontend `features/secrets/index.tsx`: reemplazar mock por las 5 llamadas reales, autocomplete contra `GET /api/v1/catalog/apps`
- [x] Verificación: crear un secret personal y uno que matchee un app del catálogo, confirmar que este último aparece en Connectors
