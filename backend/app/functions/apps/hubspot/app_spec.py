"""HubSpot: OAuth 2.0 con codigo de autorizacion y refresco (access_token de 30 min, refresh_token sin caducidad).

Verificado en developers.hubspot.com (2026-10-07): authorize_url y token_url salen del esquema OAuth de la referencia de la API;
la respuesta del token trae `refresh_token` y la lista `scopes`. provider="hubspot"; account_id = portalId (Hub ID), que sale de `whoami`.
HubSpot responde "falta un permiso" como HTTP 403 (categoria MISSING_SCOPES), que el sistema ya traduce a missing_scope:
no hace falta scope_error_marker.

OJO al conectar: la app de HubSpot exige que `scope` de la URL coincida con los permisos OBLIGATORIOS configurados en su consola
(o en `app-hsmeta.json` del proyecto); si sobra o falta uno, HubSpot rechaza la autorizacion.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="hubspot",
    provider_keys=["hubspot"],
    api_version="2026-09",
    multi_account=True,
    whoami="hubspot.account.get",
    auth=AuthSpec(
        type=AuthType.oauth2_code,
        scopes=["oauth", "crm.objects.contacts.read", "crm.objects.companies.read", "crm.objects.deals.read"],
        authorize_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
        client_id_env="HUBSPOT_CLIENT_ID",
        client_secret_env="HUBSPOT_CLIENT_SECRET",
    ),
))
