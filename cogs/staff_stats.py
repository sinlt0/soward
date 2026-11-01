import time

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, staff_stats as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import MOD_ACTION, bus

NO_MENTIONS = discord.AllowedMentions.none()
WEEK = 7 * 86400


class StaffStats(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.alerted: dict[tuple[int, int], float] = {}
        self.weekly.start()
        bus.subscribe(MOD_ACTION, self.on_mod_action)

    def cog_unload(self):
        self.weekly.cancel()
        bus.unsubscribe(MOD_ACTION, self.on_mod_action)

    async def on_mod_action(self, guild_id: int = 0, moderator_id: int = 0, action: str = "", **_):
        if not guild_id or not moderator_id or action not in store.SEVERE:
            return
        cfg = await store.get_config(guild_id)
        if not cfg["channel"]:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None or moderator_id in (self.bot.user.id, guild.owner_id):
            return
        key = (guild_id, moderator_id)
        if time.time() - self.alerted.get(key, 0) < 3600:
            return
        count = await store.severe_recent(guild_id, moderator_id)
        if count < cfg["spike"]:
            return
        channel = guild.get_channel(int(cfg["channel"]))
        if channel is None:
            return
        self.alerted[key] = time.time()
        try:
            await channel.send(view=error_layout("Staff action spike", f"<@{moderator_id}> made **{count}** bans or kicks in the last hour (limit {cfg['spike']}). Check that this is intended."), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def build(self, guild: discord.Guild, days: int) -> str:
        since = time.time() - days * 86400
        stats = await store.collect(guild.id, since)
        if not stats:
            return "No staff activity in this period."
        ranked = sorted(stats.items(), key=lambda kv: store.total(kv[1]), reverse=True)[:15]
        return "\n".join(store.render_line(uid, entry) for uid, entry in ranked)

    @tasks.loop(minutes=30)
    async def weekly(self):
        for guild in self.bot.guilds:
            cfg = await store.get_config(guild.id)
            if not cfg["enabled"] or not cfg["channel"]:
                continue
            last = await db.get("staff_report", str(guild.id))
            if last is None:
                await db.set("staff_report", str(guild.id), time.time())
                continue
            if time.time() - float(last) < WEEK:
                continue
            channel = guild.get_channel(int(cfg["channel"]))
            if channel is None:
                continue
            try:
                await channel.send(view=info_layout("Weekly staff report", await self.build(guild, 7)), allowed_mentions=NO_MENTIONS)
            except discord.HTTPException:
                continue
            await db.set("staff_report", str(guild.id), time.time())

    @weekly.before_loop
    async def before_weekly(self):
        await self.bot.wait_until_ready()

    @commands.group(name="staff", invoke_without_command=True, help="Staff accountability tools.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def staff(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Staff", "`staff stats [member] [days]` · `staff report` · `staff channel <#channel>` · `staff weekly on|off` · `staff spike <number>`"))

    @staff.command(name="stats", help="Activity of one staff member or the whole team. Usage: staff stats [member] [days]")
    @has_guild_permission("manage_guild")
    async def staff_stats(self, ctx: commands.Context, member: discord.Member = None, days: int = 30):
        days = max(1, min(180, days))
        if member is None:
            return await ctx.send(view=info_layout(f"Staff activity · {days} days", await self.build(ctx.guild, days)), allowed_mentions=NO_MENTIONS)
        stats = await store.collect(ctx.guild.id, time.time() - days * 86400)
        entry = stats.get(member.id, {f: 0 for f in store.FIELDS})
        lines = "\n".join(f"**{k.replace('_', ' ').title()}:** {v}" for k, v in entry.items())
        await ctx.send(view=info_layout(f"{member.display_name} · {days} days", lines), allowed_mentions=NO_MENTIONS)

    @staff.command(name="report", help="Post the staff report now.")
    @has_guild_permission("manage_guild")
    async def staff_report(self, ctx: commands.Context, days: int = 7):
        days = max(1, min(180, days))
        await ctx.send(view=info_layout(f"Staff report · {days} days", await self.build(ctx.guild, days)), allowed_mentions=NO_MENTIONS)

    @staff.command(name="channel", help="Where the weekly report and spike alerts go.")
    @has_guild_permission("manage_guild")
    async def staff_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await store.set_config(ctx.guild.id, "channel", channel.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Staff", f"Reports and alerts go to {channel.mention}."))

    @staff.command(name="weekly", help="Turn the weekly report on or off.")
    @has_guild_permission("manage_guild")
    async def staff_weekly(self, ctx: commands.Context, toggle: bool):
        await store.set_config(ctx.guild.id, "enabled", toggle)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Staff", f"Weekly report is **{'on' if toggle else 'off'}**."))

    @staff.command(name="spike", help="Bans or kicks by one moderator in an hour that trigger an alert.")
    @has_guild_permission("manage_guild")
    async def staff_spike(self, ctx: commands.Context, amount: int):
        if not 3 <= amount <= 100:
            return await ctx.send(view=error_layout("Invalid number", "Use 3 to 100."))
        await store.set_config(ctx.guild.id, "spike", amount)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Staff", f"Alert after **{amount}** bans or kicks by one moderator in an hour."))


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffStats(bot))
