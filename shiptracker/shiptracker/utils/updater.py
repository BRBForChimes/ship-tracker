import discord
from typing import Callable, Awaitable, Dict, Any, List, Optional

async def update_all_instances(
    bot: discord.Client,
    instances: list[Dict[str, Any]],
    build_embed: Callable[[], Awaitable[discord.Embed]],
    build_view: Callable[[], discord.ui.View] | None = None,
):
    embed = await build_embed()
    view = build_view() if build_view else None
    for inst in instances:
        try:
            channel = await bot.fetch_channel(inst["channel_id"])
            if not hasattr(channel, "fetch_message"):
                continue
            msg = await channel.fetch_message(inst["message_id"])
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logger = getattr(bot, "logger", None)
            if logger:
                logger.warning(f"Failed to update message {inst.get('message_id')} in {inst.get('channel_id')}: {e}")