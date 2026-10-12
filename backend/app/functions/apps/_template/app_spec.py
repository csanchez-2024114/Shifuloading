"""PLANTILLA: copia esta carpeta a app/functions/apps/<tu_app>/ y cambia los nombres.

Aqui se declara COMO se conecta la app. Elige UNO de los tipos de AuthType:
  oauth2_code   OAuth 2.0 con refresco (Google, Dropbox, Asana, HubSpot...)  -> token_url, client_id_env, client_secret_env
  bearer        token largo (ClickUp con scheme="", Notion, Slack bot)
  api_key       una clave en un header o en la query (Brevo: header_name="api-key")
  basic         usuario y clave
  custom_params varios campos (Trello: key + token)  -> param_names y placement
  none          API publica
Los tipos oauth1, oauth2_client_credentials y hmac_signature estan declarados pero SIN estrategia todavia:
ver doc/funciones/AUTENTICACION.md para agregarlos.
"""
from app.functions.registry import register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType

APP = register_app(AppSpec(
    app="example",                       # minusculas, sin espacios; es el primer tramo del id de cada funcion
    provider_keys=["example"],           # valor(es) de `provider` en user_connected_accounts
    api_version="v1",
    multi_account=True,                  # False si el conector solo soporta una cuenta (queda marcado para adaptar)
    whoami="example.account.get",        # opcional: funcion de lectura sin parametros que dice quien es la cuenta
    auth=AuthSpec(
        type=AuthType.bearer,
        scopes=["items.read"],           # los que la app puede pedir; cada funcion declara los suyos
    ),
))
