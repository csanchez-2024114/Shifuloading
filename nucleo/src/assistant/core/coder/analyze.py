"""Analizador estático del código de un proyecto (segunda capa: la defensa real es la CSP del sandbox). Nada se
ejecuta: se recorre el HTML con html.parser y el JS/CSS con expresiones regulares. Severidades:
- block: no se puede publicar (recursos o peticiones a otros sitios, iframes anidados, redirecciones, navegación a
  una URL externa);
- warn: publicar exige aviso explícito (eval, contraseñas, datos de pago, posible suplantación, navegación dinámica);
- info: solo informa (enlaces externos, archivos que faltan).
Los detalles van en inglés: los lee el modelo."""
import re
from html.parser import HTMLParser

from assistant.core.coder.paths import extension

_ext = r"(?:https?:|wss?:)?//"
_ext_url = re.compile(r"^\s*" + _ext, re.I)
_q = r"['\"`]"
# (patrón, código, severidad, detalle) sobre el texto de JS
_js_rules = [
    (re.compile(r"\bfetch\s*\(\s*" + _q + r"\s*" + _ext, re.I), "external_request", "block",
     "fetch() to another site"),
    (re.compile(r"\.open\s*\(\s*" + _q + r"[a-z]+" + _q + r"\s*,\s*" + _q + r"\s*" + _ext, re.I), "external_request",
     "block", "XMLHttpRequest to another site"),
    (re.compile(r"\bnew\s+(?:WebSocket|EventSource)\s*\("), "external_request", "block",
     "WebSocket/EventSource (there is no server to talk to)"),
    (re.compile(r"\bsendBeacon\s*\("), "external_request", "block", "navigator.sendBeacon()"),
    (re.compile(r"\bimportScripts\s*\("), "external_script", "block", "importScripts()"),
    (re.compile(r"\bimport\s*\(\s*" + _q + r"\s*" + _ext, re.I), "external_script", "block",
     "dynamic import from another site"),
    (re.compile(r"\bfrom\s+['\"]\s*" + _ext, re.I), "external_script", "block", "module import from another site"),
    (re.compile(r"\blocation(?:\.href)?\s*=(?!=)\s*" + _q + r"\s*" + _ext, re.I), "external_navigation", "block",
     "navigates the page to another site"),
    (re.compile(r"\blocation\s*\.\s*(?:assign|replace)\s*\(\s*" + _q + r"\s*" + _ext, re.I), "external_navigation",
     "block", "navigates the page to another site"),
    (re.compile(r"\bwindow\s*\.\s*open\s*\(\s*" + _q + r"\s*" + _ext, re.I), "external_navigation", "block",
     "opens another site"),
    # un literal ya está cubierto: local (bien) o externo (external_navigation, arriba)
    (re.compile(r"\blocation(?:\.href)?\s*=(?!=)(?!\s*" + _q + r")", re.I),
     "dynamic_navigation", "warn", "assigns a computed URL to location"),
    (re.compile(r"\blocation\s*\.\s*(?:assign|replace)\s*\((?!\s*" + _q + r")", re.I), "dynamic_navigation", "warn",
     "navigates to a computed URL"),
    (re.compile(r"\b(?:top|parent)\s*\.\s*location\b"), "dynamic_navigation", "warn", "touches top/parent location"),
    (re.compile(r"\bwindow\s*\.\s*open\s*\((?!\s*" + _q + r"\s*" + _ext + ")", re.I), "popup", "warn",
     "window.open() (pop-ups are blocked)"),
    (re.compile(r"(?<![\w.])eval\s*\("), "eval", "warn", "eval() (blocked by the sandbox)"),
    (re.compile(r"\bnew\s+Function\s*\("), "eval", "warn", "new Function() (blocked by the sandbox)"),
    (re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*" + _q), "eval", "warn", "setTimeout/setInterval with a string"),
    (re.compile(r"\bdocument\s*\.\s*cookie\b"), "storage", "warn", "document.cookie (not available in the sandbox)"),
    (re.compile(r"\b(?:localStorage|sessionStorage|indexedDB)\b"), "storage", "warn",
     "browser storage (not available in the sandbox)"),
]
_css_rules = [
    (re.compile(r"@import\s+(?:url\(\s*)?['\"]?\s*" + _ext, re.I), "external_resource", "block",
     "CSS @import from another site"),
    (re.compile(r"url\(\s*['\"]?\s*" + _ext, re.I), "external_resource", "block", "CSS url() from another site"),
]
_frames = {"iframe", "frame", "frameset", "object", "embed", "applet", "portal"}
_media = {"img", "audio", "video", "source", "track", "input"}
_payment = re.compile(r"cc-(?:number|csc|exp|name)|card.?num|cvv|cvc|expir|tarjeta", re.I)
# freno extra contra la suplantación (no es una defensa): login o pago + nombre de una marca conocida
_brands = re.compile(r"\b(?:google|gmail|microsoft|outlook|office ?365|apple|icloud|paypal|facebook|instagram|"
                     r"whatsapp|amazon|netflix|bbva|santander|banamex|banorte|hsbc|mercado ?pago|mercado ?libre|"
                     r"twitter|linkedin|github|bank|banco)\b", re.I)


def _finding(code, severity, path, line, detail) -> dict:
    return {"code": code, "severity": severity, "path": path, "line": line, "detail": detail}


def _scan(text: str, rules, path: str, first_line: int = 1) -> list[dict]:
    out = []
    for pattern, code, severity, detail in rules:
        for m in pattern.finditer(text):
            out.append(_finding(code, severity, path, first_line + text.count("\n", 0, m.start()), detail))
    return out


def _is_external(url: str | None) -> bool:
    return bool(url) and bool(_ext_url.match(url))


def _local(url: str | None) -> str | None:
    """Ruta local de una referencia relativa ("js/app.js", "./a.css"), o None si no es local."""
    if not url or _is_external(url) or re.match(r"^\s*(?:data:|blob:|#|javascript:|mailto:|tel:)", url, re.I):
        return None
    clean = url.strip().split("#")[0].split("?")[0]
    while clean.startswith("./"):
        clean = clean[2:]
    return clean.lower() or None


class _Html(HTMLParser):
    def __init__(self, path: str):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.findings: list[dict] = []
        self.refs: list[tuple[str, int]] = []
        self.scripts: list[tuple[str, int]] = []
        self.styles: list[tuple[str, int]] = []
        self.text: list[str] = []
        self.password = False
        self._in: str | None = None
        self._start = 0

    def _add(self, code, severity, detail):
        self.findings.append(_finding(code, severity, self.path, self.getpos()[0], detail))

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        line = self.getpos()[0]
        if tag in _frames:
            self._add("nested_frame", "block", f"<{tag}> (embedded pages are not allowed)")
        if tag == "base":
            self._add("redirect", "block", "<base> changes where every link points")
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self._add("redirect", "block", "<meta http-equiv=refresh> redirect")
        if tag == "script":
            if _is_external(a.get("src")):
                self._add("external_script", "block", f"script from another site: {a['src'][:80]}")
            elif _local(a.get("src")):
                self.refs.append((_local(a["src"]), line))
            self._in, self._start = "script", line
        if tag == "style":
            self._in, self._start = "style", line
        if tag == "link" and a.get("href"):
            if _is_external(a["href"]):
                self._add("external_resource", "block", f"<link> to another site: {a['href'][:80]}")
            elif "stylesheet" in a.get("rel", "").lower() and _local(a["href"]):
                self.refs.append((_local(a["href"]), line))
        if tag in _media:
            for attr in ("src", "srcset", "poster"):
                value = a.get(attr, "")
                if any(_is_external(part.strip().split(" ")[0]) for part in value.split(",") if part.strip()):
                    self._add("external_resource", "block", f"<{tag}> loads from another site")
                elif attr == "src" and _local(value) and tag != "input":
                    self.refs.append((_local(value), line))
        if tag == "form":
            action = a.get("action", "")
            if _is_external(action):
                self._add("external_form", "block", f"form sends data to another site: {action[:80]}")
            elif action.strip() not in ("", "#"):
                self._add("form_action", "warn", "form with an action (forms cannot be submitted in the sandbox)")
        if tag == "input":
            if a.get("type", "").lower() == "password":
                self.password = True
                self._add("password_field", "warn", "password field")
            if _payment.search(" ".join((a.get("autocomplete", ""), a.get("name", ""), a.get("id", ""),
                                         a.get("placeholder", "")))):
                self._add("payment_field", "warn", "payment card field")
        if tag == "a":
            href = a.get("href", "")
            if _is_external(href):
                self._add("external_link", "info", f"link to another site: {href[:80]}")
            elif href.strip().lower().startswith("javascript:"):
                self._add("javascript_url", "warn", "javascript: link")
        if a.get("style"):
            self.styles.append((a["style"], line))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._in = None

    def handle_data(self, data):
        if self._in == "script":
            self.scripts.append((data, self._start))
        elif self._in == "style":
            self.styles.append((data, self._start))
        else:
            self.text.append(data)


def analyze(files: dict[str, str]) -> list[dict]:
    """Hallazgos de los archivos de texto de un proyecto ({ruta: contenido}), ordenados por severidad y ruta."""
    findings: list[dict] = []
    known = set(files)
    for path, content in sorted(files.items()):
        ext = extension(path)
        if ext == ".html":
            parser = _Html(path)
            parser.feed(content)
            parser.close()
            findings += parser.findings
            for script, line in parser.scripts:
                findings += _scan(script, _js_rules, path, line)
            for style, line in parser.styles:
                findings += _scan(style, _css_rules, path, line)
            for ref, line in parser.refs:
                if ref not in known:
                    findings.append(_finding("missing_file", "info", path, line, f"references {ref}, which does not "
                                                                                  "exist"))
            text = " ".join(parser.text)
            if parser.password and _brands.search(text):
                findings.append(_finding("impersonation", "warn", path, 1, "a login form that names a real company or "
                                                                           "service"))
        elif ext == ".js":
            findings += _scan(content, _js_rules, path)
        elif ext == ".css":
            findings += _scan(content, _css_rules, path)
    order = {"block": 0, "warn": 1, "info": 2}
    return sorted(findings, key=lambda f: (order[f["severity"]], f["path"], f["line"], f["code"]))


def blockers(findings: list[dict]) -> list[dict]:
    """Lo que impide publicar."""
    return [f for f in findings if f["severity"] == "block"]


def warnings(findings: list[dict]) -> list[dict]:
    """Lo que exige aviso explícito para publicar."""
    return [f for f in findings if f["severity"] == "warn"]


def summary(findings: list[dict], limit: int = 12) -> str:
    """Resumen para el modelo (inglés)."""
    if not findings:
        return "Code check: no problems found."
    lines = [f'- [{f["severity"]}] {f["path"]}:{f["line"]} {f["detail"]}' for f in findings[:limit]]
    more = f"\n- ... and {len(findings) - limit} more" if len(findings) > limit else ""
    head = (f"Code check: {len(blockers(findings))} blocking, {len(warnings(findings))} warnings. Blocking problems "
            "must be fixed before the project can be shared:")
    return head + "\n" + "\n".join(lines) + more
