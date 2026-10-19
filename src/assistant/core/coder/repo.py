"""Interfaz del almacén de proyectos del codificador (Mongo en producción, memoria en tests). Solo primitivas: la
lógica (cuotas, versionado, parches) vive en projects.py. Toda consulta de proyecto lleva el user_id del dueño.

Formato (colecciones con prefijo coder_ en la base de negocio):
- coder_projects: {user_id, project_id, nombre, tipo, creado, actualizado, version_actual, bytes, pinned_versions}
- coder_files: {project_id, user_id, ruta, contenido, tipo_mime, hash, bytes, version}; filas inmutables, `version`
  es la versión en la que nació ese contenido
- coder_versions: {project_id, user_id, version, archivos {ruta: version_de_fila}, origen, nota, desde_version, creado}
"""
from typing import Protocol


class Duplicate(Exception):
    """Clave única repetida (otra escritura ganó la carrera)."""


class CoderRepo(Protocol):
    # proyectos
    def insert_project(self, doc: dict) -> None: ...
    def get_project(self, user_id: str, project_id: str) -> dict | None: ...
    def list_projects(self, user_id: str) -> list[dict]: ...
    def update_project(self, user_id: str, project_id: str, fields: dict, if_version: int | None = None) -> bool: ...
    def delete_project(self, user_id: str, project_id: str) -> None: ...

    # filas de archivos
    def insert_file(self, doc: dict) -> None: ...  # Duplicate si (project_id, ruta, version) ya existe
    def get_file(self, project_id: str, ruta: str, version: int) -> dict | None: ...
    def file_rows(self, project_id: str) -> list[dict]: ...  # sin `contenido`: {ruta, version, bytes, hash}
    def delete_file_rows(self, project_id: str, keys: list[tuple[str, int]]) -> None: ...
    def delete_files(self, project_id: str) -> None: ...

    # versiones
    def insert_version(self, doc: dict) -> None: ...  # Duplicate si (project_id, version) ya existe
    def get_version(self, project_id: str, version: int) -> dict | None: ...
    def list_versions(self, project_id: str, limit: int = 0) -> list[dict]: ...  # de la más nueva a la más vieja
    def delete_version_docs(self, project_id: str, versions: list[int]) -> None: ...
    def delete_versions(self, project_id: str) -> None: ...
