import time
from typing import Generic, TypeVar, Dict, Optional, Tuple

K = TypeVar("K")
V = TypeVar("V")

class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: float, maxsize: int = 1024):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._store: Dict[K, Tuple[float, V]] = {}

    def get(self, key: K) -> Optional[V]:
        now = time.monotonic()
        item = self._store.get(key)
        if not item:
            return None
        ts, val = item
        if now - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: K, value: V) -> None:
        if len(self._store) >= self.maxsize:
            oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
            self._store.pop(oldest_key, None)
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: K) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
