"""Textos al usuario en español (base de TextCatalog). Son los textos que antes vivían en el núcleo, literales: con el
perfil por defecto nada visible cambia. Las constantes conservan el nombre que tenían en su módulo de origen."""

# --------------------------------------------------------------------------- agente (antes en core/agent.py)
LIMIT_MSG = "Se alcanzó el límite de llamadas al modelo para este mensaje; detuve el proceso. Escribe «continúa» para seguir."
CUT_NOTE = ("\n\n⚠️ La respuesta se cortó por el límite de longitud (MAX_TOKENS). Escribe «continúa» y sigo justo "
            "donde me quedé, sin repetir lo anterior.")
UNVERIFIED_NOTE = "No verificada: este mensaje llegó a su tope de tokens (TURN_TOKEN_CAP)"
# avisos al usuario: texto plano (la interfaz no interpreta _cursiva_ y mostraba los guiones bajos)
TURN_CAP_MSG = ("\n\n⚠️ Detuve este mensaje: superó el tope de {cap} tokens por mensaje (TURN_TOKEN_CAP). Lo que "
                "alcancé a hacer puede estar incompleto; si lo necesitas, pídemelo con una pregunta más acotada.")
RECURSION_MSG = ("Me detuve: la tarea superó {limit} pasos internos. "
                 "Pídeme que continúe o sube RECURSION_LIMIT en .env.")
COMPACT_UNSUPPORTED_MSG = "Este agente no admite compactación"
COMPACT_PENDING_MSG = "La conversación espera una aprobación"
THOUSANDS_SEP = "."  # 45.000, como se escribe en español

# --------------------------------------------------------------------------- herramientas (antes en core/tools.py)
DEEP_RESEARCH_CONFIRM = "Esto tardará unos 1-2 minutos y consume bastante más; ¿sigo?"  # tarjeta de aprobación

# --------------------------------------------------------------------------- citas (antes en core/citations.py)
CORRECTION_DISCARDED_NOTE = ("no se pudo corregir sin agregar datos no respaldados ({numbers}); "
                             "se conserva la respuesta original")
CITATION_REMOVED_NOTE = "se eliminó una cita sin respaldo en la búsqueda: {url}"
SOURCES_LABEL = "Fuentes: "
SOURCES_RESTORED_NOTE = "se restauraron fuentes que la corrección había quitado"

TEXTS = {
    "agent.limit_reached": LIMIT_MSG,
    "agent.cut_note": CUT_NOTE,
    "agent.unverified_note": UNVERIFIED_NOTE,
    "agent.turn_cap": TURN_CAP_MSG,
    "agent.recursion_limit": RECURSION_MSG,
    "agent.compact_unsupported": COMPACT_UNSUPPORTED_MSG,
    "agent.compact_pending": COMPACT_PENDING_MSG,
    "format.thousands_sep": THOUSANDS_SEP,
    "tools.deep_research_confirm": DEEP_RESEARCH_CONFIRM,
    "citations.correction_discarded": CORRECTION_DISCARDED_NOTE,
    "citations.citation_removed": CITATION_REMOVED_NOTE,
    "citations.sources_label": SOURCES_LABEL,
    "citations.sources_restored": SOURCES_RESTORED_NOTE,
}
