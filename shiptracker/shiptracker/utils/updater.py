import discord
from typing import Callable, Awaitable, Dict, Any, List, Optional

async def update_all_instances(
    bot: discord.Client,
    instances: List[Dict[str, Any]],
    build_embed: Callable[[], Awaitable[discord.Embed]],
    build_view: Optional[Callable[[], discord.ui.View]] = None
) -> None:
    """
    Update all tracked instances of a ship's message across channels.

    Args:
        bot: The Discord client/bot instance.
        instances: List of dicts with 'channel_id' and 'message_id'.
        build_embed: Async function returning the updated embed.
        build_view: Optional function returning a View for buttons.
    """
    embed = await build_embed()
    view = build_view() if build_view else None

    for inst in instances:
        try:
            channel = await bot.fetch_channel(inst["channel_id"])
            if not hasattr(channel, "fetch_message"):
                continue  # Skip if it's not a text-based channel

            msg = await channel.fetch_message(inst["message_id"])
            await msg.edit(embed=embed, view=view)

        except discord.NotFound:
            # Message or channel was deleted
            logger = getattr(bot, "logger", None)
            logger and logger.info(f"Message {inst['message_id']} in channel {inst['channel_id']} no longer exists.")
        except discord.Forbidden:
            logger = getattr(bot, "logger", None)
            logger and logger.warning(f"No permission to edit message {inst['message_id']} in {inst['channel_id']}.")
        except Exception as e:
            logger = getattr(bot, "logger", None)
            logger and logger.error(f"Failed to update message {inst['message_id']} in {inst['channel_id']}: {e}")
