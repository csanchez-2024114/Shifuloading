from app.routes.dev import coder


def test_run_python_ok_falla_y_tiempo(monkeypatch):
    assert coder._run_python("print(2 + 2)") == (True, "4\n")
    assert coder._run_python("print('cómo')") == (True, "cómo\n")
    ok, out = coder._run_python("assert 1 == 2, 'mal'")
    assert not ok and "AssertionError" in out
    monkeypatch.setattr(coder, "RUN_SECONDS", 1)
    assert coder._run_python("while True: pass")[0] is False


def test_run_python_no_ve_las_llaves(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secreta")
    assert coder._run_python("import os; print(os.getenv('OPENAI_API_KEY'))") == (True, "None\n")
