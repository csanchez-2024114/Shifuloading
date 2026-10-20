"""Toma de requerimientos de diseño (estilo Alan, D26-D27): la ficha vive en el documento (`doc["toma"]`, contrato §1), no en el prompt.

Copia de la lógica de `laboratorio/src/plantillas/edicion.js` (tomaVacia, prepararTurnoToma, senalTomaTrasVuelta, construirDesdeFicha, el
resumen y las herramientas abrir_toma, anotar_bloque, anotar_ficha, anotar_nota, quitar_de_ficha y cerrar_toma) y de `piezasNombradas`
de `laboratorio/servidor/chat.js`.

El código abre y cierra la ficha y decide cuándo está lista; el modelo solo la llena con lo que dijo la persona. Al confirmar («sí»), el
CÓDIGO arma el inicio desde la ficha (sin el modelo).

Lo que no es de la toma entra inyectado (lo dueñan otros módulos):
- `Catalogo`: las secciones de la plantilla efectiva (como `secciones_v.secciones_de`), los gráficos posibles por campos (`compatibles`,
  `opciones_por_defecto`, nombres de `graficos`), la revisión de opciones de una vista (`revisar_vista`) y las `fuentes` permitidas;
- en `construir_desde_ficha`: `acomodar` (el acomodo automático del lienzo) y `validar` (la validación de la plantilla completa).

Funciones puras: reciben el documento y devuelven uno nuevo (nunca cambian el que reciben).
"""
from __future__ import annotations

import copy
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import regex  # \p{L} igual que en JS

from assistant.packs.crm import plantillas

ANCHOS_COL = [3, 4, 6, 8, 12]
ALTO_MAX = 4
VISTAS_INICIO = ["kpis", "tablero", "agenda", "vencimientos", "grafico", "tabla", "calendario_mes", "tablero_dinero", "cifra", "atencion",
                 "franjas", "matriz"]
FASES_ABIERTAS = ("juntando", "confirmando")

HERRAMIENTAS_BLOQUEADAS_EN_TOMA = frozenset([
    "agregar_bloque", "cambiar_visual", "cambiar_tamano", "mover_bloque", "quitar_bloque", "cambiar_rangos",
    "cambiar_marca", "usar_logo", "restablecer_marca", "crear_seccion", "agregar_campo", "renombrar_seccion", "quitar_seccion",
    "cambiar_ficha", "cambiar_tarjeta", "quitar_campo", "renombrar_campo", "cambiar_opciones_estado",
])
# Herramientas que el modelo solo ve con la ficha abierta (chat.js).
SOLO_EN_TOMA = frozenset(["anotar_bloque", "quitar_de_ficha", "anotar_ficha", "anotar_nota", "cerrar_toma"])
NOMBRES_TOMA = ("abrir_toma", "anotar_bloque", "quitar_de_ficha", "anotar_ficha", "anotar_nota", "cerrar_toma")

NOMBRE_VISTA = {"kpis": "resumen con cifras", "tablero": "tablero por etapas", "agenda": "agenda", "vencimientos": "por vencer", "grafico": "gráfica",
                "tabla": "lista", "calendario_mes": "calendario del mes", "tablero_dinero": "tablero con montos", "cifra": "cifra con meta y tendencia",
                "atencion": "panel de atención", "franjas": "bandeja por prioridad", "matriz": "cruce de dos campos"}
PREGUNTA_FALTA = {
    "objetivo": "¿Para qué quieres esta pantalla de inicio? (por ejemplo controlar ventas, ver cobros, seguir clientes…)",
    "secciones": "¿Qué partes de tu negocio quieres ver ahí? (ventas, clientes, inventario, lo que uses a diario…)",
    "bloques": "¿Qué quieres ver en tu inicio y de qué parte? (por ejemplo: un resumen de pagos, una gráfica de los estados de tus miembros, la lista de lo que vence…)",
}

# ───────── Textos del código (literales del laboratorio: el prompt es frágil, medido) ─────────

AVISO_ABIERTA = ("El código abrió la ficha de diseño con este pedido (no llames abrir_toma). NO toques la pantalla: anota con anotar_bloque (una llamada "
                 "por cada cosa) SOLO lo que la persona dijo en este mensaje que quiere ver, y anotar_ficha solo para marca o restricciones si las dijo; "
                 "luego haz la pregunta de FALTA.")
AVISO_ABANDONO = ("La persona abandonó la ficha: el código ya la cerró. Dile en una línea que quedó todo como estaba (la pantalla NO cambió) y no "
                  "toques nada.")
AVISO_AJUSTE = ("La persona pidió un ajuste. Si es reemplazar algo («mejor X en vez de Y»): quitar_de_ficha del bloque Y y anotar_bloque con X, las dos "
                "en este turno. Si es agregar: anotar_bloque. Usa solo lo que dijo en ESTE mensaje.")
AVISO_DIGRESION = "Digresión: responde la charla en una línea y retoma la ficha cuando quieran; no anotes este mensaje ni cambies la pantalla."
ERROR_SIN_PIEZAS = ("ERROR: en este mensaje la persona no nombró ninguna pieza (resumen, lista, tablero, gráfica…). No anotes bloques: pregúntale qué "
                    "quiere ver.")

# ───────── Lo que detecta el código (no el modelo) ─────────

# Pedido de DISEÑAR o REHACER una pantalla completa (no un cambio puntual).
_PIDE_DISENO = regex.compile(r"(?<!\p{L})(dis[eé][ñn]a(me|r)?|redis[eé][ñn]a|rehaz|rehacer|arma(me)?\s+(un|mi|el)\s+(nuevo\s+)?(inicio|crm|tablero|pantalla)"
                             r"|(un|mi)\s+inicio\s+nuevo|nuevo\s+inicio|empecemos\s+de\s+cero)(?!\p{L})", regex.IGNORECASE)
_ABANDONA = regex.compile(r"(?<!\p{L})(olv[ií]d(a|alo|ate)|d[eé]jalo(\s+as[ií]|\s+como\s+est[aá])?|ya\s+no\s+(quiero|lo\s+hagas)|mejor\s+no|cancela(lo)?"
                          r"|dejemos\s+eso)(?!\p{L})", regex.IGNORECASE)
# Los \b de estas tres son de JS sin la bandera u: solo cuentan las letras ASCII (re.ASCII).
_OBJETIVO = re.compile(r"\bpara\s+([^:.;]+)", re.IGNORECASE | re.ASCII)
_DIGRESION = re.compile(r"¿?\s*qué hora|qué hora es|cuántas? son|clima|tiempo hace|temperatura", re.IGNORECASE)
_CONFIRMA = regex.compile(r"^\s*(s[ií]|si|dale|ok|claro|confirmo|hazlo|perfecto|adelante)(?:\s|[.!,]|\Z)", regex.IGNORECASE)
_AJUSTE = re.compile(r"\b(no|mejor|cambia|cambiar|en vez|prefiero)\b", re.IGNORECASE | re.ASCII)
# Piezas que la persona NOMBRÓ en su mensaje (mismo vocabulario de la ficha). «lo que vence» también nombra la de vencimientos.
_PIEZAS = re.compile(r"(resumen|gr[aá]fica|dona|barras|columnas|l[ií]nea|pastel|lista|tablero|agenda|calendario|por vencer|vencimientos|lo que vence|embudo|cifra|matriz)")
_HEX = re.compile(r"#?([0-9a-f]{3}|[0-9a-f]{6})", re.IGNORECASE)


@dataclass
class Catalogo:
    """Lo que la toma necesita saber del CRM y no calcula ella."""
    secciones: list[dict]                                          # plantilla efectiva: [{id, titulo, campos?, fuente?, …}]
    compatibles: Callable[[list[dict]], list[dict]]                 # campos → [{id, nombre, …}] gráficos que se pueden dibujar
    opciones_por_defecto: Callable[[str | None, list[dict]], dict]  # (tipo, campos) → opciones que el gráfico elegiría solo
    revisar_vista: Callable[[str, dict, list[dict], str], list[str]]  # (vista, opciones, campos, dónde) → errores
    graficos: dict = field(default_factory=dict)                   # {tipo: {nombre}}
    fuentes: list[str] = field(default_factory=list)               # tipografías permitidas, en orden


# ───────── Ayudas de equivalencia con JS ─────────

def _verdad(x: Any) -> bool:
    """Lo «verdadero» de JS: listas y objetos vacíos cuentan como verdaderos."""
    if isinstance(x, (dict, list)):
        return True
    if isinstance(x, float) and math.isnan(x):
        return False
    return bool(x)


def _js_str(x: Any) -> str:
    """`String(x)` de JS para lo que llega en los argumentos del modelo."""
    if x is _FALTA:
        return "undefined"
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float):
        return _js_num_str(x)
    if isinstance(x, dict):
        return "[object Object]"
    if isinstance(x, list):
        return ",".join("" if v is None else _js_str(v) for v in x)
    return str(x)


def _js_num(x: Any) -> float:
    """`Number(x)` de JS."""
    if x is _FALTA:
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
        return 0.0 if not x else (_js_num(x[0]) if len(x) == 1 else math.nan)
    return math.nan


def _js_num_str(n: float) -> str:
    if math.isnan(n):
        return "NaN"
    return str(int(n)) if float(n).is_integer() else repr(n)


class _Falta:
    def __repr__(self) -> str:
        return "undefined"


_FALTA = _Falta()


def _cadena(x: Any) -> str:
    """`String(x || '')` de JS."""
    return _js_str(x) if _verdad(x) and x is not _FALTA else ""


def _arg(args: dict, k: str) -> Any:
    return args[k] if k in args else _FALTA


def _slug(t: Any) -> str:
    s = unicodedata.normalize("NFD", str(t or "").lower())
    s = re.sub("[̀-ͯ]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"^_|_$", "", s)[:30]
    return s or "x"


def es_hex(c: Any) -> bool:
    return isinstance(c, str) and _HEX.fullmatch(c.strip()) is not None


def _tiene_datos(s: dict) -> bool:
    """La sección tiene registros (propios o de otra, con `fuente`)."""
    return s.get("campos") is not None or _verdad(s.get("fuente"))


def _campos_de(s: dict, por_id: dict) -> list[dict]:
    if _verdad(s.get("fuente")):
        return (por_id.get(s["fuente"]) or {}).get("campos") or []
    return s.get("campos") or []


def _seccion_de(secciones: list[dict], id_: Any) -> dict | None:
    """Acepta el id, el título o el título escrito de otra forma («inventario productos limpieza» → inventario_productos_limpiez…)."""
    q = _slug(id_)
    crudo = "" if not _verdad(id_) else _js_str(id_)
    for s in secciones:
        if s.get("id") == id_ or str(s.get("titulo") or "").lower() == crudo.lower():
            return s
    for s in secciones:
        sid = s.get("id") or ""
        if _slug(s.get("titulo")) == q or sid == q[:30] or (len(q) > 5 and (sid.startswith(q[:25]) or q.startswith(sid))):
            return s
    return None


# ───────── La ficha ─────────

def toma_vacia() -> dict:
    return {"activa": False, "fase": "juntando", "ficha": {"objetivo": "", "secciones": [], "bloques": [], "marca": {}, "restricciones": []},
            "notas": [], "preguntadas": [], "rechazo": False}


def asegurar_toma(doc: dict) -> dict:
    """Copia del documento con `toma` (vacía si no tenía)."""
    d = copy.deepcopy(doc)
    if not d.get("toma"):
        d["toma"] = toma_vacia()
    return d


def toma_abierta(doc: dict) -> bool:
    t = doc.get("toma") or {}
    return bool(t.get("activa")) and t.get("fase") in FASES_ABIERTAS


def faltantes_toma(doc: dict) -> list[dict]:
    """Obligatorios de la ficha antes de confirmar: [{campo, pregunta}]."""
    t = doc.get("toma") or {}
    f = t.get("ficha")
    if not t.get("activa") or not f:
        return []
    out = []
    if not str(f.get("objetivo") or "").strip():
        out.append({"campo": "objetivo", "pregunta": PREGUNTA_FALTA["objetivo"]})
    if not f.get("bloques"):
        out.append({"campo": "bloques", "pregunta": PREGUNTA_FALTA["bloques"]})
    return out


def resumen_de_toma(doc: dict, cat: Catalogo) -> str:
    """Resumen en palabras (sin ids técnicos) para la confirmación."""
    por_id = {s["id"]: s for s in cat.secciones}
    t = doc.get("toma") or {}
    f = t.get("ficha") or {}
    lineas = []
    if f.get("objetivo"):
        lineas.append(f"Vas a tener un inicio para {f['objetivo']}.")
    secs = [x for x in ((por_id.get(i) or {}).get("titulo") or i for i in f.get("secciones") or []) if x]
    if secs:
        lineas.append(f"Partes del menú que importan: {', '.join(secs)}.")
    for n, b in enumerate(f.get("bloques") or []):
        tit = (por_id.get(b.get("seccion")) or {}).get("titulo") or "una sección"
        det = NOMBRE_VISTA.get(b.get("vista")) or b.get("vista")
        tipo = (b.get("opciones") or {}).get("tipo")
        if b.get("vista") == "grafico" and tipo:
            det = f"{(cat.graficos.get(tipo) or {}).get('nombre') or 'gráfica'} en {tit}"
        else:
            det = f"{det} de {tit}"
        tam = b.get("tamano") or {}
        if tam.get("ancho") or tam.get("alto"):
            ancho = f"ancho {_js_str(tam['ancho'])}" if tam.get("ancho") else ""
            coma = ", " if tam.get("ancho") and tam.get("alto") else ""
            alto = f"alto {_js_str(tam['alto'])}" if tam.get("alto") else ""
            det += re.sub(r"\(\s*,", "(", f" ({ancho}{coma}{alto})", count=1)
        lineas.append(f"{n + 1}. {det}")
    m = f.get("marca") or {}
    marca = [x for x in [m.get("primario") and f"color principal {m['primario']}", m.get("secundario") and f"acento {m['secundario']}",
                         m.get("tipografia") and f"letra {m['tipografia']}"] if x]
    if marca:
        lineas.append(f"Marca: {', '.join(marca)}.")
    if f.get("restricciones"):
        lineas.append(f"Restricciones: {'; '.join(f['restricciones'])}.")
    if t.get("notas"):
        lineas.append(f"Notas: {'; '.join(t['notas'])}.")
    return " ".join(lineas) or "Aún no hay nada en la ficha."


def tarjeta_toma(doc: dict, cat: Catalogo) -> dict:
    """Lo que ve el chat (tarjeta compacta): campos llenos o pendientes, sin ids."""
    por_id = {s["id"]: s for s in cat.secciones}
    t = doc.get("toma") or {}
    f = t.get("ficha") or {}
    falta = {x["campo"] for x in faltantes_toma(doc)}
    filas = [
        {"etiqueta": "Objetivo", "texto": f.get("objetivo") or "—", "pendiente": "objetivo" in falta},
        {"etiqueta": "Secciones", "texto": ", ".join((por_id.get(i) or {}).get("titulo") or i for i in f.get("secciones") or []) or "—",
         "pendiente": "secciones" in falta},
        {"etiqueta": "Bloques en inicio", "texto": " · ".join(f"{NOMBRE_VISTA.get(b.get('vista')) or b.get('vista')} ({(por_id.get(b.get('seccion')) or {}).get('titulo') or '?'})"
                                                            for b in f.get("bloques") or []) or "—", "pendiente": "bloques" in falta},
    ]
    m = f.get("marca") or {}
    marca_txt = " · ".join(x for x in [m.get("primario"), m.get("secundario"), m.get("tipografia")] if x)
    if marca_txt or f.get("restricciones"):
        filas.append({"etiqueta": "Marca / extras", "texto": " · ".join(x for x in [marca_txt, *(f.get("restricciones") or [])] if x) or "—", "pendiente": False})
    return {"fase": t.get("fase"), "filas": filas, "notas": t.get("notas") or []}


# ───────── El turno ─────────

def preparar_turno_toma(doc: dict, texto: str) -> dict:
    """Antes de llamar al modelo: abre la ficha si piden diseñar, la cierra si la abandonan, detecta la digresión y el «sí» o el ajuste.

    Devuelve {doc, aviso, digresion, construir}. Con `construir` = True el código arma el inicio (`construir_desde_ficha`) sin el modelo.
    """
    e = asegurar_toma(doc)
    texto = str(texto)
    if not e["toma"]["activa"] and _PIDE_DISENO.search(texto):
        # Se abre por código: el modelo solo llena la ficha con lo que dijo la persona.
        # Objetivo = lo que viene después de «para …» («diséñame un inicio para controlar mis cobros» → «controlar mis cobros»).
        m = _OBJETIVO.search(texto)
        obj = (m.group(1) if m else "").strip()[:120]
        t = toma_vacia()
        t.update(activa=True, fase="juntando")
        t["ficha"]["objetivo"] = obj
        e["toma"] = t
        return {"doc": e, "aviso": AVISO_ABIERTA, "digresion": False, "construir": False}
    t = e["toma"]
    if not t["activa"]:
        return {"doc": e, "aviso": None, "digresion": False, "construir": False}
    if _ABANDONA.search(texto):
        e["toma"] = toma_vacia()
        return {"doc": e, "aviso": AVISO_ABANDONO, "digresion": True, "construir": False}
    digresion = bool(_DIGRESION.search(texto))
    aviso = None
    if t["fase"] == "confirmando":
        if _CONFIRMA.search(texto):
            return {"doc": e, "aviso": None, "digresion": False, "construir": True}
        if _AJUSTE.search(texto):
            t["fase"] = "juntando"
            t["rechazo"] = True
            # (el pedido de ajuste no se guarda como nota: se aplica con quitar_de_ficha/anotar_bloque)
            aviso = AVISO_AJUSTE
    return {"doc": e, "aviso": aviso, "digresion": digresion, "construir": False}


def _pista_toma(doc: dict, cat: Catalogo, mutar: bool) -> str | None:
    t = doc.get("toma")
    if not t or not t.get("activa") or t.get("fase") == "construida":
        return None
    falt = faltantes_toma(doc)
    if t["fase"] == "juntando":
        if not falt:
            if mutar and not t.get("rechazo"):
                t["fase"] = "confirmando"
            if t.get("rechazo"):
                return "Ajuste pendiente: anota con anotar_ficha lo que pidieron y vuelve a resumir cuando esté claro."
            return f"RESUMEN (muéstralo en palabras sencillas y pregunta «¿Lo armo así?»):\n{resumen_de_toma(doc, cat)}"
        f = falt[0]
        if mutar and f["campo"] not in t["preguntadas"]:
            t["preguntadas"].append(f["campo"])
        return f"FALTA: {f['campo']} — pregunta sugerida: {f['pregunta']}"
    if t["fase"] == "confirmando":
        return f"RESUMEN (muéstralo y pregunta «¿Lo armo así?»):\n{resumen_de_toma(doc, cat)}"
    return None


def senal_toma_tras_vuelta(doc: dict, cat: Catalogo) -> tuple[dict, str | None]:
    """Tras las herramientas de una vuelta: una sola pista (FALTA o RESUMEN). Puede avanzar la fase a «confirmando» (por eso devuelve el
    documento nuevo junto con la pista)."""
    d = copy.deepcopy(doc)
    return d, _pista_toma(d, cat, True)


def instruccion_toma_en_contexto(doc: dict, cat: Catalogo) -> str | None:
    t = doc.get("toma") or {}
    if not t.get("activa"):
        return None
    if t.get("fase") == "construida":
        return "La ficha ya está confirmada: aplica el diseño con las herramientas de pantalla según estado.toma.ficha."
    return _pista_toma(copy.deepcopy(doc), cat, False)


def contexto_toma(doc: dict, cat: Catalogo) -> dict:
    """Lo que el modelo ve de la ficha en el estado de la pantalla (`toma` de describirPantalla)."""
    t = doc.get("toma") or {}
    if not t.get("activa"):
        return {"activa": False}
    return {"activa": True, "fase": t.get("fase"), "ficha": t.get("ficha"), "notas": t.get("notas"),
            "faltantes": [x["campo"] for x in faltantes_toma(doc)], "instruccion_turno": instruccion_toma_en_contexto(doc, cat)}


def _piezas_en_orden(texto: Any) -> list[str]:
    out = []
    for x in _PIEZAS.findall(str(texto).lower()):
        if x in ("dona", "barras", "columnas", "línea", "linea", "pastel", "embudo"):
            x = "gráfica"
        elif x in ("lo que vence", "vencimientos"):
            x = "por vencer"
        else:
            x = x.replace("grafica", "gráfica")
        if x not in out:
            out.append(x)
    return out


def piezas_nombradas(texto: Any) -> set[str]:
    """Piezas que la persona NOMBRÓ en su mensaje (medido por el código, mismo vocabulario de la ficha)."""
    return set(_piezas_en_orden(texto))


def herramientas_para(doc: dict) -> list[dict]:
    """Las herramientas de la toma que ve el modelo: las de anotar, solo con la ficha abierta."""
    activa = bool((doc.get("toma") or {}).get("activa"))
    return [h for h in TOMA_HERRAMIENTAS if activa or h["function"]["name"] not in SOLO_EN_TOMA]


def error_anotar_sin_piezas(nombre: str, toma_entrada_activa: bool, doc: dict, texto: str) -> str | None:
    """Ficha recién abierta y la persona no nombró ninguna pieza: no se anotan bloques (medido: «diséñame un inicio para mis miembros»
    anotaba un resumen que nadie pidió, 2 de 8). Se pregunta qué quiere ver."""
    if nombre == "anotar_bloque" and not toma_entrada_activa and (doc.get("toma") or {}).get("activa") and not piezas_nombradas(texto):
        return ERROR_SIN_PIEZAS
    return None


def aviso_piezas_faltantes(doc: dict, texto: str, anotadas: int) -> str | None:
    """Si pidió VARIAS cosas en este mensaje y anotó menos, el código le pide las que faltan (también con 0 anotadas). Solo cuenta lo que
    escribió: no empuja a inventar."""
    t = doc.get("toma") or {}
    if not t.get("activa") or t.get("fase") == "construida":
        return None
    pedidas = _piezas_en_orden(texto)
    if pedidas and anotadas < len(pedidas):
        return f"[Aviso del código] En este mensaje pidió {len(pedidas)} cosas ({', '.join(pedidas)}) y anotaste {anotadas}. Anota con anotar_bloque las que faltan."
    return None


def respuesta_confirmando(doc: dict, cat: Catalogo) -> str | None:
    """En «confirmando» la respuesta la escribe el CÓDIGO desde la ficha real (el modelo podía decir «barras» con «dona» en la ficha)."""
    t = doc.get("toma") or {}
    if not (t.get("activa") and t.get("fase") == "confirmando"):
        return None
    return re.sub(r"^Vas a tener", "Así quedaría tu inicio:", resumen_de_toma(doc, cat), count=1) + "\n\n¿Lo armo así? (dime «sí», o qué cambiarías)"


def respuesta_construida(r: dict) -> str:
    """Lo que dice Shifu tras `construir_desde_ficha` (chat.js)."""
    if r["errores"]:
        return f"No pude armarlo: {r['errores'][0]} Dime qué cambio y lo ajusto."
    n = len(r["doc"].get("inicio") or [])
    return f"¡Listo! Armé tu inicio nuevo con {n} {'bloque' if n == 1 else 'bloques'}, tal como quedó en la ficha. Si quieres mover, agrandar o cambiar algo, dímelo."


# ───────── Construir desde la ficha ─────────

def _base36(n: int) -> str:
    dig = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while True:
        n, r = divmod(n, 36)
        s = dig[r] + s
        if not n:
            return s


def construir_desde_ficha(doc: dict, acomodar: Callable[[list[dict]], list[dict]], validar: Callable[[dict], list[str]],
                          fuentes: Iterable[str] = (), ahora_ms: int | None = None) -> dict:
    """Arma el inicio DESDE LA FICHA confirmada, por código (sin el modelo): reemplaza los bloques, acomoda tamaños (resumen, tablero y
    agenda a lo ancho; lo demás a media fila; si queda uno solo en su fila, a lo ancho) y aplica la marca.

    `acomodar(bloques)` tapa los huecos (el acomodo del lienzo). `validar(doc_candidato)` devuelve los errores de la plantilla resultante;
    `doc_candidato` es el documento nuevo con `inicio` = los bloques SIN acomodar (como valida el laboratorio). Si hay errores no cambia
    nada. Los uid salen de `ahora_ms` en base 36 (por defecto, la hora actual), como `Date.now().toString(36)`.

    Devuelve {doc, errores}.
    """
    estado = asegurar_toma(doc)
    f = estado["toma"]["ficha"]
    ancho_completo = ("kpis", "tablero", "agenda")
    medios = [b for b in f["bloques"] if b.get("vista") not in ancho_completo]
    ultimo_medio = medios[-1] if len(medios) % 2 else None
    base = _base36(int(time.time() * 1000) if ahora_ms is None else ahora_ms)
    bloques = []
    for i, b in enumerate(f["bloques"]):
        tam = b.get("tamano") or {}
        bloques.append({"uid": f"f{base}{i}", "seccion": b.get("seccion"), "vista": b.get("vista"), "opciones": b.get("opciones") or {},
                        "ancho": tam.get("ancho") or (12 if b.get("vista") in ancho_completo or b is ultimo_medio else 6),
                        "alto": 1 if b.get("vista") == "kpis" else (tam.get("alto") or 2)})
    m = f.get("marca") or {}
    fuentes = list(fuentes)
    marca = {**(estado.get("marca") or {})}
    if es_hex(m.get("primario")):
        marca["primario"] = m["primario"]
    if es_hex(m.get("secundario")):
        marca["secundario"] = m["secundario"]
    if m.get("tipografia") and m["tipografia"] in fuentes:
        marca["fuenteTitulos"] = m["tipografia"]
        marca["fuenteTexto"] = m["tipografia"]
    nuevo = {**estado, "inicio": acomodar(copy.deepcopy(bloques)), "marca": marca, "toma": toma_vacia()}
    errores = list(validar({**nuevo, "inicio": bloques}))
    return {"doc": asegurar_toma(doc) if errores else nuevo, "errores": errores}


# ───────── Las herramientas ─────────

def bloqueo_en_toma(doc: dict, nombre: str, digresion: bool = False) -> str | None:
    """Con la ficha abierta, las herramientas de pantalla esperan a que se confirme; en una digresión no se anota nada. Devuelve el
    error (con «ERROR: ») o None si la herramienta puede seguir."""
    if not toma_abierta(doc):
        return None
    if nombre in HERRAMIENTAS_BLOQUEADAS_EN_TOMA and not digresion:
        return "ERROR: primero termina y confirma la ficha de diseño (o ciérrala con cerrar_toma si ya no quieren diseñar)."
    if digresion and nombre in ("anotar_ficha", "anotar_nota"):
        return "ERROR: es una digresión: responde la charla y no anotes nada de este mensaje en la ficha."
    return None


def _validar_valor_ficha(cat: Catalogo, campo: str, valor: Any) -> tuple[bool, Any]:
    secciones = cat.secciones
    por_id = {s["id"]: s for s in secciones}
    if campo == "objetivo":
        t = _cadena(valor).strip()
        return (True, t[:200]) if t else (False, "el objetivo no puede estar vacío.")
    if campo == "seccion":
        s = _seccion_de(secciones, valor)
        if not s:
            return False, f"la sección «{_js_str(valor)}» no existe. Secciones: {', '.join(x['titulo'] for x in secciones if _tiene_datos(x))}."
        return True, s["id"]
    if campo == "bloque":
        b = valor if isinstance(valor, dict) else {}
        sec_arg = _arg(b, "seccion")
        s = _seccion_de(secciones, sec_arg)
        if not s:
            return False, f"la sección «{_js_str(sec_arg)}» no existe."
        vista = _arg(b, "vista")
        if vista not in VISTAS_INICIO:
            return False, f"vista «{_js_str(vista)}» no válida; usa: {', '.join(VISTAS_INICIO)}."
        op = b.get("opciones") if _verdad(b.get("opciones")) else {}
        campos = _campos_de(s, por_id)
        if vista == "grafico":
            posibles = [g["id"] for g in cat.compatibles(campos)]
            tipo_raw = op.get("tipo") if isinstance(op, dict) else None
            tipo = (plantillas.resolver_tipo_grafico(tipo_raw) or tipo_raw) if isinstance(tipo_raw, str) else tipo_raw
            if isinstance(tipo, str) and tipo != tipo_raw and isinstance(op, dict):
                op = {**op, "tipo": tipo}
            if not _verdad(tipo) or tipo not in cat.graficos:
                return False, f"falta opciones.tipo de gráfico válido (posibles con {s['titulo']}: {', '.join(posibles)})."
            if tipo not in posibles:
                return False, f"«{cat.graficos[tipo]['nombre']}» no se puede con {s['titulo']}."
        else:
            errs = cat.revisar_vista(vista, op, campos, f"«{s['titulo']}»")
            if errs:
                return False, " ".join(errs)
        tam = b.get("tamano")
        if _verdad(tam) and isinstance(tam, dict):
            if tam.get("ancho") is not None and _js_num(tam["ancho"]) not in ANCHOS_COL:
                return False, f"ancho debe ser uno de {', '.join(map(str, ANCHOS_COL))}."
            if tam.get("alto") is not None:
                alto = _js_num(tam["alto"])
                if alto < 1 or alto > ALTO_MAX:
                    return False, f"alto entre 1 y {ALTO_MAX}."
        return True, {**b, "seccion": s["id"]}
    if campo in ("marca_primario", "marca_secundario"):
        h = _cadena(valor).strip()
        if not es_hex(h):
            return False, "debe ser un color hex como #1E40AF."
        return True, h if h.startswith("#") else f"#{h}"
    if campo == "tipografia":
        fnt = _cadena(valor).strip()
        if fnt not in cat.fuentes:
            return False, f"tipografía «{fnt}» no disponible ({', '.join(cat.fuentes)})."
        return True, fnt
    if campo == "restriccion":
        t = _cadena(valor).strip()
        return (True, t[:120]) if t else (False, "la restricción no puede estar vacía.")
    return False, f"campo «{campo}» no reconocido (objetivo, seccion, bloque, marca_primario, marca_secundario, tipografia, restriccion)."


def ejecutar_toma(doc: dict, nombre: str, args: dict | None, cat: Catalogo, texto: str = "", digresion: bool = False) -> dict:
    """Ejecuta UNA herramienta de la toma. Devuelve {doc, ok, resultado}: resultado es el texto que lee el modelo («ERROR: …» si no se
    pudo; entonces el documento queda igual). `texto` es el mensaje de la persona (cerrar_toma solo si ella abandona)."""
    args = args if isinstance(args, dict) else {}
    estado = asegurar_toma(doc)
    t0 = estado["toma"]

    def no(resultado: str) -> dict:
        return {"doc": estado, "ok": False, "resultado": f"ERROR: {resultado}"}

    def si(nuevo: dict, resultado: str) -> dict:
        return {"doc": nuevo, "ok": True, "resultado": resultado}

    def con_toma(t: dict) -> dict:
        return {**estado, "toma": t}

    bloqueo = bloqueo_en_toma(estado, nombre, digresion)
    if bloqueo:
        return {"doc": estado, "ok": False, "resultado": bloqueo}
    secciones = cat.secciones
    por_id = {s["id"]: s for s in secciones}

    if nombre == "abrir_toma":
        if t0["activa"] and t0["fase"] in FASES_ABIERTAS:
            return si(estado, "La toma de diseño ya está abierta: sigue con anotar_ficha, no vuelvas a abrir.")
        t = toma_vacia()
        t.update(activa=True, fase="juntando")
        if _verdad(args.get("objetivo")):
            t["ficha"]["objetivo"] = _js_str(args["objetivo"])[:200]
        return si(con_toma(t), "Toma de diseño abierta. Anota solo lo que la persona dijo en este mensaje con anotar_ficha; ideas dudosas van en anotar_nota.")

    if nombre == "cerrar_toma":
        # Abandonar la ficha lo decide la persona, no el modelo (si no, el modelo la cierra para construir directo).
        if not _ABANDONA.search(texto or ""):
            return no("la persona no pidió dejar el diseño: sigue con la ficha (anota lo que pidió) y no la cierres.")
        return si(con_toma(toma_vacia()), "Toma de diseño cerrada. La pantalla no cambió por la ficha.")

    if nombre == "anotar_nota":
        if not t0["activa"]:
            return no("no hay una toma de diseño abierta.")
        n = _cadena(args.get("texto")).strip()[:240]
        if not n:
            return no("falta el texto de la nota.")
        return si(con_toma({**t0, "notas": [*t0["notas"], n]}), "Nota guardada (no es un dato confirmado de la ficha).")

    if nombre == "anotar_bloque":
        # La IA dice en simple QUÉ ver y DE QUÉ parte; el código lo traduce al bloque técnico con valores razonables.
        if not t0["activa"]:
            return no("no hay una ficha de diseño abierta.")
        if t0["fase"] == "construida":
            return no("la ficha ya está confirmada.")
        sec_arg = _arg(args, "seccion")
        sec = _seccion_de(secciones, sec_arg)
        if not sec or not _tiene_datos(sec):
            return no(f"no encuentro «{_js_str(sec_arg)}». Partes: {', '.join(x['titulo'] for x in secciones if _tiene_datos(x))}.")
        campos = _campos_de(sec, por_id)
        estado_c = next((c for c in campos if c.get("tipo") == "estado"), None)
        fecha = next((c for c in campos if c.get("tipo") == "fecha"), None)
        dinero = next((c for c in campos if c.get("tipo") in ("dinero", "numero")), None)
        texto_c = next((c for c in campos if c.get("tipo") == "texto"), None)
        posibles = [g["id"] for g in cat.compatibles(campos)]
        que = args.get("que")
        if que == "resumen":
            bloque = {"vista": "kpis", "seccion": sec["id"], "opciones": {**({"por": estado_c["id"]} if estado_c else {}),
                                                                           **({"suma": dinero["id"]} if dinero and dinero.get("tipo") == "dinero" else {})}}
        elif que == "grafica":
            pedido_arg = args.get("grafico")
            resuelto = plantillas.resolver_tipo_grafico(str(pedido_arg)) if _verdad(pedido_arg) else None
            pedido = resuelto if resuelto and resuelto in posibles else None
            if _verdad(pedido_arg) and not pedido:
                return no(f"«{_js_str(pedido_arg)}» no se puede con {sec['titulo']}. Posibles: {', '.join(posibles)}.")
            tipo = pedido or ("dona" if estado_c and "dona" in posibles else (posibles[0] if posibles else None))
            bloque = {"vista": "grafico", "seccion": sec["id"], "opciones": {**cat.opciones_por_defecto(tipo, campos), "tipo": tipo}}
        elif que == "lista":
            bloque = {"vista": "tabla", "seccion": sec["id"], "opciones": {}}
        elif que == "tablero":
            if not estado_c:
                return no(f"{sec['titulo']} no tiene un campo de estado para armar un tablero.")
            bloque = {"vista": "tablero", "seccion": sec["id"], "opciones": {"por": estado_c["id"], **({"titulo": texto_c["id"]} if texto_c else {})}}
        elif que == "por_vencer":
            if not fecha:
                return no(f"{sec['titulo']} no tiene fechas.")
            bloque = {"vista": "vencimientos", "seccion": sec["id"], "opciones": {"fecha": fecha["id"], **({"titulo": texto_c["id"]} if texto_c else {}), "dias": 30}}
        elif que == "agenda":
            if not fecha:
                return no(f"{sec['titulo']} no tiene fechas.")
            bloque = {"vista": "agenda", "seccion": sec["id"], "opciones": {"fecha": fecha["id"], **({"titulo": texto_c["id"]} if texto_c else {}), "dias": 7}}
        else:
            return no("«que» debe ser: resumen, grafica, lista, tablero, por_vencer o agenda.")
        err = cat.revisar_vista(bloque["vista"], bloque["opciones"], campos, f"«{sec['titulo']}»")
        if err:
            return no(" ".join(err))
        f0 = t0["ficha"]
        ficha = {**f0, "bloques": [*f0["bloques"], bloque], "secciones": list(dict.fromkeys([*f0["secciones"], sec["id"]]))}
        t = {**t0, "ficha": ficha, "fase": "juntando" if t0["fase"] == "confirmando" else t0["fase"], "rechazo": False}
        tipo = bloque["opciones"].get("tipo")
        extra = f" ({_js_str((cat.graficos.get(tipo) or {}).get('nombre', _FALTA))})" if _verdad(tipo) else ""
        return si(con_toma(t), f"Anotado en la ficha: {que}{extra} de {sec['titulo']}.")

    if nombre == "quitar_de_ficha":
        if not t0["activa"]:
            return no("no hay una ficha abierta.")
        i = _js_num(_arg(args, "numero")) - 1
        bs = list(t0["ficha"]["bloques"])
        if not (i >= 0 and i < len(bs)):
            return no(f"la ficha tiene {len(bs)} bloques (numera desde 1).")
        del bs[int(i)]
        t = {**t0, "ficha": {**t0["ficha"], "bloques": bs}, "fase": "juntando", "rechazo": False}
        return si(con_toma(t), f"Quitado el bloque {_js_num_str(i + 1)} de la ficha. Si la persona pidió algo EN SU LUGAR, anótalo AHORA con anotar_bloque.")

    if nombre == "anotar_ficha":
        if not t0["activa"]:
            return no("no hay una toma de diseño abierta.")
        if t0["fase"] == "construida":
            return no("la ficha ya está confirmada: aplica el diseño con las herramientas de pantalla.")
        campo = _cadena(args.get("campo")).strip()
        ok, val = _validar_valor_ficha(cat, campo, _arg(args, "valor"))
        if not ok:
            return no(val)
        f0 = t0["ficha"]
        ficha = {**f0, "marca": {**(f0.get("marca") or {})}, "restricciones": list(f0.get("restricciones") or []),
                 "secciones": list(f0.get("secciones") or []), "bloques": list(f0.get("bloques") or [])}
        if campo == "objetivo":
            ficha["objetivo"] = val
        elif campo == "seccion":
            if val not in ficha["secciones"]:
                ficha["secciones"].append(val)
        elif campo == "bloque":
            ficha["bloques"].append(val)  # la sección sale del bloque
            if val.get("seccion") and val["seccion"] not in ficha["secciones"]:
                ficha["secciones"].append(val["seccion"])
        elif campo == "marca_primario":
            ficha["marca"]["primario"] = val
        elif campo == "marca_secundario":
            ficha["marca"]["secundario"] = val
        elif campo == "tipografia":
            ficha["marca"]["tipografia"] = val
        elif campo == "restriccion":
            ficha["restricciones"].append(val)
        return si(con_toma({**t0, "ficha": ficha, "rechazo": False}), f"Ficha actualizada ({campo}).")

    return no(f"la herramienta «{nombre}» no existe.")


# ───────── Esquemas para el modelo (formato OpenAI), literales del laboratorio ─────────

def _herramienta(nombre: str, descripcion: str, propiedades: dict, requeridas: list[str]) -> dict:
    return {"type": "function", "function": {"name": nombre, "description": descripcion,
                                              "parameters": {"type": "object", "properties": propiedades, "required": requeridas}}}


TOMA_HERRAMIENTAS = [
    _herramienta("abrir_toma", "Abre la toma de requerimientos cuando la persona pide DISEÑAR o REHACER la pantalla de inicio o un CRM completo. NO uses esto "
                 "para cambios puntuales (mover, achicar, un solo bloque): esos van directo con las herramientas de pantalla.", {
                     "objetivo": {"type": "string", "description": "solo si lo dijo en este mensaje"}}, []),
    _herramienta("anotar_bloque", "FICHA DE DISEÑO: anota UN bloque que la persona pidió en ESTE mensaje, dicho en simple. que = resumen | grafica | lista | "
                 "tablero | por_vencer | agenda; seccion = la parte del menú (nombre). grafico = tipo opcional SOLO si lo nombró (dona, barras, columnas, "
                 "linea…). Llama una vez por cada cosa que pidió. No preguntes detalles técnicos: el código elige lo razonable.", {
                     "que": {"type": "string", "enum": ["resumen", "grafica", "lista", "tablero", "por_vencer", "agenda"]}, "seccion": {"type": "string"},
                     "grafico": {"type": "string"}}, ["que", "seccion"]),
    _herramienta("quitar_de_ficha", "Quita de la ficha el bloque número N (como aparece en el resumen) cuando la persona lo pide.",
                 {"numero": {"type": "integer", "minimum": 1}}, ["numero"]),
    _herramienta("anotar_ficha", "Anota en la ficha de diseño UN dato que la persona dijo explícitamente en ESTE mensaje (nunca inventes ni completes). Si "
                 "dudas, usa anotar_nota. Campos: objetivo, seccion, bloque {vista, seccion, opciones?, tamano?}, marca_primario, marca_secundario, "
                 "tipografia, restriccion.", {
                     "campo": {"type": "string"}, "valor": {"description": "string u objeto según el campo"}}, ["campo", "valor"]),
    _herramienta("anotar_nota", "Guarda una idea o duda que la persona mencionó pero que no es un dato firme de la ficha.", {"texto": {"type": "string"}}, ["texto"]),
    _herramienta("cerrar_toma", "Cierra la toma si la persona abandona el diseño o ya no quiere seguir con la ficha.", {}, []),
]
