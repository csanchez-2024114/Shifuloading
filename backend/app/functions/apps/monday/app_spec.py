"""monday.com: OAuth 2.0 con codigo (flujo clasico): el token NO caduca y no hay refresh_token.

Verificado en developer.monday.com (2026-10-07): authorize_url, token_url, scopes y respuesta del token (`scope` separado por espacios).
El token vale hasta que el usuario desinstala la app; un 401 sin refresh_token deja la cuenta en auth_expired (ya funciona asi).
La API pide el token crudo en `Authorization` (sin "Bearer"), de ahi scheme="".
provider="monday"; account_id = id del USUARIO de monday que conecto (sale de `whoami`).
Los scopes pedidos deben estar activados en la pestana «OAuth y permisos > Alcances» de la app en el Developer Center: si falta uno,
monday rechaza el login con invalid_scope. Incluye ya los de lectura de las tareas 3 y 4 para conectar una sola vez.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="monday",
    provider_keys=["monday"],
    api_version="2026-10",
    multi_account=True,
    whoami="monday.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["me:read", "account:read", "users:read", "boards:read", "workspaces:read", "teams:read", "updates:read", "docs:read",
                "webhooks:read"],
        authorize_url="https://auth.monday.com/oauth2/authorize",
        token_url="https://auth.monday.com/oauth2/token",
        client_id_env="MONDAY_CLIENT_ID",
        client_secret_env="MONDAY_CLIENT_SECRET",
        scheme="",
    ),
))
