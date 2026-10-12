"""Minimal in-memory TTL cache used to avoid Flask-Caching dependency."""
from __future__ import annotations
import threading
import time
from typing import Any, Dict, Optional, Tuple

class LocalTTLCache:
    """Thread-safe local cache with TTL semantics."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        now = time.time()
        with self._lock:
            if key not in self._store:
                return None
            value, expires_at = self._store[key]
            if expires_at is not None and expires_at <= now:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, timeout: Optional[int]=None) -> None:
        expires_at = None if timeout is None else time.time() + max(timeout, 0)
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
