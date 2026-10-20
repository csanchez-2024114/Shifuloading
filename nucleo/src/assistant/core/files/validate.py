"""Validación de un archivo subido, por su contenido y no solo por su extensión. Nada del archivo se ejecuta aquí: se
leen bytes mágicos y, de los zip de Office, solo el índice de entradas."""
import io
import re
import unicodedata
import zipfile

# tipo -> (extensiones, mime)
ALLOWED = {
    "pdf": ((".pdf",), "application/pdf"),
    "txt": ((".txt",), "text/plain"),
    "md": ((".md", ".markdown"), "text/markdown"),
    "csv": ((".csv",), "text/csv"),
    "xlsx": ((".xlsx",), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "docx": ((".docx",), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "png": ((".png",), "image/png"),
    "jpeg": ((".jpg", ".jpeg"), "image/jpeg"),
    "gif": ((".gif",), "image/gif"),
    "webp": ((".webp",), "image/webp"),
}
TEXT_KINDS = frozenset({"txt", "md", "csv"})
ZIP_MAX_ENTRIES = 1000
ZIP_MAX_UNCOMPRESSED = 100_000_000
ZIP_MAX_RATIO = 200  # descomprimido / comprimido, por entrada
NAME_MAX = 120


class FileRejected(Exception):
    """El archivo no se acepta. `code` es la clave del aviso al usuario (files.<code>) y `values` sus datos."""

    def __init__(self, code: str, **values):
        super().__init__(code)
        self.code = code
        self.values = values


def sanitize_name(name: str) -> str:
    """Solo el nombre (sin rutas), NFKC, sin caracteres de control ni reservados de Windows, ≤ 120 caracteres
    conservando la extensión."""
    name = unicodedata.normalize("NFKC", name or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*')
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "archivo"
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return name[:NAME_MAX]
    ext = ext[:10]
    return f"{stem[: NAME_MAX - len(ext) - 1].rstrip(' .')}.{ext}"


def kind_by_extension(name: str) -> str | None:
    lower = name.lower()
    return next((k for k, (exts, _) in ALLOWED.items() if lower.endswith(exts)), None)


def sniff(data: bytes) -> str | None:
    """Tipo por bytes mágicos; "zip" para los de Office (se decide después)."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    return None


def office_kind(data: bytes) -> str:
    """xlsx o docx según las entradas del zip. Rechaza macros, zips raros y zip bombs."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        raise FileRejected("content_mismatch") from exc
    if len(infos) > ZIP_MAX_ENTRIES or sum(i.file_size for i in infos) > ZIP_MAX_UNCOMPRESSED:
        raise FileRejected("zip_bomb")
    if any(i.compress_size and i.file_size / i.compress_size > ZIP_MAX_RATIO for i in infos):
        raise FileRejected("zip_bomb")
    names = {i.filename for i in infos}
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise FileRejected("macro")
    if "[Content_Types].xml" not in names:
        raise FileRejected("content_mismatch")
    types = zf.read("[Content_Types].xml").decode("utf-8", "replace").lower()
    if "macroenabled" in types or "vbaproject" in types:
        raise FileRejected("macro")
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "word/document.xml" in names:
        return "docx"
    raise FileRejected("content_mismatch")


def decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise FileRejected("not_text")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileRejected("not_text") from exc


def validate(data: bytes, filename: str, max_bytes: int) -> tuple[str, str, str]:
    """(tipo, mime, nombre saneado) o FileRejected."""
    name = sanitize_name(filename)
    if not data:
        raise FileRejected("empty")
    if max_bytes and len(data) > max_bytes:
        raise FileRejected("too_large", max=max_bytes)
    kind = kind_by_extension(name)
    if kind is None:
        raise FileRejected("type_not_allowed")
    found = sniff(data)
    if kind in TEXT_KINDS:
        if found is not None:  # un binario conocido con extensión de texto
            raise FileRejected("content_mismatch")
        decode_text(data)
    elif kind in ("xlsx", "docx"):
        if found != "zip" or office_kind(data) != kind:
            raise FileRejected("content_mismatch")
    elif found != kind:
        raise FileRejected("content_mismatch")
    return kind, ALLOWED[kind][1], name
