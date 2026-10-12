import json
import re

import pytest

from app.functions.postman import collection_for_app, environment_template, invalid_input, render
from app.functions.registry import get_function, list_apps, load_all


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


def test_one_collection_per_app_with_login_and_per_function_folders():
    for app in list_apps():
        col = collection_for_app(app.app)
        assert col["info"]["schema"].endswith("collection.json") and col["auth"]["bearer"][0]["value"] == "{{token}}"
        assert col["item"][0]["name"].startswith("0 · Login") and "access_token" in "".join(col["item"][0]["event"][0]["script"]["exec"])
        folders = col["item"][1:]
        assert folders and all(f["item"] for f in folders)
        names = [i["name"] for i in folders[0]["item"]]
        assert names[0] == "Ver ficha" and any(n.startswith("Caso normal") for n in names)
        assert sum(n.startswith("Cuenta ") for n in names) == 2


def test_requests_hit_the_internal_test_endpoint_with_the_example_input():
    col = collection_for_app("brevo")
    folder = next(f for f in col["item"][1:] if f["name"].startswith("brevo.contacts.list"))
    normal = next(i for i in folder["item"] if i["name"].startswith("Caso normal"))
    assert normal["request"]["url"]["raw"] == "{{baseUrl}}/internal/functions/brevo.contacts.list/test"
    assert json.loads(normal["request"]["body"]["raw"]) == {"input": get_function("brevo.contacts.list").spec.examples[0].input}
    acct = next(i for i in folder["item"] if i["name"].startswith("Cuenta A"))
    assert json.loads(acct["request"]["body"]["raw"])["account_ids"] == ["{{account_id_brevo_a}}"]


def test_invalid_input_breaks_the_schema_by_type():
    assert invalid_input(get_function("brevo.contacts.list")) == {"limit": "no-es-un-numero"}
    assert invalid_input(get_function("dropbox.files.search")) == {"query": 12345}
    assert invalid_input(get_function("brevo.account.get")) is None  # sin campos no hay como romperla


def test_output_is_deterministic():
    assert render(collection_for_app("dropbox")) == render(collection_for_app("dropbox"))
    assert render(environment_template()) == render(environment_template())


def test_no_secret_values_anywhere():
    texts = [render(collection_for_app(a.app)) for a in list_apps()] + [render(environment_template())]
    for text in texts:
        assert not re.search(r"sk-[A-Za-z0-9]{10,}|Bearer ey|api-key\"\s*:\s*\"[A-Za-z0-9]{8,}", text)
    env = environment_template()
    secrets = {v["key"]: v["value"] for v in env["values"] if v["type"] == "secret"}
    assert set(secrets) == {"password", "token"} and all(v == "" for v in secrets.values())
    assert all(v["value"] == "" for v in env["values"] if v["key"].startswith("account_id_"))
    assert {v["key"] for v in env["values"] if v["key"].startswith("account_id_")} >= {"account_id_brevo_a", "account_id_dropbox_b"}
