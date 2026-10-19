"""Lógica de proyectos del codificador sobre un CoderRepo: crear, escribir, parchear, borrar archivos, versionar,
comparar, restaurar, cuotas y borrado en cascada. Cada cambio crea una versión nueva cuyo manifiesto reutiliza las
filas que no cambiaron; restaurar también crea una versión nueva (no se pierde nada). Todo se consulta con el user_id
del dueño: un proyecto ajeno y uno inexistente dan el mismo error (project_not_found)."""
import difflib
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from assistant.core.coder.errors import CoderError
from assistant.core.coder.paths import TEXT_TYPES, extension, mime_for, safe_name, safe_path
from assistant.core.coder.repo import CoderRepo, Duplicate

kinds = ("landing", "game", "tool", "other")
preview_minutes = 30
max_edits = 20
_project_id = re.compile(r"p_[0-9a-f]{12}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def summary(doc: dict) -> dict:
    """Lo que ven el modelo y la UI de un proyecto (sin user_id)."""
    return {"project_id": doc["project_id"], "name": doc["nombre"], "kind": doc["tipo"],
            "version": doc["version_actual"], "bytes": doc.get("bytes", 0),
            "created": doc["creado"].isoformat(), "updated": doc["actualizado"].isoformat()}


class Projects:
    def __init__(self, repo: CoderRepo, settings):
        self.repo = repo
        self.s = settings

    # ------------------------------------------------------------------ lectura

    def get(self, user_id: str, project_id: str) -> dict:
        if not isinstance(project_id, str) or not _project_id.fullmatch(project_id):
            raise CoderError("project_not_found")
        doc = self.repo.get_project(user_id, project_id)
        if doc is None:
            raise CoderError("project_not_found")
        return doc

    def list_projects(self, user_id: str) -> list[dict]:
        return [summary(p) for p in self.repo.list_projects(user_id)]

    def usage(self, user_id: str) -> dict:
        projects = self.repo.list_projects(user_id)
        return {"projects": len(projects), "bytes": sum(p.get("bytes", 0) for p in projects)}

    def manifest(self, project_id: str, version: int) -> dict:
        doc = self.repo.get_version(project_id, version)
        if doc is None:
            raise CoderError("version_not_found", version=version)
        return doc["archivos"]

    def list_files(self, user_id: str, project_id: str, version: int | None = None) -> list[dict]:
        project = self.get(user_id, project_id)
        manifest = self.manifest(project_id, project["version_actual"] if version is None else version)
        rows = {(r["ruta"], r["version"]): r for r in self.repo.file_rows(project_id)}
        out = []
        for ruta in sorted(manifest):
            row = rows.get((ruta, manifest[ruta]), {})
            out.append({"path": ruta, "bytes": row.get("bytes", 0), "mime": row.get("tipo_mime", mime_for(ruta)),
                        "hash": row.get("hash", ""), "since_version": manifest[ruta]})
        return out

    def read_file(self, user_id: str, project_id: str, path: str, version: int | None = None) -> dict:
        project = self.get(user_id, project_id)
        ruta = safe_path(path)
        current = project["version_actual"] if version is None else version
        manifest = self.manifest(project_id, current)
        if ruta not in manifest:
            raise CoderError("file_not_found", path=ruta)
        row = self.repo.get_file(project_id, ruta, manifest[ruta])
        if row is None:  # manifiesto sin su fila: no debería pasar
            raise CoderError("file_not_found", path=ruta)
        return {"path": ruta, "content": row["contenido"], "mime": row["tipo_mime"], "hash": row["hash"],
                "bytes": row["bytes"], "version": current}

    def list_versions(self, user_id: str, project_id: str, limit: int = 20) -> list[dict]:
        self.get(user_id, project_id)
        return [{"version": v["version"], "origin": v["origen"], "note": v.get("nota", ""),
                 "from_version": v.get("desde_version"), "files": len(v["archivos"]),
                 "created": v["creado"].isoformat()}
                for v in self.repo.list_versions(project_id, max(1, min(int(limit), 100)))]

    def diff(self, user_id: str, project_id: str, from_version: int, to_version: int, path: str = "",
             max_lines: int = 200) -> str:
        """Diff unificado entre dos versiones (todas las rutas o una), acotado a `max_lines` líneas."""
        self.get(user_id, project_id)
        a, b = self.manifest(project_id, from_version), self.manifest(project_id, to_version)
        rutas = [safe_path(path)] if path else sorted(set(a) | set(b))
        lines: list[str] = []
        for ruta in rutas:
            if a.get(ruta) == b.get(ruta):
                continue
            if extension(ruta) not in TEXT_TYPES:
                lines.append(f"binary file {ruta} changed")
                continue
            old = self._content(project_id, ruta, a.get(ruta))
            new = self._content(project_id, ruta, b.get(ruta))
            lines += difflib.unified_diff(old.splitlines(), new.splitlines(), f"v{from_version}/{ruta}",
                                          f"v{to_version}/{ruta}", lineterm="", n=2)
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... (diff truncated: {len(lines) - max_lines} more lines)"]
        return "\n".join(lines)

    def _content(self, project_id: str, ruta: str, version: int | None) -> str:
        if version is None:
            return ""
        row = self.repo.get_file(project_id, ruta, version)
        return row["contenido"] if row else ""

    # ------------------------------------------------------------------ escritura

    def create(self, user_id: str, name: str, kind: str = "other") -> dict:
        nombre = safe_name(name)
        if kind not in kinds:
            raise CoderError("invalid_kind", kind=str(kind)[:20], allowed=", ".join(kinds))
        if len(self.repo.list_projects(user_id)) >= self.s.coder_max_projects_per_user:
            raise CoderError("quota_projects", limit=self.s.coder_max_projects_per_user)
        now = _now()
        for attempt in range(3):  # project_id es único entre usuarios: ante un choque (improbable), otro id
            doc = {"user_id": user_id, "project_id": "p_" + secrets.token_hex(6), "nombre": nombre, "tipo": kind,
                   "creado": now, "actualizado": now, "version_actual": 0, "bytes": 0, "pinned_versions": []}
            try:
                self.repo.insert_project(doc)
                break
            except Duplicate:
                if attempt == 2:
                    raise CoderError("conflict") from None
        self.repo.insert_version({"project_id": doc["project_id"], "user_id": user_id, "version": 0, "archivos": {},
                                  "origen": "create", "nota": "", "desde_version": None, "creado": now})
        return summary(doc)

    def write_file(self, user_id: str, project_id: str, path: str, content: str) -> int:
        """Crea o reemplaza un archivo de texto. Devuelve la versión nueva."""
        project = self.get(user_id, project_id)
        ruta = self._text_path(path)
        return self._save(user_id, project, ruta, content, "write")

    def edit_file(self, user_id: str, project_id: str, path: str, edits: list, expected_version: int) -> int:
        """Aplica parches {old, new} en orden; cada `old` debe aparecer exactamente una vez. Exige que
        `expected_version` sea la versión actual (el agente leyó el archivo antes de editarlo)."""
        project = self.get(user_id, project_id)
        ruta = self._text_path(path)
        if not isinstance(edits, list) or not edits or len(edits) > max_edits:
            raise CoderError("edit_invalid", reason=f"edits must be a list of 1 to {max_edits} items")
        if expected_version != project["version_actual"]:
            raise CoderError("stale_version", expected=expected_version, current=project["version_actual"])
        text = self.read_file(user_id, project_id, ruta)["content"]
        for i, edit in enumerate(edits):
            old = edit.get("old") if isinstance(edit, dict) else None
            new = edit.get("new") if isinstance(edit, dict) else None
            if not isinstance(old, str) or not old or not isinstance(new, str):
                raise CoderError("edit_invalid", index=i, reason="each edit needs a non-empty 'old' and a 'new' string")
            count = text.count(old)
            if count == 0:
                raise CoderError("edit_not_found", index=i)
            if count > 1:
                raise CoderError("edit_ambiguous", index=i, count=count)
            text = text.replace(old, new, 1)
        return self._save(user_id, project, ruta, text, "edit")

    def delete_file(self, user_id: str, project_id: str, path: str) -> int:
        project = self.get(user_id, project_id)
        ruta = safe_path(path)
        manifest = self.manifest(project_id, project["version_actual"])
        if ruta not in manifest:
            raise CoderError("file_not_found", path=ruta)
        archivos = {k: v for k, v in manifest.items() if k != ruta}
        return self._commit(user_id, project, archivos, [], "delete", ruta)

    def restore(self, user_id: str, project_id: str, version: int) -> int:
        """Versión nueva con el manifiesto de `version`. La actual queda en el historial."""
        project = self.get(user_id, project_id)
        old = self.manifest(project_id, version)
        if old == self.manifest(project_id, project["version_actual"]):
            raise CoderError("unchanged")
        return self._commit(user_id, project, dict(old), [], "restore", f"v{version}", desde=version)

    def delete_project(self, user_id: str, project_id: str) -> None:
        self.get(user_id, project_id)
        self.repo.delete_files(project_id)
        self.repo.delete_versions(project_id)
        self.repo.delete_preview_tokens(project_id)
        self.repo.delete_project(user_id, project_id)

    def delete_user(self, user_id: str) -> int:
        projects = self.repo.list_projects(user_id)
        for p in projects:
            self.delete_project(user_id, p["project_id"])
        return len(projects)

    # ------------------------------------------------------------------ vista previa

    def issue_preview(self, user_id: str, project_id: str) -> dict:
        """Token de vista previa de la versión actual: 32 bytes aleatorios; solo se guarda su sha256 y caduca a los
        30 minutos. Quien lo tenga ve esa versión (solo lectura) mientras no caduque."""
        project = self.get(user_id, project_id)
        token = secrets.token_urlsafe(32)
        now = _now()
        expires = now + timedelta(minutes=preview_minutes)
        self.repo.insert_preview_token({"token_hash": hashlib.sha256(token.encode()).hexdigest(), "user_id": user_id,
                                        "project_id": project_id, "version": project["version_actual"],
                                        "creado": now, "expira": expires})
        return {"token": token, "version": project["version_actual"], "expires": expires}

    def resolve_preview(self, token: str) -> dict | None:
        """{project_id, version} de un token vigente, o None (inexistente, caducado, mal formado o de un proyecto
        borrado: siempre lo mismo, sin distinguir)."""
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{30,64}", token):
            return None
        doc = self.repo.get_preview_token(hashlib.sha256(token.encode()).hexdigest())
        if doc is None or doc["expira"] <= _now():
            return None
        if self.repo.get_project(doc["user_id"], doc["project_id"]) is None:
            return None
        return {"project_id": doc["project_id"], "version": doc["version"]}

    def version_file(self, project_id: str, version: int, path: str) -> dict | None:
        """Archivo de una versión concreta para servirlo, o None si la ruta no es válida o no está en esa versión."""
        try:
            ruta = safe_path(path)
            manifest = self.manifest(project_id, version)
        except CoderError:
            return None
        if ruta not in manifest:
            return None
        row = self.repo.get_file(project_id, ruta, manifest[ruta])
        return None if row is None else {"path": ruta, "content": row["contenido"], "mime": row["tipo_mime"],
                                         "hash": row["hash"]}

    def version_texts(self, project_id: str, version: int) -> dict[str, str]:
        """{ruta: contenido} de los archivos de texto de una versión (para el analizador)."""
        out = {}
        for ruta, v in self.manifest(project_id, version).items():
            if extension(ruta) in TEXT_TYPES and (row := self.repo.get_file(project_id, ruta, v)) is not None:
                out[ruta] = row["contenido"]
        return out

    # ------------------------------------------------------------------ internos

    @staticmethod
    def _text_path(path: str) -> str:
        ruta = safe_path(path)
        if extension(ruta) not in TEXT_TYPES:
            raise CoderError("type_not_allowed", path=ruta, reason="asset_needs_upload")
        return ruta

    def _save(self, user_id: str, project: dict, ruta: str, content: str, origen: str) -> int:
        if not isinstance(content, str) or "\x00" in content:
            raise CoderError("invalid_content")
        size = _size(content)
        if size > self.s.coder_max_file_bytes:
            raise CoderError("quota_file_bytes", limit=self.s.coder_max_file_bytes, size=size)
        pid = project["project_id"]
        manifest = self.manifest(pid, project["version_actual"])
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if ruta in manifest:
            row = self.repo.get_file(pid, ruta, manifest[ruta])
            if row and row["hash"] == digest:
                raise CoderError("unchanged")
        elif len(manifest) >= self.s.coder_max_files:
            raise CoderError("quota_files", limit=self.s.coder_max_files)
        used = self.usage(user_id)["bytes"]
        if used + size > self.s.coder_max_user_bytes:
            raise CoderError("quota_user_bytes", limit=self.s.coder_max_user_bytes, used=used)
        row = {"project_id": pid, "user_id": user_id, "ruta": ruta, "contenido": content,
               "tipo_mime": mime_for(ruta), "hash": digest, "bytes": size}
        return self._commit(user_id, project, dict(manifest), [row], origen, ruta)

    def _commit(self, user_id: str, project: dict, archivos: dict, rows: list[dict], origen: str, nota: str,
                desde: int | None = None) -> int:
        """Versión actual + 1: reclama el número (índice único), inserta las filas nuevas y avanza el proyecto solo
        si nadie lo avanzó antes (si no, deshace y da `conflict`)."""
        pid, prev = project["project_id"], project["version_actual"]
        version = prev + 1
        for row in rows:
            row["version"] = version
            archivos[row["ruta"]] = version
        try:
            self.repo.insert_version({"project_id": pid, "user_id": user_id, "version": version, "archivos": archivos,
                                      "origen": origen, "nota": nota, "desde_version": desde, "creado": _now()})
        except Duplicate:
            raise CoderError("conflict") from None
        inserted = []
        try:
            for row in rows:
                self.repo.insert_file(row)
                inserted.append((row["ruta"], version))
        except Duplicate:
            self._undo(pid, version, inserted)
            raise CoderError("conflict") from None
        added = sum(r["bytes"] for r in rows)
        if not self.repo.update_project(user_id, pid, {"version_actual": version, "actualizado": _now(),
                                                      "bytes": project.get("bytes", 0) + added}, if_version=prev):
            self._undo(pid, version, inserted)
            raise CoderError("conflict")
        self._prune(user_id, pid)
        return version

    def _undo(self, project_id: str, version: int, rows: list[tuple[str, int]]) -> None:
        self.repo.delete_file_rows(project_id, rows)
        self.repo.delete_version_docs(project_id, [version])

    def _prune(self, user_id: str, project_id: str) -> None:
        """Por encima de CODER_MAX_VERSIONS borra las versiones más viejas (nunca la actual ni las fijadas, p. ej. la
        publicada) y las filas que ya no usa ninguna versión."""
        versions = self.repo.list_versions(project_id)
        limit = max(1, self.s.coder_max_versions)
        if len(versions) <= limit:
            return
        project = self.repo.get_project(user_id, project_id)
        keep = {project["version_actual"], *project.get("pinned_versions", [])}
        drop = [v["version"] for v in versions[limit:] if v["version"] not in keep]
        if not drop:
            return
        self.repo.delete_version_docs(project_id, drop)
        used = {(ruta, v) for doc in versions if doc["version"] not in drop for ruta, v in doc["archivos"].items()}
        orphans = [r for r in self.repo.file_rows(project_id) if (r["ruta"], r["version"]) not in used]
        if orphans:
            self.repo.delete_file_rows(project_id, [(r["ruta"], r["version"]) for r in orphans])
            total = sum(r["bytes"] for r in self.repo.file_rows(project_id))
            self.repo.update_project(user_id, project_id, {"bytes": total})
