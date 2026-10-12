"""
Node label registry for agent status streaming.

get_node_label(name) returns a user-facing Spanish label for a graph node.
Known nodes → curated label from _LABELS.
Unknown nodes → auto-derived from the last recognizable word in the snake_case name.
Internal LangChain chains (no recognized role word) → None → silently ignored.
"""

_LABELS: dict[str, str] = {
    "goal_resolver":      "Cargando objetivo...",
    "memory_retriever":   "Recuperando memoria...",
    "semantic_intake":    "Analizando tu solicitud...",
    "catalog_checker":    "Verificando apps disponibles...",
    "auth_validator":     "Verificando autorizaciones...",
    "document_analyzer":  "Leyendo tus documentos...",
    "tavily_searcher":    "Buscando en la web...",
    "research_curator":   "Procesando resultados...",
    "research_analyst":   "Analizando las fuentes...",
    "bigtools_inspector": "Identificando herramientas...",
    "req_investigator":   "Diseñando tu workflow...",
    "workflow_planner":   "Planificando flujo de trabajo...",
    "action_runner":      "Consultando tus apps...",
    "workflow_manager":   "Revisando tus workflows...",
    "responder":          "Generando respuesta...",
    "response_evaluator": "Evaluando calidad...",
    "memory_updater":     "Guardando en memoria...",
}

_VERB_MAP: dict[str, str] = {
    "resolver":   "Resolviendo",
    "retriever":  "Recuperando",
    "intake":     "Analizando",
    "checker":    "Verificando",
    "validator":  "Validando",
    "searcher":   "Buscando",
    "curator":    "Procesando",
    "inspector":  "Inspeccionando",
    "responder":  "Generando respuesta",
    "evaluator":  "Evaluando",
    "updater":    "Actualizando",
    "handler":    "Procesando",
    "subgraph":   "Ejecutando",
}


def get_node_label(node_name: str) -> str | None:
    if not node_name:
        return None
    if node_name in _LABELS:
        return _LABELS[node_name]
    for word in reversed(node_name.split("_")):
        if word in _VERB_MAP:
            return f"{_VERB_MAP[word]}..."
    return None
