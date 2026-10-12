# Phase 10 — Tool Awareness

**Estado:** ✅ Implementada (2026-06-02)

---

## Qué hace

Shifu sabe qué herramientas existen en la plataforma, cuáles tiene disponibles el usuario (conectadas), y cuáles son relevantes para el contexto actual de la conversación. No ejecuta las herramientas todavía — solo las conoce y las menciona inteligentemente.

---

## Objetivos

| Objetivo | Estado | Descripción | Verificación en debug |
|----------|--------|-------------|----------------------|
| Tool Catalog Awareness | ✅ | Conocer el catálogo completo de apps e integraciones disponibles | Shifu puede decir "puedo conectarte con Gmail, Slack, Notion..." |
| Connected Apps Awareness | ✅ | Saber qué apps tiene conectadas el usuario (multi-cuenta) | Shifu dice "tienes Gmail conectado con alaneduardo@..." |
| Tool Discovery | ✅ | Sugerir herramientas relevantes para el objetivo del usuario | Shifu guía al usuario a conectar la app necesaria |
| OAuth Connection Guidance | ✅ | Nunca pedir credenciales — dirigir al botón Connect en la UI | Shifu dice "usa el botón Connect Gmail en la plataforma" |
| Capability Awareness | ❌ | Saber qué puede hacer con cada herramienta (triggers, acciones) | Pendiente Fase 11 |
| Tool Selection Context | ❌ | En un plan, seleccionar la herramienta correcta para cada paso | Pendiente Fase 11 |
| Tool Usage History | ❌ | Recordar qué herramientas el usuario ya usó y cómo | Pendiente Long-Term Memory integration |

---

## Cómo lo tenía v1

- `catalog_apps` collection — catálogo completo de apps disponibles
- `user_connected_accounts` collection — qué cuentas tiene conectadas el usuario
- Ambas se cargaban en `context_loader` y se inyectaban como SystemMessage
- El agente sabía si Gmail estaba conectado o no antes de intentar usarlo
- Si una cuenta no estaba conectada → Shifu pedía al usuario que la conectara primero

---

## Implementación propuesta

**Colecciones existentes a reutilizar:**
- `catalog_apps` — ya existe en la DB
- `user_connected_accounts` — ya existe en la DB

**Nuevo nodo: `tool_context_loader`**

Posición en graph:
```
long_term_memory_loader → tool_context_loader → conversation_context_builder
```

**Qué hace:**
1. Lee `catalog_apps` (global, cacheable)
2. Lee `user_connected_accounts` para el usuario actual
3. Filtra: solo apps relevantes al topic de la conversación (para no inyectar 50 apps cuando solo se habla de email)
4. Inyecta SystemMessage con:
   - Apps conectadas del usuario
   - Apps disponibles para conectar relevantes al contexto
   - Estado de cada conexión (activa / expirada / nunca conectada)

---

## Cómo verificarlo en la interfaz de debug

1. Preguntar "¿con qué puedes conectarte?" → Shifu lista las apps del catálogo
2. Si Gmail está conectado: "puedo acceder a tu Gmail"
3. Si Gmail no está conectado: "para conectar Gmail necesitas autorizar desde Settings > Integraciones"
4. Logs: `[tool_context_loader] user=X connected=3 relevant=2`

---

## Dependencias

- `catalog_apps` y `user_connected_accounts` ya existen en MongoDB ✅
- No requiere Phase 11 — Tool Awareness puede existir sin ejecutar herramientas
- Se beneficia de Phase 8 (Intent) para filtrar qué herramientas son relevantes al contexto

---

## Prioridad sugerida

Alta. Es el prerrequisito directo para Phase 11 (Tool Execution) y agrega valor inmediato — Shifu puede guiar al usuario a conectar las cuentas necesarias incluso antes de poder ejecutarlas.
