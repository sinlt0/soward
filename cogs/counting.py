import re

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NUMBER = re.compile(r"^\s*(\d{1,12})\b")


class Counting(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _state(self, guild_id: int) -> dict:
        row = await db.raw_fetchone("SELECT * FROM counting_state WHERE guild_id=?", (guild_id,))
        if row:
            return dict(row)
        return {"guild_id": guild_id, "current": 0, "last_user_id": None, "high_score": 0, "total_ruined": 0}

    async def _save(self, state: dict):
        await db.raw_execute(
            "INSERT INTO counting_state (guild_id, current, last_user_id, high_score, total_ruined) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET current=excluded.current, last_user_id=excluded.last_user_id,"
            " high_score=excluded.high_score, total_ruined=excluded.total_ruined",
            (state["guild_id"], state["current"], state["last_user_id"], state["high_score"], state["total_ruined"]),
        )

    async def _bump(self, guild_id: int, user_id: int, correct: int, ruined: int):
        await db.raw_execute(
            "INSERT INTO counting_users (guild_id, user_id, correct, ruined) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET correct=correct+excluded.correct, ruined=ruined+excluded.ruined",
            (guild_id, user_id, correct, ruined),
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        channel_id = await guild_settings.get(message.guild.id, "count_channel_id")
        if not channel_id or message.channel.id != channel_id:
            return
        if not await guild_settings.get(message.guild.id, "count_enabled", True):
            return
        match = NUMBER.match(message.content)
        if not match:
            return
        value = int(match.group(1))
        state = await self._state(message.guild.id)
        expected = state["current"] + 1
        if message.author.id == state["last_user_id"]:
            return await self._ruin(message, state, f"{message.author.mention} counted twice in a row.")
        if value != expected:
            return await self._ruin(message, state, f"{message.author.mention} said **{value}** but the next number was **{expected}**.")
        state["current"] = value
        state["last_user_id"] = message.author.id
        new_record = value > state["high_score"]
        if new_record:
            state["high_score"] = value
        await self._save(state)
        await self._bump(message.guild.id, message.author.id, 1, 0)
        try:
            await message.add_reaction("🏆" if new_record and value >= 10 and value % 10 == 0 else "✅")
        except discord.HTTPException:
            pass
        if value % 100 == 0:
            try:
                await message.channel.send(f"🎉 **{value}!** Great teamwork, keep going.")
            except discord.HTTPException:
                pass

    async def _ruin(self, message: discord.Message, state: dict, reason: str):
        reached = state["current"]
        state["current"] = 0
        state["last_user_id"] = None
        state["total_ruined"] += 1
        await self._save(state)
        await self._bump(message.guild.id, message.author.id, 0, 1)
        try:
            await message.add_reaction("❌")
            await message.channel.send(
                f"{reason} The count reached **{reached}** and is now back to **0**. The next number is **1**.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    @commands.group(name="counting", aliases=["count"], invoke_without_command=True, help="Counting game status.")
    @commands.guild_only()
    async def counting(self, ctx: commands.Context):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "count_channel_id")
        enabled = await guild_settings.get(ctx.guild.id, "count_enabled", True)
        state = await self._state(ctx.guild.id)
        body = (
            f"**Status:** {'on' if enabled else 'off'}\n"
            f"**Channel:** {f'<#{channel_id}>' if channel_id else 'not set'}\n"
            f"**Current number:** {state['current']}\n"
            f"**Record:** {state['high_score']}\n"
            f"**Times ruined:** {state['total_ruined']}\n\n"
            "Rules: count up one at a time and never twice in a row. A wrong number resets the count to 0.\n"
            "`counting channel #c`, `counting toggle`, `counting set <n>`, `counting reset`, `counting top`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Counting", body))

    @counting.command(name="channel", help="Set the counting channel.")
    @has_guild_permission("manage_guild")
    async def counting_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "count_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Counting happens in {channel.mention}. The next number is **{(await self._state(ctx.guild.id))['current'] + 1}**."))

    @counting.command(name="toggle", help="Turn counting on or off.")
    @has_guild_permission("manage_guild")
    async def counting_toggle(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await guild_settings.get(ctx.guild.id, "count_enabled", True)
        await guild_settings.set(ctx.guild.id, "count_enabled", not current)
        await ctx.send(view=success_layout(f"{e('check')} Counting", f"Counting is now **{'off' if current else 'on'}**."))

    @counting.command(name="set", help="Set the current number. Usage: counting set <number>")
    @has_guild_permission("manage_guild")
    async def counting_set(self, ctx: commands.Context, number: int):
        e = emoji_manager.get
        if not 0 <= number <= 10_000_000:
            return await ctx.send(view=error_layout("Invalid Number", "Use a number between 0 and 10,000,000."))
        state = await self._state(ctx.guild.id)
        state["current"] = number
        state["last_user_id"] = None
        state["high_score"] = max(state["high_score"], number)
        await self._save(state)
        await ctx.send(view=success_layout(f"{e('check')} Count Set", f"The next number is **{number + 1}**."))

    @counting.command(name="reset", help="Reset the count to 0.")
    @has_guild_permission("manage_guild")
    async def counting_reset(self, ctx: commands.Context):
        e = emoji_manager.get
        state = await self._state(ctx.guild.id)
        state["current"] = 0
        state["last_user_id"] = None
        await self._save(state)
        await ctx.send(view=success_layout(f"{e('check')} Count Reset", "The next number is **1**."))

    @counting.command(name="top", aliases=["leaderboard", "lb"], help="Show the best counters.")
    @commands.guild_only()
    async def counting_top(self, ctx: commands.Context):
        rows = await db.raw_fetch(
            "SELECT user_id, correct, ruined FROM counting_users WHERE guild_id=? ORDER BY correct DESC LIMIT 10", (ctx.guild.id,)
        )
        if not rows:
            return await ctx.send(view=info_layout("🔢 Top Counters", "Nobody has counted yet."))
        lines = [f"**{i}.** <@{r['user_id']}> - {r['correct']} correct, {r['ruined']} ruined" for i, r in enumerate(rows, 1)]
        await ctx.send(view=info_layout("🔢 Top Counters", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))
