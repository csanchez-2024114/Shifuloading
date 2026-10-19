"""
Punto de entrada principal de HyperShifu API V2.
Arquitectura: Manejo de ciclo de vida (Lifespan),
Seguridad Global (CORS, Rate Limiting, Exception Handling),
Registro dinámico de agentes LangGraph y Orquestación OAuth Multicuenta.
"""

import os
import re
import logging
import logging.handlers
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi

import redis.asyncio as redis
from dotenv import load_dotenv

# [INTEGRACIÓN DE SEGURIDAD] - Rate Limiting
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter

# Importación de la Configuración Centralizada
from config import Config
from app.core.mongo import init_mongo, close_mongo, get_sync_client
from langgraph.checkpoint.mongodb import MongoDBSaver
from app.agent.shifu_base_v1.registry import init_v1_graphs, get_v1_graph
from app.services.workflow_run_service import set_stream_client

# ==========================================
#  IMPORTACIONES DE TODAS LAS RUTAS
# ==========================================

# 1. Rutas Core & Auth
from app.routes.conversations.conversation_routes_fastapi import (
    router as conversations_router,
)

from app.routes.webhooks.webhook_inbound import router as webhook_inbound_router
from app.routes.me.me import router as me_router
from app.routes.me.secrets import router as me_secrets_router
from app.routes.me.analytics import router as me_analytics_router
from app.routes.me.notifications import router as me_notifications_router
from app.routes.crm.crmRoutes import router as crm_router
from app.routes.workflows.workflows import router as workflows_router
from app.routes.connectors.customRequestRoutes import router as custom_connector_router
from app.routes.ws.workflow_ws import router as workflow_ws_router
from app.routes.ws.debug_ws import router as shifu_debug_ws_router
from app.routes.chat.chat import router as shifu_chat_router
from app.routes.me.files import router as files_router
from app.routes.internal.functions import router as functions_router
from app.routes.workflows.run import router as workflow_run_router
from app.routes.workflows.webhook import router as workflow_webhook_router

from app.workers.workflow_worker import worker as workflow_worker
from app.workers.scheduler_worker import scheduler as scheduler_worker
from app.workers.trigger_poller import trigger_poller
from app.workers.proactive_notifier import proactive_notifier
from app.workers.learning_reflection_worker import learning_reflection_worker
from app.routes.processes.processes import router as process_query_router
from app.routes.processes.history import router as process_history_router

from app.routes.auth.authRoutes import router as auth_router
from app.routes.onboarding.onboardingRoutes import router as onboarding_router
from app.routes.workspaces.workspaceRoutes import router as workspaces_router
from app.routes.auth.forgot_password import (
    router as forgot_password_router,
)  # Rutas de recuperación

# 2. Rutas de API Externas & Varios
from app.routes.gmail.disable_webhook import router as disable_gmail_router
from app.routes.proxy.proxyRoutes import router as proxy_router
from app.routes.uploads.cloudinary_routes import router as cloudinary_router
from app.routes.contact.contact import router as contact_router
from app.routes.blog.blogMain import router as blog_router
from app.routes.users import connected_accounts  # [NUEVO]: Gestión Multicuentas

# 3. Rutas Legacy V1 & Generales
from app.routes.users.userRoutes import router as user_router
from app.routes.social.announcements import admin_router as announcements_admin_router, me_router as announcements_me_router
from app.routes.integrations.integrationRoutes import router as integration_router
from app.routes.secretary.secretaryPostRoutes import router as secretary_post_router
from app.routes.secretary.secretaryGetRoutes import router as secretary_get_router
from app.routes.integrations.catalog_apps_routes import router as catalog_router
from app.routes.users.referralsRoutes import router as referrals_router
from app.routes.social.rewardRoutes import (
    router as reward_router,
    admin_router as reward_admin_router,
    challenge_router as reward_challenge_router,
    streak_router as reward_streak_router,
    me_router as reward_me_router,
)
from app.routes.billing.billing_routes import router as stripe_router
from app.routes.secretary.last_messages import router as messages_router
from app.integrations.providers.whatsapp import router as whatsapp_router

# 4. Rutas de Autenticación (OAuth) — ahora desde app/integrations/providers/
from app.integrations.providers.jira import router as jira_auth_router
from app.integrations.providers.trello import router as trello_auth_router
from app.integrations.providers.slack import router as slack_auth_router
from app.integrations.providers.monday import router as monday_auth_router
from app.integrations.providers.notion import router as notion_auth_router
from app.integrations.providers.salesforce import router as salesforce_auth_router
from app.integrations.providers.kick import router as kick_auth_router
from app.integrations.providers.tiktok import router as tiktok_auth_router
from app.integrations.providers.brevo import router as brevo_auth_router
from app.integrations.providers.mailchimp import router as mailchimp_auth_router
from app.integrations.providers.twitter import router as twitter_auth_router
from app.integrations.providers.telegram import router as telegram_auth_router
from app.integrations.providers.threads import router as threads_auth_router
from app.integrations.providers.onlyfans import router as onlyfans_auth_router
from app.integrations.providers.ubereats import router as ubereats_auth_router
from app.integrations.providers.pedidosya import router as pedidosya_auth_router
from app.integrations.providers.facebook import router as facebook_auth_router
from app.integrations.providers.instagram import router as instagram_auth_router
from app.integrations.providers.hubspot import router as hubspot_auth_router
from app.integrations.providers.discord import router as discord_auth_router
from app.integrations.providers.linkedin import router as linkedin_auth_router
from app.integrations.providers.teams import router as teams_auth_router
from app.integrations.providers.onedrive import router as onedrive_auth_router
from app.integrations.providers.outlook import router as outlook_auth_router
from app.integrations.providers.dropbox import router as dropbox_auth_router
from app.integrations.providers.clickup import router as clickup_auth_router
from app.integrations.providers.google import router as google_auth_router
from app.integrations.providers.asana import router as asana_auth_router

# --- CONFIGURACIÓN DE LOGGING ---
class _ColoredFormatter(logging.Formatter):
    """ANSI-colored console formatter. No external dependencies."""
    _RESET  = "\033[0m"
    _GREY   = "\033[90m"
    _LEVEL  = {
        "DEBUG":    "\033[36m",    # cyan
        "INFO":     "\033[32m",    # green
        "WARNING":  "\033[1;33m",  # bold yellow
        "ERROR":    "\033[1;31m",  # bold red
        "CRITICAL": "\033[1;41m",  # bold white on red bg
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self._LEVEL.get(record.levelname, self._RESET)
        fmt = (
            f"{self._GREY}%(asctime)s{self._RESET} "
            f"{color}%(levelname)-8s{self._RESET} "
            f"{self._GREY}%(name)s{self._RESET}: "
            f"%(message)s"
        )
        return logging.Formatter(fmt, datefmt="%H:%M:%S").format(record)

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
_root = logging.getLogger()
_root.setLevel(getattr(logging, log_level, logging.INFO))

# Console — colored
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ColoredFormatter())
_root.addHandler(_console_handler)

# Rotating file handlers
_logs_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_logs_dir, exist_ok=True)

_plain_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

# Full log — cleared on every restart so it only contains the current session
_app_log_path = os.path.join(_logs_dir, "app.log")
open(_app_log_path, "w", encoding="utf-8").close()  # truncate on startup
_app_handler = logging.FileHandler(_app_log_path, mode="a", encoding="utf-8")
_app_handler.setLevel(logging.INFO)
_app_handler.setFormatter(_plain_fmt)
_root.addHandler(_app_handler)

# Error-only — max 5 MB, 3 backups
_error_handler = logging.handlers.RotatingFileHandler(
    os.path.join(_logs_dir, "errors.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_error_handler.setLevel(logging.ERROR)
_error_handler.setFormatter(_plain_fmt)
_root.addHandler(_error_handler)

logger = logging.getLogger(__name__)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)

load_dotenv()


async def _worker_monitor(
    db,
    redis_url: str,
    worker_tasks: dict,
    worker_factories: dict,
) -> None:
    """
    WorkerMonitor — checks worker heartbeats every 60s and restarts dead tasks.

    A worker is considered dead if its Redis heartbeat key (TTL=120s, written every 60s)
    has expired AND its asyncio Task has completed (crashed or returned unexpectedly).
    Restarted workers re-register their own heartbeat via worker_heartbeat().
    """
    import redis.asyncio as aioredis
    r = None
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        while True:
            await asyncio.sleep(60)
            for name, task in list(worker_tasks.items()):
                key = f"worker:heartbeat:{name}"
                try:
                    alive = await r.exists(key)
                except Exception as exc:
                    logger.debug("[WorkerMonitor] Redis error checking %s: %s", name, exc)
                    continue
                if not alive and task.done():
                    logger.warning(
                        "[WorkerMonitor] Worker '%s' heartbeat missing and task dead — restarting",
                        name,
                    )
                    try:
                        factory = worker_factories[name]
                        worker_tasks[name] = asyncio.create_task(factory(db))
                        logger.info("[WorkerMonitor] Worker '%s' restarted.", name)
                    except Exception as exc:
                        logger.error("[WorkerMonitor] Failed to restart '%s': %s", name, exc)
                elif not alive:
                    logger.warning(
                        "[WorkerMonitor] Worker '%s' heartbeat missing (task still running).",
                        name,
                    )
    except asyncio.CancelledError:
        pass
    finally:
        if r:
            await r.aclose()


# --- LIFESPAN (GESTIÓN DE RECURSOS) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y cierre de recursos sin bloqueos."""
    logger.info(" Iniciando HyperShifu Backend...")

    # El CRM con IA importa langchain (en frío tarda decenas de segundos): se adelanta en segundo plano para que nadie lo espere.
    import threading as _hilo
    from app.crm import diseno as _diseno_crm
    _hilo.Thread(target=_diseno_crm.precalentar, daemon=True, name="precalentar-crm").start()

    # 1. Validación de Seguridad Crítica
    if not Config.SECRET_KEY or Config.SECRET_KEY == "mysecretkey":
        if Config.ENVIRONMENT == "production":
            logger.error(" ERROR FATAL: SECRET_KEY no segura en producción.")
            raise ValueError("SECRET_KEY robusta es obligatoria.")

    app.state.secret_key = Config.SECRET_KEY

    # 2. Validación de Webhook Secret (DEBUG)
    if Config.WEBHOOK_SECRET:
        logger.info(f" ✅ WEBHOOK_SECRET configurado: {Config.WEBHOOK_SECRET[:20]}...")
    else:
        logger.warning(" ⚠️ WEBHOOK_SECRET no está configurado. Los webhooks fallarán.")

    # 2. Conexión global a MongoDB
    try:
        await init_mongo(app)
        if hasattr(app.state, "db"):
            logger.info(f" MongoDB conectado: {app.state.db.name}")
        else:
            logger.warning(
                " init_mongo se ejecutó, pero app.state.db no está definido."
            )
        # Crear índices — cada grupo en su propio try para aislar fallos
        for _col, _spec, _opts, _label in [
            ("langgraph_pending_states", [("expires_at", 1)],
             {"expireAfterSeconds": 0, "name": "idx_langgraph_pending_states_expires_at"}, "TTL expires_at"),
            ("langgraph_pending_states", [("resume_token", 1)],
             {"unique": True, "name": "idx_langgraph_pending_states_resume_token"}, "resume_token"),
            ("agent_session_state", [("user_id", 1), ("conversation_id", 1)],
             {"unique": True, "name": "idx_agent_session_state_user_conv"}, "agent_session_state"),
            # name matches what create_indexes.py already created — avoids IndexOptionsConflict (code 85)
            ("user_active_goals", [("user_id", 1), ("status", 1)],
             {"name": "idx_user_active_goals_by_status"}, "user_active_goals status"),
            ("user_semantic_memory", [("user_id", 1)],
             {"name": "idx_user_semantic_memory_user"}, "user_semantic_memory"),
            ("user_daily_diary", [("user_id", 1), ("date", -1)],
             {"name": "idx_user_daily_diary_user_date"}, "user_daily_diary"),
            ("user_decision_memory", [("user_id", 1), ("goal_id", 1)],
             {"name": "idx_user_decision_memory_user_goal"}, "user_decision_memory"),
            ("document_extractions", [("file_id", 1)],
             {"unique": True, "name": "idx_document_extractions_file_id"}, "document_extractions dedup"),
            ("crm_workspaces", [("user_id", 1)],
             {"unique": True, "name": "idx_crm_workspaces_user"}, "crm_workspaces un CRM por persona"),
            ("crm_conversaciones", [("user_id", 1)],
             {"unique": True, "name": "idx_crm_conversaciones_user"}, "crm_conversaciones una conversacion por persona"),
            ("crm_puntos", [("user_id", 1), ("n", 1)],
             {"unique": True, "name": "idx_crm_puntos_user_n"}, "crm_puntos puntos de deshacer por persona"),
            ("crm_logos", [("user_id", 1), ("id", 1)],
             {"unique": True, "name": "idx_crm_logos_user_id"}, "crm_logos logo del negocio por persona"),
            ("document_extractions", [("user_id", 1), ("last_used_at", -1)],
             {"name": "idx_document_extractions_user_recency"}, "document_extractions cleanup"),
        ]:
            try:
                await app.state.db[_col].create_index(_spec, **_opts)
                logger.debug("Índice asegurado: %s / %s", _col, _label)
            except Exception as e:
                logger.warning("No se pudo crear índice %s / %s: %s", _col, _label, e)
        logger.info("Índices de startup verificados.")

        # Compile shifu_graph with MongoDB checkpointer so conversation state
        # (messages, selected_accounts, available_accounts, etc.) persists
        # across turns without manual save/load in the WS handler.
        # MongoDBSaver is sync (pymongo); LangGraph wraps it in run_in_executor
        # automatically when ainvoke() is called.
        checkpointer = MongoDBSaver(
            client=get_sync_client(),
            db_name=Config.MONGO_DB_NAME,
            checkpoint_collection_name="shifu_checkpoints",
            writes_collection_name="shifu_checkpoint_writes",
        )
        init_v1_graphs(checkpointer=checkpointer)
        app.state.shifu_graph = get_v1_graph()
        logger.info("shifu_graph compilado con MongoDB checkpointer.")

    except Exception as e:
        logger.critical(f" Error al conectar con MongoDB: {e}")
        raise e

    # 3. Conexión a Redis (Async)
    if Config.REDIS_URL:
        try:
            app.state.redis = redis.from_url(Config.REDIS_URL, decode_responses=True)
            await app.state.redis.ping()
            set_stream_client(app.state.redis)
            logger.info(" Redis conectado correctamente.")
        except Exception as e:
            logger.warning(f" Redis no disponible: {e}")

    # 4. Background workers (solo si INLINE_WORKER=true)
    worker_task = None
    scheduler_task = None
    trigger_task = None

    notifier_task = None
    learning_task = None
    monitor_task = None
    if os.getenv("INLINE_WORKER", "false").lower() == "true":
        _redis_client = getattr(app.state, "redis", None)
        worker_task    = asyncio.create_task(workflow_worker.start(app.state.db, redis_client=_redis_client))
        scheduler_task = asyncio.create_task(scheduler_worker.start(app.state.db))
        trigger_task   = asyncio.create_task(trigger_poller.start(app.state.db))
        notifier_task  = asyncio.create_task(proactive_notifier.start(app.state.db))
        learning_task  = asyncio.create_task(learning_reflection_worker.start(app.state.db))

        if Config.REDIS_URL:
            _worker_task_registry = {
                "workflow_worker":       worker_task,
                "scheduler_worker":      scheduler_task,
                "trigger_poller":        trigger_task,
                "proactive_notifier":    notifier_task,
                "learning_reflection":   learning_task,
            }
            _worker_factories = {
                "workflow_worker":       lambda db: workflow_worker.start(db, redis_client=_redis_client),
                "scheduler_worker":      scheduler_worker.start,
                "trigger_poller":        trigger_poller.start,
                "proactive_notifier":    proactive_notifier.start,
                "learning_reflection":   learning_reflection_worker.start,
            }
            monitor_task = asyncio.create_task(
                _worker_monitor(app.state.db, Config.REDIS_URL, _worker_task_registry, _worker_factories)
            )
            logger.info(
                " Workers inline + ProactiveNotifier + WorkerMonitor iniciados."
            )
        else:
            logger.info(
                " Workers inline iniciados (sin WorkerMonitor — Redis no configurado)."
            )
    else:
        logger.info(" Workers externos — ejecutar worker_main.py por separado.")

    # Programador del standalone en este mismo proceso: solo con SHIFU_SCHEDULER=1.
    # Tambien corre el disparador por correo, los recordatorios y los avisos por correo.
    # claim_due_task es atomico, asi que convive con scheduler_worker sin duplicar corridas.
    standalone_scheduler_task = None
    if os.getenv("SHIFU_SCHEDULER", "") == "1":
        from app.workers.scheduler_loop import run_forever, tick_seconds_from_env

        standalone_scheduler_task = asyncio.create_task(run_forever(app.state.db, tick_seconds_from_env()))

    yield

    if standalone_scheduler_task:
        standalone_scheduler_task.cancel()
        try:
            await standalone_scheduler_task
        except asyncio.CancelledError:
            pass

    # Shutdown: Stop workers inline if running
    if worker_task:
        workflow_worker.stop()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] worker_task cancelled during shutdown")
    if scheduler_task:
        scheduler_worker.stop()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] scheduler_task cancelled during shutdown")
    if trigger_task:
        trigger_poller.stop()
        trigger_task.cancel()
        try:
            await trigger_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] trigger_task cancelled during shutdown")

    if notifier_task:
        proactive_notifier.stop()
        notifier_task.cancel()
        try:
            await notifier_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] notifier_task cancelled during shutdown")
    if learning_task:
        learning_reflection_worker.stop()
        learning_task.cancel()
        try:
            await learning_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] learning_task cancelled during shutdown")
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("[LIFESPAN] monitor_task cancelled during shutdown")

    # 4. Shutdown: Cierre de conexiones
    logger.info(" Cerrando conexiones...")
    await close_mongo(app)
    if hasattr(app.state, "redis"):
        await app.state.redis.close()
    logger.info(" Aplicación cerrada correctamente.")


# --- INSTANCIA FASTAPI ---
app = FastAPI(
    title="HyperShifu API",
    description="API backend para HyperShifu - Arquitectura Enterprise",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if Config.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if Config.ENVIRONMENT != "production" else None,
)


# --- OPENAPI / SWAGGER UI: JWT BEARER AUTH ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Pega tu JWT token (sin el prefijo 'Bearer')",
        }
    }
    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

# --- OPENTELEMETRY (activo solo si OTEL_EXPORTER_OTLP_ENDPOINT está configurado) ---
_otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if _otel_endpoint:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _provider = TracerProvider()
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_endpoint)))
    trace.set_tracer_provider(_provider)
    FastAPIInstrumentor().instrument_app(app)
    logger.info(f"OpenTelemetry tracing activo → {_otel_endpoint}")

# --- SEGURIDAD: RATE LIMITING ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- MIDDLEWARES ---

# CORS Dinámico y Seguro
allowed_origins = Config.CORS_ALLOWED_ORIGINS
allowed_origin_regex = Config.CORS_ALLOWED_ORIGIN_REGEX
logger.info(f" CORS orígenes permitidos: {allowed_origins}")
if allowed_origin_regex:
    logger.info(f" CORS regex permitido: {allowed_origin_regex}")


def _is_origin_allowed(origin: str) -> bool:
    if origin in allowed_origins:
        return True
    if allowed_origin_regex:
        try:
            return re.match(allowed_origin_regex, origin) is not None
        except re.error as regex_error:
            logger.error(f"CORS_ALLOWED_ORIGIN_REGEX invalido: {regex_error}")
    return False


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Authorization"],
)

# Protección TrustedHost
allowed_hosts = [
    "localhost",
    "127.0.0.1",
    "hypershifu.com",
    "www.hypershifu.com",
    "backend-hyper-shifu-nyzm.onrender.com",
]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


# Headers de deprecación para rutas legacy /api/v2/ y /api/v3/
@app.middleware("http")
async def deprecation_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/v2/") or path.startswith("/api/v3/"):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2027-06-01"
        response.headers["Link"] = '</api/v1/>; rel="successor-version"'
    return response


# Manejador de Errores Global
@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            f"Error en {request.method} {request.url.path}: {str(e)}", exc_info=True
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor. Proceso auditado."},
        )
        origin = request.headers.get("origin")
        if origin and _is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = (
                "Content-Type, Authorization"
            )
        return response


# --- ENDPOINTS BASE ---


_WORKER_NAMES = [
    "workflow_worker",
    "scheduler_worker",
    "trigger_poller",
    "memory_compaction",
    "learning_reflection",
    "proactive_notifier",
]


@app.get("/health")
async def health_check():
    """
    Structured health check.
    Returns mongodb, redis, and per-worker heartbeat status.
    HTTP 503 if any critical component is unhealthy.
    """
    result: dict = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": os.getenv("APP_VERSION", "2.0.0"),
    }
    unhealthy = False

    # MongoDB
    try:
        if hasattr(app.state, "mongo_client"):
            await app.state.mongo_client.admin.command("ping")
        elif hasattr(app.state, "db"):
            await app.state.db.command("ping")
        result["mongodb"] = "ok"
    except Exception as exc:
        logger.error("Health check — MongoDB error: %s", exc)
        result["mongodb"] = "error"
        unhealthy = True

    # Redis + worker heartbeats
    redis_url = getattr(Config, "REDIS_URL", None)
    if redis_url:
        try:
            _r = redis.from_url(redis_url, decode_responses=True)
            await _r.ping()
            result["redis"] = "ok"

            workers: dict = {}
            inline = os.getenv("INLINE_WORKER", "false").lower() == "true"
            if inline:
                for name in _WORKER_NAMES:
                    alive = bool(await _r.exists(f"worker:heartbeat:{name}"))
                    workers[name] = "alive" if alive else "dead"
                    if not alive:
                        logger.warning("Health check — worker '%s' heartbeat missing", name)
            result["workers"] = workers if inline else "not_started"
            await _r.aclose()
        except Exception as exc:
            logger.warning("Health check — Redis error: %s", exc)
            result["redis"] = "unavailable"
            result["workers"] = "unknown"
    else:
        result["redis"] = "not_configured"
        result["workers"] = "not_configured"

    if unhealthy:
        result["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=result)

    return result


@app.get("/")
async def root():
    return {"message": "HyperShifu API v2.0.0", "status": "running"}


# ==========================================
#  REGISTRO DE ROUTERS — SOLO /api/v1/ CANÓNICO
#  (Legacy removido según BACKEND_ENDPOINTS_V1.md §3.1)
# ==========================================

# 1. Core & Auth
app.include_router(auth_router,             prefix="/api/v1/auth",          tags=["V1 Auth"])
app.include_router(forgot_password_router,  prefix="/api/v1/auth",          tags=["V1 Auth"])
app.include_router(onboarding_router,       prefix="/api/v1/onboarding",    tags=["V1 Onboarding"])
app.include_router(user_router,             prefix="/api/v1/users",         tags=["V1 Users"])

# 2. Conversations, Processes, History
app.include_router(conversations_router,    prefix="/api/v1/conversations", tags=["V1 Conversations"])
app.include_router(process_query_router,    prefix="/api/v1/processes",     tags=["V1 Processes"])
app.include_router(process_history_router,  prefix="/api/v1/process-history", tags=["V1 Process History"])

# 3. Catalog & Integrations
app.include_router(catalog_router,          prefix="/api/v1/catalog",       tags=["V1 Catalog"])
app.include_router(integration_router,      prefix="/api/v1/integrations",  tags=["V1 Integrations"])

# 4. Secretary, Proxy, Contact, Blog, Uploads, Messages, Gmail, WhatsApp, Accounts, Referrals, Billing, Rewards
app.include_router(secretary_post_router,   prefix="/api/v1/secretary",     tags=["V1 Secretary"])
app.include_router(secretary_get_router,    prefix="/api/v1/secretary",     tags=["V1 Secretary"])
app.include_router(proxy_router,            prefix="/api/v1/proxy",         tags=["V1 Proxy"])
app.include_router(disable_gmail_router,    prefix="/api/v1/integrations/gmail", tags=["V1 Gmail"])
app.include_router(contact_router,          prefix="/api/v1/contact",       tags=["V1 Contact"])
app.include_router(blog_router,             prefix="/api/v1/blog",          tags=["V1 Blog"])
app.include_router(cloudinary_router,       prefix="/api/v1/uploads",       tags=["V1 Uploads"])
app.include_router(whatsapp_router,         prefix="/api/v1/webhooks/whatsapp", tags=["V1 WhatsApp Webhook"])
app.include_router(connected_accounts.router, prefix="/api/v1/accounts",    tags=["V1 Accounts"])
app.include_router(referrals_router,        prefix="/api/v1/referrals",     tags=["V1 Referrals"])
app.include_router(stripe_router,           prefix="/api/v1/billing",       tags=["V1 Billing"])
app.include_router(messages_router,         prefix="/api/v1/messages",      tags=["V1 Messages"])
app.include_router(announcements_admin_router, prefix="/api/v1/admin",      tags=["V1 Announcements"])
app.include_router(announcements_me_router, prefix="/api/v1/me",            tags=["V1 Announcements"])
app.include_router(reward_router,           prefix="/api/v1/rewards",       tags=["V1 Rewards"])
app.include_router(reward_admin_router,     prefix="/api/v1/admin",         tags=["V1 Rewards"])
app.include_router(reward_challenge_router, prefix="/api/v1/challenges",    tags=["V1 Rewards"])
app.include_router(reward_streak_router,    prefix="/api/v1/reward-streaks", tags=["V1 Rewards"])
app.include_router(reward_me_router,        prefix="/api/v1/me/rewards",    tags=["V1 Rewards"])

# 5. Me, Workflows, Webhooks, WebSockets
app.include_router(me_router,               prefix="/api/v1/me",            tags=["V1 Me"])
app.include_router(workspaces_router,       prefix="/api/v1/workspaces",    tags=["V1 Workspaces"])
app.include_router(me_secrets_router,       prefix="/api/v1/me/secrets",    tags=["V1 Me Secrets"])
app.include_router(me_analytics_router,     prefix="/api/v1/me/analytics",  tags=["V1 Me Analytics"])
app.include_router(me_notifications_router, prefix="/api/v1/me/notifications", tags=["V1 Me Notifications"])
app.include_router(crm_router,              prefix="/api/v1/crm",           tags=["V1 CRM"])
if os.getenv("CRM_LAB_ADAPTER", "0").strip() == "1":
    from app.routes.crm import labRoutes as _lab_routes  # noqa: E402

    app.include_router(_lab_routes.router, prefix="/api/v1/crm", tags=["V1 CRM Lab"])
app.include_router(workflows_router,        prefix="/api/v1/workflows",     tags=["V1 Workflows"])
app.include_router(custom_connector_router, prefix="/api/v1/connectors",    tags=["V1 Connectors"])
# El webhook del standalone va ANTES que webhook_inbound (misma ruta /webhooks/{token}, gana el primero):
# mismo campo webhook_token, pero con limite por IP, tope de 64 KB y el cuerpo disponible como {{trigger.campo}}.
app.include_router(workflow_webhook_router, prefix="/api/v1",               tags=["V1 Webhooks"])
app.include_router(webhook_inbound_router,  prefix="/api/v1",               tags=["V1 Webhooks"])
app.include_router(workflow_run_router,     prefix="/api/v1",               tags=["V1 Workflows"])  # POST /workflows/{id}/run, GET /workflows/runs/{id}
app.include_router(files_router,            prefix="/api/v1/files",         tags=["V1 Files"])  # adjuntos del chat
app.include_router(functions_router,        prefix="/internal",             tags=["Internal Functions"])
app.include_router(shifu_debug_ws_router,   prefix="/api/v1",               tags=["V1 Debug WS"])
app.include_router(shifu_chat_router,       prefix="/api/v1",               tags=["V1 Chat"])
app.include_router(workflow_ws_router,      prefix="/api/v1",               tags=["V1 Workflow WS"])

# 6. OAuth Providers — canónicos en /api/v1/integrations/{provider}/
#    (Solo /login y /status aquí; /callback y /disconnect son externos §4)
oauth_v1_configs = [
    (jira_auth_router, "jira", "V1 Integration Jira"),
    (trello_auth_router, "trello", "V1 Integration Trello"),
    (slack_auth_router, "slack", "V1 Integration Slack"),
    (monday_auth_router, "monday", "V1 Integration Monday"),
    (notion_auth_router, "notion", "V1 Integration Notion"),
    (salesforce_auth_router, "salesforce", "V1 Integration Salesforce"),
    (kick_auth_router, "kick", "V1 Integration Kick"),
    (tiktok_auth_router, "tiktok", "V1 Integration TikTok"),
    (brevo_auth_router, "brevo", "V1 Integration Brevo"),
    (mailchimp_auth_router, "mailchimp", "V1 Integration Mailchimp"),
    (twitter_auth_router, "twitter", "V1 Integration Twitter"),
    (telegram_auth_router, "telegram", "V1 Integration Telegram"),
    (threads_auth_router, "threads", "V1 Integration Threads"),
    (onlyfans_auth_router, "onlyfans", "V1 Integration OnlyFans"),
    (ubereats_auth_router, "ubereats", "V1 Integration UberEats"),
    (pedidosya_auth_router, "pedidosya", "V1 Integration PedidosYa"),
    (facebook_auth_router, "facebook", "V1 Integration Facebook"),
    (instagram_auth_router, "instagram", "V1 Integration Instagram"),
    (hubspot_auth_router, "hubspot", "V1 Integration HubSpot"),
    (discord_auth_router, "discord", "V1 Integration Discord"),
    (linkedin_auth_router, "linkedin", "V1 Integration LinkedIn"),
    (teams_auth_router, "teams", "V1 Integration Teams"),
    (onedrive_auth_router, "onedrive", "V1 Integration OneDrive"),
    (outlook_auth_router, "outlook", "V1 Integration Outlook"),
    (dropbox_auth_router, "dropbox", "V1 Integration Dropbox"),
    (clickup_auth_router, "clickup", "V1 Integration ClickUp"),
    (google_auth_router, "google", "V1 Integration Google"),
    (asana_auth_router, "asana", "V1 Integration Asana"),
]

for router_obj, provider_name, tag_str in oauth_v1_configs:
    app.include_router(router_obj, prefix=f"/api/v1/integrations/{provider_name}", tags=[tag_str])

# ==========================================
#  LEGACY ALIASES — SOLO CONSUMIDORES EXTERNOS (§4)
#  Controlados por flag LEGACY_ROUTES_ENABLED (default: false)
# ==========================================
LEGACY_ROUTES_ENABLED = os.getenv("LEGACY_ROUTES_ENABLED", "false").lower() == "true"

if LEGACY_ROUTES_ENABLED:
    # Stripe webhook + redirect URLs (externos)
    app.include_router(stripe_router, prefix="/api/v2/stripe", tags=["Legacy Stripe"])
    # OAuth callbacks (externos) — montar callbacks en rutas viejas
    oauth_legacy_configs = [
        (jira_auth_router, "/auth/jira", "Legacy Jira"),
        (trello_auth_router, "/auth/trello", "Legacy Trello"),
        (slack_auth_router, "/auth/slack", "Legacy Slack"),
        (monday_auth_router, "/auth/monday", "Legacy Monday"),
        (notion_auth_router, "/auth/notion", "Legacy Notion"),
        (salesforce_auth_router, "/auth/salesforce", "Legacy Salesforce"),
        (kick_auth_router, "/auth/kick", "Legacy Kick"),
        (tiktok_auth_router, "/auth/tiktok", "Legacy TikTok"),
        (brevo_auth_router, "/auth/brevo", "Legacy Brevo"),
        (mailchimp_auth_router, "/auth/mailchimp", "Legacy Mailchimp"),
        (twitter_auth_router, "/auth/twitter", "Legacy Twitter"),
        (telegram_auth_router, "/auth/telegram", "Legacy Telegram"),
        (threads_auth_router, "/auth/threads", "Legacy Threads"),
        (onlyfans_auth_router, "/auth/onlyfans", "Legacy OnlyFans"),
        (ubereats_auth_router, "/auth/ubereats", "Legacy UberEats"),
        (pedidosya_auth_router, "/auth/pedidosya", "Legacy PedidosYa"),
        (facebook_auth_router, "/auth/facebook", "Legacy Facebook"),
        (instagram_auth_router, "/auth/instagram", "Legacy Instagram"),
        (hubspot_auth_router, "/auth/hubspot", "Legacy HubSpot"),
        (discord_auth_router, "/auth/discord", "Legacy Discord"),
        (linkedin_auth_router, "/auth/linkedin", "Legacy LinkedIn"),
        (teams_auth_router, "/auth/teams", "Legacy Teams"),
        (onedrive_auth_router, "/auth/onedrive", "Legacy OneDrive"),
        (outlook_auth_router, "/auth/outlook", "Legacy Outlook"),
        (dropbox_auth_router, "/auth/dropbox", "Legacy Dropbox"),
        (clickup_auth_router, "/auth/clickup", "Legacy ClickUp"),
        (google_auth_router, "/auth/google", "Legacy Google"),
        (asana_auth_router, "/auth/asana", "Legacy Asana"),
    ]
    for router_obj, prefix_str, tag_str in oauth_legacy_configs:
        app.include_router(router_obj, prefix=prefix_str, tags=[tag_str])
    
    # WhatsApp webhook legacy
    app.include_router(whatsapp_router, prefix="/auth/whatsapp", tags=["Legacy WhatsApp"])
    
    # Webhook inbound legacy
    app.include_router(webhook_inbound_router, prefix="/api/v4", tags=["Legacy Webhook"])

# Interfaz de pruebas del agente (chat + trazas + metricas + coder): SOLO con SHIFU_DEV_UI=1. Nunca en produccion.
if os.getenv("SHIFU_DEV_UI", "").lower() in ("1", "true", "yes") and Config.ENVIRONMENT != "production":
    from fastapi.staticfiles import StaticFiles as _DevStaticFiles
    from app.routes.dev.dev_connect import router as dev_connect_router
    from app.routes.dev.metrics import router as dev_metrics_router
    from app.routes.dev.coder import router as dev_coder_router

    app.mount("/ui", _DevStaticFiles(directory=os.path.join(os.path.dirname(__file__), "ui"), html=True), name="ui")
    for _dev_router in (dev_connect_router, dev_metrics_router, dev_coder_router):
        app.include_router(_dev_router, prefix="/api/v1/dev", tags=["Dev"])

logger.info(" Registro de todas las rutas completado exitosamente.")

# --- PUNTO DE ENTRADA ---
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=(Config.ENVIRONMENT == "development"),
        log_level=log_level.lower(),
    )

