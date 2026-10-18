"""Perfil del agente: todo lo que define un caso de uso (prompt, herramientas, aprobaciones, políticas de memoria,
nombres antiguos de herramientas, UI). El núcleo lo recibe de aquí y nunca importa un perfil: lo carga por nombre
(AGENT_PROFILE, default "default") desde `assistant.profiles.<nombre>` o desde una ruta con puntos."""
import importlib
import os
import pkgutil
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Mapping

from assistant.core.config import ConfigError
from assistant.core.i18n import REQUIRED_TEXTS, TextCatalog

PROFILES_PACKAGE = "assistant.profiles"  # única referencia del núcleo a los perfiles: un nombre, no un import
DEFAULT_PROFILE = "default"

Effect = Literal["read", "write", "send", "delete"]
NEVER = re.compile(r"(?!)")  # patrón que no reconoce nada: default de las reglas (el núcleo no asume idioma)


@dataclass(frozen=True)
class IntentRules:
    """Reglas de intención del perfil (antes regex fijos del núcleo). Los textos se comparan en minúsculas y sin
    tildes, salvo continue_request (texto tal cual, con match al inicio) y sources_heading (la respuesta)."""
    continue_request: re.Pattern = NEVER          # "continúa" tras una respuesta cortada por MAX_TOKENS
    classifier_signal: re.Pattern = NEVER         # un mensaje corto con esto sí pasa por el clasificador de esfuerzo
    classifier_signal_words: tuple[str, ...] = ()  # ...o con una palabra que empiece por alguno de estos prefijos
    short_message_chars: int = 60                 # más largo que esto: siempre al clasificador
    explicit_research: re.Pattern = NEVER         # pide investigar en este mensaje: deep_research sin tarjeta
    research_again: re.Pattern = NEVER            # en un seguimiento breve, pide investigar de nuevo
    follow_up_max_chars: int = 200                # más largo que esto no es un seguimiento breve
    sources_heading: re.Pattern = NEVER           # encabezado de una sección de fuentes (se quita si no hubo web)


def _whole_word(word: str) -> str:
    return word


@dataclass(frozen=True)
class MemoryLexicon:
    """Léxico de la memoria por palabras: sujeto genérico que se quita al guardar ("El usuario vive en X" -> "Vive en
    X"), palabras vacías, temas (raíz -> tema) y la raíz de una palabra (ya en minúsculas y sin tildes). El default no
    sabe de ningún idioma: no quita sujeto, no hay palabras vacías ni temas y la raíz es la palabra entera."""
    subject: re.Pattern = NEVER
    stopwords: frozenset[str] = frozenset()
    topics: Mapping[str, str] = field(default_factory=dict)
    stem: Callable[[str], str] = _whole_word


@dataclass(frozen=True)
class ToolPolicy:
    effect: Effect = "read"  # metadato: aún no cambia el comportamiento
    # lo que recibe HumanInTheLoopMiddleware(interrupt_on={nombre: approval}): False (sin aprobación), True o un dict
    # con allowed_decisions/description/when
    approval: bool | dict = False
    description_key: str | None = None  # clave del catálogo con el texto de la tarjeta (se resuelve al construir)
    evidence: bool = False  # su resultado es evidencia para ANSWER_VERIFY (si no se ejecutó, no cuenta)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    display_name: str
    system_prompt_path: Path              # se relee en cada mensaje
    static_dir: Path                      # carpeta de la UI (index.html)
    # (modelo, settings, herramientas base del núcleo en su orden) -> herramientas del agente normal
    build_tools: Callable[..., list]
    bigtool_tools: Callable[..., list] = lambda settings: []   # (settings) -> extra del registro de bigtool
    tool_policies: Mapping[str, ToolPolicy] = field(default_factory=dict)
    memory_policies: Mapping[str, str] = field(default_factory=dict)  # "strict" obligatoria; "broad"...
    search_economy_rule: str = ""
    legacy_tool_names: Mapping[str, str] = field(default_factory=dict)  # nombre antiguo -> actual (hilos viejos)
    texts: TextCatalog = field(default_factory=TextCatalog)  # textos al usuario: base de un pack + sobreescrituras
    intents: IntentRules = field(default_factory=IntentRules)  # reglas de intención (idioma del caso de uso)
    lexicon: MemoryLexicon = field(default_factory=MemoryLexicon)  # búsqueda de recuerdos por palabras


_CACHE: dict[str, AgentProfile] = {}


def profile_name() -> str:
    return (os.getenv("AGENT_PROFILE") or "").strip() or DEFAULT_PROFILE


def available_profiles() -> list[str]:
    package = importlib.import_module(PROFILES_PACKAGE)
    return sorted(m.name for m in pkgutil.iter_modules(package.__path__) if m.ispkg)


def load_profile(name: str | None = None) -> AgentProfile:
    """Perfil `name` (o el de AGENT_PROFILE). ConfigError con mensaje claro si no existe o no es válido."""
    name = name or profile_name()
    if name in _CACHE:
        return _CACHE[name]
    module_name = name if "." in name else f"{PROFILES_PACKAGE}.{name}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # solo si falta el propio perfil; un import roto dentro de un perfil existente se relanza tal cual
        if exc.name and (module_name == exc.name or module_name.startswith(exc.name + ".")):
            raise ConfigError(f"No existe el perfil '{name}' (AGENT_PROFILE). Perfiles disponibles: "
                              f"{', '.join(available_profiles())}.") from None
        raise
    profile = getattr(module, "PROFILE", None)
    if not isinstance(profile, AgentProfile):
        raise ConfigError(f"El perfil '{name}' no define PROFILE (un AgentProfile de assistant.core.profile).")
    if "strict" not in profile.memory_policies:
        raise ConfigError(f"El perfil '{name}' no define la política de memoria 'strict' (memory_policies).")
    if missing := [key for key in REQUIRED_TEXTS if key not in profile.texts]:
        raise ConfigError(f"Al catálogo de textos del perfil '{name}' le faltan estas claves: {', '.join(missing)}.")
    _CACHE[name] = profile
    return profile


def active_profile() -> AgentProfile:
    return load_profile()


def tool_aliases(names, profile=None) -> tuple[str, ...]:
    """`names` (nombres actuales de herramientas) más sus nombres antiguos según el perfil, en el orden de su mapa."""
    legacy = (profile or active_profile()).legacy_tool_names
    return (*names, *(old for old, new in legacy.items() if new in names))
