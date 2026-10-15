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
    summary_keep_messages: int = 20     # últimos mensajes que se conservan sin resumir
    memory_verify: bool = False         # verifica con el LLM que un recuerdo lo dijo el usuario antes de guardarlo
    answer_verify: bool = False         # segundo paso que contrasta la respuesta con lo buscado en la web
    memory_min_score: float = 0.68      # búsqueda semántica (Atlas): puntuación mínima; calibrado, ver README

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "gpt-6-luna").strip(),
            mongodb_uri=os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017").strip(),
            mongodb_db=os.getenv("MONGODB_DB", "assistant").strip(),
            max_tokens=int(os.getenv("MAX_TOKENS", "0")),
            recursion_limit=int(os.getenv("RECURSION_LIMIT", "100")),
            model_call_limit=int(os.getenv("MODEL_CALL_LIMIT", "0")),
            memory_semantic=_bool("MEMORY_SEMANTIC"),
            enable_hitl_demo=_bool("ENABLE_HITL_DEMO"),
            use_bigtool=_bool("USE_BIGTOOL"),
            bigtool_demo_tools=_bool("BIGTOOL_DEMO_TOOLS"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            memory_summarize=_bool("MEMORY_SUMMARIZE"),
            summary_trigger_tokens=int(os.getenv("SUMMARY_TRIGGER_TOKENS", "12000")),
            summary_keep_messages=int(os.getenv("SUMMARY_KEEP_MESSAGES", "20")),
            memory_verify=_bool("MEMORY_VERIFY"),
            answer_verify=_bool("ANSWER_VERIFY"),
            memory_min_score=float(os.getenv("MEMORY_MIN_SCORE", "0.68")),
        )

    def require_api_key(self) -> None:
        if not self.openai_api_key:
            raise ConfigError(
                "Falta OPENAI_API_KEY. Crea un archivo .env en la raíz del proyecto "
                "(copia .env.example) y pon tu clave."
            )


def read_system_prompt() -> str:
    return (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
