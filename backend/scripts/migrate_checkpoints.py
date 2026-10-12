"""
One-time migration: rename v3_checkpoints → shifu_checkpoints.

Run ONCE before deploying the updated main.py that uses shifu_checkpoints.
After running, all conversation history is accessible under the new names.

Usage:
    python scripts/migrate_checkpoints.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient

_RENAMES = [
    ("v3_checkpoints",        "shifu_checkpoints"),
    ("v3_checkpoint_writes",  "shifu_checkpoint_writes"),
]


async def migrate(dry_run: bool) -> None:
    uri     = os.environ["MONGO_URI"]
    db_name = os.environ.get("MONGO_DB_NAME", "hyperShifu")

    client = AsyncIOMotorClient(uri)
    db     = client[db_name]

    existing = await db.list_collection_names()
    for src, dst in _RENAMES:
        if src not in existing:
            print(f"  SKIP {src!r} — collection does not exist")
            continue
        if dst in existing:
            print(f"  SKIP {src!r} → {dst!r} — destination already exists")
            continue
        count = await db[src].count_documents({})
        print(f"  {'[DRY] ' if dry_run else ''}RENAME {src!r} → {dst!r}  ({count} docs)")
        if not dry_run:
            await db[src].rename(dst)

    client.close()
    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, don't rename")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))
