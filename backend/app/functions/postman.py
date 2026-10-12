"""Genera las colecciones de Postman (una por app) y la plantilla de entorno desde el registro de funciones.

Es el punto de partida del junior: ya trae el caso normal, la entrada invalida y una solicitud por cuenta. El junior guarda sus
respuestas de ejemplo en cada solicitud (ese es su registro) y re-exporta la coleccion a doc/postman/<app>.json.
Salida determinista (ids derivados del nombre, claves ordenadas): los diffs de git solo muestran cambios reales.
Nunca contiene valores de secretos: todo va por variables {{...}} del entorno, que no se versiona.
"""
import json
import uuid
from typing import Any

from app.functions.registry import RegisteredFunction, get_app, list_apps, list_functions
from app.functions.spec import Verb

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
_NS = uuid.UUID("6f1c2a52-6f5f-4d3a-9c0e-5d6a8f3b1a10")  # fijo: ids estables entre ejecuciones


def _id(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "/".join(parts)))


def _wrong_value(prop: dict[str, Any]) -> Any:
    t = prop.get("type")
    if t in ("integer", "number"):
        return "no-es-un-numero"
    if t == "boolean":
        return "quizas"
    if t == "array":
        return "no-es-una-lista"
    return 12345  # string, enum o sin tipo: un numero no es una cadena valida


def invalid_input(fn: RegisteredFunction) -> dict[str, Any] | None:
    """Una entrada que rompe el esquema (primer campo con el tipo equivocado); None si la funcion no tiene campos."""
    props = fn.spec.input_schema.get("properties") or {}
    if not props:
        return None
    name = next(iter(props))
    return {name: _wrong_value(props[name])}


def _request(name: str, method: str, path: list[str], body: dict[str, Any] | None = None, tests: str | None = None) -> dict[str, Any]:
    req: dict[str, Any] = {
        "method": method,
        "header": [{"key": "Content-Type", "value": "application/json"}] if body is not None else [],
        "url": {"raw": "{{baseUrl}}/" + "/".join(path), "host": ["{{baseUrl}}"], "path": path},
    }
    if body is not None:
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False), "options": {"raw": {"language": "json"}}}
    item: dict[str, Any] = {"id": _id(name, method, *path), "name": name, "request": req, "response": []}
    if tests:
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": tests.splitlines()}}]
    return item


def _function_folder(fn: RegisteredFunction) -> dict[str, Any]:
    s = fn.spec
    base = ["internal", "functions", s.id]
    example = s.examples[0].input
    items = [
        _request("Ver ficha", "GET", base),
        _request("Caso normal (ejemplo de la ficha)", "POST", base + ["test"], {"input": example}),
    ]
    bad = invalid_input(fn)
    if bad is not None:
        items.append(_request("Entrada invalida (debe dar invalid_input)", "POST", base + ["test"], {"input": bad}))
    for letter in ("a", "b"):  # una solicitud por cuenta; borra la que no necesites o agrega las que quieras
        items.append(_request(f"Cuenta {letter.upper()} ({{{{account_id_{s.app}_{letter}}}}})", "POST", base + ["test"],
                              {"input": example, "account_ids": [f"{{{{account_id_{s.app}_{letter}}}}}"]}))
    if s.verb != Verb.read:
        items.append(_request("ATENCION: ejecucion real (allow_write)", "POST", base + ["test"],
                              {"input": example, "allow_write": True}))
    return {"id": _id(s.id), "name": f"{s.id} (v{s.version})", "item": items}


_LOGIN_TESTS = """pm.test("login ok", function () { pm.response.to.have.status(200); });
pm.environment.set("token", pm.response.json().access_token);"""


def collection_for_app(app: str) -> dict[str, Any]:
    spec = get_app(app)
    funcs = [f for f in list_functions() if f.spec.app == app]
    return {
        "info": {
            "_postman_id": _id("collection", app),
            "name": f"Shifu · funciones · {app}",
            "description": (f"Pruebas por API de las funciones de {app} (autenticacion: {spec.auth.type.value}, API {spec.api_version or 'sin version'}). "
                            "Generada por scripts/export_postman.py. Guarda tus respuestas de ejemplo en cada solicitud y re-exporta."),
            "schema": SCHEMA,
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
        "item": [
            {"id": _id("login", app), "name": "0 · Login (guarda el token en el entorno)",
             "request": {"method": "POST", "auth": {"type": "noauth"}, "header": [{"key": "Content-Type", "value": "application/json"}],
                         "url": {"raw": "{{baseUrl}}/api/v1/auth/login", "host": ["{{baseUrl}}"], "path": ["api", "v1", "auth", "login"]},
                         "body": {"mode": "raw", "raw": '{\n  "email": "{{email}}",\n  "password": "{{password}}"\n}',
                                  "options": {"raw": {"language": "json"}}}},
             "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": _LOGIN_TESTS.splitlines()}}], "response": []},
            *[_function_folder(f) for f in funcs],
        ],
    }


def environment_template() -> dict[str, Any]:
    values = [
        {"key": "baseUrl", "value": "http://localhost:5001", "type": "default", "enabled": True},
        {"key": "email", "value": "", "type": "default", "enabled": True},
        {"key": "password", "value": "", "type": "secret", "enabled": True},
        {"key": "token", "value": "", "type": "secret", "enabled": True},
    ]
    for app in list_apps():
        for letter in ("a", "b"):
            values.append({"key": f"account_id_{app.app}_{letter}", "value": "", "type": "default", "enabled": True})
    return {"id": _id("environment"), "name": "Shifu local (plantilla; copiala y llena tus valores, no la subas)",
            "values": values, "_postman_variable_scope": "environment"}


def render(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
