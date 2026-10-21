import calendar
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9
DEFAULT_MESSAGE = "Happy birthday {user}! 🎂 Everyone in {server} wishes you an amazing day."


def parse_date(text: str) -> Optional[tuple[int, int]]:
    cleaned = text.strip().lower().replace(",", " ")
    match = re.fullmatch(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})", cleaned)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        if month > 12 >= day:
            day, month = month, day
    else:
        parts = [re.sub(r"(st|nd|rd|th)$", "", p) for p in cleaned.split()]
        if len(parts) != 2:
            return None
        if parts[0] in MONTHS and parts[1].isdigit():
            month, day = MONTHS[parts[0]], int(parts[1])
        elif parts[1] in MONTHS and parts[0].isdigit():
            month, day = MONTHS[parts[1]], int(parts[0])
        else:
            return None
    if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(2024, month)[1]:
        return None
    return month, day


def format_date(month: int, day: int) -> str:
    return f"{calendar.month_name[month]} {day}"


def _today(offset_hours: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


def _matches_today(month: int, day: int, now: datetime) -> bool:
    if (month, day) == (now.month, now.day):
        return True
    return (month, day) == (2, 29) and (now.month, now.day) == (2, 28) and not calendar.isleap(now.year)


def _days_until(month: int, day: int, now: datetime) -> int:
    for year in (now.year, now.year + 1):
        target_day = day
        if (month, day) == (2, 29) and not calendar.isleap(year):
            target_day = 28
        target = datetime(year, month, target_day)
        delta = (target.date() - now.date()).days
        if delta >= 0:
            return delta
    return 365


class Birthdays(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.check_loop.start()

    async def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=5)
    async def check_loop(self):
        for guild in list(self.bot.guilds):
            try:
                await self._run_guild(guild)
            except Exception:
                continue

    @check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    async def _run_guild(self, guild: discord.Guild):
        channel_id = await guild_settings.get(guild.id, "bday_channel_id")
        role_id = await guild_settings.get(guild.id, "bday_role_id")
        if not channel_id and not role_id:
            return
        if not await guild_settings.get(guild.id, "bday_enabled", True):
            return
        offset = float(await guild_settings.get(guild.id, "bday_utc_offset", 0))
        now = _today(offset)
        rows = await db.raw_fetch("SELECT user_id, month, day, last_announced FROM birthdays WHERE guild_id=?", (guild.id,))
        today_ids = set()
        for row in rows:
            if not _matches_today(row["month"], row["day"], now):
                continue
            member = guild.get_member(row["user_id"])
            if member is None:
                continue
            today_ids.add(member.id)
            role = guild.get_role(role_id) if role_id else None
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Birthday")
                except discord.HTTPException:
                    pass
            if row["last_announced"] == now.year:
                continue
            await db.raw_execute(
                "UPDATE birthdays SET last_announced=? WHERE guild_id=? AND user_id=?", (now.year, guild.id, member.id)
            )
            channel = guild.get_channel(channel_id) if channel_id else None
            if channel is not None:
                template = await guild_settings.get(guild.id, "bday_message", DEFAULT_MESSAGE)
                text = template.replace("{user}", member.mention).replace("{username}", member.display_name).replace("{server}", guild.name)
                try:
                    await channel.send(text, allowed_mentions=discord.AllowedMentions(users=[member], roles=False, everyone=False))
                except discord.HTTPException:
                    pass
        role = guild.get_role(role_id) if role_id else None
        if role:
            for member in list(role.members):
                if member.id not in today_ids:
                    try:
                        await member.remove_roles(role, reason="Birthday over")
                    except discord.HTTPException:
                        pass

    @commands.group(name="birthday", aliases=["bday", "birthdays"], invoke_without_command=True, help="Set and view birthdays. Usage: birthday [member]")
    @commands.guild_only()
    async def birthday(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        target = member or ctx.author
        row = await db.raw_fetchone("SELECT month, day FROM birthdays WHERE guild_id=? AND user_id=?", (ctx.guild.id, target.id))
        if row is None:
            body = "You have not set a birthday. Use `birthday set <date>`." if target == ctx.author else f"{target.display_name} has not set a birthday."
            return await ctx.send(view=info_layout(f"{e('settings')} Birthday", body))
        await ctx.send(view=info_layout("🎂 Birthday", f"{target.display_name}'s birthday is **{format_date(row['month'], row['day'])}**."))

    @birthday.command(name="set", help="Set your birthday. Usage: birthday set <15 March | 15/03 | March 15>")
    @commands.guild_only()
    async def birthday_set(self, ctx: commands.Context, *, date: str):
        e = emoji_manager.get
        parsed = parse_date(date)
        if parsed is None:
            return await ctx.send(view=error_layout("Invalid Date", "Use a format like `15 March`, `March 15` or `15/03`. The year is not needed."))
        month, day = parsed
        await db.raw_execute(
            "INSERT INTO birthdays (guild_id, user_id, month, day, last_announced) VALUES (?, ?, ?, ?, NULL)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET month=excluded.month, day=excluded.day, last_announced=NULL",
            (ctx.guild.id, ctx.author.id, month, day),
        )
        await ctx.send(view=success_layout(f"{e('check')} Birthday Saved", f"Your birthday is now **{format_date(month, day)}**. Only the day and month are stored."))

    @birthday.command(name="remove", aliases=["clear", "delete"], help="Remove your birthday.")
    @commands.guild_only()
    async def birthday_remove(self, ctx: commands.Context):
        e = emoji_manager.get
        await db.raw_execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (ctx.guild.id, ctx.author.id))
        await ctx.send(view=success_layout(f"{e('check')} Birthday Removed", "Your birthday was removed."))

    @birthday.command(name="today", help="Show whose birthday it is today.")
    @commands.guild_only()
    async def birthday_today(self, ctx: commands.Context):
        offset = float(await guild_settings.get(ctx.guild.id, "bday_utc_offset", 0))
        now = _today(offset)
        rows = await db.raw_fetch("SELECT user_id, month, day FROM birthdays WHERE guild_id=?", (ctx.guild.id,))
        names = [m.mention for r in rows if _matches_today(r["month"], r["day"], now) and (m := ctx.guild.get_member(r["user_id"]))]
        await ctx.send(view=info_layout("🎂 Birthdays Today", ", ".join(names) if names else "Nobody has a birthday today."))

    @birthday.command(name="upcoming", aliases=["next", "list"], help="Show the next birthdays.")
    @commands.guild_only()
    async def birthday_upcoming(self, ctx: commands.Context):
        offset = float(await guild_settings.get(ctx.guild.id, "bday_utc_offset", 0))
        now = _today(offset)
        rows = await db.raw_fetch("SELECT user_id, month, day FROM birthdays WHERE guild_id=?", (ctx.guild.id,))
        entries = []
        for r in rows:
            member = ctx.guild.get_member(r["user_id"])
            if member is not None:
                entries.append((_days_until(r["month"], r["day"], now), member, r["month"], r["day"]))
        entries.sort(key=lambda x: x[0])
        if not entries:
            return await ctx.send(view=info_layout("🎂 Upcoming Birthdays", "No birthdays have been set yet."))
        lines = [f"**{format_date(m, d)}** - {member.display_name}" + (" (today)" if days == 0 else f" (in {days}d)") for days, member, m, d in entries[:10]]
        await ctx.send(view=info_layout("🎂 Upcoming Birthdays", "\n".join(lines)))

    @birthday.group(name="config", aliases=["setup"], invoke_without_command=True, help="Configure birthday announcements.")
    @has_guild_permission("manage_guild")
    async def birthday_config(self, ctx: commands.Context):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "bday_channel_id")
        role_id = await guild_settings.get(ctx.guild.id, "bday_role_id")
        enabled = await guild_settings.get(ctx.guild.id, "bday_enabled", True)
        offset = await guild_settings.get(ctx.guild.id, "bday_utc_offset", 0)
        message = await guild_settings.get(ctx.guild.id, "bday_message", DEFAULT_MESSAGE)
        body = (
            f"**Status:** {'on' if enabled else 'off'}\n"
            f"**Channel:** {f'<#{channel_id}>' if channel_id else 'not set'}\n"
            f"**Birthday role:** {f'<@&{role_id}>' if role_id else 'not set'}\n"
            f"**UTC offset:** {offset}\n"
            f"**Message:** {message}\n\n"
            "`birthday config channel #channel`, `role @role`, `message <text>`, `offset <hours>`, `toggle`, `reset`\n"
            "Message variables: `{user}` `{username}` `{server}`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Birthday Setup", body))

    @birthday_config.command(name="channel", help="Set the announcement channel.")
    @has_guild_permission("manage_guild")
    async def config_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "bday_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Birthdays will be announced in {channel.mention}."))

    @birthday_config.command(name="role", help="Set the role given on a member's birthday.")
    @has_guild_permission("manage_guild")
    async def config_role(self, ctx: commands.Context, role: discord.Role):
        e = emoji_manager.get
        if role >= ctx.guild.me.top_role:
            return await ctx.send(view=error_layout("Role Too High", "That role is above my highest role."))
        await guild_settings.set(ctx.guild.id, "bday_role_id", role.id)
        await ctx.send(view=success_layout(f"{e('check')} Role Set", f"Members will get {role.mention} on their birthday."))

    @birthday_config.command(name="message", help="Set the announcement message.")
    @has_guild_permission("manage_guild")
    async def config_message(self, ctx: commands.Context, *, text: str):
        e = emoji_manager.get
        if len(text) > 1000:
            return await ctx.send(view=error_layout("Too Long", "The message must be under 1000 characters."))
        await guild_settings.set(ctx.guild.id, "bday_message", text)
        await ctx.send(view=success_layout(f"{e('check')} Message Set", text))

    @birthday_config.command(name="offset", help="Set the UTC offset in hours, for example 6 or -5.")
    @has_guild_permission("manage_guild")
    async def config_offset(self, ctx: commands.Context, hours: float):
        e = emoji_manager.get
        if not -12 <= hours <= 14:
            return await ctx.send(view=error_layout("Invalid Offset", "Use a number between -12 and 14."))
        await guild_settings.set(ctx.guild.id, "bday_utc_offset", hours)
        await ctx.send(view=success_layout(f"{e('check')} Offset Set", f"Birthdays now change at midnight UTC{hours:+g}."))

    @birthday_config.command(name="toggle", help="Turn birthday announcements on or off.")
    @has_guild_permission("manage_guild")
    async def config_toggle(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await guild_settings.get(ctx.guild.id, "bday_enabled", True)
        await guild_settings.set(ctx.guild.id, "bday_enabled", not current)
        await ctx.send(view=success_layout(f"{e('check')} Birthdays", f"Birthday announcements are now **{'off' if current else 'on'}**."))

    @birthday_config.command(name="reset", help="Clear the channel, role and message.")
    @has_guild_permission("manage_guild")
    async def config_reset(self, ctx: commands.Context):
        e = emoji_manager.get
        for key in ("bday_channel_id", "bday_role_id", "bday_message", "bday_utc_offset", "bday_enabled"):
            await guild_settings.delete(ctx.guild.id, key)
        await ctx.send(view=success_layout(f"{e('check')} Reset", "Birthday settings were cleared. Saved birthdays are kept."))

    @birthday.command(name="forget", help="Remove a member's birthday. Usage: birthday forget <member>")
    @has_guild_permission("manage_guild")
    async def birthday_forget(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        await db.raw_execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
        await ctx.send(view=success_layout(f"{e('check')} Birthday Removed", f"Removed the birthday of {member.display_name}."))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await db.raw_execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (member.guild.id, member.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
