"""
Standalone workflow background worker.

Run this as a separate process (separate terminal or Render Background Worker):
    python worker_main.py

Requires env vars: MONGO_URI, REDIS_URL, SECRET_KEY (same as the API server).
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from app.workers.workflow_worker import worker


async def main():
    client = AsyncIOMotorClient(Config.MONGO_URI)
    db = client[Config.MONGO_DB_NAME]
    logger.info(f"[Worker] MongoDB conectado: {db.name}")
    logger.info("[Worker] Iniciando loop de ejecución...")
    await worker.start(db)


if __name__ == "__main__":
    asyncio.run(main())
