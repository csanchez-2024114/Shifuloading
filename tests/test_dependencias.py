"""Regla de dependencias del refactor núcleo/perfiles (modo estricto):
- assistant.core no importa assistant.packs ni assistant.profiles (el núcleo carga el perfil por nombre, en
  core/profile.py, sin importarlo);
- assistant.packs no importa assistant.profiles;
- un perfil no importa otro perfil.
Cuenta todos los imports: los de nivel de módulo, los de dentro de funciones, los relativos y
importlib.import_module/__import__ con un literal; cada nombre se resuelve por los alias de _compat (un nombre viejo
como assistant.extra_tools es en realidad assistant.packs.tools.utilities). Sin red ni Mongo."""
import ast
from pathlib import Path

from assistant import _compat

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = SRC / "assistant"
WHITELIST: set[tuple[str, str]] = set()  # (archivo relativo a src/, nombre real) permitidos; vacío = modo estricto
# el único sitio del núcleo que nombra a los perfiles: un prefijo para cargarlos por nombre, no un import
PROFILE_LOADER = "assistant/core/profile.py"


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_names(source: str, module: str, is_package: bool = False) -> list[tuple[int, str]]:
    """(línea, nombre real) de cada import de `source` (escrito en el módulo `module`), resuelto por los alias."""
    package = module if is_package else module.rpartition(".")[0]
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - (node.level - 1)]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            names = [prefix] + [f"{prefix}.{a.name}" for a in node.names if a.name != "*"]
        elif isinstance(node, ast.Call) and node.args:
            fn = node.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            arg = node.args[0]
            if fname in ("import_module", "__import__"):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names = [arg.value]
                elif isinstance(arg, ast.JoinedStr) and arg.values and isinstance(arg.values[0], ast.Constant):
                    names = [str(arg.values[0].value)]  # f"assistant.profiles.{x}": cuenta su prefijo
        found += [(node.lineno, _compat.resolve(n) or n) for n in names if n]
    return found


def _violations(layer: str, forbidden) -> list[str]:
    out = []
    for path in sorted((PKG / layer).rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        module = _module_name(path)
        for line, name in imported_names(path.read_text(encoding="utf-8-sig"), module, path.name == "__init__.py"):
            if rel == PROFILE_LOADER and name.rstrip(".") == "assistant.profiles":
                continue
            if forbidden(module, name) and (rel, name) not in WHITELIST:
                out.append(f"{rel}:{line} importa {name}")
    return out


def _is_layer(name: str, layer: str) -> bool:
    return name == layer or name.startswith(layer + ".")


def test_nucleo_no_importa_packs_ni_perfiles():
    assert not WHITELIST, "modo estricto: la lista blanca debe estar vacía"
    malos = _violations("core", lambda mod, n: _is_layer(n, "assistant.packs") or _is_layer(n, "assistant.profiles"))
    assert not malos, malos


def test_packs_no_importan_perfiles():
    malos = _violations("packs", lambda mod, n: _is_layer(n, "assistant.profiles"))
    assert not malos, malos


def test_un_perfil_no_importa_otro_perfil():
    def otro_perfil(mod, n):
        if not _is_layer(n, "assistant.profiles") or n.count(".") < 2:
            return False
        return n.split(".")[2] != mod.split(".")[2]

    malos = _violations("profiles", otro_perfil)
    assert not malos, malos


def test_el_detector_marca_imports_prohibidos():
    fuente = '''
import importlib
from assistant.core import tools          # permitido
import assistant.extra_tools              # alias: es assistant.packs.tools.utilities

def perezoso(nombre):
    from assistant.profiles.default import PROFILE
    from ..profiles import generic
    importlib.import_module("assistant.profiles.default")
    return importlib.import_module(f"assistant.profiles.{nombre}")
'''
    nombres = [n for _, n in imported_names(fuente, "assistant.core.agent")]
    assert "assistant.core.tools" in nombres
    assert "assistant.packs.tools.utilities" in nombres  # resuelto por el alias
    assert "assistant.profiles.default.PROFILE" in nombres  # dentro de una función
    assert "assistant.profiles.generic" in nombres  # relativo
    assert nombres.count("assistant.profiles.default") >= 2 and "assistant.profiles." in nombres  # import_module
