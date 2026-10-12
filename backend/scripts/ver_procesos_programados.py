from app.core.mongo import get_sync_database
from bson import json_util
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# ==============================
# 🔧 CONEXIÓN REAL
# ==============================

db = get_sync_database()

collection = db["scheduled_processes"]  # 👈 colección correcta

# Opcional: filtrar por usuario
FILTRO_USUARIO = None  # Ej: "correo@usuario.com"


def print_section(title):
    print("\n" + "=" * 80)
    print(f"📦 {title}")
    print("=" * 80)


def pretty_print(docs):
    if not docs:
        print("   (vacío)")
        return

    for i, doc in enumerate(docs, 1):
        print(f"\n🔹 Documento #{i}")
        print(json_util.dumps(doc, indent=2, ensure_ascii=False))


def main():
    print("\n🔎 INSPECTOR DE SCHEDULED PROCESSES\n")

    base_filter = {}
    if FILTRO_USUARIO:
        base_filter["correo_usuario"] = FILTRO_USUARIO

    # ==============================
    # 1️⃣ TODOS LOS JOBS
    # ==============================
    print_section("TODOS LOS JOBS")
    all_jobs = list(collection.find(base_filter))
    pretty_print(all_jobs)

    # ==============================
    # 2️⃣ JOBS PENDING
    # ==============================
    print_section("JOBS PENDING")
    pending_jobs = list(collection.find({
        **base_filter,
        "status": "PENDING"
    }))
    pretty_print(pending_jobs)

    # ==============================
    # 3️⃣ JOBS VENCIDOS (lo que ejecutaría el worker)
    # ==============================
    print_section("JOBS VENCIDOS (run_at <= ahora)")

    ahora = datetime.now(timezone.utc)

    due_jobs = list(collection.find({
        **base_filter,
        "status": "PENDING",
        "run_at": {"$lte": ahora}
    }))

    pretty_print(due_jobs)

    # ==============================
    # 4️⃣ JOBS EN ERROR
    # ==============================
    print_section("JOBS EN ERROR")

    error_jobs = list(collection.find({
        **base_filter,
        "status": "ERROR"
    }))

    pretty_print(error_jobs)

    # ==============================
    # 5️⃣ JOBS RUNNING
    # ==============================
    print_section("JOBS RUNNING")

    running_jobs = list(collection.find({
        **base_filter,
        "status": "RUNNING"
    }))

    pretty_print(running_jobs)

    # ==============================
    # 6️⃣ RESUMEN
    # ==============================
    print_section("RESUMEN")

    total = collection.count_documents(base_filter)
    pending = collection.count_documents({**base_filter, "status": "PENDING"})
    running = collection.count_documents({**base_filter, "status": "RUNNING"})
    done = collection.count_documents({**base_filter, "status": "DONE"})
    error = collection.count_documents({**base_filter, "status": "ERROR"})

    print(f"Total jobs: {total}")
    print(f"PENDING: {pending}")
    print(f"RUNNING: {running}")
    print(f"DONE: {done}")
    print(f"ERROR: {error}")


if __name__ == "__main__":
    main()
