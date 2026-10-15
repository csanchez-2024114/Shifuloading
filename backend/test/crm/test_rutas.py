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

from app.crm import agente, repositorio as repo  # noqa: E402
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


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    """Estas pruebas nunca deben llamar al OpenAI de verdad (el .env del backend trae una clave real y se carga solo)."""
    monkeypatch.setenv("CRM_IA", "0")


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


def con_contactos(cli, usuario="u1", nombres=("Ana Morales", "Luis Pérez", "Sofía Ríos")):
    """El CRM nace vacío: las pruebas que necesitan contactos los agregan igual que lo haría la persona."""
    return cli.post("/api/v1/crm/contactos", json={"filas": [{"n": n} for n in nombres], "canal": "WhatsApp"}, headers={"X-Usuario": usuario}).json()


H = {"X-Usuario": "u1"}


def test_sin_crm_da_404_con_mensaje(cli):
    r = cli.get("/api/v1/crm", headers=H)
    assert r.status_code == 404 and "mensaje" in r.json()


def test_crear_y_obtener(cli):
    r = crear(cli)
    assert r.status_code == 201
    crm = r.json()
    assert crm["brief"]["nombre"] == "Clínica Sol"
    # nace vacío: nada de contactos, equipo, tareas ni actividad inventados
    assert crm["totalContactos"] == 0 and crm["contactos"] == [] and crm["vendedores"] == ["Tú"]
    assert crm["tareas"] == {"porHacer": [], "enCurso": [], "hecho": []}
    assert [e["t"] for e in crm["eventos"]] == ["Shifu creó tu CRM"]
    again = cli.get("/api/v1/crm", headers=H).json()
    assert again["brief"] == crm["brief"] and again["totalContactos"] == 0
    assert all(isinstance(e["h"], str) for e in again["eventos"])  # las fechas guardadas sin zona horaria no rompen la vista


def test_el_brief_se_limpia_y_se_acota(cli):
    r = cli.post("/api/v1/crm", json={"brief": {"nombre": "x" * 61}}, headers=H)
    assert r.status_code == 422
    r = cli.post("/api/v1/crm", json={"brief": {**BRIEF, "campo_raro": "no debe guardarse", "canales": ["x" * 31]}}, headers=H)
    assert r.status_code == 422
    r = cli.post("/api/v1/crm", json={"brief": {**BRIEF, "campo_raro": "no debe guardarse"}}, headers=H)
    assert r.status_code == 201 and "campo_raro" not in r.json()["brief"]


def test_un_crm_con_datos_no_se_pisa_al_crear_otro(cli, db):
    crear(cli)
    assert con_contactos(cli)["totalContactos"] == 3
    r = crear(cli, brief={**BRIEF, "cartera": "k1"})  # p. ej. un cuestionario viejo que quedó en el navegador
    assert r.status_code == 409 and "Repetir cuestionario" in r.json()["mensaje"]
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 3  # no se tocó nada
    assert len(db["crm_workspaces"].docs) == 1


def test_un_crm_con_tareas_o_registros_tampoco_se_pisa(cli):
    crear(cli)
    cli.post("/api/v1/crm/tareas", json={"t": "Llamar a proveedores"}, headers=H)
    assert crear(cli).status_code == 409


def test_un_crm_vacio_si_se_puede_volver_a_crear(cli, db):
    crear(cli)
    r = crear(cli, brief={**BRIEF, "cartera": "k1"})  # la persona no ha trabajado nada: no hay qué perder
    assert r.status_code == 201 and r.json()["brief"]["cartera"] == "k1" and len(db["crm_workspaces"].docs) == 1


def test_las_tareas_de_las_automatizaciones_no_cuentan_como_trabajo_de_la_persona(cli, db):
    crear(cli)
    db["crm_workspaces"].docs[0]["tareas"]["porHacer"].append({"id": "a1", "t": "Dar seguimiento a X", "auto": "recordatorios"})
    assert crear(cli).status_code == 201


def test_para_rehacer_se_borra_primero_y_entonces_se_crea(cli):
    crear(cli)
    con_contactos(cli)
    assert cli.delete("/api/v1/crm", headers=H).status_code == 204
    assert crear(cli, brief={**BRIEF, "cartera": "k1"}).status_code == 201


def test_borrar_crm(cli):
    crear(cli)
    assert cli.delete("/api/v1/crm", headers=H).status_code == 204
    assert cli.get("/api/v1/crm", headers=H).status_code == 404


def test_cada_persona_ve_solo_su_crm(cli):
    crear(cli, "u1")
    cid = con_contactos(cli, "u1")["contactos"][0]["id"]
    assert cli.get("/api/v1/crm", headers={"X-Usuario": "u2"}).status_code == 404
    crear(cli, "u2", {**BRIEF, "nombre": "Otro"})
    # u2 no puede tocar un contacto de u1 aunque conozca su id, ni ve los suyos en su CRM
    assert cli.delete(f"/api/v1/crm/contactos/{cid}", headers={"X-Usuario": "u2"}).status_code == 404
    assert cli.get("/api/v1/crm", headers={"X-Usuario": "u2"}).json()["contactos"] == []
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 3


def test_sin_crm_las_operaciones_dan_404(cli):
    assert cli.post("/api/v1/crm/tareas", json={"t": "x"}, headers=H).status_code == 404
    assert cli.post("/api/v1/crm/chat", json={"texto": "hola"}, headers=H).status_code == 404


def test_contactos_alta_cambio_y_baja(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/contactos", json={"filas": [{"n": "Laura Gómez", "det": "5555"}], "canal": "Importado", "texto": "Importaste 1 contacto"}, headers=H)
    assert r.status_code == 201
    crm = r.json()
    assert crm["totalContactos"] == 1 and crm["contactos"][0]["det"] == "5555" and crm["eventos"][0]["t"] == "Importaste 1 contacto"
    cid = crm["contactos"][0]["id"]
    crm = cli.patch(f"/api/v1/crm/contactos/{cid}", json={"etapa": "Cliente"}, headers=H).json()
    assert crm["contactos"][0]["etapa"] == "Cliente"
    crm = cli.delete(f"/api/v1/crm/contactos/{cid}", headers=H).json()
    assert crm["totalContactos"] == 0 and all(c["id"] != cid for c in crm["contactos"])


def test_validaciones_de_contactos(cli):
    crear(cli)
    cid = con_contactos(cli)["contactos"][0]["id"]
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
    crm = cli.put("/api/v1/crm/automatizaciones/resumen", json={"on": True}, headers=H).json()
    assert next(a for a in crm["automatizaciones"] if a["id"] == "resumen")["on"] is True
    assert cli.put("/api/v1/crm/automatizaciones/nada", json={"on": True}, headers=H).status_code == 404
    crm = cli.put("/api/v1/crm/secciones/actividad", json={"nombre": "Bitácora clínica"}, headers=H).json()
    assert crm["secciones"]["actividad"] == "Bitácora clínica"
    assert cli.put("/api/v1/crm/secciones/inventada", json={"nombre": "X"}, headers=H).status_code == 404
    assert cli.put("/api/v1/crm/secciones/actividad", json={"nombre": "x" * 29}, headers=H).status_code == 422


def test_chat_completo_con_confirmacion_de_borrado(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H).json()
    assert r["vista"] == "contactos" and r["crm"]["contactos"][0]["n"] == "Laura Gómez" and r["crm"]["totalContactos"] == 1
    r = cli.post("/api/v1/crm/chat", json={"texto": "Elimina a Laura Gómez"}, headers=H).json()
    assert "pendiente" in r and r["crm"]["totalContactos"] == 1  # todavía no se borró
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": r["pendiente"]}}, headers=H).json()
    assert r["crm"]["totalContactos"] == 0 and "pendiente" not in r


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
    assert cli.post("/api/v1/crm/chat", json={"texto": "x" * 2001}, headers=H).status_code == 422
    # un "archivo" que no es imagen no cuenta como captura
    assert cli.post("/api/v1/crm/chat", json={"texto": "", "contexto": {"imagen": "data:text/html;base64,AAAA"}}, headers=H).status_code == 422
    # un pendiente falso se ignora en vez de borrar algo
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": {"tipo": "contacto", "id": "../x", "extra": 1}}}, headers=H)
    assert r.status_code == 200 and r.json()["crm"]["totalContactos"] == 0


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


# ───────── Chat con IA (el agente se reemplaza por uno falso: no hay llamadas reales) ─────────

def _con_ia(monkeypatch, funcion):
    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(agente, "responder", funcion)


def test_el_chat_usa_la_ia_cuando_esta_disponible(cli, monkeypatch):
    crear(cli)
    visto = {}

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **_):
        visto.update(texto=texto, historial=historial, captura=con_captura)
        from app.crm import operaciones as op
        return {"doc": op.contactos_crear(doc, [{"n": "Pedro Castillo"}], "Chat con Shifu"), "respuesta": "Agregué a Pedro Castillo.", "modo": "ia", "vista": "contactos"}

    _con_ia(monkeypatch, falso)
    r = cli.post("/api/v1/crm/chat", json={"texto": "mete a pedro", "contexto": {"historial": [{"de": "yo", "t": "hola"}, {"de": "shifu", "t": "¿en qué te ayudo?"}]}}, headers=H).json()
    assert r["modo"] == "ia" and r["respuesta"] == "Agregué a Pedro Castillo." and r["vista"] == "contactos"
    assert r["crm"]["contactos"][0]["n"] == "Pedro Castillo" and r["crm"]["totalContactos"] == 1  # y quedó guardado
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 1
    assert visto["texto"] == "mete a pedro" and len(visto["historial"]) == 2 and visto["captura"] is False


def test_si_la_ia_falla_el_chat_sigue_con_las_reglas(cli, monkeypatch):
    crear(cli)

    async def roto(*_a, **_k):
        raise RuntimeError("insufficient_quota")

    _con_ia(monkeypatch, roto)
    r = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H).json()
    assert r["modo"] == "reglas" and r["crm"]["contactos"][0]["n"] == "Laura Gómez"


def test_confirmar_un_borrado_nunca_pasa_por_la_ia(cli, monkeypatch):
    crear(cli)
    cid = con_contactos(cli)["contactos"][0]["id"]
    llamadas = []

    async def no_debe_llamarse(*_a, **_k):
        llamadas.append(1)
        raise AssertionError("la IA no debe resolver confirmaciones")

    _con_ia(monkeypatch, no_debe_llamarse)
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": {"tipo": "contacto", "id": cid}}}, headers=H).json()
    assert llamadas == [] and r["modo"] == "reglas" and r["crm"]["totalContactos"] == 2


def test_una_captura_sin_texto_va_a_la_ia_con_la_imagen_y_la_seccion(cli, monkeypatch):
    crear(cli)
    visto = {}

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **extra):
        visto.update(texto=texto, captura=con_captura, **extra)
        return {"doc": doc, "respuesta": "Veo una tabla con 3 clientes.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    img = "data:image/jpeg;base64,/9j/4AAQ"
    r = cli.post("/api/v1/crm/chat", json={"texto": "", "contexto": {"imagen": img, "seccion": "Pacientes"}}, headers=H).json()
    assert visto["imagen"] == img and visto["seccion"] == "Pacientes" and visto["captura"] is True and "imagen" in visto["texto"].lower()
    assert r["respuesta"] == "Veo una tabla con 3 clientes." and r["modo"] == "ia"  # con IA no hay aviso de "no puedo leer"


def test_con_ia_la_captura_no_lleva_el_aviso_de_que_no_se_puede_leer(cli, monkeypatch):
    crear(cli)

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **_):
        return {"doc": doc, "respuesta": "Listo.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    r = cli.post("/api/v1/crm/chat", json={"texto": "mira esto", "contexto": {"imagen": "data:image/png;base64,iVBOR"}}, headers=H).json()
    assert r["respuesta"] == "Listo." and r["modo"] == "ia"


def test_una_captura_con_un_borrado_por_confirmar_igual_la_lee_la_ia(cli, monkeypatch):
    crear(cli)
    visto = {}

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **extra):
        visto.update(extra)
        return {"doc": doc, "respuesta": "Veo la tabla.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    ctx = {"imagen": "data:image/png;base64,iVBOR", "pendiente": {"tipo": "contacto", "id": "c1"}}
    r = cli.post("/api/v1/crm/chat", json={"texto": "mira esto", "contexto": ctx}, headers=H).json()
    assert r["modo"] == "ia" and visto["imagen"] and "pendiente" not in r  # el borrado pendiente se descarta, nada se borra


def test_si_el_modelo_no_puede_con_la_imagen_se_reintenta_solo_con_el_texto(cli, monkeypatch):
    crear(cli)
    intentos = []

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **extra):
        intentos.append("imagen" in extra)
        if "imagen" in extra:
            raise RuntimeError("Error code: 400 - invalid image")
        return {"doc": doc, "respuesta": "Sin ver la imagen, ¿qué necesitas?", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    antes = agente._pausa_hasta
    r = cli.post("/api/v1/crm/chat", json={"texto": "mira esto", "contexto": {"imagen": "data:image/jpeg;base64,/9j/4AAQ"}}, headers=H).json()
    assert intentos == [True, False] and r["modo"] == "ia" and agente._pausa_hasta == antes  # un mal archivo no apaga la IA para todos


def test_sin_ia_la_captura_se_reconoce_pero_dice_que_no_puede_leerla(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/chat", json={"texto": "agrega la tarea revisar esta tabla", "contexto": {"imagen": "data:image/jpeg;base64,/9j/4AAQ"}}, headers=H).json()
    assert r["modo"] == "reglas" and r["respuesta"].startswith("📸 Recibí tu captura") and "no puedo leer imágenes" in r["respuesta"]


def test_solo_se_aceptan_los_formatos_de_imagen_que_el_modelo_lee(cli):
    crear(cli)
    for mime in ("png", "jpeg", "jpg", "webp", "gif"):
        assert cli.post("/api/v1/crm/chat", json={"texto": "hola", "contexto": {"imagen": f"data:image/{mime};base64,AAAA"}}, headers=H).status_code == 200
    # un SVG u otro "archivo" no cuenta como captura: sin texto no hay nada que hacer
    assert cli.post("/api/v1/crm/chat", json={"texto": "", "contexto": {"imagen": "data:image/svg+xml;base64,AAAA"}}, headers=H).status_code == 422


def test_el_historial_del_chat_se_valida(cli):
    crear(cli)
    muchos = [{"de": "yo", "t": "x"}] * 21
    assert cli.post("/api/v1/crm/chat", json={"texto": "hola", "contexto": {"historial": muchos}}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/chat", json={"texto": "hola", "contexto": {"historial": [{"de": "otro", "t": "x"}]}}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/chat", json={"texto": "hola", "contexto": {"historial": [{"de": "yo", "t": "x" * 501}]}}, headers=H).status_code == 422


def test_sin_clave_el_chat_responde_con_reglas_y_lo_dice(cli):
    crear(cli)
    r = cli.post("/api/v1/crm/chat", json={"texto": "hola"}, headers=H).json()
    assert r["modo"] == "reglas"


def test_si_otra_pestana_cambia_el_crm_mientras_la_ia_piensa_se_repite(cli, db, monkeypatch):
    crear(cli)
    veces = []

    async def lento(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **_):
        from app.crm import operaciones as op
        veces.append(doc["version"])
        if len(veces) == 1:  # mientras "piensa", otra pestaña guarda
            db["crm_workspaces"].docs[0]["version"] += 1
        return {"doc": op.tareas_crear(doc, "Revisar", None), "respuesta": "Listo.", "modo": "ia"}

    _con_ia(monkeypatch, lento)
    r = cli.post("/api/v1/crm/chat", json={"texto": "agrega una tarea"}, headers=H).json()
    assert veces == [1, 2] and r["crm"]["tareas"]["porHacer"][0]["t"] == "Revisar" and len(r["crm"]["tareas"]["porHacer"]) == 1


def test_tras_un_fallo_de_la_ia_el_siguiente_mensaje_no_la_vuelve_a_intentar(cli, monkeypatch):
    crear(cli)
    llamadas = []

    async def sin_saldo(*_a, **_k):
        llamadas.append(1)
        raise RuntimeError("Error code: 429 - insufficient_quota")

    monkeypatch.setattr(agente, "responder", sin_saldo)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-prueba")
    monkeypatch.setenv("CRM_IA", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)
    try:
        r1 = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H).json()
        r2 = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Pedro Castillo"}, headers=H).json()
        assert r1["modo"] == "reglas" and r2["modo"] == "reglas" and r2["crm"]["totalContactos"] == 2
        assert llamadas == [1]  # el segundo mensaje ni siquiera intentó con la IA
    finally:
        monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


# ───────── Estructura: secciones propias, etapas y campos ─────────

def _con_lista(db, nombre="Proveedores", campos=None):
    """Aplica una operación de estructura directo en la base falsa (en la app real la hace la IA por el chat)."""
    from app.crm import estructura as est
    doc = db["crm_workspaces"].docs[0]
    nuevo = est.lista_crear(doc, nombre, campos or [{"nombre": "Nombre"}, {"nombre": "Deuda", "tipo": "numero"}])
    nuevo["version"] = doc["version"] + 1
    db["crm_workspaces"].docs[0] = nuevo
    return nuevo["listas"][-1]


def test_un_crm_viejo_sin_los_campos_nuevos_se_sigue_pudiendo_abrir(cli, db):
    crear(cli)
    for k in ("etapas", "ocultas", "campos_contacto", "listas"):
        db["crm_workspaces"].docs[0].pop(k, None)
    r = cli.get("/api/v1/crm", headers=H).json()
    assert r["etapas"] == ["Nuevo", "En contacto", "Interesado", "Cliente"] and r["listas"] == [] and r["ocultas"] == [] and r["camposContacto"] == []


def test_registros_de_una_seccion_propia_por_las_rutas(cli, db):
    crear(cli)
    l = _con_lista(db)
    nombre, deuda = (c["id"] for c in l["campos"])
    r = cli.post(f"/api/v1/crm/listas/{l['id']}/registros", json={"valores": {nombre: "Ferretería Díaz", deuda: "1,200"}}, headers=H)
    assert r.status_code == 201
    reg = r.json()["listas"][0]["registros"][0]
    assert reg["valores"] == {nombre: "Ferretería Díaz", deuda: 1200}
    r = cli.patch(f"/api/v1/crm/listas/{l['id']}/registros/{reg['id']}", json={"valores": {deuda: 900}}, headers=H).json()
    assert r["listas"][0]["registros"][0]["valores"][deuda] == 900
    r = cli.delete(f"/api/v1/crm/listas/{l['id']}/registros/{reg['id']}", headers=H).json()
    assert r["listas"][0]["registros"] == []


def test_validaciones_de_registros(cli, db):
    crear(cli)
    l = _con_lista(db)
    nombre, deuda = (c["id"] for c in l["campos"])
    url = f"/api/v1/crm/listas/{l['id']}/registros"
    assert cli.post(url, json={"valores": {deuda: "mucho"}}, headers=H).status_code == 422
    assert cli.post(url, json={"valores": {"f_inventado": "x"}}, headers=H).status_code == 422
    assert cli.post(url, json={"valores": {}}, headers=H).status_code == 422
    assert cli.post("/api/v1/crm/listas/l_no/registros", json={"valores": {nombre: "x"}}, headers=H).status_code == 404
    assert cli.patch(f"{url}/no-existe", json={"valores": {nombre: "x"}}, headers=H).status_code == 404
    assert cli.delete(f"{url}/no-existe", headers=H).status_code == 404
    assert cli.post(url, json={"valores": {c: "x" for c in [f"c{i}" for i in range(20)]}}, headers=H).status_code == 422  # demasiados campos


def test_los_registros_son_de_cada_persona(cli, db):
    crear(cli, "u1")
    l = _con_lista(db)
    crear(cli, "u2")
    assert cli.post(f"/api/v1/crm/listas/{l['id']}/registros", json={"valores": {l["campos"][0]["id"]: "x"}}, headers={"X-Usuario": "u2"}).status_code == 404


def test_campos_extra_de_los_contactos_por_las_rutas(cli, db):
    from app.crm import estructura as est
    crear(cli)
    cid_contacto = con_contactos(cli)["contactos"][0]["id"]
    doc = db["crm_workspaces"].docs[0]
    nuevo = est.campo_agregar(doc, "contactos", "Teléfono", "texto")
    nuevo["version"] = doc["version"] + 1
    db["crm_workspaces"].docs[0] = nuevo
    cid = nuevo["campos_contacto"][0]["id"]
    r = cli.patch(f"/api/v1/crm/contactos/{cid_contacto}", json={"extra": {cid: "5555-1234"}}, headers=H).json()
    assert r["contactos"][0]["extra"] == {cid: "5555-1234"} and r["camposContacto"][0]["nombre"] == "Teléfono"
    assert cli.patch(f"/api/v1/crm/contactos/{cid_contacto}", json={"extra": {"f_inventado": "x"}}, headers=H).status_code == 422
    r = cli.post("/api/v1/crm/contactos", json={"filas": [{"n": "Pedro", "extra": {cid: "4444"}}], "canal": "Chat"}, headers=H).json()
    assert r["contactos"][0]["extra"] == {cid: "4444"}


def test_las_etapas_propias_valen_para_las_rutas_de_contactos(cli, db):
    from app.crm import estructura as est
    crear(cli)
    cid = con_contactos(cli)["contactos"][0]["id"]
    doc = db["crm_workspaces"].docs[0]
    nuevo = est.etapas_definir(doc, ["Prospecto", "Cotización", "Cliente"])
    nuevo["version"] = doc["version"] + 1
    db["crm_workspaces"].docs[0] = nuevo
    assert cli.patch(f"/api/v1/crm/contactos/{cid}", json={"etapa": "Nuevo"}, headers=H).status_code == 422
    r = cli.patch(f"/api/v1/crm/contactos/{cid}", json={"etapa": "Cotización"}, headers=H).json()
    assert r["etapas"] == ["Prospecto", "Cotización", "Cliente"] and r["contactos"][0]["etapa"] == "Cotización"


def test_renombrar_una_seccion_propia_por_la_ruta(cli, db):
    crear(cli)
    l = _con_lista(db)
    r = cli.put(f"/api/v1/crm/secciones/{l['id']}", json={"nombre": "Mis proveedores"}, headers=H).json()
    assert r["listas"][0]["nombre"] == "Mis proveedores"


def test_confirmar_el_borrado_de_una_seccion_propia_por_el_chat(cli, db):
    crear(cli)
    l = _con_lista(db)
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": {"tipo": "lista", "id": l["id"]}}}, headers=H).json()
    assert r["crm"]["listas"] == [] and r["modo"] == "reglas"
    # un pendiente con otra persona o inventado no borra nada
    l2 = _con_lista(db, "Otra")
    r = cli.post("/api/v1/crm/chat", json={"texto": "sí", "contexto": {"pendiente": {"tipo": "lista", "id": "l_inventada"}}}, headers=H).json()
    assert len(r["crm"]["listas"]) == 1 and l2["id"] == r["crm"]["listas"][0]["id"]


# ───────── La IA diseña el CRM desde el cuestionario ─────────

def test_las_preguntas_de_seguimiento_no_piden_sesion_y_usan_las_del_rubro_sin_ia(cli):
    r = cli.post("/api/v1/crm/seguimiento", json={"brief": {"rubro": "tecnologia", "nombre": "Nube Sur"}})
    assert r.status_code == 200 and r.json()["modo"] == "base" and r.json()["preguntas"]
    p = r.json()["preguntas"][0]
    assert {"id", "tipo", "titulo", "emoji", "opciones"} <= set(p)


def test_las_preguntas_de_seguimiento_exigen_el_rubro_y_validan_el_cuestionario(cli):
    assert cli.post("/api/v1/crm/seguimiento", json={"brief": {"nombre": "Sin rubro"}}).status_code == 422
    assert cli.post("/api/v1/crm/seguimiento", json={"brief": {"rubro": "comercio", "que_vendes": "x" * 301}}).status_code == 422
    assert cli.post("/api/v1/crm/seguimiento", json={}).status_code == 422


def test_el_cuestionario_acepta_que_vende_y_las_respuestas_de_seguimiento(cli):
    brief = {**BRIEF, "que_vendes": "pan por encargo", "seguimiento": [{"pregunta": "¿Haces entregas?", "respuesta": "A domicilio, En el local"}]}
    r = crear(cli, brief=brief)
    assert r.status_code == 201
    assert r.json()["brief"]["que_vendes"] == "pan por encargo" and r.json()["brief"]["seguimiento"][0]["respuesta"] == "A domicilio, En el local"
    assert r.json()["resumenIA"] is None  # sin IA no hay resumen: la plantilla base no inventa nada
    muchas = {**BRIEF, "seguimiento": [{"pregunta": "p", "respuesta": "r"}] * 7}
    assert crear(cli, brief=muchas).status_code == 422


def test_con_ia_el_crm_nace_con_la_estructura_que_diseno(cli, monkeypatch):
    import json as _json
    from langchain_core.messages import AIMessage
    from app.crm import diseno

    propuesta = {"resumen": "Armé tu CRM para tus pedidos.", "etapas": ["Consulta", "Pedido", "Entregado"], "campos_contacto": [{"nombre": "Cumpleaños", "tipo": "fecha"}],
                 "secciones": [{"nombre": "Proveedores", "campos": [{"nombre": "Nombre"}, {"nombre": "Teléfono"}]}], "nombres": {"rrhh": "Mi equipo"}, "automatizaciones": ["recordatorios"]}

    class Falso:
        async def ainvoke(self, _m):
            return AIMessage(content=_json.dumps(propuesta, ensure_ascii=False))

    monkeypatch.setenv("OPENAI_API_KEY", "sk-prueba")
    monkeypatch.setenv("CRM_IA", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)
    monkeypatch.setattr(diseno, "_modelo", lambda: Falso())
    r = crear(cli).json()
    assert r["etapas"] == ["Consulta", "Pedido", "Entregado"] and [c["nombre"] for c in r["camposContacto"]] == ["Cumpleaños"]
    assert [l["nombre"] for l in r["listas"]] == ["Proveedores"] and r["secciones"]["rrhh"] == "Mi equipo"
    assert r["resumenIA"] == "Armé tu CRM para tus pedidos." and r["totalContactos"] == 0
    # y queda guardado: al pedirlo de nuevo sigue igual
    assert cli.get("/api/v1/crm", headers=H).json()["resumenIA"] == "Armé tu CRM para tus pedidos."


def test_si_la_ia_falla_al_crear_el_crm_se_crea_igual_con_la_plantilla(cli, monkeypatch):
    from app.crm import diseno

    class Roto:
        async def ainvoke(self, _m):
            raise RuntimeError("Error code: 429 - insufficient_quota")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-prueba")
    monkeypatch.setenv("CRM_IA", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)
    monkeypatch.setattr(diseno, "_modelo", lambda: Roto())
    try:
        r = crear(cli)
        assert r.status_code == 201 and r.json()["listas"] == [] and r.json()["etapas"] == ["Nuevo", "En contacto", "Interesado", "Cliente"]
    finally:
        monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


# ───────── Automatizaciones al abrir el CRM ─────────

def test_al_abrir_el_crm_las_automatizaciones_crean_los_recordatorios_pendientes(cli, db):
    from datetime import datetime, timedelta, timezone

    crear(cli, brief={**BRIEF, "objetivos": ["seguimientos"]})
    con_contactos(cli, nombres=("Oscar Siacajau",))
    doc = db["crm_workspaces"].docs[0]
    doc["contactos"][0]["ultimo_contacto"] = datetime.now(timezone.utc) - timedelta(days=5)  # lleva 5 días sin avanzar
    r1 = cli.get("/api/v1/crm", headers=H).json()
    auto = [t for t in r1["tareas"]["porHacer"] if t.get("auto")]
    assert len(auto) == 1 and auto[0]["t"] == "Dar seguimiento a Oscar Siacajau" and auto[0]["contacto"] == "Oscar Siacajau"
    assert any("Recordatorio automático" in e["t"] for e in r1["eventos"])
    r2 = cli.get("/api/v1/crm", headers=H).json()  # abrir otra vez no duplica
    assert len([t for t in r2["tareas"]["porHacer"] if t.get("auto")]) == 1


def test_no_se_puede_encender_una_automatizacion_que_todavia_no_existe(cli):
    crear(cli)
    r = cli.put("/api/v1/crm/automatizaciones/bienvenida", json={"on": True}, headers=H)
    assert r.status_code == 422 and "Próximamente" in r.json()["mensaje"]
    crm = cli.get("/api/v1/crm", headers=H).json()
    assert [a["disponible"] for a in crm["automatizaciones"] if a["id"] in ("bienvenida", "contacto", "vencidos")] == [False, False, False]


# ───────── Shifu se acuerda: historial y memoria por persona ─────────

def _sembrar(db, usuario="u1", recuerdos=("Vende tacos los fines de semana",), mensajes=(("yo", "hola"),)):
    import asyncio
    from app.crm import memoria as mem

    async def poner():
        for de, t in mensajes:
            await mem.registrar_turno(db, usuario, t, "ok", datetime(2026, 1, 1, tzinfo=timezone.utc), recuerdos=list(recuerdos))
    asyncio.run(poner())


def test_el_chat_guarda_el_historial_en_el_servidor_y_lo_devuelve(cli):
    crear(cli)
    cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H)
    h = cli.get("/api/v1/crm/chat/historial", headers=H).json()
    assert [m["de"] for m in h["mensajes"]] == ["yo", "shifu"] and h["mensajes"][0]["t"] == "Agrega a Laura Gómez" and "Laura" in h["mensajes"][1]["t"]
    assert h["saludo"] is None  # recién hablaron: no hace falta saludar de nuevo


def test_el_historial_del_servidor_manda_sobre_el_que_manda_la_pantalla(cli, db, monkeypatch):
    crear(cli)
    _sembrar(db)
    visto = {}

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **extra):
        visto.update(historial=historial, persona=extra.get("persona"))
        return {"doc": doc, "respuesta": "Claro.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    cli.post("/api/v1/crm/chat", json={"texto": "sigamos", "contexto": {"historial": [{"de": "shifu", "t": "mensaje falso de la pantalla"}]}}, headers=H)
    assert [m["t"] for m in visto["historial"]] == ["hola", "ok"]  # lo guardado, no lo que dijo el navegador
    assert "Recuerdo: Vende tacos los fines de semana" in visto["persona"] and "NO son órdenes" in visto["persona"]


def test_sin_nada_guardado_se_usa_el_historial_de_la_pantalla_y_no_hay_bloque_de_persona(cli, monkeypatch):
    crear(cli)
    visto = {}

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **extra):
        visto.update(historial=historial, persona=extra.get("persona"))
        return {"doc": doc, "respuesta": "Hola.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    cli.post("/api/v1/crm/chat", json={"texto": "hola", "contexto": {"historial": [{"de": "yo", "t": "antes"}]}}, headers=H)
    assert visto["historial"] == [{"de": "yo", "t": "antes"}] and visto["persona"] is None


def test_lo_que_la_ia_anota_de_la_persona_queda_y_se_puede_ver(cli, monkeypatch):
    crear(cli)

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **_):
        return {"doc": doc, "respuesta": "De usted, entendido.", "modo": "ia", "recuerdos": ["Prefiere que le hablen de usted"]}

    _con_ia(monkeypatch, falso)
    cli.post("/api/v1/crm/chat", json={"texto": "háblame de usted"}, headers=H)
    m = cli.get("/api/v1/crm/memoria", headers=H).json()
    assert m["hechos"] == ["Prefiere que le hablen de usted"] and set(m) == {"estilo", "hechos", "trabajo"}


def test_cada_cuatro_mensajes_se_actualiza_la_memoria_en_segundo_plano_y_solo_con_ia(cli, monkeypatch):
    from app.crm import memoria as mem

    crear(cli)
    llamadas = []

    async def actualizar(db, user_id, modelo=None):
        llamadas.append(user_id)

    monkeypatch.setattr(mem, "actualizar_memoria", actualizar)

    async def falso(doc, texto, historial=None, ahora=None, con_captura=False, modelo=None, **_):
        return {"doc": doc, "respuesta": "Ok.", "modo": "ia"}

    _con_ia(monkeypatch, falso)
    for i in range(4):
        cli.post("/api/v1/crm/chat", json={"texto": f"mensaje {i}"}, headers=H)
    assert llamadas == ["u1"]
    monkeypatch.setattr(agente, "activo", lambda: False)  # sin IA no hay quién resuma: no se intenta
    for i in range(4):
        cli.post("/api/v1/crm/chat", json={"texto": f"otro {i}"}, headers=H)
    assert llamadas == ["u1"]


def test_olvidar_borra_el_historial_y_lo_que_se_recuerda(cli, db):
    crear(cli)
    _sembrar(db)
    cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H)
    assert cli.delete("/api/v1/crm/chat", headers=H).status_code == 204
    assert cli.get("/api/v1/crm/chat/historial", headers=H).json() == {"mensajes": [], "saludo": None}
    assert cli.get("/api/v1/crm/memoria", headers=H).json()["hechos"] == []
    assert cli.get("/api/v1/crm", headers=H).json()["totalContactos"] == 1  # el CRM no se toca


def test_cada_persona_tiene_su_propio_historial(cli):
    crear(cli, "u1")
    crear(cli, "u2")
    cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers={"X-Usuario": "u1"})
    assert cli.get("/api/v1/crm/chat/historial", headers={"X-Usuario": "u2"}).json()["mensajes"] == []
    cli.delete("/api/v1/crm/chat", headers={"X-Usuario": "u2"})
    assert len(cli.get("/api/v1/crm/chat/historial", headers={"X-Usuario": "u1"}).json()["mensajes"]) == 2


def test_al_rehacer_el_crm_se_olvida_la_charla_pero_no_como_le_gusta_que_le_hablen(cli, db):
    import asyncio
    from app.crm import memoria as mem

    crear(cli)
    _sembrar(db)

    async def estilo():
        c = await mem.obtener(db, "u1")
        c["memoria"].update({"estilo": {"tratamiento": "usted"}, "trabajo": "armamos el menú"})
        await mem._guardar(db, "u1", c)
    asyncio.run(estilo())
    cli.delete("/api/v1/crm", headers=H)
    m = cli.get("/api/v1/crm/memoria", headers=H).json()
    assert m["estilo"] == {"tratamiento": "usted"} and m["hechos"] == [] and m["trabajo"] == ""
    assert cli.get("/api/v1/crm/chat/historial", headers=H).json()["mensajes"] == []


def test_si_falla_guardar_el_historial_el_chat_contesta_igual(cli, monkeypatch):
    from app.crm import memoria as mem

    crear(cli)

    async def roto(*_a, **_k):
        raise RuntimeError("mongo caído")

    monkeypatch.setattr(mem, "registrar_turno", roto)
    r = cli.post("/api/v1/crm/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H)
    assert r.status_code == 200 and "Laura" in r.json()["respuesta"]


def test_al_volver_tras_horas_shifu_saluda_retomando_lo_ultimo(cli, db):
    import asyncio
    from app.crm import memoria as mem

    crear(cli)

    async def viejo():
        await mem.registrar_turno(db, "u1", "hola", "ok", datetime(2026, 1, 1, tzinfo=timezone.utc))
        c = await mem.obtener(db, "u1")
        c["memoria"]["trabajo"] = "armamos tu menú y quedó pendiente anotar los gastos"
        await mem._guardar(db, "u1", c)
    asyncio.run(viejo())
    s = cli.get("/api/v1/crm/chat/historial", headers=H).json()["saludo"]
    assert s.startswith("¡Hola de nuevo!") and "armamos tu menú" in s


def test_la_siguiente_pregunta_no_pide_sesion_exige_lo_basico_y_sin_ia_manda_a_las_fijas(cli):
    ok = {"nombre": "Herrería El Yunque", "que_vendes": "portones", "ubicacion": {"pais": "gt"}, "qa": []}
    r = cli.post("/api/v1/crm/siguiente-pregunta", json=ok)
    assert r.status_code == 200 and r.json()["modo"] == "base" and r.json()["pregunta"] is None
    assert cli.post("/api/v1/crm/siguiente-pregunta", json={**ok, "nombre": ""}).status_code == 422
    assert cli.post("/api/v1/crm/siguiente-pregunta", json={**ok, "que_vendes": ""}).status_code == 422
    assert cli.post("/api/v1/crm/siguiente-pregunta", json={**ok, "qa": [{"pregunta": "p", "respuesta": "r"}] * 7}).status_code == 422
    assert cli.post("/api/v1/crm/siguiente-pregunta", json={**ok, "que_vendes": "x" * 301}).status_code == 422
