"""Rutas de deshacer y los puntos que dejan las rutas a mano (contrato §3 y §4), con una base falsa en memoria que sabe de crm_puntos."""
import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_rutas import BRIEF, _Coleccion, _como_mongo, router  # noqa: F401  (misma base falsa y mismas rutas que test_rutas)

from assistant.packs.crm import repositorio as repo

H = {"X-Usuario": "u1"}
URL = "/api/v1/crm"


def _cumple(valor, condicion):
    if isinstance(condicion, dict) and any(k.startswith("$") for k in condicion):
        return all({"$gte": lambda: valor is not None and valor >= c, "$lte": lambda: valor is not None and valor <= c,
                    "$in": lambda: valor in c}[op]() for op, c in condicion.items())
    return valor == condicion


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, campo, orden):
        self.docs = sorted(self.docs, key=lambda d: d.get(campo), reverse=orden < 0)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    async def to_list(self, length=None):
        return self.docs


def _proyectar(d, proyeccion):
    if not proyeccion:
        return d
    incluir = {k for k, v in proyeccion.items() if v and k != "_id"}
    if incluir:
        return {k: v for k, v in d.items() if k in incluir}
    return {k: v for k, v in d.items() if proyeccion.get(k, 1)}


class _ColeccionPuntos(_Coleccion):
    """La colección falsa de test_rutas, más lo que usan los puntos: insert_one, find con sort/skip, delete_many y operadores."""

    def _coincide(self, d, filtro):
        return all(_cumple(d.get(k), v) for k, v in filtro.items())

    async def insert_one(self, doc):
        if any(d.get("user_id") == doc.get("user_id") and d.get("n") == doc.get("n") for d in self.docs):
            raise AssertionError("índice único (user_id, n) violado")
        self.docs.append(_como_mongo(copy.deepcopy(doc)))

    def find(self, filtro, proyeccion=None):
        return _Cursor([_proyectar(copy.deepcopy(d), proyeccion) for d in self.docs if self._coincide(d, filtro)])

    async def delete_many(self, filtro):
        self.docs = [d for d in self.docs if not self._coincide(d, filtro)]


class _FakeDbPuntos:
    def __init__(self):
        self.cols: dict[str, _ColeccionPuntos] = {}

    def __getitem__(self, nombre):
        return self.cols.setdefault(nombre, _ColeccionPuntos())


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")


@pytest.fixture
def db():
    return _FakeDbPuntos()


@pytest.fixture
def cli(db):
    app = FastAPI()
    app.state.db = db
    app.include_router(router, prefix=URL)
    return TestClient(app)


@pytest.fixture
def crm(cli):
    r = cli.post(URL, json={"brief": BRIEF}, headers=H)
    assert r.status_code == 201
    return r.json()


def _agregar(cli, *nombres):
    return cli.post(f"{URL}/contactos", json={"filas": [{"n": n} for n in nombres], "canal": "WhatsApp"}, headers=H)


def _nombres(crm):
    return [c["n"] for c in crm["contactos"]]


def test_un_crm_nuevo_nace_en_el_esquema_2_sin_puntos(crm):
    assert crm["esquema"] == 2 and crm["puntos"] == [] and crm["inicio"][0]["vista"] == "kpis"


def test_lo_hecho_a_mano_deja_su_punto(cli, crm):
    r = _agregar(cli, "Rosa")
    assert r.status_code == 201
    assert r.json()["puntos"] == [{"n": 1, "antesDe": "A mano: agregó a Rosa", "hora": r.json()["puntos"][0]["hora"], "cambio": ["datos"]}]
    cid = r.json()["contactos"][0]["id"]
    cli.patch(f"{URL}/contactos/{cid}", json={"etapa": "Cliente"}, headers=H)
    cli.post(f"{URL}/tareas", json={"t": "Llamar a Rosa"}, headers=H)
    cli.put(f"{URL}/secciones/cobros", json={"nombre": "Caja"}, headers=H)
    puntos = cli.get(f"{URL}/puntos", headers=H).json()["puntos"]
    assert [(p["n"], p["antesDe"], p["cambio"]) for p in puntos] == [
        (1, "A mano: agregó a Rosa", ["datos"]), (2, "A mano: editó a Rosa", ["datos"]),
        (3, "A mano: agregó la tarea «Llamar a Rosa»", ["datos"]), (4, "A mano: renombró una sección a «Caja»", ["estructura"])]
    assert all("foto" not in p for p in puntos)
    assert cli.get(URL, headers=H).json()["puntos"] == puntos


def test_lo_que_no_se_puede_deshacer_no_deja_punto(cli, crm, db):
    auto = crm["automatizaciones"][0]
    r = cli.put(f"{URL}/automatizaciones/{auto['id']}", json={"on": not auto["on"]}, headers=H)
    assert r.status_code == 200 and r.json()["puntos"] == []
    r = cli.delete(f"{URL}/contactos/no-existe", headers=H)
    assert r.status_code == 404 and db["crm_puntos"].docs == []


def test_deshacer_el_ultimo_y_uno_en_particular(cli, crm):
    _agregar(cli, "Carlos")
    _agregar(cli, "Rosa")
    rosa = next(c for c in cli.get(URL, headers=H).json()["contactos"] if c["n"] == "Rosa")
    cli.patch(f"{URL}/contactos/{rosa['id']}", json={"det": "Plan anual"}, headers=H)
    carlos = next(c for c in cli.get(URL, headers=H).json()["contactos"] if c["n"] == "Carlos")
    cli.delete(f"{URL}/contactos/{carlos['id']}", headers=H)

    r = cli.post(f"{URL}/deshacer", json={"n": 3}, headers=H)  # lo que le cambié a Rosa: Carlos sigue borrado
    assert r.status_code == 200
    body = r.json()
    assert _nombres(body) == ["Rosa"] and body["contactos"][0]["det"] is None
    assert body["deshacer"]["deshechos"] == [3] and "«A mano: editó a Rosa»" in body["deshacer"]["texto"]
    assert [p["n"] for p in body["puntos"]] == [1, 2, 4]

    r = cli.post(f"{URL}/deshacer", headers=H)  # sin n: el último (el borrado de Carlos)
    body = r.json()
    assert sorted(_nombres(body)) == ["Carlos", "Rosa"] and body["totalContactos"] == 2
    assert body["contactos"][1]["det"] is None  # Rosa no revive lo ya deshecho
    assert [p["n"] for p in body["puntos"]] == [1, 2]


def test_deshacer_sin_puntos_o_con_uno_que_no_existe(cli, crm):
    r = cli.post(f"{URL}/deshacer", json={}, headers=H)
    assert r.status_code == 404 and r.json()["mensaje"] == "No hay nada que deshacer."
    _agregar(cli, "Rosa")
    r = cli.post(f"{URL}/deshacer", json={"n": 7}, headers=H)
    assert r.status_code == 404 and "1 «A mano: agregó a Rosa»" in r.json()["mensaje"]
    assert cli.post(f"{URL}/deshacer", json={"n": 0}, headers=H).status_code == 422


def test_en_cadena_se_dice(cli, crm):
    _agregar(cli, "Rosa")
    rid = cli.get(URL, headers=H).json()["contactos"][0]["id"]
    cli.patch(f"{URL}/contactos/{rid}", json={"etapa": "Cliente"}, headers=H)
    body = cli.post(f"{URL}/deshacer", json={"n": 1}, headers=H).json()
    assert body["contactos"] == [] and body["deshacer"]["deshechos"] == [1, 2] and "También se deshizo" in body["deshacer"]["texto"]
    assert body["puntos"] == []


def test_se_guardan_los_ultimos_30(cli, crm, db):
    for i in range(33):
        _agregar(cli, f"Persona {i}")
    puntos = cli.get(f"{URL}/puntos", headers=H).json()["puntos"]
    assert len(puntos) == 30 and puntos[0]["n"] == 4 and puntos[-1]["n"] == 33
    assert len(db["crm_puntos"].docs) == 30


def test_los_puntos_son_de_cada_persona(cli, crm):
    _agregar(cli, "Rosa")
    cli.post(URL, json={"brief": BRIEF}, headers={"X-Usuario": "u2"})
    assert cli.get(f"{URL}/puntos", headers={"X-Usuario": "u2"}).json()["puntos"] == []
    assert cli.post(f"{URL}/deshacer", headers={"X-Usuario": "u2"}).status_code == 404


def test_borrar_o_rehacer_el_crm_olvida_los_puntos(cli, crm, db):
    _agregar(cli, "Rosa")
    assert cli.delete(URL, headers=H).status_code == 204
    assert db["crm_puntos"].docs == []
    assert cli.post(URL, json={"brief": BRIEF}, headers=H).json()["puntos"] == []


def test_quitar_ejemplos_y_deshacerlo(cli, crm, db):
    doc = db["crm_workspaces"].docs[0]  # las secciones se crean por el chat: aquí se siembra directo, como lo haría una plantilla
    doc["listas"] = [{"id": "l_miembros", "nombre": "Miembros", "campos": [{"id": "nombre", "nombre": "Nombre", "tipo": "texto"}],
                      "registros": [{"id": "e1", "valores": {"nombre": "Ejemplo"}, "creado": doc["created_at"], "ejemplo": True},
                                    {"id": "r1", "valores": {"nombre": "Rosa"}, "creado": doc["created_at"]}]}]
    r = cli.post(f"{URL}/registros/ejemplos/quitar", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body["listas"][0]["registros"]] == ["r1"]
    assert body["puntos"][-1]["antesDe"] == "A mano: quitó los ejemplos"
    assert cli.post(f"{URL}/registros/ejemplos/quitar", json={"seccion": "l_miembros"}, headers=H).status_code == 404
    body = cli.post(f"{URL}/deshacer", headers=H).json()
    assert body["listas"][0]["registros"][0] == {"id": "e1", "valores": {"nombre": "Ejemplo"}, "ejemplo": True}


def test_importar_sigue_respondiendo_igual_y_se_puede_deshacer(cli, crm, db):
    doc = db["crm_workspaces"].docs[0]
    doc["listas"] = [{"id": "l_prov", "nombre": "Proveedores", "campos": [{"id": "f_n", "nombre": "Nombre", "tipo": "texto"}], "registros": []}]
    r = cli.post(f"{URL}/listas/l_prov/registros/lote", json={"filas": [{"f_n": "A"}, {"f_n": "B"}], "lote": {"id": "lote01", "nombre": "x.xlsx"}}, headers=H)
    assert r.status_code == 201 and r.json()["importacion"] == {"agregadas": 2, "omitidas": 0}
    assert r.json()["puntos"][-1]["antesDe"] == "A mano: importó 2 filas a Proveedores"
    body = cli.post(f"{URL}/deshacer", headers=H).json()
    assert body["listas"][0]["registros"] == []


def test_si_no_se_puede_guardar_el_punto_el_cambio_igual_se_hace(cli, crm, monkeypatch):
    async def falla(*_a, **_k):
        raise RuntimeError("sin Mongo")

    monkeypatch.setattr(repo, "puntos_agregar", falla)
    r = _agregar(cli, "Rosa")
    assert r.status_code == 201 and _nombres(r.json()) == ["Rosa"]


def test_un_crm_demasiado_grande_no_se_guarda(cli, crm, monkeypatch):
    monkeypatch.setattr(repo, "MAX_BYTES", 2000)
    r = _agregar(cli, "Rosa")
    assert r.status_code == 413 and "demasiado grande" in r.json()["mensaje"]
    assert cli.get(URL, headers=H).json()["contactos"] == []
