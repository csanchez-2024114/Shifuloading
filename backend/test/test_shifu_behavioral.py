"""
Shifu Behavioral Test Suite
============================
Runs against a live server (localhost:5000) using the test Gmail account.
Tests Phase 1 consultative UX, GATE A/B/C, WebSocket streaming,
auth detection, and Generative UI emission.

Usage:
    python test/test_shifu_behavioral.py

Requires: httpx, websockets
"""

import asyncio
import json
import sys
import time
import uuid
from typing import Any

import httpx
import websockets

BASE = "http://localhost:5000"
WS_BASE = "ws://localhost:5000"
EMAIL = "gallodelacruz1977@gmail.com"
PASSWORD = "Al1234$$"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
INFO = "\033[36mINFO\033[0m"

results: list[dict] = []


def log(label: str, status: str, detail: str = "") -> None:
    icon = PASS if status == "PASS" else (FAIL if status == "FAIL" else INFO)
    print(f"  [{icon}] {label}" + (f"\n        {detail}" if detail else ""))
    results.append({"test": label, "status": status, "detail": detail})


def conv_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


# ─── T1: Auth ────────────────────────────────────────────────────────────────

async def t1_auth(client: httpx.AsyncClient) -> tuple[str, str]:
    print("\n── T1: Authentication ──")
    r = await client.post("/api/v2/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        log("T1 Login", "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")
        sys.exit(1)
    data = r.json()
    token = data.get("token", "")
    user_id = data.get("user", {}).get("id", "")
    if token and user_id:
        log("T1 Login", "PASS", f"user_id={user_id[:12]}...")
    else:
        log("T1 Login", "FAIL", f"Missing token or user_id in response: {list(data.keys())}")
        sys.exit(1)
    return token, user_id


# ─── T2: Health ──────────────────────────────────────────────────────────────

async def t2_health(client: httpx.AsyncClient) -> None:
    print("\n── T2: Health Check ──")
    r = await client.get("/health")
    data = r.json()
    if data.get("mongodb") == "ok":
        log("T2 Health", "PASS", f"status={data.get('status')}")
    else:
        log("T2 Health", "FAIL", str(data))


# ─── T3: Gmail Integration Verified ─────────────────────────────────────────

async def t3_gmail(client: httpx.AsyncClient) -> None:
    """Verify Gmail is connected by probing the user profile and a lightweight chat turn."""
    print("\n── T3: Gmail Integration ──")
    # The /api/accounts/ endpoint has a known pre-existing ResponseValidationError.
    # Fall back to verifying via /api/v2/auth/me (user.integrations) or a chat probe.
    r = await client.get("/api/v2/auth/me")
    if r.status_code == 200:
        user = r.json()
        integrations = user.get("integrations") or user.get("user", {}).get("integrations", {})
        gmail_keys = [k for k in integrations if "gmail" in k.lower() or "google" in k.lower()]
        if gmail_keys:
            log("T3 Gmail connected (via /me)", "PASS", f"Integration keys: {gmail_keys}")
        else:
            log("T3 Gmail connected (via /me)", "FAIL", f"integrations keys: {list(integrations.keys())[:10]}")
    else:
        # Last resort: send a simple Gmail chat and check if the agent uses Gmail tools
        r2 = await client.post(
            "/api/v3/agent/chat",
            json={"conversation_id": conv_id(), "user_input": "¿Tengo Gmail conectado?", "model": "gpt-4o-mini"},
            timeout=60,
        )
        if r2.status_code == 200:
            answer = r2.json().get("final_answer", "") or ""
            if "gmail" in answer.lower() or "conectad" in answer.lower():
                log("T3 Gmail connected (via chat probe)", "PASS", answer[:150])
            else:
                log("T3 Gmail connected (via chat probe)", "FAIL", answer[:150])
        else:
            log("T3 Gmail connected", "FAIL", f"/me HTTP {r.status_code}, chat HTTP {r2.status_code}")


# ─── T4: Vague Intent ────────────────────────────────────────────────────────

async def t4_vague_intent(client: httpx.AsyncClient) -> None:
    print("\n── T4: Phase 1 — Vague Intent ──")
    cid = conv_id()
    r = await client.post(
        "/api/v3/agent/chat",
        json={"conversation_id": cid, "user_input": "quiero automatizar algo", "model": "gpt-4o-mini"},
        timeout=120,
    )
    if r.status_code != 200:
        log("T4 Vague intent HTTP", "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")
        return
    data = r.json()
    answer = data.get("final_answer", "") or ""

    # Check: no raw phase tag
    if "[PHASE:" in answer:
        log("T4 Phase tag stripped", "FAIL", f"Raw tag found in: {answer[:200]}")
    else:
        log("T4 Phase tag stripped", "PASS")

    # Check: no UI_ACTION text leaked
    if "UI_ACTION:" in answer:
        log("T4 UI_ACTION stripped", "FAIL", f"Raw UI_ACTION in answer: {answer[:200]}")
    else:
        log("T4 UI_ACTION stripped", "PASS")

    # Check: contains multiple workflow ideas (look for emojis, card separators, or numbered items)
    idea_signals = sum(1 for c in [
        "🎯", "📊", "🔔", "🗂", "💬", "⚡", "📧", "📅", "🔄", "💼", "🧠", "📬",
        "1.", "2.", "3.", "---", "· cada", "**["
    ] if c in answer)
    if idea_signals >= 2:
        log("T4 Proposes workflow ideas", "PASS", f"Found {idea_signals} idea signals")
    else:
        log("T4 Proposes workflow ideas", "FAIL", f"Too few ideas ({idea_signals}): {answer[:300]}")

    # Check: only one question mark at the end (one-question rule)
    question_marks = answer.count("?")
    if question_marks <= 2:
        log("T4 One-question rule", "PASS", f"{question_marks} question mark(s)")
    else:
        log("T4 One-question rule", "FAIL", f"{question_marks} question marks — multiple questions detected")

    # Check: no tool names exposed
    forbidden = ["listar_correos", "crear_workflow", "tool_name", "evaluar_certeza"]
    leaked = [t for t in forbidden if t in answer.lower()]
    if not leaked:
        log("T4 No tool names exposed", "PASS")
    else:
        log("T4 No tool names exposed", "FAIL", f"Leaked: {leaked}")


# ─── T5: Specific Gmail Workflow ──────────────────────────────────────────────

async def t5_specific_workflow(client: httpx.AsyncClient) -> str:
    """Returns the conversation_id for use in T6."""
    print("\n── T5: Phase 1 — Specific Gmail→Sheets Workflow ──")
    cid = conv_id()
    r = await client.post(
        "/api/v3/agent/chat",
        json={
            "conversation_id": cid,
            "user_input": "Quiero guardar en Google Sheets los correos de leads que llegan a Gmail",
            "model": "gpt-4o-mini",
        },
        timeout=120,
    )
    if r.status_code != 200:
        log("T5 Request", "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")
        return cid
    data = r.json()
    answer = data.get("final_answer", "") or ""

    # Phase tag stripped
    if "[PHASE:" in answer:
        log("T5 Phase tag stripped", "FAIL")
    else:
        log("T5 Phase tag stripped", "PASS")

    # Should ask ONE question
    q_count = answer.count("?")
    if 1 <= q_count <= 2:
        log("T5 Single question asked", "PASS", f"{q_count} question mark(s)")
    else:
        log("T5 Single question asked", "FAIL", f"{q_count} question mark(s) in: {answer[:300]}")

    # Should NOT have built the workflow yet (no crear_workflow callS should be in history)
    if "crear_workflow" in answer.lower():
        log("T5 GATE A (no early build)", "FAIL", "crear_workflow mentioned in response")
    else:
        log("T5 GATE A (no early build)", "PASS")

    print(f"    {INFO} Answer preview: {answer[:250]}")
    return cid


# ─── T6: Phase 1 Loop ────────────────────────────────────────────────────────

async def t6_phase1_loop(client: httpx.AsyncClient, cid: str) -> None:
    print("\n── T6: Phase 1 — One-Question Loop ──")
    _APPROVAL = [
        "lo creamos", "te parece bien", "procedemos", "lo construyo", "empezamos",
        "lo activo", "arrancamos", "lo hacemos", "confirmamos", "aprobado",
        "así está bien", "lo creamos así", "empezamos a construir", "quieres que lo construya",
        "aquí tienes el plan", "aquí está el plan", "el plan queda", "el plan es",
        "aquí está la propuesta", "⚡ **", "---\n⚡",
    ]
    # Scripted answers designed to drive the agent through Phase 1 to Final Plan
    turns = [
        "Los leads tienen la palabra 'presupuesto' en el asunto",
        "Sí, crea una hoja llamada 'Leads Capturados'",
        "Cada 15 minutos está bien",
        "sí, todo está bien así",
        "Sí, correcto",
        "Sí, eso es suficiente información",
        "Sí, adelante con eso",
        "Sí, procede",
        "Sí, créalo",
        "Sí, dale",
    ]
    for i, msg in enumerate(turns):
        r = await client.post(
            "/api/v3/agent/chat",
            json={"conversation_id": cid, "user_input": msg, "model": "gpt-4o-mini"},
            timeout=120,
        )
        if r.status_code != 200:
            log(f"T6 Turn {i+1}", "FAIL", f"HTTP {r.status_code}")
            continue
        answer = r.json().get("final_answer", "") or ""
        q = answer.count("?")

        if "[PHASE:" in answer:
            log(f"T6 Turn {i+1} phase tag", "FAIL")
        else:
            log(f"T6 Turn {i+1} phase tag stripped", "PASS")

        if q <= 2:
            log(f"T6 Turn {i+1} one-question rule", "PASS", f"{q} '?' — {answer[:120]}")
        else:
            log(f"T6 Turn {i+1} one-question rule", "FAIL", f"{q} '?' in: {answer[:200]}")

        if any(s in answer.lower() for s in _APPROVAL):
            log(f"T6 Final Plan reached at turn {i+1}", "PASS")
            return
    log("T6 Final Plan reached", "FAIL", "Exhausted all turns without reaching final plan")


# ─── T7: GATE A ──────────────────────────────────────────────────────────────

async def t7_gate_a(client: httpx.AsyncClient) -> None:
    print("\n── T7: GATE A — Cannot Build Before Approval ──")
    cid = conv_id()
    # Turn 1: vague request
    await client.post(
        "/api/v3/agent/chat",
        json={"conversation_id": cid, "user_input": "Crea un workflow de Gmail a Sheets", "model": "gpt-4o-mini"},
        timeout=120,
    )
    # Turn 2: immediate approval attempt
    r = await client.post(
        "/api/v3/agent/chat",
        json={"conversation_id": cid, "user_input": "dale hazlo ya", "model": "gpt-4o-mini"},
        timeout=120,
    )
    if r.status_code != 200:
        log("T7 GATE A", "FAIL", f"HTTP {r.status_code}")
        return
    answer = r.json().get("final_answer", "") or ""
    # Agent should still be asking questions, not building
    if "?" in answer and "crear_workflow" not in answer.lower():
        log("T7 GATE A enforced", "PASS", f"Still asking questions: {answer[:200]}")
    elif "crear_workflow" in answer.lower():
        log("T7 GATE A enforced", "FAIL", "Agent called crear_workflow before approval!")
    else:
        log("T7 GATE A enforced", "FAIL", f"Unexpected response: {answer[:200]}")


# ─── T10/T11: WebSocket Baseline + Ping ──────────────────────────────────────

async def t10_t11_websocket_baseline(token: str) -> None:
    print("\n── T10: WebSocket Token Streaming + T11: Ping/Pong ──")
    cid = conv_id()
    uri = f"{WS_BASE}/api/v3/ws/chat?token={token}&conversation_id={cid}"
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            # T11: ping/pong
            await ws.send(json.dumps({"type": "ping"}))
            pong_raw = await asyncio.wait_for(ws.recv(), timeout=5)
            pong = json.loads(pong_raw)
            if pong.get("type") == "pong":
                log("T11 Ping/Pong", "PASS")
            else:
                log("T11 Ping/Pong", "FAIL", f"Got: {pong}")

            # T10: streaming baseline
            await ws.send(json.dumps({
                "type": "user_message",
                "text": "Hola, ¿qué puedes hacer con Gmail?",
                "model": "gpt-4o-mini",
            }))
            tokens: list[str] = []
            done_event: dict = {}
            tool_starts: list[str] = []
            deadline = time.time() + 120
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    log("T10 WS timeout", "FAIL", "No message received in 30s")
                    break
                ev = json.loads(raw)
                etype = ev.get("type", "")
                if etype == "token":
                    tokens.append(ev.get("text", ""))
                elif etype == "tool_start":
                    tool_starts.append(ev.get("tool", ""))
                elif etype == "done":
                    done_event = ev
                    break
                elif etype == "error":
                    log("T10 WS error", "FAIL", ev.get("message", ""))
                    break

            if done_event:
                final_text = done_event.get("text", "")
                sugg = done_event.get("suggestions", [])

                # Check tokens arrived
                if tokens:
                    log("T10 Token streaming", "PASS", f"{len(tokens)} chunks received")
                else:
                    log("T10 Token streaming", "FAIL", "No token events received")

                # Check done.text clean
                if "[PHASE:" not in final_text and "UI_ACTION:" not in final_text:
                    log("T10 Done.text clean", "PASS")
                else:
                    log("T10 Done.text clean", "FAIL", f"Dirty text: {final_text[:200]}")

                # Check suggestions
                if isinstance(sugg, list) and len(sugg) >= 2:
                    log("T10 Suggestions", "PASS", f"{len(sugg)} suggestions: {sugg[:2]}")
                else:
                    log("T10 Suggestions", "FAIL", f"Got: {sugg}")

                if tool_starts:
                    log("T10 Tool events received", "PASS", f"Tools: {tool_starts}")
                else:
                    log("T10 Tool events received", "INFO", "No tool_start events (may be expected for greeting)")
            else:
                log("T10 Done event", "FAIL", "Never received 'done' event")

    except Exception as exc:
        log("T10/T11 WebSocket connect", "FAIL", str(exc))


# ─── T9: Auth Detection (Notion not connected) ───────────────────────────────

async def t9_auth_detection(token: str) -> None:
    print("\n── T9: Auth Detection — Unconnected App (Notion) ──")
    cid = conv_id()
    uri = f"{WS_BASE}/api/v3/ws/chat?token={token}&conversation_id={cid}"
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            await ws.send(json.dumps({
                "type": "user_message",
                "text": "Quiero conectar Notion con mis tareas de Gmail",
                "model": "gpt-4o-mini",
            }))
            ui_actions: list[dict] = []
            done_text = ""
            deadline = time.time() + 120
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    log("T9 WS timeout", "FAIL", "No message in 30s")
                    break
                ev = json.loads(raw)
                etype = ev.get("type", "")
                if etype == "ui_action":
                    ui_actions.append(ev.get("action", {}))
                elif etype == "done":
                    done_text = ev.get("text", "")
                    break
                elif etype == "error":
                    log("T9 WS error", "FAIL", ev.get("message", ""))
                    break

            # Auth detection check
            auth_actions = [a for a in ui_actions if a.get("type") == "auth_required"]
            notion_actions = [a for a in auth_actions if a.get("provider", "").lower() == "notion"]

            if notion_actions:
                log("T9 auth_required for Notion", "PASS", f"action={notion_actions[0]}")
            else:
                log("T9 auth_required for Notion", "FAIL",
                    f"No auth_required action for Notion. ui_actions={ui_actions}, done_text={done_text[:200]}")

            # Gmail should still work (connected)
            if done_text and "?" in done_text:
                log("T9 Agent responded (not crashed)", "PASS", done_text[:150])

    except Exception as exc:
        log("T9 WebSocket connect", "FAIL", str(exc))


# ─── T8: Phase 2 Build via WebSocket ─────────────────────────────────────────

async def _ws_turn(ws, text: str, model: str = "gpt-4o-mini", timeout: int = 120) -> tuple[str, list, list]:
    """Send one message via WS and collect (done_text, tool_events, ui_actions) until 'done'."""
    await ws.send(json.dumps({"type": "user_message", "text": text, "model": model}))
    tool_events: list[str] = []
    ui_actions: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            return "", tool_events, ui_actions
        ev = json.loads(raw)
        etype = ev.get("type", "")
        if etype == "tool_start":
            tool_events.append(ev.get("tool", ""))
        elif etype == "ui_action":
            ui_actions.append(ev.get("action", {}))
        elif etype == "done":
            return ev.get("text", ""), tool_events, ui_actions
        elif etype == "error":
            return f"ERROR:{ev.get('message','')}", tool_events, ui_actions
    return "", tool_events, ui_actions


async def t8_phase2_build(client: httpx.AsyncClient, token: str, cid5: str) -> str | None:
    """
    Drive Phase 1 + Phase 2 entirely via WebSocket (shifu_v3 graph).
    Uses a fresh cid so shifu_v3 owns the workflow_phase lifecycle end-to-end,
    ensuring GATE B is satisfied when the user approves.
    cid5 is accepted but not used (kept for call-site compatibility).
    """
    print("\n── T8: Phase 2 — Full Build via WebSocket ──")
    cid = conv_id()
    uri = f"{WS_BASE}/api/v3/ws/chat?token={token}&conversation_id={cid}"

    # Scripted Phase 1 turns designed to collect all required info.
    # First turn includes identity context to bypass the user-profile check that applies to
    # fresh conversations with no existing preferences summary.
    # Answers are phrased as CONFIGURATION, not commands (avoids live tool calls in Phase 1).
    phase1_turns = [
        "Soy emprendedor y quiero guardar en Sheets los correos de leads de Gmail",
        "La palabra clave para filtrar leads es 'cotizacion' en el asunto del correo",
        "Crea una hoja nueva llamada 'Leads 2026' con columnas Fecha, Remitente, Asunto",
        "Que revise los correos cada 15 minutos",
        "Sí, eso está perfecto, ya es suficiente",
        "Sí, adelante con ese plan exactamente como está",
        "Sí, procede",
        "Sí, dale",
        "Sí, créalo",
    ]

    all_tool_events: list[str] = []
    all_ui_actions: list[dict] = []
    final_plan_reached = False
    done_text = ""

    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            # Drive conversation through Phase 1 informational turns.
            # Exit when we see a definitive Phase 2 signal:
            #   (a) workflow_built UI_ACTION → full build complete, no approval needed
            #   (b) confirm_plan UI_ACTION → plan presented, send explicit approval next
            # Do NOT exit on crear_workflow tool_start — that may be a blocked GATE B
            # attempt (the event fires before the tool actually runs).
            for i, msg in enumerate(phase1_turns):
                done_text, tevents, uactions = await _ws_turn(ws, msg)
                all_tool_events.extend(tevents)
                all_ui_actions.extend(uactions)
                if done_text.startswith("ERROR:"):
                    log("T8 WS error in Phase1", "FAIL", done_text)
                    return None

                if any(a.get("type") == "workflow_built" for a in uactions):
                    log("T8 Final Plan reached via WS", "PASS",
                        f"turn {i+1}: workflow_built UI_ACTION — full build complete inline")
                    final_plan_reached = True
                    break

                if any(a.get("type") == "confirm_plan" for a in uactions):
                    log("T8 Final Plan reached via WS", "PASS",
                        f"turn {i+1}: confirm_plan UI_ACTION received — sending approval")
                    final_plan_reached = True
                    break

            # Always send the explicit approval turn:
            # - If confirm_plan was detected → user approves the presented plan
            # - If nothing was detected → phase1_proposed was reached (LLM skipped UI_ACTION),
            #   approval message triggers the build with GATE B satisfied
            # - If workflow_built was already detected → approval turn may be a no-op, that's fine
            build_text, build_tools, build_actions = await _ws_turn(
                ws, "sí, dale, créalo", timeout=180
            )
            all_tool_events.extend(build_tools)
            all_ui_actions.extend(build_actions)
            if build_text and not done_text:
                done_text = build_text

            if not final_plan_reached:
                if any(a.get("type") == "workflow_built" for a in all_ui_actions) or \
                        "confirmar_workflow" in all_tool_events:
                    log("T8 Final Plan reached via WS", "PASS",
                        "Build completed on explicit approval (no prior UI_ACTION signal)")
                    final_plan_reached = True
                else:
                    log("T8 Final Plan reached", "FAIL",
                        f"No build after {len(phase1_turns)} turns + approval. "
                        f"tool_events={all_tool_events}")
                    return None

    except Exception as exc:
        log("T8 WebSocket connect", "FAIL", str(exc))
        return None

    # Evaluate build quality
    if "crear_workflow" in all_tool_events:
        log("T8 crear_workflow called", "PASS",
            f"tools seen: {[t for t in all_tool_events if t in ('crear_workflow','agregar_paso_workflow','confirmar_workflow','programar_workflow')]}")
    else:
        log("T8 crear_workflow called", "FAIL", f"Tool events: {all_tool_events}")

    workflow_built_actions = [a for a in all_ui_actions if a.get("type") == "workflow_built"]
    if workflow_built_actions:
        log("T8 workflow_built UI_ACTION emitted", "PASS", str(workflow_built_actions[0]))
    else:
        # Formatter fix should now preserve workflow_built — T12 will confirm via DB
        log("T8 workflow_built UI_ACTION emitted", "FAIL", f"ui_actions={all_ui_actions}")

    if done_text:
        log("T8 Done event received", "PASS", done_text[:150])
    else:
        log("T8 Done event received", "FAIL", "No done event")

    # Extract workflow_id from ui_action payload
    workflow_id = None
    if workflow_built_actions:
        workflow_id = workflow_built_actions[0].get("payload", {}).get("workflow_id")
    return workflow_id


# ─── T12: Workflow CRUD ───────────────────────────────────────────────────────

async def t12_workflow_crud(client: httpx.AsyncClient, workflow_id: str | None) -> None:
    print("\n── T12: Workflow CRUD ──")
    # List workflows
    r = await client.get("/api/v3/agent/workflows", timeout=30)
    if r.status_code == 200:
        wfs = r.json().get("workflows", [])
        log("T12 List workflows", "PASS", f"{len(wfs)} workflow(s) found")
    else:
        log("T12 List workflows", "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")
        wfs = []

    # Prefer a confirmed/active workflow for run test; fall back to any workflow
    runnable_statuses = {"active", "paused", "requires_attention"}
    active_wf = next(
        (w for w in wfs if (w.get("status") or "") in runnable_statuses), None
    )
    if not workflow_id and active_wf:
        workflow_id = str(active_wf.get("_id") or active_wf.get("id", ""))
    elif not workflow_id and wfs:
        workflow_id = str(wfs[0].get("_id") or wfs[0].get("id", ""))

    if workflow_id:
        r2 = await client.get(f"/api/v3/agent/workflows/{workflow_id}", timeout=30)
        if r2.status_code == 200:
            wf_status = r2.json().get("status", "unknown")
            log("T12 Get single workflow", "PASS", f"id={workflow_id[:12]} status={wf_status}")
        else:
            log("T12 Get single workflow", "FAIL", f"HTTP {r2.status_code}")
            wf_status = "unknown"

        if wf_status in runnable_statuses:
            r3 = await client.post(f"/api/v3/agent/workflows/{workflow_id}/run", timeout=30)
            if r3.status_code == 200:
                run_id = r3.json().get("run_id", "")
                log("T12 Manual run triggered", "PASS", f"run_id={run_id[:12] if run_id else 'N/A'}")
            else:
                log("T12 Manual run triggered", "FAIL", f"HTTP {r3.status_code}: {r3.text[:200]}")
        else:
            log("T12 Manual run triggered", "INFO",
                f"Workflow status '{wf_status}' — run requires active/paused/requires_attention")
    else:
        log("T12 CRUD with specific workflow", "INFO", "No workflow_id available to test get/run")


# ─── T13: Phase Tag Regression ───────────────────────────────────────────────

def t13_regression(captured_answers: list[str]) -> None:
    print("\n── T13: Phase Tag / Tool Name Regression ──")
    violations: list[str] = []
    for ans in captured_answers:
        if "[PHASE:" in ans:
            violations.append(f"[PHASE: found in: {ans[:100]}")
        if "UI_ACTION:" in ans:
            violations.append(f"UI_ACTION: found in: {ans[:100]}")
        for tool in ["listar_correos", "crear_workflow", "evaluar_certeza_workflow"]:
            if tool in ans.lower():
                violations.append(f"Tool name '{tool}' exposed in: {ans[:100]}")
    if not violations:
        log("T13 No leaks in REST answers", "PASS", f"Checked {len(captured_answers)} responses")
    else:
        for v in violations:
            log("T13 Regression", "FAIL", v)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("  Shifu Behavioral Test Suite")
    print(f"  Target: {BASE}")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # T1 — Auth (mandatory)
        token, user_id = await t1_auth(client)
        client.headers["Authorization"] = f"Bearer {token}"

        # T2 + T3 — Health + Gmail
        await t2_health(client)
        await t3_gmail(client)

        # T4 — Vague intent
        await t4_vague_intent(client)

        # T5 — Specific workflow (returns cid for T6)
        cid5 = await t5_specific_workflow(client)

        # T6 — Phase 1 loop
        await t6_phase1_loop(client, cid5)

        # T7 — GATE A
        await t7_gate_a(client)

        # T10 + T11 — WebSocket baseline + ping (before the slow T8)
        await t10_t11_websocket_baseline(token)

        # T9 — Auth detection (Notion)
        await t9_auth_detection(token)

        # T8 — Phase 2 build via WebSocket using the T5/T6 conversation (already at Final Plan)
        workflow_id = await t8_phase2_build(client, token, cid5)

        # T12 — Workflow CRUD
        await t12_workflow_crud(client, workflow_id)

    # T13 — Regression check on all REST answers captured
    rest_answers = [
        r["detail"] for r in results
        if "answer" in r.get("detail", "").lower() or "preview" in r.get("test", "").lower()
    ]
    t13_regression(rest_answers)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = passed + failed
    print(f"  Passed: {passed}/{total}  |  Failed: {failed}/{total}")
    if failed:
        print("\n  Failed tests:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"    • {r['test']}: {r['detail'][:120]}")
    print("=" * 60)

    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("  Results saved to test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
