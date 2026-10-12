"""
v1 graph registry — single source for compiled graph instances.

Usage in main.py lifespan:
    from app.agent.shifu_base_v1.registry import init_v1_graphs, get_v1_graph
    init_v1_graphs(checkpointer=checkpointer)
    app.state.v3_graph = get_v1_graph()
"""

from app.agent.shifu_base_v1.graph.builder_standard import build_graph

_graphs: dict = {}


def init_v1_graphs(checkpointer=None) -> dict:
    _graphs["standard"] = build_graph(checkpointer=checkpointer)
    return _graphs


def get_v1_graph(tier: str = "standard"):
    return _graphs.get(tier) or _graphs.get("standard")


# Commercial alias — use this in new code
get_shifu_graph = get_v1_graph
