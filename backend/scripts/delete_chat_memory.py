from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------
# CONEXIÓN
# -----------------------------------------

db = get_sync_database()

chat_history_collection = db["memory_chat_history"]
chat_summary_collection = db["memory_chat_summaries"]

correo_usuario = "ecalcinap@unsa.edu.pe"

# -----------------------------------------
# ELIMINAR HISTORIAL
# -----------------------------------------

print("\n🧹 Eliminando chat_history...")
history_result = chat_history_collection.delete_many(
    {"correo_usuario": correo_usuario}
)

print(f"✅ Documentos eliminados en memory_chat_history: {history_result.deleted_count}")

# -----------------------------------------
# ELIMINAR SUMMARIES
# -----------------------------------------

print("\n🧹 Eliminando chat_summaries...")
summary_result = chat_summary_collection.delete_many(
    {"correo_usuario": correo_usuario}
)

print(f"✅ Documentos eliminados en memory_chat_summaries: {summary_result.deleted_count}")

# -----------------------------------------
# VERIFICACIÓN
# -----------------------------------------

remaining_history = chat_history_collection.count_documents(
    {"correo_usuario": correo_usuario}
)

remaining_summaries = chat_summary_collection.count_documents(
    {"correo_usuario": correo_usuario}
)

print("\n🔎 Verificación final:")
print(f"Historial restante: {remaining_history}")
print(f"Summaries restantes: {remaining_summaries}")

if remaining_history == 0 and remaining_summaries == 0:
    print("✅ Limpieza completa exitosa")
else:
    print("⚠️ Aún quedan documentos por eliminar")
