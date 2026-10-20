"""Fixture `repo_factory` para los tests del codificador: devuelve una función que crea un almacén vacío, en memoria
o en Mongo local. Cada almacén Mongo usa su propia base temporal assistant_ux_tmp_coder_<id>, que se borra al terminar
el test (nunca una base real)."""
import uuid

import pytest

from assistant.core.coder.memory import MemoryCoderRepo

TMP_PREFIX = "assistant_ux_tmp_coder_"


@pytest.fixture(params=["memoria", "mongo"])
def repo_factory(request):
    if request.param == "memoria":
        yield MemoryCoderRepo
        return
    from assistant.core.coder.mongo import MongoCoderRepo

    client = request.getfixturevalue("mongo_client")  # se salta si Mongo local no responde
    names: list[str] = []

    def make():
        names.append(TMP_PREFIX + uuid.uuid4().hex[:12])
        return MongoCoderRepo(client[names[-1]])

    yield make
    for name in names:
        client.drop_database(name)
