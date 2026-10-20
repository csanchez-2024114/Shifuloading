"""Tool template for the bigtool registry: rich, validated tool specs with prerequisite functions.

Usage (see docs/PLANTILLA_HERRAMIENTA.md):

    @tool_spec(app="crm", resource="order", action="create", summary=..., when_to_use=...,
               examples=[...], requires={"customer_id": ["crm_find_customer_by_email", "crm_list_customers"]},
               auto={"customer_id": AutoResolve(source="crm_find_customer_by_email",
                                                args={"email": "customer_email"}, field="id")})
    def crm_create_order(product: str, customer_id: str = "", customer_email: str = "") -> dict:
        '''Create an order.

        Args:
            product: Product name or SKU.
            ...
        '''

Each spec produces two texts:
- llm_description(): short, what the model sees when the tool is bound.
- document(tool): rich text that is embedded in the semantic index used by retrieve_tools.

Prerequisites ("requires") are resolved two ways:
- the agent calls them: retrieve_tools adds the prerequisite tools to the agent's toolset (expand_requirements);
- optionally automatically: an "auto" rule runs the source tool when the parameter is missing.
"""
import functools
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool, StructuredTool

EFFECTS = ("read", "write")
MIN_EXAMPLES = 2

# name -> tool for every tool built with @tool_spec (AutoResolve looks sources up here)
SPEC_TOOLS: dict[str, BaseTool] = {}


@dataclass(frozen=True)
class AutoResolve:
    """Resolve a missing parameter by calling another tool.

    source: tool to call. args: {source_param: this_tool_param}. field: key of the source result to use."""

    source: str
    args: dict[str, str]
    field: str


@dataclass(frozen=True)
class ToolSpec:
    app: str
    resource: str
    action: str
    summary: str
    when_to_use: str
    when_not_to_use: str = ""
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    requires: dict[str, list[str]] = field(default_factory=dict)
    auto: dict[str, AutoResolve] = field(default_factory=dict)
    effect: str = "read"

    def _requirements_text(self) -> str:
        return " ".join(f"Requires {param}: get it first with {' or '.join(sources)}."
                        for param, sources in self.requires.items())

    def llm_description(self) -> str:
        parts = [self.summary, f"Use when: {self.when_to_use}"]
        if self.when_not_to_use:
            parts.append(f"Do not use: {self.when_not_to_use}")
        if self.requires:
            parts.append(self._requirements_text())
        return " ".join(parts)

    def document(self, tool: BaseTool) -> str:
        """Text embedded in the tool index (no API-call examples: they hurt retrieval)."""
        params = "; ".join(f"{name} ({p.get('description', p.get('type', ''))})" for name, p in tool.args.items())
        lines = [
            f"App: {self.app} | Resource: {self.resource} | Action: {self.action}",
            f"Tool: {tool.name.replace('_', ' ')} ({tool.name})",
            f"Summary: {self.summary}",
            f"When to use: {self.when_to_use}",
        ]
        if self.when_not_to_use:
            lines.append(f"When NOT to use: {self.when_not_to_use}")
        if params:
            lines.append(f"Parameters: {params}")
        if self.requires:
            lines.append(f"Prerequisites: {self._requirements_text()}")
        if self.tags:
            lines.append(f"Tags: {', '.join(self.tags)}")
        if self.examples:
            lines.append("Example requests: " + " | ".join(f'"{e}"' for e in self.examples))
        return "\n".join(lines)


def get_spec(tool: BaseTool) -> ToolSpec | None:
    return (tool.metadata or {}).get("spec")


def _with_prerequisites(fn: Callable, spec: ToolSpec) -> Callable:
    """Fill missing prerequisite parameters with their AutoResolve rule; if still missing, return a clear
    error telling the agent which tools provide them (instead of calling the function with empty values)."""

    @functools.wraps(fn)
    def run(**kwargs):
        for param, rule in spec.auto.items():
            if kwargs.get(param):
                continue
            source_args = {src: kwargs.get(own) for src, own in rule.args.items()}
            if not all(source_args.values()):
                continue  # nothing to resolve from: fall through to the requires check
            result = SPEC_TOOLS[rule.source].invoke(source_args)
            value = result.get(rule.field) if isinstance(result, dict) else None
            if not value:
                alternatives = [s for s in spec.requires.get(param, []) if s != rule.source]
                return {"error": f"Could not resolve {param} automatically with {rule.source}: {result}.",
                        "hint": f"Try {' or '.join(alternatives) or 'asking the user'} to get {param}."}
            kwargs[param] = value
        missing = [p for p in spec.requires if not kwargs.get(p)]
        if missing:
            return {"error": f"Missing required parameter(s): {', '.join(missing)}.",
                    "hint": spec._requirements_text()}
        return fn(**kwargs)

    return run


def tool_spec(*, app: str, resource: str, action: str, summary: str, when_to_use: str,
              when_not_to_use: str = "", tags=(), examples=(), requires: dict[str, list[str]] | None = None,
              auto: dict[str, AutoResolve] | None = None, effect: str = "read") -> Callable[[Callable], BaseTool]:
    """Decorator: turns a documented function into a registry tool with a validated ToolSpec."""
    spec = ToolSpec(app=app, resource=resource, action=action, summary=summary, when_to_use=when_to_use,
                    when_not_to_use=when_not_to_use, tags=tuple(tags), examples=tuple(examples),
                    requires=dict(requires or {}), auto=dict(auto or {}), effect=effect)

    def decorate(fn: Callable) -> BaseTool:
        func = _with_prerequisites(fn, spec) if (spec.requires or spec.auto) else fn
        tool = StructuredTool.from_function(func=func, name=fn.__name__, description=spec.llm_description(),
                                            parse_docstring=True, metadata={"spec": spec})
        SPEC_TOOLS[tool.name] = tool
        return tool

    return decorate


def validate_registry(registry: dict[str, BaseTool]) -> None:
    """Fail fast (at startup) with every problem found in the spec'd tools of the registry."""
    problems = []
    for name, tool in registry.items():
        spec = get_spec(tool)
        if spec is None:
            continue
        if not name.startswith(f"{spec.app}_"):
            problems.append(f"{name}: name must start with the app prefix '{spec.app}_'")
        for attr in ("app", "resource", "action", "summary", "when_to_use"):
            if not getattr(spec, attr).strip():
                problems.append(f"{name}: '{attr}' must not be empty")
        if len(spec.examples) < MIN_EXAMPLES:
            problems.append(f"{name}: needs at least {MIN_EXAMPLES} example requests")
        if spec.effect not in EFFECTS:
            problems.append(f"{name}: effect must be one of {EFFECTS}")
        params = set(tool.args)
        for param, sources in spec.requires.items():
            if param not in params:
                problems.append(f"{name}: requires unknown parameter '{param}'")
            problems += [f"{name}: prerequisite '{s}' is not in the registry" for s in sources if s not in registry]
        for param, rule in spec.auto.items():
            if param not in params:
                problems.append(f"{name}: auto rule for unknown parameter '{param}'")
            if rule.source not in registry:
                problems.append(f"{name}: auto source '{rule.source}' is not in the registry")
                continue
            source_params = set(registry[rule.source].args)
            for src, own in rule.args.items():
                if src not in source_params:
                    problems.append(f"{name}: auto source '{rule.source}' has no parameter '{src}'")
                if own not in params:
                    problems.append(f"{name}: auto rule uses unknown parameter '{own}'")
    if problems:
        raise ValueError("Invalid tool registry:\n- " + "\n- ".join(problems))


def expand_requirements(tool_ids: list[str], registry: dict[str, BaseTool], depth: int = 2) -> list[str]:
    """Add the prerequisite tools of the retrieved ones (transitively, up to `depth` levels), keeping order."""
    out, frontier = list(dict.fromkeys(tool_ids)), list(tool_ids)
    for _ in range(depth):
        nxt = []
        for tid in frontier:
            spec = get_spec(registry[tid]) if tid in registry else None
            for sources in (spec.requires.values() if spec else []):
                nxt += [s for s in sources if s not in out and s in registry]
        if not nxt:
            break
        out += list(dict.fromkeys(nxt))
        frontier = nxt
    return out
