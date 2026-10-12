# Phase 8 — Intent & Understanding Reconstruction

**Estado:** ✅ Completa

---

## Qué hace

Antes de responder, Shifu reconstruye una comprensión estructurada de lo que el usuario realmente quiere: qué objetivo tiene, qué acción está pidiendo, qué información falta, y qué tan seguro está Shifu de haber entendido correctamente.

Esta fase es la base para que Phase 9 (Planning) y Phase 11 (Tool Execution) funcionen bien — sin intent claro, no se puede planificar ni ejecutar.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| User Goal Extraction | ✅ | ¿Qué quiere lograr el usuario a nivel alto? | Log `[intent_reconstructor]` muestra `user_goal` |
| Requested Action Detection | ✅ | ¿Qué acción concreta está pidiendo en este turno? | Campo `requested_action` en el log |
| Missing Information Detection | ✅ | ¿Qué le falta saber para poder ayudar? | `missing_info=N` en el log |
| Confidence Scoring | ✅ | ¿Qué tan seguro está Shifu de haber entendido? | Log `confidence=0.XX` por turno |
| Structured Understanding Context | ✅ | JSON estructurado inyectado como bloque en el SystemMessage | `intent(conf=X,ambig=False)` en `[AgenteV2/context_blocks]` |

---

## Lo que está implementado

**Nodo: `intent_reconstructor`**

Posición en graph:
```
app_catalog_validator → intent_reconstructor → chat
```

**Qué hace:**
1. Toma el último mensaje del usuario + `working_memory_context` + `conversation_context`
2. LLM (`gpt-4o-mini`, T=0, max_tokens=300) produce JSON estructurado:

```json
{
  "user_goal":            "string — objetivo a nivel alto",
  "requested_action":     "string — qué está pidiendo ahora",
  "missing_info":         ["lista de qué falta para poder ayudar"],
  "confidence":           0.0,
  "ambiguous":            false,
  "clarification_needed": "pregunta específica | null"
}
```

3. Si `confidence < 0.6` o `ambiguous: true` → el bloque instruye a Shifu a pedir la aclaración exacta indicada en `clarification_needed`
4. Si `missing_info` tiene items → Shifu pregunta exactamente eso como parte de la respuesta
5. El JSON se convierte en un bloque `## Intent Context [internal]` y se inyecta en el SystemMessage antes de `conv_context` y `working_memory`

**Short-circuits (no se ejecuta):**
- Primer turno (sin AI reply previo)
- Stage `idle` o `completed` — mensajes de saludo o tarea terminada
- Sin mensaje de usuario en el estado

**Estado en graph:**
```python
state.intent_context: Optional[dict]  # {"user_goal", "requested_action", "missing_info", "confidence", "ambiguous", "clarification_needed"}
```

**Variable de entorno:**
```
AGENTE_V2_INTENT_MODEL=gpt-4o-mini   # modelo para la llamada de intent
```

---

## Cómo verificarlo

1. **Mensaje ambiguo:** "ayúdame con eso" → log muestra `ambiguous=True confidence=0.3X`, Shifu pide aclaración específica
2. **Mensaje claro:** "quiero crear un workflow que envíe email cuando llegue un nuevo lead" → log muestra `confidence=0.9X missing_info=2`
3. **Mensaje incompleto:** "conéctame Gmail" → `missing_info=["which Gmail account"]`, Shifu pregunta antes de conectar
4. **Logs a buscar:**
   ```
   [intent_reconstructor] stage=execution confidence=0.85 ambiguous=False missing_info=1 clarification=no
   [AgenteV2/context_blocks] active=[..., intent(conf=0.85,ambig=False), ...]
   ```

---

## Archivos

| Archivo | Rol |
|---------|-----|
| `nodes/core/intent_reconstructor.py` | Nodo — llama LLM, parsea JSON, escribe `intent_context` |
| `prompts/intent_reconstruction.py` | Prompt del LLM + `build_intent_block()` |
| `state.py` | Campo `intent_context: Optional[dict]` |
| `graph.py` | Edge `app_catalog_validator → intent_reconstructor → chat` |
| `nodes/core/chat.py` | Lee `intent_context`, llama `build_intent_block()`, agrega a `system_parts` |

---

## Dependencias

- Requiere Phase 1 ✅ (`conversation_stage` para short-circuit en idle/completed)
- Requiere Phase 2 ✅ (`working_memory_context` para contexto de entidades activas)
- No requiere DB nueva
