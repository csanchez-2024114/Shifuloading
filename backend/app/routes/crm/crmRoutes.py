"""
/api/v1/crm — El CRM de cada persona (contactos, tareas, secciones, automatizaciones) y su chat.

Todas las rutas están ligadas al usuario autenticado: nadie ve ni toca el CRM de otra persona. Cada ruta que cambia algo
devuelve el CRM completo y actualizado (forma documentada en API.md), así la pantalla solo lo reemplaza.
Errores: `{"mensaje": "..."}` con el código HTTP que corresponda.
Lo que se cambia a mano (estas rutas) deja un punto de deshacer, con `antes_de` = «A mano: …» (ver `app/crm/puntos.py`).

Endpoints (relativos al prefijo):
  GET    ""                       — El CRM (404 si todavía no tiene uno)
  POST   ""                       — Crea el CRM a partir del cuestionario; la IA diseña etapas, campos y secciones (reemplaza el anterior).
                                    Con CRM_DISENO=1 se siembra la plantilla del laboratorio que elige `asignar` (ver app/crm/sembrar.py)
  POST   /seguimiento             — (antiguo) Preguntas de seguimiento que la IA hace según el negocio (sin sesión, con límite)
  POST   /siguiente-pregunta      — La siguiente pregunta del cuestionario, escrita por la IA según lo contestado (sin sesión, con límite)
  DELETE ""                       — Lo borra (para repetir el cuestionario)
  POST   /contactos               — Alta de uno o varios contactos
  PATCH  /contactos/{id}          — Cambia nombre, etapa, canal, responsable o detalle
  DELETE /contactos/{id}
  POST   /tareas                  — Nueva tarea (entra en "Por hacer")
  PATCH  /tareas/{id}             — La mueve de columna o cambia su texto, fecha u hora
  DELETE /tareas/{id}
  PUT    /automatizaciones/{id}   — Activa o apaga
  PUT    /secciones/{id}          — Renombra una sección (integrada o propia)
  POST   /listas/{id}/registros   — Agrega un registro a una sección propia (valores por id de campo)
  PATCH  /listas/{id}/registros/{rid}  — Cambia valores de un registro
  DELETE /listas/{id}/registros/{rid}
  POST   /registros/ejemplos/quitar  — Quita los registros de ejemplo (los que sembró una plantilla); lo de la persona se queda
  GET    /puntos                  — Los puntos de deshacer (los últimos 30, sin foto)
  POST   /deshacer                — Deshace un punto ({n}; sin n, el último): solo lo que ese cambio tocó
  POST   /chat                    — Mensaje para Shifu (texto y/o captura) -> respuesta + CRM actualizado
"""
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.limiter import limiter
from app.crm import adjuntos
from app.crm import agente
from app.crm import diseno
from app.crm import estructura as est
from app.crm import memoria as mem
from app.crm import operaciones as op
from app.crm import puntos as pt
from app.crm import repositorio as repo
from app.crm import sembrar
from app.crm.chat import responder, sanear_pendiente
from app.crm.seleccion import nota_seleccion
from app.crm.generador import generar
from app.crm.vista import vista_crm
from app.database import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGEN = 4_000_000  # caracteres del data URL (≈3 MB de imagen)
_IMAGEN_LEIBLE = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,", re.I)  # los formatos que lee el modelo (no SVG ni otros)
TEXTO_SOLO_CAPTURA = "Mira esta imagen: dime en una línea qué ves y haz lo más obvio con ella, o propón una acción concreta."
TEXTO_SOLO_ARCHIVO = "Te mando este archivo: ¿qué hago con él?"
MAX_ADJUNTO = 7_000_000  # base64 de un archivo de hasta 5 MB


# ───────── Entradas ─────────

class _Texto(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class Ubicacion(_Texto):
    pais: Optional[str] = Field(None, max_length=12)
    ciudad: Optional[str] = Field(None, max_length=60)


class Seguimiento(_Texto):
    pregunta: str = Field(..., max_length=140)
    respuesta: str = Field(..., max_length=300)


class BriefEntrada(_Texto):
    """Respuestas del cuestionario. Lo desconocido se ignora; todo tiene tope de tamaño."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    nombre: str = Field("", max_length=60)
    ubicacion: Optional[Ubicacion] = None
    rubro: Optional[str] = Field(None, max_length=30)
    tiempo: Optional[str] = Field(None, max_length=30)
    canales: list[str] = Field(default_factory=list, max_length=20)
    cartera: Optional[str] = Field(None, max_length=30)
    ciclo: Optional[str] = Field(None, max_length=30)
    problemas: list[str] = Field(default_factory=list, max_length=20)
    equipo: Optional[str] = Field(None, max_length=30)
    herramientas: list[str] = Field(default_factory=list, max_length=20)
    objetivos: list[str] = Field(default_factory=list, max_length=20)
    dolor: Optional[str] = Field(None, max_length=300)
    que_vendes: Optional[str] = Field(None, max_length=300)
    seguimiento: list[Seguimiento] = Field(default_factory=list, max_length=6)  # preguntas que la IA hizo según el negocio, con sus respuestas
    armado: Optional[str] = Field(None, max_length=30)
    autonomia: Optional[str] = Field(None, max_length=30)
    presupuesto: Optional[str] = Field(None, max_length=30)

    @field_validator("canales", "problemas", "herramientas", "objetivos")
    @classmethod
    def _items_cortos(cls, v: list[str]) -> list[str]:
        if any(len(x) > 30 for x in v):
            raise ValueError("cada opción debe tener 30 caracteres o menos")
        return v


class CrearCrm(BaseModel):
    brief: BriefEntrada


class PedirSeguimiento(BaseModel):
    brief: BriefEntrada


class RespuestaIA(Seguimiento):
    abierta: bool = False  # la pregunta fue de texto libre


class SiguienteEntrada(_Texto):
    """Lo contestado hasta ahora en el cuestionario: las 3 preguntas fijas y las que la IA ya hizo."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    nombre: str = Field("", max_length=60)
    ubicacion: Optional[Ubicacion] = None
    que_vendes: Optional[str] = Field(None, max_length=300)
    qa: list[RespuestaIA] = Field(default_factory=list, max_length=6)


class FilaContacto(_Texto):
    n: str = Field(..., min_length=1, max_length=40)
    det: Optional[str] = Field(None, max_length=120)
    extra: Optional[dict[str, Any]] = None  # valores de los campos extra de los contactos, por id de campo
    canal: Optional[str] = Field(None, min_length=1, max_length=40)
    etapa: Optional[str] = Field(None, max_length=30)


class ContactosCrear(_Texto):
    filas: list[FilaContacto] = Field(..., min_length=1, max_length=300)
    canal: str = Field("Importado", min_length=1, max_length=40)
    texto: Optional[str] = Field(None, max_length=120)


class ContactoCambios(_Texto):
    n: Optional[str] = Field(None, min_length=1, max_length=40)
    det: Optional[str] = Field(None, max_length=120)
    canal: Optional[str] = Field(None, min_length=1, max_length=40)
    etapa: Optional[str] = Field(None, max_length=30)
    dueno: Optional[str] = Field(None, max_length=60)
    extra: Optional[dict[str, Any]] = None


class LoteImportacion(_Texto):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{6,40}$")
    nombre: str = Field("Importación", max_length=80)


class RegistrosLote(_Texto):
    """Filas para importar (de un Excel, por ejemplo): cada una va por id de campo. `lote` identifica la importación para poder quitarla entera."""
    filas: list[dict[str, Any]] = Field(..., min_length=1, max_length=300)
    lote: Optional[LoteImportacion] = None

    @field_validator("filas")
    @classmethod
    def _filas_sanas(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for fila in v:
            if len(fila) > est.MAX_CAMPOS or any(not isinstance(x, (str, int, float)) or isinstance(x, bool) or len(str(x)) > 200 for x in fila.values()):
                raise ValueError("cada fila debe tener valores de texto o número de hasta 200 caracteres")
        return v


class RegistroValores(BaseModel):
    valores: dict[str, Any] = Field(..., max_length=est.MAX_CAMPOS)  # por id de campo


class TareaNueva(_Texto):
    t: str = Field(..., min_length=1, max_length=60)
    vence: Optional[str] = Field(None, max_length=12)
    hora: Optional[str] = Field(None, max_length=8)


class TareaCambios(_Texto):
    columna: Optional[str] = Field(None, max_length=20)
    t: Optional[str] = Field(None, min_length=1, max_length=60)
    vence: Optional[str] = Field(None, max_length=12)  # "" le quita la fecha
    hora: Optional[str] = Field(None, max_length=8)


class AutomatizacionFijar(BaseModel):
    on: bool


class SeccionNombre(_Texto):
    nombre: str = Field(..., min_length=1, max_length=28)


class MensajePrevio(_Texto):
    de: str = Field(..., pattern="^(yo|shifu)$")
    t: str = Field(..., max_length=500)


class Adjunto(BaseModel):
    """Archivo en base64: no pasa por _Texto para no tocar el payload."""
    nombre: str = Field(..., max_length=120)
    datos: str = Field(..., max_length=MAX_ADJUNTO)


class PiezaElegida(_Texto):
    tipo: str = Field("", max_length=20)
    id: str = Field("", max_length=60)
    nombre: str = Field("", max_length=80)


class ContextoChat(_Texto):
    historial: list[MensajePrevio] = Field(default_factory=list, max_length=20)  # últimos mensajes, para entender "y también a Pedro"
    pendiente: Optional[dict[str, Any]] = None
    imagen: Optional[str] = Field(None, max_length=MAX_IMAGEN)
    archivo: Optional[Adjunto] = None
    seccion: Optional[str] = Field(None, max_length=40)
    seleccion: list[PiezaElegida] = Field(default_factory=list, max_length=12)


class QuitarEjemplos(_Texto):
    seccion: Optional[str] = Field(None, max_length=40)  # sin sección: de todas


class Deshacer(BaseModel):
    n: Optional[int] = Field(None, ge=1)  # sin n: el último


class ChatEntrada(_Texto):
    texto: str = Field("", max_length=2000)
    contexto: Optional[ContextoChat] = None


# ───────── Ayudas ─────────

def _error(e: op.ErrorCrm) -> JSONResponse:
    return JSONResponse({"mensaje": e.mensaje}, status_code=e.estado)


async def _vista(db, user_id: str, doc: dict) -> dict:
    """El CRM para la pantalla, con sus puntos de deshacer (si no se pueden leer, sale sin ellos: no impide nada)."""
    try:
        puntos = await repo.puntos_listar(db, user_id)
    except Exception as e:
        logger.warning("No se pudieron leer los puntos de deshacer: %s", type(e).__name__)
        puntos = None
    return vista_crm(doc, puntos=puntos)


async def _guardar_punto(db, user_id: str, punto: dict) -> None:
    try:
        await repo.puntos_agregar(db, user_id, punto)
    except Exception as e:  # el cambio ya se guardó: que no se pueda deshacer no lo echa atrás
        logger.warning("No se pudo guardar el punto de deshacer: %s", type(e).__name__)


async def _aplicar(request: Request, user: dict, cambiar, estado: int = 200, que=None, extra: dict | None = None):
    """Corre una operación sobre el CRM de la persona y devuelve el CRM actualizado.
    `que` (texto, o función del CRM de antes que lo da) describe el cambio: si cambió algo que se puede deshacer, queda un punto
    «A mano: <que>». `extra` se suma a la respuesta (lo llena `cambiar`)."""
    db = request.app.state.db
    punto: dict = {}

    def con_punto(d: dict) -> dict:
        nuevo = cambiar(d)
        if nuevo is d or que is None:
            return nuevo
        nuevo, p = pt.con_punto(d, nuevo, f"A mano: {que(d) if callable(que) else que}")
        punto.clear()
        punto.update(p or {})
        return nuevo

    try:
        doc = await repo.actualizar(db, user["id"], con_punto)
    except op.ErrorCrm as e:
        return _error(e)
    if punto:
        await _guardar_punto(db, user["id"], punto)
    return JSONResponse({**await _vista(db, user["id"], doc), **(extra or {})}, status_code=estado)


def _contacto(d: dict, contacto_id: str) -> str:
    return next((c["n"] for c in d["contactos"] if c["id"] == contacto_id), "un contacto")


def _seccion(d: dict, lista_id: str) -> str:
    return next((l["nombre"] for l in d["listas"] if l["id"] == lista_id), "una sección")


def _tarea(d: dict, tarea_id: str) -> str:
    return next((t["t"] for col in d["tareas"].values() for t in col if t["id"] == tarea_id), "una tarea")


# ───────── CRM ─────────

@router.get("")
async def obtener_crm(request: Request, user: dict = Depends(get_current_user)):
    doc = await repo.obtener(request.app.state.db, user["id"])
    if doc is None:
        return JSONResponse({"mensaje": "Todavía no tienes un CRM."}, status_code=404)
    return await _vista(request.app.state.db, user["id"], doc)


def _tiene_datos(doc: dict) -> bool:
    """¿La persona ya trabajó en este CRM? Contactos, registros o tareas suyas (las que crean las automatizaciones y los ejemplos
    que sembró una plantilla no cuentan)."""
    return bool((doc.get("total_contactos") or 0) > sum(1 for c in doc.get("contactos", []) if c.get("ejemplo"))
                or any(not r.get("ejemplo") for l in doc.get("listas", []) for r in l["registros"])
                or any(not t.get("auto") and not t.get("ejemplo") for col in doc.get("tareas", {}).values() for t in col))


@router.post("", status_code=201)
async def crear_crm(request: Request, datos: CrearCrm, user: dict = Depends(get_current_user)):
    existente = await repo.obtener(request.app.state.db, user["id"])
    if existente and _tiene_datos(existente):
        # Crear reemplaza el CRM: con datos de la persona adentro no se permite (un cuestionario viejo no debe borrarle su trabajo).
        return JSONResponse({"mensaje": "Ya tienes un CRM con información. Para rehacerlo usa «Repetir cuestionario» (eso borra el actual)."}, status_code=409)
    brief = datos.brief.model_dump(exclude_none=True)
    if sembrar.activo():
        # CRM_DISENO=1: la plantilla del laboratorio que elige `asignar`, sembrada con sus ejemplos; la IA solo ajusta nombres y campos.
        doc = await sembrar.crear_desde_cuestionario(user["id"], brief)
    else:
        doc = await diseno.disenar(generar(user["id"], brief), brief)  # la IA arma la estructura a la medida; sin IA queda la plantilla base
    doc = est.normalizar(doc)  # nace en el esquema 2 (inicio, marca, toma…), igual que lo verá la próxima lectura
    await repo.reemplazar(request.app.state.db, user["id"], doc)
    await _olvidar_puntos(request.app.state.db, user["id"])  # los del CRM anterior no sirven para este
    return JSONResponse(vista_crm(doc, puntos=[]), status_code=201)


async def _olvidar_puntos(db, user_id: str) -> None:
    try:
        await repo.puntos_borrar_desde(db, user_id, 0)
    except Exception as e:
        logger.warning("No se pudieron borrar los puntos de deshacer: %s", type(e).__name__)


@router.post("/seguimiento")
@limiter.limit("12/hour")
async def preguntas_de_seguimiento(request: Request, datos: PedirSeguimiento):
    """Preguntas que la IA hace según lo que la persona ya contó (el cuestionario ocurre antes de crear la cuenta, por eso no pide sesión:
    va limitada por IP y por tope diario)."""
    brief = datos.brief.model_dump(exclude_none=True)
    if not brief.get("rubro"):
        return JSONResponse({"mensaje": "Falta el tipo de negocio."}, status_code=422)
    preguntas, modo = await diseno.preguntas_de_seguimiento(brief)
    return {"preguntas": preguntas, "modo": modo}


@router.post("/siguiente-pregunta")
@limiter.limit("60/hour")
async def siguiente_pregunta(request: Request, datos: SiguienteEntrada):
    """La siguiente pregunta del cuestionario, escrita por la IA según lo ya contestado (sin sesión: el cuestionario va antes de crear la cuenta;
    limitada por IP y por tope diario). `modo: "base"` significa que la IA no está disponible y la pantalla sigue con las preguntas fijas."""
    if len(datos.nombre) < 2 or not (datos.que_vendes or "").strip():
        return JSONResponse({"mensaje": "Faltan el nombre del negocio y qué vendes."}, status_code=422)
    return await diseno.siguiente_pregunta(datos.model_dump(exclude_none=True))


@router.delete("", status_code=204)
async def borrar_crm(request: Request, user: dict = Depends(get_current_user)):
    await repo.borrar(request.app.state.db, user["id"])
    await _olvidar_puntos(request.app.state.db, user["id"])
    await mem.reiniciar_trabajo(request.app.state.db, user["id"])  # el CRM nuevo no arrastra la conversación del anterior; sí cómo le gusta que le hablen
    return Response(status_code=204)


# ───────── Contactos ─────────

@router.post("/contactos", status_code=201)
async def crear_contactos(request: Request, datos: ContactosCrear, user: dict = Depends(get_current_user)):
    filas = [f.model_dump(exclude_none=True) for f in datos.filas]  # `extra` va por id de campo
    que = f"agregó a {filas[0]['n']}" if len(filas) == 1 else f"agregó {len(filas)} contactos"
    return await _aplicar(request, user, lambda d: op.contactos_crear(d, filas, datos.canal, datos.texto), 201, que)


@router.patch("/contactos/{contacto_id}")
async def actualizar_contacto(contacto_id: str, request: Request, datos: ContactoCambios, user: dict = Depends(get_current_user)):
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        return JSONResponse({"mensaje": "No hay nada que cambiar."}, status_code=422)
    return await _aplicar(request, user, lambda d: op.contactos_actualizar(d, contacto_id, cambios), que=lambda d: f"editó a {_contacto(d, contacto_id)}")


@router.delete("/contactos/{contacto_id}")
async def eliminar_contacto(contacto_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.contactos_eliminar(d, contacto_id), que=lambda d: f"eliminó a {_contacto(d, contacto_id)}")


# ───────── Registros de las secciones propias ─────────
# Crear, quitar o cambiar la estructura (secciones, campos, etapas) se hace por el chat: ahí la IA decide y confirma lo que borra.

@router.post("/listas/{lista_id}/registros", status_code=201)
async def crear_registro(lista_id: str, request: Request, datos: RegistroValores, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_agregar(d, lista_id, datos.valores), 201, lambda d: f"agregó un registro a {_seccion(d, lista_id)}")


@router.post("/listas/{lista_id}/registros/lote", status_code=201)
async def crear_registros_lote(lista_id: str, request: Request, datos: RegistrosLote, user: dict = Depends(get_current_user)):
    """Importa varias filas a una sección. Responde el CRM actualizado y `importacion: { agregadas, omitidas }`."""
    resumen: dict[str, int] = {}

    def cambiar(d: dict) -> dict:
        nuevo, agregadas, omitidas = est.registros_agregar_lote(d, lista_id, datos.filas, lote=datos.lote.model_dump() if datos.lote else None)
        resumen.update(agregadas=agregadas, omitidas=omitidas)
        return nuevo

    return await _aplicar(request, user, cambiar, 201, lambda d: f"importó {len(datos.filas)} filas a {_seccion(d, lista_id)}", {"importacion": resumen})


@router.delete("/listas/{lista_id}/registros")
async def vaciar_lista(lista_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Borra TODOS los registros de una sección (la sección y sus campos se quedan). No se puede deshacer."""
    return await _aplicar(request, user, lambda d: est.registros_vaciar(d, lista_id), que=lambda d: f"vació {_seccion(d, lista_id)}")


@router.delete("/listas/{lista_id}/importaciones")
async def quitar_todas_las_importaciones(lista_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Quita TODO lo importado en una sección (lo escrito a mano se queda). No se puede deshacer."""
    return await _aplicar(request, user, lambda d: est.importaciones_quitar_todas(d, lista_id), que=lambda d: f"quitó lo importado en {_seccion(d, lista_id)}")


@router.delete("/listas/{lista_id}/importaciones/{lote_id}")
async def quitar_importacion(lista_id: str, lote_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Quita una importación entera (todos sus registros). No se puede deshacer."""
    return await _aplicar(request, user, lambda d: est.importacion_quitar(d, lista_id, lote_id), que=lambda d: f"quitó una importación de {_seccion(d, lista_id)}")


@router.patch("/listas/{lista_id}/registros/{registro_id}")
async def cambiar_registro(lista_id: str, registro_id: str, request: Request, datos: RegistroValores, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_actualizar(d, lista_id, registro_id, datos.valores), que=lambda d: f"editó un registro de {_seccion(d, lista_id)}")


@router.delete("/listas/{lista_id}/registros/{registro_id}")
async def eliminar_registro(lista_id: str, registro_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_eliminar(d, lista_id, registro_id), que=lambda d: f"eliminó un registro de {_seccion(d, lista_id)}")


# ───────── Tareas ─────────

@router.post("/tareas", status_code=201)
async def crear_tarea(request: Request, datos: TareaNueva, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.tareas_crear(d, datos.t, vence=datos.vence, hora=datos.hora), 201, f"agregó la tarea «{datos.t}»")


@router.patch("/tareas/{tarea_id}")
async def mover_tarea(tarea_id: str, request: Request, datos: TareaCambios, user: dict = Depends(get_current_user)):
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if "vence" in datos.model_fields_set and datos.vence is None:
        cambios["vence"] = ""
    if not cambios:
        return JSONResponse({"mensaje": "No hay nada que cambiar."}, status_code=422)

    def cambiar(d: dict) -> dict:
        campos = {k: v for k, v in cambios.items() if k in ("t", "vence", "hora")}
        if campos:
            d = op.tareas_actualizar(d, tarea_id, campos)
        if "columna" in cambios:
            d = op.tareas_mover(d, tarea_id, cambios["columna"])
        return d

    return await _aplicar(request, user, cambiar, que=lambda d: f"{'movió' if set(cambios) == {'columna'} else 'cambió'} la tarea «{_tarea(d, tarea_id)}»")


@router.delete("/tareas/{tarea_id}")
async def eliminar_tarea(tarea_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.tareas_eliminar(d, tarea_id), que=lambda d: f"eliminó la tarea «{_tarea(d, tarea_id)}»")


# ───────── Automatizaciones y secciones ─────────

@router.put("/automatizaciones/{auto_id}")
async def fijar_automatizacion(auto_id: str, request: Request, datos: AutomatizacionFijar, user: dict = Depends(get_current_user)):
    # Prender o apagar una automatización no es bloques, marca, estructura ni datos: no deja punto (con_punto no mide nada).
    return await _aplicar(request, user, lambda d: op.automatizacion_fijar(d, auto_id, datos.on), que=f"{'activó' if datos.on else 'apagó'} una automatización")


@router.put("/secciones/{seccion_id}")
async def renombrar_seccion(seccion_id: str, request: Request, datos: SeccionNombre, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.seccion_renombrar(d, seccion_id, datos.nombre), que=f"renombró una sección a «{datos.nombre}»")


@router.post("/registros/ejemplos/quitar")
async def quitar_ejemplos(request: Request, datos: Optional[QuitarEjemplos] = None, user: dict = Depends(get_current_user)):
    """Quita los registros de ejemplo (`ejemplo: true`) de todas las secciones o de una. Se puede deshacer."""
    seccion = datos.seccion if datos else None
    return await _aplicar(request, user, lambda d: est.ejemplos_quitar(d, seccion), que="quitó los ejemplos")


# ───────── Deshacer ─────────

@router.get("/puntos")
async def listar_puntos(request: Request, user: dict = Depends(get_current_user)):
    """Los puntos de deshacer, del más viejo al más nuevo: {n, antesDe, hora, cambio} (sin foto)."""
    from app.crm.vista import vista_puntos

    return {"puntos": vista_puntos(await repo.puntos_listar(request.app.state.db, user["id"]))}


@router.post("/deshacer")
async def deshacer(request: Request, datos: Optional[Deshacer] = None, user: dict = Depends(get_current_user)):
    """Deshace un punto (`n`; sin n, el último): solo lo que ese cambio tocó. Si uno posterior tocó lo mismo, se deshace también
    y se dice. Responde el CRM y `deshacer: {texto, deshechos}`."""
    db = request.app.state.db
    puntos = await repo.puntos_listar(db, user["id"], con_foto=True)
    n = datos.n if datos else None
    resultado: dict = {}

    def cambiar(d: dict) -> dict:
        r = pt.deshacer(d, puntos, n)
        resultado.clear()
        resultado.update(r)
        return r["doc"]

    try:
        doc = await repo.actualizar(db, user["id"], cambiar)
    except op.ErrorCrm as e:
        return _error(e)
    try:
        await repo.puntos_reponer(db, user["id"], min(resultado["deshechos"]), resultado["puntos"])
    except Exception as e:
        logger.warning("No se pudieron ajustar los puntos de deshacer: %s", type(e).__name__)
    return {**await _vista(db, user["id"], doc), "deshacer": {"texto": resultado["texto"], "deshechos": resultado["deshechos"]}}


# ───────── Chat ─────────

async def _turno_de_chat(db, user_id: str, texto: str, pendiente: dict | None, historial: list[dict], con_captura: bool,
                         imagen: str | None = None, seccion: str | None = None, persona: str | None = None, adjunto: str | None = None,
                         por_hacer: list[dict] | None = None):
    """Resuelve un mensaje del chat. Con IA si se puede (y no hay un borrado por confirmar); si no, con las reglas.
    El modelo trabaja sobre una copia: solo se guarda si nadie cambió el CRM mientras tanto (si cambió, se repite).
    Si el turno cambió algo que se puede deshacer, deja un punto con `antes_de` = lo que escribió la persona (como lo hecho a mano):
    sin él, deshacer un punto anterior podía pisar en silencio lo que el chat cambió después. Con CRM_DISENO=1 el agente recibe los
    puntos (`deshacer`); si deshizo alguno, aquí se quitan de `crm_puntos` y el punto del turno se mide desde lo que quedó."""
    diseno = agente.diseno_activo()
    for _ in range(3):
        doc = await repo.obtener(db, user_id)
        if doc is None:
            raise op.ErrorCrm(404, "Todavía no tienes un CRM. Responde el cuestionario para crearlo.")
        r = None
        if (texto or imagen) and not pendiente and agente.activo():
            # Con imagen se intenta verla; si el modelo no puede con ella (formato raro, demasiado grande) se reintenta solo con el texto.
            intentos = [{"imagen": imagen, "seccion": seccion, "persona": persona}, {"persona": persona, "seccion": seccion}] if imagen else [{"persona": persona, "seccion": seccion}]
            if adjunto:  # el archivo solo lo lee el modelo; las reglas (sin IA) nunca lo toman como órdenes
                intentos = [{**x, "adjunto": adjunto} for x in intentos]
            if diseno:
                puntos = await _puntos_con_foto(db, user_id)
                intentos = [{**x, "puntos": puntos, "por_hacer": por_hacer} for x in intentos]
            for extra in intentos:
                try:
                    r = await agente.responder(doc, texto or (TEXTO_SOLO_ARCHIVO if adjunto else TEXTO_SOLO_CAPTURA), historial, con_captura=con_captura, **extra)
                    break
                except Exception as e:  # sin saldo, tiempo agotado, clave inválida…: se sigue con las reglas
                    if extra is intentos[-1]:
                        agente.marcar_fallo(e)
                        logger.warning("El agente del CRM falló; se usan las reglas un rato: %s", type(e).__name__)
                    else:
                        logger.warning("El agente no pudo con la imagen; se reintenta solo con el texto: %s", type(e).__name__)
        if r is None:
            r = {**(responder(doc, texto, pendiente) if texto else {"doc": doc, "respuesta": ""}), "modo": "reglas"}
        if r["doc"] is doc:
            return doc, r
        deshecho = r.get("deshacer")
        nuevo, punto = pt.con_punto(deshecho["base"] if deshecho else doc, r["doc"], texto or "(adjuntó una imagen)")
        guardado = await repo.guardar_version(db, user_id, nuevo, doc["version"])
        if guardado:
            if deshecho:
                await _reponer_puntos(db, user_id, deshecho)
            if punto:
                await _guardar_punto(db, user_id, punto)
            return guardado, r
    raise op.ErrorCrm(409, "Tu CRM cambió mientras guardábamos. Inténtalo de nuevo.")


async def _puntos_con_foto(db, user_id: str) -> list[dict]:
    try:
        return await repo.puntos_listar(db, user_id, con_foto=True)
    except Exception as e:  # sin puntos el chat igual contesta: solo no habrá qué deshacer
        logger.warning("No se pudieron leer los puntos de deshacer: %s", type(e).__name__)
        return []


async def _reponer_puntos(db, user_id: str, deshecho: dict) -> None:
    try:
        await repo.puntos_reponer(db, user_id, min(deshecho["deshechos"]), deshecho["puntos"])
    except Exception as e:
        logger.warning("No se pudieron ajustar los puntos de deshacer: %s", type(e).__name__)


async def _salida_sin_turno(db, user_id: str, doc: dict, respuesta: str) -> dict:
    """Respuesta de chat sin tocar el CRM ni llamar al modelo (p. ej. adjunto ilegible)."""
    diseno = agente.diseno_activo()
    crm = await _vista(db, user_id, doc) if diseno else vista_crm(doc)
    salida = {"respuesta": respuesta, "crm": crm, "modo": "ia" if agente.activo() else "reglas"}
    if diseno:
        for clave in ("cambios", "fallos", "intentos", "consultas", "avisos"):
            salida[clave] = []
    return salida


@router.post("/chat")
@limiter.limit("60/minute")
async def chat_crm(request: Request, datos: ChatEntrada, segundo_plano: BackgroundTasks, user: dict = Depends(get_current_user)):
    ctx = datos.contexto or ContextoChat()
    db = request.app.state.db
    imagen = ctx.imagen if ctx.imagen and _IMAGEN_LEIBLE.match(ctx.imagen) else None
    adj_leido: dict | None = None
    if ctx.archivo:
        adj_leido = adjuntos.leer_adjunto(ctx.archivo.nombre, ctx.archivo.datos)
        if not adj_leido.get("ok"):
            doc = await repo.obtener(db, user["id"])
            if doc is None:
                return _error(op.ErrorCrm(404, "Todavía no tienes un CRM. Responde el cuestionario para crearlo."))
            return await _salida_sin_turno(db, user["id"], doc, adj_leido["error"])
    if not datos.texto and not imagen and not ctx.archivo:
        return JSONResponse({"mensaje": "Escribe algo o adjunta una captura o un archivo."}, status_code=422)

    pendiente = sanear_pendiente(ctx.pendiente)
    if imagen or ctx.archivo:
        pendiente = None  # captura o documento: tema nuevo, sin borrado pendiente
    bloque_adjunto = adjuntos.para_el_modelo(adj_leido) if adj_leido and adj_leido.get("ok") else None
    nota_sel = nota_seleccion([p.model_dump() for p in ctx.seleccion])
    # Archivo y selección van al modelo por el mismo canal que `adjunto` en el agente (no en el texto de la persona).
    extra_modelo = "\n".join(x for x in (nota_sel, bloque_adjunto) if x) or None
    # El historial y lo que Shifu recuerda de la persona viven en el servidor; lo que mande la pantalla solo sirve si todavía no hay nada guardado.
    try:
        conv = await mem.obtener(db, user["id"])
    except Exception as e:  # la memoria nunca debe impedir que el chat conteste
        logger.warning("No se pudo leer la memoria de Shifu: %s", type(e).__name__)
        conv = None
    # Al modelo: lo que sabe de la persona, el resumen de lo que ya no cabe en los 16 mensajes, y esos 16 completos.
    historial = mem.historial_para_modelo(conv) or [m.model_dump() for m in ctx.historial]
    persona = "\n\n".join(x for x in (mem.bloque_persona(conv, user.get("name"), actual=datos.texto or None), mem.bloque_resumen(conv)) if x) or None if conv else None
    try:
        doc, resultado = await _turno_de_chat(db, user["id"], datos.texto, pendiente, historial, bool(imagen), imagen, ctx.seccion, persona, extra_modelo,
                                              por_hacer=(conv or {}).get("por_hacer"))
    except op.ErrorCrm as e:
        return _error(e)

    respuesta = resultado["respuesta"]
    if imagen and resultado.get("modo") != "ia":
        # Sin la IA (sin saldo, apagada, falló) no hay quien lea la imagen: se dice con sinceridad y se actúa con el texto.
        donde = f" de “{ctx.seccion}”" if ctx.seccion else ""
        respuesta = (f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes: me guío por lo que escribiste. {respuesta}" if datos.texto
                     else f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.")
    if bloque_adjunto and resultado.get("modo") != "ia":
        respuesta = f"📎 Recibí «{ctx.archivo.nombre}», pero ahora mismo no puedo leer archivos." + (f" {respuesta}" if datos.texto and respuesta else " Inténtalo en un rato.")
    texto_memoria = datos.texto or ("(adjuntó una imagen)" if imagen else "")
    if adj_leido and adj_leido.get("ok"):
        texto_memoria = (f"{datos.texto} 📎 {ctx.archivo.nombre}".strip() if datos.texto else f"📎 {ctx.archivo.nombre}")
    try:
        _, toca = await mem.registrar_turno(db, user["id"], texto_memoria or "(adjuntó un archivo)", respuesta, recuerdos=mem.sin_clientes(resultado.get("recuerdos"), [c["n"] for c in doc["contactos"]]),
                                            por_hacer=resultado.get("por_hacer") if "por_hacer" in resultado else None)  # sin IA, lo pendiente sigue igual
        if toca and agente.activo():
            segundo_plano.add_task(mem.actualizar_memoria, db, user["id"])  # se pone al día lo que Shifu recuerda sin hacer esperar a la persona
    except Exception as e:
        logger.warning("No se pudo guardar el historial con Shifu: %s", type(e).__name__)
    diseno = agente.diseno_activo()
    crm = await _vista(db, user["id"], doc) if diseno else vista_crm(doc)  # con el sistema de diseño, también los puntos de deshacer
    salida = {"respuesta": respuesta, "crm": crm, "modo": resultado.get("modo", "reglas")}
    for clave in ("vista", "pendiente"):
        if resultado.get(clave):
            salida[clave] = resultado[clave]
    if diseno:  # la traza del turno, con la forma del laboratorio (las reglas no llaman herramientas: listas vacías)
        for clave in ("cambios", "fallos", "intentos", "consultas", "avisos"):
            salida[clave] = resultado.get(clave) or []
    return salida


# ───────── Historial y memoria ─────────

@router.get("/chat/historial")
async def historial_chat(request: Request, user: dict = Depends(get_current_user)):
    """La conversación guardada (para que el chat siga donde se quedó) y, si hace rato que no hablan, un saludo que retoma lo último."""
    conv = await mem.obtener(request.app.state.db, user["id"])
    return {"mensajes": [{"de": m["de"], "t": m["t"]} for m in conv.get("mensajes", [])[-60:]], "saludo": mem.saludo_de_regreso(conv, user.get("name"))}


@router.get("/memoria")
async def memoria_de_shifu(request: Request, user: dict = Depends(get_current_user)):
    """Lo que Shifu recuerda de la persona, a la vista (nada escondido)."""
    conv = await mem.obtener(request.app.state.db, user["id"])
    memoria = conv.get("memoria") or {}
    persona = [m["t"] for m in conv.get("mensajes", []) if m.get("de") == "yo"]
    return {"estilo": mem.estilo_final(memoria, persona), "hechos": memoria.get("hechos") or [], "trabajo": memoria.get("trabajo") or ""}


@router.delete("/chat", status_code=204)
async def olvidar_chat(request: Request, user: dict = Depends(get_current_user)):
    """Borra el historial y todo lo que Shifu recuerda de la persona."""
    await mem.borrar(request.app.state.db, user["id"])
    return Response(status_code=204)
