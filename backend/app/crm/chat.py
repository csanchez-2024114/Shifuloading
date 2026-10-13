"""Cerebro del chat del CRM: entiende frases sencillas en español para agregar, modificar y eliminar.

Es determinista (sin LLM): sirve para que el CRM funcione de punta a punta sin claves de IA y deja fijado el contrato del
chat. Cuando se conecte el agente de Shifu, este módulo queda como respaldo y la IA llama a las mismas
`operaciones` como herramientas. Antes de borrar siempre pide confirmación: el servidor devuelve `pendiente` y el
cliente lo reenvía con el siguiente mensaje.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from app.crm import operaciones as op
from app.crm.secciones import ETAPAS, IDS_COLUMNA, IDS_SECCION, titulo_seccion

MAX_NOMBRE = 40
MAX_TAREA = 60
MAX_SECCION = 28


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()


def _capitaliza(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in s.split())


_RE_CONFIRMA = re.compile(r"^(si|claro|dale|confirmo|ok|adelante|borralo|eliminalo)")
_RE_IMPORTAR = re.compile(r"(import|excel|notas|csv|hoja de calculo|sheets|archivo)")
# Si la frase empieza con una orden ("agrega la tarea importar contactos"), manda la orden: "importar" es parte del texto.
_RE_ORDEN = re.compile(r"^(agrega|anade|crea|registra|anota|suma|nuevo|nueva|elimina|borra|quita|saca|remueve|renombra|cambia|mueve|pasa|modifica|actualiza|pon|activa|enciende|prende|desactiva|apaga)")
_RE_AUTO = re.compile(r"^(activa|enciende|prende|desactiva|apaga)r?\s+(?:la\s+|el\s+|las\s+|los\s+)?(.+)$")
_RE_RENOMBRAR = re.compile(
    r"^(?:renombra|renombrar|cambia(?:r)?(?:\s+el\s+nombre\s+de)?|mueve|pasa|modifica|actualiza|pon)\s+"
    r"(?:la\s+secci[oó]n\s+|secci[oó]n\s+|la\s+etapa\s+de\s+|a\s+)?(.+?)\s+(?:a|por|como)\s+(.+)$", re.IGNORECASE)
_RE_ELIMINAR = re.compile(r"^(?:elimina(?:r)?|borra(?:r)?|quita(?:r)?|saca(?:r)?|remueve)\s+(?:a\s+|al\s+|el\s+|la\s+)?(.+)$", re.IGNORECASE)
_RE_AGREGAR = re.compile(r"^(?:agrega(?:r)?|a[ñn]ade|a[ñn]adir|crea(?:r)?|registra(?:r)?|anota(?:r)?|suma(?:r)?|nuevo|nueva)\s+(.+)$", re.IGNORECASE)
_RE_TAREA = re.compile(r"^(?:la\s+|una\s+)?tarea\s*:?\s*(.+)$", re.IGNORECASE)
_RE_TIPO_CONTACTO = re.compile(r"^(?:a\s+|al\s+|un\s+|una\s+|el\s+|la\s+)?(?:contacto|cliente|paciente|alumno|comprador|interesado|cuenta|prospecto)?\s*(?:llamad[oa]\s+)?", re.IGNORECASE)
_RE_SALUDO = re.compile(r"^(hola|buenas|hey|ayuda|que puedes)")


def sanear_pendiente(p: Any) -> dict | None:
    """El cliente reenvía `pendiente`: solo se acepta con la forma esperada."""
    if isinstance(p, dict) and p.get("tipo") in ("contacto", "tarea") and isinstance(p.get("id"), str) and len(p["id"]) <= 64:
        return {"tipo": p["tipo"], "id": p["id"]}
    return None


def responder(doc: dict, crudo: str, pendiente: dict | None = None, ahora: datetime | None = None) -> dict:
    """Devuelve `{doc, respuesta, vista?, pendiente?}`. `doc` es el CRM ya con los cambios (o el mismo si no hubo)."""
    ahora = ahora or op.ahora_utc()
    texto = crudo.strip()
    t = _norm(texto)
    estado = {"doc": doc}
    rubro = (doc.get("brief") or {}).get("rubro")

    def titulo(seccion_id: str) -> str:
        return titulo_seccion(rubro, seccion_id, estado["doc"]["secciones"])

    def salida(respuesta: str, **extra: Any) -> dict:
        return {"doc": estado["doc"], "respuesta": respuesta, **extra}

    def buscar_contacto(q: str) -> dict | None:
        k = _norm(q)
        return next((c for c in estado["doc"]["contactos"] if k and k in _norm(c["n"])), None)

    def buscar_seccion(q: str) -> str | None:
        k = _norm(q)
        if not k:
            return None
        return next((i for i in IDS_SECCION if _norm(titulo(i)) in k or k in _norm(titulo(i))), None)

    def buscar_etapa(q: str) -> str | None:
        k = _norm(q)
        return next((e for e in ETAPAS if _norm(e) == k or _norm(e).split(" ")[-1] in k), None)

    def buscar_tarea(q: str) -> dict | None:
        k = _norm(q)
        for col in IDS_COLUMNA:
            for x in estado["doc"]["tareas"][col]:
                if k and k in _norm(x["t"]):
                    return x
        return None

    # 1) Confirmación de un borrado que quedó pendiente
    if pendiente:
        if _RE_CONFIRMA.match(t):
            try:
                if pendiente["tipo"] == "contacto":
                    c = next((x for x in doc["contactos"] if x["id"] == pendiente["id"]), None)
                    estado["doc"] = op.contactos_eliminar(doc, pendiente["id"], ahora)
                    return salida(f"Listo, eliminé a {c['n'] if c else 'ese contacto'} de tu CRM.")
                x = next((y for col in IDS_COLUMNA for y in doc["tareas"][col] if y["id"] == pendiente["id"]), None)
                estado["doc"] = op.tareas_eliminar(doc, pendiente["id"], ahora)
                return salida(f"Listo, eliminé la tarea “{x['t'] if x else ''}”.")
            except op.ErrorCrm:
                return salida("Eso ya no existe, así que no hay nada que borrar.")
        return salida("Perfecto, no borré nada. 👍")

    # 2) Importar datos
    if _RE_IMPORTAR.search(t) and not _RE_ORDEN.match(t):
        return salida("Claro. Te llevé a “Importar datos”: pega ahí tus notas o las celdas de tu Excel y yo las ordeno como contactos.", vista="importar")

    # 3) Activar o apagar automatizaciones
    m = _RE_AUTO.match(t)
    if m:
        palabras = [w for w in _norm(m.group(2)).split(" ") if len(w) > 3]
        a = next((x for x in doc["automatizaciones"] if any(w[:6] in _norm(x["t"]) for w in palabras)), None)
        if a is None:
            return salida(f"No encontré esa automatización. Tienes: {', '.join(x['t'].lower() for x in doc['automatizaciones'])}.")
        quiere = m.group(1) in ("activa", "enciende", "prende")
        estado["doc"] = op.automatizacion_fijar(doc, a["id"], quiere, ahora)
        return salida(f"{'Activé' if quiere else 'Apagué'} “{a['t']}”.", vista="automatizaciones")

    # 4) Renombrar una sección o cambiar un contacto de etapa / de nombre
    m = _RE_RENOMBRAR.match(texto)
    if m:
        x, y = m.group(1), m.group(2)
        sec = buscar_seccion(x)
        if sec and not buscar_contacto(x):
            nuevo = _capitaliza(y)[:MAX_SECCION]
            estado["doc"] = op.seccion_renombrar(doc, sec, nuevo, ahora)
            return salida(f"Hecho: ahora la sección se llama “{nuevo}”.")
        c = buscar_contacto(x)
        if c:
            et = buscar_etapa(y)
            if et:
                estado["doc"] = op.contactos_actualizar(doc, c["id"], {"etapa": et}, f"{c['n']} pasó a “{et}”", ahora)
                return salida(f"Listo: {c['n']} ahora está en “{et}”.", vista="contactos")
            nuevo = _capitaliza(y)[:MAX_NOMBRE]
            estado["doc"] = op.contactos_actualizar(doc, c["id"], {"n": nuevo}, f"{c['n']} ahora se llama {nuevo}", ahora)
            return salida(f"Listo, cambié el nombre de {c['n']} a {nuevo}.", vista="contactos")
        return salida(f"No encontré “{x}” ni como sección ni como contacto. ¿Me das el nombre tal como aparece?")

    # 5) Eliminar (siempre con confirmación)
    m = _RE_ELIMINAR.match(texto)
    if m:
        tarea = re.match(r"^tarea\s*:?\s*(.+)$", m.group(1), re.IGNORECASE)
        if tarea:
            x = buscar_tarea(tarea.group(1))
            if x is None:
                return salida(f"No encontré la tarea “{tarea.group(1)}”.")
            return salida(f"¿Seguro que quieres eliminar la tarea “{x['t']}”? Responde “sí” para confirmar.", pendiente={"tipo": "tarea", "id": x["id"]})
        c = buscar_contacto(re.sub(r"^(contacto|cliente|paciente|alumno|comprador|interesado|cuenta)\s+", "", m.group(1), flags=re.IGNORECASE))
        if c is None:
            return salida(f"No encuentro a “{m.group(1)}”. Escríbelo como aparece en tu lista.")
        return salida(f"¿Seguro que quieres eliminar a {c['n']}? Responde “sí” para confirmar.", pendiente={"tipo": "contacto", "id": c["id"]})

    # 6) Agregar un contacto o una tarea
    m = _RE_AGREGAR.match(texto)
    if m:
        tarea = _RE_TAREA.match(m.group(1))
        if tarea:
            nombre = tarea.group(1).strip()
            nombre = (nombre[:1].upper() + nombre[1:])[:MAX_TAREA]
            estado["doc"] = op.tareas_crear(doc, nombre, ahora)
            return salida(f"Anoté la tarea “{nombre}” en “Por hacer”.", vista="desarrollo")
        nombre = _capitaliza(_RE_TIPO_CONTACTO.sub("", m.group(1), count=1))[:MAX_NOMBRE]
        if len(nombre) < 2:
            return salida("¿Cómo se llama? Por ejemplo: “Agrega a Laura Gómez”.")
        existente = buscar_contacto(nombre)
        if existente and existente["n"].lower() == nombre.lower():
            return salida(f"{nombre} ya está en tu lista.")
        estado["doc"] = op.contactos_crear(doc, [{"n": nombre}], "Chat con Shifu", None, ahora)
        return salida(f"Listo, agregué a {nombre} en “{titulo('contactos')}”, en la etapa “Nuevo”.", vista="contactos")

    if _RE_SALUDO.match(t):
        return salida("Puedo agregar contactos y tareas, cambiarlos de etapa o de nombre, renombrar secciones, activar automatizaciones y eliminar lo que ya no uses (siempre te pido confirmación).")
    return salida("Aún no entendí eso. Prueba con: “Agrega a Laura Gómez”, “Renombra Cobros a Facturación”, “Mueve a [nombre] a Cliente”, “Activa los recordatorios” o “Elimina a [nombre]”.")
