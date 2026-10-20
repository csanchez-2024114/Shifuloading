"""Adaptador entre el estado del laboratorio (bancos de prueba) y el documento CRM de Carlos (esquema 2).

Funciones puras, sin I/O. Los bancos (`laboratorio/pruebas/*.py`) envían `{plantilla, estado, texto, …}` y esperan la misma
forma de respuesta que `/api/lab/chat`; este módulo traduce estado ↔ documento para medir el motor Python sin cambiar los bancos.

Puntos de deshacer: en el laboratorio viven en `estado.puntos` (con `foto` en forma lab). En Carlos van en `crm_puntos` con
`foto` en forma documento (contrato §3). El adaptador traduce las fotos en ambos sentidos; el contador `puntos_n` queda en el doc.
"""
from __future__ import annotations

import copy
import inspect
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

from assistant.packs.crm import ejemplos
from assistant.packs.crm import estructura as est
from assistant.packs.crm import plantillas as catalogo
from assistant.packs.crm import puntos as pt
from assistant.packs.crm import sembrar
from assistant.packs.crm.generador import generar
from assistant.packs.crm import chat as chat_reglas
from assistant.packs.crm.secciones import IDS_SECCION
from assistant.packs.crm.secciones_v import registros_de as regs_de

PREFIJO = sembrar.PREFIJO
_FIJAS_LAB = sembrar.FIJAS  # feed → actividad, etc.


def _hoy_default(hoy: date | None) -> date:
    return hoy or date.today()


def _muestra_norm(muestra: dict | None) -> dict:
    m = muestra or {}
    nivel = m.get("nivel") or "pocos"
    if nivel not in ("vacio", "pocos", "muchos"):
        nivel = "pocos"
    return {"nivel": nivel, "ejemplos": m.get("ejemplos") is not False, "pais": (m.get("pais") or "gt")[:5]}


def mapa_secciones(plantilla: dict, doc: dict) -> dict[str, str]:
    """Id de sección del laboratorio → id en el documento (p. ej. `miembros` → `l_miembros`)."""
    out: dict[str, str] = {}
    personas = sembrar.seccion_personas(plantilla)
    if personas:
        out[personas[0]["id"]] = "contactos"
    for s in plantilla.get("secciones") or []:
        sid = s["id"]
        if sid in out:
            continue
        if s.get("vista") in _FIJAS_LAB and not s.get("campos"):
            out[sid] = _FIJAS_LAB[s["vista"]]
        elif s.get("campos") and not s.get("fuente"):
            out[sid] = PREFIJO + sid
        elif s.get("fuente"):
            out[sid] = out.get(s["fuente"], PREFIJO + s["fuente"])
    # Lo que realmente quedó sembrado (por si una sección no cupo).
    for l in doc.get("listas") or []:
        if l["id"].startswith(PREFIJO):
            out.setdefault(l["id"][len(PREFIJO):], l["id"])
    return out


def _inv_mapa(mapa: dict[str, str], plantilla: dict | None = None) -> dict[str, str]:
    """Documento → id de sección del laboratorio. Si varias secciones de plantilla comparten lista (`fuente`), gana la dueña."""
    if not plantilla:
        return {v: k for k, v in mapa.items()}
    por = {s["id"]: s for s in plantilla.get("secciones") or []}
    inv: dict[str, str] = {}
    for lab_id, doc_sec in mapa.items():
        s = por.get(lab_id, {})
        if s.get("campos") and not s.get("fuente"):
            inv[doc_sec] = lab_id
    for lab_id, doc_sec in mapa.items():
        inv.setdefault(doc_sec, lab_id)
    return inv


def _fuente_lab(plantilla: dict, lab_sec: str) -> str:
    por = {s["id"]: s for s in plantilla.get("secciones") or []}
    s = por.get(lab_sec)
    if not s:
        return lab_sec
    return s.get("fuente") or s["id"]


def _bloque_a_doc(b: dict, mapa: dict[str, str]) -> dict:
    sec = b.get("seccion")
    doc_sec = mapa.get(sec, sec)
    vista = "grafico" if b.get("vista") == "grafica" else b.get("vista")
    return {**copy.deepcopy(b), "seccion": doc_sec, "vista": vista}


def _bloque_a_lab(b: dict, inv: dict[str, str]) -> dict:
    sec = b.get("seccion")
    lab_sec = inv.get(sec, sec[len(PREFIJO):] if isinstance(sec, str) and sec.startswith(PREFIJO) else sec)
    # El laboratorio acepta `grafica` (vieja) y `grafico`; no forzamos una u otra al volver.
    return {**copy.deepcopy(b), "seccion": lab_sec}


def _aplicar_datos_lab(registros: dict[str, list[dict]], delta: dict | None, mapeo_estado: dict | None) -> dict[str, list[dict]]:
    """Port de `aplicarDatos` (datosEjemplo.js): delta sobre registros por sección dueña."""
    if not delta or not any(delta.get(k) for k in ("nuevos", "cambios", "borrados")):
        return registros
    out = {k: [copy.deepcopy(r) for r in v] for k, v in registros.items()}
    fuentes = set((delta.get("nuevos") or {}).keys()) | set((delta.get("cambios") or {}).keys()) | set((delta.get("borrados") or {}).keys())
    for f in fuentes:
        fuera = set(delta.get("borrados", {}).get(f) or [])
        cambios = delta.get("cambios", {}).get(f) or {}
        out[f] = [*(out.get(f) or []), *[copy.deepcopy(r) for r in (delta.get("nuevos", {}).get(f) or [])]]
        out[f] = [r for r in out[f] if r["id"] not in fuera]
        out[f] = [{**r, "valores": {**r["valores"], **cambios[r["id"]]}} if r["id"] in cambios else r for r in out[f]]
        if mapeo_estado and mapeo_estado.get(f):
            out[f] = ejemplos._mapear_estados(out[f], mapeo_estado[f])
    return out


def _registros_semilla_lab(plantilla: dict, muestra: dict, estructura: dict | None, hoy: date) -> dict[str, list[dict]]:
    m = _muestra_norm(muestra)
    base = ejemplos.datos_ejemplo(plantilla, m["nivel"], hoy, m["pais"])
    if not m["ejemplos"]:
        base = ejemplos.sin_ejemplos(base) or base
    ext = ejemplos.extender_datos(base, plantilla, estructura or {}, m["nivel"], hoy) or base
    return ext["registros"]


def _delta_datos_lab(actuales: dict[str, list[dict]], semilla: dict[str, list[dict]], plantilla: dict) -> dict | None:
    """Registros actuales → delta {nuevos, cambios, borrados, n} frente a la semilla (ids de ejemplo)."""
    nuevos: dict[str, list] = {}
    cambios: dict[str, dict] = {}
    borrados: dict[str, list] = {}
    n = 0
    for s in plantilla.get("secciones") or []:
        if not s.get("campos"):
            continue
        f = _fuente_lab(plantilla, s["id"])
        base_ids = {r["id"] for r in semilla.get(f, [])}
        por_id = {r["id"]: r for r in actuales.get(f, [])}
        for rid in base_ids:
            if rid not in por_id:
                borrados.setdefault(f, []).append(rid)
        for rid, r in por_id.items():
            if rid in base_ids:
                base_r = next(x for x in semilla[f] if x["id"] == rid)
                diff = {k: v for k, v in r["valores"].items() if base_r["valores"].get(k) != v}
                if diff:
                    cambios.setdefault(f, {})[rid] = diff
            else:
                nuevos.setdefault(f, []).append({"id": rid, "valores": dict(r["valores"])})
                n = max(n, 1)
    if not nuevos and not cambios and not borrados:
        return None
    out: dict[str, Any] = {}
    if nuevos:
        out["nuevos"] = nuevos
    if cambios:
        out["cambios"] = cambios
    if borrados:
        out["borrados"] = borrados
    if n or nuevos:
        out["n"] = max(n, len([r for rs in nuevos.values() for r in rs]))
    return out


def _poner_registros_lab(doc: dict, plantilla: dict, mapa: dict[str, str], registros: dict[str, list[dict]]) -> dict:
    """Escribe registros (claves lab / fuente) en el documento."""
    out = copy.deepcopy(doc)
    inv = _inv_mapa(mapa)
    for lab_f, rs in registros.items():
        doc_sec = mapa.get(lab_f, PREFIJO + lab_f)
        if doc_sec == "contactos":
            continue  # los bancos de membresías no usan contactos
        lista = next((l for l in out["listas"] if l["id"] == doc_sec), None)
        if lista is None:
            continue
        creado = lista["registros"][0]["creado"] if lista["registros"] else datetime.now(timezone.utc)
        lista["registros"] = [
            {"id": r["id"], "valores": copy.deepcopy(r["valores"]), "ejemplo": bool(r.get("ejemplo")), "creado": creado}
            for r in rs
        ]
    return out


def _registros_actuales_lab(doc: dict, plantilla: dict, mapa: dict[str, str]) -> dict[str, list[dict]]:
    inv = _inv_mapa(mapa)
    out: dict[str, list] = {}
    for lab_id, doc_sec in mapa.items():
        if doc_sec in ("actividad", "rrhh", "automatizaciones", "cobros", "desarrollo", "importar"):
            continue
        f = _fuente_lab(plantilla, lab_id)
        if f in out:
            continue
        try:
            out[f] = regs_de(doc, doc_sec)
        except Exception:
            out[f] = []
    return out


def _aplicar_estructura_lab(doc: dict, plantilla: dict, est_lab: dict | None, mapa: dict[str, str], hoy: date) -> dict:
    if not est_lab:
        return doc
    out = copy.deepcopy(doc)
    m = _muestra_norm({})
    # Páginas propias de pestañas
    if est_lab.get("paginas"):
        paginas = {}
        for lab_pid, bloques in est_lab["paginas"].items():
            doc_pid = mapa.get(lab_pid, PREFIJO + lab_pid)
            paginas[doc_pid] = [_bloque_a_doc(b, mapa) for b in bloques]
        out["paginas"] = paginas
    # Títulos
    for lab_id, titulo in (est_lab.get("titulos") or {}).items():
        doc_sec = mapa.get(lab_id)
        if not doc_sec:
            continue
        if doc_sec.startswith(PREFIJO):
            lista = next((l for l in out["listas"] if l["id"] == doc_sec), None)
            if lista:
                lista["nombre"] = titulo
        else:
            out.setdefault("secciones", {})[doc_sec] = titulo
    # Campos nuevos por sección
    for lab_id, campos in (est_lab.get("campos") or {}).items():
        doc_sec = mapa.get(lab_id, PREFIJO + lab_id)
        for c in campos:
            try:
                out = est.campo_agregar(out, doc_sec, c.get("nombre", "Campo"), c.get("tipo", "texto"), opciones=c.get("opciones"))
            except Exception:
                pass
    # Secciones nuevas
    for sec in est_lab.get("secciones") or []:
        if sec["id"] in mapa:
            continue
        try:
            defs = sec.get("campos") or []
            campos = [{"nombre": c["nombre"], "tipo": c.get("tipo", "texto")} for c in defs]
            out = est.lista_crear(out, sec.get("titulo") or sec["id"], campos or None)
            lista = out["listas"][-1]
            deseado = PREFIJO + sec["id"]
            if not any(l["id"] == deseado for l in out["listas"] if l is not lista):
                lista["id"] = deseado
            for i, c_def in enumerate(defs):
                if i < len(lista["campos"]) and c_def.get("id"):
                    lista["campos"][i]["id"] = c_def["id"]
            mapa[sec["id"]] = lista["id"]
        except Exception:
            pass
    # Meta en listas existentes
    for lab_id, doc_sec in list(mapa.items()):
        if not doc_sec.startswith(PREFIJO):
            continue
        lista = next((l for l in out["listas"] if l["id"] == doc_sec), None)
        if not lista:
            continue
        base = next((s for s in plantilla.get("secciones") or [] if s["id"] == lab_id), None)
        cq = (est_lab.get("camposQuitados") or {}).get(lab_id) or []
        if cq and base:
            for cid in cq:
                try:
                    out = est.campo_eliminar(out, doc_sec, cid)
                except Exception:
                    pass
        nc = (est_lab.get("nombresCampo") or {}).get(lab_id) or {}
        for cid, nombre in nc.items():
            try:
                out = est.campo_renombrar(out, doc_sec, cid, nombre)
            except Exception:
                pass
        oe = (est_lab.get("opcionesEstado") or {}).get(lab_id) or {}
        for cid, opts in oe.items():
            lista = next(l for l in out["listas"] if l["id"] == doc_sec)
            lista["opciones_estado"] = {**(lista.get("opciones_estado") or {}), cid: list(opts)}
            campo = next((c for c in lista["campos"] if c["id"] == cid), None)
            if campo and campo.get("tipo") in est.CON_OPCIONES:
                campo["opciones"] = list(opts)
        me = (est_lab.get("mapeoEstado") or {}).get(lab_id) or {}
        if me:
            lista = next(l for l in out["listas"] if l["id"] == doc_sec)
            lista["mapeo_estado"] = {**(lista.get("mapeo_estado") or {}), **me}
        if (est_lab.get("ficha") or {}).get(lab_id):
            lista = next(l for l in out["listas"] if l["id"] == doc_sec)
            lista["ficha"] = copy.deepcopy(est_lab["ficha"][lab_id])
        if (est_lab.get("tarjeta") or {}).get(lab_id):
            lista = next(l for l in out["listas"] if l["id"] == doc_sec)
            lista["tarjeta"] = copy.deepcopy(est_lab["tarjeta"][lab_id])
    # Ocultas (ids del laboratorio)
    ocultas_passthrough: list[str] = []
    for lab_id in est_lab.get("ocultas") or []:
        doc_sec = mapa.get(lab_id)
        if doc_sec and doc_sec in IDS_SECCION:
            try:
                out = est.seccion_ocultar(out, doc_sec)
            except Exception:
                ocultas_passthrough.append(lab_id)
        else:
            # En el laboratorio ocultar una lista propia no borra `l_*`; solo vive en estado.estructura.ocultas.
            ocultas_passthrough.append(lab_id)
    if ocultas_passthrough:
        out["_adaptador_lab"] = {**(out.get("_adaptador_lab") or {}), "ocultas": ocultas_passthrough}
    return out


def _paginas_en_lab(paginas: dict | None, inv: dict[str, str]) -> dict[str, list]:
    out: dict[str, list] = {}
    for doc_pid, bloques in (paginas or {}).items():
        lab_pid = inv.get(doc_pid, doc_pid[len(PREFIJO):] if doc_pid.startswith(PREFIJO) else doc_pid)
        out[lab_pid] = [_bloque_a_lab(b, inv) for b in bloques]
    return out


def _estructura_lab(doc: dict, doc_sembrado: dict, plantilla: dict, mapa: dict[str, str]) -> dict | None:
    est_out: dict[str, Any] = {}
    inv = _inv_mapa(mapa, plantilla)
    por_plantilla = {s["id"]: s for s in plantilla.get("secciones") or []}
    paginas_lab = _paginas_en_lab(doc.get("paginas"), inv)
    paginas_sem = _paginas_en_lab(doc_sembrado.get("paginas"), inv)
    if paginas_lab != paginas_sem:
        est_out["paginas"] = paginas_lab
    doc_secs_vistas: set[str] = set()
    for lab_id, doc_sec in mapa.items():
        if not doc_sec.startswith(PREFIJO):
            continue
        if doc_sec in doc_secs_vistas:
            continue
        if por_plantilla.get(lab_id, {}).get("fuente"):
            continue
        doc_secs_vistas.add(doc_sec)
        lista = next((l for l in doc["listas"] if l["id"] == doc_sec), None)
        lista0 = next((l for l in doc_sembrado["listas"] if l["id"] == doc_sec), None)
        base = por_plantilla.get(lab_id)
        if not lista or not base:
            continue
        if lista["nombre"] != base.get("titulo"):
            est_out.setdefault("titulos", {})[lab_id] = lista["nombre"]
        ids_base = {c["id"] for c in base.get("campos") or []}
        ids_now = {c["id"] for c in lista["campos"]}
        quitados = [c for c in ids_base if c not in ids_now]
        if quitados:
            est_out.setdefault("camposQuitados", {})[lab_id] = quitados
        agregados = [c for c in lista["campos"] if c["id"] not in ids_base]
        if agregados:
            est_out.setdefault("campos", {})[lab_id] = [{k: c[k] for k in ("id", "nombre", "tipo", "opciones") if k in c} for c in agregados]
        nombres = {}
        por_base = {c["id"]: c for c in base.get("campos") or []}
        for c in lista["campos"]:
            if c["id"] in por_base and c.get("nombre") != por_base[c["id"]].get("nombre"):
                nombres[c["id"]] = c["nombre"]
        if nombres:
            est_out.setdefault("nombresCampo", {})[lab_id] = nombres
        for c in lista["campos"]:
            if c.get("tipo") not in est.CON_OPCIONES:
                continue
            opts_b = (por_base.get(c["id"]) or {}).get("opciones")
            opts_n = c.get("opciones")
            if opts_b and opts_n and list(opts_b) != list(opts_n):
                est_out.setdefault("opcionesEstado", {})[lab_id] = {**(est_out.get("opcionesEstado", {}).get(lab_id) or {}), c["id"]: list(opts_n)}
        me = lista.get("mapeo_estado") or {}
        me0 = (lista0 or {}).get("mapeo_estado") or {}
        if me and me != me0:
            est_out.setdefault("mapeoEstado", {})[lab_id] = copy.deepcopy(me)
        if lista.get("ficha") and lista.get("ficha") != base.get("ficha"):
            est_out.setdefault("ficha", {})[lab_id] = copy.deepcopy(lista["ficha"])
        if lista.get("tarjeta") and lista.get("tarjeta") != base.get("tarjeta"):
            est_out.setdefault("tarjeta", {})[lab_id] = copy.deepcopy(lista["tarjeta"])
    # Secciones integradas renombradas (doc.secciones) y ocultas (doc.ocultas vs siembra).
    inv_doc = {v: k for k, v in mapa.items()}
    secciones_doc = doc.get("secciones") or {}
    secciones_sem = doc_sembrado.get("secciones") or {}
    for doc_sec, titulo in secciones_doc.items():
        if titulo != secciones_sem.get(doc_sec):
            lab_id = inv_doc.get(doc_sec, doc_sec)
            if lab_id in por_plantilla:
                est_out.setdefault("titulos", {})[lab_id] = titulo
    ocultas_sem = set(doc_sembrado.get("ocultas") or [])
    ocultas_doc = set(doc.get("ocultas") or [])
    ocultas_lab: list[str] = []
    for doc_sec in sorted(ocultas_doc - ocultas_sem):
        lab_id = inv_doc.get(doc_sec)
        if lab_id:
            ocultas_lab.append(lab_id)
    ocultas_lab.extend((doc.get("_adaptador_lab") or {}).get("ocultas") or [])
    if ocultas_lab:
        est_out["ocultas"] = list(dict.fromkeys(ocultas_lab))
    # Listas nuevas (no estaban en la siembra): vuelven como estructura.secciones del laboratorio.
    ids_sem = {l["id"] for l in doc_sembrado.get("listas") or []}
    ids_plantilla = {s["id"] for s in plantilla.get("secciones") or [] if s.get("campos") and not s.get("fuente")}
    for lista in doc.get("listas") or []:
        if lista["id"] in ids_sem:
            continue
        lab_id = inv_doc.get(lista["id"]) or (lista["id"][len(PREFIJO):] if lista["id"].startswith(PREFIJO) else lista["id"])
        if lab_id in ids_plantilla:
            continue
        est_out.setdefault("secciones", []).append({
            "id": lab_id,
            "titulo": lista.get("nombre") or lab_id,
            "campos": [{"id": c["id"], "nombre": c.get("nombre", c["id"]), "tipo": c.get("tipo", "texto")} for c in lista.get("campos") or []],
        })
    return est_out or None


def _foto_punto_a_lab(foto_doc: dict, inv: dict[str, str]) -> dict:
    """La foto en forma del laboratorio (`conPunto` de edicion.js: el estado de antes, `bloques` como lista y las páginas en
    `estructura.paginas`). Solo informativa: lo que vale para deshacer es la foto en forma documento que viaja en `doc`."""
    foto: dict[str, Any] = {}
    b = foto_doc.get("bloques")
    if b is not None:
        foto["bloques"] = [_bloque_a_lab(x, inv) for x in b.get("inicio") or []]
        paginas = _paginas_en_lab(b.get("paginas"), inv)
        if paginas:
            foto["estructura"] = {"paginas": paginas}
    if "marca" in foto_doc:
        foto["marca"] = {k: v for k, v in (foto_doc["marca"] or {}).items() if k != "logo_id"}
    return foto


def puntos_lab_desde_doc(puntos_doc: list[dict], plantilla: dict, mapa: dict[str, str]) -> list[dict]:
    """Los puntos del motor en forma del laboratorio. Cada uno lleva su foto en forma documento en `doc` (opaca para los
    bancos, que solo devuelven el estado en el turno siguiente), así `puntos.deshacer` recibe la misma foto que guardó."""
    inv = _inv_mapa(mapa, plantilla)
    out = []
    for p in puntos_doc or []:
        hora = p.get("hora") or ""
        if isinstance(hora, str) and len(hora) > 8:
            hora = hora[11:16] if "T" in hora else hora[:5]
        foto = p.get("foto") or {}
        out.append({"n": p["n"], "antes_de": p.get("antes_de", ""), "hora": hora, "cambio": list(p.get("cambio") or []),
                    "foto": _foto_punto_a_lab(foto, inv), "doc": {"hora": p.get("hora"), "foto": copy.deepcopy(foto)}})
    return out


def puntos_doc_desde_lab(puntos_lab: list[dict], plantilla_id: str, muestra: dict | None, *, hoy: date | None = None) -> list[dict]:
    """Los puntos del estado del laboratorio en forma documento (contrato §3). Si vienen del motor (`doc`), tal cual; si son del
    laboratorio, la foto (el estado de antes) se arma como documento con `doc_desde_lab` y se toman las partes que cambiaron."""
    out = []
    for p in puntos_lab or []:
        cambio = list(p.get("cambio") or [])
        if isinstance(p.get("doc"), dict):
            hora, foto = p["doc"].get("hora"), copy.deepcopy(p["doc"].get("foto") or {})
        else:
            hora = p.get("hora") or ""
            if hora and len(hora) <= 5:
                hora = datetime.now(timezone.utc).replace(hour=int(hora[:2]), minute=int(hora[3:5]), second=0, microsecond=0).isoformat()
            antes = doc_desde_lab(plantilla_id, p.get("foto") or {}, muestra, hoy=hoy)
            foto = {c: copy.deepcopy(pt._parte(antes, c)) for c in cambio if c in pt.CATEGORIAS}
        out.append({"n": p["n"], "antes_de": p.get("antes_de", ""), "hora": hora, "cambio": cambio, "foto": foto})
    return out


def sembrar_doc(plantilla_id: str, muestra: dict | None, *, hoy: date | None = None, user_id: str = "lab") -> dict:
    """Documento sembrado (baseline para deltas)."""
    hoy = _hoy_default(hoy)
    m = _muestra_norm(muestra)
    plantilla = catalogo.plantilla_por_id(plantilla_id)
    if plantilla is None:
        raise KeyError(f"no existe la plantilla «{plantilla_id}»")
    base = generar(user_id, {"nombre": "Lab"}, datetime.now(timezone.utc))
    return sembrar.sembrar(base, plantilla, nivel=m["nivel"], hoy=hoy, pais=m["pais"], porque=["banco"])


def doc_desde_lab(plantilla_id: str, estado: dict | None, muestra: dict | None, *, hoy: date | None = None) -> dict:
    """Estado del laboratorio → documento esquema 2."""
    hoy = _hoy_default(hoy)
    estado = estado or {}
    m = _muestra_norm(muestra)
    plantilla = catalogo.plantilla_por_id(plantilla_id)
    if plantilla is None:
        raise KeyError(f"no existe la plantilla «{plantilla_id}»")
    doc = sembrar_doc(plantilla_id, m, hoy=hoy)
    mapa = mapa_secciones(plantilla, doc)
    est_lab = estado.get("estructura") or {}
    doc = _aplicar_estructura_lab(doc, plantilla, est_lab, mapa, hoy)
    mapa = mapa_secciones(plantilla, doc)
    semilla = _registros_semilla_lab(plantilla, m, est_lab, hoy)
    regs = _aplicar_datos_lab(semilla, estado.get("datos"), (est_lab or {}).get("mapeoEstado"))
    doc = _poner_registros_lab(doc, plantilla, mapa, regs)
    if estado.get("bloques") is not None:
        doc["inicio"] = [_bloque_a_doc(b, mapa) for b in estado["bloques"]]
    if estado.get("marca"):
        doc["marca"] = {**(doc.get("marca") or {}), **copy.deepcopy(estado["marca"])}
    if estado.get("toma"):
        doc["toma"] = copy.deepcopy(estado["toma"])
    pts_lab = estado.get("puntos") or []
    if pts_lab:
        doc["puntos_n"] = max(p["n"] for p in pts_lab)
    return doc


def lab_desde_doc(
    doc_final: dict,
    doc_sembrado: dict,
    plantilla_id: str,
    *,
    vista: str | None = None,
    puntos_doc: list[dict] | None = None,
    muestra: dict | None = None,
    hoy: date | None = None,
) -> dict:
    """Documento → estado en forma del laboratorio (datos como delta frente a la siembra)."""
    plantilla = catalogo.plantilla_por_id(plantilla_id)
    if plantilla is None:
        raise KeyError(f"no existe la plantilla «{plantilla_id}»")
    mapa = mapa_secciones(plantilla, doc_sembrado)
    mapa.update(mapa_secciones(plantilla, doc_final))
    inv = _inv_mapa(mapa, plantilla)
    est_lab = _estructura_lab(doc_final, doc_sembrado, plantilla, mapa)
    semilla = _registros_semilla_lab(plantilla, _muestra_norm(muestra), est_lab, _hoy_default(hoy))
    actuales = _registros_actuales_lab(doc_final, plantilla, mapa)
    datos = _delta_datos_lab(actuales, semilla, plantilla)
    estado: dict[str, Any] = {"vista": vista or "inicio", "bloques": [_bloque_a_lab(b, inv) for b in doc_final.get("inicio") or []]}
    if est_lab:
        estado["estructura"] = est_lab
    if datos:
        estado["datos"] = datos
    marca = {k: v for k, v in (doc_final.get("marca") or {}).items() if k != "logo_id"}
    if marca:
        estado["marca"] = marca
    toma = doc_final.get("toma")
    if toma and toma != est.toma_vacia():
        estado["toma"] = copy.deepcopy(toma)
    if puntos_doc:
        estado["puntos"] = puntos_lab_desde_doc(puntos_doc, plantilla, mapa)
    elif doc_final.get("puntos_n"):
        estado["puntos"] = []
    return estado


def normalizar_estado_lab(estado: dict) -> dict:
    """Quita claves vacías para comparar round-trips."""
    e = copy.deepcopy(estado)

    def limpia(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: limpia(v) for k, v in obj.items() if v is not None and v != {} and v != [] and v != est.toma_vacia()}
        return obj

    return limpia(e)


def _kwargs_responder(responder: Callable[..., dict | Awaitable[dict]], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Contrato §7: (doc, texto, historial, contexto, puntos=…); `imagen` solo si el callable la declara, si no va en contexto."""
    try:
        sig = inspect.signature(responder)
    except (TypeError, ValueError):
        return kwargs
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    filtrado = {k: v for k, v in kwargs.items() if k in params}
    if kwargs.get("imagen") and "imagen" not in filtrado and "contexto" in params:
        ctx = dict(filtrado.get("contexto") or {})
        ctx["imagen"] = kwargs["imagen"]
        filtrado["contexto"] = ctx
    return filtrado


async def _invocar_responder(
    responder: Callable[..., dict | Awaitable[dict]],
    **kwargs: Any,
) -> dict:
    r = responder(**_kwargs_responder(responder, kwargs))
    if inspect.isawaitable(r):
        return await r
    return r


async def procesar_chat_lab(
    cuerpo: dict,
    responder: Callable[..., dict | Awaitable[dict]],
    *,
    hoy: date | None = None,
) -> dict:
    """Un turno de banco: traduce entrada, llama al motor, devuelve forma lab."""
    plantilla_id = cuerpo.get("plantilla") or "membresias"
    estado_in = cuerpo.get("estado") or {}
    muestra = cuerpo.get("muestra")
    hoy = _hoy_default(hoy)
    doc_sem = sembrar_doc(plantilla_id, muestra, hoy=hoy)
    doc = doc_desde_lab(plantilla_id, estado_in, muestra, hoy=hoy)
    if isinstance(cuerpo.get("brief"), dict):  # lo que la persona contó de su negocio (cuestionario): los bancos lo mandan aparte
        doc["brief"] = {**(doc.get("brief") or {}), **cuerpo["brief"]}
    puntos = puntos_doc_desde_lab(estado_in.get("puntos") or [], plantilla_id, muestra, hoy=hoy)
    contexto = {"muestra": _muestra_norm(muestra), "vista": estado_in.get("vista") or "inicio", "seleccion": cuerpo.get("seleccion")}
    pendiente = chat_reglas.sanear_pendiente(cuerpo.get("pendiente"))
    if pendiente:
        # Como la ruta del chat (`crmRoutes._turno_de_chat`): con un borrado pendiente, el «sí» lo resuelven las reglas, sin la IA.
        r = chat_reglas.responder(doc, str(cuerpo.get("texto") or ""), pendiente)
        cambio = r["doc"] is not doc
        estado_out = lab_desde_doc(r["doc"], doc_sem, plantilla_id, vista=contexto["vista"], puntos_doc=puntos, muestra=muestra, hoy=hoy)
        return {"respuesta": r["respuesta"], "estado": estado_out, "cambios": [{"herramienta": "confirmar_pendiente", "args": pendiente, "resultado": r["respuesta"]}] if cambio else [],
                "fallos": [], "intentos": [], "consultas": [], "avisos": [], "estadoCambio": cambio}
    salida = await _invocar_responder(
        responder,
        doc=doc,
        texto=str(cuerpo.get("texto") or ""),
        historial=cuerpo.get("historial") or [],
        contexto=contexto,
        puntos=puntos,
        imagen=cuerpo.get("imagen"),
    )
    doc_fin = salida.get("doc") or doc
    puntos_fin = salida["puntos"] if salida.get("puntos") is not None else puntos  # [] tras deshacer el único punto: vale
    estado_out = lab_desde_doc(doc_fin, doc_sem, plantilla_id, vista=salida.get("vista") or contexto["vista"], puntos_doc=puntos_fin, muestra=muestra, hoy=hoy)
    return {
        "respuesta": salida.get("respuesta") or "",
        "estado": estado_out,
        "cambios": salida.get("cambios") or [],
        "fallos": salida.get("fallos") or [],
        "intentos": salida.get("intentos") or [],
        "consultas": salida.get("consultas") or [],
        "avisos": salida.get("avisos") or [],
        "estadoCambio": bool(salida.get("cambios")) or salida.get("estadoCambio"),
        **({"pendiente": salida["pendiente"]} if salida.get("pendiente") else {}),
    }
