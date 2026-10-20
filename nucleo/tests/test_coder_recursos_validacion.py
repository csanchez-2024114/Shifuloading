"""Recursos del codificador: validación por contenido y preparación (core/coder/assets.py + asset_worker). S18: un
PNG con extensión .jpg, un SVG y un políglota se rechazan. Las imágenes salen reencodeadas sin metadatos y con tope de
lado y de píxeles. Sin tokens ni red."""
import io

import pytest

from assistant.core.coder.assets import prepare_asset
from assistant.core.coder.asset_worker import max_side, reencode
from assistant.core.coder.errors import CoderError

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

MAX = 2_000_000


def _img(fmt: str, size=(40, 30), mode="RGB", **save) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (200, 30, 30) if mode == "RGB" else 1).save(out, format=fmt, **save)
    return out.getvalue()


def _exif() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "Fabricante secreto"  # Make
    exif[0x8825] = {2: (19.0, 26.0, 0.0)}  # GPSInfo: una ubicación
    return exif.tobytes()


def _code(fn) -> str:
    with pytest.raises(CoderError) as e:
        fn()
    return e.value.code


@pytest.mark.parametrize("fmt, name, kind", [("PNG", "logo.png", "png"), ("JPEG", "foto.JPG", "jpeg"),
                                             ("JPEG", "foto.jpeg", "jpeg"), ("GIF", "a.gif", "gif"),
                                             ("WEBP", "a.webp", "webp")])
def test_imagenes_validas_salen_reencodeadas(fmt, name, kind):
    out = prepare_asset(_img(fmt), name, MAX)
    assert out["kind"] == kind and out["width"] == 40 and out["height"] == 30
    assert out["name"].endswith({"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}[kind])
    assert Image.open(io.BytesIO(out["data"])).format == fmt


def test_sin_exif_ni_metadatos():
    from PIL import PngImagePlugin

    jpg = _img("JPEG", exif=_exif())
    assert b"Fabricante secreto" in jpg
    out = prepare_asset(jpg, "foto.jpg", MAX)["data"]
    assert b"Fabricante secreto" not in out and "exif" not in Image.open(io.BytesIO(out)).info
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "Ana Secreta")
    png = _img("PNG", pnginfo=meta)
    assert b"Ana Secreta" in png
    assert b"Ana Secreta" not in prepare_asset(png, "a.png", MAX)["data"]


def test_tope_de_lado_y_de_pixeles():
    out = prepare_asset(_img("PNG", size=(4000, 1000)), "ancho.png", MAX)
    assert (out["width"], out["height"]) == (max_side, max_side // 4)
    bomba = io.BytesIO()
    Image.new("1", (10000, 9000)).save(bomba, format="PNG")  # 90 M de píxeles, pocos KB comprimida
    assert len(bomba.getvalue()) < MAX
    assert _code(lambda: prepare_asset(bomba.getvalue(), "bomba.png", MAX)) == "asset_too_many_pixels"


# ---------------------------------------------------------------- S18 y otros rechazos

@pytest.mark.parametrize("data, name, code", [
    (_img("PNG"), "foto.jpg", "asset_mismatch"),  # S18: PNG con extensión .jpg
    (_img("JPEG"), "logo.png", "asset_mismatch"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "dibujo.svg",
     "asset_type_not_allowed"),  # S18: SVG
    (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "dibujo.png", "asset_mismatch"),  # SVG disfrazado
    (_img("PNG") + b"<script>fetch('https://evil.example')</script>", "a.png", "asset_polyglot"),  # S18: políglota
    (_img("GIF") + b"<html><body onload=alert(1)>", "a.gif", "asset_polyglot"),
    (b"GIF89a/*" + b"\x00" * 20 + b"*/=alert(document.domain);", "a.gif", "asset_mismatch"),  # GIF/JS sin marcas
    (b"OggS" + b"\x00" * 30 + b"<script>alert(1)</script>", "a.ogg", "asset_polyglot"),
    (b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"javascript:alert(1)", "a.mp3", "asset_polyglot"),
    (b"MZ\x90\x00", "programa.exe", "asset_type_not_allowed"),
    (b"<?php echo 1;", "x.php", "asset_type_not_allowed"),
    (b"<h1>x</h1>", "pagina.html", "asset_type_not_allowed"),
    (b"x", "sin_extension", "asset_type_not_allowed"),
    (b"{no es json", "datos.json", "asset_mismatch"),
    (b"a,b\x00c", "datos.csv", "asset_mismatch"),
    (_img("PNG"), "notas.txt", "asset_mismatch"),  # binario con extensión de texto
    (b"\xff\xfe\x00\x00", "notas.txt", "asset_mismatch"),
    (b"abc", "musica.mp3", "asset_mismatch"),
    (b"", "a.png", "asset_empty"),
])
def test_rechazos(data, name, code):
    assert _code(lambda: prepare_asset(data, name, MAX)) == code


def test_demasiado_grande():
    assert _code(lambda: prepare_asset(b"x" * 101, "a.txt", 100)) == "asset_too_large"


# ---------------------------------------------------------------- audio y datos

def test_mp3_sin_etiquetas_id3_y_ogg():
    tag = b"TIT2" + (13).to_bytes(4, "big") + b"\x00\x00" + b"\x00Mi cancion!!"
    v2 = b"ID3\x03\x00\x00" + bytes([0, 0, 0, len(tag)]) + tag
    frames = b"\xff\xfb\x90\x00" + b"\x11" * 400
    v1 = b"TAG" + b"Artista secreto".ljust(125, b"\x00")
    out = prepare_asset(v2 + frames + v1, "cancion.mp3", MAX)
    assert out["data"] == frames and out["mime"] == "audio/mpeg"
    ogg = b"OggS\x00\x02" + b"\x01" * 200
    assert prepare_asset(ogg, "efecto.ogg", MAX)["data"] == ogg


def test_datos_de_texto():
    out = prepare_asset('﻿{"puntos": [1, 2]}'.encode("utf-8"), "datos.json", MAX)
    assert out["data"] == b'{"puntos": [1, 2]}' and out["mime"] == "application/json; charset=utf-8"
    assert prepare_asset("nombre,puntos\nAna,3".encode(), "tabla.CSV", MAX)["name"] == "tabla.csv"
    texto = prepare_asset("<script>esto es solo texto</script>".encode(), "notas.txt", MAX)
    assert texto["mime"] == "text/plain; charset=utf-8"  # se sirve como texto (con nosniff): no se ejecuta


def test_nombre_saneado():
    out = prepare_asset(_img("PNG"), "../../secreto/<mi> logo.PNG", MAX)
    assert out["name"] == "mi logo.png"


def test_el_subproceso_se_corta_por_tiempo():
    assert _code(lambda: reencode(_img("PNG"), "png", timeout=0.001)) == "asset_timeout"


def test_gif_animado_conserva_sus_cuadros():
    frames = [Image.new("RGB", (20, 20), (i * 40, 0, 0)) for i in range(3)]
    data = io.BytesIO()
    frames[0].save(data, format="GIF", save_all=True, append_images=frames[1:], duration=[50, 60, 70], loop=0,
                   comment=b"comentario secreto")
    assert b"comentario secreto" in data.getvalue()
    out = prepare_asset(data.getvalue(), "anim.gif", MAX)["data"]
    assert Image.open(io.BytesIO(out)).n_frames == 3 and b"comentario secreto" not in out
