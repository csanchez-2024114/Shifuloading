#!/usr/bin/env python3
"""Migration helper: dry-run by default; use `--apply` to perform renames.

Performs top-level collection and field renames according to built-in mappings.
Default behavior is safe (dry-run). Use `--apply` to perform changes and
`--backup` to create per-collection JSONL gzip backups in `backups/`.
"""
import argparse
import datetime
import gzip
import os
from pathlib import Path

try:
    from bson.json_util import dumps
    from pymongo import MongoClient
except Exception:
    print("Missing dependencies: install 'pymongo' and 'bson'.")
    raise


COLLECTION_RENAMES = {
    "usuarios": "users",
    "procesos": "processes",
    "procesos_temp": "processes_temp",
}

# catalog_apps.category value normalization (Spanish → canonical English)
CATALOG_CATEGORY_MAP = {
    "comunicación": "communication",
    "comunicacion": "communication",
    "ventas y crm": "sales & crm",
    "ventas": "sales & crm",
    "crm": "sales & crm",
    "marketing y redes": "marketing & social",
    "marketing": "marketing & social",
    "redes sociales": "marketing & social",
    "productividad": "productivity",
    "gestión de proyectos": "project management",
    "gestion de proyectos": "project management",
    "proyectos": "project management",
    "gestión de procesos": "process management",
    "gestion de procesos": "process management",
    "procesos": "process management",
    "automatización": "automation",
    "automatizacion": "automation",
    "archivos": "files & storage",
    "almacenamiento": "files & storage",
    "finanzas": "finance",
}

FIELD_RENAMES = {
    "users": {
        "correo": "email",
        "nombre": "name",
        "apellido": "last_name",
        "preferencias": "preferences",
    },
    "processes": {
        "correo_usuario": "user_email",
        "nombre_proceso": "process_name",
    },
    "processes_temp": {
        "correo_usuario": "user_email",
        "nombre_proceso": "process_name",
    },
    "oauth_vault": {"correo": "email"},
    "user_memories": {"correo_usuario": "user_email"},
}


def parse_args():
    p = argparse.ArgumentParser(description="Migrate MongoDB fields/collections Spanish->English (dry-run default)")
    p.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default=os.environ.get("MONGO_DB", "shifuai"))
    p.add_argument("--collections", help="Comma-separated collections to check (default: all mapped)")
    p.add_argument("--apply", action="store_true", help="Apply changes (destructive)")
    p.add_argument("--backup", action="store_true", help="Create per-collection JSONL gzip backup before applying")
    return p.parse_args()


def backup_collection(db, coll_name: str, out_dir: str = "backups") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(out_dir) / f"{db.name}_{coll_name}_{ts}.json.gz"
    col = db[coll_name]
    written = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        for doc in col.find({}):
            f.write(dumps(doc))
            f.write("\n")
            written += 1
    return out_path


def analyze_collection(col, mapping: dict):
    summary = []
    total_planned = 0
    total_conflicts = 0
    for old, new in mapping.items():
        q_old_only = {old: {"$exists": True}, new: {"$exists": False}}
        q_both = {old: {"$exists": True}, new: {"$exists": True}}
        try:
            cnt_old_only = col.count_documents(q_old_only)
            cnt_both = col.count_documents(q_both)
        except Exception as e:
            cnt_old_only = 0
            cnt_both = 0
            print(f"  Error counting for {old}->{new}: {e}")
        total_planned += cnt_old_only
        total_conflicts += cnt_both
        summary.append((old, new, cnt_old_only, cnt_both))
    return summary, total_planned, total_conflicts


def apply_renames(col, summary, do_apply=False):
    modified = 0
    for old, new, to_rename, conflicts in summary:
        if to_rename <= 0:
            continue
        q_old_only = {old: {"$exists": True}, new: {"$exists": False}}
        if do_apply:
            res = col.update_many(q_old_only, {"$rename": {old: new}})
            modified += int(res.modified_count)
    return modified


def main():
    args = parse_args()
    client = MongoClient(args.mongo_uri)
    db = client[args.db]

    target_cols = None
    if args.collections:
        target_cols = [c.strip() for c in args.collections.split(",") if c.strip()]

    print(f"Connected to {args.mongo_uri} db={args.db} (dry-run={not args.apply})")

    # Optional: collection renames
    print("\n== Collection renames ==")
    existing = set(db.list_collection_names())
    for old, new in COLLECTION_RENAMES.items():
        if target_cols and old not in target_cols and new not in target_cols:
            continue
        if old in existing:
            if new in existing:
                print(f" Skip rename {old} -> {new}: target exists")
            else:
                print(f" Will rename collection: {old} -> {new}")
                if args.apply:
                    try:
                        db[old].rename(new)
                        print(f"  Renamed {old} -> {new}")
                    except Exception as e:
                        print(f"  ERROR renaming {old} -> {new}: {e}")

    # Field renames
    print("\n== Field renames ==")
    results = []
    for coll_name, mapping in FIELD_RENAMES.items():
        if target_cols and coll_name not in target_cols and coll_name not in COLLECTION_RENAMES.values():
            continue
        # prefer english collection name if exists, else legacy
        physical = coll_name if coll_name in existing else None
        inv = {v: k for k, v in COLLECTION_RENAMES.items()}
        legacy = inv.get(coll_name)
        if not physical and legacy and legacy in existing:
            physical = legacy
        if not physical:
            print(f" Skip {coll_name}: collection not found")
            continue

        col = db[physical]
        summary, planned, conflicts = analyze_collection(col, mapping)
        print(f"\nCollection: {physical} -> planned={planned}, conflicts={conflicts}")
        for old, new, to_rename, conf in summary:
            print(f" - {old} -> {new}: to_rename={to_rename}, conflicts={conf}")

        if args.apply:
            if args.backup:
                print(f" Creating backup for {physical}...")
                p = backup_collection(db, physical)
                print(f"  Backup saved to {p}")
            modified = apply_renames(col, summary, do_apply=True)
            print(f" Applied renames on {physical}: modified={modified}")

        results.append({"collection": physical, "planned": planned, "conflicts": conflicts})

    # catalog_apps category value normalization
    print("\n== catalog_apps.category value normalization ==")
    col = db["catalog_apps"]
    for es_val, en_val in CATALOG_CATEGORY_MAP.items():
        count = col.count_documents({"category": {"$regex": f"^{es_val}$", "$options": "i"}})
        if count:
            print(f" '{es_val}' -> '{en_val}': {count} doc(s)")
            if args.apply:
                col.update_many(
                    {"category": {"$regex": f"^{es_val}$", "$options": "i"}},
                    {"$set": {"category": en_val}},
                )
                print(f"  Applied.")
        else:
            print(f" '{es_val}': 0 docs — skip")

    print("\n=== Summary ===")
    for r in results:
        print(f" {r['collection']}: planned={r['planned']}, conflicts={r['conflicts']}")

    client.close()


if __name__ == "__main__":
    main()
