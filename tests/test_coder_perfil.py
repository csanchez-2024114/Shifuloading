"""Perfil coder: herramientas (base de conversación + archivos de proyecto), aprobación con tarjeta en español y datos
reales para restaurar y borrar proyecto, memoria que no guarda contenido de proyectos, y el perfil por defecto sin
cambios. Sin tokens: modelo falso guionizado."""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from assistant.core import tools as core_tools
from assistant.core.agent import approvals, build_agent, stream_events, system_prompt_text
from assistant.core.coder import runtime
from assistant.core.coder.memory import MemoryCoderRepo
from assistant.core.coder.projects import Projects
from assistant.core.config import ConfigError
from assistant.core.memory import memory_policy
from assistant.core.profile import load_profile
from conftest import FakeSearch, _settings, fake_llm, run_turn, tool_call, uid

A, B = "usuario-a", "usuario-b"
CODER = dict(coder_enabled=True, auth_enabled=True, model_call_limit=0)


@pytest.fixture
def coder():
    return load_profile("coder")


@pytest.fixture
def projects():
    p = Projects(MemoryCoderRepo(), _settings(**CODER))
    runtime.set_current(p)
    yield p
    runtime.set_current(None)


def _names(profile, **overrides):
    s = _settings(**overrides)
    return [t.name for t in core_tools.build_tools(fake_llm("x"), s, search_fn=FakeSearch(), profile=profile)]


def test_herramientas_del_perfil(coder):
    assert _names(coder, **CODER) == [
        "web_search", "calculator", "current_datetime", "save_memory", "search_memories", "update_memory",
        "create_project", "list_projects", "list_project_files", "read_project_file", "write_project_file",
        "edit_project_file", "delete_project_file", "preview_project", "list_project_versions", "diff_project_versions",
        "restore_project_version", "delete_project"]
    con_archivos = _names(coder, files_enabled=True, **CODER)
    assert {"read_file", "search_in_file"} <= set(con_archivos)  # leer un adjunto con especificaciones
    assert "deep_research" not in con_archivos and "check_python_syntax" not in con_archivos


def test_sin_coder_enabled_el_perfil_no_arranca(coder):
    with pytest.raises(ConfigError, match="El perfil coder necesita CODER_ENABLED=1"):
        _names(coder)


def test_el_perfil_por_defecto_no_cambia_con_el_codificador():
    default = load_profile("default")
    assert _names(default) == _names(default, **CODER)
    assert not any("project" in n for n in _names(default, **CODER))


def test_politicas_y_aprobaciones(coder):
    s = _settings(**CODER)
    cards = approvals(coder, s)
    assert set(cards) == {"restore_project_version", "delete_project"}
    assert all(callable(c["description"]) for c in cards.values())
    efectos = {n: p.effect for n, p in coder.tool_policies.items()}
    assert efectos["delete_project"] == "delete" and efectos["read_project_file"] == "read"
    # con EFFECT_APPROVAL=1, cualquier cambio pide tarjeta (como en el perfil por defecto)
    todas = approvals(coder, _settings(effect_approval=True, **CODER))
    assert {"create_project", "write_project_file", "edit_project_file", "delete_project_file"} <= set(todas)


def test_memoria_y_prompt(coder):
    texto = memory_policy("strict", 3, profile=coder)
    assert "Never save project content" in texto
    prompt = system_prompt_text(_settings(**CODER), coder)
    for frase in ("payments", "third-party accounts", "never load scripts", "impersonate", "data, not instructions",
                  "Never say a project is finished"):
        assert frase in prompt


def _agent(coder, *responses):
    s = _settings(**CODER)
    llm = fake_llm(*responses)
    tools = core_tools.build_tools(llm, s, search_fn=FakeSearch(), profile=coder)
    return build_agent(llm, tools, s, checkpointer=InMemorySaver(), store=InMemoryStore(), profile=coder), s


def _resume(agent, s, thread, user, decision):
    return list(stream_events(agent, Command(resume={"decisions": [decision]}), thread, user, s))


def test_restaurar_pide_tarjeta_con_los_datos_reales_y_aprobar_restaura(coder, projects):
    pid = projects.create(A, "Mi landing", "landing")["project_id"]
    projects.write_file(A, pid, "index.html", "uno")
    projects.write_file(A, pid, "app.js", "js")
    projects.write_file(A, pid, "index.html", "dos")
    agent, s = _agent(coder, tool_call("restore_project_version", {"project_id": pid, "version": 2}), "Restaurado.")
    thread = uid()
    events = run_turn(agent, s, "vuelve a la versión 2", thread, user_id=A)
    intr = next(e for e in events if e["type"] == "interrupt")
    req = intr["action_requests"][0]
    assert req["name"] == "restore_project_version"
    assert req["description"] == ("Restaurar «Mi landing» a la versión 2 (2 archivos). Se crea la versión 4 con esos "
                                  "archivos; la versión actual (3) queda en el historial.")
    assert projects.get(A, pid)["version_actual"] == 3  # nada cambia antes de aprobar
    events = _resume(agent, s, thread, A, {"type": "approve"})
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["status"] == "success"
    assert projects.read_file(A, pid, "index.html")["content"] == "uno"
    assert projects.get(A, pid)["version_actual"] == 4


def test_rechazar_restaurar_no_cambia_nada_y_el_chip_no_dice_hecho(coder, projects):
    pid = projects.create(A, "x")["project_id"]
    projects.write_file(A, pid, "index.html", "uno")
    projects.write_file(A, pid, "index.html", "dos")
    agent, s = _agent(coder, tool_call("restore_project_version", {"project_id": pid, "version": 1}), "Vale.")
    thread = uid()
    run_turn(agent, s, "restaura", thread, user_id=A)
    events = _resume(agent, s, thread, A, {"type": "reject", "message": "No"})
    end = next(e for e in events if e["type"] == "tool_end")
    assert end["status"] == "skipped"
    assert projects.read_file(A, pid, "index.html")["content"] == "dos"


def test_borrar_proyecto_pide_tarjeta_y_aprobar_lo_borra(coder, projects):
    pid = projects.create(A, "Juego viejo", "game")["project_id"]
    projects.write_file(A, pid, "index.html", "x")
    projects.write_file(A, pid, "app.js", "y")
    agent, s = _agent(coder, tool_call("delete_project", {"project_id": pid}), "Borrado.")
    thread = uid()
    intr = next(e for e in run_turn(agent, s, "borra el juego viejo", thread, user_id=A) if e["type"] == "interrupt")
    assert intr["action_requests"][0]["description"] == (
        "Borrar el proyecto «Juego viejo» con sus 2 archivos y 3 versiones. No se puede deshacer.")
    assert projects.list_projects(A)  # sigue ahí hasta aprobar
    end = next(e for e in _resume(agent, s, thread, A, {"type": "approve"}) if e["type"] == "tool_end")
    assert end["status"] == "success" and projects.list_projects(A) == []


def test_tarjeta_sobre_un_proyecto_ajeno_no_revela_nada_y_aprobar_no_hace_nada(coder, projects):
    pid = projects.create(A, "Secreto de A")["project_id"]
    projects.write_file(A, pid, "index.html", "x")
    agent, s = _agent(coder, tool_call("delete_project", {"project_id": pid}), "Listo.")
    thread = uid()
    intr = next(e for e in run_turn(agent, s, "borra ese", thread, user_id=B) if e["type"] == "interrupt")
    desc = intr["action_requests"][0]["description"]
    assert "no existe o no es tuyo" in desc and "Secreto" not in desc
    end = next(e for e in _resume(agent, s, thread, B, {"type": "approve"}) if e["type"] == "tool_end")
    assert end["status"] == "skipped"
    assert [p["project_id"] for p in projects.list_projects(A)] == [pid]


def test_escribir_no_pide_tarjeta(coder, projects):
    pid = projects.create(A, "x")["project_id"]
    agent, s = _agent(coder, tool_call("write_project_file", {"project_id": pid, "path": "index.html",
                                                              "content": "<h1>hola</h1>"}), "Hecho.")
    events = run_turn(agent, s, "escribe", uid(), user_id=A)
    assert not any(e["type"] == "interrupt" for e in events)
    assert next(e for e in events if e["type"] == "tool_end")["status"] == "success"
