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

TIPOS_DE_CAMPO = ("texto", "numero", "fecha", "lista")  # "lista" = el valor es una de las `opciones` fijas del campo
# Esquema 2 (sistema de diseño del laboratorio): más tipos. "estado" es el nombre del laboratorio para "lista" (opciones fijas).
# TIPOS_DE_CAMPO se queda como estaba porque es el enum que ve el agente de Carlos (su prompt no cambia).
TIPOS_V2 = ("texto", "numero", "dinero", "fecha", "hora", "estado", "lista")
CON_OPCIONES = ("estado", "lista")
MIN_OPCIONES, MAX_OPCIONES, LARGO_OPCION = 2, 8, 24
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
    doc.setdefault("resumen_ia", None)
    for c in doc.get("contactos", []):
        c.setdefault("extra", {})
    for k, v in esquema2_faltante(doc).items():  # esquema 2, perezoso: solo lo que falta; nunca toca registros
        doc.setdefault(k, v)
    return doc


# ───────── Esquema 2 (perezoso) ─────────

ESQUEMA = 2


def toma_vacia() -> dict:
    """La toma de requisitos sin empezar (la misma forma que `tomaVacia` del laboratorio)."""
    return {"activa": False, "fase": "juntando", "ficha": {"objetivo": "", "secciones": [], "bloques": [], "marca": {}, "restricciones": []},
            "notas": [], "preguntadas": [], "rechazo": False}


def inicio_por_defecto(doc: dict) -> list[dict]:
    """Las piezas del inicio de un CRM que todavía no tiene: un resumen de los contactos por etapa (si se ven) y la tabla de la
    primera sección propia. Los uid son fijos para que leer dos veces el mismo CRM sin guardar dé lo mismo."""
    bloques: list[dict] = []
    if "contactos" not in (doc.get("ocultas") or []):
        bloques.append({"uid": "b0", "vista": "kpis", "seccion": "contactos", "opciones": {"por": "etapa"}, "ancho": 12, "alto": 1})
    if doc.get("listas"):
        bloques.append({"uid": f"b{len(bloques)}", "vista": "tabla", "seccion": doc["listas"][0]["id"], "opciones": {}, "ancho": 12, "alto": 2})
    return bloques


def esquema2_faltante(doc: dict) -> dict:
    """Lo del esquema 2 que el documento todavía no tiene, con su valor por defecto. No cambia `doc`.
    `inicio` solo se arma si la clave no existe: si la persona quitó todas las piezas (lista vacía), se respeta."""
    faltan: dict[str, Any] = {}
    if "esquema" not in doc:
        faltan["esquema"] = ESQUEMA
    if "plantilla" not in doc:
        faltan["plantilla"] = None
    if "inicio" not in doc:
        faltan["inicio"] = inicio_por_defecto(doc)
    if "paginas" not in doc:
        faltan["paginas"] = {}
    if "marca" not in doc:
        faltan["marca"] = {}
    if "toma" not in doc:
        faltan["toma"] = toma_vacia()
    if "puntos_n" not in doc:
        faltan["puntos_n"] = 0
    return faltan


def _nombre(texto: Any, largo: int, que: str) -> str:
    n = " ".join(str(texto or "").split())[:largo]
    if not n:
        raise ErrorCrm(422, f"Falta {que}.")
    return n[:1].upper() + n[1:]


def _igual(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


# ───────── Valores de los campos ─────────

def opciones_validas(opciones: Any) -> list[str]:
    """Las opciones de un campo tipo lista: de 2 a 8, sin repetir (da igual mayúsculas), cortas. Lanza ErrorCrm si no sirven."""
    limpias: list[str] = []
    for o in opciones if isinstance(opciones, list) else []:
        n = " ".join(str(o or "").split())[:LARGO_OPCION]
        if n and not any(_igual(n, x) for x in limpias):
            limpias.append(n)
    if not MIN_OPCIONES <= len(limpias) <= MAX_OPCIONES:
        raise ErrorCrm(422, f"Una lista necesita entre {MIN_OPCIONES} y {MAX_OPCIONES} opciones distintas.")
    return limpias


def valor_de_tipo(tipo: str, valor: Any, campo: str = "", opciones: list[str] | None = None) -> Any:
    """Convierte lo que escribió la persona al formato guardado, o lanza ErrorCrm si no sirve. Vacío = sin valor (None)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == "texto":
        return str(valor).strip()[:200]
    if tipo in CON_OPCIONES:  # "estado" (laboratorio) = "lista" (Carlos)
        elegida = next((o for o in opciones or [] if _igual(o, str(valor))), None)
        if elegida is None:
            raise ErrorCrm(422, f"“{campo}” solo admite: {', '.join(opciones or [])}. Recibí “{valor}”.")
        return elegida
    if tipo == "hora":
        return _hora(valor, campo)
    if tipo in ("numero", "dinero"):  # dinero se guarda como número; el formato (Q, $) lo pone la pantalla
        if isinstance(valor, bool):
            raise ErrorCrm(422, f"“{campo}” debe ser un número.")
        if isinstance(valor, (int, float)):
            n = float(valor)
        else:
            limpio = re.sub(r"[^\d,.\-]", "", str(valor))
            if "," in limpio and "." in limpio:
                # Con los dos, el que aparece al final es el decimal: "1,190.50" y "1.190,50" valen lo mismo (1190.5).
                decimal = "," if limpio.rfind(",") > limpio.rfind(".") else "."
                limpio = limpio.replace("," if decimal == "." else ".", "").replace(decimal, ".")
            elif limpio.count(",") == 1 and len(limpio.split(",")[1]) != 3:
                limpio = limpio.replace(",", ".")  # una sola coma con 1 o 2 dígitos después es decimal ("3,5"); con 3 es separador de miles ("1,250")
            elif limpio.count(".") > 1:
                limpio = limpio.replace(".", "")  # "1.190.500": puntos como separador de miles
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


_HORA = re.compile(r"^(\d{1,2})(?:\s*[:h.]\s*(\d{2}))?\s*(?:([ap])\.?\s*m?\.?)?$", re.I)


def _hora(valor: Any, campo: str) -> str:
    """'16:30', '4:30 pm', '4pm', '9' → 'HH:MM'. Lanza ErrorCrm si no es una hora."""
    m = _HORA.match(str(valor).strip().lower())
    if m:
        h, mi, ap = int(m[1]), int(m[2] or 0), m[3]
        if ap:
            h = h % 12 + (12 if ap == "p" else 0) if 1 <= h <= 12 else 99
        if h <= 23 and mi <= 59:
            return f"{h:02d}:{mi:02d}"
    raise ErrorCrm(422, f"“{campo}” debe ser una hora (por ejemplo 16:30) y recibí “{valor}”.")


def valores_validos(campos: list[dict], valores: dict[str, Any]) -> dict[str, Any]:
    """`valores` va por id de campo. Devuelve solo los que existen, ya convertidos. Un campo desconocido es un error, no se ignora."""
    por_id = {c["id"]: c for c in campos}
    salida: dict[str, Any] = {}
    for cid, v in (valores or {}).items():
        campo = por_id.get(cid)
        if campo is None:
            raise ErrorCrm(422, "Ese campo no existe.")
        salida[cid] = valor_de_tipo(campo["tipo"], v, campo["nombre"], campo.get("opciones"))
    return salida


def _campo_nuevo(nombre: Any, tipo: Any, existentes: list[dict], opciones: Any = None) -> dict:
    n = _nombre(nombre, LARGO_NOMBRE, "el nombre del campo")
    t = str(tipo or "texto").strip().lower()
    if t not in TIPOS_V2:
        raise ErrorCrm(422, f"El tipo del campo debe ser uno de: {', '.join(TIPOS_V2)}.")
    if any(_igual(c["nombre"], n) for c in existentes):
        raise ErrorCrm(422, f"Ya existe un campo llamado “{n}”.")
    if len(existentes) >= MAX_CAMPOS:
        raise ErrorCrm(422, f"Una sección admite hasta {MAX_CAMPOS} campos.")
    campo = {"id": "f_" + nuevo_id()[:8], "nombre": n, "tipo": t}
    if t in CON_OPCIONES:
        campo["opciones"] = opciones_validas(opciones)
    return campo


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
        lista_campos.append(_campo_nuevo((c or {}).get("nombre"), (c or {}).get("tipo"), lista_campos, (c or {}).get("opciones")))
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


def campo_agregar(doc: dict, ambito: str, nombre: Any, tipo: Any = "texto", ahora: datetime | None = None, opciones: Any = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    nuevo = _campo_nuevo(nombre, tipo, campos, opciones)
    campos.append(nuevo)
    _registrar(out, "🧱", f"Agregaste el campo “{nuevo['nombre']}” ({nuevo['tipo']}) a {donde}", ahora)
    return out


def campo_hacer_lista(doc: dict, ambito: str, campo_id: str, opciones: Any, ahora: datetime | None = None) -> dict:
    """Convierte un campo que ya existe en una lista de opciones fijas (o cambia las opciones de una lista). Los valores que
    ya coinciden con una opción se conservan con su forma correcta; los demás se quedan como estaban (no se pierde nada)."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    campo = next((c for c in campos if c["id"] == campo_id), None)
    if campo is None:
        raise ErrorCrm(404, "Ese campo no existe.")
    opts = opciones_validas(opciones)
    campo["tipo"], campo["opciones"] = "lista", opts
    if ambito == "contactos":
        filas = [c.setdefault("extra", {}) for c in out["contactos"]]
    else:
        filas = [r["valores"] for r in _lista(out, ambito)["registros"]]
    for valores in filas:
        if isinstance(valores.get(campo_id), str):
            valores[campo_id] = next((o for o in opts if _igual(o, valores[campo_id])), valores[campo_id])
    _registrar(out, "🧱", f"El campo “{campo['nombre']}” de {donde} ahora es una lista: {', '.join(opts)}", ahora)
    return out


def campo_mover(doc: dict, ambito: str, campo_id: str, posicion: Any, ahora: datetime | None = None) -> dict:
    """Cambia el lugar de un campo (de los contactos o de una sección propia). `posicion`: "inicio", "final" o el número de lugar (1 = primero)."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    i = next((k for k, c in enumerate(campos) if c["id"] == campo_id), None)
    if i is None:
        raise ErrorCrm(404, "Ese campo no existe.")
    p = str(posicion).strip().lower()
    if p in ("inicio", "principio", "primero", "al inicio", "al principio"):
        destino = 0
    elif p in ("final", "ultimo", "último", "al final"):
        destino = len(campos) - 1
    else:
        try:
            destino = int(p) - 1
        except ValueError:
            raise ErrorCrm(422, "La posición debe ser “inicio”, “final” o un número (1 es el primero).") from None
    destino = max(0, min(len(campos) - 1, destino))
    campo = campos.pop(i)
    campos.insert(destino, campo)
    _registrar(out, "↔️", f"Moviste el campo “{campo['nombre']}” de {donde} al lugar {destino + 1}", ahora)
    return out


def campo_renombrar(doc: dict, ambito: str, campo_id: str, nombre: Any, ahora: datetime | None = None) -> dict:
    """Le cambia el nombre a un campo (los datos que ya tenía se conservan)."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    campos, donde = _ambito(out, ambito)
    campo = next((c for c in campos if c["id"] == campo_id), None)
    if campo is None:
        raise ErrorCrm(404, "Ese campo no existe.")
    n = _nombre(nombre, LARGO_NOMBRE, "el nombre del campo")
    if any(c["id"] != campo_id and _igual(c["nombre"], n) for c in campos):
        raise ErrorCrm(422, f"Ya existe un campo llamado “{n}”.")
    anterior = campo["nombre"]
    campo["nombre"] = n
    _registrar(out, "✏️", f"Renombraste el campo “{anterior}” a “{n}” en {donde}", ahora)
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


def registros_agregar_lote(doc: dict, lista_id: str, filas: list[dict[str, Any]], ahora: datetime | None = None, lote: dict | None = None) -> tuple[dict, int, int]:
    """Importa varias filas de una vez (por ejemplo, las de un Excel). Cada fila va por id de campo. Devuelve (CRM, agregadas, omitidas).
    Se omiten las filas vacías, las que traen un valor que no sirve para su campo (un texto donde va un precio) y las que ya existen idénticas.
    `lote` ({id, nombre}) marca de qué importación vienen, para poder quitarla entera después (una importación grande llega en varias tandas con el mismo id)."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    nuevos: list[dict] = []
    omitidas = 0
    primer_problema = ""
    existentes = [{k: v for k, v in r["valores"].items() if v is not None} for r in l["registros"]]
    for fila in filas:
        if len(l["registros"]) + len(nuevos) >= MAX_REGISTROS:
            omitidas += 1
            continue
        try:
            ok = valores_validos(l["campos"], fila)
        except ErrorCrm as e:
            omitidas += 1
            primer_problema = primer_problema or e.mensaje
            continue
        limpio = {k: v for k, v in ok.items() if v is not None}
        if not limpio or limpio in existentes:
            omitidas += 1
            continue
        existentes.append(limpio)
        nuevos.append({"id": nuevo_id(), "valores": ok, "creado": ahora, **({"lote": lote["id"]} if lote else {})})
    if not nuevos:
        raise ErrorCrm(422, "No pude importar ninguna fila: revisa que cada columna tenga lo que corresponde." + (f" Por ejemplo: {primer_problema}" if primer_problema else ""))
    l["registros"][0:0] = nuevos  # en el mismo orden del archivo, arriba
    if lote and not any(i["id"] == lote["id"] for i in l.setdefault("importaciones", [])):
        l["importaciones"].append({"id": lote["id"], "nombre": " ".join(str(lote.get("nombre") or "Importación").split())[:80], "creado": ahora})
    _registrar(out, "📥", f"Importaste {len(nuevos)} {'registro' if len(nuevos) == 1 else 'registros'} en “{l['nombre']}”", ahora)
    return out, len(nuevos), omitidas


def importacion_quitar(doc: dict, lista_id: str, lote_id: str, ahora: datetime | None = None) -> dict:
    """Quita de la sección todos los registros de una importación (incluso los que la persona ya editó). No se puede deshacer."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    quitar = [r for r in l["registros"] if r.get("lote") == lote_id]
    if not quitar and not any(i["id"] == lote_id for i in l.get("importaciones", [])):
        raise ErrorCrm(404, "Esa importación no existe.")
    nombre = next((i["nombre"] for i in l.get("importaciones", []) if i["id"] == lote_id), "una importación")
    l["registros"] = [r for r in l["registros"] if r.get("lote") != lote_id]
    l["importaciones"] = [i for i in l.get("importaciones", []) if i["id"] != lote_id]
    _registrar(out, "🧹", f"Quitaste la importación “{nombre}” ({len(quitar)} {'registro' if len(quitar) == 1 else 'registros'}) de “{l['nombre']}”", ahora)
    return out


def registros_vaciar(doc: dict, lista_id: str, ahora: datetime | None = None) -> dict:
    """Borra TODOS los registros de una sección (lo importado y lo escrito a mano). La sección y sus campos se quedan. No se puede deshacer."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    if not l["registros"]:
        raise ErrorCrm(404, "Esta sección ya está vacía.")
    n = len(l["registros"])
    l["registros"] = []
    l["importaciones"] = []
    _registrar(out, "🧹", f"Vaciaste “{l['nombre']}” ({n} {'registro' if n == 1 else 'registros'})", ahora)
    return out


def importaciones_quitar_todas(doc: dict, lista_id: str, ahora: datetime | None = None) -> dict:
    """Quita de la sección TODO lo que se importó (todas sus importaciones, incluso lo editado). Lo que la persona escribió a mano se queda."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    l = _lista(out, lista_id)
    quitar = [r for r in l["registros"] if r.get("lote")]
    if not quitar and not l.get("importaciones"):
        raise ErrorCrm(404, "Esta sección no tiene nada importado.")
    n_imp = len(l.get("importaciones", []))
    l["registros"] = [r for r in l["registros"] if not r.get("lote")]
    l["importaciones"] = []
    _registrar(out, "🧹", f"Quitaste todo lo importado en “{l['nombre']}” ({len(quitar)} {'registro' if len(quitar) == 1 else 'registros'} de {n_imp} {'importación' if n_imp == 1 else 'importaciones'})", ahora)
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


# ───────── Ejemplos sembrados (esquema 2) ─────────

def ejemplos_quitar(doc: dict, seccion_id: str | None = None, ahora: datetime | None = None) -> dict:
    """Quita los registros de ejemplo (`ejemplo: true`, los que siembra una plantilla) de todas las secciones o de una.
    Lo que la persona escribió o importó se queda. Lanza ErrorCrm si no hay ejemplos que quitar."""
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    quitados = 0
    for l in out["listas"]:
        if seccion_id in (None, l["id"]):
            antes = len(l["registros"])
            l["registros"] = [r for r in l["registros"] if not r.get("ejemplo")]
            quitados += antes - len(l["registros"])
    if seccion_id in (None, "contactos"):
        antes = len(out["contactos"])
        out["contactos"] = [c for c in out["contactos"] if not c.get("ejemplo")]
        out["total_contactos"] = max(0, out["total_contactos"] - (antes - len(out["contactos"])))
        quitados += antes - len(out["contactos"])
    if seccion_id in (None, "desarrollo"):
        for col, tareas in out["tareas"].items():
            out["tareas"][col] = [t for t in tareas if not t.get("ejemplo")]
            quitados += len(tareas) - len(out["tareas"][col])
    if not quitados:
        raise ErrorCrm(404, "No hay registros de ejemplo que quitar.")
    _registrar(out, "🧹", f"Quitaste {quitados} {'registro' if quitados == 1 else 'registros'} de ejemplo", ahora)
    return out
