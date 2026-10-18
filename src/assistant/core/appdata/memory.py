"""Base de negocio en memoria (tests y prototipos). Misma interfaz que mongo.py."""
import threading
from datetime import datetime, timezone

from assistant.core.appdata.repos import DuplicateEmail


class _Users:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, user_id, email, display_name, password_hash):
        if any(u["email"] == email for u in self.rows.values()):
            raise DuplicateEmail(email)
        doc = {"user_id": user_id, "email": email, "display_name": display_name, "password_hash": password_hash,
               "created_at": datetime.now(timezone.utc), "status": "active"}
        self.rows[user_id] = doc
        return dict(doc)

    def get(self, user_id):
        return dict(self.rows[user_id]) if user_id in self.rows else None

    def get_by_email(self, email):
        return next((dict(u) for u in self.rows.values() if u["email"] == email), None)

    def delete(self, user_id):
        self.rows.pop(user_id, None)


class _Sessions:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, token_hash, user_id, expires_at):
        now = datetime.now(timezone.utc)
        self.rows[token_hash] = {"token_hash": token_hash, "user_id": user_id, "created_at": now, "last_seen": now,
                                 "expires_at": expires_at}

    def get(self, token_hash):
        return dict(self.rows[token_hash]) if token_hash in self.rows else None

    def touch(self, token_hash, expires_at):
        if token_hash in self.rows:
            self.rows[token_hash].update(expires_at=expires_at, last_seen=datetime.now(timezone.utc))

    def delete(self, token_hash):
        self.rows.pop(token_hash, None)

    def delete_for_user(self, user_id):
        for k in [k for k, s in self.rows.items() if s["user_id"] == user_id]:
            del self.rows[k]


class _Threads:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, thread_id, user_id, title=""):
        now = datetime.now(timezone.utc)
        self.rows[thread_id] = {"thread_id": thread_id, "user_id": user_id, "title": title, "created_at": now,
                                "last_activity": now}
        return dict(self.rows[thread_id])

    def get(self, thread_id):
        return dict(self.rows[thread_id]) if thread_id in self.rows else None

    def touch(self, thread_id, title=None):
        row = self.rows.get(thread_id)
        if row:
            row["last_activity"] = datetime.now(timezone.utc)
            if title and not row["title"]:
                row["title"] = title

    def rename(self, thread_id, title):
        if thread_id in self.rows:
            self.rows[thread_id]["title"] = title

    def list_for_user(self, user_id):
        return sorted((dict(t) for t in self.rows.values() if t["user_id"] == user_id),
                      key=lambda t: t["last_activity"], reverse=True)

    def delete(self, thread_id):
        self.rows.pop(thread_id, None)

    def delete_for_user(self, user_id):
        for k in [k for k, t in self.rows.items() if t["user_id"] == user_id]:
            del self.rows[k]


class _Attempts:
    def __init__(self):
        self.fails: list[tuple[str, datetime]] = []
        self.locks: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def record_failure(self, key, at):
        with self._lock:
            self.fails.append((key, at))

    def failures_since(self, key, since):
        return sum(1 for k, at in self.fails if k == key and at >= since)

    def lock(self, key, until):
        self.locks[key] = until

    def locked_until(self, key):
        return self.locks.get(key)

    def clear(self, key):
        with self._lock:
            self.fails = [(k, at) for k, at in self.fails if k != key]
        self.locks.pop(key, None)


class _Rows:
    """turn_metrics y feedback en memoria."""

    def __init__(self, key: tuple[str, ...]):
        self.key = key
        self.rows: dict[tuple, dict] = {}
        self._lock = threading.Lock()

    def add(self, record):
        with self._lock:
            self.rows[tuple(record[k] for k in self.key)] = dict(record)

    put = add  # feedback: el último gana

    def get(self, turn_id):
        row = next((r for r in self.rows.values() if r.get("turn_id") == turn_id), None)
        return dict(row) if row else None

    def since(self, since, user_id=None):
        return [dict(r) for r in self.rows.values()
                if r["ts"] >= since and (user_id is None or r.get("user_id") == user_id)]

    def delete_for_thread(self, thread_id):
        with self._lock:
            self.rows = {k: r for k, r in self.rows.items() if r.get("thread_id") != thread_id}

    def delete_for_user(self, user_id):
        with self._lock:
            self.rows = {k: r for k, r in self.rows.items() if r.get("user_id") != user_id}


class MemoryAppData:
    def __init__(self):
        self.users = _Users()
        self.sessions = _Sessions()
        self.threads = _Threads()
        self.attempts = _Attempts()
        self.turn_metrics = _Rows(("turn_id",))
        self.feedback = _Rows(("turn_id", "user_id"))
