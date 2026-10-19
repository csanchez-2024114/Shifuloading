import os
import logging
import json
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger(__name__)

def get_runtime_environment() -> str:
    """Resuelve el entorno usando ENVIRONMENT y mantiene compatibilidad con FLASK_ENV."""
    return (
        os.getenv("ENVIRONMENT")
        or os.getenv("FLASK_ENV")
        or "production"
    ).strip().lower()

def _extract_db_name_from_mongo_uri(uri: str) -> Optional[str]:
    """Extrae nombre de DB desde MONGO_URI (mongodb://.../db_name)."""
    try:
        parsed = urlparse(uri)
        path = (parsed.path or "").lstrip("/")
        return path or None
    except Exception:
        return None

def _parse_origins_env(value: str) -> List[str]:
    """Parsea CORS_ALLOWED_ORIGINS aceptando CSV o JSON array."""
    raw = (value or "").strip()
    if not raw:
        return []

    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            logger.warning("CORS_ALLOWED_ORIGINS con formato JSON inválido. Se intentará parseo CSV.")

    return [origin.strip() for origin in raw.split(",") if origin.strip()]

DEFAULT_TRUSTED_HOSTS: List[str] = [
    "localhost",
    "127.0.0.1",
    "hypershifu.com",
    "www.hypershifu.com",
    "backend-hyper-shifu-nyzm.onrender.com",
]


def parse_trusted_hosts_extra(value: str) -> List[str]:
    """Hosts extra para TrustedHostMiddleware desde TRUSTED_HOSTS_EXTRA (CSV o JSON array).

    Acepta nombres simples ("crm.midominio.com"), comodines de subdominio de Starlette
    ("*.midominio.com") y, por comodidad, una URL completa (se queda solo con el host,
    sin esquema ni puerto). Un "*" solo se ignora: apagaría la protección completa.
    """
    hosts: List[str] = []
    for item in _parse_origins_env(value):
        host = item.strip().lower()
        if "://" in host:
            host = (urlparse(host).hostname or "").lower()
        else:
            host = host.split("/", 1)[0]
            if not host.startswith("[") and host.count(":") == 1:
                host = host.split(":", 1)[0]
        if not host:
            continue
        if host == "*":
            logger.warning("TRUSTED_HOSTS_EXTRA: se ignora '*' (desactivaría la protección TrustedHost).")
            continue
        if host not in hosts:
            hosts.append(host)
    return hosts


def trusted_hosts(extra_env: Optional[str] = None) -> List[str]:
    """Lista final de hosts confiables: los de siempre + TRUSTED_HOSTS_EXTRA, sin repetidos."""
    raw = os.getenv("TRUSTED_HOSTS_EXTRA", "") if extra_env is None else extra_env
    final = list(DEFAULT_TRUSTED_HOSTS)
    for host in parse_trusted_hosts_extra(raw):
        if host not in final:
            final.append(host)
    return final

def validate_oauth_transport() -> None:
    """
    [CRÍTICO] Blindaje de transporte OAuth.
    Asegura que OAUTHLIB_INSECURE_TRANSPORT nunca esté activo en producción.
    """
    app_env = get_runtime_environment()
    
    if app_env == "development":
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        logger.warning(" MODO DESARROLLO: OAUTHLIB_INSECURE_TRANSPORT activado. No usar en producción.")
    else:
        if "OAUTHLIB_INSECURE_TRANSPORT" in os.environ:
            del os.environ["OAUTHLIB_INSECURE_TRANSPORT"]
        logger.info(" MODO PRODUCCIÓN: Seguridad SSL para OAuth forzada.")

# Ejecutar validación de seguridad al importar el módulo
validate_oauth_transport()


class Config:
    """Configuración inmutable de nivel Enterprise para toda la aplicación."""
    
    # --- SEGURIDAD CORE ---
    ENVIRONMENT: str = get_runtime_environment()
    MIN_SECRET_KEY_LENGTH: int = 32
    SECRET_KEY: str = os.getenv('SECRET_KEY', '')
    
    # [HARDENING] Evitar que el servidor inicie con llaves por defecto en producción
    if not SECRET_KEY or SECRET_KEY == 'mysecretkey' or len(SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
        if ENVIRONMENT == "production":
            logger.error(" ERROR CRÍTICO: SECRET_KEY no configurada o insegura en PRODUCCIÓN.")
            raise ValueError("SECRET_KEY robusta (min 32 caracteres) es obligatoria para producción.")
        else:
            logger.warning(" SECRET_KEY no configurada o muy corta. Usando fallback local temporal.")
            SECRET_KEY = os.getenv("SECRET_KEY_FALLBACK", "dev_key_fallback_only_for_local_2026")
            
    # --- JWT AUTHENTICATION ---
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # --- CORS ---
    DEFAULT_CORS_ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "https://hypershifu.com",
        "https://www.hypershifu.com",
        "https://app.hypershifu.com",
        "https://hyper-shifu-frontend.onrender.com",
    ]
    _cors_env: str = os.getenv("CORS_ALLOWED_ORIGINS", "")
    _cors_extra: List[str] = _parse_origins_env(_cors_env)
    CORS_ALLOWED_ORIGINS: List[str] = sorted(set(DEFAULT_CORS_ALLOWED_ORIGINS + _cors_extra))
    CORS_ALLOWED_ORIGIN_REGEX: Optional[str] = os.getenv("CORS_ALLOWED_ORIGIN_REGEX", "").strip() or None

    # --- BASES DE DATOS Y CACHÉ ---
    MONGO_URI: str = os.getenv('MONGO_URI', '')
    if not MONGO_URI:
        raise ValueError("MONGO_URI es obligatoria para el funcionamiento del sistema.")

    MONGO_DB_NAME: str = (
        os.getenv('MONGO_DB_NAME')
        or _extract_db_name_from_mongo_uri(MONGO_URI)
        or 'shifu_production'
    )
    REDIS_URL: Optional[str] = os.getenv('REDIS_URL')

    # --- INTELIGENCIA ARTIFICIAL (OpenAI / LangGraph) ---
    OPENAI_API_KEY: Optional[str] = os.getenv("CHAT_API_KEY")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    LANGGRAPH_CORE_MODEL: str = os.getenv("LANGGRAPH_CORE_MODEL", "gpt-4o-mini")
    TAVILY_API_KEY: Optional[str] = os.getenv("TAVILY_API_KEY")
    LLAMA_API_KEY: Optional[str] = os.getenv('LLAMA_API_KEY')
    
    # --- GOOGLE ECOSYSTEM (Consolidado) ---
    GOOGLE_SIGNIN_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_SIGNIN_CLIENT_ID")
    GOOGLE_SIGNIN_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_SIGNIN_CLIENT_SECRET")
    GOOGLE_SIGNIN_REDIRECT_URI: str = os.getenv("GOOGLE_SIGNIN_REDIRECT_URI", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://app.hypershifu.com")
    # Public base URL of THIS backend — used to build absolute inbound-webhook URLs
    # returned to the user (e.g. "https://api.hypershifu.com/api/v1/webhooks/<token>").
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

    # --- TELEGRAM LOGIN WIDGET (autenticación, distinto de la integración de Telegram) ---
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("DRIVE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("DRIVE_CLIENT_SECRET")
    GOOGLE_TOKEN_URI: str = "https://oauth2.googleapis.com/token"

    # Alias de compatibilidad estricta
    DRIVE_CLIENT_ID: Optional[str] = GOOGLE_CLIENT_ID
    DRIVE_CLIENT_SECRET: Optional[str] = GOOGLE_CLIENT_SECRET
    DRIVE_TOKEN_URI: str = GOOGLE_TOKEN_URI
    
    SHEETS_CLIENT_ID: Optional[str] = GOOGLE_CLIENT_ID
    SHEETS_CLIENT_SECRET: Optional[str] = GOOGLE_CLIENT_SECRET
    SHEETS_TOKEN_URI: str = GOOGLE_TOKEN_URI
    
    DOCS_CLIENT_ID: Optional[str] = GOOGLE_CLIENT_ID
    DOCS_CLIENT_SECRET: Optional[str] = GOOGLE_CLIENT_SECRET
    DOCS_TOKEN_URI: str = GOOGLE_TOKEN_URI

    # Fallback seguro usando 'or' para evitar strings vacíos de .env
    GMAIL_CLIENT_ID: Optional[str] = os.getenv('GMAIL_CLIENT_ID') or GOOGLE_CLIENT_ID
    GMAIL_CLIENT_SECRET: Optional[str] = os.getenv('GMAIL_CLIENT_SECRET') or GOOGLE_CLIENT_SECRET
    
    GMAIL_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify"
    ]
    DRIVE_SCOPES: List[str] = ["https://www.googleapis.com/auth/drive"]
    DOCS_SCOPES: List[str] = ["https://www.googleapis.com/auth/documents"]
    SLIDES_SCOPES: List[str] = ["https://www.googleapis.com/auth/presentations"]
    SHEETS_SCOPES: List[str] = ["https://www.googleapis.com/auth/spreadsheets"]
    CALENDAR_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    # --- INTEGRACIONES SAAS ---
    MONDAY_API_URL: str = "https://api.monday.com/v2"
    SLACK_CLIENT_ID: Optional[str] = os.getenv('SLACK_CLIENT_ID')
    SLACK_CLIENT_SECRET: Optional[str] = os.getenv('SLACK_CLIENT_SECRET')
    SLACK_BOT_TOKEN: Optional[str] = os.getenv('SLACK_BOT_TOKEN')
    SLACK_USER_TOKEN: Optional[str] = os.getenv('SLACK_USER_TOKEN')
    NOTION_CLIENT_ID: Optional[str] = os.getenv('NOTION_CLIENT_ID')
    NOTION_CLIENT_SECRET: Optional[str] = os.getenv('NOTION_CLIENT_SECRET')
    ASANA_CLIENT_ID: Optional[str] = os.getenv('ASANA_CLIENT_ID')
    ASANA_CLIENT_SECRET: Optional[str] = os.getenv('ASANA_CLIENT_SECRET')
    DROPBOX_CLIENT_ID: Optional[str] = os.getenv('DROPBOX_CLIENT_ID')
    DROPBOX_CLIENT_SECRET: Optional[str] = os.getenv('DROPBOX_CLIENT_SECRET')
    HUBSPOT_CLIENT_ID: Optional[str] = os.getenv('HUBSPOT_CLIENT_ID')
    HUBSPOT_CLIENT_SECRET: Optional[str] = os.getenv('HUBSPOT_CLIENT_SECRET')
    SALESFORCE_CLIENT_ID: Optional[str] = os.getenv('SALESFORCE_CLIENT_ID')
    SALESFORCE_CLIENT_SECRET: Optional[str] = os.getenv('SALESFORCE_CLIENT_SECRET')

    FACEBOOK_CLIENT_ID: Optional[str] = os.getenv('FACEBOOK_CLIENT_ID')
    FACEBOOK_CLIENT_SECRET: Optional[str] = os.getenv('FACEBOOK_CLIENT_SECRET')
    TEAMS_CLIENT_ID: Optional[str] = os.getenv('TEAMS_CLIENT_ID')
    TEAMS_CLIENT_SECRET: Optional[str] = os.getenv('TEAMS_CLIENT_SECRET')
    JIRA_CLIENT_ID: Optional[str] = os.getenv('JIRA_CLIENT_ID')
    JIRA_CLIENT_SECRET: Optional[str] = os.getenv('JIRA_CLIENT_SECRET')
    
    # Routing global para OAuth callbacks
    FRONTEND_REDIRECT_URL: str = os.getenv('FRONTEND_REDIRECT_URL', 'https://hypershifu.com/chat')

    # --- CLOUDINARY (Gestión de Medios) ---
    CLOUDINARY_CLOUD_NAME: str = os.getenv('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY: str = os.getenv('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET: str = os.getenv('CLOUDINARY_API_SECRET', '')

    # --- STRIPE (Pagos y Suscripciones) ---
    STRIPE_SECRET_KEY: str = os.getenv('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY: str = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
    WEBHOOK_SECRET: str = os.getenv('WEBHOOK_SECRET', '')
    STRIPE_PRICE_PRO: Optional[str] = os.getenv('STRIPE_PRICE_PRO')
    STRIPE_PRICE_STANDARD: Optional[str] = os.getenv('STRIPE_PRICE_STANDARD')
    STRIPE_PRICE_PREMIUM: Optional[str] = os.getenv('STRIPE_PRICE_PREMIUM')
    STRIPE_PRICE_ENTERPRISE: Optional[str] = os.getenv('STRIPE_PRICE_ENTERPRISE')

    # Reglas de planes movidas a app/billing/plans.py