import traceback
import discord
from discord.ext import commands
from shiptracker.utils.errors import ShipTrackerError

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        original = getattr(error, "original", error)
        if isinstance(original, ShipTrackerError):
            msg = str(original) or "Something went wrong."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        # Fallbacks
        if isinstance(original, discord.Forbidden):
            text = "I don’t have permission to do that here."
        elif isinstance(original, discord.HTTPException):
            text = "Discord API error — try again soon."
        else:
            text = "Unexpected error. The logs will have details."
            self.bot.logger.error("Unhandled error: %s", "".join(traceback.format_exception(error)))
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
