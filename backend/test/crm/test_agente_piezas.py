"""Piezas del inicio y cercos de pantalla del agente con diseño (E2): herramientas de edicion, etiquetas, lado, gráfico negado y sustituto."""
import copy
import re

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage  # noqa: E402

from app.crm import agente  # noqa: E402
from app.crm import operaciones as op  # noqa: E402
from app.crm.generador import generar  # noqa: E402
from app.crm.pantalla import describir_pantalla  # noqa: E402
from test_agente_diseno import AHORA, BRIEF, correr, dice, llamar  # noqa: E402
from lab_doc import doc_de_lab  # noqa: E402


@pytest.fixture(autouse=True)
def diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")


@pytest.fixture
def doc():
    d = generar("u1", BRIEF, AHORA)
    return op.contactos_crear(d, [{"n": n} for n in ["Ana Morales", "Luis Pérez"]], "WhatsApp", ahora=AHORA)

E = {"bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}]}


@pytest.fixture
def doc_lab():
    return doc_de_lab("membresias", E)[0]


@pytest.mark.asyncio
async def test_el_modelo_ve_las_herramientas_de_bloques_y_leer_enlace(doc_lab, monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    _, modelo = await correr(doc_lab, "hola", dice("Hola."))
    nombres = modelo.ataduras[0]["nombres"]
    for n in ("agregar_bloque", "mover_bloque", "cambiar_visual", "quitar_bloque", "leer_enlace", "crear_seccion"):
        assert n in nombres
    assert "definir_opciones" in nombres  # solo Carlos
    estado = __import__("json").loads(modelo.recibidos[0][0].content.split("Estado de la pantalla (JSON):\n", 1)[1])
    assert "bloques" in estado and estado["bloques"][0]["id"] == "b0"


@pytest.mark.asyncio
async def test_agregar_bloque_deja_cambio_y_etiqueta(doc_lab):
    antes = copy.deepcopy(doc_lab["inicio"])
    r, _ = await correr(doc_lab, "agrega una lista de miembros",
                        dice("", llamar("agregar_bloque", seccion="l_miembros", vista="tabla")),
                        dice("Listo, agregué la lista."))
    assert len(r["doc"]["inicio"]) == len(antes) + 1
    c = r["cambios"][0]
    assert c["herramienta"] == "agregar_bloque" and c.get("etiqueta") and "agregó" in c["etiqueta"]


@pytest.mark.asyncio
async def test_crear_seccion_con_nombre_de_carlos_sigue_siendo_alias(doc):
    r, _ = await correr(doc, "lleva mis cobros",
                        dice("", llamar("crear_seccion", nombre="Cobros", campos=[{"nombre": "Cliente"}])),
                        dice("Creé la sección Cobros."))
    assert r["doc"]["listas"][0]["nombre"] == "Cobros"
    assert r["cambios"][0]["herramienta"] == "crear_seccion"


@pytest.mark.asyncio
async def test_cerco_lado_cuando_no_coincide(doc_lab):
    # Sola en su fila, el acomodo (lienzo.acomodar, como en el laboratorio) la estira a ancho completo: no queda «a la derecha».
    r, modelo = await correr(doc_lab, "pon una lista a la derecha",
                             dice("", llamar("agregar_bloque", seccion="l_miembros", vista="tabla", ancho=6)),
                             dice("Listo, quedó a la derecha."),
                             dice("Listo, quedó a la derecha."),
                             dice("Listo, quedó a la derecha."))
    assert any(a["aviso"].startswith('[Aviso interno] Dices "derecha"') for a in r["avisos"])
    assert len(modelo.recibidos) == 4 and "Ojo: en realidad quedó en la fila 2, ancho completo." in r["respuesta"]


@pytest.mark.asyncio
async def test_cerco_lado_no_dispara_si_coincide():
    # Con media fila libre al lado de b0, la tabla nueva queda a la derecha y decirlo es verdad.
    d = doc_de_lab("membresias", {"bloques": [{**E["bloques"][0], "ancho": 6}]})[0]
    r, modelo = await correr(d, "pon una lista a la derecha",
                             dice("", llamar("agregar_bloque", seccion="l_miembros", vista="tabla", ancho=6)),
                             dice("Listo, quedó a la derecha."))
    assert r["avisos"] == [] and len(modelo.recibidos) == 2


@pytest.mark.asyncio
async def test_cerco_lado_no_dispara_por_un_bloque_quitado(doc_lab):
    # «Quité la gráfica que estaba a la derecha» es verdad: un bloque quitado no tiene lado que verificar (antes el aviso
    # empujaba al modelo a achicar otro bloque).
    uid = doc_lab["inicio"][-1]["uid"]
    r, modelo = await correr(doc_lab, "quita esto", dice("", llamar("quitar_bloque", bloque=uid)),
                             dice("Quité la gráfica que estaba a la derecha."))
    assert r["avisos"] == [] and len(modelo.recibidos) == 2


@pytest.mark.asyncio
async def test_cerco_grafico_negado_cuando_si_existe(doc_lab):
    g = next(sec["graficos_posibles"][0] for sec in describir_pantalla(doc_lab)["secciones"] if sec.get("graficos_posibles"))
    nombre = re.sub(r" \d+ %", "", re.search(r"\((.*)\)", g).group(1)).lower()
    r, _ = await correr(doc_lab, f"quiero un gráfico de {nombre}",
                        dice(f"No puedo, no hay {nombre} para tus miembros."),
                        dice(f"No puedo, no hay {nombre} para tus miembros."),
                        dice(f"No puedo, no hay {nombre} para tus miembros."))
    assert r["avisos"] and "SÍ se puede dibujar" in r["avisos"][0]["aviso"]


@pytest.mark.asyncio
async def test_ofrecer_un_grafico_parecido_no_es_negarlo(doc_lab):
    """«No hay velas japonesas; lo más parecido es X» nombra X como alternativa: no se le pide agregarlo (banco2 con la IA real)."""
    g = next(sec["graficos_posibles"][0] for sec in describir_pantalla(doc_lab)["secciones"] if sec.get("graficos_posibles"))
    nombre = re.sub(r" \d+ %", "", re.search(r"\((.*)\)", g).group(1)).lower()
    r, modelo = await correr(doc_lab, "quiero un gráfico de velas japonesas",
                             dice(f"No hay gráfico de velas japonesas. ¿Quieres {nombre}, que es lo más parecido?"))
    assert r["avisos"] == [] and len(modelo.recibidos) == 1 and r["cambios"] == []


@pytest.mark.asyncio
async def test_con_pestana_abierta_los_bloques_del_inicio_cambian_de_nombre(doc_lab):
    # «aquí pon…» mirando Miembros llamaba cambiar_visual sobre b0 del inicio (1 de 3 en la línea base; el error nombraba b1).
    # El estado sigue trayendo esos bloques, con un nombre que dice que no se ven ahora.
    from test_agente_diseno import ModeloFalso
    modelo = ModeloFalso(dice("Hola."))
    await agente.responder(doc_lab, "aquí pon arriba un resumen", [], AHORA, False, modelo=modelo, seccion="Miembros")
    estado = __import__("json").loads(modelo.recibidos[0][0].content.split("Estado de la pantalla (JSON):\n", 1)[1])
    assert "bloques" not in estado
    assert estado["bloques_del_inicio_no_se_ven_ahora"][0]["id"] == "b0"
    assert estado["pestana_abierta"] != "inicio"


@pytest.mark.asyncio
async def test_negar_otra_cosa_no_niega_la_dona_pedida(doc_lab):
    # «tiene dona, pero no hay nube» no es negar la dona (el aviso empujaba a agregar y quitar).
    r, modelo = await correr(doc_lab, "agrega una dona por estado y una nube de palabras de los planes",
                             dice("La sección tiene gráfica de dona, pero no hay nube de palabras."))
    assert r["avisos"] == [] and len(modelo.recibidos) == 1


@pytest.mark.asyncio
async def test_el_sustituto_no_deshace_la_pieza_que_si_pidieron(doc_lab):
    # Compuesto: la dona se queda aunque la respuesta ofrezca una alternativa para la nube.
    r, _ = await correr(doc_lab, "agrega una dona por estado y una nube de palabras de los planes",
                        dice("", llamar("agregar_bloque", seccion="l_miembros", vista="grafico",
                                        opciones={"tipo": "dona", "estado": "estado"})),
                        dice("Agregué la dona por estado. La nube de palabras no existe; lo más parecido sería barras. ¿La quieres?"))
    assert any((b.get("opciones") or {}).get("tipo") == "dona" for b in r["doc"]["inicio"])
    assert not any("sustituto" in a["aviso"].lower() for a in r["avisos"])


@pytest.mark.asyncio
async def test_sustituto_impuesto_revierte_el_doc(doc_lab):
    inicio = copy.deepcopy(doc_lab["inicio"])
    r, _ = await correr(doc_lab, "mapa de calor por ciudad",
                        dice("", llamar("agregar_bloque", seccion="l_miembros", vista="tabla")),
                        dice("No hay forma de hacer el mapa; puse una lista como alternativa."),
                        dice("Eso no existe todavía. ¿Quieres una lista en su lugar?"))
    assert r["doc"]["inicio"] == inicio
    assert any("sustituto" in a["aviso"].lower() for a in r["avisos"])


@pytest.mark.asyncio
async def test_sin_bandera_no_cambia_herramientas(doc, monkeypatch):
    monkeypatch.delenv("CRM_DISENO", raising=False)
    _, modelo = await correr(doc, "hola", dice("Hola."))
    assert "agregar_bloque" not in modelo.ataduras[0]["nombres"]
    assert modelo.ataduras[0]["nombres"] == [h["function"]["name"] for h in agente.HERRAMIENTAS]
