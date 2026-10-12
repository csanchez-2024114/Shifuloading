from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()
db = get_sync_database()

correo = "ecalcinap@unsa.edu.pe"

result = db.users.delete_one({
    "$or": [
        {"correo": correo},
        {"email": correo}
    ]
})

if result.deleted_count == 1:
    print("🔥 Usuario eliminado correctamente")
else:
    print("❌ No se encontró usuario para eliminar")
