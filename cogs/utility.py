import platform
import time
from typing import Optional

import discord
import psutil
from discord.ext import commands

import config
from utils import db, emoji_manager
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import error_layout, footer_block, info_layout, success_layout
from utils.converters import format_duration


def _layout(title: str, body: str, *, color: int = NEUTRAL, thumbnail: Optional[str] = None, image: Optional[str] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)

    if thumbnail:
        section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=thumbnail))
        section.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
        container.add_item(section)
    else:
        container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))

    if image:
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=image)
        container.add_item(gallery)

    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


async def _build_team_body(bot: commands.Bot) -> str:
    owner_ids = set(config.OWNER_IDS)
    dev_ids = set(config.DEV_IDS)
    all_ids = owner_ids | dev_ids

    lines = []
    for user_id in all_ids:
        try:
            user = await bot.fetch_user(user_id)
            display = f"{user.mention} (`{user}`)"
        except discord.HTTPException:
            display = f"<@{user_id}>"

        if user_id in owner_ids and user_id in dev_ids:
            role = "Owner & Developer"
        elif user_id in owner_ids:
            role = "Owner"
        else:
            role = "Developer"
        lines.append(f"{display} — {role}")

    body = "\n".join(lines) if lines else "No owners or developers configured."

    if config.DEV_ROLE_IDS:
        role_mentions = ", ".join(f"<@&{rid}>" for rid in config.DEV_ROLE_IDS)
        body += f"\n\n**Dev roles (any server):** {role_mentions}"

    return body


class AboutButtonsRow(discord.ui.ActionRow):
    def __init__(self, bot: commands.Bot):
        super().__init__(
            discord.ui.Button(label="Owners & Devs", style=discord.ButtonStyle.secondary, custom_id="about:owners"),
        )
        self.bot = bot
        self.children[0].callback = self._show_team

    async def _show_team(self, interaction: discord.Interaction):
        e = emoji_manager.get
        body = await _build_team_body(self.bot)
        await interaction.response.send_message(
            view=info_layout(f"{e('soward')} Owners & Developers", body), ephemeral=True
        )


class Utility(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()
        self._process = psutil.Process()

    @commands.command(name="ping", help="Check the bot's response latency.")
    async def ping(self, ctx: commands.Context):
        e = emoji_manager.get
        start = time.perf_counter()
        message = await ctx.send(view=info_layout(f"{e('ping')} Pong!", "Measuring..."))
        rest_latency = (time.perf_counter() - start) * 1000
        gateway_latency = round(self.bot.latency * 1000)

        db_start = time.perf_counter()
        await db.raw_fetchone("SELECT 1")
        db_latency = (time.perf_counter() - db_start) * 1000

        body = (
            f"**Gateway:** `{gateway_latency}ms`\n"
            f"**REST API:** `{rest_latency:.0f}ms`\n"
            f"**Database:** `{db_latency:.1f}ms`"
        )
        await message.edit(view=info_layout(f"{e('ping')} Pong!", body))

    @commands.command(name="uptime", help="Show how long the bot has been running.")
    async def uptime(self, ctx: commands.Context):
        e = emoji_manager.get
        elapsed = int(time.time() - self.start_time)
        started_at = int(self.start_time)
        body = (
            f"**Online for:** {format_duration(elapsed)}\n"
            f"**Started:** <t:{started_at}:F> (<t:{started_at}:R>)"
        )
        await ctx.send(view=info_layout(f"{e('uptime')} Uptime", body))

    @commands.command(name="about", aliases=["credits", "botinfo", "bi"], help="About Soward — version, developer, and live stats.")
    async def about(self, ctx: commands.Context):
        e = emoji_manager.get

        try:
            developer = await self.bot.fetch_user(config.DEVELOPER_USER_ID)
            dev_display = f"{developer.mention} (`{developer}`)"
        except discord.HTTPException:
            dev_display = f"<@{config.DEVELOPER_USER_ID}>"

        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        text_channels = sum(len(g.text_channels) for g in self.bot.guilds)
        voice_channels = sum(len(g.voice_channels) for g in self.bot.guilds)

        mem_info = self._process.memory_info()
        mem_mb = mem_info.rss / (1024 * 1024)
        cpu_percent = self._process.cpu_percent(interval=None)

        uptime_secs = int(time.time() - self.start_time)
        db_mode = "MongoDB (primary) + SQLite (mirror)" if db.is_mongo_available() else "SQLite (MongoDB unavailable)"

        music_cog = self.bot.get_cog("Music")
        voice_connections = len(music_cog.bot.voice_clients) if music_cog else len(self.bot.voice_clients)

        body = (
            f"**{config.BOT_NAME}** is an all-in-one Discord bot built for moderation, security, "
            f"engagement, and utility — running on Components V2 throughout.\n\n"
            f"**Developer:** {dev_display}\n"
            f"**Version:** `{config.BOT_VERSION}`\n"
            f"**Library:** discord.py `{discord.__version__}`\n"
            f"**Python:** `{platform.python_version()}`\n\n"
            f"**Servers:** `{len(self.bot.guilds):,}`\n"
            f"**Users:** `{total_members:,}`\n"
            f"**Channels:** `{text_channels:,}` text · `{voice_channels:,}` voice\n"
            f"**Voice connections:** `{voice_connections}`\n\n"
            f"**Commands loaded:** `{len(self.bot.commands)}`\n"
            f"**Cogs loaded:** `{len(self.bot.cogs)}`\n\n"
            f"**Memory usage:** `{mem_mb:.1f} MB`\n"
            f"**CPU usage:** `{cpu_percent:.1f}%`\n"
            f"**Database:** {db_mode}\n\n"
            f"**Uptime:** {format_duration(uptime_secs)}\n"
            f"**Gateway latency:** `{round(self.bot.latency * 1000)}ms`"
        )
        about_view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=NEUTRAL)
        section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=self.bot.user.display_avatar.url))
        section.add_item(discord.ui.TextDisplay(f"## {e('soward')} About {config.BOT_NAME}\n{body}"))
        container.add_item(section)
        container.add_item(discord.ui.Separator())
        container.add_item(AboutButtonsRow(self.bot))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        about_view.add_item(container)
        await ctx.send(view=about_view)

    @commands.command(name="owners", aliases=["devs", "developers"], help="View the bot's owners and developers.")
    async def owners(self, ctx: commands.Context):
        e = emoji_manager.get
        body = await _build_team_body(self.bot)
        await ctx.send(view=info_layout(f"{e('soward')} Owners & Developers", body))

    @commands.command(name="userinfo", aliases=["whois", "ui"], help="Display information about a member.")
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        member = member or ctx.author

        roles = [r.mention for r in reversed(member.roles) if not r.is_default()]
        roles_text = ", ".join(roles[:10]) if roles else "None"
        if len(roles) > 10:
            roles_text += f" (+{len(roles) - 10} more)"

        badges = []
        if member.id == ctx.guild.owner_id:
            badges.append("👑 Owner")
        if member.bot:
            badges.append("🤖 Bot")
        if member.premium_since:
            badges.append("💎 Booster")
        badge_text = " · ".join(badges) if badges else "None"

        status_map = {
            discord.Status.online: "🟢 Online", discord.Status.idle: "🌙 Idle",
            discord.Status.dnd: "⛔ Do Not Disturb", discord.Status.offline: "⚫ Offline",
        }

        body = (
            f"**ID:** `{member.id}`\n"
            f"**Nickname:** {member.nick or 'None'}\n"
            f"**Status:** {status_map.get(member.status, 'Unknown')}\n"
            f"**Badges:** {badge_text}\n\n"
            f"**Created:** <t:{int(member.created_at.timestamp())}:F> (<t:{int(member.created_at.timestamp())}:R>)\n"
            f"**Joined:** <t:{int(member.joined_at.timestamp())}:F> (<t:{int(member.joined_at.timestamp())}:R>)\n\n"
            f"**Top Role:** {member.top_role.mention}\n"
            f"**Roles ({len(roles)}):** {roles_text}"
        )
        await ctx.send(view=_layout(f"{e('info')} {member}", body, thumbnail=member.display_avatar.url))

    @commands.command(name="serverinfo", aliases=["si", "guildinfo"], help="Display information about this server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        e = emoji_manager.get
        guild = ctx.guild

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        body = (
            f"**ID:** `{guild.id}`\n"
            f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"**Created:** <t:{int(guild.created_at.timestamp())}:F> (<t:{int(guild.created_at.timestamp())}:R>)\n\n"
            f"**Members:** `{guild.member_count:,}` total — `{humans:,}` humans, `{bots:,}` bots\n"
            f"**Channels:** `{text_channels}` text, `{voice_channels}` voice, `{categories}` categories\n"
            f"**Roles:** `{len(guild.roles)}`\n"
            f"**Emojis:** `{len(guild.emojis)}`\n\n"
            f"**Boosts:** `{guild.premium_subscription_count}` (Level `{guild.premium_tier}`)\n"
            f"**Verification Level:** `{guild.verification_level}`\n"
            f"**Soward Prefix:** run `prefix` to check"
        )
        await ctx.send(view=_layout(f"{e('guild')} {guild.name}", body, thumbnail=guild.icon.url if guild.icon else None))

    @commands.command(name="roleinfo", aliases=["ri"], help="Display information about a role.")
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role):
        e = emoji_manager.get
        member_count = len(role.members)
        key_perms = [
            name.replace("_", " ").title() for name, value in role.permissions
            if value and name in (
                "administrator", "manage_guild", "manage_roles", "manage_channels",
                "manage_messages", "kick_members", "ban_members", "manage_webhooks",
                "mention_everyone", "manage_nicknames", "moderate_members",
            )
        ]
        perms_text = ", ".join(key_perms) if key_perms else "None notable"

        body = (
            f"**ID:** `{role.id}`\n"
            f"**Color:** `{str(role.color)}`\n"
            f"**Position:** `{role.position}` / `{len(ctx.guild.roles)}`\n"
            f"**Created:** <t:{int(role.created_at.timestamp())}:F> (<t:{int(role.created_at.timestamp())}:R>)\n\n"
            f"**Members:** `{member_count}`\n"
            f"**Hoisted:** {'Yes' if role.hoist else 'No'}\n"
            f"**Mentionable:** {'Yes' if role.mentionable else 'No'}\n"
            f"**Managed:** {'Yes (bot/integration role)' if role.managed else 'No'}\n\n"
            f"**Key Permissions:** {perms_text}"
        )
        await ctx.send(view=_layout(f"{e('role')} {role.name}", body, color=role.color.value or NEUTRAL))

    @commands.command(name="channelinfo", aliases=["ci"], help="Display information about a channel.")
    @commands.guild_only()
    async def channelinfo(self, ctx: commands.Context, channel: Optional[discord.abc.GuildChannel] = None):
        e = emoji_manager.get
        channel = channel or ctx.channel

        type_map = {
            discord.ChannelType.text: "Text",
            discord.ChannelType.voice: "Voice",
            discord.ChannelType.category: "Category",
            discord.ChannelType.stage_voice: "Stage",
            discord.ChannelType.forum: "Forum",
            discord.ChannelType.news: "Announcement",
        }
        channel_type = type_map.get(channel.type, str(channel.type).title())

        body = (
            f"**ID:** `{channel.id}`\n"
            f"**Type:** `{channel_type}`\n"
            f"**Category:** {channel.category.name if channel.category else 'None'}\n"
            f"**Position:** `{channel.position}`\n"
            f"**Created:** <t:{int(channel.created_at.timestamp())}:F> (<t:{int(channel.created_at.timestamp())}:R>)\n"
        )

        if isinstance(channel, discord.TextChannel):
            body += (
                f"\n**Topic:** {channel.topic or 'None'}\n"
                f"**NSFW:** {'Yes' if channel.is_nsfw() else 'No'}\n"
                f"**Slowmode:** {channel.slowmode_delay}s\n"
                f"**Members with access:** `{len(channel.members)}`"
            )
        elif isinstance(channel, discord.VoiceChannel):
            body += (
                f"\n**Bitrate:** `{channel.bitrate // 1000}kbps`\n"
                f"**User limit:** `{channel.user_limit or 'Unlimited'}`\n"
                f"**Connected:** `{len(channel.members)}`"
            )

        await ctx.send(view=_layout(f"{e('channel')} #{channel.name}", body))

    @commands.command(name="avatar", aliases=["av", "pfp"], help="Show a member's avatar.")
    async def avatar(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        member = member or ctx.author
        await ctx.send(view=_layout(f"{e('info')} {member.display_name}'s Avatar", "", image=member.display_avatar.url))

    @commands.command(name="servericon", aliases=["icon"], help="Show this server's icon.")
    @commands.guild_only()
    async def servericon(self, ctx: commands.Context):
        e = emoji_manager.get
        if not ctx.guild.icon:
            return await ctx.send(view=error_layout("No Icon", "This server has no icon set."))
        await ctx.send(view=_layout(f"{e('guild')} {ctx.guild.name}'s Icon", "", image=ctx.guild.icon.url))

    @commands.command(name="prefix", help="View or change the command prefix for this server.")
    @commands.guild_only()
    async def prefix_cmd(self, ctx: commands.Context, new_prefix: Optional[str] = None):
        from utils import prefix as prefix_utils
        e = emoji_manager.get

        if new_prefix is None:
            current = await prefix_utils.get_guild_prefix(ctx.guild.id)
            return await ctx.send(view=info_layout(
                f"{e('settings')} Current Prefix",
                f"The prefix for this server is `{current}`.\nUse `{current}prefix <new prefix>` to change it.",
            ))

        if not ctx.author.guild_permissions.administrator:
            return await ctx.send(view=error_layout("Permission Denied", "Only administrators can change the prefix."))

        if not new_prefix.strip():
            return await ctx.send(view=error_layout("Invalid Prefix", "Prefix cannot be empty or whitespace."))

        if len(new_prefix) > 5:
            return await ctx.send(view=error_layout("Invalid Prefix", "Prefix must be 5 characters or fewer."))

        await prefix_utils.set_guild_prefix(ctx.guild.id, new_prefix)
        await ctx.send(view=success_layout(f"{e('check')} Prefix Updated", f"The prefix for this server is now `{new_prefix}`."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
