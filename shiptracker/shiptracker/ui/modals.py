import time
import discord
from typing import Optional

class ReturnModal(discord.ui.Modal, title="Return to Port"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(
            label="Where is the ship?", required=True, max_length=100
        )
        self.smokes = discord.ui.TextInput(
            label="How many smokes? (0–5)", required=False, max_length=2
        )
        self.notes = discord.ui.TextInput(
            label="Additional notes (optional)", style=discord.TextStyle.paragraph,
            required=False, max_length=1000
        )
        self.add_item(self.where)
        self.add_item(self.smokes)
        self.add_item(self.notes)


class StartRepairsModal(discord.ui.Modal, title="Start Repairs"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(
            label="Where is the drydock located?", required=True, max_length=100
        )
        self.add_item(self.where)


class FinishRepairsModal(discord.ui.Modal, title="Finish Repairs"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(
            label="Where is the ship parked?", required=True, max_length=100
        )
        self.notes = discord.ui.TextInput(
            label="Additional notes (optional)", style=discord.TextStyle.paragraph,
            required=False, max_length=1000
        )
        self.add_item(self.where)
        self.add_item(self.notes)


class NotesModal(discord.ui.Modal, title="Edit Notes"):
    def __init__(self, existing: Optional[str] = None):
        super().__init__()
        self.notes = discord.ui.TextInput(
            label="Notes (leave empty to clear)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            default=existing or ""
        )
        self.add_item(self.notes)


class EditModal(discord.ui.Modal, title="Edit Ship"):
    def __init__(self, ship: dict):
        super().__init__()
        self.name = discord.ui.TextInput(label="Name", default=ship.get("name", ""), max_length=64)
        self.status = discord.ui.TextInput(label="Status", default=ship.get("status", ""), max_length=32)
        self.damage = discord.ui.TextInput(
            label="Damage (0–5)", default=str(ship.get("damage") or 0),
            max_length=2, required=False
        )
        self.location = discord.ui.TextInput(
            label="Location", default=ship.get("location", "") or "",
            max_length=100, required=False
        )
        self.keys = discord.ui.TextInput(
            label="Keys", default=ship.get("keys", "") or "",
            max_length=200, required=False
        )
        for item in (self.name, self.status, self.damage, self.location, self.keys):
            self.add_item(item)


class LogModal(discord.ui.Modal, title="Log Actions"):
    def __init__(self):
        super().__init__()
        self.kills = discord.ui.TextInput(
            label="Kill log (optional)", required=False, max_length=1000
        )
        self.debrief = discord.ui.TextInput(
            label="Action report (optional)", style=discord.TextStyle.paragraph,
            required=False, max_length=1500
        )
        self.add_item(self.kills)
        self.add_item(self.debrief)


class AddUserModal(discord.ui.Modal, title="Authorise User on Ship"):
    def __init__(self):
        super().__init__()
        self.user = discord.ui.TextInput(
            label="User mention or ID", required=True, max_length=64
        )
        self.add_item(self.user)


class CreateShipModal(discord.ui.Modal, title="Create Ship"):
    """Collect Home Port / Regiment / Keys; all required."""
    def __init__(self, cog, name: str, ship_type: str):
        super().__init__()
        self.cog = cog
        self.ship_name = name
        self.ship_type = ship_type

        self.home_port = discord.ui.TextInput(label="Home Port", required=True, max_length=100)
        self.regiment = discord.ui.TextInput(label="Regiment", required=True, max_length=100)
        self.keys = discord.ui.TextInput(label="Keys", required=True, max_length=200)

        self.add_item(self.home_port)
        self.add_item(self.regiment)
        self.add_item(self.keys)

    async def on_submit(self, interaction: discord.Interaction):
        # Authorization check before creation
        if not await interaction.client.service_auth.user_is_authorized_in_guild(
            interaction.guild_id, interaction.user.id
        ):
            await interaction.response.send_message("❌ You are not authorized to create ships in this guild.", ephemeral=True)
            return

        from shiptracker.ui.embeds import ship_main_embed  # local import to avoid circular
        from shiptracker.ui.views import ShipView

        hp = self.home_port.value.strip()
        reg = self.regiment.value.strip()
        keys = self.keys.value.strip()
        lock_ts = int(time.time()) + 2 * 24 * 3600

        defaults = {
            "type": self.ship_type,
            "status": "Parked",
            "damage": 0,
            "location": hp,
            "home_port": hp,
            "regiment": reg,
            "keys": keys,
            "squad_lock_until": lock_ts,
        }

        ship = await self.cog.service.get_or_create_ship(interaction.guild_id, self.ship_name, defaults=defaults)

        # Confirmation
        await interaction.response.send_message(
            f"✅ Created **{ship['name']}** as **{self.ship_type}**. Squad lock until <t:{lock_ts}:f>.",
            ephemeral=True,
        )

        # Public embed post
        embed = ship_main_embed(ship)
        view = ShipView(ship, mode="main")
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)

        # Track the instance
        await interaction.client.db.register_instance(
            ship["id"], interaction.guild_id, interaction.channel_id, msg.id, is_original=True
        )
        interaction.client.service_auth.invalidate_ship_presence(ship["id"])
