from typing import Dict, Any

# Slugs canónicos (deben coincidir con user.plan, que Stripe siempre guarda en minúsculas)
DEFAULT_PLAN = "free"

# ponytail: daily_token_limit y max_apps_per_workflow son placeholders sin validar
# contra costo real de OpenAI ni contra uso real de usuarios — ajustar con datos
# reales antes de anunciarlos públicamente como límites del plan.
PLAN_RULES: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_agents": 1,
        "max_iterations": 5,
        "tools": ["calendar", "tasks"],
        "ocr_enabled": False,
        "rpm_limit": 20,
        "max_workflows": 1,
        "max_apps_per_workflow": 2,
        "max_accounts_per_provider": 1,
        "max_workspaces": 1,
        "max_concurrent_runs": 1,
        "daily_token_limit": 20000,
    },
    "standard": {
        "max_agents": 5,
        "max_iterations": 12,
        "tools": ["calendar", "tasks", "gmail", "drive", "sheets"],
        "ocr_enabled": True,
        "rpm_limit": 40,
        "max_workflows": 5,
        "max_apps_per_workflow": 2,
        "max_accounts_per_provider": 2,
        "max_workspaces": 2,
        "max_concurrent_runs": 2,
        "daily_token_limit": 80000,
    },
    "pro": {
        "max_agents": 15,
        "max_iterations": 25,
        "tools": ["calendar", "tasks", "gmail", "drive", "sheets", "slack", "notion", "tavily_search"],
        "ocr_enabled": True,
        "rpm_limit": 60,
        "max_workflows": 15,
        "max_apps_per_workflow": 4,
        "max_accounts_per_provider": 3,
        "max_workspaces": 5,
        "max_concurrent_runs": 3,
        "daily_token_limit": 250000,
    },
    "premium": {
        "max_agents": 50,
        "max_iterations": 40,
        "tools": ["calendar", "tasks", "gmail", "drive", "sheets", "slack", "notion", "tavily_search", "monday", "asana", "hubspot"],
        "ocr_enabled": True,
        "rpm_limit": 100,
        "max_workflows": 50,
        "max_apps_per_workflow": 8,
        "max_accounts_per_provider": 5,
        "max_workspaces": 10,
        "max_concurrent_runs": 5,
        "daily_token_limit": 800000,
    },
    "enterprise": {
        "max_agents": -1,
        "max_iterations": 100,
        "tools": ["all"],
        "ocr_enabled": True,
        "rpm_limit": -1,
        "max_workflows": -1,
        "max_apps_per_workflow": -1,
        "max_accounts_per_provider": -1,
        "max_workspaces": -1,
        "max_concurrent_runs": -1,
        "daily_token_limit": -1,
    },
}


def get_plan_rules(plan: str) -> Dict[str, Any]:
    """Lookup case-insensitive — user.plan siempre viene en minúsculas, pero no confiamos ciegamente en eso."""
    return PLAN_RULES.get((plan or DEFAULT_PLAN).lower(), PLAN_RULES[DEFAULT_PLAN])


# El grafo agente_v3 usaba un recursion_limit fijo de 50 para todos los planes (nunca se rompía nada).
# `max_iterations` en PLAN_RULES fue pensado para otro conteo (loop de tools) y sus valores crudos
# (5/12/25/40) son más bajos que los super-steps que ya consume un turno simple sin límites — usarlos
# tal cual cortaría conversaciones normales en Free/Standard. Los usamos como multiplicador sobre el
# piso actual (50) para diferenciar tiers pagos sin arriesgar el comportamiento ya validado en Free.
# ponytail: multiplicador provisional; ajustar con datos reales de super-steps por conversación.
_BASE_RECURSION_LIMIT = 50
_RECURSION_MULTIPLIER = 5
_ENTERPRISE_RECURSION_LIMIT = _BASE_RECURSION_LIMIT * 8


def get_recursion_limit(plan: str) -> int:
    max_iterations = get_plan_rules(plan).get("max_iterations", 5)
    if max_iterations == -1:
        return _ENTERPRISE_RECURSION_LIMIT
    return max(_BASE_RECURSION_LIMIT, max_iterations * _RECURSION_MULTIPLIER)


def filter_providers_by_plan(plan: str, connected_providers: set) -> set:
    """Intersecta los proveedores conectados con el whitelist de tools del plan."""
    allowed_tools = get_plan_rules(plan).get("tools", [])
    if "all" in allowed_tools:
        return connected_providers
    allowed_lower = {t.lower() for t in allowed_tools}
    return {p for p in connected_providers if p.lower() in allowed_lower}
