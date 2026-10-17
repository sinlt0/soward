import datetime
import time
from collections import defaultdict, deque
from typing import Optional, Union

import discord
from discord.ext import commands

from utils import automod_filters as filters
from utils import automod_native, cases, warn_ladder
from utils import emoji_manager, guild_settings, incident, security, threat
from utils import security_settings as settings
from utils import security_whitelist as whitelist
from utils import security_cmds
from utils.checks import has_guild_permission
from utils.security_access import security_owner, security_staff
from utils.events_bus import (
    AUTOMOD_VIOLATION,
    MEMBER_JOINED_UNVERIFIED,
    MEMBER_VERIFIED,
    LOG_EVENT,
    bus,
)
import config

_state: dict[tuple[int, int], dict] = {}
_history: dict[tuple[int, int], deque] = {}
_unverified: dict[int, set] = defaultdict(set)
_panic_flags: dict[int, list[tuple[int, float]]] = defaultdict(list)
_counter = [0]
_bursts: dict[int, deque] = defaultdict(deque)

FILTER_DEFAULTS = {
    "scamlinks": True,
    "caps": True,
    "zalgo": True,
    "duplicates": True,
    "emoji": True,
    "attachments": True,
    "wholeword": False,
}


def _record_panic_flag(guild_id: int, user_id: int) -> int:
    now = time.time()
    window = config.PANIC_MODE_WINDOW_SECONDS
    flags = [(uid, ts) for uid, ts in _panic_flags[guild_id] if now - ts <= window]
    if not any(uid == user_id for uid, _ in flags):
        flags.append((user_id, now))
    _panic_flags[guild_id] = flags
    return len({uid for uid, _ in flags})


def _get_heat(guild_id: int, user_id: int, decay: float = config.AUTOMOD_HEAT_DECAY_PER_SECOND, reset: int = config.AUTOMOD_MUTE_MULTIPLIER_RESET_SECONDS) -> tuple[float, int]:
    data = _state.get((guild_id, user_id))
    if data is None:
        return 0.0, 1
    now = time.time()
    heat = max(0.0, data["heat"] - decay * (now - data["ts"]))
    multiplier = data["mult"]
    if multiplier > 1 and now - data["offense"] > reset:
        multiplier = 1
    return heat, multiplier


def _add_heat(guild_id: int, user_id: int, amount: float, decay: float, reset: int) -> tuple[float, int]:
    heat, multiplier = _get_heat(guild_id, user_id, decay, reset)
    previous = _state.get((guild_id, user_id))
    _state[(guild_id, user_id)] = {
        "heat": heat + amount, "ts": time.time(), "mult": multiplier,
        "offense": previous["offense"] if previous else 0.0,
    }
    return heat + amount, multiplier


def _register_offense(guild_id: int, user_id: int, ceiling: int, reset_heat: bool, decay: float, reset: int) -> None:
    heat, multiplier = _get_heat(guild_id, user_id, decay, reset)
    now = time.time()
    _state[(guild_id, user_id)] = {"heat": 0.0 if reset_heat else heat, "ts": now, "mult": min(multiplier + 1, ceiling), "offense": now}


def clear_heat(guild_id: int, user_id: int) -> None:
    _state.pop((guild_id, user_id), None)
    _history.pop((guild_id, user_id), None)


def heat_members(guild_id: int) -> list[int]:
    return [uid for (gid, uid) in list(_state) if gid == guild_id]


def _prune_state() -> None:
    now = time.time()
    for key in [k for k, v in _state.items() if now - max(v["ts"], v["offense"]) > config.AUTOMOD_STALE_SECONDS]:
        del _state[key]
    for key in [k for k, v in _history.items() if not v or now - v[-1][0] > config.AUTOMOD_STALE_SECONDS]:
        del _history[key]


class AutoMod(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bus.subscribe(MEMBER_JOINED_UNVERIFIED, self._on_member_joined_unverified)
        bus.subscribe(MEMBER_VERIFIED, self._on_member_verified)

    async def _on_member_joined_unverified(self, *, guild_id: int, user_id: int, **_):
        _unverified[guild_id].add(user_id)

    async def _on_member_verified(self, *, guild_id: int, user_id: int, **_):
        _unverified[guild_id].discard(user_id)

    async def _is_enabled(self, guild_id: int) -> bool:
        return await settings.get(guild_id, "automod", "enabled")

    async def _filter_on(self, guild_id: int, name: str) -> bool:
        return bool(await settings.get(guild_id, "automod", f"filter_{name}"))

    async def _is_exempt(self, message: discord.Message) -> bool:
        member = message.author
        guild_id = message.guild.id
        if await security.is_exempt(guild_id, member, "automod", message.channel):
            return True
        channels: list = await settings.get(guild_id, "automod", "exempt_channels")
        if channels:
            channel = message.channel
            ids = {channel.id, getattr(channel, "category_id", None), getattr(channel, "parent_id", None)}
            if any(int(c) in ids for c in channels):
                return True
        roles: list = await settings.get(guild_id, "automod", "exempt_roles")
        if roles and any(r.id in {int(x) for x in roles} for r in getattr(member, "roles", [])):
            return True
        return False

    async def _evaluate(self, message: discord.Message, *, edited: bool) -> tuple[float, list[str], bool]:
        guild_id = message.guild.id
        skip = await whitelist.scopes_for(guild_id, message.author, message.channel)
        user_id = message.author.id
        content = message.content or ""
        events = {name: float(await settings.get(guild_id, "automod", f"weight_{name}")) for name in config.AUTOMOD_HEAT_EVENTS}
        heat = 0.0 if edited else events["message"]
        reasons: list[str] = []
        remove = False

        mention_limit = await settings.get(guild_id, "automod", "mention_limit")
        mentions = len(message.mentions) + len(message.role_mentions)
        if mentions >= mention_limit and "mentions" not in skip:
            heat += events["mention"] * mentions
            reasons.append("mass mention")
            remove = True
        if message.mention_everyone and "mentions" not in skip:
            heat += events["everyone"]
            reasons.append("everyone ping")

        banned: list = await settings.get(guild_id, "automod", "banned_words")
        if banned and "words" not in skip:
            hit = filters.banned_word_hit(content, banned, await self._filter_on(guild_id, "wholeword"))
            if hit:
                heat += events["banned_word"]
                reasons.append("banned word")
                remove = True

        if content and "invites" not in skip and await settings.get(guild_id, "automod", "block_invites") and filters.has_invite(content):
            heat += events["invite"]
            reasons.append("invite link")
            remove = True

        if content and "links" not in skip:
            blocklist: list = await settings.get(guild_id, "automod", "link_blocklist")
            allowlist: list = await settings.get(guild_id, "automod", "link_allowlist")
            blocked = filters.blocked_host(content, blocklist) if blocklist else None
            disallowed = filters.disallowed_host(content, allowlist) if allowlist else None
            if blocked or disallowed:
                heat += events["link"]
                reasons.append("blocked link")
                remove = True
            if await self._filter_on(guild_id, "scamlinks"):
                scam = filters.scam_host(content)
                if scam:
                    heat += events["phishing"] if scam[1] == "phishing" else events["iplogger"]
                    reasons.append("phishing link" if scam[1] == "phishing" else "ip logger link")
                    remove = True

        if content and await self._filter_on(guild_id, "zalgo") and filters.is_zalgo(content):
            heat += events["zalgo"]
            reasons.append("zalgo text")
            remove = True

        if "spam" not in skip:
            if not edited and content and await self._filter_on(guild_id, "duplicates"):
                history = _history.setdefault((guild_id, user_id), deque(maxlen=5))
                window = await settings.get(guild_id, "automod", "duplicate_window")
                similarity = await settings.get(guild_id, "automod", "duplicate_similarity")
                if filters.is_duplicate(history, content, time.time(), window, similarity):
                    heat += events["duplicate_message"]
                    reasons.append("duplicate message")
                    remove = True
            if content and await self._filter_on(guild_id, "caps"):
                if filters.is_caps_spam(content, await settings.get(guild_id, "automod", "caps_min_length"), await settings.get(guild_id, "automod", "caps_ratio")):
                    heat += events["caps"]
                    reasons.append("excessive caps")
            if content and filters.is_text_wall(content, await settings.get(guild_id, "automod", "wall_length")):
                heat += events["wall"]
                reasons.append("text wall")
            if content and await self._filter_on(guild_id, "emoji") and filters.is_emoji_spam(content, await settings.get(guild_id, "automod", "emoji_limit")):
                heat += events["emoji"]
                reasons.append("emoji spam")
            if not edited and await self._filter_on(guild_id, "attachments") and len(message.attachments) >= await settings.get(guild_id, "automod", "attachment_limit"):
                heat += events["attachments"]
                reasons.append("attachment spam")

        if reasons:
            if user_id in _unverified.get(guild_id, set()):
                heat *= await settings.get(guild_id, "automod", "unverified_heat_factor")
            if await security.is_panic_mode_active(guild_id) or threat.is_beast(guild_id):
                heat *= await settings.get(guild_id, "automod", "raid_heat_factor")
        return heat, reasons, remove

    async def _cleanup(self, message: discord.Message):
        channel = message.channel
        cutoff = discord.utils.utcnow() - datetime.timedelta(seconds=60)
        try:
            await channel.purge(limit=20, check=lambda m: m.author.id == message.author.id and m.created_at >= cutoff, bulk=True)
        except (discord.HTTPException, AttributeError):
            pass

    async def _warn(self, message: discord.Message, reasons: list[str]):
        channel = message.channel
        if not channel.permissions_for(message.guild.me).send_messages:
            return
        e = emoji_manager.get
        lifetime = await settings.get(message.guild.id, "automod", "notify_delete_after")
        try:
            await channel.send(
                f"{e('cross')} {message.author.mention}, your message was removed: {', '.join(dict.fromkeys(reasons))}.",
                delete_after=lifetime,
                allowed_mentions=discord.AllowedMentions(users=[message.author]),
            )
        except discord.HTTPException:
            pass

    async def _punish(self, guild: discord.Guild, member: discord.Member, action: str, reason: str, seconds: int):
        try:
            if action == "timeout":
                until = discord.utils.utcnow() + datetime.timedelta(seconds=min(seconds, 2419200))
                await member.timeout(until, reason=reason)
            elif action == "kick":
                await member.kick(reason=reason)
            elif action == "ban":
                await guild.ban(member, reason=reason, delete_message_days=1)
            elif action == "quarantine":
                await security.quarantine_member(guild, member, reason)
        except discord.HTTPException:
            pass

    async def _apply_heat_punishment(self, message: discord.Message, heat: float, multiplier: int, violation: str):
        member = message.author
        guild = message.guild
        gid = guild.id
        if await settings.get(gid, "automod", "purge_on_punish"):
            await self._cleanup(message)

        severe = heat >= await settings.get(gid, "automod", "panic_threshold")
        if severe:
            action = await settings.get(gid, "automod", "panic_action")
            await self._punish(guild, member, action, f"AutoMod: heat panic threshold exceeded ({violation})", 0)
            flagged_count = _record_panic_flag(gid, member.id)
            if flagged_count >= config.PANIC_MODE_RAIDER_COUNT and not await security.is_panic_mode_active(gid):
                await security.trigger_panic_mode(gid, triggered_by="automod_heat_panic")
            await threat.add(gid, "automod_severe", f"{member.id}: {violation}")
        else:
            action = await settings.get(gid, "automod", "mute_action")
            seconds = int(await settings.get(gid, "automod", "base_mute")) * multiplier
            note = f"AutoMod: {violation} (x{multiplier} repeat offender)" if multiplier > 1 else f"AutoMod: {violation}"
            await self._punish(guild, member, action, note, seconds)
            await threat.add(gid, "automod_punish", f"{member.id}: {violation}")
            if await settings.get(gid, "automod", "warn_on_punish"):
                await cases.create_warn(gid, member.id, self.bot.user.id, f"AutoMod: {violation}")
                await warn_ladder.apply(guild, member)
        _register_offense(
            gid, member.id, int(await settings.get(gid, "automod", "max_multiplier")),
            bool(await settings.get(gid, "automod", "reset_heat_on_punish")),
            float(await settings.get(gid, "automod", "decay")), int(await settings.get(gid, "automod", "multiplier_reset")),
        )

        await bus.publish(
            AUTOMOD_VIOLATION,
            guild_id=gid,
            user_id=member.id,
            channel_id=message.channel.id,
            violation_type=violation,
            detail=f"heat={heat:.1f} multiplier={multiplier} action={action}",
            incident_state=await incident.get_state(gid),
        )
        await bus.publish(LOG_EVENT, guild_id=gid, action="automod_action", user_id=member.id, channel_id=message.channel.id, detail=f"{violation} heat={heat:.1f} action={action}")

    async def _scan(self, message: discord.Message, *, edited: bool):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        if not await self._is_enabled(message.guild.id):
            return
        if await self._is_exempt(message):
            return

        _counter[0] += 1
        if _counter[0] % 500 == 0:
            _prune_state()

        gid = message.guild.id
        user_id = message.author.id
        gained, reasons, remove = await self._evaluate(message, edited=edited)
        decay = float(await settings.get(gid, "automod", "decay"))
        reset = int(await settings.get(gid, "automod", "multiplier_reset"))
        new_heat, multiplier = _add_heat(gid, user_id, gained, decay, reset)
        label = reasons[0] if reasons else "heat threshold exceeded"
        delete = remove and await settings.get(gid, "automod", "delete_flagged")

        if new_heat >= await settings.get(gid, "automod", "mute_threshold"):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self._apply_heat_punishment(message, new_heat, multiplier, label)
        elif delete:
            try:
                await message.delete()
            except discord.HTTPException:
                return
            if await settings.get(gid, "automod", "notify"):
                await self._warn(message, reasons)
            await bus.publish(LOG_EVENT, guild_id=gid, action="automod_action", user_id=user_id, channel_id=message.channel.id, detail=f"{label} removed")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild and message.webhook_id and getattr(message, "application_id", None) is None:
            return await self._guard_webhook(message)
        await self._scan(message, edited=False)
        await self._watch_burst(message)

    async def _watch_burst(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        if not await self._is_enabled(gid) or not await settings.get(gid, "automod", "burst_lockdown"):
            return
        limit = await settings.get(gid, "automod", "mention_limit")
        if not (message.mention_everyone or len(message.mentions) + len(message.role_mentions) >= limit):
            return
        now = time.time()
        window = await settings.get(gid, "automod", "burst_window")
        events = _bursts[gid]
        events.append(now)
        while events and now - events[0] > window:
            events.popleft()
        if len(events) < await settings.get(gid, "automod", "burst_count"):
            return
        events.clear()
        lockdown = self.bot.get_cog("Lockdown")
        if lockdown is not None:
            await lockdown.start(message.guild, "Mass-mention burst detected by AutoMod", None)
            await threat.add(gid, "automod_burst", "mass-mention burst")

    async def _guard_webhook(self, message: discord.Message):
        gid = message.guild.id
        if not await self._is_enabled(gid) or not await settings.get(gid, "automod", "webhook_protection"):
            return
        limit = await settings.get(gid, "automod", "mention_limit")
        invite = filters.has_invite(message.content)
        if not (message.mention_everyone or invite or len(message.mentions) + len(message.role_mentions) >= limit):
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        if await settings.get(gid, "automod", "webhook_delete") and message.guild.me.guild_permissions.manage_webhooks:
            try:
                hook = discord.utils.get(await message.guild.webhooks(), id=message.webhook_id)
                if hook is not None:
                    await hook.delete(reason="AutoMod: abusive webhook message")
            except discord.HTTPException:
                pass
        await threat.add(gid, "automod_webhook", f"webhook {message.webhook_id}")
        await bus.publish(LOG_EVENT, guild_id=gid, action="automod_action", user_id=0, channel_id=message.channel.id, detail=f"webhook {message.webhook_id} message removed")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content:
            return
        await self._scan(after, edited=True)

    @commands.group(name="automod", aliases=["am"], invoke_without_command=True, help='View or configure AutoMod filters.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def automod_group(self, ctx: commands.Context):
        from utils.security_panels import AutoModOverviewLayout
        view = await AutoModOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @automod_group.command(name="settings", aliases=["config", "options"], help="List every automod setting and its current value. Usage: settings [group|all]")
    @has_guild_permission("administrator")
    async def automod_cfg_settings(self, ctx: commands.Context, group: Optional[str] = None):
        await security_cmds.show_settings(ctx, "automod", group)

    @automod_group.command(name="get", help="Show one automod setting with its default. Usage: get <key>")
    @has_guild_permission("administrator")
    async def automod_cfg_get(self, ctx: commands.Context, key: str):
        await security_cmds.get_setting(ctx, "automod", key)

    @automod_group.command(name="set", help="Change an AutoMod setting. Usage: set <key> <value>")
    @security_staff()
    async def automod_cfg_set(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.set_setting(ctx, "automod", key, value)

    @automod_group.command(name="reset", help="Reset one automod setting, or `all`, to its default. Usage: reset <key|all>")
    @security_owner()
    async def automod_cfg_reset(self, ctx: commands.Context, key: str):
        await security_cmds.reset_setting(ctx, "automod", key)

    @automod_group.command(name="add", help="Add an entry to an AutoMod list setting. Usage: add <key> <value>")
    @security_staff()
    async def automod_cfg_add(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "automod", key, value, True)

    @automod_group.command(name="remove", help="Remove an entry from an AutoMod list setting. Usage: remove <key> <value>")
    @security_staff()
    async def automod_cfg_remove(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "automod", key, value, False)

    @automod_group.command(name="list", help="Show the entries of an AutoMod list setting. Usage: list <key>")
    @has_guild_permission("administrator")
    async def automod_cfg_list(self, ctx: commands.Context, key: str):
        await security_cmds.show_list(ctx, "automod", key)

    @automod_group.command(name="enable", help='Enable AutoMod filters.')
    @security_staff()
    async def automod_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AutoMod enabled", "AutoMod is now active in this server."))

    @automod_group.command(name="disable", help='Disable AutoMod filters.')
    @security_owner()
    async def automod_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AutoMod disabled", "AutoMod has been disabled."))

    @automod_group.group(name="native", invoke_without_command=True, help="Mirror these filters into Discord's built-in AutoMod. Usage: native [sync|status|off]")
    @security_staff()
    @commands.guild_only()
    async def automod_native(self, ctx: commands.Context):
        await self.automod_native_status(ctx)

    @automod_native.command(name="status", help="Show the Discord AutoMod rules Soward manages.")
    @security_staff()
    async def automod_native_status(self, ctx: commands.Context):
        from utils.components import info_layout
        rules = await automod_native.status(ctx.guild)
        body = "\n".join(f"• {line}" for line in rules) if rules else "No native rules yet. Run `automod native sync`."
        await ctx.send(view=info_layout("Native AutoMod", body))

    @automod_native.command(name="sync", help="Create or refresh Discord AutoMod rules from banned words, mention limit and spam.")
    @security_staff()
    async def automod_native_sync(self, ctx: commands.Context):
        from utils.components import error_layout, info_layout
        made, notes = await automod_native.sync(ctx.guild, ctx.author)
        lines = [f"Created: {', '.join(made)}" if made else "Nothing was created."]
        lines += [f"• {note}" for note in notes]
        layout = info_layout if made else error_layout
        await ctx.send(view=layout("Native AutoMod", "\n".join(lines)))

    @automod_native.command(name="off", aliases=["remove"], help="Delete the Discord AutoMod rules Soward created.")
    @security_staff()
    async def automod_native_off(self, ctx: commands.Context):
        from utils.components import info_layout
        count = await automod_native.remove(ctx.guild, f"Removed by {ctx.author}")
        await ctx.send(view=info_layout("Native AutoMod", f"Removed {count} rule(s)."))

    @automod_group.command(name="banword", help='Add a word to the banned words list.')
    @security_staff()
    async def automod_banword(self, ctx: commands.Context, *, word: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        word = word.lower().strip()
        current: list = await guild_settings.get(ctx.guild.id, "automod_banned_words", [])
        if len(word) < 2 or len(word) > 100:
            return await ctx.send(view=error_layout("Invalid word", "Banned words must be 2-100 characters."))
        if len(current) >= 100 and word not in current:
            return await ctx.send(view=error_layout("List full", "AutoMod can hold up to 100 banned words."))
        if word not in current:
            current.append(word)
            await guild_settings.set(ctx.guild.id, "automod_banned_words", current)
        await ctx.send(view=success_layout(f"{e('check')} Word banned", "Added to the banned words list. Look-alike characters, spacing tricks and edits are matched too."))

    @automod_group.command(name="unbanword", help='Remove a word from the banned words list.')
    @security_staff()
    async def automod_unbanword(self, ctx: commands.Context, *, word: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        word = word.lower().strip()
        current: list = await guild_settings.get(ctx.guild.id, "automod_banned_words", [])
        if word in current:
            current.remove(word)
            await guild_settings.set(ctx.guild.id, "automod_banned_words", current)
            await ctx.send(view=success_layout(f"{e('check')} Word removed", "Removed from the banned words list."))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Not found", "That word is not in the banned words list."))

    @automod_group.command(name="blockinvites", help='Toggle blocking of Discord invite links.')
    @security_staff()
    async def automod_blockinvites(self, ctx: commands.Context, toggle: bool):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_block_invites", toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Invite blocking {state}", f"Invite link filtering is now {state}."))

    async def _edit_domains(self, ctx: commands.Context, key: str, domain: str, add: bool, label: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        cleaned = filters.clean_domain(domain)
        if "." not in cleaned or len(cleaned) > 100:
            return await ctx.send(view=error_layout("Invalid domain", "Give a domain such as `example.com`."))
        current: list = await guild_settings.get(ctx.guild.id, key, [])
        if add:
            if len(current) >= 100 and cleaned not in current:
                return await ctx.send(view=error_layout("List full", "A list can hold up to 100 domains."))
            if cleaned not in current:
                current.append(cleaned)
            await guild_settings.set(ctx.guild.id, key, current)
            return await ctx.send(view=success_layout(f"{e('check')} Domain added", f"`{cleaned}` and its subdomains were added to the {label}."))
        if cleaned not in current:
            return await ctx.send(view=error_layout(f"{e('cross')} Not found", f"`{cleaned}` is not in the {label}."))
        current.remove(cleaned)
        await guild_settings.set(ctx.guild.id, key, current)
        await ctx.send(view=success_layout(f"{e('check')} Domain removed", f"`{cleaned}` was removed from the {label}."))

    @automod_group.command(name="blockdomain", help='Add a domain to the link blocklist. Subdomains are blocked too.')
    @security_staff()
    async def automod_blockdomain(self, ctx: commands.Context, domain: str):
        await self._edit_domains(ctx, "automod_link_blocklist", domain, True, "link blocklist")

    @automod_group.command(name="unblockdomain", help='Remove a domain from the link blocklist.')
    @security_staff()
    async def automod_unblockdomain(self, ctx: commands.Context, domain: str):
        await self._edit_domains(ctx, "automod_link_blocklist", domain, False, "link blocklist")

    @automod_group.command(name="allowdomain", help='Add a domain to the link allowlist. Once set, only allowlisted domains are permitted.')
    @security_staff()
    async def automod_allowdomain(self, ctx: commands.Context, domain: str):
        await self._edit_domains(ctx, "automod_link_allowlist", domain, True, "link allowlist")

    @automod_group.command(name="unallowdomain", help='Remove a domain from the link allowlist.')
    @security_staff()
    async def automod_unallowdomain(self, ctx: commands.Context, domain: str):
        await self._edit_domains(ctx, "automod_link_allowlist", domain, False, "link allowlist")

    @automod_group.command(name="filter", help="Toggle a built-in filter: scamlinks, caps, zalgo, duplicates, emoji, attachments or wholeword.")
    @security_staff()
    async def automod_filter(self, ctx: commands.Context, name: str, toggle: bool):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        name = name.lower()
        if name not in FILTER_DEFAULTS:
            return await ctx.send(view=error_layout("Unknown filter", f"Choose from: {', '.join(f'`{n}`' for n in FILTER_DEFAULTS)}"))
        await guild_settings.set(ctx.guild.id, f"automod_filter_{name}", toggle)
        await ctx.send(view=success_layout(f"{e('check')} Filter updated", f"`{name}` is now {'on' if toggle else 'off'}."))

    @automod_group.command(name="mentions", help="Set how many mentions in one message count as mass mention (2-50).")
    @security_staff()
    async def automod_mentions(self, ctx: commands.Context, limit: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 2 <= limit <= 50:
            return await ctx.send(view=error_layout("Invalid limit", "Choose a number between 2 and 50."))
        await guild_settings.set(ctx.guild.id, "automod_mention_limit", limit)
        await ctx.send(view=success_layout(f"{e('check')} Mention limit set", f"Messages with **{limit}** or more mentions are removed."))

    @automod_group.command(name="exempt", help="Exempt a channel, category or role from AutoMod. Usage: exempt <add|remove|list> [channel or role]")
    @security_staff()
    async def automod_exempt(self, ctx: commands.Context, action: str, target: Optional[Union[discord.abc.GuildChannel, discord.Role]] = None):
        from utils.components import error_layout, info_layout, success_layout
        e = emoji_manager.get
        action = action.lower()
        channels: list = await guild_settings.get(ctx.guild.id, "automod_exempt_channels", [])
        roles: list = await guild_settings.get(ctx.guild.id, "automod_exempt_roles", [])
        if action == "list":
            body = "**Channels:** " + (" ".join(f"<#{c}>" for c in channels) or "none") + "\n**Roles:** " + (" ".join(f"<@&{r}>" for r in roles) or "none")
            return await ctx.send(view=info_layout(f"{e('shield')} AutoMod exemptions", body))
        if action not in ("add", "remove") or target is None:
            return await ctx.send(view=error_layout("Invalid usage", "Use `exempt add <channel or role>`, `exempt remove <channel or role>` or `exempt list`."))
        is_role = isinstance(target, discord.Role)
        store = roles if is_role else channels
        key = "automod_exempt_roles" if is_role else "automod_exempt_channels"
        if action == "add":
            if len(store) >= 50 and target.id not in store:
                return await ctx.send(view=error_layout("List full", "You can exempt up to 50 channels and 50 roles."))
            if target.id not in store:
                store.append(target.id)
        else:
            if target.id not in store:
                return await ctx.send(view=error_layout(f"{e('cross')} Not exempt", "That target is not exempt from AutoMod."))
            store.remove(target.id)
        await guild_settings.set(ctx.guild.id, key, store)
        await ctx.send(view=success_layout(f"{e('check')} Exemptions updated", f"{target.mention} {'is now exempt from' if action == 'add' else 'is no longer exempt from'} AutoMod."))

    @automod_group.command(name="heat", help="View a member's current AutoMod heat score.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def automod_heat(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        from utils.components import info_layout
        e = emoji_manager.get
        member = member or ctx.author
        heat, multiplier = _get_heat(ctx.guild.id, member.id)
        await ctx.send(view=info_layout(
            f"{e('heat')} Heat score for {member.display_name}",
            f"**Current heat:** {heat:.1f}\n"
            f"**Mute multiplier:** {multiplier}x\n"
            f"**Mute threshold:** {config.AUTOMOD_HEAT_MUTE_THRESHOLD}\n"
            f"**Panic threshold:** {config.AUTOMOD_HEAT_PANIC_THRESHOLD}",
        ))

    @automod_group.command(name="resetheat", help="Reset a member's heat score and mute multiplier.")
    @security_staff()
    @commands.guild_only()
    async def automod_resetheat(self, ctx: commands.Context, member: discord.Member):
        from utils.components import success_layout
        e = emoji_manager.get
        clear_heat(ctx.guild.id, member.id)
        await ctx.send(view=success_layout(f"{e('check')} Heat reset", f"Heat score and mute multiplier cleared for {member.mention}."))

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
