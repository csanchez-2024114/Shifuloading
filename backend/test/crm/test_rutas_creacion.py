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


def test_con_la_bandera_se_siembra_la_plantilla_de_asignar(cli, db, con_diseno):
    r = crear(cli, BRIEF_DENTAL)
    assert r.status_code == 201
    crm = r.json()
    assert crm["esquema"] == 2 and crm["plantilla"]["id"] == "clinica-dental" and crm["plantilla"]["origen"] == "asignar"
    assert [l["id"] for l in crm["listas"]] == ["l_citas", "l_tratamientos", "l_pacientes"]
    assert all(len(l["registros"]) == 220 and all(x.get("ejemplo") for x in l["registros"]) for l in crm["listas"])
    assert {b["seccion"] for b in crm["inicio"]} <= {"l_citas", "l_tratamientos", "l_pacientes"} and crm["inicio"][0]["uid"] == "b0"
    assert crm["totalContactos"] == 0 and crm["vendedores"] == ["Tú"]
    guardado = db["crm_workspaces"].docs[0]
    assert guardado["plantilla"]["id"] == "clinica-dental" and len(guardado["listas"][0]["registros"]) == 220
    assert cli.get(URL, headers=H).json()["listas"][0]["id"] == "l_citas"


def test_con_la_bandera_y_respuestas_ambiguas_es_lo_de_carlos(cli, con_diseno):
    crm = crear(cli, BRIEF).json()
    assert crm["plantilla"] == {"id": None, "origen": "generador", "porque": []}
    assert crm["listas"] == [] and crm["contactos"] == []


def test_quitar_ejemplos_borra_solo_los_ejemplos_sembrados(cli, con_diseno):
    crear(cli, BRIEF_DENTAL)
    r = cli.post(f"{URL}/listas/l_pacientes/registros", json={"valores": {"nombre": "Paciente real", "tipo": "Nuevo"}}, headers=H)
    assert r.status_code == 201, r.json()
    crm = cli.post(f"{URL}/registros/ejemplos/quitar", json={"seccion": "l_citas"}, headers=H).json()
    assert [len(l["registros"]) for l in crm["listas"]] == [0, 220, 221]  # solo la sección pedida
    crm = cli.post(f"{URL}/registros/ejemplos/quitar", headers=H).json()
    assert [len(l["registros"]) for l in crm["listas"]] == [0, 0, 1]
    assert crm["listas"][2]["registros"][0]["valores"]["nombre"] == "Paciente real"
    assert [l["id"] for l in crm["listas"]] == ["l_citas", "l_tratamientos", "l_pacientes"]  # las secciones y el inicio se quedan
    assert cli.post(f"{URL}/registros/ejemplos/quitar", headers=H).status_code == 404  # ya no hay ejemplos


def test_un_crm_con_solo_ejemplos_se_puede_volver_a_crear_y_uno_con_datos_no(cli, db, con_diseno):
    crear(cli, BRIEF_DENTAL)
    assert crear(cli, BRIEF_DENTAL).status_code == 201  # los ejemplos no son trabajo de la persona
    cli.post(f"{URL}/listas/l_pacientes/registros", json={"valores": {"nombre": "Paciente real"}}, headers=H)
    assert crear(cli, BRIEF_DENTAL).status_code == 409
    assert len(db["crm_workspaces"].docs) == 1


def test_con_contactos_sembrados_tambien_se_puede_rehacer(cli, monkeypatch, con_diseno):
    from app.crm import sembrar

    monkeypatch.setattr(sembrar, "elegir", lambda brief: {"recomendada": {"id": "agencia-marketing", "porque": ["tu rubro"]}, "opciones": [], "ambiguo": False})
    crm = crear(cli, {"nombre": "Ola", "rubro": "agencia"}).json()
    assert crm["totalContactos"] == 220 and crm["etapas"] == ["Prospecto", "Activo", "En pausa", "Cerrado"]
    assert crear(cli, {"nombre": "Ola", "rubro": "agencia"}).status_code == 201
    cli.post(f"{URL}/contactos", json={"filas": [{"n": "Cliente real"}], "canal": "WhatsApp"}, headers=H)
    assert crear(cli, {"nombre": "Ola", "rubro": "agencia"}).status_code == 409
