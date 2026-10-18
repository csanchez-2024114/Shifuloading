"""Puntos de deshacer (como `conPunto` / `revertirDatos` del laboratorio, con los datos de Carlos).

Cada cambio que hace la persona (por el chat o a mano) deja un punto: qué pidió (`antes_de`), qué partes del CRM cambiaron
(lo mide el código, nunca el modelo) y la foto de ANTES de solo esas partes. Las partes son:
  - `bloques`: el inicio y las páginas propias de cada pestaña;
  - `marca`: colores, fuentes, logo;
  - `estructura`: las secciones propias sin sus registros, las etapas, los campos de los contactos, lo oculto y los nombres;
  - `datos`: los registros de cada sección (contactos, tareas y secciones propias). Solo se guardan las secciones que cambiaron.

Deshacer es selectivo: solo vuelve lo que ESE punto cambió. En los datos se hace a 3 vías (lo de ese pedido vuelve a como
estaba y lo demás se queda: deshacer lo que le cambié a Rosa no revive a Carlos, borrado después). Si un pedido posterior tocó
lo mismo, no hay forma de conservarlo: se deshace también, en cadena, y se dice.

Funciones puras. Los puntos se guardan aparte, en `crm_puntos` (ver `repositorio`).
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from app.crm.operaciones import ErrorCrm, _registrar, ahora_utc
from app.crm.secciones import IDS_COLUMNA

CATEGORIAS = ("bloques", "marca", "estructura", "datos")
MAX_PUNTOS = 30
LARGO_ANTES_DE = 80
CONTACTOS, TAREAS = "contactos", "desarrollo"
NOMBRE = {"bloques": "los bloques del inicio", "marca": "los colores y la marca", "estructura": "las secciones y campos", "datos": "los registros"}
# De cada lista, lo que NO es estructura: sus registros (son datos) y sus importaciones (van con los registros, ver `_reconciliar`).
_NO_META = ("registros", "importaciones")
_FALTA = object()


# ───────── Comparar sin que las fechas engañen ─────────

def _plano(v: Any) -> Any:
    """Mongo devuelve las fechas sin zona horaria (en UTC); recién calculadas la traen. Para comparar, todas sin zona."""
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, dict):
        return {k: _plano(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plano(x) for x in v]
    return v


def _igual(a: Any, b: Any) -> bool:
    return a == b or _plano(a) == _plano(b)


# ───────── Las partes del CRM ─────────

def _bloques(doc: dict) -> dict:
    return {"inicio": doc.get("inicio") or [], "paginas": doc.get("paginas") or {}}


def _estructura(doc: dict) -> dict:
    return {
        "listas_meta": [{k: v for k, v in l.items() if k not in _NO_META} for l in doc.get("listas") or []],
        "etapas": doc.get("etapas") or [],
        "campos_contacto": doc.get("campos_contacto") or [],
        "ocultas": doc.get("ocultas") or [],
        "secciones": doc.get("secciones") or {},
    }


def datos_de(doc: dict) -> dict[str, list[dict]]:
    """Los registros de cada sección tal como se guardan. Las tareas van en una sola lista, cada una con su `columna`."""
    datos = {CONTACTOS: doc.get("contactos") or [],
             TAREAS: [{**t, "columna": col} for col in IDS_COLUMNA for t in (doc.get("tareas") or {}).get(col, [])]}
    for l in doc.get("listas") or []:
        datos[l["id"]] = l.get("registros") or []
    return datos


def _parte(doc: dict, cat: str) -> Any:
    if cat == "bloques":
        return _bloques(doc)
    if cat == "marca":
        return doc.get("marca") or {}
    if cat == "estructura":
        return _estructura(doc)
    return datos_de(doc)


# ───────── Crear el punto ─────────

def con_punto(antes: dict, despues: dict, texto: str, ahora: datetime | None = None) -> tuple[dict, dict | None]:
    """Mide qué cambió de `antes` a `despues` y arma el punto con la foto de ANTES de solo eso.
    Devuelve (CRM con `puntos_n` al día, punto) o (`despues`, None) si no cambió nada que se pueda deshacer."""
    ahora = ahora or ahora_utc()
    cambio: list[str] = []
    foto: dict[str, Any] = {}
    for cat in CATEGORIAS:
        a, b = _parte(antes, cat), _parte(despues, cat)
        if cat == "datos":
            secs = [s for s in dict.fromkeys([*a, *b]) if not _igual(a.get(s, []), b.get(s, []))]
            if secs:
                cambio.append(cat)
                foto[cat] = {s: a.get(s, []) for s in secs}
        elif not _igual(a, b):
            cambio.append(cat)
            foto[cat] = a
    if not cambio:
        return despues, None
    n = int(antes.get("puntos_n") or 0) + 1
    punto = {"n": n, "hora": ahora.isoformat(), "antes_de": " ".join(str(texto or "").split())[:LARGO_ANTES_DE], "cambio": cambio,
             "foto": copy.deepcopy(foto)}
    return {**despues, "puntos_n": n}, punto


# ───────── Deshacer datos a 3 vías ─────────

def _claves(registros: list[dict]) -> tuple[dict[tuple, Any], dict[tuple, Any]]:
    """Cada cosa de los registros como una clave: que el registro exista, cada campo suelto y cada valor de `valores`/`extra`.
    Devuelve (claves para comparar, con las fechas sin zona; los mismos valores tal cual, para devolverlos sin cambiarlos)."""
    m: dict[tuple, Any] = {}
    crudo: dict[tuple, Any] = {}
    for r in registros:
        rid = r["id"]
        m[("r", rid)] = crudo[("r", rid)] = True
        for k, v in r.items():
            if k == "id":
                continue
            if k in ("valores", "extra") and isinstance(v, dict):
                m[("d", rid, k)] = crudo[("d", rid, k)] = True  # el diccionario existe aunque quede vacío
                for kk, vv in v.items():
                    m[("v", rid, k, kk)], crudo[("v", rid, k, kk)] = _plano(vv), vv
            else:
                m[("v", rid, k)], crudo[("v", rid, k)] = _plano(v), v
    return m, crudo


def _difieren(a: dict, b: dict, igual=None) -> dict:
    """Las claves que no valen lo mismo en `a` y en `b`, en el orden del laboratorio (las de `a`, luego las que solo están en `b`)."""
    igual = igual or (lambda x, y: x == y)
    return {k: True for k in dict.fromkeys([*a, *b]) if k not in a or k not in b or not igual(a[k], b[k])}


def _tres_vias(A: dict, B: dict, C: dict, A_salida: dict | None = None, C_salida: dict | None = None, igual=None) -> dict | None:
    """El corazón de `revertirDatos` (laboratorio), igual para el delta del laboratorio y para los registros de Carlos:
    lo que cambió de A a B (el pedido) vuelve en C a como estaba en A; lo demás de C queda. None si después de B algo tocó
    lo mismo (choca). `A_salida`/`C_salida`: los valores a devolver, si se comparó con otros (fechas sin zona)."""
    del_pedido, despues_de = _difieren(A, B, igual), _difieren(B, C, igual)
    if any(k in despues_de for k in del_pedido):
        return None
    A_salida = A if A_salida is None else A_salida
    R = dict(C if C_salida is None else C_salida)
    for k in del_pedido:
        if k in A:
            R[k] = A_salida[k]
        else:
            R.pop(k, None)
    return R


def revertir_seccion(antes: list[dict], despues: list[dict], actual: list[dict]) -> list[dict] | None:
    """Deshace en `actual` solo lo que cambió de `antes` a `despues` (un pedido). None si un cambio posterior tocó lo mismo."""
    (A, A_crudo), (B, _), (C, C_crudo) = _claves(antes), _claves(despues), _claves(actual)
    R = _tres_vias(A, B, C, A_crudo, C_crudo)
    if R is None:
        return None
    # El orden: el de `actual`; lo que vuelve, en su lugar de antes (después del que lo precedía).
    orden = [r["id"] for r in actual if ("r", r["id"]) in R]
    en_orden = set(orden)
    ids_antes = [r["id"] for r in antes]
    for i, rid in enumerate(ids_antes):
        if ("r", rid) in R and rid not in en_orden:
            previo = next((ids_antes[j] for j in range(i - 1, -1, -1) if ids_antes[j] in en_orden), None)
            orden.insert(orden.index(previo) + 1 if previo else 0, rid)
            en_orden.add(rid)
    por_id: dict[str, dict[str, Any]] = {rid: {"id": rid} for rid in orden}
    for k, v in R.items():
        reg = por_id.get(k[1])
        if reg is None or k[0] == "r":
            continue
        if k[0] == "d":
            reg.setdefault(k[2], {})
        elif len(k) == 4:
            reg.setdefault(k[2], {})[k[3]] = v
        else:
            reg[k[2]] = v
    return [por_id[rid] for rid in orden]


def _js(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _claves_delta(d: dict | None) -> dict[tuple, Any]:
    """`clavesDatos` del laboratorio: cada cosa del delta como una clave (los valores de cada registro propio, cada cambio a un
    ejemplo y cada borrado)."""
    d = d or {}
    m: dict[tuple, Any] = {}
    for f, rs in (d.get("nuevos") or {}).items():
        for r in rs:
            m[("n", f, r["id"])] = True
            for k, v in (r.get("valores") or {}).items():
                m[("n", f, r["id"], k)] = v
    for f, ids in (d.get("cambios") or {}).items():
        for rid, vs in ids.items():
            for k, v in vs.items():
                m[("c", f, rid, k)] = v
    for f, ids in (d.get("borrados") or {}).items():
        for rid in ids:
            m[("b", f, rid)] = True
    return m


def revertir_delta(antes: dict | None, despues: dict | None, actual: dict | None) -> dict:
    """`revertirDatos` del laboratorio, literal, sobre su delta de datos ({nuevos, cambios, borrados, …} frente a los ejemplos).
    Devuelve {"datos": delta} o {"choca": True}. Se verifica con `fixtures/lab/revertirDatos.json`."""
    antes, actual = antes or {}, actual or {}
    R = _tres_vias(_claves_delta(antes), _claves_delta(despues), _claves_delta(actual), igual=lambda x, y: _js(x) == _js(y))
    if R is None:
        return {"choca": True}
    # Se rearma el delta: los registros propios en el orden de `actual` y, al final, los que vuelven.
    nuevos: dict[str, list] = {}
    cambios: dict[str, dict] = {}
    borrados: dict[str, list] = {}
    for f in dict.fromkeys([*(actual.get("nuevos") or {}), *(antes.get("nuevos") or {})]):
        orden = dict.fromkeys(r["id"] for r in [*((actual.get("nuevos") or {}).get(f) or []), *((antes.get("nuevos") or {}).get(f) or [])])
        rs = [{"id": rid, "valores": {k[3]: v for k, v in R.items() if len(k) == 4 and k[0] == "n" and k[1] == f and k[2] == rid}}
              for rid in orden if ("n", f, rid) in R]
        if rs:
            nuevos[f] = rs
    for k, v in R.items():
        if k[0] == "c":
            cambios.setdefault(k[1], {}).setdefault(k[2], {})[k[3]] = v
        elif k[0] == "b":
            borrados.setdefault(k[1], []).append(k[2])
    return {"datos": {**actual, "nuevos": nuevos, "cambios": cambios, "borrados": borrados}}


def revertir_datos(antes: dict, despues: dict, actual: dict) -> dict:
    """La misma regla que `revertirDatos` del laboratorio, por secciones ({sec_id: [registros]}): solo las secciones de `antes`.
    Devuelve {"datos": {sec_id: registros}} o {"choca": True} si un pedido posterior tocó lo mismo."""
    salida = {}
    for sec, registros in antes.items():
        r = revertir_seccion(registros, despues.get(sec, []), actual.get(sec, []))
        if r is None:
            return {"choca": True}
        salida[sec] = r
    return {"datos": salida}


# ───────── Poner de vuelta ─────────

def _reconciliar(lista: dict, ahora: datetime) -> None:
    """Si vuelven registros de una importación que ya se había quitado, la importación vuelve a aparecer (con nombre genérico:
    el original no se guarda en la foto)."""
    hay = {i["id"] for i in lista.get("importaciones", [])}
    for r in lista["registros"]:
        if r.get("lote") and r["lote"] not in hay:
            lista.setdefault("importaciones", []).append({"id": r["lote"], "nombre": "Importación", "creado": ahora})
            hay.add(r["lote"])


def _poner_estructura(doc: dict, est: dict) -> None:
    actuales = {l["id"]: l for l in doc.get("listas") or []}
    listas = []
    for meta in est["listas_meta"]:
        previa = actuales.get(meta["id"], {})
        listas.append({**copy.deepcopy(meta), "registros": previa.get("registros", []),
                       **({"importaciones": previa["importaciones"]} if previa.get("importaciones") else {})})
    doc["listas"] = listas
    for k in ("etapas", "campos_contacto", "ocultas", "secciones"):
        doc[k] = copy.deepcopy(est[k])


def _poner_datos(doc: dict, sec: str, registros: list[dict], ahora: datetime) -> bool:
    """Pone los registros de una sección. False si la sección ya no existe."""
    registros = copy.deepcopy(registros)
    if sec == CONTACTOS:
        doc["total_contactos"] = max(0, int(doc.get("total_contactos") or 0) + len(registros) - len(doc.get("contactos") or []))
        doc["contactos"] = registros
        return True
    if sec == TAREAS:
        tareas = {col: [] for col in IDS_COLUMNA}
        for t in registros:
            col = t.pop("columna", "porHacer")
            tareas[col if col in tareas else "porHacer"].append(t)
        doc["tareas"] = tareas
        return True
    lista = next((l for l in doc.get("listas") or [] if l["id"] == sec), None)
    if lista is None:
        return False
    lista["registros"] = registros
    _reconciliar(lista, ahora)
    return True


def _secciones_existentes(doc: dict) -> set[str]:
    return {CONTACTOS, TAREAS, *(l["id"] for l in doc.get("listas") or [])}


# ───────── Deshacer ─────────

def _cosas(p: dict) -> set:
    """Lo que toca un punto: sus categorías y, en datos, cada sección (('datos', sec_id))."""
    cosas = {c for c in p.get("cambio") or [] if c != "datos"}
    if "datos" in (p.get("cambio") or []):
        cosas |= {("datos", s) for s in (p.get("foto") or {}).get("datos", {})}
    return cosas


def deshacer(doc: dict, puntos: list[dict], n: int | None = None, ahora: datetime | None = None) -> dict:
    """Deshace el punto `n` (o el último). Devuelve {doc, puntos, deshechos, texto}:
      - `doc`: el CRM con solo lo de ese punto de vuelta (y lo de los que cambiaban lo mismo, en cadena);
      - `puntos`: la lista que queda, sin los deshechos y con las fotos de los posteriores ajustadas (si después se deshace
        uno de ellos, no revive lo ya deshecho);
      - `deshechos`: los n que se deshicieron; `texto`: qué se hizo, para decírselo a la persona tal cual.
    Lanza ErrorCrm si no hay ese punto."""
    ahora = ahora or ahora_utc()
    lista = sorted(copy.deepcopy(puntos or []), key=lambda x: x["n"])
    if not lista:
        raise ErrorCrm(404, "No hay nada que deshacer.")
    p = lista[-1] if n is None else next((x for x in lista if x["n"] == n), None)
    if p is None:
        pedidos = ", ".join(f"{x['n']} «{x['antes_de']}»" for x in lista)
        raise ErrorCrm(404, f"No hay un pedido {n} para deshacer. Pedidos: {pedidos}.")
    posteriores = [x for x in lista if x["n"] > p["n"]]
    actual = datos_de(doc)
    existentes = _secciones_existentes(doc)

    # 1. Los datos de ESTE punto, a 3 vías por sección. `despues` = cómo quedó la sección justo después de este punto:
    #    la foto del siguiente punto que la tocó o, si ninguno, como está ahora.
    tres_vias: dict[str, list[dict]] = {}
    despues_de: dict[str, list[dict]] = {}
    for sec, antes_sec in ((p.get("foto") or {}).get("datos") or {}).items():
        despues_de[sec] = next((x["foto"]["datos"][sec] for x in posteriores if sec in (x["foto"].get("datos") or {})), actual.get(sec, []))
        if sec not in existentes:
            continue  # la sección ya no está: se vuelve por foto y en cadena con lo que la quitó
        r = revertir_seccion(antes_sec, despues_de[sec], actual.get(sec, []))
        if r is not None:
            tres_vias[sec] = r

    # 2. Lo que vuelve por foto (todo lo demás de este punto) y los posteriores que lo tocaron, en cadena hasta que no cambie.
    #    `desde[cosa]` = el punto más viejo del grupo que la toca: de su foto sale cómo vuelve.
    grupo, en_grupo = [p], {p["n"]}
    desde = {c: p for c in _cosas(p) if not (isinstance(c, tuple) and c[1] in tres_vias)}
    cambio = True
    while cambio:
        cambio = False
        listas_que_vuelven = None
        if "estructura" in desde:
            listas_que_vuelven = {m["id"] for m in desde["estructura"]["foto"]["estructura"]["listas_meta"]}
        for x in posteriores:
            if x["n"] in en_grupo:
                continue
            cosas = _cosas(x)
            toca = any(c in desde and x["n"] > desde[c]["n"] for c in cosas)
            # Si la estructura vuelve a un momento en que una sección no existía, lo que se le hizo a esa sección no puede quedar.
            toca = toca or (listas_que_vuelven is not None and any(isinstance(c, tuple) and c[1] not in (CONTACTOS, TAREAS)
                                                                    and c[1] not in listas_que_vuelven for c in cosas))
            if not toca:
                continue
            grupo.append(x)
            en_grupo.add(x["n"])
            cambio = True
            for c in cosas:
                if isinstance(c, tuple) and c[1] in tres_vias:  # esa sección ya no puede ir a 3 vías: vuelve por la foto de este punto
                    tres_vias.pop(c[1])
                    desde[c] = p
                desde.setdefault(c, x)

    # 3. Se arma el CRM: primero la estructura (las secciones tienen que existir), luego bloques y marca, luego los datos.
    out = copy.deepcopy(doc)
    if "estructura" in desde:
        _poner_estructura(out, desde["estructura"]["foto"]["estructura"])
    if "bloques" in desde:
        b = copy.deepcopy(desde["bloques"]["foto"]["bloques"])
        out["inicio"], out["paginas"] = b.get("inicio") or [], b.get("paginas") or {}
    if "marca" in desde:
        out["marca"] = copy.deepcopy(desde["marca"]["foto"]["marca"])
    for c, x in desde.items():
        if isinstance(c, tuple):
            _poner_datos(out, c[1], x["foto"]["datos"][c[1]], ahora)
    for sec, registros in tres_vias.items():
        _poner_datos(out, sec, registros, ahora)

    # 4. Las fotos de los que se quedan olvidan lo deshecho a 3 vías.
    fuera = {x["n"] for x in grupo}
    quedan = []
    for x in lista:
        if x["n"] in fuera:
            continue
        if x["n"] > p["n"]:
            for sec in tres_vias:
                if sec in (x["foto"].get("datos") or {}):
                    r = revertir_seccion(p["foto"]["datos"][sec], despues_de[sec], x["foto"]["datos"][sec])
                    if r is not None:
                        x["foto"]["datos"][sec] = r
        quedan.append(x)

    arrastrados = [x for x in grupo if x is not p]
    que = " y ".join(NOMBRE[c] for c in p.get("cambio") or [])
    tambien = ", ".join(f"«{x['antes_de']}»" for x in arrastrados)
    texto = (f"Deshecho el pedido {p['n']} «{p['antes_de']}» ({que} quedaron como antes)."
             + (f" También se deshizo {tambien} porque cambiaba lo mismo." if arrastrados else "")
             + " Lo demás quedó igual.")
    out.setdefault("eventos", [])
    _registrar(out, "↩️", f"Deshiciste «{p['antes_de']}»", ahora)
    return {"doc": out, "puntos": quedan, "deshechos": sorted(fuera), "texto": texto}
