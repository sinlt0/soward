import datetime
import re
import time
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings, incident, security
from utils.checks import has_guild_permission
from utils.events_bus import (
    AUTOMOD_VIOLATION,
    MEMBER_JOINED_UNVERIFIED,
    MEMBER_VERIFIED,
    LOG_EVENT,
    bus,
)
import config

_heat: dict[int, dict[int, list]] = defaultdict(dict)

_last_message: dict[tuple, str] = {}

_unverified: dict[int, set] = defaultdict(set)

_panic_flags: dict[int, list[tuple[int, float]]] = defaultdict(list)


def _record_panic_flag(guild_id: int, user_id: int) -> int:
    now = time.time()
    window = config.PANIC_MODE_WINDOW_SECONDS
    flags = [(uid, ts) for uid, ts in _panic_flags[guild_id] if now - ts <= window]
    if not any(uid == user_id for uid, _ in flags):
        flags.append((user_id, now))
    _panic_flags[guild_id] = flags
    return len({uid for uid, _ in flags})

def _get_heat(guild_id: int, user_id: int) -> tuple[float, int]:
    now = time.time()
    data = _heat[guild_id].get(user_id)
    if data is None:
        return 0.0, 1
    heat, last_updated, multiplier = data
    elapsed = now - last_updated
    decayed = max(0.0, heat - config.AUTOMOD_HEAT_DECAY_PER_SECOND * elapsed)
    return decayed, multiplier

def _add_heat(guild_id: int, user_id: int, amount: float) -> tuple[float, int]:
    now = time.time()
    current, multiplier = _get_heat(guild_id, user_id)
    new_heat = current + amount
    _heat[guild_id][user_id] = [new_heat, now, multiplier]
    return new_heat, multiplier

def _increment_multiplier(guild_id: int, user_id: int):
    data = _heat[guild_id].get(user_id, [0.0, time.time(), 1])
    data[2] = min(data[2] + 1, 10)
    data[1] = time.time()
    _heat[guild_id][user_id] = data

def _reset_multiplier(guild_id: int, user_id: int):
    data = _heat[guild_id].get(user_id)
    if data:
        data[2] = 1
        _heat[guild_id][user_id] = data

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
        return await guild_settings.get(guild_id, "automod_enabled", False)

    async def _is_whitelisted(self, guild_id: int, member: discord.Member) -> bool:
        return await security.is_trusted(guild_id, member)

    async def _apply_heat_punishment(self, message: discord.Message, heat: float, multiplier: int, violation: str):
        member = message.author
        guild = message.guild

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        if heat >= config.AUTOMOD_HEAT_PANIC_THRESHOLD:
            await security.quarantine_member(guild, member, f"AutoMod: heat panic threshold exceeded ({violation})")

            flagged_count = _record_panic_flag(guild.id, member.id)
            if flagged_count >= config.PANIC_MODE_RAIDER_COUNT and not await security.is_panic_mode_active(guild.id):
                await security.trigger_panic_mode(guild.id, triggered_by="automod_heat_panic")

            _increment_multiplier(guild.id, member.id)
        elif heat >= config.AUTOMOD_HEAT_MUTE_THRESHOLD:
            mute_secs = config.AUTOMOD_BASE_MUTE_SECONDS * multiplier
            mute_secs = min(mute_secs, 2419200)
            try:
                until = discord.utils.utcnow() + datetime.timedelta(seconds=mute_secs)
                await member.timeout(until, reason=f"AutoMod: {violation} (x{multiplier} repeat offender)" if multiplier > 1 else f"AutoMod: {violation}")
            except discord.HTTPException:
                pass

        await bus.publish(
            AUTOMOD_VIOLATION,
            guild_id=guild.id,
            user_id=member.id,
            channel_id=message.channel.id,
            violation_type=violation,
            detail=f"heat={heat:.1f} multiplier={multiplier}",
            incident_state=await incident.get_state(guild.id),
        )
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="automod_action", user_id=member.id, detail=f"{violation} heat={heat:.1f}")

    async def _check_banned_words(self, guild_id: int, content: str) -> Optional[str]:
        banned: list = await guild_settings.get(guild_id, "automod_banned_words", [])
        lower = content.lower()
        for word in banned:
            if word.lower() in lower:
                return word
        return None

    async def _check_invite(self, guild_id: int, content: str) -> bool:
        if not await guild_settings.get(guild_id, "automod_block_invites", False):
            return False
        return bool(re.search(r"(discord\.gg|discord\.com/invite)/[a-zA-Z0-9]+", content))

    async def _check_link(self, guild_id: int, content: str) -> Optional[str]:
        allowlist: list = await guild_settings.get(guild_id, "automod_link_allowlist", [])
        blocklist: list = await guild_settings.get(guild_id, "automod_link_blocklist", [])
        if not allowlist and not blocklist:
            return None
        domains = re.findall(r"https?://([a-zA-Z0-9.\-]+)", content)
        for domain in domains:
            if any(domain.endswith(b) for b in blocklist):
                return domain
            if allowlist and not any(domain.endswith(a) for a in allowlist):
                return domain
        return None

    def _check_duplicate(self, guild_id: int, user_id: int, content: str) -> bool:
        key = (guild_id, user_id)
        last = _last_message.get(key, "")
        _last_message[key] = content
        if not content or len(content) < 10:
            return False
        similarity = len(set(content.lower()) & set(last.lower())) / max(len(set(content)), 1)
        return last == content or similarity > 0.9

    def _check_mass_mention(self, message: discord.Message) -> int:
        return len(message.mentions) + len(message.role_mentions)

    def _check_text_wall(self, content: str) -> bool:
        return len(content) > 600 and "\n" not in content[:300]

    def _check_emoji_spam(self, content: str) -> bool:
        emoji_pattern = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>|[\U0001F000-\U0001FFFF]")
        emojis = emoji_pattern.findall(content)
        return len(emojis) > 10

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not await self._is_enabled(message.guild.id):
            return
        if await self._is_whitelisted(message.guild.id, message.author):
            return

        content = message.content
        guild_id = message.guild.id
        user_id = message.author.id
        is_unverified = user_id in _unverified.get(guild_id, set())

        heat_gained = config.AUTOMOD_HEAT_EVENTS["message"]

        mention_count = self._check_mass_mention(message)
        if mention_count >= 5:
            heat_gained += config.AUTOMOD_HEAT_EVENTS["mention"] * mention_count

        banned_word = await self._check_banned_words(guild_id, content)
        if banned_word:
            heat_gained += config.AUTOMOD_HEAT_EVENTS["banned_word"]

        if await self._check_invite(guild_id, content):
            heat_gained += config.AUTOMOD_HEAT_EVENTS["invite"]

        blocked_domain = await self._check_link(guild_id, content)
        if blocked_domain:
            heat_gained += config.AUTOMOD_HEAT_EVENTS["link"]

        if self._check_duplicate(guild_id, user_id, content):
            heat_gained += config.AUTOMOD_HEAT_EVENTS["duplicate_message"]

        if self._check_text_wall(content):
            heat_gained += 1.0

        if self._check_emoji_spam(content):
            heat_gained += 1.5

        if is_unverified:
            heat_gained *= 1.5

        new_heat, multiplier = _add_heat(guild_id, user_id, heat_gained)

        if new_heat >= config.AUTOMOD_HEAT_MUTE_THRESHOLD:
            violation_label = banned_word or blocked_domain or ("mass mention" if mention_count >= 5 else "heat threshold exceeded")
            await self._apply_heat_punishment(message, new_heat, multiplier, violation_label)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = member.guild.id
        if not await self._is_enabled(guild_id):
            return

    @commands.group(name="automod", aliases=["am"], invoke_without_command=True, help='View or configure AutoMod filters.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def automod_group(self, ctx: commands.Context):
        from utils.security_panels import AutoModOverviewLayout
        view = await AutoModOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @automod_group.command(name="enable", help='Enable AutoMod filters.')
    @has_guild_permission("administrator")
    async def automod_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AutoMod enabled", "AutoMod is now active in this server."))

    @automod_group.command(name="disable", help='Disable AutoMod filters.')
    @has_guild_permission("administrator")
    async def automod_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AutoMod disabled", "AutoMod has been disabled."))

    @automod_group.command(name="banword", help='Add a word to the banned words list.')
    @has_guild_permission("administrator")
    async def automod_banword(self, ctx: commands.Context, *, word: str):
        from utils.components import success_layout
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "automod_banned_words", [])
        if word.lower() not in current:
            current.append(word.lower())
            await guild_settings.set(ctx.guild.id, "automod_banned_words", current)
        await ctx.send(view=success_layout(f"{e('check')} Word banned", f"`{word}` added to the banned words list."))

    @automod_group.command(name="unbanword", help='Remove a word from the banned words list.')
    @has_guild_permission("administrator")
    async def automod_unbanword(self, ctx: commands.Context, *, word: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "automod_banned_words", [])
        if word.lower() in current:
            current.remove(word.lower())
            await guild_settings.set(ctx.guild.id, "automod_banned_words", current)
            await ctx.send(view=success_layout(f"{e('check')} Word removed", f"`{word}` removed from the banned words list."))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Not found", f"`{word}` is not in the banned words list."))

    @automod_group.command(name="blockinvites", help='Toggle blocking of Discord invite links.')
    @has_guild_permission("administrator")
    async def automod_blockinvites(self, ctx: commands.Context, toggle: bool):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "automod_block_invites", toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Invite blocking {state}", f"Invite link filtering is now {state}."))

    @automod_group.command(name="blockdomain", help='Add a domain to the link blocklist.')
    @has_guild_permission("administrator")
    async def automod_blockdomain(self, ctx: commands.Context, domain: str):
        from utils.components import success_layout
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "automod_link_blocklist", [])
        if domain not in current:
            current.append(domain)
            await guild_settings.set(ctx.guild.id, "automod_link_blocklist", current)
        await ctx.send(view=success_layout(f"{e('check')} Domain blocked", f"`{domain}` added to the link blocklist."))

    @automod_group.command(name="allowdomain", help='Add a domain to the link allowlist.')
    @has_guild_permission("administrator")
    async def automod_allowdomain(self, ctx: commands.Context, domain: str):
        from utils.components import success_layout
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "automod_link_allowlist", [])
        if domain not in current:
            current.append(domain)
            await guild_settings.set(ctx.guild.id, "automod_link_allowlist", current)
        await ctx.send(view=success_layout(f"{e('check')} Domain allowed", f"`{domain}` added to the link allowlist. Only links from allowlisted domains will be permitted."))

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
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def automod_resetheat(self, ctx: commands.Context, member: discord.Member):
        from utils.components import success_layout
        e = emoji_manager.get
        _heat[ctx.guild.id].pop(member.id, None)
        _reset_multiplier(ctx.guild.id, member.id)
        await ctx.send(view=success_layout(f"{e('check')} Heat reset", f"Heat score and mute multiplier cleared for {member.mention}."))

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
