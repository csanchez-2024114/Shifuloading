# Production Readiness — Shifu drives everything through chat (7 fronts)

## Context

The board/limits work (previous plan phase) shipped: FlowDesigner tabs are
real Boards, analytics filter by workspace/board, and PLAN_RULES already carries
`max_workflows / max_apps_per_workflow / max_accounts_per_provider / max_workspaces /
max_concurrent_runs / daily_token_limit`. This plan closes the remaining gaps to reach
production across the 7 things the user listed. Recon (3 Explore passes + ui_actions trace)
found the app is **much more live than expected** — the real work is a handful of concrete
gaps, not a rewrite.

**The one architectural decision that unifies all 7 fronts (user's explicit ask): everything
is driven by the Shifu agent through chat, surfaced to the frontend via a generalized
`ui_actions` protocol.** Today `ui_actions` is a single hardcoded `connect_app` type
(`chat.py:_build_ui_actions:87`) consumed by an inline filter in
`ChatFlowDesigner/index.tsx:224` + a thin `uiActionsSlice.ts`. We turn it into a **typed
directive channel** the agent uses to: render/patch canvas nodes live, open the trigger it
configured, refresh charts, prompt connect-app, and surface plan-limit upgrades. No new
manual-config UI is built — the agent emits directives, the frontend renders them.

All 4 workstreams are launch-blocking (user confirmed). Phases below are execution order, not
priority tiers.

---

## Phase 0 — Generalize `ui_actions` into a typed directive protocol (foundation, do first)

Everything else emits through this. Keep it a plain discriminated-union list on the existing
`done` frame — no new transport, `/chat/stream` SSE + `/ws/chat` already carry `ui_actions`.

**Backend** — `app/routes/chat/chat.py`:
- Rewrite `_build_ui_actions(final_state)` (`:87`) to collect a typed list from state, not just
  auth reports. Each action: `{ "type": <kind>, ...payload }`. Kinds this plan needs:
  - `connect_app` — unchanged (keep existing auth-report derivation).
  - `render_workflow` — `{ workflow_id, steps: [...] }` so the canvas paints without a second
    REST round-trip (today the frontend re-fetches via `getWorkflow`; keep that as fallback).
  - `open_trigger` — `{ workflow_id, trigger_type, summary }` so the UI can confirm/show what
    Shifu automated (webhook URL, schedule, event).
  - `refresh_charts` — `{}` a hint that analytics changed (belt-and-suspenders alongside the
    run-WS refresh in Phase 3).
  - `upgrade_plan` — `{ limit, used, plan }` when the agent hit a plan cap (replaces ad-hoc
    limit toasts; reuses `openUpgradePlan` that already exists).
- The agent already computes the raw material: `req_workflow_id`, `validation_reports`,
  `req_plan.steps`, frequency/trigger fields. `_build_ui_actions` just projects state → typed
  actions. No new graph nodes.

**Frontend** — `src/redux/slices/uiActionsSlice.ts` + a single dispatcher:
- Add a `dispatchUiActions(actions)` thunk (one `switch` on `type`) called once from
  `ChatFlowDesigner/index.tsx:onDone` — replaces the inline `connect_app` filter (`:224-241`)
  and the `workflow_id` special-case. Each case maps to an existing action
  (`openTrainview`/`openUpgradePlan`/`setPendingWorkflow`) or a new one
  (`render_workflow`→hydrate canvas, `open_trigger`→show trigger chip, `refresh_charts`→bump a
  refresh nonce Phase 3 listens to).
- Type the union in one place (`types.ts` next to the slice) so every consumer is exhaustive.

Verification: send a chat that connects an app, creates a workflow, and schedules it → confirm
one `done` frame carries `connect_app` + `render_workflow` + `open_trigger` and the UI reacts to
all three without a page action.

---

## Phase 1 — Shifu generates the workflow correctly: schema + live nodes (user items 3, 4)

Recon confirmed identity/context is solid (DB-driven `identity_loader.py`, user-name grounding,
mission/vision block) and the multi-turn builder `req_nodes.py` persists real workflows. Two
concrete schema bugs + one liveness gap remain.

1. **`grafica` node-type mismatch (schema drift).** Backend `_VALID_NODE_TYPES`
   (`req_nodes.py:44`) and the L2 planner prompt allow `"grafica"`, but the frontend
   `WorkflowNodeThemeKey` (`nodes/workflowNode.types.ts:11`) + `NODE_TYPE_DEFAULTS`
   (`nodes/nodeDefaults.ts:10`) don't — a `grafica` step renders as `"ia"`
   (`FlowDesigner/index.tsx:62`). **Add `grafica` to the frontend node theme** (icon/color/label)
   so it round-trips. (The *live mini-chart* rendering inside that node is Phase 4.)

2. **Round-trip field loss.** `nodesToBackendSteps` (`FlowDesigner/index.tsx:40`) writes
   `app = badgeText`, `action = description`, dropping the real `action`/`account_id`. A
   chat-built workflow edited on the canvas + saved corrupts its own steps. **Carry `action` and
   `account_id` through the node `data`** (add fields in `backendStepsToNodes:56` and read them
   back in `nodesToBackendSteps`) so edit-save is lossless.

3. **Live node rendering.** Today the whole workflow builds atomically at `req_level==5`
   (`_deploy`) then the frontend re-fetches. Wire the `render_workflow` ui_action (Phase 0) so
   `_deploy` returns `req_plan.steps` in state and the canvas paints from the `done` frame
   directly (still falls back to `getWorkflow`). This is the "que literal lo genere en vivo"
   ask — nodes appear the moment the agent finishes, no manual reload.

Rules/context (item 3) needs no code change beyond keeping `agent_identity`/`agent_personality`
Mongo docs populated — add a one-shot `demo()` self-check that asserts `build_system_messages`
includes the user name + mission block, so regressions surface.

Verification: chat "créame un workflow que grafique mis ventas semanales" → confirm a `grafica`
node renders with its own theme, appears live on completion, and editing+saving preserves
`action`/`account_id` (check the Mongo `steps` doc).

---

## Phase 2 — Automatización: workflows stay running (user items 2, 5) — the biggest gap

Recon: webhook **receiver works** (`webhook_inbound.py`) but **registration is orphaned**
(`set_webhook_trigger` `workflow_service.py:482` has zero callers, `webhook_token` not
PATCH-able); scheduled runs **work but only via the agent bigtool** `_schedule_workflow`
(`workflow_bigtools.py:727`, and it omits cron); the **trigger-poller has no data source**
(nothing writes `trigger_config.next_check/trigger_tool/trigger_filter`); frequency fields are
**informational only**. User's rule: all trigger setup happens **through chat via Shifu**, so the
fix is agent-bigtool-first, not a UI.

1. **Wire webhook registration into the agent.** In `req_nodes._deploy` (`:270`), when the plan's
   `trigger_type == "webhook"`, call the existing `set_webhook_trigger(workflow_id, db)` and
   surface the resulting URL via the `open_trigger` ui_action. This makes the orphaned function
   live with no new endpoint.

2. **Make scheduled triggers real from chat, including cron.** `_schedule_workflow` bigtool
   already calls `create_scheduled_task`; extend its `schedule_config` builder to also emit
   `cron` (the service `scheduled_task_service._next_cron_run` already supports it — pure
   backend gap). Ensure `req_nodes._deploy`'s `set_workflow_frequency` path actually creates a
   `scheduled_tasks` row (today it only writes informational top-level fields that no worker
   reads).

3. **Populate the event-poller's inputs.** When Shifu configures an app-event trigger, write
   `trigger_type="event"` + `trigger_config.{next_check, trigger_tool, trigger_filter, every_seconds}`
   (the exact shape `trigger_poller._check_and_fire:102` reads). This is the only way the poller
   ever finds work. Done from the agent bigtool, not a raw PATCH.

4. **Fix the double-execution bug (production risk).** `webhook_inbound.py`, `scheduler_worker.py`,
   and `trigger_poller.py` each call `create_run` (which publishes to the Redis
   `workflow:runs` stream, so `workflow_worker` claims it) **and** re-fetch + inline
   `WorkflowExecutor.execute()` — flagged as a known bug in `workflows.py:205`. **Drop the inline
   execute** in all three; let the stream worker be the single executor (matches the manual
   trigger path). Verify runs still fire via the worker.

Verification: chat "cada lunes 9am corre este workflow" → `scheduled_tasks` row with a cron
`next_run_at`, fires once via the worker (not twice). Chat "cuando llegue un correo nuevo…" →
webhook URL returned + event poller picks it up. Confirm no run executes twice
(`workflow_runs` count).

---

## Phase 3 — Charts en tiempo real + data correcta (user item 6a)

Recon: analytics endpoints **already filter correctly** by `user_id`+`workspace_id`+`board_id`
(contingent on the run/executor denormalization, which is in place). The only gap is refresh:
`useFetchAnalytics*` hooks are **fetch-once-on-mount** (deps `[token, workspace, board]`), no
realtime. User chose **refresh-on-run-completion via the existing `/ws/runs` WebSocket**.

- Reuse the run WebSocket already opened in `FlowDesigner/index.tsx:handleRun` — but the
  dashboard needs it independently of FlowDesigner. Add a small `useRunEventsSocket()` hook
  (single app-level connection to `/api/v1/ws/runs`) that bumps a Redux `analyticsRefreshNonce`
  on `run_completed`/`run_failed`.
- Add that nonce to each `useFetchAnalytics*` `useEffect` dep array (+ the `refresh_charts`
  ui_action from Phase 0 bumps the same nonce). Charts refetch exactly when data changes —
  event-driven, no polling. Add a manual "Actualizar" affordance for good measure.
- Data-correctness caveat to document (not fix): runs written **before** the workspace/board
  denormalization have no `board_id` and drop out under a board filter — expected.

Verification: dashboard open, trigger a workflow run in another tab → charts update within a
second of `run_completed`, scoped to the active board.

---

## Phase 4 — El nodo de gráfica con mini-chart en vivo dentro de FlowDesigner (user item 6b, "final")

User wants the **full** version: the `grafica` node not just themed (Phase 1) but rendering a
**real mini-chart with live analytics data** inside the canvas node.

- Extend the `grafica` node component (new `nodes/GraficaNode.tsx`, registered in `nodes/index.ts`
  alongside `workflowNode`) to render a compact **recharts** sparkline/bar — reuse
  `ChartRenderer`'s primitives and the existing `useFetchAnalytics*` data (scoped to the node's
  workflow/board). The node's `data.config` carries which metric/chart type to show (the agent
  sets this when it emits a `grafica` step).
- Feed it from the same `analyticsRefreshNonce` (Phase 3) so the in-canvas chart is live too.
- ponytail: one small chart type inside the node (sparkline), not the full 9-chart suite —
  add more chart types when a workflow actually needs them.

Verification: a workflow with a `grafica` step shows a live mini-chart in the node that updates
on run completion.

---

## Phase 5 — Conectar API en vivo + niveles de límite de plataforma (user item 7)

Recon: PLAN_RULES + most enforcement is **already done**. Two real bugs + surfacing remain.

1. **`max_connected_apps` bug (caps EVERY plan to 1 app).** `_enforce_connected_apps_limit`
   (`integrationRoutes.py:80`) reads `get_plan_rules(plan).get("max_connected_apps", 1)` — a key
   that **does not exist in any tier**, so it always falls back to 1. Rewrite it to enforce the
   real, intended rule: **`max_accounts_per_provider`** (defined in every tier, currently
   enforced nowhere) — count accounts of the *same* provider within the workspace, never cap
   distinct providers. Thread `workspace_id`/`provider` into its two call sites
   (`integrationRoutes.py:199`, `:315`).
2. **Surface limits through the agent, not toasts.** When any limit raises
   (`WorkflowLimitExceededError`, `ConcurrentRunLimitExceededError`,
   `WorkflowAppsLimitExceededError`, the new provider cap), emit the `upgrade_plan` ui_action
   (Phase 0) so Shifu explains the cap in chat and the existing `openUpgradePlan` modal opens —
   consistent with "todo por chat".
3. **Live API sweep.** Remove/finish the remaining frontend stubs that would look broken in prod:
   fake Share button (`FlowDesignerToolbar.tsx:43`), static group-node mode
   (`WorkflowGroupNode.tsx:8`), hardcoded `StoragePanel` (`charts/InfoPanel.tsx:106`), and delete
   dead `src/hooks/mockDashboardData.ts`. Persist chat history (today
   `useChatHistory.ts:24` seeds `MOCK_CHAT_HISTORY`, localStorage only) against a real
   conversation endpoint, or explicitly scope it out if acceptable for launch.

Verification: on `free`, connect two different providers (both succeed), try a 2nd account of the
same provider (blocked with an `upgrade_plan` action in chat); hit a workflow cap and confirm
the upgrade modal opens from chat, not a toast.

---

## Cross-cutting verification (end-to-end, pre-prod)

One chat-driven happy path exercises every phase:
1. Log in on `free`. Open FlowDesigner.
2. Chat: "conéctame Gmail y créame un workflow que cada lunes 9am me grafique los correos
   recibidos la semana pasada."
3. Expect, from a single agent turn: `connect_app` (Gmail) → after connect, `render_workflow`
   paints nodes **live** incl. a themed `grafica` node → `open_trigger` shows the Monday-9am
   schedule → a `scheduled_tasks` row exists with a cron `next_run_at`.
4. Let (or force) a run: it executes **once** (no double-exec), writes
   `workflow_runs`/`workflow_analytics`/`intent_outcomes` with `workspace_id`/`board_id`.
5. Dashboard + the in-canvas `grafica` node both refresh on `run_completed`, scoped to the board.
6. Hit a plan cap → `upgrade_plan` surfaces in chat and opens the modal.

Ship-blockers all covered: automatización (P2), Shifu genera bien (P1), charts realtime (P3/P4),
límites+API (P5), on the `ui_actions` spine (P0).
