import discord
from discord import app_commands
from discord.ext import commands
from shiptracker.utils.checks import require_guild_admin

class AdminAuth(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    auth_group = app_commands.Group(
        name="auth",
        description="Manage guild-level authorized roles and users"
    )

    # ---- USERS ----
    @auth_group.command(name="add_user", description="Add a guild-level authorized user (admin only)")
    @require_guild_admin()
    async def add_user(self, interaction: discord.Interaction, user: discord.User):
        users = await self.bot.db.get_guild_auth_users(interaction.guild_id)
        if user.id in users:
            await interaction.response.send_message(f"{user.mention} is already authorized.", ephemeral=True)
            return
        users.append(user.id)
        await self.bot.db.set_guild_auth_users(interaction.guild_id, users)
        await interaction.response.send_message(f"Added {user.mention} to authorized users.", ephemeral=True)

    @auth_group.command(name="remove_user", description="Remove a guild-level authorized user (admin only)")
    @require_guild_admin()
    async def remove_user(self, interaction: discord.Interaction, user: discord.User):
        users = await self.bot.db.get_guild_auth_users(interaction.guild_id)
        if user.id not in users:
            await interaction.response.send_message(f"{user.mention} is not in the authorized list.", ephemeral=True)
            return
        users.remove(user.id)
        await self.bot.db.set_guild_auth_users(interaction.guild_id, users)
        await interaction.response.send_message(f"Removed {user.mention} from authorized users.", ephemeral=True)

    # ---- ROLES ----
    @auth_group.command(name="add_role", description="Add a guild-level authorized role (admin only)")
    @require_guild_admin()
    async def add_role(self, interaction: discord.Interaction, role: discord.Role):
        roles = await self.bot.db.get_guild_auth_roles(interaction.guild_id)
        if role.id in roles:
            await interaction.response.send_message(f"{role.mention} is already authorized.", ephemeral=True)
            return
        roles.append(role.id)
        await self.bot.db.set_guild_auth_roles(interaction.guild_id, roles)
        self.bot.service_auth.invalidate_guild_roles(interaction.guild_id)
        await interaction.response.send_message(f"Added {role.mention} to authorized roles.", ephemeral=True)

    @auth_group.command(name="remove_role", description="Remove a guild-level authorized role (admin only)")
    @require_guild_admin()
    async def remove_role(self, interaction: discord.Interaction, role: discord.Role):
        roles = await self.bot.db.get_guild_auth_roles(interaction.guild_id)
        if role.id not in roles:
            await interaction.response.send_message(f"{role.mention} is not in the authorized list.", ephemeral=True)
            return
        roles.remove(role.id)
        await self.bot.db.set_guild_auth_roles(interaction.guild_id, roles)
        self.bot.service_auth.invalidate_guild_roles(interaction.guild_id)
        await interaction.response.send_message(f"Removed {role.mention} from authorized roles.", ephemeral=True)
    @auth_group.command(name="list", description="List authorized roles and users for this guild (admin only)")
    @require_guild_admin()  
    async def list_auth(self, interaction: discord.Interaction):
        roles = await self.bot.db.get_guild_auth_roles(interaction.guild_id)
        users = await self.bot.db.get_guild_auth_users(interaction.guild_id)

        # Build mentions if available; fall back to plain IDs if not resolvable
        guild = interaction.guild
        role_mentions = []
        for rid in roles:
            role = guild.get_role(rid) if guild else None
            role_mentions.append(role.mention if role else f"`{rid}`")

        user_mentions = []
        for uid in users:
            member = guild.get_member(uid) if guild else None
            user_mentions.append(member.mention if member else f"<@{uid}>")

        embed = discord.Embed(title="Authorized Access (This Guild)")
        embed.add_field(
            name="Roles",
            value=(" ".join(role_mentions) if role_mentions else "—"),
            inline=False,
        )
        embed.add_field(
            name="Users",
            value=(" ".join(user_mentions) if user_mentions else "—"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
    bot.tree.add_command(Admin.group)
