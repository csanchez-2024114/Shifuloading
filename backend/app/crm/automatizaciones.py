"""Automatizaciones del CRM: lo que Shifu hace solo.

Hoy funcionan de verdad tres que no necesitan conectar nada de afuera:
- recordatorios: crea una tarea cuando un contacto lleva 3 días sin cambiar de etapa.
- reparto: asigna cada contacto nuevo, por turnos, a las personas del equipo.
- resumen: una vez por semana deja en Actividad un resumen de contactos y tareas.

Las otras tres (bienvenida por WhatsApp, crear el contacto desde un mensaje, aviso de cobros vencidos) necesitan WhatsApp, correo o el
módulo de cobros: se muestran como "Próximamente" y no se pueden encender, para no aparentar que hacen algo.

No hay un proceso en segundo plano: lo pendiente se calcula cuando alguien abre o toca el CRM (`ejecutar_pendientes`, desde el repositorio),
de forma que repetirlo no duplica nada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.crm import operaciones as op

DIAS_SIN_AVANCE = 3
MAX_RECORDATORIOS_POR_VEZ = 10

# id: (pilar, nombre, descripción, ¿funciona hoy?, nota si no)
CATALOGO: dict[str, tuple[str, str, str, bool, str | None]] = {
    "recordatorios": ("Estructura", "Recordatorios de seguimiento",
                      f"Crea una tarea cuando un contacto lleva {DIAS_SIN_AVANCE} días sin cambiar de etapa.", True, None),
    "bienvenida": ("Estructura", "Bienvenida automática por WhatsApp", "Responde al instante cuando alguien te escribe por primera vez.", False,
                   "Próximamente: necesita conectar tu WhatsApp."),
    "contacto": ("Estructura", "Crear el contacto desde cada mensaje", "Shifu detecta quién te escribe y lo agrega con lo que pidió.", False,
                 "Próximamente: necesita conectar tu WhatsApp o tu correo."),
    "reparto": ("Medición y equipo", "Repartir contactos nuevos entre el equipo", "Cada contacto nuevo se asigna por turnos a las personas de tu equipo.", True, None),
    "vencidos": ("Medición y equipo", "Aviso de cobros vencidos", "Te avisa y le recuerda al cliente cuando un pago se atrasa.", False,
                 "Próximamente: necesita el módulo de cobros."),
    "resumen": ("Medición y equipo", "Resumen semanal", "Cada semana deja en Actividad un resumen de tus contactos y tareas.", True, None),
}
DISPONIBLES = [i for i, (_p, _n, _d, ok, _x) in CATALOGO.items() if ok]


def armar(encendidas: set[str] | None = None) -> list[dict]:
    """La lista de automatizaciones de un CRM nuevo. Solo las que funcionan pueden nacer encendidas."""
    encendidas = encendidas or set()
    return [{"id": i, "pilar": p, "t": n, "d": d, "on": ok and i in encendidas} for i, (p, n, d, ok, _x) in CATALOGO.items()]


def normalizar(doc: dict) -> dict:
    """Pone al día las automatizaciones de un CRM guardado antes: textos actuales, las que faltan, y apaga las que todavía no existen."""
    por_id = {a["id"]: a for a in doc.get("automatizaciones", [])}
    doc["automatizaciones"] = [
        {"id": i, "pilar": p, "t": n, "d": d, "on": bool(ok and por_id.get(i, {}).get("on", False))} for i, (p, n, d, ok, _x) in CATALOGO.items()
    ]
    return doc


def detalle(auto_id: str) -> dict:
    """Lo que el frontend necesita saber de cada una, además de lo guardado."""
    ok, nota = CATALOGO[auto_id][3], CATALOGO[auto_id][4]
    return {"disponible": ok, "nota": nota}


def _on(doc: dict, auto_id: str) -> bool:
    return any(a["id"] == auto_id and a["on"] for a in doc.get("automatizaciones", []))


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # Mongo devuelve fechas sin zona horaria: siempre UTC


# ───────── Reparto: al crear contactos ─────────

def repartir(doc: dict, nuevos: list[dict]) -> None:
    """Asigna `dueno` por turnos entre el equipo a los contactos recién creados (modifica `doc` y `nuevos`, que ya son copias)."""
    if not _on(doc, "reparto") or len(doc["vendedores"]) < 2:
        return
    turno = int(doc.get("reparto_n", 0))
    for c in nuevos:
        c["dueno"] = doc["vendedores"][turno % len(doc["vendedores"])]
        turno += 1
    doc["reparto_n"] = turno


# ───────── Lo pendiente al abrir el CRM ─────────

def _recordatorios(doc: dict, ahora: datetime) -> int:
    if not _on(doc, "recordatorios") or not doc["etapas"]:
        return 0
    final = doc["etapas"][-1]  # un contacto que ya llegó a la última etapa no necesita seguimiento
    limite = ahora - timedelta(days=DIAS_SIN_AVANCE)
    hoy = op.hora_local(ahora).date().isoformat()
    creados = 0
    for c in doc["contactos"]:
        if creados >= MAX_RECORDATORIOS_POR_VEZ:
            break
        ultimo = _utc(c["ultimo_contacto"])
        if c["etapa"] == final or ultimo > limite or c.get("recordado") == ultimo.isoformat():
            continue
        c["recordado"] = ultimo.isoformat()  # ya se le recordó por este tramo sin avance: no se repite hasta que cambie de etapa
        doc["tareas"]["porHacer"].append({"id": op.nuevo_id(), "t": f"Dar seguimiento a {c['n']}"[:60], "vence": hoy, "contacto_id": c["id"], "auto": "recordatorios"})
        creados += 1
    if creados:
        op._registrar(doc, "⚡", f"Recordatorio automático: {creados} contacto{'s' if creados > 1 else ''} sin avance en {DIAS_SIN_AVANCE} días", ahora)
    return creados


def _clave_de_semana(ahora: datetime) -> str:
    anio, semana, _ = op.hora_local(ahora).isocalendar()
    return f"{anio}-W{semana:02d}"


def _resumen(doc: dict, ahora: datetime) -> bool:
    if not _on(doc, "resumen"):
        return False
    clave = _clave_de_semana(ahora)
    if doc.get("ultimo_resumen") == clave:
        return False
    primera_vez = doc.get("ultimo_resumen") is None
    doc["ultimo_resumen"] = clave
    if primera_vez:  # se marca la semana en que se encendió: el primer resumen llega la semana siguiente
        return True
    hoy = op.hora_local(ahora).date().isoformat()
    tareas = doc["tareas"]
    vencidas = sum(1 for col in ("porHacer", "enCurso") for t in tareas[col] if t.get("vence") and t["vence"] < hoy)
    if doc["total_contactos"] or any(tareas.values()):
        por_etapa = ", ".join(f"{sum(1 for c in doc['contactos'] if c['etapa'] == e)} en {e}" for e in doc["etapas"])
        texto = (f"Resumen de la semana: {doc['total_contactos']} contactos ({por_etapa}). "
                 f"Tareas: {len(tareas['porHacer'])} por hacer, {len(tareas['enCurso'])} en curso, {len(tareas['hecho'])} hechas"
                 + (f", {vencidas} vencida{'s' if vencidas > 1 else ''}." if vencidas else "."))
        op._registrar(doc, "📊", texto[:240], ahora)
    return True


def ejecutar_pendientes(doc: dict, ahora: datetime | None = None) -> tuple[dict, bool]:
    """Corre lo que toque ahora. Devuelve (doc, hubo cambios); si no hubo, es el mismo objeto. Repetirlo no duplica nada."""
    ahora = ahora or op.ahora_utc()
    if not any(a["on"] for a in doc.get("automatizaciones", [])):
        return doc, False
    out = op._copia(doc)
    cambio = bool(_recordatorios(out, ahora))
    cambio = _resumen(out, ahora) or cambio
    return (out, True) if cambio else (doc, False)
