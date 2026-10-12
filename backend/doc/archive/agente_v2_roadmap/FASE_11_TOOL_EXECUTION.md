# Phase 11 — Tool Execution

**Estado:** ❌ No implementada en v2 (v1 lo tenía)

---

## Qué hace

Shifu puede invocar herramientas reales: leer emails, crear eventos en calendario, escribir en Notion, enviar Slack messages, etc. Procesa los resultados, los incorpora a la conversación, y puede encadenar múltiples herramientas en secuencia para completar un objetivo.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Tool Routing | ❌ | Decidir qué herramienta invocar para el step actual del plan | Logs: `[tool_executor] tool=gmail.read_emails` |
| Tool Invocation | ❌ | Llamar a la herramienta con los parámetros correctos | La herramienta ejecuta y devuelve resultado |
| Tool Result Processing | ❌ | Interpretar el resultado y continuar la conversación | Shifu narra lo que encontró/hizo en lenguaje natural |
| Tool Loops | ❌ | Reintentar si falla, paginar si hay muchos resultados | Logs: `[tool_executor] retry=1` |
| Multi-Tool Coordination | ❌ | Usar 2+ herramientas en un mismo flujo | "Leí el email → lo guardé en Notion → te notifiqué por Slack" |

---

## Cómo lo tenía v1

- Tool binding directo al LLM (LangChain `bind_tools`)
- `tool_executor_node` en el graph — procesaba ToolCall + ToolMessage
- Loop: `chat → tool_executor → chat` hasta que el LLM dejaba de llamar herramientas
- El LLM decidía qué herramienta usar basándose en los tools disponibles
- Resultados de herramientas se agregaban como `ToolMessage` al historial

---

## Implementación propuesta

### Nodo: `tool_executor`

Loop en el graph:
```
chat → tool_executor → chat  (loop hasta que LLM no llama más tools)
```

En LangGraph esto se implementa con un conditional edge:
```python
def should_continue(state):
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tool_executor"
    return END
```

### Cómo se pasan las herramientas al LLM

```python
# En chat_node, antes de llamar al LLM:
tools = state.get("available_tools") or []
if tools:
    llm = llm.bind_tools(tools)
```

### Herramientas disponibles (ejemplo de estructura)

```python
@tool
def gmail_read_emails(query: str, max_results: int = 10) -> list[dict]:
    """Read emails from Gmail matching a query."""
    ...

@tool
def notion_create_page(title: str, content: str, database_id: str) -> dict:
    """Create a new page in a Notion database."""
    ...
```

### Estado agregado

```python
state.available_tools: Optional[list]   # herramientas disponibles este turno
state.tool_call_count: Optional[int]    # para límite de loops
```

---

## Cómo verificarlo en la interfaz de debug

1. Decir: "léeme los últimos 5 emails de mi Gmail"
2. Shifu debe invocar la herramienta, esperar el resultado, y narrar los emails
3. Logs: `[tool_executor] tool=gmail_read_emails args={query: "...", max_results: 5} result_len=5`
4. El historial debe mostrar: `AIMessage (tool_call)` → `ToolMessage (result)` → `AIMessage (respuesta)`
5. Flujo multi-tool: "léeme los emails nuevos y crea una tarea en Notion por cada uno"

---

## Manejo de errores

| Error | Comportamiento esperado |
|-------|------------------------|
| Cuenta no conectada | Shifu informa y pide conectar desde Settings |
| Token expirado | Shifu pide re-autorizar |
| API externa falla | Shifu informa el error y sugiere reintentar |
| Loop infinito | Límite de 5 tool calls por turno, luego Shifu para y reporta |

---

## Dependencias

- Requiere Phase 10 ❌ (Tool Awareness — para saber qué herramientas están disponibles y conectadas)
- Requiere Phase 8 ❌ (Intent — para saber cuándo usar una herramienta vs solo conversar)
- Se beneficia de Phase 9 ❌ (Planning — para saber en qué step del plan está)

---

## Prioridad sugerida

Muy alta a largo plazo — es el core del producto. Pero requiere Phase 8, 9 y 10 primero. La implementación sin esas bases genera un agente que invoca herramientas sin entender bien cuándo y por qué.
