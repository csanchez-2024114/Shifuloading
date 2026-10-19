"""Catálogo de conceptos del CRM (lista 19-oct, punto 19): una línea por concepto en cada turno; detalle solo si aparece en el mensaje.

También: sugerir 2–3 gráficas (13/14), resolver un «sí» suelto a la opción recomendada (7), y quitar jerga interna de la respuesta (8).
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.crm import agente
from app.crm import pantalla
from app.crm import plantillas
from app.crm import secciones_v as sv
from app.crm.validar import campos_de

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
_TIPOS_GRAFICA = (
    "columnas apiladas", "columnas 100", "barras horizontales", "barras apiladas", "barra 100", "línea con área", "linea con area",
    "área apilada", "línea con tendencia", "anillos concéntricos", "anillo de meta", "mapa de árbol", "caja y bigotes", "mapa de calor",
    "tabla de posiciones", "columnas + acumulado", "múltiplos pequeños", "media dona", "rosa polar", "puntos por categoría",
    "línea de tiempo", "barras de progreso", "bala contra meta", "dos kpis", "kpi con tendencia", "columnas", "barras", "línea", "linea",
    "dona", "pastel", "medidor", "embudo", "radar", "dispersión", "burbujas", "histograma", "cascada", "estadísticas", "paleta", "pareto",
    "escalones", "pendiente", "waffle", "sol", "gantt", "kpi", "posiciones",
)
_RECOMIENDO = re.compile(r"te la recomiendo|la recomiendo|te recomiendo", re.I)
_PREGUNTA = re.compile(r"\?|¿")


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


def _linea_compacta(c: dict) -> str:
    falta = c.get("falta")
    extra = f" (todavía no: {falta})" if falta else ""
    return f"{c['id']}: {c['que_es']}{extra}"


def _detalle(c: dict) -> str:
    partes = [f"**{c['nombre']}** — {c['que_es']} Para: {c['para_que']}."]
    frases = c.get("frases") or []
    if frases:
        partes.append("Frases típicas: " + "; ".join(frases[:5]) + ".")
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
    if c.get("falta"):
        partes.append(f"Todavía no está en el producto ({c['falta']}): dilo con honestidad y ofrece lo más parecido que SÍ puedas.")
    conf = c.get("no_confundir_con") or []
    if conf:
        partes.append("No confundir con: " + ", ".join(conf) + ".")
    return " ".join(partes)


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


def bloque_para_prompt(texto: str, seleccion: str | None = None) -> str:
    """Una línea por concepto + detalle de los detectados (0 llamadas extra)."""
    por_id = {c["id"]: c for c in _catalogo()}
    lineas = [_linea_compacta(c) for c in _catalogo()]
    detectados = _detectar(texto, seleccion)
    extras = [_detalle(por_id[i]) for i in sorted(detectados) if i in por_id]
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
            lista = ", ".join(f"{g['nombre']} ({g['id']})" for g in sug)
            avisos.append(f"Si preguntan qué gráficas pueden poner: ofrece SOLO 2 o 3 de esta lista (con una recomendada), no enumerar el catálogo entero: {lista}.")
        else:
            avisos.append("Si preguntan qué gráficas pueden poner: con los campos que hay, elige 2 o 3 del catálogo compatibles y recomienda una.")
    if _PEDIR_GRAFICA.search(texto or "") and sec:
        n = _cuenta_registros(doc, sec["id"])
        if n == 0:
            tit = sec.get("titulo") or sec.get("id")
            avisos.append(f"La pestaña «{tit}» no tiene registros todavía: no agregues la gráfica sin avisar; di que está vacía y ofrece cargar datos o importar.")
    return avisos


def _tipo_recomendado(msg: str) -> str | None:
    """Tipo de gráfica recomendada en el último mensaje de Shifu (p. ej. dona)."""
    t = msg or ""
    pos = None
    m = _RECOMIENDO.search(t)
    if m:
        pos = m.start()
    ventana = t[:pos] if pos is not None else t
    ventana_l = ventana.lower()
    for g in _TIPOS_GRAFICA:
        if g in ventana_l:
            return g.replace("linea", "línea") if g == "linea" else g
    return None


def texto_tras_afirmacion(texto: str, historial: list[dict] | None) -> str | None:
    """Un «sí» suelto tras una pregunta con recomendación → instrucción explícita (punto 7)."""
    if not agente._AFIRMA.match(texto or ""):
        return None
    ultima = next((str(h.get("t") or "") for h in reversed(historial or []) if h.get("de") == "shifu"), "")
    if not _PREGUNTA.search(ultima):
        return None
    rec = _tipo_recomendado(ultima)
    if rec:
        return f"acepto tu recomendación: pon la gráfica de {rec} en el inicio"
    if _RECOMIENDO.search(ultima):
        return "acepto la opción que recomendaste"
    return None


def masivo_destruye_bloques(texto: str) -> bool:
    """«Todos» que pide quitar varias piezas, no «todos los miembros» como alcance de una sola gráfica."""
    t = texto or ""
    if re.search(r"\b(quita|quitar|saca|borra|elimina)\s+(todos?|todas?)\s+(los?\s+)?(bloque|gr[aá]fica|grafica|pieza)", t, re.I):
        return True
    if re.search(r"\b(todos?|todas?)\s+(los?\s+)?(bloque|gr[aá]fica|grafica|pieza)", t, re.I):
        return True
    return False


def masivo_destruye_registros(texto: str) -> bool:
    return bool(re.search(r"\btod[ao]s?\b|\bvarias\b|\btodo\b", texto or "", re.I | re.ASCII))


_JERGA_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"propia,?\s*no\s+integrad[ao]", re.I), ""),
    (re.compile(r"\bintegrad[ao]\b", re.I), "del menú"),
    (re.compile(r"\bpestanas_base\b", re.I), ""),
    (re.compile(r"\bgraficos_posibles\b", re.I), "tipos de gráfica disponibles"),
    (re.compile(r"\b(l_[a-z0-9_]+|p_[a-z0-9_]+|b\d+)\b", re.I), ""),
    (re.compile(r"\b[a-z]+_[a-z_]{2,}\b"), ""),
    (re.compile(r"\bagregar_\w+\b|\bquitar_\w+\b|\bcrear_\w+\b", re.I), ""),
    (re.compile(r"\s{2,}"), " "),
]


def sin_jerga(texto: str) -> str:
    """Quita jerga interna visible en la respuesta (punto 8)."""
    if not texto:
        return texto
    out = texto
    for pat, repl in _JERGA_SUBS:
        out = pat.sub(repl, out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
