"""Agente codificador, garantías fijas: con todos los CODER_* en 0 las rutas HTTP son exactamente las del tag
pre-agente-codificador, y la poda de versiones nunca borra una versión fijada (p. ej. la publicada) ni sus archivos.
Sin tokens."""
import json
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from assistant.core.coder.projects import Projects
from coder_repos import repo_factory  # noqa: F401
from conftest import _settings, build_test_agent

PREVIA = Path(__file__).parent / "snapshots" / "huella_pre_agente_codificador.json"
CODER_FLAGS = ("coder_enabled", "coder_data_enabled", "coder_sharing_enabled", "coder_public_write_enabled")


def _rutas(app) -> list:
    return sorted([r.path, sorted(getattr(r, "methods", None) or [])] for r in app.routes)


def _app(**overrides):
    from assistant.core import server
    from assistant.core.appdata.memory import MemoryAppData

    s = _settings(**overrides)
    extra = {"appdata": MemoryAppData()} if s.auth_enabled else {}
    return server.create_app(agent=build_test_agent(["x"], s, checkpointer=InMemorySaver()), settings=s,
                             store=InMemoryStore(), **extra)


def test_con_los_coder_en_0_las_rutas_son_las_del_tag():
    s = _settings()
    assert not any(getattr(s, f) for f in CODER_FLAGS)
    previa = json.loads(PREVIA.read_text(encoding="utf-8"))["routes"]
    assert _rutas(_app()) == previa


@pytest.mark.parametrize("overrides", [dict(auth_enabled=True), dict(files_enabled=True),
                                       dict(auth_enabled=True, files_enabled=True)])
def test_con_otros_interruptores_y_coder_en_0_no_aparece_ninguna_ruta_del_codificador(overrides):
    pytest.importorskip("pypdf") if overrides.get("files_enabled") else None
    app = _app(**overrides)
    assert not any(path.startswith("/coder") for path, _ in _rutas(app))
    assert not hasattr(app.state, "coder")


@pytest.mark.parametrize("limite", [1, 2, 5])
def test_la_poda_nunca_borra_la_version_fijada(repo_factory, limite):
    repo = repo_factory()
    p = Projects(repo, _settings(coder_max_versions=limite))
    pid = p.create("u", "x")["project_id"]
    p.write_file("u", pid, "index.html", "publicada")
    p.write_file("u", pid, "app.js", "js publicado")
    repo.update_project("u", pid, {"pinned_versions": [2]})  # la v2 es la publicada
    for i in range(20):
        p.write_file("u", pid, "index.html", f"borrador {i}")
        p.write_file("u", pid, "app.js", f"js {i}")
    versiones = [v["version"] for v in p.list_versions("u", pid, limit=100)]
    actual = p.get("u", pid)["version_actual"]
    assert 2 in versiones and actual in versiones
    assert len(versiones) <= limite + 1  # las `limite` más nuevas (con la actual) + la fijada
    assert p.read_file("u", pid, "index.html", version=2)["content"] == "publicada"
    assert p.read_file("u", pid, "app.js", version=2)["content"] == "js publicado"
    assert p.read_file("u", pid, "index.html")["content"] == "borrador 19"
    # los bytes contados son exactamente los de las filas que quedan
    assert p.get("u", pid)["bytes"] == sum(r["bytes"] for r in repo.file_rows(pid))


def test_restaurar_la_version_fijada_tras_la_poda(repo_factory):
    repo = repo_factory()
    p = Projects(repo, _settings(coder_max_versions=2))
    pid = p.create("u", "x")["project_id"]
    p.write_file("u", pid, "index.html", "publicada")
    repo.update_project("u", pid, {"pinned_versions": [1]})
    for i in range(6):
        p.write_file("u", pid, "index.html", f"b{i}")
    nueva = p.restore("u", pid, 1)
    assert p.read_file("u", pid, "index.html")["content"] == "publicada"
    assert 1 in [v["version"] for v in p.list_versions("u", pid, limit=100)]
    assert p.get("u", pid)["version_actual"] == nueva
