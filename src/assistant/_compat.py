"""Compatibilidad de imports tras el refactor núcleo/perfiles: los nombres viejos (`assistant.agent`,
`assistant.server`...) siguen funcionando y son el MISMO objeto de módulo que el nuevo (`assistant.core.agent`...).

No es una reexportación: con `from assistant.core.agent import *` un `monkeypatch.setattr(assistant.agent, ...)`
caería en una copia y el núcleo no lo vería, y las clases se duplicarían. Cubre también submódulos
(`assistant.appdata.mongo`). Cada nombre viejo avisa una vez con DeprecationWarning."""
import importlib
import importlib.abc
import importlib.util
import sys
import warnings

# nombre viejo -> nombre nuevo (se llena en cada paso del movimiento)
ALIASES: dict[str, str] = {}


def resolve(name: str) -> str | None:
    """Nombre nuevo de `name` si es un nombre viejo (o un submódulo de uno); None si no."""
    for old, new in ALIASES.items():
        if name == old or name.startswith(old + "."):
            return new + name[len(old):]
    return None


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target: str):
        self.target = target
        self.saved = None

    def create_module(self, spec):
        warnings.warn(f"{spec.name} se movió a {self.target}; usa el nombre nuevo", DeprecationWarning, stacklevel=2)
        module = importlib.import_module(self.target)
        # la maquinaria de import reescribe __spec__/__package__ con el nombre viejo: se restauran en exec_module
        self.saved = (module.__spec__, module.__loader__, module.__package__)
        return module

    def exec_module(self, module):
        module.__spec__, module.__loader__, module.__package__ = self.saved


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        new = resolve(name)
        return importlib.util.spec_from_loader(name, _AliasLoader(new)) if new else None


def install() -> None:
    if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
