"""Arma un CRM nuevo a partir de las respuestas del cuestionario (el "brief").

Hoy es determinista y usa datos de ejemplo para que la persona pueda probarlo desde el primer minuto. Cuando se conecte
el agente, aquí es donde la IA propondrá etapas, campos y automatizaciones a la medida del negocio.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.crm.operaciones import ahora_utc, nuevo_id
from app.crm.secciones import ETAPAS

_NOMBRES = ["Ana Morales", "Luis Pérez", "Sofía Ríos", "Marcos Díaz", "Valeria Soto", "Diego Castillo", "Camila Vega", "Jorge Luna",
            "Paola Méndez", "Andrés Cruz", "Lucía Torres", "Mateo Rojas", "Elena Salas", "Hugo Ibarra", "Renata Paz", "Iván Aguirre"]
_EQUIPO = ["Mariana Solís", "Carlos Aguilar", "Diana Hidalgo"]
_CARTERA = {"k1": 40, "k2": 120, "k3": 600, "k4": 1200}
_PERSONAS = {"solo": 1, "chico": 2, "medio": 3, "grande": 4}
_CANALES = {"whatsapp": "WhatsApp", "correo": "Correo", "llamadas": "Llamadas", "redes": "Instagram o Facebook",
            "presencial": "En persona", "web": "Formulario web"}


def generar(user_id: str, brief: dict, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    total = _CARTERA.get(brief.get("cartera"), 60)
    vendedores = (["Tú", *_EQUIPO, "Ana Ruiz"])[: _PERSONAS.get(brief.get("equipo"), 1)]
    canales = [_CANALES.get(c, c) for c in (brief.get("canales") or ["whatsapp"])]
    objetivos = brief.get("objetivos") or []
    brief_canales = brief.get("canales") or []
    visibles = min(total, 16)

    contactos = [{
        "id": nuevo_id(), "n": _NOMBRES[k % len(_NOMBRES)], "det": None, "canal": canales[k % len(canales)],
        "etapa": ETAPAS[k % 4], "dueno": vendedores[k % len(vendedores)], "ultimo_contacto": ahora - timedelta(days=(k % 6) + 1),
    } for k in range(visibles)]

    eventos = [
        ("🤖", "Shifu creó tu CRM", 0), ("📥", f"Se cargaron {total} contactos de ejemplo", 0),
        ("🔔", "Se activaron los recordatorios de seguimiento", 60), ("💬", f"Canales listos para conectar: {', '.join(canales)}", 60),
        ("👋", "Cuenta creada", 3 * 3600),
    ]
    automatizaciones = [
        ("recordatorios", "Estructura", "Recordatorios de seguimiento", "Te avisa cuando un contacto lleva 3 días sin respuesta.",
         "seguimientos" in objetivos or "olvido" in (brief.get("problemas") or [])),
        ("bienvenida", "Estructura", "Bienvenida automática por WhatsApp", "Responde al instante cuando alguien te escribe por primera vez.", "whatsapp" in brief_canales),
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
        "total_contactos": total,
        "contactos": contactos,
        "vendedores": vendedores,
        "tareas": {
            "porHacer": [{"id": nuevo_id(), "t": t} for t in ["Importar contactos", "Definir etapas de venta", "Plantilla de cotización"]],
            "enCurso": [{"id": nuevo_id(), "t": t} for t in ["Conectar WhatsApp", "Invitar al equipo"]],
            "hecho": [{"id": nuevo_id(), "t": t} for t in ["Crear cuenta", "Responder el cuestionario"]],
        },
        "eventos": [{"id": nuevo_id(), "e": e, "t": t, "ts": ahora - timedelta(seconds=seg)} for e, t, seg in eventos],
        "automatizaciones": [{"id": i, "pilar": p, "t": t, "d": d, "on": bool(on)} for i, p, t, d, on in automatizaciones],
        "secciones": {},
        "created_at": ahora,
        "updated_at": ahora,
    }
