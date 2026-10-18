"""Ejecución de las evals. Los dos modos hablan HTTP con la app real (`/chat`, `/resume`, `/history`, `/memories`):
- falso: `create_app` en proceso con un modelo guionizado por caso y búsquedas falsas (0 tokens, corre en la suite);
- real: `scripts/eval_server.py` en 127.0.0.1:8001, base temporal y tope duro (lo arranca `scripts/run_evals.py`).

Cada caso del dataset (`dataset.jsonl`, una línea JSON):
  id, category, modes ["fake","real"], noise ("web" si interviene web_search: ±30 % de ruido en tokens),
  settings {VARIABLE: valor} (nombres de variables de entorno), est_tokens (estimación real), margin (peor caso real),
  steps: [{"chat": texto, "pad": n, "new_thread": bool, "status": 200} | {"resume": "approve"|"reject"}],
  expect: ver `checks.py`, fake: {"model": [...], "search": texto}.
Un elemento de fake.model es un texto o {"text": ..., "tools": [{"name", "args"}], "tokens": n}."""
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from dataclasses import fields, replace
from pathlib import Path

from evals.checks import _ANY_URL, evaluate

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "dataset.jsonl"
RESULTS_DIR = ROOT / "evals" / "resultados"
# el mismo texto que manda la UI al rechazar una tarjeta (packs/ui/index.html, REJECT_MSG)
REJECT_MSG = "The user declined this action. Do not run it again; answer without it."
PAD = "Detalle adicional sin importancia para la pregunta. "


# ------------------------------------------------------------------ dataset
def load_dataset(path: Path = DATASET, mode: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [c["id"] for c in cases]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"ids repetidos en el dataset: {sorted(dup)}")
    return [c for c in cases if mode is None or mode in c.get("modes", ["fake", "real"])]


def dataset_sha(path: Path = DATASET) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def message_text(step: dict) -> str:
    text = step["chat"]
    if step.get("pad"):  # mensaje largo: relleno hasta `pad` caracteres
        text = (text + " " + PAD * (step["pad"] // len(PAD) + 1))[: step["pad"]]
    return text


# ------------------------------------------------------------------ SSE
def parse_sse(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


# ------------------------------------------------------------------ un caso
def run_case(client, case: dict, run_tag: str, real: bool = False) -> dict:
    user = f"eval-{run_tag}-{case['id']}"
    thread = f"eval-{uuid.uuid4().hex[:10]}"
    threads = [thread]
    steps: list[dict] = []
    last_interrupts: list[dict] = []
    started = time.monotonic()
    for st in case["steps"]:
        if st.get("new_thread"):
            thread = f"eval-{uuid.uuid4().hex[:10]}"
            threads.append(thread)
        if real:
            client.post("/_eval/margin", params={"n": case.get("margin", 30000)})
        if "chat" in st:
            path, body, decision = "/chat", {"message": message_text(st), "thread_id": thread, "user_id": user,
                                             "effort": st.get("effort")}, None
        else:
            decision = st["resume"]
            dec = {"type": "approve"} if decision == "approve" else {"type": "reject", "message": REJECT_MSG}
            path, body = "/resume", {"thread_id": thread, "user_id": user, "decisions": [dec]}
        before = len(client.get("/_eval/turns", params={"thread_id": thread}).json()["turns"])
        t0 = time.monotonic()
        resp = client.post(path, json=body)
        seconds = round(time.monotonic() - t0, 2)
        events = parse_sse(resp.text) if resp.status_code == 200 else []
        turns = client.get("/_eval/turns", params={"thread_id": thread}).json()["turns"][before:]
        steps.append({"kind": path[1:], "status_code": resp.status_code, "expect_status": st.get("status", 200),
                      "decision": decision, "prev_interrupts": last_interrupts if decision else [],
                      "events": events, "seconds": seconds,
                      "tokens": sum(t.get("tokens_total", 0) for t in turns),
                      "detail": None if resp.status_code == 200 else resp.text[:300]})
        last_interrupts = [e for e in events if e["type"] == "interrupt"]
    history = client.get(f"/history/{thread}").json().get("messages", [])
    answer = next((m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"), "")
    evidence = "\n".join(client.get(f"/_eval/evidence/{t}").json()["text"] for t in threads)
    mems = client.get(f"/memories/{user}").json().get("memories", [])
    return {"steps": steps, "answer": answer, "evidence": evidence, "memories": [m["text"] for m in mems],
            "tokens": sum(s["tokens"] for s in steps), "seconds": round(time.monotonic() - started, 2)}


def summarize_case(case: dict, tr: dict) -> dict:
    checks = evaluate(tr, case)
    tools = [{"name": e.get("name"), "status": e.get("status")} for s in tr["steps"] for e in s["events"]
             if e["type"] == "tool_end"]
    return {"id": case["id"], "category": case.get("category"), "noise": case.get("noise"),
            "passed": all(c["ok"] for c in checks), "checks": checks, "tokens": tr["tokens"],
            "seconds": tr["seconds"], "tools": tools, "answer": tr["answer"][:2000],
            # para diagnosticar urls_backed sin la base temporal (que se borra): las URLs de la evidencia, no su texto
            "evidence_urls": sorted(set(_ANY_URL.findall(tr["evidence"])))[:50],
            "steps": [{k: s[k] for k in ("kind", "status_code", "tokens", "seconds", "detail")} for s in tr["steps"]]}


# ------------------------------------------------------------------ modo falso
def _fake_settings(case: dict):
    """_settings de los tests con los overrides del caso (nombres de variables -> campos de Settings)."""
    from conftest import _settings

    base = _settings()
    names = {f.name for f in fields(base)}
    over = {}
    for env, value in case.get("settings", {}).items():
        name = env.lower()
        if name not in names:
            raise ValueError(f"{case['id']}: {env} no es una variable de Settings")
        current = getattr(base, name)
        if isinstance(current, bool):
            over[name] = str(value).strip().lower() in ("1", "true", "yes", "si", "sí")
        elif isinstance(current, (int, float)):
            over[name] = type(current)(value)
        else:
            over[name] = value
    return replace(base, **over)


def _scripted_model(items: list):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    from conftest import FakeChat

    class Scripted(FakeChat):
        """Respuestas en orden, compartidas por el agente y sus subagentes; cada una con sus tokens."""

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            item = next(self.messages)
            item = {"text": item} if isinstance(item, str) else item
            text = item.get("text", "")
            for piece in re.findall(r"\S+\s*", text):
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
                if run_manager:
                    run_manager.on_llm_new_token(piece, chunk=chunk)
                yield chunk
            calls = [{"name": t["name"], "args": json.dumps(t.get("args", {})), "id": f"c{i}-{uuid.uuid4().hex[:6]}",
                      "index": i, "type": "tool_call_chunk"} for i, t in enumerate(item.get("tools", []))]
            n = item.get("tokens", 0)
            usage = {"input_tokens": n, "output_tokens": 0, "total_tokens": n}
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=calls, usage_metadata=usage,
                                                             chunk_position="last"))

    return Scripted(messages=iter(list(items)))


def _fake_client(case: dict, meter):
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from assistant.core.agent import build_agent
    from assistant.core.server import create_app
    from assistant.core.tools import build_tools
    from conftest import FakeSearch
    from evals.harness import install

    fake = case.get("fake", {})

    class Search(FakeSearch):
        def __call__(self, query, settings):
            self.calls.append(query)
            return (fake["search"] if "search" in fake else f"Resultado falso para {query}"), self.engine

    s = _fake_settings(case)
    llm = _scripted_model(fake.get("model", []))
    store = InMemoryStore()
    agent = build_agent(llm, build_tools(llm, s, search_fn=Search()), s, checkpointer=InMemorySaver(), store=store)
    app = create_app(agent=agent, settings=s, store=store)
    install(app, meter, lambda: agent, s)
    return TestClient(app)


def run_fake(cases: list[dict]) -> list[dict]:
    from evals.harness import Meter

    tests_dir = str(ROOT / "tests")
    if tests_dir not in sys.path:  # FakeChat, FakeSearch y _settings salen de tests/conftest.py
        sys.path.insert(0, tests_dir)
    out = []
    with Meter() as meter:
        for case in cases:
            with _fake_client(case, meter) as client:
                out.append(summarize_case(case, run_case(client, case, "fake")))
    return out


# ------------------------------------------------------------------ modo real
REAL_PORT = 8001


def real_plan(cases: list[dict], cap: int) -> dict:
    messages = sum(len(c["steps"]) for c in cases)
    return {"cases": len(cases), "messages": messages, "turn_token_cap": cap,
            "estimate": sum(c.get("est_tokens", 0) for c in cases),
            "worst": sum(c.get("margin", 30000) for c in cases)}


def _groups(cases: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Casos agrupados por settings: cada grupo es un arranque del servidor (misma base temporal)."""
    out: dict[str, tuple[dict, list[dict]]] = {}
    for c in cases:
        key = json.dumps(c.get("settings", {}), sort_keys=True)
        out.setdefault(key, (c.get("settings", {}), []))[1].append(c)
    return list(out.values())


def _wait_up(client, proc, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"el servidor de evals terminó al arrancar (código {proc.returncode})")
        try:
            if client.get("/health").status_code == 200:
                return
        except Exception:  # noqa: BLE001 - aún no escucha
            pass
        time.sleep(0.5)
    raise RuntimeError("el servidor de evals no respondió en :8001")


def run_real(cases: list[dict], cap: int, hard_cap: int, log_path: Path, db: str) -> list[dict]:
    import os

    import httpx

    assert db.startswith("assistant_ux_tmp_"), "solo bases temporales"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = []
    client = httpx.Client(base_url=f"http://127.0.0.1:{REAL_PORT}", timeout=900)
    run_tag = time.strftime("%H%M%S")
    for settings, group in _groups(cases):
        cmd = [sys.executable, str(ROOT / "scripts" / "eval_server.py"), "--db", db, "--log", str(log_path),
               "--cap", str(settings.get("TURN_TOKEN_CAP", cap)), "--hard-cap", str(hard_cap)]
        cmd += [a for k, v in settings.items() if k != "TURN_TOKEN_CAP" for a in ("--set", f"{k}={v}")]
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
        try:
            _wait_up(client, proc)
            for case in group:
                state = client.get("/_eval").json()
                if state["spent"] + case.get("margin", 30000) > hard_cap:
                    print(f"  {case['id']}: sin presupuesto (gastado {state['spent']}), no se corre", flush=True)
                    out.append({"id": case["id"], "category": case.get("category"), "noise": case.get("noise"),
                                "passed": None, "skipped": "sin presupuesto", "checks": [], "tokens": 0})
                    continue
                res = summarize_case(case, run_case(client, case, run_tag, real=True))
                print(f"  {case['id']}: {'ok' if res['passed'] else 'FALLA'} · {res['tokens']} tokens · "
                      f"{res['seconds']} s", flush=True)
                out.append(res)
        finally:
            proc.terminate()
            proc.wait(timeout=30)
    return out


def drop_temp_db(db: str) -> list[str]:
    """Borra la base temporal del clúster de .env y devuelve las bases que quedan."""
    from pymongo import MongoClient

    from assistant.core.config import Settings

    assert db.startswith("assistant_ux_tmp_"), "solo bases temporales"
    client = MongoClient(Settings.from_env().mongodb_uri)
    client.drop_database(db)
    return client.list_database_names()


# ------------------------------------------------------------------ resultados
def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def build_results(mode: str, cases_out: list[dict], extra: dict | None = None) -> dict:
    ran = [c for c in cases_out if c.get("passed") is not None]
    return {"meta": {"mode": mode, "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "commit": git_commit(),
                     "dataset_sha": dataset_sha(), **(extra or {})},
            "summary": {"cases": len(cases_out), "passed": sum(1 for c in ran if c["passed"]),
                        "failed": sum(1 for c in ran if not c["passed"]),
                        "skipped": len(cases_out) - len(ran), "tokens": sum(c.get("tokens", 0) for c in cases_out)},
            "cases": cases_out}


def save_results(results: dict, directory: Path = RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}_{results['meta']['mode']}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
