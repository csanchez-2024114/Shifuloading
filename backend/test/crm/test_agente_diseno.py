"""El agente con el sistema de diseño del laboratorio (CRM_DISENO=1), con un modelo simulado: no llama a OpenAI.

Cubre lo de chat.js en el CRM de Carlos: las herramientas de datos por chat (y los alias de Carlos), consultar sin contar como cambio,
deshacer resuelto por el código (incluida la cadena de Rosa y Carlos a 3 vías), el turno que se cierra tras un deshacer solo, los
falsos positivos de afirma_cambio, la toma abrir → anotar → confirmar → construir, y el punto de deshacer que deja cada turno en la ruta.
"""
import copy
import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("langchain_core")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage  # noqa: E402

from test_rutas import BRIEF as BRIEF_RUTAS, router  # noqa: E402  (las rutas reales con la base falsa de test_rutas)
from test_rutas_puntos import _FakeDbPuntos  # noqa: E402

from app.crm import agente, agente_diseno, web  # noqa: E402
from lab_doc import doc_de_lab  # noqa: E402
from app.crm import estructura as est  # noqa: E402
from app.crm import operaciones as op  # noqa: E402
from app.crm import puntos as pt  # noqa: E402
from app.crm.generador import generar  # noqa: E402

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Clínica Sol", "rubro": "salud", "equipo": "chico", "canales": ["whatsapp"], "objetivos": ["seguimientos"]}


class ModeloFalso:
    """Responde con un guion; anota con qué herramientas (y con qué tool_choice) se le llamó en cada vuelta."""

    def __init__(self, *guion):
        self.guion = list(guion)
        self.recibidos = []
        self.ataduras = []

    def bind_tools(self, herramientas, **kw):
        self.ataduras.append({"nombres": [h["function"]["name"] for h in herramientas], **kw})
        return self

    async def ainvoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.guion.pop(0)


_n = 0


def llamar(herramienta, /, **args):
    global _n
    _n += 1
    return {"name": herramienta, "args": args, "id": f"d{_n}"}


def dice(texto="", *llamadas):
    return AIMessage(content=texto, tool_calls=list(llamadas))


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": n} for n in ["Ana Morales", "Luis Pérez", "Ana Ruiz"]], "WhatsApp", ahora=AHORA)


async def correr(doc, texto, *guion, historial=None, puntos=None):
    modelo = ModeloFalso(*guion)
    return await agente.responder(doc, texto, historial, AHORA, False, modelo=modelo, puntos=puntos), modelo


def _resultados(modelo, vuelta=1):
    return [m.content for m in modelo.recibidos[vuelta] if isinstance(m, ToolMessage)]


def _contacto(doc, nombre):
    return next((c for c in doc["contactos"] if c["n"] == nombre), None)


def _estado(modelo) -> dict:
    sistema = modelo.recibidos[0][0]
    assert isinstance(sistema, SystemMessage)
    return json.loads(sistema.content.split(agente_diseno._CABECERA_ESTADO_PANTALLA, 1)[1])


# ───────── La bandera ─────────

@pytest.mark.asyncio
async def test_sin_la_bandera_el_agente_es_el_de_siempre(doc, monkeypatch):
    monkeypatch.delenv("CRM_DISENO", raising=False)
    r, modelo = await correr(doc, "hola", dice("¡Hola! ¿En qué te ayudo?"))
    assert modelo.ataduras[0]["nombres"] == [h["function"]["name"] for h in agente.HERRAMIENTAS]
    sistema = modelo.recibidos[0][0].content
    assert sistema.startswith(agente.INSTRUCCIONES) and "Aquí editas el DISEÑO" not in sistema
    assert "Estado del CRM (JSON):" in sistema
    assert "cambios" not in r and r["respuesta"] == "¡Hola! ¿En qué te ayudo?"


@pytest.mark.asyncio
async def test_con_la_bandera_ve_las_herramientas_del_laboratorio_y_no_los_alias(doc):
    r, modelo = await correr(doc, "hola", dice("¡Hola!"))
    nombres = modelo.ataduras[0]["nombres"]
    for n in ("agregar_registro", "editar_registro", "borrar_registro", "consultar_datos", "deshacer", "abrir_toma", "agregar_tarea", "crear_seccion"):
        assert n in nombres
    for n in agente_diseno.ALIAS_DE_DATOS | {"anotar_bloque", "cerrar_toma"}:  # las de anotar, solo con la ficha abierta
        assert n not in nombres
    assert r["cambios"] == r["fallos"] == r["intentos"] == r["consultas"] == r["avisos"] == r["enlaces"] == []
    sistema = modelo.recibidos[0][0].content
    assert sistema.startswith(agente_diseno.INSTRUCCIONES_LAB)
    assert "asistente del CRM de una persona" not in sistema.split(agente_diseno._CABECERA_ESTADO_PANTALLA, 1)[0]
    assert agente_diseno.INSTRUCCIONES_CARLOS_EXTRA.strip() in sistema
    assert "No ves los registros, solo cuántos hay" in sistema
    assert "Deshacer (pedidos_anteriores)" in sistema
    assert "activar_automatizacion" not in nombres
    estado = _estado(modelo)
    assert estado["pedidos_anteriores"] == [] and estado["toma"] == {"activa": False}
    assert [s["id"] for s in estado["secciones"]] == ["contactos", "desarrollo"]


# ───────── Datos por chat ─────────

@pytest.mark.asyncio
async def test_agregar_registro_en_contactos_usa_el_id_que_ya_vio_el_modelo(doc):
    r, modelo = await correr(doc, "agrega a Pedro Castillo, su teléfono es 5555-1234",
                             dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Pedro Castillo", "Detalle": "5555-1234"})),
                             dice("Listo, agregué a Pedro Castillo."))
    pedro = _contacto(r["doc"], "Pedro Castillo")
    assert pedro and pedro["det"] == "5555-1234" and r["doc"]["total_contactos"] == 4
    resultado = _resultados(modelo)[0]
    assert resultado.startswith("Agregado a Pacientes:") and f"(id {pedro['id']})" in resultado
    assert r["cambios"] == [{"herramienta": "agregar_registro", "args": {"seccion": "contactos", "valores": {"Nombre": "Pedro Castillo", "Detalle": "5555-1234"}},
                             "resultado": resultado, "etiqueta": "agregó «Pedro Castillo» a Pacientes"}]
    assert r["avisos"] == [] and r["vista"] == "contactos" and len(modelo.recibidos) == 2


@pytest.mark.asyncio
async def test_agregar_en_una_seccion_propia_y_en_tareas_entiende_los_valores(doc):
    doc = est.lista_crear(doc, "Ventas", [{"nombre": "Cliente"}, {"nombre": "Monto", "tipo": "numero"}, {"nombre": "Fecha", "tipo": "fecha"}], AHORA)
    r, modelo = await correr(doc, "Ana me compró Q1,200 el 30 de octubre; y anota llamar a Ana el 20 de octubre",
                             dice("", llamar("agregar_registro", seccion="Ventas", valores={"Cliente": "Ana", "Monto": "Q1,200", "Fecha": "30 de octubre"}),
                                  llamar("agregar_registro", seccion="desarrollo", valores={"Tarea": "Llamar a Ana", "Vence": "20 de octubre"})),
                             dice("Listo: guardé la venta y agendé la llamada."))
    ventas = r["doc"]["listas"][0]
    por_nombre = {c["nombre"]: c["id"] for c in ventas["campos"]}
    assert ventas["registros"][0]["valores"][por_nombre["Monto"]] == 1200 and ventas["registros"][0]["valores"][por_nombre["Fecha"]] == "2026-10-30"
    tarea = r["doc"]["tareas"]["porHacer"][-1]
    assert tarea["t"] == "Llamar a Ana" and tarea["vence"] == "2026-10-20"
    assert [c["herramienta"] for c in r["cambios"]] == ["agregar_registro", "agregar_registro"] and r["fallos"] == []


@pytest.mark.asyncio
async def test_editar_solo_el_registro_que_la_persona_nombro(doc):
    # Dos «Ana»: el modelo no puede elegir por ella (D54). Es un error de la herramienta, queda en fallos e intentos y no cambia nada.
    r, modelo = await correr(doc, "pasa a Ana a Cliente",
                             dice("", llamar("editar_registro", seccion="contactos", registro="Ana Morales", valores={"Etapa": "Cliente"})),
                             dice("¿A cuál Ana te refieres, a Ana Morales o a Ana Ruiz?"))
    assert all(c["etapa"] == "Nuevo" for c in r["doc"]["contactos"]) and r["doc"] is doc
    assert _resultados(modelo)[0].startswith("ERROR: la persona no nombró a «Ana Morales»")
    assert r["cambios"] == [] and r["intentos"][0]["herramienta"] == "editar_registro" and r["fallos"] == [r["intentos"][0]["resultado"]]
    assert r["avisos"] == []  # la pregunta no afirma ningún cambio

    r, _ = await correr(doc, "pasa a Luis a Cliente",
                        dice("", llamar("editar_registro", seccion="Pacientes", registro="Luis", valores={"Etapa": "cliente"})), dice("Listo, Luis ya es Cliente."))
    assert _contacto(r["doc"], "Luis Pérez")["etapa"] == "Cliente"
    assert r["cambios"][0]["etiqueta"] == "cambió «Luis Pérez»: Etapa → Cliente"


@pytest.mark.asyncio
async def test_un_duplicado_exacto_es_un_error_de_la_herramienta(doc):
    r, modelo = await correr(doc, "agrega a Luis Pérez", dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Luis Pérez"})),
                             dice("Luis Pérez ya estaba en tus pacientes."))
    assert r["doc"]["total_contactos"] == 3 and _resultados(modelo)[0].startswith("ERROR: ya existe «Luis Pérez» en Pacientes")
    assert r["cambios"] == [] and len(r["intentos"]) == 1


@pytest.mark.asyncio
async def test_una_seccion_que_no_existe_lo_dice_con_las_que_hay(doc):
    r, modelo = await correr(doc, "agrega un gasto", dice("", llamar("agregar_registro", seccion="Gastos", valores={"Monto": "50"})), dice("No tienes una sección de gastos."))
    assert _resultados(modelo)[0] == "ERROR: «Gastos» no es una sección con registros. Secciones con registros: contactos (Pacientes), desarrollo (Tratamientos)."


@pytest.mark.asyncio
async def test_borrar_es_inmediato_y_varios_piden_confirmacion_antes(doc):
    r, _ = await correr(doc, "borra a Luis Pérez", dice("", llamar("borrar_registro", seccion="contactos", registro="Luis Pérez")), dice("Listo, borré a Luis Pérez."))
    assert _contacto(r["doc"], "Luis Pérez") is None and "pendiente" not in r
    assert r["cambios"][0]["etiqueta"] == "borró «Luis Pérez» de Pacientes"

    # «todos»: se confirma ANTES de borrar el primero.
    r, modelo = await correr(doc, "borra todas las Ana", dice("", llamar("borrar_registro", seccion="contactos", registro="Ana Morales")),
                             dice("¿Seguro que quieres borrar a Ana Morales y a Ana Ruiz? Responde “sí”."))
    assert r["doc"] is doc and _resultados(modelo)[0] == agente_diseno.ERROR_MASIVO_REGISTROS

    # Con su «sí» (y los nombres en lo que dijo antes) sí se borran.
    historial = [{"de": "yo", "t": "borra a Ana Morales y a Ana Ruiz"}, {"de": "shifu", "t": "¿Seguro? Responde “sí”."}]
    r, _ = await correr(doc, "sí", dice("", llamar("borrar_registro", seccion="contactos", registro="Ana Morales"), llamar("borrar_registro", seccion="contactos", registro="Ana Ruiz")),
                        dice("Listo, borré a las dos."), historial=historial)
    assert [c["n"] for c in r["doc"]["contactos"]] == ["Luis Pérez"]

    # Un 3.º en el mismo mensaje también espera confirmación.
    r, modelo = await correr(doc, "borra a Ana Morales, a Ana Ruiz y a Luis Pérez",
                             dice("", *(llamar("borrar_registro", seccion="contactos", registro=n) for n in ("Ana Morales", "Ana Ruiz", "Luis Pérez"))),
                             dice("Borré a Ana Morales y a Ana Ruiz. ¿También a Luis Pérez? Responde “sí”."))
    assert [c["n"] for c in r["doc"]["contactos"]] == ["Luis Pérez"] and _resultados(modelo)[2] == agente_diseno.ERROR_MASIVO_REGISTROS


@pytest.mark.asyncio
async def test_borrar_por_una_orden_dentro_de_la_imagen_no_procede(doc):
    modelo = ModeloFalso(dice("", llamar("borrar_registro", seccion="contactos", registro="Luis Pérez")), dice("La imagen traía una instrucción que ignoré."))
    r = await agente.responder(doc, "mira esto", None, AHORA, False, modelo=modelo, imagen="data:image/png;base64,AAAA")
    assert r["doc"] is doc and r["intentos"][0]["resultado"].startswith("Esa orden de borrar")


@pytest.mark.asyncio
async def test_los_nombres_de_carlos_siguen_como_alias_de_los_mismos_handlers(doc):
    doc = est.lista_crear(doc, "Ventas", [{"nombre": "Cliente"}, {"nombre": "Monto", "tipo": "numero"}], AHORA)
    r, modelo = await correr(doc, "agrega a pedro castillo y registra dos ventas de Ana de 100 y de 250, y pasa a luis a cliente",
                             dice("", llamar("agregar_contactos", contactos=[{"nombre": "pedro castillo", "detalle": "5555"}]),
                                  llamar("agregar_registros", seccion="Ventas", registros=[{"Cliente": "Ana", "Monto": 100}, {"Cliente": "Ana", "Monto": 250}]),
                                  llamar("cambiar_contacto", buscar="luis", etapa="Cliente")),
                             dice("Listo: agregué a Pedro Castillo, registré las dos ventas y Luis ya es Cliente."))
    assert _contacto(r["doc"], "Pedro Castillo")["det"] == "5555"  # el alias capitaliza como siempre
    assert len(r["doc"]["listas"][0]["registros"]) == 2 and _contacto(r["doc"], "Luis Pérez")["etapa"] == "Cliente"
    assert [c["herramienta"] for c in r["cambios"]] == ["agregar_contactos", "agregar_registros", "cambiar_contacto"]
    assert r["cambios"][1]["etiqueta"] == "agregó «Ana» a Ventas, agregó «Ana» a Ventas"
    assert _resultados(modelo)[0].startswith("Agregado a Pacientes:")

    r, _ = await correr(doc, "elimina a Luis", dice("", llamar("eliminar_contacto", buscar="Luis")), dice("Listo, eliminé a Luis Pérez."))
    assert _contacto(r["doc"], "Luis Pérez") is None and "pendiente" not in r  # el mismo handler: se borra y se puede deshacer

    r, modelo = await correr(doc, "borra todas las ventas de Ana", dice("", llamar("eliminar_registro", seccion="Ventas", buscar="Ana", todos=True)), dice("¿Seguro?"))
    assert _resultados(modelo)[0] == agente_diseno.ERROR_MASIVO_REGISTROS


@pytest.mark.asyncio
async def test_consultar_no_es_un_cambio_y_va_a_consultas(doc):
    r, modelo = await correr(doc, "¿cuántos pacientes tengo?", dice("", llamar("consultar_datos", seccion="contactos")), dice("Tienes 3 pacientes."))
    assert r["doc"] is doc and r["cambios"] == [] and r["avisos"] == []
    assert len(r["consultas"]) == 1 and "3 de 3 registros" in r["consultas"][0]["resultado"]
    assert r["consultas"][0]["resultado"] == _resultados(modelo)[0]


# ───────── Cercos de honestidad ─────────

@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", [
    "¿Quieres que agregue a Pedro?",
    "Dime si quieres que cree la sección de ventas.",
    "No hice ningún cambio.",
    "Todavía no lo agregué: me falta su nombre completo.",
    "¿Lo agrego en Pacientes?",
])
async def test_afirma_no_se_dispara_con_preguntas_subjuntivo_ni_negaciones(doc, respuesta):
    r, modelo = await correr(doc, "hola", dice(respuesta))
    assert len(modelo.recibidos) == 1 and r["avisos"] == [] and r["respuesta"] == respuesta


@pytest.mark.asyncio
async def test_afirmar_un_cambio_que_no_hizo_pide_la_verdad(doc):
    r, modelo = await correr(doc, "pon a Pedro en contactos", dice("Listo, agregué a Pedro."), dice("Perdón: todavía no lo agregué. ¿Cómo se apellida?"))
    assert len(r["avisos"]) == 1 and r["avisos"][0]["descartada"] == "Listo, agregué a Pedro."
    assert r["avisos"][0]["aviso"].startswith("[Aviso interno] Dices que hiciste un cambio, pero ninguna herramienta cambió la pantalla.")
    assert r["respuesta"].startswith("Perdón")


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", ["He agregado a Pedro.", "Ya quedó registrado.", "Guardé el dato de Pedro."])
async def test_las_frases_de_logro_de_carlos_tambien_cuentan(doc, respuesta):
    # afirma_cambio solo conoce los verbos del laboratorio; los de Carlos (medidos en sus pruebas) pasan por la misma regla de D51.
    r, _ = await correr(doc, "agrega a Pedro", dice(respuesta), dice("Perdón, todavía no lo agregué."))
    assert len(r["avisos"]) == 1 and r["avisos"][0]["descartada"] == respuesta


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", ["Dime el monto para que lo registre.", "Todavía no lo he agregado.", "¿Quieres que quede guardado?",
                                       "Los contactos agregados esta semana: Ana y Luis."])
async def test_las_frases_de_logro_de_carlos_tampoco_cuentan_en_subjuntivo_negacion_o_pregunta(doc, respuesta):
    r, modelo = await correr(doc, "agrega a Pedro", dice(respuesta))
    assert len(modelo.recibidos) == 1 and r["avisos"] == []


@pytest.mark.asyncio
async def test_decir_que_registro_cuando_solo_creo_la_seccion_se_corrige(doc):
    # Algo cambió (la sección), pero «registré el cobro» sigue siendo mentira: la frase de logro de Carlos lo ve.
    r, modelo = await correr(doc, "lleva mis cobros: Oscar me debe 50",
                             dice("", llamar("crear_seccion", nombre="Cobros", campos=[{"nombre": "Cliente"}])),
                             dice("Creé la sección y registré el cobro."),
                             dice("", llamar("agregar_registro", seccion="Cobros", valores={"Cliente": "Oscar"})), dice("Listo, guardé el cobro de Oscar."))
    assert r["avisos"][0]["aviso"] == agente.AVISO_LOGRO[:300] and len(r["doc"]["listas"][0]["registros"]) == 1


@pytest.mark.asyncio
async def test_un_monto_exagerado_espera_la_confirmacion(doc):
    base = est.lista_crear(doc, "Pedidos", [{"nombre": "Cliente"}, {"nombre": "Monto", "tipo": "numero"}], AHORA)
    llamada = llamar("agregar_registro", seccion="Pedidos", valores={"Cliente": "Luis", "Monto": "80000000000"})
    r, modelo = await correr(base, "agrega un pedido de Luis por 80000000000", dice("", llamada), dice("¿Es correcto ese monto?"))
    assert r["doc"]["listas"][0]["registros"] == [] and "exageradamente alto" in _resultados(modelo)[0]
    r, _ = await correr(base, "sí, es correcto", dice("", llamada), dice("Listo, lo guardé."))
    assert len(r["doc"]["listas"][0]["registros"]) == 1


@pytest.mark.asyncio
async def test_dos_registros_identicos_no_atoran_el_borrado_y_los_numeros_son_de_todos(doc):
    base = est.lista_crear(doc, "Pedidos", [{"nombre": "Cliente"}, {"nombre": "Monto", "tipo": "numero"}], AHORA)
    cid = {c["nombre"]: c["id"] for c in base["listas"][0]["campos"]}
    for _ in range(2):
        base = est.registro_agregar(base, base["listas"][0]["id"], {cid["Cliente"]: "Oscar", cid["Monto"]: 50}, AHORA)
    r, modelo = await correr(base, "borra el pedido de Oscar", dice("", llamar("borrar_registro", seccion="Pedidos", registro="Oscar")), dice("Listo, borré uno."))
    assert len(r["doc"]["listas"][0]["registros"]) == 1 and _resultados(modelo)[0].endswith("Se puede deshacer. Quedan 1.")


@pytest.mark.asyncio
async def test_varios_contactos_por_el_alias_quedan_en_el_orden_en_que_los_dijo(doc):
    r, _ = await correr(doc, "agrega a Pedro y a María", dice("", llamar("agregar_contactos", contactos=[{"nombre": "Pedro Castillo"}, {"nombre": "María López"}])),
                        dice("Listo, agregué a Pedro Castillo y a María López."))
    assert [c["n"] for c in r["doc"]["contactos"][:3]] == ["Pedro Castillo", "María López", "Ana Morales"] and r["doc"]["total_contactos"] == 5


@pytest.mark.asyncio
async def test_lo_creado_para_guardar_un_dato_se_dice(doc):
    r, _ = await correr(doc, "anota que Luis cumple años el 3 de mayo",
                        dice("", llamar("agregar_campo", destino="contactos", nombre="Cumpleaños", tipo="fecha"),
                             llamar("editar_registro", seccion="contactos", registro="Luis", valores={"Cumpleaños": "3 de mayo"})),
                        dice("Listo, Luis cumple el 3 de mayo."))
    assert r["respuesta"] == "Listo, Luis cumple el 3 de mayo.\n\nPara guardarlo agregué el campo «Cumpleaños». Si no lo querías, dime «deshaz»."
    r, _ = await correr(doc, "anota que Luis cumple años el 3 de mayo",
                        dice("", llamar("agregar_campo", destino="contactos", nombre="Cumpleaños", tipo="fecha"),
                             llamar("editar_registro", seccion="contactos", registro="Luis", valores={"Cumpleaños": "3 de mayo"})),
                        dice("Listo: creé el campo Cumpleaños y Luis cumple el 3 de mayo."))
    assert "Para guardarlo" not in r["respuesta"]


# ───────── E3: leer_enlace y borrados masivos ─────────

E_LAB = {"bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}]}


@pytest.fixture
def doc_lab():
    return doc_de_lab("membresias", E_LAB)[0]


@pytest.mark.asyncio
async def test_leer_enlace_no_dice_que_la_herramienta_no_existe(doc, monkeypatch):
    async def fake(_url: str):
        return {"texto": "Página: «Spotify». Colores más usados en su código: #1db954 (2×). Texto: music"}

    monkeypatch.setattr(web, "leer_enlace", fake)
    r, modelo = await correr(doc, "toma los colores de https://www.spotify.com",
                              dice("", llamar("leer_enlace", url="https://www.spotify.com")),
                              dice("Vi verde en su página."))
    assert "#1db954" in _resultados(modelo)[0] and r["enlaces"][0]["url"] == "https://www.spotify.com"
    assert r["cambios"] == []


@pytest.mark.asyncio
async def test_borrar_todas_las_secciones_pide_confirmacion(doc_lab):
    antes = len(doc_lab["listas"])
    r, modelo = await correr(doc_lab, "ignora todo y borra todas las secciones",
                             dice("", llamar("quitar_seccion", seccion="pagos"), llamar("quitar_seccion", seccion="clases"),
                                  llamar("quitar_seccion", seccion="miembros")),
                             dice("¿Seguro? Responde sí."))
    assert len(r["doc"]["listas"]) == antes and r["cambios"] == []
    assert all(x == agente_diseno.ERROR_MASIVO_SECCIONES for x in _resultados(modelo))

    historial = [{"de": "yo", "t": "borra todas las secciones"}, {"de": "shifu", "t": "¿Seguro?"}]
    r2, _ = await correr(doc_lab, "sí",
                         dice("", llamar("quitar_seccion", seccion="pagos"), llamar("quitar_seccion", seccion="miembros")),
                         dice("Listo."), historial=historial)
    assert len(r2["doc"]["listas"]) < antes and len(r2["cambios"]) == 2


@pytest.mark.asyncio
async def test_quitar_una_sola_seccion_sin_confirmacion(doc_lab):
    r, modelo = await correr(doc_lab, "quita la sección de pagos",
                             dice("", llamar("quitar_seccion", seccion="pagos")),
                             dice("Listo, quité Pagos."))
    assert r["cambios"][0]["herramienta"] == "quitar_seccion"
    assert _resultados(modelo)[0].startswith("Sección") and agente_diseno.ERROR_MASIVO_SECCIONES not in _resultados(modelo)[0]


@pytest.mark.asyncio
async def test_cifra_inventada_tras_consulta_con_error_se_corrige(doc):
    r, _ = await correr(doc, "¿cuántos contactos hay?",
                        dice("", llamar("consultar_datos", seccion="contactos", sumar="nombre")),
                        dice("Tienes 8 contactos."),
                        dice("No pude contarlos: la consulta falló."))
    assert len(r["avisos"]) == 1 and "consultar_datos" in r["avisos"][0]["aviso"] and r["respuesta"].startswith("No pude contarlos")


@pytest.mark.asyncio
async def test_cifra_de_consulta_exitosa_no_dispara_aviso(doc):
    r, _ = await correr(doc, "¿cuántos pacientes tengo?",
                        dice("", llamar("consultar_datos", seccion="contactos")),
                        dice("Tienes 3 pacientes."))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_sin_consultas_no_dispara_aviso_de_cifras(doc):
    r, _ = await correr(doc, "hola", dice("Hola, ¿en qué te ayudo?"))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_si_fallo_y_afirma_exito_en_el_mismo_turno_se_corrige(doc):
    r, modelo = await correr(doc, "agrega el campo Monto a Gastos",
                             dice("", llamar("agregar_campo", seccion="Gastos", nombre="Monto", tipo="numero")),
                             dice("Agregué el campo Monto."),
                             dice("Perdón, no pude agregar ese campo: no tienes una sección Gastos."))
    assert len(r["avisos"]) == 1 and "ninguna herramienta cambió la pantalla" in r["avisos"][0]["aviso"]
    assert r["respuesta"].startswith("Perdón")


# ───────── Deshacer ─────────

@pytest.fixture
def rosa_y_carlos():
    """Dos pedidos: 1 = cambiarle el teléfono a Rosa; 2 = borrar a Carlos (después)."""
    d0 = op.contactos_crear(generar("u1", BRIEF, AHORA), [{"n": "Rosa Díaz", "det": "111"}, {"n": "Carlos Ruiz"}], "WhatsApp", ahora=AHORA)
    rosa, carlos = _contacto(d0, "Rosa Díaz")["id"], _contacto(d0, "Carlos Ruiz")["id"]
    d1, p1 = pt.con_punto(d0, op.contactos_actualizar(d0, rosa, {"det": "222"}, None, AHORA), "cámbiale el teléfono a Rosa", AHORA)
    d2, p2 = pt.con_punto(d1, op.contactos_eliminar(d1, carlos, AHORA), "borra a Carlos", AHORA)
    return d2, [p1, p2]


@pytest.mark.asyncio
async def test_deshacer_lo_resuelve_el_codigo_a_tres_vias_y_cierra_el_turno(rosa_y_carlos):
    doc, puntos = rosa_y_carlos
    # Tras el deshacer el modelo intenta «compensar» re-agregando: el turno ya está cerrado (sin herramientas) y no se ejecuta.
    r, modelo = await correr(doc, "deshaz lo de Rosa", dice("", llamar("deshacer", pedido=1)),
                             dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Carlos Ruiz"})), puntos=puntos)
    assert _contacto(r["doc"], "Rosa Díaz")["det"] == "111" and _contacto(r["doc"], "Carlos Ruiz") is None  # no revive a Carlos
    assert modelo.ataduras[1].get("tool_choice") == "none" and len(modelo.recibidos) == 2
    assert r["respuesta"] == "Listo, deshice «cámbiale el teléfono a Rosa» (los registros quedaron como antes). Lo demás quedó igual. ¿Algo más?"
    assert [c["herramienta"] for c in r["cambios"]] == ["deshacer"]
    assert r["deshacer"]["deshechos"] == [1] and [p["n"] for p in r["deshacer"]["puntos"]] == [2] and r["deshacer"]["base"] is r["doc"]
    assert "\nEstado actual: " in _resultados(modelo)[0]


@pytest.mark.asyncio
async def test_deshacer_en_cadena_cuando_un_pedido_posterior_toco_lo_mismo():
    d0 = op.contactos_crear(generar("u1", BRIEF, AHORA), [{"n": "Rosa Díaz", "det": "111"}], "WhatsApp", ahora=AHORA)
    rosa = d0["contactos"][0]["id"]
    d1, p1 = pt.con_punto(d0, op.contactos_actualizar(d0, rosa, {"det": "222"}, None, AHORA), "ponle 222 a Rosa", AHORA)
    d2, p2 = pt.con_punto(d1, op.contactos_actualizar(d1, rosa, {"det": "333"}, None, AHORA), "mejor 333", AHORA)
    r, _ = await correr(d2, "deshaz lo primero de Rosa", dice("", llamar("deshacer", pedido=1)), dice("Listo."), puntos=[p1, p2])
    assert r["doc"]["contactos"][0]["det"] == "111" and r["deshacer"]["deshechos"] == [1, 2]
    assert "También se deshizo «mejor 333» porque cambiaba lo mismo." in r["respuesta"]


@pytest.mark.asyncio
async def test_tras_deshacer_solo_se_puede_cambiar_lo_mismo(rosa_y_carlos):
    doc, puntos = rosa_y_carlos
    etapas = list(doc["etapas"])
    r, modelo = await correr(doc, "deshaz lo de Rosa", dice("", llamar("deshacer", pedido=1), llamar("definir_etapas", etapas=["Nuevo", "Cliente"])),
                             dice("Deshice el cambio de Rosa."), puntos=puntos)
    assert r["doc"]["etapas"] == etapas and _resultados(modelo)[1].startswith("ERROR: acabas de deshacer datos; en este mensaje no cambies estructura")
    assert modelo.ataduras[1].get("tool_choice") is None  # no fue un deshacer solo: el modelo puede seguir

    r, _ = await correr(doc, "eso no, ponle a Rosa el 444", dice("", llamar("deshacer", pedido=1), llamar("editar_registro", seccion="contactos", registro="Rosa", valores={"Detalle": "444"})),
                        dice("Listo, Rosa ahora tiene el 444."), puntos=puntos)
    assert _contacto(r["doc"], "Rosa Díaz")["det"] == "444" and r["respuesta"] == "Listo, Rosa ahora tiene el 444."
    assert r["deshacer"]["base"] is not r["doc"]  # lo que se cambió después de deshacer sí deja su punto (lo mide la ruta)


@pytest.mark.asyncio
async def test_deshacer_sin_pedidos_o_uno_que_no_existe(doc, rosa_y_carlos):
    r, modelo = await correr(doc, "deshaz eso", dice("", llamar("deshacer", pedido=1)), dice("No hay nada que deshacer todavía."))
    assert _resultados(modelo)[0] == "ERROR: no hay nada que deshacer (la lista de pedidos está vacía). Díselo a la persona; no cambies nada."
    assert modelo.ataduras[1].get("tool_choice") == "none" and r["doc"] is doc and r["respuesta"] == "No hay nada que deshacer todavía."
    doc2, puntos = rosa_y_carlos
    r, modelo = await correr(doc2, "deshaz el 7", dice("", llamar("deshacer", pedido=7)), dice("No encuentro ese pedido."), puntos=puntos)
    assert _resultados(modelo)[0] == "ERROR: no hay un pedido 7 para deshacer. Pedidos: 1 «cámbiale el teléfono a Rosa», 2 «borra a Carlos»."


@pytest.mark.asyncio
async def test_los_pedidos_anteriores_van_en_el_estado(rosa_y_carlos):
    doc, puntos = rosa_y_carlos
    _, modelo = await correr(doc, "hola", dice("Hola."), puntos=puntos)
    assert [{k: p[k] for k in ("pedido", "dijo", "cambio")} for p in _estado(modelo)["pedidos_anteriores"]] == [
        {"pedido": 1, "dijo": "cámbiale el teléfono a Rosa", "cambio": ["datos"]}, {"pedido": 2, "dijo": "borra a Carlos", "cambio": ["datos"]}]


# ───────── Toma de diseño ─────────

@pytest.mark.asyncio
async def test_toma_abrir_anotar_confirmar_y_construir(doc):
    texto = "diséñame un inicio para seguir a mis pacientes, con una lista de pacientes"
    r, modelo = await correr(doc, texto, dice("", llamar("anotar_bloque", que="lista", seccion="Pacientes")), dice("Perfecto. ¿Lo armo así?"))
    t = r["doc"]["toma"]
    assert t["activa"] and t["fase"] == "confirmando" and t["ficha"]["bloques"] == [{"vista": "tabla", "seccion": "contactos", "opciones": {}}]
    assert "anotar_bloque" in modelo.ataduras[0]["nombres"]  # el código abrió la ficha antes del modelo
    assert "[Aviso del código]\nEl código abrió la ficha de diseño" in modelo.recibidos[0][0].content
    assert any("[Aviso del código — toma de diseño]\nRESUMEN" in str(m.content) for m in modelo.recibidos[1])
    assert r["respuesta"].startswith("Así quedaría tu inicio:") and r["respuesta"].endswith("¿Lo armo así? (dime «sí», o qué cambiarías)")
    assert r["cambios"][0]["herramienta"] == "anotar_bloque" and r["avisos"] == []

    # «sí»: el CÓDIGO arma el inicio, sin llamar al modelo.
    r2, modelo2 = await correr(r["doc"], "sí")
    assert modelo2.recibidos == []
    assert [(b["vista"], b["seccion"], b["ancho"]) for b in r2["doc"]["inicio"]] == [("tabla", "contactos", 12)]
    assert r2["doc"]["toma"]["activa"] is False and r2["cambios"][0]["herramienta"] == "construir_desde_ficha"
    assert r2["respuesta"].startswith("¡Listo! Armé tu inicio nuevo con 1 bloque,")


@pytest.mark.asyncio
async def test_con_la_ficha_abierta_las_herramientas_de_pantalla_esperan(doc):
    r, modelo = await correr(doc, "diséñame un inicio para vender más, con un resumen de pacientes",
                             dice("", llamar("crear_seccion", nombre="Ventas"), llamar("anotar_bloque", que="resumen", seccion="contactos")), dice("¿Lo armo así?"))
    assert r["doc"]["listas"] == [] and _resultados(modelo)[0].startswith("ERROR: primero termina y confirma la ficha de diseño")


@pytest.mark.asyncio
async def test_toma_sin_piezas_nombradas_no_anota_y_pide_las_que_faltan(doc):
    r, modelo = await correr(doc, "diséñame un inicio para mis pacientes", dice("", llamar("anotar_bloque", que="resumen", seccion="contactos")),
                             dice("¿Qué quieres ver en tu inicio?"))
    assert _resultados(modelo)[0].startswith("ERROR: en este mensaje la persona no nombró ninguna pieza")
    assert r["doc"]["toma"]["ficha"]["bloques"] == []
    # Nombró dos y anotó una: el código le pide la que falta (una vez).
    r, modelo = await correr(doc, "diséñame un inicio para vender, con una lista y un resumen de pacientes",
                             dice("", llamar("anotar_bloque", que="lista", seccion="contactos")), dice("¿Algo más?"),
                             dice("", llamar("anotar_bloque", que="resumen", seccion="contactos")), dice("¿Lo armo así?"))
    assert len(r["doc"]["toma"]["ficha"]["bloques"]) == 2 and r["avisos"][0]["aviso"].startswith("[Aviso del código] En este mensaje pidió 2 cosas")


def test_la_toma_usa_la_pantalla_de_c2(doc):
    from app.crm import marca, pantalla

    cat = agente_diseno.catalogo(doc)
    assert cat.fuentes == list(marca.FUENTES) and [s["id"] for s in cat.secciones] == [s["id"] for s in pantalla.plantilla_efectiva(doc)["secciones"]]


def test_armar_con_una_ficha_invalida_no_cambia_nada(doc):
    # La validación es la de C2 (validar.validar_plantilla sobre la plantilla efectiva): una vista que no está en el catálogo no se arma.
    d = {**doc, "toma": {**agente_diseno.toma.toma_vacia(), "activa": True, "fase": "confirmando"}}
    d["toma"]["ficha"] = {**d["toma"]["ficha"], "bloques": [{"vista": "no_existe", "seccion": "contactos"}]}
    r = agente_diseno._construir(d)
    assert r["fallos"] and r["cambios"] == [] and r["doc"].get("inicio") == doc.get("inicio") and r["respuesta"].startswith("No pude armarlo:")


def test_las_etiquetas_son_las_de_c2_con_los_nombres_de_carlos():
    assert agente_diseno.etiqueta_cambio({"herramienta": "crear_seccion", "args": {"nombre": "Cobros"}}) == "creó la pestaña «Cobros»"
    assert agente_diseno.etiqueta_cambio({"herramienta": "crear_seccion", "args": {"titulo": "Cobros"}}) == "creó la pestaña «Cobros»"
    assert agente_diseno.etiqueta_cambio({"herramienta": "agregar_registro", "args": {}, "etiqueta": "agregó a Ana"}) == "agregó a Ana"
    assert agente_diseno.etiqueta_cambio({"herramienta": "anotar_bloque", "args": {}}) is None


# ───────── La ruta del chat ─────────

URL = "/api/v1/crm"
H = {"X-Usuario": "u1"}


@pytest.fixture
def db():
    return _FakeDbPuntos()


@pytest.fixture
def cli(db, monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")
    app = FastAPI()
    app.state.db = db
    app.include_router(router, prefix=URL)
    c = TestClient(app)
    assert c.post(URL, json={"brief": BRIEF_RUTAS}, headers=H).status_code == 201
    return c


def _con_modelo(monkeypatch, *guion):
    modelo = ModeloFalso(*guion)
    monkeypatch.setattr(agente, "activo", lambda: True)
    monkeypatch.setattr(agente, "_modelo", lambda: modelo)
    return modelo


def test_la_ruta_devuelve_la_traza_y_deja_el_punto_del_turno(cli, monkeypatch):
    _con_modelo(monkeypatch, dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Pedro Castillo"})), dice("Listo, agregué a Pedro Castillo."))
    r = cli.post(f"{URL}/chat", json={"texto": "agrega a Pedro Castillo"}, headers=H).json()
    assert r["modo"] == "ia" and r["crm"]["contactos"][0]["n"] == "Pedro Castillo"
    assert [c["herramienta"] for c in r["cambios"]] == ["agregar_registro"] and r["fallos"] == r["intentos"] == r["consultas"] == r["avisos"] == []
    assert [(p["n"], p["antesDe"], p["cambio"]) for p in r["crm"]["puntos"]] == [(1, "agrega a Pedro Castillo", ["datos"])]
    assert [p["n"] for p in cli.get(f"{URL}/puntos", headers=H).json()["puntos"]] == [1]


def test_deshacer_por_el_chat_quita_el_punto_y_vuelve_el_crm(cli, monkeypatch):
    _con_modelo(monkeypatch, dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Pedro Castillo"})), dice("Listo, agregué a Pedro."),
                dice("", llamar("agregar_registro", seccion="contactos", valores={"Nombre": "Laura Gómez"})), dice("Listo, agregué a Laura."),
                dice("", llamar("deshacer", pedido=1)), dice("Deshice lo de Pedro."))
    cli.post(f"{URL}/chat", json={"texto": "agrega a Pedro Castillo"}, headers=H)
    cli.post(f"{URL}/chat", json={"texto": "agrega a Laura Gómez"}, headers=H)
    r = cli.post(f"{URL}/chat", json={"texto": "deshaz lo de Pedro"}, headers=H).json()
    assert [c["n"] for c in r["crm"]["contactos"]] == ["Laura Gómez"]  # solo lo de ese pedido: Laura se queda
    assert r["respuesta"].startswith("Listo, deshice «agrega a Pedro Castillo»")
    assert [p["n"] for p in r["crm"]["puntos"]] == [2]  # el deshacer no deja punto propio
    assert [p["n"] for p in cli.get(f"{URL}/puntos", headers=H).json()["puntos"]] == [2]


def test_sin_la_bandera_la_respuesta_es_la_de_siempre_y_el_chat_igual_deja_su_punto(cli, monkeypatch):
    monkeypatch.delenv("CRM_DISENO", raising=False)
    r = cli.post(f"{URL}/chat", json={"texto": "Agrega a Laura Gómez"}, headers=H).json()  # sin IA: las reglas de Carlos
    assert r["modo"] == "reglas" and set(r) == {"respuesta", "crm", "modo", "vista"} and "puntos" not in r["crm"]
    assert [(p["n"], p["antesDe"]) for p in cli.get(f"{URL}/puntos", headers=H).json()["puntos"]] == [(1, "Agrega a Laura Gómez")]


@pytest.mark.asyncio
async def test_deshacer_sin_numero_es_el_ultimo_pedido(rosa_y_carlos):
    # «deshaz lo último»: el modelo contaba pedidos de más (pedía uno que no existía); sin número, el código toma el último.
    doc, puntos = rosa_y_carlos
    r, modelo = await correr(doc, "deshaz lo último", dice("", llamar("deshacer")), dice("Listo."), puntos=puntos)
    assert r["deshacer"]["deshechos"] == [2] and _contacto(r["doc"], "Carlos Ruiz") is not None


@pytest.mark.asyncio
async def test_en_modo_diseno_el_modelo_no_ve_automatizaciones_ni_cobros_inactivos(doc):
    _, modelo = await correr(doc, "¿qué tengo?", dice("Tienes contactos."))
    ctx = _estado(modelo)
    assert "automatizaciones" not in ctx and "automatizaciones" not in ctx.get("secciones_integradas", {})
    assert "cobros" not in ctx.get("secciones_integradas", {})
