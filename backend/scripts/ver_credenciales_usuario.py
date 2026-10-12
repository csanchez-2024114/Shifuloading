from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv
from bson import json_util  # <- Importante para ObjectId

load_dotenv()
db = get_sync_database()

correo_usuario = 'ecalcinap@unsa.edu.pe'
# Obtener TODO el documento del usuario
user = db.users.find_one({'correo': correo_usuario})

if user:
    print("📄 Documento completo del usuario:")
    # Usamos json_util para serializar ObjectId y otros tipos de BSON
    print(json_util.dumps(user, indent=4))
else:
    print(f"❌ No se encontró ningún usuario con correo {correo_usuario}")

