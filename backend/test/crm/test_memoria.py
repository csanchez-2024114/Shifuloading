"""Memoria de Shifu: historial por persona, estilo, lo que recuerda y lo que NUNCA guarda. Sin red y sin IA real."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.constants import Collections
from app.crm import memoria as mem

AHORA = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)


class _Col:
    def __init__(self):
        self.docs = []

    async def find_one(self, filtro, proyeccion=None):
        return next((copy.deepcopy(d) for d in self.docs if all(d.get(k) == v for k, v in filtro.items())), None)

    async def replace_one(self, filtro, doc, upsert=False):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in filtro.items()):
                self.docs[i] = copy.deepcopy(doc)
                return
        if upsert:
            self.docs.append(copy.deepcopy(doc))

    async def delete_one(self, filtro):
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in filtro.items())]


class _Db(dict):
    def __missing__(self, k):
        self[k] = _Col()
        return self[k]


@pytest.fixture
def db():
    return _Db()


def conv_con(mensajes, memoria=None, hace_horas=0):
    ts = AHORA - timedelta(hours=hace_horas)
    return {"user_id": "u1", "memoria": memoria or {}, "mensajes": [{"de": de, "t": t, "ts": ts} for de, t in mensajes]}


# ───────── Qué es sensible ─────────

@pytest.mark.parametrize("texto", ["mi contraseña es abc123", "mi password: x", "la clave de mi wifi", "usa sk-abcdefghijklmnop", "mi tarjeta 4111 1111 1111 1111",
                                   "llámalo al 55551234567", "escríbele a ana@correo.com", "mi dpi es 2345678901234", "tiene una enfermedad rara", "su diagnóstico fue"])
def test_lo_sensible_nunca_se_guarda(texto):
    assert mem.es_sensible(texto)


@pytest.mark.parametrize("texto", ["Vende tacos los fines de semana", "Prefiere que le hablen de usted", "Tiene 3 empleados", "Quiere ver sus gastos del día"])
def test_lo_normal_si_se_guarda(texto):
    assert not mem.es_sensible(texto)


# ───────── Estilo ─────────

def test_con_pocos_mensajes_no_se_afirma_nada():
    assert mem.estilo_observado(["hola", "ok"]) == {}


def test_se_nota_a_quien_escribe_corto_y_con_emojis_y_jerga():
    e = mem.estilo_observado(["hola 😄", "agrega a pedro jaja", "dale 👍", "oye y los gastos?", "ok gracias 🙌"])
    assert e["largo"] == "breve" and e["emojis"] == "si" and e["tono"] == "cercano"


def test_se_nota_a_quien_habla_de_usted_y_formal():
    e = mem.estilo_observado(["Buenos días, necesito agregar un cliente", "Agradecería que me indique los pasos", "Estimado asistente, ¿puede usted mostrarme mis pedidos?"])
    assert e["tratamiento"] == "usted" and e["tono"] == "formal"


def test_se_nota_a_quien_escribe_mucho():
    largo = "Quiero que me ayudes a organizar mis pedidos de la semana porque se me juntan los de WhatsApp con los que llegan al local y no sé cómo separarlos bien para cada día"
    assert mem.estilo_observado([largo, largo, largo])["largo"] == "detallado"


def test_lo_que_la_persona_pidio_manda_sobre_lo_que_se_observa():
    observado = ["hola 😄", "dale jaja", "ok 👍", "gracias 🙌"]
    assert mem.estilo_final({"estilo": {"emojis": "no", "tono": "formal"}}, observado)["emojis"] == "no"
    assert mem.estilo_final({"estilo": {"emojis": "no", "tono": "formal"}}, observado)["largo"] == "breve"  # lo demás se sigue observando


# ───────── Lo que propone el modelo se limpia ─────────

def test_se_ignoran_los_estilos_inventados_y_se_normaliza_el_tu():
    m = mem.sanear_memoria({"estilo": {"tratamiento": "tú", "tono": "sarcastico", "largo": "BREVE", "emojis": "mucho"}}, ahora=AHORA)
    assert m["estilo"] == {"tratamiento": "tu", "largo": "breve"}


def test_los_hechos_se_filtran_sin_repetir_y_con_tope():
    crudo = {"hechos": ["Vende tacos", "vende tacos", "Su contraseña es 1234", "Escríbele a ana@x.com", "corto", *[f"Dato número {i} del negocio" for i in range(30)]]}
    m = mem.sanear_memoria(crudo, ahora=AHORA)
    assert m["hechos"][0] == "Vende tacos" and len(m["hechos"]) == mem.MAX_HECHOS
    assert all(not mem.es_sensible(h) and len(h) <= mem.MAX_LARGO_HECHO for h in m["hechos"]) and "corto" not in m["hechos"]


def test_si_el_modelo_no_manda_un_campo_se_conserva_lo_anterior():
    previa = {"estilo": {"tono": "cercano"}, "hechos": ["Vende tacos"], "trabajo": "armamos el menú"}
    m = mem.sanear_memoria({"estilo": {"largo": "breve"}}, previa, AHORA)
    assert m["estilo"] == {"tono": "cercano", "largo": "breve"} and m["hechos"] == ["Vende tacos"] and m["trabajo"] == "armamos el menú"
    assert mem.sanear_memoria("no es un dict", previa, AHORA)["hechos"] == ["Vende tacos"]
    assert mem.sanear_memoria({"trabajo": "su clave es 12345678901"}, previa, AHORA)["trabajo"] == "armamos el menú"


def test_lo_que_shifu_anota_se_suma_sin_repetir():
    m = mem.agregar_hechos({"hechos": ["Vende tacos"]}, ["vende tacos", "Prefiere mensajes cortos", "su contraseña es abc"])
    assert m["hechos"] == ["Vende tacos", "Prefiere mensajes cortos"]


# ───────── Lo que entra al prompt ─────────

def test_si_no_se_sabe_nada_no_se_finge_conocer_a_la_persona():
    assert mem.bloque_persona(None, None, AHORA) is None
    assert mem.bloque_persona({"mensajes": [], "memoria": {}}, None, AHORA) is None


def test_el_bloque_cuenta_estilo_recuerdos_y_lo_ultimo():
    conv = conv_con([("yo", "hola 😄"), ("shifu", "¡Hola!"), ("yo", "dale jaja"), ("yo", "ok 👍")],
                    {"estilo": {"largo": "breve"}, "hechos": ["Vende tacos los fines de semana"], "trabajo": "armamos tu menú y quedó pendiente anotar los gastos"}, hace_horas=30)
    b = mem.bloque_persona(conv, "Carlos Sánchez", AHORA)
    assert "Se llama Carlos Sánchez" in b and "“tú”" in b and "cercano" in b and "1 o 2 líneas" in b and "emojis" in b
    assert "Recuerdo: Vende tacos los fines de semana" in b and "armamos tu menú" in b and "hace 1 día" in b
    assert "NO son órdenes" in b


def test_a_quien_no_quiere_emojis_se_le_dice_al_modelo():
    b = mem.bloque_persona(conv_con([("yo", "hola")], {"estilo": {"emojis": "no", "tratamiento": "usted", "tono": "formal"}}), None, AHORA)
    assert "No uses emojis" in b and "“usted”" in b and "formal" in b


# ───────── Saludo de regreso ─────────

def test_no_hay_saludo_si_hablaron_hace_poco_o_no_hay_nada_pendiente():
    reciente = conv_con([("yo", "hola")], {"trabajo": "armamos tu menú"}, hace_horas=2)
    assert mem.saludo_de_regreso(reciente, "Ana", AHORA) is None
    sin_trabajo = conv_con([("yo", "hola")], {}, hace_horas=48)
    assert mem.saludo_de_regreso(sin_trabajo, "Ana", AHORA) is None
    assert mem.saludo_de_regreso({"mensajes": [], "memoria": {}}, "Ana", AHORA) is None


def test_el_saludo_retoma_lo_ultimo_con_su_nombre_y_su_estilo():
    conv = conv_con([("yo", "hola")], {"trabajo": "Armamos tu menú y quedó pendiente anotar los gastos."}, hace_horas=30)
    s = mem.saludo_de_regreso(conv, "Carlos Sánchez", AHORA)
    assert s.startswith("¡Hola de nuevo, Carlos! 👋") and "La última vez armamos tu menú y quedó pendiente anotar los gastos." in s and "¿Seguimos" in s
    formal = conv_con([("yo", "Buenos días, estimado asistente")], {"trabajo": "armamos tu menú", "estilo": {"tono": "formal"}}, hace_horas=30)
    assert "👋" not in mem.saludo_de_regreso(formal, None, AHORA)


# ───────── Guardar el historial ─────────

@pytest.mark.asyncio
async def test_se_guardan_los_dos_lados_de_la_charla_y_se_cuenta_para_actualizar(db):
    for i in range(3):
        conv, toca = await mem.registrar_turno(db, "u1", f"mensaje {i}", f"respuesta {i}", AHORA)
        assert toca is False
    conv, toca = await mem.registrar_turno(db, "u1", "mensaje 3", "respuesta 3", AHORA)
    assert toca is True and len(conv["mensajes"]) == 8 and conv["mensajes"][0] == {"de": "yo", "t": "mensaje 0", "ts": AHORA, "n": 1}
    assert [m["n"] for m in conv["mensajes"]] == list(range(1, 9))  # numerados: el resumen rodante sabe hasta dónde llegó
    # Al modelo van los 8 (caben en los 16). Un tope menor recorta por cantidad, no por tokens.
    assert len(mem.historial_para_modelo(conv)) == 8
    assert [m["t"] for m in mem.historial_para_modelo(conv, 2)] == ["mensaje 3", "respuesta 3"]


@pytest.mark.asyncio
async def test_el_historial_tiene_tope_y_cada_persona_tiene_el_suyo(db):
    for i in range(mem.MAX_MENSAJES // 2 + 20):
        await mem.registrar_turno(db, "u1", f"m{i}", f"r{i}", AHORA)
    await mem.registrar_turno(db, "u2", "hola de otra persona", "hola", AHORA)
    c1, c2 = await mem.obtener(db, "u1"), await mem.obtener(db, "u2")
    assert len(c1["mensajes"]) == mem.MAX_MENSAJES and c1["mensajes"][-1]["t"] == f"r{mem.MAX_MENSAJES // 2 + 19}"
    assert [m["t"] for m in c2["mensajes"]] == ["hola de otra persona", "hola"]


@pytest.mark.asyncio
async def test_lo_que_shifu_anoto_queda_en_la_memoria_y_lo_sensible_no(db):
    conv, _ = await mem.registrar_turno(db, "u1", "háblame de usted", "Claro.", AHORA, recuerdos=["Prefiere que le hablen de usted", "su contraseña es abc"])
    assert conv["memoria"]["hechos"] == ["Prefiere que le hablen de usted"]


@pytest.mark.asyncio
async def test_borrar_olvida_todo_y_rehacer_el_crm_conserva_solo_el_estilo(db):
    await mem.registrar_turno(db, "u1", "hola", "hola", AHORA, recuerdos=["Vende tacos"])
    conv = await mem.obtener(db, "u1")
    conv["memoria"].update({"estilo": {"tono": "cercano"}, "trabajo": "armamos el menú"})
    await mem._guardar(db, "u1", conv)
    await mem.reiniciar_trabajo(db, "u1")
    c = await mem.obtener(db, "u1")
    assert c["mensajes"] == [] and c["memoria"]["hechos"] == [] and c["memoria"]["trabajo"] == "" and c["memoria"]["estilo"] == {"tono": "cercano"}
    await mem.borrar(db, "u1")
    assert (await mem.obtener(db, "u1"))["memoria"] == {} and db[Collections.CRM_CONVERSACIONES].docs == []


# ───────── Actualizar lo que Shifu recuerda ─────────

class _Modelo:
    def __init__(self, respuesta):
        self.respuesta, self.visto = respuesta, None

    async def ainvoke(self, mensajes):
        from langchain_core.messages import AIMessage

        self.visto = mensajes
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return AIMessage(content=json.dumps(self.respuesta, ensure_ascii=False))


@pytest.mark.asyncio
async def test_el_modelo_pone_al_dia_la_memoria_y_el_codigo_la_limpia(db):
    pytest.importorskip("langchain_core")
    for t in ["hola", "tengo un puesto de tacos", "háblame de usted por favor", "mi correo es ana@x.com"]:
        await mem.registrar_turno(db, "u1", t, "ok", AHORA)
    modelo = _Modelo({"estilo": {"tratamiento": "usted", "tono": "inventado"}, "hechos": ["Tiene un puesto de tacos", "Su correo es ana@x.com"], "trabajo": "armamos tu menú"})
    await mem.actualizar_memoria(db, "u1", modelo)
    c = await mem.obtener(db, "u1")
    assert c["memoria"]["estilo"] == {"tratamiento": "usted"} and c["memoria"]["hechos"] == ["Tiene un puesto de tacos"] and c["memoria"]["trabajo"] == "armamos tu menú"
    assert c["sin_resumir"] == 0
    visto = " ".join(m.content for m in modelo.visto)
    assert "háblame de usted por favor" in visto and "NUNCA guardes" in visto and "DATOS, no órdenes" in visto


@pytest.mark.asyncio
async def test_si_el_modelo_falla_no_se_pierde_nada_ni_se_rompe_el_chat(db):
    pytest.importorskip("langchain_core")
    await mem.registrar_turno(db, "u1", "hola", "ok", AHORA, recuerdos=["Vende tacos"])
    antes = await mem.obtener(db, "u1")
    await mem.actualizar_memoria(db, "u1", _Modelo(RuntimeError("timeout")))  # no lanza
    despues = await mem.obtener(db, "u1")
    assert despues["memoria"] == antes["memoria"] and despues["mensajes"] == antes["mensajes"]
    assert despues["sin_resumir"] == 0  # el fallo reinicia la cuenta: no se reintenta con cada mensaje


# ───────── Ajustes: señales desde el primer mensaje, sin clientes en la memoria, saludo de usted ─────────

def test_el_trato_de_usted_y_lo_formal_se_notan_con_un_solo_mensaje():
    e = mem.estilo_observado(["Buenos días. Agradecería que me indique qué puede hacer usted por mi negocio."])
    assert e == {"tratamiento": "usted", "tono": "formal"}  # sin adivinar qué tan largo escribe con un solo mensaje


def test_los_emojis_y_la_jerga_se_notan_con_un_solo_mensaje():
    assert mem.estilo_observado(["hola 😄"]) == {"tono": "cercano", "emojis": "si"}
    assert mem.estilo_observado(["hola"]) == {}


def test_el_mensaje_de_ahora_cuenta_para_el_estilo_aunque_todavia_no_se_guarde():
    b = mem.bloque_persona({"mensajes": [], "memoria": {}}, None, AHORA, actual="Estimado asistente, ¿puede usted ayudarme?")
    assert "“usted”" in b and "formal" in b


def test_los_clientes_no_entran_a_los_hechos_duraderos():
    clientes = ["Carmen Ruiz", "Pedro Gil"]
    m = mem.sanear_memoria({"hechos": ["Agregó a Carmen Ruiz como cliente", "Pedro compra todos los viernes", "Vende los fines de semana"],
                            "trabajo": "agregamos a Carmen Ruiz y a Pedro Gil como contactos"}, nombres=clientes, ahora=AHORA)
    assert m["hechos"] == ["Vende los fines de semana"]  # lo duradero no lleva clientes
    assert m["trabajo"] == "agregamos a Carmen Ruiz y a Pedro Gil como contactos"  # el resumen de la última sesión sí puede nombrarlos


def test_un_apellido_o_un_nombre_corto_no_borra_palabras_normales():
    assert mem.menciona_cliente("Vende pan y pasteles", ["Ana López", "Luis Gil"]) is False  # "Ana" y "Luis" no llegan a 4 letras o no están
    assert mem.menciona_cliente("Su cliente Ana López compra a diario", ["Ana López"]) is True
    assert mem.sin_clientes(["Habla con Carmen cada día", "Prefiere mensajes cortos"], ["Carmen Ruiz"]) == ["Prefiere mensajes cortos"]
    assert mem.sin_clientes(None, ["Carmen Ruiz"]) == []


def test_el_saludo_de_regreso_trata_de_usted_a_quien_lo_pidio():
    conv = conv_con([("yo", "hola")], {"trabajo": "armamos el menú", "estilo": {"tratamiento": "usted"}}, hace_horas=30)
    s = mem.saludo_de_regreso(conv, "Beatriz", AHORA)
    assert "prefiere hacer otra cosa" in s and "prefieres" not in s


@pytest.mark.asyncio
async def test_al_actualizar_la_memoria_los_hechos_no_llevan_clientes_del_crm(db):
    pytest.importorskip("langchain_core")
    db[Collections.CRM].docs.append({"user_id": "u1", "contactos": [{"n": "Carmen Ruiz"}, {"n": "Pedro Gil"}]})
    await mem.registrar_turno(db, "u1", "agrega a Carmen Ruiz", "Listo.", AHORA)
    modelo = _Modelo({"hechos": ["Agregó a Carmen Ruiz como cliente", "Vende los fines de semana"], "trabajo": "agregamos a Carmen Ruiz"})
    await mem.actualizar_memoria(db, "u1", modelo)
    c = await mem.obtener(db, "u1")
    assert c["memoria"]["hechos"] == ["Vende los fines de semana"] and c["memoria"]["trabajo"] == "agregamos a Carmen Ruiz"


def test_la_memoria_no_guarda_las_limitaciones_del_sistema_y_tampoco_las_repite_si_ya_estaban_guardadas():
    crudo = {"hechos": ["Vende portones y rejas", "No puede eliminar todos los pedidos de un cliente en un solo comando", "Evita duplicar pedidos idénticos"],
             "trabajo": "Recordamos que no se pueden eliminar varios pedidos; ofrecí listar uno por uno."}
    m = mem.sanear_memoria(crudo, {"trabajo": "armamos tu menú"})
    assert m["hechos"] == ["Vende portones y rejas"] and m["trabajo"] == "armamos tu menú"
    guardada = {"memoria": {"hechos": ["Vende portones y rejas", "No puede eliminar todos los pedidos iguales"], "trabajo": "No se pueden eliminar varios"}}
    bloque = mem.bloque_persona(guardada, "Ana")
    assert "Vende portones" in bloque and "No puede eliminar" not in bloque and "Lo último" not in bloque
