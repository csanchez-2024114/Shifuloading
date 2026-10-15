"""ANSWER_VERIFY: reglas de citas aplicadas en código, y que los errores de conexión no filtran la contraseña."""
import logging

import pytest

from assistant.citations import enforce, normalize_url
from conftest import fake_llm, run_turn, tool_call, uid

EVIDENCIA = ("Según el INSEE, Francia tiene 69,1 millones de habitantes. "
             "([insee.fr](https://www.insee.fr/fr/statistiques/2012692?utm_source=openai))\n"
             "Biografía: https://regierung.li/regierungsmitglied/16690/lebenslauf/brigitte-haas?utm_source=openai#top")


def test_url_con_y_sin_utm_es_la_misma():
    a = normalize_url("https://www.insee.fr/fr/statistiques/2012692?utm_source=openai")
    assert a == normalize_url("https://insee.fr/fr/statistiques/2012692")
    assert a == normalize_url("HTTPS://WWW.INSEE.FR/fr/statistiques/2012692/#tabla")
    assert a == normalize_url("https://insee.fr/fr/statistiques/2012692?utm_medium=x&fbclid=abc")
    assert a != normalize_url("https://insee.fr/fr/statistiques/999")


def test_respuesta_correcta_con_citas_validas_no_cambia():
    original = "Francia tiene 69,1 millones de habitantes ([INSEE](https://insee.fr/fr/statistiques/2012692))."
    assert enforce(original, None, EVIDENCIA) == (original, "ok", [])
    # el verificador "corrige" devolviendo lo mismo: no se marca como corrección
    assert enforce(original, original + " ", EVIDENCIA)[1] == "ok"


def test_correccion_que_pierde_cita_respaldada_la_restaura():
    original = ("Francia tiene 69,1 millones ([INSEE](https://insee.fr/fr/statistiques/2012692)). "
                "La ministra es Brigitte Haas ([biografía](https://regierung.li/regierungsmitglied/16690/lebenslauf/brigitte-haas)).")
    correccion = "Francia tiene 69,1 millones de habitantes. La ministra es Brigitte Haas."
    texto, status, notas = enforce(original, correccion, EVIDENCIA)
    assert status == "corrected" and "se restauraron fuentes" in notas[-1]
    assert "(https://insee.fr/fr/statistiques/2012692)" in texto
    assert "brigitte-haas)" in texto


def test_url_inventada_se_elimina_aunque_el_verificador_diga_ok():
    original = "Francia tiene 69,1 millones ([fuente](https://ejemplo-inventado.com/francia))."
    texto, status, notas = enforce(original, None, EVIDENCIA)
    assert "ejemplo-inventado.com" not in texto and "fuente" in texto
    assert status == "corrected" and "sin respaldo" in notas[0]


def test_correccion_con_cifras_nuevas_se_descarta():
    original = "Francia tiene muchos habitantes ([INSEE](https://insee.fr/fr/statistiques/2012692))."
    correccion = "Francia tiene 71,3 millones de habitantes desde 2031."
    texto, status, notas = enforce(original, correccion, EVIDENCIA)
    assert texto == original and status == "kept_original" and "no se pudo corregir" in notas[0]


def test_answer_verify_de_punta_a_punta_restaura_cita(make_settings):
    from assistant.agent import build_agent, get_history
    from assistant.tools import build_tools

    def search(query, settings):
        return EVIDENCIA, "openai_web_search"

    s = make_settings(answer_verify=True)
    llm = fake_llm(tool_call("buscar_web", {"consulta": "población de Francia"}, "w1"),
                   "Francia tiene 70 millones ([INSEE](https://insee.fr/fr/statistiques/2012692)).")
    checker = fake_llm("Francia tiene 69,1 millones de habitantes.")  # corrige la cifra pero pierde la cita
    agent = build_agent(llm, build_tools(llm, s, search_fn=search), s, checker=checker,
                        checkpointer=__import__("langgraph.checkpoint.memory", fromlist=["InMemorySaver"]).InMemorySaver())
    thread = uid()
    ev = run_turn(agent, s, "¿Cuántos habitantes tiene Francia?", thread)
    [v] = [e for e in ev if e["type"] == "verify"]
    assert v["status"] == "corrected" and "69,1 millones" in v["text"]
    assert "(https://insee.fr/fr/statistiques/2012692)" in v["text"]  # la fuente sigue ahí
    h = get_history(agent, thread, s)[-1]
    assert h["original"].startswith("Francia tiene 70 millones") and h["verify"]["status"] == "corrected"


# --------------------------------------------------------------------------- B5: errores de conexión

CLAVE = "ClaveSecreta987"


def test_error_de_conexion_no_muestra_la_contrasena(caplog):
    from assistant.config import ConfigError
    from assistant.memory import ping_mongo

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ConfigError) as exc:
        ping_mongo(f"mongodb://usuariofalso:{CLAVE}@127.0.0.1:1/", timeout_ms=200)
    msg = str(exc.value)
    assert CLAVE not in msg and "usuariofalso" not in msg and "***@127.0.0.1:1" in msg
    assert CLAVE not in caplog.text


def test_srv_inexistente_no_muestra_la_contrasena():
    from assistant.config import ConfigError
    from assistant.memory import ping_mongo

    with pytest.raises(ConfigError) as exc:
        ping_mongo(f"mongodb+srv://usuariofalso:{CLAVE}@cluster-que-no-existe.invalid/", timeout_ms=200)
    assert CLAVE not in str(exc.value) and CLAVE not in repr(exc.value.__cause__)


@pytest.mark.parametrize("uri", [
    f"mongodb+srv://usuariofalso:{CLAVE}@cluster-que-no-existe.invalid/",  # DNS: falla al construir el cliente
    f"mongodb://usuariofalso:{CLAVE}@",                                     # URI mal formada
])
def test_errores_al_construir_el_cliente_dan_mensaje_claro(uri, caplog):
    from assistant.config import ConfigError
    from assistant.memory import ping_mongo

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ConfigError) as exc:
        ping_mongo(uri, timeout_ms=200)
    msg = str(exc.value)
    assert msg.startswith("No pude conectar a MongoDB en ") and "Verifica" in msg
    assert CLAVE not in msg and "usuariofalso" not in msg and CLAVE not in caplog.text
