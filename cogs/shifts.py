import time

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, shifts as store, staff_stats
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.converters import DurationConverter

NO_MENTIONS = discord.AllowedMentions.none()


class Shifts(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.alerted: dict[int, float] = {}
        self.watch.start()

    def cog_unload(self):
        self.watch.cancel()

    async def _allowed(self, ctx: commands.Context, cfg: dict) -> bool:
        if ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.administrator:
            return True
        return bool(cfg["staff_role"] and ctx.author.get_role(int(cfg["staff_role"])))

    async def _set_role(self, guild: discord.Guild, user_id: int, cfg: dict, add: bool):
        if not cfg["role"]:
            return
        role = guild.get_role(int(cfg["role"]))
        member = guild.get_member(user_id)
        if role is None or member is None or role >= guild.me.top_role:
            return
        try:
            if add:
                await member.add_roles(role, reason="Staff shift started")
            else:
                await member.remove_roles(role, reason="Staff shift ended")
        except discord.HTTPException:
            pass

    async def _post(self, guild: discord.Guild, cfg: dict, view: discord.ui.LayoutView):
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if channel is None:
            return
        try:
            await channel.send(view=view, allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def _handover(self, guild: discord.Guild, shift: dict, cfg: dict, auto: bool = False):
        done = await store.end(shift["shift_id"], auto)
        if done is None:
            return None
        await self._set_role(guild, int(done["user_id"]), cfg, False)
        entry = await store.activity(guild.id, done)
        work = await store.open_work(guild.id)
        lines = [f"<@{done['user_id']}> · {store.span(done['ended_at'] - done['started_at'])}" + (" · ended automatically" if auto else "")]
        lines.append("**Did:** " + (staff_stats.render_line(int(done["user_id"]), entry).split("· ", 1)[1]))
        lines.append("**Still open:** " + ", ".join(f"{n} {k}" for k, n in work.items() if n) if any(work.values()) else "**Still open:** nothing")
        if done["notes"]:
            lines.append(f"\n**Handover notes**\n{done['notes']}")
        await self._post(guild, cfg, info_layout("Shift handover", "\n".join(lines)))
        return done

    @tasks.loop(minutes=10)
    async def watch(self):
        for shift in await store.stale():
            guild = self.bot.get_guild(int(shift["guild_id"]))
            if guild is None:
                continue
            cfg = await store.get_config(guild.id)
            await self._handover(guild, shift, cfg, True)
        for guild in self.bot.guilds:
            cfg = await store.get_config(guild.id)
            if not cfg["enabled"] or cfg["coverage_start"] is None or cfg["coverage_end"] is None or not cfg["channel"]:
                continue
            if not store.in_window(int(cfg["coverage_start"]), int(cfg["coverage_end"]), await store.local_hour(guild.id)):
                continue
            if time.time() - self.alerted.get(guild.id, 0) < store.ALERT_GAP:
                continue
            if len(await store.on_duty(guild.id)) >= int(cfg["coverage_min"]):
                continue
            self.alerted[guild.id] = time.time()
            work = await store.open_work(guild.id)
            open_text = ", ".join(f"{n} {k}" for k, n in work.items() if n) or "nothing waiting"
            ping = f"<@&{cfg['staff_role']}> " if cfg["staff_role"] else ""
            channel = guild.get_channel(int(cfg["channel"]))
            if channel is None:
                continue
            try:
                await channel.send(content=ping or None, view=error_layout("Nobody on shift", f"Coverage hours are active and fewer than **{cfg['coverage_min']}** staff are on duty. Waiting: {open_text}. Use `shift start` to take over."),
                                   allowed_mentions=discord.AllowedMentions(roles=True))
            except discord.HTTPException:
                continue

    @watch.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()

    @commands.group(name="shift", aliases=["shifts", "duty"], invoke_without_command=True, help="Staff shifts and handover notes.")
    @commands.guild_only()
    async def shift(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        if not cfg["enabled"]:
            return await ctx.send(view=info_layout("Shifts", "Shifts are off. A manager can turn them on with `shift on`."))
        await self.shift_status(ctx)

    @shift.command(name="start", aliases=["in", "clockin"], help="Clock in and read the last handover notes.")
    @commands.guild_only()
    async def shift_start(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        if not cfg["enabled"]:
            return await ctx.send(view=error_layout("Shifts are off", "Ask a manager to turn them on with `shift on`."))
        if not await self._allowed(ctx, cfg):
            return await ctx.send(view=error_layout("Not staff", "You need Manage Messages or the shift staff role."))
        if await store.active(ctx.guild.id, ctx.author.id):
            return await ctx.send(view=error_layout("Already on shift", "Use `shift end [notes]` when you are done."))
        await store.start(ctx.guild.id, ctx.author.id)
        await self._set_role(ctx.guild, ctx.author.id, cfg, True)
        work = await store.open_work(ctx.guild.id)
        lines = ["You are on duty.", "**Waiting:** " + (", ".join(f"{n} {k}" for k, n in work.items() if n) or "nothing")]
        last = await store.last_handover(ctx.guild.id, ctx.author.id)
        if last:
            lines.append(f"\n**Last handover** from <@{last['user_id']}> <t:{int(last['ended_at'])}:R>\n{last['notes']}")
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shift started", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @shift.command(name="note", help="Add a note for the next person on shift. Usage: shift note <text>")
    @commands.guild_only()
    async def shift_note(self, ctx: commands.Context, *, text: str):
        current = await store.active(ctx.guild.id, ctx.author.id)
        if current is None:
            return await ctx.send(view=error_layout("Not on shift", "Use `shift start` first."))
        await store.add_note(current["shift_id"], text[:500])
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Note saved", "It will be in your handover."))

    @shift.command(name="end", aliases=["out", "clockout"], help="Clock out and post a handover. Usage: shift end [notes]")
    @commands.guild_only()
    async def shift_end(self, ctx: commands.Context, *, notes: str = ""):
        cfg = await store.get_config(ctx.guild.id)
        current = await store.active(ctx.guild.id, ctx.author.id)
        if current is None:
            return await ctx.send(view=error_layout("Not on shift", "You are not clocked in."))
        if notes:
            await store.add_note(current["shift_id"], notes[:500])
        done = await self._handover(ctx.guild, current, cfg)
        channel_text = f"Handover posted in <#{cfg['channel']}>." if cfg["channel"] else "No handover channel is set, so nothing was posted."
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shift ended", f"You were on for **{store.span(done['ended_at'] - done['started_at'])}**. {channel_text}"))

    @shift.command(name="status", aliases=["who", "list"], help="Who is on duty right now.")
    @commands.guild_only()
    async def shift_status(self, ctx: commands.Context):
        rows = await store.on_duty(ctx.guild.id)
        work = await store.open_work(ctx.guild.id)
        lines = [f"<@{r['user_id']}> · since <t:{int(r['started_at'])}:R>" for r in rows] or ["Nobody is on duty."]
        lines.append("\n**Waiting:** " + (", ".join(f"{n} {k}" for k, n in work.items() if n) or "nothing"))
        await ctx.send(view=info_layout("On duty", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @shift.command(name="handover", help="Read the latest handover notes.")
    @commands.guild_only()
    async def shift_handover(self, ctx: commands.Context):
        rows = [r for r in await store.recent(ctx.guild.id, limit=8) if r["notes"]][:3]
        if not rows:
            return await ctx.send(view=info_layout("Handover", "No handover notes yet."))
        body = "\n\n".join(f"<@{r['user_id']}> <t:{int(r['ended_at'])}:R>\n{r['notes']}" for r in rows)
        await ctx.send(view=info_layout("Handover", body), allowed_mentions=NO_MENTIONS)

    @shift.command(name="log", aliases=["history"], help="Recent shifts, or one member's. Usage: shift log [member]")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_log(self, ctx: commands.Context, member: discord.Member = None):
        rows = await store.recent(ctx.guild.id, member.id if member else None, 12)
        if not rows:
            return await ctx.send(view=info_layout("Shift log", "No finished shifts."))
        lines = [f"<@{r['user_id']}> · <t:{int(r['started_at'])}:f> · {store.span(r['ended_at'] - r['started_at'])}" + (" · auto" if r["auto_ended"] else "") for r in rows]
        await ctx.send(view=info_layout("Shift log", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @shift.command(name="hours", help="Time on shift per staff member. Usage: shift hours [days]")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_hours(self, ctx: commands.Context, days: int = 30):
        days = max(1, min(180, days))
        rows = await store.totals(ctx.guild.id, time.time() - days * 86400)
        if not rows:
            return await ctx.send(view=info_layout(f"Shift hours · {days} days", "No shifts in this period."))
        lines = [f"<@{uid}> · {store.span(secs)} over {n} shift{'s' if n != 1 else ''}" for uid, n, secs in rows[:20]]
        await ctx.send(view=info_layout(f"Shift hours · {days} days", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @shift.command(name="on", help="Turn shifts on.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_on(self, ctx: commands.Context):
        await store.set_config(ctx.guild.id, "enabled", True)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", "Shifts are **on**. Set a handover channel with `shift channel #channel`."))

    @shift.command(name="off", aliases=["disable"], help="Turn shifts off.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_off(self, ctx: commands.Context):
        await store.set_config(ctx.guild.id, "enabled", False)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", "Shifts are **off**."))

    @shift.command(name="channel", help="Where handovers and coverage alerts are posted.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await store.set_config(ctx.guild.id, "channel", channel.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", f"Handovers go to {channel.mention}."))

    @shift.command(name="role", help="Role given while on duty. Use it as the ping role for reports, appeals and tickets.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_role(self, ctx: commands.Context, role: discord.Role = None):
        await store.set_config(ctx.guild.id, "role", role.id if role else None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", f"On-duty role is {role.mention}." if role else "On-duty role removed."), allowed_mentions=NO_MENTIONS)

    @shift.command(name="staffrole", help="Role that may clock in besides members with Manage Messages. It is pinged for coverage alerts.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_staffrole(self, ctx: commands.Context, role: discord.Role = None):
        await store.set_config(ctx.guild.id, "staff_role", role.id if role else None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", f"Shift staff role is {role.mention}." if role else "Shift staff role removed."), allowed_mentions=NO_MENTIONS)

    @shift.command(name="coverage", help="Alert when nobody is on shift. Usage: shift coverage <start hour> <end hour> [minimum] or shift coverage off")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def shift_coverage(self, ctx: commands.Context, start: str, end: str = "", minimum: int = 1):
        if start.lower() in ("off", "none", "disable"):
            await store.set_config(ctx.guild.id, "coverage_start", None)
            await store.set_config(ctx.guild.id, "coverage_end", None)
            return await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", "Coverage alerts are **off**."))
        first, last = store.parse_hour(start), store.parse_hour(end)
        if first is None or last is None or not 1 <= minimum <= 20:
            return await ctx.send(view=error_layout("Invalid hours", "Use hours like `18 23` or `6pm 11pm`, and a minimum from 1 to 20."))
        await store.set_config(ctx.guild.id, "coverage_start", first)
        await store.set_config(ctx.guild.id, "coverage_end", last)
        await store.set_config(ctx.guild.id, "coverage_min", minimum)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Shifts", f"Between **{first:02d}:00** and **{last:02d}:00** (server timezone, `!event timezone`) Soward alerts the handover channel if fewer than **{minimum}** staff are on duty. At most one alert every 2 hours."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Shifts(bot))
