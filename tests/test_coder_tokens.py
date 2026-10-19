"""Tokens de vista previa del codificador: solo se guarda su hash, caducan a los 30 minutos, quedan atados a una
versión, mueren con el proyecto, y uno inexistente, caducado, mal formado o de un proyecto borrado da lo mismo (None).
Memoria y Mongo local temporal. Sin tokens de modelo."""
from datetime import timedelta

import pytest

from assistant.core.coder import projects as projects_mod
from assistant.core.coder.projects import Projects
from coder_repos import repo_factory  # noqa: F401
from conftest import _settings

A = "usuario-a"


def _p(repo):
    return Projects(repo, _settings())


def _stored(repo) -> list[dict]:
    if hasattr(repo, "db"):
        return [dict(d) for d in repo.db["coder_preview_tokens"].find({}, {"_id": 0})]
    return list(repo.previews.values())


def test_emitir_y_resolver_solo_guarda_el_hash(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "<h1>v1</h1>")
    issued = p.issue_preview(A, pid)
    token = issued["token"]
    assert len(token) >= 43 and issued["version"] == 1
    assert p.resolve_preview(token) == {"project_id": pid, "version": 1}
    docs = _stored(repo)
    assert len(docs) == 1 and token not in str(docs)  # nunca el token en claro
    left = docs[0]["expira"] - docs[0]["creado"]
    assert timedelta(minutes=29) < left <= timedelta(minutes=30)


def test_el_token_queda_atado_a_su_version(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "<h1>v1</h1>")
    token = p.issue_preview(A, pid)["token"]
    p.edit_file(A, pid, "index.html", [{"old": "v1", "new": "v2"}], expected_version=1)
    found = p.resolve_preview(token)
    assert p.version_file(pid, found["version"], "index.html")["content"] == "<h1>v1</h1>"
    assert p.version_file(pid, 2, "index.html")["content"] == "<h1>v2</h1>"


@pytest.mark.parametrize("ruta", ["../index.html", "/index.html", "no.html", "INDEX.HTML%00", "", "a\\b.html"])
def test_archivo_fuera_de_la_version(repo_factory, ruta):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "x")
    assert p.version_file(pid, 1, ruta) is None
    assert p.version_file(pid, 99, "index.html") is None


def test_caducado_inexistente_mal_formado_y_de_proyecto_borrado(repo_factory, monkeypatch):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "x")
    vigente = p.issue_preview(A, pid)["token"]
    caducado = p.issue_preview(A, pid)["token"]
    real_now = projects_mod._now
    monkeypatch.setattr(projects_mod, "_now", lambda: real_now() + timedelta(minutes=31))
    assert p.resolve_preview(caducado) is None
    monkeypatch.setattr(projects_mod, "_now", real_now)
    assert p.resolve_preview(vigente) is not None
    for malo in ("", "x" * 43, vigente[:-1] + ("A" if vigente[-1] != "A" else "B"), vigente + "/../x", None, 42,
                 {"$ne": None}, "a" * 500):
        assert p.resolve_preview(malo) is None
    p.delete_project(A, pid)
    assert p.resolve_preview(vigente) is None
    assert _stored(repo) == []  # borrar el proyecto borra sus tokens


def test_mongo_indice_ttl(mongo_client):
    import uuid

    from assistant.core.coder.mongo import MongoCoderRepo
    from coder_repos import TMP_PREFIX

    name = TMP_PREFIX + uuid.uuid4().hex[:12]
    try:
        repo = MongoCoderRepo(mongo_client[name])
        p = _p(repo)
        pid = p.create(A, "x")["project_id"]
        p.issue_preview(A, pid)
        ttl = [i for i in mongo_client[name]["coder_preview_tokens"].list_indexes() if "expireAfterSeconds" in i]
        assert [(list(i["key"].keys()), i["expireAfterSeconds"]) for i in ttl] == [(["expira"], 0)]
    finally:
        mongo_client.drop_database(name)
