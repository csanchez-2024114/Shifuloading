
from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()

# Conectarse al servidor MongoDB

# Seleccionar la base de datos "Prueba"
db = client["Prueba"]

# Obtener todas las colecciones
collections = db.list_collection_names()

# Mostrar los nombres
print("📚 Colecciones en la base de datos 'Prueba':")
for name in collections:
    print("-", name)
