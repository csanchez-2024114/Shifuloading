"""Agente del chat con el sistema de diseño del laboratorio (D61). Solo con CRM_DISENO=1; apagado, todo va por `agente.py` como siempre.

Es el agente de Carlos (modelo + herramientas + verificador, las mismas INSTRUCCIONES) con lo que el laboratorio midió en
`laboratorio/servidor/chat.js`:
- Datos por chat: agregar_registro, editar_registro, borrar_registro y consultar_datos (esquemas LITERALES de `registros.py`) sobre
  TODAS las secciones con registros (`secciones_v`: contactos, tareas y secciones propias). El código entiende cada valor, encuentra
  el registro y dice qué cambiar (`registros.ejecutar_dato`); aquí solo se aplica con `secciones_v.registro_*`, con el id ya generado.
  Las herramientas de Carlos que hacían lo mismo (agregar_contactos, cambiar_contacto, eliminar_contacto, agregar_registros,
  cambiar_registro, eliminar_registro) ya no se le muestran al modelo, pero si las llama siguen funcionando: van a los mismos
  handlers (alias por una versión, contrato §8). consultar_datos no cambia nada: va a `consultas`, no a `cambios`.
- Deshacer por pedido (`deshacer`, resuelto por el código con `puntos.deshacer`; la lista va en `pedidos_anteriores`). Reglas de
  chat.js: tras un deshacer solo (sin otra herramienta en esa vuelta) el turno se cierra y el modelo responde sin herramientas; tras
  deshacer, en el mismo mensaje solo se puede cambiar LO MISMO; si lo único que pasó fue deshacer, la respuesta la escribe el código.
  El punto de cada turno lo guarda la ruta del chat (`crmRoutes._turno_de_chat`).
- Cercos de honestidad: afirma_cambio (D51) en vez de las frases de logro, lo creado para guardar un dato y no dicho, borrar varios
  registros con confirmación, y los errores de duplicado y de procedencia de `registros` como errores de la herramienta.
- La toma de diseño (`toma.py`): el código abre, cierra y confirma la ficha, y al «sí» arma el inicio sin el modelo.

Ganchos que llena E2 con la pantalla de C2 (`lienzo`, `edicion`): el lado (derecha/izquierda), el gráfico negado y el sustituto
impuesto (`GANCHOS_PANTALLA`, `revisar_sustituto_final`). Si `lienzo`/`validar` todavía no existen, el acomodo y la validación de
`construir_desde_ficha` quedan en identidad / sin errores (se detecta con importlib, así funciona solo cuando C2 llegue).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Callable

import regex  # \p{L} igual que en JS

from app.crm import agente
from app.crm import estructura as est
from app.crm import operaciones as op
from app.crm import plantillas
from app.crm import puntos as pt
from app.crm import registros
from app.crm import secciones_v as sv
from app.crm import toma
from app.crm import web
from app.crm.afirma import afirma_cambio, afirma_con
from app.crm import chat as agente_chat
from app.crm.chat import _capitaliza, _norm
from app.crm.regional import PAISES
from app.crm.valores import parse_numero

logger = logging.getLogger(__name__)

CONTACTOS, TAREAS = sv.CONTACTOS, sv.TAREAS
MAX_CONSULTAS = 6  # consultar_datos por mensaje (no cuentan como acciones: no cambian nada)
_SIN = object()

# ───────── Herramientas ─────────

# `deshacer` de `laboratorio/src/plantillas/edicion.js`, LITERAL.
HERR_DESHACER = {"type": "function", "function": {
    "name": "deshacer",
    "description": "Anula UN pedido anterior de la persona (ver pedidos_anteriores: qué dijo y qué cambió). El código revierte solo lo que ese "
                   "pedido cambió y conserva lo demás. Úsalo para \"eso no\", \"como estaba antes\", \"deshaz lo del color\", \"deshaz también X\". "
                   "Nunca lo uses sin que la persona lo pida.",
    "parameters": {"type": "object", "properties": {"pedido": {"type": "integer", "minimum": 1, "description": "número de pedidos_anteriores"}},
                   "required": ["pedido"]}}}

# Las de Carlos que hacen lo mismo que las de datos del laboratorio: no se muestran, pero si el modelo las llama van al mismo handler.
ALIAS_DE_DATOS = frozenset({"agregar_contactos", "cambiar_contacto", "eliminar_contacto", "agregar_registros", "cambiar_registro", "eliminar_registro"})
HERRAMIENTAS_CARLOS = [h for h in agente.HERRAMIENTAS if h["function"]["name"] not in ALIAS_DE_DATOS]
_BORRAR = frozenset({"borrar_registro", "eliminar_contacto", "eliminar_registro"})
_GUARDA_DATO = frozenset({"agregar_registro", "editar_registro", "agregar_contactos", "cambiar_contacto", "agregar_registros", "cambiar_registro"})

# Qué parte del CRM toca cada herramienta (para el deshacer selectivo y su cerco). Las del laboratorio, literal (chat.js), más las de
# Carlos que tocan lo mismo. Lo que no está aquí cuenta como «bloques», como en el laboratorio.
CATEGORIA: dict[str, str] = {
    **{n: "marca" for n in ("cambiar_marca", "usar_logo", "restablecer_marca")},
    **{n: "datos" for n in ("agregar_registro", "editar_registro", "borrar_registro")},
    **{n: "estructura" for n in ("crear_seccion", "agregar_campo", "renombrar_seccion", "quitar_seccion", "cambiar_ficha", "cambiar_tarjeta",
                                 "quitar_campo", "renombrar_campo", "cambiar_opciones_estado")},
    # De Carlos
    **{n: "datos" for n in (*ALIAS_DE_DATOS, "agregar_tarea", "cambiar_tarea", "mover_tarea", "eliminar_tarea")},
    **{n: "estructura" for n in ("definir_etapas", "mostrar_seccion", "definir_opciones", "mover_campo")},
}

INSTRUCCIONES_DISENO = """Datos, deshacer y diseño
- Sus DATOS: agregas, cambias, borras y consultas sus registros con agregar_registro, editar_registro, borrar_registro y consultar_datos, en cualquiera de las “secciones” del Estado (contactos, tareas y secciones propias).
- Si una herramienta devuelve ERROR, corrige y vuelve a intentar, o explica la verdad.
- Deshacer (pedidos_anteriores): cada pedido que cambió algo queda en la lista con lo que dijo la persona y qué cambió. Si quiere anular algo ("eso no", "como estaba antes", "deshaz lo del color", "deshaz también la dona"), usa deshacer con el número del PEDIDO que quiere anular (el código revierte solo lo que ese pedido cambió) y di qué deshiciste. Para deshacer SIEMPRE usa deshacer, no quites ni cambies bloques a mano. Si la lista está vacía, no hay nada que deshacer: dilo.
- Toma de diseño (estado.toma): si la persona pide diseñar o rehacer el inicio o un CRM completo, abre abrir_toma (no para cambios puntuales). Durante juntando/confirmando anota cada cosa concreta que pidan con anotar_bloque (qué ver + de qué parte; sin preguntar detalles técnicos) y el resto (objetivo, colores, letra, restricciones) con anotar_ficha, solo lo dicho en ESE mensaje; para cambiar un bloque de la ficha usa quitar_de_ficha + anotar_bloque; una pregunta por turno según instruccion_turno/FALTA. En confirmando muestra el RESUMEN y pregunta «¿Lo armo así?». No uses herramientas de pantalla hasta que el código confirme la ficha. Si charlan de otra cosa (digresión), contesta sin anotar ni cambiar la pantalla. cerrar_toma si abandonan."""

# chat.js, literales.
PROMESA = regex.compile(r"(?<!\p{L})(voy a|vamos a|procedo|creo una|agrego un|pongo un|armo una?)(?!\p{L})", regex.IGNORECASE)
MASIVO = re.compile(r"\btod[ao]s?\b|\bvarias\b|\btodo\b", re.IGNORECASE | re.ASCII)  # «borra todas»: se confirma ANTES de borrar el primero
SUSTITUTO = re.compile(r"m[aá]s parecid|en su lugar|como alternativa|no hay forma|no (se )?puedo hacer|no es posible|no se puede hacer"
                       r"|solo puedo (mostrar|hacer|poner)|no existe[^.]*\.[^?]*\bya (agregu|puse)", re.IGNORECASE)  # para el gancho de E2
ERROR_MASIVO_REGISTROS = ("ERROR: borrar varios registros de una vez necesita confirmación. No borres nada más: di cuáles se borrarían y pregunta "
                          "si está seguro (que responda \"sí\").")
NOMBRE_VISTA = toma.NOMBRE_VISTA
# Las frases de logro de Carlos con la regla de D51 para el subjuntivo: solo con tilde («registré» afirma, «que registre» no).
_LOGROS_D51 = [(re.compile(p.pattern.replace("[eé]", "é"), p.flags), h) for p, h in agente._LOGROS]
# El vocabulario de logro de Carlos (`agente._EXITO`) solo en las formas que AFIRMAN que Shifu lo hizo: «he agregado», «agregué». El
# participio suelto («tus contactos agregados», «la sección fue creada») también describe lo que ya había: no cuenta (D51).
_EXITO_D51 = re.compile(agente._EXITO.pattern.replace(r"\b(he |ya )?", r"\b(he|hemos|ya he|ya hemos)\s+", 1), agente._EXITO.flags)
MONTO_ABSURDO = 1_000_000_000  # como `Sesion._monto_absurdo` de Carlos: mil millones o más casi siempre es un error de dedo
# Las 12 tipografías de la marca (marca.js), por si `marca.py` de C2 todavía no está.
_FUENTES_MARCA = ["Inter", "Poppins", "Nunito", "Montserrat", "DM Sans", "Rubik", "Work Sans", "Lato", "Playfair Display", "Lora", "Merriweather", "Outfit"]


# ───────── Lo que pone C2 (lienzo, validar, marca): se usa si ya está ─────────

def _modulo(nombre: str) -> Any:
    """El módulo `app.crm.<nombre>` si existe; None si todavía no (o si no carga: se dice en el log y se sigue sin él)."""
    try:
        if importlib.util.find_spec(f"app.crm.{nombre}") is None:
            return None
        return importlib.import_module(f"app.crm.{nombre}")
    except Exception:
        logger.exception("No se pudo cargar app.crm.%s; el agente sigue sin él", nombre)
        return None


def _de_c2(atributo: str, modulos: tuple[str, ...] = ("lienzo", "validar")) -> Any:
    for m in modulos:
        f = getattr(_modulo(m), atributo, None)
        if f is not None:
            return f
    return None


def acomodar(bloques: list[dict]) -> list[dict]:
    """El acomodo automático del lienzo (`lienzo.acomodar`); sin lienzo, los bloques quedan como vienen."""
    f = _de_c2("acomodar")
    return f(bloques) if callable(f) else bloques


def revisar_vista(vista: str, opciones: dict, campos: list[dict], donde: str) -> list[str]:
    """Los errores de las opciones de una vista (`validar.revisar_vista`); sin validar, ninguno."""
    f = _de_c2("revisar_vista")
    return list(f(vista, opciones, campos, donde)) if callable(f) else []


def validar(doc: dict) -> list[str]:
    """Los errores del inicio que arma `construir_desde_ficha` (`validar.validar_plantilla` sobre las secciones del CRM).
    Solo cuentan los de los bloques del inicio: lo demás ya estaba antes de la ficha y no lo arregla rehacer el inicio."""
    f = _de_c2("validar_plantilla")
    if not callable(f):
        return []
    errores = f({"id": "crm", "nombre": "CRM", "secciones": sv.secciones_de(_visible(doc)), "inicio": doc.get("inicio") or []})
    return [e for e in errores if str(e).startswith("Inicio")]


def fuentes() -> list[str]:
    f = _de_c2("FUENTES", ("marca",))
    return list(f) if f else list(_FUENTES_MARCA)


def catalogo(doc: dict) -> toma.Catalogo:
    """Lo que la toma necesita del CRM: sus secciones (secciones_v), los gráficos posibles y la revisión de vistas."""
    return toma.Catalogo(secciones=sv.secciones_de(_visible(doc)), compatibles=plantillas.compatibles, opciones_por_defecto=plantillas.opciones_por_defecto,
                         revisar_vista=revisar_vista, graficos=plantillas.graficos(), fuentes=fuentes())


# ───────── Ayudas ─────────

def _visible(doc: dict) -> dict:
    """El CRM con contactos y tareas a la vista aunque estén ocultas: sus registros se pueden leer, y escribir en ellas las vuelve a
    mostrar (como `Sesion._revelar_la_vista` de Carlos: el menú crece con lo que la persona usa)."""
    ocultas = doc.get("ocultas") or []
    if not any(x in ocultas for x in (CONTACTOS, TAREAS)):
        return doc
    return {**doc, "ocultas": [x for x in ocultas if x not in (CONTACTOS, TAREAS)]}


def pais_de(doc: dict) -> str:
    """El país del negocio para los formatos (código de `regional.PAISES`); si no se sabe, Guatemala, como el laboratorio."""
    brief = doc.get("brief") or {}
    for p in (doc.get("pais"), brief.get("pais"), (brief.get("ubicacion") or {}).get("pais")):
        if isinstance(p, str) and p.strip():
            k = _norm(p)
            if k in PAISES:
                return k
            por_nombre = {_norm(v["nombre"]): c for c, v in PAISES.items()}
            if k in por_nombre:
                return por_nombre[k]
    return "gt"


def _sin_identicos(regs: list[dict]) -> list[dict]:
    """El primero de cada grupo de registros con los mismos valores."""
    vistos: list[dict] = []
    out = []
    for r in regs:
        if r["valores"] not in vistos:
            vistos.append(r["valores"])
            out.append(r)
    return out


def _toma_distinta(a: dict, b: dict) -> bool:
    return (a.get("toma") or toma.toma_vacia()) != (b.get("toma") or toma.toma_vacia())


def _js(v: Any) -> str:
    """`${v}` de JS para un número del modelo (3.0 → «3»)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "undefined" if v is None else str(v)


def etiqueta_cambio(c: dict) -> str | None:
    """Cada cambio dicho en simple (`etiquetaCambio` de edicion.js). None = no se muestra."""
    if "etiqueta" in c:
        return c["etiqueta"]
    a = c.get("args") or {}
    donde = f" en «{a['pestana']}»" if a.get("pestana") and a.get("pestana") != "inicio" else ""
    v = NOMBRE_VISTA.get(a.get("vista")) or ("gráfica" if a.get("vista") == "grafico" else "pieza")
    h = c.get("herramienta")
    fijas = {"quitar_bloque": "quitó una pieza", "mover_bloque": "movió una pieza", "cambiar_tamano": "cambió el tamaño de una pieza",
             "cambiar_rangos": "cambió los grupos de lo que vence", "cambiar_opciones_estado": "cambió las opciones de un estado",
             "cambiar_ficha": "cambió la ficha", "cambiar_tarjeta": "cambió las tarjetas del tablero", "cambiar_marca": "cambió colores o letra",
             "usar_logo": "puso tu logo", "restablecer_marca": "volvió al diseño base", "deshacer": "deshizo un pedido",
             "construir_desde_ficha": "armó tu inicio nuevo"}
    if h in fijas:
        return fijas[h]
    if h == "agregar_bloque":
        return f"agregó {'una pieza' if v == 'pieza' else f'«{v}»'}{donde}"
    if h == "cambiar_visual":
        return f"cambió una pieza a «{v}»"
    if h == "crear_seccion":  # el laboratorio la nombra con `titulo`; Carlos, con `nombre`
        return f"creó la pestaña «{a.get('titulo') or a.get('desde') or a.get('nombre') or 'nueva'}»"
    if h == "agregar_campo":
        return f"agregó el campo «{a.get('nombre')}»"
    if h == "quitar_campo":
        return f"quitó el campo «{a.get('campo')}»"
    if h == "renombrar_campo":
        return f"renombró un campo a «{a.get('nombre')}»"
    if h == "renombrar_seccion":
        return f"renombró una pestaña a «{a.get('titulo') or a.get('nombre')}»"
    if h == "quitar_seccion":
        return f"quitó la pestaña «{a.get('seccion')}»"
    return None  # navegar y anotar en la ficha no cambian la pantalla


def creado_sin_decir(doc_antes: dict, cambios: list[dict], respuesta: str = "") -> list[str]:
    """Estructura creada EN ESTE TURNO para poder guardar un dato (un campo o una opción nueva) que la respuesta no menciona
    (`creadoSinDecir` de edicion.js). Medido: «cambia a Ana a Congelada» creaba la opción y respondía solo «cambió a Congelada»."""
    if not any(c["herramienta"] in _GUARDA_DATO for c in cambios):
        return []
    creado: list[tuple[str, str]] = []
    for c in cambios:
        a = c.get("args") or {}
        if c["herramienta"] == "agregar_campo":
            creado.append(("el campo", a.get("nombre")))
        elif c["herramienta"] in ("cambiar_opciones_estado", "definir_opciones"):
            previas = _opciones_antes(doc_antes, a.get("seccion") or a.get("destino"), a.get("campo"))
            renombradas = set((a.get("renombrar") or {}).values()) if isinstance(a.get("renombrar"), dict) else set()
            creado += [("la opción", o) for o in (a.get("opciones") or []) if o not in previas and o not in renombradas]

    def dicho(nombre: Any) -> bool:
        return str(nombre).lower() in respuesta.lower() and bool(re.search(r"agregu|cre[eé]|nuev|añad", respuesta, re.IGNORECASE))

    return [f"{que} «{nombre}»" for que, nombre in creado if not dicho(nombre)]


def _opciones_antes(doc: dict, seccion: Any, campo: Any) -> list:
    s = agente.Sesion(doc, op.ahora_utc())
    campos, _, error = s._campos_de(str(seccion or ""))
    if error or campos is None:
        s2 = next((x for x in sv.secciones_de(_visible(doc)) if x["id"] == seccion), None)
        campos = s2["campos"] if s2 else []
    c = next((x for x in campos if x.get("id") == campo), None) or agente.Sesion._campo(campos, str(campo or ""))
    return list((c or {}).get("opciones") or [])


# ───────── Ganchos de la pantalla (los llena E2 con lienzo/edicion de C2) ─────────

def _gancho_lado(respuesta: str, sesion: "SesionDiseno") -> str | None:
    # TODO(E2): si dice «derecha»/«izquierda», algún bloque agregado o movido en este mensaje debe haber quedado ahí
    # (chat.js con `edicion.ubicarTodo`; aquí `lienzo.ubicar_todo`). Tras MAX_CORRECCIONES, el código agrega «Ojo: en realidad quedó…».
    return None


def _gancho_grafico_negado(respuesta: str, sesion: "SesionDiseno") -> str | None:
    # TODO(E2): «no hay / no se puede» nombrando un gráfico que SÍ está en graficos_posibles (describir_pantalla de C2).
    return None


def _gancho_sustituto(respuesta: str, sesion: "SesionDiseno") -> str | None:
    # TODO(E2): SUSTITUTO con agregar_bloque/cambiar_visual en `cambios`: el código vuelve al CRM del principio y pide preguntar.
    return None


GANCHOS_PANTALLA: list[Callable[[str, "SesionDiseno"], str | None]] = [_gancho_lado, _gancho_grafico_negado, _gancho_sustituto]


def revisar_sustituto_final(respuesta: str, sesion: "SesionDiseno") -> None:
    # TODO(E2): si tras las correcciones insiste en imponer un sustituto, deshacerlo sí o sí y rehacer la respuesta sin herramientas.
    return None


# ───────── La sesión ─────────

class SesionDiseno(agente.Sesion):
    """La `Sesion` de Carlos con lo del laboratorio: herramientas de datos, deshacer, toma y la traza del turno (cambios, fallos,
    intentos, consultas, avisos)."""

    diseno = True

    def __init__(self, doc: dict, ahora: datetime, texto: str = "", con_imagen: bool = False, historial: list[dict] | None = None,
                 puntos: list[dict] | None = None, digresion: bool = False, toma_entrada: bool = False):
        super().__init__(doc, ahora, texto, con_imagen)
        self.historial = historial or []
        self.puntos = sorted(puntos or [], key=lambda x: x["n"])
        self.digresion = digresion
        self.toma_entrada = toma_entrada  # ¿la ficha ya estaba abierta al llegar el mensaje?
        self.confirmado = bool(agente._AFIRMA.match(texto or ""))  # un «sí» suelto confirma (como `agregar_vendedor` de Carlos)
        # Lo que escribió la persona (este mensaje y los anteriores): un registro a cambiar o borrar debe ser uno que ELLA nombró.
        self.dichos = "\n".join([*(str(h.get("t", "")) for h in self.historial if h.get("de") == "yo"), texto or ""])
        self.hoy: date = op.hora_local(ahora).date()
        self.pais = pais_de(doc)
        self.cambios: list[dict] = []
        self.intentos: list[dict] = []
        self.consultas: list[dict] = []
        self.avisos: list[dict] = []
        self.deshecho: set[str] = set()   # categorías deshechas en este turno
        self.deshechos: set[int] = set()  # números de los puntos deshechos (la ruta los quita de crm_puntos)
        self.doc_tras_deshacer: dict | None = None
        self._etiqueta: Any = _SIN
        self._agregado: tuple[str, str] | None = None

    # --- lo que ve el modelo ---
    def herramientas(self) -> list[dict]:
        """Las de Carlos (sin las que ahora son alias), las de la toma según el estado, deshacer y las de datos del laboratorio."""
        return [*HERRAMIENTAS_CARLOS, *toma.herramientas_para(self.doc), HERR_DESHACER, *registros.HERRAMIENTAS_DATOS]

    def contexto(self) -> str:
        """El Estado del CRM de Carlos, más lo del laboratorio: las secciones con sus campos (ids para las herramientas de datos), los
        pedidos que se pueden deshacer y la ficha de diseño."""
        base = json.loads(agente.contexto_crm(self.doc, self.ahora))
        base["secciones"] = [{"id": s["id"], "titulo": s["titulo"], "campos": [{"id": c["id"], "nombre": c["nombre"], "tipo": c["tipo"],
                                                                               **({"opciones": c["opciones"]} if c.get("opciones") else {})} for c in s["campos"]]}
                             for s in sv.secciones_de(_visible(self.doc))]
        base["pedidos_anteriores"] = [{"pedido": p["n"], "dijo": p.get("antes_de"), "cambio": p.get("cambio") or ["bloques", "marca", "estructura"],
                                       "hora": p.get("hora")} for p in self.puntos]
        base["toma"] = toma.contexto_toma(self.doc, catalogo(self.doc))
        return json.dumps(base, ensure_ascii=False, default=str)

    def solo_toma(self) -> bool:
        t = self.doc.get("toma") or {}
        return bool(t.get("activa")) and t.get("fase") != "construida"

    # --- los cercos que usa agente.revisar_respuesta ---
    def revisar_pantalla(self, respuesta: str) -> str | None:
        for gancho in GANCHOS_PANTALLA:
            aviso = gancho(respuesta, self)
            if aviso:
                return aviso
        # Ficha: si pidió VARIAS cosas en este mensaje y anotó menos, el código le pide las que faltan.
        return toma.aviso_piezas_faltantes(self.doc, self.texto, sum(1 for c in self.cambios if c["herramienta"] == "anotar_bloque"))

    @staticmethod
    def promete(respuesta: str) -> bool:
        return bool(PROMESA.search(respuesta))

    def afirma_sin_cambios(self, respuesta: str) -> str | None:
        """chat.js: afirma un cambio y ninguna herramienta cambió nada. «Afirma» = el vocabulario del laboratorio (afirma_cambio) o el de
        Carlos (`_EXITO_D51`: «he agregado», «registré»…), las dos con la regla de D51."""
        if not self.cambios and (afirma_cambio(respuesta) or afirma_con(respuesta, _EXITO_D51)):
            fallaron = f" (fallaron: {' | '.join(self.fallos[-2:])})" if self.fallos else ""
            return f"[Aviso interno] Dices que hiciste un cambio, pero ninguna herramienta cambió la pantalla{fallaron}. Llama a la herramienta o di la verdad."
        return None

    def logro_sin_herramienta(self, respuesta: str) -> str | None:
        """Las frases de logro de Carlos (`agente._LOGROS`) con la regla de D51: «creé la sección y registré el cobro» con solo
        crear_seccion sigue siendo mentira aunque algo haya cambiado. Las de datos del laboratorio cuentan como las de Carlos."""
        for patron, herramientas in _LOGROS_D51:
            hechas = herramientas | ({"agregar_registro", "editar_registro"} if "crear_seccion" not in herramientas else set())
            if afirma_con(respuesta, patron) and not (hechas & self.hechas):
                return agente.AVISO_LOGRO
        return None

    # --- ejecución ---
    def ejecutar(self, nombre: str, args: dict) -> str:
        if not isinstance(args, dict):
            args = {}
        self.acciones += 1
        if self.acciones > agente.MAX_ACCIONES:
            resultado = "Se alcanzó el límite de acciones por mensaje. Dile al usuario que continúe en otro mensaje."
        else:
            resultado = self._cerco(nombre, args)
            if resultado is None:
                try:
                    resultado = self._correr(nombre, args)
                    self._revelar_la_vista()
                except op.ErrorCrm as e:
                    resultado = f"No se pudo: {e.mensaje}"
                except TypeError:
                    resultado = "Faltan datos o hay datos de más para esa herramienta."
        self._anotar(nombre, args, resultado)
        return resultado

    def _cerco(self, nombre: str, args: dict) -> str | None:
        """Lo que el código no deja pasar antes de ejecutar (chat.js). Devuelve el error o None."""
        cat = CATEGORIA.get(nombre, "bloques")
        if self.deshecho and cat not in self.deshecho:
            # Tras deshacer, en el mismo turno solo se acepta cambiar LO MISMO («eso no, mejor azul»): otra cosa sería compensar.
            return (f"ERROR: acabas de deshacer {' y '.join(sorted(self.deshecho))}; en este mensaje no cambies {cat} si la persona no lo pidió. "
                    "Responde qué deshiciste.")
        sin_piezas = toma.error_anotar_sin_piezas(nombre, self.toma_entrada, self.doc, self.texto)
        if sin_piezas:
            return sin_piezas
        if nombre in _BORRAR:
            if self._orden_de_borrar_viene_de_la_imagen():
                return self._ORDEN_DE_LA_IMAGEN
            ya = sum(1 for c in self.cambios if c["herramienta"] in _BORRAR)
            todos = nombre == "eliminar_registro" and bool(args.get("todos"))
            if (MASIVO.search(self.texto or "") or ya >= 2 or todos) and not self.confirmado:
                return ERROR_MASIVO_REGISTROS
        if nombre not in toma.NOMBRES_TOMA:  # las de la toma lo revisan ellas mismas
            return toma.bloqueo_en_toma(self.doc, nombre, self.digresion)
        return None

    def _correr(self, nombre: str, args: dict) -> str:
        if nombre in toma.NOMBRES_TOMA:
            r = toma.ejecutar_toma(self.doc, nombre, args, catalogo(self.doc), self.texto, self.digresion)
            if r["ok"] and _toma_distinta(self.doc, r["doc"]):
                self.doc = r["doc"]
            return r["resultado"]
        if nombre in registros.HERR_DATOS:
            return self._un_dato(nombre, args)
        funcion = getattr(self, f"_h_{nombre}", None)
        if funcion is None:
            return f"La herramienta {nombre} no existe."
        return funcion(**args)

    @staticmethod
    def es_fallo(resultado: str) -> bool:
        return resultado.startswith(("ERROR", *agente._PREFIJOS_DE_FALLO, "Esa orden de borrar"))

    def _anotar(self, nombre: str, args: dict, resultado: str) -> None:
        """Trazabilidad: lo que salió va a `cambios`; cada intento fallido, con su herramienta y argumentos, a `intentos` y `fallos`."""
        etiqueta, self._etiqueta = self._etiqueta, _SIN
        if self.es_fallo(resultado):
            self.fallos.append(resultado)
            self.intentos.append({"herramienta": nombre, "args": args, "resultado": resultado})
            return
        self.hechas.add(nombre)
        c = {"herramienta": nombre, "args": args, "resultado": resultado}
        if etiqueta is not _SIN:
            c["etiqueta"] = etiqueta
        self.cambios.append(c)

    # --- datos (registros.py + secciones_v) ---
    def _seccion_datos(self, q: Any) -> tuple[dict | None, str | None]:
        """La sección con registros a la que se refiere el modelo: por id, o por su nombre como lo entiende Carlos (`_seccion`)."""
        secs = sv.secciones_de(_visible(self.doc))
        k = str(q if q is not None else "").strip()
        s = next((x for x in secs if x["id"] == k), None)
        if s is None and k:
            sid = self._seccion(k)
            s = next((x for x in secs if x["id"] == sid), None) or next((x for x in secs if _norm(x["titulo"]) == _norm(k)), None)
        if s is None:
            # Literal de edicion.js (contextoDatos). Fuera del f-string: comillas iguales anidadas no compilan en Python 3.11.
            cuales = ", ".join(f"{x['id']} ({x['titulo']})" for x in secs)
            return None, f"ERROR: «{_js(q)}» no es una sección con registros. Secciones con registros: {cuales}."
        return s, None

    def _dato(self, nombre: str, args: dict) -> tuple[bool, str, Any]:
        """Una herramienta de datos: el código decide (`registros.ejecutar_dato`) y aquí se aplica. Devuelve (ok, texto, etiqueta)."""
        s, error = self._seccion_datos(args.get("seccion"))
        if error:
            return False, error, None
        absurdo = self._monto_absurdo_en(s["campos"], args.get("valores"))
        if absurdo:
            return False, absurdo, None
        regs = sv.registros_de(_visible(self.doc), s["id"])
        # Registros idénticos (mismos valores) no se pueden distinguir: se toma el primero y el siguiente mensaje se ocupa del otro
        # (regla medida de Carlos, `Sesion._registros`: antes se preguntaba «¿cuál?» sin salida).
        unicos = regs if nombre == "agregar_registro" else _sin_identicos(regs)
        r = registros.ejecutar_dato(nombre, s, s["campos"], unicos, args, hoy=self.hoy, pais=self.pais, confirmado=self.confirmado, dichos=self.dichos)
        if not r["ok"]:
            return False, r["resultado"], None
        texto = r["resultado"]
        if len(unicos) != len(regs):  # los números del texto son de TODOS los registros
            texto = re.sub(r" Quedan \d+\.$", f" Quedan {len(regs) - 1}.", texto)
        if r["operacion"]:
            self._aplicar(s["id"], r["operacion"])
        return True, texto, r["etiqueta"]

    def _monto_absurdo_en(self, campos: list[dict], valores: Any) -> str | None:
        """Un número de mil millones o más no se guarda hasta que la persona lo confirma (la regla 7 de Carlos, `_monto_absurdo`)."""
        if not isinstance(valores, dict) or agente._CONFIRMA.search(self.texto or ""):
            return None
        for k, v in valores.items():
            c = registros.campo_por_clave(campos, k)
            if c and c.get("tipo") in ("numero", "dinero"):
                n = parse_numero(v)
                if n is not None and abs(n) >= MONTO_ABSURDO:
                    return (f"No se pudo: El monto “{v}” en “{c['nombre']}” es exageradamente alto. NO lo guardes todavía: pregúntale UNA vez al "
                            "usuario, amable, si es correcto.")
        return None

    def _aplicar(self, sec_id: str, operacion: dict) -> None:
        """La operación que dijo `registros`, con `secciones_v`. Si la sección estaba oculta, se vuelve a mostrar (solo si se guardó)."""
        d = self.doc
        if sec_id in (d.get("ocultas") or []):
            d = est.seccion_mostrar(d, sec_id, self.ahora)
        tipo = operacion["tipo"]
        if tipo == "agregar":
            d, _ = sv.registro_agregar(d, sec_id, operacion["valores"], self.ahora, canal="Chat", id=operacion["id"])
            self._agregado = (sec_id, operacion["id"])
        elif tipo == "editar":
            d, _ = sv.registro_actualizar(d, sec_id, operacion["id"], operacion["cambios"], self.ahora)
        elif tipo == "borrar":
            d = sv.registro_eliminar(d, sec_id, operacion["id"], self.ahora)
        self.doc = d
        self.vista = sec_id

    def _en_orden(self, nuevos: list[tuple[str, str]]) -> None:
        """Los contactos nuevos entran primero, uno sobre otro: agregados de a uno quedarían al revés. Se ponen en el orden en que los
        dijo, como cuando agregar_contactos los creaba de una vez. (Los registros de una sección propia ya quedaban del más nuevo al
        más viejo con agregar_registros, y las tareas van al final: esos quedan como siempre.)"""
        ids = [rid for s, rid in nuevos if s == CONTACTOS]
        if len(ids) < 2:
            return
        por_id = {c["id"]: c for c in self.doc["contactos"]}
        self.doc = {**self.doc, "contactos": [por_id[i] for i in ids if i in por_id] + [c for c in self.doc["contactos"] if c["id"] not in ids]}

    def _un_dato(self, nombre: str, args: dict) -> str:
        ok, texto, etiqueta = self._dato(nombre, args)
        if ok:
            self._etiqueta = etiqueta
        return texto

    def _varios(self, alias: str, nombre: str, lista: list[dict]) -> str:
        """Un alias de Carlos con varios registros: una herramienta de datos por registro. Si alguno no se pudo, el texto lo dice (y
        queda en `intentos`); si ninguno se pudo, es un error."""
        hechos, errores, etiquetas, nuevos = [], [], [], []
        for a in lista[:agente.MAX_CONTACTOS_POR_LLAMADA]:
            self._agregado = None
            ok, texto, etiqueta = self._dato(nombre, a)
            (hechos if ok else errores).append(texto)
            if ok and etiqueta:
                etiquetas.append(etiqueta)
            if self._agregado:
                nuevos.append(self._agregado)
        self._en_orden(nuevos)
        if not hechos:
            return " ".join(errores) or "ERROR: no hay registros para agregar."
        if errores:
            self.intentos.append({"herramienta": alias, "args": {"registros": len(lista)}, "resultado": " ".join(errores)})
        self._etiqueta = ", ".join(etiquetas) or None
        return " ".join([*hechos, *errores])

    # --- alias de Carlos (contrato §8): mismos argumentos de siempre, mismo handler que las del laboratorio ---
    def _h_agregar_contactos(self, contactos: list | None = None, **_: Any) -> str:
        if not isinstance(contactos, list) or not contactos:
            return "No hay contactos para agregar."
        lista = []
        for c in contactos:
            c = c if isinstance(c, dict) else {}
            nombre = _capitaliza(str(c.get("nombre") or ""))[:agente_chat.MAX_NOMBRE]  # como siempre lo guardó agregar_contactos
            valores = {"nombre": nombre, **{k: c[k] for k in ("detalle", "etapa") if c.get(k)},
                       **(c["campos"] if isinstance(c.get("campos"), dict) else {})}
            lista.append({"seccion": CONTACTOS, "valores": valores})
        return self._varios("agregar_contactos", "agregar_registro", lista)

    def _h_cambiar_contacto(self, buscar: str = "", etapa: str | None = None, nombre: str | None = None, detalle: str | None = None,
                            canal: str | None = None, responsable: str | None = None, campos: dict | None = None, **_: Any) -> str:
        valores = {k: v for k, v in (("etapa", etapa), ("nombre", nombre), ("detalle", detalle), ("canal", canal), ("responsable", responsable)) if v}
        valores.update(campos if isinstance(campos, dict) else {})
        if not valores:
            return "No me dijeron qué cambiar."
        return self._un_dato("editar_registro", {"seccion": CONTACTOS, "registro": buscar, "valores": valores})

    def _h_eliminar_contacto(self, buscar: str = "", **_: Any) -> str:
        return self._un_dato("borrar_registro", {"seccion": CONTACTOS, "registro": buscar})

    def _h_agregar_registros(self, seccion: str = "", registros: list | None = None, **_: Any) -> str:
        if not isinstance(registros, list) or not registros:
            return "No hay registros para agregar."
        return self._varios("agregar_registros", "agregar_registro", [{"seccion": seccion, "valores": r if isinstance(r, dict) else {}} for r in registros])

    def _h_cambiar_registro(self, seccion: str = "", buscar: str = "", valores: dict | None = None, **_: Any) -> str:
        return self._un_dato("editar_registro", {"seccion": seccion, "registro": buscar, "valores": valores})

    def _h_eliminar_registro(self, seccion: str = "", buscar: str = "", todos: bool = False, **_: Any) -> str:
        if not todos:
            return self._un_dato("borrar_registro", {"seccion": seccion, "registro": buscar})
        # «Todos los de Carla», ya confirmado con un «sí» (sin él, el cerco pide confirmar antes): todos los que dicen ese texto.
        s, error = self._seccion_datos(seccion)
        if error:
            return error
        k = _norm(str(buscar or ""))
        ids = [r["id"] for r in sv.registros_de(_visible(self.doc), s["id"])
               if k and k in _norm(" ".join(str(v) for v in r["valores"].values() if v is not None))]
        if not ids:
            return f"ERROR: no encontré «{buscar}» en {s['titulo']}. Pregúntale cómo se llama exactamente."
        for rid in ids:
            self._aplicar(s["id"], {"tipo": "borrar", "id": rid})
        self._etiqueta = f"borró {len(ids)} registros de {s['titulo']}"
        return f"Borrados de {s['titulo']}: {len(ids)} registros que dicen «{buscar}». Se puede deshacer."

    # --- consultar y deshacer (no pasan por ejecutar: no son cambios de herramientas) ---
    def consultar(self, args: Any) -> str:
        """consultar_datos: el código filtra, cuenta y suma; no cambia nada (no es un cambio). Va a `consultas`, completo."""
        args = args if isinstance(args, dict) else {}
        if len(self.consultas) >= MAX_CONSULTAS:
            t = "ERROR: ya consultaste los datos varias veces en este mensaje. Responde con lo que ya tienes."
        else:
            s, error = self._seccion_datos(args.get("seccion"))
            t = error or registros.consultar(s, s["campos"], sv.registros_de(_visible(self.doc), s["id"]), args, hoy=self.hoy, pais=self.pais)
        self.consultas.append({"args": args, "resultado": t[:2500]})
        return t

    def deshacer(self, args: Any) -> str:
        """Deshacer selectivo, calculado por el código (`puntos.deshacer`): solo lo que ESE pedido cambió; si uno posterior tocó lo mismo,
        también se deshace y se dice."""
        args = args if isinstance(args, dict) else {}
        self.acciones += 1
        pedido = args.get("pedido")
        try:
            n = int(pedido) if pedido is not None and float(pedido).is_integer() else None
        except (TypeError, ValueError):
            n = None
        p = next((x for x in self.puntos if x["n"] == n), None)
        if p is None:
            if self.puntos:
                lista = ", ".join(f"{x['n']} «{x.get('antes_de')}»" for x in self.puntos)
                r0 = f"ERROR: no hay un pedido {_js(pedido)} para deshacer. Pedidos: {lista}."
            else:
                r0 = "ERROR: no hay nada que deshacer (la lista de pedidos está vacía). Díselo a la persona; no cambies nada."
            self.fallos.append(r0)
            return r0
        try:
            r = pt.deshacer(self.doc, self.puntos, n, self.ahora)
        except op.ErrorCrm as e:
            r0 = f"ERROR: {e.mensaje}"
            self.fallos.append(r0)
            return r0
        self.doc = self.doc_tras_deshacer = r["doc"]
        self.puntos = r["puntos"]
        self.deshechos.update(r["deshechos"])
        self.deshecho.update(p.get("cambio") or ["bloques", "marca", "estructura"])
        self.hechas.add("deshacer")
        self.cambios.append({"herramienta": "deshacer", "args": args, "resultado": r["texto"]})
        return f"{r['texto']}\nEstado actual: {self.contexto()}"

    # --- toma ---
    def senal_toma(self) -> str | None:
        """Tras las herramientas de una vuelta: la pista FALTA o RESUMEN (puede pasar la ficha a «confirmando»)."""
        if not (self.doc.get("toma") or {}).get("activa"):
            return None
        d, senal = toma.senal_toma_tras_vuelta(self.doc, catalogo(self.doc))
        if _toma_distinta(self.doc, d):
            self.doc = d
        return senal

    # --- la respuesta cuando el modelo no dio texto ---
    def respuesta_del_codigo(self, ultimos: list[str]) -> str:
        """Sin texto del modelo, el CÓDIGO cuenta lo que de verdad pasó (chat.js). Si solo corrieron herramientas de Carlos (sin
        etiqueta), se dice lo que respondieron, como hacía `agente.responder`."""
        hechos = [e for e in (etiqueta_cambio(c) for c in self.cambios) if e]
        fallo = re.split(r"(?<=\.)\s", re.sub(r"^ERROR:\s*", "", self.fallos[-1]))[0] if self.fallos else ""
        if hechos:
            return f"Esto es lo que cambió: {', '.join(hechos)}." + (f" No pude hacer todo lo que pediste: {fallo}" if fallo else "")
        if self.cambios:
            return " ".join(ultimos) or "Listo."
        return f"No pude hacer ese cambio: {fallo}" if fallo else "No pude hacer ese cambio."


def _respuesta_solo_deshacer(cambios: list[dict]) -> str:
    """Si lo único que pasó fue deshacer, la respuesta la escribe el CÓDIGO con lo que se deshizo de verdad (chat.js)."""
    partes = [re.sub(r" Lo demás quedó igual\.$", "", re.sub(r"^Deshecho el pedido \d+ ", "deshice ", c["resultado"])) for c in cambios]
    return f"Listo, {' '.join(partes)} Lo demás quedó igual. ¿Algo más?"


def _atar(modelo: Any, herramientas: list[dict], solo_responder: bool) -> Any:
    """El modelo con sus herramientas. Tras un deshacer solo, sin poder llamarlas (tool_choice «none»); el código además ignora
    cualquier llamada que llegue igual."""
    if solo_responder:
        try:
            return modelo.bind_tools(herramientas, tool_choice="none")
        except TypeError:
            pass
    return modelo.bind_tools(herramientas)


def _traza(sesion: SesionDiseno) -> dict:
    return {"cambios": sesion.cambios, "fallos": sesion.fallos, "intentos": sesion.intentos, "consultas": sesion.consultas, "avisos": sesion.avisos}


def _construir(doc: dict) -> dict:
    """«Sí» a la ficha: el CÓDIGO arma el inicio (sin llamar al modelo): rápido, completo y sin fallos a medias."""
    r = toma.construir_desde_ficha(doc, acomodar, validar, fuentes())
    salida: dict[str, Any] = {"respuesta": toma.respuesta_construida(r), "modo": "ia", "fallos": list(r["errores"]), "intentos": [], "consultas": [], "avisos": []}
    if r["errores"]:
        return {**salida, "doc": doc, "cambios": []}
    n = len(r["doc"].get("inicio") or [])
    return {**salida, "doc": r["doc"], "cambios": [{"herramienta": "construir_desde_ficha", "args": {}, "resultado": f"Inicio armado con {n} bloques."}]}


# ───────── Un mensaje completo ─────────

async def responder(doc: dict, texto: str, historial: list[dict] | None = None, ahora: datetime | None = None, con_captura: bool = False,
                    modelo: Any = None, buscador: Any = None, imagen: str | None = None, seccion: str | None = None, persona: str | None = None,
                    puntos: list[dict] | None = None) -> dict:
    """Como `agente.responder`, más `cambios`, `fallos`, `intentos`, `consultas` y `avisos` (forma del laboratorio). Si en el turno se
    deshizo algo, `deshacer` = {deshechos, puntos (los que quedan, con foto), base (el CRM justo tras el último deshacer: el punto del
    turno se mide desde ahí)}. Lanza excepción si el modelo falla: quien llama usa las reglas."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    buscador = buscador or web.buscar
    ahora = ahora or op.ahora_utc()
    historial = historial or []
    prep = toma.preparar_turno_toma(doc, texto or "")
    doc_turno = prep["doc"] if _toma_distinta(doc, prep["doc"]) else doc
    if prep["construir"]:
        return _construir(doc_turno)

    sesion = SesionDiseno(doc_turno, ahora, texto, bool(imagen), historial=historial, puntos=puntos, digresion=prep["digresion"],
                          toma_entrada=bool((doc.get("toma") or {}).get("activa")))
    doc_inicial = sesion.doc
    base = modelo or agente._modelo()
    mensajes = agente._mensajes(doc, texto, historial, ahora, con_captura, imagen, seccion, persona)
    sobre = f"\n\n{persona}" if persona else ""
    aviso_toma = "\n".join(x for x in (prep["aviso"], prep["digresion"] and toma.AVISO_DIGRESION) if x)
    del_codigo = f"\n\n[Aviso del código]\n{aviso_toma}" if aviso_toma else ""
    mensajes[0] = SystemMessage(content=f"{agente.INSTRUCCIONES}\n\n{INSTRUCCIONES_DISENO}{sobre}{del_codigo}\n\nEstado del CRM (JSON):\n{sesion.contexto()}")

    respuesta = ""
    ultimos: list[str] = []
    correcciones = busquedas = 0
    solo_responder = False
    for _ in range(agente.MAX_VUELTAS):
        ia = await _atar(base, sesion.herramientas(), solo_responder).ainvoke(mensajes)
        contenido = (ia.content if isinstance(ia.content, str) else "").strip()
        llamadas = [] if solo_responder else list(getattr(ia, "tool_calls", None) or [])
        if not llamadas:
            respuesta = contenido
            aviso = agente.revisar_respuesta(respuesta, sesion, doc_inicial) if correcciones < agente.MAX_CORRECCIONES else None
            if aviso:
                correcciones += 1
                sesion.avisos.append({"aviso": aviso[:300], "descartada": respuesta[:300]})
                # (sin las llamadas que haya intentado: tras un deshacer solo no se ejecutan y no deben quedar sin respuesta)
                mensajes.extend([AIMessage(content=respuesta) if solo_responder else ia, HumanMessage(content=aviso)])
                respuesta = ""
                continue
            break
        mensajes.append(ia)
        ultimos = []
        for ll in llamadas:
            nombre, args = ll.get("name", ""), ll.get("args") or {}
            if nombre == "buscar_en_internet":
                busquedas += 1
                if busquedas > agente.MAX_BUSQUEDAS:
                    resultado = "Ya hiciste las búsquedas permitidas para este mensaje. Responde con lo que tienes."
                else:
                    resultado = await buscador(str(args.get("consulta", "")))
            elif nombre == "consultar_datos":
                resultado = sesion.consultar(args)
            elif nombre == "deshacer":
                resultado = sesion.deshacer(args)
            else:
                resultado = sesion.ejecutar(nombre, args)
            ultimos.append(resultado)
            mensajes.append(ToolMessage(content=resultado, tool_call_id=ll.get("id") or nombre or "x"))
        # Tras un deshacer pedido solo (sin otra herramienta en esa vuelta) el turno se cierra: el modelo responde y no puede
        # «compensar» con más cambios (visto en 3 de 6 corridas reales: re-agregar, mover o quitar lo deshecho).
        if all(ll.get("name") == "deshacer" for ll in llamadas):
            solo_responder = True
        senal = sesion.senal_toma()
        if senal:
            mensajes.append(HumanMessage(content=f"[Aviso del código — toma de diseño]\n{senal}"))
    else:
        respuesta = " ".join(ultimos)  # el modelo no terminó: se le dice a la persona lo que sí se hizo

    revisar_sustituto_final(respuesta, sesion)
    respuesta = agente.limpiar_respuesta(respuesta)
    if not respuesta:
        respuesta = sesion.respuesta_del_codigo(ultimos)
    falta = creado_sin_decir(doc, sesion.cambios, respuesta)
    if falta:
        respuesta += f"\n\nPara guardarlo agregué {' y '.join(falta)}. Si no lo querías, dime «deshaz»."
    if sesion.cambios and all(c["herramienta"] == "deshacer" for c in sesion.cambios):
        respuesta = _respuesta_solo_deshacer(sesion.cambios)
    confirmando = toma.respuesta_confirmando(sesion.doc, catalogo(sesion.doc))
    if confirmando:
        respuesta = confirmando  # el resumen lo escribe el CÓDIGO desde la ficha real
    if (sesion.doc.get("toma") or {}).get("fase") == "construida" and any(c["herramienta"] in toma.HERRAMIENTAS_BLOQUEADAS_EN_TOMA for c in sesion.cambios):
        sesion.doc = {**sesion.doc, "toma": toma.toma_vacia()}
    if sesion.pendiente and "sí" not in respuesta.lower() and "si " not in respuesta.lower():
        respuesta += " Responde “sí” para confirmar."

    salida: dict[str, Any] = {"doc": sesion.doc, "respuesta": respuesta, "modo": "ia", **_traza(sesion)}
    if sesion.recuerdos:
        salida["recuerdos"] = sesion.recuerdos
    if sesion.vista:
        salida["vista"] = sesion.vista
    if sesion.pendiente:
        salida["pendiente"] = sesion.pendiente
    if sesion.deshechos:
        salida["deshacer"] = {"deshechos": sorted(sesion.deshechos), "puntos": sesion.puntos, "base": sesion.doc_tras_deshacer}
    return salida
