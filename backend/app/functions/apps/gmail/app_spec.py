"""Gmail: OAuth 2.0 con codigo de autorizacion y refresco (Google Identity), reutilizando las cuentas que ya guarda el login de Google.

Verificado en el Discovery Document oficial (gmail.googleapis.com/$discovery/rest?version=v1, 2026-10-10):
- Autorizacion GET https://accounts.google.com/o/oauth2/v2/auth; intercambio y refresco POST https://oauth2.googleapis.com/token
  (igual que la estrategia oauth2_code: no hay codigo de conexion nuevo). El access_token dura 3600 s.
- Google solo entrega `refresh_token` con `access_type=offline` (y solo la primera vez salvo `prompt=consent`): van en authorize_params.
- MISMA conexion que el flujo viejo (app/integrations/providers/google/auth.py): provider="gmail", account_id = el correo de Google
  (se guarda `google_email`), mismo cliente OAuth (DRIVE_CLIENT_ID / DRIVE_CLIENT_SECRET) y exactamente los mismos scopes. Asi los
  usuarios que ya conectaron Gmail no tienen que reconectar. El flujo viejo guarda access_token/refresh_token por separado (no
  credentials_enc); `get_connection` ya lee ese formato.
- Scopes (los del flujo viejo):
    openid, email, profile      identifican a la persona (el flujo viejo los pide siempre)
    gmail.readonly              leer mensajes, etiquetas y perfil
    gmail.modify                leer, cambiar etiquetas y ENVIAR / crear borradores (users.messages.send y users.drafts.create
                                aceptan gmail.modify; ver Discovery). No permite borrar definitivamente (eso es mail.google.com)
- En la consola de Google Cloud hay que HABILITAR la Gmail API. gmail.readonly y gmail.modify son scopes RESTRINGIDOS: en produccion
  piden verificacion de Google; en modo «Testing» el refresh_token caduca a los 7 dias.
- Un scope insuficiente responde HTTP 403 (que connections.py traduce a missing_scope sin marcar la cuenta como vencida). Ojo: Gmail
  tambien responde 403 para el limite de ritmo (rateLimitExceeded / userRateLimitExceeded); functions.py lo distingue.

provider="gmail"; whoami = gmail.profile.get (users.getProfile devuelve emailAddress, que es el account_id guardado).
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="gmail",
    provider_keys=["gmail"],
    api_version="v1",
    multi_account=True,
    whoami="gmail.profile.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"access_type": "offline", "prompt": "consent"},  # sin esto Google no entrega refresh_token
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="DRIVE_CLIENT_ID",          # el mismo cliente OAuth de Google que usa el flujo viejo
        client_secret_env="DRIVE_CLIENT_SECRET",
    ),
))
