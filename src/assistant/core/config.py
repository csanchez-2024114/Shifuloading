"""Configuración leída del entorno (.env). Sin efectos secundarios de red."""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


class ConfigError(Exception):
    """Error de configuración/arranque con mensaje claro para el usuario (sin stack trace)."""


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si", "sí")


def _num(name: str, default: str, kind=int):
    # una variable vacía en .env (p. ej. "CONTEXT_WINDOW_TOKENS=") vale su default, no rompe el arranque
    value = (os.getenv(name) or "").strip()
    return kind(value or default)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    llm_model: str
    mongodb_uri: str
    mongodb_db: str
    max_tokens: int
    recursion_limit: int
    model_call_limit: int
    memory_semantic: bool
    enable_hitl_demo: bool
    use_bigtool: bool = False          # agente alterno con langgraph-bigtool (busca herramientas en un registro)
    bigtool_demo_tools: bool = False   # +50 herramientas inofensivas de demostración en el registro
    embedding_model: str = "text-embedding-3-small"  # índice semántico de herramientas (bigtool)
    memory_summarize: bool = False      # compacta (resume) la conversación vieja al pasar el umbral (solo agente normal)
    # modo anterior: si SUMMARY_TRIGGER_TOKENS está definida, el disparo es por tokens de los mensajes (sin prompt ni
    # herramientas) y se ignora el porcentaje de la ventana. 0 = no definida.
    summary_trigger_tokens: int = 0
    summary_keep_tokens: int = 0
    context_window_tokens: int = 0      # ventana del modelo; 0 = la del perfil del modelo (o DEFAULT_CONTEXT_WINDOW)
    compact_warn_pct: int = 70          # medidor en ámbar
    compact_trigger_pct: int = 80       # medidor en rojo y compactación automática
    compact_keep_tokens: int = 0        # tokens recientes que se conservan al compactar; 0 = COMPACT_KEEP_PCT
    compact_keep_pct: int = 20          # % de la ventana que se conserva si no hay COMPACT_KEEP_TOKENS
    compact_prune_tools: bool = False   # capa 1: poda resultados viejos de herramientas en la vista del modelo
    compact_prune_age: int = 6          # antigüedad (en mensajes) a partir de la cual se podan
    compact_structured: bool = False    # capa 2: resumen estructurado e incremental
    compact_summary_max_tokens: int = 1200
    compact_first_message: bool = False  # el resumen cita el primer mensaje del usuario (línea fija, una sola vez)
    compact_model: str = ""             # modelo del resumen; "" = LLM_MODEL
    memory_save_policy: str = "strict"  # strict: solo datos puntuales del usuario; broad: política anterior
    memory_max_per_turn: int = 3        # recuerdos guardados por mensaje; 0 = sin tope
    memory_dedup: bool = False          # save_memory rechaza un dato equivalente a uno existente
    memory_search_economy: bool = False  # regla del prompt: no buscar en memoria lo que ya está en la conversación
    memory_dedup_score: float = 0.85    # con MEMORY_SEMANTIC: puntuación desde la que dos recuerdos son el mismo
    memory_verify: bool = False         # verifica con el LLM que un recuerdo lo dijo el usuario antes de guardarlo
    answer_verify: bool = False         # segundo paso que contrasta la respuesta con lo buscado en la web
    memory_min_score: float = 0.68      # búsqueda semántica (Atlas): puntuación mínima; calibrado, ver README
    investigator_max_tokens: int = 6000     # tope de salida del investigador (MAX_TOKENS no se le aplica); 0 = sin tope
    investigator_max_searches: int = 4      # búsquedas por investigación
    investigator_token_budget: int = 120000  # tokens (entrada+salida) del investigador por turno
    effort_high_max_calls: int = 15     # tope de llamadas al modelo con esfuerzo alto
    effort_high_max_tokens: int = 12000  # MAX_TOKENS efectivo con esfuerzo alto (el razonamiento cuenta dentro)
    tool_repeat_limit: int = 8          # veces que una misma herramienta puede usarse en un turno; 0 = sin tope
    sse_ping_seconds: float = 15.0      # comentario ": ping" en el stream SSE durante silencios; 0 = apagado
    search_context_size: str = "low"    # web_search hospedado: low/medium/high (contenido que recupera)
    search_max_tool_calls: int = 1      # búsquedas internas por llamada al web_search hospedado; 0 = sin tope
    search_cost_estimate: int = 15000   # tokens que se reservan antes de cada búsqueda (medido: ~9k-13k con low y 1)
    turn_max_searches: int = 6          # búsquedas web por mensaje, sumando agente e investigador; 0 = sin tope
    turn_token_cap: int = 150000        # tokens (entrada+salida) de todas las llamadas de un mensaje; 0 = sin tope
    # base de negocio (usuarios, sesiones, dueños de conversaciones): obligatoria solo con AUTH_ENABLED=1
    app_mongodb_uri: str = ""
    app_mongodb_db: str = ""
    auth_enabled: bool = False          # cuentas de usuario: el user_id sale de la sesión, nunca del navegador
    session_ttl_days: int = 14          # caducidad de la sesión (renovación deslizante)
    cookie_secure: str = "auto"         # cookie Secure: auto (si la petición llega por https), 1 o 0
    login_max_fails: int = 5            # fallos de login por correo antes del bloqueo
    login_max_fails_ip: int = 20        # fallos de login por IP antes del bloqueo (más alto: IP compartidas)
    login_lock_minutes: int = 10        # ventana de fallos y duración del bloqueo
    # P4: tope de espera por llamada a OpenAI y reintentos, en todos los ChatOpenAI. 300 s y no 90: una llamada con
    # razonamiento alto o del investigador puede pasar de 90 s y se cortaría (cambio de comportamiento); 300 solo
    # corta llamadas colgadas (antes, el cliente de OpenAI esperaba hasta 600 s). 2 reintentos = lo de antes.
    llm_timeout_seconds: float = 300.0  # 0 = sin tope propio (el del cliente de OpenAI)
    llm_max_retries: int = 2
    # P4.3: tiempo máximo de un mensaje (segundos). Al pasarlo, el turno se cierra en la siguiente frontera de paso,
    # igual que con TURN_TOKEN_CAP (una respuesta final en curso termina). 0 = apagado (default: sin cambio).
    turn_max_seconds: float = 0.0
    # P2.1-P2.2: envuelve el contenido de la web en <untrusted_web_content> y suma una regla al prompt. Apagado por
    # defecto: cambia lo que ve el modelo (prompt y resultados de herramientas).
    untrusted_wrap: bool = False
    # P2.3: save_memory/update_memory solo guardan si la evidencia cita literalmente lo que escribió el usuario
    # (confidence "quoted"), sin llamar a un LLM. Apagado por defecto: hoy un recuerdo sin cita se guarda como
    # "unverified" y el modelo recibiría otro resultado.
    memory_require_quote: bool = False
    # P2.4: al terminar cada turno quita de la respuesta los enlaces cuya URL (con su query) no está en lo que
    # devolvieron las herramientas ni en lo que escribió el usuario, aunque ANSWER_VERIFY=0. 0 tokens. Apagado por
    # defecto: puede cambiar la respuesta final.
    url_filter_always: bool = False
    # P3.3: las herramientas con efecto write/send/delete (ToolPolicy.effect del perfil o effect de @tool_spec) piden
    # aprobación con la tarjeta, en el agente normal y en bigtool. Apagado por defecto: cambia el flujo
    # (crm_create_order, por ejemplo, hoy corre sin preguntar).
    effect_approval: bool = False
    # S1: cabeceras Host aceptadas (TrustedHostMiddleware). Con AUTH_ENABLED=0 solo pueden ser locales.
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    # S5 (parcial): largo máximo de un mensaje en /chat. Alto a propósito para no cortar usos actuales (~12k tokens);
    # 0 = sin tope. El presupuesto por usuario y el rate limit quedan para después.
    max_message_chars: int = 50000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "gpt-6-luna").strip(),
            # base de la IA: AI_MONGODB_* o, por compatibilidad, MONGODB_*
            mongodb_uri=(os.getenv("AI_MONGODB_URI") or os.getenv("MONGODB_URI") or "mongodb://127.0.0.1:27017").strip(),
            mongodb_db=(os.getenv("AI_MONGODB_DB") or os.getenv("MONGODB_DB") or "assistant").strip(),
            max_tokens=_num("MAX_TOKENS", "8000"),
            recursion_limit=_num("RECURSION_LIMIT", "100"),
            model_call_limit=_num("MODEL_CALL_LIMIT", "0"),
            memory_semantic=_bool("MEMORY_SEMANTIC"),
            enable_hitl_demo=_bool("ENABLE_HITL_DEMO"),
            use_bigtool=_bool("USE_BIGTOOL"),
            bigtool_demo_tools=_bool("BIGTOOL_DEMO_TOOLS"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            memory_summarize=_bool("MEMORY_SUMMARIZE"),
            summary_trigger_tokens=_num("SUMMARY_TRIGGER_TOKENS", "0"),
            summary_keep_tokens=_num("SUMMARY_KEEP_TOKENS", "0"),
            context_window_tokens=_num("CONTEXT_WINDOW_TOKENS", "0"),
            compact_warn_pct=_num("COMPACT_WARN_PCT", "70"),
            compact_trigger_pct=_num("COMPACT_TRIGGER_PCT", "80"),
            compact_keep_tokens=_num("COMPACT_KEEP_TOKENS", "0"),
            compact_keep_pct=_num("COMPACT_KEEP_PCT", "20"),
            compact_prune_tools=_bool("COMPACT_PRUNE_TOOLS"),
            compact_prune_age=_num("COMPACT_PRUNE_AGE", "6"),
            compact_structured=_bool("COMPACT_STRUCTURED"),
            compact_summary_max_tokens=_num("COMPACT_SUMMARY_MAX_TOKENS", "1200"),
            compact_first_message=_bool("COMPACT_FIRST_MESSAGE"),
            compact_model=os.getenv("COMPACT_MODEL", "").strip(),
            memory_save_policy=os.getenv("MEMORY_SAVE_POLICY", "strict").strip().lower(),
            memory_max_per_turn=_num("MEMORY_MAX_PER_TURN", "3"),
            memory_dedup=_bool("MEMORY_DEDUP"),
            memory_search_economy=_bool("MEMORY_SEARCH_ECONOMY"),
            memory_dedup_score=_num("MEMORY_DEDUP_SCORE", "0.85", float),
            memory_verify=_bool("MEMORY_VERIFY"),
            answer_verify=_bool("ANSWER_VERIFY"),
            memory_min_score=_num("MEMORY_MIN_SCORE", "0.68", float),
            investigator_max_tokens=_num("INVESTIGATOR_MAX_TOKENS", "6000"),
            investigator_max_searches=_num("INVESTIGATOR_MAX_SEARCHES", "4"),
            investigator_token_budget=_num("INVESTIGATOR_TOKEN_BUDGET", "120000"),
            effort_high_max_calls=_num("EFFORT_HIGH_MAX_CALLS", "15"),
            effort_high_max_tokens=_num("EFFORT_HIGH_MAX_TOKENS", "12000"),
            tool_repeat_limit=_num("TOOL_REPEAT_LIMIT", "8"),
            sse_ping_seconds=_num("SSE_PING_SECONDS", "15", float),
            search_context_size=os.getenv("SEARCH_CONTEXT_SIZE", "low").strip().lower(),
            search_max_tool_calls=_num("SEARCH_MAX_TOOL_CALLS", "1"),
            search_cost_estimate=_num("SEARCH_COST_ESTIMATE", "15000"),
            turn_max_searches=_num("TURN_MAX_SEARCHES", "6"),
            turn_token_cap=_num("TURN_TOKEN_CAP", "150000"),
            app_mongodb_uri=os.getenv("APP_MONGODB_URI", "").strip(),
            app_mongodb_db=os.getenv("APP_MONGODB_DB", "").strip(),
            auth_enabled=_bool("AUTH_ENABLED"),
            session_ttl_days=_num("SESSION_TTL_DAYS", "14"),
            cookie_secure=os.getenv("COOKIE_SECURE", "auto").strip().lower(),
            login_max_fails=int(os.getenv("LOGIN_MAX_FAILS_PER_EMAIL") or os.getenv("LOGIN_MAX_FAILS") or "5"),
            login_max_fails_ip=int(os.getenv("LOGIN_MAX_FAILS_PER_IP") or "20"),
            login_lock_minutes=_num("LOGIN_LOCK_MINUTES", "10"),
            llm_timeout_seconds=_num("LLM_TIMEOUT_SECONDS", "300", float),
            llm_max_retries=_num("LLM_MAX_RETRIES", "2"),
            turn_max_seconds=_num("TURN_MAX_SECONDS", "0", float),
            untrusted_wrap=_bool("UNTRUSTED_WRAP"),
            memory_require_quote=_bool("MEMORY_REQUIRE_QUOTE"),
            url_filter_always=_bool("URL_FILTER_ALWAYS"),
            effect_approval=_bool("EFFECT_APPROVAL"),
            max_message_chars=_num("MAX_MESSAGE_CHARS", "50000"),
            trusted_hosts=tuple(h.strip().lower() for h in (os.getenv("TRUSTED_HOSTS") or "localhost,127.0.0.1")
                                .split(",") if h.strip()),
        )

    def context_window(self) -> int:
        """CONTEXT_WINDOW_TOKENS o, si no está, la ventana de entrada del perfil del modelo en langchain."""
        if self.context_window_tokens > 0:
            return self.context_window_tokens
        return _profile_window(self.llm_model)

    def compact_legacy(self) -> bool:
        """SUMMARY_TRIGGER_TOKENS definida: disparo anterior (tokens de los mensajes, sin prompt ni herramientas)."""
        return self.summary_trigger_tokens > 0

    def compact_trigger(self) -> int:
        if self.compact_legacy():
            return self.summary_trigger_tokens
        return max(1, self.context_window() * self.compact_trigger_pct // 100)

    def compact_due(self, context_tokens: int) -> bool:
        """Compactar antes de esta llamada: el contexto pasó el umbral, o la llamada ya no cabría en la ventana con su
        salida máxima (MAX_TOKENS), aunque aún no llegue al umbral."""
        if context_tokens >= self.compact_trigger():
            return True
        return not self.compact_legacy() and context_tokens + (self.max_tokens or 0) >= self.context_window()

    def compact_keep(self) -> int:
        keep = (self.summary_keep_tokens or self.compact_keep_tokens
                or self.context_window() * self.compact_keep_pct // 100)
        # lo conservado queda muy por debajo del umbral: si no, el siguiente mensaje vuelve a dispararlo
        return max(1, min(keep, self.compact_trigger() // 2))

    def require_api_key(self) -> None:
        if not self.openai_api_key:
            from assistant.core.i18n import tr  # perezoso: el catálogo es del perfil

            raise ConfigError(tr("startup.missing_api_key"))


def llm_kwargs(settings: Settings) -> dict:
    """timeout y max_retries de LLM_TIMEOUT_SECONDS/LLM_MAX_RETRIES para todo ChatOpenAI que hace llamadas."""
    return {"timeout": settings.llm_timeout_seconds or None, "max_retries": settings.llm_max_retries}


DEFAULT_CONTEXT_WINDOW = 128000  # modelos sin perfil conocido en langchain


@lru_cache(maxsize=8)
def _profile_window(model: str) -> int:
    try:
        from langchain_openai import ChatOpenAI

        profile = ChatOpenAI(model=model, api_key="sk-profile-only").profile or {}
        return int(profile.get("max_input_tokens") or DEFAULT_CONTEXT_WINDOW)
    except Exception:  # noqa: BLE001
        return DEFAULT_CONTEXT_WINDOW


def read_system_prompt(profile=None) -> str:
    """Prompt del sistema del perfil (el activo si no se pasa). Se relee en cada mensaje."""
    from assistant.core.profile import active_profile  # perezoso: profile importa config

    return (profile or active_profile()).system_prompt_path.read_text(encoding="utf-8")
