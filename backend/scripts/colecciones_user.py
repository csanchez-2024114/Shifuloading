from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv
from bson import json_util

load_dotenv()

db = get_sync_database()

collection = db["users"]

# Traer últimos 5 usuarios ordenados por más reciente
usuarios = collection.find(
    {},
    {
        "correo": 1,
        "email": 1,
        "password": 1
    }
).sort("_id", -1).limit(5)

print("🔎 Últimos 5 usuarios:\n")

for i, usuario in enumerate(usuarios, start=1):
    print(f"--- Usuario #{i} ---")
    print(json_util.dumps(usuario, indent=4))
    print("\n")
