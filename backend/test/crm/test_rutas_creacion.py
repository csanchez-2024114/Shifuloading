"""POST /api/v1/crm con y sin CRM_DISENO=1 (frente H), con la misma base falsa en memoria y las mismas rutas que test_rutas."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_rutas import BRIEF, _FakeDb, router  # noqa: F401

H = {"X-Usuario": "u1"}
URL = "/api/v1/crm"
BRIEF_DENTAL = {"nombre": "Sonrisas", "rubro": "salud", "ciclo": "recurrente", "objetivos": ["seguimientos"], "que_vendes": "Consultorio dental familiar"}


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")


@pytest.fixture
def db():
    return _FakeDb()


@pytest.fixture
def cli(db):
    app = FastAPI()
    app.state.db = db
    app.include_router(router, prefix=URL)
    return TestClient(app)


@pytest.fixture
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")


def crear(cli, brief):
    return cli.post(URL, json={"brief": brief}, headers=H)


@pytest.mark.parametrize("valor", [None, "0", ""])
def test_sin_la_bandera_es_exactamente_lo_de_siempre(cli, monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("CRM_DISENO", raising=False)
    else:
        monkeypatch.setenv("CRM_DISENO", valor)
    crm = crear(cli, BRIEF_DENTAL).json()  # aunque haya una plantilla ganadora clara
    assert crm["plantilla"] is None and crm["listas"] == [] and crm["contactos"] == [] and crm["totalContactos"] == 0
    assert [b["seccion"] for b in crm["inicio"]] == ["contactos"]  # el inicio por defecto del esquema 2


def test_con_la_bandera_se_arma_uno_nuevo_con_piezas_y_pocos_ejemplos(cli, db, con_diseno):
    r = crear(cli, BRIEF_DENTAL)
    assert r.status_code == 201
    crm = r.json()
    assert crm["esquema"] == 2 and crm["plantilla"]["origen"] == "piezas" and crm["plantilla"]["id"].startswith("medida-")
    ids = [l["id"] for l in crm["listas"]]
    assert len(ids) >= 3 and "l_pacientes" in ids  # la pieza de pacientes de la clínica dental (sin IA: respaldo con las de mayor %)
    assert all(len(l["registros"]) == 8 and all(x.get("ejemplo") for x in l["registros"]) for l in crm["listas"])  # pocos, no 220
    assert {b["seccion"] for b in crm["inicio"]} <= set(ids) and len(crm["inicio"]) >= 2 and crm["inicio"][0]["uid"] == "b0"
    assert crm["totalContactos"] == 0 and crm["vendedores"] == ["Tú"]
    assert crm["resumenIA"].startswith("Te dejé una base con") and crm["saludoEjemplos"]
    guardado = db["crm_workspaces"].docs[0]
    assert guardado["plantilla"]["respaldo"] is True and len(guardado["listas"][0]["registros"]) == 8
    assert [l["id"] for l in cli.get(URL, headers=H).json()["listas"]] == ids


def test_con_la_bandera_respuestas_vagas_tampoco_dejan_un_crm_casi_vacio(cli, con_diseno):
    crm = crear(cli, BRIEF).json()  # antes: «ambiguo» → 0 secciones y 0 ejemplos (caso 21b)
    assert crm["plantilla"]["origen"] == "piezas" and len(crm["listas"]) >= 3
    assert all(l["registros"] for l in crm["listas"]) and len(crm["inicio"]) >= 2


def test_quitar_ejemplos_borra_solo_los_ejemplos_sembrados(cli, con_diseno):
    ids = [l["id"] for l in crear(cli, BRIEF_DENTAL).json()["listas"]]
    r = cli.post(f"{URL}/listas/l_pacientes/registros", json={"valores": {"nombre": "Paciente real"}}, headers=H)
    assert r.status_code == 201, r.json()
    otra = next(i for i in ids if i != "l_pacientes")
    crm = cli.post(f"{URL}/registros/ejemplos/quitar", json={"seccion": otra}, headers=H).json()
    por_id = {l["id"]: len(l["registros"]) for l in crm["listas"]}
    assert por_id[otra] == 0 and por_id["l_pacientes"] == 9  # solo la sección pedida
    crm = cli.post(f"{URL}/registros/ejemplos/quitar", headers=H).json()
    assert {l["id"]: len(l["registros"]) for l in crm["listas"]} == {i: (1 if i == "l_pacientes" else 0) for i in ids}
    assert [l["id"] for l in crm["listas"]] == ids  # las secciones y el inicio se quedan
    assert cli.post(f"{URL}/registros/ejemplos/quitar", headers=H).status_code == 404  # ya no hay ejemplos


def test_un_crm_con_solo_ejemplos_se_puede_volver_a_crear_y_uno_con_datos_no(cli, db, con_diseno):
    crear(cli, BRIEF_DENTAL)
    assert crear(cli, BRIEF_DENTAL).status_code == 201  # los ejemplos no son trabajo de la persona
    cli.post(f"{URL}/listas/l_pacientes/registros", json={"valores": {"nombre": "Paciente real"}}, headers=H)
    assert crear(cli, BRIEF_DENTAL).status_code == 409
    assert len(db["crm_workspaces"].docs) == 1


class _ModeloClientes:
    """La IA (falsa) arma clientes con etapas primero: van a los contactos de Carlos."""

    async def ainvoke(self, mensajes):
        import json

        return type("R", (), {"content": json.dumps({"secciones": [
            {"id": "clientes", "titulo": "Clientes", "campos": [["nombre", "Nombre", "texto", "persona"], ["telefono", "Teléfono", "texto", ["5555 1234"]],
                                                                 ["etapa", "Etapa", "estado", ["Prospecto", "Activo", "En pausa", "Cerrado"]]]},
            {"id": "campanas", "titulo": "Campañas", "vista": "tablero", "opciones": {"por": "estado"},
             "campos": [["campana", "Campaña", "texto", ["Lanzamiento"]], ["estado", "Estado", "estado", ["Propuesta", "Activa", "Cerrada"]], ["inicio", "Inicio", "fecha"]]},
            {"id": "entregas", "titulo": "Entregables", "campos": [["pieza", "Pieza", "texto", ["Video"]], ["entrega", "Entrega", "fecha"]]}],
            "inicio": [{"seccion": "campanas", "vista": "kpis", "opciones": {"por": "estado"}}, {"seccion": "entregas", "vista": "vencimientos", "opciones": {}}]})})()


def test_con_contactos_sembrados_tambien_se_puede_rehacer(cli, monkeypatch, con_diseno):
    from app.crm import agente, primer_diseno

    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(primer_diseno, "modelo_creacion", lambda: _ModeloClientes())
    crm = crear(cli, {"nombre": "Ola", "rubro": "agencia"}).json()
    assert crm["totalContactos"] == 8 and crm["etapas"] == ["Prospecto", "Activo", "En pausa", "Cerrado"]
    assert crm["plantilla"]["respaldo"] is False and crm["plantilla"]["llamadas"] == 1
    assert crear(cli, {"nombre": "Ola", "rubro": "agencia"}).status_code == 201
    cli.post(f"{URL}/contactos", json={"filas": [{"n": "Cliente real"}], "canal": "WhatsApp"}, headers=H)
    assert crear(cli, {"nombre": "Ola", "rubro": "agencia"}).status_code == 409


def test_la_pregunta_abierta_y_las_respuestas_aceptan_1500_caracteres(cli, con_diseno):
    largo = {"nombre": "PepesCore", "rubro": "comercio", "que_vendes": "v" * 1500, "seguimiento": [{"pregunta": "¿Qué quieres lograr?", "respuesta": "r" * 1500}]}
    assert crear(cli, largo).status_code == 201  # antes se cortaba en 300 («…y mi personal», lista 24)
    assert crear(cli, {**largo, "que_vendes": "v" * 1501}).status_code == 422
    assert crear(cli, {**largo, "seguimiento": [{"pregunta": "¿Qué?", "respuesta": "r" * 1501}]}).status_code == 422
