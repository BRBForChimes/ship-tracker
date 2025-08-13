
import discord
from discord import app_commands
from discord.ext import commands
from shiptracker.utils.checks import require_guild_admin


class AdminAuth(commands.Cog):
    """Admin-only auth management for guild-level roles and users."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Static group for /auth
    auth_group = app_commands.Group(
        name="auth",
        description="Manage guild-level authorized roles and users (admin only)"
    )

    # ---------- Internal helpers ----------

    async def _ensure_guild(self, interaction: discord.Interaction) -> bool:
        """Ensure this command is run in a guild."""
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return False
        return True

    async def _add_guild_user(self, guild_id: int, user_id: int) -> bool:
        users = await self.bot.db.get_guild_auth_users(guild_id)
        if user_id in users:
            return False
        users.append(user_id)
        await self.bot.db.set_guild_auth_users(guild_id, users)
        # If you cache guild-level authorized users, invalidate it:
        if hasattr(self.bot, "service_auth"):
            # Add this in your AuthService if not present
            invalidate = getattr(self.bot.service_auth, "invalidate_guild_users", None)
            if callable(invalidate):
                invalidate(guild_id)
        return True

    async def _remove_guild_user(self, guild_id: int, user_id: int) -> bool:
        users = await self.bot.db.get_guild_auth_users(guild_id)
        if user_id not in users:
            return False
        users.remove(user_id)
        await self.bot.db.set_guild_auth_users(guild_id, users)
        if hasattr(self.bot, "service_auth"):
            invalidate = getattr(self.bot.service_auth, "invalidate_guild_users", None)
            if callable(invalidate):
                invalidate(guild_id)
        return True

    async def _add_guild_role(self, guild_id: int, role_id: int) -> bool:
        roles = await self.bot.db.get_guild_auth_roles(guild_id)
        if role_id in roles:
            return False
        roles.append(role_id)
        await self.bot.db.set_guild_auth_roles(guild_id, roles)
        if hasattr(self.bot, "service_auth"):
            self.bot.service_auth.invalidate_guild_roles(guild_id)
        return True

    async def _remove_guild_role(self, guild_id: int, role_id: int) -> bool:
        roles = await self.bot.db.get_guild_auth_roles(guild_id)
        if role_id not in roles:
            return False
        roles.remove(role_id)
        await self.bot.db.set_guild_auth_roles(guild_id, roles)
        if hasattr(self.bot, "service_auth"):
            self.bot.service_auth.invalidate_guild_roles(guild_id)
        return True

    # ---------- USERS ----------

    @auth_group.command(name="add_user", description="Add a guild-level authorized user")
    @app_commands.guild_only()
    @require_guild_admin()
    async def add_user(self, interaction: discord.Interaction, user: discord.User):
        if not await self._ensure_guild(interaction):
            return
        ok = await self._add_guild_user(interaction.guild_id, user.id)
        if ok:
            await interaction.response.send_message(f"Added {user.mention} to authorized users.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is already authorized.", ephemeral=True)

    @auth_group.command(name="remove_user", description="Remove a guild-level authorized user")
    @app_commands.guild_only()
    @require_guild_admin()
    async def remove_user(self, interaction: discord.Interaction, user: discord.User):
        if not await self._ensure_guild(interaction):
            return
        ok = await self._remove_guild_user(interaction.guild_id, user.id)
        if ok:
            await interaction.response.send_message(f"Removed {user.mention} from authorized users.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is not in the authorized list.", ephemeral=True)

    # ---------- ROLES ----------

    @auth_group.command(name="add_role", description="Add a guild-level authorized role")
    @app_commands.guild_only()
    @require_guild_admin()
    async def add_role(self, interaction: discord.Interaction, role: discord.Role):
        if not await self._ensure_guild(interaction):
            return
        ok = await self._add_guild_role(interaction.guild_id, role.id)
        if ok:
            await interaction.response.send_message(f"Added {role.mention} to authorized roles.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{role.mention} is already authorized.", ephemeral=True)

    @auth_group.command(name="remove_role", description="Remove a guild-level authorized role")
    @app_commands.guild_only()
    @require_guild_admin()
    async def remove_role(self, interaction: discord.Interaction, role: discord.Role):
        if not await self._ensure_guild(interaction):
            return
        ok = await self._remove_guild_role(interaction.guild_id, role.id)
        if ok:
            await interaction.response.send_message(f"Removed {role.mention} from authorized roles.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{role.mention} is not in the authorized list.", ephemeral=True)

    # ---------- LIST ----------

    @auth_group.command(name="list", description="List authorized roles and users for this guild")
    @app_commands.guild_only()
    @require_guild_admin()
    async def list_auth(self, interaction: discord.Interaction):
        if not await self._ensure_guild(interaction):
            return

        roles = await self.bot.db.get_guild_auth_roles(interaction.guild_id)
        users = await self.bot.db.get_guild_auth_users(interaction.guild_id)

        guild = interaction.guild
        # Prefer mentions if resolvable
        role_bits = [(guild.get_role(r).mention if guild and guild.get_role(r) else f"<@&{r}>") for r in roles]
        user_bits = [(guild.get_member(u).mention if guild and guild.get_member(u) else f"<@{u}>") for u in users]

        embed = discord.Embed(title="Authorized Access (This Guild)")
        embed.add_field(name="Roles", value=(" ".join(role_bits) if role_bits else "—"), inline=False)
        embed.add_field(name="Users", value=(" ".join(user_bits) if user_bits else "—"), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminAuth(bot))
    # Avoid duplicate registration if the extension reloads
    if bot.tree.get_command("auth") is None:
        bot.tree.add_command(AdminAuth.auth_group)

