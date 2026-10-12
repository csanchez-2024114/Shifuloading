from app.core.mongo import get_sync_database
from bson import ObjectId
import os
from dotenv import load_dotenv
import re

load_dotenv()

# Conexión
db = client["Prueba"]
collection = db["procesos_agente"]

print("=" * 80)
print("PRUEBA DIRECTA DE QUERIES")
print("=" * 80)

# Test 1: Por ObjectId
print("\n1. Búsqueda por user_id como ObjectId:")
user_id = ObjectId("68596e87123f683381e6cc4b")
result = collection.count_documents({"user_id": user_id})
print(f"   Query: {{'user_id': ObjectId('68596e87123f683381e6cc4b')}}")
print(f"   Resultado: {result} documentos")

# Test 2: Por email exacto
print("\n2. Búsqueda por correo exacto:")
email = "ecalcinap@unsa.edu.pe"
result = collection.count_documents({"correo_usuario": email})
print(f"   Query: {{'correo_usuario': '{email}'}}")
print(f"   Resultado: {result} documentos")

# Test 3: Por email con regex
print("\n3. Búsqueda por correo con regex:")
email_pattern = re.escape(email)
result = collection.count_documents({"correo_usuario": {"$regex": email_pattern, "$options": "i"}})
print(f"   Query: {{'correo_usuario': {{'$regex': '{email_pattern}', '$options': 'i'}}}}")
print(f"   Resultado: {result} documentos")

# Test 4: Ver qué hay realmente en correo_usuario
print("\n4. Valores únicos en correo_usuario:")
pipeline = [
    {"$group": {"_id": "$correo_usuario", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
correos = list(collection.aggregate(pipeline))
for item in correos:
    print(f"   '{item['_id']}' -> {item['count']} documentos")

print("\n" + "=" * 80)