"""
eval_memory.py — mide la memoria del agente en conversaciones largas y entre sesiones (al estilo LongMemEval, ICLR 2025).

    python scripts/eval_memory.py --label base --repeats 2 --max-usd 1.5
    python scripts/eval_memory.py --only larga_25 --repeats 1

Casos como datos en scripts/eval_memory_cases.json. Por caso: un usuario nuevo, una o varias sesiones (conversaciones).
- plant:  el usuario dice un dato (texto del caso).
- filler: N turnos de un USUARIO SIMULADO (mini agente) que reacciona a la respuesta real del agente, con la persona y el
          objetivo del caso: alarga la conversacion de forma natural (un guion fijo no sirve para 25 turnos).
Una sesion puede traer "now" (ISO UTC): se manda en cada turno de esa sesion (el backend necesita SHIFU_DEV_UI=1) para
probar compromisos con fecha sin esperar dias.
- probe:  pregunta con respuesta correcta (gold). Un juez dice correct | wrong | abstained y CITA la respuesta; el codigo
          valida que la cita exista (si no, cuenta como wrong).
Mide: precision por habilidad, por distancia en turnos (plant -> probe), dentro de la conversacion vs entre sesiones,
tokens de entrada del responder por turno, reintentos en las preguntas y costo. Anota una linea en doc/agente/BITACORA_MEMORIA.md.
"""
import argparse
import asyncio
import json
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_agent import JUDGE_EST_USD, ROOT, SPEND, Agent  # noqa: E402  (carga .env y el path del proyecto)

SIM_MODEL = JUDGE_MODEL = "gpt-4o-mini"
SIM_EST_USD = 0.0005
BITACORA = ROOT / "doc" / "agente" / "BITACORA_MEMORIA.md"

_SIM = """\
You are role-playing a REAL user chatting with an AI assistant of an automation platform (it connects apps and builds
automations). You are: {persona}. Your goal in this conversation: {goal}.
Write ONLY your next message (1-2 short sentences, in Spanish, in your style). Move the conversation forward: react to
what the assistant just said, answer its question if it asked one, or ask something new about your goal.
Do not say goodbye. NEVER write again any name, day, number or tool from these messages you already sent (the test
measures whether the assistant remembers them on its own; if it asks, answer vaguely, e.g. "la que te dije"):
{planted}"""

_JUDGE = """\
You grade whether an AI assistant REMEMBERED something correctly. You get the user's question, the correct answer
(gold) and the assistant's reply. Verdict:
- "correct": the reply states the gold information (same meaning; extra details are fine if they do not contradict it).
- "abstained": the reply says it does not know / was not told / asks the user for it, without inventing.
- "wrong": anything else (a different value, an invented value, or it does not answer).
When the gold describes HOW the reply must be (its language, its format, what it proposes first) instead of a fact to
state, "correct" means the reply itself IS that way, even if it never mentions the preference: a reply written in English
is correct for "the reply is written in English".
Copy into `quote` the exact words of the reply that support your verdict (empty only if the reply says nothing relevant)."""


class Grade(BaseModel):
    quote: str
    verdict: Literal["correct", "wrong", "abstained"]


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split()).strip(" .\"'“”«»")


async def simulate_user(oa: AsyncOpenAI, case: dict, history: list) -> str:
    convo = "\n".join(f"{r.upper()}: {t[:500]}" for r, t in history[-8:]) or "(start of the conversation)"
    planted = "\n".join(f"- {t['plant']}" for s in case["sessions"] for t in s["turns"] if "plant" in t) or "(none)"
    r = await oa.chat.completions.create(model=SIM_MODEL, temperature=0.8, messages=[
        {"role": "system", "content": _SIM.format(persona=case["persona"], goal=case["goal"], planted=planted)},
        {"role": "user", "content": f"Conversation so far:\n{convo}\n\nYour next message:"}])
    SPEND["usd"] += SIM_EST_USD
    return (r.choices[0].message.content or "").strip().strip('"')


async def grade(oa: AsyncOpenAI, question: str, gold: str, reply: str) -> tuple[str, str]:
    r = await oa.beta.chat.completions.parse(model=JUDGE_MODEL, temperature=0, response_format=Grade, messages=[
        {"role": "system", "content": _JUDGE},
        {"role": "user", "content": f"QUESTION: {question}\nGOLD: {gold}\nREPLY: {reply}"}])
    SPEND["usd"] += JUDGE_EST_USD
    g = r.choices[0].message.parsed
    # La cita tiene que existir (el juez no adivina). Puede venir partida con "..." entre trozos: cada trozo debe existir.
    parts = [p for p in re.split(r"\.\.\.|…", g.quote) if len(_norm(p)) >= 3]
    ok = bool(parts) and all(_norm(p) in _norm(reply) for p in parts)
    return (g.verdict if ok else "wrong"), g.quote


def _responder_tokens(usage: dict | None) -> int | None:
    calls = [c for c in (usage or {}).get("calls", []) if c.get("node") == "responder"]
    return calls[-1]["input"] if calls else None   # el ultimo intento (el que se entrego)


async def run_case(base: str, oa: AsyncOpenAI, case: dict, rep: int, sem: asyncio.Semaphore) -> list[dict]:
    rows, planted, turn_no = [], {}, 0
    async with sem:
        agent = Agent(base)
        await agent.register()
        for s_idx, session in enumerate(case["sessions"]):
            conv, history = str(uuid.uuid4()), []
            for t in session["turns"]:
                n = t.get("filler", 1)
                for _ in range(n):
                    if SPEND["limit"] and SPEND["usd"] >= SPEND["limit"]:
                        SPEND["stopped"] = True
                        return rows
                    text = t.get("plant") or t.get("probe") or await simulate_user(oa, case, history)
                    reply, q, err, usage = await agent.chat(conv, text, now=session.get("now"))  # reloj simulado de la sesion
                    turn_no += 1
                    SPEND["usd"] += (usage or {}).get("usd", 0)
                    history += [("user", text), ("assistant", reply)]
                    row = {"case": case["id"], "rep": rep, "session": s_idx + 1, "turn": turn_no, "kind":
                           "plant" if "plant" in t else "probe" if "probe" in t else "filler", "user": text, "reply": reply,
                           "error": err, "attempts": (q or {}).get("attempts", 1), "rejections": (q or {}).get("rejections", 0),
                           "failed_checks": [f["name"] for e in (q or {}).get("evals", []) for f in e["failed"]],
                           "responder_input_tokens": _responder_tokens(usage), "usd": (usage or {}).get("usd"),
                           "agent_version": (usage or {}).get("agent_version")}
                    if "plant" in t and t.get("key"):
                        planted[t["key"]] = (turn_no, s_idx + 1)
                    if "probe" in t:
                        verdict, quote = await grade(oa, text, t["gold"], reply) if reply else ("wrong", "")
                        src = planted.get(t.get("about"))
                        want = "abstained" if t["ability"] == "abstention" else "correct"
                        row.update(ability=t["ability"], gold=t["gold"], verdict=verdict, quote=quote, ok=verdict == want,
                                   distance=(turn_no - src[0]) if src else None,
                                   cross_session=(src[1] != s_idx + 1) if src else None)
                    rows.append(row)
                    print(f"  {case['id']} r{rep} s{s_idx + 1} t{turn_no} {row['kind']}"
                          + (f" -> {row['verdict']} {'✓' if row['ok'] else '✗'}" if row["kind"] == "probe" else ""), flush=True)
    return rows


def _bucket(d):
    return "?" if d is None else "1-5" if d <= 5 else "6-15" if d <= 15 else "16+"


def summarize(rows: list[dict]) -> dict:
    probes = [r for r in rows if r["kind"] == "probe"]
    rate = lambda xs: f"{sum(x['ok'] for x in xs)}/{len(xs)}" if xs else "-"  # noqa: E731
    by = lambda key: {k: rate(v) for k, v in sorted(_group(probes, key).items())}  # noqa: E731
    tok = defaultdict(list)
    for r in rows:
        if r["responder_input_tokens"]:
            tok[r["turn"]].append(r["responder_input_tokens"])
    last = max(tok) if tok else None
    return {
        "probes": rate(probes),
        "by_ability": by(lambda r: r["ability"]),
        "by_distance": by(lambda r: _bucket(r["distance"])),
        "by_scope": by(lambda r: "entre sesiones" if r["cross_session"] else "misma conversacion" if r["cross_session"] is False else "?"),
        "probe_attempts": round(sum(r["attempts"] for r in probes) / max(len(probes), 1), 2),
        "probe_no_fabrication_rejections": sum("no_fabrication" in r["failed_checks"] for r in probes),
        "responder_tokens_turn1": round(sum(tok[1]) / len(tok[1])) if tok.get(1) else None,
        "responder_tokens_last_turn": f"t{last}: {round(sum(tok[last]) / len(tok[last]))}" if last else None,
        "errors": sum(bool(r["error"]) for r in rows),
        "agent_version": ", ".join(sorted({r["agent_version"] for r in rows if r.get("agent_version")})) or "?",
        "spent_usd_est": round(SPEND["usd"], 3), "stopped_by_budget": SPEND["stopped"],
    }


def _group(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out


def log_run(label: str, s: dict, path: Path):
    if not BITACORA.exists():
        BITACORA.write_text(
            "# Bitácora de memoria del agente\n\n"
            "Corridas de `scripts/eval_memory.py` (casos en `scripts/eval_memory_cases.json`). La línea se agrega sola; las "
            "notas de revisión a mano van en `BITACORA.md`. Precisión = preguntas acertadas / preguntas (abstención correcta = "
            "decir que no sabe).\n\n"
            "| fecha | versión | etiqueta | precisión | por habilidad | por distancia (turnos) | misma conv. / entre sesiones | "
            "tokens responder t1 → último | rechazos no_fabrication en preguntas | USD | archivo |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    fmt = lambda d: ", ".join(f"{k} {v}" for k, v in d.items())  # noqa: E731
    with open(BITACORA, "a", encoding="utf-8") as fh:
        fh.write(f"| {datetime.now():%Y-%m-%d %H:%M} | {s['agent_version']} | {label} | {s['probes']} | {fmt(s['by_ability'])} | "
                 f"{fmt(s['by_distance'])} | {fmt(s['by_scope'])} | {s['responder_tokens_turn1']} → {s['responder_tokens_last_turn']} | "
                 f"{s['probe_no_fabrication_rejections']} | {s['spent_usd_est']} | {path.name} |\n")
    print(f"Anotado en {BITACORA.relative_to(ROOT)}")


async def main(args):
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    SPEND.update(limit=args.max_usd)
    oa, sem = AsyncOpenAI(), asyncio.Semaphore(args.concurrency)
    print(f"Memoria '{args.label}' en {args.base}: {len(cases)} casos x {args.repeats}")
    jobs = [run_case(args.base, oa, c, rep, sem) for rep in range(1, args.repeats + 1) for c in cases]
    rows = [r for chunk in await asyncio.gather(*jobs) for r in chunk]
    s = summarize(rows)
    path = ROOT / "eval_results" / f"mem_{args.label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"label": args.label, "summary": s, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + json.dumps(s, ensure_ascii=False, indent=1))
    print("\nFallas:")
    for r in rows:
        if r["kind"] == "probe" and not r["ok"]:
            print(f"  {r['case']} r{r['rep']} t{r['turn']} [{r['ability']}, dist {r['distance']}] {r['verdict']}\n"
                  f"     P: {r['user']}\n     gold: {r['gold']}\n     R: {r['reply'][:300]}")
    print(f"\nGuardado en {path}")
    log_run(args.label, s, path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5001")
    ap.add_argument("--label", default="mem")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--cases", default=str(ROOT / "scripts" / "eval_memory_cases.json"))
    ap.add_argument("--only", default="")
    ap.add_argument("--max-usd", type=float, default=1.5)
    asyncio.run(main(ap.parse_args()))
