"""Configuración leída del entorno (.env). Sin efectos secundarios de red."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class ConfigError(Exception):
    """Error de configuración/arranque con mensaje claro para el usuario (sin stack trace)."""


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si", "sí")


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
    memory_summarize: bool = False      # resume la conversación vieja al pasar el umbral (solo agente normal)
    summary_trigger_tokens: int = 12000
    summary_keep_tokens: int = 5000     # tokens recientes que se conservan sin resumir (muy por debajo del umbral)
    memory_verify: bool = False         # verifica con el LLM que un recuerdo lo dijo el usuario antes de guardarlo
    answer_verify: bool = False         # segundo paso que contrasta la respuesta con lo buscado en la web
    memory_min_score: float = 0.68      # búsqueda semántica (Atlas): puntuación mínima; calibrado, ver README
    investigator_max_tokens: int = 6000     # tope de salida del investigador (MAX_TOKENS no se le aplica); 0 = sin tope
    investigator_max_searches: int = 4      # búsquedas por investigación
    investigator_token_budget: int = 120000  # tokens (entrada+salida) del investigador por turno
    effort_high_max_calls: int = 15     # tope de llamadas al modelo con esfuerzo alto
    tool_repeat_limit: int = 8          # veces que una misma herramienta puede usarse en un turno; 0 = sin tope
    sse_ping_seconds: float = 15.0      # comentario ": ping" en el stream SSE durante silencios; 0 = apagado
    search_context_size: str = "low"    # web_search hospedado: low/medium/high (contenido que recupera)
    search_max_tool_calls: int = 1      # búsquedas internas por llamada al web_search hospedado; 0 = sin tope
    search_cost_estimate: int = 15000   # tokens que se reservan antes de cada búsqueda (medido: ~9k-13k con low y 1)
    turn_max_searches: int = 6          # búsquedas web por mensaje, sumando agente e investigador; 0 = sin tope
    turn_token_cap: int = 150000        # tokens (entrada+salida) de todas las llamadas de un mensaje; 0 = sin tope

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "gpt-6-luna").strip(),
            mongodb_uri=os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017").strip(),
            mongodb_db=os.getenv("MONGODB_DB", "assistant").strip(),
            max_tokens=int(os.getenv("MAX_TOKENS", "8000")),
            recursion_limit=int(os.getenv("RECURSION_LIMIT", "100")),
            model_call_limit=int(os.getenv("MODEL_CALL_LIMIT", "0")),
            memory_semantic=_bool("MEMORY_SEMANTIC"),
            enable_hitl_demo=_bool("ENABLE_HITL_DEMO"),
            use_bigtool=_bool("USE_BIGTOOL"),
            bigtool_demo_tools=_bool("BIGTOOL_DEMO_TOOLS"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            memory_summarize=_bool("MEMORY_SUMMARIZE"),
            summary_trigger_tokens=int(os.getenv("SUMMARY_TRIGGER_TOKENS", "12000")),
            summary_keep_tokens=int(os.getenv("SUMMARY_KEEP_TOKENS", "5000")),
            memory_verify=_bool("MEMORY_VERIFY"),
            answer_verify=_bool("ANSWER_VERIFY"),
            memory_min_score=float(os.getenv("MEMORY_MIN_SCORE", "0.68")),
            investigator_max_tokens=int(os.getenv("INVESTIGATOR_MAX_TOKENS", "6000")),
            investigator_max_searches=int(os.getenv("INVESTIGATOR_MAX_SEARCHES", "4")),
            investigator_token_budget=int(os.getenv("INVESTIGATOR_TOKEN_BUDGET", "120000")),
            effort_high_max_calls=int(os.getenv("EFFORT_HIGH_MAX_CALLS", "15")),
            tool_repeat_limit=int(os.getenv("TOOL_REPEAT_LIMIT", "8")),
            sse_ping_seconds=float(os.getenv("SSE_PING_SECONDS", "15")),
            search_context_size=os.getenv("SEARCH_CONTEXT_SIZE", "low").strip().lower(),
            search_max_tool_calls=int(os.getenv("SEARCH_MAX_TOOL_CALLS", "1")),
            search_cost_estimate=int(os.getenv("SEARCH_COST_ESTIMATE", "15000")),
            turn_max_searches=int(os.getenv("TURN_MAX_SEARCHES", "6")),
            turn_token_cap=int(os.getenv("TURN_TOKEN_CAP", "150000")),
        )

    def require_api_key(self) -> None:
        if not self.openai_api_key:
            raise ConfigError(
                "Falta OPENAI_API_KEY. Crea un archivo .env en la raíz del proyecto "
                "(copia .env.example) y pon tu clave."
            )


def read_system_prompt() -> str:
    return (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
