import time

import discord
from discord.ext import commands

from utils import cases, emoji_manager
from utils import security_settings as settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.converters import DurationConverter, format_duration
from utils.security_access import security_staff

NO_MENTIONS = discord.AllowedMentions.none()
STEP_KEYS = {"timeout": "warn_timeout_at", "kick": "warn_kick_at", "ban": "warn_ban_at"}


async def put(guild_id: int, key: str, value) -> None:
    await settings.put(guild_id, settings.find("automod", key), value)


class Ladder(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def summary(self, guild_id: int) -> str:
        get = lambda key: settings.get(guild_id, "automod", key)
        on = await get("warn_ladder_enabled")
        window = await get("warn_window")
        lines = [f"**Status:** {'on' if on else 'off'}", f"**Warnings count for:** {format_duration(window)}"]
        for name, key in STEP_KEYS.items():
            at = await get(key)
            extra = f" for {format_duration(await get('warn_timeout_duration'))}" if name == "timeout" and at else ""
            lines.append(f"**{name.title()}:** " + (f"at {at} warnings{extra}" if at else "off"))
        return "\n".join(lines)

    @commands.group(name="ladder", aliases=["warnladder", "warnsteps"], invoke_without_command=True, help="Warning ladder: timeout, kick and ban at set warning counts.")
    @commands.guild_only()
    @has_guild_permission("manage_messages")
    async def ladder(self, ctx: commands.Context):
        body = await self.summary(ctx.guild.id)
        body += "\n\n`ladder on|off` · `ladder timeout <warns> [duration]` · `ladder kick <warns>` · `ladder ban <warns>` · `ladder window <duration>` · `ladder check <member>`"
        await ctx.send(view=info_layout("Warning ladder", body))

    @ladder.command(name="on", help="Turn the ladder on.")
    @security_staff()
    async def ladder_on(self, ctx: commands.Context):
        await put(ctx.guild.id, "warn_ladder_enabled", True)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Warning ladder", await self.summary(ctx.guild.id)))

    @ladder.command(name="off", aliases=["disable"], help="Turn the ladder off.")
    @security_staff()
    async def ladder_off(self, ctx: commands.Context):
        await put(ctx.guild.id, "warn_ladder_enabled", False)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Warning ladder", "The ladder is **off**. Warnings are still recorded."))

    async def _step(self, ctx: commands.Context, name: str, count: int):
        if not 0 <= count <= 50:
            return await ctx.send(view=error_layout("Invalid number", "Use 1 to 50, or 0 to turn this step off."))
        await put(ctx.guild.id, STEP_KEYS[name], count)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Warning ladder", await self.summary(ctx.guild.id)))

    @ladder.command(name="timeout", help="Timeout at this many warnings. Usage: ladder timeout <warns> [duration]")
    @security_staff()
    async def ladder_timeout(self, ctx: commands.Context, count: int, duration: DurationConverter = None):
        if duration is not None:
            if not 60 <= duration <= 2419200:
                return await ctx.send(view=error_layout("Invalid duration", "Use 1 minute to 28 days."))
            await put(ctx.guild.id, "warn_timeout_duration", duration)
        await self._step(ctx, "timeout", count)

    @ladder.command(name="kick", help="Kick at this many warnings (0 = off).")
    @security_staff()
    async def ladder_kick(self, ctx: commands.Context, count: int):
        await self._step(ctx, "kick", count)

    @ladder.command(name="ban", help="Ban at this many warnings (0 = off).")
    @security_staff()
    async def ladder_ban(self, ctx: commands.Context, count: int):
        await self._step(ctx, "ban", count)

    @ladder.command(name="window", help="How long a warning counts. Usage: ladder window <duration>")
    @security_staff()
    async def ladder_window(self, ctx: commands.Context, duration: DurationConverter):
        if not 3600 <= duration <= 31536000:
            return await ctx.send(view=error_layout("Invalid duration", "Use 1 hour to 365 days."))
        await put(ctx.guild.id, "warn_window", duration)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Warning ladder", await self.summary(ctx.guild.id)))

    @ladder.command(name="check", aliases=["progress"], help="See a member's warnings and the next step. Usage: ladder check <member>")
    async def ladder_check(self, ctx: commands.Context, member: discord.Member):
        gid = ctx.guild.id
        window = await settings.get(gid, "automod", "warn_window")
        cutoff = time.time() - window
        warns = [w for w in await cases.get_warns(gid, member.id) if w["created_at"] >= cutoff]
        count = len(warns)
        steps = []
        for name, key in STEP_KEYS.items():
            at = await settings.get(gid, "automod", key)
            if at:
                steps.append((at, name))
        steps.sort()
        upcoming = next(((at, name) for at, name in steps if at > count), None)
        on = await settings.get(gid, "automod", "warn_ladder_enabled")
        lines = [f"**Active warnings:** {count}"]
        if upcoming:
            lines.append(f"**Next step:** {upcoming[1]} at {upcoming[0]} warnings ({upcoming[0] - count} more)")
        else:
            lines.append("**Next step:** none, every step is already reached or off")
        if warns:
            oldest = min(w["created_at"] for w in warns)
            lines.append(f"**Oldest warning stops counting** <t:{int(oldest + window)}:R>")
        if not on:
            lines.append("-# The ladder is off, so nothing happens automatically.")
        await ctx.send(view=info_layout(f"{member.display_name} · warning ladder", "\n".join(lines)), allowed_mentions=NO_MENTIONS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ladder(bot))
