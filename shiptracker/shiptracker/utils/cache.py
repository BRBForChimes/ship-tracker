
import time
import threading
from typing import Generic, TypeVar, Dict, Optional, Tuple

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: float, maxsize: int = 1024, *, thread_safe: bool = False):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._store: Dict[K, Tuple[float, V]] = {}
        self._lock: Optional[threading.Lock] = threading.Lock() if thread_safe else None

    # ---- internal lock helper ------------------------------------------------
    def _with_lock(self):
        """Context manager that no-ops if thread safety is disabled."""
        class _Dummy:
            def __enter__(self_inner): return None
            def __exit__(self_inner, exc_type, exc, tb): return False
        return self._lock if self._lock is not None else _Dummy()

    # ---- core API ------------------------------------------------------------
    def get(self, key: K) -> Optional[V]:
        now = time.monotonic()
        with self._with_lock():
            item = self._store.get(key)
            if not item:
                return None
            ts, val = item
            if now - ts > self.ttl:
                # expired
                self._store.pop(key, None)
                return None
            return val

    def set(self, key: K, value: V) -> None:
        with self._with_lock():
            if len(self._store) >= self.maxsize:
                # evict oldest by timestamp
                oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest_key, None)
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: K) -> None:
        with self._with_lock():
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._with_lock():
            self._store.clear()

    # ---- QoL additions -------------------------------------------------------
    def __contains__(self, key: K) -> bool:
        """Support: `key in cache` (also refreshes TTL if expired -> returns False)."""
        return self.get(key) is not None

    def __len__(self) -> int:
        """Number of entries currently stored (may include expired items until accessed)."""
        with self._with_lock():
            return len(self._store)

