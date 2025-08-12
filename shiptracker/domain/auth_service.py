from __future__ import annotations
from typing import List, Optional, Set, Dict
import discord
from shiptracker.db.dao import Database
from shiptracker.utils.cache import TTLCache
from shiptracker.config import Settings

class AuthService:
    def __init__(self, bot: discord.Client, db: Database, ship_service, settings: Settings):
        self.bot = bot
        self.db = db
        self.ship_service = ship_service

        # Caches
        self.member_roles_cache = TTLCache[tuple[int, int], Set[int]](settings.auth_member_ttl)  # (guild_id,user_id) -> role ids
        self.auth_roles_map_cache = TTLCache[int, Set[int]](settings.auth_roles_map_ttl)         # guild_id -> authorized role ids
        self.ship_instance_guilds_cache = TTLCache[int, List[int]](settings.auth_instance_guilds_ttl)  # ship_id -> [guild_ids]

    async def _get_member_role_ids(self, guild_id: int, user_id: int) -> Set[int]:
        key = (guild_id, user_id)
        cached = self.member_roles_cache.get(key)
        if cached is not None:
            return cached
        guild = self.bot.get_guild(guild_id)
        role_ids: Set[int] = set()
        if guild:
            try:
                member = await guild.fetch_member(user_id)
                role_ids = {r.id for r in getattr(member, "roles", [])}
            except (discord.NotFound, discord.Forbidden):
                role_ids = set()
        self.member_roles_cache.set(key, role_ids)
        return role_ids

    async def _get_guild_auth_roles(self, guild_id: int) -> Set[int]:
        cached = self.auth_roles_map_cache.get(guild_id)
        if cached is not None:
            return cached
        roles_map = await self.db.get_guild_auth_roles_many([guild_id])
        role_ids = roles_map.get(guild_id, set())
        self.auth_roles_map_cache.set(guild_id, role_ids)
        return role_ids

    async def _get_ship_presence_guilds(self, ship_id: int, home_guild_id: int) -> List[int]:
        cached = self.ship_instance_guilds_cache.get(ship_id)
        if cached is not None:
            return cached
        guild_ids = {int(home_guild_id)}
        guild_ids.update(await self.db.get_instance_guild_ids(ship_id))
        lst = list(guild_ids)
        self.ship_instance_guilds_cache.set(ship_id, lst)
        return lst

    async def user_is_authorized_for_ship_any_guild(self, requesting_guild_id: int, ship_name: str, user_id: int) -> bool:
        war_id = await self.ship_service.current_war_id(requesting_guild_id)
        ship = await self.db.get_ship(requesting_guild_id, war_id, ship_name)
        if not ship:
            return False

        ship_id = ship["id"]

        # 1) Per-ship auth
        if await self.db.is_user_authorized_for_ship(ship_id, user_id):
            return True

        # 2) Guild-level user auth across ANY presence guild
        presence_guilds = await self._get_ship_presence_guilds(ship_id, int(ship["guild_id"]))
        if await self.db.is_user_in_guild_auth_users_many(presence_guilds, user_id):
            return True

        # 3) Guild-level role auth across ANY presence guild
        for gid in presence_guilds:
            auth_roles = await self._get_guild_auth_roles(gid)
            if not auth_roles:
                continue
            user_role_ids = await self._get_member_role_ids(gid, user_id)
            if user_role_ids & auth_roles:
                return True

        return False

    # Invalidation hooks (call on changes)
    def invalidate_member(self, guild_id: int, user_id: int):
        self.member_roles_cache.invalidate((guild_id, user_id))

    def invalidate_guild_roles(self, guild_id: int):
        self.auth_roles_map_cache.invalidate(guild_id)

    def invalidate_ship_presence(self, ship_id: int):
        self.ship_instance_guilds_cache.invalidate(ship_id)
