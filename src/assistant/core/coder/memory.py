"""Almacén de proyectos en memoria, para tests. Copia los documentos al entrar y al salir (como una base de datos) y
respeta las mismas claves únicas que los índices de Mongo."""
import copy
import threading

from assistant.core.coder.repo import Duplicate


class MemoryCoderRepo:
    def __init__(self):
        self._lock = threading.Lock()
        self.projects: dict[tuple[str, str], dict] = {}
        self.files: dict[tuple[str, str, int], dict] = {}
        self.versions: dict[tuple[str, int], dict] = {}
        self.previews: dict[str, dict] = {}

    # proyectos
    def insert_project(self, doc):
        with self._lock:
            key = (doc["user_id"], doc["project_id"])
            if any(pid == doc["project_id"] for _, pid in self.projects):  # project_id único entre usuarios
                raise Duplicate(key)
            self.projects[key] = copy.deepcopy(doc)

    def get_project(self, user_id, project_id):
        return copy.deepcopy(self.projects.get((user_id, project_id)))

    def list_projects(self, user_id):
        rows = [copy.deepcopy(p) for (u, _), p in self.projects.items() if u == user_id]
        return sorted(rows, key=lambda p: p["actualizado"], reverse=True)

    def update_project(self, user_id, project_id, fields, if_version=None):
        with self._lock:
            doc = self.projects.get((user_id, project_id))
            if doc is None or (if_version is not None and doc["version_actual"] != if_version):
                return False
            doc.update(copy.deepcopy(fields))
            return True

    def delete_project(self, user_id, project_id):
        with self._lock:
            self.projects.pop((user_id, project_id), None)

    # filas de archivos
    def insert_file(self, doc):
        with self._lock:
            key = (doc["project_id"], doc["ruta"], doc["version"])
            if key in self.files:
                raise Duplicate(key)
            self.files[key] = copy.deepcopy(doc)

    def get_file(self, project_id, ruta, version):
        return copy.deepcopy(self.files.get((project_id, ruta, version)))

    def file_rows(self, project_id):
        return [{k: v for k, v in d.items() if k != "contenido"} for (p, _, _), d in self.files.items()
                if p == project_id]

    def delete_file_rows(self, project_id, keys):
        with self._lock:
            for ruta, version in keys:
                self.files.pop((project_id, ruta, version), None)

    def delete_files(self, project_id):
        with self._lock:
            for key in [k for k in self.files if k[0] == project_id]:
                del self.files[key]

    # versiones
    def insert_version(self, doc):
        with self._lock:
            key = (doc["project_id"], doc["version"])
            if key in self.versions:
                raise Duplicate(key)
            self.versions[key] = copy.deepcopy(doc)

    def get_version(self, project_id, version):
        return copy.deepcopy(self.versions.get((project_id, version)))

    def list_versions(self, project_id, limit=0):
        rows = sorted((copy.deepcopy(d) for (p, _), d in self.versions.items() if p == project_id),
                      key=lambda d: d["version"], reverse=True)
        return rows[:limit] if limit else rows

    def delete_version_docs(self, project_id, versions):
        with self._lock:
            for v in versions:
                self.versions.pop((project_id, v), None)

    def delete_versions(self, project_id):
        with self._lock:
            for key in [k for k in self.versions if k[0] == project_id]:
                del self.versions[key]

    # tokens de vista previa
    def insert_preview_token(self, doc):
        with self._lock:
            if doc["token_hash"] in self.previews:
                raise Duplicate(doc["token_hash"])
            self.previews[doc["token_hash"]] = copy.deepcopy(doc)

    def get_preview_token(self, token_hash):
        return copy.deepcopy(self.previews.get(token_hash))

    def delete_preview_tokens(self, project_id):
        with self._lock:
            for key in [k for k, d in self.previews.items() if d["project_id"] == project_id]:
                del self.previews[key]
