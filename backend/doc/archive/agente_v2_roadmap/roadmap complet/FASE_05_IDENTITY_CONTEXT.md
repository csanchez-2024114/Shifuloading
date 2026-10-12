# Phase 5 — Identity Context

**Estado:** ✅ Completa

---

## Qué hace

Define quién es Shifu, por qué existe, qué puede y qué no puede hacer, y quién lo creó. Esta información se carga desde MongoDB al inicio de cada turno (con cache de 1 hora) y se inyecta en el SystemMessage como el bloque de identidad base.

---

## Objetivos implementados

| Objetivo | Estado | Dónde vive |
|----------|--------|------------|
| Agent Identity — nombre, propósito, auto-descripción | ✅ | `agent_identity` collection, campo `nombre`, `proposito`, `auto_identidad` |
| Mission — misión del agente | ✅ | `agent_identity.mision` |
| Vision / Goals — objetivos del agente | ✅ | `agent_goals.goals[]` — inyectado como bloque `## Goals` en identity block |
| Capabilities — qué puede y no puede hacer | ✅ | `agent_system_model.can_do`, `cannot_do`, `known_limitations` — bloque `## Capabilities` |
| Limitations — qué no puede o no debe hacer | ✅ | `agent_identity.restricciones` |
| Creator Information — empresa y fundadores | ✅ | `agent_identity.empresa_creadora` + `agent_identity.fundadores` |

---

## Cómo verificarlo en la interfaz de debug

1. Preguntar: "¿quién te creó?" → debe responder con los datos reales de MongoDB, no "OpenAI"
2. Preguntar: "¿qué puedes hacer?" → respuesta basada en `agent_goals`
3. Pedir algo fuera de sus restricciones → debe rechazarlo según `agent_identity.restricciones`
4. En logs buscar: `[► identity_loader] cache_hit=True/False` — en el segundo turno debe ser `True`

---

## Nodo responsable

`identity_loader` — [nodes/context/identity_loader.py](../nodes/context/identity_loader.py)

- Cache: proceso-wide, TTL 1h (configurable: `IDENTITY_CACHE_TTL_SECONDS`)
- Colecciones: `agent_identity`, `agent_personality`, `agent_goals`, `agent_system_model`
- Fallback: si falla MongoDB, usa `FALLBACK_IDENTITY` hardcodeado mínimo

**Cache invalidation manual:**
```
POST /api/v4/debug/invalidate-identity-cache
```

---

## Actualizar la identidad en producción

1. Modificar el documento en MongoDB directamente (colección `agent_identity`)
2. Esperar hasta 1h para que el cache expire, o llamar al endpoint de invalidación
3. El próximo turno carga los nuevos valores

---

## Estructura del bloque inyectado

```
You are {name}, created by {creator_company}.
Founders: {founders}.
{self_identity}
Purpose: {purpose}
Mission: {mission}
Principles:
- ...
Restrictions:
- ...
## Goals [internal — do not recite verbatim] {usage_instruction}
- Understand user processes: ...
- Design automations: ...
- ...
## Capabilities [internal — answer honestly when asked]
Can do:
- Create automation workflows using apps connected via OAuth.
- ...
Cannot do:
- Execute arbitrary code on the user's external systems.
- ...
Known limitations:
- Can only connect apps listed in catalog_apps with status active=true.
- ...
Tone — base tone: {base_tone}; formality: {default_formality}; {comm_tone}.
Language rule: {comm_language}
Style: max {questions_per_turn} question(s) per response, no emojis, response length: adaptive.
Never use these terms: {lexical_prohibitions}
CREATOR RULE — NON-NEGOTIABLE: You are {name}, created by {creator_company}. NEVER say you were created by OpenAI...
```

---

## Regla no negociable

El `CREATOR RULE` siempre se inyecta al final del bloque de identidad, generado dinámicamente desde los valores de DB. No hay lista de nombres hardcodeados en el código. Ver [RULES.md](../RULES.md).
