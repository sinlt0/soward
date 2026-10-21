import re
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

BUTTON_ID = "conf:submit"
INVITE_PATTERN = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
COOLDOWN = 60.0
MAX_LENGTH = 1800
NO_MENTIONS = discord.AllowedMentions.none()


def confession_view(number: int, text: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xFFB3D9)
    container.add_item(discord.ui.TextDisplay(f"## 🤫 Anonymous Confession #{number}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(text))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("-# Sent anonymously. Staff cannot see who wrote it."))
    view.add_item(container)
    return view


def panel_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xFFB3D9)
    container.add_item(discord.ui.TextDisplay(
        "## 🤫 Confessions\nShare something anonymously. Press the button, write your confession and it will be posted without your name.\n"
        "-# No hate, threats, personal info or invite links. Abuse can get you blocked from confessing."
    ))
    container.add_item(discord.ui.Separator())
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Confess", emoji="🤫", style=discord.ButtonStyle.primary, custom_id=BUTTON_ID))
    container.add_item(row)
    view.add_item(container)
    return view


class ConfessModal(discord.ui.Modal, title="Anonymous Confession"):
    text = discord.ui.TextInput(label="Your confession", style=discord.TextStyle.paragraph, max_length=MAX_LENGTH, min_length=5)

    def __init__(self, cog: "Confessions"):
        super().__init__(timeout=600)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.submit(interaction, str(self.text.value))


class Confessions(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_sent: dict[tuple[int, int], float] = {}

    async def _channel(self, guild: discord.Guild, key: str):
        channel_id = await guild_settings.get(guild.id, key)
        return guild.get_channel(channel_id) if channel_id else None

    async def submit(self, interaction: discord.Interaction, text: str):
        guild = interaction.guild
        user = interaction.user
        channel = await self._channel(guild, "confess_channel_id")
        if channel is None or not await guild_settings.get(guild.id, "confess_enabled", True):
            return await interaction.response.send_message("Confessions are turned off in this server.", ephemeral=True)
        banned = await db.raw_fetchone("SELECT 1 FROM confession_bans WHERE guild_id=? AND user_id=?", (guild.id, user.id))
        if banned:
            return await interaction.response.send_message("You are blocked from sending confessions here.", ephemeral=True)
        key = (guild.id, user.id)
        wait = COOLDOWN - (time.monotonic() - self.last_sent.get(key, -COOLDOWN))
        if wait > 0:
            return await interaction.response.send_message(f"Please wait {wait:.0f}s before confessing again.", ephemeral=True)
        if INVITE_PATTERN.search(text):
            return await interaction.response.send_message("Invite links are not allowed in confessions.", ephemeral=True)
        row = await db.raw_fetchone("SELECT COALESCE(MAX(number), 0) AS n FROM confessions WHERE guild_id=?", (guild.id,))
        number = int(row["n"]) + 1
        try:
            message = await channel.send(view=confession_view(number, text), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            return await interaction.response.send_message("I could not post in the confession channel.", ephemeral=True)
        self.last_sent[key] = time.monotonic()
        await db.raw_execute(
            "INSERT INTO confessions (guild_id, number, user_id, channel_id, message_id, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild.id, number, user.id, channel.id, message.id, text, time.time()),
        )
        await interaction.response.send_message(f"Your confession was posted as **#{number}**. Nobody can see who sent it.", ephemeral=True)
        log_channel = await self._channel(guild, "confess_log_channel_id")
        if log_channel is not None:
            try:
                await log_channel.send(
                    view=info_layout(f"Confession #{number}", f"{text}\n\n-# Author hidden. Use `confess ban {number}` to block the sender or `confess delete {number}` to remove it."),
                    allowed_mentions=NO_MENTIONS,
                )
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        if (interaction.data or {}).get("custom_id") != BUTTON_ID:
            return
        await interaction.response.send_modal(ConfessModal(self))

    @commands.group(name="confess", aliases=["confessions", "confession"], invoke_without_command=True, help="Anonymous confessions.")
    @commands.guild_only()
    async def confess(self, ctx: commands.Context):
        e = emoji_manager.get
        channel = await self._channel(ctx.guild, "confess_channel_id")
        log_channel = await self._channel(ctx.guild, "confess_log_channel_id")
        enabled = await guild_settings.get(ctx.guild.id, "confess_enabled", True)
        body = (
            f"**Status:** {'on' if enabled else 'off'}\n"
            f"**Channel:** {channel.mention if channel else 'not set'}\n"
            f"**Staff log:** {log_channel.mention if log_channel else 'not set'}\n\n"
            "Members press the **Confess** button on the panel. Staff commands: `confess channel #c`, `confess log #c`, `confess panel [#c]`, "
            "`confess delete <n>`, `confess ban <n>`, `confess unban <n>`, `confess toggle`."
        )
        await ctx.send(view=info_layout(f"{e('settings')} Confessions", body))

    @confess.command(name="channel", help="Set where confessions are posted.")
    @has_guild_permission("manage_guild")
    async def confess_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "confess_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Confessions will be posted in {channel.mention}. Use `confess panel` to post the button."))

    @confess.command(name="log", help="Set a private staff channel that receives a copy of each confession.")
    @has_guild_permission("manage_guild")
    async def confess_log(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        if channel is None:
            await guild_settings.delete(ctx.guild.id, "confess_log_channel_id")
            return await ctx.send(view=success_layout(f"{e('check')} Log Removed", "The staff log was turned off."))
        await guild_settings.set(ctx.guild.id, "confess_log_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Log Set", f"Confession copies will go to {channel.mention}. The author is never shown."))

    @confess.command(name="panel", help="Post the confession button. Usage: confess panel [#channel]")
    @has_guild_permission("manage_guild")
    async def confess_panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        target = channel or ctx.channel
        try:
            await target.send(view=panel_view())
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Can't Post", f"I cannot send messages in {target.mention}."))
        await ctx.send(view=success_layout(f"{e('check')} Panel Posted", f"The confession panel is in {target.mention}."))

    @confess.command(name="toggle", help="Turn confessions on or off.")
    @has_guild_permission("manage_guild")
    async def confess_toggle(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await guild_settings.get(ctx.guild.id, "confess_enabled", True)
        await guild_settings.set(ctx.guild.id, "confess_enabled", not current)
        await ctx.send(view=success_layout(f"{e('check')} Confessions", f"Confessions are now **{'off' if current else 'on'}**."))

    async def _row(self, ctx: commands.Context, number: int):
        row = await db.raw_fetchone("SELECT * FROM confessions WHERE guild_id=? AND number=?", (ctx.guild.id, number))
        if row is None:
            await ctx.send(view=error_layout("Not Found", f"There is no confession #{number}."))
        return row

    @confess.command(name="delete", aliases=["remove"], help="Delete a confession. Usage: confess delete <number>")
    @has_guild_permission("manage_messages")
    async def confess_delete(self, ctx: commands.Context, number: int):
        e = emoji_manager.get
        row = await self._row(ctx, number)
        if row is None:
            return
        channel = ctx.guild.get_channel(row["channel_id"])
        if channel is not None:
            try:
                await (await channel.fetch_message(row["message_id"])).delete()
            except discord.HTTPException:
                pass
        await db.raw_execute("UPDATE confessions SET content='' WHERE guild_id=? AND number=?", (ctx.guild.id, number))
        await ctx.send(view=success_layout(f"{e('check')} Deleted", f"Confession #{number} was removed."))

    @confess.command(name="ban", help="Block the sender of a confession without revealing them. Usage: confess ban <number>")
    @has_guild_permission("manage_guild")
    async def confess_ban(self, ctx: commands.Context, number: int):
        e = emoji_manager.get
        row = await self._row(ctx, number)
        if row is None:
            return
        await db.raw_execute(
            "INSERT OR IGNORE INTO confession_bans (guild_id, user_id, banned_at) VALUES (?, ?, ?)", (ctx.guild.id, row["user_id"], time.time())
        )
        await ctx.send(view=success_layout(f"{e('check')} Sender Blocked", f"The sender of #{number} can no longer confess. Their identity was not shown."))

    @confess.command(name="unban", help="Unblock the sender of a confession. Usage: confess unban <number>")
    @has_guild_permission("manage_guild")
    async def confess_unban(self, ctx: commands.Context, number: int):
        e = emoji_manager.get
        row = await self._row(ctx, number)
        if row is None:
            return
        await db.raw_execute("DELETE FROM confession_bans WHERE guild_id=? AND user_id=?", (ctx.guild.id, row["user_id"]))
        await ctx.send(view=success_layout(f"{e('check')} Sender Unblocked", f"The sender of #{number} can confess again."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Confessions(bot))
