from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

DEFAULT_EMOJI = "⭐"
DEFAULT_THRESHOLD = 3


class Starboard(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _settings(self, guild: discord.Guild):
        channel_id = await guild_settings.get(guild.id, "star_channel_id")
        if not channel_id or not await guild_settings.get(guild.id, "star_enabled", True):
            return None
        channel = guild.get_channel(channel_id)
        if channel is None:
            return None
        emoji = await guild_settings.get(guild.id, "star_emoji", DEFAULT_EMOJI)
        threshold = int(await guild_settings.get(guild.id, "star_threshold", DEFAULT_THRESHOLD))
        return channel, emoji, threshold

    @staticmethod
    def _matches(emoji: discord.PartialEmoji, configured: str) -> bool:
        return str(emoji) == configured

    async def _count(self, message: discord.Message, configured: str) -> int:
        for reaction in message.reactions:
            if str(reaction.emoji) == configured:
                users = [u async for u in reaction.users(limit=200)]
                return len({u.id for u in users if not u.bot and u.id != message.author.id})
        return 0

    def _build(self, message: discord.Message, emoji: str, stars: int) -> tuple[str, discord.Embed]:
        embed = discord.Embed(description=message.content[:4000] or None, color=0xFFAC33, timestamp=message.created_at)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        image = next((a for a in message.attachments if (a.content_type or "").startswith("image/")), None)
        if image:
            embed.set_image(url=image.url)
        extra = [a for a in message.attachments if a is not image]
        if extra:
            embed.add_field(name="Attachments", value="\n".join(f"[{a.filename}]({a.url})" for a in extra[:5]), inline=False)
        embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})", inline=False)
        return f"{emoji} **{stars}** | {message.channel.mention}", embed

    async def _update(self, guild: discord.Guild, channel_id: int, message_id: int):
        config = await self._settings(guild)
        if config is None:
            return
        star_channel, emoji, threshold = config
        source = guild.get_channel_or_thread(channel_id)
        if source is None or source.id == star_channel.id or getattr(source, "is_nsfw", lambda: False)():
            return
        try:
            message = await source.fetch_message(message_id)
        except discord.HTTPException:
            return
        if message.author.bot and message.author.id == self.bot.user.id:
            return
        stars = await self._count(message, emoji)
        row = await db.raw_fetchone("SELECT star_message_id FROM starboard_posts WHERE guild_id=? AND message_id=?", (guild.id, message_id))
        if row is None:
            if stars < threshold:
                return
            content, embed = self._build(message, emoji, stars)
            try:
                posted = await star_channel.send(content, embed=embed)
            except discord.HTTPException:
                return
            await db.raw_execute(
                "INSERT INTO starboard_posts (guild_id, message_id, channel_id, star_message_id, stars) VALUES (?, ?, ?, ?, ?)",
                (guild.id, message_id, channel_id, posted.id, stars),
            )
            return
        try:
            posted = await star_channel.fetch_message(row["star_message_id"])
        except discord.NotFound:
            await db.raw_execute("DELETE FROM starboard_posts WHERE guild_id=? AND message_id=?", (guild.id, message_id))
            return
        except discord.HTTPException:
            return
        if stars < max(1, threshold - 1):
            try:
                await posted.delete()
            except discord.HTTPException:
                pass
            await db.raw_execute("DELETE FROM starboard_posts WHERE guild_id=? AND message_id=?", (guild.id, message_id))
            return
        content, embed = self._build(message, emoji, stars)
        try:
            await posted.edit(content=content, embed=embed)
        except discord.HTTPException:
            return
        await db.raw_execute("UPDATE starboard_posts SET stars=? WHERE guild_id=? AND message_id=?", (stars, guild.id, message_id))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle(payload)

    async def _handle(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        config = await self._settings(guild)
        if config is None or not self._matches(payload.emoji, config[1]):
            return
        await self._update(guild, payload.channel_id, payload.message_id)

    @commands.group(name="starboard", aliases=["stars"], invoke_without_command=True, help="Highlight popular messages.")
    @commands.guild_only()
    async def starboard(self, ctx: commands.Context):
        e = emoji_manager.get
        channel_id = await guild_settings.get(ctx.guild.id, "star_channel_id")
        emoji = await guild_settings.get(ctx.guild.id, "star_emoji", DEFAULT_EMOJI)
        threshold = await guild_settings.get(ctx.guild.id, "star_threshold", DEFAULT_THRESHOLD)
        enabled = await guild_settings.get(ctx.guild.id, "star_enabled", True)
        body = (
            f"**Status:** {'on' if enabled else 'off'}\n"
            f"**Channel:** {f'<#{channel_id}>' if channel_id else 'not set'}\n"
            f"**Emoji:** {emoji}\n"
            f"**Stars needed:** {threshold}\n\n"
            "`starboard channel #channel`, `starboard emoji <emoji>`, `starboard threshold <number>`, `starboard toggle`, `starboard top`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Starboard", body))

    @starboard.command(name="channel", help="Set the starboard channel.")
    @has_guild_permission("manage_guild")
    async def star_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "star_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Popular messages will be posted in {channel.mention}."))

    @starboard.command(name="emoji", help="Set the emoji members react with.")
    @has_guild_permission("manage_guild")
    async def star_emoji(self, ctx: commands.Context, emoji: str):
        e = emoji_manager.get
        if emoji.isascii() and not emoji.startswith("<"):
            return await ctx.send(view=error_layout("Invalid Emoji", "Use a normal emoji or a custom emoji from this server."))
        await guild_settings.set(ctx.guild.id, "star_emoji", emoji)
        await ctx.send(view=success_layout(f"{e('check')} Emoji Set", f"Members now react with {emoji}."))

    @starboard.command(name="threshold", help="Set how many reactions are needed.")
    @has_guild_permission("manage_guild")
    async def star_threshold(self, ctx: commands.Context, amount: int):
        e = emoji_manager.get
        if not 1 <= amount <= 50:
            return await ctx.send(view=error_layout("Invalid Amount", "Use a number between 1 and 50."))
        await guild_settings.set(ctx.guild.id, "star_threshold", amount)
        await ctx.send(view=success_layout(f"{e('check')} Threshold Set", f"Messages need **{amount}** reaction(s) to be starred."))

    @starboard.command(name="toggle", help="Turn the starboard on or off.")
    @has_guild_permission("manage_guild")
    async def star_toggle(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await guild_settings.get(ctx.guild.id, "star_enabled", True)
        await guild_settings.set(ctx.guild.id, "star_enabled", not current)
        await ctx.send(view=success_layout(f"{e('check')} Starboard", f"The starboard is now **{'off' if current else 'on'}**."))

    @starboard.command(name="top", help="Show the most starred messages.")
    @commands.guild_only()
    async def star_top(self, ctx: commands.Context):
        rows = await db.raw_fetch(
            "SELECT channel_id, message_id, stars FROM starboard_posts WHERE guild_id=? ORDER BY stars DESC LIMIT 10", (ctx.guild.id,)
        )
        if not rows:
            return await ctx.send(view=info_layout("⭐ Top Messages", "Nothing has been starred yet."))
        lines = [f"**{i}.** {r['stars']} stars - https://discord.com/channels/{ctx.guild.id}/{r['channel_id']}/{r['message_id']}" for i, r in enumerate(rows, 1)]
        await ctx.send(view=info_layout("⭐ Top Messages", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Starboard(bot))
