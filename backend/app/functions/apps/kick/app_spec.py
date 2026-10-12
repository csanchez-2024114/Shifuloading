"""Kick: OAuth 2.1 con codigo, PKCE obligatorio (S256) y refresco.

Verificado en KickEngineering/KickDevDocs (2026-10-07): authorize y token en id.kick.com; el intercambio lleva client_secret y code_verifier.
Usa las credenciales de la app de Kick que ya tiene el sistema viejo (KICK_CLIENT_ID / KICK_CLIENT_SECRET). provider="kick";
account_id = user_id de Kick (sale de `whoami`). Si el redirect usa 127.0.0.1 en vez de localhost, la documentacion pide un parametro extra.
Scopes verificados en docs.kick.com/getting-started/scopes: los de lectura del sprint (events:subscribe lo pide listar suscripciones).
La app de Kick se crea en Configuracion de la cuenta > Developer (exige 2FA) y tiene UNA sola redirect URL: para local usa una app de desarrollo propia.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="kick",
    provider_keys=["kick"],
    api_version="public/v1",
    multi_account=True,
    whoami="kick.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["user:read", "channel:read", "channel:rewards:read", "kicks:read", "ads:read", "events:subscribe"],
        authorize_url="https://id.kick.com/oauth/authorize",
        token_url="https://id.kick.com/oauth/token",
        pkce=True,
        client_id_env="KICK_CLIENT_ID",
        client_secret_env="KICK_CLIENT_SECRET",
    ),
))
