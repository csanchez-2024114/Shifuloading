"""Validación y preparación de los recursos que sube el usuario para un proyecto (imágenes, audio y datos). El tipo se
decide por el contenido, no solo por la extensión. Lista permitida: png, jpg/jpeg, gif, webp, mp3, ogg, json, csv y
txt; SVG nunca (puede llevar scripts). Las imágenes se reencodean sin metadatos en un subproceso aislado
(asset_worker); al mp3 se le quitan las etiquetas ID3; un binario con marcas de HTML/SVG/JS dentro (políglota) se
rechaza. Nada del archivo se ejecuta aquí."""
import json
import re

from assistant.core.coder.asset_worker import reencode
from assistant.core.coder.errors import CoderError
from assistant.core.files.validate import sanitize_name, sniff

# extensión -> (tipo, mime con el que se servirá, extensión canónica)
asset_kinds = {
    ".png": ("png", "image/png", ".png"),
    ".jpg": ("jpeg", "image/jpeg", ".jpg"),
    ".jpeg": ("jpeg", "image/jpeg", ".jpg"),
    ".gif": ("gif", "image/gif", ".gif"),
    ".webp": ("webp", "image/webp", ".webp"),
    ".mp3": ("mp3", "audio/mpeg", ".mp3"),
    ".ogg": ("ogg", "audio/ogg", ".ogg"),
    ".json": ("json", "application/json; charset=utf-8", ".json"),
    ".csv": ("csv", "text/csv; charset=utf-8", ".csv"),
    ".txt": ("txt", "text/plain; charset=utf-8", ".txt"),
}
image_kinds = ("png", "jpeg", "gif", "webp")
text_kinds = ("json", "csv", "txt")
# marcas de documento activo dentro de un binario: un políglota (imagen o audio que también es HTML/SVG/JS)
_markup = re.compile(rb"<\s*(?:script|svg|html|iframe|body|object|embed|\?xml)|javascript\s*:", re.I)


def _audio_kind(data: bytes) -> str | None:
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


def _strip_id3(data: bytes) -> bytes:
    """Quita la etiqueta ID3v2 del principio y la ID3v1 del final (artista, comentarios, imágenes incrustadas...)."""
    if data.startswith(b"ID3") and len(data) > 10:
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        data = data[10 + size + (10 if data[5] & 0x10 else 0):]
    if len(data) >= 128 and data[-128:-125] == b"TAG":
        data = data[:-128]
    return data


def prepare_asset(data: bytes, filename: str, max_bytes: int, timeout: float = 20.0) -> dict:
    """{"kind", "mime", "name", "data", "bytes", "width"?, "height"?} listo para guardar, o CoderError:
    asset_empty, asset_too_large, asset_type_not_allowed, asset_mismatch, asset_polyglot, asset_too_many_pixels,
    asset_timeout."""
    name = sanitize_name(filename)
    stem, dot, ext = name.rpartition(".")
    ext = f".{ext.lower()}" if dot else ""
    if not data:
        raise CoderError("asset_empty")
    if max_bytes and len(data) > max_bytes:
        raise CoderError("asset_too_large", limit=max_bytes)
    if ext not in asset_kinds:
        raise CoderError("asset_type_not_allowed", ext=ext or "(none)")
    kind, mime, canonical = asset_kinds[ext]
    name = (stem or "archivo") + canonical
    found = sniff(data) or _audio_kind(data)
    if kind in text_kinds:
        if found is not None or b"\x00" in data:
            raise CoderError("asset_mismatch")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CoderError("asset_mismatch") from exc
        if kind == "json":
            try:
                json.loads(text)
            except ValueError as exc:
                raise CoderError("asset_mismatch") from exc
        out = text.encode("utf-8")
        return {"kind": kind, "mime": mime, "name": name, "data": out, "bytes": len(out)}
    if found != kind:
        raise CoderError("asset_mismatch")  # p. ej. un PNG con extensión .jpg
    if _markup.search(data):
        raise CoderError("asset_polyglot")
    if kind in image_kinds:
        clean = reencode(data, kind, timeout)
        if max_bytes and len(clean["data"]) > max_bytes:
            raise CoderError("asset_too_large", limit=max_bytes)
        return {"kind": kind, "mime": mime, "name": name, "data": clean["data"], "bytes": len(clean["data"]),
                "width": clean["width"], "height": clean["height"]}
    out = _strip_id3(data) if kind == "mp3" else data
    if not out:
        raise CoderError("asset_mismatch")
    return {"kind": kind, "mime": mime, "name": name, "data": out, "bytes": len(out)}
