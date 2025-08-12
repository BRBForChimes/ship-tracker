import asyncio
from collections import defaultdict

class KeyedLocks:
    def __init__(self):
        self._locks = defaultdict(asyncio.Lock)

    async def with_lock(self, key: str, coro):
        async with self._locks[key]:
            return await coro

locks = KeyedLocks()
