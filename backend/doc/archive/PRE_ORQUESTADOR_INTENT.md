# Pre-Orquestador de Intención — Diseño de Arquitectura

**Objetivo:** Hacer Shifu resistente a prompts vagos de usuarios no técnicos.  
Antes de que el agente principal procese cualquier mensaje, un nodo ligero y rápido
analiza la intención, extrae entidades clave y enriquece el prompt — o hace
**una sola pregunta de clarificación** si el mensaje es demasiado ambiguo.

---

## Problema que resuelve

| Prompt del usuario | Problema | Sin pre-orquestador | Con pre-orquestador |
|---|---|---|---|
| "quiero que me avise del dólar" | Vago, sin canal ni frecuencia | Shifu pregunta varias veces | Una pregunta: "¿Por correo o WhatsApp?" |
| "ya no quiero ese flujo" | ¿Cuál flujo? | Shifu lista todos y pregunta | Detecta intent=editar, lista flujos automáticamente |
| "actualiza el de gmail" | Sin contexto de qué actualizar | Confusión de pasos | Carga el workflow de Gmail antes de preguntar |
| "ponlo a las 3" | Sin referencia clara | Fallo o respuesta incorrecta | Detecta intent=editar_horario, vincula con último workflow mencionado |

---

## Flujo General

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUARIO                                  │
│   "quiero que me avise cuando suba el dólar"                    │
└─────────────────────────┬───────────────────────────────────────┘
                          │ mensaje crudo
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  intent_analyzer_node                           │
│                                                                 │
│  Modelo: GPT-4o-mini (rápido y barato)                          │
│  Output estructurado (JSON):                                    │
│    intent_type:    "crear_workflow"                             │
│    confidence:     0.82                                         │
│    entities:                                                    │
│      trigger:      "cambio de precio"                           │
│      app:          ["busqueda_web", "email"]                    │
│      topic:        "dólar quetzal"                              │
│    missing_info:   ["canal_notificacion", "frecuencia"]         │
│    enriched_prompt: "Crear workflow que monitoree el tipo de    │
│                      cambio USD/GTQ y notifique al usuario..."  │
│    clarification:  "¿Cada cuánto quieres el aviso — una vez al │
│                     día o en tiempo real?"                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   confidence >= 0.6?  │
              └───────────┬───────────┘
                    NO ◄──┤──► SÍ
                    │              │
                    ▼              ▼
          ┌──────────────┐  ┌──────────────────────────────────┐
          │  Devolver    │  │  context_loader_node             │
          │  clarification  │  (recibe enriched_prompt +        │
          │  al usuario  │  │   intent_type como hint)         │
          └──────┬───────┘  └──────────────┬───────────────────┘
                 │                         │
                 │ usuario responde         ▼
                 │                  ┌──────────────────┐
                 └─────────────────►│  agent_node      │
                                    │  (V3 ó Bigtool)  │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  tool_executor   │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  memory_saver    │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                           END
```

---

## Tipos de Intención

| intent_type | Descripción | Acción del enriquecedor |
|---|---|---|
| `crear_workflow` | Usuario quiere automatizar algo nuevo | Infiere apps, trigger, pasos probables |
| `editar_workflow` | Usuario quiere modificar un flujo existente | Sugiere cargar `listar_mis_workflows` primero |
| `ejecutar_workflow` | Usuario quiere correr un flujo ya creado | Identifica el workflow por nombre/descripción |
| `eliminar_workflow` | Usuario quiere borrar o pausar un flujo | Añade confirmación explícita al prompt |
| `consultar_estado` | Usuario pregunta qué flujos tiene o cómo van | Dirige a `listar_mis_workflows` |
| `pregunta_capacidad` | "¿Puedes hacer X?" — pregunta sobre funciones | Responde directamente sin crear nada |
| `unclear` | No se puede inferir ninguna intención | Hace la pregunta de clarificación |

---

## Reglas de Confianza

```
confidence >= 0.75  →  Enriquecer y pasar al agente sin preguntar
confidence 0.50–0.74 →  Enriquecer pero añadir contexto de incertidumbre al hint
confidence < 0.50   →  Devolver clarification_question al usuario (NO al agente)
```

**La pregunta de clarificación siempre es UNA sola**, concisa, con opciones cuando
sea posible:
> "¿Quieres que te avise por correo, por WhatsApp o en la app?"

---

## Entidades que Extrae

```json
{
  "intent_type": "crear_workflow",
  "confidence": 0.82,
  "entities": {
    "trigger":     "cambio de precio / una vez al día / cuando suba",
    "apps":        ["tavily", "gmail", "google_sheets"],
    "topic":       "tipo de cambio dólar quetzal",
    "target_data": "precio / valor / tasa",
    "destination": "correo / hoja de cálculo"
  },
  "missing_info":      ["frecuencia", "umbral_de_alerta"],
  "enriched_prompt":   "Crear un workflow llamado 'Monitor Dólar-Quetzal' que ...",
  "clarification":     "¿Cada cuánto quieres el aviso — una vez al día o en tiempo real?"
}
```

---

## Integración con el Grafo Existente

### Estado — campos nuevos en `ShifuState`

```python
class ShifuState(TypedDict):
    # ... campos existentes ...
    intent_analysis: dict          # salida completa del pre-orquestador
    enriched_message: str | None   # prompt enriquecido (reemplaza al crudo en context_loader)
    needs_clarification: bool      # True → devolver al usuario sin pasar al agente
    clarification_question: str | None
```

### Nodo nuevo — `intent_analyzer_node`

```python
async def intent_analyzer_node(state: ShifuState, config: RunnableConfig) -> dict:
    """
    Análisis rápido de intención con GPT-4o-mini.
    Costo estimado: ~0.002 USD por llamada (prompt pequeño + output JSON corto).
    Latencia: ~300–600 ms.
    """
    last_user_msg = _get_last_user_message(state["messages"])

    analysis = await _call_intent_llm(last_user_msg, state.get("user_context"))

    if analysis["confidence"] < 0.50:
        return {
            "intent_analysis": analysis,
            "needs_clarification": True,
            "clarification_question": analysis["clarification"],
        }

    return {
        "intent_analysis": analysis,
        "enriched_message": analysis.get("enriched_prompt"),
        "needs_clarification": False,
    }
```

### Grafo modificado

```
START
  │
  ▼
intent_analyzer_node          ← NUEVO
  │
  ├─ needs_clarification=True ──► clarification_responder ──► END
  │                                (devuelve la pregunta al usuario)
  │
  └─ needs_clarification=False ─► context_loader_node
                                       │
                                       ▼
                                   agent_node
                                       │
                                       ▼
                                   tool_executor
                                       │
                                       ▼
                                   memory_saver
                                       │
                                       ▼
                                      END
```

---

## Prompt del Pre-Orquestador (GPT-4o-mini)

```
Eres un clasificador de intenciones para un asistente de automatización.
El usuario puede ser no técnico. Analiza su mensaje y responde SOLO JSON.

Intenciones posibles:
- crear_workflow
- editar_workflow
- ejecutar_workflow
- eliminar_workflow
- consultar_estado
- pregunta_capacidad
- unclear

Apps disponibles: email, whatsapp, google_sheets, google_calendar, 
                  tavily (búsqueda web), ai_extract, slack, jira, ...

Mensaje del usuario: "{mensaje}"
Historial reciente: {ultimos_3_turnos}

Responde con este JSON exacto:
{
  "intent_type": "...",
  "confidence": 0.0-1.0,
  "entities": {
    "trigger": "...",
    "apps": [...],
    "topic": "...",
    "destination": "..."
  },
  "missing_info": [...],
  "enriched_prompt": "versión clara y técnica del pedido del usuario",
  "clarification": "UNA sola pregunta corta si falta info crítica, sino null"
}
```

---

## Ejemplos de Enriquecimiento

### Ejemplo 1 — Vago pero inferible

| | Texto |
|---|---|
| **Original** | "quiero que me avise del dólar" |
| **Enriched** | "Crear un workflow que busque el tipo de cambio USD/GTQ con Tavily una vez al día, extraiga el valor numérico con AI y me envíe un correo con el resultado" |
| **Confidence** | 0.71 |
| **Clarification** | null (confianza suficiente, se enriquece y pasa al agente) |

### Ejemplo 2 — Demasiado vago

| | Texto |
|---|---|
| **Original** | "ponlo a las 3" |
| **Enriched** | null |
| **Confidence** | 0.28 |
| **Clarification** | "¿Qué workflow quieres programar a las 3? ¿Es de mañana o de tarde?" |

### Ejemplo 3 — Edición sin ID

| | Texto |
|---|---|
| **Original** | "ya no quiero ese flujo de gmail" |
| **Enriched** | "El usuario quiere eliminar o desactivar el workflow relacionado con Gmail. Primero llama a listar_mis_workflows para identificarlo y muéstraselo antes de eliminar" |
| **Confidence** | 0.78 |
| **Clarification** | null |

---

## Plan de Implementación

### Fase 1 — MVP (1–2 días)

- [ ] Agregar `intent_analysis`, `enriched_message`, `needs_clarification`, `clarification_question` a `ShifuState`
- [ ] Implementar `intent_analyzer_node` en `app/agents/shifu_v3/intent_analyzer.py`
- [ ] Agregar `clarification_responder_node` (nodo simple que formatea y devuelve la pregunta)
- [ ] Conectar al grafo V3 en `graph.py` con edge condicional
- [ ] Modificar `context_loader_node` para usar `enriched_message` si existe

### Fase 2 — Refinamiento (2–3 días)

- [ ] Afinar el prompt del clasificador con ejemplos reales de usuarios
- [ ] Añadir memoria de corto plazo: el clasificador lee los últimos 3 turnos para resolver referencias anafóricas ("ese flujo", "ponlo")
- [ ] Logging de confianza y tipo de intención para poder medir y mejorar

### Fase 3 — Mejoras opcionales

- [ ] Panel en el frontend de debug que muestre el `intent_analysis` por turno
- [ ] Feedback loop: si el agente falla, bajar el umbral de confianza para ese tipo de prompt

---

## Costo Estimado

| Componente | Modelo | Tokens aprox. | Costo por llamada |
|---|---|---|---|
| Intent Analyzer | GPT-4o-mini | ~400 in + 150 out | ~$0.00009 |
| Agente principal | GPT-4o | ~8000 in + 500 out | ~$0.045 |
| **Total por turno** | | | **~$0.045** (impacto mínimo) |

---

## Archivos a Crear/Modificar

```
app/agents/shifu_v3/
├── intent_analyzer.py      ← NUEVO  (nodo + prompt del clasificador)
├── nodes.py                ← MODIF  (context_loader usa enriched_message)
├── state.py                ← MODIF  (4 campos nuevos en ShifuState)
└── graph.py                ← MODIF  (nodo + edge condicional al inicio)
```
