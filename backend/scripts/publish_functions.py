"""
Publica las fichas de funciones (codigo) a Mongo: colecciones functions y function_apps. Idempotente.
Se niega si una ficha cambio sin subir su `version`. Uso:  python scripts/publish_functions.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.mongo import MongoManager
from app.functions.publish import PublishConflict, publish
from app.functions.registry import load_all


async def main() -> int:
    load_all()  # falla en voz alta si alguna ficha es invalida
    mongo = MongoManager()
    await mongo.connect()
    try:
        report = await publish(mongo.db)
    except PublishConflict as exc:
        print(f"ERROR: {exc}\nSube `version` de esas funciones y vuelve a publicar.")
        return 1
    finally:
        await mongo.disconnect()
    print(f"publicado: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
