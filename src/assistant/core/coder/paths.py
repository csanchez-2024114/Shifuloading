"""Saneamiento de rutas de archivos de un proyecto y de nombres de proyecto. Una ruta válida es relativa, en
minúsculas, con segmentos [a-z0-9._-], sin "..", sin segmentos ocultos ni nombres reservados de Windows, con una
extensión permitida; los recursos binarios solo viven bajo assets/."""
import re
import unicodedata

from assistant.core.coder.errors import CoderError

# extensión -> tipo MIME. Texto: lo que escribe el agente. Recursos: lo que sube el usuario (Fase D), solo en assets/.
TEXT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}
ASSET_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
}
ASSET_DIR = "assets/"
PATH_MAX = 120
DEPTH_MAX = 4
NAME_MAX = 60
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9._-]*")
_WINDOWS_RESERVED = re.compile(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?")


def safe_path(raw: str) -> str:
    """La ruta normalizada (NFKC, minúsculas) o CoderError("invalid_path", reason=...)."""
    def bad(reason: str):
        return CoderError("invalid_path", path=str(raw)[:PATH_MAX], reason=reason)

    if not isinstance(raw, str) or not raw.strip():
        raise bad("empty")
    path = unicodedata.normalize("NFKC", raw).strip().lower()
    if len(path) > PATH_MAX:
        raise bad("too_long")
    if any(c in path for c in "\\:%") or any(unicodedata.category(c).startswith("C") for c in path):
        raise bad("forbidden_character")
    if path.startswith("/") or path.startswith("~"):
        raise bad("absolute")
    segments = path.split("/")
    if len(segments) > DEPTH_MAX:
        raise bad("too_deep")
    for seg in segments:
        if seg in ("", ".", ".."):
            raise bad("traversal")
        if not _SEGMENT.fullmatch(seg) or seg.endswith("."):
            raise bad("forbidden_character")
        if _WINDOWS_RESERVED.fullmatch(seg):
            raise bad("reserved_name")
    mime_for(path)
    return path


def extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[name.rfind("."):] if "." in name else ""


def is_asset(path: str) -> bool:
    return extension(path) in ASSET_TYPES


def mime_for(path: str) -> str:
    """Tipo MIME de una ruta ya normalizada; CoderError("type_not_allowed") si la extensión no está permitida o si un
    recurso binario no está bajo assets/."""
    ext = extension(path)
    if ext in TEXT_TYPES:
        return TEXT_TYPES[ext]
    if ext in ASSET_TYPES:
        if not path.startswith(ASSET_DIR):
            raise CoderError("type_not_allowed", path=path, reason="assets_only")
        return ASSET_TYPES[ext]
    raise CoderError("type_not_allowed", path=path, reason="extension")


def safe_name(raw: str) -> str:
    """Nombre visible de un proyecto: NFKC, sin control ni <>"'`, espacios colapsados, ≤ 60 caracteres."""
    name = unicodedata.normalize("NFKC", raw or "")
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C") and c not in "<>\"'`")
    name = " ".join(name.split())[:NAME_MAX].strip()
    if not name:
        raise CoderError("invalid_name")
    return name
