import discord
from discord.ext import commands, tasks

from utils import console_capture, emoji_manager
from utils.components import error_layout, info_layout
from utils.loggers import _get_webhook
import config


class Console(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.console_dump_loop.start()

    def cog_unload(self):
        self.console_dump_loop.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="console", aliases=["consolelogs"], help="Fetch recent console/application logs. Usage: console [lines]")
    async def console_cmd(self, ctx: commands.Context, lines: int = 40):
        e = emoji_manager.get
        lines = max(1, min(lines, 200))
        recent = console_capture.get_lines(lines)

        if not recent:
            return await ctx.send(view=error_layout("No Logs", "Nothing has been captured yet."))

        text = "\n".join(recent)
        if len(text) <= 1900:
            await ctx.send(view=info_layout(f"{e('settings')} Console Output ({len(recent)} lines)", f"```\n{text}\n```"))
            return

        file = console_capture.get_file(lines)
        await ctx.send(
            view=info_layout(f"{e('settings')} Console Output", f"Last {len(recent)} lines attached."),
            file=discord.File(file, filename="console.txt"),
        )

    @commands.command(name="consolefile", aliases=["consoledump"], help="Get the full captured console buffer as a file, sent immediately.")
    async def consolefile(self, ctx: commands.Context):
        e = emoji_manager.get
        file = console_capture.get_file()
        await ctx.send(
            view=info_layout(f"{e('settings')} Console Dump", "Full captured buffer attached."),
            file=discord.File(file, filename="console.txt"),
        )

    @tasks.loop(hours=6)
    async def console_dump_loop(self):
        if not config.DEV_LOG_ERRORS_WEBHOOK_URL:
            return

        webhook = _get_webhook(config.DEV_LOG_ERRORS_WEBHOOK_URL, self.bot)
        if not webhook:
            return

        file = console_capture.get_file()
        try:
            await webhook.send(
                content="Periodic console log dump.",
                file=discord.File(file, filename="console.txt"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    @console_dump_loop.before_loop
    async def _before_console_dump_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Console(bot))
