"""Google Drive: OAuth 2.0 con codigo de autorizacion y refresco (Google Identity).

Verificado en el Discovery Document oficial de Drive v3 (www.googleapis.com/discovery/v1/apis/drive/v3/rest, 2026-10-10).

Reutiliza las cuentas que ya guarda el login de Google existente (app/integrations/providers/google/auth.py), para que el usuario NO
tenga que reconectar:
- mismo cliente OAuth (DRIVE_CLIENT_ID / DRIVE_CLIENT_SECRET) y mismos scopes exactos del servicio "drive":
  openid, email, profile (BASE_SCOPES) + https://www.googleapis.com/auth/drive.
- provider="google_drive" en user_connected_accounts. OJO: el login viejo guarda `account_id` = el CORREO de Google (no el permissionId
  que usa Google Slides), asi que la whoami `google_drive.about.get` devuelve `account_id` = correo para que coincida con esas cuentas.
- access_type=offline + prompt=consent: sin eso Google no entrega refresh_token (igual que el login viejo).
- Un 403 es scope insuficiente (connections.py lo traduce a missing_scope sin marcar la cuenta como vencida).
- En la consola de Google Cloud debe estar habilitada la Google Drive API.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="google_drive",
    provider_keys=["google_drive"],
    api_version="v3",
    multi_account=True,
    whoami="google_drive.about.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/drive",
        ],
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"access_type": "offline", "prompt": "consent"},  # sin esto Google no entrega refresh_token
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="DRIVE_CLIENT_ID",
        client_secret_env="DRIVE_CLIENT_SECRET",
    ),
))
