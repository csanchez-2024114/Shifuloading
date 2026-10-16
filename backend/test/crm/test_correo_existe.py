"""POST /api/v1/auth/email-exists: el primer paso del inicio de sesión manda a registrarse a quien no tiene cuenta."""
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.constants import Collections

_lim_stub = types.ModuleType("app.core.limiter")
_lim_stub.limiter = types.SimpleNamespace(limit=lambda *_a, **_k: (lambda f: f))
_original = sys.modules.get("app.core.limiter")
sys.modules["app.core.limiter"] = _lim_stub
try:
    from app.routes.auth.authRoutes import router
finally:
    if _original is None:
        sys.modules.pop("app.core.limiter", None)
    else:
        sys.modules["app.core.limiter"] = _original


class _Usuarios:
    def __init__(self, correos):
        self.correos = set(correos)
        self.consultas = []

    async def find_one(self, filtro, proyeccion=None):
        self.consultas.append((filtro, proyeccion))
        return {"_id": "x"} if filtro.get("email") in self.correos else None


@pytest.fixture
def cli():
    usuarios = _Usuarios({"ana@correo.com"})
    app = FastAPI()
    app.state.db = {Collections.USERS: usuarios}
    app.include_router(router, prefix="/api/v1/auth")
    c = TestClient(app)
    c.usuarios = usuarios
    return c


def test_dice_si_el_correo_ya_tiene_cuenta(cli):
    assert cli.post("/api/v1/auth/email-exists", json={"email": "ana@correo.com"}).json() == {"exists": True}
    assert cli.post("/api/v1/auth/email-exists", json={"email": "nadie@correo.com"}).json() == {"exists": False}


def test_ignora_mayusculas_y_espacios_como_el_login(cli):
    assert cli.post("/api/v1/auth/email-exists", json={"email": "  ANA@Correo.com "}).json() == {"exists": True}


def test_solo_pide_el_id_y_no_devuelve_datos_de_la_persona(cli):
    r = cli.post("/api/v1/auth/email-exists", json={"email": "ana@correo.com"})
    assert set(r.json()) == {"exists"} and cli.usuarios.consultas[-1][1] == {"_id": 1}


def test_un_correo_mal_escrito_se_rechaza(cli):
    assert cli.post("/api/v1/auth/email-exists", json={"email": "no-es-correo"}).status_code == 422
    assert cli.post("/api/v1/auth/email-exists", json={}).status_code == 422
