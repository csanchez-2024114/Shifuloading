from app.core.mongo import get_sync_database
from bson import json_util
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONEXIÓN ----------------

db = get_sync_database()

# Colección de procesos programados
scheduled_collection = db["scheduled_processes"]

# Usuario a filtrar
correo_usuario = "ecalcinap@unsa.edu.pe"

# ---------------- PROCESOS PROGRAMADOS ----------------

scheduled = list(scheduled_collection.find({"correo_usuario": correo_usuario}))

print("\n================ PROCESOS PROGRAMADOS ================\n")

if scheduled:
    print(f"⏰ Procesos PROGRAMADOS encontrados para {correo_usuario}: {len(scheduled)}\n")

    for job in scheduled:
        print(json_util.dumps(job, indent=4))
        print("------------------------------------------------------------\n")
else:
    print(f"❌ No se encontraron procesos programados para {correo_usuario}\n")
