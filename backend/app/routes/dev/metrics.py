"""SOLO desarrollo (se monta con SHIFU_DEV_UI=1): panel de metricas del agente por version y por dia.
Lee lo que ya se guarda (chat_messages.usage/quality, message_feedback, action_log); no escribe nada.
La agregacion es una funcion pura sobre listas de documentos para poder probarla sin Mongo."""

import math
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.constants import Collections
from app.database import get_current_user, get_db

router = APIRouter()

NO_VERSION = "(sin version)"
MAX_DOCS = 20_000  # tope por coleccion: un panel de desarrollo no debe leer toda la historia; si se alcanza, se avisa
_DOWN_LIMIT = 20


def _day(d: Any) -> str:
    return d.strftime("%Y-%m-%d") if isinstance(d, datetime) else (str(d)[:10] if d else "?")


def _k(d: Any) -> datetime:
    """Clave ordenable: Mongo devuelve fechas con o sin zona segun el cliente, y mezclarlas lanza TypeError."""
    return d.replace(tzinfo=None) if isinstance(d, datetime) else datetime.min


def _p95(values: list[float]) -> float:
    """Rango mas cercano: con pocos datos devuelve el mayor, que es lo honesto."""
    if not values:
        return 0.0
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def _row(replies: list[dict], feedback: list[dict], actions: list[dict]) -> dict:
    """Una fila de metricas para un grupo (una version o un dia)."""
    usd = [float((m.get("usage") or {}).get("usd") or 0) for m in replies]
    quals = [m.get("quality") or {} for m in replies]
    attempts = [q["attempts"] for q in quals if q.get("attempts")]
    n = len(replies)
    up = sum(1 for f in feedback if f.get("rating") == "up")
    down = sum(1 for f in feedback if f.get("rating") == "down")
    failing = Counter(
        c.get("name") or "?" for q in quals for e in q.get("evals") or [] for c in e.get("failed") or []
    )
    ok = sum(1 for a in actions if a.get("ok"))
    return {
        "replies": n,
        "usd_total": round(sum(usd), 4),
        "usd_avg": round(sum(usd) / n, 5) if n else 0.0,
        "usd_p95": round(_p95(usd), 5),
        "attempts_avg": round(sum(attempts) / len(attempts), 2) if attempts else None,
        "rejection_rate": _pct(sum(1 for q in quals if (q.get("rejections") or 0) > 0), n),
        "exhausted_rate": _pct(sum(1 for q in quals if q.get("final") == "exhausted"), n),
        "top_failing": [{"name": k, "count": v} for k, v in failing.most_common(5)],
        "up": up,
        "down": down,
        "up_pct": _pct(up, up + down),
        "writes": len(actions),
        "writes_ok_pct": _pct(ok, len(actions)),
        "confirmed": sum(1 for a in actions if a.get("via") == "confirmed"),
        "assumed": sum(1 for a in actions if a.get("via") == "assumed"),
    }


def _version_of(m: dict) -> str:
    return (m.get("usage") or {}).get("agent_version") or NO_VERSION


def aggregate(messages: list[dict], feedback: list[dict], actions: list[dict]) -> dict:
    """messages: respuestas del agente (role ai). Devuelve filas por version y por dia, y los ultimos 👎 con comentario."""
    # action_log no guarda la version: se le asigna la de la ultima respuesta de esa conversacion anterior a la accion
    # (la accion ocurre durante o justo despues de una respuesta). Sin respuesta previa conocida queda sin version.
    by_conv: dict[Any, list[tuple[Any, str]]] = {}
    for m in sorted(messages, key=lambda x: _k(x.get("created_at"))):
        by_conv.setdefault(m.get("conversation_id"), []).append((_k(m.get("created_at")), _version_of(m)))

    def action_version(a: dict) -> str:
        found = NO_VERSION
        for ts, v in by_conv.get(a.get("conversation_id"), []):
            if ts <= _k(a.get("ts")):
                found = v
        return found

    def group(key_m, key_f, key_a) -> dict[str, dict]:
        buckets: dict[str, list[list[dict]]] = {}
        for i, items, key in ((0, messages, key_m), (1, feedback, key_f), (2, actions, key_a)):
            for it in items:
                buckets.setdefault(key(it), [[], [], []])[i].append(it)
        return {k: _row(*v) for k, v in buckets.items()}

    by_version = group(_version_of, lambda f: f.get("agent_version") or NO_VERSION, action_version)
    by_day = group(lambda m: _day(m.get("created_at")), lambda f: _day(f.get("updated_at")), lambda a: _day(a.get("ts")))

    reply_by_conv = {}
    for m in messages:  # texto de la respuesta mas reciente por conversacion, para mostrar contexto del 👎
        reply_by_conv[m.get("conversation_id")] = m.get("content") or ""
    downs = sorted(
        (f for f in feedback if f.get("rating") == "down" and (f.get("comment") or "").strip()),
        key=lambda f: _k(f.get("updated_at")), reverse=True,
    )[:_DOWN_LIMIT]
    return {
        "by_version": [{"version": k, **v} for k, v in sorted(by_version.items(), key=lambda kv: -kv[1]["replies"])],
        "by_day": [{"day": k, **v} for k, v in sorted(by_day.items(), reverse=True)],
        "recent_down": [
            {
                "date": _day(f.get("updated_at")), "version": f.get("agent_version") or NO_VERSION,
                "comment": f["comment"], "conversation_id": f.get("conversation_id"),
                "reply": (f.get("reply") or reply_by_conv.get(f.get("conversation_id")) or "")[:200],
            }
            for f in downs
        ],
    }


def _require_admin(user: dict) -> None:
    """Admin = correo en ADMIN_EMAILS. Sin lista y con SHIFU_DEV_UI=1 (local) cualquier logueado pasa.
    Se lee en cada peticion para que los tests puedan cambiar el entorno."""
    admins = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    email = (user.get("email") or user.get("correo") or "").strip().lower()
    if admins and email in admins:
        return
    if not admins and os.getenv("SHIFU_DEV_UI") == "1":
        return
    raise HTTPException(status_code=403, detail="Solo administradores.")


# ponytail: el panel solo lo ven admins (ADMIN_EMAILS); falta un rol real en users en vez de una lista de correos
@router.get("/metrics")
async def metrics(days: int = Query(7, ge=1, le=90), user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    _require_admin(user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async def fetch(col: str, query: dict, sort_field: str) -> list[dict]:
        return await db[col].find(query, {"_id": 0}).sort(sort_field, -1).to_list(MAX_DOCS)

    messages = await fetch("chat_messages", {"role": "ai", "created_at": {"$gte": since}, "usage": {"$ne": None}}, "created_at")
    feedback = await fetch("message_feedback", {"updated_at": {"$gte": since}}, "updated_at")
    actions = await fetch(Collections.ACTION_LOG, {"ts": {"$gte": since}}, "ts")
    out = aggregate(messages, feedback, actions)
    out["days"] = days
    out["truncated"] = any(len(x) >= MAX_DOCS for x in (messages, feedback, actions))
    return out
