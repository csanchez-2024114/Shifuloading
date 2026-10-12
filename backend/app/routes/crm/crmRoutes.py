"""
/api/v1/crm — El CRM de cada persona (contactos, tareas, secciones, automatizaciones) y su chat.

Todas las rutas están ligadas al usuario autenticado: nadie ve ni toca el CRM de otra persona. Cada ruta que cambia algo
devuelve el CRM completo y actualizado (forma documentada en API.md), así la pantalla solo lo reemplaza.
Errores: `{"mensaje": "..."}` con el código HTTP que corresponda.

Endpoints (relativos al prefijo):
  GET    ""                       — El CRM (404 si todavía no tiene uno)
  POST   ""                       — Crea el CRM a partir del cuestionario (reemplaza el anterior)
  DELETE ""                       — Lo borra (para repetir el cuestionario)
  POST   /contactos               — Alta de uno o varios contactos
  PATCH  /contactos/{id}          — Cambia nombre, etapa, canal, responsable o detalle
  DELETE /contactos/{id}
  POST   /tareas                  — Nueva tarea (entra en "Por hacer")
  PATCH  /tareas/{id}             — La mueve de columna
  DELETE /tareas/{id}
  PUT    /automatizaciones/{id}   — Activa o apaga
  PUT    /secciones/{id}          — Renombra una sección
  POST   /chat                    — Mensaje para Shifu (texto y/o captura) -> respuesta + CRM actualizado
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.limiter import limiter
from app.crm import operaciones as op
from app.crm import repositorio as repo
from app.crm.chat import responder, sanear_pendiente
from app.crm.generador import generar
from app.crm.vista import vista_crm
from app.database import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGEN = 4_000_000  # caracteres del data URL (≈3 MB de imagen)


# ───────── Entradas ─────────

class _Texto(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class Ubicacion(_Texto):
    pais: Optional[str] = Field(None, max_length=12)
    ciudad: Optional[str] = Field(None, max_length=60)


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


class FilaContacto(_Texto):
    n: str = Field(..., min_length=1, max_length=40)
    det: Optional[str] = Field(None, max_length=120)


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


class TareaNueva(_Texto):
    t: str = Field(..., min_length=1, max_length=60)


class TareaMover(_Texto):
    columna: str = Field(..., max_length=20)


class AutomatizacionFijar(BaseModel):
    on: bool


class SeccionNombre(_Texto):
    nombre: str = Field(..., min_length=1, max_length=28)


class ContextoChat(_Texto):
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
    doc = generar(user["id"], brief)
    await repo.reemplazar(request.app.state.db, user["id"], doc)
    return JSONResponse(vista_crm(doc), status_code=201)


@router.delete("", status_code=204)
async def borrar_crm(request: Request, user: dict = Depends(get_current_user)):
    await repo.borrar(request.app.state.db, user["id"])
    return Response(status_code=204)


# ───────── Contactos ─────────

@router.post("/contactos", status_code=201)
async def crear_contactos(request: Request, datos: ContactosCrear, user: dict = Depends(get_current_user)):
    filas = [f.model_dump(exclude_none=True) for f in datos.filas]
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

@router.post("/chat")
@limiter.limit("60/minute")
async def chat_crm(request: Request, datos: ChatEntrada, user: dict = Depends(get_current_user)):
    ctx = datos.contexto or ContextoChat()
    imagen = ctx.imagen if ctx.imagen and ctx.imagen.startswith("data:image/") else None
    if not datos.texto and not imagen:
        return JSONResponse({"mensaje": "Escribe algo o adjunta una captura."}, status_code=422)

    pendiente = sanear_pendiente(ctx.pendiente)
    resultado: dict = {}

    def cambiar(doc: dict) -> dict:
        resultado.update(responder(doc, datos.texto, pendiente) if datos.texto else {"doc": doc, "respuesta": ""})
        return resultado["doc"]

    try:
        doc = await repo.actualizar(request.app.state.db, user["id"], cambiar)
    except op.ErrorCrm as e:
        return _error(e)

    respuesta = resultado["respuesta"]
    if imagen:
        # La imagen todavía no se lee (falta conectar el modelo de visión): se acusa recibo y se actúa con el texto.
        donde = f" de “{ctx.seccion}”" if ctx.seccion else ""
        respuesta = (f"📸 Recibí tu captura{donde}. {respuesta}" if datos.texto
                     else f"📸 Recibí tu captura{donde}. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.")
    salida = {"respuesta": respuesta, "crm": vista_crm(doc)}
    for clave in ("vista", "pendiente"):
        if resultado.get(clave):
            salida[clave] = resultado[clave]
    return salida
