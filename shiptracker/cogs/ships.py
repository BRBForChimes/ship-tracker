import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from shiptracker.domain.ships_service import ShipService
from shiptracker.ui.embeds import ship_card
from shiptracker.utils.validators import validate_name, validate_url, clamp_text, parse_bool_or_int
from shiptracker.utils.checks import require_auth_any_guild
from shiptracker.utils.updater import update_all_instances

class Ships(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service: ShipService = bot.service

    async def _ship_name_autocomplete(self, interaction: discord.Interaction, current: str):
        # scope to current war for this guild; exclude “Dead”
        war_id = await self.service.current_war_id(interaction.guild_id)
        names = await self.bot.db.search_ship_names(interaction.guild_id, war_id, current, limit=25, exclude_dead=True)
        return [app_commands.Choice(name=n, value=n) for n in names]
    
    group = app_commands.Group(name="ship", description="Manage ships")


    @group.command(name="list", description="List ships in the current war")
    @require_auth_any_guild("name")

    async def list_cmd(self, interaction: discord.Interaction):
        ships = await self.service.list_ships(interaction.guild_id)
        if not ships:
            await interaction.response.send_message("No ships yet.", ephemeral=True)
            return
        text = "\n".join(f"• {s['name']} — {s.get('status','?')}" for s in ships)
        await interaction.response.send_message(text)

    @group.command(name="update", description="Update a ship field")
    @app_commands.describe(field="status|damage|location|home_port|notes|regiment|keys|image_url|type|squad_lock_until",
                           value="New value")
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=Ships._ship_name_autocomplete)
    async def update(self, interaction: discord.Interaction, name: str, field: str, value: str):
        name = validate_name(name)
        if field == "image_url":
            value = validate_url(value)
        elif field in {"notes","damage","location","home_port","regiment","status","type","keys"}:
            value = clamp_text(value)
        elif field == "squad_lock_until":
            try:
                value = int(value)
            except ValueError:
                await interaction.response.send_message("squad_lock_until must be an integer Unix timestamp.", ephemeral=True)
                return
        else:
            await interaction.response.send_message("Unsupported field.", ephemeral=True)
            return

        ship = await self.service.update_field(interaction.guild_id, name, interaction.user.id, field, value)
        instances = await self.service.instances_for_updates(interaction.guild_id, name)
        async def build():
            supplies = await self.bot.db.list_supplies(ship["id"])
            return ship_card(ship, supplies)
        await update_all_instances(self.bot, instances, build)
        await interaction.response.send_message("Updated.", ephemeral=True)
        
    @group.command(name="supply", description="Set a supply quantity")
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=Ships._ship_name_autocomplete)
    async def supply(self, interaction: discord.Interaction, name: str, resource: str, quantity: int):
        name = validate_name(name)
        supplies = await self.service.set_supply(interaction.guild_id, name, resource, quantity)

        # Update all instances (build embed using fresh ship data)
        war_id = await self.service.current_war_id(interaction.guild_id)
        ship = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
        instances = await self.service.instances_for_updates(interaction.guild_id, name)
        async def build():
            return ship_card(ship, supplies)
        await update_all_instances(self.bot, instances, build)
        pretty = ", ".join(f"{r}: {q}" for r, q in supplies)
        await interaction.response.send_message(f"Supplies for **{name}** → {pretty}", ephemeral=True)
        
    @Ships.group.command(name="post", description="Create/import (if needed) and post a ship card with buttons")
    @app_commands.describe(name_or_code="Ship name OR one-time share code")
    @require_authorized_in_guild()
    @app_commands.autocomplete(name=Ships._ship_name_autocomplete)
    async def post(self, interaction: discord.Interaction, name_or_code: str):
        ident = name_or_code.strip()
        try:
            # Import if code; else create/get by name
            if CODE_RE.match(ident):
                ship = await self.service.import_from_share_code(interaction.guild_id, interaction.user.id, ident)
            else:
                ship = await self.service.get_or_create_ship(interaction.guild_id, ident)

            embed = ship_main_embed(ship)
            view = ShipView(ship, mode="main")
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # Track this posted instance
            await self.bot.db.register_instance(ship["id"], interaction.guild_id, interaction.channel_id, msg.id, is_original=True)
            self.bot.service_auth.invalidate_ship_presence(ship["id"])

        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

        

async def setup(bot: commands.Bot):
    await bot.add_cog(Ships(bot))
    bot.tree.add_command(Ships.group)
