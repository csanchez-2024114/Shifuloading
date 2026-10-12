"""Google Docs: OAuth 2.0 con codigo de autorizacion y refresco (Google Identity), reutilizando las cuentas del login de Google.

Verificado contra la referencia oficial de Google Docs API v1 (developers.google.com/docs/api/reference/rest, 2026-10-11):
- Autorizacion GET https://accounts.google.com/o/oauth2/v2/auth; intercambio y refresco POST https://oauth2.googleapis.com/token
  (form-encoded, igual que la estrategia oauth2_code). El access_token dura 3600 s.
- Google solo entrega `refresh_token` con `access_type=offline` (y solo la primera vez salvo `prompt=consent`): van en authorize_params.
- Se usa el MISMO cliente OAuth que el login actual (app/integrations/providers/google/auth.py: DRIVE_CLIENT_ID / DRIVE_CLIENT_SECRET) y
  el provider="google_docs" con account_id = correo de Google, igual que lo guarda el login actual.
- Scopes: el login legacy del servicio "docs" (SERVICE_SCOPES["docs"]) pide openid, email, profile y `documents`, y es el unico login que
  conecta una cuenta google_docs; con eso se leen, crean y editan documentos. BUSCAR documentos por nombre y RENOMBRARLOS es Drive API,
  que NO acepta el scope `documents`, y ese login no concede Drive: por eso esas dos funciones no existen aqui. Las hace la app
  google_drive (files.search con file_type "document", files.rename), que exige tener Google Drive conectado.
- Un 403 es falta de scope O documento no compartido con la cuenta; connections.py lo separa (missing_scope / access_denied / rate_limited)
  sin marcar la cuenta como vencida.
- En la consola de Google Cloud hay que HABILITAR la Google Docs API en el proyecto del cliente OAuth.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="google_docs",
    provider_keys=["google_docs"],
    api_version="v1",
    multi_account=True,
    whoami="google_docs.account.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/documents",
        ],
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"access_type": "offline", "prompt": "consent"},  # sin esto Google no entrega refresh_token
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="DRIVE_CLIENT_ID",
        client_secret_env="DRIVE_CLIENT_SECRET",
    ),
))
