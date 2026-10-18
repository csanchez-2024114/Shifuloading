"""Siembra un CRM de Carlos (esquema 2) a partir de una plantilla del laboratorio, con sus datos de ejemplo.

Es lo que hace el laboratorio al elegir una plantilla (`ExperienciaPage.jsx`: `asignar` → `plantillaPorId` → `datosEjemplo(p, 'muchos')`
→ `PlantillaCRM` con `acomodar(conTamano(inicio))`), pero escrito en el documento de Carlos. Lo decide el CÓDIGO, no la IA: la
plantilla, sus secciones, sus campos, sus registros de ejemplo y el inicio salen iguales para las mismas respuestas.

Reglas de traducción (plantilla → documento):
- Cada sección CON `campos` es una lista (`listas[i]`) con id `l_<id>` (contrato §1), sus campos con los ids de la plantilla (las
  piezas del inicio los nombran así), su vista, opciones, ícono, grupo, `origen` = id de la plantilla, y sus registros de ejemplo
  (`ejemplo: True`, ids estables `<id>-<i>`, los mismos de `ejemplos.datos_ejemplo`).
- Las secciones FIJAS no se duplican: `feed` (Historial) → `actividad`, `equipo` → `rrhh`, `interruptores` → `automatizaciones`,
  las de Carlos, con el título de la plantilla. El historial, el equipo y las automatizaciones de ejemplo del laboratorio NO se
  siembran (no se pueden marcar como ejemplo): el CRM sigue naciendo con «Tú» y con el único hecho real «Shifu creó tu CRM».
- Las secciones con `fuente` (una vista sobre los registros de otra, p. ej. «Vencimientos» de Membresías) no son pestaña: pasan a
  ser la página (`paginas[<dueña>]`) de la sección dueña, con dos piezas: la vista de la dueña y la de la sección con fuente. Si una
  pieza del inicio apunta a una sección con fuente, apunta a la dueña.
- Personas → contactos (`seccion_personas`): si la PRIMERA sección con campos es la lista de clientes o prospectos (id `clientes`,
  `prospectos` o `contactos`), empieza por `nombre` y tiene un campo estado (`etapa` o, si no, `estado`) con opciones que sirven de
  etapas (de 2 a 8, cortas), esa sección son los CONTACTOS de Carlos: las etapas = esas opciones, `nombre` → nombre, `telefono` →
  detalle, el estado → etapa y el resto de campos → `campos_contacto` con id `f_<id>`. Las piezas del inicio que la nombran pasan
  a `contactos` con los ids de campo traducidos. En cualquier otro caso (una agenda, unos pedidos, unos miembros…) es una lista.
- Las integradas de Carlos que la plantilla no usa se ocultan (cobros, desarrollo, importar y, si no son las personas, contactos):
  no se borran, aparecen cuando se necesitan, igual que en `diseno`.
- Topes de Carlos (`estructura`): hasta 12 listas, 15 campos por lista y 2000 registros por lista. Si una plantilla se pasa, se
  corta en el orden de la plantilla (lo primero se queda) y se deja en el log; las piezas que nombran algo cortado se quitan.
- `inicio` = las piezas de la plantilla con uid `b0`, `b1`… y el tamaño de `conTamano` + `acomodar` del laboratorio (lienzo.jsx y
  edicion.js, portados abajo; `acomodar` se verifica con `test/crm/fixtures/lab/acomodar.json`).
- `plantilla` = {id, origen: "asignar", porque}.

Funciones puras: reciben el documento base (el de `generador.generar`) y devuelven uno nuevo; no tocan la base de datos.
"""
from __future__ import annotations

import copy
import logging
from datetime import date, datetime
from typing import Any

from app.crm import ejemplos
from app.crm import estructura as est
from app.crm import operaciones as op
from app.crm import plantillas as catalogo
from app.crm.asignar import asignar

logger = logging.getLogger(__name__)

PREFIJO = "l_"
NIVEL = "muchos"  # el mismo nivel de ejemplos con que el laboratorio muestra la plantilla elegida
# Secciones fijas de la plantilla (por su vista) → la integrada de Carlos que ya hace eso.
FIJAS = {"feed": "actividad", "equipo": "rrhh", "interruptores": "automatizaciones"}
OCULTAS_SEMBRADO = ("cobros", "desarrollo", "importar")  # integradas de Carlos que ninguna plantilla usa
PERSONAS = ("clientes", "prospectos", "contactos")
_NO_SON_CAMPO = ("tipo", "funcion")  # opciones de una pieza cuyo valor no es un id de campo (el tipo de gráfico, suma/promedio)


# ───────── Tamaños del lienzo (port de lienzo.jsx → conTamano y edicion.js → colocar/acomodar) ─────────

ANCHO_COMPLETO = ("kpis", "tablero", "agenda")
ALTO_MAX = 4


def con_tamano(bloques: list[dict]) -> list[dict]:
    """Tamaño inicial: resumen, tablero y agenda a lo ancho; lo demás a media columna; si queda uno solo en su fila, a lo ancho.
    Lo que ya trae ancho o alto se respeta (como `b.ancho || …` del laboratorio)."""
    medios = [b for b in bloques if b.get("vista") not in ANCHO_COMPLETO]
    solo = medios[-1].get("uid") if len(medios) % 2 == 1 else None
    return [{**b, "ancho": b.get("ancho") or (12 if b.get("vista") in ANCHO_COMPLETO or b.get("uid") == solo else 6),
             "alto": b.get("alto") or (1 if b.get("vista") == "kpis" else 2)} for b in bloques]


def _colocar(bloques: list[dict]) -> tuple[dict, dict]:
    """El acomodo «dense» del CSS: ({uid: {f, c, w, h}}, celdas[fila][col] = uid)."""
    celdas: dict[int, dict[int, str]] = {}

    def libre(f: int, c: int, w: int, h: int) -> bool:
        for y in range(f, f + h):
            for x in range(c, c + w):
                if celdas.get(y, {}).get(x):
                    return False
        return c + w <= 12

    pos: dict[str, dict] = {}
    for b in bloques:
        w = max(1, min(12, b.get("ancho") or 6))
        h = 1 if b.get("vista") == "kpis" else (b.get("alto") or 1)
        f = 0
        while True:
            c = next((x for x in range(13 - w) if libre(f, x, w, h)), None)
            if c is not None:
                break
            f += 1
        for y in range(f, f + h):
            fila = celdas.setdefault(y, {})
            for x in range(c, c + w):
                fila[x] = b.get("uid")
        pos[b.get("uid")] = {"f": f, "c": c, "w": w, "h": h}
    return pos, celdas


def acomodar(bloques: list[dict], fijos0: Any = ()) -> list[dict]:
    """Acomodo automático (D38): tapa los huecos. El vecino de la IZQUIERDA se ensancha o, si no, el de ARRIBA crece una fila; si
    nadie puede, el primer bloque que viene después y no cabe se angosta al ancho del hueco (mínimo 3). Los `fijos` no se tocan.
    Port literal de `acomodar` de edicion.js (cuando exista `edicion.acomodar` en Python, esta debe ser la misma)."""
    fijos = set(fijos0) | {b.get("uid") for b in bloques if b.get("fijo")}
    bs = [dict(b) for b in bloques]
    imposibles: set[tuple[int, int]] = set()
    for _vuelta in range(40):
        pos, celdas = _colocar(bs)
        filas = (max(celdas) + 1) if celdas else 0
        hueco = next(((f, c) for f in range(filas) for c in range(12) if not celdas.get(f, {}).get(c) and (f, c) not in imposibles), None)
        if hueco is None:
            break
        f, c = hueco
        largo = 0
        while c + largo < 12 and not celdas.get(f, {}).get(c + largo):
            largo += 1
        izq = celdas.get(f, {}).get(c - 1) if c > 0 else None
        arriba = celdas.get(f - 1, {}).get(c) if f > 0 else None

        def libre_en(y: int, x0: int, n: int) -> bool:
            return all(not celdas.get(y, {}).get(x) for x in range(x0, x0 + n))

        hecho = False
        if izq and izq not in fijos:
            p = pos[izq]
            if all(libre_en(p["f"] + dy, c, largo) for dy in range(p["h"])):
                bs = [{**b, "ancho": p["w"] + largo} if b.get("uid") == izq else b for b in bs]
                hecho = True
        if not hecho and arriba and arriba not in fijos:
            p = pos[arriba]
            b = next(x for x in bs if x.get("uid") == arriba)
            if b.get("vista") != "kpis" and p["h"] < ALTO_MAX and p["f"] + p["h"] == f and libre_en(f, p["c"], p["w"]):
                bs = [{**x, "alto": p["h"] + 1} if x.get("uid") == arriba else x for x in bs]
                hecho = True
        if not hecho and largo >= 3:
            despues = next((b for b in bs if b.get("uid") not in fijos and b.get("vista") != "kpis"
                            and (pos[b.get("uid")]["f"] > f or (pos[b.get("uid")]["f"] == f and pos[b.get("uid")]["c"] > c))
                            and pos[b.get("uid")]["w"] > largo), None)
            if despues is not None:
                bs = [{**b, "ancho": largo} if b is despues else b for b in bs]
                hecho = True
        if not hecho:
            imposibles.add((f, c))
    return bs


# ───────── Personas → contactos ─────────

def seccion_personas(plantilla: dict) -> tuple[dict, dict] | None:
    """(sección, campo de etapa) si la primera sección con campos de la plantilla son sus clientes o prospectos con un estado que
    sirve de etapas (regla en el docstring del módulo); si no, None (todas sus secciones son listas)."""
    sec = next((s for s in plantilla.get("secciones") or [] if s.get("campos") and not s.get("fuente")), None)
    if sec is None or sec["id"] not in PERSONAS:
        return None
    campos = sec["campos"]
    if campos[0].get("id") != "nombre" or campos[0].get("tipo") != "texto":
        return None
    estados = {c["id"]: c for c in campos if c.get("tipo") == "estado"}
    campo = estados.get("etapa") or estados.get("estado")
    opciones = (campo or {}).get("opciones") or []
    if not campo or not est.MIN_ETAPAS <= len(opciones) <= est.MAX_ETAPAS or any(len(o) > est.LARGO_ETAPA for o in opciones):
        return None
    return sec, campo


def _mapa_contactos(sec: dict, campo_etapa: dict) -> dict[str, str]:
    """id de campo de la plantilla → id de campo de la sección virtual `contactos` (contrato §2)."""
    mapa = {}
    for c in sec["campos"]:
        if c["id"] == "nombre":
            mapa[c["id"]] = "nombre"
        elif c["id"] == "telefono" and c.get("tipo") == "texto":
            mapa[c["id"]] = "detalle"
        elif c["id"] == campo_etapa["id"]:
            mapa[c["id"]] = "etapa"
        else:
            mapa[c["id"]] = "f_" + c["id"]
    return mapa


def _sembrar_contactos(doc: dict, sec: dict, campo_etapa: dict, registros: list[dict], ahora: datetime) -> dict[str, str]:
    """Pone la sección de personas en los contactos de Carlos (modifica `doc`, que ya es copia). Devuelve el mapa de campos."""
    mapa = _mapa_contactos(sec, campo_etapa)
    doc["etapas"] = list(campo_etapa["opciones"])
    extras = [c for c in sec["campos"] if mapa[c["id"]].startswith("f_")]
    if len(extras) > est.MAX_CAMPOS:
        logger.info("Plantilla con %d campos extra de contactos: se dejan %d", len(extras), est.MAX_CAMPOS)
        extras = extras[:est.MAX_CAMPOS]
    doc["campos_contacto"] = [{"id": mapa[c["id"]], "nombre": c["nombre"], "tipo": c["tipo"], **({"opciones": list(c["opciones"])} if c.get("opciones") else {})}
                              for c in extras]
    con_extra = {c["id"] for c in extras}
    if len(registros) > op.MAX_CONTACTOS:
        logger.info("Plantilla con %d contactos de ejemplo: se dejan %d", len(registros), op.MAX_CONTACTOS)
        registros = registros[:op.MAX_CONTACTOS]
    dueno = (doc.get("vendedores") or ["Tú"])[0]
    doc["contactos"] = [{
        "id": r["id"], "n": str(r["valores"].get("nombre") or "")[:40], "det": r["valores"].get("telefono") if mapa.get("telefono") == "detalle" else None,
        "canal": None, "etapa": r["valores"].get(campo_etapa["id"]) or doc["etapas"][0], "dueno": dueno, "ultimo_contacto": ahora,
        "extra": {mapa[k]: v for k, v in r["valores"].items() if k in con_extra and v is not None}, "ejemplo": True,
    } for r in registros]
    doc["total_contactos"] = len(doc["contactos"])
    doc["secciones"]["contactos"] = sec["titulo"]
    return mapa


# ───────── Siembra ─────────

def _traducir_opciones(opciones: dict, mapa: dict[str, str]) -> dict:
    return {k: (mapa.get(v, v) if isinstance(v, str) and k not in _NO_SON_CAMPO else copy.deepcopy(v)) for k, v in (opciones or {}).items()}


def _nombra_cortado(opciones: dict, cortados: set[str]) -> bool:
    return any(isinstance(v, str) and k not in _NO_SON_CAMPO and v in cortados for k, v in (opciones or {}).items())


def _hoy(ahora: datetime) -> date:
    return op.hora_local(ahora).date()


def sembrar(doc_base: dict, plantilla: dict | str, *, nivel: str = NIVEL, hoy: date | None = None, pais: str | None = None,
            porque: list[str] | None = None, origen: str = "asignar", ahora: datetime | None = None) -> dict:
    """Documento de esquema 2 con la plantilla y sus ejemplos sobre `doc_base` (el de `generador.generar`). No cambia `doc_base`.
    `plantilla`: id del catálogo (semilla, biblioteca o `pestana-<id>`) o el dict. Lanza KeyError si el id no existe."""
    if isinstance(plantilla, str):
        p = catalogo.plantilla_por_id(plantilla)
        if p is None:
            raise KeyError(f"no existe la plantilla «{plantilla}»")
        plantilla = p
    ahora = ahora or op.ahora_utc()
    hoy = hoy or _hoy(ahora)
    doc = est.normalizar(copy.deepcopy(doc_base))
    datos = ejemplos.registros_ejemplo(plantilla, nivel, hoy, pais)
    secciones = plantilla.get("secciones") or []
    por_id = {s["id"]: s for s in secciones}

    personas = seccion_personas(plantilla)
    destino: dict[str, str] = {}   # id de sección de la plantilla → id en el documento
    mapas: dict[str, dict] = {}    # id en el documento → traducción de ids de campo (solo contactos)
    cortados: set[str] = set()     # ids de campo cortados por el tope (las piezas que los nombran se quitan)
    if personas:
        sec, campo_etapa = personas
        mapas["contactos"] = _sembrar_contactos(doc, sec, campo_etapa, datos.get(sec["id"]) or [], ahora)
        destino[sec["id"]] = "contactos"

    listas: list[dict] = []
    libres = est.MAX_LISTAS - len(doc["listas"])
    for s in secciones:
        if s["id"] in destino:
            continue
        if s.get("vista") in FIJAS and not s.get("campos"):
            sid = FIJAS[s["vista"]]
            destino[s["id"]] = sid
            if s.get("titulo") and s["titulo"] != catalogo_titulo(doc, sid):
                doc["secciones"][sid] = s["titulo"]
            continue
        if not s.get("campos") or s.get("fuente"):
            continue  # las de fuente se resuelven abajo, cuando ya se sabe dónde quedó su dueña
        if len(listas) >= libres:
            logger.info("Plantilla %s: la sección %s no cabe (tope de %d listas)", plantilla.get("id"), s["id"], est.MAX_LISTAS)
            continue
        campos = s["campos"]
        if len(campos) > est.MAX_CAMPOS:
            logger.info("Plantilla %s: la sección %s tiene %d campos; se dejan %d", plantilla.get("id"), s["id"], len(campos), est.MAX_CAMPOS)
            cortados |= {c["id"] for c in campos[est.MAX_CAMPOS:]}
            campos = campos[:est.MAX_CAMPOS]
        ids = {c["id"] for c in campos}
        registros = datos.get(s["id"]) or []
        if len(registros) > est.MAX_REGISTROS:
            logger.info("Plantilla %s: la sección %s trae %d ejemplos; se dejan %d", plantilla.get("id"), s["id"], len(registros), est.MAX_REGISTROS)
            registros = registros[:est.MAX_REGISTROS]
        lid = PREFIJO + s["id"]
        lista = {
            "id": lid, "nombre": s["titulo"],
            "campos": [{k: copy.deepcopy(c[k]) for k in ("id", "nombre", "tipo", "opciones") if k in c} for c in campos],
            "registros": [{"id": r["id"], "ejemplo": True, "valores": {k: v for k, v in r["valores"].items() if k in ids}, "creado": ahora} for r in registros],
            "vista": s.get("vista") or "tabla", "opciones": copy.deepcopy(s.get("opciones") or {}), "icono": s.get("icono"),
            "grupo": s.get("grupo", 0), "origen": plantilla.get("id"),
        }
        for k in ("ficha", "tarjeta"):
            if s.get(k) is not None:
                lista[k] = copy.deepcopy(s[k])
        listas.append(lista)
        destino[s["id"]] = lid
    doc["listas"] = [*doc["listas"], *listas]

    # Secciones con fuente: la página de su dueña (la vista de la dueña y luego la suya).
    paginas: dict[str, list[dict]] = {}
    for s in secciones:
        if not s.get("fuente"):
            continue
        dueno = por_id.get(s["fuente"])
        did = destino.get(s["fuente"])
        if dueno is None or did is None:
            logger.info("Plantilla %s: la sección %s muestra %s, que no quedó; se omite", plantilla.get("id"), s["id"], s["fuente"])
            continue
        destino[s["id"]] = did
        mapa = mapas.get(did, {})
        if did not in paginas:
            paginas[did] = [{"vista": dueno.get("vista") or "tabla", "seccion": did, "opciones": _traducir_opciones(dueno.get("opciones"), mapa)}]
        paginas[did].append({"vista": s.get("vista") or "tabla", "seccion": did, "opciones": _traducir_opciones(s.get("opciones"), mapa)})
    doc["paginas"] = {sid: acomodar(con_tamano([{**b, "uid": f"b{i}"} for i, b in enumerate(bs)])) for sid, bs in paginas.items()}

    # Inicio: las piezas de la plantilla que apuntan a algo que quedó, con uid b0, b1… y el tamaño del laboratorio.
    inicio: list[dict] = []
    for b in plantilla.get("inicio") or []:
        sid = destino.get(b.get("seccion"))
        if sid is None or sid in FIJAS.values() or _nombra_cortado(b.get("opciones"), cortados):
            logger.info("Plantilla %s: la pieza %s de %s no tiene sección; se omite", plantilla.get("id"), b.get("vista"), b.get("seccion"))
            continue
        pieza = {**copy.deepcopy(b), "seccion": sid, "opciones": _traducir_opciones(b.get("opciones"), mapas.get(sid, {}))}
        inicio.append(pieza)
    doc["inicio"] = acomodar(con_tamano([{**b, "uid": f"b{i}"} for i, b in enumerate(inicio)]))

    usadas = set(destino.values())
    doc["ocultas"] = [i for i in doc["ocultas"] if i in OCULTAS_SEMBRADO or i not in usadas]
    for sid in (*OCULTAS_SEMBRADO, *(() if "contactos" in usadas else ("contactos",))):
        if sid not in doc["ocultas"]:
            doc["ocultas"].append(sid)
    doc["esquema"] = est.ESQUEMA
    doc["plantilla"] = {"id": plantilla.get("id"), "origen": origen, "porque": list(porque or [])}
    return doc


def catalogo_titulo(doc: dict, seccion_id: str) -> str:
    """El nombre que la integrada ya tiene en este CRM (por rubro o el que se le puso)."""
    from app.crm.secciones import titulo_seccion

    return titulo_seccion((doc.get("brief") or {}).get("rubro"), seccion_id, doc.get("secciones"))


# ───────── Elegir la plantilla con el cuestionario ─────────

def respuestas_de(brief: dict) -> dict:
    """Las respuestas del cuestionario de Carlos con la forma que pide `asignar`."""
    return {"rubro": brief.get("rubro"), "ciclo": brief.get("ciclo"), "objetivos": list(brief.get("objetivos") or []),
            "que_vendes": brief.get("que_vendes") or ""}


def elegir(brief: dict) -> dict:
    """`asignar` con el cuestionario: {recomendada, opciones, ambiguo}."""
    return asignar(respuestas_de(brief))


# ───────── Ejemplos para lo que se agregue después de sembrar ─────────

def ejemplos_para_campos(doc: dict, sec_id: str, campos: list[dict], nivel: str = NIVEL, hoy: date | None = None) -> dict:
    """Llena con valores de ejemplo los campos NUEVOS de una lista sembrada, solo en sus registros de ejemplo (los reales no se
    tocan). Cada campo nuevo tiene su propia semilla (como `extenderDatos`), así lo que ya estaba no cambia. Devuelve un doc nuevo."""
    out = copy.deepcopy(doc)
    lista = next((l for l in out["listas"] if l["id"] == sec_id), None)
    if lista is None or not campos:
        return out
    base = (out.get("plantilla") or {}).get("id") or "crm"
    propios = [{**c, "tipo": "estado" if c.get("tipo") == "lista" else c.get("tipo")} for c in campos]
    sid = sec_id[len(PREFIJO):] if sec_id.startswith(PREFIJO) else sec_id
    extra = ejemplos.registros_ejemplo({"id": f"{base}:{sid}:campos", "secciones": [{"id": sid, "campos": propios}]}, nivel, hoy).get(sid) or []
    i = 0
    for r in lista["registros"]:
        if not r.get("ejemplo"):
            continue
        if i < len(extra):
            r["valores"].update({k: v for k, v in extra[i]["valores"].items() if v is not None})
        i += 1
    return out
