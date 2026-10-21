import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

PREFIX = "sug:"
NO_MENTIONS = discord.AllowedMentions.none()
STATUSES = {
    "pending": ("Pending", 0x5865F2),
    "approved": ("Approved", 0x57F287),
    "denied": ("Denied", 0xED4245),
    "considered": ("Under Consideration", 0xFEE75C),
    "implemented": ("Implemented", 0xEB459E),
}


async def counts(guild_id: int, number: int) -> tuple[int, int]:
    rows = await db.raw_fetch("SELECT vote, COUNT(*) AS n FROM suggestion_votes WHERE guild_id=? AND number=? GROUP BY vote", (guild_id, number))
    tally = {r["vote"]: r["n"] for r in rows}
    return tally.get(1, 0), tally.get(-1, 0)


def suggestion_view(row: dict, author_text: str, up: int, down: int, closed: bool) -> discord.ui.LayoutView:
    label, color = STATUSES[row["status"]]
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## 💡 Suggestion #{row['number']}\n-# From {author_text}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(row["content"]))
    container.add_item(discord.ui.Separator())
    status_line = f"**Status:** {label}"
    if row["reason"]:
        status_line += f"\n**Reason:** {row['reason']}"
    container.add_item(discord.ui.TextDisplay(status_line))
    if not closed:
        action_row = discord.ui.ActionRow()
        action_row.add_item(discord.ui.Button(label=str(up), emoji="👍", style=discord.ButtonStyle.success, custom_id=f"{PREFIX}{row['number']}:up"))
        action_row.add_item(discord.ui.Button(label=str(down), emoji="👎", style=discord.ButtonStyle.danger, custom_id=f"{PREFIX}{row['number']}:down"))
        container.add_item(action_row)
    else:
        container.add_item(discord.ui.TextDisplay(f"-# 👍 {up} · 👎 {down}"))
    view.add_item(container)
    return view


class Suggestions(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_sent: dict[tuple[int, int], float] = {}

    async def _is_reviewer(self, guild: discord.Guild, member: discord.Member) -> bool:
        if member.guild_permissions.manage_guild:
            return True
        role_id = await guild_settings.get(guild.id, "sug_staff_role_id")
        return bool(role_id) and any(r.id == role_id for r in member.roles)

    async def _render(self, guild: discord.Guild, row) -> discord.ui.LayoutView:
        data = dict(row)
        up, down = await counts(guild.id, data["number"])
        member = guild.get_member(data["user_id"])
        author_text = member.mention if member else f"<@{data['user_id']}>"
        return suggestion_view(data, author_text, up, down, data["status"] in ("approved", "denied", "implemented"))

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith(PREFIX):
            return
        parts = custom_id[len(PREFIX):].split(":")
        if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in ("up", "down"):
            return
        number, direction = int(parts[0]), 1 if parts[1] == "up" else -1
        guild = interaction.guild
        row = await db.raw_fetchone("SELECT * FROM suggestions WHERE guild_id=? AND number=?", (guild.id, number))
        if row is None or row["message_id"] != interaction.message.id:
            return await interaction.response.send_message("This suggestion no longer exists.", ephemeral=True)
        existing = await db.raw_fetchone(
            "SELECT vote FROM suggestion_votes WHERE guild_id=? AND number=? AND user_id=?", (guild.id, number, interaction.user.id)
        )
        if existing and existing["vote"] == direction:
            await db.raw_execute("DELETE FROM suggestion_votes WHERE guild_id=? AND number=? AND user_id=?", (guild.id, number, interaction.user.id))
        else:
            await db.raw_execute(
                "INSERT INTO suggestion_votes (guild_id, number, user_id, vote) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(guild_id, number, user_id) DO UPDATE SET vote=excluded.vote",
                (guild.id, number, interaction.user.id, direction),
            )
        await interaction.response.edit_message(view=await self._render(guild, row))

    @commands.command(name="suggest", aliases=["suggestion"], help="Send a suggestion. Usage: suggest <idea>")
    @commands.guild_only()
    async def suggest(self, ctx: commands.Context, *, idea: str):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "sug_channel_id")
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return await ctx.send(view=error_layout("Not Set Up", "Suggestions are not set up here. A staff member can use `suggestions channel #channel`."))
        if len(idea) > 1800:
            return await ctx.send(view=error_layout("Too Long", "Suggestions must be under 1800 characters."))
        key = (ctx.guild.id, ctx.author.id)
        if time.monotonic() - self.last_sent.get(key, -60.0) < 60.0:
            return await ctx.send(view=error_layout("Slow Down", "Please wait a minute between suggestions."))
        self.last_sent[key] = time.monotonic()
        row = await db.raw_fetchone("SELECT COALESCE(MAX(number), 0) AS n FROM suggestions WHERE guild_id=?", (ctx.guild.id,))
        number = int(row["n"]) + 1
        data = {"number": number, "content": idea, "status": "pending", "reason": ""}
        try:
            message = await channel.send(view=suggestion_view(data, ctx.author.mention, 0, 0, False), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Can't Post", "I cannot send messages in the suggestions channel."))
        await db.raw_execute(
            "INSERT INTO suggestions (guild_id, number, user_id, channel_id, message_id, content, status, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', '', ?)",
            (ctx.guild.id, number, ctx.author.id, channel.id, message.id, idea, time.time()),
        )
        await ctx.send(view=success_layout(f"{e('check')} Suggestion Sent", f"Your suggestion is **#{number}** in {channel.mention}."))

    @commands.group(name="suggestions", invoke_without_command=True, help="Review and configure suggestions.")
    @commands.guild_only()
    async def suggestions(self, ctx: commands.Context):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "sug_channel_id")
        role_id = await guild_settings.get(ctx.guild.id, "sug_staff_role_id")
        body = (
            f"**Channel:** {f'<#{channel_id}>' if channel_id else 'not set'}\n"
            f"**Reviewer role:** {f'<@&{role_id}>' if role_id else 'Manage Server only'}\n\n"
            "Members use `suggest <idea>`. Reviewers use `suggestions approve|deny|consider|implement <number> [reason]`.\n"
            "Setup: `suggestions channel #channel`, `suggestions staffrole @role`."
        )
        await ctx.send(view=info_layout(f"{e('settings')} Suggestions", body))

    @suggestions.command(name="channel", help="Set the suggestions channel.")
    @has_guild_permission("manage_guild")
    async def sug_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "sug_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Suggestions will be posted in {channel.mention}."))

    @suggestions.command(name="staffrole", help="Let a role review suggestions.")
    @has_guild_permission("manage_guild")
    async def sug_staffrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        e = emoji_manager.get
        if role is None:
            await guild_settings.delete(ctx.guild.id, "sug_staff_role_id")
            return await ctx.send(view=success_layout(f"{e('check')} Reviewer Role Removed", "Only members with Manage Server can review."))
        await guild_settings.set(ctx.guild.id, "sug_staff_role_id", role.id)
        await ctx.send(view=success_layout(f"{e('check')} Reviewer Role Set", f"{role.mention} can now review suggestions."))

    async def _review(self, ctx: commands.Context, number: int, status: str, reason: str):
        e = emoji_manager.get
        if not await self._is_reviewer(ctx.guild, ctx.author):
            return await ctx.send(view=error_layout("No Permission", "You need Manage Server or the reviewer role."))
        row = await db.raw_fetchone("SELECT * FROM suggestions WHERE guild_id=? AND number=?", (ctx.guild.id, number))
        if row is None:
            return await ctx.send(view=error_layout("Not Found", f"There is no suggestion #{number}."))
        await db.raw_execute(
            "UPDATE suggestions SET status=?, reason=? WHERE guild_id=? AND number=?", (status, reason[:500], ctx.guild.id, number)
        )
        row = await db.raw_fetchone("SELECT * FROM suggestions WHERE guild_id=? AND number=?", (ctx.guild.id, number))
        channel = ctx.guild.get_channel(row["channel_id"])
        if channel is not None:
            try:
                message = await channel.fetch_message(row["message_id"])
                await message.edit(view=await self._render(ctx.guild, row))
            except discord.HTTPException:
                pass
        member = ctx.guild.get_member(row["user_id"])
        if member is not None:
            try:
                await member.send(f"Your suggestion #{number} in **{ctx.guild.name}** is now **{STATUSES[status][0]}**." + (f"\nReason: {reason}" if reason else ""))
            except discord.HTTPException:
                pass
        await ctx.send(view=success_layout(f"{e('check')} Suggestion Updated", f"Suggestion #{number} is now **{STATUSES[status][0]}**."))

    @suggestions.command(name="approve", help="Approve a suggestion.")
    async def sug_approve(self, ctx: commands.Context, number: int, *, reason: str = ""):
        await self._review(ctx, number, "approved", reason)

    @suggestions.command(name="deny", help="Deny a suggestion.")
    async def sug_deny(self, ctx: commands.Context, number: int, *, reason: str = ""):
        await self._review(ctx, number, "denied", reason)

    @suggestions.command(name="consider", help="Mark a suggestion as under consideration.")
    async def sug_consider(self, ctx: commands.Context, number: int, *, reason: str = ""):
        await self._review(ctx, number, "considered", reason)

    @suggestions.command(name="implement", aliases=["implemented", "done"], help="Mark a suggestion as implemented.")
    async def sug_implement(self, ctx: commands.Context, number: int, *, reason: str = ""):
        await self._review(ctx, number, "implemented", reason)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
