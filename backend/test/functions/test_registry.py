import pytest
from functions_helpers import DESC
from pydantic import BaseModel, Field

from app.functions.registry import (
    RegistryError, function, get_function, isolated_registry, list_functions, load_all, register_app, validate_registry,
)
from app.functions.context import Context
from app.functions.spec import AppSpec, AuthSpec, AuthType, Verb


class In(BaseModel):
    q: str = Field(default="", description="Text to search for in the demo data")


class Out(BaseModel):
    n: int = 0


class WhoAmI(BaseModel):
    account_id: str = ""


def demo_app(**over) -> AppSpec:
    base = dict(app="demo", provider_keys=["demo"], auth=AuthSpec(type=AuthType.bearer, scopes=["r", "w"]))
    base.update(over)
    return AppSpec(**base)


def ex(**kw):
    return {"input": {"q": "a"}, "output": {"n": 1}, **kw}


async def handler(ctx: Context, args: In) -> Out:
    return Out()


def register(id="demo.things.list", version=1, **kw):
    kw.setdefault("verb", Verb.read)
    kw.setdefault("description", DESC)
    kw.setdefault("examples", [ex()])
    return function(id=id, version=version, **kw)(handler)


def test_register_and_lookup_builds_schemas_from_the_models():
    with isolated_registry():
        register_app(demo_app())
        register()
        fn = get_function("demo.things.list")
        assert fn.spec.input_schema["properties"]["q"]["type"] == "string"
        assert fn.spec.output_schema["properties"]["n"]["type"] == "integer"
        assert fn.spec.multi_account is True  # hereda de la app


def test_function_needs_its_app_first():
    with isolated_registry(), pytest.raises(RegistryError, match="registra primero la app"):
        register()


def test_handler_must_annotate_models():
    async def bad(ctx, args): ...
    with isolated_registry():
        register_app(demo_app())
        with pytest.raises(RegistryError, match="modelo Pydantic"):
            function(id="demo.things.list", version=1, verb=Verb.read, description=DESC, examples=[ex()])(bad)


def test_example_must_satisfy_its_own_schemas():
    with isolated_registry():
        register_app(demo_app())
        with pytest.raises(RegistryError, match="ejemplo"):
            register(examples=[{"input": {"q": 123}}])
        with pytest.raises(RegistryError, match="ejemplo"):
            register(examples=[{"input": {}, "output": {"n": "no-es-int"}}])


def test_scopes_must_belong_to_the_app():
    with isolated_registry():
        register_app(demo_app())
        with pytest.raises(RegistryError, match="no estan declarados"):
            register(scopes=["admin"])
        register(scopes=["r"])


def test_duplicates_and_versions():
    with isolated_registry():
        register_app(demo_app())
        register(version=1)
        with pytest.raises(RegistryError, match="ya esta registrada"):
            register(version=1)
        register(version=2)
        assert get_function("demo.things.list").spec.version == 2          # sin version: la mayor
        assert get_function("demo.things.list", 1).spec.version == 1
        with pytest.raises(RegistryError, match="version 9"):
            get_function("demo.things.list", 9)
        assert [f.spec.version for f in list_functions()] == [1, 2]


def test_same_app_twice_must_be_identical():
    with isolated_registry():
        register_app(demo_app())
        register_app(demo_app())  # igual: ok
        with pytest.raises(RegistryError, match="otra definicion"):
            register_app(demo_app(api_version="v2"))


def test_validate_rejects_unimplemented_auth_type():
    with isolated_registry():
        register_app(demo_app(auth=AuthSpec(type=AuthType.oauth1)))
        with pytest.raises(RegistryError, match="oauth1"):
            validate_registry()


def test_validate_whoami_rules():
    class NeedsArg(BaseModel):
        id: str = Field(description="Required identifier that a whoami must not ask for")

    async def who_ok(ctx: Context, args: In) -> WhoAmI: ...
    async def who_arg(ctx: Context, args: NeedsArg) -> WhoAmI: ...
    async def who_noid(ctx: Context, args: In) -> Out: ...

    with isolated_registry():
        register_app(demo_app(whoami="demo.account.get"))
        with pytest.raises(RegistryError, match="no esta registrada"):
            validate_registry()
        function(id="demo.account.get", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])(who_ok)
        validate_registry()
    with isolated_registry():
        register_app(demo_app(whoami="demo.account.get"))
        function(id="demo.account.get", version=1, verb=Verb.read, description=DESC, examples=[{"input": {"id": "1"}}])(who_arg)
        with pytest.raises(RegistryError, match="no debe pedir parametros"):
            validate_registry()
    with isolated_registry():
        register_app(demo_app(whoami="demo.account.get"))
        function(id="demo.account.get", version=1, verb=Verb.update, description=DESC, examples=[{"input": {}}])(who_ok)
        with pytest.raises(RegistryError, match="de lectura"):
            validate_registry()
    with isolated_registry():
        register_app(demo_app(whoami="demo.account.get"))
        function(id="demo.account.get", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])(who_noid)
        with pytest.raises(RegistryError, match="campo account_id"):
            validate_registry()


def test_load_all_registers_real_apps_skips_templates_and_validates():
    # Real (no aislado): load_all importa los modulos una sola vez, asi que dentro de un registro aislado se perderian.
    load_all()
    load_all()  # idempotente
    ids = {f.spec.id for f in list_functions()}
    assert {"brevo.account.get", "dropbox.account.get"} <= ids
    assert all(not i.startswith("example.") for i in ids)  # la carpeta _template no se carga como app real


def test_every_input_field_needs_an_english_description():
    class Undocumented(BaseModel):
        q: str = ""

    class Spanish(BaseModel):
        q: str = Field(default="", description="Texto a buscar para el usuario")

    class Short(BaseModel):
        q: str = Field(default="", description="text")

    class Nested(BaseModel):
        inner: str = Field(default="", description="A nested field that is documented properly")

    class NestedParent(BaseModel):
        child: Nested = Field(default_factory=Nested, description="The nested object, documented properly too")

    class Good(BaseModel):
        q: str = Field(default="", description="Text to search for in names and contents")

    async def with_model(model):
        async def h(ctx: Context, args: model) -> Out: ...
        return h

    import asyncio
    for model, expect in ((Undocumented, "sin descripcion"), (Short, "sin descripcion"), (Spanish, "ingles")):
        with isolated_registry():
            register_app(demo_app())
            h = asyncio.run(with_model(model))
            with pytest.raises(RegistryError, match=expect):
                function(id="demo.things.list", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])(h)
    with isolated_registry():
        register_app(demo_app())
        for fid, model in (("demo.good.list", Good), ("demo.nested.list", NestedParent)):
            function(id=fid, version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])(asyncio.run(with_model(model)))
