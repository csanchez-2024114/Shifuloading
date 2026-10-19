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
    doc_sem = adp.sembrar_doc(plantilla_id, muestra, hoy=HOY)
    doc = adp.doc_desde_lab(plantilla_id, estado, muestra, hoy=HOY)
    vuelta = adp.lab_desde_doc(doc, doc_sem, plantilla_id, vista=estado.get("vista"), muestra=muestra, hoy=HOY)
    return _igual_grafica(adp.normalizar_estado_lab(vuelta), estado), adp.normalizar_estado_lab(estado)


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


def test_ruta_desactivada_sin_env(monkeypatch):
    monkeypatch.delenv("CRM_LAB_ADAPTER", raising=False)
    labRoutes.configurar_responder(lambda **k: {})
    app = FastAPI()
    app.include_router(labRoutes.router, prefix="/api/v1/crm")
    c = TestClient(app)
    assert c.post("/api/v1/crm/lab/chat", json={"texto": "hola"}).status_code == 404
