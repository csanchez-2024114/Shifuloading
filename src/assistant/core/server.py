"""FastAPI: chat con streaming SSE, historial y reanudación human-in-the-loop."""
import contextvars
import json
import logging
import queue
import sys
import threading
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from assistant.core import agent as agent_mod
from assistant.core import ai_data
from assistant.core import context as context_mod
from assistant.core import hosts
from assistant.core import memory
from assistant.core.appdata import MAX_TITLE_CHARS, clean_title, thread_title
from assistant.core.auth import CSRF_HEADER, SESSION_COOKIE, AuthError, AuthService, csrf_for, csrf_ok
from assistant.core.config import ConfigError, Settings
from assistant.core.i18n import tr
from assistant.core.profile import active_profile

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("assistant")


class ChatIn(BaseModel):
    message: str
    thread_id: str
    user_id: str = "anon"
    effort: str | None = None  # bajo/medio/alto desde el selector de la UI; None o "auto" = clasificador
    file_ids: list[str] = []   # FILES_ENABLED: archivos ya subidos a este hilo que van con el mensaje


class ResumeIn(BaseModel):
    thread_id: str
    user_id: str = "anon"
    decisions: list[dict]


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordIn(BaseModel):
    password: str


class RenameIn(BaseModel):
    title: str


def _build_real_agent(settings: Settings, profile):
    """Devuelve (agente, store de recuerdos)."""
    client = memory.startup_checks(settings)
    from assistant.core.tools import build_tools

    model = agent_mod.make_model(settings)
    checkpointer = memory.build_checkpointer(client, settings.mongodb_db)
    store = memory.build_store(client, settings.mongodb_db, settings.memory_semantic, settings.openai_api_key)
    if settings.use_bigtool:
        from assistant.core.extensions.bigtool import BIGTOOL_PROMPT, build_bigtool_agent

        log.info("Agente: langgraph-bigtool (demo tools: %s)", settings.bigtool_demo_tools)
        # antes de buscar solo ve retrieve_tools
        agent_mod.check_turn_cap(settings, extra_prompt=BIGTOOL_PROMPT)
        agent = build_bigtool_agent(model, settings, checkpointer=checkpointer, memories_store=store, profile=profile)
        # bigtool no tiene medidor en vivo: el endpoint usa el uso real guardado
        agent.base_context_tokens = context_mod.prompt_tokens(agent_mod.system_prompt_text(settings, profile)
                                                              + BIGTOOL_PROMPT)
        return agent, store
    tools = build_tools(model, settings, profile=profile)
    agent_mod.check_turn_cap(settings, tools)
    return agent_mod.build_agent(model, tools, settings, checkpointer=checkpointer, store=store, profile=profile), store


PING = ": ping\n\n"  # comentario SSE: el cliente lo ignora, pero mantiene viva la conexión en proxies
_END = object()


def with_keepalive(events, interval: float):
    """Reenvía `events` (iterador bloqueante) y emite PING cada `interval` segundos sin eventos.
    El iterador corre en un hilo aparte (con el contexto actual); si el cliente se va, se detiene en el
    siguiente evento."""
    if not interval or interval <= 0:
        yield from events
        return
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def produce():
        try:
            for item in events:
                q.put(item)
                if stop.is_set():
                    break
        except BaseException as exc:  # noqa: BLE001 - se re-lanza en el hilo del servidor
            q.put(exc)
        finally:
            close = getattr(events, "close", None)
            if close:
                close()
            q.put(_END)

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(produce,), daemon=True).start()
    try:
        while True:
            try:
                item = q.get(timeout=interval)
            except queue.Empty:
                yield PING
                continue
            if item is _END:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()


def create_app(agent=None, settings: Settings | None = None, classify=None, store=None, appdata=None,
               profile=None) -> FastAPI:
    """`appdata`: base de negocio (AUTH_ENABLED); se inyecta en tests. `profile`: perfil del agente (prompt,
    herramientas, UI); None = el de AGENT_PROFILE."""
    settings = settings or Settings.from_env()
    profile = profile or active_profile()
    if settings.files_enabled and settings.use_bigtool:
        # bigtool aún no añade la regla de archivos al prompt (REFACTOR_NOTAS.md, Fase 4): no se combinan
        raise ConfigError(profile.texts.get("startup.files_bigtool") or
                          "FILES_ENABLED=1 no funciona todavía con USE_BIGTOOL=1: apaga una de las dos.")
    if classify is None:
        # agente inyectado (tests) → sin llamadas reales a OpenAI para clasificar
        classify = agent_mod.clasificar_esfuerzo if agent is None else (lambda s, m: "medio")
    if agent is None:
        agent, store = _build_real_agent(settings, profile)
        host = settings.mongodb_uri.rsplit("@", 1)[-1]  # nunca loguear usuario/contraseña
        log.info("Modelo: %s | MongoDB IA: %s (db %s)", settings.llm_model, host, settings.mongodb_db)
        if appdata is None and (app_client := memory.app_startup(settings)) is not None:
            from assistant.core.appdata.mongo import MongoAppData

            appdata = MongoAppData(app_client, settings.app_mongodb_db, settings.metrics_ttl_days)
            log.info("MongoDB negocio: %s (db %s)", settings.app_mongodb_uri.rsplit("@", 1)[-1],
                     settings.app_mongodb_db)
    if settings.auth_enabled and appdata is None:
        raise ConfigError(tr("http.server_needs_app_db", profile))
    if (settings.turn_metrics or settings.feedback_enabled) and appdata is None:
        raise ConfigError(profile.texts.get("startup.metrics_need_app_db") or
                          "TURN_METRICS y FEEDBACK_ENABLED necesitan la base de negocio (APP_MONGODB_URI).")
    auth = AuthService(appdata, settings.session_ttl_days, settings.login_max_fails,
                       settings.login_lock_minutes, settings.login_max_fails_ip) if settings.auth_enabled else None

    if not settings.auth_enabled and (lejanos := hosts.non_local_hosts(settings.trusted_hosts)):
        raise ConfigError(tr("startup.non_local_hosts", profile, hosts=", ".join(lejanos)))

    app = FastAPI(title=profile.display_name)
    # S1: el último en agregarse corre primero. Loopback (sin cuentas) y luego la cabecera Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    if not settings.auth_enabled:
        app.add_middleware(hosts.LoopbackOnly, message=tr("http.not_loopback", profile))

    # ---------------------------------------------------------------- sesión y propiedad (AUTH_ENABLED=1)
    def _token(request: Request) -> str | None:
        return request.cookies.get(SESSION_COOKIE)

    def _user(request: Request) -> dict:
        user = auth.session_user(_token(request))
        if user is None:
            raise HTTPException(401, tr("http.login_required", profile))
        return user

    def _same_origin(request: Request) -> None:
        # CSRF (1/2): las peticiones que cambian estado deben venir de esta misma página
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, tr("http.origin_forbidden", profile))

    def _changing(request: Request) -> dict:
        """Usuario de una petición que cambia estado: mismo origen, sesión y cabecera CSRF (2/2)."""
        _same_origin(request)
        user = _user(request)
        if not csrf_ok(_token(request), request.headers.get(CSRF_HEADER)):
            raise HTTPException(403, tr("http.csrf_invalid", profile))
        return user

    def _owned(user: dict, thread_id: str) -> dict:
        # un hilo ajeno o inexistente responde igual: 404, para no revelar que existe
        row = appdata.threads.get(thread_id)
        if row is None or row["user_id"] != user["user_id"]:
            raise HTTPException(404, tr("http.thread_not_found", profile))
        return row

    def _cookie_secure(request: Request) -> bool:
        return settings.cookie_secure in ("1", "true", "yes") or (
            settings.cookie_secure == "auto" and request.url.scheme == "https")

    def _session_response(request: Request, user: dict, token: str) -> JSONResponse:
        resp = JSONResponse({"user": {"display_name": user["display_name"], "email": user["email"]},
                             "csrf": csrf_for(token)})
        resp.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_days * 86400, httponly=True,
                        samesite="lax", secure=_cookie_secure(request), path="/")
        return resp

    def _auth_error(exc: AuthError) -> HTTPException:
        return HTTPException(exc.status, exc.message)

    # TURN_METRICS: cada turno deja su fila (sin contenido de mensajes) en la base de negocio
    observer = appdata.turn_metrics.add if settings.turn_metrics else None

    def sse(payload, thread_id: str, user_id: str, esfuerzo: str | None = None, origen: str = "auto"):
        extra = {"observer": observer} if observer else {}
        events = (f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n" for event in
                  agent_mod.stream_events(agent, payload, thread_id, user_id, settings, esfuerzo, origen, **extra))
        return with_keepalive(events, settings.sse_ping_seconds)

    def sse_response(gen):
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/")
    def index():
        return FileResponse(profile.static_dir / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "model": settings.llm_model, "auth_enabled": settings.auth_enabled}

    @app.post("/chat")
    def chat(body: ChatIn, request: Request):
        if settings.max_message_chars and len(body.message) > settings.max_message_chars:
            raise HTTPException(413, tr("http.message_too_long", profile, max=f"{settings.max_message_chars:,}"
                                        .replace(",", tr("format.thousands_sep", profile))))
        user_id = body.user_id
        if auth:  # el user_id sale de la sesión, nunca del navegador
            user = _changing(request)
            row = _owned(user, body.thread_id)
            appdata.threads.touch(body.thread_id, None if row["title"] else thread_title(body.message))
            user_id = user["user_id"]
        payload = {"messages": [{"role": "user", "content": body.message}]}
        if settings.files_enabled and body.file_ids:
            payload = {"messages": [_message_with_files(body, user_id)]}
        esfuerzo, origen = agent_mod.elegir_esfuerzo(settings, body.message, body.effort, classify)
        return sse_response(sse(payload, body.thread_id, user_id, esfuerzo, origen))

    @app.post("/resume")
    def resume(body: ResumeIn, request: Request):
        user_id = body.user_id
        if auth:
            user = _changing(request)
            _owned(user, body.thread_id)
            appdata.threads.touch(body.thread_id)
            user_id = user["user_id"]
        return sse_response(sse(Command(resume={"decisions": body.decisions}), body.thread_id, user_id))

    @app.get("/history/{thread_id}")
    def history(thread_id: str, request: Request):
        if auth:
            _owned(_user(request), thread_id)
        return {"thread_id": thread_id, "messages": agent_mod.get_history(agent, thread_id, settings)}

    # ---------------------------------------------------------------- cuentas (AUTH_ENABLED=1)
    @app.get("/auth/me")
    def auth_me(request: Request):
        if not auth:
            return {"auth_enabled": False}
        user = auth.session_user(_token(request))
        if user is None:
            return {"auth_enabled": True, "user": None}
        return {"auth_enabled": True, "user": {"display_name": user["display_name"], "email": user["email"]},
                "csrf": csrf_for(_token(request))}

    def _require_auth():
        if not auth:
            raise HTTPException(404, tr("http.accounts_disabled", profile))

    @app.post("/auth/register")
    def auth_register(body: RegisterIn, request: Request):
        _require_auth()
        _same_origin(request)
        try:
            auth.register(body.email, body.password, body.display_name)
            user, token = auth.login(body.email, body.password, request.client.host if request.client else "")
        except AuthError as exc:
            raise _auth_error(exc) from None
        return _session_response(request, user, token)

    @app.post("/auth/login")
    def auth_login(body: LoginIn, request: Request):
        _require_auth()
        _same_origin(request)
        try:
            user, token = auth.login(body.email, body.password, request.client.host if request.client else "")
        except AuthError as exc:
            raise _auth_error(exc) from None
        return _session_response(request, user, token)

    @app.post("/auth/logout")
    def auth_logout(request: Request):
        _require_auth()
        if auth.session_user(_token(request)) is not None:
            _changing(request)
            auth.logout(_token(request))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    @app.post("/auth/delete-account")
    def auth_delete_account(body: PasswordIn, request: Request):
        """Borra la cuenta y TODO lo suyo: primero la base de la IA (hilos y memoria global), luego la de negocio."""
        _require_auth()
        user = _changing(request)
        if not auth.check_password(user, body.password):
            raise HTTPException(401, tr("http.wrong_password", profile))
        uid = user["user_id"]
        threads = [t["thread_id"] for t in appdata.threads.list_for_user(uid)]
        ai_data.delete_user_ai_data(agent.checkpointer, store, uid, threads)
        if store is not None:  # archivos adjuntos (también los subidos cuando FILES_ENABLED estaba encendido)
            from assistant.core.files import store as fstore

            fstore.delete_user(store, uid)
        appdata.turn_metrics.delete_for_user(uid)
        appdata.feedback.delete_for_user(uid)
        appdata.sessions.delete_for_user(uid)
        appdata.threads.delete_for_user(uid)
        appdata.attempts.clear(f"email:{user['email']}")
        appdata.users.delete(uid)
        resp = JSONResponse({"deleted": True, "threads": len(threads)})
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    # ---------------------------------------------------------------- conversaciones del usuario
    @app.get("/threads")
    def list_threads(request: Request):
        _require_auth()
        user = _user(request)
        return {"threads": [{"thread_id": t["thread_id"], "title": t["title"],
                             "created_at": t["created_at"].isoformat(),
                             "last_activity": t["last_activity"].isoformat()}
                            for t in appdata.threads.list_for_user(user["user_id"])]}

    @app.post("/threads")
    def new_thread(request: Request):
        _require_auth()
        user = _changing(request)
        row = appdata.threads.create(uuid.uuid4().hex, user["user_id"])
        return {"thread_id": row["thread_id"], "title": ""}

    @app.patch("/threads/{thread_id}")
    def rename_thread(thread_id: str, body: RenameIn, request: Request):
        """Renombra la conversación (solo el dueño). Solo cambia la fila de negocio; no llama al modelo."""
        _require_auth()
        user = _changing(request)
        _owned(user, thread_id)
        title = clean_title(body.title)
        if title is None:
            raise HTTPException(400, tr("http.title_length", profile, max=MAX_TITLE_CHARS))
        appdata.threads.rename(thread_id, title)
        return {"thread_id": thread_id, "title": title}

    @app.delete("/threads/{thread_id}")
    def delete_thread(thread_id: str, request: Request):
        """Borra la conversación en la base de la IA (checkpoints, resumen, métricas) y su fila en la de negocio."""
        _require_auth()
        user = _changing(request)
        _owned(user, thread_id)
        ai_data.delete_thread(agent.checkpointer, thread_id)
        if store is not None:
            from assistant.core.files import store as fstore

            fstore.delete_thread(store, user["user_id"], thread_id)
        appdata.turn_metrics.delete_for_thread(thread_id)
        appdata.feedback.delete_for_thread(thread_id)
        appdata.threads.delete(thread_id)
        return {"deleted": thread_id}

    base_tokens = (getattr(agent, "base_context_tokens", None)
                   or context_mod.prompt_tokens(agent_mod.system_prompt_text(settings, profile)))
    can_compact = getattr(agent, "compactor", None) is not None

    @app.get("/threads/{thread_id}/context")
    def thread_context(thread_id: str, request: Request):
        """Medidor de contexto del hilo, desde su checkpoint (sin llamar al modelo)."""
        if auth:
            _owned(_user(request), thread_id)
        values = agent.get_state(agent_mod.run_config(thread_id, settings)).values or {}
        return {"thread_id": thread_id, **context_mod.context_report(values, settings, base_tokens, can_compact)}

    @app.post("/threads/{thread_id}/compact")
    def compact(thread_id: str, request: Request):
        """Compactación manual ("Compactar ahora"): resume la parte más antigua del hilo."""
        if auth:
            _owned(_changing(request), thread_id)
        try:
            record = agent_mod.compact_thread(agent, thread_id, settings)
        except ValueError as exc:
            raise HTTPException(501, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"thread_id": thread_id, "compacted": record is not None, "record": record}

    def _store():
        if store is None:
            raise HTTPException(503, tr("http.store_unavailable", profile))
        return store

    # Con AUTH_ENABLED=1 los recuerdos son los del usuario de la sesión (/me/memories); las rutas con {user_id} (texto
    # libre del navegador, app local sin cuentas) solo existen con AUTH_ENABLED=0.
    @app.get("/me/memories")
    def my_memories(request: Request):
        _require_auth()
        return {"memories": memory.list_memories(_store(), _user(request)["user_id"])}

    @app.delete("/me/memories/{key}")
    def delete_my_memory(key: str, request: Request):
        _require_auth()
        if not memory.delete_memory(_store(), _changing(request)["user_id"], key):
            raise HTTPException(404, tr("http.memory_not_found", profile))
        return {"deleted": key}

    # ---------------------------------------------------------------- archivos (FILES_ENABLED=1)
    def _file_owner(request: Request, thread_id: str, user_id: str, changing: bool) -> str:
        """user_id dueño de los archivos del hilo: el de la sesión (y el hilo debe ser suyo) o, sin cuentas, el que
        manda la página, como en /chat."""
        if not auth:
            return user_id
        user = _changing(request) if changing else _user(request)
        _owned(user, thread_id)
        return user["user_id"]

    def _message_with_files(body: ChatIn, user_id: str):
        from assistant.core.files import user_message
        from assistant.core.files import store as fstore

        ids = list(dict.fromkeys(body.file_ids))
        if len(ids) > settings.file_max_per_message:
            raise HTTPException(400, tr("files.too_many", profile, max=settings.file_max_per_message))
        metas, images = [], {}
        for fid in ids:
            meta = fstore.get(_store(), user_id, body.thread_id, fid)
            if meta is None:
                raise HTTPException(404, tr("files.not_found", profile))
            metas.append(meta)
            if (img := fstore.image(store, user_id, body.thread_id, fid)) is not None:
                images[fid] = img
        return user_message(body.message, metas, images)

    if settings.files_enabled:
        _install_file_routes(app, settings, profile, _store, _file_owner)

    # ---------------------------------------------------------------- métricas (TURN_METRICS=1)
    if settings.turn_metrics:
        @app.get("/metrics/summary")
        def metrics_summary(request: Request, days: int = 7):
            """Resumen de los turnos de los últimos `days` días: con cuentas, solo los del usuario de la sesión; sin
            cuentas (app local), todos."""
            from datetime import datetime, timedelta, timezone

            from assistant.core.metrics import summarize

            days = max(1, min(days, 365))
            uid = _user(request)["user_id"] if auth else None
            since = datetime.now(timezone.utc) - timedelta(days=days)
            out = {"days": days, **summarize(appdata.turn_metrics.since(since, uid))}
            if settings.feedback_enabled:
                scores = [f.get("score") for f in appdata.feedback.since(since, uid)]
                out["feedback"] = {"up": scores.count(1), "down": scores.count(-1)}
            return out

    @app.get("/memories/{user_id}")
    def list_memories(user_id: str):
        if auth:
            raise HTTPException(404, "Not Found")
        return {"user_id": user_id, "memories": memory.list_memories(_store(), user_id)}

    @app.delete("/memories/{user_id}/{key}")
    def delete_memory(user_id: str, key: str):
        if auth or not memory.delete_memory(_store(), user_id, key):
            raise HTTPException(404, tr("http.memory_not_found", profile))
        return {"deleted": key}

    return app


def _install_file_routes(app: FastAPI, settings: Settings, profile, get_store, owner) -> None:
    """Rutas de FILES_ENABLED. Solo se registran con el interruptor (con el default, las rutas no cambian)."""
    from assistant.core.i18n import FILE_TEXTS

    for module in ("pypdf", "openpyxl", "docx", "PIL", "multipart"):
        try:
            __import__(module)
        except ImportError as exc:
            raise ConfigError(tr("startup.files_missing_deps", profile, module=module)) from exc
    if missing := [k for k in FILE_TEXTS if k not in profile.texts]:
        raise ConfigError(f"El perfil {profile.name!r} no trae los textos de archivos: {', '.join(missing)}")

    import hashlib

    from fastapi import File, Form, UploadFile

    from assistant.core.files import store as fstore
    from assistant.core.files.extract import extract
    from assistant.core.files.validate import FileRejected, validate

    def rejected(exc: FileRejected) -> HTTPException:
        status = 413 if exc.code == "too_large" else 415 if exc.code in ("type_not_allowed", "content_mismatch")             else 422
        return HTTPException(status, tr(f"files.{exc.code}", profile, **exc.values))

    @app.get("/files/config")
    def files_config():
        from assistant.core.files.validate import ALLOWED

        return {"max_bytes": settings.file_max_bytes, "max_per_message": settings.file_max_per_message,
                "extensions": sorted(e for exts, _ in ALLOWED.values() for e in exts)}

    @app.post("/threads/{thread_id}/files")
    def upload_file(thread_id: str, request: Request, file: UploadFile = File(...), user_id: str = Form("anon")):
        uid = owner(request, thread_id, user_id, True)
        data = file.file.read(settings.file_max_bytes + 1)  # nunca más del tope en memoria
        try:
            kind, mime, name = validate(data, file.filename or "", settings.file_max_bytes)
            extracted = extract(data, kind, settings)
        except FileRejected as exc:
            raise rejected(exc) from exc
        meta = fstore.save(get_store(), uid, thread_id, name, kind, mime, len(data),
                           hashlib.sha256(data).hexdigest(), extracted)
        log.info("Archivo %s (%s, %d bytes, %d páginas) en el hilo %s", meta["file_id"], kind, len(data),
                 meta["pages"], thread_id)  # sin el nombre ni el contenido
        return {k: meta[k] for k in ("file_id", "name", "kind", "size", "pages", "chars", "truncated")}

    @app.get("/threads/{thread_id}/files")
    def list_files(thread_id: str, request: Request, user_id: str = "anon"):
        uid = owner(request, thread_id, user_id, False)
        return {"files": [{k: m[k] for k in ("file_id", "name", "kind", "size", "pages", "chars", "truncated")}
                          for m in fstore.list_files(get_store(), uid, thread_id)]}

    @app.delete("/threads/{thread_id}/files/{file_id}")
    def delete_file(thread_id: str, file_id: str, request: Request, user_id: str = "anon"):
        uid = owner(request, thread_id, user_id, True)
        if not fstore.delete(get_store(), uid, thread_id, file_id):
            raise HTTPException(404, tr("files.not_found", profile))
        return {"deleted": file_id}


def __getattr__(name: str):
    # ponytail: `app` se crea perezosamente para que importar el módulo (tests) no conecte a Mongo/OpenAI.
    if name != "app":
        raise AttributeError(name)
    try:
        globals()["app"] = create_app()
    except ConfigError as e:
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    return globals()["app"]
