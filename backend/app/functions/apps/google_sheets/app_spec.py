"""Google Sheets: OAuth 2.0 con codigo de autorizacion y refresco (Google Identity), reutilizando las cuentas del login de Google.

Verificado contra la referencia oficial de Google Sheets API v4 (developers.google.com/sheets/api/reference/rest, 2026-10-10):
- Autorizacion GET https://accounts.google.com/o/oauth2/v2/auth; intercambio y refresco POST https://oauth2.googleapis.com/token
  (form-encoded, igual que la estrategia oauth2_code). El access_token dura 3600 s.
- Google solo entrega `refresh_token` con `access_type=offline` (y solo la primera vez salvo `prompt=consent`): van en authorize_params.
- Se usa el MISMO cliente OAuth que el login actual (app/integrations/providers/google/auth.py: DRIVE_CLIENT_ID / DRIVE_CLIENT_SECRET) y
  EXACTAMENTE los scopes del login legacy (openid, email, profile, spreadsheets), para que las cuentas ya guardadas en
  user_connected_accounts (provider="google_sheets", account_id = correo de Google) sirvan sin reconectar.
- Con solo el scope `spreadsheets` NO se pueden listar las hojas de calculo del usuario (eso es Drive API): no se agrega un scope de Drive
  porque obligaria a reconectar. El usuario (o el agente) debe dar la URL o el id de la hoja; las funciones aceptan ambos.
- La identidad (whoami) sale del endpoint OpenID userinfo (https://openidconnect.googleapis.com/v1/userinfo), que acepta los scopes openid/email/profile.
- Un 403 (PERMISSION_DENIED) significa falta de scope O que la hoja no es de esa cuenta ni esta compartida con ella; connections.py lo traduce
  a missing_scope sin marcar la cuenta como vencida.
- En la consola de Google Cloud hay que HABILITAR la Google Sheets API en el proyecto del cliente OAuth.

provider="google_sheets"; account_id = correo de la cuenta de Google (igual que lo guarda el login actual).
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="google_sheets",
    provider_keys=["google_sheets"],
    api_version="v4",
    multi_account=True,
    whoami="google_sheets.account.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"access_type": "offline", "prompt": "consent"},  # sin esto Google no entrega refresh_token
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="DRIVE_CLIENT_ID",
        client_secret_env="DRIVE_CLIENT_SECRET",
    ),
))
