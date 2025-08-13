# shiptracker/domain/ships_service.py
from __future__ import annotations
import time
import re
from typing import Dict, Any, List, Optional

from shiptracker.db.dao import Database

# One-time share codes: 8 uppercase letters/numbers
CODE_RE = re.compile(r"^[A-Z0-9]{8}$")
MENTION_RE = re.compile(r"<@!?(\d+)>")


def _clean(s: Optional[str]) -> Optional[str]:
    """Trim text; return None if empty after trim."""
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def _clamp_damage(v: Optional[str | int]) -> int:
    """Clamp to 0–5 from string or int."""
    if v is None:
        return 0
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, iv))


class ShipService:
    """
    Core ship operations. War is a global numeric id (from .env WAR).
    """

    def __init__(self, db: Database, war_number: int):
        self.db = db
        self.war_id = int(war_number)

    async def current_war_id(self, _guild_id: int) -> int:
        # Ensure the war row exists once; return global id.
        await self.db.ensure_war_exists(self.war_id)
        return self.war_id

    # ---------- Ships ----------

    async def get_or_create_ship(
        self,
        guild_id: int,
        name: str,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        war_id = await self.current_war_id(guild_id)
        name = name.strip()
        existing = await self.db.get_ship(guild_id, war_id, name)
        if existing:
            return existing

        fields = dict(defaults or {})
        fields["name"] = name
        ship_id = await self.db.add_ship(guild_id, war_id, **fields)
        return await self.db.get_ship_by_id(ship_id)

    async def list_ships(self, guild_id: int):
        war_id = await self.current_war_id(guild_id)
        return await self.db.list_ships_for_guild(guild_id, war_id)

    async def update_field(self, guild_id: int, name: str, user_id: int, field: str, value):
        """Single-field update (propagates to linked copies)."""
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.update_field_linked(ship["id"], user_id, field, value)
        return await self.db.get_ship_by_id(ship["id"])

    # ---------- Supplies (kept per-copy) ----------

    async def set_supply(self, guild_id: int, name: str, resource: str, qty: int):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.set_supply(ship["id"], resource, int(qty))
        return await self.db.list_supplies(ship["id"])

    # ---------- Instances / Sharing ----------

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

    # ---------- Mutations (read-only if Dead) ----------

    async def _ensure_mutable(self, ship: dict):
        if (ship.get("status") or "").strip().lower() == "dead":
            raise ValueError("This ship is marked Dead and is read-only.")

    async def set_status(self, ship_id: int, user_id: int, status: str):
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        await self.db.update_field_linked(ship_id, user_id, "status", status)

    async def set_location(self, ship_id: int, user_id: int, where: str | None):
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        await self.db.update_field_linked(ship_id, user_id, "location", (where or "").strip() or None)

    async def set_damage_clamped(self, ship_id: int, user_id: int, damage_str: str | None):
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        dmg = 0
        if damage_str and damage_str.strip().isdigit():
            dmg = max(0, min(5, int(damage_str)))
        await self.db.update_field_linked(ship_id, user_id, "damage", dmg)

    async def set_notes(self, ship_id: int, user_id: int, notes: str | None):
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        clean = (notes or "").strip() or None
        await self.db.update_field_linked(ship_id, user_id, "notes", clean)

    async def refresh_squad_lock(self, ship_id: int, user_id: int, days: int = 2) -> int:
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        ts = int(time.time()) + days * 24 * 3600
        await self.db.update_field_linked(ship_id, user_id, "squad_lock_until", ts)
        return ts

    async def finish_repairs(self, ship_id: int, user_id: int, parked_where: str | None, notes: str | None):
        ship = await self.db.get_ship_by_id(ship_id); await self._ensure_mutable(ship)
        await self.db.update_field_linked(ship_id, user_id, "location", (parked_where or "").strip() or None)
        await self.db.update_field_linked(ship_id, user_id, "damage", 0)
        clean = (notes or "").strip() or None
        await self.db.update_field_linked(ship_id, user_id, "notes", clean)
        await self.db.update_field_linked(ship_id, user_id, "status", "Parked")

    async def start_repairs(self, ship_id: int, user_id: int, drydock_loc: Optional[str]):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_location(ship_id, user_id, drydock_loc)
        await self.set_status(ship_id, user_id, "Repairing")

    async def depart(self, ship_id: int, user_id: int):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_status(ship_id, user_id, "Deployed")

    async def return_to_port(self, ship_id: int, user_id: int, where: Optional[str], smokes: Optional[str | int], addl_notes: Optional[str]):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        await self.set_location(ship_id, user_id, where)
        await self.set_damage_clamped(ship_id, user_id, smokes)
        await self.set_notes(ship_id, user_id, addl_notes)
        await self.set_status(ship_id, user_id, "Parked")

    async def mark_dead(self, ship_id: int, user_id: int):
        # Once dead, ship becomes read-only (propagate to linked copies)
        await self.db.update_field_linked(ship_id, user_id, "status", "Dead")

    async def edit_fields_bulk(self, ship_id: int, user_id: int, fields: dict):
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)

        # Sanitize a few known fields
        if "damage" in fields:
            fields["damage"] = _clamp_damage(fields["damage"])
        for k in ("location", "home_port", "notes", "regiment", "keys", "status", "type", "image_url", "name"):
            if k in fields:
                fields[k] = _clean(fields[k])

        # Propagate each field to all linked copies
        for k, v in fields.items():
            await self.db.update_field_linked(ship_id, user_id, k, v)

    async def log_kill_and_op(self, ship_id: int, user_id: int, kills_raw: Optional[str], debrief: Optional[str]):
        # Kept per-copy by design; change if you want logs shared across guilds
        if kills_raw and kills_raw.strip():
            await self.db.add_kill(ship_id, user_id, kills_raw.strip())
        if debrief and debrief.strip():
            await self.db.add_op(ship_id, user_id, debrief.strip())

    # ---------- Sharing ----------

    async def gen_one_time_share_code(self, ship_id: int, user_id: int) -> str:
        import secrets, string
        ship = await self.db.get_ship_by_id(ship_id)
        await self._ensure_mutable(ship)
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        await self.db.update_ship_field(ship_id, user_id, "share_code", code)
        return code

    async def consume_share_code(self, code: str) -> Optional[int]:
        """Look up ship by code and clear it (one-use)."""
        async with self.db.connect() as conn:
            cur = await conn.execute("SELECT id FROM ships WHERE share_code=?", (code,))
            row = await cur.fetchone()
            if not row:
                return None
            ship_id = int(row[0])
            await conn.execute("UPDATE ships SET share_code=NULL WHERE id=?", (ship_id,))
            return ship_id

    async def import_from_share_code(self, target_guild_id: int, user_id: int, code: str) -> dict:
        origin_ship_id = await self.consume_share_code(code)
        if not origin_ship_id:
            raise ValueError("Invalid or already-used share code.")
        origin = await self.db.get_ship_by_id(origin_ship_id)
        if not origin:
            raise ValueError("Origin ship not found.")
        await self.current_war_id(target_guild_id)  # optional safety
        return origin

    # ---------- Lock helpers for slash usage (now linked) ----------

    async def set_lock_for_days(self, guild_id: int, name: str, user_id: int, days: int = 2) -> int:
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        ts = int(time.time()) + int(days) * 24 * 3600
        await self.db.update_field_linked(ship["id"], user_id, "squad_lock_until", ts)
        return ts

    async def set_lock_epoch(self, guild_id: int, name: str, user_id: int, epoch: Optional[int]):
        war_id = await self.current_war_id(guild_id)
        ship = await self.db.get_ship(guild_id, war_id, name)
        if not ship:
            raise ValueError("Ship not found")
        await self.db.update_field_linked(ship["id"], user_id, "squad_lock_until", int(epoch) if epoch else 0)
        return epoch

    # ---------- Helper for /ship post ----------

    async def ensure_for_post(self, guild_id: int, identifier: str) -> dict:
        """
        If identifier looks like a share code, import; else treat as name and create if missing.
        (Pass a real user_id to import_from_share_code where you call this in your cog, if you want audit.)
        """
        ident = identifier.strip()
        if CODE_RE.match(ident):
            # NOTE: this uses user_id=0 since ensure_for_post is used in places where we don't have the actor handy.
            # If you want audit, call import_from_share_code directly from the Cog with interaction.user.id.
            return await self.import_from_share_code(guild_id, user_id=0, code=ident)
        return await self.get_or_create_ship(guild_id, ident)
