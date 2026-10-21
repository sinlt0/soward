import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.icebreaker_data import NHIE, QUESTIONS, RIZZ, WYR


def _card(title: str, body: str, color: int, footer: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    if footer:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {footer}"))
    view.add_item(container)
    return view


class Icebreakers(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.daily_loop.start()

    async def cog_unload(self):
        self.daily_loop.cancel()

    @commands.command(name="wyr", aliases=["wouldyourather"], help="Get a would you rather question.")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def wyr(self, ctx: commands.Context):
        a, b = random.choice(WYR)
        message = await ctx.send(view=_card("🤔 Would You Rather", f"🅰️ **{a}**\n\n🅱️ **{b}**", 0x9B59B6, "React with 🅰️ or 🅱️"))
        for emoji in ("🅰️", "🅱️"):
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                break

    @commands.command(name="nhie", aliases=["neverhaveiever"], help="Get a never have I ever prompt.")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def nhie(self, ctx: commands.Context):
        await ctx.send(view=_card("🙈 Never Have I Ever", random.choice(NHIE), 0xE67E22, "Drink a sip of water if you have!"))

    @commands.command(name="rizz", help="Get a cheesy pickup line. Usage: rizz [member]")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def rizz(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        line = random.choice(RIZZ)
        target = f"{member.mention}, " if member and member != ctx.author else ""
        await ctx.send(view=_card("😎 Rizz", f"{target}{line}", 0xFF69B4), allowed_mentions=discord.AllowedMentions(users=[member] if member else False))

    @commands.command(name="icebreaker", aliases=["question", "ice"], help="Get a conversation starter.")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def icebreaker(self, ctx: commands.Context):
        await ctx.send(view=_card("🎯 Icebreaker", random.choice(QUESTIONS), 0x3498DB))

    async def _pick_daily(self, guild_id: int) -> str:
        used = await guild_settings.get(guild_id, "dq_used", [])
        pool = [i for i in range(len(QUESTIONS)) if i not in used]
        if not pool:
            used, pool = [], list(range(len(QUESTIONS)))
        index = random.choice(pool)
        await guild_settings.set(guild_id, "dq_used", used + [index])
        return QUESTIONS[index]

    async def _post_daily(self, guild: discord.Guild) -> bool:
        channel_id = await guild_settings.get(guild.id, "dq_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return False
        role_id = await guild_settings.get(guild.id, "dq_role_id")
        role = guild.get_role(role_id) if role_id else None
        question = await self._pick_daily(guild.id)
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x3498DB)
        container.add_item(discord.ui.TextDisplay(f"## ❓ Question of the Day\n{question}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("-# Answer below and read what others said." + (f"\n{role.mention}" if role else "")))
        view.add_item(container)
        try:
            await channel.send(view=view, allowed_mentions=discord.AllowedMentions(roles=[role] if role else False))
        except discord.HTTPException:
            return False
        return True

    @tasks.loop(minutes=1)
    async def daily_loop(self):
        for guild in list(self.bot.guilds):
            try:
                if not await guild_settings.get(guild.id, "dq_channel_id") or not await guild_settings.get(guild.id, "dq_enabled", True):
                    continue
                offset = float(await guild_settings.get(guild.id, "dq_utc_offset", 0))
                now = datetime.now(timezone.utc) + timedelta(hours=offset)
                hour, minute = (int(x) for x in str(await guild_settings.get(guild.id, "dq_time", "12:00")).split(":"))
                today = now.strftime("%Y-%m-%d")
                if now.hour * 60 + now.minute < hour * 60 + minute or await guild_settings.get(guild.id, "dq_last_date") == today:
                    continue
                await guild_settings.set(guild.id, "dq_last_date", today)
                await self._post_daily(guild)
            except Exception:
                continue

    @daily_loop.before_loop
    async def before_daily_loop(self):
        await self.bot.wait_until_ready()

    @commands.group(name="daily", aliases=["dq", "dailyquestion"], invoke_without_command=True, help="Daily question autopost settings.")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "dq_channel_id")
        role_id = await guild_settings.get(ctx.guild.id, "dq_role_id")
        body = (
            f"**Status:** {'on' if await guild_settings.get(ctx.guild.id, 'dq_enabled', True) else 'off'}\n"
            f"**Channel:** {f'<#{channel_id}>' if channel_id else 'not set'}\n"
            f"**Time:** {await guild_settings.get(ctx.guild.id, 'dq_time', '12:00')} (UTC{float(await guild_settings.get(ctx.guild.id, 'dq_utc_offset', 0)):+g})\n"
            f"**Ping role:** {f'<@&{role_id}>' if role_id else 'none'}\n\n"
            "`daily channel #c`, `daily time <HH:MM>`, `daily offset <hours>`, `daily role [@role]`, `daily toggle`, `daily now`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Daily Question", body))

    @daily.command(name="channel", help="Set the daily question channel.")
    @has_guild_permission("manage_guild")
    async def daily_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "dq_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"The daily question will be posted in {channel.mention}."))

    @daily.command(name="time", help="Set the posting time as HH:MM, 24 hour clock.")
    @has_guild_permission("manage_guild")
    async def daily_time(self, ctx: commands.Context, time: str):
        e = emoji_manager.get
        try:
            hour, minute = (int(x) for x in time.split(":"))
            valid = 0 <= hour <= 23 and 0 <= minute <= 59
        except ValueError:
            valid = False
        if not valid:
            return await ctx.send(view=error_layout("Invalid Time", "Use `HH:MM` such as `09:30` or `18:00`."))
        await guild_settings.set(ctx.guild.id, "dq_time", f"{hour:02d}:{minute:02d}")
        await ctx.send(view=success_layout(f"{e('check')} Time Set", f"The question will be posted at **{hour:02d}:{minute:02d}**."))

    @daily.command(name="offset", help="Set the UTC offset in hours, for example 6 or -5.")
    @has_guild_permission("manage_guild")
    async def daily_offset(self, ctx: commands.Context, hours: float):
        e = emoji_manager.get
        if not -12 <= hours <= 14:
            return await ctx.send(view=error_layout("Invalid Offset", "Use a number between -12 and 14."))
        await guild_settings.set(ctx.guild.id, "dq_utc_offset", hours)
        await ctx.send(view=success_layout(f"{e('check')} Offset Set", f"The time now uses UTC{hours:+g}."))

    @daily.command(name="role", help="Set a role to ping, or leave empty to remove it.")
    @has_guild_permission("manage_guild")
    async def daily_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        e = emoji_manager.get
        if role is None:
            await guild_settings.delete(ctx.guild.id, "dq_role_id")
            return await ctx.send(view=success_layout(f"{e('check')} Ping Removed", "The daily question will not ping a role."))
        await guild_settings.set(ctx.guild.id, "dq_role_id", role.id)
        await ctx.send(view=success_layout(f"{e('check')} Ping Set", f"{role.mention} will be pinged."))

    @daily.command(name="toggle", help="Turn the daily question on or off.")
    @has_guild_permission("manage_guild")
    async def daily_toggle(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await guild_settings.get(ctx.guild.id, "dq_enabled", True)
        await guild_settings.set(ctx.guild.id, "dq_enabled", not current)
        await ctx.send(view=success_layout(f"{e('check')} Daily Question", f"The daily question is now **{'off' if current else 'on'}**."))

    @daily.command(name="now", help="Post a question right now.")
    @has_guild_permission("manage_guild")
    async def daily_now(self, ctx: commands.Context):
        e = emoji_manager.get
        if not await self._post_daily(ctx.guild):
            return await ctx.send(view=error_layout("Can't Post", "Set a channel with `daily channel #channel` first and check my permissions there."))
        await ctx.send(view=success_layout(f"{e('check')} Posted", "A question was posted."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Icebreakers(bot))
