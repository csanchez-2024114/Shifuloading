from fastapi import APIRouter, Request, HTTPException, Query
from bson import json_util, ObjectId
import json

router = APIRouter()


# ── GET endpoints ─────────────────────────────────────────────────────────────


@router.get("/")
async def get_processes(
    request: Request,
    email: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    skip: int = Query(default=0),
    sort: str = Query(default="created_at"),
    order: str = Query(default="asc"),
):
    try:
        collection = request.app.state.db.procesos
        sort_direction = -1 if order == "desc" else 1
        query = {}
        if email:
            query["user_email"] = email
        total_count = await collection.count_documents(query)
        cursor = collection.find(query).sort(sort, sort_direction).skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        procesos = await cursor.to_list(length=limit or total_count or 0)
        if not procesos:
            return {
                "success": True,
                "message": f"No se encontraron procesos" + (f" para {email}" if email else ""),
                "data": {"email": email, "total": 0, "count": 0, "procesos": []},
            }
        procesos_json = json.loads(json_util.dumps(procesos))
        return {
            "success": True,
            "message": f"Procesos encontrados" + (f" para {email}" if email else ""),
            "data": {
                "email": email,
                "total": total_count,
                "count": len(procesos),
                "skip": skip,
                "limit": limit,
                "procesos": procesos_json,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener procesos: {str(e)}")


@router.get("/count")
async def count_processes(
    request: Request,
    email: str = Query(..., description="Email to count processes for"),
):
    try:
        collection = request.app.state.db.procesos
        count = await collection.count_documents({"user_email": email})
        return {"success": True, "data": {"email": email, "count": count}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al contar procesos: {str(e)}")


@router.get("/{process_id}")
async def get_process_by_id(process_id: str, request: Request):
    try:
        if not ObjectId.is_valid(process_id):
            raise HTTPException(status_code=400, detail="ID de proceso inválido")
        collection = request.app.state.db.procesos
        process = await collection.find_one({"_id": ObjectId(process_id)})
        if not process:
            raise HTTPException(
                status_code=404, detail=f"No se encontró el proceso con ID {process_id}"
            )
        proceso_json = json.loads(json_util.dumps(process))
        return {"success": True, "data": proceso_json}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener proceso: {str(e)}")


# ── DELETE endpoints ───────────────────────────────────────────────────────────


@router.delete("/{process_id}")
async def delete_process_by_id(process_id: str, request: Request):
    try:
        collection = request.app.state.db.procesos
        if not ObjectId.is_valid(process_id):
            raise HTTPException(status_code=400, detail="ID de proceso inválido")
        result = await collection.delete_one({"_id": ObjectId(process_id)})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404, detail=f"No se encontró el proceso con ID {process_id}"
            )
        return {
            "success": True,
            "message": "Proceso eliminado exitosamente",
            "data": {"process_id": process_id, "deleted_count": result.deleted_count},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el proceso: {str(e)}")


@router.delete("/")
async def delete_processes_by_query(
    request: Request,
    name: str | None = Query(default=None, description="Process name to delete by"),
    email: str | None = Query(default=None, description="Email to delete all processes for"),
):
    try:
        collection = request.app.state.db.procesos
        deleted_count = 0

        if name is not None:
            result = await collection.delete_many({"nombre_proceso": name})
            deleted_count = result.deleted_count
            if deleted_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No se encontraron procesos con el nombre '{name}'",
                )
            message = "Procesos eliminados exitosamente por nombre"
            data = {"nombre_proceso": name, "deleted_count": deleted_count}
        elif email is not None:
            result = await collection.delete_many({"user_email": email})
            deleted_count = result.deleted_count
            if deleted_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No se encontraron procesos para el correo {email}",
                )
            message = "Todos los procesos eliminados exitosamente por email"
            data = {"email": email, "deleted_count": deleted_count}
        else:
            raise HTTPException(
                status_code=400,
                detail="Debe proporcionar 'name' o 'email' como parámetro de consulta",
            )

        return {"success": True, "message": message, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar procesos: {str(e)}")