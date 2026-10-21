"""Catálogo de conceptos del CRM (lista 19-oct, punto 19): una línea por concepto en cada turno; detalle solo si aparece en el mensaje.

También: sugerir 2–3 gráficas (13/14) y humanizar el estado que ve el modelo (sin jerga de ids internos en lo visible).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from assistant.packs.crm import pantalla
from assistant.packs.crm import plantillas
from assistant.packs.crm import secciones_v as sv
from assistant.packs.crm.validar import campos_de

_CARPETA = Path(__file__).resolve().parent / "catalogos"

# Brief rubro → nombre en rubros_grok.json (si no hay match por palabras en que_vendes).
_RUBRO_GROK: dict[str, str] = {
    "comercio": "Tienda de ropa",
    "servicios": "Agencia y servicios profesionales",
    "agencia": "Agencia y servicios profesionales",
    "salud": "Clínica y consultorio",
    "educacion": "Academia y escuela",
    "tecnologia": "Venta y reparación de tecnología",
    "inmobiliaria": "Inmobiliaria",
    "otro": "Agencia y servicios profesionales",
}

_TECNO = re.compile(r"comput|celular|laptop|repar|taller|tecnolog|repuesto|geek", re.I)
_GRAFICAS_PREGUNTA = re.compile(r"gr[aá]ficas?\s+puedo|qu[eé]\s+gr[aá]ficas?", re.I)
_PEDIR_GRAFICA = re.compile(r"gr[aá]fica|grafico|dona|embudo|columnas|barras", re.I)
@lru_cache(maxsize=1)
def _catalogo() -> list[dict]:
    with open(_CARPETA / "conceptos.json", encoding="utf-8") as f:
        return json.load(f)["conceptos"]


@lru_cache(maxsize=1)
def _rubros_grok() -> list[dict]:
    with open(_CARPETA / "rubros_grok.json", encoding="utf-8") as f:
        return json.load(f)["rubros"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Lo que ya se puede hacer y con qué herramienta (etapa 2). El catálogo marcaba «falta» a mano y se quedó viejo: decía «todavía no está:
# ofrece lo más parecido» para relación, calculado y movimientos cuando ya existían, y el modelo ofrecía en vez de hacer (banco_erp,
# banco_calculos y conceptos, 21-oct). Ahora lo decide el código con lo que de verdad está activo.
_YA_SE_HACE = {"relacion": "enlazar_campo", "calculado": "calcular_campo", "movimientos": "aplicar_receta (inventario)"}


def _falta(c: dict) -> str | None:
    """Lo que de verdad falta de ese concepto, o None si ya se puede (CRM_CONECTAR=0 lo vuelve a esconder, como las herramientas)."""
    f = c.get("falta")
    if f in _YA_SE_HACE and os.getenv("CRM_CONECTAR", "1").strip() != "0":
        return None
    return f


def _linea_compacta(c: dict) -> str:
    falta = _falta(c)
    extra = f" (todavía no: {falta})" if falta else ""
    return f"{c['id']}: {c['que_es']}{extra}"


def _detalle(c: dict, en_tu_crm: str | None = None) -> str:
    """Qué es y para qué; si el CRM de la persona YA lo tiene (lo calcula el código), ese hecho en vez de la receta para armarlo."""
    partes = [f"**{c['nombre']}** — {c['que_es']} Para: {c['para_que']}."]
    frases = c.get("frases") or []
    if frases:
        partes.append("Frases típicas: " + "; ".join(frases[:5]) + ".")
    if en_tu_crm:
        partes.append(en_tu_crm)
    else:
        arma = c.get("se_arma_con") or {}
        piezas = []
        if arma.get("vista"):
            piezas.append(f"vista {arma['vista']}")
        campos = arma.get("campos") or []
        if campos:
            piezas.append("campos " + ", ".join(f"{x.get('nombre', '?')} ({x.get('tipo', '?')})" for x in campos[:4]))
        if arma.get("pestana_base"):
            piezas.append(f"pestaña base {arma['pestana_base']}")
        if piezas:
            partes.append("Se arma con: " + "; ".join(piezas) + ".")
    if _falta(c):
        partes.append(f"Todavía no está en el producto ({_falta(c)}): dilo con honestidad y ofrece lo más parecido que SÍ puedas.")
    elif c.get("falta") in _YA_SE_HACE:
        partes.append(f"Ya se puede: hazlo con {_YA_SE_HACE[c['falta']]}.")
    conf = c.get("no_confundir_con") or []
    if conf:
        partes.append("No confundir con: " + ", ".join(conf) + ".")
    return " ".join(partes)




def vistas_nombradas(texto: str) -> set[str]:
    """Las vistas que la persona nombró, por cómo le dice la gente a cada una (`se_le_dice` del catálogo). Solo la usa el cerco de quitar;
    no cambia el detalle del prompt (agregarlo ahí movía otros casos: banco_pestanas y banco_deshacer)."""
    t = _norm(texto or "")
    return {(c.get("se_arma_con") or {}).get("vista") for c in _catalogo()
            if any(re.search(rf"\b{re.escape(_norm(x))}\b", t) for x in c.get("se_le_dice") or [])} - {None}


def es_de_vista(b: dict, vistas: set[str]) -> bool:
    return b.get("vista") in vistas or ("calendario_mes" in vistas and b.get("vista") == "grafico"
                                        and (b.get("opciones") or {}).get("tipo") == "calendario")


def en_tu_crm(c: dict, doc: dict, titulo: Any, abierta: str | None) -> str | None:
    """El hecho del CRM de la persona sobre este concepto (lo calcula el código; el modelo decide qué hacer con él)."""
    sid = c.get("seccion_integrada")
    if sid:
        tit = titulo(sid)
        if sid in (doc.get("ocultas") or []):
            return (f"En este CRM ya existe: es «{tit}», oculta en el menú. No armes otra sección para lo mismo: pregunta si la muestras "
                    "o si quiere otra aparte.")
        return f"En este CRM ya existe: es «{tit}»."
    # Las vistas no llevan hecho aquí: «no hay calendario» se leía como «no se puede» al pedir uno (banco_pestanas 23→19).
    # Quitar una pieza que no está en lo que mira lo frena el cerco (`_no_es_la_pieza_nombrada`).
    return None


def _detectar(texto: str, seleccion: str | None = None) -> set[str]:
    t = _norm(texto or "")
    sel = _norm(seleccion or "")
    hallados: set[str] = set()
    for c in _catalogo():
        cid = c["id"]
        if cid in t or _norm(c.get("nombre") or "") in t:
            hallados.add(cid)
            continue
        for fr in c.get("frases") or []:
            f = _norm(fr)
            if len(f) >= 8 and f in t:
                hallados.add(cid)
                break
            # Raíz de 2+ palabras significativas de la frase
            palabras = [p for p in re.findall(r"[\wáéíóúñ]+", f) if len(p) > 3]
            if len(palabras) >= 2 and all(p in t for p in palabras[:2]):
                hallados.add(cid)
                break
        if sel and cid in sel:
            hallados.add(cid)
    # Intenciones frecuentes sin depender de una sola frase del catálogo
    if re.search(r"\bcita\b|agendar|agéndame|reserv", t):
        hallados.add("cita")
    if re.search(r"\binventario\b|\bstock\b", t):
        hallados.add("inventario")
    if re.search(r"cr[eé]dito|me debe|cuenta por cobrar", t):
        hallados.add("cuenta_por_cobrar")
    if _GRAFICAS_PREGUNTA.search(texto or ""):
        hallados.add("grafica")
    return hallados


def bloque_para_prompt(texto: str, seleccion: str | None = None, doc: dict | None = None, titulo: Any = None,
                       abierta: str | None = None) -> str:
    """Una línea por concepto + detalle de los detectados (0 llamadas extra). Con `doc`, el detalle dice lo que ese CRM ya tiene."""
    por_id = {c["id"]: c for c in _catalogo()}
    lineas = [_linea_compacta(c) for c in _catalogo()]
    detectados = _detectar(texto, seleccion)
    titulo = titulo or (lambda sid: sid)
    extras = [_detalle(por_id[i], en_tu_crm(por_id[i], doc, titulo, abierta) if doc is not None else None)
              for i in sorted(detectados) if i in por_id]
    out = "Conceptos del CRM (una línea cada uno; usa el detalle ampliado solo para lo que la persona mencionó):\n" + "\n".join(lineas)
    if extras:
        out += "\n\nDetalle (solo lo detectado en este mensaje):\n" + "\n".join(extras)
    return out


def _rubro_grok(doc: dict) -> dict | None:
    brief = doc.get("brief") or {}
    rubro = brief.get("rubro") or "otro"
    que = brief.get("que_vendes") or ""
    nombre = _RUBRO_GROK.get(rubro, _RUBRO_GROK["otro"])
    if rubro == "comercio" and _TECNO.search(que):
        nombre = "Venta y reparación de tecnología"
    for r in _rubros_grok():
        if r.get("rubro") == nombre:
            return r
    return _rubros_grok()[0] if _rubros_grok() else None


def _seccion_objetivo(doc: dict, vista: str | None, texto: str) -> dict | None:
    efectiva = pantalla.plantilla_efectiva(doc)
    por_id = {s["id"]: s for s in efectiva["secciones"]}
    if vista and vista != "inicio" and vista in por_id:
        return por_id[vista]
    t = _norm(texto)
    for s in efectiva["secciones"]:
        if _norm(s.get("titulo") or "") in t or _norm(s.get("id") or "") in t:
            return s
    # La primera sección con campos que admite gráficas
    for s in efectiva["secciones"]:
        if pantalla.con_registros(s):
            return s
    return None


def _cuenta_registros(doc: dict, sec_id: str) -> int:
    try:
        return len(sv.registros_de(doc, sec_id))
    except Exception:
        return 0


def sugerir_graficas(doc: dict, seccion: dict | None, limite: int = 3) -> list[dict]:
    """2–3 tipos del catálogo compatibles con los campos, priorizando el rubro (plantillas.compatibles)."""
    if not seccion:
        return []
    por_id = {s["id"]: s for s in pantalla.plantilla_efectiva(doc)["secciones"]}
    campos = campos_de(seccion, por_id)
    compat = plantillas.compatibles(campos)
    ids_compat = {g["id"] for g in compat}
    rubro = _rubro_grok(doc)
    orden: list[str] = []
    if rubro:
        for g in rubro.get("graficas") or []:
            tid = g.get("tipo")
            if tid and tid in ids_compat and tid not in orden:
                orden.append(tid)
    for g in compat:
        if g["id"] not in orden:
            orden.append(g["id"])
    out: list[dict] = []
    graf = plantillas.graficos()
    for tid in orden[:limite]:
        g = graf.get(tid)
        if g:
            out.append({"id": tid, "nombre": g["nombre"]})
    return out


def avisos_turno(doc: dict, texto: str, historial: list[dict] | None, vista: str | None) -> list[str]:
    """Avisos del código al modelo (0 llamadas): gráficas, sección vacía, negocio."""
    avisos: list[str] = []
    brief = doc.get("brief") or {}
    if brief.get("que_vendes"):
        avisos.append("Prioriza consejos y ejemplos según lo que la persona contó de su negocio (que_vendes en el brief), no según el nombre de la plantilla.")
    sec = _seccion_objetivo(doc, vista, texto)
    if _GRAFICAS_PREGUNTA.search(texto or ""):
        sug = sugerir_graficas(doc, sec, 3)
        if sug:
            lista = ", ".join(g["nombre"] for g in sug)
            avisos.append(f"Si preguntan qué gráficas pueden poner: ofrece SOLO 2 o 3 de esta lista (con una recomendada), no enumerar el catálogo entero: {lista}.")
        else:
            avisos.append("Si preguntan qué gráficas pueden poner: con los campos que hay, elige 2 o 3 del catálogo compatibles y recomienda una.")
    if _PEDIR_GRAFICA.search(texto or "") and sec:
        n = _cuenta_registros(doc, sec["id"])
        if n == 0:
            tit = sec.get("titulo") or sec.get("id")
            avisos.append(f"La pestaña «{tit}» no tiene registros todavía: no agregues la gráfica sin avisar; di que está vacía y ofrece cargar datos o importar.")
    return avisos


def masivo_destruye_registros(texto: str) -> bool:
    return bool(re.search(r"\btod[ao]s?\b|\bvarias\b|\btodo\b", texto or "", re.I | re.ASCII))


def humanizar_estado_modelo(estado: dict) -> dict:
    """Renombra claves del contexto a lenguaje de la persona sin quitar los ids que exigen las herramientas (vista, seccion, graficas id+nombre)."""
    from assistant.packs.crm import pantalla

    out = dict(estado)
    integradas = out.pop("secciones_integradas", None)
    if integradas is not None:
        out["secciones_del_menu"] = {
            sid: {
                "nombre": info.get("nombre") or sid,
                "oculta_en_menu": info.get("oculta"),
                "sirve_para": info.get("para_que"),
            }
            for sid, info in integradas.items()
        }
    propias = out.pop("secciones_propias", None)
    if propias is not None:
        out["tablas_del_negocio"] = [
            {
                **({"id": p["id"]} if p.get("id") else {}),
                "nombre": p.get("nombre"),
                "campos": p.get("campos"),
                "cuantos_registros": p.get("total_registros"),
                **({k: p[k] for k in ("totales_exactos", "conteo_por_opcion") if k in p}),
            }
            for p in propias
        ]
    titulos = {s.get("id"): s.get("titulo") or s.get("id") for s in out.get("secciones") or []}
    for sec in out.get("secciones") or []:
        if "graficos_posibles" in sec:
            sec["graficas_disponibles"] = sec.pop("graficos_posibles")
    if "pestanas_base" in out:
        out["plantillas_de_pestana"] = out.pop("pestanas_base")
    nombre_vista = pantalla.NOMBRE_VISTA
    for bloque in out.get("bloques") or []:
        v = bloque.get("vista")
        if isinstance(v, str) and v in nombre_vista:
            bloque["tipo_de_pieza"] = nombre_vista[v]
        sec = bloque.get("seccion")
        if sec in titulos and not bloque.get("titulo_seccion"):
            bloque["titulo_seccion"] = titulos[sec]
    for pieza in out.get("piezas_que_se_ven_ahora") or []:
        v = pieza.get("vista")
        if isinstance(v, str) and v in nombre_vista:
            pieza["tipo_de_pieza"] = nombre_vista[v]
    if out.get("grafico"):
        out["grafico"] = out["grafico"].replace("graficos_posibles", "graficas_disponibles de esa pestaña")
    return out


def humanizar_resultado_herramienta(texto: str, doc: dict) -> str:
    """Sustituye la cola «Así se ve ahora: b0 (kpis)…» por nombres legibles."""
    from assistant.packs.crm import pantalla

    marca = "Así se ve ahora:"
    if marca not in (texto or ""):
        return texto
    prefijo, _ = texto.split(marca, 1)
    titulos = {s["id"]: s.get("titulo") or s["id"] for s in pantalla.plantilla_efectiva(doc)["secciones"]}
    legible = pantalla.asi_se_ve_legible(doc.get("inicio") or [], titulos)
    return f"{prefijo}{marca} {legible}."
