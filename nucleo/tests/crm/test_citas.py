"""Citas en la agenda, borrar solo lo que se ve y no elegir por la persona (pendientes 2, 3, 9, 10 y 43 de LISTA_PENDIENTES_2026-10-19,
y «siempre sabe qué hay en pantalla» del PLAN_MAESTRO §2). Casos de la prueba manual del 19-oct. Sin IA real: el modelo es un guion."""
from datetime import date

import pytest

from lab_doc import doc_de_lab
from test_agente_diseno import AHORA, con_diseno, correr, dice, llamar  # noqa: F401  (con_diseno es fixture)
from test_agente_diseno import _resultados

from assistant.packs.crm import agente_diseno as ad
from assistant.packs.crm import chat
from assistant.packs.crm import pantalla
from assistant.packs.crm import secciones_v as sv
from assistant.packs.crm.generador import generar
from assistant.packs.crm.secciones import titulo_seccion

# AHORA = martes 13-oct-2026 09:00 en Guatemala: «mañana» = miércoles 14; los jueves siguientes = 15, 22 y 29.
B = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2}]


@pytest.fixture
def agenda():
    return doc_de_lab("agenda", {"vista": "inicio", "bloques": []})[0]


@pytest.fixture
def memb():
    return doc_de_lab("membresias", {"vista": "inicio", "bloques": B})[0]


def citas(doc):
    return sorted((r["valores"].get("fecha"), r["valores"].get("hora"), r["valores"].get("cliente")) for r in sv.registros_de(doc, "l_citas"))


# ───────── 2/43: la cita es un registro en la agenda; las repeticiones las calcula el código ─────────

def test_las_fechas_de_una_serie_las_calcula_el_codigo():
    hoy = date(2026, 10, 13)
    manana = date(2026, 10, 14)
    assert ad.fechas_de_cita(manana, {"cada": "jueves", "veces": 3}, hoy)[0] == [manana, date(2026, 10, 15), date(2026, 10, 22), date(2026, 10, 29)]
    jueves = date(2026, 10, 15)
    assert ad.fechas_de_cita(jueves, {"cada": "jueves", "veces": 3}, hoy)[0] == [jueves, date(2026, 10, 22), date(2026, 10, 29)]
    assert ad.fechas_de_cita(jueves, {"cada": "semana", "veces": 2}, hoy)[0] == [jueves, date(2026, 10, 22)]
    assert ad.fechas_de_cita(jueves, {"cada": "semana", "hasta": "30 de octubre"}, hoy)[0] == [jueves, date(2026, 10, 22), date(2026, 10, 29)]
    assert ad.fechas_de_cita(date(2026, 1, 31), {"cada": "mes", "veces": 2}, hoy)[0] == [date(2026, 1, 31), date(2026, 2, 28)]
    assert ad.fechas_de_cita(jueves, None, hoy)[0] == [jueves]
    assert ad.fechas_de_cita(jueves, {"cada": "semana"}, hoy)[1].startswith("ERROR")  # sin cuántas ni hasta cuándo: se pregunta
    assert len(ad.fechas_de_cita(jueves, {"cada": "dia", "veces": 500}, hoy)[0]) == ad.MAX_REPETIR


@pytest.mark.asyncio
async def test_cita_de_manana_y_cada_jueves_quedan_como_registros_en_la_agenda(agenda):
    r, modelo = await correr(agenda, "agéndame una cita con Ramires mañana a las 3 y luego cada jueves por 3 semanas",
                             dice("", llamar("agendar", dia="mañana", hora="3 de la tarde", valores={"cliente": "Ramires"},
                                             repetir={"cada": "jueves", "veces": 3})),
                             dice("Agendé 4 citas con Ramires: mañana y los jueves 15, 22 y 29 de octubre a las 15:00."))
    assert citas(r["doc"]) == [(f, "15:00", "Ramires") for f in ("2026-10-14", "2026-10-15", "2026-10-22", "2026-10-29")]
    assert r["doc"]["tareas"] == agenda["tareas"] and "desarrollo" in r["doc"]["ocultas"]  # ni tarea ni tablero que reaparece
    assert r["avisos"] == [] and len(modelo.recibidos) == 2  # 0 llamadas de más
    assert "2026-10-29" in _resultados(modelo)[0] and "agendó 4 en Agenda" in r["cambios"][0]["etiqueta"]


@pytest.mark.asyncio
async def test_una_tarea_con_dia_y_hora_es_una_cita(agenda):
    r, modelo = await correr(agenda, "agenda una cita con Ramires mañana a las 3",
                             dice("", llamar("agregar_tarea", texto="Cita con Ramires", fecha="2026-10-14", hora="15:00")),
                             dice("", llamar("agendar", dia="mañana", hora="15:00", valores={"cliente": "Ramires"})),
                             dice("Agendé la cita con Ramires para mañana a las 15:00."))
    assert "Usa agendar" in _resultados(modelo)[0] and "l_citas (Agenda)" in _resultados(modelo)[0]
    assert r["doc"]["tareas"] == agenda["tareas"] and citas(r["doc"]) == [("2026-10-14", "15:00", "Ramires")]


@pytest.mark.asyncio
async def test_sin_agenda_no_se_guarda_en_otro_lado_y_se_propone_crearla(memb):
    r, modelo = await correr(memb, "agéndame una cita con Ramires mañana a las 3",
                             dice("", llamar("agendar", dia="mañana", hora="3 de la tarde", valores={"cliente": "Ramires"})),
                             dice("No tienes una agenda. ¿Creo la pestaña «Citas» para guardarla ahí?"))
    assert _resultados(modelo)[0].startswith("ERROR: no hay ninguna agenda") and 'desde=\\"citas\\"' not in _resultados(modelo)[0]
    assert 'desde="citas"' in _resultados(modelo)[0] and r["cambios"] == [] and r["doc"]["tareas"] == memb["tareas"]
    r2, modelo2 = await correr(memb, "agéndame una cita con Ramires mañana a las 3",
                               dice("", llamar("agregar_tarea", texto="Cita con Ramires", fecha="2026-10-14", hora="15:00")), dice("¿Creo «Citas»?"))
    assert "No hay ninguna agenda" in _resultados(modelo2)[0] and r2["cambios"] == []


@pytest.mark.asyncio
async def test_agendar_en_una_seccion_que_no_es_agenda_lo_dice(agenda):
    r, modelo = await correr(agenda, "agenda a Ramires mañana", dice("", llamar("agendar", seccion="l_clientes", dia="mañana", valores={"cliente": "Ramires"})),
                             dice("¿En Citas?"))
    assert "«Clientas» no es una agenda" in _resultados(modelo)[0] and r["cambios"] == []


def test_el_estado_dice_donde_se_agenda_y_para_que_es_el_tablero(agenda):
    s = ad.SesionDiseno(agenda, AHORA, "hola")
    import json
    c = json.loads(s.contexto())
    assert c["agendas"] == ["l_citas (Agenda)"]
    assert any("las citas van en una agenda" in (v["sirve_para"] or "") for v in c["secciones_del_menu"].values())
    nombres = {h["function"]["name"]: h for h in s.herramientas()}
    assert "agendar" in nombres and "agendar" in nombres["agregar_tarea"]["function"]["description"]


def test_en_comercio_el_tablero_ya_no_se_llama_pedidos():
    assert titulo_seccion("comercio", "desarrollo") == "Pendientes"
    assert titulo_seccion("comercio", "desarrollo", {"desarrollo": "Pedidos"}) == "Pedidos"  # si la persona le puso otro, manda el suyo


# ───────── 3: «borra todo» arma la lista desde lo visible; el «sí» ejecuta esa lista ─────────

def test_lo_visible_no_incluye_lo_oculto_ni_lo_que_el_menu_no_muestra(memb):
    ids = [s["id"] for s in pantalla.secciones_visibles(memb)]
    assert ids == ["l_miembros", "l_pagos", "actividad", "rrhh"]


def test_el_pendiente_de_secciones_se_sanea():
    assert chat.sanear_pendiente({"tipo": "secciones", "ids": ["l_a", "rrhh", "l_a"], "x": 1}) == {"tipo": "secciones", "ids": ["l_a", "rrhh"]}
    for malo in ({"tipo": "secciones", "ids": []}, {"tipo": "secciones", "ids": "l_a"}, {"tipo": "secciones", "ids": ["x" * 65]},
                 {"tipo": "secciones", "ids": [f"l_{i}" for i in range(chat.MAX_SECCIONES_PENDIENTES + 1)]}):
        assert chat.sanear_pendiente(malo) is None


@pytest.mark.asyncio
async def test_borrar_las_pestanas_que_nombro_solo_cuenta_las_que_se_ven(memb):
    r, modelo = await correr(memb, "quita contactos, pagos y miembros",
                             dice("", llamar("quitar_seccion", seccion="contactos"), llamar("quitar_seccion", seccion="pagos"),
                                  llamar("quitar_seccion", seccion="miembros")))
    assert r["pendiente"] == {"tipo": "secciones", "ids": ["l_pagos", "l_miembros"]} and r["cambios"] == []
    assert "«Pacientes» no se ve en tu menú" in r["respuesta"] and len(modelo.recibidos) == 1


def test_el_si_quita_exactamente_la_lista_aunque_algo_ya_no_este(memb):
    nuevo, texto = chat.ejecutar_pendiente(memb, {"tipo": "secciones", "ids": ["l_pagos", "l_no_existe"]}, AHORA)
    assert [l["id"] for l in nuevo["listas"]] == ["l_miembros"] and texto.startswith("Listo, quité 1 pestaña: «Pagos»")
    r = chat.responder(memb, "no, mejor no", {"tipo": "secciones", "ids": ["l_pagos"]})
    assert r["doc"] is memb  # sin «sí» no se borra nada


# ───────── Siempre sabe qué hay en pantalla ─────────

@pytest.mark.asyncio
async def test_borra_la_tabla_sin_tabla_en_pantalla_no_toca_otra_pestana(memb):
    r, modelo = await correr(memb, "borra la tabla", dice("", llamar("quitar_bloque", bloque="p_l_miembros")),
                             dice("Aquí en el inicio no hay ninguna tabla: tienes el resumen y lo que vence. ¿A cuál te refieres?"))
    res = _resultados(modelo)[0]
    assert res.startswith("ERROR: «p_l_miembros» (lista) está en «Miembros»") and "b0 (resumen con cifras de Miembros)" in res and r["cambios"] == []


@pytest.mark.asyncio
async def test_si_nombra_la_otra_pestana_si_se_puede(memb):
    r, modelo = await correr(memb, "en miembros quita la tabla", dice("", llamar("quitar_bloque", bloque="p_l_miembros")), dice("Listo."))
    assert not _resultados(modelo)[0].startswith("ERROR")
    assert [c["herramienta"] for c in r["cambios"]] == ["quitar_bloque"]


@pytest.mark.asyncio
async def test_mirando_una_pestana_un_bloque_del_inicio_no_se_toca_si_no_lo_nombra(memb):
    from test_agente_diseno import ModeloFalso
    from assistant.packs.crm import agente
    modelo = ModeloFalso(dice("", llamar("quitar_bloque", bloque="b1")), dice("Aquí no hay calendario. ¿A qué te refieres?"))
    r = await agente.responder(memb, "quita el calendario de aquí", [], AHORA, False, modelo=modelo, seccion="Miembros")
    res = _resultados(modelo)[0]
    assert res.startswith("ERROR: «b1» (por vencer) está en «Inicio», pero la persona está mirando «Miembros»") and "p_l_miembros (lista de Miembros)" in res
    assert "No ofrezcas quitarlo" in res  # no hay calendario: no se ofrece quitar el bloque del inicio
    assert r["cambios"] == []


def _kpis_en(doc, pid):
    efectiva = pantalla.plantilla_efectiva(doc)
    return [b for b in (pantalla.pagina_de(efectiva, doc, pid) or []) if b.get("vista") == "kpis"]


@pytest.mark.asyncio
async def test_el_resumen_pedido_mirando_una_pestana_no_se_cambia_en_el_inicio(memb):
    """banco_pestanas: «aquí pon arriba un resumen» llama cambiar_visual sobre b0 (el del inicio), a veces con pestana="inicio".
    La pieza queda en la pestaña abierta; el inicio no se toca."""
    from test_agente_diseno import ModeloFalso
    from assistant.packs.crm import agente
    modelo = ModeloFalso(dice("", llamar("cambiar_visual", bloque="b0", vista="kpis", pestana="inicio", opciones={"por": "estado"})),
                         dice("Listo, puse el resumen en Miembros."))
    r = await agente.responder(memb, "aquí pon arriba un resumen por estado", [], AHORA, False, modelo=modelo, seccion="Miembros")
    assert [c["herramienta"] for c in r["cambios"]] == ["agregar_bloque"]
    assert r["cambios"][0]["args"]["pestana"] == "l_miembros"
    assert _kpis_en(r["doc"], "l_miembros") and [b["vista"] for b in r["doc"]["inicio"]] == ["kpis", "vencimientos"]
    assert r["fallos"] == []


@pytest.mark.asyncio
async def test_si_nombra_el_inicio_cambiar_visual_si_lo_toca(memb):
    from test_agente_diseno import ModeloFalso
    from assistant.packs.crm import agente
    modelo = ModeloFalso(dice("", llamar("cambiar_visual", bloque="b0", vista="tabla", pestana="inicio")), dice("Listo, el del inicio ahora es una lista."))
    r = await agente.responder(memb, "en el inicio cambia el resumen por una lista", [], AHORA, False, modelo=modelo, seccion="Miembros")
    assert [c["herramienta"] for c in r["cambios"]] == ["cambiar_visual"]
    assert [b["vista"] for b in r["doc"]["inicio"]] == ["tabla", "vencimientos"]
    assert not _kpis_en(r["doc"], "l_miembros")


# ───────── 9: no elige sola qué quitar ─────────

@pytest.mark.asyncio
async def test_el_campo_que_creas_menos_importante_no_lo_elige_el_modelo(memb):
    r, modelo = await correr(memb, "a miembros quítale el campo que tú creas menos importante",
                             dice("", llamar("quitar_campo", seccion="l_miembros", campo="plan")),
                             dice("Te propongo quitar «Plan»: es el que menos se usa. ¿Lo quito?"))
    res = _resultados(modelo)[0]
    assert res.startswith("ERROR: la persona no nombró el campo «Plan»") and "Plan " in res and "/" in res
    assert r["cambios"] == [] and any(c["id"] == "plan" for c in next(l for l in r["doc"]["listas"] if l["id"] == "l_miembros")["campos"])


@pytest.mark.asyncio
async def test_si_shifu_lo_propuso_y_dice_que_si_se_quita(memb):
    historial = [{"de": "yo", "t": "a miembros quítale el campo que tú creas menos importante"},
                 {"de": "shifu", "t": "Te propongo quitar «Plan»: es el que menos se usa. ¿Lo quito?"}]
    r, _ = await correr(memb, "sí", dice("", llamar("quitar_campo", seccion="l_miembros", campo="plan")), dice("Listo, quité Plan."),
                        historial=historial)
    assert [c["herramienta"] for c in r["cambios"]] == ["quitar_campo"]


@pytest.mark.asyncio
async def test_una_pestana_que_no_nombro_no_se_quita(memb):
    r, modelo = await correr(memb, "quita la pestaña que menos uso", dice("", llamar("quitar_seccion", seccion="l_pagos")),
                             dice("¿Quito «Pagos»? Es la que menos registros tiene."))
    assert _resultados(modelo)[0].startswith("ERROR: la persona no nombró la pestaña «Pagos»") and r["cambios"] == []


# ───────── 10: hay una oculta para lo mismo → pregunta «¿la muestro o creo otra?» ─────────

@pytest.mark.asyncio
async def test_crear_empleados_con_equipo_oculta_pregunta_antes(memb):
    memb = {**memb, "ocultas": [*memb["ocultas"], "rrhh"]}
    crear = llamar("crear_seccion", titulo="Empleados", campos=[{"nombre": "Nombre", "tipo": "texto"}, {"nombre": "Puesto", "tipo": "texto"}])
    r, modelo = await correr(memb, "agrega a mis empleados: Ana López cajera", dice("", crear),
                             dice("Ya tienes «Especialistas» oculta. ¿La muestro o creo otra sección «Empleados»?"))
    assert _resultados(modelo)[0].startswith("ERROR: no la creé: ya existe «Especialistas», oculta en el menú") and r["cambios"] == []

    historial = [{"de": "yo", "t": "agrega a mis empleados: Ana López cajera"},
                 {"de": "shifu", "t": "Ya tienes «Especialistas» oculta. ¿La muestro o creo otra sección «Empleados»?"}]
    crear2 = llamar("crear_seccion", titulo="Empleados", campos=[{"nombre": "Nombre", "tipo": "texto"}, {"nombre": "Puesto", "tipo": "texto"}])
    r2, _ = await correr(memb, "crea otra", dice("", crear2), dice("Listo, creé «Empleados»."), historial=historial)
    assert [c["herramienta"] for c in r2["cambios"]] == ["crear_seccion"]


@pytest.mark.asyncio
async def test_una_seccion_que_no_tiene_que_ver_con_las_ocultas_se_crea_directo(memb):
    crear = llamar("crear_seccion", titulo="Cobros", campos=[{"nombre": "Miembro", "tipo": "texto"}, {"nombre": "Monto", "tipo": "dinero"}])
    r, _ = await correr(memb, "quiero llevar cobros de cada miembro", dice("", crear), dice("Creé «Cobros»."))
    assert [c["herramienta"] for c in r["cambios"]] == ["crear_seccion"]  # «Cobros» de Carlos (oculta, sin datos) no cuenta


def test_otros_nombres_no_confunden_secciones_distintas():
    assert ad._parecidos("Empleados", "Empleado") and ad._parecidos("Colaboradores", "Colaborador")
    assert not ad._parecidos("Clases", "Clientes") and not ad._parecidos("Pagos", "Equipo")
    d = generar("u1", {"rubro": "comercio"}, AHORA)
    assert titulo_seccion("comercio", "rrhh", d["secciones"]) == "Vendedores"


@pytest.mark.asyncio
async def test_la_misma_cita_dos_veces_no_se_repite(agenda):
    pide = llamar("agendar", dia="mañana", hora="15:00", valores={"cliente": "Ramires"})
    r, _ = await correr(agenda, "agenda a Ramires mañana a las 3", dice("", pide), dice("Agendé a Ramires."))
    otra = llamar("agendar", dia="mañana", hora="3 de la tarde", valores={"cliente": "ramires"})
    r2, modelo = await correr(r["doc"], "agenda a Ramires mañana a las 3", dice("", otra), dice("Esa cita ya existe: no la repetí."))
    assert _resultados(modelo)[0].startswith("Ya existe esa cita") and r2["cambios"] == [] and len(citas(r2["doc"])) == 1


@pytest.mark.asyncio
async def test_meter_gente_en_el_equipo_oculto_dice_que_existe(memb):
    memb = {**memb, "ocultas": [*memb["ocultas"], "rrhh"]}
    r, modelo = await correr(memb, "agrega a mis empleados: Ana López", dice("", llamar("agregar_registro", seccion="rrhh", valores={"nombre": "Ana López"})),
                             dice("¿Muestro «Especialistas» o creo otra sección?"))
    assert "«Especialistas» no lleva registros" in _resultados(modelo)[0] and "está oculta" in _resultados(modelo)[0] and r["cambios"] == []
