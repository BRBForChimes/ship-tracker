# shiptracker/cogs/ships.py
import re
import discord
from discord import app_commands
from discord.ext import commands

from shiptracker.ui.modals import CreateShipModal
from shiptracker.domain.ships_service import ShipService
from shiptracker.ui.embeds import ship_main_embed
from shiptracker.ui.views import ShipView, AddShipTypeView
from shiptracker.utils.validators import validate_name, validate_url, clamp_text
from shiptracker.utils.checks import require_auth_any_guild, require_authorized_in_guild
from shiptracker.utils.updater import update_all_instances

# One-time share codes: 8 uppercase letters/numbers
CODE_RE = re.compile(r"^[A-Z0-9]{8}$")


class Ships(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service: ShipService = bot.service

    # Command group definition
    group = app_commands.Group(name="ship", description="Ship commands")

    # ------- Helpers -------

    async def _ship_name_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for ship names in the current war (excluding Dead ships)."""
        war_id = await self.service.current_war_id(interaction.guild_id)
        names = await self.bot.db.search_ship_names(
            interaction.guild_id, war_id, current, limit=25, exclude_dead=True
        )
        return [app_commands.Choice(name=n, value=n) for n in names]

    # ------- Commands -------

    @group.command(name="list", description="List ships in the current war")
    @require_authorized_in_guild()
    async def list_cmd(self, interaction: discord.Interaction):
        """Lists all ships in the current war for this guild."""
        ships = await self.service.list_ships(interaction.guild_id)
        if not ships:
            await interaction.response.send_message("No ships yet.", ephemeral=True)
            return

        text = "\n".join(f"• {s['name']} — {s.get('status', '?')}" for s in ships)
        await interaction.response.send_message(text, ephemeral=True)

    @group.command(name="update", description="Update a ship field")
    @app_commands.describe(
        field="status|damage|location|home_port|notes|regiment|keys|image_url|type|squad_lock_until",
        value="New value (damage: 0–5; squad_lock_until: unix timestamp)"
    )
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=_ship_name_autocomplete)
    async def update(self, interaction: discord.Interaction, name: str, field: str, value: str):
        """Updates a specific field of a ship."""
        name = validate_name(name)

        # Field validation
        if field == "image_url":
            value = validate_url(value)
        elif field in {"notes", "location", "home_port", "regiment", "status", "type", "keys"}:
            value = clamp_text(value)
        elif field == "damage":
            if not value.strip().isdigit():
                await interaction.response.send_message("Damage must be an integer 0–5.", ephemeral=True)
                return
            value = max(0, min(5, int(value)))
        elif field == "squad_lock_until":
            try:
                value = int(value)
            except ValueError:
                await interaction.response.send_message(
                    "squad_lock_until must be an integer Unix timestamp.", ephemeral=True
                )
                return
        else:
            await interaction.response.send_message("Unsupported field.", ephemeral=True)
            return

        # Update field
        await self.service.update_field(interaction.guild_id, name, interaction.user.id, field, value)

        # Refresh embeds everywhere
        instances = await self.service.instances_for_updates(interaction.guild_id, name)
        war_id = await self.service.current_war_id(interaction.guild_id)

        async def build():
            war_id = await self.service.current_war_id(interaction.guild_id)
            fresh = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
            return ship_main_embed(fresh)

        def build_view():
            # You need the same fresh data for status-sensitive buttons
            # If you want absolutely fresh here, re-fetch inside build_view too.
            # For consistency with build(), fetch once outside then close over.
            return ShipView(fresh, mode="main")  # make sure `fresh` is in scope

        await update_all_instances(self.bot, instances, build, build_view)
        
        await interaction.response.send_message("Updated.", ephemeral=True)

    @group.command(name="supply", description="Set a supply quantity")
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=_ship_name_autocomplete)
    async def supply(self, interaction: discord.Interaction, name: str, resource: str, quantity: int):
        """Sets the supply quantity for a ship."""
        name = validate_name(name)
        supplies = await self.service.set_supply(interaction.guild_id, name, resource, quantity)

        # Refresh embeds everywhere
        war_id = await self.service.current_war_id(interaction.guild_id)
        instances = await self.service.instances_for_updates(interaction.guild_id, name)

        async def build():
            war_id = await self.service.current_war_id(interaction.guild_id)
            fresh = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
            return ship_main_embed(fresh)

        def build_view():
            # You need the same fresh data for status-sensitive buttons
            # If you want absolutely fresh here, re-fetch inside build_view too.
            # For consistency with build(), fetch once outside then close over.
            return ShipView(fresh, mode="main")  # make sure `fresh` is in scope

        await update_all_instances(self.bot, instances, build, build_view)

        pretty = ", ".join(f"{r}: {q}" for r, q in supplies)
        await interaction.response.send_message(f"Supplies for **{name}** → {pretty}", ephemeral=True)

    @group.command(name="post", description="Create/import and post a ship card with buttons")
    @app_commands.describe(name_or_code="Ship name OR one-time share code")
    @require_authorized_in_guild()
    async def post(self, interaction: discord.Interaction, name_or_code: str):
        """Posts an interactive ship card to the channel."""
        ident = name_or_code.strip()
        try:
            if CODE_RE.match(ident):
                ship = await self.service.import_from_share_code(interaction.guild_id, interaction.user.id, ident)
            else:
                ship = await self.service.get_or_create_ship(interaction.guild_id, ident)

            embed = ship_main_embed(ship)
            view = ShipView(ship, mode="main")
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # Track posted instance for updates
            await self.bot.db.register_instance(
                ship["id"], interaction.guild_id, interaction.channel_id, msg.id, is_original=True
            )
            self.bot.service_auth.invalidate_ship_presence(ship["id"])

        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @group.command(name="add", description="Create a new ship (guided)")
    @require_authorized_in_guild()
    async def add(self, interaction: discord.Interaction, name: str):
        """Starts the guided ship creation process."""
        name = validate_name(name)

        war_id = await self.service.current_war_id(interaction.guild_id)
        existing = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
        if existing:
            await interaction.response.send_message(
                f"A ship named **{name}** already exists in this war.", ephemeral=True
            )
            return

        view = AddShipTypeView(self, name)
        await interaction.response.send_message(
            f"Creating **{name}** — select a type:", view=view, ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Ships(bot))
    if bot.tree.get_command("ship") is None:  # Avoid duplicate group registration
        bot.tree.add_command(Ships.group)
