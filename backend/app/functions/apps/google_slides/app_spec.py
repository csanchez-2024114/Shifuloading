"""Google Slides: OAuth 2.0 con codigo de autorizacion y refresco (Google Identity).

Verificado en el Discovery Document oficial (slides.googleapis.com/$discovery/rest?version=v1 y drive v3, 2026-10-08):
- Autorizacion GET https://accounts.google.com/o/oauth2/v2/auth; intercambio y refresco POST https://oauth2.googleapis.com/token
  (form-encoded, igual que la estrategia oauth2_code: no hay codigo de conexion nuevo). El access_token dura 3600 s.
- Google solo entrega `refresh_token` si se pide `access_type=offline`, y solo la primera vez salvo que se fuerce
  `prompt=consent`: por eso van en authorize_params (igual que token_access_type en Dropbox).
- El token trae `scope` con las URL completas separadas por espacios; esas URL son las que se guardan en «Permisos concedidos».
- Scopes: la Slides API acepta presentations(.readonly), drive, drive.file y drive.readonly, pero NO acepta drive.metadata.*.
  Los scopes de Drive son los que cubren la whoami (about.get y files.list aceptan drive.metadata.readonly). Se piden los minimos:
    presentations.readonly      leer presentaciones, paginas y miniaturas (Slides API)
    drive.metadata.readonly     identidad de la cuenta (about) y listar presentaciones (Drive API), sin leer su contenido
    presentations               crear presentaciones y modificarlas (batchUpdate: agregar/duplicar diapositivas, reemplazar texto)
  Las lecturas siguen pidiendo solo presentations.readonly. El login legacy de "slides" (app/integrations/providers/google/auth.py,
  SERVICE_SCOPES["slides"]) ya concede `presentations`, asi que las escrituras funcionan en las cuentas conectadas con el, sin
  reconectar. Lo que a esas cuentas legacy les falta es `drive.metadata.readonly`, que necesita `presentations.list` (y la whoami).
- En la consola de Google Cloud hay que HABILITAR las dos APIs (Google Slides API y Google Drive API) y configurar la pantalla de
  consentimiento; en modo «Testing» solo entran las cuentas agregadas como usuarios de prueba y el refresh_token caduca a los 7 dias.
- Un scope insuficiente responde HTTP 403 (PERMISSION_DENIED / ACCESS_TOKEN_SCOPE_INSUFFICIENT), que connections.py ya traduce a
  missing_scope sin marcar la cuenta como vencida, asi que no hace falta scope_error_marker (solo mira 400/401).
- La app necesita redirect http://localhost:8001/function-apps/google_slides/oauth-callback registrado tal cual en
  Credenciales > ID de cliente OAuth (tipo «Aplicacion web»).

provider="google_slides"; account_id = permissionId de Drive del usuario (estable), que sale de la whoami `google_slides.presentations.list`.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="google_slides",
    provider_keys=["google_slides"],
    api_version="v1",
    multi_account=True,
    whoami="google_slides.presentations.list",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[
            "https://www.googleapis.com/auth/presentations.readonly",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
            "https://www.googleapis.com/auth/presentations",
        ],
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        authorize_params={"access_type": "offline", "prompt": "consent"},  # sin esto Google no entrega refresh_token
        token_url="https://oauth2.googleapis.com/token",
        client_id_env="GOOGLE_SLIDES_CLIENT_ID",
        client_secret_env="GOOGLE_SLIDES_CLIENT_SECRET",
    ),
))
