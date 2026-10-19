"""Agente codificador sobre Mongo local (base temporal assistant_ux_tmp_coder_*, borrada al terminar): nada se crea
hasta la primera escritura, índices únicos y project_id único entre usuarios. Sin tokens."""
import pytest

from assistant.core.coder import projects as projects_mod
from assistant.core.coder.errors import CoderError
from assistant.core.coder.projects import Projects
from coder_repos import repo_factory  # noqa: F401
from conftest import _settings


@pytest.fixture
def mongo_repo(mongo_client):
    import uuid

    from assistant.core.coder.mongo import MongoCoderRepo
    from coder_repos import TMP_PREFIX

    name = TMP_PREFIX + uuid.uuid4().hex[:12]
    yield MongoCoderRepo(mongo_client[name]), mongo_client, name
    mongo_client.drop_database(name)


def test_leer_no_crea_colecciones(mongo_repo):
    repo, client, name = mongo_repo
    p = Projects(repo, _settings())
    assert p.list_projects("u") == [] and p.usage("u") == {"projects": 0, "bytes": 0}
    with pytest.raises(CoderError):
        p.get("u", "p_000000000000")
    assert repo.list_versions("p_000000000000") == [] and repo.file_rows("p_000000000000") == []
    assert [c for c in client[name].list_collection_names() if c.startswith("coder_")] == []


def test_indices_unicos_tras_la_primera_escritura(mongo_repo):
    repo, client, name = mongo_repo
    p = Projects(repo, _settings())
    pid = p.create("u", "x")["project_id"]
    p.write_file("u", pid, "index.html", "hola")
    db = client[name]
    unicos = {c: sorted(tuple(i["key"].keys()) for i in db[c].list_indexes() if i.get("unique"))
              for c in ("coder_projects", "coder_files", "coder_versions")}
    assert unicos == {
        "coder_projects": [("project_id",), ("user_id", "project_id")],
        "coder_files": [("project_id", "ruta", "version")],
        "coder_versions": [("project_id", "version")],
    }
    assert "contenido" not in repo.file_rows(pid)[0]


def test_project_id_repetido_entre_usuarios_se_reintenta(repo_factory, monkeypatch):
    p = Projects(repo_factory(), _settings())
    ids = iter(["aaaaaaaaaaaa", "aaaaaaaaaaaa", "bbbbbbbbbbbb"] + ["cccccccccccc"] * 4)
    monkeypatch.setattr(projects_mod.secrets, "token_hex", lambda n: next(ids))
    assert p.create("a", "uno")["project_id"] == "p_aaaaaaaaaaaa"
    assert p.create("b", "dos")["project_id"] == "p_bbbbbbbbbbbb"  # el primer intento chocó con el de "a"
    p.create("c", "tres")
    with pytest.raises(CoderError) as e:  # tres choques seguidos
        p.create("d", "cuatro")
    assert e.value.code == "conflict"
    assert p.list_projects("d") == []
