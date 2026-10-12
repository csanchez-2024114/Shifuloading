"""Asana: OAuth 2.0 con codigo de autorizacion y refresco.

Verificado en la documentacion oficial (developers.asana.com/docs/oauth y /docs/oauth-scopes, 2026-10-07):
- Autorizacion GET https://app.asana.com/-/oauth_authorize; intercambio y refresco POST https://app.asana.com/-/oauth_token
  (form-encoded: grant_type, client_id, client_secret, redirect_uri, code). El refresh manda grant_type=refresh_token con
  client_id y client_secret, igual que ya hace la estrategia oauth2_code: no hay codigo de conexion nuevo.
- El `code` vuelve en el QUERY STRING (?code=...&state=...) y el access_token dura 3600 s. La respuesta del intercambio trae
  access_token, expires_in, token_type, refresh_token y `data` (id/gid/name/email) pero NO `scope`: los permisos reales se
  consultan con POST /-/token_info, asi que el campo `scopes` de la cuenta puede quedar vacio en /debug (avisar a Alan).
- Para que un usuario pueda autorizar, la app debe estar disponible en su workspace (Manage distribution, Specific workspace
  o Any workspace) y sus scopes registrados en la consola. Pedir un scope no registrado produce `forbidden_scopes` en la
  pantalla de consentimiento; Full permissions (scope=default) y scopes especificos son excluyentes entre si.
- 2026-10-07: la app "BunnyDrop" de Crhistian tiene activado "Full permissions" en la consola. Con Full permissions NO se
  pueden pedir scopes especificos en el authorize (`forbidden_scopes`), y Asana usa el scope "default" si no se manda
  `scope`. Por eso la lista de abajo quedo ARCHIVADA (comentario) y `scopes` queda vacio: el backend omite el parametro
  `scope` (accounts.py:67-68) y Asana otorga acceso completo. Si algun dia se pasa a scopes granulares, mover la lista
  abajo a `scopes=[...]` en AuthSpec.
- Redirect: la consola exige https en el registro. Si rechaza http://localhost:8001/function-apps/asana/oauth-callback,
  registrar un tunel https y fijar ASANA_FUNCTIONS_REDIRECT_URI (accounts.py lo lee) en lugar de tocar codigo.

Scopes granulares oficiales (la lista completa esta en /docs/oauth-scopes). El catalogo ATENCION/tareas/asana.md pide scopes
que NO existen (sections:read, status_updates:read, memberships:read, time_tracking:read, user_task_lists:read, ooo:read,
rates:read, reactions:read, time_periods:read, organization_exports:read, project_briefs:read, access_requests:read,
agents:read, allocations:read, audit_log:read, ai_studio_usage:read): pedirlos rompe la conexion. `workspaces.typeahead:read`
si existe en la lista oficial pero no en el esquema OAuth publicado: ya la usa `asana.typeahead.search` (Tarea 7) y esta en la lista
archivada de abajo junto con tasks:write y stories:write (Tarea 9).

provider="asana"; account_id = gid del usuario, que sale de la whoami `asana.users.get`.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="asana",
    provider_keys=["asana"],
    api_version="1.0",
    multi_account=True,
    whoami="asana.users.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[],
        # Archivo: scopes granulares (si se desactiva "Full permissions" en la consola, moverlos a `scopes`):
        # ["attachments:read", "custom_fields:read", "custom_types:read", "goals:read", "jobs:read",
        #  "ooo_entries:read", "portfolios:read", "project_portfolio_settings:read", "project_templates:read",
        #  "projects:read", "roles:read", "stories:read", "tags:read", "task_templates:read", "tasks:read",
        #  "team_memberships:read", "teams:read", "time_tracking_categories:read", "time_tracking_entries:read",
        #  "timesheet_approval_statuses:read", "users:read", "webhooks:read", "workspaces:read",
        #  "workspaces.typeahead:read", "tasks:write", "stories:write"],  # los dos ultimos: escrituras de la Tarea 9
        authorize_url="https://app.asana.com/-/oauth_authorize",
        token_url="https://app.asana.com/-/oauth_token",
        client_id_env="ASANA_CLIENT_ID",
        client_secret_env="ASANA_CLIENT_SECRET",
    ),
))
