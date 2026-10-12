"""Archivos que sube el usuario (documentos e imagenes) para adjuntarlos a un mensaje.

Flujo de dos pasos: POST /api/v1/files devuelve un `file_id`; el chat recibe `files: [file_id]`. El chat nunca
recibe una URL del cliente: `document_analyzer` descarga lo que le digan, y una URL libre le dejaria pedir
direcciones internas del servidor. Todo se filtra por `user_id`.

Aqui vive la ficha (Mongo `user_files`: dueno, nombre, tamano, `storage`, `key`) y las reglas de entrada. Los bytes
los guarda el servicio elegido con FILE_STORAGE (`file_storage.py`: disco local hoy, Cloudinary cuando se quiera).
"""

import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.services import file_storage

COLLECTION = "user_files"
SCHEME = "shifu-file://"
MAX_BYTES = int(os.getenv("SHIFU_UPLOAD_MAX_MB", "10")) * 1024 * 1024
MAX_FILES_PER_USER = int(os.getenv("SHIFU_UPLOAD_MAX_FILES", "200"))
MAX_PER_TURN = 5
IMAGES = {"png", "jpg", "jpeg", "webp"}
# Lo que FileProvider.get_text_and_meta sabe leer. Sin zip: se expande descargando por URL.
ALLOWED = IMAGES | {"pdf", "docx", "xlsx", "xls", "pptx", "csv", "json", "txt", "md", "msg"}
# Primeros bytes de los formatos binarios: un .exe renombrado a .pdf no entra.
_MAGIC = {"pdf": (b"%PDF",), "png": (b"\x89PNG",), "jpg": (b"\xff\xd8",), "jpeg": (b"\xff\xd8",), "webp": (b"RIFF",),
          "docx": (b"PK",), "xlsx": (b"PK",), "pptx": (b"PK",), "xls": (b"\xd0\xcf\x11\xe0", b"PK"), "msg": (b"\xd0\xcf\x11\xe0",)}


class FileRejected(ValueError):
    """El archivo no se acepta; el mensaje es para el usuario."""


def ext_of(name: str) -> str:
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def _oid(file_id: str) -> ObjectId | None:
    try:
        return ObjectId(file_id)
    except (InvalidId, TypeError):
        return None


def _public(doc: dict) -> dict:
    return {"file_id": str(doc["_id"]), "name": doc["name"], "size": doc["size"], "kind": doc["kind"],
            "content_type": doc.get("content_type"), "created_at": doc["created_at"].isoformat()}


async def save(db, user_id: str, name: str, data: bytes, content_type: str | None = None) -> dict:
    name = os.path.basename((name or "archivo").replace("\\", "/"))[:200]
    ext = ext_of(name)
    if ext not in ALLOWED:
        raise FileRejected(f"Tipo de archivo no admitido (.{ext or '?'}). Admitidos: {', '.join(sorted(ALLOWED))}.")
    if not data:
        raise FileRejected("El archivo está vacío.")
    if len(data) > MAX_BYTES:
        raise FileRejected(f"El archivo pesa más de {MAX_BYTES // (1024 * 1024)} MB.")
    if ext in _MAGIC and not data.startswith(_MAGIC[ext]):
        raise FileRejected(f"El contenido no corresponde a un archivo .{ext}.")
    if await db[COLLECTION].count_documents({"user_id": user_id}) >= MAX_FILES_PER_USER:
        raise FileRejected(f"Llegaste al tope de {MAX_FILES_PER_USER} archivos. Borra alguno para subir más.")
    oid, storage = ObjectId(), file_storage.current()
    key = f"{user_id}/{oid}.{ext}"
    await file_storage.BACKENDS[storage].put(key, data)  # primero los bytes: una ficha sin archivo seria un adjunto roto
    doc = {"_id": oid, "user_id": user_id, "name": name, "size": len(data), "kind": "image" if ext in IMAGES else "document",
           "content_type": content_type, "created_at": datetime.now(timezone.utc), "storage": storage, "key": key}
    await db[COLLECTION].insert_one(doc)
    return _public(doc)


async def read(db, user_id: str, file_id: str) -> tuple[dict, bytes] | None:
    """(ficha, bytes) del archivo, o None si no existe o es de otro usuario. Se lee del servicio con que se subio."""
    oid = _oid(file_id)
    doc = await db[COLLECTION].find_one({"_id": oid, "user_id": user_id}) if oid else None
    return (_public(doc), await file_storage.BACKENDS[doc["storage"]].get(doc["key"])) if doc else None


async def list_files(db, user_id: str) -> list[dict]:
    cursor = db[COLLECTION].find({"user_id": user_id}).sort("created_at", -1).limit(MAX_FILES_PER_USER)
    return [_public(d) async for d in cursor]


async def delete(db, user_id: str, file_id: str) -> bool:
    oid = _oid(file_id)
    doc = await db[COLLECTION].find_one_and_delete({"_id": oid, "user_id": user_id}) if oid else None
    if doc:
        await file_storage.BACKENDS[doc["storage"]].delete(doc["key"])
    return bool(doc)


async def resources(db, user_id: str, file_ids) -> list[dict]:
    """Los `file_id` del mensaje convertidos en `turn_resources`. Los ajenos o inexistentes se descartan."""
    out = []
    for file_id in [str(f) for f in file_ids if f][:MAX_PER_TURN] if isinstance(file_ids, list) else []:
        oid = _oid(file_id)
        doc = await db[COLLECTION].find_one({"_id": oid, "user_id": user_id}) if oid else None
        if doc:
            out.append({"type": doc["kind"], "url": SCHEME + file_id, "title": doc["name"], "provider": "upload",
                        "file_id": file_id, "metadata": {"size": doc["size"]}})
    return out
