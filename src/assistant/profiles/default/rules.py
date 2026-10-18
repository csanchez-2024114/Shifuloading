"""Reglas de intención del perfil por defecto (español e inglés). Son los mismos patrones que antes vivían fijos en el
núcleo (core/agent.py, core/tools.py, core/citations.py), sin cambiar una letra."""
import re

from assistant.core.profile import IntentRules

# "continúa", "sigue", "continue"... como mensaje corto tras una respuesta cortada
CONTINUE_RE = re.compile(r"^\W*(contin[uú]a|continuar|sigue|segu[ií]|seguir|dale|continue|go on|keep going)\b", re.I)

# Señales de que un mensaje corto aún necesita clasificarse: dígitos, operadores, código o verbos de trabajo.
SIGNAL_RE = re.compile(r"\d|[+*/=^%×÷√<>]|```")
SIGNAL_WORDS = ("calcul", "resuelv", "resolv", "optimi", "demuestr", "demostr", "plan", "disen", "codigo",
                "program", "investig", "compar", "analiz", "calculate", "solve", "optimiz", "prove", "design",
                "code", "research", "compare",
                # actualidad: "¿quién ganó el último partido?" es corto pero necesita buscar (sin tildes: ya normalizado)
                "ultim", "hoy", "ayer", "gano", "ganador", "precio", "noticia", "cotiza",
                "latest", "last", "today", "yesterday", "won", "winner", "price", "news")
SHORT_MESSAGE_CHARS = 60

# palabras con las que el usuario pide investigar de nuevo (sin acentos)
RESEARCH_AGAIN_RE = re.compile(r"\b(investiga\w*|busca\w*|de nuevo|otra vez|nuevamente|actualiza\w*|research\w*|"
                               r"search\w*|look (it )?up|again)\b")
FOLLOW_UP_MAX_CHARS = 200

# el usuario pide investigar en ESTE mensaje: no hace falta confirmar (texto ya normalizado: sin tildes)
EXPLICIT_RESEARCH_RE = re.compile(r"\b(investig\w*|research\w*|a fondo|en profundidad|exhaustiv\w*|in[- ]depth|"
                                  r"thorough\w*|deep dive)\b")

# encabezado de una sección de fuentes ("## Fuentes", "**Sources:**", "Referencias:"...), sin acentos ni mayúsculas
SOURCES_HEADING_RE = re.compile(r"^\s*(#{1,6}\s*)?(\*\*|__)?\s*(fuentes|sources|referencias|references|bibliograf\w*)"
                                r"\b[^\n]*$", re.I | re.M)

INTENTS = IntentRules(
    continue_request=CONTINUE_RE,
    classifier_signal=SIGNAL_RE,
    classifier_signal_words=SIGNAL_WORDS,
    short_message_chars=SHORT_MESSAGE_CHARS,
    explicit_research=EXPLICIT_RESEARCH_RE,
    research_again=RESEARCH_AGAIN_RE,
    follow_up_max_chars=FOLLOW_UP_MAX_CHARS,
    sources_heading=SOURCES_HEADING_RE,
)
