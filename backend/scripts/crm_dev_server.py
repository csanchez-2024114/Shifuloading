"""Servidor de DESARROLLO del CRM de Shifu: sin Mongo, sin Redis y sin credenciales.

Usa las rutas reales de /api/v1/crm (las mismas que el backend completo) con una base de datos en memoria y un /auth
falso que imita el contrato del backend real (register, login, refresh con rotación y logout). Sirve para ver y probar
el frontend de punta a punta. Todo se pierde al apagarlo.

SOLO PARA DESARROLLO: no cifra contraseñas, no limita intentos y solo escucha en 127.0.0.1. Nunca se despliega.

Uso (desde la carpeta backend/):
    pip install fastapi uvicorn pydantic
    python scripts/crm_dev_server.py            # puerto 5000
    python scripts/crm_dev_server.py --puerto 5055

En el frontend, `.env`:  VITE_API_URL=http://localhost:5000/api/v1
"""
from __future__ import annotations

import argparse
import copy
import re
import secrets
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

# Las rutas del CRM piden `get_current_user` (Mongo + JWT) y el limitador (Redis). Aquí se sustituyen solo esas dos piezas
# por versiones de desarrollo; todo lo demás es el código real.
_sesiones_acceso: dict[str, str] = {}  # token de acceso -> id de la persona


async def usuario_actual(request: Request):
    cab = request.headers.get("Authorization", "")
    uid = _sesiones_acceso.get(cab.removeprefix("Bearer ").strip())
    if not uid:
        raise HTTPException(401, "Token inválido o expirado.")
    return {"id": uid}


_bd = types.ModuleType("app.database")
_bd.get_current_user = usuario_actual
_limitador = types.ModuleType("app.core.limiter")
_limitador.limiter = types.SimpleNamespace(limit=lambda *_a, **_k: (lambda f: f))
sys.modules["app.database"] = _bd
sys.modules["app.core.limiter"] = _limitador

import os as _os  # noqa: E402

from app.routes.crm.crmRoutes import router as crm_router  # noqa: E402


# ───────── Base de datos en memoria (imita lo que usa app/crm/repositorio.py) ─────────

def _como_mongo(v):
    """Mongo guarda las fechas en UTC y las devuelve sin zona horaria."""
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, dict):
        return {k: _como_mongo(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_como_mongo(x) for x in v]
    return v


class _Resultado:
    def __init__(self, matched=0):
        self.matched_count = matched


class _Cursor:
    """Lo que usa el código de `find`: sort, skip y to_list."""
    def __init__(self, docs):
        self.docs = docs

    def sort(self, clave, sentido=1):
        self.docs.sort(key=lambda d: (d.get(clave) is None, d.get(clave)), reverse=sentido < 0)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n] if n else self.docs
        return self

    async def to_list(self, length=None):
        return self.docs if length is None else self.docs[:length]


class _Coleccion:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _coincide(d, filtro):
        def cumple(x, v):
            if isinstance(v, dict) and v and all(str(k).startswith("$") for k in v):
                ops = {"$gte": lambda a, b: a is not None and a >= b, "$lte": lambda a, b: a is not None and a <= b,
                       "$gt": lambda a, b: a is not None and a > b, "$lt": lambda a, b: a is not None and a < b,
                       "$ne": lambda a, b: a != b, "$in": lambda a, b: a in b}
                return all(ops[k](x, b) for k, b in v.items())
            return x == v
        return all(cumple(d.get(k), v) for k, v in filtro.items())

    @staticmethod
    def _proyectar(d, proyeccion):
        if not proyeccion:
            return d
        if any(v for k, v in proyeccion.items() if k != "_id"):
            return {k: x for k, x in d.items() if proyeccion.get(k)}
        return {k: x for k, x in d.items() if proyeccion.get(k, 1)}

    def find(self, filtro=None, proyeccion=None):
        return _Cursor([self._proyectar(copy.deepcopy(d), proyeccion) for d in self.docs if self._coincide(d, filtro or {})])

    async def insert_one(self, doc):
        self.docs.append(_como_mongo(copy.deepcopy(doc)))

    async def delete_many(self, filtro):
        self.docs = [d for d in self.docs if not self._coincide(d, filtro)]

    async def find_one(self, filtro, proyeccion=None):
        return next((self._proyectar(copy.deepcopy(d), proyeccion) for d in self.docs if self._coincide(d, filtro)), None)

    async def replace_one(self, filtro, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if self._coincide(d, filtro):
                self.docs[i] = _como_mongo(copy.deepcopy(doc))
                return _Resultado(1)
        if upsert:
            self.docs.append(_como_mongo(copy.deepcopy(doc)))
        return _Resultado(0)

    async def delete_one(self, filtro):
        self.docs = [d for d in self.docs if not self._coincide(d, filtro)]


class BaseEnMemoria:
    def __init__(self):
        self.cols: dict[str, _Coleccion] = {}

    def __getitem__(self, nombre):
        return self.cols.setdefault(nombre, _Coleccion())


# ───────── /auth de desarrollo ─────────

USUARIOS: dict[str, dict] = {}   # correo -> persona
RENOVACION: dict[str, str] = {}  # token de renovación vigente -> id


class Registro(BaseModel):
    name: str
    last_name: str
    email: str
    password: str


class Entrada(BaseModel):
    email: str
    password: str


class Renovar(BaseModel):
    refresh_token: str


def _abrir(u: dict) -> dict:
    acceso, renovacion = "acc-" + secrets.token_hex(12), "ref-" + secrets.token_hex(12)
    _sesiones_acceso[acceso] = u["id"]
    RENOVACION[renovacion] = u["id"]
    return {"user": {k: u[k] for k in ("id", "name", "last_name", "email")}, "access_token": acceso,
            "refresh_token": renovacion, "auth_methods": ["password"]}


def crear_app() -> FastAPI:
    app = FastAPI(title="Shifu CRM (desarrollo)")
    app.state.db = BaseEnMemoria()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5180", "http://127.0.0.1:5180", "http://localhost:5173", "http://localhost:5199", "http://localhost:5205"],
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.post("/api/v1/auth/register", status_code=201)
    async def register(d: Registro):
        if len(d.name.strip()) < 2 or len(d.last_name.strip()) < 2 or len(d.password) < 8 \
                or not re.search(r"\d", d.password) or not re.search(r"[^\W\d_]", d.password):
            raise HTTPException(422, "Datos inválidos.")
        correo = d.email.lower().strip()
        if correo in USUARIOS:
            raise HTTPException(400, "La cuenta ya existe. Inicia sesión con tu contraseña.")
        u = {"id": "u" + secrets.token_hex(6), "name": d.name.strip(), "last_name": d.last_name.strip(), "email": correo, "password": d.password}
        USUARIOS[correo] = u
        return _abrir(u)

    @app.post("/api/v1/auth/login")
    async def login(d: Entrada):
        u = USUARIOS.get(d.email.lower().strip())
        if not u or u["password"] != d.password:
            raise HTTPException(401, "Credenciales incorrectas")
        return _abrir(u)

    @app.post("/api/v1/auth/refresh")
    async def refresh(d: Renovar):
        uid = RENOVACION.pop(d.refresh_token, None)  # rotación: el anterior deja de servir
        if not uid:
            raise HTTPException(401, "Refresh token inválido.")
        acceso, renovacion = "acc-" + secrets.token_hex(12), "ref-" + secrets.token_hex(12)
        _sesiones_acceso[acceso] = uid
        RENOVACION[renovacion] = uid
        return {"access_token": acceso, "refresh_token": renovacion}

    @app.post("/api/v1/auth/logout")
    async def logout(d: Renovar):
        RENOVACION.pop(d.refresh_token, None)
        return {"success": True, "message": "Sesión cerrada."}

    @app.post("/dev/expirar")
    async def expirar(todo: bool = False):
        """Para probar la renovación de sesión: caduca los tokens de acceso (con ?todo=true, también los de renovación)."""
        _sesiones_acceso.clear()
        if todo:
            RENOVACION.clear()
        return {"ok": True}

    app.include_router(crm_router, prefix="/api/v1/crm")
    if _os.getenv("CRM_LAB_ADAPTER", "0").strip() == "1":
        from app.routes.crm import labRoutes as _lab_routes  # noqa: E402

        app.include_router(_lab_routes.router, prefix="/api/v1/crm")
    return app


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--puerto", type=int, default=5000)
    args = ap.parse_args()
    print(f"Servidor de desarrollo del CRM en http://127.0.0.1:{args.puerto}/api/v1  (todo se guarda en memoria)")
    uvicorn.run(crear_app(), host="127.0.0.1", port=args.puerto, log_level="warning")
