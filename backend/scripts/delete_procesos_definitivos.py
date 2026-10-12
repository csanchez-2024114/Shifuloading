from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()

db = get_sync_database()
collection = db["procesos"]

correo_usuario = "ecalcinap@unsa.edu.pe"

resultado = collection.delete_many({"correo_usuario": correo_usuario})

print(f"🗑️ {resultado.deleted_count} procesos eliminados para {correo_usuario}")
