"""El lienzo (acomodo automático D38 y ubicación): los 788 casos dorados de acomodar.json y el port de laboratorio/pruebas/acomodar.test.mjs."""
import json
from pathlib import Path

import pytest

from assistant.packs.crm.lienzo import acomodar, ajustar_ancho, colocar, rangos_de, ubicar

CASOS = json.loads((Path(__file__).parent / "fixtures" / "lab" / "acomodar.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso"] for c in CASOS])
def test_acomodar_igual_que_el_laboratorio(caso):
    e = caso["entrada"]
    assert acomodar(e["bloques"], set(e["fijos"])) == caso["salida"]


def test_son_todos_los_casos_grabados():
    assert len(CASOS) == 788


def huecos(bs):
    """Celdas vacías de la rejilla (misma simulación «dense» que el CSS)."""
    _, celdas = colocar(bs)
    return sum(1 for f in range(len(celdas)) for c in range(12) if not celdas.en(f, c))


def B(uid, ancho, alto=2, vista="grafico"):
    return {"uid": uid, "ancho": ancho, "alto": alto, "vista": vista, "seccion": "s", "opciones": {}}


def test_sin_huecos_no_cambia_nada():
    bs = [B("a", 12, 1, "kpis"), B("b", 6), B("c", 6)]
    assert acomodar(bs) == bs


def test_8_mas_3_el_ultimo_llena_la_fila():
    r = acomodar([B("a", 8), B("b", 3)])
    assert huecos(r) == 0 and r[1]["ancho"] == 4


def test_quitar_uno_de_tres_deja_0_huecos():
    assert huecos(acomodar([B("a", 4), B("b", 4)])) == 0


def test_fila_incompleta_al_final_se_completa():
    r = acomodar([B("a", 6), B("b", 6), B("c", 6)])
    assert huecos(r) == 0 and r[2]["ancho"] == 12


def test_alto_distinto_el_chico_crece_hacia_abajo():
    r = acomodar([B("a", 8, 2), B("b", 4, 1)])
    assert huecos(r) == 0 and r[1]["alto"] == 2


def test_el_resumen_nunca_crece_de_alto():
    assert acomodar([B("k", 8, 1, "kpis"), B("a", 4, 2)])[0]["alto"] == 1


def test_el_bloque_fijo_no_se_toca():
    assert acomodar([B("a", 4), B("b", 8)], {"a"})[0]["ancho"] == 4
    assert acomodar([{**B("a", 4), "fijo": True}, B("b", 8)])[0]["ancho"] == 4


def test_no_cambia_el_orden_ni_quita_bloques():
    r = acomodar([B("a", 3), B("b", 8), B("c", 3, 1), B("d", 6)])
    assert [b["uid"] for b in r] == ["a", "b", "c", "d"]


def test_ubicar_coincide_con_el_acomodo():
    u = ubicar([B("a", 6), B("b", 6)])
    assert u["a"]["lado"] == "izquierda" and u["b"]["lado"] == "derecha"


def test_al_azar_500_inicios_casi_sin_huecos():
    """La medida del laboratorio: 500 inicios al azar (misma semilla) → 24 con huecos y 112 celdas vacías después."""
    semilla = 7.0  # en flotantes, como JS (el producto pasa de 2^53 y se redondea igual)

    def azar():
        nonlocal semilla
        semilla = (semilla * 1103515245.0 + 12345.0) % 2147483648.0
        return semilla / 2147483648

    antes = despues = celdas_antes = celdas_despues = 0
    for _ in range(500):
        n = 2 + int(azar() * 6)
        bs = [B(f"r{j}", [3, 4, 6, 8, 12][int(azar() * 5)], 1 + int(azar() * 3)) for j in range(n)]
        h0, h1 = huecos(bs), huecos(acomodar(bs))
        antes += h0 > 0
        despues += h1 > 0
        celdas_antes += h0
        celdas_despues += h1
    assert (antes, despues, celdas_antes, celdas_despues) == (485, 24, 8663, 112)


def test_ajustar_ancho_y_rangos():
    assert [ajustar_ancho(a) for a in (1, 5, 7, 10, 20, float("nan"))] == [3, 6, 6, 8, 12, 6]  # 5: empate entre 4 y 6, gana 6
    assert rangos_de({}) == [{"desde": None, "hasta": -1}, {"desde": 0, "hasta": 7}, {"desde": 8, "hasta": 30}]
    assert rangos_de({"dias": 7}) == [{"desde": None, "hasta": -1}, {"desde": 0, "hasta": 7}]


@pytest.mark.parametrize("pid", ["embudo", "agenda", "pedidos", "membresias", "proyectos", "simple"])
def test_quitar_cada_bloque_de_una_plantilla_deja_0_huecos(pid):
    """El acomodo automático corre dentro de ejecutar: quitar cualquier pieza del inicio de cada plantilla no deja huecos."""
    from assistant.packs.crm import plantillas
    from assistant.packs.crm.edicion import ejecutar
    from lab_doc import doc_de_lab

    p = plantillas.plantilla_por_id(pid)
    bloques = [{**b, "uid": f"b{i + 1}", "ancho": b.get("ancho") or (12 if b["vista"] in ("kpis", "tablero", "agenda") else 6),
                "alto": b.get("alto") or (1 if b["vista"] == "kpis" else 2)} for i, b in enumerate(p["inicio"])]
    doc, _ = doc_de_lab(pid, {"bloques": bloques})
    for b in doc["inicio"]:
        r = ejecutar(doc, "quitar_bloque", {"bloque": b["uid"]})
        assert r["ok"], r["resultado"]
        assert huecos(r["doc"]["inicio"]) == 0, f"al quitar {b['uid']} ({b['vista']}): {[(x['uid'], x['ancho'], x['alto']) for x in r['doc']['inicio']]}"
