"""Threads (Meta): OAuth 2.0 con codigo; token corto (1 h), sin refresh_token.

Verificado en developers.facebook.com/docs/threads (2026-10-07): authorize en threads.com/oauth/authorize (threads_basic es obligatorio),
intercambio por POST con formulario en graph.threads.com/oauth/access_token. Usa las credenciales de la app de Threads que ya tiene el
sistema viejo (THREADS_CLIENT_ID / THREADS_CLIENT_SECRET). provider="threads"; account_id = id de usuario de Threads (sale de `whoami`).
POR RESOLVER (plataforma, Alan): el token largo de 60 dias pide un intercambio (th_exchange_token).
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="threads",
    provider_keys=["threads"],
    api_version="v1.0",
    multi_account=True,
    whoami="threads.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["threads_basic"],
        authorize_url="https://threads.com/oauth/authorize",
        token_url="https://graph.threads.com/oauth/access_token",
        client_id_env="THREADS_CLIENT_ID",
        client_secret_env="THREADS_CLIENT_SECRET",
    ),
))
