"""Secciones virtuales: una vista uniforme de TODO lo que tiene registros (contactos, tareas y secciones propias), sin mover los datos.

El laboratorio trabaja con "secciones" que tienen campos y registros. En el CRM de Carlos los contactos y las tareas viven en su
propio lugar con su propia forma; aquí se muestran como secciones más, y cada escritura va a la función de siempre:
  - `contactos` → `operaciones.contactos_*`
  - `desarrollo` (las tareas, con el id de su menú) → `operaciones.tareas_*`
  - cada lista (`l_…`) → `estructura.registro_*`

Funciones puras, como `operaciones`: reciben el CRM y devuelven uno nuevo, o lanzan `ErrorCrm`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from assistant.packs.crm import estructura as est
from assistant.packs.crm import operaciones as op
from assistant.packs.crm.operaciones import ErrorCrm
from assistant.packs.crm.secciones import COLUMNAS, titulo_seccion

CONTACTOS, TAREAS = "contactos", "desarrollo"
ESTADOS_TAREA = [nombre for _, nombre in COLUMNAS]  # «Por hacer», «En curso», «Hecho»
COLUMNA_DE = {nombre: col for col, nombre in COLUMNAS}
ESTADO_DE = {col: nombre for col, nombre in COLUMNAS}
LARGO_NOMBRE_CONTACTO, LARGO_DETALLE, LARGO_CANAL, LARGO_TAREA = 40, 120, 40, 60  # los mismos topes que las rutas de Carlos

# Campo de la sección → clave del contacto
_CLAVE_CONTACTO = {"nombre": "n", "detalle": "det", "canal": "canal", "etapa": "etapa", "responsable": "dueno"}
_CLAVE_TAREA = {"tarea": "t", "vence": "vence", "hora": "hora"}


def _campo(c: dict) -> dict:
    """El campo con el vocabulario del laboratorio: "lista" (Carlos) sale como "estado" (son lo mismo; lo guardado no cambia)."""
    tipo = "estado" if c["tipo"] == "lista" else c["tipo"]
    return {"id": c["id"], "nombre": c["nombre"], "tipo": tipo, **({"opciones": c["opciones"]} if c.get("opciones") else {})}


def _campos_contactos(doc: dict) -> list[dict]:
    return [
        {"id": "nombre", "nombre": "Nombre", "tipo": "texto"},
        {"id": "detalle", "nombre": "Detalle", "tipo": "texto"},
        {"id": "canal", "nombre": "Canal", "tipo": "texto"},
        {"id": "etapa", "nombre": "Etapa", "tipo": "estado", "opciones": list(doc["etapas"])},
        {"id": "responsable", "nombre": "Responsable", "tipo": "texto"},
        *[_campo(c) for c in doc["campos_contacto"]],
    ]


_CAMPOS_TAREAS = [
    {"id": "tarea", "nombre": "Tarea", "tipo": "texto"},
    {"id": "vence", "nombre": "Vence", "tipo": "fecha"},
    {"id": "hora", "nombre": "Hora", "tipo": "hora"},
    {"id": "estado", "nombre": "Estado", "tipo": "estado", "opciones": ESTADOS_TAREA},
]


def secciones_de(doc: dict) -> list[dict]:
    """Todas las secciones con registros, en el orden del menú: contactos, tareas y las secciones propias.
    Las integradas que la persona ocultó no aparecen (sus datos siguen ahí)."""
    rubro = (doc.get("brief") or {}).get("rubro")
    ocultas = doc.get("ocultas") or []
    out: list[dict] = []
    if CONTACTOS not in ocultas:
        out.append({"id": CONTACTOS, "titulo": titulo_seccion(rubro, CONTACTOS, doc["secciones"]), "campos": _campos_contactos(doc),
                    "vista": "tabla", "opciones": {}, "icono": "usuarios", "grupo": 0, "virtual": "contactos"})
    if TAREAS not in ocultas:
        out.append({"id": TAREAS, "titulo": titulo_seccion(rubro, TAREAS, doc["secciones"]), "campos": [dict(c) for c in _CAMPOS_TAREAS],
                    "vista": "tablero", "opciones": {"por": "estado", "titulo": "tarea"}, "icono": "tablero", "grupo": 0, "virtual": "tareas"})
    for l in doc["listas"]:
        s = {"id": l["id"], "titulo": l["nombre"], "campos": [_campo(c) for c in l["campos"]], "vista": l.get("vista") or "tabla",
             "opciones": l.get("opciones") or {}, "icono": l.get("icono") or "tabla", "grupo": l.get("grupo", 0), "virtual": None}
        for k in ("ficha", "tarjeta"):
            if l.get(k) is not None:
                s[k] = l[k]
        out.append(s)
    return out


def _seccion(doc: dict, sec_id: str) -> dict:
    s = next((x for x in secciones_de(doc) if x["id"] == sec_id), None)
    if s is None:
        raise ErrorCrm(404, "Esa sección no existe.")
    return s


# ───────── Lectura ─────────

def _registro_contacto(c: dict) -> dict:
    valores = {campo: c.get(clave) for campo, clave in _CLAVE_CONTACTO.items()}
    valores.update(c.get("extra") or {})
    return {"id": c["id"], "valores": {k: v for k, v in valores.items() if v is not None}, **({"ejemplo": True} if c.get("ejemplo") else {})}


def _registro_tarea(t: dict, col: str) -> dict:
    valores = {campo: t.get(clave) for campo, clave in _CLAVE_TAREA.items()}
    valores["estado"] = ESTADO_DE[col]
    return {"id": t["id"], "valores": {k: v for k, v in valores.items() if v is not None}, **({"ejemplo": True} if t.get("ejemplo") else {})}


def _registro_lista(r: dict) -> dict:
    return {"id": r["id"], "valores": dict(r["valores"]), **({"ejemplo": True} if r.get("ejemplo") else {})}


def registros_de(doc: dict, sec_id: str) -> list[dict]:
    """Los registros de una sección, todos con la misma forma: {id, valores: {campo_id: valor}, ejemplo?}."""
    s = _seccion(doc, sec_id)
    if s["virtual"] == "contactos":
        return [_registro_contacto(c) for c in doc["contactos"]]
    if s["virtual"] == "tareas":
        return [_registro_tarea(t, col) for col, _ in COLUMNAS for t in doc["tareas"][col]]
    return [_registro_lista(r) for r in est._lista(doc, sec_id)["registros"]]


def _uno(doc: dict, sec_id: str, rid: str) -> dict:
    r = next((x for x in registros_de(doc, sec_id) if x["id"] == rid), None)
    if r is None:
        raise ErrorCrm(404, "Ese registro no existe.")
    return r


# ───────── Conversión de valores ─────────
# En una edición, "" (o None) es «dejar el campo vacío»: se guarda el vacío de Carlos (None, o la clave fuera). Los campos sin los
# que el registro no existe (nombre, canal, etapa, responsable de un contacto; texto y estado de una tarea) no pueden quedar vacíos.

def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _desconocidos(campos: list[dict], valores: dict) -> None:
    ids = {c["id"] for c in campos}
    if any(k not in ids for k in valores):
        raise ErrorCrm(422, "Ese campo no existe.")


def _texto(valor: Any, largo: int, que: str) -> str | None:
    v = est.valor_de_tipo("texto", valor, que)
    if v is not None and len(v) > largo:
        raise ErrorCrm(422, f"“{que}” admite hasta {largo} caracteres.")
    return v


def _cambios_contacto(doc: dict, valores: dict) -> dict:
    """Valores por campo de la sección → los cambios que entiende `operaciones.contactos_*`."""
    _desconocidos(_campos_contactos(doc), valores)
    cambios: dict[str, Any] = {}
    if "nombre" in valores:
        n = _texto(valores["nombre"], LARGO_NOMBRE_CONTACTO, "Nombre")
        if not n:
            raise ErrorCrm(422, "Falta el nombre.")
        cambios["n"] = n
    if "detalle" in valores:
        cambios["det"] = None if _vacio(valores["detalle"]) else _texto(valores["detalle"], LARGO_DETALLE, "Detalle")
    if "canal" in valores:
        canal = _texto(valores["canal"], LARGO_CANAL, "Canal")
        if not canal:
            raise ErrorCrm(422, "Falta el canal.")
        cambios["canal"] = canal
    if "etapa" in valores:
        etapa = est.valor_de_tipo("estado", valores["etapa"], "Etapa", doc["etapas"])
        if etapa is None:
            raise ErrorCrm(422, f"La etapa debe ser una de: {', '.join(doc['etapas'])}.")
        cambios["etapa"] = etapa
    if "responsable" in valores:
        quien = next((v for v in doc["vendedores"] if str(valores["responsable"] or "").strip().lower() == v.lower()), None)
        if quien is None:
            raise ErrorCrm(422, "Esa persona no está en tu equipo.")
        cambios["dueno"] = quien
    extra = {k: v for k, v in valores.items() if k not in _CLAVE_CONTACTO}
    if extra:
        cambios["extra"] = extra  # `operaciones` lo valida con los tipos de cada campo
    return cambios


def _cambios_tarea(valores: dict) -> tuple[dict, str | None]:
    """Valores por campo → (cambios para `operaciones.tareas_*`, columna destino o None)."""
    _desconocidos(_CAMPOS_TAREAS, valores)
    cambios: dict[str, Any] = {}
    if "tarea" in valores:
        t = _texto(valores["tarea"], LARGO_TAREA, "Tarea")
        if not t:
            raise ErrorCrm(422, "Falta el texto de la tarea.")
        cambios["t"] = t
    if "vence" in valores:
        cambios["vence"] = "" if _vacio(valores["vence"]) else valores["vence"]  # "" = sin fecha para `tareas_actualizar`
    if "hora" in valores:
        cambios["hora"] = None if _vacio(valores["hora"]) else est.valor_de_tipo("hora", valores["hora"], "Hora")
    columna = None
    if "estado" in valores:
        estado = est.valor_de_tipo("estado", valores["estado"], "Estado", ESTADOS_TAREA)
        if estado is None:
            raise ErrorCrm(422, f"El estado debe ser uno de: {', '.join(ESTADOS_TAREA)}.")
        columna = COLUMNA_DE[estado]
    return cambios, columna


# ───────── Escritura ─────────

def _con_id(lista: list[dict], viejo: str, nuevo: str | None) -> str:
    """Le pone al registro recién creado el id que ya se nombró (el que vio el modelo en el texto del resultado)."""
    if nuevo:
        next(r for r in lista if r["id"] == viejo)["id"] = nuevo
    return nuevo or viejo


def registro_agregar(doc: dict, sec_id: str, valores: dict[str, Any], ahora: datetime | None = None, canal: str = "Chat",
                     id: str | None = None) -> tuple[dict, dict]:
    """Agrega un registro a la sección. Devuelve (CRM nuevo, registro con la forma uniforme).
    `id`: el id ya generado por quien llama (por ejemplo `registros.ejecutar_dato`); sin él se genera como siempre."""
    s = _seccion(doc, sec_id)
    valores = dict(valores or {})
    if id is not None:
        id = str(id).strip()
        if not id or len(id) > 80:
            raise ErrorCrm(422, "El id del registro no sirve.")
        if any(r["id"] == id for r in registros_de(doc, sec_id)):
            raise ErrorCrm(409, "Ya existe un registro con ese id.")
    if s["virtual"] == "contactos":
        cambios = _cambios_contacto(doc, valores)
        if not cambios.get("n"):
            raise ErrorCrm(422, "Falta el nombre.")
        fila = {"n": cambios["n"], **{k: cambios[k] for k in ("det", "canal", "etapa", "extra") if cambios.get(k)}}
        out = op.contactos_crear(doc, [fila], canal, None, ahora)
        if "dueno" in cambios:  # `contactos_crear` pone al primero del equipo (o reparte); si la persona dijo quién, se respeta
            out["contactos"][0]["dueno"] = cambios["dueno"]
        _con_id(out["contactos"], out["contactos"][0]["id"], id)
        return out, _registro_contacto(out["contactos"][0])
    if s["virtual"] == "tareas":
        cambios, columna = _cambios_tarea(valores)
        if not cambios.get("t"):
            raise ErrorCrm(422, "Falta el texto de la tarea.")
        out = op.tareas_crear(doc, cambios["t"], ahora, cambios.get("vence") or None, cambios.get("hora"))
        tid = _con_id(out["tareas"]["porHacer"], out["tareas"]["porHacer"][-1]["id"], id)
        if columna and columna != "porHacer":
            out = op.tareas_mover(out, tid, columna)
        return out, _uno(out, sec_id, tid)
    out = est.registro_agregar(doc, sec_id, valores, ahora)
    registros = est._lista(out, sec_id)["registros"]
    _con_id(registros, registros[0]["id"], id)
    return out, _registro_lista(registros[0])


def registro_actualizar(doc: dict, sec_id: str, rid: str, cambios: dict[str, Any], ahora: datetime | None = None) -> tuple[dict, dict]:
    """Cambia valores de un registro (por id de campo). Devuelve (CRM nuevo, registro actualizado)."""
    s = _seccion(doc, sec_id)
    cambios = dict(cambios or {})
    if not cambios:
        raise ErrorCrm(422, "No hay nada que cambiar.")
    if s["virtual"] == "contactos":
        _uno(doc, sec_id, rid)
        out = op.contactos_actualizar(doc, rid, _cambios_contacto(doc, cambios), None, ahora)
        return out, _uno(out, sec_id, rid)
    if s["virtual"] == "tareas":
        _uno(doc, sec_id, rid)
        campos, columna = _cambios_tarea(cambios)
        out = op.tareas_actualizar(doc, rid, campos, ahora) if campos else doc
        if columna:
            out = op.tareas_mover(out, rid, columna)
        return out, _uno(out, sec_id, rid)
    out = est.registro_actualizar(doc, sec_id, rid, cambios, ahora)
    return out, _uno(out, sec_id, rid)


def registro_eliminar(doc: dict, sec_id: str, rid: str, ahora: datetime | None = None) -> dict:
    s = _seccion(doc, sec_id)
    if s["virtual"] == "contactos":
        return op.contactos_eliminar(doc, rid, ahora)
    if s["virtual"] == "tareas":
        return op.tareas_eliminar(doc, rid, ahora)
    return est.registro_eliminar(doc, sec_id, rid, ahora)
