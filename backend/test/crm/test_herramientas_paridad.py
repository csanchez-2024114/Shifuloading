"""Paridad de las herramientas de diseño con el laboratorio: los escenarios de los bancos (banco2, banco_pestanas, banco_ficha) que
grabó `laboratorio/servidor/grabar-herramientas.mjs` con `ejecutar` de edicion.js, corridos con edicion.py sobre el documento equivalente.
Se compara el TEXTO que lee el modelo, cómo quedan inicio, pestañas, marca y secciones, la pestaña abierta, la etiqueta y el estado que
se le describe al modelo. Las diferencias a propósito están en DIFERENCIAS, cada una con su porqué (ver también edicion.py)."""
import copy
import json
from pathlib import Path

import pytest

from app.crm import edicion, secciones_v
from app.crm.pantalla import describir_pantalla
from lab_doc import a_lab, args_de_lab, doc_de_lab, uids_en_orden

LAB = Path(__file__).parent / "fixtures" / "lab"
CASOS = json.loads((LAB / "herramientas_casos.json").read_text(encoding="utf-8"))
ESQUEMAS = json.loads((LAB / "herramientas_esquemas.json").read_text(encoding="utf-8"))

# (escenario, número de paso desde 1) → (ok y texto que da el CRM, con el vocabulario del laboratorio; por qué difiere; ¿el estado sigue
# igual al del laboratorio?). Si no sigue igual, el resto del escenario ya no se compara.
_ASI = "Así se ve ahora: b0 (kpis) → fila 1, ancho completo; b1 (vencimientos) → fila 2, izquierda; b2 (grafica) → fila 2, derecha."
DIFERENCIAS: dict[tuple[str, int], tuple[bool, str, str, bool]] = {
    ("quitar sección", 1): (
        True, f"Sección «Pagos» quitada del menú con sus registros (se puede deshacer). También se quitaron sus bloques del inicio. {_ASI}",
        "Una lista se quita con estructura.lista_eliminar (borra sus registros); el laboratorio solo la ocultaba. El texto dice la verdad.", True),
    ("quitar la sección de las piezas del inicio", 1): (
        True, "Sección «Miembros» quitada del menú con sus registros (se puede deshacer). También se quitaron sus bloques del inicio. Así se ve ahora: .",
        "El laboratorio valida contra el inicio POR DEFECTO de la plantilla (que usa Miembros) aunque no esté en pantalla; el CRM no tiene "
        "ese inicio: valida las secciones y quita los bloques reales, como dice el texto.", False),
    ("quitar un campo libre", 3): (
        True, f"Campo «Plan» quitado de «Miembros» con sus datos (se puede deshacer). {_ASI}",
        "Igual que arriba: el laboratorio lo frena porque «plan» lo usa un bloque del inicio por defecto de la plantilla, que no está en "
        "pantalla. En el CRM se quita (con estructura.campo_eliminar, que borra sus valores) y se limpia de la ficha y la tarjeta.", False),
    ("agregar campos hasta el máximo", 4): (
        True, f"Campo «Nota» (texto) agregado a «Miembros». {_ASI}",
        "Tope único de campos por sección (`topes.CAMPOS_POR_SECCION` = 20, punto 48): el laboratorio sigue con 8. Con 8, en la prueba "
        "manual el chat quitó «Técnico» a un taller para poder agregar «Estado». El tope de 20 se prueba en test_topes.py.", False),
}


def _secciones(doc):
    return [{"id": s["id"], "titulo": s["titulo"], "campos": s["campos"], "vista": s["vista"], "opciones": s.get("opciones") or {},
             **({"ficha": s["ficha"]} if s.get("ficha") else {}), **({"tarjeta": s["tarjeta"]} if s.get("tarjeta") else {})}
            for s in secciones_v.secciones_de(doc)]


def _marca(m, py):
    m = copy.deepcopy(m)
    if py and m.pop("logo_id", None):
        m["logo"] = "(logo)"
    elif not py and m.get("logo"):
        m["logo"] = "(logo)"
    return m


def correr(caso):
    """Los pasos del escenario en Python: [(salida_python_en_vocabulario_lab, salida_js)]."""
    doc, ctx = doc_de_lab(caso["plantilla"], caso["estado"])
    vista = ctx["vista"]
    uids_py, uids_js = {}, {}
    pares = []
    for paso, js in zip(caso["pasos"], caso["salidas"]):
        r = edicion.ejecutar(doc, paso["nombre"], args_de_lab(paso["args"]), {**paso["contexto"], "vista": vista})
        doc, vista = r["doc"], r["vista"]
        py = {"ok": r["ok"], "resultado": r["resultado"], "etiqueta": r["etiqueta"], "vista": vista, "bloques": doc.get("inicio") or [],
              "paginas": doc.get("paginas") or {}, "marca": _marca(doc.get("marca") or {}, True), "secciones": _secciones(doc)}
        if "describir" in js:
            py["describir"] = describir_pantalla(doc, vista)
        py = a_lab(py, uids_py)
        esperado = json.loads(uids_en_orden(json.dumps({**js, "marca": _marca(js["marca"], False)}, ensure_ascii=False), uids_js))
        pares.append((py, esperado))
    return pares


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso"] for c in CASOS])
def test_paridad_con_el_laboratorio(caso):
    for i, (py, js) in enumerate(correr(caso), 1):
        donde = f"{caso['caso']} · paso {i} ({caso['pasos'][i - 1]['nombre']})"
        dif = DIFERENCIAS.get((caso["caso"], i))
        if dif:
            assert (py["ok"], py["resultado"]) == dif[:2], donde
            if not dif[3]:
                return
            py, js = {**py, "resultado": None}, {**js, "resultado": None}
        for k in ("ok", "resultado", "etiqueta", "vista", "bloques", "paginas", "marca", "secciones", "describir"):
            if k in js:
                assert py[k] == js[k], f"{donde}: {k}"
        if "describir" in js:  # lo que se le manda al modelo: también el ORDEN de las claves (el JSON del prompt, byte a byte)
            assert json.dumps(py["describir"], ensure_ascii=False) == json.dumps(js["describir"], ensure_ascii=False), donde


def test_las_diferencias_existen():
    nombres = {c["caso"]: len(c["pasos"]) for c in CASOS}
    assert all(c in nombres and 1 <= i <= nombres[c] for c, i in DIFERENCIAS)


# ───────── Esquemas ─────────

def test_esquemas_literales_del_laboratorio():
    assert json.dumps(edicion.HERRAMIENTAS, ensure_ascii=False) == json.dumps(ESQUEMAS["HERRAMIENTAS"], ensure_ascii=False)
    assert edicion.HERR_ENLACE == ESQUEMAS["HERR_ENLACE"]


@pytest.mark.parametrize("para", ESQUEMAS["para"], ids=lambda p: f"toma={p['toma']} imagen={p['imagen']}")
def test_herramientas_para_igual_que_chat_js(para):
    doc = {"toma": {"activa": True}} if para["toma"] else {}
    hs = edicion.herramientas_para(doc, "data:image/png;base64,x" if para["imagen"] else None)
    assert [h["function"]["name"] for h in hs] == para["nombres"]
