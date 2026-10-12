from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()

db = get_sync_database()

correo_usuario = 'ecalcinap@unsa.edu.pe'

# Campos que quieres eliminar
campos_a_eliminar = [
    "chat_refs",
    "preferencias",
    "preferencias_historial",
    "pending_features",
]

# Construimos el diccionario para $unset
unset_fields = {campo: "" for campo in campos_a_eliminar}

resultado = db.users.update_one(
    {"correo": correo_usuario},
    {"$unset": unset_fields}
)

if resultado.modified_count > 0:
    print("✅ Campos eliminados correctamente")
else:
    print("⚠️ No se realizaron cambios (usuario no encontrado o campos inexistentes)")

