from typing import Callable
from discord import Interaction
from discord.ext import commands
from shiptracker.utils.errors import NotAuthorized

async def _is_guild_authorized(interaction: Interaction) -> bool:
    """Checks if the user is authorized in this guild."""
    member = interaction.user
    guild_id = interaction.guild_id
    role_ids = [r.id for r in getattr(member, "roles", [])] if hasattr(member, "roles") else []
    return await interaction.client.db.is_user_authorized_for_guild(guild_id, member.id, role_ids)

def require_guild_auth() -> Callable:
    """
    Requires that the user is authorized for the current guild.
    """
    async def inner(interaction: Interaction):
        if not await _is_guild_authorized(interaction):
            raise NotAuthorized("You’re not authorized to use this here.")
    return commands.check(inner)

# Alias for semantic use
require_authorized_in_guild = require_guild_auth

def require_guild_admin() -> Callable:
    """
    Requires Manage Server (Manage Guild) or Administrator permission.
    """
    async def inner(interaction: Interaction):
        perms = getattr(interaction.user, "guild_permissions", None)
        if not perms or not (perms.manage_guild or perms.administrator):
            raise NotAuthorized("Admin (Manage Server) permission required.")
    return commands.check(inner)

def require_auth_any_guild(ship_name_param: str) -> Callable:
    """
    Requires that the user is authorized for the given ship name in ANY guild.
    Looks up ship_name_param from interaction.namespace or command kwargs.
    """
    async def inner(interaction: Interaction):
        # Try from namespace first, then from command kwargs
        ship_name = getattr(interaction.namespace, ship_name_param, None)
        if ship_name is None and hasattr(interaction, "command") and hasattr(interaction.command, "callback"):
            try:
                ship_name = interaction.data["options"][0]["value"]  # fallback for slash command raw data
            except Exception:
                pass

        if not ship_name:
            raise NotAuthorized("Ship name missing for authorization check.")

        ok = await interaction.client.service_auth.user_is_authorized_for_ship_any_guild(
            interaction.guild_id, ship_name, interaction.user.id
        )
        if not ok:
            raise NotAuthorized("You’re not authorized to do that for this ship.")
    return commands.check(inner)
