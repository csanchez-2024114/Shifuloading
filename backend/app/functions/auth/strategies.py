"""Estrategias implementadas: none, api_key, bearer, basic, custom_params y oauth2_code (con refresco)."""
import base64
import os
from typing import Optional

import httpx

from app.functions.auth.base import AuthStrategy, Credentials, RequestParts, register_auth
from app.functions.spec import AuthSpec, AuthType


def _with_scheme(value: str, scheme: Optional[str]) -> str:
    return f"{scheme} {value}" if scheme else value  # scheme "" o None = valor crudo (ClickUp, Brevo)


def _bearer_scheme(spec: AuthSpec) -> str:
    return "Bearer" if spec.scheme is None else spec.scheme  # None = por defecto "Bearer"; "" = crudo


@register_auth(AuthType.none)
class NoAuth(AuthStrategy):
    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        return None


@register_auth(AuthType.api_key)
class ApiKey(AuthStrategy):
    """Clave unica en un header (Brevo: 'api-key') o en la query (param_names[0], por defecto 'api_key')."""

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        if spec.placement == "query":
            req.params[spec.param_names[0] if spec.param_names else "api_key"] = creds.token
        else:
            req.headers[spec.header_name] = _with_scheme(creds.token, spec.scheme)


@register_auth(AuthType.bearer)
class Bearer(AuthStrategy):
    """Token largo en el header de autorizacion. Sin refresco."""

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        req.headers[spec.header_name] = _with_scheme(creds.token, _bearer_scheme(spec))


@register_auth(AuthType.basic)
class Basic(AuthStrategy):
    """Usuario y clave (campos 'username' y 'password' en credentials_enc)."""

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        raw = f"{creds.fields.get('username', '')}:{creds.fields.get('password', '')}".encode("utf-8")
        req.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")


@register_auth(AuthType.custom_params)
class CustomParams(AuthStrategy):
    """Varios campos (Trello: key + token), cada uno en un header o en la query segun spec.placement."""

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        target = req.params if spec.placement == "query" else req.headers
        for name in spec.param_names:
            target[name] = creds.fields.get(name, "")


@register_auth(AuthType.oauth2_code)
class OAuth2Code(AuthStrategy):
    """OAuth 2.0 con codigo de autorizacion. Access token en el header; refresco con refresh_token."""
    can_refresh = True

    def apply(self, req: RequestParts, creds: Credentials, spec: AuthSpec) -> None:
        req.headers[spec.header_name] = _with_scheme(creds.token, _bearer_scheme(spec))

    async def refresh(self, client: httpx.AsyncClient, creds: Credentials, spec: AuthSpec) -> Optional[dict[str, str]]:
        refresh_token = creds.fields.get("refresh_token")
        client_id = os.getenv(spec.client_id_env or "")
        client_secret = os.getenv(spec.client_secret_env or "")
        if not (refresh_token and spec.token_url and client_id and client_secret):
            return None
        resp = await client.post(spec.token_url, data={
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": client_id, "client_secret": client_secret,
        })
        if resp.status_code != 200:
            return None
        body = resp.json()
        if not body.get("access_token"):
            return None
        out = {"access_token": body["access_token"]}
        if body.get("refresh_token"):
            out["refresh_token"] = body["refresh_token"]
        return out
