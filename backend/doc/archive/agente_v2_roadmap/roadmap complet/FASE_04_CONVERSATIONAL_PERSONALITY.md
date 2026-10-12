# Phase 4 — Conversational Personality

**Estado:** ✅ Completa

---

## Qué hace

Define el estilo, tono y comportamiento de Shifu como agente, más allá de solo responder correctamente.

En el flujo actual:
- `identity_loader` carga `agent_personality` desde DB.
- `chat` construye el bloque de identidad/personality y lo inyecta en el SystemMessage del turno.
- `get_temperature()` ajusta temperatura por `conversation_stage`.

Incluye consistencia de tono, reglas de qué no decir, iniciativa contextual y patrones de interacción.
La adaptación dinámica por usuario se mantiene fuera del alcance de esta fase (Phase 6).

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Communication Style | ✅ | Tono base definido en DB (`tono_base`) + policy de comportamiento por stage | Logs `[AgenteV2/personality]` muestran patrón aplicado |
| Tone Consistency | ✅ | El tono no cambia entre mensajes ni entre turnos | Pedir respuestas en distintos contextos — el tono base es el mismo |
| Initiative | ✅ | Propone 1 siguiente paso concreto cuando hay acción pendiente en `requirements/planning/execution` | Log `initiative_applied=True` |
| Interaction Patterns | ✅ | Selección de formato/detalle/preguntas por stage y complejidad del turno | Log `interaction_pattern=...` |
| Behavioral Rules | ✅ | `prohibiciones_lexicas`, reglas de qué nunca decir | Intentar hacer decir a Shifu algo prohibido — debe rechazarlo |

---

## Lo que está implementado hoy

**En DB (`agent_personality` collection):**
- `tono_base` — descripción del tono general
- `reglas_comunicacion.prohibiciones_lexicas` — lista de términos que Shifu no puede usar
- `reglas_comunicacion` — reglas de estilo de comunicación
- `interaction_patterns` — reglas por stage + overrides por complejidad

**En DB (`agent_goals` collection):**
- `initiative_rules` — habilitación de iniciativa, stages permitidos y límites

**En memoria de usuario (`_MEMORY_BEHAVIOR_RULES`):**
- Confirmar preferencias en una sola frase
- Nunca pedir al usuario que diga "guárdalo"
- Nunca decir "intentaré recordar"

**Temperatura dinámica por stage:**
- `execution` → T=0.2 (preciso)
- `planning` → T=0.55
- `idle` → T=0.8 (más natural)

---

## Cómo verificarlo en la interfaz de debug

1. Buscar en logs: `[AgenteV2/chat] model=... stage=... temperature=... identity_source=...`
	- `temperature` debe variar por etapa
	- `identity_source=db` confirma carga de personalidad desde DB
2. Buscar en logs: `[AgenteV2/personality] stage=... initiative_applied=... interaction_pattern=... complexity=...`
	- `initiative_applied=True` debe aparecer cuando hay acción pendiente en `requirements/planning/execution`
	- `interaction_pattern` debe cambiar entre turnos simples y complejos
3. Intentar hacer decir algo de la lista de prohibiciones → no debe aparecer en la respuesta
4. Hablar de algo casual (idle) vs dar instrucciones técnicas (execution) → el tono y formato deben sentirse diferentes

---

## Lo pendiente para completar la fase

Ninguno — fase completamente implementada.

> La adaptación dinámica de estilo de respuesta por usuario fue movida a **Phase 6 (User Understanding)**,
> donde pertenece junto al Cognitive Profile. Ver [FASE_06_USER_UNDERSTANDING.md](../../FASE_06_USER_UNDERSTANDING.md).

---

## Nodo responsable

`identity_loader` (carga personality doc) + `chat` (aplica al construir el identity block)

Se ejecuta dentro de `context_subgraph` antes de `chat`.

[nodes/context/identity_loader.py](../nodes/context/identity_loader.py) | [nodes/core/chat.py](../nodes/core/chat.py)
