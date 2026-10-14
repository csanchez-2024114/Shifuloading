"""Arma un CRM nuevo a partir de las respuestas del cuestionario (el "brief").

El CRM nace **vacío**: sin contactos, tareas, equipo ni actividad inventados. Lo único que trae es lo que sale de lo que
la persona contó (su rubro para nombrar las secciones, sus canales y objetivos para dejar prendidas las automatizaciones
que le sirven) y un solo hecho real: que Shifu lo creó. Cuando se conecte el agente, aquí es donde la IA propondrá etapas,
campos y automatizaciones a la medida del negocio.
"""
from __future__ import annotations

from datetime import datetime

from app.crm import automatizaciones
from app.crm.operaciones import ahora_utc, nuevo_id
from app.crm.secciones import ETAPAS


def generar(user_id: str, brief: dict, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    objetivos = brief.get("objetivos") or []
    problemas = brief.get("problemas") or []
    encendidas = set()
    if "seguimientos" in objetivos or "olvido" in problemas:
        encendidas.add("recordatorios")
    if brief.get("equipo") and brief.get("equipo") != "solo":
        encendidas.add("reparto")
    if "reportes" in objetivos:
        encendidas.add("resumen")
    return {
        "user_id": user_id,
        "version": 1,
        "brief": brief,
        "total_contactos": 0,
        "contactos": [],
        "vendedores": ["Tú"],  # la persona; su equipo se agrega después
        "tareas": {"porHacer": [], "enCurso": [], "hecho": []},
        "eventos": [{"id": nuevo_id(), "e": "🤖", "t": "Shifu creó tu CRM", "ts": ahora}],
        "automatizaciones": automatizaciones.armar(encendidas),
        "secciones": {},
        "etapas": list(ETAPAS),
        "ocultas": [],
        "campos_contacto": [],
        "listas": [],
        "created_at": ahora,
        "updated_at": ahora,
    }
