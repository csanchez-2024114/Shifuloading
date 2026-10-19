"""Agente codificador: saneamiento de rutas y nombres (core/coder/paths.py). Sin tokens ni red."""
import pytest

from assistant.core.coder.errors import CoderError
from assistant.core.coder.paths import mime_for, safe_name, safe_path


@pytest.mark.parametrize("raw, esperado", [
    ("index.html", "index.html"),
    ("Index.HTML", "index.html"),
    ("js/game.js", "js/game.js"),
    ("css/estilos-v2.css", "css/estilos-v2.css"),
    ("assets/logo.png", "assets/logo.png"),
    ("  data/puntos.json ", "data/puntos.json"),
    ("ｉｎｄｅｘ.html", "index.html"),  # NFKC: ancho completo -> ASCII
])
def test_rutas_validas(raw, esperado):
    assert safe_path(raw) == esperado


@pytest.mark.parametrize("raw, motivo", [
    ("", "empty"),
    ("../x.html", "traversal"),
    ("a/../../x.html", "traversal"),
    ("a//b.html", "traversal"),
    ("./index.html", "traversal"),
    ("/etc/passwd.txt", "absolute"),
    ("~/x.txt", "absolute"),
    ("a\\b.html", "forbidden_character"),
    ("a\bb.html", "forbidden_character"),  # retroceso (control)
    ("C:x.html", "forbidden_character"),
    ("%2e%2e/x.html", "forbidden_character"),
    ("a\x00b.html", "forbidden_character"),
    ("a\u202eb.html", "forbidden_character"),  # control de dirección (categoría Cf)
    ("con.html", "reserved_name"),
    ("lpt1.txt", "reserved_name"),
    ("aux", "reserved_name"),
    (".env.txt", "forbidden_character"),
    ("js/.oculto.js", "forbidden_character"),
    ("a b.html", "forbidden_character"),
    ("x.html.", "forbidden_character"),
    ("a/b/c/d/e.html", "too_deep"),
    ("a" * 200 + ".html", "too_long"),
])
def test_rutas_rechazadas(raw, motivo):
    with pytest.raises(CoderError) as e:
        safe_path(raw)
    assert e.value.code == "invalid_path"
    assert e.value.values["reason"] == motivo


@pytest.mark.parametrize("raw, motivo", [
    ("server.py", "extension"),
    ("x.php", "extension"),
    ("x.svg", "extension"),
    ("x.exe", "extension"),
    ("sin_extension", "extension"),
    ("logo.png", "assets_only"),
    ("img/foto.jpg", "assets_only"),
])
def test_tipos_no_permitidos(raw, motivo):
    with pytest.raises(CoderError) as e:
        safe_path(raw)
    assert e.value.code == "type_not_allowed"
    assert e.value.values["reason"] == motivo


def test_mime_por_extension():
    assert mime_for("index.html").startswith("text/html")
    assert mime_for("js/app.js").startswith("text/javascript")
    assert mime_for("assets/a.webp") == "image/webp"


@pytest.mark.parametrize("raw, esperado", [
    ("Mi juego", "Mi juego"),
    ("  Mi   landing  ", "Mi landing"),
    ("<script>alert(1)</script>", "scriptalert(1)/script"),
    ("a\nb\tc", "abc"),
    ("x" * 100, "x" * 60),
])
def test_nombres(raw, esperado):
    assert safe_name(raw) == esperado


@pytest.mark.parametrize("raw", ["", "   ", "<>", "\x00"])
def test_nombre_vacio(raw):
    with pytest.raises(CoderError) as e:
        safe_name(raw)
    assert e.value.code == "invalid_name"
