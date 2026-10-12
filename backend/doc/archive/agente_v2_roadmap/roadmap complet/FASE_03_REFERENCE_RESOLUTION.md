# Phase 3 — Conversational Reference Resolution

**Estado:** ✅ Implementada

---

## Qué hace

Permite que Shifu entienda referencias implícitas en el lenguaje del usuario: "eso", "lo de antes", "el que me dijiste", "esa app", "el flujo que creamos".

Antes del `chat`, el nodo `reference_resolver` analiza el último mensaje del usuario junto con:
- `conversation_context` (Phase 1)
- `working_memory_context` (Phase 2)

Si detecta referencias ambiguas con contexto suficiente, produce una versión enriquecida del último mensaje (`resolved_user_message`) para ese turno.

---

## Objetivos implementados

| Objetivo | Estado | Verificación en debug |
|----------|--------|-----------------------|
| Reference Resolution | ✅ | Log `[reference_resolver]` con `original=... resolved=...` |
| Implicit References | ✅ | Mensaje enriquecido en `resolved_user_message` en state |
| Context Linking | ✅ | Usa `working_memory_context` + `conversation_context` para resolver |
| Entity Resolution | ✅ | `resolved_references` reporta source → target |
| Pronoun Resolution | ✅ | `chat_node` aplica resolución al último HumanMessage del turno |

---

## Cómo está implementada

Se implementó la **Opción A — Enriquecimiento de mensaje**.

Antes del nodo `chat`, `reference_resolver` toma el último mensaje del usuario y lo reescribe con referencias explícitas cuando hay contexto suficiente.

El historial persistido no se modifica: la versión enriquecida solo se aplica al turno actual dentro de `chat_node`.

```
working_memory_builder → reference_resolver → chat
```

Flujo del subgrafo de contexto actual:

identity_loader → user_context_loader → long_term_memory_loader →
conversation_context_builder → working_memory_builder → reference_resolver

---

## Implementación actual

- Nodo: `reference_resolver` — [nodes/context/reference_resolver.py](../nodes/context/reference_resolver.py)
- Modelo: `gpt-4.1-nano` (T=0, max_tokens=150)
- Input: último mensaje del usuario + `conversation_context` + `working_memory_context`
- Output en state: `resolved_user_message` + `reference_resolution`
- No-op si no detecta referencia ambigua o no hay resolución confiable

---

## Verificación en debug

1. Decir: "quiero conectar Gmail" → siguiente turno: "configúralo con mi cuenta"
2. Shifu debe entender que "configúralo" = "Gmail" sin preguntar
3. Decir: "¿qué decidimos sobre eso?" → Shifu debe referirse a la última decisión tomada
4. Ver logs: `[reference_resolver] model=... refs=N original='...' resolved='...'`
5. Ver logs: `[AgenteV2/chat] applied_reference_resolution ...`

---

## Dependencias

- Requiere Phase 2 (Working Memory) para tener el inventario de entidades y decisiones activas ✅ ya disponible
- No requiere DB nueva

---

## Nodos responsables

- `reference_resolver` — [nodes/context/reference_resolver.py](../nodes/context/reference_resolver.py)
- `chat` — [nodes/core/chat.py](../nodes/core/chat.py) (aplica `resolved_user_message` al turno actual)
- `context_subgraph` — [context_subgraph.py](../context_subgraph.py)

---

## Prioridad

Completada.
