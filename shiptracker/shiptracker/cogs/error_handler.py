import traceback
import discord
from discord.ext import commands
from shiptracker.utils.errors import ShipTrackerError

class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        """Handles errors from application (slash) commands."""
        original = getattr(error, "original", error)

        # Known, user-facing errors
        if isinstance(original, ShipTrackerError):
            msg = str(original) or "Something went wrong."
            await self._safe_respond(interaction, msg)
            return

        # Permission or Discord-related issues
        if isinstance(original, discord.Forbidden):
            text = "I don’t have permission to do that here."
        elif isinstance(original, discord.HTTPException):
            text = "Discord API error — try again soon."
        else:
            text = "Unexpected error. The logs will have details."
            self.bot.logger.error(
                "Unhandled error in command: %s\n%s",
                getattr(interaction.command, 'name', 'unknown'),
                "".join(traceback.format_exception(original))
            )

        await self._safe_respond(interaction, text)

    async def _safe_respond(self, interaction: discord.Interaction, message: str):
        """Send a message without throwing if the response is already done."""
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
