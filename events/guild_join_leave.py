import logging

import discord
from discord.ext import commands

from utils import db, loggers
import config

log = logging.getLogger("soward.events.guild")

def setup(bot: commands.Bot) -> None:
    @bot.listen("on_guild_join")
    async def _on_guild_join(guild: discord.Guild):
        await db.raw_execute(
            "INSERT INTO guilds (guild_id, prefix, premium, server_np_enabled, incident_state) VALUES (?, ?, 0, ?, 0)"
            " ON CONFLICT(guild_id) DO NOTHING",
            (guild.id, config.DEFAULT_PREFIX, int(config.SERVER_NO_PREFIX_ENABLED_DEFAULT)),
        )
        log.info("Joined guild '%s' (%d), bootstrapped default config.", guild.name, guild.id)
        await loggers.log_guild_join(bot, guild)

    @bot.listen("on_guild_remove")
    async def _on_guild_remove(guild: discord.Guild):
        log.info("Removed from guild '%s' (%d).", guild.name, guild.id)
        await loggers.log_guild_leave(bot, guild)
