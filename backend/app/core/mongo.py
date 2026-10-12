import logging
from typing import Optional
from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from config import Config
logger = logging.getLogger(__name__)
_sync_client: Optional[MongoClient] = None

class LegacyMongoWrapper:
    """Compatibility wrapper for legacy code that expects mongo.database/mongo.db."""

    def __init__(self, db):
        self.db = db

    def __getattr__(self, name):
        if name in {'database', 'db'}:
            return self.db
        if name == 'usuarios':
            return self.db['users']
        return getattr(self.db, name)

    def __getitem__(self, key):
        if key == 'usuarios':
            return self.db['users']
        return self.db[key]

class MongoManager:
    """Global Mongo manager using Motor as the canonical backend client."""

    def __init__(self) -> None:
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.db_name = Config.MONGO_DB_NAME

    async def connect(self) -> None:
        if self.client is not None and self.db is not None:
            return
        self.client = AsyncIOMotorClient(Config.MONGO_URI, maxPoolSize=100, minPoolSize=10, serverSelectionTimeoutMS=5000)
        await self.client.admin.command('ping')
        self.db = self.client.get_database(self.db_name)
        logger.info('MongoDB conectado (global manager): %s', self.db.name)

    async def disconnect(self) -> None:
        if self.client is None:
            return
        self.client.close()
        self.client = None
        self.db = None
mongo_manager = MongoManager()

async def init_mongo(app: FastAPI) -> None:
    """Initialize global Mongo and expose canonical handles in app.state."""
    await mongo_manager.connect()
    app.state.mongo_client = mongo_manager.client
    app.state.db = mongo_manager.db
    app.state.db_name = mongo_manager.db_name
    app.state.mongo = LegacyMongoWrapper(mongo_manager.db)

async def close_mongo(app: FastAPI) -> None:
    """Close global Mongo connection pool."""
    await mongo_manager.disconnect()
    close_sync_client()

def get_request_db(request: Request):
    db = getattr(request.app.state, 'db', None)
    if db is None:
        raise RuntimeError('Database not initialized')
    return db

def get_sync_client() -> MongoClient:
    """Return a shared synchronous Mongo client for legacy sync modules."""
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(Config.MONGO_URI, maxPoolSize=100, minPoolSize=5, serverSelectionTimeoutMS=5000)
    return _sync_client

def get_sync_database(db_name: Optional[str]=None):
    name = db_name or mongo_manager.db_name
    raw_db = get_sync_client()[name]
    return LegacyMongoWrapper(raw_db)

def close_sync_client() -> None:
    global _sync_client
    if _sync_client is None:
        return
    _sync_client.close()
    _sync_client = None
