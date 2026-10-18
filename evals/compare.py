"""Comparación de dos corridas de evals, caso por caso (nunca por promedio).

- Regresión: un check que pasaba y ahora falla, un caso que pasaba y ya no corrió, o tokens por encima del ruido.
- Ruido en tokens: ±30 % en los casos con web_search (`noise: "web"`; la búsqueda hospedada varió hasta ese punto en la
  validación E2E) y ±5 % en el resto. Dentro del ruido no se marca nada; por debajo se anota como mejora.
- La latencia solo se informa."""
NOISE = {"web": 0.30, None: 0.05}


def _by_id(results: dict) -> dict[str, dict]:
    return {c["id"]: c for c in results.get("cases", [])}


def compare(base: dict, new: dict) -> dict:
    a, b = _by_id(base), _by_id(new)
    regressions, improvements, notes = [], [], []
    for cid, old in a.items():
        cur = b.get(cid)
        if cur is None:
            notes.append({"id": cid, "what": "el caso ya no está en la corrida nueva"})
            continue
        if cur.get("passed") is None or old.get("passed") is None:
            if old.get("passed") and cur.get("passed") is None:
                regressions.append({"id": cid, "what": f"no se corrió ({cur.get('skipped')})"})
            continue
        old_checks = {c["name"]: c["ok"] for c in old.get("checks", [])}
        for c in cur.get("checks", []):
            if old_checks.get(c["name"]) and not c["ok"]:
                regressions.append({"id": cid, "what": f"check {c['name']} pasó a fallar: {c['detail']}"})
            elif old_checks.get(c["name"]) is False and c["ok"]:
                improvements.append({"id": cid, "what": f"check {c['name']} ahora pasa"})
        t0, t1 = old.get("tokens") or 0, cur.get("tokens") or 0
        if t0 and t1:
            noise = NOISE.get(cur.get("noise") or old.get("noise"), NOISE[None])
            delta = (t1 - t0) / t0
            row = {"id": cid, "what": f"tokens {t0} → {t1} ({delta:+.1%}, ruido ±{noise:.0%})"}
            if delta > noise:
                regressions.append(row)
            elif delta < -noise:
                improvements.append(row)
    for cid in b.keys() - a.keys():
        notes.append({"id": cid, "what": "caso nuevo, sin línea base"})
    return {"regressions": regressions, "improvements": improvements, "notes": notes,
            "base": base.get("meta", {}), "new": new.get("meta", {})}


def render(report: dict) -> str:
    lines = [f"Base: {report['base'].get('date')} ({report['base'].get('mode')}, {report['base'].get('commit')})",
             f"Nueva: {report['new'].get('date')} ({report['new'].get('mode')}, {report['new'].get('commit')})", ""]
    for title, key in (("Regresiones", "regressions"), ("Mejoras", "improvements"), ("Notas", "notes")):
        lines.append(f"{title}: {len(report[key])}")
        lines += [f"  - {r['id']}: {r['what']}" for r in report[key]]
    return "\n".join(lines)
