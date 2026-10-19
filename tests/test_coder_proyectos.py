"""Agente codificador: proyectos, versionado por edición, parches, restaurar, cuotas, aislamiento por usuario y borrado
en cascada (core/coder/projects.py). Sin tokens. Corre sobre el almacén en memoria y, si responde, sobre Mongo local
en una base temporal assistant_ux_tmp_coder_* que se borra al terminar."""
import pytest

from assistant.core.coder.errors import CoderError
from assistant.core.coder.projects import Projects
from coder_repos import repo_factory  # noqa: F401  (fixture parametrizada: memoria y Mongo)
from conftest import _settings

A, B = "usuario-a", "usuario-b"


def _p(repo, **limits) -> Projects:
    return Projects(repo, _settings(**limits))


def _code(exc_info) -> str:
    return exc_info.value.code


def _counts(repo, pid) -> tuple[int, int]:
    return len(repo.file_rows(pid)), len(repo.list_versions(pid))


# ---------------------------------------------------------------------------------------------- crear y listar

def test_crear_y_listar(repo_factory):
    p = _p(repo_factory())
    a = p.create(A, "  Mi   landing ", "landing")
    assert a["name"] == "Mi landing" and a["kind"] == "landing" and a["version"] == 0
    assert a["project_id"].startswith("p_") and len(a["project_id"]) == 14
    assert "user_id" not in a
    assert [x["project_id"] for x in p.list_projects(A)] == [a["project_id"]]
    assert p.list_projects(B) == []


def test_tipo_invalido_y_cuota_de_proyectos(repo_factory):
    p = _p(repo_factory(), coder_max_projects_per_user=2)
    with pytest.raises(CoderError) as e:
        p.create(A, "x", "backend")
    assert _code(e) == "invalid_kind"
    p.create(A, "uno")
    p.create(A, "dos")
    with pytest.raises(CoderError) as e:
        p.create(A, "tres")
    assert _code(e) == "quota_projects"
    p.create(B, "de otro")  # la cuota es por usuario
    assert len(p.list_projects(A)) == 2


# ---------------------------------------------------------------------------------------------- versionado

def test_escribir_editar_y_manifiesto_que_reutiliza_filas(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "juego", "game")["project_id"]
    assert p.write_file(A, pid, "index.html", "<h1>Hola</h1>\n<p>uno</p>\n") == 1
    assert p.write_file(A, pid, "css/style.css", "h1{color:red}") == 2
    v = p.edit_file(A, pid, "index.html", [{"old": "uno", "new": "dos"}], expected_version=2)
    assert v == 3
    assert p.read_file(A, pid, "index.html")["content"] == "<h1>Hola</h1>\n<p>dos</p>\n"
    assert p.read_file(A, pid, "index.html", version=1)["content"].endswith("<p>uno</p>\n")
    files = {f["path"]: f for f in p.list_files(A, pid)}
    assert files["css/style.css"]["since_version"] == 2  # la v3 reutiliza la fila del css
    assert files["index.html"]["since_version"] == 3
    assert _counts(repo, pid) == (3, 4)  # filas: index v1, css v2, index v3; versiones 0..3
    assert [x["origin"] for x in p.list_versions(A, pid)] == ["edit", "write", "write", "create"]


@pytest.mark.parametrize("edits, esperado", [
    ([{"old": "no existe", "new": "x"}], "edit_not_found"),
    ([{"old": "a", "new": "x"}], "edit_ambiguous"),
    ([{"old": "", "new": "x"}], "edit_invalid"),
    ([{"old": "uno"}], "edit_invalid"),
    ([], "edit_invalid"),
    ("old=uno", "edit_invalid"),
    ([{"old": "uno", "new": "dos"}, {"old": "uno", "new": "tres"}], "edit_not_found"),  # en orden, sobre lo editado
])
def test_parches_que_fallan_no_cambian_nada(repo_factory, edits, esperado):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "a a uno")
    with pytest.raises(CoderError) as e:
        p.edit_file(A, pid, "index.html", edits, expected_version=1)
    assert _code(e) == esperado
    assert p.read_file(A, pid, "index.html")["content"] == "a a uno"
    assert _counts(repo, pid) == (1, 2)


def test_editar_exige_la_version_actual(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "uno")
    p.write_file(A, pid, "app.js", "let a=1")
    with pytest.raises(CoderError) as e:
        p.edit_file(A, pid, "index.html", [{"old": "uno", "new": "dos"}], expected_version=1)
    assert _code(e) == "stale_version" and e.value.values["current"] == 2


def test_escribir_lo_mismo_no_crea_version(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "igual")
    with pytest.raises(CoderError) as e:
        p.write_file(A, pid, "index.html", "igual")
    assert _code(e) == "unchanged"
    assert p.get(A, pid)["version_actual"] == 1


def test_borrar_archivo_y_restaurar(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "uno")
    p.write_file(A, pid, "app.js", "js")
    assert p.delete_file(A, pid, "app.js") == 3
    assert [f["path"] for f in p.list_files(A, pid)] == ["index.html"]
    with pytest.raises(CoderError) as e:
        p.read_file(A, pid, "app.js")
    assert _code(e) == "file_not_found"
    assert p.restore(A, pid, 2) == 4
    assert p.read_file(A, pid, "app.js")["content"] == "js"
    assert p.list_versions(A, pid)[0]["origin"] == "restore"
    assert p.list_versions(A, pid)[0]["from_version"] == 2
    with pytest.raises(CoderError) as e:
        p.restore(A, pid, 4 - 2)  # igual a la actual
    assert _code(e) == "unchanged"
    with pytest.raises(CoderError) as e:
        p.restore(A, pid, 99)
    assert _code(e) == "version_not_found"


def test_diff_acotado(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    p.write_file(A, pid, "index.html", "uno\ndos\n")
    p.edit_file(A, pid, "index.html", [{"old": "dos", "new": "DOS"}], expected_version=1)
    d = p.diff(A, pid, 1, 2)
    assert "-dos" in d and "+DOS" in d and "v1/index.html" in d
    p.write_file(A, pid, "big.txt", "\n".join(str(i) for i in range(500)))
    d = p.diff(A, pid, 2, 3, max_lines=50)
    assert d.count("\n") == 50 and "diff truncated" in d


# ---------------------------------------------------------------------------------------------- seguridad

@pytest.mark.parametrize("ruta, codigo", [
    ("../x.html", "invalid_path"),
    ("/abs.html", "invalid_path"),
    ("assets/logo.png", "type_not_allowed"),  # un recurso binario no se escribe como texto
    ("server.py", "type_not_allowed"),
])
def test_rutas_peligrosas_no_se_escriben(repo_factory, ruta, codigo):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    with pytest.raises(CoderError) as e:
        p.write_file(A, pid, ruta, "x")
    assert _code(e) == codigo
    assert _counts(repo, pid) == (0, 1)


def test_contenido_con_nul_se_rechaza(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    with pytest.raises(CoderError) as e:
        p.write_file(A, pid, "a.txt", "a\x00b")
    assert _code(e) == "invalid_content"


def test_otro_usuario_recibe_lo_mismo_que_un_proyecto_inexistente(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "privado")["project_id"]
    p.write_file(A, pid, "index.html", "secreto")
    intentos = [
        lambda: p.get(B, pid),
        lambda: p.read_file(B, pid, "index.html"),
        lambda: p.list_files(B, pid),
        lambda: p.list_versions(B, pid),
        lambda: p.diff(B, pid, 0, 1),
        lambda: p.write_file(B, pid, "index.html", "pisado"),
        lambda: p.edit_file(B, pid, "index.html", [{"old": "secreto", "new": "x"}], 1),
        lambda: p.delete_file(B, pid, "index.html"),
        lambda: p.restore(B, pid, 0),
        lambda: p.delete_project(B, pid),
        lambda: p.get(A, "p_000000000000"),  # inexistente
        lambda: p.get(A, {"$ne": None}),  # inyección de operador
        lambda: p.get(A, "p_../../x"),
    ]
    for intento in intentos:
        with pytest.raises(CoderError) as e:
            intento()
        assert _code(e) == "project_not_found"
    assert p.read_file(A, pid, "index.html")["content"] == "secreto"


# ---------------------------------------------------------------------------------------------- cuotas

def test_cuotas_de_archivo_archivos_y_bytes_del_usuario(repo_factory):
    repo = repo_factory()
    p = _p(repo, coder_max_file_bytes=100, coder_max_files=2, coder_max_user_bytes=250)
    pid = p.create(A, "x")["project_id"]
    with pytest.raises(CoderError) as e:
        p.write_file(A, pid, "a.txt", "x" * 101)
    assert _code(e) == "quota_file_bytes"
    p.write_file(A, pid, "a.txt", "x" * 100)
    p.write_file(A, pid, "b.txt", "y" * 100)
    with pytest.raises(CoderError) as e:
        p.write_file(A, pid, "c.txt", "z")
    assert _code(e) == "quota_files"
    with pytest.raises(CoderError) as e:  # 200 usados + 60 > 250 (las versiones viejas también cuentan)
        p.write_file(A, pid, "a.txt", "w" * 60)
    assert _code(e) == "quota_user_bytes"
    assert _counts(repo, pid) == (2, 3)
    otro = p.create(A, "otro")["project_id"]
    with pytest.raises(CoderError) as e:  # la cuota de bytes es por usuario, no por proyecto
        p.write_file(A, otro, "a.txt", "q" * 60)
    assert _code(e) == "quota_user_bytes"
    assert p.usage(A) == {"projects": 2, "bytes": 200}


def test_poda_de_versiones_respeta_la_actual_y_las_fijadas(repo_factory):
    repo = repo_factory()
    p = _p(repo, coder_max_versions=3)
    pid = p.create(A, "x")["project_id"]
    for i in range(1, 7):
        p.write_file(A, pid, "index.html", f"v{i}")
        if i == 2:
            repo.update_project(A, pid, {"pinned_versions": [2]})  # p. ej. la versión publicada
    versiones = [v["version"] for v in p.list_versions(A, pid, limit=100)]
    assert versiones == [6, 5, 4, 2]
    assert p.read_file(A, pid, "index.html", version=2)["content"] == "v2"
    filas = sorted(r["version"] for r in repo.file_rows(pid))
    assert filas == [2, 4, 5, 6]  # las filas huérfanas se borran
    assert p.get(A, pid)["bytes"] == 8


def test_carrera_entre_dos_escrituras_da_conflicto_sin_dejar_restos(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    pid = p.create(A, "x")["project_id"]
    vieja = p.get(A, pid)  # otra llamada leyó el proyecto antes...
    p.write_file(A, pid, "index.html", "gana")  # ...y esta escribió primero
    with pytest.raises(CoderError) as e:
        p._save(A, vieja, "index.html", "pierde", "write")
    assert _code(e) == "conflict"
    assert p.read_file(A, pid, "index.html")["content"] == "gana"
    assert _counts(repo, pid) == (1, 2)


# ---------------------------------------------------------------------------------------------- borrado

def test_borrar_proyecto_y_usuario_en_cascada(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    uno = p.create(A, "uno")["project_id"]
    dos = p.create(A, "dos")["project_id"]
    de_b = p.create(B, "de b")["project_id"]
    for pid, user in ((uno, A), (dos, A), (de_b, B)):
        p.write_file(user, pid, "index.html", "x")
        p.write_file(user, pid, "app.js", "y")
    p.delete_project(A, uno)
    assert _counts(repo, uno) == (0, 0)
    assert repo.get_project(A, uno) is None
    assert p.delete_user(A) == 1
    assert _counts(repo, dos) == (0, 0) and p.list_projects(A) == []
    assert _counts(repo, de_b) == (2, 3)  # lo de otro usuario no se toca
