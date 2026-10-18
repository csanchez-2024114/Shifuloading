"""Evaluadores simples en código, sin LLM. Cada uno recibe la transcripción de un caso (`runner.run_case`) y lo que
espera el dataset, y devuelve (ok, detalle). Ninguno aplica si su clave no está en `expect`, salvo los que valen
siempre: códigos HTTP, turno completo y chip veraz."""
import re

from assistant.core.agent import tool_ran
from assistant.core.citations import normalize_url, urls

_ANY_URL = re.compile(r"https?://[^\s)\]\"'>]+")


def _events(tr: dict, kind: str) -> list[dict]:
    return [e for step in tr["steps"] for e in step["events"] if e["type"] == kind]


def _ran(tr: dict) -> dict[str, list[str]]:
    """herramienta -> estados de sus tool_end en todo el caso."""
    out: dict[str, list[str]] = {}
    for e in _events(tr, "tool_end"):
        out.setdefault(e.get("name"), []).append(e.get("status"))
    return out


def _was_cut(step: dict) -> bool:
    """El turno terminó por TURN_TOKEN_CAP o TURN_MAX_SECONDS (el aviso nombra la variable)."""
    text = "".join(e.get("text", "") for e in step["events"] if e["type"] == "token")
    return "TURN_TOKEN_CAP" in text or "TURN_MAX_SECONDS" in text


def http(tr: dict, case: dict) -> tuple[bool, str]:
    bad = [f"paso {i}: {s['status_code']} (esperado {s['expect_status']})" for i, s in enumerate(tr["steps"], 1)
           if s["status_code"] != s["expect_status"]]
    return not bad, "; ".join(bad) or "ok"


def completed(tr: dict, case: dict) -> tuple[bool, str]:
    """Cada stream abierto termina en done y sin evento error (salvo que el caso espere el error)."""
    if case["expect"].get("error"):
        return bool(_events(tr, "error")), "se esperaba un evento error"
    bad = []
    for i, step in enumerate(tr["steps"], 1):
        if step["status_code"] != 200:
            continue
        types = [e["type"] for e in step["events"]]
        if "error" in types or not types or types[-1] != "done":
            bad.append(f"paso {i}: {types[-3:]}")
    return not bad, "; ".join(bad) or "ok"


def interrupt(tr: dict, case: dict) -> tuple[bool, str]:
    names = [r.get("name") for e in _events(tr, "interrupt") for r in e.get("action_requests", [])]
    want = case["expect"]["interrupt"]
    return want in names, f"tarjetas: {names}"


def tools_used(tr: dict, case: dict) -> tuple[bool, str]:
    ran = _ran(tr)
    missing = [t for t in case["expect"]["tools_used"] if "success" not in ran.get(t, [])]
    return not missing, f"sin ejecutar: {missing}; corridas: {ran}" if missing else "ok"


def tools_not_used(tr: dict, case: dict) -> tuple[bool, str]:
    ran = _ran(tr)
    used = [t for t in case["expect"]["tools_not_used"] if "success" in ran.get(t, [])]
    return not used, f"se ejecutaron: {used}" if used else "ok"


def tools_skipped(tr: dict, case: dict) -> tuple[bool, str]:
    ran = _ran(tr)
    bad = [t for t in case["expect"]["tools_skipped"] if not ran.get(t) or "success" in ran[t]]
    return not bad, f"no quedaron como no realizadas: {bad}; estados: {ran}" if bad else "ok"


def chip_truthful(tr: dict, case: dict) -> tuple[bool, str]:
    """El chip nunca dice "hecho" de algo que no corrió: cada tool_start tiene su tool_end, un "success" corresponde a
    una salida que de verdad se ejecutó, y una herramienta rechazada en la tarjeta no queda como "success"."""
    starts = {e.get("id"): e.get("name") for e in _events(tr, "tool_start")}
    ends = {e.get("id"): e for e in _events(tr, "tool_end")}
    # un turno cortado por el tope deja chips abiertos y la UI los marca como abortados (index.html, "abortados")
    cut = {e.get("id") for step in tr["steps"] if _was_cut(step) for e in step["events"] if e["type"] == "tool_start"}
    bad = [f"sin tool_end: {name}" for cid, name in starts.items() if cid not in ends and cid not in cut]
    bad += [f"{e.get('name')}: success con salida no ejecutada" for e in ends.values()
            if e.get("status") == "success" and not tool_ran(e.get("output") or "")]
    rejected = {r.get("name") for step in tr["steps"] if step.get("decision") == "reject"
                for e in step["prev_interrupts"] for r in e.get("action_requests", [])}
    bad += [f"{e.get('name')}: rechazada pero con estado {e.get('status')}" for e in ends.values()
            if e.get("name") in rejected and e.get("status") == "success"]
    return not bad, "; ".join(bad) or "ok"


def rejected(tr: dict, case: dict) -> tuple[bool, str]:
    """Tras rechazar la tarjeta, la herramienta no corrió y el turno igual respondió."""
    steps = [s for s in tr["steps"] if s.get("decision") == "reject"]
    if not steps:
        return False, "el caso no rechazó ninguna tarjeta"
    names = {r.get("name") for s in steps for e in s["prev_interrupts"] for r in e.get("action_requests", [])}
    ran = _ran(tr)
    bad = [n for n in names if "success" in ran.get(n, [])]
    if bad:
        return False, f"corrió pese al rechazo: {bad}"
    return bool(tr["answer"].strip()), "ok" if tr["answer"].strip() else "sin respuesta tras el rechazo"


def _matches(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.I | re.S)]


def contains(tr: dict, case: dict) -> tuple[bool, str]:
    pats = case["expect"]["contains"]
    missing = [p for p in pats if p not in _matches(pats, tr["answer"])]
    return not missing, f"no aparece: {missing}" if missing else "ok"


def not_contains(tr: dict, case: dict) -> tuple[bool, str]:
    found = _matches(case["expect"]["not_contains"], tr["answer"])
    return not found, f"aparece: {found}" if found else "ok"


def urls_backed(tr: dict, case: dict) -> tuple[bool, str]:
    """Cada URL de la respuesta final (dominio + ruta) aparece en lo que devolvieron las herramientas o en lo que
    escribió el usuario."""
    # en la evidencia vale cualquier URL, también entre paréntesis (citations.urls las salta para no duplicar enlaces)
    backed = {normalize_url(u) for u in _ANY_URL.findall(tr["evidence"])}
    loose = [u for u in urls(tr["answer"]) if normalize_url(u) not in backed]
    return not loose, f"sin respaldo: {loose}" if loose else f"ok ({len(urls(tr['answer']))} URL)"


def max_tokens(tr: dict, case: dict) -> tuple[bool, str]:
    cap = case["expect"]["max_tokens"]
    return tr["tokens"] <= cap, f"{tr['tokens']} de {cap}"


def memories(tr: dict, case: dict) -> tuple[bool, str]:
    exp = case["expect"]["memories"]
    texts = tr["memories"]
    joined = "\n".join(texts)
    bad = []
    if "count" in exp and len(texts) != exp["count"]:
        bad.append(f"{len(texts)} recuerdos (esperados {exp['count']})")
    bad += [f"falta: {p}" for p in exp.get("contains", []) if not _matches([p], joined)]
    bad += [f"no debía estar: {p}" for p in exp.get("not_contains", []) if _matches([p], joined)]
    return not bad, "; ".join(bad) or f"ok ({len(texts)})"


ALWAYS = {"http": http, "completed": completed, "chip_truthful": chip_truthful}
OPTIONAL = {"interrupt": interrupt, "tools_used": tools_used, "tools_not_used": tools_not_used,
            "tools_skipped": tools_skipped, "rejected": rejected, "contains": contains, "not_contains": not_contains,
            "urls_backed": urls_backed, "max_tokens": max_tokens, "memories": memories}


def evaluate(tr: dict, case: dict) -> list[dict]:
    exp = case.get("expect", {})
    run = dict(ALWAYS)
    run.update({k: f for k, f in OPTIONAL.items() if k in exp and exp[k] not in (False, None)})
    if tr["steps"] and all(s["status_code"] != 200 for s in tr["steps"]):
        run.pop("completed", None)  # nada se abrió (p. ej. 413): no hay stream que terminar
    out = []
    for name, fn in run.items():
        ok, detail = fn(tr, case)
        out.append({"name": name, "ok": bool(ok), "detail": detail})
    return out
