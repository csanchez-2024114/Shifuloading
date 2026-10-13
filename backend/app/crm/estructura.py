"""Operaciones que cambian la ESTRUCTURA del CRM: etapas, secciones visibles, secciones propias (listas), campos y registros.

Es lo que permite que cada persona moldee su CRM hablando con Shifu: quitar lo que no usa, crear secciones nuevas con sus propios
campos (por ejemplo "Proveedores" con Nombre, Teléfono y Próxima compra) y cambiar las etapas de su proceso de venta.

Igual que `operaciones`, son funciones puras: reciben el CRM y devuelven uno nuevo, o lanzan `ErrorCrm`.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.crm.operaciones import ErrorCrm, _copia, _registrar, ahora_utc, nuevo_id
from app.crm.secciones import ETAPAS, IDS_SECCION, titulo_seccion

TIPOS_DE_CAMPO = ("texto", "numero", "fecha")
MAX_LISTAS = 12
MAX_CAMPOS = 15
MAX_REGISTROS = 2000
MIN_ETAPAS, MAX_ETAPAS = 2, 8
LARGO_NOMBRE = 28
LARGO_ETAPA = 24


def normalizar(doc: dict) -> dict:
    """Pone los campos de estructura que un CRM guardado antes de que existieran. No cambia nada si ya están."""
    doc.setdefault("etapas", list(ETAPAS))
    doc.setdefault("ocultas", [])
    doc.setdefault("campos_contacto", [])
    doc.setdefault("listas", [])
    doc.setdefault("ciudad", None)
    for c in doc.get("contactos", []):
        c.setdefault("extra", {})
    return doc


def _nombre(texto: Any, largo: int, que: str) -> str:
    n = " ".join(str(texto or "").split())[:largo]
    if not n:
        raise ErrorCrm(422, f"Falta {que}.")
    return n[:1].upper() + n[1:]


def _igual(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


# ───────── Valores de los campos ─────────

def valor_de_tipo(tipo: str, valor: Any, campo: str = "") -> Any:
    """Convierte lo que escribió la persona al formato guardado, o lanza ErrorCrm si no sirve. Vacío = sin valor (None)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == "texto":
        return str(valor).strip()[:200]
    if tipo == "numero":
        if isinstance(valor, bool):
            raise ErrorCrm(422, f"“{campo}” debe ser un número.")
        if isinstance(valor, (int, float)):
            n = float(valor)
        else:
            limpio = re.sub(r"[^\d,.\-]", "", str(valor))
            # Una sola coma y ningún punto: con 1 o 2 dígitos después es decimal ("3,5"); con 3 es separador de miles ("1,250").
            if limpio.count(",") == 1 and "." not in limpio and len(limpio.split(",")[1]) != 3:
                limpio = limpio.replace(",", ".")
            else:
                limpio = limpio.replace(",", "")
            try:
                n = float(limpio)
            except ValueError:
                raise ErrorCrm(422, f"“{campo}” debe ser un número y recibí “{valor}”.") from None
        return int(n) if n.is_integer() else n
    if tipo == "fecha":
        s = str(valor).strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, formato).date().isoformat()
            except ValueError:
                continue
        raise ErrorCrm(422, f"“{campo}” debe ser una fecha (por ejemplo 25/12/2026) y recibí “{valor}”.")
    raise ErrorCrm(422, f"Tipo de campo desconocido: {tipo}.")


def valores_validos(campos: list[dict], valores: dict[str, Any]) -> dict[str, Any]:
    """`valores` va por id de campo. Devuelve solo los que existen, ya convertidos. Un campo desconocido es un error, no se ignora."""
    por_id = {c["id"]: c for c in campos}
    salida: dict[str, Any] = {}
    for cid, v in (valores or {}).items():
        campo = por_id.get(cid)
        if campo is None:
            raise ErrorCrm(422, "Ese campo no existe.")
        salida[cid] = valor_de_tipo(campo["tipo"], v, campo["nombre"])
    return salida


def _campo_nuevo(nombre: Any, tipo: Any, existentes: list[dict]) -> dict:
    n = _nombre(nombre, LARGO_NOMBRE, "el nombre del campo")
    t = str(tipo or "texto").strip().lower()
    if t not in TIPOS_DE_CAMPO:
        raise ErrorCrm(422, f"El tipo del campo debe ser uno de: {', '.join(TIPOS_DE_CAMPO)}.")
    if any(_igual(c["nombre"], n) for c in existentes):
        raise ErrorCrm(422, f"Ya existe un campo llamado “{n}”.")
    if len(existentes) >= MAX_CAMPOS:
        raise ErrorCrm(422, f"Una sección admite hasta {MAX_CAMPOS} campos.")
    return {"id": "f_" + nuevo_id()[:8], "nombre": n, "tipo": t}


# ───────── Etapas del proceso de venta ─────────

def etapas_definir(doc: dict, etapas: list[str], ahora: datetime | None = None) -> dict:
    """Cambia las etapas. Los contactos que ya estaban en una etapa que se conserva siguen ahí; los demás pasan a la etapa que
    ocupa el mismo lugar en la lista nueva (o a la última si la lista nueva es más corta)."""
    ahora = ahora or ahora_utc()
    limpias: list[str] = []
    for e in etapas or []:
        n = " ".join(str(e).split())[:LARGO_ETAPA]
        if n and not any(_igual(n, x) for x in limpias):
            limpias.append(n[:1].upper() + n[1:])
    if not MIN_ETAPAS <= len(limpias) <= MAX_ETAPAS:
        raise ErrorCrm(422, f"Se necesitan entre {MIN_ETAPAS} y {MAX_ETAPAS} etapas distintas.")
    out = _copia(doc)
    viejas = out["etapas"]
    mapa = {}
    for i, v in enumerate(viejas):
        igual = next((n for n in limpias if _igual(n, v)), None)
        mapa[v] = igual or limpias[min(i, len(limpias) - 1)]
    for c in out["contactos"]:
        c["etapa"] = mapa.get(c["etapa"], limpias[0])
    out["etapas"] = limpias
    _registrar(out, "🧭", f"Cambiaste las etapas a: {', '.join(limpias)}", ahora)
    return out


# ───────── Secciones del menú ─────────

def _visibles(doc: dict) -> int:
    return len([i for i in IDS_SECCION if i not in doc["ocultas"]]) + len(doc["listas"])


def seccion_ocultar(doc: dict, seccion_id: str, ahora: datetime | None = None) -> dict:
    """Quita una sección integrada del menú (no borra sus datos: se puede volver a mostrar)."""
    ahora = ahora or ahora_utc()
    if seccion_id not in IDS_SECCION:
        raise ErrorCrm(404, "Esa sección no existe.")
    if seccion_id in doc["ocultas"]:
        return doc
    if _visibles(doc) <= 1:
        raise ErrorCrm(422, "Tiene que quedar al menos una sección visible.")
    out = _copia(doc)
    out["ocultas"].append(seccion_id)
    _registrar(out, "🙈", f"Quitaste la sección “{titulo_seccion((out.get('brief') or {}).get('rubro'), seccion_id, out['secciones'])}” del menú", ahora)
    return out


def seccion_mostrar(doc: dict, seccion_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    if seccion_id not in IDS_SECCION:
        raise ErrorCrm(404, "Esa sección no existe.")
    if seccion_id not in doc["ocultas"]:
        return doc
    out = _copia(doc)
    out["ocultas"].remove(seccion_id)
    _registrar(out, "👀", f"Volviste a mostrar la sección “{titulo_seccion((out.get('brief') or {}).get('rubro'), seccion_id, out['secciones'])}”", ahora)
    return out


# ───────── Secciones propias (listas) ─────────

def _lista(doc: dict, lista_id: str) -> dict:
    l = next((x for x in doc["listas"] if x["id"] == lista_id), None)
    if l is None:
        raise ErrorCrm(404, "Esa sección no existe.")
    return l


def lista_crear(doc: dict, nombre: Any, campos: list[dict] | None = None, ahora: datetime | None = None) -> dict:
    """Crea una sección propia. `campos` es [{nombre, tipo}]; si no hay ninguno, lleva un campo "Nombre"."""
    ahora = ahora or ahora_utc()
    if len(doc["listas"]) >= MAX_LISTAS:
        raise ErrorCrm(422, f"Puedes tener hasta {MAX_LISTAS} secciones propias.")
    n = _nombre(nombre, LARGO_NOMBRE, "el nombre de la sección")
    rubro = (doc.get("brief") or {}).get("rubro")
    nombres_en_uso = [titulo_seccion(rubro, i, doc["secciones"]) for i in IDS_SECCION] + [l["nombre"] for l in doc["listas"]]
    if any(_igual(n, x) for x in nombres_en_uso):
        raise ErrorCrm(422, f"Ya hay una sección llamada “{n}”.")
    lista_campos: list[dict] = []
    for c in (campos or [{"nombre": "Nombre", "tipo": "texto"}]):
        lista_campos.append(_campo_nuevo((c or {}).get("nombre"), (c or {}).get("tipo"), lista_campos))
    out = _copia(doc)
    out["listas"].append({"id": "l_" + nuevo_id()[:8], "nombre": n, "campos": lista_campos, "registros": []})
    _registrar(out, "🧩", f"Creaste la sección “{n}” con los campos: {', '.join(c['nombre'] for c in lista_campos)}", ahora)
    return out


def lista_eliminar(doc: dict, lista_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    l = _lista(doc, lista_id)
    if _visibles(doc) <= 1:
        raise ErrorCrm(422, "Tiene que quedar al menos una sección visible.")
    out = _copia(doc)
    out["listas"] = [x for x in out["listas"] if x["id"] != lista_id]
    _registrar(out, "🗑️", f"Eliminaste la sección “{l['nombre']}” y sus {len(l['registros'])} registros", ahora)
    return out


def lista_renombrar(doc: dict, lista_id: str, nombre: Any, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    l = _lista(doc, lista_id)
    n = _nombre(nombre, LARGO_NOMBRE, "el nombre de la sección")
    out = _copia(doc)
    _lista(out, lista_id)["nombre"] = n
    _registrar(out, "✏️", f"Renombraste “{l['nombre']}” a “{n}”", ahora)
    return out


# ───────── Campos (de los contactos o de una sección propia) ─────────

def _ambito(doc: dict, ambito: str) -> tuple[list[dict], str]:
    """(lista de campos, nombre para mostrar) de "contactos" o de una sección propia."""
    if ambito == "contactos":
        return doc["campos_contacto"], "los contactos"
    l = _lista(doc, ambito)
    return l["campos"], f"“{l['nombre']}”"


def campo_agregar(doc: dict, ambito: str, nombre: Any, tipo: Any = "texto", ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    nuevo = _campo_nuevo(nombre, tipo, campos)
    campos.append(nuevo)
    _registrar(out, "🧱", f"Agregaste el campo “{nuevo['nombre']}” ({nuevo['tipo']}) a {donde}", ahora)
    return out


def campo_eliminar(doc: dict, ambito: str, campo_id: str, ahora: datetime | None = None) -> dict:
    """Quita un campo y los valores que tenía guardados."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    campo = next((c for c in campos if c["id"] == campo_id), None)
    if campo is None:
        raise ErrorCrm(404, "Ese campo no existe.")
    if ambito != "contactos" and len(campos) <= 1:
        raise ErrorCrm(422, "Una sección necesita al menos un campo.")
    campos[:] = [c for c in campos if c["id"] != campo_id]
    if ambito == "contactos":
        for c in out["contactos"]:
            c["extra"].pop(campo_id, None)
    else:
        for r in _lista(out, ambito)["registros"]:
            r["valores"].pop(campo_id, None)
    _registrar(out, "🗑️", f"Quitaste el campo “{campo['nombre']}” de {donde}", ahora)
    return out


# ───────── Registros de una sección propia ─────────

def registro_agregar(doc: dict, lista_id: str, valores: dict[str, Any], ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    if len(l["registros"]) >= MAX_REGISTROS:
        raise ErrorCrm(422, f"Una sección admite hasta {MAX_REGISTROS} registros por ahora.")
    ok = valores_validos(l["campos"], valores)
    if not any(v is not None for v in ok.values()):
        raise ErrorCrm(422, "El registro no tiene ningún valor.")
    l["registros"].insert(0, {"id": nuevo_id(), "valores": ok, "creado": ahora})
    primero = next((str(v) for c in l["campos"] if (v := ok.get(c["id"])) is not None), "un registro")
    _registrar(out, "➕", f"Agregaste “{primero}” en “{l['nombre']}”", ahora)
    return out


def registro_actualizar(doc: dict, lista_id: str, registro_id: str, valores: dict[str, Any], ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    r = next((x for x in l["registros"] if x["id"] == registro_id), None)
    if r is None:
        raise ErrorCrm(404, "Ese registro no existe.")
    ok = valores_validos(l["campos"], valores)
    if not ok:
        raise ErrorCrm(422, "No hay nada que cambiar.")
    for cid, v in ok.items():
        if v is None:
            r["valores"].pop(cid, None)
        else:
            r["valores"][cid] = v
    _registrar(out, "🔁", f"Actualizaste un registro de “{l['nombre']}”", ahora)
    return out


def registro_eliminar(doc: dict, lista_id: str, registro_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    if not any(x["id"] == registro_id for x in l["registros"]):
        raise ErrorCrm(404, "Ese registro no existe.")
    l["registros"] = [x for x in l["registros"] if x["id"] != registro_id]
    _registrar(out, "🗑️", f"Eliminaste un registro de “{l['nombre']}”", ahora)
    return out


def resumen_de_registro(lista: dict, registro: dict) -> str:
    """Texto corto para nombrar un registro ("Ferretería Díaz · 5555-1234")."""
    partes = [str(v) for c in lista["campos"] if (v := registro["valores"].get(c["id"])) is not None]
    return " · ".join(partes[:2]) or "(vacío)"
