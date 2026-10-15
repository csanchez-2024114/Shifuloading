"""Tool template (@tool_spec): rich index document, startup validation and prerequisite functions."""
import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from assistant.apps import crm_demo
from assistant.tool_spec import AutoResolve, expand_requirements, get_spec, tool_spec, validate_registry
from conftest import FakeSearch, fake_llm, run_turn, tool_call, uid


@pytest.fixture(autouse=True)
def _crm_limpio():
    crm_demo.reset()
    yield
    crm_demo.reset()


def _crm_registry():
    return {t.name: t for t in crm_demo.crm_tools()}


def test_documento_indexado_tiene_todos_los_campos():
    t = crm_demo.crm_create_order
    doc = get_spec(t).document(t)
    for fragment in ("App: crm | Resource: order | Action: create", "When to use:", "When NOT to use:",
                     "Parameters: product (Product name or SKU.)", "Prerequisites:", "Tags:", "Example requests:"):
        assert fragment in doc
    assert "crm_find_customer_by_email or crm_list_customers" in t.description  # el LLM ve el requisito


def test_validacion_reporta_todos_los_problemas():
    @tool_spec(app="shop", resource="item", action="get", summary="Get an item.", when_to_use="Need an item.",
               examples=["only one"], requires={"item_id": ["shop_missing_tool"]},
               auto={"nope": AutoResolve(source="crm_list_customers", args={"bad": "item_id"}, field="id")},
               effect="delete")
    def wrong_prefix_get(item_id: str = "") -> dict:
        """Get an item.

        Args:
            item_id: Item id.
        """
        return {}

    registry = {**_crm_registry(), wrong_prefix_get.name: wrong_prefix_get}
    with pytest.raises(ValueError) as exc:
        validate_registry(registry)
    msg = str(exc.value)
    for expected in ("must start with the app prefix 'shop_'", "at least 2 example requests", "effect must be one of",
                     "prerequisite 'shop_missing_tool' is not in the registry", "auto rule for unknown parameter 'nope'",
                     "has no parameter 'bad'"):
        assert expected in msg
    validate_registry(_crm_registry())  # el CRM de ejemplo es válido


def test_expand_requirements_agrega_prefunciones_sin_duplicar():
    reg = _crm_registry()
    assert expand_requirements(["crm_create_order"], reg) == [
        "crm_create_order", "crm_find_customer_by_email", "crm_list_customers"]
    assert expand_requirements(["crm_list_customers"], reg) == ["crm_list_customers"]


def test_auto_resuelve_customer_id_y_errores_claros():
    t = crm_demo.crm_create_order
    ok = t.invoke({"product": "Monitor", "quantity": 2, "customer_email": "ana@example.com"})
    assert ok["created"] and ok["order"]["customer_id"] == "c-001"
    no = t.invoke({"product": "Monitor", "quantity": 2, "customer_email": "nadie@example.com"})
    assert "Could not resolve customer_id" in no["error"] and "crm_list_customers" in no["hint"]
    falta = t.invoke({"product": "Monitor", "quantity": 2})
    assert falta["error"] == "Missing required parameter(s): customer_id."


def test_flujo_agente_llama_la_prefuncion(make_settings):
    from assistant.bigtool_agent import _index_document, build_bigtool_agent, build_registry

    s = make_settings(use_bigtool=True, bigtool_demo_tools=True)
    query = _index_document(build_registry(None, s, InMemoryStore())["crm_list_orders"])
    agent = build_bigtool_agent(fake_llm(
        tool_call("retrieve_tools", {"query": query}, "r1"),
        tool_call("crm_list_customers", {"name_contains": "Luis"}, "c1"),   # la pre-función llegó con la búsqueda
        tool_call("crm_list_orders", {"customer_id": "c-002"}, "c2"),
        "Luis tiene 2 pedidos: Laptop y Mouse",
    ), s, checkpointer=InMemorySaver(), memories_store=InMemoryStore(),
        embeddings=DeterministicFakeEmbedding(size=64), search_fn=FakeSearch())

    ev = run_turn(agent, s, "¿qué pedidos tiene Luis?", uid())
    ends = {e["name"]: e for e in ev if e["type"] == "tool_end"}
    assert "crm_find_customer_by_email" in ends["retrieve_tools"]["output"]
    assert "crm_list_customers" in ends["retrieve_tools"]["output"]
    assert "c-002" in ends["crm_list_customers"]["output"] and "Laptop" in ends["crm_list_orders"]["output"]
    assert ev[-1]["type"] == "done"
