"""check_python_syntax: solo ast.parse. Nunca ejecuta, importa ni toca archivos o red. Sin tokens ni Mongo."""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeSearch, fake_llm, run_turn, tool_call, uid

ROOT = Path(__file__).resolve().parents[1]
# el SyntaxError real de la prueba de 3 escenarios (falta la comilla de apertura de la f-string)
CODIGO_ROTO = '''def f(numero, fecha, ultima_fecha):
    raise SystemExit(
        f"registro {numero} ({fecha}) aparece después "
        f de {ultima_fecha}."
    )
'''


def _check(code):
    from assistant.tools import check_python_syntax
    return check_python_syntax.invoke({"code": code})


def test_codigo_valido_y_error_con_linea_y_columna():
    from assistant.tools import SYNTAX_OK_MSG

    assert _check("def f(x):\n    return x + 1\n") == SYNTAX_OK_MSG
    out = _check(CODIGO_ROTO)
    assert re.match(r"SyntaxError at line 4, column \d+: ", out), out
    assert 'f de {ultima_fecha}."' in out and "^" in out


def test_nunca_ejecuta_el_codigo_recibido(tmp_path, capsys):
    marca = tmp_path / "efecto.txt"
    codigo = (f"open({str(marca)!r}, 'w').write('ejecutado')\n"
              f"import os\nos.system({'echo hola > ' + str(tmp_path / 'sistema.txt')!r})\n"
              "print('IMPRESO')\nraise SystemExit(3)\n")
    assert _check(codigo).startswith("OK")
    assert not marca.exists() and not (tmp_path / "sistema.txt").exists()
    assert "IMPRESO" not in capsys.readouterr().out
    t0 = time.perf_counter()
    assert _check("while True:\n    pass\n").startswith("OK")  # un bucle infinito vuelve al instante
    assert time.perf_counter() - t0 < 1


def test_entradas_raras_no_rompen_la_herramienta():
    from assistant.tools import SYNTAX_MAX_CHARS

    nulos = _check("x = 1\x00")  # bytes nulos: error sin posición
    assert nulos.startswith(("SyntaxError", "Not checked")) and "None" not in nulos
    assert _check("x" * (SYNTAX_MAX_CHARS + 1)).startswith("Not checked")
    assert _check("(" * 5000 + ")" * 5000).startswith(("OK", "Not checked", "SyntaxError"))


def test_el_agente_la_usa_y_la_ui_la_muestra_en_espanol(settings):
    from assistant.agent import build_agent
    from assistant.tools import build_tools

    llm = fake_llm(tool_call("check_python_syntax", {"code": CODIGO_ROTO}, "s1"), "Corregido")
    agent = build_agent(llm, build_tools(llm, settings, search_fn=FakeSearch()), settings, checkpointer=InMemorySaver())
    [fin] = [e for e in run_turn(agent, settings, "dame el script", uid()) if e["type"] == "tool_end"]
    assert fin["name"] == "check_python_syntax" and fin["output"].startswith("SyntaxError at line 4")
    node = shutil.which("node")
    if not node:
        pytest.skip("node no está instalado")
    html = (ROOT / "src" / "assistant" / "packs" / "ui" / "index.html").read_text(encoding="utf-8")
    src = "\n".join(re.search(rf"/\* {k}-START \*/(.*?)/\* {k}-END \*/", html, re.S).group(1)
                    for k in ("TOOL-LABELS", "TOOL-NAMES"))
    salidas = [fin["output"], _check("x = 1\n")]
    js = (f"{src}\nconsole.log(JSON.stringify([TOOL_DONE['check_python_syntax'], TOOL_LABELS['check_python_syntax']]"
          f".concat({json.dumps(salidas)}.map(toolOutputLabel))));")
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True,
                                    encoding="utf-8").stdout)
    assert out[0] == "🐍 Sintaxis revisada" and out[1] == "🐍 Revisando la sintaxis…"
    assert out[2].startswith("Error de sintaxis en la línea 4, columna") and out[3] == "Sintaxis correcta"


def test_funciona_en_bigtool(make_settings):
    from assistant.bigtool_agent import build_bigtool_agent, build_registry

    s = make_settings(use_bigtool=True)
    t = build_registry(None, s, InMemoryStore())["check_python_syntax"]
    agent = build_bigtool_agent(
        fake_llm(tool_call("retrieve_tools", {"query": f"{t.name}: {t.description}"}, "r1"),
                 tool_call("check_python_syntax", {"code": CODIGO_ROTO}, "s1"), "Corregido"),
        s, checkpointer=InMemorySaver(), memories_store=InMemoryStore(),
        embeddings=DeterministicFakeEmbedding(size=64), search_fn=FakeSearch())
    fines = {e["name"]: e["output"] for e in run_turn(agent, s, "revisa este código", uid()) if e["type"] == "tool_end"}
    assert "check_python_syntax" in fines["retrieve_tools"]
    assert fines["check_python_syntax"].startswith("SyntaxError at line 4")
