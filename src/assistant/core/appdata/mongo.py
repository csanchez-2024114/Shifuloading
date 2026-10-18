"""Base de negocio en MongoDB. Colecciones: users, sessions, threads, login_attempts, login_locks."""
from datetime import datetime, timezone

import pymongo
from pymongo.errors import DuplicateKeyError

from assistant.core.appdata.repos import DuplicateEmail


def _utc(dt):
    # pymongo devuelve fechas sin zona (UTC): se marcan para poder compararlas con datetime.now(timezone.utc)
    return dt.replace(tzinfo=timezone.utc) if isinstance(dt, datetime) and dt.tzinfo is None else dt


def _doc(d: dict | None) -> dict | None:
    if d is None:
        return None
    out = {k: _utc(v) for k, v in d.items() if k != "_id"}
    return out


class MongoUsers:
    def __init__(self, db):
        self.col = db["users"]
        self.col.create_index("user_id", unique=True)
        self.col.create_index("email", unique=True)

    def create(self, user_id, email, display_name, password_hash):
        doc = {"user_id": user_id, "email": email, "display_name": display_name, "password_hash": password_hash,
               "created_at": datetime.now(timezone.utc), "status": "active"}
        try:
            self.col.insert_one(dict(doc))
        except DuplicateKeyError as exc:
            raise DuplicateEmail(email) from exc
        return doc

    def get(self, user_id):
        return _doc(self.col.find_one({"user_id": user_id}))

    def get_by_email(self, email):
        return _doc(self.col.find_one({"email": email}))

    def delete(self, user_id):
        self.col.delete_one({"user_id": user_id})


class MongoSessions:
    def __init__(self, db):
        self.col = db["sessions"]
        self.col.create_index("token_hash", unique=True)
        self.col.create_index("user_id")
        self.col.create_index("expires_at", expireAfterSeconds=0)  # Mongo borra las caducadas

    def create(self, token_hash, user_id, expires_at):
        now = datetime.now(timezone.utc)
        self.col.insert_one({"token_hash": token_hash, "user_id": user_id, "created_at": now, "last_seen": now,
                             "expires_at": expires_at})

    def get(self, token_hash):
        return _doc(self.col.find_one({"token_hash": token_hash}))

    def touch(self, token_hash, expires_at):
        self.col.update_one({"token_hash": token_hash},
                            {"$set": {"expires_at": expires_at, "last_seen": datetime.now(timezone.utc)}})

    def delete(self, token_hash):
        self.col.delete_one({"token_hash": token_hash})

    def delete_for_user(self, user_id):
        self.col.delete_many({"user_id": user_id})


class MongoThreads:
    def __init__(self, db):
        self.col = db["threads"]
        self.col.create_index("thread_id", unique=True)
        self.col.create_index([("user_id", pymongo.ASCENDING), ("last_activity", pymongo.DESCENDING)])

    def create(self, thread_id, user_id, title=""):
        now = datetime.now(timezone.utc)
        doc = {"thread_id": thread_id, "user_id": user_id, "title": title, "created_at": now, "last_activity": now}
        self.col.insert_one(dict(doc))
        return doc

    def get(self, thread_id):
        return _doc(self.col.find_one({"thread_id": thread_id}))

    def touch(self, thread_id, title=None):
        update = {"last_activity": datetime.now(timezone.utc)}
        if title:
            self.col.update_one({"thread_id": thread_id, "title": ""}, {"$set": {"title": title}})
        self.col.update_one({"thread_id": thread_id}, {"$set": update})

    def rename(self, thread_id, title):
        self.col.update_one({"thread_id": thread_id}, {"$set": {"title": title}})

    def list_for_user(self, user_id):
        return [_doc(d) for d in self.col.find({"user_id": user_id}).sort("last_activity", pymongo.DESCENDING)]

    def delete(self, thread_id):
        self.col.delete_one({"thread_id": thread_id})

    def delete_for_user(self, user_id):
        self.col.delete_many({"user_id": user_id})


class MongoAttempts:
    def __init__(self, db, window_seconds: int = 3600):
        self.fails = db["login_attempts"]
        self.locks = db["login_locks"]
        self.fails.create_index([("key", pymongo.ASCENDING), ("at", pymongo.DESCENDING)])
        self.fails.create_index("at", expireAfterSeconds=window_seconds)
        self.locks.create_index("key", unique=True)
        self.locks.create_index("until", expireAfterSeconds=0)

    def record_failure(self, key, at):
        self.fails.insert_one({"key": key, "at": at})

    def failures_since(self, key, since):
        return self.fails.count_documents({"key": key, "at": {"$gte": since}})

    def lock(self, key, until):
        self.locks.update_one({"key": key}, {"$set": {"until": until}}, upsert=True)

    def locked_until(self, key):
        d = self.locks.find_one({"key": key})
        return _utc(d["until"]) if d else None

    def clear(self, key):
        self.fails.delete_many({"key": key})
        self.locks.delete_many({"key": key})


class MongoAppData:
    def __init__(self, client: pymongo.MongoClient, db_name: str):
        db = client[db_name]
        self.db_name = db_name
        self.users = MongoUsers(db)
        self.sessions = MongoSessions(db)
        self.threads = MongoThreads(db)
        self.attempts = MongoAttempts(db)
