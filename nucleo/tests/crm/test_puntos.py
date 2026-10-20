"""Puntos de deshacer (contrato §3): qué cambió lo mide el código; deshacer es selectivo y, en los datos, a 3 vías."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from assistant.packs.crm import estructura as est
from assistant.packs.crm import operaciones as op
from assistant.packs.crm import puntos as pt
from assistant.packs.crm.generador import generar
from assistant.packs.crm.operaciones import ErrorCrm

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)
BRIEF = {"nombre": "Gimnasio Fuerte", "rubro": "otro"}


class Historia:
    """Un CRM con su lista de puntos: cada paso es lo que haría una ruta (aplicar + con_punto)."""

    def __init__(self, doc):
        self.doc = est.normalizar(doc)
        self.puntos: list[dict] = []

    def paso(self, texto, cambiar):
        nuevo = cambiar(self.doc)
        self.doc, p = pt.con_punto(self.doc, nuevo, texto, AHORA)
        if p:
            self.puntos.append(p)
        return p

    def deshacer(self, n=None):
        r = pt.deshacer(self.doc, self.puntos, n, AHORA)
        self.doc, self.puntos = r["doc"], r["puntos"]
        return r


@pytest.fixture
def h():
    d = est.lista_crear(generar("u1", BRIEF, AHORA), "Miembros", [{"nombre": "Nombre"}, {"nombre": "Plan", "tipo": "estado", "opciones": ["Básico", "Premium"]}], AHORA)
    return Historia(d)


def _lista(doc):
    l = doc["listas"][0]
    return l["id"], {c["nombre"]: c["id"] for c in l["campos"]}


def _nombres(doc):
    lid, c = _lista(doc)
    return {r["valores"][c["Nombre"]]: r["valores"].get(c["Plan"]) for r in doc["listas"][0]["registros"]}


def _agregar(nombre, plan):
    def f(d):
        lid, c = _lista(d)
        return est.registro_agregar(d, lid, {c["Nombre"]: nombre, c["Plan"]: plan}, AHORA)
    return f


def _editar_plan(nombre, plan):
    def f(d):
        lid, c = _lista(d)
        rid = next(r["id"] for r in d["listas"][0]["registros"] if r["valores"][c["Nombre"]] == nombre)
        return est.registro_actualizar(d, lid, rid, {c["Plan"]: plan}, AHORA)
    return f


def _borrar(nombre):
    def f(d):
        lid, c = _lista(d)
        rid = next(r["id"] for r in d["listas"][0]["registros"] if r["valores"][c["Nombre"]] == nombre)
        return est.registro_eliminar(d, lid, rid, AHORA)
    return f


# ───────── con_punto ─────────

def test_con_punto_mide_solo_lo_que_cambio(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    p = h.puntos[-1]
    lid, _ = _lista(h.doc)
    assert p["n"] == 1 and p["cambio"] == ["datos"] and list(p["foto"]) == ["datos"]
    assert list(p["foto"]["datos"]) == [lid] and p["foto"]["datos"][lid] == []  # solo la sección que cambió, como estaba ANTES
    assert h.doc["puntos_n"] == 1 and p["antes_de"] == "agregó a Carlos" and p["hora"].startswith("2026-10-13T15:00")


def test_las_categorias(h):
    p = h.paso("marca", lambda d: {**d, "marca": {"primario": "#0a7"}})
    assert p["cambio"] == ["marca"] and p["foto"] == {"marca": {}}
    p = h.paso("bloques", lambda d: {**d, "inicio": d["inicio"][:1]})
    assert p["cambio"] == ["bloques"] and len(p["foto"]["bloques"]["inicio"]) == 2 and p["foto"]["bloques"]["paginas"] == {}
    p = h.paso("etapas", lambda d: est.etapas_definir(d, ["Prueba", "Activo"], AHORA))
    assert p["cambio"] == ["estructura"] and set(p["foto"]["estructura"]) == {"listas_meta", "etapas", "campos_contacto", "ocultas", "secciones"}
    assert all("registros" not in l for l in p["foto"]["estructura"]["listas_meta"])
    h.paso("contacto", lambda d: op.contactos_crear(d, [{"n": "Ana"}], "x", ahora=AHORA))
    p = h.paso("etapas con contactos", lambda d: est.etapas_definir(d, ["Uno", "Dos", "Tres"], AHORA))
    assert p["cambio"] == ["estructura", "datos"] and list(p["foto"]["datos"]) == ["contactos"]  # reubicó a Ana de etapa
    assert [x["n"] for x in h.puntos] == [1, 2, 3, 4, 5]


def test_sin_cambios_que_se_puedan_deshacer_no_hay_punto(h):
    d = h.doc
    nuevo = op.automatizacion_fijar(d, d["automatizaciones"][0]["id"], not d["automatizaciones"][0]["on"], AHORA) if d["automatizaciones"] else copy.deepcopy(d)
    out, p = pt.con_punto(d, nuevo, "automatización", AHORA)
    assert p is None and out is nuevo


def test_las_fechas_sin_zona_de_mongo_no_cuentan_como_cambio(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    como_mongo = copy.deepcopy(h.doc)
    for r in como_mongo["listas"][0]["registros"]:
        r["creado"] = r["creado"].astimezone(timezone.utc).replace(tzinfo=None)
    _, p = pt.con_punto(como_mongo, copy.deepcopy(h.doc), "nada", AHORA)
    assert p is None


def test_el_texto_se_corta_a_80(h):
    p = h.paso("x" * 200, _agregar("Carlos", "Básico"))
    assert len(p["antes_de"]) == 80


# ───────── deshacer: datos a 3 vías (el caso de Rosa y Carlos) ─────────

def test_rosa_y_carlos(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    h.paso("agregó a Rosa", _agregar("Rosa", "Básico"))
    h.paso("cambió el plan de Rosa", _editar_plan("Rosa", "Premium"))
    h.paso("borró a Carlos", _borrar("Carlos"))
    assert _nombres(h.doc) == {"Rosa": "Premium"}

    r = h.deshacer(3)  # «deshaz lo que le cambié a Rosa»: Carlos sigue borrado
    assert _nombres(h.doc) == {"Rosa": "Básico"}
    assert r["deshechos"] == [3] and [x["n"] for x in h.puntos] == [1, 2, 4]
    assert r["texto"] == "Deshecho el pedido 3 «cambió el plan de Rosa» (los registros quedaron como antes). Lo demás quedó igual."

    r = h.deshacer(4)  # «deshaz el borrado»: Carlos vuelve, y Rosa NO revive su plan Premium
    assert _nombres(h.doc) == {"Carlos": "Básico", "Rosa": "Básico"}
    assert [r["valores"] for r in h.doc["listas"][0]["registros"]][1][_lista(h.doc)[1]["Nombre"]] == "Carlos"  # en su lugar de antes
    assert r["deshechos"] == [4] and [x["n"] for x in h.puntos] == [1, 2]


def test_si_uno_posterior_toco_lo_mismo_se_deshace_en_cadena_y_se_dice(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    h.paso("agregó a Rosa", _agregar("Rosa", "Básico"))
    h.paso("cambió el plan de Rosa", _editar_plan("Rosa", "Premium"))
    r = h.deshacer(2)  # quitar a Rosa no puede conservar el cambio de su plan
    assert _nombres(h.doc) == {"Carlos": "Básico"}
    assert r["deshechos"] == [2, 3] and [x["n"] for x in h.puntos] == [1]
    assert "También se deshizo «cambió el plan de Rosa» porque cambiaba lo mismo." in r["texto"]


def test_deshacer_sin_n_es_el_ultimo_y_deja_evento(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    h.paso("agregó a Rosa", _agregar("Rosa", "Básico"))
    r = h.deshacer()
    assert _nombres(h.doc) == {"Carlos": "Básico"} and r["deshechos"] == [2]
    assert h.doc["eventos"][0]["t"] == "Deshiciste «agregó a Rosa»"


def test_no_hay_que_deshacer(h):
    with pytest.raises(ErrorCrm) as e:
        pt.deshacer(h.doc, [], None, AHORA)
    assert e.value.estado == 404
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    with pytest.raises(ErrorCrm) as e:
        pt.deshacer(h.doc, h.puntos, 9, AHORA)
    assert e.value.estado == 404 and "1 «agregó a Carlos»" in e.value.mensaje


def test_deshacer_es_puro(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    doc, puntos = copy.deepcopy(h.doc), copy.deepcopy(h.puntos)
    pt.deshacer(h.doc, h.puntos, None, AHORA)
    assert h.doc == doc and h.puntos == puntos


def test_contactos_y_tareas_tambien(h):
    manana = (AHORA + timedelta(days=1)).date().isoformat()
    h.paso("agregó a Ana", lambda d: op.contactos_crear(d, [{"n": "Ana"}], "x", ahora=AHORA))
    h.paso("agregó a Luis", lambda d: op.contactos_crear(d, [{"n": "Luis"}], "x", ahora=AHORA))
    h.paso("tarea", lambda d: op.tareas_crear(d, "Llamar", AHORA, manana))
    tid = h.doc["tareas"]["porHacer"][0]["id"]
    h.paso("movió la tarea", lambda d: op.tareas_mover(d, tid, "hecho"))
    h.deshacer(4)
    assert h.doc["tareas"]["porHacer"][0]["id"] == tid and h.doc["tareas"]["hecho"] == []
    h.deshacer(1)  # Ana se va; Luis (después) se queda
    assert [c["n"] for c in h.doc["contactos"]] == ["Luis"] and h.doc["total_contactos"] == 1


# ───────── deshacer: las otras categorías ─────────

def test_deshacer_la_marca_no_toca_los_datos(h):
    h.paso("marca", lambda d: {**d, "marca": {"primario": "#0a7"}})
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    r = h.deshacer(1)
    assert h.doc["marca"] == {} and _nombres(h.doc) == {"Carlos": "Básico"} and r["deshechos"] == [1]
    assert r["texto"].startswith("Deshecho el pedido 1 «marca» (los colores y la marca quedaron como antes).")


def test_deshacer_bloques_arrastra_los_bloques_posteriores(h):
    inicio = copy.deepcopy(h.doc["inicio"])
    h.paso("quitó la tabla", lambda d: {**d, "inicio": d["inicio"][:1]})
    h.paso("agrandó el resumen", lambda d: {**d, "inicio": [{**d["inicio"][0], "ancho": 6}]})
    h.paso("marca", lambda d: {**d, "marca": {"primario": "#0a7"}})
    r = h.deshacer(1)
    assert h.doc["inicio"] == inicio and h.doc["marca"] == {"primario": "#0a7"}
    assert r["deshechos"] == [1, 2] and [x["n"] for x in h.puntos] == [3]


def test_deshacer_borrar_una_seccion_la_trae_con_sus_registros(h):
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    lid, _ = _lista(h.doc)
    h.paso("creó Pagos", lambda d: est.lista_crear(d, "Pagos", None, AHORA))
    h.paso("borró Miembros", lambda d: est.lista_eliminar(d, lid, AHORA))
    assert [l["nombre"] for l in h.doc["listas"]] == ["Pagos"]
    r = h.deshacer(3)
    assert [l["nombre"] for l in h.doc["listas"]] == ["Miembros", "Pagos"] and _nombres(h.doc) == {"Carlos": "Básico"}
    assert r["deshechos"] == [3]


def test_deshacer_un_registro_de_una_seccion_borrada_despues_la_trae_de_vuelta(h):
    lid, _ = _lista(h.doc)
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    h.paso("borró Miembros", lambda d: est.lista_eliminar(d, lid, AHORA) if len(d["listas"]) else d)
    r = h.deshacer(1)  # lo posterior (borrar la sección) tocó lo mismo: se deshace en cadena, y la sección vuelve sin Carlos
    assert [l["id"] for l in h.doc["listas"]] == [lid] and _nombres(h.doc) == {}
    assert r["deshechos"] == [1, 2] and "«borró Miembros»" in r["texto"]


def test_deshacer_una_estructura_vieja_arrastra_lo_que_se_hizo_en_una_seccion_que_no_existia(h):
    h.paso("creó Pagos", lambda d: est.lista_crear(d, "Pagos", None, AHORA))
    pid = h.doc["listas"][1]["id"]
    campo = h.doc["listas"][1]["campos"][0]["id"]
    h.paso("agregó un pago", lambda d: est.registro_agregar(d, pid, {campo: "Enero"}, AHORA))
    h.paso("agregó a Carlos", _agregar("Carlos", "Básico"))
    r = h.deshacer(1)
    assert [l["nombre"] for l in h.doc["listas"]] == ["Miembros"] and _nombres(h.doc) == {"Carlos": "Básico"}
    assert r["deshechos"] == [1, 2] and [x["n"] for x in h.puntos] == [3]


def test_quitar_una_importacion_y_deshacerlo_la_devuelve(h):
    lid, c = _lista(h.doc)
    h.paso("importó", lambda d: est.registros_agregar_lote(d, lid, [{c["Nombre"]: "A"}, {c["Nombre"]: "B"}], AHORA, {"id": "lote01", "nombre": "Socios.xlsx"})[0])
    h.paso("quitó la importación", lambda d: est.importacion_quitar(d, lid, "lote01", AHORA))
    assert h.puntos[-1]["cambio"] == ["datos"]  # las importaciones van con los registros, no con la estructura
    h.deshacer()
    l = h.doc["listas"][0]
    assert len(l["registros"]) == 2 and [i["id"] for i in l["importaciones"]] == ["lote01"]


# ───────── revertir_datos: la regla del laboratorio ─────────

def test_revertir_datos_choca_si_lo_mismo_cambio_despues():
    a = {"s": [{"id": "1", "valores": {"x": 1}}]}
    b = {"s": [{"id": "1", "valores": {"x": 2}}]}
    assert pt.revertir_datos(a, b, {"s": [{"id": "1", "valores": {"x": 3}}]}) == {"choca": True}
    assert pt.revertir_datos(a, b, {"s": [{"id": "1", "valores": {"x": 2, "y": 5}}]}) == {"datos": {"s": [{"id": "1", "valores": {"x": 1, "y": 5}}]}}


def test_revertir_un_campo_que_el_pedido_puso_lo_quita():
    a = {"s": [{"id": "1", "valores": {"x": 1}}]}
    b = {"s": [{"id": "1", "valores": {"x": 1, "y": 2}}]}
    assert pt.revertir_datos(a, b, b) == {"datos": {"s": [{"id": "1", "valores": {"x": 1}}]}}
    vacio = {"s": [{"id": "1", "valores": {}}]}
    assert pt.revertir_datos(vacio, {"s": [{"id": "1", "valores": {"y": 2}}]}, {"s": [{"id": "1", "valores": {"y": 2}}]}) == {"datos": vacio}


# ───────── Fixtures dorados del laboratorio (contrato §6) ─────────

_FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "lab" / "revertirDatos.json").read_text(encoding="utf-8"))


def test_los_fixtures_del_laboratorio_estan_completos():
    assert len(_FIXTURES) == 708 and sum(1 for c in _FIXTURES if c["salida"].get("choca")) == 23


@pytest.mark.parametrize("caso", _FIXTURES, ids=[f"{i}:{c['caso'][:40]}" for i, c in enumerate(_FIXTURES)])
def test_revertir_delta_igual_que_el_laboratorio(caso):
    e = caso["entrada"]
    salida = pt.revertir_delta(e.get("antes"), e.get("despues"), e.get("actual"))
    assert salida == caso["salida"]  # las listas (borrados, registros) también en el mismo orden


def test_la_misma_regla_en_los_registros_de_carlos():
    """El caso de Rosa del fixture, con los registros completos de una sección: lo mismo que revertir_delta."""
    rosa = lambda plan: {"id": "p1", "valores": {"nombre": "Rosa Gómez", "plan": plan, "estado": "Activa"}}
    carlos = {"id": "1", "valores": {"nombre": "Carlos", "plan": "Mensual", "estado": "Activa"}}
    r = pt.revertir_seccion([carlos, rosa("Mensual")], [carlos, rosa("Anual")], [rosa("Anual")])  # Carlos se borró después
    assert r == [rosa("Mensual")]
    assert pt.revertir_seccion([carlos], [carlos, rosa("Mensual")], [carlos, rosa("Anual")]) is None  # el alta tocada después choca
