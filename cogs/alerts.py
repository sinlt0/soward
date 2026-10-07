import time
import uuid
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

import config
from utils import db, emoji_manager, guild_settings
from utils.alert_clients import TwitchClient, YouTubeClient
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout


YOUTUBE_VARIABLES = {
    "channel_name": "The YouTube channel's display name",
    "channel_url": "Link to the YouTube channel",
    "video_title": "Title of the new video or livestream",
    "video_url": "Link to the video or livestream",
    "video_thumbnail": "Thumbnail image URL of the video",
    "kind": "\"video\" or \"livestream\" depending on what triggered the alert",
}

TWITCH_VARIABLES = {
    "streamer_name": "The Twitch streamer's display name",
    "streamer_url": "Link to the Twitch channel",
    "stream_title": "Title of the current stream",
    "game_name": "Game/category currently being streamed",
    "viewer_count": "Current live viewer count",
    "stream_thumbnail": "Thumbnail image URL of the stream",
}

DEFAULT_YOUTUBE_MESSAGE = "**{channel_name}** just posted a new {kind}!\n{video_title}\n{video_url}"
DEFAULT_TWITCH_MESSAGE = "**{streamer_name}** just went live!\n{stream_title}\n**Playing:** {game_name}\n{streamer_url}"


def _layout(title: str, body: str, *, color: int = NEUTRAL, thumbnail: Optional[str] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)

    if thumbnail:
        section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=thumbnail))
        section.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
        container.add_item(section)
    else:
        container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))

    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def _substitute(template: str, variables: dict) -> str:
    msg = template
    for key, value in variables.items():
        msg = msg.replace(f"{{{key}}}", str(value))
    return msg


def _variables_body(platform: str) -> str:
    var_set = YOUTUBE_VARIABLES if platform == "youtube" else TWITCH_VARIABLES
    lines = [f"`{{{k}}}` — {v}" for k, v in var_set.items()]
    return "\n".join(lines)


class MessageEditModal(discord.ui.Modal, title="Edit Alert Message"):
    def __init__(self, platform: str, current: str, on_saved):
        super().__init__()
        self.platform = platform
        self.on_saved = on_saved
        self.message_input = discord.ui.TextInput(
            label="Message template",
            style=discord.TextStyle.paragraph,
            default=current,
            max_length=1500,
            required=True,
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_saved(interaction, self.message_input.value)


class VariablesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Variables", style=discord.ButtonStyle.secondary, custom_id="alerts:menu:variables")

    async def callback(self, interaction: discord.Interaction):
        e = emoji_manager.get
        body = (
            f"**YouTube variables:**\n{_variables_body('youtube')}\n\n"
            f"**Twitch variables:**\n{_variables_body('twitch')}\n\n"
            "-# Use these inside `alerts message` or the default message editor."
        )
        await interaction.response.send_message(view=info_layout(f"{e('info')} Available Variables", body), ephemeral=True)


class ListButton(discord.ui.Button):
    def __init__(self, cog: "Alerts"):
        super().__init__(label="List", style=discord.ButtonStyle.secondary, custom_id="alerts:menu:list")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        e = emoji_manager.get
        subs = await self.cog._get_subscriptions(interaction.guild.id)
        if not subs:
            return await interaction.response.send_message(
                view=info_layout(f"{e('info')} Alerts", "No subscriptions configured yet."), ephemeral=True
            )

        lines = []
        for sub in subs:
            platform_label = "YouTube" if sub["platform"] == "youtube" else "Twitch"
            lines.append(
                f"`{sub['subscription_id']}` **{platform_label}** — {sub['target_name'] or sub['target_id']}\n"
                f"-# → <#{sub['announce_channel_id']}>"
                + (f" · pings <@&{sub['ping_role_id']}>" if sub["ping_role_id"] else "")
            )
        await interaction.response.send_message(
            view=info_layout(f"{e('info')} Subscriptions ({len(subs)})", "\n\n".join(lines)), ephemeral=True
        )


class EditDefaultMessageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit Default Message", style=discord.ButtonStyle.secondary, custom_id="alerts:menu:editdefault")

    async def callback(self, interaction: discord.Interaction):
        e = emoji_manager.get
        select = discord.ui.Select(
            placeholder="Which platform's default message?",
            options=[
                discord.SelectOption(label="YouTube", value="youtube"),
                discord.SelectOption(label="Twitch", value="twitch"),
            ],
        )

        async def on_select(select_interaction: discord.Interaction):
            platform = select_interaction.data["values"][0]
            current = await guild_settings.get(
                interaction.guild.id, f"alerts_default_message_{platform}",
                DEFAULT_YOUTUBE_MESSAGE if platform == "youtube" else DEFAULT_TWITCH_MESSAGE,
            )

            async def on_saved(modal_interaction: discord.Interaction, new_message: str):
                await guild_settings.set(interaction.guild.id, f"alerts_default_message_{platform}", new_message)
                preview_vars = {k: f"[{k}]" for k in (YOUTUBE_VARIABLES if platform == "youtube" else TWITCH_VARIABLES)}
                preview = _substitute(new_message, preview_vars)
                await modal_interaction.response.send_message(
                    view=success_layout(
                        f"{e('check')} Default Message Updated",
                        f"**Preview:**\n{preview}",
                    ),
                    ephemeral=True,
                )

            modal = MessageEditModal(platform, current, on_saved)
            await select_interaction.response.send_modal(modal)

        select.callback = on_select
        temp_view = discord.ui.View(timeout=60)
        temp_view.add_item(select)
        await interaction.response.send_message(
            content="Choose which platform's default message to edit:", view=temp_view, ephemeral=True
        )


class PlatformSetupSelect(discord.ui.Select):
    def __init__(self, cog: "Alerts"):
        super().__init__(
            placeholder="Set up a new alert...",
            options=[
                discord.SelectOption(label="YouTube", value="youtube", description="New video uploads and livestreams"),
                discord.SelectOption(label="Twitch", value="twitch", description="Live stream notifications"),
            ],
            custom_id="alerts:menu:platform_select",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        platform = self.values[0]
        count = await db.raw_fetchone(
            "SELECT COUNT(*) as c FROM alert_subscriptions WHERE guild_id=? AND platform=?",
            (interaction.guild.id, platform),
        )
        if count and count["c"] >= config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM:
            e = emoji_manager.get
            return await interaction.response.send_message(
                view=error_layout(
                    "Limit Reached",
                    f"This server already has {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM}/{config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} {platform.title()} subscriptions.",
                ),
                ephemeral=True,
            )

        if platform == "youtube" and not config.YOUTUBE_API_KEY:
            return await interaction.response.send_message(
                view=error_layout("Not Configured", "The bot owner has not set up a YouTube API key."), ephemeral=True
            )
        if platform == "twitch" and not (config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET):
            return await interaction.response.send_message(
                view=error_layout("Not Configured", "The bot owner has not set up Twitch API credentials."), ephemeral=True
            )

        label = "channel handle, username, or channel ID" if platform == "youtube" else "Twitch username"
        modal = SetupTargetModal(self.cog, platform, label)
        await interaction.response.send_modal(modal)


class SetupTargetModal(discord.ui.Modal, title="Set Up Alert"):
    def __init__(self, cog: "Alerts", platform: str, label_hint: str):
        super().__init__()
        self.cog = cog
        self.platform = platform
        self.target_input = discord.ui.TextInput(label=f"Enter {label_hint}", max_length=100, required=True)
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction):
        e = emoji_manager.get
        await interaction.response.defer(ephemeral=True)

        if self.platform == "youtube":
            resolved = await self.cog._youtube.resolve_channel_id(self.target_input.value.strip())
            if not resolved:
                return await interaction.followup.send(
                    view=error_layout("Not Found", f"Could not find a YouTube channel matching `{self.target_input.value}`."),
                    ephemeral=True,
                )
            target_id, target_name = resolved["channel_id"], resolved["title"]
        else:
            resolved = await self.cog._twitch.resolve_user(self.target_input.value.strip())
            if not resolved:
                return await interaction.followup.send(
                    view=error_layout("Not Found", f"Could not find a Twitch user named `{self.target_input.value}`."),
                    ephemeral=True,
                )
            target_id, target_name = resolved["login"], resolved["display_name"]

        existing = await db.raw_fetchone(
            "SELECT 1 FROM alert_subscriptions WHERE guild_id=? AND platform=? AND target_id=?",
            (interaction.guild.id, self.platform, target_id),
        )
        if existing:
            return await interaction.followup.send(
                view=error_layout("Already Subscribed", f"Already subscribed to **{target_name}**."), ephemeral=True
            )

        channel_select = discord.ui.ChannelSelect(
            placeholder="Choose the announcement channel...",
            channel_types=[discord.ChannelType.text],
        )

        async def on_channel_chosen(channel_interaction: discord.Interaction):
            announce_channel = channel_select.values[0]
            subscription_id = str(uuid.uuid4())[:8].upper()

            await db.raw_execute(
                "INSERT INTO alert_subscriptions (subscription_id, guild_id, platform, target_id, target_name, announce_channel_id, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (subscription_id, interaction.guild.id, self.platform, target_id, target_name, announce_channel.id, interaction.user.id, time.time()),
            )

            if self.platform == "youtube":
                latest = await self.cog._youtube.get_latest_upload(resolved["uploads_playlist_id"])
                if latest:
                    await db.raw_execute(
                        "INSERT INTO alert_state (platform, target_id, last_video_id, updated_at) VALUES ('youtube', ?, ?, ?)"
                        " ON CONFLICT(platform, target_id) DO UPDATE SET last_video_id=excluded.last_video_id, updated_at=excluded.updated_at",
                        (target_id, latest["video_id"], time.time()),
                    )

            await channel_interaction.response.edit_message(
                content=None,
                view=success_layout(
                    f"{e('check')} Subscribed",
                    f"Now watching **{target_name}** ({self.platform.title()}).\n"
                    f"Alerts post in {announce_channel.mention}.\n\n"
                    f"**Subscription ID:** `{subscription_id}`\n"
                    "-# Use `alerts message <id> <text>` to customize this alert's message,"
                    " or `alerts role <id> @role` to add a ping.",
                ),
            )

        channel_select.callback = on_channel_chosen
        temp_view = discord.ui.View(timeout=120)
        temp_view.add_item(channel_select)
        await interaction.followup.send(content=f"Found **{target_name}** — choose where alerts should post:", view=temp_view, ephemeral=True)


class AlertsMenuView(discord.ui.LayoutView):
    def __init__(self, cog: "Alerts"):
        super().__init__(timeout=300)
        e = emoji_manager.get

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('info')} Stream & Upload Alerts\n"
            "Get notified when a YouTube channel uploads/goes live, or a Twitch streamer starts streaming.\n\n"
            f"-# Up to {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} YouTube + {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} Twitch subscriptions per server."
        ))
        container.add_item(discord.ui.Separator())

        button_row = discord.ui.ActionRow(VariablesButton(), ListButton(cog), EditDefaultMessageButton())
        container.add_item(button_row)
        container.add_item(discord.ui.Separator())

        select_row = discord.ui.ActionRow(PlatformSetupSelect(cog))
        container.add_item(select_row)
        container.add_item(discord.ui.Separator())

        for item in footer_block():
            container.add_item(item)
        self.add_item(container)


class Alerts(commands.Cog):
    category = "Engagement"
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._youtube: Optional[YouTubeClient] = None
        self._twitch: Optional[TwitchClient] = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession()
        self._youtube = YouTubeClient(self._session)
        self._twitch = TwitchClient(self._session)
        self.poll_youtube.start()
        self.poll_twitch.start()

    def cog_unload(self):
        self.poll_youtube.cancel()
        self.poll_twitch.cancel()
        if self._session:
            self.bot.loop.create_task(self._session.close())

    async def _get_subscriptions(self, guild_id: int, platform: Optional[str] = None) -> list:
        if platform:
            return await db.raw_fetch(
                "SELECT * FROM alert_subscriptions WHERE guild_id=? AND platform=?", (guild_id, platform)
            )
        return await db.raw_fetch("SELECT * FROM alert_subscriptions WHERE guild_id=?", (guild_id,))

    async def _build_message(self, sub: dict, variables: dict) -> str:
        if sub["custom_message"]:
            template = sub["custom_message"]
        else:
            template = await guild_settings.get(
                sub["guild_id"], f"alerts_default_message_{sub['platform']}",
                DEFAULT_YOUTUBE_MESSAGE if sub["platform"] == "youtube" else DEFAULT_TWITCH_MESSAGE,
            )

        msg = _substitute(template, variables)
        if sub["ping_role_id"]:
            msg = f"<@&{sub['ping_role_id']}> {msg}"
        return msg

    async def _already_sent(self, subscription_id: str, content_id: str) -> bool:
        row = await db.raw_fetchone(
            "SELECT 1 FROM alert_sent_log WHERE subscription_id=? AND content_id=?", (subscription_id, content_id)
        )
        return row is not None

    async def _mark_sent(self, subscription_id: str, content_id: str):
        await db.raw_execute(
            "INSERT OR IGNORE INTO alert_sent_log (subscription_id, content_id) VALUES (?, ?)",
            (subscription_id, content_id),
        )

    async def _announce(self, sub: dict, view: discord.ui.LayoutView, plain_message: str):
        guild = self.bot.get_guild(sub["guild_id"])
        if not guild:
            return
        channel = guild.get_channel(sub["announce_channel_id"])
        if not channel:
            return
        try:
            await channel.send(
                content=plain_message if sub["ping_role_id"] else None,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=config.ALERT_POLL_INTERVAL)
    async def poll_youtube(self):
        if not config.YOUTUBE_API_KEY:
            return

        subs = await db.raw_fetch("SELECT * FROM alert_subscriptions WHERE platform='youtube'")
        if not subs:
            return

        channels: dict[str, list] = {}
        for sub in subs:
            channels.setdefault(sub["target_id"], []).append(sub)

        for channel_id, channel_subs in channels.items():
            try:
                state = await db.raw_fetchone(
                    "SELECT * FROM alert_state WHERE platform='youtube' AND target_id=?", (channel_id,)
                )
                resolved = await self._youtube.resolve_channel_id(channel_id)
                if not resolved:
                    continue

                latest = await self._youtube.get_latest_upload(resolved["uploads_playlist_id"])
                if not latest:
                    continue

                is_first_check = state is None
                last_video_id = state["last_video_id"] if state else None

                if not is_first_check and latest["video_id"] != last_video_id:
                    is_live_video = await self._youtube.is_live(latest["video_id"])
                    kind = "live" if is_live_video else "upload"

                    for sub in channel_subs:
                        enabled = sub["live_enabled"] if kind == "live" else sub["upload_enabled"]
                        if not enabled:
                            continue
                        if await self._already_sent(sub["subscription_id"], latest["video_id"]):
                            continue

                        variables = {
                            "channel_name": resolved["title"],
                            "channel_url": f"https://www.youtube.com/channel/{resolved['channel_id']}",
                            "video_title": latest["title"],
                            "video_url": latest["url"],
                            "video_thumbnail": latest["thumbnail"],
                            "kind": "livestream" if kind == "live" else "video",
                        }
                        plain = await self._build_message(dict(sub), variables)
                        title_prefix = "New Livestream" if kind == "live" else "New Upload"
                        view = _layout(
                            f"{title_prefix} — {resolved['title']}",
                            f"{latest['title']}\n\n{latest['url']}",
                            color=SUCCESS,
                            thumbnail=latest["thumbnail"],
                        )
                        await self._announce(dict(sub), view, plain)
                        await self._mark_sent(sub["subscription_id"], latest["video_id"])

                await db.raw_execute(
                    "INSERT INTO alert_state (platform, target_id, last_video_id, updated_at) VALUES ('youtube', ?, ?, ?)"
                    " ON CONFLICT(platform, target_id) DO UPDATE SET last_video_id=excluded.last_video_id, updated_at=excluded.updated_at",
                    (channel_id, latest["video_id"], time.time()),
                )
            except Exception:
                continue

    @poll_youtube.before_loop
    async def _before_poll_youtube(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=config.ALERT_POLL_INTERVAL)
    async def poll_twitch(self):
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return

        subs = await db.raw_fetch("SELECT * FROM alert_subscriptions WHERE platform='twitch'")
        if not subs:
            return

        logins_by_sub: dict[str, list] = {}
        for sub in subs:
            logins_by_sub.setdefault(sub["target_id"].lower(), []).append(sub)

        try:
            live_streams = await self._twitch.get_streams(list(logins_by_sub.keys()))
        except Exception:
            return

        for login, sub_list in logins_by_sub.items():
            state = await db.raw_fetchone(
                "SELECT * FROM alert_state WHERE platform='twitch' AND target_id=?", (login,)
            )
            was_live = bool(state["is_live"]) if state else False
            stream = live_streams.get(login)

            if stream and not was_live:
                for sub in sub_list:
                    if not sub["live_enabled"]:
                        continue
                    if await self._already_sent(sub["subscription_id"], stream["stream_id"]):
                        continue

                    stream_url = f"https://twitch.tv/{login}"
                    variables = {
                        "streamer_name": sub["target_name"] or login,
                        "streamer_url": stream_url,
                        "stream_title": stream["title"],
                        "game_name": stream["game_name"] or "N/A",
                        "viewer_count": f"{stream['viewer_count']:,}",
                        "stream_thumbnail": stream["thumbnail"],
                    }
                    plain = await self._build_message(dict(sub), variables)
                    view = _layout(
                        f"Now Live — {sub['target_name'] or login}",
                        f"{stream['title']}\n**Playing:** {stream['game_name'] or 'N/A'}\n**Viewers:** {stream['viewer_count']:,}\n\n{stream_url}",
                        color=SUCCESS,
                        thumbnail=stream["thumbnail"],
                    )
                    await self._announce(dict(sub), view, plain)
                    await self._mark_sent(sub["subscription_id"], stream["stream_id"])

            await db.raw_execute(
                "INSERT INTO alert_state (platform, target_id, last_live_stream_id, is_live, updated_at) VALUES ('twitch', ?, ?, ?, ?)"
                " ON CONFLICT(platform, target_id) DO UPDATE SET last_live_stream_id=excluded.last_live_stream_id,"
                " is_live=excluded.is_live, updated_at=excluded.updated_at",
                (login, stream["stream_id"] if stream else None, int(stream is not None), time.time()),
            )

    @poll_twitch.before_loop
    async def _before_poll_twitch(self):
        await self.bot.wait_until_ready()

    @commands.group(name="alerts", invoke_without_command=True, help="Open the interactive alerts menu, or use subcommands directly.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def alerts_group(self, ctx: commands.Context):
        await ctx.send(view=AlertsMenuView(self))

    @alerts_group.group(name="youtube", aliases=["yt"], invoke_without_command=True, help="Manage YouTube upload/live alerts.")
    @has_guild_permission("manage_guild")
    async def alerts_youtube(self, ctx: commands.Context):
        await ctx.send(view=info_layout("YouTube Alerts", "Use `alerts youtube add <channel> #channel` to subscribe, or run bare `alerts` for the interactive menu."))

    @alerts_youtube.command(name="add", help="Subscribe to a YouTube channel. Usage: alerts youtube add <channel handle or ID> #channel")
    @has_guild_permission("manage_guild")
    @commands.bot_has_permissions(embed_links=True)
    async def yt_add(self, ctx: commands.Context, channel_ref: str, announce_channel: discord.TextChannel):
        e = emoji_manager.get
        if not config.YOUTUBE_API_KEY:
            return await ctx.send(view=error_layout("Not Configured", "The bot owner has not set up a YouTube API key."))

        count = await db.raw_fetchone(
            "SELECT COUNT(*) as c FROM alert_subscriptions WHERE guild_id=? AND platform='youtube'", (ctx.guild.id,)
        )
        if count and count["c"] >= config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} YouTube subscriptions per server."))

        resolved = await self._youtube.resolve_channel_id(channel_ref)
        if not resolved:
            return await ctx.send(view=error_layout("Not Found", f"Could not find a YouTube channel matching `{channel_ref}`."))

        existing = await db.raw_fetchone(
            "SELECT 1 FROM alert_subscriptions WHERE guild_id=? AND platform='youtube' AND target_id=?",
            (ctx.guild.id, resolved["channel_id"]),
        )
        if existing:
            return await ctx.send(view=error_layout("Already Subscribed", f"Already subscribed to **{resolved['title']}**."))

        subscription_id = str(uuid.uuid4())[:8].upper()
        await db.raw_execute(
            "INSERT INTO alert_subscriptions (subscription_id, guild_id, platform, target_id, target_name, announce_channel_id, created_by, created_at)"
            " VALUES (?, ?, 'youtube', ?, ?, ?, ?, ?)",
            (subscription_id, ctx.guild.id, resolved["channel_id"], resolved["title"], announce_channel.id, ctx.author.id, time.time()),
        )

        latest = await self._youtube.get_latest_upload(resolved["uploads_playlist_id"])
        if latest:
            await db.raw_execute(
                "INSERT INTO alert_state (platform, target_id, last_video_id, updated_at) VALUES ('youtube', ?, ?, ?)"
                " ON CONFLICT(platform, target_id) DO UPDATE SET last_video_id=excluded.last_video_id, updated_at=excluded.updated_at",
                (resolved["channel_id"], latest["video_id"], time.time()),
            )

        await ctx.send(view=success_layout(
            f"{e('check')} Subscribed",
            f"Now watching **{resolved['title']}** for new uploads and livestreams.\n"
            f"Alerts will post in {announce_channel.mention}.\n\n**Subscription ID:** `{subscription_id}`",
        ))

    @alerts_youtube.command(name="remove", help="Unsubscribe from a YouTube channel by subscription ID.")
    @has_guild_permission("manage_guild")
    async def yt_remove(self, ctx: commands.Context, subscription_id: str):
        await self._remove_subscription(ctx, subscription_id.upper())

    @alerts_group.group(name="twitch", invoke_without_command=True, help="Manage Twitch live alerts.")
    @has_guild_permission("manage_guild")
    async def alerts_twitch(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Twitch Alerts", "Use `alerts twitch add <username> #channel` to subscribe, or run bare `alerts` for the interactive menu."))

    @alerts_twitch.command(name="add", help="Subscribe to a Twitch streamer. Usage: alerts twitch add <username> #channel")
    @has_guild_permission("manage_guild")
    @commands.bot_has_permissions(embed_links=True)
    async def tw_add(self, ctx: commands.Context, username: str, announce_channel: discord.TextChannel):
        e = emoji_manager.get
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return await ctx.send(view=error_layout("Not Configured", "The bot owner has not set up Twitch API credentials."))

        count = await db.raw_fetchone(
            "SELECT COUNT(*) as c FROM alert_subscriptions WHERE guild_id=? AND platform='twitch'", (ctx.guild.id,)
        )
        if count and count["c"] >= config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} Twitch subscriptions per server."))

        resolved = await self._twitch.resolve_user(username)
        if not resolved:
            return await ctx.send(view=error_layout("Not Found", f"Could not find a Twitch user named `{username}`."))

        existing = await db.raw_fetchone(
            "SELECT 1 FROM alert_subscriptions WHERE guild_id=? AND platform='twitch' AND target_id=?",
            (ctx.guild.id, resolved["login"]),
        )
        if existing:
            return await ctx.send(view=error_layout("Already Subscribed", f"Already subscribed to **{resolved['display_name']}**."))

        subscription_id = str(uuid.uuid4())[:8].upper()
        await db.raw_execute(
            "INSERT INTO alert_subscriptions (subscription_id, guild_id, platform, target_id, target_name, announce_channel_id, created_by, created_at)"
            " VALUES (?, ?, 'twitch', ?, ?, ?, ?, ?)",
            (subscription_id, ctx.guild.id, resolved["login"], resolved["display_name"], announce_channel.id, ctx.author.id, time.time()),
        )
        await ctx.send(view=success_layout(
            f"{e('check')} Subscribed",
            f"Now watching **{resolved['display_name']}** for live streams.\n"
            f"Alerts will post in {announce_channel.mention}.\n\n**Subscription ID:** `{subscription_id}`",
        ))

    @alerts_twitch.command(name="remove", help="Unsubscribe from a Twitch streamer by subscription ID.")
    @has_guild_permission("manage_guild")
    async def tw_remove(self, ctx: commands.Context, subscription_id: str):
        await self._remove_subscription(ctx, subscription_id.upper())

    async def _remove_subscription(self, ctx: commands.Context, subscription_id: str):
        e = emoji_manager.get
        row = await db.raw_fetchone(
            "SELECT * FROM alert_subscriptions WHERE subscription_id=? AND guild_id=?", (subscription_id, ctx.guild.id)
        )
        if not row:
            return await ctx.send(view=error_layout("Not Found", f"No subscription with ID `{subscription_id}` in this server."))

        await db.raw_execute("DELETE FROM alert_subscriptions WHERE subscription_id=?", (subscription_id,))
        await ctx.send(view=success_layout(f"{e('check')} Unsubscribed", f"Removed alerts for **{row['target_name'] or row['target_id']}**."))

    @alerts_group.command(name="list", help="List all alert subscriptions with their IDs.")
    @has_guild_permission("manage_guild")
    async def alerts_list(self, ctx: commands.Context):
        e = emoji_manager.get
        subs = await self._get_subscriptions(ctx.guild.id)
        if not subs:
            return await ctx.send(view=info_layout(f"{e('info')} Subscriptions", "No subscriptions configured."))

        lines = [
            f"`{s['subscription_id']}` — **{s['platform'].title()}** · {s['target_name'] or s['target_id']} → <#{s['announce_channel_id']}>"
            for s in subs
        ]
        await ctx.send(view=info_layout(f"{e('info')} Subscriptions ({len(subs)})", "\n".join(lines)))

    @alerts_group.command(name="variables", aliases=["vars"], help="Show all available message template variables.")
    async def alerts_variables(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            f"**YouTube variables:**\n{_variables_body('youtube')}\n\n"
            f"**Twitch variables:**\n{_variables_body('twitch')}"
        )
        await ctx.send(view=info_layout(f"{e('info')} Available Variables", body))

    @alerts_group.command(name="role", help="Set a role to ping for a subscription. Usage: alerts role <subscription_id> [@role]")
    @has_guild_permission("manage_guild")
    async def alerts_role(self, ctx: commands.Context, subscription_id: str, role: Optional[discord.Role] = None):
        e = emoji_manager.get
        subscription_id = subscription_id.upper()
        row = await db.raw_fetchone(
            "SELECT 1 FROM alert_subscriptions WHERE subscription_id=? AND guild_id=?", (subscription_id, ctx.guild.id)
        )
        if not row:
            return await ctx.send(view=error_layout("Not Found", f"No subscription with ID `{subscription_id}` in this server."))

        await db.raw_execute(
            "UPDATE alert_subscriptions SET ping_role_id=? WHERE subscription_id=?",
            (role.id if role else None, subscription_id),
        )
        if role:
            await ctx.send(view=success_layout(f"{e('check')} Ping Role Set", f"{role.mention} will be pinged for this subscription."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Ping Role Removed", "No role will be pinged for this subscription."))

    @alerts_group.command(name="message", help="Set a custom alert message for one subscription. Usage: alerts message <subscription_id> <message>")
    @has_guild_permission("manage_guild")
    async def alerts_message(self, ctx: commands.Context, subscription_id: str, *, message: str):
        e = emoji_manager.get
        subscription_id = subscription_id.upper()
        row = await db.raw_fetchone(
            "SELECT * FROM alert_subscriptions WHERE subscription_id=? AND guild_id=?", (subscription_id, ctx.guild.id)
        )
        if not row:
            return await ctx.send(view=error_layout("Not Found", f"No subscription with ID `{subscription_id}` in this server."))

        await db.raw_execute(
            "UPDATE alert_subscriptions SET custom_message=? WHERE subscription_id=?", (message, subscription_id)
        )

        var_set = YOUTUBE_VARIABLES if row["platform"] == "youtube" else TWITCH_VARIABLES
        preview_vars = {k: f"[{k}]" for k in var_set}
        preview = _substitute(message, preview_vars)
        await ctx.send(view=success_layout(
            f"{e('check')} Custom Message Set",
            f"**Preview:**\n{preview}\n\n-# Use `alerts variables` to see all placeholders for {row['platform'].title()}.",
        ))

    @alerts_group.command(name="toggle", help="Toggle live or upload notifications for a subscription. Usage: alerts toggle <subscription_id> <live|upload>")
    @has_guild_permission("manage_guild")
    async def alerts_toggle(self, ctx: commands.Context, subscription_id: str, kind: str):
        e = emoji_manager.get
        subscription_id = subscription_id.upper()
        kind = kind.lower()
        if kind not in ("live", "upload"):
            return await ctx.send(view=error_layout("Invalid", "Use `live` or `upload`."))

        row = await db.raw_fetchone(
            "SELECT * FROM alert_subscriptions WHERE subscription_id=? AND guild_id=?", (subscription_id, ctx.guild.id)
        )
        if not row:
            return await ctx.send(view=error_layout("Not Found", f"No subscription with ID `{subscription_id}` in this server."))

        column = "live_enabled" if kind == "live" else "upload_enabled"
        new_value = 0 if row[column] else 1
        await db.raw_execute(f"UPDATE alert_subscriptions SET {column}=? WHERE subscription_id=?", (new_value, subscription_id))
        state = "enabled" if new_value else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Updated", f"`{kind}` alerts {state} for this subscription."))

    @alerts_group.command(name="clear", help="Remove all alert subscriptions for this server.")
    @has_guild_permission("manage_guild")
    async def alerts_clear(self, ctx: commands.Context):
        e = emoji_manager.get
        subs = await self._get_subscriptions(ctx.guild.id)
        if not subs:
            return await ctx.send(view=error_layout("Nothing To Clear", "No subscriptions configured."))

        confirm = ConfirmLayout(
            "Confirm Clear",
            f"Remove all **{len(subs)}** alert subscription(s) for this server?",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Subscriptions were not cleared."))

        await db.raw_execute("DELETE FROM alert_subscriptions WHERE guild_id=?", (ctx.guild.id,))
        await msg.edit(view=success_layout(f"{e('check')} Cleared", f"Removed **{len(subs)}** subscription(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Alerts(bot))
