
from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Conexión a MongoDB
db = get_sync_database()

# Colección de procesos
collection = db["procesos"]

# Correo del usuario
correo_usuario = "ecalcinap@unsa.edu.pe"

# Consulta SOLO el campo nombre_proceso
procesos = list(
    collection.find(
        {"correo_usuario": correo_usuario},
        {"_id": 0, "nombre_proceso": 1}
    )
)

# Mostrar resultados
if procesos:
    print(f"📊 Procesos encontrados para {correo_usuario}: {len(procesos)}\n")
    for p in procesos:
        print(f"- {p['nombre_proceso']}")
else:
    print(f"❌ No se encontraron procesos para {correo_usuario}")
