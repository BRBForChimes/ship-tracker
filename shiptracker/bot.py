from shiptracker.domain.ships_service import ShipService
from shiptracker.domain.auth_service import AuthService
from shiptracker.config import Settings
from shiptracker.db.dao import Database
from shiptracker.ui.views import handle_component, ShipView

import os
import logging
import discord
from discord.ext import commands

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shiptracker")

# Intents (members intent needed for cross-guild auth role checks)
intents = discord.Intents.default()
intents.guilds = True
intents.members = True 
settings = Settings()
if not settings.token:
    raise RuntimeError("DISCORD_TOKEN is missing in .env")
if settings.war_number <= 0:
    raise RuntimeError("WAR must be a positive integer in .env")

db = Database(settings.database_path)

class ShipTrackerBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)
        self.logger = logger
        self.db = db  # make db accessible via bot.db

    async def setup_hook(self):
        # Create tables
        await self.db.setup(settings.schema_path)

        # Services
        self.service = ShipService(self.db, settings.war_number)
        self.service_auth = AuthService(self, self.db, self.service, settings)

        # Load cogs
        await self.load_extension("shiptracker.cogs.admin")
        await self.load_extension("shiptracker.cogs.ships")

        # Re-register persistent views for all known ship messages
        async with self.db.connect() as conn:
            cur = await conn.execute("SELECT DISTINCT ship_id FROM ship_instances")
            rows = await cur.fetchall()

        rehydrated = 0
        for (ship_id,) in rows:
            ship = await self.db.get_ship_by_id(int(ship_id))
            if ship:
                self.add_view(ShipView(ship, mode="main"))
                rehydrated += 1
        self.logger.info(f"Rehydrated {rehydrated} ship views.")

        # Component router (single registration)
        @self.listen("on_interaction")
        async def _route_components(interaction: discord.Interaction):
            if interaction.type is discord.InteractionType.component:
                await handle_component(interaction)

        # Fast sync during development
        dev_gid = os.getenv("DEV_GUILD_ID")
        try:
            if dev_gid:
                await self.tree.sync(guild=discord.Object(id=int(dev_gid)))
                self.logger.info(f"Synced commands to dev guild {dev_gid}.")
            elif os.getenv("SYNC_CMDS_ON_START", "1") == "1":
                await self.tree.sync()
                self.logger.info("Synced global commands.")
        except Exception as e:
            self.logger.warning(f"Slash command sync failed: {e}")
            
        async with db.connect() as conn:
            cur = await conn.execute("SELECT DISTINCT ship_id FROM ship_instances")
            rows = await cur.fetchall()

        for (ship_id,) in rows:
            ship = await db.get_ship_by_id(int(ship_id))
            if ship:
                self.add_view(ShipView(ship, mode="main"))

bot = ShipTrackerBot()

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id}) — War {settings.war_number}")

bot.run(settings.token)

