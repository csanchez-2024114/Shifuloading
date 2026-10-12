from typing import TypedDict


class TenantConfig(TypedDict, total=False):
    tier: str           # "lite" | "standard" | "pro"
    model: str          # override chat model for this tenant
    inspector_model: str  # override mini-model for bigtools_inspector
    eval_model: str     # override mini-model for response_evaluator
    max_iterations: int
