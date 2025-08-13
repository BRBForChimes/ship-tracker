
import re
import discord
from discord import app_commands
from discord.ext import commands

from shiptracker.domain.ships_service import ShipService
from shiptracker.ui.embeds import ship_main_embed
from shiptracker.ui.views import ShipView, AddShipTypeView, _refresh_everywhere
from shiptracker.ui.modals import CreateShipModal
from shiptracker.utils.validators import validate_name, validate_url, clamp_text
from shiptracker.utils.checks import require_auth_any_guild, require_authorized_in_guild

CODE_RE = re.compile(r"^[A-Z0-9]{8}$")


class Ships(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service: ShipService = bot.service

    # define the group BEFORE any @group.command methods
    group = app_commands.Group(name="ship", description="Ship commands")

    # ---- Autocomplete helper (instance-scoped, current guild/war) ------------
    async def _ship_name_autocomplete(self, interaction: discord.Interaction, current: str):
        war_id = await self.service.current_war_id(interaction.guild_id)
        names = await self.bot.db.search_ship_names_in_guild(
            interaction.guild_id, war_id, current, limit=25, exclude_dead=True
        )
        return [app_commands.Choice(name=n, value=n) for n in names]

    # -------------------------- Commands --------------------------------------

    @group.command(name="list", description="List ships available in this guild (current war)")
    @require_authorized_in_guild()
    async def list_cmd(self, interaction: discord.Interaction):
        ships = await self.service.list_ships(interaction.guild_id)
        if not ships:
            await interaction.response.send_message("No ships here yet.", ephemeral=True)
            return
        text = "\n".join(f"• {s['name']} — {s.get('status','?')}" for s in ships)
        await interaction.response.send_message(text, ephemeral=True)

    @group.command(name="post", description="Post a ship card (by name or one-time share code)")
    @app_commands.describe(name_or_code="Ship name OR one-time share code")
    @require_authorized_in_guild()
    async def post(self, interaction: discord.Interaction, name_or_code: str):
        ident = name_or_code.strip()
        try:
            if CODE_RE.match(ident):
                # Share: do NOT clone; returns origin ship. We'll register a new instance in this guild.
                ship = await self.service.import_from_share_code(interaction.guild_id, interaction.user.id, ident)
            else:
                # Create or fetch a local ship in this guild
                ship = await self.service.get_or_create_ship(interaction.guild_id, ident)

            embed = ship_main_embed(ship)
            view = ShipView(ship, mode="main")
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

            # Register this message as an instance in THIS GUILD
            await self.bot.db.register_instance(
                ship["id"], interaction.guild_id, interaction.channel_id, msg.id,
                is_original=not CODE_RE.match(ident)
            )

            # Push the freshest state to all instances (all guilds) of this ship
            await _refresh_everywhere(self.bot, ship["id"])

        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @group.command(name="add", description="Create a new ship (guided UI)")
    @require_authorized_in_guild()
    async def add(self, interaction: discord.Interaction, name: str):
        # Validate and ensure it doesn't already exist locally
        name = validate_name(name)
        war_id = await self.service.current_war_id(interaction.guild_id)
        existing = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
        if existing:
            await interaction.response.send_message(
                f"A ship named **{name}** already exists in this war.", ephemeral=True
            )
            return

        # Show type selector; modal will follow after selection
        view = AddShipTypeView(self, name)
        await interaction.response.send_message(
            f"Creating **{name}** — select a type:", view=view, ephemeral=True
        )

    @group.command(name="update", description="Update a ship field")
    @app_commands.describe(
        field="status|damage|location|home_port|notes|regiment|keys|image_url|type|squad_lock_until",
        value="New value (damage: 0–5; squad_lock_until: unix timestamp)",
    )
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=_ship_name_autocomplete)
    async def update(self, interaction: discord.Interaction, name: str, field: str, value: str):
        name = validate_name(name)

        # Normalize/validate input by field
        if field == "image_url":
            value = validate_url(value)
        elif field in {"notes", "location", "home_port", "regiment", "status", "type", "keys"}:
            value = clamp_text(value)
        elif field == "damage":
            v = (value or "").strip()
            if not v.isdigit():
                await interaction.response.send_message("Damage must be an integer 0–5.", ephemeral=True)
                return
            iv = max(0, min(5, int(v)))
            value = iv
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

        # Persist -> returns the ship row so we can refresh everywhere
        ship = await self.service.update_field(interaction.guild_id, name, interaction.user.id, field, value)

        # Cross-guild refresh (embed + buttons) on ALL instances of this ship
        await _refresh_everywhere(self.bot, ship["id"])
        await interaction.response.send_message("Updated.", ephemeral=True)

    @group.command(name="supply", description="Set a supply quantity (per-guild instance)")
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=_ship_name_autocomplete)
    async def supply(self, interaction: discord.Interaction, name: str, resource: str, quantity: int):
        name = validate_name(name)
        supplies = await self.service.set_supply(interaction.guild_id, name, resource, quantity)

        # Get the ship row (for id) then refresh all instances' embeds/views
        war_id = await self.service.current_war_id(interaction.guild_id)
        ship = await self.bot.db.get_ship(interaction.guild_id, war_id, name)
        if ship:
            await _refresh_everywhere(self.bot, ship["id"])

        pretty = ", ".join(f"{r}: {q}" for r, q in supplies)
        await interaction.response.send_message(f"Supplies for **{name}** → {pretty}", ephemeral=True)

        
    @group.command(name="image", description="Set a ship image from a PNG attachment")
    @app_commands.describe(
        name="Ship name (auto-complete)",
        file="PNG image to use on the ship card"
    )
    @require_auth_any_guild("name")
    @app_commands.autocomplete(name=_ship_name_autocomplete)
    async def image(self, interaction: discord.Interaction, name: str, file: discord.Attachment):
        # basic validation
        name = validate_name(name)

        # Check it looks like a PNG; Discord provides content_type most of the time
        ct = (file.content_type or "").lower()
        if not (ct.startswith("image/png") or file.filename.lower().endswith(".png")):
            await interaction.response.send_message("Please upload a **PNG** image.", ephemeral=True)
            return

        # (Optional) size guard — Discord allows up to 25MB on many servers,
        # but you can enforce a smaller limit if you prefer. Comment out if not needed.
        max_bytes = 8 * 1024 * 1024  # 8 MB
        if file.size and file.size > max_bytes:
            await interaction.response.send_message("PNG is too large (max 8 MB).", ephemeral=True)
            return

        # We don't need to download the file — the CDN url is permanent enough for embeds.
        image_url = file.url

        # Persist via the service path; this returns the ship row
        ship = await self.service.update_field(
            interaction.guild_id, name, interaction.user.id, "image_url", image_url
        )

        # Refresh every posted instance (across all guilds)
        await _refresh_everywhere(self.bot, ship["id"])

        await interaction.response.send_message("Image updated ✅", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ships(bot))
    # Avoid duplicate group registration if extension reloads
    if bot.tree.get_command("ship") is None:
        bot.tree.add_command(Ships.group)

