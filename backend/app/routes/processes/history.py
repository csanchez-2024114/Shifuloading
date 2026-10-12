"""
Process History V2 - Endpoints CRUD para la Interfaz Gráfica (Araña).
Provee datos estructurados, paginados y protegidos contra IDOR.
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.database import get_current_user
from app.models.processes.process_history_model_en import (
    ProcessHistoryCreateEN as ProcessHistoryCreate,
    ProcessHistoryUpdateEN as ProcessHistoryUpdate,
    ProcessHistoryResponseEN as ProcessHistoryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()
COLLECTION_NAME = "process_history"


def get_valid_object_id(id_str: str) -> ObjectId:
    """Valida y convierte un string a ObjectId de forma segura. Lanza 400 si es inválido."""
    if not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=400, detail=f"El formato del ID proporcionado es inválido: {id_str}"
        )
    return ObjectId(id_str)


def _map_step_to_dto(step: dict) -> dict:
    """
    [CRÍTICO] Adapter Pattern: Traduce un step plano guardado por LangGraph
    al DTO complejo exigido por el contrato del CTO (ProcessHistoryResponse).
    """
    return {
        "id": step.get("id") or str(ObjectId()),
        "title": step.get("title", "Paso del proceso"),
        "description": step.get("task", "Ejecutando acción automatizada"),
        "details": step.get("observation", "Sin detalles adicionales registrados."),
        "status": step.get("status", "completado"),
        "timestamp": step.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "subSteps": [],
        "image": "default.png",
        "appId": step.get("tool", "system"),
    }


def format_mongo_doc(doc: dict) -> dict:
    """Parsea el documento raíz de MongoDB al formato esperado por el ResponseModel."""
    if not doc:
        return {}
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    if "steps" in doc and isinstance(doc["steps"], list):
        doc["steps"] = [_map_step_to_dto(step) for step in doc["steps"]]
    return doc


@router.post("/", response_model=ProcessHistoryResponse, status_code=201)
async def create_process_history(
    request: Request,
    payload: ProcessHistoryCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Crea un nuevo historial de proceso.
    Fuerza el user_id a nivel de servidor (Prevención Anti-Spoofing).
    """
    try:
        user_id = str(current_user["id"])
        now = datetime.now(timezone.utc)
        doc = payload.model_dump()
        doc.update({"user_id": user_id, "created_at": now, "updated_at": now})
        db = request.app.state.db
        result = await db[COLLECTION_NAME].insert_one(doc)
        doc["_id"] = result.inserted_id
        return JSONResponse(status_code=201, content=jsonable_encoder(format_mongo_doc(doc)))
    except Exception as e:
        logger.error(
            f"Error creando process_history para el usuario {current_user.get('correo')}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Error interno al crear el historial de proceso.")


@router.get("/", response_model=dict)
async def list_process_histories(
    request: Request,
    session_id: Optional[str] = Query(None, description="Filtrar por sesión"),
    status: Optional[str] = Query(None, description="Filtrar por estado del proceso"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Resultados por página"),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista los procesos del usuario autenticado con paginación y filtros.
    Control de acceso estricto: Nadie puede ver los procesos de otro usuario.
    """
    try:
        db = request.app.state.db
        user_id = str(current_user["id"])
        query = {"user_id": user_id}
        if session_id:
            query["session_id"] = session_id
        if status:
            query["status"] = status
        skip = (page - 1) * limit
        cursor = db[COLLECTION_NAME].find(query).sort("created_at", -1).skip(skip).limit(limit)
        docs, total_count = await asyncio.gather(
            cursor.to_list(length=limit),
            db[COLLECTION_NAME].count_documents(query),
        )
        formatted_docs = [format_mongo_doc(doc) for doc in docs]
        response_data = {
            "data": formatted_docs,
            "meta": {
                "total": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit if limit > 0 else 0,
            },
        }
        return JSONResponse(status_code=200, content=jsonable_encoder(response_data))
    except Exception as e:
        logger.error(f"Error listando process_history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al obtener los historiales de procesos.")


@router.get("/{process_id}", response_model=ProcessHistoryResponse)
async def get_process_history(
    request: Request,
    process_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Obtiene el detalle completo de un proceso. Valida la propiedad del documento."""
    try:
        db = request.app.state.db
        obj_id = get_valid_object_id(process_id)
        user_id = str(current_user["id"])
        doc = await db[COLLECTION_NAME].find_one({"_id": obj_id, "user_id": user_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Proceso no encontrado o no autorizado.")
        return JSONResponse(status_code=200, content=jsonable_encoder(format_mongo_doc(doc)))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo process_id {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al consultar el proceso.")


@router.put("/{process_id}", response_model=ProcessHistoryResponse)
async def update_process_history(
    request: Request,
    process_id: str,
    payload: ProcessHistoryUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Actualiza un proceso o sus pasos de forma parcial."""
    try:
        db = request.app.state.db
        obj_id = get_valid_object_id(process_id)
        user_id = str(current_user["id"])
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No se enviaron datos válidos para actualizar.")
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await db[COLLECTION_NAME].find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_data},
            return_document=True,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Proceso no encontrado o no autorizado.")
        return JSONResponse(status_code=200, content=jsonable_encoder(format_mongo_doc(result)))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando process_id {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al actualizar el proceso.")


@router.delete("/{process_id}")
async def delete_process_history(
    request: Request,
    process_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Elimina un proceso de forma permanente."""
    try:
        db = request.app.state.db
        obj_id = get_valid_object_id(process_id)
        user_id = str(current_user["id"])
        result = await db[COLLECTION_NAME].delete_one({"_id": obj_id, "user_id": user_id})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404, detail="Proceso no encontrado o no autorizado para borrar."
            )
        return JSONResponse(
            status_code=200, content={"success": True, "message": "Proceso eliminado correctamente."}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error borrando process_id {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al eliminar el proceso.")
