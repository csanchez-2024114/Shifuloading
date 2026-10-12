"""Registro de apps y funciones. Es estricto a proposito: una ficha invalida FALLA EN VOZ ALTA al importar.

(El loader viejo, bigtools_loader, salta en silencio los modulos que no existen o fallan.)

Uso en app/functions/apps/<app>/:
    app_spec.py   -> register_app(AppSpec(...))
    functions.py  -> @function(id="app.recurso.verbo", version=1, verb=Verb.read, description=..., examples=[...])
                     async def handler(ctx: Context, args: Entrada) -> Salida: ...
Las anotaciones de `args` y del retorno (modelos Pydantic) generan input_schema y output_schema.
"""
import contextlib
import importlib
import pkgutil
import typing
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from pydantic import BaseModel, ValidationError

from app.functions.auth import get_strategy
from app.functions.spec import (
    MIN_FIELD_DESCRIPTION_CHARS, AppSpec, Example, FunctionSpec, Status, Verb, looks_spanish,
)


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class RegisteredFunction:
    spec: FunctionSpec
    handler: Callable[..., Any]
    input_model: type[BaseModel]
    output_model: type[BaseModel]


_APPS: dict[str, AppSpec] = {}
_FUNCS: dict[tuple[str, int], RegisteredFunction] = {}


def undocumented_fields(schema: Any, path: str = "") -> list[str]:
    """Campos de un esquema JSON sin descripcion util en ingles (el agente lee esto para llenar los argumentos)."""
    problems: list[str] = []
    if isinstance(schema, dict):
        for name, prop in (schema.get("properties") or {}).items():
            desc = prop.get("description", "") if isinstance(prop, dict) else ""
            if len(desc.strip()) < MIN_FIELD_DESCRIPTION_CHARS:
                problems.append(f"{path}{name}: sin descripcion (minimo {MIN_FIELD_DESCRIPTION_CHARS} caracteres)")
            elif looks_spanish(desc):
                problems.append(f"{path}{name}: la descripcion debe estar en ingles")
        for key, value in schema.items():
            if key != "properties":
                problems += undocumented_fields(value, path)
    elif isinstance(schema, list):
        for item in schema:
            problems += undocumented_fields(item, path)
    return problems


def register_app(spec: AppSpec) -> AppSpec:
    existing = _APPS.get(spec.app)
    if existing is not None and existing != spec:
        raise RegistryError(f"La app '{spec.app}' ya esta registrada con otra definicion.")
    _APPS[spec.app] = spec
    return spec


def function(*, id: str, version: int, verb: Verb, description: str, examples: Iterable[Any],
             exits_outside: bool = False, reversible: bool = True, scopes: Iterable[str] = (),
             upstream_api: str = "", status: Status = Status.draft):
    def deco(fn):
        app_name = id.split(".", 1)[0]
        app = _APPS.get(app_name)
        if app is None:
            raise RegistryError(f"{id}: registra primero la app '{app_name}' con register_app().")
        hints = typing.get_type_hints(fn)
        in_model, out_model = hints.get("args"), hints.get("return")
        for label, model in (("args", in_model), ("el retorno", out_model)):
            if not (isinstance(model, type) and issubclass(model, BaseModel)):
                raise RegistryError(f"{id}: {label} del handler debe estar anotado con un modelo Pydantic.")
        scopes_t = list(scopes)
        extra = set(scopes_t) - set(app.auth.scopes)
        if app.auth.scopes and extra:
            raise RegistryError(f"{id}: scopes {sorted(extra)} no estan declarados en la app '{app_name}'.")
        spec = FunctionSpec(
            id=id, version=version, app=app_name, upstream_api=upstream_api, verb=verb,
            exits_outside=exits_outside, reversible=reversible, scopes=scopes_t, multi_account=app.multi_account,
            description=description, examples=[e if isinstance(e, Example) else Example(**e) for e in examples],
            input_schema=in_model.model_json_schema(), output_schema=out_model.model_json_schema(), status=status,
        )
        bad = undocumented_fields(spec.input_schema)
        if bad:
            raise RegistryError(f"{id}: todos los campos de entrada necesitan descripcion en ingles -> " + "; ".join(bad))
        for ex in spec.examples:  # un ejemplo que no cumple sus propios esquemas es una ficha rota
            try:
                in_model.model_validate(ex.input)
                if ex.output is not None:
                    out_model.model_validate(ex.output)
            except ValidationError as exc:
                raise RegistryError(f"{id}: el ejemplo '{ex.name}' no cumple los esquemas: {exc.errors()[0]['msg']}") from exc
        key = (id, version)
        if key in _FUNCS:
            raise RegistryError(f"{id} version {version} ya esta registrada.")
        _FUNCS[key] = RegisteredFunction(spec=spec, handler=fn, input_model=in_model, output_model=out_model)
        return fn

    return deco


def get_app(app: str) -> AppSpec:
    try:
        return _APPS[app]
    except KeyError:
        raise RegistryError(f"App '{app}' no registrada.") from None


def list_apps() -> list[AppSpec]:
    return sorted(_APPS.values(), key=lambda a: a.app)


def list_functions() -> list[RegisteredFunction]:
    return sorted(_FUNCS.values(), key=lambda f: (f.spec.id, f.spec.version))


def get_function(id: str, version: Optional[int] = None) -> RegisteredFunction:
    versions = sorted(v for (fid, v) in _FUNCS if fid == id)
    if not versions:
        raise RegistryError(f"Funcion '{id}' no registrada.")
    use = version if version is not None else versions[-1]  # sin version: la mayor
    try:
        return _FUNCS[(id, use)]
    except KeyError:
        raise RegistryError(f"Funcion '{id}' no tiene la version {use} (hay {versions}).") from None


def validate_registry() -> None:
    for app in _APPS.values():
        try:
            get_strategy(app.auth.type)
        except NotImplementedError as exc:
            raise RegistryError(f"App '{app.app}': {exc}") from None
        if app.whoami:
            who = next((f for f in _FUNCS.values() if f.spec.id == app.whoami), None)
            if who is None:
                raise RegistryError(f"App '{app.app}': whoami '{app.whoami}' no esta registrada.")
            if who.spec.verb != Verb.read:
                raise RegistryError(f"App '{app.app}': whoami '{app.whoami}' debe ser de lectura.")
            if "account_id" not in who.output_model.model_fields:
                raise RegistryError(f"App '{app.app}': whoami '{app.whoami}' debe devolver un campo account_id (el mismo valor guardado en la conexion).")
            try:
                who.input_model.model_validate({})
            except ValidationError:
                raise RegistryError(f"App '{app.app}': whoami '{app.whoami}' no debe pedir parametros.") from None


def load_all() -> None:
    """Importa cada paquete app/functions/apps/<app>/ (los que empiezan por '_' son plantillas) y valida."""
    import app.functions.apps as pkg

    for mod in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"app.functions.apps.{mod.name}.app_spec")
        importlib.import_module(f"app.functions.apps.{mod.name}.functions")
    validate_registry()


@contextlib.contextmanager
def isolated_registry():
    """Para pruebas: registra lo que quieras y al salir se restaura el registro real.
    No llames a load_all() aqui dentro: importa cada modulo una sola vez y se perderia al salir."""
    apps, funcs = dict(_APPS), dict(_FUNCS)
    _APPS.clear(), _FUNCS.clear()
    try:
        yield
    finally:
        _APPS.clear(), _FUNCS.clear()
        _APPS.update(apps), _FUNCS.update(funcs)
