"""Perfil por defecto: Agente 0, asistente tipo ChatGPT. Reproduce exactamente el comportamiento anterior al refactor."""
from assistant.core.config import ROOT
from assistant.core.memory import MEMORY_POLICIES, SEARCH_ECONOMY_RULE
from assistant.core.profile import AgentProfile
from assistant.profiles.default.policies import OLD_TOOL_NAMES, TOOL_POLICIES
from assistant.profiles.default.tools import bigtool_tools, build_tools

PROFILE = AgentProfile(
    name="default",
    display_name="Agente 0",
    system_prompt_path=ROOT / "prompts" / "system.md",
    static_dir=ROOT / "static",
    build_tools=build_tools,
    bigtool_tools=bigtool_tools,
    tool_policies=TOOL_POLICIES,
    memory_policies=MEMORY_POLICIES,
    search_economy_rule=SEARCH_ECONOMY_RULE,
    legacy_tool_names=OLD_TOOL_NAMES,
)
