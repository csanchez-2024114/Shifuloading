"""Herramientas inofensivas de demostración para bigtool (BIGTOOL_DEMO_TOOLS): funciones de math y de texto, para
probar la búsqueda de herramientas con decenas de ellas."""
import math
import re
import types
import unicodedata
import warnings

from langchain_core._api.beta_decorator import LangChainBetaWarning
from langchain_core.tools import BaseTool, tool
from langgraph_bigtool.utils import convert_positional_only_function_to_tool

_EXCLUIR_MATH = {"factorial", "comb", "perm", "prod"}  # ponytail: pueden tardar muchísimo con números enormes


def _herramientas_texto() -> list[BaseTool]:
    @tool
    def to_uppercase(text: str) -> str:
        """Convert text to UPPERCASE."""
        return text.upper()

    @tool
    def to_lowercase(text: str) -> str:
        """Convert text to lowercase."""
        return text.lower()

    @tool
    def title_case(text: str) -> str:
        """Capitalize The First Letter Of Each Word."""
        return text.title()

    @tool
    def reverse_text(text: str) -> str:
        """Reverse the characters of a text."""
        return text[::-1]

    @tool
    def count_words(text: str) -> int:
        """Count the words in a text."""
        return len(text.split())

    @tool
    def count_characters(text: str) -> int:
        """Count the characters in a text (including spaces)."""
        return len(text)

    @tool
    def remove_accents(text: str) -> str:
        """Remove accents/diacritics from a text (an accented vowel becomes the plain vowel)."""
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

    @tool
    def slugify(text: str) -> str:
        """Convert a text to a URL slug (lowercase, hyphens, no accents)."""
        plain = remove_accents.invoke({"text": text}).lower()
        return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")

    @tool
    def is_palindrome(text: str) -> bool:
        """Check whether a text is a palindrome, ignoring spaces, case and accents."""
        plain = re.sub(r"[^a-z0-9]", "", remove_accents.invoke({"text": text}).lower())
        return plain == plain[::-1]

    return [to_uppercase, to_lowercase, title_case, reverse_text, count_words, count_characters,
            remove_accents, slugify, is_palindrome]


def _herramientas_math() -> list[BaseTool]:
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", LangChainBetaWarning)  # la utilidad de bigtool está marcada beta
        for name in dir(math):
            fn = getattr(math, name)
            if name in _EXCLUIR_MATH or not isinstance(fn, types.BuiltinFunctionType):
                continue
            if t := convert_positional_only_function_to_tool(fn):
                out.append(t)
    return out
