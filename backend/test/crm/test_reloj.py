"""El reloj del CRM: ejecuta las automatizaciones sin que nadie abra el CRM y deja avisos. Base de datos falsa en memoria."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import Collections
from app.crm import automatizaciones as au
from app.crm import operaciones as op
from app.crm import reloj
from app.crm.generador import generar

AHORA = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)  # miércoles
BRIEF = {"nombre": "Tacos", "rubro": "comercio", "equipo": "solo", "objetivos": ["seguimientos", "reportes"], "problemas": ["olvido"]}


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return [copy.deepcopy(d) for d in self.docs[:n]]


class _Col:
    def __init__(self):
        self.docs = []
        self.antes_de_reemplazar = None

    def _ok(self, d, filtro):
        for k, v in filtro.items():
            if isinstance(v, dict) and "$elemMatch" in v:
                if not any(all(e.get(a) == b for a, b in v["$elemMatch"].items()) for e in d.get(k, [])):
                    return False
            elif d.get(k) != v:
                return False
        return True

    def find(self, filtro, proyeccion=None):
        return _Cursor([d for d in self.docs if self._ok(d, filtro)])

    async def find_one(self, filtro, proyeccion=None):
        return next((copy.deepcopy(d) for d in self.docs if self._ok(d, filtro)), None)

    async def replace_one(self, filtro, doc, upsert=False):
        if self.antes_de_reemplazar:
            gancho, self.antes_de_reemplazar = self.antes_de_reemplazar, None
            gancho(self)
        for i, d in enumerate(self.docs):
            if self._ok(d, filtro):
                self.docs[i] = copy.deepcopy(doc)
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))


class _Db(dict):
    def __missing__(self, k):
        self[k] = _Col()
        return self[k]


@pytest.fixture(autouse=True)
def sin_espera_ni_eventos(monkeypatch):
    reloj._ultima_pasada = 0.0
    import app.utils.events as eventos

    async def nada(*_a, **_k):
        return None

    monkeypatch.setattr(eventos, "publish_user_event", nada)  # sin Redis en las pruebas


@pytest.fixture
def db():
    return _Db()


def crm_de(user_id, nombres, hace_dias=5, brief=BRIEF, apagar=False):
    d = generar(user_id, brief, AHORA)
    d = op.contactos_crear(d, [{"n": n} for n in nombres], "Chat", ahora=AHORA - timedelta(days=hace_dias))
    if apagar:
        for a in d["automatizaciones"]:
            a["on"] = False
    return d


def avisos(db, user_id=None):
    return [a for a in db[Collections.USER_NOTIFICATIONS].docs if user_id is None or a["user_id"] == user_id]


# ───────── Recordatorios ─────────

@pytest.mark.asyncio
async def test_sin_abrir_el_crm_se_crea_la_tarea_y_el_aviso(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Oscar Siacajau"]))
    assert await reloj.tick(db, AHORA) == 1
    doc = db[Collections.CRM].docs[0]
    t = doc["tareas"]["porHacer"][0]
    assert t["t"] == "Dar seguimiento a Oscar Siacajau" and t["auto"] == "recordatorios" and doc["version"] == 2
    [a] = avisos(db, "u1")
    assert a["type"] == "crm_recordatorio" and a["title"] == "Toca dar seguimiento a Oscar Siacajau" and "3 días" in a["message"] and a["read"] is False


@pytest.mark.asyncio
async def test_otra_pasada_no_duplica_ni_la_tarea_ni_el_aviso(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Oscar"]))
    await reloj.tick(db, AHORA)
    assert await reloj.tick(db, AHORA + timedelta(hours=2), forzar=True) == 0
    assert len(db[Collections.CRM].docs[0]["tareas"]["porHacer"]) == 1 and len(avisos(db)) == 1


@pytest.mark.asyncio
async def test_varios_contactos_dan_un_solo_aviso(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Ana López", "Luis Pérez", "Marta Gil", "Pedro Ruiz", "Rosa Díaz"]))
    await reloj.tick(db, AHORA)
    [a] = avisos(db)
    assert a["title"] == "5 contactos llevan 3 días sin avanzar" and "y 2 más" in a["message"]
    assert len(db[Collections.CRM].docs[0]["tareas"]["porHacer"]) == 5


@pytest.mark.asyncio
async def test_cada_persona_recibe_solo_lo_suyo(db):
    db[Collections.CRM].docs += [crm_de("u1", ["Oscar"]), crm_de("u2", ["Laura"], hace_dias=0)]
    await reloj.tick(db, AHORA)
    assert [a["user_id"] for a in avisos(db)] == ["u1"]
    assert db[Collections.CRM].docs[1]["tareas"]["porHacer"] == []


@pytest.mark.asyncio
async def test_sin_automatizaciones_encendidas_no_se_toca_nada(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Oscar"], apagar=True))
    assert await reloj.tick(db, AHORA) == 0
    assert db[Collections.CRM].docs[0]["version"] == 1 and avisos(db) == []


# ───────── Dos procesos a la vez, fallos y ritmo ─────────

@pytest.mark.asyncio
async def test_si_otro_proceso_cambio_el_crm_en_medio_no_hay_aviso_doble(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Oscar"]))

    def otro_proceso(col):  # justo antes de guardar, alguien más ya lo guardó
        col.docs[0]["version"] += 1

    db[Collections.CRM].antes_de_reemplazar = otro_proceso
    assert await reloj.tick(db, AHORA) == 0
    assert avisos(db) == [] and db[Collections.CRM].docs[0]["tareas"]["porHacer"] == []  # se reintenta en la siguiente pasada
    assert await reloj.tick(db, AHORA, forzar=True) == 1 and len(avisos(db)) == 1


@pytest.mark.asyncio
async def test_un_crm_roto_no_frena_a_los_demas(db, monkeypatch):
    db[Collections.CRM].docs += [crm_de("u1", ["Oscar"]), crm_de("u2", ["Laura"])]
    original = reloj._pasar_uno

    async def rompe_el_primero(db_, user_id, ahora):
        if user_id == "u1":
            raise RuntimeError("documento raro")
        return await original(db_, user_id, ahora)

    monkeypatch.setattr(reloj, "_pasar_uno", rompe_el_primero)
    assert await reloj.tick(db, AHORA) == 1
    assert [a["user_id"] for a in avisos(db)] == ["u2"]


@pytest.mark.asyncio
async def test_el_reloj_no_corre_mas_de_una_vez_cada_cierto_tiempo(db, monkeypatch):
    monkeypatch.setenv("CRM_RELOJ_SEGUNDOS", "300")
    db[Collections.CRM].docs.append(crm_de("u1", ["Oscar"]))
    assert await reloj.tick(db, AHORA) == 1
    db[Collections.CRM].docs.append(crm_de("u2", ["Laura"]))
    assert await reloj.tick(db, AHORA) == 0  # el programador llama cada 30 s, pero todavía no toca
    assert await reloj.tick(db, AHORA, forzar=True) == 1


def test_el_ritmo_se_configura_con_un_minimo(monkeypatch):
    monkeypatch.setenv("CRM_RELOJ_SEGUNDOS", "60")
    assert reloj._cada_cuanto() == 60
    monkeypatch.setenv("CRM_RELOJ_SEGUNDOS", "1")
    assert reloj._cada_cuanto() == 5
    monkeypatch.setenv("CRM_RELOJ_SEGUNDOS", "no es número")
    assert reloj._cada_cuanto() == reloj.SEGUNDOS_POR_DEFECTO


# ───────── Resumen semanal ─────────

@pytest.mark.asyncio
async def test_el_resumen_de_la_semana_llega_como_aviso_y_como_actividad(db):
    d = crm_de("u1", ["Ana", "Luis"], hace_dias=0)
    d["ultimo_resumen"] = "2026-W41"  # el de la semana pasada
    db[Collections.CRM].docs.append(d)
    await reloj.tick(db, AHORA)
    [a] = avisos(db)
    assert a["type"] == "crm_resumen" and a["title"] == "Resumen de tu semana" and a["message"].startswith("Resumen de la semana: 2 contactos")
    doc = db[Collections.CRM].docs[0]
    assert doc["ultimo_resumen"] == "2026-W42" and doc["eventos"][0]["t"].startswith("Resumen de la semana")
    assert await reloj.tick(db, AHORA + timedelta(days=1), forzar=True) == 0  # esta semana ya se mandó


@pytest.mark.asyncio
async def test_la_primera_vez_solo_se_marca_la_semana_sin_aviso(db):
    db[Collections.CRM].docs.append(crm_de("u1", ["Ana"], hace_dias=0))
    await reloj.tick(db, AHORA)
    assert avisos(db) == [] and db[Collections.CRM].docs[0]["ultimo_resumen"] == "2026-W42"


# ───────── Correo y programador ─────────

def test_los_avisos_del_crm_tambien_salen_por_correo_por_defecto(monkeypatch):
    from app.workers import notice_mailer

    monkeypatch.delenv("SHIFU_NOTICE_EMAIL_TYPES", raising=False)
    assert {"crm_recordatorio", "crm_resumen"} <= set(notice_mailer._types())
    assert {"run_failed", "trigger_disabled", "commitment_due"} <= set(notice_mailer._types())  # lo que ya mandaba sigue igual


def test_el_programador_llama_al_reloj_del_crm_y_si_falla_sigue(monkeypatch):
    from app.workers import scheduler_loop as sl

    llamadas = []

    def espia(nombre, falla=False):
        async def f(*_a, **_k):
            llamadas.append(nombre)
            if falla:
                raise RuntimeError("fallo")
        return f

    for nombre in ("tick", "reminder_tick", "mailer_tick", "email_tick"):
        monkeypatch.setattr(sl, nombre, espia(nombre))
    monkeypatch.setattr(sl, "crm_tick", espia("crm_tick", falla=True))

    async def corta(_s):
        raise asyncio.CancelledError

    monkeypatch.setattr(sl.asyncio, "sleep", corta)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sl.run_forever(object(), 1))
    assert "crm_tick" in llamadas and "mailer_tick" in llamadas and "email_tick" in llamadas  # el fallo del CRM no frena lo demás
