"""Reglas de citas de ANSWER_VERIFY aplicadas en código (no se confía solo en el prompt del verificador).

- Una URL cuenta como respaldada si su forma normalizada (dominio + ruta, sin www, sin parámetros de seguimiento,
  sin fragmento ni barra final) aparece en la evidencia del turno.
- Una cita respaldada nunca se pierde: si la corrección la quita, se vuelve a insertar al final.
- Una cita cuya URL no está en la evidencia se elimina (queda el texto del enlace).
- Una corrección que trae cifras que no están ni en la respuesta original ni en la evidencia se descarta.
"""
import re
from urllib.parse import urlsplit

from assistant.core.i18n import tr

_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")
_BARE_URL = re.compile(r"(?<![(\[])https?://[^\s)\]\"'>]+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def normalize_url(url: str) -> str:
    """dominio + ruta comparables: utm_*, fbclid, etc. y el resto de la query no cuentan."""
    try:
        parts = urlsplit(url.strip().rstrip(".,;:"))
    except ValueError:
        return url
    host = (parts.hostname or "").lower().removeprefix("www.")
    return host + parts.path.rstrip("/")


def urls(text: str) -> list[str]:
    return [u for _, u in _MD_LINK.findall(text)] + _BARE_URL.findall(text)


def _links(text: str) -> list[tuple[str, str, str]]:
    """(texto completo del enlace, título, url) de los enlaces markdown y las URLs sueltas."""
    out = [(m.group(0), m.group(1), m.group(2)) for m in _MD_LINK.finditer(text)]
    out += [(u, "", u) for u in _BARE_URL.findall(text)]
    return out


# encabezado de una sección de fuentes ("## Fuentes", "**Sources:**", "Referencias:"...), sin acentos ni mayúsculas
_SOURCES_HEADING = re.compile(r"^\s*(#{1,6}\s*)?(\*\*|__)?\s*(fuentes|sources|referencias|references|bibliograf\w*)"
                              r"\b[^\n]*$", re.I | re.M)
_HEADING = re.compile(r"^\s*#{1,6}\s", re.M)


def keep_supported(text: str, evidence: str) -> tuple[str, list[str]]:
    """Quita de `text` las URLs que no aparecen en `evidence` (de un enlace markdown queda el título; una URL suelta
    desaparece). Devuelve (texto, URLs quitadas)."""
    supported = {normalize_url(u) for u in urls(evidence)}
    removed = []
    for whole, title, url in _links(text):
        if normalize_url(url) not in supported:
            text = text.replace(whole, title, 1)
            removed.append(url)
    return text, removed


def drop_sources_section(text: str) -> str:
    """Quita las secciones de fuentes: desde su encabezado hasta el siguiente encabezado markdown o el final."""
    while m := _SOURCES_HEADING.search(text):
        nxt = _HEADING.search(text, m.end())
        text = text[:m.start()] + (text[nxt.start():] if nxt else "")
    return text.rstrip()


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def enforce(original: str, correction: str | None, evidence: str) -> tuple[str, str, list[str]]:
    """Aplica las reglas a la corrección (None = el verificador dijo OK: se revisa el original).
    Devuelve (texto final, status, notas). status: "ok" (sin cambios), "corrected" (cambió el texto) o
    "kept_original" (se descartó la corrección del verificador; puede llevar citas inventadas quitadas)."""
    supported = {normalize_url(u) for u in urls(evidence)}
    notes: list[str] = []
    candidate, descartada = original if correction is None else correction, False

    # la corrección no puede agregar cifras que no estén en el original ni en la evidencia
    if correction is not None:
        nuevas = _numbers(correction) - _numbers(original) - _numbers(evidence)
        if nuevas:
            notes.append(tr("citations.correction_discarded", numbers=", ".join(sorted(nuevas))))
            candidate, descartada = original, True

    # citas inventadas (URL fuera de la evidencia): se quita el enlace y queda su título
    for whole, title, url in _links(candidate):
        if normalize_url(url) not in supported:
            candidate = candidate.replace(whole, title, 1)
            notes.append(tr("citations.citation_removed", url=url))

    # citas respaldadas del original que la corrección perdió: se reinsertan
    present = {normalize_url(u) for u in urls(candidate)}
    perdidas = []
    for whole, title, url in _links(original):
        key = normalize_url(url)
        if key in supported and key not in present:
            perdidas.append(f"[{title or key}]({url})")
            present.add(key)
    if perdidas:
        candidate = candidate.rstrip() + "\n\n" + tr("citations.sources_label") + ", ".join(perdidas)
        notes.append(tr("citations.sources_restored"))

    if descartada:
        return candidate, "kept_original", notes
    if " ".join(candidate.split()) == " ".join(original.split()):
        return original, "ok", notes  # el verificador "corrigió" sin cambiar nada: no se marca como corrección
    return candidate, "corrected", notes
