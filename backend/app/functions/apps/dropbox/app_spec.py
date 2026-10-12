"""Dropbox: OAuth 2.0 con codigo de autorizacion y refresco.

App de REFERENCIA del sistema: la conexion la hace `accounts.py` solo con lo declarado aqui (authorize_url, scopes,
token_url, client_id_env). provider="dropbox"; account_id = id de cuenta de Dropbox, que sale de `whoami`.
Dropbox devuelve el error de "falta un permiso" como HTTP 401 con `missing_scope` (AuthError) o, si la APP no tiene
el permiso activado en su consola, como HTTP 400 con "does not have the required scope" (verificado con la API real), por eso
scope_error_marker: sin el, un permiso faltante se confundiria con un token vencido.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="dropbox",
    provider_keys=["dropbox"],
    api_version="2",
    multi_account=True,
    whoami="dropbox.account.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["account_info.read", "files.metadata.read"],
        authorize_url="https://www.dropbox.com/oauth2/authorize",
        authorize_params={"token_access_type": "offline"},  # sin esto Dropbox no entrega refresh_token
        token_url="https://api.dropboxapi.com/oauth2/token",
        client_id_env="DROPBOX_CLIENT_ID",
        client_secret_env="DROPBOX_CLIENT_SECRET",
        scope_error_marker="missing_scope|required scope",  # 401 con `missing_scope`; 400 con "...does not have the required scope"
    ),
))
