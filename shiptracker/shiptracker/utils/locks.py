import asyncio
from typing import Callable, Awaitable, TypeVar, Dict

T = TypeVar("T")
_locks: Dict[str, asyncio.Lock] = {}

async def with_lock(key: str, fn: Callable[[], Awaitable[T]]) -> T:
    """Run fn() under an asyncio lock keyed by `key`."""
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        try:
            return await fn()
        finally:
            # Optionally clean up if no one else is waiting
            if not lock.locked():
                _locks.pop(key, None)
