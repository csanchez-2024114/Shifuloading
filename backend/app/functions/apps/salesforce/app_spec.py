"""Salesforce: OAuth 2.0 con codigo de autorizacion, PKCE y refresco (Web Server Flow).

Verificado en developer.salesforce.com y en https://login.salesforce.com/.well-known/openid-configuration (2026-10-09):
- authorize_url y token_url salen de login.salesforce.com (produccion y Developer Edition). Los sandbox usan test.salesforce.com
  y las orgs con My Domain pueden exigir su propio dominio: por ahora solo se soporta login.salesforce.com.
- Scopes: `api` (REST), `refresh_token` (alias offline_access; sin el no llega refresh_token) y `openid` (permite llamar a
  /services/oauth2/userinfo, que es lo que usa la whoami). Los tres deben estar activados en la app de Salesforce, o la
  autorizacion falla con invalid_scope. El token trae `scope` separado por espacios (esos son los «Permisos concedidos»).
- pkce=True: las External Client Apps (las apps nuevas) lo exigen por defecto y las demas lo aceptan.
- Un token vencido responde 401 INVALID_SESSION_ID; la estrategia oauth2_code lo refresca con grant_type=refresh_token.

- Con un access token vencido o roto, /userinfo responde HTTP 403 con el texto `Bad_OAuth_Token` (verificado con la API real, no es un 401):
  token_invalid_marker lo trata como token vencido (refresca con el refresh_token o marca la cuenta expired) y no como permiso faltante.

LIMITACION CONOCIDA: la API de datos vive en el `instance_url` que Salesforce devuelve en la
respuesta del token y es propio de cada org, pero accounts.py solo guarda access_token y refresh_token. Hasta que el sistema lo
guarde, solo se puede llamar a hosts fijos como login.salesforce.com: la whoami usa /userinfo.
Las lecturas de las tareas 3 a 6 (/services/data/...) necesitan ese soporte.

provider="salesforce"; account_id = user_id de Salesforce (18 caracteres), que sale de `whoami`.
Redirect a registrar tal cual: http://localhost:8001/function-apps/salesforce/oauth-callback
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="salesforce",
    provider_keys=["salesforce"],
    api_version="v62.0",
    multi_account=True,
    whoami="salesforce.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["api", "refresh_token", "openid"],
        authorize_url="https://login.salesforce.com/services/oauth2/authorize",
        token_url="https://login.salesforce.com/services/oauth2/token",
        pkce=True,
        client_id_env="SALESFORCE_CLIENT_ID",
        client_secret_env="SALESFORCE_CLIENT_SECRET",
        token_invalid_marker="Bad_OAuth_Token",  # /userinfo responde 403 (no 401) con ese texto cuando el access token esta vencido o roto
    ),
))
