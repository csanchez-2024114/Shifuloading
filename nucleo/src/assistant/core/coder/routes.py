"""Instalación del codificador en la app principal. create_app la llama siempre; con todos los interruptores CODER_* en
0 no hace nada (ni rutas, ni estado, ni colecciones). Con alguno encendido valida la combinación (ConfigError en
español), deja en app.state.coder la lógica de proyectos sobre la base de negocio y registra las rutas del dueño
(sesión + CSRF; el user_id sale siempre de la sesión y un proyecto ajeno da 404). Plan: docs/CODER_PLAN.md."""
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from assistant.core.coder.analyze import analyze
from assistant.core.coder.errors import CoderError
from assistant.core.coder.projects import Projects
from assistant.core.config import ConfigError


def coder_requested(settings) -> bool:
    return any((settings.coder_enabled, settings.coder_data_enabled, settings.coder_sharing_enabled,
                settings.coder_public_write_enabled))


def _text(profile, key: str, fallback: str, **values) -> str:
    # texto del catálogo del perfil si lo tiene; si no, el de respaldo (como http.thread_busy en server.py)
    text = (profile.texts.get(key) if profile is not None else None) or fallback
    return text.format(**values) if values else text


def check_settings(settings, profile=None, appdata=None) -> None:
    """ConfigError si la combinación de interruptores CODER_* no es válida."""
    if not coder_requested(settings):
        return
    if not settings.coder_enabled:
        raise ConfigError(_text(profile, "startup.coder_flag_needs_coder",
                                "CODER_DATA_ENABLED, CODER_SHARING_ENABLED y CODER_PUBLIC_WRITE_ENABLED necesitan "
                                "CODER_ENABLED=1."))
    if not settings.auth_enabled or appdata is None:
        raise ConfigError(_text(profile, "startup.coder_needs_auth",
                                "CODER_ENABLED=1 necesita AUTH_ENABLED=1 y la base de negocio (APP_MONGODB_URI y "
                                "APP_MONGODB_DB): los proyectos son por usuario y el usuario sale de la sesión."))
    if settings.coder_public_write_enabled and not (settings.coder_data_enabled and settings.coder_sharing_enabled):
        raise ConfigError(_text(profile, "startup.coder_public_write_needs",
                                "CODER_PUBLIC_WRITE_ENABLED=1 necesita también CODER_DATA_ENABLED=1 y "
                                "CODER_SHARING_ENABLED=1."))
    if settings.use_bigtool:
        raise ConfigError(_text(profile, "startup.coder_bigtool",
                                "CODER_ENABLED=1 no funciona con USE_BIGTOOL=1: bigtool no aplica las aprobaciones "
                                "del perfil (borrar, restaurar y compartir proyectos las necesitan)."))
    origin = urlparse(settings.coder_sandbox_origin)
    if origin.scheme not in ("http", "https") or not origin.hostname or origin.path not in ("", "/") \
            or origin.query or origin.fragment or origin.username or origin.password:
        raise ConfigError(_text(profile, "startup.coder_sandbox_origin",
                                "CODER_SANDBOX_ORIGIN debe ser un origen http(s) sin ruta, p. ej. "
                                "http://127.0.0.2:8100 (es «{origin}»).", origin=settings.coder_sandbox_origin))
    host = origin.hostname.lower()
    if host in settings.trusted_hosts or "*" in settings.trusted_hosts:
        raise ConfigError(_text(profile, "startup.coder_sandbox_host_shared",
                                "El host de CODER_SANDBOX_ORIGIN ({host}) también está en TRUSTED_HOSTS: la vista "
                                "previa y lo publicado deben servirse desde otro host que la app (las cookies no se "
                                "separan por puerto). Usa en TRUSTED_HOSTS solo el host de la app (p. ej. 127.0.0.1) "
                                "u otro host para el sandbox.", host=host))


def _repo(appdata):
    """El almacén de proyectos sobre la misma base de negocio que `appdata`. Un test puede inyectar el suyo en
    appdata.coder_repo; con la base de negocio en memoria (tests), uno en memoria."""
    if (repo := getattr(appdata, "coder_repo", None)) is not None:
        return repo
    users = getattr(appdata, "users", None)
    if users is not None and hasattr(users, "col"):  # MongoAppData: misma base de negocio
        from assistant.core.coder.mongo import MongoCoderRepo

        return MongoCoderRepo(users.col.database)
    from assistant.core.coder.memory import MemoryCoderRepo

    return MemoryCoderRepo()


def preview_url(settings, token: str) -> str:
    return f"{settings.coder_sandbox_origin.rstrip('/')}/p/{token}/"


def install_coder_routes(app, settings, profile, appdata, user=None, changing=None) -> None:
    """`user`/`changing`: los de create_app (sesión; sesión + mismo origen + CSRF)."""
    if not coder_requested(settings):
        return
    check_settings(settings, profile, appdata)
    for module in ("PIL", "multipart"):  # reencodeo de imágenes y subida de recursos
        try:
            __import__(module)
        except ImportError as exc:
            raise ConfigError(_text(profile, "startup.coder_missing_deps",
                                    "CODER_ENABLED=1 necesita las dependencias de archivos (falta {module}). "
                                    "Instálalas con: uv pip install --python .venv -e \".[files]\"",
                                    module=module)) from exc
    projects = app.state.coder = Projects(_repo(appdata), settings)
    from assistant.core.coder import runtime

    runtime.set_current(projects)  # lo usan las herramientas del perfil al ejecutarse

    def not_found() -> HTTPException:
        # uno ajeno y uno inexistente responden igual, para no revelar que existe
        return HTTPException(404, _text(profile, "coder.project_not_found", "No existe ese proyecto."))

    @app.post("/coder/projects/{project_id}/preview")
    def coder_preview(project_id: str, request: Request):
        """Token de vista previa (30 minutos) de la versión actual, con la URL del sandbox y el análisis del código."""
        owner = changing(request)
        try:
            issued = projects.issue_preview(owner["user_id"], project_id)
        except CoderError:
            raise not_found() from None
        return {"url": preview_url(settings, issued["token"]), "version": issued["version"],
                "expires": issued["expires"].isoformat(),
                "findings": analyze(projects.version_texts(project_id, issued["version"]))}

    from fastapi import File, UploadFile

    from assistant.core.coder.assets import prepare_asset

    @app.post("/coder/uploads")
    def coder_upload(request: Request, file: UploadFile = File(...)):
        """Sube un recurso (imagen, audio o datos) a nombre del usuario de la sesión; el agente lo pasa después a un
        proyecto. Cualquier user_id del formulario se ignora."""
        owner = changing(request)
        data = file.file.read(settings.coder_max_asset_bytes + 1)  # nunca más del tope en memoria
        try:
            return projects.stage_upload(owner["user_id"],
                                         prepare_asset(data, file.filename or "", settings.coder_max_asset_bytes))
        except CoderError as exc:
            raise HTTPException(upload_status.get(exc.code, 422), _text(
                profile, f"coder.upload.{exc.code}", "No se pudo usar ese archivo.", **exc.values)) from None

    @app.get("/coder/uploads")
    def coder_uploads(request: Request):
        return {"uploads": projects.list_uploads(user(request)["user_id"])}

    @app.delete("/coder/uploads/{upload_id}")
    def coder_delete_upload(upload_id: str, request: Request):
        owner = changing(request)
        if not projects.delete_upload(owner["user_id"], upload_id):
            raise HTTPException(404, _text(profile, "coder.upload_not_found", "No existe esa subida."))
        return {"deleted": upload_id}


# código del error al subir -> estado HTTP
upload_status = {
    "asset_too_large": 413, "asset_too_many_pixels": 413, "quota_user_bytes": 413, "quota_uploads": 413,
    "asset_type_not_allowed": 415, "asset_mismatch": 415, "asset_polyglot": 415,
    "asset_empty": 422, "asset_timeout": 422,
}
