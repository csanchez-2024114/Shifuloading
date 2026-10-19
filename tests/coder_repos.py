"""Fixture `repo_factory` para los tests del codificador: devuelve una función que crea un almacén vacío, en memoria
o en Mongo local (base temporal assistant_ux_tmp_coder_*, borrada al terminar)."""
import pytest

from assistant.core.coder.memory import MemoryCoderRepo

KINDS = ["memoria"]


@pytest.fixture(params=KINDS)
def repo_factory(request):
    if request.param == "memoria":
        yield MemoryCoderRepo
        return
