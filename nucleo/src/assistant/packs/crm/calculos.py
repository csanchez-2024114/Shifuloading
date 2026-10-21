"""Datos que se conectan (etapa 2, paso 4): relación entre secciones y campos calculados. El código calcula; el modelo nunca.

Relación = enlace suave. Un campo de texto (por ejemplo Pagos.Miembro) declara a qué sección apunta (`relacion`: id de la sección);
el valor sigue siendo el nombre que se ve («Ana López») y el código lo une con el registro que se llama igual en esa sección (sin
acentos ni mayúsculas), como ya une la ficha del laboratorio. Todo lo que existe sigue igual (tablas, gráficas, Excel, filtros) y los
datos viejos se enlazan solos. Si en la sección destino hay dos con el mismo nombre, ese enlace no cuenta y el código lo dice.
Si cambia el nombre del destino, el código lo cambia en los registros que lo nombraban (`propagar_renombres`).

Calculado = un campo `numero` o `dinero` con `calculo`, una definición de listas cerradas (nada de texto de fórmula ni `eval`):
  {"op": "multiplicar" | "sumar" | "restar" | "dividir", "campos": [id, id, …]}      dentro del registro (cantidad × precio)
  {"op": "saldo", "mas": [id, …], "menos": [id, …]}                                  entradas − salidas (stock, saldo)
  {"op": "dias_desde" | "dias_hasta", "campo": id_fecha}                            días desde/hasta una fecha
  {"op": "resumen", "funcion": "suma" | "cuenta" | "promedio" | "maximo" | "minimo",
   "seccion": id_otra, "relacion": id_campo_relacion_en_otra, "campo": id_numero}  de los registros que lo nombran (lo pagado por Ana)
El valor se calcula al LEER (`con_calculos`): nunca se guarda, así que nunca queda viejo. Escribir en un calculado no se permite.

Al ESCRIBIR por el chat (`preparar_valores`): el valor de un campo enlazado se identifica en la sección destino (igual, singular o
plural, o que contenga sus palabras) y se guarda con el nombre exacto; si no existe o hay varios, es un ERROR que pregunta. Un campo
con `hereda` ({"relacion": id, "campo": id_en_destino}) que llega vacío al CREAR copia ese valor del enlazado (el precio de la venta
queda congelado aunque después cambie el del producto).
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from assistant.packs.crm import secciones_v as sv
from assistant.packs.crm.valores import campo_titulo, parse_numero, sin_acentos

OPS_REGISTRO = ("multiplicar", "sumar", "restar", "dividir")
OPS_FECHA = ("dias_desde", "dias_hasta")
OPS_SALDO = ("saldo",)
FUNCIONES = ("suma", "cuenta", "promedio", "maximo", "minimo")
FORMATOS = ("numero", "dinero")
PASADAS = 3  # un calculado puede usar otro calculado (de su registro o de otra sección): se repite hasta que se acomoda
MAX_EJEMPLOS = 5


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", sin_acentos(str(v or "")).lower()).strip()


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    n = parse_numero(v)
    return None if n is None else float(n)


def _fecha(v: Any) -> date | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    try:
        return date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


def _lista(doc: dict, lista_id: str) -> dict | None:
    return next((l for l in doc.get("listas") or [] if l["id"] == lista_id), None)


def es_calculado(campo: dict) -> bool:
    return isinstance(campo.get("calculo"), dict)


# ───────── Relación ─────────

def titulos(doc: dict, seccion_id: str) -> dict[str, list[str]]:
    """Nombre normalizado → ids de los registros de esa sección que se llaman así (más de uno = ambiguo)."""
    sec = next((s for s in sv.secciones_de({**doc, "ocultas": []}) if s["id"] == seccion_id), None)
    if sec is None:
        return {}
    ct = campo_titulo(sec, sec["campos"])
    out: dict[str, list[str]] = {}
    for r in sv.registros_de({**doc, "ocultas": []}, seccion_id):
        k = _norm((r.get("valores") or {}).get(ct["id"])) if ct else ""
        if k:
            out.setdefault(k, []).append(r["id"])
    return out


def informe_enlace(doc: dict, lista_id: str, campo_id: str) -> dict:
    """Cuántos registros de la lista quedan enlazados por ese campo, y cuáles no tienen pareja o son ambiguos (lo dice el código)."""
    lista = _lista(doc, lista_id)
    campo = next((c for c in (lista or {}).get("campos") or [] if c["id"] == campo_id), None)
    if not lista or not campo or not campo.get("relacion"):
        return {"enlazados": 0, "total": 0, "sin_pareja": [], "ambiguos": []}
    idx = titulos(doc, campo["relacion"])
    enlazados, sin_pareja, ambiguos = 0, [], []
    for r in lista["registros"]:
        v = (r.get("valores") or {}).get(campo_id)
        k = _norm(v)
        if not k:
            continue
        n = len(idx.get(k, []))
        if n == 1:
            enlazados += 1
        elif n == 0:
            sin_pareja.append(str(v))
        else:
            ambiguos.append(str(v))
    return {"enlazados": enlazados, "total": sum(1 for r in lista["registros"] if _norm((r.get("valores") or {}).get(campo_id))),
            "sin_pareja": sorted(set(sin_pareja)), "ambiguos": sorted(set(ambiguos))}


def enlazar(doc: dict, lista_id: str, campo_id: str, destino_id: str) -> dict:
    """Marca el campo de texto como relación con la sección destino. Devuelve el doc nuevo (no toca los valores)."""
    out = copy.deepcopy(doc)
    campo = next(c for c in _lista(out, lista_id)["campos"] if c["id"] == campo_id)
    campo["relacion"] = destino_id
    return out


def propagar_renombres(antes: dict, despues: dict) -> dict:
    """Si cambió el nombre de un registro al que otros apuntan, el nombre nuevo se pone en esos registros (lo que se ve y lo que une).
    Devuelve `despues` (el mismo objeto si no había nada que cambiar)."""
    destinos = {c["relacion"] for l in despues.get("listas") or [] for c in l["campos"] if c.get("relacion")}
    cambios: dict[str, dict[str, str]] = {}
    for d in destinos:
        viejos = {i: k for k, ids in titulos(antes, d).items() for i in ids}
        nuevos = {i: k for k, ids in titulos(despues, d).items() for i in ids}
        cambio = {viejos[i]: i for i in viejos if i in nuevos and nuevos[i] != viejos[i]}
        if cambio:
            # el texto nuevo, tal como lo escribió la persona (no normalizado)
            sec = next(s for s in sv.secciones_de({**despues, "ocultas": []}) if s["id"] == d)
            ct = campo_titulo(sec, sec["campos"])
            reales = {r["id"]: (r.get("valores") or {}).get(ct["id"]) for r in sv.registros_de({**despues, "ocultas": []}, d)}
            cambios[d] = {viejo: reales[i] for viejo, i in cambio.items() if len(titulos(antes, d).get(viejo, [])) == 1}
    if not any(cambios.values()):
        return despues
    out = copy.deepcopy(despues)
    for l in out["listas"]:
        for c in l["campos"]:
            mapa = cambios.get(c.get("relacion") or "")
            if not mapa:
                continue
            for r in l["registros"]:
                v = (r.get("valores") or {}).get(c["id"])
                if _norm(v) in mapa:
                    r["valores"][c["id"]] = mapa[_norm(v)]
    return out


# ───────── Calculado ─────────

def revisar_calculo(doc: dict, lista_id: str, calculo: Any, campo_id: str | None = None) -> str | None:
    """None si la definición es válida para esa sección; si no, el ERROR para el modelo (con lo que sí se puede)."""
    lista = _lista(doc, lista_id)
    if not isinstance(calculo, dict):
        return "ERROR: falta «calculo»."
    campos = {c["id"]: c for c in lista["campos"]}
    numericos = [c for c in lista["campos"] if c.get("tipo") in FORMATOS and c["id"] != campo_id]
    op = calculo.get("op")
    if op in OPS_REGISTRO:
        ids = calculo.get("campos")
        if not isinstance(ids, list) or len(ids) < 2:
            return f"ERROR: «{op}» necesita 2 o más campos de número o dinero de {lista['nombre']}."
        malos = [i for i in ids if i not in campos or campos[i].get("tipo") not in FORMATOS or i == campo_id]
        if malos:
            ok = ", ".join(f"{c['id']} ({c['nombre']})" for c in numericos) or "ninguno (agrégalos primero)"
            return f"ERROR: {', '.join(map(str, malos))} no son campos de número o dinero de {lista['nombre']}. Se puede usar: {ok}."
        return None
    if op in OPS_SALDO:
        mas, menos = calculo.get("mas") or [], calculo.get("menos") or []
        if not isinstance(mas, list) or not isinstance(menos, list) or not mas:
            return "ERROR: «saldo» necesita «mas» (1 o más campos) y «menos» (0 o más) de número o dinero."
        malos = [i for i in [*mas, *menos] if i not in campos or campos[i].get("tipo") not in FORMATOS or i == campo_id]
        if malos:
            ok = ", ".join(f"{c['id']} ({c['nombre']})" for c in numericos) or "ninguno"
            return f"ERROR: {', '.join(map(str, malos))} no son campos de número o dinero de {lista['nombre']}. Se puede usar: {ok}."
        return None
    if op in OPS_FECHA:
        c = campos.get(calculo.get("campo"))
        if not c or c.get("tipo") != "fecha":
            fechas = ", ".join(f"{x['id']} ({x['nombre']})" for x in lista["campos"] if x.get("tipo") == "fecha") or "ninguna"
            return f"ERROR: «{op}» necesita un campo de fecha de {lista['nombre']}: {fechas}."
        return None
    if op == "resumen":
        if calculo.get("funcion") not in FUNCIONES:
            return f"ERROR: funcion debe ser una de: {', '.join(FUNCIONES)}."
        otra = _lista(doc, str(calculo.get("seccion") or ""))
        if not otra:
            return "ERROR: «seccion» debe ser el id de otra sección propia (la de los registros que se resumen)."
        rels = [c for c in otra["campos"] if c.get("relacion") == lista_id]
        rel = next((c for c in rels if c["id"] == calculo.get("relacion")), rels[0] if len(rels) == 1 else None)
        if not rel:
            texto = ", ".join(f"{c['id']} ({c['nombre']})" for c in otra["campos"] if c.get("tipo") == "texto")
            return (f"ERROR: en {otra['nombre']} ningún campo está enlazado con {lista['nombre']}. Primero enlázalo con enlazar_campo "
                    f"(campos de texto de {otra['nombre']}: {texto}).") if not rels else \
                f"ERROR: {otra['nombre']} tiene varios campos enlazados con {lista['nombre']}: pon «relacion» ({', '.join(c['id'] for c in rels)})."
        calculo["relacion"] = rel["id"]
        if calculo["funcion"] != "cuenta":
            c = next((x for x in otra["campos"] if x["id"] == calculo.get("campo")), None)
            if not c or c.get("tipo") not in FORMATOS:
                nums = ", ".join(f"{x['id']} ({x['nombre']})" for x in otra["campos"] if x.get("tipo") in FORMATOS) or "ninguno"
                return f"ERROR: para «{calculo['funcion']}» pon «campo»: uno de número o dinero de {otra['nombre']}: {nums}."
        return None
    return f"ERROR: «op» debe ser una de: {', '.join((*OPS_REGISTRO, *OPS_SALDO, *OPS_FECHA, 'resumen'))}."


def _valor(calculo: dict, valores: dict, doc: dict, lista: dict, registro: dict, hoy: date, ct_lista: dict | None,
           idx_cache: dict) -> float | None:
    op = calculo["op"]
    if op in OPS_REGISTRO:
        xs = [_num(valores.get(i)) for i in calculo["campos"]]
        if op in ("sumar", "restar"):
            if all(x is None for x in xs):
                return None
            xs = [x or 0.0 for x in xs]
            return xs[0] + sum(xs[1:]) if op == "sumar" else xs[0] - sum(xs[1:])
        if any(x is None for x in xs):
            return None
        if op == "multiplicar":
            out = 1.0
            for x in xs:
                out *= x
            return out
        out = xs[0]
        for x in xs[1:]:
            if x == 0:
                return None
            out /= x
        return out
    if op in OPS_SALDO:
        mas = [_num(valores.get(i)) for i in calculo["mas"]]
        menos = [_num(valores.get(i)) for i in calculo.get("menos") or []]
        if all(x is None for x in mas + menos):
            return None
        return sum(x or 0.0 for x in mas) - sum(x or 0.0 for x in menos)
    if op in OPS_FECHA:
        f = _fecha(valores.get(calculo["campo"]))
        if not f:
            return None
        return float((hoy - f).days if op == "dias_desde" else (f - hoy).days)
    # resumen: los registros de la otra sección cuyo campo de relación nombra a ESTE registro (si su nombre no es ambiguo)
    otra = _lista(doc, calculo["seccion"])
    if not otra or not ct_lista:
        return None
    clave = ("titulos", lista["id"])
    if clave not in idx_cache:
        idx_cache[clave] = titulos(doc, lista["id"])
    yo = _norm(valores.get(ct_lista["id"]))
    if not yo or len(idx_cache[clave].get(yo, [])) != 1:
        return None
    mios = [r for r in otra["registros"] if _norm((r.get("valores") or {}).get(calculo["relacion"])) == yo]
    f = calculo["funcion"]
    if f == "cuenta":
        return float(len(mios))
    xs = [x for x in (_num((r.get("valores") or {}).get(calculo.get("campo"))) for r in mios) if x is not None]
    if not xs:
        return 0.0 if f == "suma" else None
    return {"suma": sum(xs), "promedio": sum(xs) / len(xs), "maximo": max(xs), "minimo": min(xs)}[f]


def con_calculos(doc: dict, hoy: date) -> dict:
    """Una copia del CRM con los calculados llenos (solo para LEER: la pantalla, las consultas, las descargas). Nunca se guarda."""
    if not any(es_calculado(c) for l in doc.get("listas") or [] for c in l["campos"]):
        return doc
    out = {**doc, "listas": [{**l, "registros": [{**r, "valores": dict(r.get("valores") or {})} for r in l["registros"]]}
                             for l in doc.get("listas") or []]}
    for _ in range(PASADAS):
        idx_cache: dict = {}
        for l in out["listas"]:
            calcs = [c for c in l["campos"] if es_calculado(c)]
            if not calcs:
                continue
            sec = next((s for s in sv.secciones_de({**out, "ocultas": []}) if s["id"] == l["id"]), None)
            ct = campo_titulo(sec, sec["campos"]) if sec else None
            for r in l["registros"]:
                for c in calcs:
                    v = _valor(c["calculo"], r["valores"], out, l, r, hoy, ct, idx_cache)
                    if v is None:
                        r["valores"].pop(c["id"], None)
                    else:
                        r["valores"][c["id"]] = round(v, 2) if c.get("tipo") == "dinero" else (int(v) if float(v).is_integer() else round(v, 4))
    return out


def ejemplos(doc: dict, lista_id: str, campo_id: str, hoy: date) -> list[str]:
    """Unos valores ya calculados, para que el modelo cuente lo que de verdad salió («Ana: 350»)."""
    calc = con_calculos(doc, hoy)
    lista = _lista(calc, lista_id)
    sec = next((s for s in sv.secciones_de({**calc, "ocultas": []}) if s["id"] == lista_id), None)
    ct = campo_titulo(sec, sec["campos"]) if sec else None
    out = []
    for r in lista["registros"][:MAX_EJEMPLOS]:
        nombre = (r.get("valores") or {}).get(ct["id"]) if ct else r["id"]
        out.append(f"{nombre}: {r['valores'].get(campo_id, '(vacío)')}")
    return out


# ───────── Al escribir: identidad del enlazado y valor heredado ─────────

def _formas(k: str) -> set[str]:
    """La clave normalizada y su singular/plural sencillo («tornillo» ↔ «tornillos», «flor» ↔ «flores»)."""
    out = {k}
    if k.endswith("es") and len(k) > 4:
        out.add(k[:-2])
    if k.endswith("s") and len(k) > 3:
        out.add(k[:-1])
    out.update({k + "s", k + "es"})
    return out


def identificar(doc: dict, destino_id: str, valor: Any) -> dict:
    """¿A qué registro del destino se refiere `valor`? {"titulo", "id"} si es uno; {"ninguno": [títulos]} o {"varios": [títulos]}."""
    sec = next((s for s in sv.secciones_de({**doc, "ocultas": []}) if s["id"] == destino_id), None)
    if sec is None:
        return {"ninguno": []}
    ct = campo_titulo(sec, sec["campos"])
    regs = sv.registros_de({**doc, "ocultas": []}, destino_id)
    nombre = lambda r: (r.get("valores") or {}).get(ct["id"]) if ct else None  # noqa: E731
    k = _norm(valor)
    for prueba in (lambda r: _norm(nombre(r)) == k, lambda r: bool(_formas(_norm(nombre(r))) & _formas(k)),
                   lambda r: bool(k) and all(p in _norm(nombre(r)) for p in k.split())):
        hay = [r for r in regs if nombre(r) and prueba(r)]
        if len(hay) == 1:
            return {"titulo": nombre(hay[0]), "id": hay[0]["id"], "registro": hay[0]}
        if len(hay) > 1:
            return {"varios": [str(nombre(r)) for r in hay[:8]]}
    return {"ninguno": [str(nombre(r)) for r in regs if nombre(r)][:12], "seccion": sec["titulo"]}


def preparar_valores(doc: dict, lista_id: str, campos: list[dict], valores: Any, crear: bool,
                     campo_por_clave) -> tuple[Any, str | None]:
    """Los valores que el modelo quiere guardar, con los enlaces identificados por el código y lo heredado (solo al crear).
    Devuelve (valores, ERROR o None). `campo_por_clave` resuelve «Producto» o «producto» al campo."""
    if not isinstance(valores, dict):
        return valores, None
    lista = _lista(doc, lista_id)
    if lista is None:
        return valores, None
    out = dict(valores)
    enlazados: dict[str, dict] = {}
    for k, v in valores.items():
        c = campo_por_clave(lista["campos"], k)
        if not c or not c.get("relacion") or not _norm(v):
            continue
        r = identificar(doc, c["relacion"], v)
        if "varios" in r:
            return valores, f"ERROR: «{v}» puede ser {', '.join(r['varios'])}. Pregúntale cuál (no lo guardes todavía)."
        if "ninguno" in r:
            hay = ", ".join(r["ninguno"]) or "ninguno todavía"
            return valores, (f"ERROR: «{v}» no está en {r.get('seccion', 'la sección enlazada')} (hay: {hay}). No lo guardes: pregúntale si es "
                             f"uno de esos o si lo agregas primero a {r.get('seccion', 'esa sección')}.")
        out[k] = r["titulo"]  # el nombre exacto: así el enlace y lo calculado siempre cuadran
        enlazados[c["id"]] = r["registro"]
    if crear:
        puestos = {(campo_por_clave(lista["campos"], k) or {}).get("id") for k, v in out.items() if v not in (None, "")}
        for c in lista["campos"]:
            h = c.get("hereda")
            if not isinstance(h, dict) or c["id"] in puestos or h.get("relacion") not in enlazados:
                continue
            v = (enlazados[h["relacion"]].get("valores") or {}).get(h.get("campo"))
            if v not in (None, ""):
                out[c["id"]] = v
    return out, None
