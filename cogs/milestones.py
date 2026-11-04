import time

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, milestones as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LEVEL_UP, bus

NO_MENTIONS = discord.AllowedMentions.none()
MAX_LISTED = 25
POST_HOUR = 9


class Milestones(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.seen: dict[tuple[int, int], float] = {}
        self.written: dict[tuple[int, int], float] = {}
        self.configs: dict[int, tuple[float, dict]] = {}
        self.anniversaries.start()
        bus.subscribe(LEVEL_UP, self.on_level_up)

    def cog_unload(self):
        self.anniversaries.cancel()
        bus.unsubscribe(LEVEL_UP, self.on_level_up)

    async def config(self, guild_id: int) -> dict:
        cached = self.configs.get(guild_id)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        cfg = await store.get_config(guild_id)
        self.configs[guild_id] = (time.time(), cfg)
        return cfg

    def channel_for(self, guild: discord.Guild, cfg: dict):
        return guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None

    async def on_level_up(self, guild_id: int = 0, user_id: int = 0, level: int = 0, **_):
        cfg = await self.config(guild_id)
        if not cfg["levels"] or level not in cfg["level_list"]:
            return
        guild = self.bot.get_guild(guild_id)
        channel = self.channel_for(guild, cfg) if guild else None
        if channel is None:
            return
        try:
            await channel.send(view=info_layout(f"{emoji_manager.get('trophy')} Level {level}", f"<@{user_id}> just reached **level {level}**. Congratulations!"), allowed_mentions=discord.AllowedMentions(users=[discord.Object(user_id)]))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        guild = message.guild
        cfg = await self.config(guild.id)
        if cfg["welcomeback"] == "off":
            return
        key = (guild.id, message.author.id)
        now = time.time()
        previous = self.seen.get(key)
        if previous is None:
            previous = await store.last_seen(guild.id, message.author.id)
        self.seen[key] = now
        if len(self.seen) > 50000:
            self.seen.clear()
            self.written.clear()
        if now - self.written.get(key, 0) >= store.WRITE_GAP:
            self.written[key] = now
            await store.touch(guild.id, message.author.id, now)
        if previous is None or now - previous < int(cfg["away_days"]) * 86400:
            return
        await self.welcome_back(message.author, previous, cfg)

    async def welcome_back(self, member: discord.Member, previous: float, cfg: dict):
        digest = await store.away_digest(member.guild, previous)
        days = int((time.time() - previous) // 86400)
        body = f"Welcome back, {member.mention}. You have been away for **{days} days**."
        if digest:
            body += "\n\n**While you were gone**\n" + "\n".join(f"- {line}" for line in digest)
        view = info_layout(f"{emoji_manager.get('swave')} Welcome back", body)
        if cfg["welcomeback"] == "dm":
            try:
                await member.send(view=view)
            except discord.HTTPException:
                pass
            return
        channel = self.channel_for(member.guild, cfg)
        if channel is None:
            return
        try:
            await channel.send(view=view, allowed_mentions=discord.AllowedMentions(users=[member]))
        except discord.HTTPException:
            pass

    @tasks.loop(minutes=30)
    async def anniversaries(self):
        for guild in self.bot.guilds:
            cfg = await self.config(guild.id)
            if not cfg["anniversary"] or not cfg["channel"]:
                continue
            now = await store.local_now(guild.id)
            if now.hour < POST_HOUR:
                continue
            today = now.strftime("%Y-%m-%d")
            if await store.anniversary_done(guild.id) == today:
                continue
            await store.mark_anniversary(guild.id, today)
            found = store.anniversaries(guild.members, today)
            channel = self.channel_for(guild, cfg)
            if not found or channel is None:
                continue
            lines = [f"<@{uid}> · **{years}** year{'s' if years != 1 else ''}" for uid, years in found[:MAX_LISTED]]
            if len(found) > MAX_LISTED:
                lines.append(f"-# and {len(found) - MAX_LISTED} more")
            try:
                await channel.send(view=info_layout(f"{emoji_manager.get('gift')} Server anniversaries", "Thank you for being here.\n\n" + "\n".join(lines)),
                                   allowed_mentions=discord.AllowedMentions(users=[discord.Object(uid) for uid, _ in found[:MAX_LISTED]]))
            except discord.HTTPException:
                continue

    @anniversaries.before_loop
    async def before_anniversaries(self):
        await self.bot.wait_until_ready()

    @commands.group(name="milestones", aliases=["milestone"], invoke_without_command=True, help="Anniversaries, level milestones and welcome back messages.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def milestones(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        channel = f"<#{cfg['channel']}>" if cfg["channel"] else "not set"
        lines = [
            f"**Channel:** {channel}",
            f"**Anniversaries:** {'on' if cfg['anniversary'] else 'off'}",
            f"**Level milestones:** {'on' if cfg['levels'] else 'off'} ({', '.join(str(n) for n in cfg['level_list'])})",
            f"**Welcome back:** {cfg['welcomeback']} after {cfg['away_days']} days away",
            "\n`milestones channel #channel` · `milestones anniversary on|off` · `milestones levels on|off|<levels...>` · `milestones welcomeback off|channel|dm` · `milestones away <days>`",
        ]
        await ctx.send(view=info_layout("Milestones", "\n".join(lines)))

    async def _saved(self, ctx: commands.Context, text: str):
        self.configs.pop(ctx.guild.id, None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Milestones", text))

    @milestones.command(name="channel", help="Where milestone posts go. Usage: milestones channel [#channel]")
    @has_guild_permission("manage_guild")
    async def milestones_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        await store.set_config(ctx.guild.id, "channel", channel.id if channel else None)
        await self._saved(ctx, f"Posts go to {channel.mention}." if channel else "Channel removed. Nothing will be posted.")

    @milestones.command(name="anniversary", aliases=["anniversaries"], help="Post member join anniversaries.")
    @has_guild_permission("manage_guild")
    async def milestones_anniversary(self, ctx: commands.Context, toggle: bool):
        await store.set_config(ctx.guild.id, "anniversary", toggle)
        await self._saved(ctx, f"Anniversaries are **{'on' if toggle else 'off'}**. They post once a day after 9:00 server time.")

    @milestones.command(name="levels", help="Level milestones. Usage: milestones levels on|off or milestones levels 10 25 50")
    @has_guild_permission("manage_guild")
    async def milestones_levels(self, ctx: commands.Context, *values: str):
        if not values:
            return await ctx.send(view=error_layout("Missing value", "Use `on`, `off` or a list of levels such as `10 25 50 100`."))
        word = values[0].lower()
        if word in ("on", "off", "true", "false", "yes", "no", "enable", "disable"):
            await store.set_config(ctx.guild.id, "levels", word in ("on", "true", "yes", "enable"))
            return await self._saved(ctx, f"Level milestones are **{'on' if word in ('on', 'true', 'yes', 'enable') else 'off'}**.")
        levels = store.parse_levels(list(values))
        if levels is None:
            return await ctx.send(view=error_layout("Invalid levels", "Give up to 20 whole numbers from 1 to 1000."))
        await store.set_config(ctx.guild.id, "level_list", levels)
        await store.set_config(ctx.guild.id, "levels", True)
        await self._saved(ctx, "Milestones at levels " + ", ".join(str(n) for n in levels) + ".")

    @milestones.command(name="welcomeback", aliases=["return"], help="Welcome back members who return after a long absence. Usage: milestones welcomeback off|channel|dm")
    @has_guild_permission("manage_guild")
    async def milestones_welcomeback(self, ctx: commands.Context, mode: str):
        mode = mode.lower()
        if mode not in store.MODES:
            return await ctx.send(view=error_layout("Invalid mode", "Use `off`, `channel` or `dm`."))
        await store.set_config(ctx.guild.id, "welcomeback", mode)
        await self._saved(ctx, f"Welcome back is **{mode}**. Soward starts tracking activity from now, so nobody is welcomed back until they have been quiet for the full period after that.")

    @milestones.command(name="away", help="Days of silence before a member counts as returning (7 to 365).")
    @has_guild_permission("manage_guild")
    async def milestones_away(self, ctx: commands.Context, days: int):
        if not 7 <= days <= 365:
            return await ctx.send(view=error_layout("Invalid number", "Use 7 to 365 days."))
        await store.set_config(ctx.guild.id, "away_days", days)
        await self._saved(ctx, f"A member counts as returning after **{days} days** without a message.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Milestones(bot))
