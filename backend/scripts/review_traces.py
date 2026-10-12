"""
review_traces.py — lee el registro de turnos (logs/agent_traces/*.jsonl) y muestra, por turno, como actuo CADA mini agente.

    python scripts/review_traces.py                      # los 3 ultimos turnos del archivo mas reciente
    python scripts/review_traces.py --last 10 --anomalies  # solo turnos con algo raro
    python scripts/review_traces.py --conv 1a2b3c4d      # una conversacion (prefijo del id)
    python scripts/review_traces.py --full               # mensajes completos de cada llamada (lo que recibio el modelo)

Marca como anomalia: llamadas que fallaron, modelos sin precio, jueces que se contradicen (severidad "major" con una nota
que dice que esta bien), turnos que agotaron los reintentos y respuestas vacias.
Para activar el registro: SHIFU_TRACE_LOG=1 en el .env del servidor.
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
_POSITIVE = re.compile(r"\b(accurate|correct|appropriate|acceptable|properly|valid|meets|satisf)", re.I)
_NEGATIVE = re.compile(r"\b(however|but|fails?|lacks?|does not|doesn't|not |missing|invent|fabricat|ignor)", re.I)


def load(args) -> list[dict]:
    files = sorted(glob.glob(str(Path(args.dir) / "*.jsonl"))) if not args.file else [args.file]
    turns = [json.loads(line) for f in files[-2:] for line in open(f, encoding="utf-8") if line.strip()]
    if args.conv:
        turns = [t for t in turns if t.get("conversation_id", "").startswith(args.conv)]
    return turns[-args.last:]


def verdicts(e: dict) -> list[dict]:
    """Salida estructurada de una llamada (los registros viejos solo traen el JSON como texto en "output")."""
    if e.get("structured_output"):
        return [x for x in e["structured_output"] if isinstance(x, dict)]
    out = (e.get("output") or "").strip()
    if out.startswith("{"):
        try:
            return [json.loads(out)]
        except ValueError:
            return []
    return []


def anomalies(t: dict) -> list[str]:
    out = []
    llms = [e for e in t["events"] if e["kind"] == "llm"]
    for e in llms:
        who = next((x for x in e.get("tags", []) if x.startswith("judge:")), e.get("node"))
        if e.get("error"):
            out.append(f"la llamada de {who} fallo: {e['error'][:140]}")
        if e.get("usage") and e["usage"].get("usd") is None:
            out.append(f"{who} uso un modelo sin precio ({e['usage'].get('model')}): el costo no esta contado")
        for so in verdicts(e):
            if so.get("severity") == "major" and _POSITIVE.search(so.get("note", "")) and not _NEGATIVE.search(so.get("note", "")):
                out.append(f"{who} marco MAJOR pero su nota dice que esta bien: \"{so['note'][:120]}\"")
    q = t.get("quality") or {}
    if q.get("final") == "exhausted":
        out.append(f"se agotaron los reintentos ({q.get('attempts')} intentos) y se entrego igual")
    if not t.get("reply") and not t.get("error"):
        out.append("el turno termino sin respuesta")
    if t.get("error"):
        out.append(f"el turno fallo: {t['error'][:160]}")
    return out


def show(t: dict, full: bool) -> None:
    u, q = t.get("usage") or {}, t.get("quality") or {}
    print("=" * 110)
    print(f"{t['ts']} | conv {t['conversation_id'][:8]} | agente {t.get('agent_id')} | {t['total_ms'] / 1000:.1f}s | "
          f"${u.get('usd', 0):.4f} | {q.get('attempts', 1)} intento(s), {q.get('rejections', 0)} rechazo(s)")
    print(f"USUARIO: {t['user_text']}")
    for e in t["events"]:
        k = e["kind"]
        if k == "node":
            print(f"  [{e['t_ms'] / 1000:5.1f}s] nodo {e['node']:<20} {e['ms']}ms  {e['output'][:150].replace(chr(10), ' ')}")
        elif k == "retry_reset":
            print(f"  [{e['t_ms'] / 1000:5.1f}s] -- el responder reescribe (intento {e['attempt']}) --")
        elif k == "llm":
            who = next((x for x in e.get("tags", []) if x.startswith("judge:")), e.get("node"))
            us = e.get("usage") or {}
            head = (f"  [{e['t_ms'] / 1000:5.1f}s] LLM  {who:<22} {str(e.get('model')):<20} intento {e['attempt']}  "
                    f"{us.get('input', '?')}in/{us.get('output', '?')}out ${(us.get('usd') or 0):.5f} {e['ms']}ms")
            print(head + ("  ERROR" if e.get("error") else ""))
            vs = verdicts(e)
            for so in vs:
                if "severity" in so:
                    print(f"           veredicto: {so['severity']:<5} | {so.get('note', '')[:170]}" + (f" | feedback: {so['feedback'][:120]}" if so.get("feedback") else ""))
                else:
                    print(f"           salida estructurada: {json.dumps(so, ensure_ascii=False)[:200]}")
            if e.get("output") and not vs:
                print(f"           respuesta: {e['output'][:200].replace(chr(10), ' ')}")
            if full:
                for m in e["messages"]:
                    print(f"           --- {m['role']} ---\n{m['content']}")
    print(f"RESPUESTA FINAL: {(t.get('reply') or '(vacia)')[:400]}")
    flags = anomalies(t)
    print("ANOMALIAS: " + ("ninguna" if not flags else "\n  - " + "\n  - ".join(flags)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "logs" / "agent_traces"))
    ap.add_argument("--file", default="")
    ap.add_argument("--conv", default="")
    ap.add_argument("--last", type=int, default=3)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--anomalies", action="store_true", help="solo turnos con anomalias")
    a = ap.parse_args()
    turns = load(a)
    if a.anomalies:
        turns = [t for t in turns if anomalies(t)]
    if not turns:
        print("No hay turnos registrados (¿SHIFU_TRACE_LOG=1 en el servidor?).")
    for t in turns:
        show(t, a.full)
