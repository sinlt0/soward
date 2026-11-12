import logging

import discord
from discord.ext import commands, tasks

from utils import presence_rotation

log = logging.getLogger("zyro.presence")


class PresenceRotator(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rotator.start()

    def cog_unload(self):
        self.rotator.cancel()

    @tasks.loop(seconds=15)
    async def rotator(self):
        try:
            await presence_rotation.tick(self.bot)
        except discord.HTTPException:
            log.debug("Presence update failed", exc_info=True)

    @rotator.before_loop
    async def _before_rotator(self):
        await self.bot.wait_until_ready()
        await presence_rotation.load()


async def setup(bot: commands.Bot):
    await bot.add_cog(PresenceRotator(bot))
