"""
Seed script: inserts catalog_apps data from the JSON export into MongoDB.
Run from the project root:
    python scripts/seed_catalog_apps.py
"""
import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bson import ObjectId
from pymongo.errors import BulkWriteError
from config import Config
from app.core.mongo import MongoManager

JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "app", "data_temporal", "shifu_production.catalog_apps.json",
)
COLLECTION = "catalog_apps"


def parse_documents(raw: list) -> list:
    docs = []
    for item in raw:
        doc = dict(item)
        if isinstance(doc.get("_id"), dict) and "$oid" in doc["_id"]:
            doc["_id"] = ObjectId(doc["_id"]["$oid"])
        docs.append(doc)
    return docs


async def seed():
    with open(JSON_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    docs = parse_documents(raw)
    print(f"Documentos a insertar: {len(docs)}")

    mongo = MongoManager()
    await mongo.connect()
    collection = mongo.db[COLLECTION]

    inserted = 0
    skipped = 0
    for doc in docs:
        existing = await collection.find_one({"_id": doc["_id"]})
        if existing:
            print(f"  SKIP (ya existe): {doc.get('name')} — {doc['_id']}")
            skipped += 1
            continue
        await collection.insert_one(doc)
        print(f"  OK: {doc.get('name')}")
        inserted += 1

    await mongo.disconnect()
    print(f"\nResultado: {inserted} insertados, {skipped} omitidos (duplicados).")


if __name__ == "__main__":
    asyncio.run(seed())
