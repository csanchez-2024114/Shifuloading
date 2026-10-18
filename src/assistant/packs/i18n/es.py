"""Textos al usuario en español (base de TextCatalog). Son los textos que antes vivían en el núcleo, literales: con el
perfil por defecto nada visible cambia. Las constantes conservan el nombre que tenían en su módulo de origen."""
from assistant.core.auth import MIN_PASSWORD_LEN

# --------------------------------------------------------------------------- agente (antes en core/agent.py)
LIMIT_MSG = "Se alcanzó el límite de llamadas al modelo para este mensaje; detuve el proceso. Escribe «continúa» para seguir."
CUT_NOTE = ("\n\n⚠️ La respuesta se cortó por el límite de longitud (MAX_TOKENS). Escribe «continúa» y sigo justo "
            "donde me quedé, sin repetir lo anterior.")
UNVERIFIED_NOTE = "No verificada: este mensaje llegó a su tope de tokens (TURN_TOKEN_CAP)"
# avisos al usuario: texto plano (la interfaz no interpreta _cursiva_ y mostraba los guiones bajos)
TURN_CAP_MSG = ("\n\n⚠️ Detuve este mensaje: superó el tope de {cap} tokens por mensaje (TURN_TOKEN_CAP). Lo que "
                "alcancé a hacer puede estar incompleto; si lo necesitas, pídemelo con una pregunta más acotada.")
EFFECT_CONFIRM = "La herramienta {name} modifica o envía datos. ¿La ejecuto?"
NON_LOCAL_HOSTS_MSG = ("Sin cuentas (AUTH_ENABLED=0) la app solo puede atender en esta máquina, pero TRUSTED_HOSTS "
                       "incluye hosts no locales: {hosts}. Activa AUTH_ENABLED=1 o deja TRUSTED_HOSTS en "
                       "localhost,127.0.0.1.")
NOT_LOOPBACK_MSG = ("Sin cuentas (AUTH_ENABLED=0) la app solo atiende conexiones locales. Ábrela en "
                    "http://localhost o activa AUTH_ENABLED=1.")
MESSAGE_TOO_LONG_MSG = "El mensaje es demasiado largo: el máximo es {max} caracteres (MAX_MESSAGE_CHARS)."
STREAM_ERROR_MSG = "Algo falló al generar la respuesta. Inténtalo de nuevo."
TURN_TIME_MSG = ("\n\n⚠️ Detuve este mensaje: superó el tiempo máximo de {seconds} s por mensaje (TURN_MAX_SECONDS). "
                 "Lo que alcancé a hacer puede estar incompleto; si lo necesitas, pídemelo con una pregunta más acotada.")
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

# --------------------------------------------------------------------------- servidor HTTP (antes en core/server.py)
LOGIN_REQUIRED_MSG = "Inicia sesión para continuar."
ORIGIN_FORBIDDEN_MSG = "Origen no permitido."
CSRF_INVALID_MSG = "Falta el token CSRF o no es válido."
THREAD_NOT_FOUND_MSG = "Conversación no encontrada."
ACCOUNTS_DISABLED_MSG = "Las cuentas no están activadas (AUTH_ENABLED=0)."
WRONG_PASSWORD_MSG = "La contraseña no es correcta."
TITLE_LENGTH_MSG = "El título debe tener entre 1 y {max} caracteres."
STORE_UNAVAILABLE_MSG = "El almacén de recuerdos no está disponible"
MEMORY_NOT_FOUND_MSG = "Recuerdo no encontrado"
SERVER_NEEDS_APP_DB_MSG = "AUTH_ENABLED=1 necesita la base de negocio (APP_MONGODB_URI y APP_MONGODB_DB)."

# --------------------------------------------------------------------------- cuentas (antes en core/auth.py)
# mensajes genéricos: no revelan si un correo existe
LOGIN_ERROR = "Correo o contraseña incorrectos."
REGISTER_ERROR = "No se pudo crear la cuenta con esos datos."
LOCKED_ERROR = "Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo."
PASSWORD_RULE = f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."

# --------------------------------------------------------------------------- arranque (antes en core/config.py y core/memory.py)
MISSING_API_KEY_MSG = ("Falta OPENAI_API_KEY. Crea un archivo .env en la raíz del proyecto "
                       "(copia .env.example) y pon tu clave.")
MONGO_UNREACHABLE_MSG = "No pude conectar a MongoDB en {uri}. Verifica que el servicio esté corriendo"
OPENAI_AUTH_MSG = ("OPENAI_API_KEY inválida (OpenAI rechazó la autenticación). "
                   "Revisa la clave en tu archivo .env")
OPENAI_CONNECTION_MSG = "No pude contactar la API de OpenAI: {error}"
OPENAI_API_ERROR_MSG = "Error de la API de OpenAI al listar modelos: {error}"
MODEL_NOT_FOUND_MSG = ("El modelo '{model}' no existe para tu cuenta. "
                       "Modelos 'luna' disponibles: {available}. Ajusta LLM_MODEL en .env")
NONE_AVAILABLE = "ninguno"
SAME_DB_MSG = ("APP_MONGODB_URI/APP_MONGODB_DB apuntan a la misma base que la IA (AI_MONGODB_*/MONGODB_*). Deben ser "
               "bases distintas: la de la IA nunca guarda correos, contraseñas ni datos de login, y la de negocio "
               "nunca guarda mensajes ni recuerdos. Usa otro nombre de base (y, en Atlas, otro usuario).")
APP_DB_REQUIRED_MSG = ("Con AUTH_ENABLED=1 hacen falta APP_MONGODB_URI y APP_MONGODB_DB (base de negocio: "
                       "usuarios y sesiones), distintas de la base de la IA.")

TEXTS = {
    "agent.limit_reached": LIMIT_MSG,
    "agent.cut_note": CUT_NOTE,
    "agent.unverified_note": UNVERIFIED_NOTE,
    "agent.turn_cap": TURN_CAP_MSG,
    "agent.turn_time_cap": TURN_TIME_MSG,
    "agent.recursion_limit": RECURSION_MSG,
    "agent.stream_error": STREAM_ERROR_MSG,
    "agent.compact_unsupported": COMPACT_UNSUPPORTED_MSG,
    "agent.compact_pending": COMPACT_PENDING_MSG,
    "format.thousands_sep": THOUSANDS_SEP,
    "tools.deep_research_confirm": DEEP_RESEARCH_CONFIRM,
    "tools.effect_confirm": EFFECT_CONFIRM,
    "citations.correction_discarded": CORRECTION_DISCARDED_NOTE,
    "citations.citation_removed": CITATION_REMOVED_NOTE,
    "citations.sources_label": SOURCES_LABEL,
    "citations.sources_restored": SOURCES_RESTORED_NOTE,
    "http.login_required": LOGIN_REQUIRED_MSG,
    "http.origin_forbidden": ORIGIN_FORBIDDEN_MSG,
    "http.csrf_invalid": CSRF_INVALID_MSG,
    "http.thread_not_found": THREAD_NOT_FOUND_MSG,
    "http.accounts_disabled": ACCOUNTS_DISABLED_MSG,
    "http.wrong_password": WRONG_PASSWORD_MSG,
    "http.title_length": TITLE_LENGTH_MSG,
    "http.store_unavailable": STORE_UNAVAILABLE_MSG,
    "http.memory_not_found": MEMORY_NOT_FOUND_MSG,
    "http.server_needs_app_db": SERVER_NEEDS_APP_DB_MSG,
    "auth.login_error": LOGIN_ERROR,
    "auth.register_error": REGISTER_ERROR,
    "auth.locked_error": LOCKED_ERROR,
    "auth.password_rule": PASSWORD_RULE,
    "startup.missing_api_key": MISSING_API_KEY_MSG,
    "startup.mongo_unreachable": MONGO_UNREACHABLE_MSG,
    "startup.openai_auth": OPENAI_AUTH_MSG,
    "startup.openai_connection": OPENAI_CONNECTION_MSG,
    "startup.openai_api_error": OPENAI_API_ERROR_MSG,
    "startup.model_not_found": MODEL_NOT_FOUND_MSG,
    "startup.none_available": NONE_AVAILABLE,
    "startup.same_db": SAME_DB_MSG,
    "startup.non_local_hosts": NON_LOCAL_HOSTS_MSG,
    "http.not_loopback": NOT_LOOPBACK_MSG,
    "http.message_too_long": MESSAGE_TOO_LONG_MSG,
    "startup.app_db_required": APP_DB_REQUIRED_MSG,
    # FILES_ENABLED (opcionales: core.i18n.FILE_TEXTS; el servidor las exige solo con el interruptor)
    "files.empty": "El archivo está vacío.",
    "files.too_large": "El archivo pesa más de {max} bytes (FILE_MAX_BYTES).",
    "files.type_not_allowed": "Tipo de archivo no permitido. Se aceptan PDF, TXT, MD, CSV, XLSX, DOCX, PNG, JPG, GIF "
                              "y WEBP.",
    "files.content_mismatch": "El contenido del archivo no corresponde a su extensión.",
    "files.macro": "El archivo tiene macros: no se acepta.",
    "files.zip_bomb": "El archivo está demasiado comprimido o tiene demasiadas partes: no se acepta.",
    "files.not_text": "El archivo de texto no es UTF-8 válido o trae datos binarios.",
    "files.encrypted": "El PDF está protegido con contraseña.",
    "files.image_too_big": "La imagen tiene demasiados píxeles.",
    "files.extract_failed": "No pude leer el contenido del archivo.",
    "files.extract_timeout": "Leer el archivo tardó demasiado (FILE_EXTRACT_TIMEOUT).",
    "files.too_many": "Puedes adjuntar como máximo {max} archivos por mensaje (FILE_MAX_PER_MESSAGE).",
    "files.not_found": "No encontré ese archivo en esta conversación.",
    "startup.metrics_need_app_db": "TURN_METRICS y FEEDBACK_ENABLED necesitan la base de negocio: configura "
                                   "APP_MONGODB_URI y APP_MONGODB_DB.",
    "startup.files_bigtool": "FILES_ENABLED=1 no funciona todavía con USE_BIGTOOL=1: bigtool no añade la regla de "
                             "archivos al prompt. Apaga una de las dos.",
    "startup.files_missing_deps": "FILES_ENABLED=1 necesita las dependencias de archivos (falta {module}). "
                                  "Instálalas con: uv pip install --python .venv -e \".[files]\"",
}
