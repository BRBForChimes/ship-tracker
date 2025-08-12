from discord.ext import commands
from shiptracker.utils.errors import NotAuthorized

def require_auth_any_guild(ship_name_param: str):
    """
    Decorator for slash commands to verify cross-guild auth for a given ship name param.
    """
    def predicate():
        async def inner(interaction):
            ship_name = getattr(interaction.namespace, ship_name_param)
            ok = await interaction.client.service_auth.user_is_authorized_for_ship_any_guild(
                interaction.guild_id, ship_name, interaction.user.id
            )
            if not ok:
                raise NotAuthorized("You’re not authorized to do that for this ship.")
        return inner
    return commands.check(predicate())


def require_guild_auth():
    """
    Gate actions that don't target a specific ship yet (e.g., /ship post <name>)
    using guild-level authorization (roles/users in this guild).
    """
    def predicate():
        async def inner(interaction):
            member = interaction.user
            guild_id = interaction.guild_id
            role_ids = [r.id for r in getattr(member, "roles", [])] if hasattr(member, "roles") else []
            ok = await interaction.client.db.is_user_authorized_for_guild(guild_id, member.id, role_ids)
            if not ok:
                raise NotAuthorized("You’re not authorized to use this here.")
        return inner
    return commands.check(predicate())

def require_guild_admin():
    """
    Admin-only (Manage Guild) actions, e.g., managing authorized roles.
    """
    def predicate():
        async def inner(interaction):
            perms = getattr(interaction.user, "guild_permissions", None)
            if not perms or not (perms.manage_guild or perms.administrator):
                raise NotAuthorized("Admin (Manage Server) permission required.")
        return inner
    return commands.check(predicate())

def require_authorized_in_guild():
    def predicate():
        async def inner(interaction):
            member = interaction.user
            guild_id = interaction.guild_id
            role_ids = [r.id for r in getattr(member, "roles", [])] if hasattr(member, "roles") else []
            ok = await interaction.client.db.is_user_authorized_for_guild(guild_id, member.id, role_ids)
            if not ok:
                raise NotAuthorized("You’re not authorized to use this here.")
        return inner
    return commands.check(predicate())