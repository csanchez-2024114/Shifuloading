import pytest
from functions_helpers import DESC
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel

from app.core.constants import Collections
from app.functions.context import Context
from app.functions.publish import PublishConflict, publish
from app.functions.registry import function, isolated_registry, register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType, Verb


class In(BaseModel):
    pass


class Out(BaseModel):
    n: int = 0


@pytest.fixture
def db():
    return AsyncMongoMockClient()["publish_test"]


def define(description=DESC, ids=("demo.a.get",), version=1, reversible=True):
    register_app(AppSpec(app="demo", provider_keys=["demo"], auth=AuthSpec(type=AuthType.bearer)))
    for fid in ids:
        async def h(ctx: Context, args: In) -> Out: ...
        function(id=fid, version=version, verb=Verb.read, reversible=reversible, description=description, examples=[{"input": {}}])(h)


async def test_first_publish_creates_and_second_is_a_noop(db):
    with isolated_registry():
        define(ids=("demo.a.get", "demo.b.get"))
        assert await publish(db) == {"functions_created": 2, "functions_text_updated": 0, "functions_unchanged": 0, "apps": 1}
        assert await publish(db) == {"functions_created": 0, "functions_text_updated": 0, "functions_unchanged": 2, "apps": 1}
        doc = await db[Collections.FUNCTIONS].find_one({"id": "demo.a.get"})
        assert doc["version"] == 1 and doc["status"] == "draft" and len(doc["spec_hash"]) == 64
        assert (await db[Collections.FUNCTION_APPS].find_one({"app": "demo"}))["auth"]["type"] == "bearer"


async def test_changed_contract_without_new_version_is_refused_and_writes_nothing(db):
    with isolated_registry():
        define()
        await publish(db)
    with isolated_registry():
        define(reversible=False, ids=("demo.a.get", "demo.nueva.get"))  # cambia el contrato (la marca reversible), no solo el texto
        with pytest.raises(PublishConflict, match=r"demo\.a\.get v1"):
            await publish(db)
        assert await db[Collections.FUNCTIONS].count_documents({}) == 1  # ni siquiera la funcion nueva se publico


async def test_new_version_is_published_next_to_the_old_one(db):
    with isolated_registry():
        define(version=1)
        await publish(db)
    with isolated_registry():
        define(reversible=False, version=2)
        assert (await publish(db))["functions_created"] == 1
        assert await db[Collections.FUNCTIONS].count_documents({"id": "demo.a.get"}) == 2


async def test_status_changed_in_mongo_survives_republish(db):
    with isolated_registry():
        define()
        await publish(db)
        await db[Collections.FUNCTIONS].update_one({"id": "demo.a.get"}, {"$set": {"status": "degraded"}})
        await publish(db)
        assert (await db[Collections.FUNCTIONS].find_one({"id": "demo.a.get"}))["status"] == "degraded"


async def test_indexes_make_id_and_version_unique(db):
    with isolated_registry():
        define()
        await publish(db)
    info = await db[Collections.FUNCTIONS].index_information()
    assert any(v.get("unique") and [k for k, _ in v["key"]] == ["id", "version"] for v in info.values())


async def test_better_wording_updates_the_text_without_a_new_version_or_touching_status(db):
    better = DESC + " It is also the function the team uses to verify that publishing refreshes wording."
    with isolated_registry():
        define()
        await publish(db)
        await db[Collections.FUNCTIONS].update_one({"id": "demo.a.get"}, {"$set": {"status": "degraded"}})
    with isolated_registry():
        define(description=better)
        assert await publish(db) == {"functions_created": 0, "functions_text_updated": 1, "functions_unchanged": 0, "apps": 1}
        doc = await db[Collections.FUNCTIONS].find_one({"id": "demo.a.get"})
        assert doc["description"] == " ".join(better.split()) and doc["status"] == "degraded" and doc["version"] == 1
        assert await db[Collections.FUNCTIONS].count_documents({}) == 1
        assert (await publish(db))["functions_text_updated"] == 0  # idempotente
