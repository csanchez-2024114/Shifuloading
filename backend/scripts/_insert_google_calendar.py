"""
One-time script: insert Google Calendar into catalog_apps.
Mirrors the schema of existing Google apps in the catalog.
Run from project root: python scripts/_insert_google_calendar.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from pymongo import MongoClient

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]

# Read an existing Google app to mirror its schema
sample = db["catalog_apps"].find_one({"nameApi": "Gmail"}, {"_id": 0})
print(f"Schema reference (Gmail): {sample}")

# Check if Google Calendar already exists under any name
existing = db["catalog_apps"].find_one(
    {"$or": [
        {"nameApi": "google calendar"},
        {"nameApi": "Google Calendar"},
        {"name": "Google Calendar"},
    ]}
)
if existing:
    print(f"\nGoogle Calendar already exists: {existing}")
    client.close()
    sys.exit(0)

doc = {
    "name": "Google Calendar",
    "nameApi": "google calendar",
    "category": sample.get("category", "Productivity") if sample else "Productivity",
    "active": True,
    "visible": True,
}

# Copy any extra schema fields from the Gmail doc (except name/nameApi)
if sample:
    for k, v in sample.items():
        if k not in ("name", "nameApi", "_id"):
            doc.setdefault(k, v)

result = db["catalog_apps"].insert_one(doc)
print(f"\nInserted Google Calendar with _id={result.inserted_id}")
print(f"Document: {doc}")

client.close()
