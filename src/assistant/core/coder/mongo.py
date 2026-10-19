"""Almacén de proyectos del codificador en la base de negocio (colecciones con prefijo coder_). Los índices se crean en
la primera escritura de cada colección: con CODER_ENABLED=0, o mientras nadie escriba, no aparece nada nuevo en la
base (leer una colección que no existe no la crea)."""
from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from assistant.core.coder.repo import Duplicate

# colección -> índices: (claves, único)
_indexes = {
    "coder_projects": [([("user_id", 1), ("project_id", 1)], True), ([("project_id", 1)], True),
                       ([("user_id", 1), ("actualizado", -1)], False)],
    "coder_files": [([("project_id", 1), ("ruta", 1), ("version", 1)], True), ([("project_id", 1), ("hash", 1)], False)],
    "coder_versions": [([("project_id", 1), ("version", 1)], True)],
    "coder_preview_tokens": [([("token_hash", 1)], True), ([("project_id", 1)], False)],
    "coder_uploads": [([("user_id", 1), ("upload_id", 1)], True)],
    "coder_assets.files": [([("metadata.project_id", 1)], False), ([("metadata.user_id", 1)], False)],
}
_ttl = ("coder_preview_tokens", "coder_uploads")  # Mongo los borra al caducar (además de comprobarlo al leer)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value


def _doc(d: dict | None) -> dict | None:
    return None if d is None else {k: _utc(v) for k, v in d.items() if k != "_id"}


class MongoCoderRepo:
    def __init__(self, db):
        self.db = db
        self.projects = db["coder_projects"]
        self.files = db["coder_files"]
        self.versions = db["coder_versions"]
        self.previews = db["coder_preview_tokens"]
        self.uploads = db["coder_uploads"]
        self.assets = gridfs.GridFSBucket(db, bucket_name="coder_assets")
        self.asset_files = db["coder_assets.files"]
        self._ready: set[str] = set()

    def _ensure(self, col) -> None:
        if col.name in self._ready:
            return
        for keys, unique in _indexes[col.name]:
            col.create_index(keys, unique=unique)
        if col.name in _ttl:
            col.create_index("expira", expireAfterSeconds=0)
        self._ready.add(col.name)

    def _insert(self, col, doc: dict) -> None:
        self._ensure(col)
        try:
            col.insert_one(dict(doc))
        except DuplicateKeyError as exc:
            raise Duplicate(str(exc)) from exc

    # proyectos
    def insert_project(self, doc):
        self._insert(self.projects, doc)

    def get_project(self, user_id, project_id):
        return _doc(self.projects.find_one({"user_id": user_id, "project_id": project_id}))

    def list_projects(self, user_id):
        return [_doc(d) for d in self.projects.find({"user_id": user_id}).sort("actualizado", -1)]

    def update_project(self, user_id, project_id, fields, if_version=None):
        query = {"user_id": user_id, "project_id": project_id}
        if if_version is not None:
            query["version_actual"] = if_version
        return self.projects.update_one(query, {"$set": dict(fields)}).matched_count == 1

    def delete_project(self, user_id, project_id):
        self.projects.delete_one({"user_id": user_id, "project_id": project_id})

    # filas de archivos
    def insert_file(self, doc):
        self._insert(self.files, doc)

    def get_file(self, project_id, ruta, version):
        return _doc(self.files.find_one({"project_id": project_id, "ruta": ruta, "version": version}))

    def file_rows(self, project_id):
        return [_doc(d) for d in self.files.find({"project_id": project_id}, {"contenido": 0})]

    def delete_file_rows(self, project_id, keys):
        if keys:
            self.files.delete_many({"project_id": project_id,
                                    "$or": [{"ruta": ruta, "version": version} for ruta, version in keys]})

    def delete_files(self, project_id):
        self.files.delete_many({"project_id": project_id})

    # versiones
    def insert_version(self, doc):
        self._insert(self.versions, doc)

    def get_version(self, project_id, version):
        return _doc(self.versions.find_one({"project_id": project_id, "version": version}))

    def list_versions(self, project_id, limit=0):
        cursor = self.versions.find({"project_id": project_id}).sort("version", -1)
        return [_doc(d) for d in (cursor.limit(limit) if limit else cursor)]

    def delete_version_docs(self, project_id, versions):
        if versions:
            self.versions.delete_many({"project_id": project_id, "version": {"$in": list(versions)}})

    def delete_versions(self, project_id):
        self.versions.delete_many({"project_id": project_id})

    # tokens de vista previa
    def insert_preview_token(self, doc):
        self._insert(self.previews, doc)

    def get_preview_token(self, token_hash):
        return _doc(self.previews.find_one({"token_hash": token_hash}))

    def delete_preview_tokens(self, project_id):
        self.previews.delete_many({"project_id": project_id})

    # recursos binarios (GridFS) y subidas pendientes
    def put_blob(self, meta, data):
        self._ensure(self.asset_files)
        return str(self.assets.upload_from_stream(meta.get("ruta", "asset"), bytes(data), metadata=dict(meta)))

    def get_blob(self, blob_id):
        try:
            return self.assets.open_download_stream(ObjectId(blob_id)).read()
        except (gridfs.errors.NoFile, InvalidId, TypeError):
            return None

    def delete_blobs(self, blob_ids):
        for blob_id in blob_ids:
            try:
                self.assets.delete(ObjectId(blob_id))
            except (gridfs.errors.NoFile, InvalidId, TypeError):
                pass

    def _delete_blobs_where(self, query):
        for doc in self.asset_files.find(query, {"_id": 1}):
            try:
                self.assets.delete(doc["_id"])
            except gridfs.errors.NoFile:
                pass

    def delete_project_blobs(self, project_id):
        self._delete_blobs_where({"metadata.project_id": project_id})

    def delete_user_blobs(self, user_id):
        self._delete_blobs_where({"metadata.user_id": user_id})

    def insert_upload(self, doc):
        self._insert(self.uploads, doc)

    def get_upload(self, user_id, upload_id):
        return _doc(self.uploads.find_one({"user_id": user_id, "upload_id": upload_id}))

    def list_uploads(self, user_id):
        return [_doc(d) for d in self.uploads.find({"user_id": user_id}).sort("creado", 1)]

    def delete_upload(self, user_id, upload_id):
        self.uploads.delete_one({"user_id": user_id, "upload_id": upload_id})

    def delete_user_uploads(self, user_id):
        self.uploads.delete_many({"user_id": user_id})
