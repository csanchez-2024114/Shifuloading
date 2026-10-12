"""
seed_ui_actions.py — carga la lista de PRUEBA de acciones de interfaz en Mongo (coleccion ui_actions_catalog).

    python scripts/seed_ui_actions.py            # agrega las que falten; no pisa las que un admin ya edito
    python scripts/seed_ui_actions.py --force    # reescribe todas con lo de este archivo

Para agregar una accion: una fila aqui (o un documento directo en Mongo) y que el frontend sepa que hacer con su `id`.
El agente la toma sola en menos de 10 minutos (cache), o al reiniciar. Ver app/agent/shared/helpers/ui_actions.py.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# description: en ingles y completa (el modelo elige con ella). label: lo que dice el boton, por idioma.
# Campos opcionales: "plans": ["pro"] (solo esos planes) y "confirm": True (cambia algo: el frontend pide confirmacion).
ACTIONS = [
    {"id": "open_workflows", "label": {"es": "Ver mis workflows", "en": "See my workflows"}, "source": "user",
     "description": "Opens the panel that lists the user's automations (workflows) with their status and last runs."},
    {"id": "open_connections", "label": {"es": "Ver mis apps conectadas", "en": "See my connected apps"}, "source": "user",
     "description": "Opens the page of connected apps and accounts, where the user sees what is connected and can connect or disconnect accounts. Use it also when the user asks to see or check which apps or accounts they have connected."},
    {"id": "open_memory", "label": {"es": "Ver lo que Shifu recuerda", "en": "See what Shifu remembers"}, "source": "user",
     "description": "Opens the memory panel with everything the assistant remembers about the user, where each item can be deleted."},
    {"id": "open_notifications", "label": {"es": "Ver mis avisos", "en": "See my notices"}, "source": "user",
     "description": "Opens the list of notices: runs that finished or failed, triggers that were turned off, reminders of commitments."},
    {"id": "open_settings", "label": {"es": "Abrir ajustes", "en": "Open settings"}, "source": "user",
     "description": "Opens the account settings: profile, time zone, language and whether notices are also sent by email."},
    {"id": "open_billing", "label": {"es": "Ver mi plan y consumo", "en": "See my plan and usage"}, "source": "user",
     "description": "Opens the plan and usage page: current plan, limits, how much was used this period and how to upgrade."},
    {"id": "new_conversation", "label": {"es": "Empezar conversación nueva", "en": "Start a new conversation"}, "source": "user",
     "description": "Starts a new, empty conversation with the assistant. Use it when the user asks to start over, open a new chat or begin a new conversation."},
    {"id": "open_help", "label": {"es": "Abrir centro de ayuda", "en": "Open the help center"}, "source": "user",
     "description": "Opens the help center with guides and how to contact support."},
    {"id": "open_app", "label": {"es": "Ver esta app", "en": "See this app"}, "source": "user", "params": {"app": "lowercase key of the app the user named, e.g. gmail, google_sheets"},
     "description": "Opens the page of ONE app the user names, with what can be done with it and its connected accounts."},
    # Las arma el codigo desde el estado del turno (chat._build_ui_actions); el modelo no las elige.
    {"id": "connect_app", "label": "Conectar app", "source": "system",
     "description": "Connect button for an app the turn needs and the user has not connected."},
    {"id": "render_workflow", "label": "Mostrar workflow", "source": "system",
     "description": "Card of the workflow the conversation just created or activated, with its steps."},
    {"id": "open_trigger", "label": "Mostrar disparador", "source": "system",
     "description": "Webhook address or trigger summary of the workflow just activated."},
]


def main(force: bool) -> None:
    col = MongoClient(os.getenv("MONGO_URI"))[os.getenv("MONGO_DB_NAME")]["ui_actions_catalog"]
    col.create_index("id", unique=True)
    now, added = datetime.now(timezone.utc), 0
    for a in ACTIONS:
        doc = {**a, "params": a.get("params") or {}, "status": "active", "updated_at": now}
        r = col.update_one({"id": a["id"]}, {"$set": doc} if force else {"$setOnInsert": doc}, upsert=True)
        added += bool(r.upserted_id or (force and r.modified_count))
    print(f"ui_actions_catalog: {added} escritas, {col.count_documents({})} en total")


if __name__ == "__main__":
    main("--force" in sys.argv)
