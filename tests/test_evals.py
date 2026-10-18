"""Evals (P5): el dataset es válido, el modo falso pasa entero con 0 tokens, los evaluadores detectan una regresión
real, el comparador respeta el ruido por tipo de caso y el modo real no corre sin confirmar el costo."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals import compare, runner  # noqa: E402
from evals.harness import Meter, install  # noqa: E402

CATEGORIES = {"simple", "web_search", "investigacion_aprobada", "investigacion_rechazada", "memoria", "calculadora",
              "fecha", "mensaje_largo", "inyeccion", "url_inventada", "tope_turno"}


def test_dataset_valido():
    cases = runner.load_dataset()
    assert len(cases) >= 30  # empezó con 40 de los escenarios reales; crece con cada hallazgo y capacidad nueva
    assert {c["category"] for c in cases} == CATEGORIES
    for c in cases:
        assert c["steps"] and "expect" in c, c["id"]
        assert set(c["modes"]) <= {"fake", "real"} and c["modes"], c["id"]
        for st in c["steps"]:
            assert ("chat" in st) != ("resume" in st), c["id"]
        if "real" in c["modes"] and c["steps"][0].get("status", 200) == 200:
            assert c["est_tokens"] > 0 and c["margin"] >= c["est_tokens"], c["id"]
        if "fake" in c["modes"] and c["steps"][0].get("status", 200) == 200:
            assert c.get("fake", {}).get("model"), c["id"]
        if any(t in c["expect"].get("tools_used", []) for t in ("web_search", "deep_research")):
            assert c.get("noise") == "web", f"{c['id']}: con búsqueda el ruido es ±30 %"


def test_modo_falso_pasa_entero_sin_tokens_reales():
    out = runner.run_fake(runner.load_dataset(mode="fake"))
    fallas = {c["id"]: [k for k in c["checks"] if not k["ok"]] for c in out if not c["passed"]}
    assert fallas == {}


def test_los_evaluadores_detectan_la_regresion_si_se_apagan_las_defensas():
    [case] = [c for c in runner.load_dataset() if c["id"] == "iny-completa"]
    [res] = runner.run_fake([{**case, "settings": {}}])  # sin MEMORY_REQUIRE_QUOTE ni URL_FILTER_ALWAYS
    fallidos = {k["name"] for k in res["checks"] if not k["ok"]}
    assert not res["passed"] and {"memories", "not_contains"} <= fallidos


def test_un_413_no_abre_stream_ni_gasta():
    [case] = [c for c in runner.load_dataset() if c["id"] == "largo-413-ajustado"]
    [res] = runner.run_fake([case])
    assert res["passed"] and res["steps"][0]["status_code"] == 413 and res["tokens"] == 0


def _res(cases, mode="real"):
    return {"meta": {"mode": mode, "date": "d", "commit": "c"}, "cases": cases}


def _case(cid, tokens, ok=True, noise=None):
    return {"id": cid, "passed": ok, "noise": noise, "tokens": tokens,
            "checks": [{"name": "contains", "ok": ok, "detail": "x"}]}


def test_comparador_por_caso_con_el_ruido_de_cada_tipo():
    base = _res([_case("web", 14400, noise="web"), _case("calc", 5000), _case("mem", 5000), _case("simple", 2500)])
    new = _res([_case("web", 18900, noise="web"),  # +31 %: fuera del ruido de web
                _case("calc", 5200),               # +4 %: ruido
                _case("mem", 5400),                # +8 %: sin búsqueda es regresión
                _case("simple", 2500, ok=False)])  # el check pasó a fallar
    rep = compare.compare(base, new)
    ids = sorted(r["id"] for r in rep["regressions"])
    assert ids == ["mem", "simple", "web"]
    rep2 = compare.compare(base, _res([_case("web", 18600, noise="web")] + base["cases"][1:]))
    assert rep2["regressions"] == []  # +29 % con web_search: dentro del ruido


def test_comparador_marca_casos_sin_correr_y_nuevos():
    base = _res([_case("a", 100), _case("b", 100)])
    new = _res([{"id": "a", "passed": None, "skipped": "sin presupuesto", "tokens": 0}, _case("c", 100)])
    rep = compare.compare(base, new)
    assert [r["id"] for r in rep["regressions"]] == ["a"]
    assert {n["id"] for n in rep["notes"]} == {"b", "c"}


def test_modo_real_no_corre_sin_confirmar_el_costo(monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_evals

    monkeypatch.setattr(runner, "run_real", lambda *a, **k: pytest.fail("no debía correr"))
    assert run_evals.main(["--real"]) == 2
    assert run_evals.main(["--real", "--hard-cap", "100000", "--confirm-cap", "99999"]) == 2
    out = capsys.readouterr().out
    assert "Plan real" in out and "TURN_TOKEN_CAP" in out and "No se corrió" in out


def test_tope_duro_responde_429_antes_de_llamar_al_modelo():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from conftest import _settings

    app = FastAPI()

    @app.post("/chat")
    def chat():
        pytest.fail("no debía llegar al modelo")

    meter = Meter()
    meter.turns.append({"thread": "t", "tokens_total": 90000})
    install(app, meter, lambda: None, _settings(), hard_cap=100000)
    client = TestClient(app)
    assert client.post("/_eval/margin", params={"n": 20000}).json()["fits"] is False
    r = client.post("/chat", json={})
    assert r.status_code == 429 and "Tope duro" in r.json()["detail"]


def test_langsmith_es_opcional(monkeypatch):
    from evals import langsmith_upload

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    class Explota:
        def __getattr__(self, name):
            raise AssertionError("no debía usar langsmith")

    monkeypatch.setitem(sys.modules, "langsmith", Explota())
    assert "no se subió" in langsmith_upload.upload(_res([_case("a", 1)]))


def test_criterios_calidad_y_seguridad_y_repeticiones():
    cases = runner.load_dataset()
    assert {c["gate"] for c in cases} == {"quality", "security"}
    seguridad = {c["id"] for c in cases if c["gate"] == "security"}
    assert {"web-3", "url-del-usuario", "iny-completa", "iny-enlace-parentesis"} <= seguridad
    rep = runner.with_repeats([c for c in cases if c["id"] in ("web-3", "calc-4")], {"web-3": 3})
    assert [c["id"] for c in rep] == ["web-3", "web-3#2", "web-3#3", "calc-4"]
    assert [c["gate"] for c in runner.security_first(rep)][:3] == ["security"] * 3
    rates = runner.gate_rates([{"gate": "security", "passed": True}, {"gate": "security", "passed": None},
                               {"gate": "quality", "passed": True}])
    assert rates["security"] == {"cases": 2, "passed": 1, "rate": 0.5} and rates["quality"]["rate"] == 1.0
