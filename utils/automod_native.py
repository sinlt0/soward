from typing import Optional

import discord

from utils import guild_settings
from utils import security_settings as settings

PREFIX = "Soward · "
STORE_KEY = "automod_native_rules"
MAX_KEYWORDS = 1000
MAX_KEYWORD_LENGTH = 60


def _ids(values, limit: int) -> list[int]:
    found = []
    for value in values or []:
        try:
            found.append(int(value))
        except (TypeError, ValueError):
            continue
    return found[:limit]


async def _owned(guild: discord.Guild) -> list[discord.AutoModRule]:
    stored = set(_ids(await guild_settings.get(guild.id, STORE_KEY, []), 50))
    try:
        rules = await guild.fetch_automod_rules()
    except discord.HTTPException:
        return []
    return [rule for rule in rules if rule.id in stored or rule.name.startswith(PREFIX)]


async def remove(guild: discord.Guild, reason: str) -> int:
    removed = 0
    for rule in await _owned(guild):
        try:
            await rule.delete(reason=reason)
            removed += 1
        except discord.HTTPException:
            continue
    await guild_settings.set(guild.id, STORE_KEY, [])
    return removed


async def sync(guild: discord.Guild, actor: Optional[discord.abc.User] = None) -> tuple[list[str], list[str]]:
    reason = f"Soward native AutoMod sync{f' by {actor}' if actor else ''}"
    gid = guild.id
    notes: list[str] = []
    made: list[str] = []
    if guild.me is None or not guild.me.guild_permissions.manage_guild:
        return made, ["I need the Manage Server permission to manage Discord's AutoMod."]

    await remove(guild, reason)
    exempt_roles = [discord.Object(id=i) for i in _ids(await settings.get(gid, "automod", "exempt_roles"), 20)]
    exempt_channels = [discord.Object(id=i) for i in _ids(await settings.get(gid, "automod", "exempt_channels"), 50)]
    block = discord.AutoModRuleAction(custom_message="Blocked by Soward AutoMod.")
    created: list[int] = []

    async def make(name: str, trigger: discord.AutoModTrigger):
        try:
            rule = await guild.create_automod_rule(
                name=PREFIX + name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[block],
                enabled=True,
                exempt_roles=exempt_roles,
                exempt_channels=exempt_channels,
                reason=reason,
            )
            created.append(rule.id)
            made.append(name)
        except discord.HTTPException as ex:
            notes.append(f"{name}: {ex.text or ex}")

    words = [w for w in await settings.get(gid, "automod", "banned_words") if 0 < len(str(w)) <= MAX_KEYWORD_LENGTH][:MAX_KEYWORDS]
    if words:
        await make("Banned words", discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.keyword, keyword_filter=[str(w) for w in words]))
    else:
        notes.append("Banned words: the list is empty, so no keyword rule was made.")
    limit = min(int(await settings.get(gid, "automod", "mention_limit")), 50)
    await make("Mention spam", discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.mention_spam, mention_limit=limit, mention_raid_protection=True))
    await make("Spam", discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam))
    await guild_settings.set(gid, STORE_KEY, created)
    return made, notes


async def status(guild: discord.Guild) -> list[str]:
    return [f"{rule.name[len(PREFIX):] or rule.name} ({'on' if rule.enabled else 'off'})" for rule in await _owned(guild)]
