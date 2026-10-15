"""Todo lo que lee el modelo va en inglés (prompts, descripciones y parámetros de herramientas, mensajes que las
herramientas devuelven). La interfaz no muestra esos mensajes en inglés: los traduce. Sin tokens ni Mongo."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from langgraph.store.memory import InMemoryStore

from conftest import FakeSearch, fake_llm

ROOT = Path(__file__).resolve().parents[1]
# palabras muy comunes del español que no existen en inglés; \b evita los nombres de herramientas (guardar_recuerdo)
SPANISH = re.compile(r"\b(el|la|los|las|que|para|con|una|del|por|pero|como|est[aá]|recuerdos?|usuario|herramientas?|"
                     r"b[uú]squeda|respuesta|mensaje|hola|gracias)\b|[áéíóúñ¿¡]", re.I)


def _spanish(text: str) -> list[str]:
    return sorted({m.group(0) for m in SPANISH.finditer(text)})


def _model_texts(make_settings) -> dict[str, str]:
    from assistant import agent, memory, tools
    from assistant.bigtool_agent import BIGTOOL_PROMPT, build_registry

    s = make_settings(enable_hitl_demo=True, bigtool_demo_tools=True)
    texts = {
        "prompts/system.md": (ROOT / "prompts" / "system.md").read_text(encoding="utf-8-sig"),
        "SUMMARY_PROMPT": agent.SUMMARY_PROMPT, "VERIFY_ANSWER_PROMPT": agent.VERIFY_ANSWER_PROMPT,
        "VERIFY_MEMORY_PROMPT": memory.VERIFY_MEMORY_PROMPT, "CLASSIFIER_PROMPT": agent.CLASSIFIER_PROMPT,
        "LAST_STEP_NOTE": agent.LAST_STEP_NOTE, "REPEAT_LIMIT_MSG": agent.REPEAT_LIMIT_MSG,
        "BIGTOOL_PROMPT": BIGTOOL_PROMPT, "INVESTIGADOR_PROMPT": tools._INVESTIGADOR_PROMPT,
        "SEARCH_LIMIT_MSG": tools.SEARCH_LIMIT_MSG, "WEB_BUDGET_MSG": tools.WEB_BUDGET_MSG,
        "memory messages": " | ".join([memory.NO_RELEVANT_MSG, memory.NO_MEMORIES_MSG, memory.SAVED_MSG,
                                       memory.UPDATED_MSG, memory.NOT_FOUND_MSG, memory.KEYWORD_MARK,
                                       memory.remember(InMemoryStore(), "u", "x", "", [], verifier=lambda c, t: (False, "")),
                                       memory.revise(InMemoryStore(), "u", "k", "x", "", [])]),
        "calculator errors": " | ".join(tools.calculadora.invoke({"expression": e}) for e in ("1/0", "2+", "__import__('os')")),
        "current_datetime error": tools.fecha_hora.invoke({"time_zone": "Nowhere/Nada"}),
        "send_simulated_email": tools.enviar_email_simulado.invoke({"recipient": "a@b.c", "subject": "x", "body": "y"}),
    }
    llm = fake_llm("x")
    todas = tools.build_tools(llm, s, search_fn=FakeSearch()) + list(build_registry(llm, s, InMemoryStore()).values())
    for t in todas:
        texts[f"tool {t.name}"] = t.description + " " + json.dumps(t.args, ensure_ascii=False)
    return texts


def test_lo_que_lee_el_modelo_esta_en_ingles(make_settings):
    malos = {k: _spanish(v) for k, v in _model_texts(make_settings).items()}
    assert not {k: v for k, v in malos.items() if v}, "texto en español en lo que lee el modelo"


def test_el_detector_si_detecta_espanol():
    assert _spanish("Recuerdo guardado.") and _spanish("No hay recuerdos relevantes para esto")
    assert not _spanish("Memory saved. Use save_memory and search_memories.")


def test_system_md_pide_responder_en_el_idioma_del_usuario():
    text = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8-sig")
    assert ("Always reply in the same language the user writes in. Tool results are in English; never copy them "
            "verbatim to the user: explain them in the user's language.") in text


def test_la_interfaz_muestra_los_mensajes_de_herramientas_en_espanol():
    from assistant import agent, memory, tools

    node = shutil.which("node")
    if not node:
        pytest.skip("node no está instalado")
    src = re.search(r"/\* TOOL-LABELS-START \*/(.*?)/\* TOOL-LABELS-END \*/",
                    (ROOT / "static" / "index.html").read_text(encoding="utf-8"), re.S).group(1)
    mensajes = [memory.SAVED_MSG, memory.UPDATED_MSG, memory.NO_RELEVANT_MSG, memory.NO_MEMORIES_MSG,
                memory.NOT_FOUND_MSG, memory.remember(InMemoryStore(), "u", "x", "", [], verifier=lambda c, t: (False, "")),
                tools.WEB_BUDGET_MSG, agent.REPEAT_LIMIT_MSG.format(name="calculator", limit=8), "No results.",
                "Tool error (ValueError): boom. Try another approach.", "Error: division by zero."]
    js = f"{src}\nconsole.log(JSON.stringify({json.dumps(mensajes)}.map(toolOutputLabel)));"
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, encoding="utf-8").stdout)
    for original, mostrado in zip(mensajes, out):
        assert mostrado != original, original
        assert not re.search(r"\b(memory|memories|saved|updated|not run|tool|results?|budget|try)\b", mostrado, re.I), mostrado
    assert out[0] == "Recuerdo guardado"
