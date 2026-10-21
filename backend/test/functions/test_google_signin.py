"""Entrar con Google (flujo en el servidor): a dónde vuelve la persona y cuándo se rechaza.
Google, la base y las sesiones van simulados: aquí solo se prueba lo que decide la ruta."""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.routes.auth import authRoutes as ar


class _Coleccion:
    def __init__(self, doc=None):
        self.doc = doc

    async def find_one(self, *_a, **_k):
        return self.doc


def _peticion(usuario):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db={ar.Collections.USERS: _Coleccion(usuario)})))


@pytest.fixture
def google(monkeypatch):
    """Configura Google y deja que cada prueba elija qué devuelve el id_token."""
    monkeypatch.setattr(ar.Config, "GOOGLE_SIGNIN_CLIENT_ID", "cid", raising=False)
    monkeypatch.setattr(ar.Config, "GOOGLE_SIGNIN_CLIENT_SECRET", "sec", raising=False)
    monkeypatch.setattr(ar.Config, "GOOGLE_SIGNIN_REDIRECT_URI", "http://api/cb", raising=False)
    monkeypatch.setattr(ar.Config, "FRONTEND_URL", "http://front", raising=False)

    class _Resp:
        def json(self):
            return {"id_token": "tok"}

    class _Cliente:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(ar.httpx, "AsyncClient", _Cliente)

    async def nada(*a, **k):
        return None

    async def sesion(*a, **k):
        return "RT", None

    for f in ("_ensure_auth_method", "update_login_streak", "_complete_pending_workspace_invites"):
        monkeypatch.setattr(ar, f, nada)
    monkeypatch.setattr(ar, "_create_session", sesion)
    monkeypatch.setattr(ar, "_build_access_token", lambda uid, email: "AT")
    info = {"sub": "g1", "email": "ana@correo.com", "email_verified": True}
    monkeypatch.setattr(ar.google_id_token, "verify_oauth2_token", lambda *a, **k: info)
    return info


async def test_vuelve_a_entrar_con_las_llaves_en_el_fragmento(google):
    r = await ar.google_callback(_peticion({"_id": "u1", "email": "ana@correo.com"}), code="c", state=ar._make_oauth_state())
    url = urlparse(r.headers["location"])
    assert (url.netloc, url.path, url.query) == ("front", "/entrar", "")  # nada de llaves en la query
    assert parse_qs(url.fragment) == {"at": ["AT"], "rt": ["RT"]}


async def test_correo_no_confirmado_por_google_no_entra(google):
    google["email_verified"] = False
    r = await ar.google_callback(_peticion({"_id": "u1", "email": "ana@correo.com"}), code="c", state=ar._make_oauth_state())
    assert r.headers["location"] == "http://front/login?error=google_verify"


async def test_estado_falso_no_entra(google):
    r = await ar.google_callback(_peticion(None), code="c", state="x.y")
    assert r.headers["location"] == "http://front/login?error=invalid_state"


async def test_sin_configurar_vuelve_al_login_con_aviso(monkeypatch):
    monkeypatch.setattr(ar.Config, "GOOGLE_SIGNIN_CLIENT_ID", "", raising=False)
    monkeypatch.setattr(ar.Config, "FRONTEND_URL", "http://front", raising=False)
    r = await ar.google_authorize()
    assert r.headers["location"] == "http://front/login?error=google_off"
