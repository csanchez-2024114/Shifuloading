"""Toma de diseño: el port a Python da lo mismo que `edicion.js` paso a paso (fixtures de `laboratorio/servidor/grabar-toma.mjs`), y los
comportamientos que mide `laboratorio/pruebas/banco_toma.py`, sin IA: se llaman las herramientas con los argumentos que mandaría el modelo.

Lo que no es de la toma se inyecta: los gráficos posibles salen del catálogo real (plantillas.py); la revisión de vistas es una copia de
`revisarVista` sobre `plantillas.vistas()`, y el acomodo y la validación de cada construir son los que grabó el laboratorio.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from assistant.packs.crm import plantillas as catalogo_crm
from assistant.packs.crm import toma as tm
from assistant.packs.crm.marca import FUENTES
from assistant.packs.crm.validar import revisar_vista

LAB = Path(__file__).parent / "fixtures" / "lab"
GUIONES = json.loads((LAB / "toma_guiones.json").read_text(encoding="utf-8"))
CAT = json.loads((LAB / "toma_catalogo.json").read_text(encoding="utf-8"))
AHORA_MS = int(datetime(2026, 10, 16, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)  # el Date.now() fijo del grabador


# ───────── Lo inyectado (en el CRM lo dan secciones_v, graficos y validar) ─────────

def test_las_tipografias_son_las_grabadas_del_laboratorio():
    assert list(FUENTES) == CAT["fuentes"]


def catalogo(pid: str) -> tm.Catalogo:
    """El catálogo real del CRM (plantillas.py: secciones, compatibles y opciones por defecto; validar.py: revisar_vista; marca.py: las
    tipografías permitidas)."""
    return tm.Catalogo(secciones=catalogo_crm.plantilla_por_id(pid)["secciones"], compatibles=catalogo_crm.compatibles,
                       opciones_por_defecto=catalogo_crm.opciones_por_defecto, revisar_vista=revisar_vista,
                       graficos=catalogo_crm.graficos(), fuentes=list(FUENTES))


def doc_inicial():
    return {"inicio": copy.deepcopy(CAT["inicio_inicial"])}


def construir(doc, esperado=None, validar=None):
    """construir_desde_ficha con el acomodo y la validación que grabó el laboratorio para ese paso."""
    def acomodar(bs):
        if esperado is None:
            return bs
        assert bs == esperado["antes_de_acomodar"]
        return copy.deepcopy(esperado["inicio"])

    def validar_grabado(d):
        if esperado is not None:
            assert d["inicio"] == esperado["antes_de_acomodar"]
        return esperado["errores"] if esperado is not None else []

    return tm.construir_desde_ficha(doc, acomodar, validar or validar_grabado, CAT["fuentes"], ahora_ms=AHORA_MS)


def correr(guion):
    """Repite un guion del laboratorio en Python y compara cada paso. Devuelve el documento final."""
    cat = catalogo(guion["plantilla"])
    doc = doc_inicial()
    for i, (paso, esperado) in enumerate(zip(guion["pasos"], guion["salidas"])):
        donde = f"{guion['caso']} · paso {i + 1} ({paso['paso']} {paso.get('nombre') or paso.get('texto') or ''})"
        if paso["paso"] == "preparar":
            r = tm.preparar_turno_toma(doc, paso["texto"])
            doc = r["doc"]
            assert {k: r[k] for k in ("aviso", "digresion", "construir")} == {k: esperado[k] for k in ("aviso", "digresion", "construir")}, donde
        elif paso["paso"] == "herramienta" and paso["nombre"] not in tm.NOMBRES_TOMA:
            # Una herramienta de pantalla: de la toma solo es el cerco (si la frena o la deja pasar); lo que haga no es de este módulo.
            assert tm.bloqueo_en_toma(doc, paso["nombre"], paso.get("digresion", False)) == (None if esperado["ok"] else esperado["resultado"]), donde
            continue
        elif paso["paso"] == "herramienta":
            r = tm.ejecutar_toma(doc, paso["nombre"], paso["args"], cat, texto=paso.get("texto", ""), digresion=paso.get("digresion", False))
            doc = r["doc"]
            assert (r["ok"], r["resultado"]) == (esperado["ok"], esperado["resultado"]), donde
        elif paso["paso"] == "senal":
            doc, senal = tm.senal_toma_tras_vuelta(doc, cat)
            assert senal == esperado["senal"], donde
        elif paso["paso"] == "resumen":
            assert tm.resumen_de_toma(doc, cat) == esperado["resumen"], donde
            assert tm.tarjeta_toma(doc, cat) == esperado["tarjeta"], donde
            assert tm.faltantes_toma(doc) == esperado["faltantes"], donde
            assert tm.contexto_toma(doc, cat) == esperado["contexto"], donde
            continue
        elif paso["paso"] == "construir":
            r = construir(doc, esperado)
            doc = r["doc"]
            assert r["errores"] == esperado["errores"], donde
            assert doc["inicio"] == esperado["inicio"], donde
            assert (doc.get("marca") or {}) == (esperado["marca"] or {}), donde
        assert doc.get("toma") == esperado["toma"], donde
    return doc


@pytest.mark.parametrize("guion", GUIONES, ids=[g["caso"] for g in GUIONES])
def test_igual_que_el_laboratorio(guion):
    correr(guion)


def test_los_guiones_cubren_todas_las_herramientas():
    usadas = {p["nombre"] for g in GUIONES for p in g["pasos"] if p["paso"] == "herramienta"}
    assert set(tm.NOMBRES_TOMA) <= usadas
    assert sum(len(g["pasos"]) for g in GUIONES) >= 100


# ───────── Esquemas y conjuntos literales ─────────

def test_esquemas_literales_del_laboratorio():
    assert tm.TOMA_HERRAMIENTAS == CAT["herramientas"]
    assert [h["function"]["name"] for h in tm.TOMA_HERRAMIENTAS] == list(tm.NOMBRES_TOMA)


def test_el_catalogo_grabado_es_el_compartido():
    for pid, p in CAT["plantillas"].items():
        assert catalogo_crm.plantilla_por_id(pid)["secciones"] == p["secciones"]
    assert catalogo_crm.vistas() == CAT["vistas"]


def test_bloqueadas_iguales_al_laboratorio():
    assert tm.HERRAMIENTAS_BLOQUEADAS_EN_TOMA == set(CAT["bloqueadas"])


def test_uid_como_date_now_en_base_36():
    assert tm._base36(AHORA_MS) == CAT["uid_base"]


# ───────── Los comportamientos de banco_toma.py, sin IA ─────────

def guion(nombre):
    return next(g for g in GUIONES if g["caso"] == nombre)


def fbloques(doc):
    return ((doc.get("toma") or {}).get("ficha") or {}).get("bloques", [])


def test_banco_pedir_anotar_cambiar_y_confirmar():
    cat = catalogo("membresias")
    doc = tm.preparar_turno_toma(doc_inicial(), "Diséñame un inicio nuevo para controlar mis pagos")["doc"]
    assert doc["toma"]["activa"] and doc["toma"]["fase"] == "juntando" and doc["toma"]["ficha"]["objetivo"] == "controlar mis pagos"
    # «Quiero un resumen de pagos y una dona de los estados de los miembros»: el modelo anota dos bloques
    texto = "Quiero un resumen de pagos y una dona de los estados de los miembros"
    assert tm.piezas_nombradas(texto) == {"resumen", "gráfica"}
    for args in ({"que": "resumen", "seccion": "Pagos"}, {"que": "grafica", "seccion": "Miembros", "grafico": "dona"}):
        r = tm.ejecutar_toma(doc, "anotar_bloque", args, cat, texto=texto)
        assert r["ok"], r["resultado"]
        doc = r["doc"]
    doc, senal = tm.senal_toma_tras_vuelta(doc, cat)
    assert len(fbloques(doc)) >= 2 and doc["toma"]["fase"] == "confirmando" and senal.startswith("RESUMEN")
    assert tm.respuesta_confirmando(doc, cat).startswith("Así quedaría tu inicio: un inicio para controlar mis pagos.")
    # «No, mejor barras en vez de dona»
    p = tm.preparar_turno_toma(doc, "No, mejor barras en vez de dona")
    doc = p["doc"]
    assert p["aviso"] == tm.AVISO_AJUSTE and doc["toma"]["fase"] == "juntando" and doc["toma"]["rechazo"] is True
    doc = tm.ejecutar_toma(doc, "quitar_de_ficha", {"numero": 2}, cat)["doc"]
    doc = tm.ejecutar_toma(doc, "anotar_bloque", {"que": "grafica", "seccion": "miembros", "grafico": "barras"}, cat)["doc"]
    doc, _ = tm.senal_toma_tras_vuelta(doc, cat)
    assert not any((b.get("opciones") or {}).get("tipo") == "dona" for b in fbloques(doc))
    assert any("barras" in json.dumps(b) for b in fbloques(doc))
    # «Sí»: el código arma el inicio
    p = tm.preparar_turno_toma(doc, "Sí")
    assert p["construir"] is True
    r = construir(p["doc"], guion("banco: pedir, anotar, cambiar y confirmar")["salidas"][11])
    doc = r["doc"]
    assert not doc["toma"]["activa"] and len(doc["inicio"]) >= 2
    assert any(b["vista"] == "grafico" and b["opciones"].get("tipo") == "barras" for b in doc["inicio"])
    assert tm.respuesta_construida(r).startswith("¡Listo! Armé tu inicio nuevo con 2 bloques")


def test_banco_abandonar_sin_cambiar_nada():
    # «rediseñar» no lo detecta el código (solo «rediseña»): la abre el modelo con abrir_toma
    doc = tm.preparar_turno_toma(doc_inicial(), "Quiero rediseñar mi inicio")["doc"]
    assert not doc["toma"]["activa"]
    doc = tm.ejecutar_toma(doc, "abrir_toma", {}, catalogo("membresias"))["doc"]
    assert doc["toma"]["activa"]
    p = tm.preparar_turno_toma(doc, "mejor olvídalo, déjalo como está")
    assert not p["doc"]["toma"]["activa"] and [b["uid"] for b in p["doc"]["inicio"]] == ["b0"]
    assert p["aviso"] == tm.AVISO_ABANDONO


def test_banco_varias_cosas_en_un_mensaje():
    texto = "diséñame un inicio con una lista de pagos, un tablero de miembros por estado y lo que vence"
    assert tm.piezas_nombradas(texto) == {"lista", "tablero", "por vencer"}
    doc = tm.preparar_turno_toma(doc_inicial(), texto)["doc"]
    # Si el modelo anota menos de lo que nombró, el código le pide las que faltan
    assert tm.aviso_piezas_faltantes(doc, texto, 1) == ("[Aviso del código] En este mensaje pidió 3 cosas (lista, tablero, por vencer) y anotaste 1. "
                                                       "Anota con anotar_bloque las que faltan.")
    assert tm.aviso_piezas_faltantes(doc, texto, 3) is None
    final = correr(guion("banco: varias cosas en un mensaje"))
    assert [b["vista"] for b in final["inicio"]] == ["tabla", "tablero", "vencimientos"]


def test_banco_digresion_en_medio_de_la_toma():
    cat = catalogo("membresias")
    doc = tm.preparar_turno_toma(doc_inicial(), "Diséñame un inicio nuevo para mis miembros")["doc"]
    p = tm.preparar_turno_toma(doc, "oye, ¿qué hora es en Guatemala?")
    assert p["digresion"] is True and p["doc"]["toma"]["activa"]
    for nombre, args in (("anotar_nota", {"texto": "la hora"}), ("anotar_ficha", {"campo": "objetivo", "valor": "la hora"})):
        r = tm.ejecutar_toma(p["doc"], nombre, args, cat, texto="oye, ¿qué hora es en Guatemala?", digresion=True)
        assert not r["ok"] and "digresión" in r["resultado"]
    assert not fbloques(p["doc"])


def test_banco_pedido_vago_abre_la_ficha_y_no_inventa_piezas():
    texto = "Diséñame un inicio nuevo para mis miembros"
    entrada = doc_inicial()
    doc = tm.preparar_turno_toma(entrada, texto)["doc"]
    assert doc["toma"]["activa"] and not fbloques(doc)
    assert tm.piezas_nombradas(texto) == set()
    # El modelo intenta anotar un resumen que nadie pidió: el código lo frena y le pide preguntar
    assert tm.error_anotar_sin_piezas("anotar_bloque", False, doc, texto) == tm.ERROR_SIN_PIEZAS
    assert tm.error_anotar_sin_piezas("anotar_bloque", True, doc, texto) is None  # la ficha ya estaba abierta antes de este mensaje
    _, senal = tm.senal_toma_tras_vuelta(doc, catalogo("membresias"))
    assert senal.startswith("FALTA: bloques")


def test_banco_cambio_puntual_no_abre_la_toma():
    p = tm.preparar_turno_toma(doc_inicial(), "haz el resumen más chico")
    assert not p["doc"]["toma"]["activa"] and p["aviso"] is None
    assert tm.bloqueo_en_toma(p["doc"], "cambiar_tamano") is None


# ───────── Cerco y pureza ─────────

def test_con_la_ficha_abierta_las_herramientas_de_pantalla_esperan():
    doc = tm.preparar_turno_toma(doc_inicial(), "rehaz mi inicio")["doc"]
    assert tm.bloqueo_en_toma(doc, "agregar_bloque").startswith("ERROR: primero termina")
    assert tm.bloqueo_en_toma(doc, "agregar_bloque", digresion=True) is None
    assert tm.bloqueo_en_toma(doc, "anotar_bloque") is None


def test_las_herramientas_de_anotar_solo_se_ven_con_la_ficha_abierta():
    cerrada = tm.asegurar_toma(doc_inicial())
    abierta = tm.preparar_turno_toma(doc_inicial(), "rehaz mi inicio")["doc"]
    assert [h["function"]["name"] for h in tm.herramientas_para(cerrada)] == ["abrir_toma"]
    assert len(tm.herramientas_para(abierta)) == 6


def test_no_cambia_el_documento_que_recibe():
    cat = catalogo("membresias")
    doc = tm.preparar_turno_toma(doc_inicial(), "Diséñame un inicio nuevo para controlar mis pagos")["doc"]
    foto = copy.deepcopy(doc)
    tm.ejecutar_toma(doc, "anotar_bloque", {"que": "resumen", "seccion": "pagos"}, cat)
    d2 = tm.ejecutar_toma(doc, "anotar_bloque", {"que": "resumen", "seccion": "pagos"}, cat)["doc"]
    tm.senal_toma_tras_vuelta(d2, cat)
    tm.preparar_turno_toma(d2, "no, mejor otra cosa")
    assert doc == foto and d2["toma"]["fase"] == "juntando"


def test_construir_con_errores_no_cambia_nada():
    cat = catalogo("membresias")
    doc = tm.preparar_turno_toma(doc_inicial(), "Diséñame un inicio nuevo para controlar mis pagos")["doc"]
    doc = tm.ejecutar_toma(doc, "anotar_bloque", {"que": "lista", "seccion": "pagos"}, cat)["doc"]
    r = tm.construir_desde_ficha(doc, lambda bs: bs, lambda d: ["Inicio, bloque 1: la sección «pagos» no existe."], CAT["fuentes"], ahora_ms=AHORA_MS)
    assert r["errores"] and r["doc"] == doc
    assert tm.respuesta_construida(r) == "No pude armarlo: Inicio, bloque 1: la sección «pagos» no existe. Dime qué cambio y lo ajusto."


def test_construir_aplica_la_marca_de_la_ficha():
    final = correr(guion("bordes de anotar_ficha, notas y marca"))
    assert final["marca"] == {"primario": "#1e40af", "secundario": "#F59E0B", "fuenteTitulos": "Poppins", "fuenteTexto": "Poppins"}
