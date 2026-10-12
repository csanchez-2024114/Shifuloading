"""/api/v1/files — archivos del usuario para adjuntar a un mensaje (ver app/services/file_store.py).

  POST   /            multipart, campo `file`  -> 201 {file_id, name, size, kind, content_type, created_at}
  GET    /            lista del usuario, lo mas nuevo primero
  GET    /{file_id}   descarga (solo el dueno; 404 si es de otro)
  DELETE /{file_id}

El chat recibe los `file_id` en `files`: {"text": "...", "files": ["<file_id>"]}.
"""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile

from app.database import get_current_user, get_db
from app.services import file_store

router = APIRouter()


def _uid(user: dict) -> str:
    return str(user.get("_id") or user.get("id", ""))


@router.post("/", status_code=201)
async def upload(file: UploadFile, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    data = await file.read(file_store.MAX_BYTES + 1)  # un byte de mas basta para saber que se paso, sin leerlo entero
    try:
        return await file_store.save(db, _uid(user), file.filename or "", data, file.content_type)
    except file_store.FileRejected as e:
        raise HTTPException(status_code=413 if len(data) > file_store.MAX_BYTES else 415, detail=str(e))


@router.get("/")
async def list_files(user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    return {"files": await file_store.list_files(db, _uid(user))}


@router.get("/{file_id}")
async def download(file_id: str, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    found = await file_store.read(db, _uid(user), file_id)
    if not found:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    meta, data = found
    # Siempre como descarga y sin adivinar el tipo: un archivo subido nunca se ejecuta en el origen de la app.
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(meta['name'])}", "X-Content-Type-Options": "nosniff"})


@router.delete("/{file_id}", status_code=204)
async def delete(file_id: str, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    if not await file_store.delete(db, _uid(user), file_id):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
