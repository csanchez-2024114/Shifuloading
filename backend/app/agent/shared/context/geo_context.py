"""
geo_context — agente_v3

Builds a compact geographic + language context block injected into the
user prompt of LLM-calling nodes (semantic_intake, bigtools_inspector)
and into the time context block of the responder.

Injecting into the USER prompt (not system prompt) preserves the cached
system prompt prefix, keeping LLM provider cache hits intact.
"""

from __future__ import annotations

# ISO 3166-1 alpha-2 → (language label, register note)
_COUNTRY_LANGUAGE: dict[str, tuple[str, str]] = {
    # Spanish Latin American
    "GT": ("Spanish", "Latin American — Guatemala"),
    "MX": ("Spanish", "Latin American — Mexico"),
    "CO": ("Spanish", "Latin American — Colombia"),
    "AR": ("Spanish", "Latin American — Argentina"),
    "PE": ("Spanish", "Latin American — Peru"),
    "CL": ("Spanish", "Latin American — Chile"),
    "VE": ("Spanish", "Latin American — Venezuela"),
    "EC": ("Spanish", "Latin American — Ecuador"),
    "BO": ("Spanish", "Latin American — Bolivia"),
    "PY": ("Spanish", "Latin American — Paraguay"),
    "UY": ("Spanish", "Latin American — Uruguay"),
    "CR": ("Spanish", "Latin American — Costa Rica"),
    "PA": ("Spanish", "Latin American — Panama"),
    "HN": ("Spanish", "Latin American — Honduras"),
    "SV": ("Spanish", "Latin American — El Salvador"),
    "NI": ("Spanish", "Latin American — Nicaragua"),
    "DO": ("Spanish", "Latin American — Dominican Republic"),
    "CU": ("Spanish", "Latin American — Cuba"),
    "PR": ("Spanish", "Latin American — Puerto Rico"),
    # Spanish Castilian
    "ES": ("Spanish", "Castilian — Spain"),
    # English
    "US": ("English", "American"),
    "GB": ("English", "British"),
    "CA": ("English", "Canadian"),
    "AU": ("English", "Australian"),
    "NZ": ("English", "New Zealand"),
    # Portuguese
    "BR": ("Portuguese", "Brazilian"),
    "PT": ("Portuguese", "European — Portugal"),
    # French
    "FR": ("French", "European — France"),
    "BE": ("French", "Belgium"),
    "CH": ("French", "Switzerland"),
    # German
    "DE": ("German", "Germany"),
    "AT": ("German", "Austria"),
    # Italian
    "IT": ("Italian", "Italy"),
    # Other
    "JP": ("Japanese", "Japan"),
    "KR": ("Korean", "Korea"),
    "CN": ("Chinese", "Mandarin — China"),
}


def get_language_hint(country_code: str | None) -> str | None:
    """Return a language hint string for a given ISO country code, or None."""
    if not country_code:
        return None
    entry = _COUNTRY_LANGUAGE.get(country_code.upper())
    if not entry:
        return None
    lang, register = entry
    return f"{lang} ({register})"


def build_geo_block(
    timezone: str | None,
    location: str | None,
    country_code: str | None = None,
) -> str:
    """
    Return a compact ## User Context block for LLM prompts.

    Returns empty string when all inputs are None/empty — never injects
    noise into prompts when no geo data is available.
    """
    if not timezone and not location:
        return ""

    lines: list[str] = ["## User Context [geographic — use for location & language awareness]"]

    if location:
        lines.append(f"Location : {location}")
    if timezone:
        lines.append(f"Timezone : {timezone}")

    lang = get_language_hint(country_code)
    if lang:
        lines.append(
            f"Language : {lang} — understand regional expressions, "
            "local slang, and cultural references accordingly."
        )

    return "\n".join(lines)
