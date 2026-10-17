"""FastAPI: chat con streaming SSE, historial y reanudación human-in-the-loop."""
import contextvars
import json
import logging
import queue
import sys
import threading
import uuid
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from assistant import agent as agent_mod
from assistant import ai_data
from assistant import context as context_mod
from assistant import memory
from assistant.appdata import MAX_TITLE_CHARS, clean_title, thread_title
from assistant.auth import (CSRF_HEADER, RESET_BODY, RESET_DONE, RESET_SENT, RESET_SUBJECT, SESSION_COOKIE, AuthError,
                            AuthService, csrf_for, csrf_ok)
from assistant.config import ROOT, ConfigError, Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("assistant")


class ChatIn(BaseModel):
    message: str
    thread_id: str
    user_id: str = "anon"
    effort: str | None = None  # bajo/medio/alto desde el selector de la UI; None o "auto" = clasificador


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


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str


def _build_real_agent(settings: Settings):
    """Devuelve (agente, store de recuerdos)."""
    client = memory.startup_checks(settings)
    from assistant.tools import build_tools

    model = agent_mod.make_model(settings)
    checkpointer = memory.build_checkpointer(client, settings.mongodb_db)
    store = memory.build_store(client, settings.mongodb_db, settings.memory_semantic, settings.openai_api_key)
    if settings.use_bigtool:
        from assistant.bigtool_agent import BIGTOOL_PROMPT, build_bigtool_agent

        log.info("Agente: langgraph-bigtool (demo tools: %s)", settings.bigtool_demo_tools)
        # antes de buscar solo ve retrieve_tools
        agent_mod.check_turn_cap(settings, extra_prompt=BIGTOOL_PROMPT)
        agent = build_bigtool_agent(model, settings, checkpointer=checkpointer, memories_store=store)
        # bigtool no tiene medidor en vivo: el endpoint usa el uso real guardado
        agent.base_context_tokens = context_mod.prompt_tokens(agent_mod.system_prompt_text(settings) + BIGTOOL_PROMPT)
        return agent, store
    tools = build_tools(model, settings)
    agent_mod.check_turn_cap(settings, tools)
    return agent_mod.build_agent(model, tools, settings, checkpointer=checkpointer, store=store), store


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
               mailer=None) -> FastAPI:
    """`appdata`: base de negocio (AUTH_ENABLED); `mailer`: envío de correo (PASSWORD_RESET_ENABLED). Se inyectan en
    tests."""
    settings = settings or Settings.from_env()
    if classify is None:
        # agente inyectado (tests) → sin llamadas reales a OpenAI para clasificar
        classify = agent_mod.clasificar_esfuerzo if agent is None else (lambda s, m: "medio")
    if agent is None:
        agent, store = _build_real_agent(settings)
        host = settings.mongodb_uri.rsplit("@", 1)[-1]  # nunca loguear usuario/contraseña
        log.info("Modelo: %s | MongoDB IA: %s (db %s)", settings.llm_model, host, settings.mongodb_db)
        if appdata is None and (app_client := memory.app_startup(settings)) is not None:
            from assistant.appdata.mongo import MongoAppData

            appdata = MongoAppData(app_client, settings.app_mongodb_db)
            log.info("MongoDB negocio: %s (db %s)", settings.app_mongodb_uri.rsplit("@", 1)[-1],
                     settings.app_mongodb_db)
    if settings.auth_enabled and appdata is None:
        raise ConfigError("AUTH_ENABLED=1 necesita la base de negocio (APP_MONGODB_URI y APP_MONGODB_DB).")
    auth = AuthService(appdata, settings.session_ttl_days, settings.login_max_fails,
                       settings.login_lock_minutes, settings.login_max_fails_ip) if settings.auth_enabled else None
    reset_on = settings.auth_enabled and settings.password_reset_enabled
    if reset_on and mailer is None:
        if not (settings.smtp_host and settings.smtp_from):
            raise ConfigError("PASSWORD_RESET_ENABLED=1 necesita SMTP_HOST y SMTP_FROM para enviar el enlace.")
        from assistant.mailer import SmtpMailer

        mailer = SmtpMailer(settings)

    app = FastAPI(title="Agente 0")

    # ---------------------------------------------------------------- sesión y propiedad (AUTH_ENABLED=1)
    def _token(request: Request) -> str | None:
        return request.cookies.get(SESSION_COOKIE)

    def _user(request: Request) -> dict:
        user = auth.session_user(_token(request))
        if user is None:
            raise HTTPException(401, "Inicia sesión para continuar.")
        return user

    def _same_origin(request: Request) -> None:
        # CSRF (1/2): las peticiones que cambian estado deben venir de esta misma página
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if urlparse(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Origen no permitido.")

    def _changing(request: Request) -> dict:
        """Usuario de una petición que cambia estado: mismo origen, sesión y cabecera CSRF (2/2)."""
        _same_origin(request)
        user = _user(request)
        if not csrf_ok(_token(request), request.headers.get(CSRF_HEADER)):
            raise HTTPException(403, "Falta el token CSRF o no es válido.")
        return user

    def _owned(user: dict, thread_id: str) -> dict:
        # un hilo ajeno o inexistente responde igual: 404, para no revelar que existe
        row = appdata.threads.get(thread_id)
        if row is None or row["user_id"] != user["user_id"]:
            raise HTTPException(404, "Conversación no encontrada.")
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

    def sse(payload, thread_id: str, user_id: str, esfuerzo: str | None = None, origen: str = "auto"):
        events = (f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n" for event in
                  agent_mod.stream_events(agent, payload, thread_id, user_id, settings, esfuerzo, origen))
        return with_keepalive(events, settings.sse_ping_seconds)

    def sse_response(gen):
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "model": settings.llm_model, "auth_enabled": settings.auth_enabled}

    @app.post("/chat")
    def chat(body: ChatIn, request: Request):
        user_id = body.user_id
        if auth:  # el user_id sale de la sesión, nunca del navegador
            user = _changing(request)
            row = _owned(user, body.thread_id)
            appdata.threads.touch(body.thread_id, None if row["title"] else thread_title(body.message))
            user_id = user["user_id"]
        payload = {"messages": [{"role": "user", "content": body.message}]}
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
            return {"auth_enabled": True, "password_reset": reset_on, "user": None}
        return {"auth_enabled": True, "password_reset": reset_on,
                "user": {"display_name": user["display_name"], "email": user["email"]},
                "csrf": csrf_for(_token(request))}

    def _require_auth():
        if not auth:
            raise HTTPException(404, "Las cuentas no están activadas (AUTH_ENABLED=0).")

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

    def _send_reset(to: str, name: str, link: str):
        try:
            mailer.send(to, RESET_SUBJECT, RESET_BODY.format(name=name, link=link))
        except Exception as exc:  # noqa: BLE001 - el usuario ya recibió la respuesta genérica
            log.warning("No se pudo enviar el correo de recuperación (%s)", type(exc).__name__)

    @app.post("/auth/forgot")
    def auth_forgot(body: ForgotIn, request: Request, tasks: BackgroundTasks):
        """Pide un enlace para cambiar la contraseña. Responde siempre lo mismo; el correo sale después de responder
        (en segundo plano), así el tiempo de respuesta tampoco revela si el correo existe."""
        _require_auth()
        if not reset_on:
            raise HTTPException(404, "La recuperación de contraseña no está activada.")
        _same_origin(request)
        found = auth.request_reset(body.email, request.client.host if request.client else "")
        if found:
            user, token = found
            base = (settings.app_base_url or str(request.base_url)).rstrip("/")
            # el token va en el fragmento (#): el navegador no lo manda al servidor, no queda en ningún log
            tasks.add_task(_send_reset, user["email"], user["display_name"], f"{base}/#reset={token}")
        return {"ok": True, "message": RESET_SENT}

    @app.post("/auth/reset")
    def auth_reset(body: ResetIn, request: Request):
        _require_auth()
        if not reset_on:
            raise HTTPException(404, "La recuperación de contraseña no está activada.")
        _same_origin(request)
        try:
            auth.reset_password(body.token, body.password)
        except AuthError as exc:
            raise _auth_error(exc) from None
        resp = JSONResponse({"ok": True, "message": RESET_DONE})
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

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
            raise HTTPException(401, "La contraseña no es correcta.")
        uid = user["user_id"]
        threads = [t["thread_id"] for t in appdata.threads.list_for_user(uid)]
        ai_data.delete_user_ai_data(agent.checkpointer, store, uid, threads)
        appdata.sessions.delete_for_user(uid)
        appdata.resets.delete_for_user(uid)
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
            raise HTTPException(400, f"El título debe tener entre 1 y {MAX_TITLE_CHARS} caracteres.")
        appdata.threads.rename(thread_id, title)
        return {"thread_id": thread_id, "title": title}

    @app.delete("/threads/{thread_id}")
    def delete_thread(thread_id: str, request: Request):
        """Borra la conversación en la base de la IA (checkpoints, resumen, métricas) y su fila en la de negocio."""
        _require_auth()
        user = _changing(request)
        _owned(user, thread_id)
        ai_data.delete_thread(agent.checkpointer, thread_id)
        appdata.threads.delete(thread_id)
        return {"deleted": thread_id}

    base_tokens = (getattr(agent, "base_context_tokens", None)
                   or context_mod.prompt_tokens(agent_mod.system_prompt_text(settings)))
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
            raise HTTPException(503, "El almacén de recuerdos no está disponible")
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
            raise HTTPException(404, "Recuerdo no encontrado")
        return {"deleted": key}

    @app.get("/memories/{user_id}")
    def list_memories(user_id: str):
        if auth:
            raise HTTPException(404, "Not Found")
        return {"user_id": user_id, "memories": memory.list_memories(_store(), user_id)}

    @app.delete("/memories/{user_id}/{key}")
    def delete_memory(user_id: str, key: str):
        if auth or not memory.delete_memory(_store(), user_id, key):
            raise HTTPException(404, "Recuerdo no encontrado")
        return {"deleted": key}

    return app


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
