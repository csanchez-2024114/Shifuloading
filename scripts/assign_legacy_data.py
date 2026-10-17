"""Asigna conversaciones y recuerdos anteriores a las cuentas (AUTH_ENABLED) a una cuenta existente.

Antes de las cuentas, el user_id era texto libre ("usuario", "ana"...) y los hilos no tenían dueño. Este script:
- en dry-run (por defecto) solo LISTA: los hilos de la base de la IA (con su dueño en la base de negocio, si lo
  tienen) y cuántos recuerdos hay por user_id antiguo. No escribe nada.
- con --apply, --email (cuenta destino, ya registrada) y --legacy-user: crea en la base de negocio las filas de
  `threads` de los hilos elegidos a nombre de esa cuenta y COPIA los recuerdos del user_id antiguo al namespace del
  UUID de la cuenta. No borra ni mueve nada; repetirlo no duplica (salta lo que ya existe). Un hilo que ya tiene
  otro dueño no se toca.

Uso (lee AI_MONGODB_* o MONGODB_*, y APP_MONGODB_* de .env):
    python scripts/assign_legacy_data.py                                   # dry-run
    python scripts/assign_legacy_data.py --apply --email ana@ejemplo.com --legacy-user usuario --threads all
    python scripts/assign_legacy_data.py --apply --email ana@ejemplo.com --legacy-user usuario --threads id1,id2
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SEP = "/"  # separador de namespace de MongoDBStore


def _namespace_prefix(namespace: list[str]) -> list[str]:
    return [SEP.join(namespace[:i]) for i in range(1, len(namespace) + 1)]


def _first_user_text(saver, thread_id: str) -> str:
    from assistant import memory

    tup = saver.get_tuple({"configurable": {"thread_id": thread_id}})
    messages = (tup.checkpoint.get("channel_values") or {}).get("messages") or [] if tup else []
    texts = memory.user_texts(messages)  # sin el resumen (no lo escribió el usuario)
    return texts[0] if texts else ""


def inventory(ai_db, appdata) -> dict:
    """Hilos y recuerdos de la base de la IA, sin contenido de mensajes."""
    threads = sorted(ai_db["checkpoints"].distinct("thread_id"))
    owners = {}
    for tid in threads:
        row = appdata.threads.get(tid) if appdata is not None else None
        owners[tid] = row["user_id"] if row else None
    mems = Counter(d["namespace"][1] for d in ai_db["memories"].find(
        {"namespace.0": "user", "namespace.2": "memories"}, {"namespace": 1}))
    return {"threads": [{"thread_id": t, "owner": owners[t]} for t in threads], "memories_by_legacy_user": dict(mems)}


def assign(ai_db, saver, appdata, email: str, legacy_user: str | None, thread_ids: list[str], apply: bool) -> dict:
    """Asigna hilos y copia recuerdos a la cuenta de `email`. Con apply=False solo informa qué haría."""
    from assistant.appdata import thread_title
    from assistant.auth import normalize_email

    user = appdata.users.get_by_email(normalize_email(email))
    if user is None:
        raise SystemExit(f"No existe una cuenta con el correo {email!r}. Regístrala antes en la app.")
    uid = user["user_id"]
    report = {"account": uid, "threads_assigned": [], "threads_skipped": [], "memories_copied": 0,
              "memories_skipped": 0, "applied": apply}
    for tid in thread_ids:
        row = appdata.threads.get(tid)
        if row is not None:
            report["threads_skipped"].append({"thread_id": tid, "reason": "ya tiene dueño" if row["user_id"] != uid
                                              else "ya asignado"})
            continue
        report["threads_assigned"].append(tid)
        if apply:
            appdata.threads.create(tid, uid, thread_title(_first_user_text(saver, tid)))
    if legacy_user:
        col = ai_db["memories"]
        for doc in col.find({"namespace": ["user", legacy_user, "memories"]}):
            target = ["user", uid, "memories"]
            if col.find_one({"namespace_str": SEP.join(target), "key": doc["key"]}):
                report["memories_skipped"] += 1
                continue
            report["memories_copied"] += 1
            if apply:
                copy = {k: v for k, v in doc.items() if k != "_id"}
                copy["namespace"] = target
                copy["namespace_str"] = SEP.join(target)  # MongoDBStore indexa (namespace_str, key)
                if "namespace_prefix" in copy:
                    copy["namespace_prefix"] = _namespace_prefix(target)
                col.insert_one(copy)
    return report


def main(argv=None) -> int:
    from langgraph.checkpoint.mongodb import MongoDBSaver

    from assistant import memory
    from assistant.appdata.mongo import MongoAppData
    from assistant.config import ConfigError, Settings

    parser = argparse.ArgumentParser(description="Asigna datos anteriores a una cuenta (dry-run por defecto).")
    parser.add_argument("--apply", action="store_true", help="escribe (sin esto solo informa)")
    parser.add_argument("--email", help="correo de la cuenta destino (ya registrada)")
    parser.add_argument("--legacy-user", help="user_id antiguo cuyos recuerdos se copian")
    parser.add_argument("--threads", default="", help="'all' o ids separados por comas")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    try:
        ai_client = memory.ping_mongo(settings.mongodb_uri)
        appdata = None
        if settings.app_mongodb_uri and settings.app_mongodb_db:
            appdata = MongoAppData(memory.ping_mongo(settings.app_mongodb_uri), settings.app_mongodb_db)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    ai_db = ai_client[settings.mongodb_db]
    inv = inventory(ai_db, appdata)
    print(f"Base de la IA: {settings.mongodb_db} | hilos: {len(inv['threads'])}")
    for t in inv["threads"]:
        print(f"  {t['thread_id']}  dueño: {t['owner'] or '(sin dueño)'}")
    print("Recuerdos por user_id antiguo:", inv["memories_by_legacy_user"] or "(ninguno)")
    if not (args.email or args.apply):
        print("\nDry-run: no se escribió nada. Para asignar: --apply --email <correo> [--legacy-user U] --threads ...")
        return 0
    if appdata is None:
        print("ERROR: faltan APP_MONGODB_URI y APP_MONGODB_DB (base de negocio).", file=sys.stderr)
        return 1
    ids = [t["thread_id"] for t in inv["threads"]] if args.threads == "all" else [
        t for t in args.threads.split(",") if t.strip()]
    report = assign(ai_db, MongoDBSaver(ai_client, db_name=settings.mongodb_db), appdata, args.email or "",
                    args.legacy_user, ids, apply=args.apply)
    print(("APLICADO: " if args.apply else "Dry-run (sin --apply no se escribe): ") + str(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
