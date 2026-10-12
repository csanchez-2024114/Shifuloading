"""ClickUp: OAuth 2.0 con codigo de autorizacion (o token personal pk_*), sin refresh.

Verificado en la documentacion oficial (developer.clickup.com/docs/authentication, 2026-10-08):
- Pantalla de consentimiento: https://app.clickup.com/api?client_id=..&redirect_uri=..&state=..  (ClickUp NO usa scopes).
- Intercambio: POST https://api.clickup.com/api/v2/oauth/token (client_id, client_secret, code). El token no caduca y no hay refresh_token.
- El token va CRUDO en `Authorization` (los tokens personales empiezan por `pk_`), por eso scheme="".
- Errores (developer.clickup.com/docs/common_errors): "Team not authorized" llega como 401 con ECODE OAUTH_023, OAUTH_026, OAUTH_027 y
  OAUTH_029..OAUTH_045: el token es valido pero el usuario no autorizo ese Workspace. Eso es un permiso faltante, no un token vencido, por eso
  scope_error_marker: sin el, esos 401 marcarian la cuenta como vencida. Los codigos de "token no encontrado" (OAUTH_019/021/025/077)
  siguen siendo auth_expired.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="clickup",
    provider_keys=["clickup"],
    api_version="v2",
    multi_account=True,
    whoami="clickup.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=[],  # ClickUp no tiene scopes: el acceso depende del rol del usuario y de los Workspaces que autorizo
        scheme="",  # token crudo: Authorization: <access_token>
        header_name="Authorization",
        authorize_url="https://app.clickup.com/api",
        token_url="https://api.clickup.com/api/v2/oauth/token",
        client_id_env="CLICKUP_CLIENT_ID",
        client_secret_env="CLICKUP_CLIENT_SECRET",
        scope_error_marker=r"OAUTH_0(?:23|26|27|29|3\d|4[0-5])\b",
    ),
))
