"""Brevo: autenticacion por API key en el header `api-key` (verificado en developers.brevo.com).

La clave se guarda al conectar con POST /api/v1/integrations/brevo/key (app/integrations/providers/brevo.py),
que escribe user_connected_accounts con provider="brevo" y account_id = el correo de la cuenta de Brevo.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="brevo",
    provider_keys=["brevo"],
    api_version="v3",
    multi_account=True,
    whoami="brevo.account.get",
    auth=AuthSpec(type=AuthType.api_key, header_name="api-key"),  # una API key no tiene scopes
))
