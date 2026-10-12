import json

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.core.security import decrypt_data, encrypt_data
from app.functions import connections
from app.functions.connections import get_connection
from app.functions.errors import FunctionError
from app.functions.spec import AppSpec, AuthSpec, AuthType, ErrorCode

COL = Collections.USER_CONNECTED_ACCOUNTS
API = "https://api.example.test/v1/things"


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    monkeypatch.setattr(connections, "RETRY_DELAY_SECONDS", 0)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["functions_test"]


def app_spec(auth_type=AuthType.bearer, **auth) -> AppSpec:
    return AppSpec(app="demo", provider_keys=["demo"], auth=AuthSpec(type=auth_type, **auth))


async def add_account(db, user="u1", account="A", token="tok-A", refresh=None, status="active", provider="demo", **extra):
    doc = {"user_id": user, "provider": provider, "account_id": account, "access_token": encrypt_data(token),
           "refresh_token": encrypt_data(refresh) if refresh else "n/a", "status": status, **extra}
    res = await db[COL].insert_one(doc)
    return res.inserted_id


def recorder(responses):
    """Transporte falso: devuelve respuestas en orden (o una funcion) y guarda cada peticion."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        r = responses(request) if callable(responses) else responses[min(len(seen) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    return httpx.MockTransport(handler), seen


def ok(body=None):
    return httpx.Response(200, json=body or {"ok": True})


async def code_of(coro):
    with pytest.raises(FunctionError) as exc:
        await coro
    return exc.value.code


# ---------- resolucion de cuenta ----------

async def test_none_auth_needs_no_database():
    transport, seen = recorder([ok()])
    conn = await get_connection(None, "u1", app_spec(AuthType.none), transport=transport)
    await conn.request("GET", API)
    assert "authorization" not in seen[0].headers


async def test_no_account_is_missing_connection(db):
    assert await code_of(get_connection(db, "u1", app_spec())) == ErrorCode.missing_connection


async def test_single_account_is_used_automatically(db):
    await add_account(db, token="tok-A")
    transport, seen = recorder([ok()])
    conn = await get_connection(db, "u1", app_spec(), transport=transport)
    await conn.request("GET", API)
    assert conn.account_id == "A" and seen[0].headers["authorization"] == "Bearer tok-A"


async def test_many_accounts_without_choice_asks_to_choose(db):
    await add_account(db, account="A", token="tok-A")
    await add_account(db, account="B", token="tok-B")
    assert await code_of(get_connection(db, "u1", app_spec())) == ErrorCode.account_selection_required


async def test_two_accounts_never_cross(db):
    await add_account(db, account="A", token="tok-A")
    await add_account(db, account="B", token="tok-B")
    transport, seen = recorder([ok(), ok()])
    conn_a = await get_connection(db, "u1", app_spec(), "A", transport=transport)
    conn_b = await get_connection(db, "u1", app_spec(), "B", transport=transport)
    await conn_a.request("GET", API)
    await conn_b.request("GET", API)
    assert seen[0].headers["authorization"] == "Bearer tok-A"
    assert seen[1].headers["authorization"] == "Bearer tok-B"
    assert (conn_a.account_id, conn_b.account_id) == ("A", "B")


async def test_other_users_accounts_are_invisible(db):
    await add_account(db, user="someone-else", account="X", token="tok-X")
    assert await code_of(get_connection(db, "u1", app_spec())) == ErrorCode.missing_connection
    assert await code_of(get_connection(db, "u1", app_spec(), "X")) == ErrorCode.missing_connection


async def test_unknown_account_id_is_missing_connection(db):
    await add_account(db, account="A")
    assert await code_of(get_connection(db, "u1", app_spec(), "ZZZ")) == ErrorCode.missing_connection


async def test_expired_or_revoked_accounts(db):
    await add_account(db, account="A", status="expired")
    await add_account(db, account="B", status="revoked")
    assert await code_of(get_connection(db, "u1", app_spec(), "A")) == ErrorCode.auth_expired
    assert await code_of(get_connection(db, "u1", app_spec())) == ErrorCode.auth_expired  # todas inutilizables


async def test_needs_refresh_status_is_still_usable(db):
    await add_account(db, status="needs_refresh")
    conn = await get_connection(db, "u1", app_spec())
    assert conn.account_id == "A"


async def test_unreadable_credentials_do_not_mark_the_account(db):
    _id = await add_account(db)
    await db[COL].update_one({"_id": _id}, {"$set": {"access_token": "texto-que-no-es-fernet"}})
    assert await code_of(get_connection(db, "u1", app_spec())) == ErrorCode.auth_expired
    assert (await db[COL].find_one({"_id": _id}))["status"] == "active"


# ---------- credenciales de varios campos ----------

async def test_multi_field_credentials_enc_custom_params(db):
    await db[COL].insert_one({"user_id": "u1", "provider": "demo", "account_id": "T", "status": "active",
                              "credentials_enc": encrypt_data(json.dumps({"key": "K", "token": "T"}))})
    transport, seen = recorder([ok()])
    spec = app_spec(AuthType.custom_params, placement="query", param_names=["key", "token"])
    conn = await get_connection(db, "u1", spec, transport=transport)
    await conn.request("GET", API, params={"q": "1"})
    assert dict(seen[0].url.params) == {"q": "1", "key": "K", "token": "T"}


async def test_api_key_in_header(db):
    await add_account(db, token="brevo-key")
    transport, seen = recorder([ok()])
    conn = await get_connection(db, "u1", app_spec(AuthType.api_key, header_name="api-key"), transport=transport)
    await conn.request("GET", API)
    assert seen[0].headers["api-key"] == "brevo-key" and "authorization" not in seen[0].headers


# ---------- refresco y vencimiento (siempre por el documento exacto) ----------

async def test_refresh_on_401_retries_and_updates_only_that_account(db, monkeypatch):
    monkeypatch.setenv("DEMO_CLIENT_ID", "cid")
    monkeypatch.setenv("DEMO_CLIENT_SECRET", "csecret")
    id_a = await add_account(db, account="A", token="old-A", refresh="rt-A")
    id_b = await add_account(db, account="B", token="tok-B", refresh="rt-B")

    def route(req: httpx.Request):
        if str(req.url) == "https://auth.example.test/token":
            assert b"rt-A" in req.content and b"rt-B" not in req.content
            return httpx.Response(200, json={"access_token": "new-A"})
        return ok() if req.headers["authorization"] == "Bearer new-A" else httpx.Response(401)

    transport, seen = recorder(route)
    spec = app_spec(AuthType.oauth2_code, token_url="https://auth.example.test/token",
                    client_id_env="DEMO_CLIENT_ID", client_secret_env="DEMO_CLIENT_SECRET")
    conn = await get_connection(db, "u1", spec, "A", transport=transport)
    resp = await conn.request("GET", API)
    assert resp.status_code == 200 and len(seen) == 3  # 401, refresco, reintento
    a, b = await db[COL].find_one({"_id": id_a}), await db[COL].find_one({"_id": id_b})
    assert decrypt_data(a["access_token"]) == "new-A" and decrypt_data(a["refresh_token"]) == "rt-A"
    assert decrypt_data(b["access_token"]) == "tok-B"  # la otra cuenta no se tocó


async def test_definitive_401_marks_only_that_account_expired(db):
    id_a = await add_account(db, account="A", token="bad")
    id_b = await add_account(db, account="B", token="good")
    transport, _ = recorder([httpx.Response(401)])
    conn = await get_connection(db, "u1", app_spec(AuthType.api_key, header_name="api-key"), "A", transport=transport)
    assert await code_of(conn.request("GET", API)) == ErrorCode.auth_expired
    assert (await db[COL].find_one({"_id": id_a}))["status"] == "expired"
    assert (await db[COL].find_one({"_id": id_b}))["status"] == "active"


async def test_oauth2_without_refresh_secret_gives_auth_expired(db, monkeypatch):
    monkeypatch.delenv("DEMO_CLIENT_ID", raising=False)
    await add_account(db, token="old", refresh="rt")
    transport, seen = recorder([httpx.Response(401)])
    spec = app_spec(AuthType.oauth2_code, token_url="https://auth.example.test/token",
                    client_id_env="DEMO_CLIENT_ID", client_secret_env="DEMO_CLIENT_SECRET")
    conn = await get_connection(db, "u1", spec, transport=transport)
    assert await code_of(conn.request("GET", API)) == ErrorCode.auth_expired
    assert len(seen) == 1  # no hubo refresco posible, no se insiste


async def test_401_with_scope_marker_is_missing_scope_and_does_not_expire_the_account(db, monkeypatch):
    monkeypatch.setenv("DEMO_CLIENT_ID", "cid")
    monkeypatch.setenv("DEMO_CLIENT_SECRET", "cs")
    _id = await add_account(db, token="tok", refresh="rt")
    transport, seen = recorder([httpx.Response(401, json={"error": {".tag": "missing_scope", "required_scope": "files.metadata.read"}})])
    spec = app_spec(AuthType.oauth2_code, token_url="https://auth.example.test/token", client_id_env="DEMO_CLIENT_ID",
                    client_secret_env="DEMO_CLIENT_SECRET", scope_error_marker="missing_scope")
    conn = await get_connection(db, "u1", spec, transport=transport)
    assert await code_of(conn.request("GET", API)) == ErrorCode.missing_scope
    assert len(seen) == 1                                                      # no se intento refrescar
    assert (await db[COL].find_one({"_id": _id}))["status"] == "active"        # y la cuenta sigue activa


# ---------- mapeo de errores HTTP ----------

@pytest.mark.parametrize("status,expected", [
    (403, ErrorCode.missing_scope), (404, ErrorCode.not_found), (422, ErrorCode.invalid_input),
    (400, ErrorCode.invalid_input), (500, ErrorCode.upstream_down),
])
async def test_http_status_to_error_code(db, status, expected):
    await add_account(db)
    transport, _ = recorder([httpx.Response(status, text="detalle")])
    conn = await get_connection(db, "u1", app_spec(), transport=transport)
    assert await code_of(conn.request("GET", API)) == expected


async def test_429_is_retried_once_then_rate_limited(db):
    await add_account(db)
    transport, seen = recorder([httpx.Response(429)])
    conn = await get_connection(db, "u1", app_spec(), transport=transport)
    assert await code_of(conn.request("GET", API)) == ErrorCode.rate_limited
    assert len(seen) == 2


async def test_transient_503_then_success(db):
    await add_account(db)
    transport, seen = recorder([httpx.Response(503), ok({"fine": 1})])
    conn = await get_connection(db, "u1", app_spec(), transport=transport)
    assert (await conn.request("GET", API)).json() == {"fine": 1} and len(seen) == 2


async def test_timeout_and_network_errors_are_upstream_down(db):
    await add_account(db)
    for exc in (httpx.ReadTimeout("t"), httpx.ConnectError("c")):
        transport, _ = recorder([exc])
        conn = await get_connection(db, "u1", app_spec(), transport=transport)
        assert await code_of(conn.request("GET", API)) == ErrorCode.upstream_down


async def test_ok_statuses_are_handed_back_to_the_handler(db):  # p. ej. Dropbox responde 409 con el detalle
    await add_account(db)
    transport, _ = recorder([httpx.Response(409, json={"error_summary": "path/not_found/"})])
    conn = await get_connection(db, "u1", app_spec(), transport=transport)
    resp = await conn.request("POST", API, ok_statuses=(409,))
    assert resp.status_code == 409 and resp.json()["error_summary"].startswith("path/not_found")


def test_403_is_split_into_rate_limit_no_access_and_missing_scope():
    from app.functions.connections import _code_for_403
    assert _code_for_403('{"reason": "userRateLimitExceeded"}') == ErrorCode.rate_limited
    assert _code_for_403("The caller does not have permission") == ErrorCode.access_denied
    assert _code_for_403('{"reason": "insufficientFilePermissions"}') == ErrorCode.access_denied
    assert _code_for_403("Request had insufficient authentication scopes.") == ErrorCode.missing_scope
    assert _code_for_403("Forbidden") == ErrorCode.missing_scope
