from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()

db = get_sync_database()

collection = db["users"]

correo_usuario = "ecalcinap@unsa.edu.pe"

# Hash argon2 copiado del usuario jd@email.com
nuevo_hash = "$argon2id$v=19$m=65536,t=3,p=4$PYew1trbW0tJydn7v5dybg$Ba9ydtzj6FXaVYbdVthRPcQ2kcIhqAcRdkBjghFWjJ8"

resultado = collection.update_one(
    {"correo": correo_usuario},
    {"$set": {"password": nuevo_hash}}
)

print("Usuarios modificados:", resultado.modified_count)