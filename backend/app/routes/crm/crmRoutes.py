"""
/api/v1/crm — El CRM de cada persona (contactos, tareas, secciones, automatizaciones) y su chat.

Todas las rutas están ligadas al usuario autenticado: nadie ve ni toca el CRM de otra persona. Cada ruta que cambia algo
devuelve el CRM completo y actualizado (forma documentada en API.md), así la pantalla solo lo reemplaza.
Errores: `{"mensaje": "..."}` con el código HTTP que corresponda.

Endpoints (relativos al prefijo):
  GET    ""                       — El CRM (404 si todavía no tiene uno)
  POST   ""                       — Crea el CRM a partir del cuestionario; la IA diseña etapas, campos y secciones (reemplaza el anterior)
  POST   /seguimiento             — Preguntas de seguimiento que la IA hace según el negocio (sin sesión, con límite)
  DELETE ""                       — Lo borra (para repetir el cuestionario)
  POST   /contactos               — Alta de uno o varios contactos
  PATCH  /contactos/{id}          — Cambia nombre, etapa, canal, responsable o detalle
  DELETE /contactos/{id}
  POST   /tareas                  — Nueva tarea (entra en "Por hacer")
  PATCH  /tareas/{id}             — La mueve de columna
  DELETE /tareas/{id}
  PUT    /automatizaciones/{id}   — Activa o apaga
  PUT    /secciones/{id}          — Renombra una sección (integrada o propia)
  POST   /listas/{id}/registros   — Agrega un registro a una sección propia (valores por id de campo)
  PATCH  /listas/{id}/registros/{rid}  — Cambia valores de un registro
  DELETE /listas/{id}/registros/{rid}
  POST   /chat                    — Mensaje para Shifu (texto y/o captura) -> respuesta + CRM actualizado
"""
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.limiter import limiter
from app.crm import agente
from app.crm import diseno
from app.crm import estructura as est
from app.crm import operaciones as op
from app.crm import repositorio as repo
from app.crm.chat import responder, sanear_pendiente
from app.crm.generador import generar
from app.crm.vista import vista_crm
from app.database import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGEN = 4_000_000  # caracteres del data URL (≈3 MB de imagen)
_IMAGEN_LEIBLE = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,", re.I)  # los formatos que lee el modelo (no SVG ni otros)
TEXTO_SOLO_CAPTURA = "Mira esta imagen: dime en una línea qué ves y haz lo más obvio con ella, o propón una acción concreta."


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
    que_vendes: Optional[str] = Field(None, max_length=200)
    seguimiento: list[Seguimiento] = Field(default_factory=list, max_length=4)  # preguntas que la IA hizo según el negocio, con sus respuestas
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


class FilaContacto(_Texto):
    n: str = Field(..., min_length=1, max_length=40)
    det: Optional[str] = Field(None, max_length=120)
    extra: Optional[dict[str, Any]] = None  # valores de los campos extra de los contactos, por id de campo


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


class RegistroValores(BaseModel):
    valores: dict[str, Any] = Field(..., max_length=est.MAX_CAMPOS)  # por id de campo


class TareaNueva(_Texto):
    t: str = Field(..., min_length=1, max_length=60)


class TareaMover(_Texto):
    columna: str = Field(..., max_length=20)


class AutomatizacionFijar(BaseModel):
    on: bool


class SeccionNombre(_Texto):
    nombre: str = Field(..., min_length=1, max_length=28)


class MensajePrevio(_Texto):
    de: str = Field(..., pattern="^(yo|shifu)$")
    t: str = Field(..., max_length=500)


class ContextoChat(_Texto):
    historial: list[MensajePrevio] = Field(default_factory=list, max_length=20)  # últimos mensajes, para entender "y también a Pedro"
    pendiente: Optional[dict[str, Any]] = None
    imagen: Optional[str] = Field(None, max_length=MAX_IMAGEN)
    seccion: Optional[str] = Field(None, max_length=40)


class ChatEntrada(_Texto):
    texto: str = Field("", max_length=300)
    contexto: Optional[ContextoChat] = None


# ───────── Ayudas ─────────

def _error(e: op.ErrorCrm) -> JSONResponse:
    return JSONResponse({"mensaje": e.mensaje}, status_code=e.estado)


async def _aplicar(request: Request, user: dict, cambiar, estado: int = 200):
    """Corre una operación sobre el CRM de la persona y devuelve el CRM actualizado."""
    try:
        doc = await repo.actualizar(request.app.state.db, user["id"], cambiar)
    except op.ErrorCrm as e:
        return _error(e)
    return JSONResponse(vista_crm(doc), status_code=estado)


# ───────── CRM ─────────

@router.get("")
async def obtener_crm(request: Request, user: dict = Depends(get_current_user)):
    doc = await repo.obtener(request.app.state.db, user["id"])
    if doc is None:
        return JSONResponse({"mensaje": "Todavía no tienes un CRM."}, status_code=404)
    return vista_crm(doc)


@router.post("", status_code=201)
async def crear_crm(request: Request, datos: CrearCrm, user: dict = Depends(get_current_user)):
    brief = datos.brief.model_dump(exclude_none=True)
    doc = await diseno.disenar(generar(user["id"], brief), brief)  # la IA arma la estructura a la medida; sin IA queda la plantilla base
    await repo.reemplazar(request.app.state.db, user["id"], doc)
    return JSONResponse(vista_crm(doc), status_code=201)


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


@router.delete("", status_code=204)
async def borrar_crm(request: Request, user: dict = Depends(get_current_user)):
    await repo.borrar(request.app.state.db, user["id"])
    return Response(status_code=204)


# ───────── Contactos ─────────

@router.post("/contactos", status_code=201)
async def crear_contactos(request: Request, datos: ContactosCrear, user: dict = Depends(get_current_user)):
    filas = [f.model_dump(exclude_none=True) for f in datos.filas]  # `extra` va por id de campo
    return await _aplicar(request, user, lambda d: op.contactos_crear(d, filas, datos.canal, datos.texto), 201)


@router.patch("/contactos/{contacto_id}")
async def actualizar_contacto(contacto_id: str, request: Request, datos: ContactoCambios, user: dict = Depends(get_current_user)):
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        return JSONResponse({"mensaje": "No hay nada que cambiar."}, status_code=422)
    return await _aplicar(request, user, lambda d: op.contactos_actualizar(d, contacto_id, cambios))


@router.delete("/contactos/{contacto_id}")
async def eliminar_contacto(contacto_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.contactos_eliminar(d, contacto_id))


# ───────── Registros de las secciones propias ─────────
# Crear, quitar o cambiar la estructura (secciones, campos, etapas) se hace por el chat: ahí la IA decide y confirma lo que borra.

@router.post("/listas/{lista_id}/registros", status_code=201)
async def crear_registro(lista_id: str, request: Request, datos: RegistroValores, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_agregar(d, lista_id, datos.valores), 201)


@router.patch("/listas/{lista_id}/registros/{registro_id}")
async def cambiar_registro(lista_id: str, registro_id: str, request: Request, datos: RegistroValores, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_actualizar(d, lista_id, registro_id, datos.valores))


@router.delete("/listas/{lista_id}/registros/{registro_id}")
async def eliminar_registro(lista_id: str, registro_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: est.registro_eliminar(d, lista_id, registro_id))


# ───────── Tareas ─────────

@router.post("/tareas", status_code=201)
async def crear_tarea(request: Request, datos: TareaNueva, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.tareas_crear(d, datos.t), 201)


@router.patch("/tareas/{tarea_id}")
async def mover_tarea(tarea_id: str, request: Request, datos: TareaMover, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.tareas_mover(d, tarea_id, datos.columna))


@router.delete("/tareas/{tarea_id}")
async def eliminar_tarea(tarea_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.tareas_eliminar(d, tarea_id))


# ───────── Automatizaciones y secciones ─────────

@router.put("/automatizaciones/{auto_id}")
async def fijar_automatizacion(auto_id: str, request: Request, datos: AutomatizacionFijar, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.automatizacion_fijar(d, auto_id, datos.on))


@router.put("/secciones/{seccion_id}")
async def renombrar_seccion(seccion_id: str, request: Request, datos: SeccionNombre, user: dict = Depends(get_current_user)):
    return await _aplicar(request, user, lambda d: op.seccion_renombrar(d, seccion_id, datos.nombre))


# ───────── Chat ─────────

async def _turno_de_chat(db, user_id: str, texto: str, pendiente: dict | None, historial: list[dict], con_captura: bool,
                         imagen: str | None = None, seccion: str | None = None):
    """Resuelve un mensaje del chat. Con IA si se puede (y no hay un borrado por confirmar); si no, con las reglas.
    El modelo trabaja sobre una copia: solo se guarda si nadie cambió el CRM mientras tanto (si cambió, se repite)."""
    for _ in range(3):
        doc = await repo.obtener(db, user_id)
        if doc is None:
            raise op.ErrorCrm(404, "Todavía no tienes un CRM. Responde el cuestionario para crearlo.")
        r = None
        if (texto or imagen) and not pendiente and agente.activo():
            # Con imagen se intenta verla; si el modelo no puede con ella (formato raro, demasiado grande) se reintenta solo con el texto.
            intentos = [{"imagen": imagen, "seccion": seccion}, {}] if imagen else [{}]
            for extra in intentos:
                try:
                    r = await agente.responder(doc, texto or TEXTO_SOLO_CAPTURA, historial, con_captura=con_captura, **extra)
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
        guardado = await repo.guardar_version(db, user_id, r["doc"], doc["version"])
        if guardado:
            return guardado, r
    raise op.ErrorCrm(409, "Tu CRM cambió mientras guardábamos. Inténtalo de nuevo.")


@router.post("/chat")
@limiter.limit("60/minute")
async def chat_crm(request: Request, datos: ChatEntrada, user: dict = Depends(get_current_user)):
    ctx = datos.contexto or ContextoChat()
    imagen = ctx.imagen if ctx.imagen and _IMAGEN_LEIBLE.match(ctx.imagen) else None
    if not datos.texto and not imagen:
        return JSONResponse({"mensaje": "Escribe algo o adjunta una captura."}, status_code=422)

    pendiente = sanear_pendiente(ctx.pendiente)
    historial = [m.model_dump() for m in ctx.historial]
    try:
        doc, resultado = await _turno_de_chat(request.app.state.db, user["id"], datos.texto, pendiente, historial, bool(imagen), imagen, ctx.seccion)
    except op.ErrorCrm as e:
        return _error(e)

    respuesta = resultado["respuesta"]
    if imagen and resultado.get("modo") != "ia":
        # Sin la IA (sin saldo, apagada, falló) no hay quien lea la imagen: se dice con sinceridad y se actúa con el texto.
        donde = f" de “{ctx.seccion}”" if ctx.seccion else ""
        respuesta = (f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes: me guío por lo que escribiste. {respuesta}" if datos.texto
                     else f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.")
    salida = {"respuesta": respuesta, "crm": vista_crm(doc), "modo": resultado.get("modo", "reglas")}
    for clave in ("vista", "pendiente"):
        if resultado.get(clave):
            salida[clave] = resultado[clave]
    return salida
