"""
/api/v1/crm — El CRM de cada persona (contactos, tareas, secciones, automatizaciones) y su chat.

Todas las rutas están ligadas al usuario autenticado: nadie ve ni toca el CRM de otra persona. Cada ruta que cambia algo
devuelve el CRM completo y actualizado (forma documentada en API.md), así la pantalla solo lo reemplaza.
Errores: `{"mensaje": "..."}` con el código HTTP que corresponda.

Endpoints (relativos al prefijo):
  GET    ""                       — El CRM (404 si todavía no tiene uno)
  POST   ""                       — Crea el CRM a partir del cuestionario; la IA diseña etapas, campos y secciones (reemplaza el anterior)
  POST   /seguimiento             — (antiguo) Preguntas de seguimiento que la IA hace según el negocio (sin sesión, con límite)
  POST   /siguiente-pregunta      — La siguiente pregunta del cuestionario, escrita por la IA según lo contestado (sin sesión, con límite)
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

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.limiter import limiter
from app.crm import agente
from app.crm import diseno
from app.crm import estructura as est
from app.crm import memoria as mem
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


class SiguienteEntrada(_Texto):
    """Lo contestado hasta ahora en el cuestionario: las 3 preguntas fijas y las que la IA ya hizo."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    nombre: str = Field("", max_length=60)
    ubicacion: Optional[Ubicacion] = None
    que_vendes: Optional[str] = Field(None, max_length=300)
    qa: list[Seguimiento] = Field(default_factory=list, max_length=6)


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
    texto: str = Field("", max_length=2000)
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


def _tiene_datos(doc: dict) -> bool:
    """¿La persona ya trabajó en este CRM? Contactos, registros o tareas suyas (las que crean las automatizaciones no cuentan)."""
    return bool(doc.get("total_contactos") or any(l["registros"] for l in doc.get("listas", []))
                or any(not t.get("auto") for col in doc.get("tareas", {}).values() for t in col))


@router.post("", status_code=201)
async def crear_crm(request: Request, datos: CrearCrm, user: dict = Depends(get_current_user)):
    existente = await repo.obtener(request.app.state.db, user["id"])
    if existente and _tiene_datos(existente):
        # Crear reemplaza el CRM: con datos de la persona adentro no se permite (un cuestionario viejo no debe borrarle su trabajo).
        return JSONResponse({"mensaje": "Ya tienes un CRM con información. Para rehacerlo usa «Repetir cuestionario» (eso borra el actual)."}, status_code=409)
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
    await mem.reiniciar_trabajo(request.app.state.db, user["id"])  # el CRM nuevo no arrastra la conversación del anterior; sí cómo le gusta que le hablen
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
                         imagen: str | None = None, seccion: str | None = None, persona: str | None = None):
    """Resuelve un mensaje del chat. Con IA si se puede (y no hay un borrado por confirmar); si no, con las reglas.
    El modelo trabaja sobre una copia: solo se guarda si nadie cambió el CRM mientras tanto (si cambió, se repite)."""
    for _ in range(3):
        doc = await repo.obtener(db, user_id)
        if doc is None:
            raise op.ErrorCrm(404, "Todavía no tienes un CRM. Responde el cuestionario para crearlo.")
        r = None
        if (texto or imagen) and not pendiente and agente.activo():
            # Con imagen se intenta verla; si el modelo no puede con ella (formato raro, demasiado grande) se reintenta solo con el texto.
            intentos = [{"imagen": imagen, "seccion": seccion, "persona": persona}, {"persona": persona}] if imagen else [{"persona": persona}]
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
async def chat_crm(request: Request, datos: ChatEntrada, segundo_plano: BackgroundTasks, user: dict = Depends(get_current_user)):
    ctx = datos.contexto or ContextoChat()
    db = request.app.state.db
    imagen = ctx.imagen if ctx.imagen and _IMAGEN_LEIBLE.match(ctx.imagen) else None
    if not datos.texto and not imagen:
        return JSONResponse({"mensaje": "Escribe algo o adjunta una captura."}, status_code=422)

    pendiente = sanear_pendiente(ctx.pendiente)
    if imagen:
        pendiente = None  # una captura es un tema nuevo: no se queda atada a un borrado por confirmar (nada se borra sin su “sí”)
    # El historial y lo que Shifu recuerda de la persona viven en el servidor; lo que mande la pantalla solo sirve si todavía no hay nada guardado.
    try:
        conv = await mem.obtener(db, user["id"])
    except Exception as e:  # la memoria nunca debe impedir que el chat conteste
        logger.warning("No se pudo leer la memoria de Shifu: %s", type(e).__name__)
        conv = None
    historial = mem.historial_para_modelo(conv) or [m.model_dump() for m in ctx.historial]
    persona = mem.bloque_persona(conv, user.get("name"), actual=datos.texto or None) if conv else None
    try:
        doc, resultado = await _turno_de_chat(db, user["id"], datos.texto, pendiente, historial, bool(imagen), imagen, ctx.seccion, persona)
    except op.ErrorCrm as e:
        return _error(e)

    respuesta = resultado["respuesta"]
    if imagen and resultado.get("modo") != "ia":
        # Sin la IA (sin saldo, apagada, falló) no hay quien lea la imagen: se dice con sinceridad y se actúa con el texto.
        donde = f" de “{ctx.seccion}”" if ctx.seccion else ""
        respuesta = (f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes: me guío por lo que escribiste. {respuesta}" if datos.texto
                     else f"📸 Recibí tu captura{donde}, pero ahora mismo no puedo leer imágenes. ¿Qué quieres que haga con eso? Por ejemplo: “agrega una tarea para revisar esto”.")
    try:
        _, toca = await mem.registrar_turno(db, user["id"], datos.texto or "(adjuntó una imagen)", respuesta, recuerdos=mem.sin_clientes(resultado.get("recuerdos"), [c["n"] for c in doc["contactos"]]))
        if toca and agente.activo():
            segundo_plano.add_task(mem.actualizar_memoria, db, user["id"])  # se pone al día lo que Shifu recuerda sin hacer esperar a la persona
    except Exception as e:
        logger.warning("No se pudo guardar el historial con Shifu: %s", type(e).__name__)
    salida = {"respuesta": respuesta, "crm": vista_crm(doc), "modo": resultado.get("modo", "reglas")}
    for clave in ("vista", "pendiente"):
        if resultado.get(clave):
            salida[clave] = resultado[clave]
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
