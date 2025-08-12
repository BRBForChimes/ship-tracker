from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite
from contextlib import asynccontextmanager

ALLOWED_FIELDS = {
  "type","name","status","damage","location","home_port","notes",
  "keys","image_url","regiment","share_code","squad_lock_until"
}

class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    @asynccontextmanager
    async def connect(self):
        if not self._conn:
            self._conn = await aiosqlite.connect(self.path)
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield self._conn
        finally:
            await self._conn.commit()

    async def setup(self, schema_path: str):
        async with self.connect() as conn, open(schema_path, "r", encoding="utf-8") as f:
            await conn.executescript(f.read())

    # ---------- Wars ----------
    async def upsert_war(self, guild_id: int, name: str) -> int:
        async with self.connect() as conn:
            await conn.execute("INSERT OR IGNORE INTO wars(guild_id, name) VALUES (?,?)", (guild_id, name))
            cur = await conn.execute("SELECT id FROM wars WHERE guild_id=? AND name=?", (guild_id, name))
            row = await cur.fetchone()
            return int(row[0])

    async def list_wars(self, guild_id: int) -> List[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT * FROM wars WHERE guild_id=? ORDER BY started_at DESC", (guild_id,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]

    async def get_war(self, guild_id: int, name: str) -> Optional[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT * FROM wars WHERE guild_id=? AND name=?", (guild_id, name))
            row = await cur.fetchone()
            if not row: return None
            cols = [c[0] for c in cur.description]
            return dict(zip(cols, row))

    async def end_war(self, war_id: int):
        async with self.connect() as conn:
            await conn.execute("UPDATE wars SET ended_at=CURRENT_TIMESTAMP WHERE id=?", (war_id,))

    # ---------- Guild auth ----------
    async def set_guild_auth_roles(self, guild_id: int, role_ids: List[int]):
        async with self.connect() as conn:
            await conn.execute("DELETE FROM guild_auth_roles WHERE guild_id=?", (guild_id,))
            if role_ids:
                await conn.executemany(
                    "INSERT INTO guild_auth_roles(guild_id, role_id) VALUES (?,?)",
                    [(guild_id, rid) for rid in role_ids],
                )

    async def set_guild_auth_users(self, guild_id: int, user_ids: List[int]):
        async with self.connect() as conn:
            await conn.execute("DELETE FROM guild_auth_users WHERE guild_id=?", (guild_id,))
            if user_ids:
                await conn.executemany(
                    "INSERT INTO guild_auth_users(guild_id, user_id) VALUES (?,?)",
                    [(guild_id, uid) for uid in user_ids],
                )

    async def is_user_authorized_for_guild(self, guild_id: int, user_id: int, member_role_ids: List[int]) -> bool:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT 1 FROM guild_auth_users WHERE guild_id=? AND user_id=?",
                                     (guild_id, user_id))
            if await cur.fetchone():
                return True
            if not member_role_ids:
                return False
            q = "SELECT 1 FROM guild_auth_roles WHERE guild_id=? AND role_id IN ({}) LIMIT 1".format(
                ",".join("?" for _ in member_role_ids)
            )
            cur = await conn.execute(q, (guild_id, *member_role_ids))
            return (await cur.fetchone()) is not None

    # Bulk helpers for cross-guild checks
    async def get_instance_guild_ids(self, ship_id: int) -> List[int]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT DISTINCT guild_id FROM ship_instances WHERE ship_id=?", (ship_id,))
            return [int(gid) for (gid,) in await cur.fetchall()]

    async def get_guild_auth_roles_many(self, guild_ids: List[int]) -> Dict[int, set[int]]:
        if not guild_ids: return {}
        placeholders = ",".join("?" for _ in guild_ids)
        async with self.connect() as conn:
            cur = await conn.execute(
                f"SELECT guild_id, role_id FROM guild_auth_roles WHERE guild_id IN ({placeholders})",
                guild_ids
            )
            out: Dict[int, set[int]] = {}
            for gid, rid in await cur.fetchall():
                out.setdefault(int(gid), set()).add(int(rid))
            return out

    async def is_user_in_guild_auth_users_many(self, guild_ids: List[int], user_id: int) -> bool:
        if not guild_ids: return False
        placeholders = ",".join("?" for _ in guild_ids)
        async with self.connect() as conn:
            cur = await conn.execute(
                f"SELECT 1 FROM guild_auth_users WHERE user_id=? AND guild_id IN ({placeholders}) LIMIT 1",
                (user_id, *guild_ids)
            )
            return (await cur.fetchone()) is not None

    # ---------- Ships ----------
    async def add_ship(self, guild_id: int, war_id: int, **fields: Any) -> int:
        cols = ["guild_id","war_id"] + list(fields.keys())
        vals = [guild_id, war_id] + list(fields.values())
        placeholders = ",".join("?" for _ in cols)
        async with self.connect() as conn:
            cur = await conn.execute(
                f"INSERT INTO ships({','.join(cols)}) VALUES ({placeholders})",
                vals
            )
            return cur.lastrowid

    async def get_ship(self, guild_id: int, war_id: int, name: str) -> Optional[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM ships WHERE guild_id=? AND war_id=? AND name=?",
                (guild_id, war_id, name)
            )
            row = await cur.fetchone()
            if not row:
                return None
            cols = [c[0] for c in cur.description]
            return dict(zip(cols, row))

    async def get_ship_by_id(self, ship_id: int) -> Optional[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT * FROM ships WHERE id=?", (ship_id,))
            row = await cur.fetchone()
            if not row: return None
            cols = [c[0] for c in cur.description]
            return dict(zip(cols, row))

    async def list_ships(self, guild_id: int, war_id: int) -> List[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM ships WHERE guild_id=? AND war_id=? ORDER BY name",
                (guild_id, war_id)
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]

    async def list_ships_in_war(self, guild_id: int, war_name: str) -> List[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                """SELECT s.* FROM ships s
                     JOIN wars w ON w.id = s.war_id
                   WHERE s.guild_id=? AND w.name=?
                   ORDER BY s.name""",
                (guild_id, war_name),
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]

    async def update_ship_field(self, ship_id: int, user_id: int, field: str, new_value: Any):
        if field not in ALLOWED_FIELDS:
            raise ValueError("Invalid field")
        async with self.connect() as conn:
            cur = await conn.execute(f"SELECT {field} FROM ships WHERE id=?", (ship_id,))
            row = await cur.fetchone()
            old = row[0] if row else None
            await conn.execute(f"UPDATE ships SET {field}=? WHERE id=?", (new_value, ship_id))
            await conn.execute(
                "INSERT INTO ship_updates(ship_id,user_id,field,old_value,new_value) VALUES (?,?,?,?,?)",
                (ship_id, user_id, field, old, str(new_value))
            )

    # ---------- Supplies ----------
    async def set_supply(self, ship_id: int, resource: str, quantity: int):
        async with self.connect() as conn:
            await conn.execute(
                "INSERT INTO ship_supplies(ship_id, resource, quantity) VALUES (?,?,?) "
                "ON CONFLICT(ship_id, resource) DO UPDATE SET quantity=excluded.quantity, updated_at=CURRENT_TIMESTAMP",
                (ship_id, resource, quantity)
            )

    async def list_supplies(self, ship_id: int) -> List[Tuple[str,int]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT resource, quantity FROM ship_supplies WHERE ship_id=? ORDER BY resource",
                (ship_id,)
            )
            return [(r, q) for (r, q) in await cur.fetchall()]

    # ---------- Logs / Kills / Ops ----------
    async def add_log(self, ship_id: int, user_id: Optional[int], text: str) -> int:
        async with self.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO ship_logs(ship_id,user_id,log) VALUES (?,?,?)",
                (ship_id, user_id, text)
            )
            return cur.lastrowid

    async def add_kill(self, ship_id: int, user_id: Optional[int], kills_raw: str) -> int:
        async with self.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO ship_kills(ship_id,user_id,kills_raw) VALUES (?,?,?)",
                (ship_id, user_id, kills_raw)
            )
            return cur.lastrowid

    async def add_op(self, ship_id: int, user_id: Optional[int], debrief: str) -> int:
        async with self.connect() as conn:
            cur = await conn.execute(
                "INSERT INTO ship_ops(ship_id,user_id,debrief) VALUES (?,?,?)",
                (ship_id, user_id, debrief)
            )
            return cur.lastrowid

    # ---------- Instances (sharing) ----------
    async def register_instance(self, ship_id: int, guild_id: int, channel_id: int, message_id: int, is_original: bool):
        async with self.connect() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO ship_instances(ship_id,guild_id,channel_id,message_id,is_original) "
                "VALUES (?,?,?,?,?)",
                (ship_id, guild_id, channel_id, message_id, 1 if is_original else 0)
            )

    async def get_instances(self, ship_id: int) -> List[Dict[str, Any]]:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT * FROM ship_instances WHERE ship_id=? ORDER BY created_at",
                (ship_id,)
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]

    # ---------- Per-ship auth ----------
    async def add_ship_auth_user(self, ship_id: int, user_id: int, authed_by: Optional[int]):
        async with self.connect() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO ship_auth_users(ship_id,user_id,authed_by) VALUES (?,?,?)",
                (ship_id, user_id, authed_by)
            )

    async def is_user_authorized_for_ship(self, ship_id: int, user_id: int) -> bool:
        async with self.connect() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM ship_auth_users WHERE ship_id=? AND user_id=?",
                (ship_id, user_id)
            )
            return (await cur.fetchone()) is not None

    async def search_ship_names(self, guild_id: int, war_id: int, query: str, limit: int = 25, exclude_dead: bool = True) -> list[str]:
        q = f"%{query.strip()}%" if query else "%"
        sql = """
          SELECT name
          FROM ships
          WHERE guild_id=? AND war_id=? AND name LIKE ? COLLATE NOCASE
        """
        params = [guild_id, war_id, q]
        if exclude_dead:
            sql += " AND LOWER(status) != 'dead'"
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        async with self.connect() as conn:
            cur = await conn.execute(sql, params)
            return [r[0] for r in await cur.fetchall()]

        

    async def get_guild_auth_roles(self, guild_id: int) -> list[int]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT role_id FROM guild_auth_roles WHERE guild_id=? ORDER BY role_id", (guild_id,))
            return [int(rid) for (rid,) in await cur.fetchall()]

    async def get_guild_auth_users(self, guild_id: int) -> list[int]:
        async with self.connect() as conn:
            cur = await conn.execute("SELECT user_id FROM guild_auth_users WHERE guild_id=? ORDER BY user_id", (guild_id,))
            return [int(uid) for (uid,) in await cur.fetchall()]