
## `bot.py`
```python
import os
import logging
import discord
from discord.ext import commands

from shiptracker.config import Settings
from shiptracker.db.dao import Database
from shiptracker.domain.ships_service import ShipService
from shiptracker.domain.auth_service import AuthService

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

    async def setup_hook(self):
        await db.setup(settings.schema_path)

        # Services
        self.service = ShipService(db, settings.war_number)
        self.service_auth = AuthService(self, db, self.service, settings)

        # Load cogs
        await self.load_extension("shiptracker.cogs.error_handler")
        await self.load_extension("shiptracker.cogs.cache_invalidator")
        await self.load_extension("shiptracker.cogs.admin")
        await self.load_extension("shiptracker.cogs.ships")

        from shiptracker.ui.views import ShipView
        instances = []
        # It's okay if this is a lot; add_view is cheap.
        async with db.connect() as conn:
            cur = await conn.execute("SELECT DISTINCT ship_id, (SELECT war_id FROM ships s WHERE s.id = ship_id) AS war_id FROM ship_instances")
            instances = await cur.fetchall()
        for ship_id, war_id in instances:
            self.add_view(ShipView(ship_id=int(ship_id), war_id=int(war_id), mode="main"))

        # Component router listener
        from shiptracker.ui.views import handle_component
        @self.listen("on_interaction")
        async def _route_components(interaction: discord.Interaction):
            if interaction.type is discord.InteractionType.component:
                await handle_component(interaction)

        if os.getenv("SYNC_CMDS_ON_START", "1") == "1":
            await self.tree.sync()

bot = ShipTrackerBot()
bot.db = db  # simple DI

@bot.listen("on_interaction")
async def _route_components(interaction: discord.Interaction):
    await handle_component(interaction)
    
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id}) — War {settings.war_number}")

bot.run(settings.token)
