"""Pruebas de las rutas /api/v1/crm con una base de datos falsa en memoria (no hace falta Mongo ni credenciales)."""
import copy
import sys
import types
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Se reemplazan solo las dos piezas que arrastran Mongo, JWT y Redis; todo lo demás es el código real.
_db_stub = types.ModuleType("app.database")


async def _usuario_de_prueba(request: Request):
    return {"id": request.headers.get("X-Usuario", "u1")}


_db_stub.get_current_user = _usuario_de_prueba
_lim_stub = types.ModuleType("app.core.limiter")
_lim_stub.limiter = types.SimpleNamespace(limit=lambda *_a, **_k: (lambda f: f))

# Los reemplazos viven solo mientras se importan las rutas: después se devuelve todo como estaba para no afectar a otras pruebas.
_originales = {k: sys.modules.get(k) for k in ("app.database", "app.core.limiter")}
sys.modules["app.database"] = _db_stub
sys.modules["app.core.limiter"] = _lim_stub
try:
    from app.routes.crm.crmRoutes import router
finally:
    for _k, _v in _originales.items():
        if _v is None:
            sys.modules.pop(_k, None)
        else:
            sys.modules[_k] = _v

from app.crm import repositorio as repo  # noqa: E402
from app.crm.generador import generar  # noqa: E402
from app.crm.operaciones import ErrorCrm  # noqa: E402

BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "cartera": "k2", "equipo": "chico", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


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


class _Coleccion:
    def __init__(self):
        self.docs: list[dict] = []
        self.antes_de_reemplazar = None  # gancho para simular un cambio ajeno en medio de una operación

    def _coincide(self, d, filtro):
        return all(d.get(k) == v for k, v in filtro.items())

    async def find_one(self, filtro, proyeccion=None):
        for d in self.docs:
            if self._coincide(d, filtro):
                return copy.deepcopy(d)
        return None

    async def replace_one(self, filtro, doc, upsert=False):
        if self.antes_de_reemplazar:
            gancho, self.antes_de_reemplazar = self.antes_de_reemplazar, None
            gancho(self)
        for i, d in enumerate(self.docs):
            if self._coincide(d, filtro):
                self.docs[i] = _como_mongo(copy.deepcopy(doc))
                return _Resultado(1)
        if upsert:
            self.docs.append(_como_mongo(copy.deepcopy(doc)))
        return _Resultado(0)

    async def delete_one(self, filtro):
        self.docs = [d for d in self.docs if not self._coincide(d, filtro)]


class _FakeDb:
    def __init__(self):
        self.cols: dict[str, _Coleccion] = {}

    def __getitem__(self, nombre):
        return self.cols.setdefault(nombre, _Coleccion())


@pytest.fixture
def db():
    return _FakeDb()


@pytest.fixture
def cli(db):
    app = FastAPI()
    app.state.db = db
    app.include_router(router, prefix="/api/v1/crm")
    return TestClient(app)


def crear(cli, usuario="u1", brief=BRIEF):
    return cli.post("/api/v1/crm", json={"brief": brief}, headers={"X-Usuario": usuario})


H = {"X-Usuario": "u1"}


def test_sin_crm_da_404_con_mensaje(cli):
    r = cli.get("/api/v1/crm", headers=H)
    assert r.status_code == 404 and "mensaje" in r.json()


def test_crear_y_obtener(cli):
    r = crear(cli)
    assert r.status_code == 201
    crm = r.json()
    assert crm["totalContactos"] == 120 and crm["brief"]["nombre"] == "Clínica Sol"
    again = cli.get("/api/v1/crm", headers=H).json()
    assert again["contactos"][0]["n"] == crm["contactos"][0]["n"]
    assert all(isinstance(e["h"], str) for e in again["eventos"])  # las fechas guardadas sin zona horaria no rompen la vista


def test_el_brief_se_limpia_y_se_acota(cli):
    r = cli.post("/api/v1/crm", json={"brief": {"nombre": "x" * 61}}, headers=H)
    assert r.status_code == 422
    r = cli.post("/api/v1/crm", json={"brief": {**BRIEF, "campo_raro": "no debe guardarse", "canales": ["x" * 31]}}, headers=H)
    assert r.status_code == 422
    r = cli.post("/api/v1/crm", json={"brief": {**BRIEF, "campo_raro": "no debe guardarse"}}, headers=H)
    assert r.status_code == 201 and "campo_raro" not in r.json()["brief"]


def test_volver_a_crear_reemplaza_el_crm(cli, db):
    crear(cli)
    cli.post("/api/v1/crm/contactos", json={"filas": [{"n": "Laura"}], "canal": "Chat"}, headers=H)
    crear(cli, brief={**BRIEF, "cartera": "k1"})
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 40
    assert len(db["crm_workspaces"].docs) == 1


def test_borrar_crm(cli):
    crear(cli)
    assert cli.delete("/api/v1/crm", headers=H).status_code == 204
    assert cli.get("/api/v1/crm", headers=H).status_code == 404


def test_cada_persona_ve_solo_su_crm(cli):
    crear(cli, "u1")
    assert cli.get("/api/v1/crm", headers={"X-Usuario": "u2"}).status_code == 404
    crear(cli, "u2", {**BRIEF, "nombre": "Otro"})
    cid = cli.get("/api/v1/crm", headers=H).json()["contactos"][0]["id"]
    # u2 no puede tocar un contacto de u1 aunque conozca su id
    assert cli.delete(f"/api/v1/crm/contactos/{cid}", headers={"X-Usuario": "u2"}).status_code == 404
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 120


def test_sin_crm_las_operaciones_dan_404(cli):
    assert cli.post("/api/v1/crm/tareas", json={"t": "x"}, headers=H).status_code == 404
    assert cli.post("/api/v1/crm/chat", json={"texto": "hola"}, headers=H).status_code == 404


def test_contactos_alta_cambio_y_baja(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/contactos", json={"filas": [{"n": "Laura Gómez", "det": "5555"}], "canal": "Importado", "texto": "Importaste 1 contacto"}, headers=H)
    assert r.status_code == 201
    crm = r.json()
    assert crm["totalContactos"] == 121 and crm["contactos"][0]["det"] == "5555" and crm["eventos"][0]["t"] == "Importaste 1 contacto"
    cid = crm["contactos"][0]["id"]
    crm = cli.patch(f"/api/v1/crm/contactos/{cid}", json={"etapa": "Cliente"}, headers=H).json()
    assert crm["contactos"][0]["etapa"] == "Cliente"
    crm = cli.delete(f"/api/v1/crm/contactos/{cid}", headers=H).json()
    assert crm["totalContactos"] == 120 and all(c["id"] != cid for c in crm["contactos"])


def test_validaciones_de_contactos(cli):
    crear(cli)
    cid = cli.get("/api/v1/crm", headers=H).json()["contactos"][0]["id"]
    assert cli.post("/api/v1/crm/contactos", json={"filas": [], "canal": "x"}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/contactos", json={"filas": [{"n": ""}], "canal": "x"}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/contactos", json={"filas": [{"n": "a"}] * 301, "canal": "x"}, headers=H).status_code == 422
    assert cli.patch(f"/api/v1/crm/contactos/{cid}", json={}, headers=H).status_code == 422
    assert cli.patch(f"/api/v1/crm/contactos/{cid}", json={"etapa": "Inventada"}, headers=H).status_code == 422
    assert cli.patch("/api/v1/crm/contactos/no-existe", json={"n": "X"}, headers=H).status_code == 404


def test_tareas(cli):
    crear(cli)
    crm = cli.post("/api/v1/crm/tareas", json={"t": "Llamar a proveedores"}, headers=H).json()
    tid = crm["tareas"]["porHacer"][-1]["id"]
    crm = cli.patch(f"/api/v1/crm/tareas/{tid}", json={"columna": "enCurso"}, headers=H).json()
    assert any(t["id"] == tid for t in crm["tareas"]["enCurso"])
    assert cli.patch(f"/api/v1/crm/tareas/{tid}", json={"columna": "nunca"}, headers=H).status_code == 422
    crm = cli.delete(f"/api/v1/crm/tareas/{tid}", headers=H).json()
    assert all(t["id"] != tid for col in crm["tareas"].values() for t in col)
    assert cli.delete(f"/api/v1/crm/tareas/{tid}", headers=H).status_code == 404


def test_automatizaciones_y_secciones(cli):
    crear(cli)
    crm = cli.put("/api/v1/crm/automatizaciones/vencidos", json={"on": True}, headers=H).json()
    assert next(a for a in crm["automatizaciones"] if a["id"] == "vencidos")["on"] is True
    assert cli.put("/api/v1/crm/automatizaciones/nada", json={"on": True}, headers=H).status_code == 404
    crm = cli.put("/api/v1/crm/secciones/actividad", json={"nombre": "Bitácora clínica"}, headers=H).json()
    assert crm["secciones"]["actividad"] == "Bitácora clínica"
    assert cli.put("/api/v1/crm/secciones/inventada", json={"nombre": "X"}, headers=H).status_code == 404
    assert cli.put("/api/v1/crm/secciones/actividad", json={"nombre": "x" * 29}, headers=H).status_code == 422


def test_chat_completo_con_confirmacion_de_borrado(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H).json()
    assert r["vista"] == "contactos" and r["crm"]["contactos"][0]["n"] == "Laura Gómez"
    r = cli.post("/api/v1/crm/chat", json={"texto": "Elimina a Laura Gómez"}, headers=H).json()
    assert "pendiente" in r and r["crm"]["totalContactos"] == 121  # todavía no se borró
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": r["pendiente"]}}, headers=H).json()
    assert r["crm"]["totalContactos"] == 120 and "pendiente" not in r


def test_chat_con_captura(cli):
    crear(cli)
    img = "data:image/jpeg;base64,/9j/4AAQ"
    r = cli.post("/api/v1/crm/chat", json={"texto": "", "contexto": {"imagen": img, "seccion": "Pacientes"}}, headers=H).json()
    assert "Recibí tu captura de “Pacientes”" in r["respuesta"] and "¿Qué quieres que haga" in r["respuesta"]
    r = cli.post("/api/v1/crm/chat", json={"texto": "agrega la tarea revisar esta tabla", "contexto": {"imagen": img}}, headers=H).json()
    assert r["respuesta"].startswith("📸 Recibí tu captura") and "Revisar esta tabla" in r["respuesta"]


def test_chat_validaciones(cli):
    crear(cli)
    assert cli.post("/api/v1/crm/chat", json={"texto": ""}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/chat", json={"texto": "x" * 301}, headers=H).status_code == 422
    # un "archivo" que no es imagen no cuenta como captura
    assert cli.post("/api/v1/crm/chat", json={"texto": "", "contexto": {"imagen": "data:text/html;base64,AAAA"}}, headers=H).status_code == 422
    # un pendiente falso se ignora en vez de borrar algo
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": {"tipo": "contacto", "id": "../x", "extra": 1}}}, headers=H)
    assert r.status_code == 200 and r.json()["crm"]["totalContactos"] == 120


@pytest.mark.asyncio
async def test_si_alguien_cambia_el_crm_en_medio_se_reintenta(db):
    await repo.reemplazar(db, "u1", generar("u1", BRIEF))
    llamadas = []

    def ajeno(col):  # otra pestaña guarda justo antes de que guardemos nosotros
        col.docs[0]["version"] += 1

    db["crm_workspaces"].antes_de_reemplazar = ajeno

    def cambiar(doc):
        llamadas.append(doc["version"])
        return {**doc, "total_contactos": 999}

    nuevo = await repo.actualizar(db, "u1", cambiar)
    assert llamadas == [1, 2] and nuevo["version"] == 3 and nuevo["total_contactos"] == 999


@pytest.mark.asyncio
async def test_si_siempre_hay_conflicto_se_avisa(db):
    await repo.reemplazar(db, "u1", generar("u1", BRIEF))
    col = db["crm_workspaces"]

    def siempre_ajeno(c):
        c.docs[0]["version"] += 1
        c.antes_de_reemplazar = siempre_ajeno

    col.antes_de_reemplazar = siempre_ajeno
    with pytest.raises(ErrorCrm) as e:
        await repo.actualizar(db, "u1", lambda d: {**d})
    assert e.value.estado == 409


@pytest.mark.asyncio
async def test_si_la_operacion_no_cambia_nada_no_se_escribe(db):
    await repo.reemplazar(db, "u1", generar("u1", BRIEF))
    doc = await repo.actualizar(db, "u1", lambda d: d)
    assert doc["version"] == 1
