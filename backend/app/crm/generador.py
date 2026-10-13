"""Arma un CRM nuevo a partir de las respuestas del cuestionario (el "brief").

El CRM nace **vacío**: sin contactos, tareas, equipo ni actividad inventados. Lo único que trae es lo que sale de lo que
la persona contó (su rubro para nombrar las secciones, sus canales y objetivos para dejar prendidas las automatizaciones
que le sirven) y un solo hecho real: que Shifu lo creó. Cuando se conecte el agente, aquí es donde la IA propondrá etapas,
campos y automatizaciones a la medida del negocio.
"""
from __future__ import annotations

from datetime import datetime

from app.crm.operaciones import ahora_utc, nuevo_id


def generar(user_id: str, brief: dict, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    objetivos = brief.get("objetivos") or []
    canales = brief.get("canales") or []
    # (id, pilar, nombre, descripción, ¿encendida según lo que contó la persona?)
    automatizaciones = [
        ("recordatorios", "Estructura", "Recordatorios de seguimiento", "Te avisa cuando un contacto lleva 3 días sin respuesta.",
         "seguimientos" in objetivos or "olvido" in (brief.get("problemas") or [])),
        ("bienvenida", "Estructura", "Bienvenida automática por WhatsApp", "Responde al instante cuando alguien te escribe por primera vez.", "whatsapp" in canales),
        ("contacto", "Estructura", "Crear el contacto desde cada mensaje", "Shifu detecta quién te escribe y lo agrega con lo que pidió.", "ia" in objetivos),
        ("reparto", "Medición y equipo", "Repartir contactos nuevos entre el equipo", "Cada contacto nuevo se asigna por turnos a tu equipo.",
         bool(brief.get("equipo")) and brief.get("equipo") != "solo"),
        ("vencidos", "Medición y equipo", "Aviso de cobros vencidos", "Te avisa y le recuerda al cliente cuando un pago se atrasa.", False),
        ("resumen", "Medición y equipo", "Resumen semanal por correo", "Cada lunes recibes cuánto vendiste, cuánto falta y quién avanzó más.", "reportes" in objetivos),
    ]
    return {
        "user_id": user_id,
        "version": 1,
        "brief": brief,
        "total_contactos": 0,
        "contactos": [],
        "vendedores": ["Tú"],  # la persona; su equipo se agrega después
        "tareas": {"porHacer": [], "enCurso": [], "hecho": []},
        "eventos": [{"id": nuevo_id(), "e": "🤖", "t": "Shifu creó tu CRM", "ts": ahora}],
        "automatizaciones": [{"id": i, "pilar": p, "t": t, "d": d, "on": bool(on)} for i, p, t, d, on in automatizaciones],
        "secciones": {},
        "created_at": ahora,
        "updated_at": ahora,
    }
