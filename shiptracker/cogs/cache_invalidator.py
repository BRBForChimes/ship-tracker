import discord
from discord.ext import commands

class CacheInvalidator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            self.bot.service_auth.invalidate_member(after.guild.id, after.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        self.bot.service_auth.invalidate_guild_roles(role.guild.id)

async def setup(bot: commands.Bot):
    await bot.add_cog(CacheInvalidator(bot))
