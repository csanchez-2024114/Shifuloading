"""Instagram (API de Instagram con inicio de sesion de Instagram / Business Login): OAuth 2.0 con codigo; token corto (1 h), sin refresh_token.

Verificado en developers.facebook.com (2026-10-07): authorize en www.instagram.com/oauth/authorize, intercambio por POST con formulario en
api.instagram.com/oauth/access_token. Solo cuentas profesionales (empresa o creador). Usa las credenciales de la app de Instagram que ya tiene
el sistema viejo (META_INSTAGRAM_LOGIN_APP_ID / _SECRET). provider="instagram"; account_id = user_id de la cuenta profesional (sale de `whoami`).
POR COMPROBAR (plataforma, Alan): la documentacion muestra la respuesta del token envuelta en {"data": [{access_token, user_id, permissions}]};
accounts.py espera access_token en la raiz. Y el token largo de 60 dias pide un intercambio (ig_exchange_token).
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="instagram",
    provider_keys=["instagram"],
    api_version="v26.0",
    multi_account=True,
    whoami="instagram.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["instagram_business_basic"],
        authorize_url="https://www.instagram.com/oauth/authorize",
        token_url="https://api.instagram.com/oauth/access_token",
        client_id_env="META_INSTAGRAM_LOGIN_APP_ID",
        client_secret_env="META_INSTAGRAM_LOGIN_APP_SECRET",
    ),
))
