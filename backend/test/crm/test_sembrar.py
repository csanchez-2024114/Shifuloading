"""Siembra de un CRM desde las plantillas del laboratorio (`app/crm/sembrar.py`) y su ajuste por la IA dentro del cerco.

Las 27 plantillas (6 semillas + 21 de biblioteca) se siembran y se comparan con los datos de ejemplo del laboratorio
(`ejemplos.datos_ejemplo`, que a su vez es idéntico al JS por fixtures). Nada llama al OpenAI de verdad: la IA es un modelo falso.
"""
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.crm import diseno, ejemplos, sembrar
from app.crm import estructura as est
from app.crm import plantillas as catalogo
from app.crm import secciones_v as sv
from app.crm.asignar import catalogo_plantillas
from app.crm.generador import generar

AHORA = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
HOY = date(2026, 10, 18)
FIXTURES = Path(__file__).parent / "fixtures" / "lab"
IDS = [p["id"] for p in catalogo_plantillas()]
CLAVES_DE_CAMPO = ("titulo", "detalle", "por", "fecha", "fecha2", "estado", "hora", "suma", "valor", "valor2", "agrupar", "vencen", "hoy", "texto")
PERSONAS = {"embudo", "simple", "agencia-marketing", "firma-contable"}


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")


def _base(brief=None):
    return generar("u1", brief or {"nombre": "Mi negocio", "rubro": "servicios"}, AHORA)


def _sembrado(pid):
    return sembrar.sembrar(_base(), pid, hoy=HOY, ahora=AHORA, porque=["tu rubro"])


def test_son_las_27_plantillas():
    assert len(IDS) == 27 and len(set(IDS)) == 27


# ───────── Lienzo ─────────

def test_acomodar_es_el_del_laboratorio():
    casos = json.loads((FIXTURES / "acomodar.json").read_text(encoding="utf-8"))
    for c in casos:
        assert sembrar.acomodar(c["entrada"]["bloques"], c["entrada"].get("fijos") or []) == c["salida"], c["caso"]


def test_con_tamano_como_lienzo_jsx():
    bs = sembrar.con_tamano([{"uid": "b0", "vista": "kpis"}, {"uid": "b1", "vista": "grafico"}, {"uid": "b2", "vista": "vencimientos"},
                             {"uid": "b3", "vista": "tabla"}, {"uid": "b4", "vista": "agenda", "ancho": 8, "alto": 3}])
    assert [(b["ancho"], b["alto"]) for b in bs] == [(12, 1), (6, 2), (6, 2), (12, 2), (8, 3)]  # el medio que queda solo va a lo ancho


# ───────── Cada plantilla siembra un documento válido ─────────

@pytest.mark.parametrize("pid", IDS)
def test_cada_plantilla_siembra_un_esquema_2_valido(pid):
    p = catalogo.plantilla_por_id(pid)
    doc = _sembrado(pid)
    datos = ejemplos.registros_ejemplo(p, "muchos", HOY)
    assert doc["esquema"] == 2 and doc["plantilla"] == {"id": pid, "origen": "asignar", "porque": ["tu rubro"]}
    personas = sembrar.seccion_personas(p)
    assert (pid in PERSONAS) == (personas is not None)

    # Listas: una por sección con campos (y sin fuente), con los campos y los registros de ejemplo del laboratorio.
    con_campos = [s for s in p["secciones"] if s.get("campos") and not s.get("fuente")]
    esperadas = [s for s in con_campos if not (personas and s["id"] == personas[0]["id"])]
    assert [l["id"] for l in doc["listas"]] == ["l_" + s["id"] for s in esperadas]
    for s, l in zip(esperadas, doc["listas"]):
        assert l["nombre"] == s["titulo"] and l["origen"] == pid and l["vista"] == s["vista"] and l["icono"] == s["icono"] and l["grupo"] == s["grupo"]
        assert l["opciones"] == (s.get("opciones") or {})
        assert l["campos"] == [{k: c[k] for k in ("id", "nombre", "tipo", "opciones") if k in c} for c in s["campos"]]
        assert len(l["registros"]) == len(datos[s["id"]]) == ejemplos.NIVELES["muchos"]
        assert [{k: r[k] for k in ("id", "ejemplo", "valores")} for r in l["registros"]] == datos[s["id"]]
        assert all(r["ejemplo"] is True for r in l["registros"])
        for c in l["campos"]:
            assert c["tipo"] in est.TIPOS_V2
            if c["tipo"] in est.CON_OPCIONES:
                assert est.opciones_validas(c["opciones"]) == c["opciones"]
        for r in l["registros"][:40]:
            assert est.valores_validos(l["campos"], r["valores"]) == r["valores"]  # cada valor ya tiene el formato guardado de Carlos

    # Topes de Carlos.
    assert len(doc["listas"]) <= est.MAX_LISTAS
    assert all(len(l["campos"]) <= est.MAX_CAMPOS and len(l["registros"]) <= est.MAX_REGISTROS for l in doc["listas"])

    # Personas → contactos.
    if personas:
        sec, campo = personas
        assert doc["etapas"] == campo["opciones"] and doc["secciones"]["contactos"] == sec["titulo"]
        assert "contactos" not in doc["ocultas"]
        assert doc["total_contactos"] == len(doc["contactos"]) == len(datos[sec["id"]])
        for c, r in zip(doc["contactos"], datos[sec["id"]]):
            assert c["ejemplo"] is True and c["id"] == r["id"] and c["n"] == r["valores"]["nombre"] and c["etapa"] == r["valores"][campo["id"]]
        assert [x["id"] for x in doc["campos_contacto"]] == ["f_" + c["id"] for c in sec["campos"] if c["id"] not in ("nombre", "telefono", campo["id"])]
    else:
        assert doc["contactos"] == [] and doc["total_contactos"] == 0 and "contactos" in doc["ocultas"]

    # Las fijas (Historial, Equipo, Automatizaciones) son las integradas de Carlos: visibles y sin duplicar.
    assert not any(l["vista"] in sembrar.FIJAS for l in doc["listas"])
    assert not {"actividad", "rrhh", "automatizaciones"} & set(doc["ocultas"])
    assert {"cobros", "desarrollo", "importar"} <= set(doc["ocultas"])

    # Inicio: piezas de la plantilla, uid b0…, sección que existe y opciones que nombran campos que existen.
    secciones = {s["id"]: s for s in sv.secciones_de(doc)}
    assert [b["uid"] for b in doc["inicio"]] == [f"b{i}" for i in range(len(p["inicio"]))]
    for b, w in zip(doc["inicio"], p["inicio"]):
        assert b["vista"] == w["vista"] and b["seccion"] in secciones
        assert b["ancho"] in (3, 4, 6, 8, 12) and 1 <= b["alto"] <= 4
        campos = {c["id"] for c in secciones[b["seccion"]]["campos"]}
        assert all(v in campos for k, v in b["opciones"].items() if k in CLAVES_DE_CAMPO), (b, campos)
    if not personas:  # sin traducción de campos, el inicio es exactamente el del laboratorio (acomodar(conTamano(inicio)))
        lab = sembrar.acomodar(sembrar.con_tamano([{**w, "uid": f"b{i}"} for i, w in enumerate(p["inicio"])]))
        assert doc["inicio"] == [{**w, "seccion": "l_" + w["seccion"]} for w in lab]

    # Páginas: solo para las secciones que muestran los registros de otra.
    fuentes = [s for s in p["secciones"] if s.get("fuente")]
    assert set(doc["paginas"]) == {"l_" + s["fuente"] for s in fuentes}
    for sid, bs in doc["paginas"].items():
        assert all(b["seccion"] == sid and b["uid"] for b in bs) and sid in secciones

    # Todo lo sembrado se lee por secciones virtuales.
    for sid in secciones:
        sv.registros_de(doc, sid)


def test_membresias_vencimientos_es_la_pagina_de_miembros():
    doc = _sembrado("membresias")
    assert [l["id"] for l in doc["listas"]] == ["l_miembros", "l_pagos"]  # Vencimientos no es una lista: no tiene datos propios
    pagina = doc["paginas"]["l_miembros"]
    vence = next(s for s in catalogo.plantilla_por_id("membresias")["secciones"] if s["id"] == "vencimientos")
    assert [(b["uid"], b["vista"]) for b in pagina] == [("b0", "tabla"), ("b1", "vencimientos")]
    assert pagina[1]["opciones"] == vence["opciones"]


def test_embudo_clientes_son_los_contactos_con_sus_etapas():
    doc = _sembrado("embudo")
    assert doc["etapas"] == ["Nuevo", "Contactado", "Propuesta", "Negociación", "Ganado", "Perdido"]
    assert doc["campos_contacto"] == [{"id": "f_alta", "nombre": "Alta", "tipo": "fecha"}]
    c = doc["contactos"][0]
    assert c["det"].startswith("+502 ") and set(c["extra"]) == {"f_alta"} and c["dueno"] == "Tú"
    tablero = next(b for b in doc["inicio"] if b["vista"] == "tablero")
    assert tablero["seccion"] == "contactos" and tablero["opciones"] == {"por": "etapa", "titulo": "nombre", "detalle": "detalle"}
    assert [l["id"] for l in doc["listas"]] == ["l_seguimientos", "l_cotizaciones"]


def test_la_regla_de_personas_es_la_documentada():
    assert {pid for pid in IDS if sembrar.seccion_personas(catalogo.plantilla_por_id(pid))} == PERSONAS
    # Una agenda o unos miembros no son la lista de personas, aunque tengan estado.
    assert sembrar.seccion_personas(catalogo.plantilla_por_id("clinica-dental")) is None
    assert sembrar.seccion_personas(catalogo.plantilla_por_id("membresias")) is None


def test_no_cambia_el_documento_base_y_es_determinista():
    base = _base()
    antes = copy.deepcopy(base)
    a = sembrar.sembrar(base, "gimnasio", hoy=HOY, ahora=AHORA)
    b = sembrar.sembrar(base, "gimnasio", hoy=HOY, ahora=AHORA)
    assert base == antes and a == b


def test_la_siembra_conserva_lo_de_carlos():
    base = _base({"nombre": "Fit", "rubro": "servicios", "objetivos": ["reportes"], "equipo": "chico"})
    doc = sembrar.sembrar(base, "gimnasio", hoy=HOY, ahora=AHORA)
    assert doc["automatizaciones"] == base["automatizaciones"] and doc["vendedores"] == ["Tú"] and doc["brief"] == base["brief"]
    assert [e["t"] for e in doc["eventos"]] == ["Shifu creó tu CRM"]  # el historial de ejemplo del laboratorio no se siembra
    assert doc["tareas"] == {"porHacer": [], "enCurso": [], "hecho": []}


def test_quitar_ejemplos_deja_solo_lo_de_la_persona():
    doc = _sembrado("embudo")
    doc = est.registro_agregar(doc, "l_cotizaciones", {"cliente": "Real S.A.", "monto": 1500, "estado": "Enviada"}, AHORA)
    limpio = est.ejemplos_quitar(doc)
    assert [len(l["registros"]) for l in limpio["listas"]] == [0, 1]
    assert limpio["listas"][1]["registros"][0]["valores"]["cliente"] == "Real S.A."
    assert limpio["contactos"] == [] and limpio["total_contactos"] == 0
    assert [l["id"] for l in limpio["listas"]] == ["l_seguimientos", "l_cotizaciones"] and limpio["inicio"] == doc["inicio"]


def test_los_topes_de_carlos_cortan_en_orden_y_quitan_las_piezas_huerfanas(monkeypatch, caplog):
    campos = [{"id": f"c{i}", "nombre": f"Campo {i}", "tipo": "texto"} for i in range(17)]
    secciones = [{"id": f"s{i}", "titulo": f"Sección {i}", "grupo": 0, "icono": "tabla", "vista": "tabla", "campos": campos[:3]} for i in range(14)]
    secciones[0]["campos"] = campos
    p = {"id": "grande", "secciones": secciones, "inicio": [
        {"vista": "tabla", "seccion": "s0", "opciones": {"titulo": "c0"}},
        {"vista": "grafico", "seccion": "s0", "opciones": {"tipo": "barras", "agrupar": "c16"}},  # nombra un campo que se corta
        {"vista": "tabla", "seccion": "s13", "opciones": {}},  # una sección que no cabe
    ]}
    monkeypatch.setattr(est, "MAX_REGISTROS", 5)
    with caplog.at_level("INFO"):
        doc = sembrar.sembrar(_base(), p, hoy=HOY, ahora=AHORA)
    assert [l["id"] for l in doc["listas"]] == [f"l_s{i}" for i in range(12)]
    assert [c["id"] for c in doc["listas"][0]["campos"]] == [f"c{i}" for i in range(15)]
    assert all(len(l["registros"]) == 5 for l in doc["listas"])
    assert [(b["uid"], b["seccion"]) for b in doc["inicio"]] == [("b0", "l_s0")]
    assert "tope de 12 listas" in caplog.text and "se dejan 15" in caplog.text


# ───────── El ajuste de la IA, dentro del cerco ─────────

class Modelo:
    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, []

    async def ainvoke(self, mensajes):
        self.llamadas.append(mensajes)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return type("R", (), {"content": json.dumps(self.respuesta, ensure_ascii=False)})()


BRIEF_DENTAL = {"nombre": "Sonrisas", "rubro": "salud", "ciclo": "recurrente", "objetivos": ["seguimientos"], "que_vendes": "Consultorio dental familiar"}


@pytest.mark.asyncio
async def test_la_ia_solo_renombra_y_agrega_campos():
    doc = sembrar.sembrar(generar("u1", BRIEF_DENTAL, AHORA), "clinica-dental", hoy=HOY, ahora=AHORA)
    propuesta = {
        "resumen": "Tu consultorio quedó con citas, tratamientos y pacientes.",
        "secciones": [
            {"id": "l_pacientes", "nombre": "Expedientes de Sonrisas", "campos": [{"id": "notas", "nombre": "Alergias"}, {"id": "nombre", "tipo": "numero"}],
             "nuevos": [{"nombre": "Seguro médico", "tipo": "estado", "opciones": ["Sí", "No"]}, {"nombre": "Cumpleaños", "tipo": "fecha"}, {"nombre": "Tercero", "tipo": "texto"}]},
            {"id": "l_citas", "nombre": "Citas"},  # ese nombre ya lo tiene: no cambia nada
            {"id": "l_nueva", "nombre": "Proveedores", "campos": [{"id": "x", "nombre": "Y"}]},  # no existe: fuera del cerco
            {"id": "l_tratamientos", "nombre": "Citas"},  # chocaría con otra sección
        ],
        "etapas": ["A", "B"], "nombres": {"desarrollo": "Pendientes"}, "automatizaciones": [],  # nada de esto se aplica aquí
    }
    m = Modelo(propuesta)
    nuevo, aplicado = await diseno.ajustar_sembrado(doc, BRIEF_DENTAL, modelo=m, ahora=AHORA)
    assert len(m.llamadas) == 1 and "l_pacientes" in m.llamadas[0][1].content
    assert aplicado["nombres"] == {"l_pacientes": "Expedientes"}  # sin el nombre del negocio
    assert aplicado["campos"] == {"l_pacientes": {"notas": "Alergias"}}
    assert [c["nombre"] for c in aplicado["nuevos"]["l_pacientes"]] == ["Seguro médico", "Cumpleaños"]  # hasta 2
    assert [l["id"] for l in nuevo["listas"]] == [l["id"] for l in doc["listas"]]  # no crea ni quita secciones
    assert [l["nombre"] for l in nuevo["listas"]] == ["Citas", "Tratamientos", "Expedientes"]
    assert nuevo["etapas"] == doc["etapas"] and nuevo["secciones"] == doc["secciones"] and nuevo["ocultas"] == doc["ocultas"]
    assert nuevo["automatizaciones"] == doc["automatizaciones"] and nuevo["inicio"] == doc["inicio"]
    assert nuevo["listas"][2]["campos"][0] == doc["listas"][2]["campos"][0]  # el tipo no cambia
    assert nuevo["resumen_ia"].startswith("Tu consultorio")
    assert [r["valores"] for r in nuevo["listas"][0]["registros"]] == [r["valores"] for r in doc["listas"][0]["registros"]]  # los datos no se tocan

    # Los campos nuevos reciben valores de ejemplo calculados por el código (y solo en los ejemplos).
    con = sembrar.ejemplos_para_campos(nuevo, "l_pacientes", aplicado["nuevos"]["l_pacientes"], hoy=HOY)
    ids = [c["id"] for c in aplicado["nuevos"]["l_pacientes"]]
    regs = con["listas"][2]["registros"]
    assert all(set(ids) <= set(r["valores"]) for r in regs)
    assert {r["valores"][ids[0]] for r in regs} <= {"Sí", "No"}
    assert con == sembrar.ejemplos_para_campos(nuevo, "l_pacientes", aplicado["nuevos"]["l_pacientes"], hoy=HOY)  # determinista


@pytest.mark.asyncio
async def test_en_los_contactos_sembrados_no_renombra_los_campos_fijos():
    doc = _sembrado("embudo")
    m = Modelo({"secciones": [{"id": "contactos", "nombre": "Prospectos", "campos": [{"id": "etapa", "nombre": "Fase"}, {"id": "f_alta", "nombre": "Desde"}],
                                "nuevos": [{"nombre": "Empresa", "tipo": "texto"}]}]})
    nuevo, aplicado = await diseno.ajustar_sembrado(doc, {"nombre": "X"}, modelo=m, ahora=AHORA)
    assert nuevo["secciones"]["contactos"] == "Prospectos" and aplicado["campos"] == {"contactos": {"f_alta": "Desde"}}
    assert [c["nombre"] for c in nuevo["campos_contacto"]] == ["Desde", "Empresa"]
    con = sembrar.ejemplos_para_campos(nuevo, "contactos", aplicado["nuevos"]["contactos"], hoy=HOY)
    fid = aplicado["nuevos"]["contactos"][0]["id"]
    assert all(fid in c["extra"] for c in con["contactos"])


@pytest.mark.asyncio
async def test_si_la_ia_falla_o_esta_apagada_queda_lo_sembrado():
    doc = _sembrado("gimnasio")
    assert (await diseno.ajustar_sembrado(doc, {}, modelo=Modelo(RuntimeError("sin saldo")), ahora=AHORA))[0] is doc
    assert (await diseno.ajustar_sembrado(doc, {}))[0] is doc  # CRM_IA=0
    assert (await diseno.ajustar_sembrado(doc, {}, modelo=Modelo({"secciones": "basura"}), ahora=AHORA))[0]["listas"] == doc["listas"]


# ───────── Crear desde el cuestionario ─────────

@pytest.mark.asyncio
async def test_con_ganadora_clara_se_siembra_su_plantilla():
    doc = await sembrar.crear_desde_cuestionario("u1", BRIEF_DENTAL, ahora=AHORA)
    assert doc["plantilla"]["id"] == "clinica-dental" and doc["plantilla"]["origen"] == "asignar"
    assert "tu rubro" in doc["plantilla"]["porque"]
    assert [l["id"] for l in doc["listas"]] == ["l_citas", "l_tratamientos", "l_pacientes"]
    assert doc["user_id"] == "u1" and doc["brief"] == BRIEF_DENTAL


@pytest.mark.asyncio
async def test_si_es_ambiguo_es_lo_de_carlos_con_origen_generador():
    brief = {"nombre": "Clínica Sol", "rubro": "salud", "objetivos": ["seguimientos"]}
    assert sembrar.elegir(brief)["ambiguo"]
    doc = await sembrar.crear_desde_cuestionario("u1", brief, ahora=AHORA)
    assert doc["plantilla"] == {"id": None, "origen": "generador", "porque": []}
    assert doc["listas"] == [] and doc["contactos"] == [] and doc["esquema"] == 2


@pytest.mark.asyncio
async def test_si_la_siembra_falla_sigue_lo_de_siempre(monkeypatch):
    def rota(*_a, **_k):
        raise ValueError("plantilla rota")

    monkeypatch.setattr(sembrar, "sembrar", rota)
    doc = await sembrar.crear_desde_cuestionario("u1", BRIEF_DENTAL, ahora=AHORA)
    assert doc["plantilla"]["origen"] == "generador" and doc["listas"] == []


@pytest.mark.asyncio
async def test_crear_con_ia_ajusta_y_llena_los_campos_nuevos():
    m = Modelo({"secciones": [{"id": "l_pacientes", "nuevos": [{"nombre": "Seguro", "tipo": "texto"}]}]})
    doc = await sembrar.crear_desde_cuestionario("u1", BRIEF_DENTAL, modelo=m, ahora=AHORA)
    pac = next(l for l in doc["listas"] if l["id"] == "l_pacientes")
    fid = pac["campos"][-1]["id"]
    assert pac["campos"][-1]["nombre"] == "Seguro" and all(r["valores"].get(fid) for r in pac["registros"])
