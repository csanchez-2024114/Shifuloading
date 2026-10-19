"""La pantalla tal como la ve la persona y como se la describe el código al modelo (port de `edicion.js`: plantillaEfectiva,
describirPantalla, fichaDe, paginaDe, etiquetaCambio y las ayudas para encontrar una sección por cómo la nombran).

En el laboratorio la plantilla efectiva es «plantilla base + cambios»; en el CRM es el documento mismo: las secciones con registros
salen de `secciones_v.secciones_de(doc)` (contactos, tareas y listas) y se suman las pestañas fijas de Carlos que no tienen registros
(cobros, actividad, equipo, importar, automatizaciones), como las fijas del laboratorio (Historial, Equipo, Automatizaciones): se
pueden abrir pero no llevan piezas. El inicio es `doc["inicio"]`, cada pestaña con lienzo propio es `doc["paginas"][id]`, la marca es
`doc["marca"]` (el logo, `logo_id`) y la pestaña que mira la persona es un dato de la pantalla que entra como `vista`.

Lo que se le dice al modelo es LITERAL del laboratorio (el prompt es frágil, medido). Sin el número de registros por sección: medido,
sumaba a que «agrega una dona» reemplazara la gráfica (1 de 6); los números los da consultar_datos.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

import regex

from app.crm import plantillas, secciones_v
from app.crm import toma as tm
from app.crm.lienzo import VISTAS_INICIO, rangos_de, ubicacion, ubicar
from app.crm.marca import FUENTES
from app.crm.secciones import IDS_SECCION, titulo_seccion
from app.crm.validar import VISTAS, campos_de, revisar_vista, verdad

# Pestañas fijas de Carlos sin registros: id → la vista del laboratorio que hace lo mismo (ninguna lleva piezas).
FIJAS = {"cobros": "feed", "actividad": "feed", "rrhh": "equipo", "importar": "feed", "automatizaciones": "interruptores"}

NOMBRE_VISTA = {"kpis": "resumen con cifras", "tablero": "tablero por etapas", "agenda": "agenda", "vencimientos": "por vencer", "grafico": "gráfica",
                "tabla": "lista", "calendario_mes": "calendario del mes", "tablero_dinero": "tablero con montos", "cifra": "cifra con meta y tendencia",
                "atencion": "panel de atención", "franjas": "bandeja por prioridad", "matriz": "cruce de dos campos"}

REJILLA = ("Inicio y cada pestaña en 12 columnas. ancho ∈ [3,4,6,8,12] (3 = cuatro por fila, 12 = ancho completo). alto ∈ 1..4 filas. Todo debe "
           "caber en una pantalla: más bloques = bloques más bajos.")
NOTA_MARCA = ("Branding: cualquier color (hex) de fondo, superficie, texto, principal y secundario, y tipografía de títulos y de texto. El código "
              "ajusta lo que no se lea.")
GRAFICO = ('vista "grafico" con opciones {tipo: <id de graficos_posibles>} y opcionalmente {funcion: conteo|suma|promedio|mediana|minimo|maximo|moda|'
           'desviacion, valor: campo numérico, agrupar: campo o "mes", meta, top}. La vieja "grafica" (barras/dona/linea) sigue existiendo en bloques '
           'que ya la tienen.')


# ───────── Ayudas de equivalencia con JS ─────────

class _Falta:
    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False


FALTA = _Falta()  # «undefined» de JS: la clave no vino


def js(v: Any) -> str:
    """`${v}` / `String(v)` de JS para lo que llega en los argumentos del modelo."""
    if v is FALTA:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Infinity" if v > 0 else "-Infinity"
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, dict):
        return "[object Object]"
    if isinstance(v, list):
        return ",".join("" if x is None or x is FALTA else js(x) for x in v)
    return str(v)


def js_num(x: Any) -> float:
    """`Number(x)` de JS."""
    if x is FALTA:
        return math.nan
    if x is None:
        return 0.0
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        t = x.strip()
        if not t:
            return 0.0
        try:
            return float(t)
        except ValueError:
            return math.nan
    if isinstance(x, list):
        return 0.0 if not x else (js_num(x[0]) if len(x) == 1 else math.nan)
    return math.nan


def entero(n: float) -> Any:
    """Un número de JS para guardar o escribir: 8.0 → 8 (NaN y decimales quedan como están)."""
    return int(n) if isinstance(n, float) and n.is_integer() else n


def arg(args: dict, k: str) -> Any:
    return args[k] if k in args else FALTA


def slug(t: Any) -> str:
    s = unicodedata.normalize("NFD", (js(t) if verdad(t) and t is not FALTA else "").lower())
    s = re.sub("[̀-ͯ]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"^_|_$", "", s)[:30]
    return s or "x"


_BORDE = regex.compile(r"^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$")


def nombre_literal(nombre: Any, texto: Any) -> str:
    """Nombre visible con las palabras LITERALES de la persona (técnica de Alan: el código pasa lo literal, no el modelo). Si el modelo
    manda «cumpleanos» y la persona escribió «cumpleaños», se usa lo de la persona (con mayúscula inicial)."""
    n = (js(nombre) if verdad(nombre) and nombre is not FALTA else "").strip()
    if not n or not verdad(texto):
        return n
    palabras = [_BORDE.sub("", w) for w in re.split(r"\s+", js(texto))]
    objetivo, k = slug(n), len(re.split(r"\s+", n))
    for i in range(len(palabras) - k + 1):
        frase = " ".join(palabras[i:i + k])
        if slug(frase) == objetivo:
            return frase[:1].upper() + frase[1:]
    return n[:1].upper() + n[1:]


# ───────── Secciones ─────────

def con_registros(s: dict | None) -> bool:
    """La sección tiene registros (propios o, con `fuente`, de otra): `s.campos || s.fuente` de JS."""
    return bool(s) and (s.get("campos") is not None or verdad(s.get("fuente")))


def seccion_de(secciones: list[dict], id_: Any) -> dict | None:
    """Acepta el id, el título o el título escrito de otra forma («inventario productos limpieza» → inventario_productos_limpiez…).
    En el CRM además acepta el id sin el prefijo `l_` de las secciones que vienen de una plantilla («miembros» → `l_miembros`)."""
    q = slug(id_)
    crudo = js(id_) if verdad(id_) and id_ is not FALTA else ""
    for s in secciones:
        if s.get("id") == id_ or str(s.get("titulo") or "").lower() == crudo.lower():
            return s
    for s in secciones:
        sid = s.get("id") or ""
        if slug(s.get("titulo")) == q or sid == q[:30] or (len(q) > 5 and (sid.startswith(q[:25]) or q.startswith(sid))) or sid == f"l_{q}":
            return s
    return None


def _fijas(doc: dict, ya: set) -> list[dict]:
    rubro = (doc.get("brief") or {}).get("rubro")
    ocultas = doc.get("ocultas") or []
    return [{"id": i, "titulo": titulo_seccion(rubro, i, doc.get("secciones") or {}), "grupo": 1, "vista": FIJAS[i], "fija": True}
            for i in IDS_SECCION if i in FIJAS and i not in ocultas and i not in ya]


def nombre_plantilla(doc: dict) -> str:
    pid = (doc.get("plantilla") or {}).get("id")
    p = plantillas.plantilla_por_id(pid) if pid else None
    return (p or {}).get("nombre") or (doc.get("brief") or {}).get("nombre") or "Mi CRM"


def plantilla_efectiva(doc: dict, secciones: list[dict] | None = None) -> dict:
    """La plantilla tal como la ve la persona: {id, nombre, secciones}. Cada sección con lienzo propio lleva `pagina` (sus piezas)."""
    secs = [dict(s) for s in (secciones if secciones is not None else secciones_v.secciones_de(doc))]
    paginas = doc.get("paginas") or {}
    for s in secs:
        if s["id"] in paginas:
            s["pagina"] = paginas[s["id"]]
    secs += _fijas(doc, {s["id"] for s in secs})
    return {"id": (doc.get("plantilla") or {}).get("id") or "crm", "nombre": nombre_plantilla(doc), "secciones": secs}


def ficha_de(seccion: dict, campos: list[dict]) -> dict:
    """Cómo se ve la ficha de un registro: la que definió la persona o, por defecto, todos sus campos en un grupo."""
    ids = {c["id"] for c in campos}
    f = seccion.get("ficha") or {}
    grupos = f["grupos"] if f.get("grupos") is not None else [{"titulo": "Datos", "campos": [c["id"] for c in campos]}]
    grupos = [{**g, "campos": [i for i in g.get("campos") or [] if i in ids]} for g in grupos]
    return {"grupos": [g for g in grupos if g["campos"]],
            "relacionados": True if f.get("relacionados") is None else f["relacionados"],
            "linea_tiempo": True if f.get("linea_tiempo") is None else f["linea_tiempo"]}


def paginable(s: dict | None) -> bool:
    return con_registros(s) and s.get("vista") in VISTAS_INICIO


def pagina_de(efectiva: dict, doc: dict, sec_id: str) -> list[dict] | None:
    """Las piezas de una pestaña: su lienzo propio o, si no tiene, su vista de siempre como única pieza (`p_<id>`). None = no admite."""
    s = next((x for x in efectiva["secciones"] if x["id"] == sec_id), None)
    if not paginable(s):
        return None
    propias = (doc.get("paginas") or {}).get(sec_id)
    if propias:
        return propias
    return [{"uid": f"p_{sec_id}", "seccion": sec_id, "vista": s["vista"], "opciones": s.get("opciones") or {}, "ancho": 12, "alto": 3}]


def lienzo_de_bloque(doc: dict, uid: Any) -> str | None:
    """En qué lienzo está un bloque: None = el inicio; si no, el id de la pestaña."""
    if not verdad(uid) or uid is FALTA or any(b.get("uid") == uid for b in doc.get("inicio") or []):
        return None
    for pid, bs in (doc.get("paginas") or {}).items():
        if any(b.get("uid") == uid for b in bs):
            return pid
    u = js(uid)
    return u[2:] if u.startswith("p_") else None  # la pieza por defecto de una pestaña sin lienzo propio


def catalogo_toma(efectiva: dict) -> tm.Catalogo:
    """Lo que la toma de diseño necesita saber del CRM (toma.py lo recibe inyectado)."""
    return tm.Catalogo(secciones=efectiva["secciones"], compatibles=plantillas.compatibles, opciones_por_defecto=plantillas.opciones_por_defecto,
                       revisar_vista=revisar_vista, graficos=plantillas.graficos(), fuentes=list(FUENTES))


# ───────── Lo que ve el modelo ─────────

def _num(v: Any) -> str:
    return js(v)


def describir_pantalla(doc: dict, vista: str | None = "inicio", puntos: list[dict] | None = None, secciones: list[dict] | None = None) -> dict:
    """El estado de la pantalla que se le manda al modelo (JSON): bloques del inicio y de cada pestaña con dónde se ven, y por sección sus
    campos, su ficha y los gráficos que admite. `puntos` son los de `crm_puntos` (lo que se puede deshacer); `vista`, la pestaña abierta."""
    efectiva = plantilla_efectiva(doc, secciones)
    por_id = {s["id"]: s for s in efectiva["secciones"]}
    inicio = doc.get("inicio") or []
    marca = {k: v for k, v in (doc.get("marca") or {}).items() if k != "logo_id"}
    tiene_logo = verdad((doc.get("marca") or {}).get("logo_id")) or verdad((doc.get("marca") or {}).get("logo"))
    vista = vista or "inicio"

    def bloque_pestana(b: dict, u: dict) -> dict:
        out = {"id": b.get("uid"), "vista": b.get("vista"), "seccion": b.get("seccion"), "donde_se_ve": ubicacion(u.get(b.get("uid")))}
        for k in ("ancho", "alto", "opciones"):
            if k in b:
                out[k] = b[k]
        return out

    pestanas = {}
    for pid, bs in (doc.get("paginas") or {}).items():
        u = ubicar(bs)
        pestanas[pid] = [bloque_pestana(b, u) for b in bs]

    salida: dict = {
        "plantilla": efectiva["nombre"],
        "pedidos_anteriores": [{"pedido": p.get("n"), "dijo": p.get("antes_de"), "cambio": p.get("cambio") or ["bloques", "marca", "estructura"], "hora": p.get("hora")}
                               for p in sorted(puntos or [], key=lambda x: x.get("n") or 0)],
        "marca": {**marca, "logo": "(tiene logo)" if tiene_logo else "(sin logo)", "fuentes_permitidas": list(FUENTES), "nota": NOTA_MARCA},
        "pestana_abierta": vista,
        "pestanas_con_piezas": pestanas,
    }
    if vista != "inicio":
        salida["piezas_que_se_ven_ahora"] = [{"id": b.get("uid"), "vista": b.get("vista"), "nombre": NOMBRE_VISTA.get(b.get("vista"), b.get("vista")),
                                              "seccion": b.get("seccion")} for b in (pagina_de(efectiva, doc, vista) or [])]
    salida["rejilla"] = REJILLA
    u = ubicar(inicio)
    bloques = []
    for i, b in enumerate(inicio):
        x = {"id": b.get("uid"), "posicion": i + 1, "donde_se_ve": ubicacion(u.get(b.get("uid"))), "vista": b.get("vista"), "seccion": b.get("seccion")}
        if b.get("seccion") in por_id:
            x["titulo_seccion"] = por_id[b["seccion"]].get("titulo")
        for k in ("opciones", "ancho", "alto"):
            if k in b:
                x[k] = b[k]
        if b.get("vista") == "vencimientos":
            x["grupos_actuales"] = ["Vencidos {vencidos:true}" if r.get("desde") is None else
                                    f"De {_num(r.get('desde'))} a {_num(r.get('hasta'))} días {{desde:{_num(r.get('desde'))},hasta:{_num(r.get('hasta'))}}}"
                                    for r in rangos_de(b.get("opciones"))]
        bloques.append(x)
    salida["bloques"] = bloques
    secs = []
    for s in efectiva["secciones"]:
        if not con_registros(s):
            continue
        campos = campos_de(s, por_id)
        x = {"id": s["id"], "titulo": s.get("titulo"),
             "campos": [{"id": c["id"], "nombre": c.get("nombre"), "tipo": c.get("tipo"), **({"opciones": c["opciones"]} if c.get("opciones") else {})} for c in campos],
             "ficha": ficha_de(s, campos)}
        if s.get("tarjeta"):
            x["tarjeta"] = s["tarjeta"].get("campos")
        x["graficos_posibles"] = [f"{g['id']} ({g['nombre']})" for g in plantillas.compatibles(campos)]
        secs.append(x)
    salida["secciones"] = secs
    salida["vistas"] = {v: {"requiere": VISTAS[v]["requiere"], "opcional": list((VISTAS[v].get("opcional") or {}).keys())} for v in VISTAS_INICIO}
    salida["grafico"] = GRAFICO
    salida["toma"] = tm.contexto_toma(doc, catalogo_toma(efectiva))
    salida["pestanas_base"] = [f"{p['id']} ({', '.join(p['palabras'][:2])})" for p in plantillas.pestanas()]
    return salida


def etiqueta_cambio(c: dict) -> str | None:
    """Cada cambio dicho en simple (el chat lo muestra SIEMPRE: nada se oculta). None = no se muestra (navegar, anotar en la ficha)."""
    if "etiqueta" in c:
        return c["etiqueta"]  # la herramienta ya lo dijo en simple (datos: a quién y qué)
    a = c.get("args") or {}
    donde = f" en «{js(a['pestana'])}»" if verdad(a.get("pestana")) and a.get("pestana") != "inicio" else ""
    v = NOMBRE_VISTA.get(a.get("vista")) if isinstance(a.get("vista"), str) else None
    v = v or ("gráfica" if a.get("vista") == "grafico" else "pieza")
    textos = {
        "agregar_bloque": f"agregó {'una pieza' if v == 'pieza' else f'«{v}»'}{donde}",
        "quitar_bloque": "quitó una pieza",
        "mover_bloque": "movió una pieza",
        "cambiar_tamano": "cambió el tamaño de una pieza",
        "cambiar_visual": f"cambió una pieza a «{v}»",
        "cambiar_rangos": "cambió los grupos de lo que vence",
        "crear_seccion": f"creó la pestaña «{js(a.get('titulo') or a.get('desde') or 'nueva')}»",
        "agregar_campo": f"agregó el campo «{js(arg(a, 'nombre'))}»",
        "quitar_campo": f"quitó el campo «{js(arg(a, 'campo'))}»",
        "renombrar_campo": f"renombró un campo a «{js(arg(a, 'nombre'))}»",
        "renombrar_seccion": f"renombró una pestaña a «{js(arg(a, 'titulo'))}»",
        "quitar_seccion": f"quitó la pestaña «{js(arg(a, 'seccion'))}»",
        "cambiar_opciones_estado": "cambió las opciones de un estado",
        "cambiar_ficha": "cambió la ficha",
        "cambiar_tarjeta": "cambió las tarjetas del tablero",
        "cambiar_marca": "cambió colores o letra",
        "usar_logo": "puso tu logo",
        "restablecer_marca": "volvió al diseño base",
        "deshacer": "deshizo un pedido",
        "construir_desde_ficha": "armó tu inicio nuevo",
    }
    return textos.get(c.get("herramienta"))


def asi_se_ve_legible(bs: list[dict], titulos_seccion: dict[str, str] | None = None) -> str:
    """Misma información que `edicion.asi_se_ve`, con nombres de pieza y pestaña (para el modelo en modo diseño)."""
    u = ubicar(bs)
    titulos = titulos_seccion or {}
    partes: list[str] = []
    for b in bs:
        v = NOMBRE_VISTA.get(b.get("vista") or "", b.get("vista") or "pieza")
        sec = titulos.get(b.get("seccion") or "", b.get("seccion") or "")
        pieza = f"{v} de «{sec}»" if sec else v
        partes.append(f"{pieza} → {ubicacion(u.get(b.get('uid')))}")
    return "; ".join(partes)
