import re
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, message_vars
from utils.components import error_layout, footer_block, info_layout, success_layout
from utils.converters import format_duration
import config

DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
DURATION_PATTERN = re.compile(r"^(\d+[smhdw])+$")

MAX_GUILD_SELECT_OPTIONS = 25


def _parse_leading_duration(text: str) -> tuple[Optional[int], str]:
    if not text:
        return None, text
    parts = text.split(maxsplit=1)
    first = parts[0].lower()
    if not DURATION_PATTERN.match(first):
        return None, text

    total = 0
    for amount, unit in re.findall(r"(\d+)([smhdw])", first):
        total += int(amount) * DURATION_UNITS[unit]
    remainder = parts[1] if len(parts) > 1 else ""
    return total, remainder


def _validate_duration(duration_seconds: Optional[int]) -> Optional[str]:
    if duration_seconds is None:
        return None
    if duration_seconds <= 0 or duration_seconds > config.AFK_MAX_AUTO_RETURN_MINUTES * 60:
        return f"Duration must be between 1 second and {config.AFK_MAX_AUTO_RETURN_MINUTES // 60} hours."
    return None


async def get_server_afk(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM member_afk WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return dict(row) if row else None


async def get_global_afk(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM global_afk WHERE user_id=?", (user_id,))
    return dict(row) if row else None


async def set_server_afk(guild: discord.Guild, member: discord.Member, message_text: str, duration_seconds: Optional[int]) -> None:
    already_afk_prefixed = (member.nick or "").startswith(config.AFK_NICK_PREFIX)
    existing = await get_server_afk(guild.id, member.id)
    original_nick = member.nick if not already_afk_prefixed else (existing or {}).get("original_nick")
    pre_afk_display_name = member.nick if (member.nick and not already_afk_prefixed) else member.name

    auto_return_at = (time.time() + duration_seconds) if duration_seconds else None

    await db.raw_execute(
        "INSERT INTO member_afk (guild_id, user_id, message, set_at, original_nick, auto_return_at) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET message=excluded.message, set_at=excluded.set_at,"
        " original_nick=excluded.original_nick, auto_return_at=excluded.auto_return_at",
        (guild.id, member.id, message_text, time.time(), original_nick, auto_return_at),
    )
    await db.raw_execute("DELETE FROM afk_mention_log WHERE guild_id=? AND afk_user_id=?", (guild.id, member.id))

    if not already_afk_prefixed:
        try:
            new_nick = f"{config.AFK_NICK_PREFIX}{pre_afk_display_name}"[:32]
            await member.edit(nick=new_nick, reason="AFK: set")
        except discord.HTTPException:
            pass


async def set_global_afk(user_id: int, message_text: str, duration_seconds: Optional[int]) -> None:
    auto_return_at = (time.time() + duration_seconds) if duration_seconds else None
    await db.raw_execute(
        "INSERT INTO global_afk (user_id, message, set_at, auto_return_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET message=excluded.message, set_at=excluded.set_at, auto_return_at=excluded.auto_return_at",
        (user_id, message_text, time.time(), auto_return_at),
    )
    await db.raw_execute("DELETE FROM global_afk_mention_log WHERE afk_user_id=?", (user_id,))


async def clear_server_afk(guild: discord.Guild, member: discord.Member) -> Optional[dict]:
    row = await get_server_afk(guild.id, member.id)
    if not row:
        return None

    await db.raw_execute("DELETE FROM member_afk WHERE guild_id=? AND user_id=?", (guild.id, member.id))

    if row["original_nick"] is not None or (member.nick or "").startswith(config.AFK_NICK_PREFIX):
        if (member.nick or "").startswith(config.AFK_NICK_PREFIX):
            try:
                await member.edit(nick=row["original_nick"] or None, reason="AFK: returned")
            except discord.HTTPException:
                pass

    return row


async def clear_global_afk(user_id: int) -> Optional[dict]:
    row = await get_global_afk(user_id)
    if not row:
        return None
    await db.raw_execute("DELETE FROM global_afk WHERE user_id=?", (user_id,))
    return row


class GuildMultiSelect(discord.ui.Select):
    def __init__(self, guilds: list[discord.Guild]):
        options = [
            discord.SelectOption(label=g.name[:100], value=str(g.id))
            for g in guilds[:MAX_GUILD_SELECT_OPTIONS]
        ]
        super().__init__(
            placeholder="Choose servers to go AFK in (optional)...",
            options=options,
            min_values=0,
            max_values=len(options),
            custom_id="afk:guild_select",
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_guild_ids = [int(v) for v in self.values]
        await interaction.response.defer()


class ServerAFKConfirmRow(discord.ui.ActionRow):
    def __init__(self, view: "AFKScopeView"):
        super().__init__(
            discord.ui.Button(label="Go AFK", style=discord.ButtonStyle.success, custom_id="afk:confirm_server"),
        )
        self.parent_view = view
        self.children[0].callback = self._confirm

    async def _confirm(self, interaction: discord.Interaction):
        view = self.parent_view
        if interaction.user.id != view.author.id:
            return await interaction.response.send_message("This isn't your AFK setup.", ephemeral=True)

        target_guild_ids = view.selected_guild_ids or [view.current_guild.id]
        e = emoji_manager.get

        applied = []
        for guild_id in target_guild_ids:
            guild = view.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(view.author.id)
            if not member:
                continue
            await set_server_afk(guild, member, view.message_text, view.duration_seconds)
            applied.append(guild.name)

        if not applied:
            return await interaction.response.edit_message(
                view=error_layout("Failed", "Couldn't apply AFK to any of the selected servers."),
            )

        body = f"**Message:** {view.message_text}\n**Servers:** {', '.join(applied)}"
        if view.duration_seconds:
            body += f"\n**Auto-return in:** {format_duration(view.duration_seconds)}"
        await interaction.response.edit_message(view=success_layout(f"{e('afk')} You're now AFK", body))


class AFKScopeRow(discord.ui.ActionRow):
    def __init__(self, view: "AFKScopeView"):
        super().__init__(
            discord.ui.Button(label="Global", style=discord.ButtonStyle.primary, custom_id="afk:scope_global"),
            discord.ui.Button(label="Server", style=discord.ButtonStyle.secondary, custom_id="afk:scope_server"),
        )
        self.parent_view = view
        self.children[0].callback = self._go_global
        self.children[1].callback = self._go_server

    async def _go_global(self, interaction: discord.Interaction):
        view = self.parent_view
        if interaction.user.id != view.author.id:
            return await interaction.response.send_message("This isn't your AFK setup.", ephemeral=True)

        e = emoji_manager.get
        await set_global_afk(view.author.id, view.message_text, view.duration_seconds)

        body = f"**Message:** {view.message_text}\n**Scope:** Global (every mutual server)"
        if view.duration_seconds:
            body += f"\n**Auto-return in:** {format_duration(view.duration_seconds)}"
        await interaction.response.edit_message(view=success_layout(f"{e('afk')} You're now AFK", body))

    async def _go_server(self, interaction: discord.Interaction):
        view = self.parent_view
        if interaction.user.id != view.author.id:
            return await interaction.response.send_message("This isn't your AFK setup.", ephemeral=True)

        view.showing_server_select = True
        view._build()
        await interaction.response.edit_message(view=view)


class AFKScopeView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, author: discord.Member, current_guild: discord.Guild, message_text: str, duration_seconds: Optional[int]):
        super().__init__(timeout=120)
        self.bot = bot
        self.author = author
        self.current_guild = current_guild
        self.message_text = message_text
        self.duration_seconds = duration_seconds
        self.showing_server_select = False
        self.selected_guild_ids: list[int] = []
        self._build()

    def _mutual_guilds(self) -> list[discord.Guild]:
        return [g for g in self.author.mutual_guilds if g.get_member(self.author.id)]

    def _build(self):
        e = emoji_manager.get
        self.clear_items()
        container = discord.ui.Container(accent_color=0x5865F2)

        if not self.showing_server_select:
            container.add_item(discord.ui.TextDisplay(
                f"## {e('afk')} Set AFK\n"
                f"**Message:** {self.message_text}\n\n"
                "Choose a scope: **Global** applies to every mutual server between you and the bot. "
                "**Server** lets you pick specific servers, or just the current one."
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(AFKScopeRow(self))
        else:
            guilds = self._mutual_guilds()
            container.add_item(discord.ui.TextDisplay(
                f"## {e('afk')} Choose Servers\n"
                f"**Message:** {self.message_text}\n\n"
                "Select one or more servers below, then press **Go AFK**. "
                f"If you don't select any, you'll just go AFK in **{self.current_guild.name}**."
            ))
            container.add_item(discord.ui.Separator())
            if guilds:
                container.add_item(discord.ui.ActionRow(GuildMultiSelect(guilds)))
            else:
                container.add_item(discord.ui.TextDisplay("-# No other mutual servers found."))
            container.add_item(ServerAFKConfirmRow(self))

        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your AFK setup.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class AFK(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.auto_return_loop.start()

    def cog_unload(self):
        self.auto_return_loop.cancel()

    @tasks.loop(minutes=1)
    async def auto_return_loop(self):
        now = time.time()

        expired_server = await db.raw_fetch(
            "SELECT * FROM member_afk WHERE auto_return_at IS NOT NULL AND auto_return_at <= ?", (now,)
        )
        for row in expired_server:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                await db.raw_execute("DELETE FROM member_afk WHERE guild_id=? AND user_id=?", (row["guild_id"], row["user_id"]))
                continue
            member = guild.get_member(row["user_id"])
            if not member:
                await db.raw_execute("DELETE FROM member_afk WHERE guild_id=? AND user_id=?", (row["guild_id"], row["user_id"]))
                continue
            await clear_server_afk(guild, member)

        expired_global = await db.raw_fetch(
            "SELECT * FROM global_afk WHERE auto_return_at IS NOT NULL AND auto_return_at <= ?", (now,)
        )
        for row in expired_global:
            await clear_global_afk(row["user_id"])
            await db.raw_execute("DELETE FROM global_afk_mention_log WHERE afk_user_id=?", (row["user_id"],))

    @auto_return_loop.before_loop
    async def _before_auto_return_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name="afk", help="Set yourself as AFK. Usage: afk [duration] [message], then choose Global or Server scope.")
    @commands.guild_only()
    async def afk_cmd(self, ctx: commands.Context, *, text: str = ""):
        duration_seconds, message_text = _parse_leading_duration(text)
        message_text = message_text.strip() or "AFK"

        error = _validate_duration(duration_seconds)
        if error:
            return await ctx.send(view=error_layout("Invalid Duration", error))

        view = AFKScopeView(self.bot, ctx.author, ctx.guild, message_text, duration_seconds)
        await ctx.send(view=view)

    @commands.Cog.listener("on_message")
    async def on_message_afk_check(self, message: discord.Message):
        if message.author.bot:
            return

        e = emoji_manager.get

        global_row = await get_global_afk(message.author.id)
        if global_row:
            cleared = await clear_global_afk(message.author.id)
            if cleared:
                await self._send_return_digest(message, cleared, scope="global")

        server_row = await get_server_afk(message.guild.id, message.author.id) if message.guild else None
        if server_row:
            cleared = await clear_server_afk(message.guild, message.author)
            if cleared:
                await self._send_return_digest(message, cleared, scope="server")

        if not message.guild or not message.mentions:
            return

        for mentioned in message.mentions:
            if mentioned.bot or mentioned.id == message.author.id:
                continue

            mentioned_global = await get_global_afk(mentioned.id)
            mentioned_server = await get_server_afk(message.guild.id, mentioned.id)
            active = mentioned_global or mentioned_server
            if not active:
                continue

            preview = message.content[:150] if message.content else "[no text content]"

            if mentioned_global:
                await db.raw_execute(
                    "INSERT INTO global_afk_mention_log (afk_user_id, mentioner_id, guild_id, channel_id, content_preview, mentioned_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (mentioned.id, message.author.id, message.guild.id, message.channel.id, preview, time.time()),
                )
            if mentioned_server:
                await db.raw_execute(
                    "INSERT INTO afk_mention_log (guild_id, afk_user_id, mentioner_id, channel_id, content_preview, mentioned_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (message.guild.id, mentioned.id, message.author.id, message.channel.id, preview, time.time()),
                )

            var_map = message_vars.build_base_variables(mentioned, message.guild, message.channel)
            afk_text = message_vars.substitute(active["message"] or "AFK", var_map)
            try:
                await message.channel.send(
                    f"{e('afk')} **This user is AFK:** {mentioned.mention}\n> {afk_text}",
                    allowed_mentions=discord.AllowedMentions.none(),
                    delete_after=15,
                )
            except discord.HTTPException:
                pass

    async def _send_return_digest(self, message: discord.Message, afk_row: dict, scope: str) -> None:
        e = emoji_manager.get

        if scope == "global":
            mentions = await db.raw_fetch(
                "SELECT * FROM global_afk_mention_log WHERE afk_user_id=? ORDER BY mentioned_at DESC LIMIT ?",
                (message.author.id, config.AFK_MENTION_LOG_LIMIT),
            )
            await db.raw_execute("DELETE FROM global_afk_mention_log WHERE afk_user_id=?", (message.author.id,))

            def location_field(m):
                guild = self.bot.get_guild(m["guild_id"])
                guild_name = guild.name if guild else "a mutual server"
                return f"<#{m['channel_id']}> in **{guild_name}**"
        else:
            mentions = await db.raw_fetch(
                "SELECT * FROM afk_mention_log WHERE guild_id=? AND afk_user_id=? ORDER BY mentioned_at DESC LIMIT ?",
                (message.guild.id, message.author.id, config.AFK_MENTION_LOG_LIMIT),
            )
            await db.raw_execute("DELETE FROM afk_mention_log WHERE guild_id=? AND afk_user_id=?", (message.guild.id, message.author.id))

            def location_field(m):
                return f"<#{m['channel_id']}>"

        duration = format_duration(int(time.time() - afk_row["set_at"]))
        scope_label = "globally" if scope == "global" else "in this server"
        body = f"Welcome back! You were AFK {scope_label} for **{duration}**."

        if mentions:
            lines = [f"<@{m['mentioner_id']}> in {location_field(m)}: {m['content_preview']}" for m in mentions[:10]]
            body += f"\n\n**You were mentioned {len(mentions)} time(s):**\n" + "\n".join(lines)
            if len(mentions) > 10:
                body += f"\n-# ...and {len(mentions) - 10} more."

        try:
            await message.channel.send(view=info_layout(f"{e('afk')} Welcome Back", body), delete_after=30)
        except discord.HTTPException:
            pass

    @commands.command(name="afkcheck", aliases=["isafk"], help="Check whether a member is currently AFK (server or global).")
    @commands.guild_only()
    async def afkcheck(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        member = member or ctx.author

        global_row = await get_global_afk(member.id)
        server_row = await get_server_afk(ctx.guild.id, member.id)

        if not global_row and not server_row:
            return await ctx.send(view=info_layout(f"{e('afk')} Not AFK", f"{member.mention} is not currently AFK."))

        row = global_row or server_row
        scope_label = "Globally" if global_row else "In this server"
        duration = format_duration(int(time.time() - row["set_at"]))
        body = f"**Scope:** {scope_label}\n**Message:** {row['message']}\n**AFK for:** {duration}"
        if row["auto_return_at"]:
            remaining = int(row["auto_return_at"] - time.time())
            if remaining > 0:
                body += f"\n**Auto-return in:** {format_duration(remaining)}"
        await ctx.send(view=info_layout(f"{e('afk')} {member.display_name} is AFK", body))


async def setup(bot: commands.Bot):
    await bot.add_cog(AFK(bot))
