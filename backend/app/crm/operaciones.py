"""Operaciones sobre el CRM (agregar, cambiar, quitar).

Son funciones puras: reciben el documento del CRM y devuelven uno nuevo, sin tocar el original. Si algo no se puede
hacer lanzan `ErrorCrm`, que las rutas convierten en una respuesta HTTP.
"""
from __future__ import annotations

import copy
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.crm.secciones import IDS_COLUMNA, IDS_SECCION, titulo_seccion

MAX_EVENTOS = 30
MAX_CONTACTOS = 5000  # tope por CRM mientras los contactos vivan dentro del mismo documento


class ErrorCrm(Exception):
    """Algo que el usuario pidió y no se puede hacer. `estado` es el código HTTP que le corresponde."""

    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


def nuevo_id() -> str:
    return uuid.uuid4().hex


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _registrar(doc: dict, emoji: str, texto: str, ahora: datetime) -> None:
    doc["eventos"] = [{"id": nuevo_id(), "e": emoji, "t": texto, "ts": ahora}, *doc["eventos"]][:MAX_EVENTOS]


def _copia(doc: dict) -> dict:
    return copy.deepcopy(doc)


# ───────── Contactos ─────────

def contactos_crear(doc: dict, filas: list[dict], canal: str, texto: str | None = None, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    if not filas:
        raise ErrorCrm(422, "No hay contactos para agregar.")
    if doc["total_contactos"] + len(filas) > MAX_CONTACTOS:
        raise ErrorCrm(422, f"Un CRM admite hasta {MAX_CONTACTOS} contactos por ahora.")
    from app.crm import estructura  # import tardío: estructura usa este módulo

    out = _copia(doc)
    for f in filas:
        if f.get("etapa") and f["etapa"] not in out["etapas"]:
            raise ErrorCrm(422, f"La etapa “{f['etapa']}” no existe. Las etapas son: {', '.join(out['etapas'])}.")
    nuevos = [{
        "id": nuevo_id(), "n": f["n"], "det": f.get("det") or None, "canal": f.get("canal") or canal,
        "etapa": f.get("etapa") or out["etapas"][0], "dueno": out["vendedores"][0], "ultimo_contacto": ahora,
        "extra": {k: v for k, v in estructura.valores_validos(out["campos_contacto"], f.get("extra") or {}).items() if v is not None},
    } for f in filas]
    from app.crm import automatizaciones  # import tardío: automatizaciones usa este módulo

    automatizaciones.repartir(out, nuevos)  # si "repartir" está encendida, cada contacto nuevo se asigna por turnos al equipo
    out["contactos"] = [*nuevos, *out["contactos"]]
    out["total_contactos"] += len(nuevos)
    _registrar(out, "➕", texto or (f"Agregaste a {nuevos[0]['n']}" if len(nuevos) == 1 else f"Agregaste {len(nuevos)} contactos"), ahora)
    return out


def contactos_actualizar(doc: dict, contacto_id: str, cambios: dict[str, Any], texto: str | None = None, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    c = next((x for x in out["contactos"] if x["id"] == contacto_id), None)
    if c is None:
        raise ErrorCrm(404, "Ese contacto no existe.")
    if "etapa" in cambios and cambios["etapa"] not in out["etapas"]:
        raise ErrorCrm(422, f"La etapa debe ser una de: {', '.join(out['etapas'])}.")
    if "dueno" in cambios and cambios["dueno"] not in out["vendedores"]:
        raise ErrorCrm(422, "Esa persona no está en tu equipo.")
    anterior = dict(c)
    for campo in ("n", "det", "canal", "etapa", "dueno"):
        if campo in cambios:
            c[campo] = cambios[campo]
    if cambios.get("extra"):
        from app.crm import estructura  # import tardío: estructura usa este módulo

        for cid, v in estructura.valores_validos(out["campos_contacto"], cambios["extra"]).items():
            if v is None:
                c["extra"].pop(cid, None)
            else:
                c["extra"][cid] = v
    if "etapa" in cambios and cambios["etapa"] != anterior["etapa"]:
        c["ultimo_contacto"] = ahora  # pasar de etapa cuenta como contacto reciente
    if texto is None:
        if c["etapa"] != anterior["etapa"]:
            texto = f"{c['n']} pasó a “{c['etapa']}”"
        elif c["n"] != anterior["n"]:
            texto = f"{anterior['n']} ahora se llama {c['n']}"
        else:
            texto = f"Actualizaste a {c['n']}"
    _registrar(out, "🔁", texto, ahora)
    return out


def contactos_eliminar(doc: dict, contacto_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    c = next((x for x in out["contactos"] if x["id"] == contacto_id), None)
    if c is None:
        raise ErrorCrm(404, "Ese contacto no existe.")
    out["contactos"] = [x for x in out["contactos"] if x["id"] != contacto_id]
    out["total_contactos"] = max(0, out["total_contactos"] - 1)
    _registrar(out, "🗑️", f"Eliminaste a {c['n']}", ahora)
    return out


# ───────── Tareas ─────────

def _buscar_tarea(doc: dict, tarea_id: str) -> tuple[str, dict] | None:
    for col in IDS_COLUMNA:
        for x in doc["tareas"][col]:
            if x["id"] == tarea_id:
                return col, x
    return None


ZONA = timezone(timedelta(hours=int(os.getenv("CRM_UTC_OFFSET", "-6"))))  # hora local del negocio (Guatemala, sin horario de verano)
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def hora_local(ahora: datetime) -> datetime:
    return (ahora if ahora.tzinfo else ahora.replace(tzinfo=timezone.utc)).astimezone(ZONA)


def fecha_en_palabras(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{_DIAS[d.weekday()]} {d.day} de {_MESES[d.month - 1]} de {d.year}"


def _cita_valida(vence: Any, hora: Any, ahora: datetime) -> tuple[str | None, str | None]:
    """(fecha AAAA-MM-DD, hora HH:MM) ya validadas. La fecha no puede estar en el pasado (en hora local del negocio)."""
    from app.crm import estructura  # import tardío: estructura usa este módulo

    fecha = estructura.valor_de_tipo("fecha", vence, "La fecha")
    h = None
    if hora not in (None, ""):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(hora))
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise ErrorCrm(422, f"La hora debe ser como 16:30 y recibí “{hora}”.")
        h = f"{int(m[1]):02d}:{m[2]}"
    if fecha is None:
        if h:
            raise ErrorCrm(422, "Una hora necesita también una fecha.")
        return None, None
    local = hora_local(ahora)
    if fecha < local.date().isoformat() or (fecha == local.date().isoformat() and h and h < local.strftime("%H:%M")):
        raise ErrorCrm(422, f"Esa fecha ya pasó: hoy es {fecha_en_palabras(local.date().isoformat())}. Pídele otra a la persona.")
    return fecha, h


def tareas_crear(doc: dict, texto_tarea: str, ahora: datetime | None = None, vence: str | None = None, hora: str | None = None,
                 contacto_id: str | None = None) -> dict:
    ahora = ahora or ahora_utc()
    fecha, h = _cita_valida(vence, hora, ahora)
    out = _copia(doc)
    tarea: dict[str, Any] = {"id": nuevo_id(), "t": texto_tarea}
    if fecha:
        tarea["vence"] = fecha
        if h:
            tarea["hora"] = h
    if contacto_id:
        if not any(c["id"] == contacto_id for c in out["contactos"]):
            raise ErrorCrm(404, "Ese contacto no existe.")
        tarea["contacto_id"] = contacto_id
    out["tareas"]["porHacer"].append(tarea)
    _registrar(out, "✅", f"Agregaste la tarea “{texto_tarea}”", ahora)
    return out


def tareas_actualizar(doc: dict, tarea_id: str, cambios: dict[str, Any], ahora: datetime | None = None) -> dict:
    """Cambia el texto, la fecha, la hora o el contacto de una tarea. `vence: ""` le quita la fecha."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    hit = _buscar_tarea(out, tarea_id)
    if hit is None:
        raise ErrorCrm(404, "Esa tarea no existe.")
    tarea = hit[1]
    if "t" in cambios:
        tarea["t"] = cambios["t"]
    if "vence" in cambios or "hora" in cambios:
        vence = cambios["vence"] if "vence" in cambios else tarea.get("vence")
        hora = cambios["hora"] if "hora" in cambios else tarea.get("hora")
        if "vence" in cambios and cambios["vence"] in (None, "") and "hora" not in cambios:
            hora = None  # sin fecha no tiene sentido una hora suelta
        fecha, h = _cita_valida(vence, hora, ahora)
        for k in ("vence", "hora"):
            tarea.pop(k, None)
        if fecha:
            tarea["vence"] = fecha
            if h:
                tarea["hora"] = h
    if "contacto_id" in cambios:
        if cambios["contacto_id"] and not any(c["id"] == cambios["contacto_id"] for c in out["contactos"]):
            raise ErrorCrm(404, "Ese contacto no existe.")
        if cambios["contacto_id"]:
            tarea["contacto_id"] = cambios["contacto_id"]
        else:
            tarea.pop("contacto_id", None)
    _registrar(out, "✏️", f"Cambiaste la tarea “{tarea['t']}”", ahora)
    return out


def tareas_mover(doc: dict, tarea_id: str, destino: str) -> dict:
    if destino not in IDS_COLUMNA:
        raise ErrorCrm(422, f"La columna debe ser una de: {', '.join(IDS_COLUMNA)}.")
    out = _copia(doc)
    hit = _buscar_tarea(out, tarea_id)
    if hit is None:
        raise ErrorCrm(404, "Esa tarea no existe.")
    col, tarea = hit
    if col != destino:
        out["tareas"][col] = [x for x in out["tareas"][col] if x["id"] != tarea_id]
        out["tareas"][destino].append(tarea)
    return out


def tareas_eliminar(doc: dict, tarea_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    hit = _buscar_tarea(out, tarea_id)
    if hit is None:
        raise ErrorCrm(404, "Esa tarea no existe.")
    col, tarea = hit
    out["tareas"][col] = [x for x in out["tareas"][col] if x["id"] != tarea_id]
    _registrar(out, "🗑️", f"Eliminaste la tarea “{tarea['t']}”", ahora)
    return out


# ───────── Equipo y negocio ─────────

MAX_VENDEDORES = 20


def vendedor_agregar(doc: dict, nombre: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    n = " ".join(str(nombre or "").split())[:40]
    if len(n) < 2:
        raise ErrorCrm(422, "Falta el nombre del vendedor.")
    n = n[:1].upper() + n[1:]
    if any(v.strip().lower() == n.lower() for v in doc["vendedores"]):
        raise ErrorCrm(422, f"{n} ya está en el equipo.")
    if len(doc["vendedores"]) >= MAX_VENDEDORES:
        raise ErrorCrm(422, f"Un CRM admite hasta {MAX_VENDEDORES} personas en el equipo por ahora.")
    out = _copia(doc)
    out["vendedores"].append(n)
    _registrar(out, "🧑‍💼", f"{n} se unió al equipo", ahora)
    return out


def ciudad_fijar(doc: dict, ciudad: str) -> dict:
    c = " ".join(str(ciudad or "").split())[:60]
    if len(c) < 2:
        raise ErrorCrm(422, "Falta la ciudad.")
    out = _copia(doc)
    out["ciudad"] = c[:1].upper() + c[1:]
    return out


# ───────── Automatizaciones y secciones ─────────

def automatizacion_fijar(doc: dict, auto_id: str, on: bool, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    a = next((x for x in out["automatizaciones"] if x["id"] == auto_id), None)
    if a is None:
        raise ErrorCrm(404, "Esa automatización no existe.")
    from app.crm import automatizaciones  # import tardío: automatizaciones usa este módulo

    if on and not automatizaciones.CATALOGO[auto_id][3]:
        raise ErrorCrm(422, f"“{a['t']}” todavía no funciona. {automatizaciones.CATALOGO[auto_id][4]}")
    if a["on"] != on:
        a["on"] = on
        _registrar(out, "⚡" if on else "⏸️", f"{'Activaste' if on else 'Apagaste'}: {a['t']}", ahora)
    return out


def seccion_renombrar(doc: dict, seccion_id: str, nombre: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    if seccion_id.startswith("l_"):  # una sección propia: su nombre vive en la propia sección
        from app.crm import estructura  # import tardío: estructura usa este módulo

        return estructura.lista_renombrar(doc, seccion_id, nombre, ahora)
    if seccion_id not in IDS_SECCION:
        raise ErrorCrm(404, "Esa sección no existe.")
    out = _copia(doc)
    rubro = (out.get("brief") or {}).get("rubro")
    anterior = titulo_seccion(rubro, seccion_id, out["secciones"])
    out["secciones"][seccion_id] = nombre
    _registrar(out, "✏️", f"Renombraste “{anterior}” a “{nombre}”", ahora)
    return out
