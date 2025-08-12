import discord
from typing import Callable, Awaitable, Dict, Any

async def update_all_instances(bot: discord.Client, instances: list[Dict[str, Any]],
                               build_embed: Callable[[], Awaitable[discord.Embed]]):
    embed = await build_embed()
    for inst in instances:
        try:
            channel = await bot.fetch_channel(inst["channel_id"])
            if not hasattr(channel, "fetch_message"):
                continue
            msg = await channel.fetch_message(inst["message_id"])
            await msg.edit(embed=embed)
        except Exception as e:
            logger = getattr(bot, "logger", None)
            if logger:
                logger.warning(f"Failed to update message {inst['message_id']} in {inst['channel_id']}: {e}")
