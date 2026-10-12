import base64

import pytest

from app.functions.auth import Credentials, RequestParts, get_strategy, implemented_types
from app.functions.spec import AuthSpec, AuthType


def apply(spec: AuthSpec, **fields) -> RequestParts:
    req = RequestParts()
    get_strategy(spec.type).apply(req, Credentials(fields=fields), spec)
    return req


def test_implemented_and_declared_types():
    assert implemented_types() == {
        AuthType.none, AuthType.api_key, AuthType.bearer, AuthType.basic, AuthType.custom_params, AuthType.oauth2_code,
    }
    for declared in (AuthType.oauth1, AuthType.oauth2_client_credentials, AuthType.hmac_signature):
        with pytest.raises(NotImplementedError, match="AUTENTICACION.md"):
            get_strategy(declared)


def test_none_adds_nothing():
    req = apply(AuthSpec(type=AuthType.none))
    assert req.headers == {} and req.params == {}


def test_api_key_header_is_raw_by_default():  # Brevo: header 'api-key' con el valor tal cual
    req = apply(AuthSpec(type=AuthType.api_key, header_name="api-key"), token="K1")
    assert req.headers == {"api-key": "K1"}


def test_api_key_header_with_prefix_and_query():
    assert apply(AuthSpec(type=AuthType.api_key, scheme="Token"), token="K1").headers == {"Authorization": "Token K1"}
    assert apply(AuthSpec(type=AuthType.api_key, placement="query"), token="K1").params == {"api_key": "K1"}
    assert apply(AuthSpec(type=AuthType.api_key, placement="query", param_names=["key"]), token="K1").params == {"key": "K1"}


def test_bearer_default_and_raw_and_custom_scheme():
    assert apply(AuthSpec(type=AuthType.bearer), token="T").headers == {"Authorization": "Bearer T"}
    assert apply(AuthSpec(type=AuthType.bearer, scheme=""), token="T").headers == {"Authorization": "T"}  # ClickUp
    assert apply(AuthSpec(type=AuthType.bearer, scheme="Bot"), token="T").headers == {"Authorization": "Bot T"}


def test_basic():
    req = apply(AuthSpec(type=AuthType.basic), username="ana", password="s3cr:et")
    assert req.headers["Authorization"] == "Basic " + base64.b64encode(b"ana:s3cr:et").decode()


def test_custom_params_in_query_and_header():  # Trello: key + token
    spec_q = AuthSpec(type=AuthType.custom_params, placement="query", param_names=["key", "token"])
    assert apply(spec_q, key="K", token="T").params == {"key": "K", "token": "T"}
    spec_h = AuthSpec(type=AuthType.custom_params, placement="header", param_names=["X-Id", "X-Secret"])
    assert apply(spec_h, **{"X-Id": "1", "X-Secret": "2"}).headers == {"X-Id": "1", "X-Secret": "2"}


def test_oauth2_applies_bearer_and_can_refresh():
    spec = AuthSpec(type=AuthType.oauth2_code)
    assert apply(spec, token="A").headers == {"Authorization": "Bearer A"}
    assert get_strategy(AuthType.oauth2_code).can_refresh is True
    assert get_strategy(AuthType.bearer).can_refresh is False
