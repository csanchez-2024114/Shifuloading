from app.core.mongo import get_sync_database
from bson import json_util
import os
from dotenv import load_dotenv
import json

load_dotenv()

# -----------------------------------------
# CONEXIÓN
# -----------------------------------------

db = get_sync_database()

chat_history_collection = db["memory_chat_history"]
chat_summary_collection = db["memory_chat_summaries"]

# -----------------------------------------
# FUNCIÓN PARA IMPRIMIR DOCUMENTOS
# -----------------------------------------

def print_collection(collection, name):
    print("\n" + "=" * 60)
    print(f"📂 COLECCIÓN: {name}")
    print("=" * 60)

    docs = list(collection.find())

    if not docs:
        print("⚠️  No hay documentos en esta colección.")
        return

    for doc in docs:
        print(json_util.dumps(doc, indent=4, ensure_ascii=False))

        print("-" * 60)


# -----------------------------------------
# EJECUCIÓN
# -----------------------------------------

if __name__ == "__main__":
    print_collection(chat_history_collection, "memory_chat_history")
    print_collection(chat_summary_collection, "memory_chat_summaries")
