"""Recursos del codificador: subidas pendientes (coder_uploads, 24 h), paso al proyecto (GridFS coder_assets para
binarios; texto para json/csv/txt), cuotas, aislamiento por usuario, poda y borrado en cascada con 0 documentos en cada
colección y en GridFS. Memoria y Mongo local temporal. Sin tokens."""
from datetime import timedelta

import pytest

from assistant.core.coder import projects as projects_mod
from assistant.core.coder.errors import CoderError
from assistant.core.coder.projects import Projects
from coder_repos import repo_factory  # noqa: F401
from conftest import _settings

A, B = "usuario-a", "usuario-b"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def _prep(name="logo.png", kind="png", mime="image/png", data=PNG, **extra) -> dict:
    return {"kind": kind, "mime": mime, "name": name, "data": data, "bytes": len(data), **extra}


def _p(repo, **limits) -> Projects:
    return Projects(repo, _settings(**limits))


def _code(fn) -> str:
    with pytest.raises(CoderError) as e:
        fn()
    return e.value.code


def _blobs(repo) -> int:
    if hasattr(repo, "db"):
        return repo.db["coder_assets.files"].count_documents({}) + repo.db["coder_assets.chunks"].count_documents({})
    return len(repo.blobs)


def test_subir_asignar_y_servir(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    up = p.stage_upload(A, _prep(width=40, height=30))
    assert up["upload_id"].startswith("up_") and up["name"] == "logo.png" and up["width"] == 40
    assert "user_id" not in up and "datos" not in up
    assert [u["upload_id"] for u in p.list_uploads(A)] == [up["upload_id"]] and p.list_uploads(B) == []
    pid = p.create(A, "juego")["project_id"]
    added = p.add_asset(A, pid, up["upload_id"])
    assert added == {"path": "assets/logo.png", "version": 1, "mime": "image/png", "bytes": len(PNG),
                     "width": 40, "height": 30}
    assert p.list_uploads(A) == []  # la subida pasó al proyecto
    assert p.version_file(pid, 1, "assets/logo.png") == {"path": "assets/logo.png", "content": PNG,
                                                         "mime": "image/png", "hash": p.list_files(A, pid)[0]["hash"]}
    assert _code(lambda: p.read_file(A, pid, "assets/logo.png")) == "binary_asset"
    assert p.usage(A)["bytes"] == len(PNG)


def test_datos_de_texto_quedan_como_archivo_legible(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    up = p.stage_upload(A, _prep("puntos.json", "json", "application/json; charset=utf-8", b'{"a": 1}'))
    assert p.add_asset(A, pid, up["upload_id"], "data/puntos.json")["path"] == "data/puntos.json"
    assert p.read_file(A, pid, "data/puntos.json")["content"] == '{"a": 1}'


def test_nombres_y_rutas(repo_factory):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    up = p.stage_upload(A, _prep("Mi Logo (final)!.png"))
    assert p.add_asset(A, pid, up["upload_id"])["path"] == "assets/mi-logo-final.png"
    for path, code in [("assets/x.jpg", "type_not_allowed"), ("../x.png", "invalid_path"),
                       ("logo.png", "type_not_allowed"), ("assets/x.svg", "type_not_allowed")]:
        up = p.stage_upload(A, _prep())
        assert _code(lambda: p.add_asset(A, pid, up["upload_id"], path)) == code, path
        assert any(u["upload_id"] == up["upload_id"] for u in p.list_uploads(A))  # si falla, la subida sigue


def test_usuario_y_proyecto_ajenos(repo_factory):
    p = _p(repo_factory())
    up_a = p.stage_upload(A, _prep())
    pid_a = p.create(A, "de a")["project_id"]
    pid_b = p.create(B, "de b")["project_id"]
    assert _code(lambda: p.add_asset(B, pid_b, up_a["upload_id"])) == "upload_not_found"  # subida ajena
    assert _code(lambda: p.add_asset(B, pid_a, up_a["upload_id"])) == "project_not_found"  # proyecto ajeno
    assert _code(lambda: p.add_asset(A, "p_000000000000", up_a["upload_id"])) == "project_not_found"
    assert _code(lambda: p.add_asset(A, pid_a, "up_0000000000000000")) == "upload_not_found"
    assert _code(lambda: p.add_asset(A, pid_a, {"$ne": None})) == "upload_not_found"
    assert p.delete_upload(B, up_a["upload_id"]) is False and p.list_uploads(A)


def test_subidas_caducan_a_las_24_horas(repo_factory, monkeypatch):
    p = _p(repo_factory())
    pid = p.create(A, "x")["project_id"]
    up = p.stage_upload(A, _prep())
    real = projects_mod._now
    monkeypatch.setattr(projects_mod, "_now", lambda: real() + timedelta(hours=24, minutes=1))
    assert p.list_uploads(A) == [] and p.usage(A)["bytes"] == 0
    assert _code(lambda: p.add_asset(A, pid, up["upload_id"])) == "upload_not_found"


def test_cuotas(repo_factory):
    p = _p(repo_factory(), coder_max_user_bytes=500, coder_max_files=1)
    p.stage_upload(A, _prep(data=b"x" * 300))
    assert _code(lambda: p.stage_upload(A, _prep(data=b"y" * 300))) == "quota_user_bytes"  # pendientes cuentan
    pid = p.create(A, "x")["project_id"]
    up = p.list_uploads(A)[0]
    p.add_asset(A, pid, up["upload_id"])  # pasar al proyecto no cuenta dos veces
    assert p.usage(A)["bytes"] == 300
    up2 = p.stage_upload(A, _prep("b.png", data=b"z" * 100))
    assert _code(lambda: p.add_asset(A, pid, up2["upload_id"])) == "quota_files"
    big = _p(repo_factory())
    for _ in range(projects_mod.max_pending_uploads):
        big.stage_upload(A, _prep(data=b"q"))
    assert _code(lambda: big.stage_upload(A, _prep(data=b"q"))) == "quota_uploads"


def test_la_poda_borra_los_recursos_huerfanos(repo_factory):
    repo = repo_factory()
    p = _p(repo, coder_max_versions=2)
    pid = p.create(A, "x")["project_id"]
    for i in range(5):
        up = p.stage_upload(A, _prep(data=PNG + bytes([i])))
        p.add_asset(A, pid, up["upload_id"], "assets/logo.png")
    filas = [r for r in repo.file_rows(pid) if r.get("blob_id")]
    assert len(filas) == 2  # solo las de las versiones que quedan
    if hasattr(repo, "db"):
        assert repo.db["coder_assets.files"].count_documents({}) == 2
    else:
        assert len(repo.blobs) == 2
    assert p.version_file(pid, p.get(A, pid)["version_actual"], "assets/logo.png")["content"] == PNG + bytes([4])


def test_borrar_proyecto_y_usuario_deja_cero_en_cada_coleccion_y_en_gridfs(repo_factory):
    repo = repo_factory()
    p = _p(repo)
    for user in (A, B):
        pid = p.create(user, "x")["project_id"]
        p.write_file(user, pid, "index.html", "<img src='assets/logo.png'>")
        p.add_asset(user, pid, p.stage_upload(user, _prep())["upload_id"])
        p.issue_preview(user, pid)
        p.stage_upload(user, _prep("pendiente.png"))
    p.delete_user(A)
    if hasattr(repo, "db"):
        for col in repo.db.list_collection_names():
            if col.startswith("coder_") and col != "coder_assets.chunks":
                campo = "metadata.user_id" if col == "coder_assets.files" else "user_id"
                assert repo.db[col].count_documents({campo: A}) == 0, col
        # B conserva lo suyo: 1 recurso en GridFS (1 archivo + sus trozos)
        assert repo.db["coder_assets.files"].count_documents({}) == 1
        assert repo.db["coder_assets.chunks"].count_documents({}) >= 1
    else:
        assert all(b["meta"]["user_id"] == B for b in repo.blobs.values()) and len(repo.blobs) == 1
        assert all(k[0] == B for k in repo.uploads)
    p.delete_user(B)
    assert _blobs(repo) == 0
    if hasattr(repo, "db"):
        for col in repo.db.list_collection_names():
            assert repo.db[col].count_documents({}) == 0, col
