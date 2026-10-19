"""Origen aislado del codificador: una app ASGI APARTE de la principal, en otro host (por defecto
http://127.0.0.2:8100). Sirve solo archivos estáticos de proyectos, de solo lectura:
    /p/<token>/<ruta>   vista previa de una versión (token de 30 minutos)
No lee cookies ni emite Set-Cookie. Toda respuesta lleva la CSP con la directiva `sandbox allow-scripts` (origen
opaco, también si se abre de primer nivel) y sin salida a otros sitios. Todo lo que no se sirve responde el mismo 404,
byte a byte. Los tokens inválidos repetidos desde una IP terminan en 429, igual exista el token o no.

Arranque (proceso propio, sin cabecera Server):
    .venv\\Scripts\\python -m uvicorn assistant.core.coder.sandbox:app --host 127.0.0.2 --port 8100 --no-server-header
"""
import sys
import threading
import time
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from assistant.core.config import ConfigError, Settings

security_headers = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cache-Control": "no-store",
}
not_found_csp = "sandbox; default-src 'none'; frame-ancestors 'none'"


def project_csp(base: str, frame_ancestors: str) -> str:
    """CSP de un archivo servido. `base` es el origen del sandbox + el prefijo del token (termina en "/"): todo se
    limita a esa ruta, así un proyecto no puede cargar archivos de otro token."""
    return (f"sandbox allow-scripts; default-src 'none'; script-src {base} 'unsafe-inline'; "
            f"style-src {base} 'unsafe-inline'; img-src {base} data: blob:; media-src {base}; font-src {base}; "
            f"connect-src {base}__data/; form-action 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; "
            f"object-src 'none'; base-uri 'none'; frame-ancestors {frame_ancestors}")


def app_ancestors(trusted_hosts) -> str:
    """Quién puede incrustar la vista previa: solo la app (sus hosts de TRUSTED_HOSTS, cualquier puerto)."""
    hosts = [h for h in trusted_hosts if h and h != "*"]
    return " ".join(f"{scheme}://{h}:*" for h in hosts for scheme in ("http", "https")) or "'none'"


def not_found() -> Response:
    """El único 404 del sandbox: mismo cuerpo y mismas cabeceras para todo lo que no se sirve."""
    return Response(b"Not found", status_code=404, media_type="text/plain",
                    headers={**security_headers, "Content-Security-Policy": not_found_csp})


def too_many() -> Response:
    return Response(b"Too many requests", status_code=429, media_type="text/plain",
                    headers={**security_headers, "Content-Security-Policy": not_found_csp})


class FailLimiter:
    """Intentos con token inválido por IP en una ventana deslizante (en memoria: un worker por proceso)."""

    def __init__(self, max_fails: int, window_seconds: float):
        self.max_fails = max_fails
        self.window = window_seconds
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._fails.get(key, []) if now - t < self.window]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        if self.max_fails <= 0:
            return False
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.max_fails

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.monotonic()).append(time.monotonic())


def create_sandbox_app(settings: Settings, projects) -> Starlette:
    origin = settings.coder_sandbox_origin.rstrip("/")
    host = urlparse(origin).hostname
    ancestors = app_ancestors(settings.trusted_hosts)
    limiter = FailLimiter(settings.coder_token_fail_max, settings.coder_token_fail_window_minutes * 60)

    def serve(request: Request) -> Response:
        if request.method not in ("GET", "HEAD"):
            return not_found()
        parts = request.url.path.split("/", 3)  # "", "p", token, ruta
        if len(parts) < 3 or parts[1] != "p":
            return not_found()
        client = request.client.host if request.client else "?"
        if limiter.blocked(client):
            return too_many()
        found = projects.resolve_preview(parts[2])
        if found is None:
            limiter.fail(client)
            return not_found()
        path = parts[3] if len(parts) > 3 else ""
        if path == "" or path.endswith("/"):
            path += "index.html"
        f = projects.version_file(found["project_id"], found["version"], path)
        if f is None:
            return not_found()
        body = f["content"].encode("utf-8") if isinstance(f["content"], str) else f["content"]
        csp = project_csp(f"{origin}/p/{parts[2]}/", ancestors)
        return Response(body, media_type=f["mime"], headers={
            **security_headers, "Content-Security-Policy": csp,
            # la página aislada tiene origen opaco: para cargar sus propios módulos JS necesita CORS (sin credenciales)
            "Access-Control-Allow-Origin": "*"})

    app = Starlette(routes=[Route("/{rest:path}", serve, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE",
                                                                    "OPTIONS"])])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host])
    return app


def _real_app() -> Starlette:
    """La app del proceso del sandbox, desde el entorno: mismos interruptores y la misma base de negocio que la app."""
    from assistant.core import memory
    from assistant.core.coder.mongo import MongoCoderRepo
    from assistant.core.coder.projects import Projects
    from assistant.core.coder.routes import check_settings

    settings = Settings.from_env()
    if not settings.coder_enabled:
        raise ConfigError("El sandbox del codificador necesita CODER_ENABLED=1.")
    client = memory.app_startup(settings)
    check_settings(settings, None, appdata=client)
    return create_sandbox_app(settings, Projects(MongoCoderRepo(client[settings.app_mongodb_db]), settings))


def __getattr__(name: str):
    # `app` perezoso, como en server.py: importar el módulo no conecta a Mongo
    if name != "app":
        raise AttributeError(name)
    try:
        globals()["app"] = _real_app()
    except ConfigError as e:
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    return globals()["app"]
