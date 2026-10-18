"""Textos al usuario (avisos del agente, errores HTTP y de arranque). El núcleo no trae textos en ningún idioma: declara
las claves que necesita (REQUIRED_TEXTS) y cada perfil da su TextCatalog (la base de un pack de idioma más sus
sobreescrituras). Se resuelven al usar (tr), nunca al importar. Lo que lee el modelo no pasa por aquí: va en inglés,
como default del núcleo."""
from collections.abc import Iterator, Mapping

REQUIRED_TEXTS = (
    # agente
    "agent.limit_reached",        # tope de llamadas al modelo por mensaje
    "agent.cut_note",             # respuesta cortada por MAX_TOKENS
    "agent.unverified_note",      # ANSWER_VERIFY no corrió por TURN_TOKEN_CAP
    "agent.turn_cap",             # mensaje abortado por TURN_TOKEN_CAP; {cap}
    "agent.recursion_limit",      # RECURSION_LIMIT; {limit}
    "agent.compact_unsupported",  # compactación manual en un agente sin compactador
    "agent.compact_pending",      # compactación manual con una aprobación pendiente
    "format.thousands_sep",       # separador de miles de las cifras en los avisos
    # herramientas
    "tools.deep_research_confirm",  # tarjeta de aprobación de deep_research
    # citas (notas de ANSWER_VERIFY que ve el usuario)
    "citations.correction_discarded",  # {numbers}
    "citations.citation_removed",      # {url}
    "citations.sources_label",
    "citations.sources_restored",
    # servidor HTTP
    "http.login_required", "http.origin_forbidden", "http.csrf_invalid", "http.thread_not_found",
    "http.accounts_disabled", "http.wrong_password", "http.title_length",  # {max}
    "http.store_unavailable", "http.memory_not_found", "http.server_needs_app_db",
    # cuentas (genéricos: no revelan si un correo existe)
    "auth.login_error", "auth.register_error", "auth.locked_error", "auth.password_rule",
    # arranque
    "startup.missing_api_key", "startup.mongo_unreachable",  # {uri}
    "startup.openai_auth", "startup.openai_connection", "startup.openai_api_error",  # {error}
    "startup.model_not_found", "startup.none_available",  # {model} {available}
    "startup.same_db", "startup.app_db_required",
)


class TextCatalog(Mapping):
    """Catálogo fusionado: `base` (p. ej. assistant.packs.i18n.es.TEXTS) y encima las sobreescrituras del perfil."""

    def __init__(self, base: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None):
        self._texts = {**dict(base or {}), **dict(overrides or {})}

    def __getitem__(self, key: str) -> str:
        return self._texts[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._texts)

    def __len__(self) -> int:
        return len(self._texts)

    def missing(self, required=REQUIRED_TEXTS) -> list[str]:
        return [k for k in required if k not in self._texts]


def tr(key: str, profile=None, **values) -> str:
    """Texto `key` del perfil (el activo si no se pasa), con `values` aplicados con str.format si se dan."""
    from assistant.core.profile import active_profile  # perezoso: profile importa este módulo

    text = (profile or active_profile()).texts[key]
    return text.format(**values) if values else text
