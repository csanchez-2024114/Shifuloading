"""Jira (Atlassian Cloud): OAuth 2.0 (3LO) con codigo y refresco (refresh_token rotativo con `offline_access`).

Verificado en developer.atlassian.com (2026-10-07): authorize_url exige audience=api.atlassian.com y prompt=consent; el token sale de
auth.atlassian.com/oauth/token. provider="jira"; account_id = account_id de Atlassian (sale de `whoami` en api.atlassian.com/me, que no
necesita el cloud_id del sitio). Los scopes se activan en la consola (developer.atlassian.com/console/myapps), incluida la «User Identity API».
POR RESOLVER (plataforma, Alan): las lecturas de Jira van a api.atlassian.com/ex/jira/{cloudid}/... y el cloud_id es propio de cada cuenta.
POR COMPROBAR: la documentacion muestra el intercambio del codigo con cuerpo JSON; accounts.py lo manda como formulario.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="jira",
    provider_keys=["jira"],
    api_version="3",
    multi_account=True,
    whoami="jira.user.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["read:me", "offline_access"],
        authorize_url="https://auth.atlassian.com/authorize",
        authorize_params={"audience": "api.atlassian.com", "prompt": "consent"},
        token_url="https://auth.atlassian.com/oauth/token",
        client_id_env="JIRA_CLIENT_ID",
        client_secret_env="JIRA_CLIENT_SECRET",
    ),
))
