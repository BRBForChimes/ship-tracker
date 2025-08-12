import time
import re
from __future__ import annotations
from typing import Dict, Any, List, Optional
from shiptracker.db.dao import Database

MENTION_RE = re.compile(r"<@!?(\d+)>")

class ShipService:
    def __init__(self, db: Database, war_number: int):
        self.db = db
        self.war_name = f"War {war_number}"
        self._war_ids: dict[int, int] = {}  # cache per guild

    async def current_war_id(self, guild_id: int) -> int:
        if guild_id not in self._war_ids:
            self._war_ids[guild_id] = await self.db.upsert_war(guild_id, self.war_name)
        return self._war_ids[guild_id]

    # ---- Ships ----
    async def get_or_create_ship(self, guild_id: int, name: str, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if ship:
            return ship
        defaults = defaults or {}
        ship_id = await self.db.add_ship(guild_id, war_id, name=name, **defaults)
        return await self.db.get_ship_by_id(ship_id)

    async def list_ships(self, guild_id: int) -> List[Dict[str, Any]]:
        war_id = await self.current_war_id(guild_id)
        return await self.db.list_ships(guild_id, war_id)

    async def update_field(self, guild_id: int, name: str, user_id: int, field: str, value: Any) -> Dict[str, Any]:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.update_ship_field(ship["id"], user_id, field, value)
        return await self.db.get_ship_by_id(ship["id"])

    # ---- Supplies ----
    async def set_supply(self, guild_id: int, name: str, resource: str, qty: int):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.set_supply(ship["id"], resource, qty)
        return await self.db.list_supplies(ship["id"])

    # ---- Logs/Kills/Ops ----
    async def add_log(self, guild_id: int, name: str, user_id: Optional[int], text: str) -> int:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        return await self.db.add_log(ship["id"], user_id, text)

    async def add_kill(self, guild_id: int, name: str, user_id: Optional[int], kills_raw: str) -> int:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        return await self.db.add_kill(ship["id"], user_id, kills_raw)

    async def add_op(self, guild_id: int, name: str, user_id: Optional[int], debrief: str) -> int:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        return await self.db.add_op(ship["id"], user_id, debrief)

    # ---- Sharing / instances ----
    async def register_instance(self, guild_id: int, name: str, channel_id: int, message_id: int, is_original: bool):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.register_instance(ship["id"], guild_id, channel_id, message_id, is_original)
        return await self.db.get_instances(ship["id"])

    async def instances_for_updates(self, guild_id: int, name: str):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        return await self.db.get_instances(ship["id"])

    async def _ensure_mutable(self, ship: dict):
        if (ship.get("status") or "").lower() == "dead":
            raise ValueError("This ship is marked Dead and is read-only.")
    
    async def set_status(self, ship_id: int, user_id: int, status: str):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.db.update_ship_field(ship_id, user_id, "status", status)

    async def set_location(self, ship_id: int, user_id: int, where: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.db.update_ship_field(ship_id, user_id, "location", (where or "").strip() or None)

    async def set_damage_clamped(self, ship_id: int, user_id: int, damage_str: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        dmg = 0
        if damage_str and damage_str.strip().isdigit():
            dmg = max(0, min(5, int(damage_str)))
        await self.db.update_ship_field(ship_id, user_id, "damage", dmg)

    async def set_notes(self, ship_id: int, user_id: int, notes: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        clean = (notes or "").strip()
        await self.db.update_ship_field(ship_id, user_id, "notes", clean if clean else None)

    async def refresh_squad_lock(self, ship_id: int, user_id: int, days: int = 2) -> int:
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        ts = int(time.time()) + days * 24 * 3600
        await self.db.update_ship_field(ship_id, user_id, "squad_lock_until", ts)
        return ts

    async def finish_repairs(self, ship_id: int, user_id: int, parked_where: str | None, notes: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_location(ship_id, user_id, parked_where)
        # set damage to 0, clear notes if empty, set status=Parked
        await self.db.update_ship_field(ship_id, user_id, "damage", 0)
        await self.set_notes(ship_id, user_id, notes)
        await self.set_status(ship_id, user_id, "Parked")

    async def start_repairs(self, ship_id: int, user_id: int, drydock_loc: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_location(ship_id, user_id, drydock_loc)
        await self.set_status(ship_id, user_id, "Repairing")

    async def depart(self, ship_id: int, user_id: int):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_status(ship_id, user_id, "Deployed")

    async def return_to_port(self, ship_id: int, user_id: int, where: str | None, smokes: str | None, addl_notes: str | None):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_location(ship_id, user_id, where)
        await self.set_damage_clamped(ship_id, user_id, smokes)
        await self.set_notes(ship_id, user_id, addl_notes)
        await self.set_status(ship_id, user_id, "Parked")

    async def mark_dead(self, ship_id: int, user_id: int):
        # once dead, ship becomes read-only
        await self.db.update_ship_field(ship_id, user_id, "status", "Dead")

    # --- Manage utilities ---
    async def edit_fields_bulk(self, ship_id: int, user_id: int, fields: dict):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        for k, v in fields.items():
            await self.db.update_ship_field(ship_id, user_id, k, v)

    async def log_kill_and_op(self, ship_id: int, user_id: int, kills_raw: str | None, debrief: str | None):
        if kills_raw and kills_raw.strip():
            await self.db.add_kill(ship_id, user_id, kills_raw.strip())
        if debrief and debrief.strip():
            await self.db.add_op(ship_id, user_id, debrief.strip())

    async def gen_one_time_share_code(self, ship_id: int, user_id: int) -> str:
        import secrets, string
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        await self.db.update_ship_field(ship_id, user_id, "share_code", code)
        return code

    async def consume_share_code(self, code: str) -> Optional[int]:
        # look up ship by code and clear it (one-time)
        async with self.db.connect() as conn:
            cur = await conn.execute("SELECT id FROM ships WHERE share_code=?", (code,))
            row = await cur.fetchone()
            if not row:
                return None
            ship_id = int(row[0])
            await conn.execute("UPDATE ships SET share_code=NULL WHERE id=?", (ship_id,))
            return ship_id

    async def add_ship_auth_user_text(self, ship_id: int, user_id: int, authed_by: int) -> bool:
        # parse mention or ID
        m = MENTION_RE.fullmatch(user_id.strip()) if isinstance(user_id, str) else None
        uid = int(m.group(1)) if m else int(user_id)
        await self.db.add_ship_auth_user(ship_id, uid, authed_by)
        return True    
    
    # ---- History
    async def list_ships_in_war(self, guild_id: int, war_name: str):
        return await self.db.list_ships_in_war(guild_id, war_name)

    async def list_wars(self, guild_id: int):
        return await self.db.list_wars(guild_id)

    async def end_current_war(self, guild_id: int):
        war_id = await self.current_war_id(guild_id)
        await self.db.end_war(war_id)

    async def set_lock_for_days(self, guild_id: int, name: str, user_id: int, days: int = 2) -> int:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship: raise ValueError("Ship not found")
        ts = int(time.time()) + days * 24 * 3600
        await self.db.update_ship_field(ship["id"], user_id, "squad_lock_until", ts)
        return ts

    async def set_lock_epoch(self, guild_id: int, name: str, user_id: int, epoch: int | None):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship: raise ValueError("Ship not found")
        await self.db.update_ship_field(ship["id"], user_id, "squad_lock_until", epoch)
        return epoch

    async def import_from_share_code(self, target_guild_id: int, user_id: int, code: string) -> dict:
        """Consume a one-time code, copy core fields into this guild's current war, return the new ship row."""
        origin_ship_id = await self.consume_share_code(code)  # one-time; returns ship_id or None
        if not origin_ship_id:
            raise ValueError("Invalid or already-used share code.")

        origin = await self.db.get_ship_by_id(origin_ship_id)
        if not origin:
            raise ValueError("Origin ship not found.")

        war_id = await self.current_war_id(target_guild_id)

        # copy core fields; no history/instances carried over
        fields = {
            "type": origin.get("type"),
            "name": origin.get("name"),
            "status": origin.get("status"),
            "damage": origin.get("damage"),
            "location": origin.get("location"),
            "home_port": origin.get("home_port"),
            "notes": origin.get("notes"),
            "keys": origin.get("keys"),
            "image_url": origin.get("image_url"),
            "regiment": origin.get("regiment"),
            "squad_lock_until": origin.get("squad_lock_until"),
        }
        # Ensure uniqueness in target guild/war; if name collides, append a suffix
        name = fields["name"] or "Unnamed"
        existing = await self.db.get_ship(target_guild_id, war_id, name)
        if existing:
            suffix = 2
            base = name
            while await self.db.get_ship(target_guild_id, war_id, f"{base} ({suffix})"):
                suffix += 1
            fields["name"] = f"{base} ({suffix})"

        new_id = await self.db.add_ship(target_guild_id, war_id, **fields)
        return await self.db.get_ship_by_id(new_id)

    async def ensure_for_post(self, guild_id: int, identifier: str) -> dict:
        """If identifier looks like a share code, import; else treat as name and create if missing."""
        if CODE_RE.match(identifier.strip()):
            return await self.import_from_share_code(guild_id, user_id=0, code=identifier.strip())  # user_id only used in updates; import is an insert
        # else treat as name
        return await self.get_or_create_ship(guild_id, identifier.strip())