import logging

import discord
from discord.ext import commands, tasks

import config

log = logging.getLogger("soward.events.presence")

_status_index = 0
_statuses = [
    lambda bot: f"{len(bot.guilds)} servers",
    lambda bot: f"{sum(g.member_count or 0 for g in bot.guilds):,} members",
    lambda bot: f"{config.BOT_NAME} • prefix-only",
]

def setup(bot: commands.Bot) -> None:
    @bot.listen("on_ready")
    async def _start_presence_rotation():
        if getattr(bot, "_presence_loop_started", False):
            return
        bot._presence_loop_started = True
        rotate_presence.start(bot)

@tasks.loop(seconds=30)
async def rotate_presence(bot: commands.Bot):
    global _status_index
    text = _statuses[_status_index % len(_statuses)](bot)
    _status_index += 1
    try:
        await bot.change_presence(activity=discord.Game(name=text))
    except Exception as exc:
        log.debug("Failed to update presence: %s", exc)
