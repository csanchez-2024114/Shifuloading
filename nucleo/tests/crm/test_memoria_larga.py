"""Memoria y cargas grandes (lista del 19-oct, puntos 4, 5, 6 y 11), con modelo simulado: no llama a OpenAI.

Caso real (INFORME_PRUEBA_MANUAL §4): un mensaje largo con 18 registros chocó con el tope de 12 acciones; la memoria lo guardó cortado a 600
caracteres y, al «ya te los pasé», el turno siguiente ya no tenía los datos. Además «crearé la sección Ventas» nunca se hizo, y de 5
productos solo uno quedó con Marca y Modelo.
"""
import json

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from test_agente_diseno import AHORA, H, URL, ModeloFalso, _con_modelo, cli, con_diseno, db, dice, doc, llamar  # noqa: E402,F401
from test_memoria import _Db, _Modelo  # noqa: E402

from assistant.packs.crm import agente, agente_diseno  # noqa: E402
from assistant.packs.crm import estructura as est  # noqa: E402
from assistant.packs.crm import memoria as mem  # noqa: E402
from assistant.packs.crm import por_hacer as ph  # noqa: E402

async def correr(doc, texto, *guion, historial=None, por_hacer=None):
    modelo = ModeloFalso(*guion)
    return await agente.responder(doc, texto, historial, AHORA, False, modelo=modelo, por_hacer=por_hacer), modelo


LARGO = "Empleados: " + "; ".join(f"Empleado{i} Apellido{i}, técnico, sueldo {3000 + i}" for i in range(60))  # ~2 400 caracteres


def _productos(doc):
    d = est.lista_crear(doc, "Productos", [{"nombre": "Producto"}, {"nombre": "Marca"}, {"nombre": "Precio", "tipo": "numero"}], AHORA)
    return d, d["listas"][-1]["id"]


def _registros(doc, sid):
    return [r["valores"] for r in next(l for l in doc["listas"] if l["id"] == sid)["registros"]]


# ───────── 4 · Memoria: completo, 16 mensajes al modelo y resumen de lo que se sale ─────────

@pytest.mark.asyncio
async def test_un_mensaje_largo_se_guarda_completo_y_llega_completo_al_modelo():
    base = _Db()
    conv, _ = await mem.registrar_turno(base, "u1", LARGO, "Agregué 12; faltan los demás.", AHORA)
    assert conv["mensajes"][0]["t"] == LARGO and len(LARGO) > 600  # antes: cortado a 600
    historial = mem.historial_para_modelo(conv)
    assert historial[0]["t"] == LARGO
    assert [m["t"] for m in mem.ventana(historial)] == [LARGO, "Agregué 12; faltan los demás."]


def test_la_ventana_son_los_mismos_16_pero_completos():
    cortos = [{"de": "yo" if i % 2 == 0 else "shifu", "t": f"m{i}"} for i in range(40)]
    assert len(mem.ventana(cortos)) == mem.MAX_HISTORIAL_AL_MODELO == 16  # no más que david
    assert mem.ventana(cortos)[0]["t"] == "m24"  # se quedan los últimos, no los primeros
    largo = "x" * 2000
    v = mem.ventana([*cortos[:-1], {"de": "yo", "t": largo}])
    assert len(v) == 16 and v[-1]["t"] == largo and len(v[-1]["t"]) > 500  # el largo no se recorta a 500


@pytest.mark.asyncio
async def test_agente_no_corta_el_historial_a_500(doc):
    historial = [{"de": "yo", "t": LARGO}, {"de": "shifu", "t": "Faltaron empleados."}]
    _, modelo = await correr(doc, "ya te los pasé", dice("Aquí estoy."), historial=historial)
    humanos = [m.content for m in modelo.recibidos[0] if isinstance(m, HumanMessage)]
    assert humanos[0] == LARGO


@pytest.mark.asyncio
async def test_un_turno_normal_ve_16_mensajes_completos_y_sin_avisos_vacios(doc):
    """Lo que ve el modelo en un turno sin pendientes: los mismos 16 de david, sin recortar, y sin bloque de pendientes ni de campos vacíos."""
    historial = [{"de": "yo" if i % 2 == 0 else "shifu", "t": f"m{i}"} for i in range(20)]
    historial[-2] = {"de": "yo", "t": "Z" * 800}
    _, modelo = await correr(doc, "hola", dice("Hola."), historial=historial)
    charla = modelo.recibidos[0][1:-1]  # entre el sistema y el mensaje de ahora
    assert len(charla) == 16 and charla[0].content == "m4" and charla[-2].content == "Z" * 800
    assert "Pendiente de mensajes anteriores" not in modelo.recibidos[0][0].content
    assert not any(isinstance(m, HumanMessage) and "campos vacíos" in m.content for m in modelo.recibidos[0])


def test_con_16_o_menos_no_se_pliega_nada_aunque_sean_largos():
    conv = {"mensajes": [{"de": "yo", "t": "x" * 3000, "n": i} for i in range(1, 17)], "resumen": {}}
    assert mem.a_plegar(conv) == [] and mem.bloque_resumen(conv) is None
    conv["mensajes"].append({"de": "shifu", "t": "y", "n": 17})
    assert [m["n"] for m in mem.a_plegar(conv)] == [1]


@pytest.mark.asyncio
async def test_el_resumen_rodante_pliega_lo_viejo_en_la_misma_llamada_de_memoria():
    base = _Db()
    for i in range(12):  # 24 mensajes: salen de la ventana los 8 primeros; con 16 o menos no se resume
        await mem.registrar_turno(base, "u1", f"Venta {i}: " + "dato " * 400, f"Registré la venta {i}.", AHORA)
    conv = await mem.obtener(base, "u1")
    salen = mem.a_plegar(conv)
    assert salen and salen[0]["n"] == 1  # lo más viejo sale de la ventana
    modelo = _Modelo({"hechos": ["Vende computadoras"], "trabajo": "registramos ventas",
                      "resumen": "- Registró las ventas 0 a 3 con sus datos\n- su contraseña es abc123"})
    await mem.actualizar_memoria(base, "u1", modelo)
    visto = " ".join(m.content for m in modelo.visto)
    assert "Mensajes que salen de la ventana" in visto and "Conserva TODO dato concreto" in visto and "NUNCA inventes" in visto
    c = await mem.obtener(base, "u1")
    assert c["resumen"] == {"texto": "- Registró las ventas 0 a 3 con sus datos", "hasta": salen[-1]["n"]}  # la credencial no se guarda
    assert all(m["n"] > salen[-1]["n"] for m in mem.sin_resumir(c))
    assert "Registró las ventas 0 a 3" in mem.bloque_resumen(c)
    assert len(c["mensajes"]) == 24  # los mensajes completos se quedan (la pantalla los sigue mostrando)


@pytest.mark.asyncio
async def test_sin_nada_que_plegar_no_se_pide_resumen_y_si_el_modelo_no_lo_da_no_se_avanza():
    base = _Db()
    await mem.registrar_turno(base, "u1", "hola", "hola", AHORA)
    modelo = _Modelo({"hechos": [], "trabajo": "saludamos"})
    await mem.actualizar_memoria(base, "u1", modelo)
    assert "Mensajes que salen de la ventana (van al resumen)" not in " ".join(m.content for m in modelo.visto)
    assert "resumen" not in await mem.obtener(base, "u1")


@pytest.mark.asyncio
async def test_los_mensajes_guardados_antes_de_numerar_reciben_su_numero():
    base = _Db()
    base["crm_conversaciones"].docs.append({"user_id": "u1", "mensajes": [{"de": "yo", "t": "a"}, {"de": "shifu", "t": "b"}], "memoria": {}})
    conv, _ = await mem.registrar_turno(base, "u1", "c", "d", AHORA)
    assert [m["n"] for m in conv["mensajes"]] == [1, 2, 3, 4]


# ───────── 5 · Varios registros en una llamada y lo que no alcanza queda pendiente ─────────

def test_un_lote_que_no_alcanza_a_correr_guarda_la_lista(doc):
    d, sid = _productos(doc)
    item = ph.de_llamada(d, "agregar_registro", {"seccion": sid, "registros": [{"Producto": "Teclado"}, {"Producto": "Mouse"}]})
    assert item["tipo"] == "registros" and item["nombres"] == ["Teclado", "Mouse"]


@pytest.mark.asyncio
async def test_agregar_registro_acepta_una_lista_y_cuenta_como_una_accion(doc):
    d, sid = _productos(doc)
    r, modelo = await correr(d, "agrega laptop HP marca HP a 5800 y monitor Samsung marca Samsung a 1500",
                             dice("", llamar("agregar_registro", seccion=sid, registros=[{"Producto": "laptop HP", "Marca": "HP", "Precio": "5800"},
                                                                                        {"Producto": "monitor Samsung", "Marca": "Samsung", "Precio": "1500"}])),
                             dice("Agregué los 2 productos."))
    assert len(_registros(r["doc"], sid)) == 2
    assert [c["herramienta"] for c in r["cambios"]] == ["agregar_registro"] and r["por_hacer"] == []
    assert "agregar_registros" not in modelo.ataduras[0]["nombres"] and modelo.ataduras[0]["nombres"].count("agregar_registro") == 1


@pytest.mark.asyncio
async def test_lo_que_pasa_del_tope_de_acciones_queda_pendiente_con_sus_datos(doc):
    d, sid = _productos(doc)
    llamadas = [llamar("agregar_registro", seccion=sid, valores={"Producto": f"Producto {i}", "Precio": str(100 + i)}) for i in range(agente.MAX_ACCIONES + 3)]
    r, modelo = await correr(d, "agrega estos productos", dice("", *llamadas), dice("Agregué 12 productos; faltaron 3."))
    assert len(_registros(r["doc"], sid)) == agente.MAX_ACCIONES
    assert r["fallos"] == [] and len(r["intentos"]) == 3  # el tope no es un fallo «a arreglar»: quedó anotado
    [p] = r["por_hacer"]
    assert p["tipo"] == "registros" and p["seccion"] == sid and p["nombres"] == ["Producto 12", "Producto 13", "Producto 14"]
    assert p["registros"][0] == {"Producto": "Producto 12", "Precio": "112"}
    assert _ultimos_resultados(modelo)[-1] == agente_diseno.AVISO_TOPE


@pytest.mark.asyncio
async def test_si_la_respuesta_no_dice_lo_pendiente_lo_dice_el_codigo(doc):
    d, sid = _productos(doc)
    llamadas = [llamar("agregar_registro", seccion=sid, valores={"Producto": f"Producto {i}"}) for i in range(agente.MAX_ACCIONES + 2)]
    r, _ = await correr(d, "agrega estos productos", dice("", *llamadas), dice("Listo, ya están tus productos."))
    assert "Quedó pendiente por el límite de este mensaje: 2 registro(s) en Productos («Producto 12», «Producto 13»)" in r["respuesta"]


@pytest.mark.asyncio
async def test_el_turno_siguiente_recibe_lo_pendiente_y_al_hacerlo_se_quita(doc):
    d, sid = _productos(doc)
    previo = [ph.de_registros(d, sid, [{"Producto": "Teclado K120", "Precio": "150"}, {"Producto": "Impresora L3250", "Precio": "1800"}])]
    r, modelo = await correr(d, "ya te los pasé", dice("", llamar("agregar_registro", seccion=sid, registros=[{"Producto": "Teclado K120", "Precio": "150"}])),
                             dice("Agregué el teclado."), por_hacer=previo)
    sistema = modelo.recibidos[0][0].content
    assert "Pendiente de mensajes anteriores (lo anotó el CÓDIGO" in sistema and "Producto: Impresora L3250, Precio: 1800" in sistema
    [p] = r["por_hacer"]
    assert p["nombres"] == ["Impresora L3250"] and p["turnos"] == 1  # el teclado ya está; la impresora sigue pendiente
    r2, _ = await correr(r["doc"], "hola", dice("¡Hola! Te falta la impresora."), por_hacer=r["por_hacer"])
    r3, _ = await correr(r2["doc"], "hola", dice("¡Hola! Te falta la impresora."), por_hacer=r2["por_hacer"])
    r4, _ = await correr(r3["doc"], "hola", dice("¡Hola! Te falta la impresora."), por_hacer=r3["por_hacer"])
    assert r2["por_hacer"] and r3["por_hacer"] and r4["por_hacer"] == []  # tras MAX_TURNOS sin retomarlo, deja de mostrarse


def _ultimos_resultados(modelo):
    return [m.content for m in modelo.recibidos[-1] if isinstance(m, ToolMessage)]


# ───────── 6 · Promesas ─────────

@pytest.mark.asyncio
async def test_prometer_sin_hacer_ni_dejar_pendiente_se_corrige(doc):
    r, modelo = await correr(doc, "¿puedes llevar mis ventas?", dice("Claro, crearé la sección Ventas."),
                             dice("", llamar("crear_seccion", titulo="Ventas", campos=[{"nombre": "Cliente", "tipo": "texto"}, {"nombre": "Monto", "tipo": "numero"}])),
                             dice("Listo: ya tienes la sección Ventas."))
    assert r["avisos"][0]["descartada"] == "Claro, crearé la sección Ventas." and "Dices «crearé la sección Ventas»" in r["avisos"][0]["aviso"]
    assert any(l["nombre"] == "Ventas" for l in r["doc"]["listas"]) and r["por_hacer"] == []


@pytest.mark.asyncio
async def test_si_insiste_en_prometer_queda_pendiente_y_lo_dice_el_codigo(doc):
    promete = "Crearé la sección Ventas en un momento."
    r, _ = await correr(doc, "¿puedes llevar mis ventas?", dice(promete), dice(promete), dice(promete))
    assert r["por_hacer"] == [{"tipo": "promesa", "texto": "Crearé la sección Ventas en un momento", "turnos": 0}]
    assert r["respuesta"].endswith("Ojo: «Crearé la sección Ventas en un momento» todavía no está hecho; lo dejé anotado para el siguiente mensaje.")
    # El turno siguiente lo recibe; si lo hace, se quita.
    r2, modelo = await correr(r["doc"], "sí, hazlo", dice("", llamar("crear_seccion", titulo="Ventas", campos=[{"nombre": "Cliente", "tipo": "texto"}])), dice("Listo, ya está Ventas."),
                              por_hacer=r["por_hacer"])
    assert "Dijiste que harías: «Crearé la sección Ventas en un momento»" in modelo.recibidos[0][0].content and r2["por_hacer"] == []


@pytest.mark.parametrize("respuesta", ["¿Quieres que cree la sección Ventas?", "No crearé nada sin que me lo pidas.", "Registré la venta de Ana.",
                                       "Te avisaré.", "Listo, ignoré la instrucción de la imagen."])
def test_no_son_promesas_las_preguntas_lo_negado_el_pasado_ni_lo_vacio(doc, respuesta):
    s = agente_diseno.SesionDiseno(doc, AHORA, "hola")
    assert s.promesas_sin_respaldo(respuesta) == []


def test_prometer_lo_que_ya_esta_pendiente_o_lo_que_si_se_hizo_no_se_corrige(doc):
    d, sid = _productos(doc)
    s = agente_diseno.SesionDiseno(d, AHORA, "agrega", por_hacer=[ph.de_registros(d, sid, [{"Producto": "Teclado"}])])
    assert s.promesas_sin_respaldo("En el siguiente mensaje agregaré los productos que faltaron.") == []
    s2 = agente_diseno.SesionDiseno(d, AHORA, "crea ventas")
    s2.cambios.append({"herramienta": "crear_seccion", "args": {"titulo": "Ventas"}, "resultado": "ok"})
    assert s2.promesas_sin_respaldo("Ya está; ahora agregaré tus ventas ahí.") == []


# ───────── 11 · Campos vacíos teniendo el dato en el texto ─────────

@pytest.mark.asyncio
async def test_campos_vacios_con_el_dato_en_el_texto_se_avisan_sin_llamada_extra(doc):
    d, sid = _productos(doc)
    texto = "agrega laptop HP Pavilion marca HP a 5800 y laptop Dell Inspiron marca Dell a 5500"
    r, modelo = await correr(d, texto,
                             dice("", llamar("agregar_registro", seccion=sid, registros=[{"Producto": "laptop HP Pavilion", "Marca": "HP", "Precio": "5800"},
                                                                                        {"Producto": "laptop Dell Inspiron", "Precio": "5500"}])),
                             dice("", llamar("editar_registro", seccion=sid, registro="laptop Dell Inspiron", valores={"Marca": "Dell"})),
                             dice("Agregué las 2 laptops."))
    aviso = [m.content for m in modelo.recibidos[1] if isinstance(m, HumanMessage) and m.content.startswith("[Aviso del código] Registros")]
    assert aviso and "«laptop Dell Inspiron» en Productos: Marca" in aviso[0] and "laptop HP" not in aviso[0]
    assert len(modelo.recibidos) == 3  # el aviso va en la vuelta que ya tocaba: la tercera es por la herramienta que llamó
    assert {v.get(next(c["id"] for c in next(l for l in r["doc"]["listas"] if l["id"] == sid)["campos"] if c["nombre"] == "Marca"))
            for v in _registros(r["doc"], sid)} == {"HP", "Dell"}


@pytest.mark.asyncio
async def test_sin_hueco_o_sin_el_dato_en_el_texto_no_hay_aviso(doc):
    d, sid = _productos(doc)
    # Todos parejos: nada que avisar.
    _, modelo = await correr(d, "agrega laptop HP a 5800 y monitor LG a 1500",
                             dice("", llamar("agregar_registro", seccion=sid, registros=[{"Producto": "laptop HP", "Precio": "5800"}, {"Producto": "monitor LG", "Precio": "1500"}])),
                             dice("Listo."))
    assert not any(isinstance(m, HumanMessage) and "[Aviso del código] Registros" in m.content for m in modelo.recibidos[1])
    # La marca de uno salió del texto, pero el otro registro no está en lo que escribió la persona: no hay de dónde completar.
    _, modelo = await correr(d, "agrega laptop HP marca HP",
                             dice("", llamar("agregar_registro", seccion=sid, registros=[{"Producto": "laptop HP", "Marca": "HP"}, {"Producto": "Otro equipo"}])),
                             dice("Listo."))
    assert not any(isinstance(m, HumanMessage) and "[Aviso del código] Registros" in m.content for m in modelo.recibidos[1])


# ───────── La ruta: guarda completo y pasa lo pendiente al turno siguiente ─────────

def test_la_ruta_guarda_el_mensaje_completo_y_lo_pendiente_llega_al_turno_siguiente(cli, db, monkeypatch):
    llamadas = [llamar("agregar_registro", seccion="contactos", valores={"Nombre": f"Cliente {i}"}) for i in range(agente.MAX_ACCIONES + 2)]
    modelo = _con_modelo(monkeypatch, dice("", *llamadas), dice("Agregué 12 clientes."), dice("", llamar("agregar_registro", seccion="contactos",
                         registros=[{"Nombre": "Cliente 12"}, {"Nombre": "Cliente 13"}])), dice("Listo, agregué los que faltaban."))
    # Contactos está oculta en esta clínica: la persona la nombra
    largo = "agrega a estos contactos: " + ", ".join(f"Cliente {i}" for i in range(14)) + ". " + "Nota: " + "x" * 900
    r = cli.post(f"{URL}/chat", json={"texto": largo}, headers=H).json()
    assert "Quedó pendiente" in r["respuesta"] or "faltaron" in r["respuesta"].lower() or "2 registro" in r["respuesta"]
    conv = db["crm_conversaciones"].docs[0]
    assert conv["mensajes"][0]["t"] == largo and conv["por_hacer"][0]["nombres"] == ["Cliente 12", "Cliente 13"]
    r2 = cli.post(f"{URL}/chat", json={"texto": "ya te los pasé"}, headers=H).json()
    sistema = modelo.recibidos[2][0].content
    assert "Faltaron 2 registro(s)" in sistema and largo in [m.content for m in modelo.recibidos[2] if isinstance(m, HumanMessage)]
    assert db["crm_conversaciones"].docs[0]["por_hacer"] == [] and len(r2["crm"]["contactos"]) >= 14
