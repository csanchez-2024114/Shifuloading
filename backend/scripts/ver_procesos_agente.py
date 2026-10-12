from app.core.mongo import get_sync_database
from bson import json_util
import os
from dotenv import load_dotenv

load_dotenv()

# Conexión a MongoDB
db = get_sync_database()

# Colecciones
procesos_collection = db["procesos"]
procesos_temp_collection = db["procesos_temp"]

# Usuario a filtrar
correo_usuario = "ecalcinap@unsa.edu.pe"

# ---------------- PROCESOS DEFINITIVOS ----------------

procesos = list(procesos_collection.find({"correo_usuario": correo_usuario}))

print("\n================ PROCESOS DEFINITIVOS ================\n")

if procesos:
    print(f"📊 Procesos encontrados para {correo_usuario}: {len(procesos)}\n")
    for p in procesos:
        print(json_util.dumps(p, indent=4))
        print("------------------------------------------------------------\n")
else:
    print(f"❌ No se encontraron procesos definitivos para {correo_usuario}\n")

# ---------------- PROCESOS TEMPORALES ----------------

procesos_temp = list(procesos_temp_collection.find({"correo_usuario": correo_usuario}))

print("\n================ PROCESOS TEMPORALES ================\n")

if procesos_temp:
    print(f"🕒 Procesos TEMPORALES encontrados para {correo_usuario}: {len(procesos_temp)}\n")
    for p in procesos_temp:
        print(json_util.dumps(p, indent=4))
        print("------------------------------------------------------------\n")
else:
    print(f"❌ No se encontraron procesos temporales para {correo_usuario}\n")

