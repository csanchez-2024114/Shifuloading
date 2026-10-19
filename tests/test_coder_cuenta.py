"""Agente codificador: borrar la cuenta borra también todos sus proyectos y versiones (en memoria y en Mongo local, base
temporal assistant_ux_tmp_coder_* que se borra al terminar); los de otro usuario no se tocan. Los recursos en GridFS
se suman a este mismo test en la Fase D. Sin tokens."""
import uuid

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import _settings, build_test_agent

ORIGIN = {"Origin": "http://testserver"}
PW = "contraseña-larga-1"


def _login(app, email):
    c = TestClient(app, headers=ORIGIN)
    r = c.post("/auth/register", json={"email": email, "password": PW, "display_name": "U"})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c, app.state.coder  # (cliente, proyectos)


@pytest.fixture(params=["memoria", "mongo"])
def appdata(request):
    from assistant.core.appdata.memory import MemoryAppData

    if request.param == "memoria":
        yield MemoryAppData()
        return
    from assistant.core.appdata.mongo import MongoAppData
    from coder_repos import TMP_PREFIX

    client = request.getfixturevalue("mongo_client")
    name = TMP_PREFIX + uuid.uuid4().hex[:12]
    yield MongoAppData(client, name)
    client.drop_database(name)


def _todo(repo, pid) -> int:
    return len(repo.file_rows(pid)) + len(repo.list_versions(pid))


def test_borrar_la_cuenta_borra_sus_proyectos(appdata):
    from assistant.core import server

    s = _settings(auth_enabled=True, coder_enabled=True, trusted_hosts=("127.0.0.1", "testserver"))
    app = server.create_app(agent=build_test_agent(["hola"], s, checkpointer=InMemorySaver()), settings=s,
                            store=InMemoryStore(), appdata=appdata)
    a, projects = _login(app, "ana@ejemplo.com")
    b, _ = _login(app, "beto@ejemplo.com")
    ana = appdata.users.get_by_email("ana@ejemplo.com")["user_id"]
    beto = appdata.users.get_by_email("beto@ejemplo.com")["user_id"]
    suyos = []
    for nombre in ("landing", "juego"):
        pid = projects.create(ana, nombre)["project_id"]
        projects.write_file(ana, pid, "index.html", "<h1>x</h1>")
        projects.edit_file(ana, pid, "index.html", [{"old": "x", "new": "y"}], expected_version=1)
        suyos.append(pid)
    de_beto = projects.create(beto, "suyo")["project_id"]
    projects.write_file(beto, de_beto, "index.html", "b")
    repo = projects.repo
    assert all(_todo(repo, pid) == 5 for pid in suyos)  # 2 filas + 3 versiones

    r = a.post("/auth/delete-account", json={"password": PW})
    assert r.status_code == 200, r.text
    assert projects.list_projects(ana) == []
    assert all(_todo(repo, pid) == 0 for pid in suyos)
    assert [p["project_id"] for p in projects.list_projects(beto)] == [de_beto]
    assert _todo(repo, de_beto) == 3
    if hasattr(repo, "db"):  # Mongo: ni un documento de Ana en ninguna coder_*
        for col in repo.db.list_collection_names():
            if col.startswith("coder_"):
                assert repo.db[col].count_documents({"user_id": ana}) == 0, col
