"""Donde se guardan los bytes de los archivos del usuario. La ficha (dueno, nombre, tamano) vive en Mongo
(`file_store.py`); aqui solo hay tres operaciones por servicio: put, get y delete.

Cambiar de servicio = cambiar `FILE_STORAGE` en el `.env` (local | cloudinary) y reiniciar. Cada ficha guarda
con que servicio se subio, asi que los archivos viejos se siguen leyendo de donde estan.
Agregar un servicio (S3, GCS...) = una clase con put/get/delete y una linea en `BACKENDS`.

La `key` la arma el servidor (`<user_id>/<id>.<ext>`): nunca lleva nada escrito por el usuario.
"""

import asyncio
import io
import os
from pathlib import Path

import httpx

from config import Config


class LocalDisk:
    """Carpeta del servidor (`SHIFU_UPLOAD_DIR`, por defecto ./uploads, fuera de git)."""

    @staticmethod
    def _path(key: str) -> Path:
        return Path(os.getenv("SHIFU_UPLOAD_DIR", "uploads")) / key

    async def put(self, key: str, data: bytes) -> None:
        def write():
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(lambda: self._path(key).unlink(missing_ok=True))


class Cloudinary:
    """Cloudinary como archivo crudo y privado: los bytes vuelven identicos y la URL solo sirve firmada."""

    _OPTS = {"resource_type": "raw", "type": "authenticated"}

    @staticmethod
    def _sdk():
        import cloudinary
        import cloudinary.uploader
        import cloudinary.utils
        if not all([Config.CLOUDINARY_CLOUD_NAME, Config.CLOUDINARY_API_KEY, Config.CLOUDINARY_API_SECRET]):
            raise RuntimeError("FILE_STORAGE=cloudinary necesita CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET")
        cloudinary.config(cloud_name=Config.CLOUDINARY_CLOUD_NAME, api_key=Config.CLOUDINARY_API_KEY,
                          api_secret=Config.CLOUDINARY_API_SECRET, secure=True)
        return cloudinary

    @staticmethod
    def _id(key: str) -> str:
        return f"shifu_files/{key}"

    async def put(self, key: str, data: bytes) -> None:
        sdk = self._sdk()
        await asyncio.to_thread(sdk.uploader.upload, io.BytesIO(data), public_id=self._id(key), overwrite=False, **self._OPTS)

    async def get(self, key: str) -> bytes:
        url, _ = self._sdk().utils.cloudinary_url(self._id(key), sign_url=True, **self._OPTS)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    async def delete(self, key: str) -> None:
        sdk = self._sdk()
        await asyncio.to_thread(sdk.uploader.destroy, self._id(key), invalidate=True, **self._OPTS)


BACKENDS = {"local": LocalDisk(), "cloudinary": Cloudinary()}


def current() -> str:
    """El servicio para los archivos NUEVOS. Un nombre desconocido falla al subir, no en silencio."""
    name = os.getenv("FILE_STORAGE", "local").lower()
    if name not in BACKENDS:
        raise RuntimeError(f"FILE_STORAGE={name!r} no existe. Opciones: {', '.join(BACKENDS)}")
    return name
