# Shifu Conversational Roadmap

> **Legend:**
> ✅ Complete | 🔄 In Progress | ⚠️ Partial | ❌ Not Started
>
> **v1** = multiAgent (legacy) | **v2** = agente_v2 (current)

---

## Tabla de estado general

> **Tecnologías:** LLM = llamada a modelo de lenguaje | LG = nodo LangGraph | BT = BigTool (herramienta externa)

| Phase | Feature | v1 | v2 | LLM | LG | BT |
|-------|---------|:--:|:--:|:---:|:--:|:--:|
| **1 — Conversation Awareness** | Active Topic | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Current Goal | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Conversation Stage | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Open Questions | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Recent Entities | ✅ | ✅ | ✅ | ✅ | ❌ |
| **2 — Session Working Memory** | Current Focus | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Active Project | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Active Task | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Important Facts | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Decisions | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Open Threads | ✅ | ✅ | ✅ | ✅ | ❌ |
| **3 — Reference Resolution** | Reference Resolution | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Implicit References | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Context Linking | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Entity Resolution | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Pronoun Resolution | ❌ | ❌ | ✅ | ✅ | ❌ |
| **4 — Conversational Personality** | Communication Style | ⚠️ | ⚠️ | ❌ | ✅ | ❌ |
| | Tone Consistency | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Initiative | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Interaction Patterns | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Behavioral Rules | ✅ | ✅ | ❌ | ✅ | ❌ |
| **5 — Identity Context** | Agent Identity | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Mission | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Vision | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Capabilities | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Limitations | ✅ | ✅ | ❌ | ✅ | ❌ |
| | Creator Information | ✅ | ✅ | ❌ | ✅ | ❌ |
| **6 — User Understanding** | User Profile | ✅ | ✅ | ❌ | ✅ | ❌ |
| | User Preferences | ✅ | ✅ | ✅ | ✅ | ❌ |
| | Communication Preferences | ✅ | ✅ | ✅ | ✅ | ❌ |
| | User Interests | ⚠️ | ⚠️ | ✅ | ✅ | ❌ |
| | Interaction Patterns (Cognitive Profile) | ✅ | ❌ | ✅ | ✅ | ❌ |
| **7 — Long-Term Memory** | Persistent Memory | ✅ | 🔄 | ✅ | ✅ | ❌ |
| | Memory Storage | ✅ | 🔄 | ✅ | ✅ | ❌ |
| | Memory Retrieval | ✅ | 🔄 | ❌ | ✅ | ❌ |
| | Memory Updates | ✅ | 🔄 | ✅ | ✅ | ❌ |
| | Memory Consolidation (vector search) | ✅ | ❌ | ❌ | ✅ | ❌ |
| **8 — Intent & Understanding** | User Goal Extraction | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Requested Action Detection | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Missing Information Detection | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Confidence Scoring | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Structured Understanding Context | ❌ | ❌ | ✅ | ✅ | ❌ |
| **9 — Planning & Reasoning** | Task Decomposition | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Goal Planning | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Multi-Step Reasoning | ❌ | ❌ | ✅ | ✅ | ❌ |
| | Execution Planning | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| | Decision Making | ⚠️ | ❌ | ✅ | ✅ | ❌ |
| **10 — Tool Awareness** | Tool Catalog Awareness | ✅ | ❌ | ❌ | ✅ | ✅ |
| | Capability Awareness | ✅ | ❌ | ❌ | ✅ | ✅ |
| | Tool Discovery | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Tool Selection Context | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| | Tool Usage History | ❌ | ❌ | ❌ | ✅ | ✅ |
| | Tool Bigtools | ❌ | ❌ | ✅ | ✅ | ✅ |
| **11 — Tool Execution** | Tool Routing | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Tool Invocation | ✅ | ❌ | ❌ | ✅ | ✅ |
| | Tool Result Processing | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Tool Loops | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Multi-Tool Coordination | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| **12 — Workflow Intelligence** | Workflow Creation | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Workflow Understanding | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Workflow Orchestration | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Automation Planning | ✅ | ❌ | ✅ | ✅ | ✅ |
| | Process Optimization | ⚠️ | ❌ | ✅ | ✅ | ✅ |
| **13 — MCP & External Systems** | MCP Integration | ❌ | ❌ | ❌ | ✅ | ✅ |
| | External Agents | ❌ | ❌ | ✅ | ✅ | ✅ |
| | External Knowledge Sources | ❌ | ❌ | ✅ | ✅ | ✅ |
| | External Services | ❌ | ❌ | ❌ | ✅ | ✅ |
| | Cross-System Coordination | ❌ | ❌ | ✅ | ✅ | ✅ |
| | Cross-System Coordination | ❌ | ❌ |
| **14 — Autonomous Agent** | Autonomous Execution | ❌ | ❌ |
| | Long-Running Tasks | ❌ | ❌ |
| | Background Objectives | ⚠️ | ❌ |
| | Self-Directed Actions | ❌ | ❌ |
| | Agent Autonomy | ❌ | ❌ |

---

## Phase 1 — Conversation Awareness ✅

| Item | v1 | v2 |
|------|----|----|
| Active Topic | ✅ | ✅ |
| Current Goal | ✅ | ✅ |
| Conversation Stage | ✅ | ✅ |
| Open Questions | ✅ | ✅ |
| Recent Entities | ✅ | ✅ |

**v2 node:** `conversation_context_builder` — LLM over last 8 messages, stateless each turn.

---

## Phase 2 — Session Working Memory ✅

| Item | v1 | v2 |
|------|----|----|
| Current Focus | ✅ | ✅ |
| Active Project | ✅ | ✅ |
| Active Task | ✅ | ✅ |
| Important Facts | ✅ | ✅ |
| Decisions | ✅ | ✅ |
| Open Threads | ✅ | ✅ |

**v2 node:** `working_memory_builder` — LLM over last 20 messages, stateless each turn.
**v1 note:** Used persistent `user_state` + `user_world_model` (MongoDB). v2 is lighter and stateless.

---

## Phase 3 — Conversational Reference Resolution ❌

| Item | v1 | v2 |
|------|----|----|
| Reference Resolution | ❌ | ❌ |
| Implicit References | ❌ | ❌ |
| Context Linking | ❌ | ❌ |
| Entity Resolution | ❌ | ❌ |
| Pronoun Resolution | ❌ | ❌ |

Neither version implemented a dedicated reference resolution layer.

---

## Phase 4 — Conversational Personality ⚠️

| Item | v1 | v2 |
|------|----|----|
| Communication Style | ⚠️ | ⚠️ |
| Tone Consistency | ✅ | ✅ |
| Initiative | ❌ | ❌ |
| Interaction Patterns | ❌ | ❌ |
| Behavioral Rules | ✅ | ✅ |

**v2 node:** `identity_loader` + `chat_node` — `agent_personality` doc (tono_base, prohibiciones_lexicas, reglas_comunicacion) loaded from DB. No dynamic style adaptation per user.

---

## Phase 5 — Identity Context ✅

| Item | v1 | v2 |
|------|----|----|
| Agent Identity | ✅ | ✅ |
| Mission | ✅ | ✅ |
| Vision | ✅ | ✅ |
| Capabilities | ✅ | ✅ |
| Limitations | ✅ | ✅ |
| Creator Information | ✅ | ✅ |

**v2 nodes:** `identity_loader` (cache 1h) + `chat_node` — reads `agent_identity`, `agent_personality`, `agent_goals`, `agent_system_model` collections.

---

## Phase 6 — User Understanding ✅

| Item | v1 | v2 |
|------|----|----|
| User Profile | ✅ | ✅ |
| User Preferences | ✅ | ✅ |
| Communication Preferences | ✅ | ✅ |
| User Interests | ⚠️ | ⚠️ |
| Interaction Patterns | ✅ | ❌ |

**v2 nodes:** `user_context_loader` (loads `user_preferences`) + `user_profile_updater` (extracts & persists new facts after each turn).
**v1 extra:** Had `user_cognitive_profile` (behavioral patterns, reasoning style, expertise areas) — not yet in v2.

---

## Phase 7 — Long-Term Memory 🔄

| Item | v1 | v2 |
|------|----|----|
| Persistent Memory | ✅ | 🔄 |
| Memory Storage | ✅ | 🔄 |
| Memory Retrieval | ✅ | 🔄 |
| Memory Updates | ✅ | 🔄 |
| Memory Consolidation | ✅ | ❌ |

**v2 nodes (Phase 3 of memory roadmap — just implemented):**
- `long_term_memory_loader` — reads `user_global_memory`, injects as SystemMessage
- `memory_saver` — saves conversation summary → `agente_v2_chat_context` → triggers `user_daily_diary` → triggers `user_global_memory` refresh (background, every 3 diary updates)

**v1 extras not yet in v2:** vector search over `user_global_memory_chunks`, `user_cognitive_profile` synthesis.
**See:** `MEMORY_LAYERS.md` for full roadmap (Phases 4 = chunks/embeddings, 5 = episodic memory).

---

## Phase 8 — Intent & Understanding Reconstruction ❌

| Item | v1 | v2 |
|------|----|----|
| User Goal Extraction | ⚠️ | ❌ |
| Requested Action Detection | ⚠️ | ❌ |
| Missing Information Detection | ⚠️ | ❌ |
| Confidence Scoring | ⚠️ | ❌ |
| Structured Understanding Context | ❌ | ❌ |

**v1 note:** `reflection_node` extracted `importance_score` + observations per turn, but no dedicated structured intent schema. v2 has no reflection node yet.

---

## Phase 9 — Planning & Reasoning ❌

| Item | v1 | v2 |
|------|----|----|
| Task Decomposition | ⚠️ | ❌ |
| Goal Planning | ⚠️ | ❌ |
| Multi-Step Reasoning | ❌ | ❌ |
| Execution Planning | ⚠️ | ❌ |
| Decision Making | ⚠️ | ❌ |

**v1 note:** `objective_state` tracked goals with step-by-step progress. `agent_internal_state` tracked pending decisions and open questions. No dedicated planning LLM node.

---

## Phase 10 — Tool Awareness ❌

| Item | v1 | v2 |
|------|----|----|
| Tool Catalog Awareness | ✅ | ❌ |
| Capability Awareness | ✅ | ❌ |
| Tool Discovery | ✅ | ❌ |
| Tool Selection Context | ⚠️ | ❌ |
| Tool Usage History | ❌ | ❌ |
| Tool Bigtools | ❌ | ❌ |

**v1 note:** `catalog_apps` + `user_connected_accounts` were loaded and injected into context. v2 has no tool catalog integration yet.

---

## Phase 11 — Tool Execution ❌

| Item | v1 | v2 |
|------|----|----|
| Tool Routing | ✅ | ❌ |
| Tool Invocation | ✅ | ❌ |
| Tool Result Processing | ✅ | ❌ |
| Tool Loops | ✅ | ❌ |
| Multi-Tool Coordination | ⚠️ | ❌ |

**v1 note:** Full tool binding to LLM + `tool_executor_node` with result processing and loops. v2 has no tool execution layer yet.

---

## Phase 12 — Workflow Intelligence ❌

| Item | v1 | v2 |
|------|----|----|
| Workflow Creation | ✅ | ❌ |
| Workflow Understanding | ✅ | ❌ |
| Workflow Orchestration | ✅ | ❌ |
| Automation Planning | ✅ | ❌ |
| Process Optimization | ⚠️ | ❌ |

**v1 note:** Full `process_discovery` system with `workflow_builder`, `session_manager`, `processes`/`workflows` collections and guided discovery flow.

---

## Phase 13 — MCP & External Systems ❌

| Item | v1 | v2 |
|------|----|----|
| MCP Integration | ❌ | ❌ |
| External Agents | ❌ | ❌ |
| External Knowledge Sources | ❌ | ❌ |
| External Services | ❌ | ❌ |
| Cross-System Coordination | ❌ | ❌ |

Neither version implemented an MCP layer.

---

## Phase 14 — Autonomous Agent Layer ❌

| Item | v1 | v2 |
|------|----|----|
| Autonomous Execution | ❌ | ❌ |
| Long-Running Tasks | ❌ | ❌ |
| Background Objectives | ⚠️ | ❌ |
| Self-Directed Actions | ❌ | ❌ |
| Agent Autonomy | ❌ | ❌ |

**v1 note:** `objective_state` existed with step tracking, but no autonomous execution engine. Background jobs existed only for memory synthesis, not agent actions.
