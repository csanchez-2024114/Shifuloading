"""Discord: OAuth 2.0 con codigo y refresco (token de usuario; scopes identify, guilds, guilds.members.read y connections, ninguno pide aprobacion).

Verificado en discord.com/developers/docs (2026-10-07): authorize en discord.com/oauth2/authorize, token en discord.com/api/oauth2/token
(formulario con client_id y client_secret). Usa la app de Discord que ya tiene el sistema viejo (DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET).
provider="discord"; account_id = id de usuario de Discord (sale de `whoami`).
POR DECIDIR (plataforma, Alan): unas 50 funciones del catalogo piden el token del BOT (servidores, canales, mensajes), que no es OAuth de usuario.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="discord",
    provider_keys=["discord"],
    api_version="v10",
    multi_account=True,
    whoami="discord.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["identify", "guilds", "guilds.members.read", "connections"],
        authorize_url="https://discord.com/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        client_id_env="DISCORD_CLIENT_ID",
        client_secret_env="DISCORD_CLIENT_SECRET",
    ),
))
