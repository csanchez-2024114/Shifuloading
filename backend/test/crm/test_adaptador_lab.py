"""Round-trip y ruta del adaptador laboratorio ↔ documento CRM (contrato §7)."""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.crm import adaptador_lab as adp
from app.crm import edicion
from app.routes.crm import labRoutes

HOY = date(2026, 10, 18)
AHORA = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
MUESTRA_DATOS = {"nivel": "pocos", "ejemplos": True, "pais": "gt"}

# ── Estados iniciales copiados de los bancos (membresías) ──

BANCO2_E = {
    "vista": "inicio",
    "bloques": [
        {"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
        {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 6, "alto": 2},
        {"uid": "b2", "vista": "grafica", "seccion": "miembros", "opciones": {"tipo": "linea", "fecha": "alta"}, "ancho": 6, "alto": 2},
    ],
}

B_DATOS = [
    {"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
    {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2},
]


def E_datos(vista="inicio", datos=None):
    return {"vista": vista, "bloques": B_DATOS, **({"datos": datos} if datos else {})}


UN_JUAN = {
    "n": 1,
    "nuevos": {"miembros": [{"id": "miembros-p1", "valores": {"nombre": "Juan Pérez", "plan": "Mensual", "alta": HOY.isoformat(), "estado": "Activa"}}]},
}
DOS_ANAS = {"n": 1, "nuevos": {"miembros": [{"id": "miembros-p1", "valores": {"nombre": "Ana Martínez", "plan": "Trimestral", "estado": "Activa"}}]}}

PAG = {
    "miembros": [
        {"uid": "p_miembros", "seccion": "miembros", "vista": "tabla", "opciones": {}, "ancho": 12, "alto": 3},
        {"uid": "pz1", "seccion": "miembros", "vista": "grafico", "opciones": {"tipo": "dona"}, "ancho": 6, "alto": 2},
    ]
}


def E_pestanas(vista="inicio", paginas=None):
    return {"vista": vista, "bloques": B_DATOS, **({"estructura": {"paginas": paginas}} if paginas else {})}


BANCO_TOMA_E = {
    "vista": "inicio",
    "bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}],
}

MARCA_RICA = {
    **BANCO2_E,
    "marca": {
        "primario": "#DC2626",
        "secundario": "#2563EB",
        "fuenteTitulos": "Montserrat",
        "fuenteTexto": "Nunito",
        "nombre": "Gym Norte",
    },
}

TOMA_ACTIVA = {
    **BANCO_TOMA_E,
    "toma": {
        "activa": True,
        "fase": "juntando",
        "ficha": {
            "objetivo": "Controlar pagos y membresías",
            "secciones": ["miembros", "pagos"],
            "bloques": [
                {"vista": "kpis", "seccion": "pagos", "opciones": {"suma": "monto"}, "ancho": 12, "alto": 1},
                {"vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "dona"}, "ancho": 6, "alto": 2},
            ],
            "marca": {"primario": "#16A34A"},
            "restricciones": ["sin mapa"],
        },
        "notas": ["prefiere colores claros"],
        "preguntadas": ["objetivo"],
        "rechazo": False,
    },
}

PUNTOS_DESHACER = {
    **BANCO2_E,
    "marca": {"primario": "#DC2626"},
    "puntos": [
        {
            "n": 1,
            "antes_de": "pon mis colores: rojo",
            "hora": "14:30",
            "cambio": ["marca"],
            "foto": {"marca": {}},
        },
        {
            "n": 2,
            "antes_de": "agrega una dona",
            "hora": "14:31",
            "cambio": ["bloques"],
            "foto": {
                "bloques": BANCO2_E["bloques"],
                "estructura": {"titulos": {"miembros": "Socios"}},
                "datos": {"nuevos": {}, "cambios": {}, "borrados": {}},
            },
        },
    ],
}

ESTRUCTURA_RICA = {
    "titulos": {"miembros": "Socios activos", "pagos": "Cobranza"},
    "nombresCampo": {"miembros": {"vence": "Fecha de vencimiento"}},
    "opcionesEstado": {"miembros": {"estado": ["Activa", "Cancelada", "Congelada"]}},
    "mapeoEstado": {"miembros": {"estado": {"Pausada": "Activa"}}},
    "ficha": {
        "miembros": {
            "grupos": [
                {"titulo": "Plan", "campos": ["plan", "estado"]},
                {"titulo": "Fechas", "campos": ["alta", "vence"]},
            ],
            "relacionados": False,
            "linea_tiempo": True,
        }
    },
    "tarjeta": {"miembros": {"campos": ["nombre", "plan"]}},
    "ocultas": ["pagos"],
    "secciones": [
        {
            "id": "proveedores",
            "titulo": "Proveedores",
            "campos": [
                {"id": "nombre", "nombre": "Nombre", "tipo": "texto"},
                {"id": "telefono", "nombre": "Teléfono", "tipo": "texto"},
                {"id": "producto", "nombre": "Qué vende", "tipo": "texto"},
            ],
        }
    ],
}

DATOS_DELTA = {
    "cambios": {"miembros": {"miembros-0": {"estado": "Pausada", "plan": "Anual"}}},
    "borrados": {"miembros": ["miembros-1"]},
    "nuevos": {
        "miembros": [
            {
                "id": "miembros-p1",
                "valores": {"nombre": "María López", "plan": "Mensual", "alta": HOY.isoformat(), "vence": HOY.isoformat(), "estado": "Activa"},
            }
        ]
    },
    "n": 1,
}

ESTADOS_ROUNDTRIP = [
    ("banco2", BANCO2_E, None),
    ("banco_datos E()", E_datos(), MUESTRA_DATOS),
    ("banco_datos UN_JUAN", E_datos(datos=UN_JUAN), MUESTRA_DATOS),
    ("banco_datos DOS_ANAS", E_datos(datos=DOS_ANAS), MUESTRA_DATOS),
    ("banco_pestanas E()", E_pestanas(), None),
    ("banco_pestanas PAG", E_pestanas("miembros", PAG), None),
    ("banco_ficha", BANCO2_E, None),
    ("banco_deshacer", BANCO2_E, None),
    ("banco_toma", BANCO_TOMA_E, None),
    ("marca rica", MARCA_RICA, None),
    ("toma activa", TOMA_ACTIVA, None),
    ("puntos deshacer", PUNTOS_DESHACER, None),
    ("estructura rica", {**BANCO2_E, "estructura": ESTRUCTURA_RICA}, None),
    ("datos delta", E_datos(datos=DATOS_DELTA), MUESTRA_DATOS),
    (
        "estructura+datos",
        {**BANCO2_E, "estructura": ESTRUCTURA_RICA, "datos": {**DATOS_DELTA, "cambios": {"miembros": {"miembros-0": {"plan": "Anual"}}}}},
        MUESTRA_DATOS,
    ),
]


def _igual_grafica(vuelta: dict, origen: dict) -> dict:
    """grafica/grafico son equivalentes en el laboratorio; al volver del doc puede salir `grafico`."""
    v = copy.deepcopy(vuelta)
    o = origen.get("bloques") or []
    for i, b in enumerate(v.get("bloques") or []):
        if i < len(o) and b.get("vista") in ("grafico", "grafica") and o[i].get("vista") in ("grafico", "grafica"):
            b["vista"] = o[i]["vista"]
    if v.get("estructura", {}).get("paginas"):
        for pid, bs in v["estructura"]["paginas"].items():
            ob = (origen.get("estructura") or {}).get("paginas", {}).get(pid) or []
            for j, b in enumerate(bs):
                if j < len(ob) and b.get("vista") in ("grafico", "grafica") and ob[j].get("vista") in ("grafico", "grafica"):
                    b["vista"] = ob[j]["vista"]
    return v


def _roundtrip(plantilla_id: str, estado: dict, muestra: dict | None) -> tuple[dict, dict]:
    from app.crm import plantillas as catalogo

    doc_sem = adp.sembrar_doc(plantilla_id, muestra, hoy=HOY)
    doc = adp.doc_desde_lab(plantilla_id, estado, muestra, hoy=HOY)
    pts_doc = adp.puntos_doc_desde_lab(estado.get("puntos") or [], plantilla_id, muestra, hoy=HOY) if estado.get("puntos") else None
    vuelta = adp.lab_desde_doc(
        doc,
        doc_sem,
        plantilla_id,
        vista=estado.get("vista"),
        puntos_doc=pts_doc,
        muestra=muestra,
        hoy=HOY,
    )
    # Los puntos no vuelven iguales a propósito (llevan su foto en forma documento en `doc`): se prueban aparte, abajo.
    sin_puntos = {k: v for k, v in estado.items() if k != "puntos"}
    vuelta.pop("puntos", None)
    return _igual_grafica(adp.normalizar_estado_lab(vuelta), sin_puntos), adp.normalizar_estado_lab(sin_puntos)


def test_foto_del_laboratorio_se_traduce_y_deshacer_la_usa():
    """La foto del laboratorio (el estado de antes) llega a `puntos.deshacer` en forma documento: deshacer la dona vuelve el inicio."""
    from app.crm import puntos as pt

    actual = {**PUNTOS_DESHACER, "bloques": [*BANCO2_E["bloques"], {"uid": "b3", "vista": "grafico", "seccion": "miembros",
                                                                       "opciones": {"tipo": "dona", "por": "estado"}, "ancho": 6, "alto": 2}]}
    doc = adp.doc_desde_lab("membresias", actual, None, hoy=HOY)
    pts = adp.puntos_doc_desde_lab(actual["puntos"], "membresias", None, hoy=HOY)
    assert set(pts[1]["foto"]) == {"bloques"} and set(pts[0]["foto"]) == {"marca"}
    r = pt.deshacer(doc, pts, 2)
    antes = adp.doc_desde_lab("membresias", BANCO2_E, None, hoy=HOY)
    assert r["doc"]["inicio"] == antes["inicio"] and r["doc"]["marca"] == doc["marca"]


def test_puntos_del_motor_vuelven_identicos():
    """Un punto que hizo el motor sale al laboratorio y vuelve en el turno siguiente con la misma foto (la que deshacer espera)."""
    from app.crm import plantillas as catalogo
    from app.crm import puntos as pt

    antes = adp.doc_desde_lab("membresias", BANCO2_E, MUESTRA_DATOS, hoy=HOY)
    despues = {**antes, "inicio": antes["inicio"][:1], "marca": {**(antes.get("marca") or {}), "primario": "#DC2626"}}
    despues, punto = pt.con_punto(antes, despues, "quita dos piezas y pon rojo", AHORA)
    plantilla = catalogo.plantilla_por_id("membresias")
    lab = adp.puntos_lab_desde_doc([punto], plantilla, adp.mapa_secciones(plantilla, despues))
    assert lab[0]["hora"] == "15:00" and len(lab[0]["foto"]["bloques"]) == 3
    vuelta = adp.puntos_doc_desde_lab(json.loads(json.dumps(lab)), "membresias", MUESTRA_DATOS, hoy=HOY)
    assert vuelta == [json.loads(json.dumps(punto))]


@pytest.mark.parametrize("nombre,estado,muestra", ESTADOS_ROUNDTRIP)
def test_roundtrip_estado_banco(nombre, estado, muestra):
    vuelta, origen = _roundtrip("membresias", estado, muestra)
    assert vuelta == origen, f"{nombre}: {json.dumps(vuelta, ensure_ascii=False)[:400]}"


@pytest.fixture
def cliente_lab(monkeypatch):
    monkeypatch.setenv("CRM_LAB_ADAPTER", "1")

    def fake_responder(doc, texto, historial, contexto, puntos=None):
        r = edicion.ejecutar(
            doc,
            "agregar_bloque",
            {"vista": "grafico", "seccion": "l_miembros", "opciones": {"tipo": "dona"}, "ancho": 4, "alto": 2},
            contexto,
        )
        cambios = []
        doc_out = doc
        if r["ok"]:
            doc_out = r["doc"]
            cambios.append({"herramienta": "agregar_bloque", "args": {}, "resultado": r["resultado"]})
        return {
            "respuesta": "Listo, agregué una dona.",
            "doc": doc_out,
            "puntos": puntos or [],
            "cambios": cambios,
            "fallos": [],
            "intentos": [],
            "consultas": [],
            "avisos": [],
            "vista": contexto.get("vista") or "inicio",
        }

    labRoutes.configurar_responder(fake_responder)
    app = FastAPI()
    app.include_router(labRoutes.router, prefix="/api/v1/crm")
    return TestClient(app)


def test_ruta_lab_chat_fake_responder(cliente_lab):
    r = cliente_lab.post(
        "/api/v1/crm/lab/chat",
        json={"plantilla": "membresias", "estado": BANCO2_E, "texto": "agrega una dona de los estados de los miembros chiquita"},
    )
    assert r.status_code == 200
    d = r.json()
    assert any(c["herramienta"] == "agregar_bloque" for c in d["cambios"])
    vistas = [b["vista"] for b in d["estado"]["bloques"]]
    assert "grafica" in vistas or "grafico" in vistas


@pytest.mark.asyncio
async def test_procesar_chat_lab_cadena_dos_turnos():
    """Turno 2 reenvía el estado devuelto; el motor debe ver marca y el registro nuevo del turno 1."""
    turnos: list[dict] = []

    def fake_responder(doc, texto, historial, contexto, puntos=None):
        turnos.append(copy.deepcopy(doc))
        if len(turnos) == 1:
            doc = edicion.ejecutar(doc, "cambiar_marca", {"primario": "#5B5CF6"}, contexto)["doc"]
            lista = next(l for l in doc["listas"] if l["id"] == "l_miembros")
            lista["registros"] = [
                *lista["registros"],
                {"id": "miembros-p2", "valores": {"nombre": "Pedro Cadena", "plan": "Mensual", "estado": "Activa"}, "ejemplo": False, "creado": AHORA},
            ]
            return {
                "respuesta": "Listo.",
                "doc": doc,
                "puntos": puntos or [],
                "cambios": [{"herramienta": "cambiar_marca"}, {"herramienta": "agregar_registro"}],
                "fallos": [],
                "intentos": [],
                "consultas": [],
                "avisos": [],
                "vista": "inicio",
            }
        lista = next(l for l in doc["listas"] if l["id"] == "l_miembros")
        nombres = [r["valores"].get("nombre") for r in lista["registros"]]
        assert (doc.get("marca") or {}).get("primario", "").lower() == "#5b5cf6"
        assert "Pedro Cadena" in nombres
        return {
            "respuesta": "ok",
            "doc": doc,
            "puntos": puntos or [],
            "cambios": [],
            "fallos": [],
            "intentos": [],
            "consultas": [],
            "avisos": [],
            "vista": "inicio",
        }

    r1 = await adp.procesar_chat_lab(
        {"plantilla": "membresias", "estado": BANCO2_E, "texto": "marca y un miembro", "muestra": MUESTRA_DATOS},
        fake_responder,
        hoy=HOY,
    )
    r2 = await adp.procesar_chat_lab(
        {
            "plantilla": "membresias",
            "estado": r1["estado"],
            "texto": "solo verifico",
            "muestra": MUESTRA_DATOS,
            "historial": [{"de": "yo", "t": "marca y un miembro"}, {"de": "shifu", "t": r1["respuesta"]}],
        },
        fake_responder,
        hoy=HOY,
    )
    assert r2["respuesta"] == "ok"
    assert len(turnos) == 2


def test_ruta_desactivada_sin_env(monkeypatch):
    monkeypatch.delenv("CRM_LAB_ADAPTER", raising=False)
    labRoutes.configurar_responder(lambda **k: {})
    app = FastAPI()
    app.include_router(labRoutes.router, prefix="/api/v1/crm")
    c = TestClient(app)
    assert c.post("/api/v1/crm/lab/chat", json={"texto": "hola"}).status_code == 404
