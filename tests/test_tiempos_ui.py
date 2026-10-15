"""Tiempos en la interfaz: cálculo del desglose (computeBreakdown de static/index.html, con node) y evento phase."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import fake_llm, run_turn, tool_call, uid

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _breakdown(events, end_t):
    node = shutil.which("node")
    if not node:
        pytest.skip("node no está instalado")
    src = re.search(r"/\* BREAKDOWN-START \*/(.*?)/\* BREAKDOWN-END \*/", HTML.read_text(encoding="utf-8"), re.S).group(1)
    js = f"{src}\nconsole.log(JSON.stringify(computeBreakdown({json.dumps(events)}, {end_t})));"
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)


def test_desglose_reparte_el_total_por_fases():
    ev = [
        {"t": 400, "type": "effort"},                              # 0.4 s clasificando
        {"t": 900, "type": "summarized"},                          # 0.5 s resumiendo
        {"t": 2000, "type": "tool_start", "name": "web_search"},
        {"t": 2100, "type": "tool_start", "name": "calculator"},  # se solapan: cuenta una vez
        {"t": 2500, "type": "tool_end", "name": "calculator"},
        {"t": 6000, "type": "tool_end", "name": "web_search"},     # 4.0 s en herramientas
        {"t": 7000, "type": "token"},
        {"t": 8000, "type": "token"},
        {"t": 8100, "type": "phase", "name": "verifying"},
        {"t": 9600, "type": "verify"},                             # 1.5 s verificando
        {"t": 9700, "type": "done"},
    ]
    b = _breakdown(ev, 10000)
    assert b == {"total": 10000, "classify": 400, "tools": 4000, "verify": 1500, "summary": 500, "thinking": 3600}
    assert sum(b[k] for k in ("classify", "tools", "verify", "summary", "thinking")) == b["total"]


def test_desglose_sin_eventos_especiales_y_herramienta_cortada():
    assert _breakdown([{"t": 1200, "type": "token"}], 3000)["thinking"] == 3000
    corte = _breakdown([{"t": 1000, "type": "tool_start", "name": "web_search"}], 5000)  # nunca llegó tool_end
    assert corte["tools"] == 4000 and corte["thinking"] == 1000


def test_phase_verifying_llega_antes_que_verify(make_settings):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    from langgraph.checkpoint.memory import InMemorySaver

    s = make_settings(answer_verify=True)
    llm = fake_llm(tool_call("web_search", {"query": "x"}, "w1"), "Respuesta")
    agent = build_agent(llm, build_tools(llm, s, search_fn=lambda q, st: ("Respuesta", "duckduckgo")), s,
                        checkpointer=InMemorySaver(), checker=fake_llm("OK"))
    kinds = [e["type"] for e in run_turn(agent, s, "busca x", uid())]
    assert kinds.index("phase") < kinds.index("verify")
