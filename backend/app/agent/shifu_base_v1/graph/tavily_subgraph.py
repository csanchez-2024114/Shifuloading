"""
tavily_subgraph — agente_v3 Retrieval + Semantic Preservation subgraph

Encapsulates the full research pipeline as a single LangGraph subgraph node.
The parent graph treats this as one unit; internally it runs two sequential nodes.

Philosophy: "No interpretar información → solo preservarla estructuralmente"

Internal flow:
  START
    │
    ▼
  tavily_searcher   ← Web retrieval (Phase 1: TavilySearch, Phase 2: TavilyExtract)
    │                  Output: retrieved_research, retrieved_sources
    ▼
  research_curator  ← Semantic preservation (adaptive segmentation + parallel
    │                  extraction + semantic synthesis)
    │                  Output: curated_research
    ▼
  END → bigtools_inspector (fan-in with catalog_checker + auth_validator)

Contract:
  Input  (reads from ShifuState):
    - optimized_search_query
    - needs_external_info
    - effort_level
    - location_aware
    - user_location

  Output (writes to ShifuState):
    - retrieved_research
    - retrieved_sources
    - curated_research
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.agent.shared.nodes.research_analyst import research_analyst_node
from app.agent.shared.nodes.research_curator import research_curator_node
from app.agent.shared.nodes.tavily_searcher import tavily_searcher_node
from app.agent.shifu_base_v1.graph.state import ShifuState

logger = logging.getLogger(__name__)

_builder = StateGraph(ShifuState)

_builder.add_node("tavily_searcher",  tavily_searcher_node)
_builder.add_node("research_curator", research_curator_node)
_builder.add_node("research_analyst", research_analyst_node)  # piensa sobre las fuentes: cuales valen, que concluye

_builder.add_edge(START,              "tavily_searcher")
_builder.add_edge("tavily_searcher",  "research_curator")
_builder.add_edge("research_curator", "research_analyst")
_builder.add_edge("research_analyst", END)

tavily_subgraph = _builder.compile()

