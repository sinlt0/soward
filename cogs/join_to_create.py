import asyncio
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import db, emoji_manager, guild_settings, premium_limits
from utils.checks import has_guild_permission
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block, info_layout, success_layout


INTERFACE_IMAGE = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQdAl0LJgl_RjGtj4_7Gt9LxJ54cNX2jZb4ZFoz6h683A&s"
INTERFACE_CHANNEL_NAME = "voice-interface"
PICK_ACTIONS = ("permit", "block", "unblock", "kick", "mute", "unmute", "transfer")
MODAL_ACTIONS = ("rename", "limit")
REGIONS = (
    ("Automatic", "auto"), ("Brazil", "brazil"), ("Hong Kong", "hongkong"), ("India", "india"), ("Japan", "japan"), ("Rotterdam", "rotterdam"),
    ("Singapore", "singapore"), ("South Africa", "southafrica"), ("Sydney", "sydney"), ("US Central", "us-central"), ("US East", "us-east"),
    ("US South", "us-south"), ("US West", "us-west"),
)
INTERFACE_MENUS = (
    ("channel", "Channel settings", (
        ("Lock", "lock", "Stop new members from joining"), ("Unlock", "unlock", "Let everyone join again"),
        ("Hide", "hide", "Hide the channel from everyone else"), ("Unhide", "unhide", "Show the channel again"),
        ("Rename", "rename", "Change the channel name"), ("Reset to defaults", "reset", "Restore name, limit, quality, region and access"),
        ("Claim", "claim", "Take over a channel whose owner left"), ("Delete", "delete", "Delete your channel"))),
    ("members", "Member management", (
        ("Permit", "permit", "Let a member join even when locked"), ("Block", "block", "Block a member from the channel"),
        ("Unblock", "unblock", "Let a blocked member join again"), ("Kick", "kick", "Remove a member from the channel"),
        ("Mute", "mute", "Stop a member from speaking"), ("Unmute", "unmute", "Let a member speak again"),
        ("Transfer ownership", "transfer", "Give the channel to someone in it"))),
    ("limits", "Limits and quality", (
        ("Set user limit", "limit", "Type a limit from 0 to 99"), ("Increase limit", "limit_up", "Add one slot"),
        ("Decrease limit", "limit_down", "Remove one slot"), ("Remove user limit", "limit_off", "Allow any number of members"),
        ("Bitrate 64 kbps", "bitrate:64", "Standard audio"), ("Bitrate 96 kbps", "bitrate:96", "Better audio"),
        ("Bitrate 128 kbps", "bitrate:128", "High audio"), ("Bitrate maximum", "bitrate:max", "The highest this server allows"),
        ("Video quality auto", "video:auto", "Let Discord choose"), ("Video quality 720p", "video:full", "Force 720p video"))),
    ("region", "Voice region", tuple((label, f"region:{value}", "Set the voice server region") for label, value in REGIONS)),
)


class JtcError(Exception):
    pass


def _emoji(key: str) -> Optional[str]:
    return emoji_manager.get(key) or None


def _clean_name(value: str) -> str:
    value = " ".join(value.replace("\n", " ").split())
    return value[:100].strip() or "Voice"


def _bitrate_ok(guild: discord.Guild, kbps: int) -> Optional[int]:
    if kbps <= 0:
        return None
    return min(kbps * 1000, guild.bitrate_limit)


async def get_hub(channel_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM jtc_hubs WHERE channel_id=?", (channel_id,))
    return dict(row) if row else None


async def get_temp(channel_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM jtc_channels WHERE channel_id=?", (channel_id,))
    return dict(row) if row else None


async def get_prefs(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM jtc_prefs WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return dict(row) if row else None


async def save_pref(guild_id: int, user_id: int, **fields) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO jtc_prefs (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE jtc_prefs SET {column}=? WHERE guild_id=? AND user_id=?", (value, guild_id, user_id))


async def hub_limit(guild_id: int) -> int:
    return await premium_limits.get(guild_id, "jtc_hubs")


def can_control(member: discord.Member, temp: dict) -> bool:
    return member.id == temp["owner_id"] or member.id in config.ALL_PRIVILEGED_IDS or member.guild_permissions.manage_channels


def humans(channel: discord.VoiceChannel) -> list[discord.Member]:
    return [m for m in channel.members if not m.bot]


async def _set_owner(channel: discord.VoiceChannel, temp: dict, new_owner: discord.Member) -> None:
    old = channel.guild.get_member(temp["owner_id"])
    await db.raw_execute("UPDATE jtc_channels SET owner_id=? WHERE channel_id=?", (new_owner.id, channel.id))
    temp["owner_id"] = new_owner.id
    try:
        await channel.set_permissions(new_owner, view_channel=True, connect=True, reason="Join to Create owner changed")
        if old is not None and old.id != new_owner.id and not old.guild_permissions.administrator:
            await channel.set_permissions(old, overwrite=None, reason="Join to Create owner changed")
    except discord.HTTPException:
        pass


async def perform(action: str, channel: discord.VoiceChannel, actor: discord.Member, temp: dict,
                  target: Optional[discord.Member] = None, value: Optional[str] = None) -> str:
    guild = channel.guild
    everyone = guild.default_role
    if action in ("lock", "unlock"):
        overwrite = channel.overwrites_for(everyone)
        overwrite.connect = False if action == "lock" else None
        await channel.set_permissions(everyone, overwrite=overwrite, reason="Join to Create")
        if actor.id == temp["owner_id"]:
            await save_pref(guild.id, actor.id, locked=1 if action == "lock" else 0)
        return "The channel is now locked. Nobody new can join unless you permit them." if action == "lock" else "The channel is unlocked."
    if action in ("hide", "unhide"):
        overwrite = channel.overwrites_for(everyone)
        overwrite.view_channel = False if action == "hide" else None
        await channel.set_permissions(everyone, overwrite=overwrite, reason="Join to Create")
        return "The channel is hidden from everyone except permitted members." if action == "hide" else "The channel is visible again."
    if action == "limit":
        try:
            number = int(str(value).strip())
        except ValueError:
            raise JtcError("Enter a number between 0 and 99. Use 0 for no limit.")
        if not 0 <= number <= 99:
            raise JtcError("The limit must be between 0 and 99. Use 0 for no limit.")
        await channel.edit(user_limit=number, reason="Join to Create")
        if actor.id == temp["owner_id"]:
            await save_pref(guild.id, actor.id, user_limit=number)
        return f"The user limit is now {number}." if number else "The user limit was removed."
    if action == "rename":
        name = _clean_name(str(value or ""))
        await channel.edit(name=name, reason="Join to Create")
        if actor.id == temp["owner_id"]:
            await save_pref(guild.id, actor.id, name=name)
        return f"The channel is now called **{name}**."
    if action in ("limit_up", "limit_down", "limit_off"):
        current = channel.user_limit or 0
        number = 0 if action == "limit_off" else min(99, current + 1) if action == "limit_up" else max(0, current - 1)
        await channel.edit(user_limit=number, reason="Join to Create")
        if actor.id == temp["owner_id"]:
            await save_pref(guild.id, actor.id, user_limit=number)
        return f"The user limit is now {number}." if number else "The user limit was removed."
    if action == "bitrate":
        kbps = guild.bitrate_limit // 1000 if str(value) == "max" else int(str(value))
        await channel.edit(bitrate=min(kbps * 1000, guild.bitrate_limit), reason="Join to Create")
        return f"The bitrate is now {min(kbps, guild.bitrate_limit // 1000)} kbps."
    if action == "video":
        mode = discord.VideoQualityMode.full if str(value) == "full" else discord.VideoQualityMode.auto
        await channel.edit(video_quality_mode=mode, reason="Join to Create")
        return "Video quality is now 720p." if mode is discord.VideoQualityMode.full else "Video quality is now automatic."
    if action == "region":
        region = None if str(value) == "auto" else str(value)
        await channel.edit(rtc_region=region, reason="Join to Create")
        label = next((name for name, key in REGIONS if key == str(value)), "Automatic")
        return f"The voice region is now {label}."
    if action == "reset":
        hub = await get_hub(temp["hub_id"])
        owner = guild.get_member(temp["owner_id"])
        overwrite = channel.overwrites_for(everyone)
        overwrite.connect = None
        overwrite.view_channel = None
        await channel.set_permissions(everyone, overwrite=overwrite, reason="Join to Create reset")
        count = (await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_channels WHERE hub_id=?", (temp["hub_id"],)))["n"]
        template = (hub["name_template"] if hub else None) or config.JTC_DEFAULT_NAME
        name = template.replace("{user}", owner.display_name if owner else "Voice").replace("{username}", owner.name if owner else "Voice").replace("{count}", str(count))
        default_bitrate = _bitrate_ok(guild, int(hub["bitrate"] or 0)) if hub else None
        await channel.edit(
            name=_clean_name(name), user_limit=int(hub["user_limit"] or 0) if hub else 0, bitrate=default_bitrate or min(64000, guild.bitrate_limit),
            video_quality_mode=discord.VideoQualityMode.auto, rtc_region=None, reason="Join to Create reset",
        )
        if actor.id == temp["owner_id"]:
            await save_pref(guild.id, actor.id, name=None, user_limit=None, locked=0)
        return "The channel was reset to its defaults."
    if action == "claim":
        owner = guild.get_member(temp["owner_id"])
        if owner is not None and owner in channel.members:
            raise JtcError(f"{owner.mention} is still in the channel, so it cannot be claimed.")
        if actor not in channel.members:
            raise JtcError("Join the channel first to claim it.")
        await _set_owner(channel, temp, actor)
        return "You are now the owner of this channel."
    if action == "delete":
        await db.raw_execute("DELETE FROM jtc_channels WHERE channel_id=?", (channel.id,))
        await channel.delete(reason="Join to Create owner deleted it")
        return "The channel was deleted."
    if target is None:
        raise JtcError("Choose a member.")
    if target.bot:
        raise JtcError("Choose a person, not a bot.")
    if target.id == temp["owner_id"] and action in ("kick", "block", "mute"):
        raise JtcError("You cannot do that to the channel owner.")
    if target.guild_permissions.administrator and action in ("kick", "block", "mute") and target.id != actor.id:
        raise JtcError("You cannot do that to an administrator.")
    if action == "permit":
        await channel.set_permissions(target, view_channel=True, connect=True, reason="Join to Create")
        return f"{target.mention} can now join."
    if action == "block":
        await channel.set_permissions(target, view_channel=False, connect=False, reason="Join to Create")
        if target in channel.members:
            await target.move_to(None, reason="Blocked from a Join to Create channel")
        return f"{target.mention} is blocked from this channel."
    if action == "unblock":
        await channel.set_permissions(target, overwrite=None, reason="Join to Create")
        return f"{target.mention} can join again."
    if action == "kick":
        if target not in channel.members:
            raise JtcError(f"{target.mention} is not in this channel.")
        await target.move_to(None, reason="Removed from a Join to Create channel")
        return f"{target.mention} was removed from the channel."
    if action == "mute":
        overwrite = channel.overwrites_for(target)
        overwrite.speak = False
        await channel.set_permissions(target, overwrite=overwrite, reason="Join to Create")
        return f"{target.mention} can no longer speak in this channel."
    if action == "unmute":
        overwrite = channel.overwrites_for(target)
        overwrite.speak = None
        await channel.set_permissions(target, overwrite=None if overwrite.is_empty() else overwrite, reason="Join to Create")
        return f"{target.mention} can speak again."
    if action == "transfer":
        if target not in channel.members:
            raise JtcError(f"{target.mention} must be in the channel to receive ownership.")
        await _set_owner(channel, temp, target)
        return f"{target.mention} is now the owner."
    raise JtcError("Unknown action.")


def panel_layout(owner: Optional[discord.abc.User]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    who = f"Owner: {owner.mention}\n" if owner is not None else ""
    container.add_item(discord.ui.TextDisplay(
        f"## {emoji_manager.get('volume')} Voice controls\n{who}Use the buttons to manage this channel. Only the owner can use them. "
        "If the owner leaves, press **Claim**."
    ))
    container.add_item(discord.ui.Separator())
    container.add_item(ControlRow([("Lock", "lock", "lock"), ("Unlock", "unlock", "unlock"), ("Hide", "hide", "settings"), ("Unhide", "unhide", "settings"), ("Claim", "claim", "star")]))
    container.add_item(ControlRow([("Rename", "rename", "settings"), ("Limit", "limit", "members"), ("Transfer", "transfer", "star"), ("Kick", "kick", "kick"), ("Block", "block", "ban")]))
    container.add_item(ControlRow([("Permit", "permit", "check"), ("Unblock", "unblock", "unlock"), ("Delete", "delete", "cross")]))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


class InterfaceSelect(discord.ui.Select):
    def __init__(self, key: str, placeholder: str, entries: tuple):
        super().__init__(
            custom_id=f"jtci:{key}", placeholder=placeholder,
            options=[discord.SelectOption(label=label, value=value, description=description) for label, value, description in entries],
        )

    async def callback(self, interaction: discord.Interaction):
        cog: "JoinToCreate" = interaction.client.get_cog("JoinToCreate")
        await cog.handle_interface(interaction, self.values[0])


def interface_layout() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0x5865F2)
    container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(INTERFACE_IMAGE)))
    container.add_item(discord.ui.TextDisplay(
        "## Voice Management Panel\n"
        "Use the menus below to manage your temporary voice channel. You need to be inside your channel, and only the channel owner can use these controls.\n\n"
        "**Channel settings**\nLock, unlock, hide, unhide, rename, reset, claim or delete your channel.\n\n"
        "**Member management**\nPermit, block, unblock, kick, mute, unmute a member or transfer ownership.\n\n"
        "**Limits and quality**\nSet the user limit, bitrate and video quality.\n\n"
        "**Voice region**\nPick the server region for lower latency."
    ))
    container.add_item(discord.ui.Separator())
    for key, placeholder, entries in INTERFACE_MENUS:
        container.add_item(discord.ui.ActionRow(InterfaceSelect(key, placeholder, entries)))
    view.add_item(container)
    return view


class ControlRow(discord.ui.ActionRow):
    def __init__(self, buttons: list[tuple[str, str, str]]):
        super().__init__()
        for label, action, emoji_key in buttons:
            style = discord.ButtonStyle.danger if action in ("delete", "block", "kick") else discord.ButtonStyle.secondary
            button = discord.ui.Button(label=label, style=style, custom_id=f"jtc:{action}", emoji=_emoji(emoji_key))
            button.callback = self._make(action)
            self.add_item(button)

    def _make(self, action: str):
        async def callback(interaction: discord.Interaction):
            cog: "JoinToCreate" = interaction.client.get_cog("JoinToCreate")
            await cog.handle_button(interaction, action)
        return callback


class ValueModal(discord.ui.Modal):
    def __init__(self, cog: "JoinToCreate", action: str, channel_id: int, panel: Optional[discord.Message] = None):
        super().__init__(title="Rename channel" if action == "rename" else "Set user limit")
        self.panel = panel
        self.cog = cog
        self.action = action
        self.channel_id = channel_id
        self.field = discord.ui.TextInput(
            label="New name" if action == "rename" else "Limit (0 to 99, 0 for none)", max_length=100 if action == "rename" else 2, required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.run_action(interaction, self.action, self.channel_id, value=self.field.value)
        if self.panel is not None:
            try:
                await self.panel.edit(view=interface_layout())
            except discord.HTTPException:
                pass


class PickLayout(discord.ui.LayoutView):
    def __init__(self, cog: "JoinToCreate", action: str, channel_id: int, author_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.action = action
        self.channel_id = channel_id
        self.author_id = author_id
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## Choose a member\nSelect who to {action}."))
        select = discord.ui.UserSelect(placeholder="Choose a member...")
        select.callback = self._picked
        self.select = select
        container.add_item(discord.ui.ActionRow(select))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def _picked(self, interaction: discord.Interaction):
        target = self.select.values[0]
        if not isinstance(target, discord.Member):
            target = interaction.guild.get_member(target.id)
        if target is None:
            return await interaction.response.edit_message(view=error_layout("Not found", "That person is not in this server."))
        await self.cog.run_action(interaction, self.action, self.channel_id, target=target, edit=True)


class JoinToCreate(commands.Cog):
    category = "Engagement"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldown: dict[tuple[int, int], float] = {}
        self._creating: set[tuple[int, int]] = set()
        self._interface_lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(panel_layout(None))
        self.bot.add_view(interface_layout())
        self.sweep.start()

    async def cog_unload(self):
        self.sweep.cancel()

    @tasks.loop(seconds=config.JTC_SWEEP_SECONDS)
    async def sweep(self):
        for row in await db.raw_fetch("SELECT * FROM jtc_channels"):
            row = dict(row)
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(row["channel_id"])
            if channel is None:
                await db.raw_execute("DELETE FROM jtc_channels WHERE channel_id=?", (row["channel_id"],))
                continue
            if not humans(channel) and time.time() - row["created_at"] > 20:
                await self._remove(channel)
        for guild in list(self.bot.guilds):
            if await guild_settings.get(guild.id, "jtc_interface_channel_id"):
                await self._cleanup_interface(guild)

    @sweep.before_loop
    async def _before_sweep(self):
        await self.bot.wait_until_ready()

    async def _remove(self, channel: discord.VoiceChannel):
        await db.raw_execute("DELETE FROM jtc_channels WHERE channel_id=?", (channel.id,))
        try:
            await channel.delete(reason="Join to Create channel is empty")
        except discord.HTTPException:
            pass
        await self._cleanup_interface(channel.guild)

    async def _cleanup_interface(self, guild: discord.Guild):
        async with self._interface_lock:
            if not await guild_settings.get(guild.id, "jtc_interface_auto", True):
                return
            active = await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_channels WHERE guild_id=?", (guild.id,))
            if active["n"] > 0:
                return
            channel = await self._interface_channel(guild)
            if channel is None:
                return
            try:
                await channel.delete(reason="No active Join to Create channels")
            except discord.HTTPException:
                return
            await guild_settings.delete(guild.id, "jtc_interface_channel_id")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await db.raw_execute("DELETE FROM jtc_hubs WHERE channel_id=?", (channel.id,))
        await db.raw_execute("DELETE FROM jtc_channels WHERE channel_id=?", (channel.id,))
        if await guild_settings.get(channel.guild.id, "jtc_interface_channel_id") == channel.id:
            await guild_settings.delete(channel.guild.id, "jtc_interface_channel_id")
            return
        if isinstance(channel, discord.VoiceChannel):
            await self._cleanup_interface(channel.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
            hub = await get_hub(after.channel.id)
            if hub is not None:
                await self._create(member, after.channel, hub)
        if before.channel is not None and (after.channel is None or after.channel.id != before.channel.id):
            await self._left(member, before.channel)

    async def _create(self, member: discord.Member, hub_channel: discord.VoiceChannel, hub: dict):
        guild = member.guild
        key = (guild.id, member.id)
        if key in self._creating:
            return
        existing = await db.raw_fetchone("SELECT channel_id FROM jtc_channels WHERE guild_id=? AND hub_id=? AND owner_id=?", (guild.id, hub["channel_id"], member.id))
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel is not None:
                try:
                    await member.move_to(channel)
                except discord.HTTPException:
                    pass
                return
        now = time.time()
        if now - self._cooldown.get(key, 0) < config.JTC_CREATE_COOLDOWN:
            try:
                await member.move_to(None, reason="Join to Create cooldown")
            except discord.HTTPException:
                pass
            return
        active = await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_channels WHERE guild_id=?", (guild.id,))
        if active["n"] >= config.JTC_MAX_ACTIVE_PER_GUILD:
            try:
                await member.move_to(None, reason="Too many temporary channels")
            except discord.HTTPException:
                pass
            return
        self._creating.add(key)
        self._cooldown[key] = now
        try:
            await self._build(member, hub_channel, hub)
        except discord.HTTPException:
            pass
        finally:
            self._creating.discard(key)

    async def _build(self, member: discord.Member, hub_channel: discord.VoiceChannel, hub: dict):
        guild = member.guild
        prefs = await get_prefs(guild.id, member.id)
        count = (await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_channels WHERE hub_id=?", (hub["channel_id"],)))["n"] + 1
        template = hub["name_template"] or config.JTC_DEFAULT_NAME
        name = template.replace("{user}", member.display_name).replace("{username}", member.name).replace("{count}", str(count))
        if prefs and prefs["name"]:
            name = prefs["name"]
        category = guild.get_channel(hub["category_id"]) if hub["category_id"] else hub_channel.category
        overwrites = {target: overwrite for target, overwrite in hub_channel.overwrites.items()}
        owner_ow = overwrites.get(member, discord.PermissionOverwrite())
        owner_ow.view_channel = True
        owner_ow.connect = True
        overwrites[member] = owner_ow
        me_ow = overwrites.get(guild.me, discord.PermissionOverwrite())
        me_ow.view_channel = True
        me_ow.connect = True
        me_ow.manage_channels = True
        me_ow.move_members = True
        me_ow.send_messages = True
        overwrites[guild.me] = me_ow
        if prefs and prefs["locked"]:
            everyone_ow = overwrites.get(guild.default_role, discord.PermissionOverwrite())
            everyone_ow.connect = False
            overwrites[guild.default_role] = everyone_ow
        limit = prefs["user_limit"] if prefs and prefs["user_limit"] is not None else hub["user_limit"]
        kwargs = {"category": category, "overwrites": overwrites, "user_limit": int(limit or 0), "reason": f"Join to Create for {member}"}
        bitrate = _bitrate_ok(guild, int(hub["bitrate"] or 0))
        if bitrate:
            kwargs["bitrate"] = bitrate
        channel = await guild.create_voice_channel(_clean_name(name), **kwargs)
        await db.raw_execute(
            "INSERT INTO jtc_channels (channel_id, guild_id, hub_id, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel.id, guild.id, hub["channel_id"], member.id, time.time()),
        )
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            await self._remove(channel)
            return
        if await self._ensure_interface(guild, category or hub_channel.category):
            return
        try:
            await channel.send(view=panel_layout(member), allowed_mentions=discord.AllowedMentions(users=[member]))
        except discord.HTTPException:
            pass

    async def _interface_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        channel_id = await guild_settings.get(guild.id, "jtc_interface_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _create_interface(self, guild: discord.Guild, category: Optional[discord.CategoryChannel]) -> Optional[discord.TextChannel]:
        overwrites = dict(category.overwrites) if category else {}
        everyone = overwrites.get(guild.default_role, discord.PermissionOverwrite())
        everyone.send_messages = False
        everyone.add_reactions = False
        everyone.create_public_threads = False
        everyone.create_private_threads = False
        overwrites[guild.default_role] = everyone
        me = overwrites.get(guild.me, discord.PermissionOverwrite())
        me.view_channel = True
        me.send_messages = True
        me.embed_links = True
        me.manage_messages = True
        overwrites[guild.me] = me
        try:
            channel = await guild.create_text_channel(INTERFACE_CHANNEL_NAME, category=category, overwrites=overwrites, topic="Manage your temporary voice channel with the menus below.", reason="Join to Create interface")
            await channel.send(view=interface_layout())
        except discord.HTTPException:
            return None
        await guild_settings.set(guild.id, "jtc_interface_channel_id", channel.id)
        return channel

    async def _ensure_interface(self, guild: discord.Guild, category: Optional[discord.CategoryChannel]) -> bool:
        async with self._interface_lock:
            if await self._interface_channel(guild) is not None:
                return True
            if not await guild_settings.get(guild.id, "jtc_interface_auto", True):
                return False
            return await self._create_interface(guild, category) is not None

    async def handle_interface(self, interaction: discord.Interaction, value: str):
        member = interaction.user
        action, _, extra = value.partition(":")
        voice = member.voice.channel if isinstance(member, discord.Member) and member.voice else None
        temp = await get_temp(voice.id) if isinstance(voice, discord.VoiceChannel) else None
        problem = None
        if temp is None:
            problem = ("Not in a temporary channel", "Join your own temporary voice channel first, then use the menus.")
        elif action != "claim" and not can_control(member, temp):
            problem = ("Owner only", f"Only <@{temp['owner_id']}> can use these controls.")
        if problem is not None:
            await interaction.response.edit_message(view=interface_layout())
            return await interaction.followup.send(view=error_layout(*problem), ephemeral=True)
        if action in MODAL_ACTIONS:
            return await interaction.response.send_modal(ValueModal(self, action, voice.id, interaction.message))
        await interaction.response.edit_message(view=interface_layout())
        if action in PICK_ACTIONS:
            return await interaction.followup.send(view=PickLayout(self, action, voice.id, member.id), ephemeral=True)
        try:
            view = success_layout("Done", await perform(action, voice, member, temp, None, extra or None))
        except JtcError as exc:
            view = error_layout("Not allowed", str(exc))
        except discord.HTTPException as exc:
            view = error_layout("Discord refused", str(exc)[:180])
        await interaction.followup.send(view=view, ephemeral=True)

    async def _left(self, member: discord.Member, channel: discord.VoiceChannel):
        temp = await get_temp(channel.id)
        if temp is None:
            return
        remaining = humans(channel)
        if not remaining:
            return await self._remove(channel)
        if member.id == temp["owner_id"]:
            new_owner = remaining[0]
            await _set_owner(channel, temp, new_owner)
            try:
                await channel.send(view=info_layout("New owner", f"{member.mention} left, so {new_owner.mention} is now the owner."))
            except discord.HTTPException:
                pass

    async def handle_button(self, interaction: discord.Interaction, action: str):
        channel = interaction.channel
        temp = await get_temp(channel.id) if isinstance(channel, discord.VoiceChannel) else None
        if temp is None:
            return await interaction.response.send_message(view=error_layout("Not a temporary channel", "These controls only work inside a Join to Create channel."), ephemeral=True)
        member = interaction.user
        if action != "claim" and not can_control(member, temp):
            return await interaction.response.send_message(view=error_layout("Owner only", f"Only <@{temp['owner_id']}> can use these controls."), ephemeral=True)
        if action in ("rename", "limit"):
            return await interaction.response.send_modal(ValueModal(self, action, channel.id))
        if action in ("transfer", "kick", "block", "permit", "unblock"):
            return await interaction.response.send_message(view=PickLayout(self, action, channel.id, member.id), ephemeral=True)
        await self.run_action(interaction, action, channel.id)

    async def run_action(self, interaction: discord.Interaction, action: str, channel_id: int,
                         target: Optional[discord.Member] = None, value: Optional[str] = None, edit: bool = False):
        channel = interaction.guild.get_channel(channel_id)
        temp = await get_temp(channel_id)
        if channel is None or temp is None:
            view = error_layout("Channel gone", "This temporary channel no longer exists.")
        elif action != "claim" and not can_control(interaction.user, temp):
            view = error_layout("Owner only", f"Only <@{temp['owner_id']}> can use these controls.")
        else:
            try:
                view = success_layout("Done", await perform(action, channel, interaction.user, temp, target, value))
            except JtcError as exc:
                view = error_layout("Not allowed", str(exc))
            except discord.HTTPException as exc:
                view = error_layout("Discord refused", str(exc)[:180])
        if edit:
            return await interaction.response.edit_message(view=view)
        if interaction.response.is_done():
            return await interaction.followup.send(view=view, ephemeral=True)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _own_channel(self, ctx: commands.Context) -> tuple[discord.VoiceChannel, dict]:
        voice = ctx.author.voice.channel if ctx.author.voice else None
        temp = await get_temp(voice.id) if voice else None
        if temp is None:
            raise JtcError("Join your temporary voice channel first.")
        if not can_control(ctx.author, temp):
            raise JtcError(f"Only <@{temp['owner_id']}> can control this channel.")
        return voice, temp

    async def _command(self, ctx: commands.Context, action: str, target: Optional[discord.Member] = None, value: Optional[str] = None):
        try:
            if action == "claim":
                voice = ctx.author.voice.channel if ctx.author.voice else None
                temp = await get_temp(voice.id) if voice else None
                if temp is None:
                    raise JtcError("Join a temporary voice channel first.")
            else:
                voice, temp = await self._own_channel(ctx)
            message = await perform(action, voice, ctx.author, temp, target, value)
        except JtcError as exc:
            return await ctx.send(view=error_layout("Not allowed", str(exc)))
        except discord.HTTPException as exc:
            return await ctx.send(view=error_layout("Discord refused", str(exc)[:180]))
        await ctx.send(view=success_layout("Done", message))

    @commands.group(name="voice", aliases=["tv"], invoke_without_command=True, help="Control your Join to Create voice channel.")
    @commands.guild_only()
    async def voice_group(self, ctx: commands.Context):
        body = (
            "Join a hub channel to get your own voice channel. Then use the buttons in its chat or these commands:\n\n"
            "`voice lock | unlock | hide | unhide`\n`voice rename <name>` `voice limit <0-99>`\n"
            "`voice permit | block | unblock | kick | transfer <member>`\n`voice claim` `voice panel` `voice delete`"
        )
        await ctx.send(view=info_layout("Voice channel commands", body))

    @voice_group.command(name="lock", help="Stop new members from joining.")
    async def v_lock(self, ctx: commands.Context):
        await self._command(ctx, "lock")

    @voice_group.command(name="unlock", help="Let everyone join again.")
    async def v_unlock(self, ctx: commands.Context):
        await self._command(ctx, "unlock")

    @voice_group.command(name="hide", help="Hide the channel from everyone else.")
    async def v_hide(self, ctx: commands.Context):
        await self._command(ctx, "hide")

    @voice_group.command(name="unhide", help="Show the channel again.")
    async def v_unhide(self, ctx: commands.Context):
        await self._command(ctx, "unhide")

    @voice_group.command(name="rename", help="Rename your channel. Usage: voice rename <name>")
    async def v_rename(self, ctx: commands.Context, *, name: str):
        await self._command(ctx, "rename", value=name)

    @voice_group.command(name="limit", help="Set the user limit. Usage: voice limit <0-99>")
    async def v_limit(self, ctx: commands.Context, number: int):
        await self._command(ctx, "limit", value=str(number))

    @voice_group.command(name="permit", help="Let a member join even when locked or hidden.")
    async def v_permit(self, ctx: commands.Context, member: discord.Member):
        await self._command(ctx, "permit", member)

    @voice_group.command(name="block", help="Block a member from your channel.")
    async def v_block(self, ctx: commands.Context, member: discord.Member):
        await self._command(ctx, "block", member)

    @voice_group.command(name="unblock", help="Unblock a member.")
    async def v_unblock(self, ctx: commands.Context, member: discord.Member):
        await self._command(ctx, "unblock", member)

    @voice_group.command(name="kick", help="Remove a member from your channel.")
    async def v_kick(self, ctx: commands.Context, member: discord.Member):
        await self._command(ctx, "kick", member)

    @voice_group.command(name="transfer", help="Give your channel to another member in it.")
    async def v_transfer(self, ctx: commands.Context, member: discord.Member):
        await self._command(ctx, "transfer", member)

    @voice_group.command(name="claim", help="Claim a channel whose owner left.")
    async def v_claim(self, ctx: commands.Context):
        await self._command(ctx, "claim")

    @voice_group.command(name="delete", help="Delete your channel.")
    async def v_delete(self, ctx: commands.Context):
        await self._command(ctx, "delete")

    @voice_group.command(name="panel", help="Post the control panel again.")
    async def v_panel(self, ctx: commands.Context):
        try:
            voice, temp = await self._own_channel(ctx)
        except JtcError as exc:
            return await ctx.send(view=error_layout("Not allowed", str(exc)))
        owner = ctx.guild.get_member(temp["owner_id"])
        await voice.send(view=panel_layout(owner))

    @commands.group(name="jtc", aliases=["jointocreate", "tempvoice"], invoke_without_command=True, help="Set up Join to Create voice channels.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def jtc_group(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "Members join a hub voice channel and get a private channel of their own. It is deleted when empty.\n\n"
            "`jtc setup` Create a hub and category\n"
            "`jtc add <voice channel> [category]` Use an existing channel as a hub\n"
            "`jtc remove <hub>` | `jtc list` | `jtc interface`\n"
            "`jtc name <hub> <template>` Variables: `{user}` `{username}` `{count}`\n"
            "`jtc limit <hub> <0-99>` | `jtc bitrate <hub> <kbps>` | `jtc category <hub> <category>`\n\n"
            "Members control their channel with the buttons or `voice` commands."
        )
        await ctx.send(view=info_layout(f"{e('settings')} Join to Create", body))

    @jtc_group.group(name="interface", invoke_without_command=True, help="Shared voice management panel.")
    async def jtc_interface(self, ctx: commands.Context):
        channel = await self._interface_channel(ctx.guild)
        auto = await guild_settings.get(ctx.guild.id, "jtc_interface_auto", True)
        body = (
            f"**Interface channel:** {channel.mention if channel else 'none yet'}\n"
            f"**Create automatically:** {'on' if auto else 'off'}\n\n"
            "When a member creates a temporary channel and no interface exists, Zyro creates a text channel with a voice management panel. "
            "If one already exists it is reused and the small panel inside each voice channel is skipped. When no temporary channel is active the interface channel is deleted and it is created again when the next one is made.\n\n"
            "`jtc interface create [#channel]` post the panel now, `jtc interface remove`, `jtc interface auto <on|off>`"
        )
        await ctx.send(view=info_layout("Voice interface", body))

    @jtc_interface.command(name="create", aliases=["post"], help="Create or post the voice interface. Usage: jtc interface create [#channel]")
    async def jtc_interface_create(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if channel is None:
            existing = await self._interface_channel(ctx.guild)
            if existing is not None:
                return await ctx.send(view=error_layout("Already exists", f"The interface is already in {existing.mention}."))
            hub = await db.raw_fetchone("SELECT category_id FROM jtc_hubs WHERE guild_id=? LIMIT 1", (ctx.guild.id,))
            category = ctx.guild.get_channel(hub["category_id"]) if hub and hub["category_id"] else None
            channel = await self._create_interface(ctx.guild, category if isinstance(category, discord.CategoryChannel) else None)
            if channel is None:
                return await ctx.send(view=error_layout("Can't create", "I could not create the channel. Check that I have Manage Channels."))
        else:
            try:
                await channel.send(view=interface_layout())
            except discord.HTTPException:
                return await ctx.send(view=error_layout("Can't post", f"I cannot send messages in {channel.mention}."))
            await guild_settings.set(ctx.guild.id, "jtc_interface_channel_id", channel.id)
        await ctx.send(view=success_layout("Interface ready", f"The voice management panel is in {channel.mention}."))

    @jtc_interface.command(name="remove", aliases=["delete"], help="Delete the voice interface channel.")
    async def jtc_interface_remove(self, ctx: commands.Context):
        channel = await self._interface_channel(ctx.guild)
        if channel is None:
            return await ctx.send(view=error_layout("None found", "There is no voice interface to remove."))
        try:
            await channel.delete(reason="Join to Create interface removed")
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Can't delete", "I could not delete that channel."))
        await guild_settings.delete(ctx.guild.id, "jtc_interface_channel_id")
        await ctx.send(view=success_layout("Interface removed", "The interface channel was deleted."))

    @jtc_interface.command(name="auto", help="Turn automatic interface creation on or off. Usage: jtc interface auto <on|off>")
    async def jtc_interface_auto(self, ctx: commands.Context, state: str):
        if state.lower() not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid option", "Use `on` or `off`."))
        await guild_settings.set(ctx.guild.id, "jtc_interface_auto", state.lower() == "on")
        await ctx.send(view=success_layout("Saved", f"Automatic interface creation is **{state.lower()}**."))

    async def _add_hub(self, ctx: commands.Context, channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel]) -> bool:
        if await get_hub(channel.id):
            await ctx.send(view=error_layout("Already a hub", f"{channel.mention} is already a Join to Create hub."))
            return False
        count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_hubs WHERE guild_id=?", (ctx.guild.id,))
        limit = await hub_limit(ctx.guild.id)
        if count["n"] >= limit:
            await ctx.send(view=error_layout("Hub limit reached", f"This server can have {limit} hubs. Remove one.{await premium_limits.hint(ctx.guild.id, 'jtc_hubs')}"))
            return False
        await db.raw_execute(
            "INSERT INTO jtc_hubs (channel_id, guild_id, category_id, name_template, user_limit, bitrate, created_by, created_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)",
            (channel.id, ctx.guild.id, category.id if category else None, config.JTC_DEFAULT_NAME, ctx.author.id, time.time()),
        )
        return True

    @jtc_group.command(name="setup", help="Create a Join to Create hub and category.")
    async def jtc_setup(self, ctx: commands.Context):
        me = ctx.guild.me.guild_permissions
        missing = [n for n, ok in (("Manage Channels", me.manage_channels), ("Move Members", me.move_members)) if not ok]
        if missing:
            return await ctx.send(view=error_layout("Missing permissions", "Zyro needs: " + ", ".join(missing) + "."))
        count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_hubs WHERE guild_id=?", (ctx.guild.id,))
        if count["n"] >= await hub_limit(ctx.guild.id):
            return await ctx.send(view=error_layout("Hub limit reached", "Remove a hub first or get Premium for more."))
        category = await ctx.guild.create_category(config.JTC_CATEGORY_NAME, reason="Join to Create setup")
        hub = await ctx.guild.create_voice_channel(
            config.JTC_HUB_NAME, category=category,
            overwrites={ctx.guild.default_role: discord.PermissionOverwrite(connect=True, speak=False)}, reason="Join to Create setup",
        )
        if not await self._add_hub(ctx, hub, category):
            return
        await ctx.send(view=success_layout("Join to Create is ready", f"Join {hub.mention} to get your own channel in **{category.name}**. Change the name with `jtc name {hub.id} <template>`."))

    @jtc_group.command(name="add", help="Use an existing voice channel as a hub. Usage: jtc add <voice channel> [category]")
    async def jtc_add(self, ctx: commands.Context, channel: discord.VoiceChannel, category: Optional[discord.CategoryChannel] = None):
        if await self._add_hub(ctx, channel, category):
            await ctx.send(view=success_layout("Hub added", f"{channel.mention} is now a Join to Create hub."))

    @jtc_group.command(name="remove", aliases=["delete"], help="Stop using a channel as a hub.")
    async def jtc_remove(self, ctx: commands.Context, channel: discord.VoiceChannel):
        hub = await get_hub(channel.id)
        if not hub or hub["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not a hub", f"{channel.mention} is not a hub."))
        await db.raw_execute("DELETE FROM jtc_hubs WHERE channel_id=?", (channel.id,))
        await ctx.send(view=success_layout("Hub removed", f"{channel.mention} is a normal channel again. Existing temporary channels stay until empty."))

    @jtc_group.command(name="list", aliases=["info"], help="Show your hubs.")
    async def jtc_list(self, ctx: commands.Context):
        rows = await db.raw_fetch("SELECT * FROM jtc_hubs WHERE guild_id=?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=info_layout("Join to Create", "No hubs yet. Run `jtc setup`."))
        lines = []
        for row in rows:
            channel = ctx.guild.get_channel(row["channel_id"])
            category = ctx.guild.get_channel(row["category_id"]) if row["category_id"] else (channel.category if channel else None)
            active = (await db.raw_fetchone("SELECT COUNT(*) AS n FROM jtc_channels WHERE hub_id=?", (row["channel_id"],)))["n"]
            lines.append(
                f"{channel.mention if channel else row['channel_id']}\nName: `{row['name_template']}`, limit: {row['user_limit'] or 'none'}, "
                f"bitrate: {str(row['bitrate']) + ' kbps' if row['bitrate'] else 'default'}, category: {category.name if category else 'none'}, active: {active}"
            )
        await ctx.send(view=info_layout("Join to Create hubs", "\n\n".join(lines)))

    async def _hub_edit(self, ctx: commands.Context, channel: discord.VoiceChannel, column: str, value) -> bool:
        hub = await get_hub(channel.id)
        if not hub or hub["guild_id"] != ctx.guild.id:
            await ctx.send(view=error_layout("Not a hub", f"{channel.mention} is not a hub."))
            return False
        await db.raw_execute(f"UPDATE jtc_hubs SET {column}=? WHERE channel_id=?", (value, channel.id))
        return True

    @jtc_group.command(name="name", help="Set the channel name template. Usage: jtc name <hub> <template>")
    async def jtc_name(self, ctx: commands.Context, channel: discord.VoiceChannel, *, template: str):
        template = template[:80]
        if await self._hub_edit(ctx, channel, "name_template", template):
            await ctx.send(view=success_layout("Name template saved", f"New channels are named `{template}`."))

    @jtc_group.command(name="limit", help="Default user limit. Usage: jtc limit <hub> <0-99>")
    async def jtc_limit(self, ctx: commands.Context, channel: discord.VoiceChannel, number: int):
        if not 0 <= number <= 99:
            return await ctx.send(view=error_layout("Invalid", "Use a number from 0 to 99."))
        if await self._hub_edit(ctx, channel, "user_limit", number):
            await ctx.send(view=success_layout("Limit saved", f"New channels allow {number or 'unlimited'} members."))

    @jtc_group.command(name="bitrate", help="Default bitrate in kbps, 0 for default. Usage: jtc bitrate <hub> <kbps>")
    async def jtc_bitrate(self, ctx: commands.Context, channel: discord.VoiceChannel, kbps: int):
        if not 0 <= kbps <= 384:
            return await ctx.send(view=error_layout("Invalid", "Use 0 or a number up to 384. Discord may cap it lower for your server's boost level."))
        if await self._hub_edit(ctx, channel, "bitrate", kbps):
            await ctx.send(view=success_layout("Bitrate saved", f"New channels use {kbps} kbps." if kbps else "New channels use the default bitrate."))

    @jtc_group.command(name="category", help="Where new channels are created. Usage: jtc category <hub> <category>")
    async def jtc_category(self, ctx: commands.Context, channel: discord.VoiceChannel, category: discord.CategoryChannel):
        if await self._hub_edit(ctx, channel, "category_id", category.id):
            await ctx.send(view=success_layout("Category saved", f"New channels go in **{category.name}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinToCreate(bot))
