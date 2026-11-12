from discord.ext import commands

from utils import dev_state


class CommandControl(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_check(self.allowed)

    def cog_unload(self):
        self.bot.remove_check(self.allowed)

    async def allowed(self, ctx: commands.Context) -> bool:
        if not dev_state.disabled or ctx.command is None:
            return True
        reason = dev_state.disabled_reason(ctx.command.qualified_name)
        if reason is None or dev_state.exempt(ctx.author.id, getattr(ctx.author, "roles", ())):
            return True
        extra = f" {reason}" if reason else ""
        raise commands.CheckFailure(f"`{ctx.command.qualified_name}` is turned off right now.{extra}")


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandControl(bot))
