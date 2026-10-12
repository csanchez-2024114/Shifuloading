import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Config
from pymongo import MongoClient

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]

print("=== catalog_apps (active=True, visible=True) ===")
for doc in db["catalog_apps"].find({"active": True, "visible": True}, {"name": 1, "nameApi": 1, "_id": 0}):
    name = doc.get("name", "")
    name_api = doc.get("nameApi", "MISSING")
    print(f"  name={name!r:35s}  nameApi={name_api!r}")

print()
print("=== user_connected_accounts para todos los usuarios ===")
seen = set()
for doc in db["user_connected_accounts"].find({"status": "active"}, {"provider": 1, "account_id": 1, "_id": 0}):
    p = doc.get("provider", "")
    if p not in seen:
        seen.add(p)
        print(f"  provider={p!r}")

client.close()
