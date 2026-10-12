"""Facebook (Meta Graph API v26.0): OAuth 2.0 con codigo (Facebook Login). Sin refresh_token: el token de usuario es corto.

Verificado en developers.facebook.com (2026-10-07): dialog/oauth y oauth/access_token de la version v26.0. Usa la app de LOGIN de Meta del
sistema viejo (META_LOGIN_APP_ID / META_LOGIN_APP_SECRET, tipo Consumidor). La app de empresa (META_APP_ID) no sirve: su login es «Facebook
Login for Business», que rechaza public_profile («necesita al menos un permiso compatible») y pide un config_id que el AuthSpec no puede leer
del entorno. provider="facebook"; account_id = id de usuario con alcance de app (sale de `whoami`).
POR RESOLVER (plataforma, Alan): token largo por intercambio (fb_exchange_token); Meta responde un token vencido con HTTP 400 y codigo 190
(no 401), asi que hoy se veria como invalid_input y no como auth_expired.
POR COMPROBAR: la documentacion muestra el intercambio del codigo por GET; accounts.py lo hace por POST con formulario.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="facebook",
    provider_keys=["facebook"],
    api_version="v26.0",
    multi_account=True,
    whoami="facebook.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["public_profile"],
        authorize_url="https://www.facebook.com/v26.0/dialog/oauth",
        token_url="https://graph.facebook.com/v26.0/oauth/access_token",
        client_id_env="META_LOGIN_APP_ID",
        client_secret_env="META_LOGIN_APP_SECRET",
    ),
))
