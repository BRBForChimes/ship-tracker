import discord
from discord.ext import commands


class CacheInvalidator(commands.Cog):
    """Auto-invalidates auth caches when roles or members change."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _safe_invoke(self, method_name: str, *args):
        method = getattr(self.bot.service_auth, method_name, None)
        if callable(method):
            method(*args)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            self._safe_invoke("invalidate_member", after.guild.id, after.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        self._safe_invoke("invalidate_guild_roles", role.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self._safe_invoke("invalidate_member", member.guild.id, member.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(CacheInvalidator(bot))
