# Phase 6 — User Understanding

**Estado:** ✅ Completa — Cognitive Profile pendiente (depende de Fase 7)

---

## Qué hace

Shifu conoce al usuario: su nombre, idioma, rol, empresa, preferencias de comunicación, y cualquier dato que el usuario haya declarado explícitamente. Este perfil crece con cada conversación y persiste en MongoDB. Se carga al inicio de cada turno y se actualiza al final.

---

## Objetivos implementados

| Objetivo | Estado | Descripción |
|----------|--------|-------------|
| User Profile | ✅ | 12 campos en `user_preferences`; 7 sembrados automáticamente desde datos de registro |
| User Preferences | ✅ | Keys fuera de whitelist → `user_semantic_memory` (schema abierto, sin límite de dimensiones) |
| Communication Preferences | ✅ | `user_language` — aplica siempre sin conflicto, persiste entre sesiones |
| User Interests | ✅ | Resuelto por Semantic Memory — intereses, tools, estilos de trabajo persisten automáticamente |
| Interaction Patterns | ❌ | Cognitive profile (patrones de razonamiento, estilo, expertise) — pendiente Fase 7 |

---

## Cómo verificarlo en la interfaz de debug

### Perfil base (semilla de registro)
1. Usuario nuevo → primera conversación → Shifu ya sabe el nombre sin haberlo preguntado
2. En logs buscar: `[user_context_loader] user=X profile_keys=7` — debe mostrar 7 claves desde el primer turno

### Preferencias dinámicas
1. Decir: "mi empresa se llama HyperShifu" → Shifu responde confirmando en una frase
2. Abrir nueva conversación → Shifu debe usar el nombre de la empresa naturalmente
3. En MongoDB buscar `user_preferences` → debe aparecer `user_company: {value: "HyperShifu"}`

### Idioma
1. Decir: "responde en inglés de ahora en adelante"
2. Shifu confirma: "Got it, I'll respond in English."
3. Cerrar y abrir nueva conversación → Shifu responde en inglés desde el primer mensaje
4. En logs: `[user_profile_updater] language updated ... 'Spanish' → 'English'`

---

## Nodos responsables

**Carga:** `user_context_loader` — [nodes/context/user_context_loader.py](../nodes/context/user_context_loader.py)
- Lee `user_preferences` de MongoDB
- Siembra 7 campos de registro en el primer turno (idempotente)
- Retorna `state.user_profile`

**Actualización:** `user_profile_updater` — [nodes/memory/user_profile_updater.py](../nodes/memory/user_profile_updater.py)
- Corre DESPUÉS del chat
- Extrae declaraciones explícitas del último intercambio Human+AI
- 3 casos: nuevo → guarda, igual → no-op, diferente → conflicto (excepto `user_language` que siempre aplica)
- Modelo: `gpt-4.1-nano` (T=0, max_tokens=200)

**Inyección:** `chat_node` — `build_profile_block()` + `build_semantic_memory_block()` — ambos bloques en el SystemMessage cada turno

---

## Campos sembrados automáticamente (registro)

| Clave | Fuente en `users` collection |
|-------|------------------------------|
| `user_name` | `nombre` + `apellido` |
| `user_first_name` | `nombre` |
| `user_last_name` | `apellido` |
| `user_email` | `correo` |
| `user_platform_role` | `rol` |
| `user_plan` | `plan` |
| `user_language` | `"Spanish"` (default) |

---

## Manejo de conflictos

Si el usuario dice algo que contradice lo que está guardado (ej: antes dijo "soy CEO" y ahora dice "soy CTO"), se marca `needs_confirmation: true` en la DB. Shifu pregunta naturalmente para confirmar antes de actualizar.

**Excepción:** `user_language` siempre se aplica inmediatamente — nunca genera conflicto.

**Roles:** `user_roles` es un array — múltiples roles coexisten (`$addToSet`). Nunca genera conflicto.

---

## Semantic Memory — extensión de User Understanding

Keys detectadas por el LLM que no están en la whitelist de 12 campos van a `user_semantic_memory`:

| Ejemplos de hechos capturados | Colección |
|---|---|
| `preferred_framework: "LangGraph"` | `user_semantic_memory` |
| `work_style: "async-first"` | `user_semantic_memory` |
| `industry: "SaaS B2B"` | `user_semantic_memory` |
| `user_goal: "automate customer support"` | `user_semantic_memory` |

Schema: `{user_id, key, value, confidence, mention_count, first_seen_at, last_seen_at, source}`

Ordenados por `mention_count DESC, last_seen_at DESC` — top-20 inyectados en cada turno.

---

## Lo pendiente para completar la fase

### Cognitive Profile (v1 lo tenía)
- Patrones de razonamiento del usuario (directo, estructurado, exploratorio)
- Áreas de expertise detectadas
- Objetivos a largo plazo
- Patrones emocionales recurrentes
- Implementación: síntesis periódica cada 7 días o 15 episodios nuevos
- Dependencia: requiere Phase 7 (Long-Term Memory) funcionando primero

### Adaptación dinámica de estilo de respuesta (movido desde Fase 4)
- Detectar preferencias estables del usuario: longitud de respuesta preferida (corta/larga), nivel de detalle, uso de listas vs párrafos
- Ajustar automáticamente entre sesiones sin que el usuario tenga que repetirlo
- Almacenar en `user_cognitive_profile` o extender `user_semantic_memory` con claves de estilo (`preferred_response_length`, `preferred_format`, etc.)
- Dependencia: `user_cognitive_profile` — requiere suficiente historial para inferir patrones (mínimo 5-10 conversaciones)
