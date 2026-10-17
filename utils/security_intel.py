import difflib
import time
from collections import defaultdict, deque
from typing import Optional

import discord

from utils.automod_filters import squash

BAN_CACHE_SECONDS = 600
BAN_CACHE_LIMIT = 1000
STAFF_LIMIT = 300
MIN_NAME_LENGTH = 4

_ban_cache: dict[int, tuple[float, list[tuple[int, Optional[str], str]]]] = {}
_invite_uses: dict[int, dict[str, int]] = {}
_join_invites: dict[int, deque] = defaultdict(lambda: deque(maxlen=500))


def _names(member: discord.abc.User) -> list[str]:
    raw = [member.name, getattr(member, "display_name", None), getattr(member, "global_name", None)]
    return list(dict.fromkeys(s for s in (squash(n) for n in raw if n) if len(s) >= MIN_NAME_LENGTH))


def _similar(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def staff_members(guild: discord.Guild) -> list[discord.Member]:
    found: list[discord.Member] = []
    for member in guild.members:
        if member.bot:
            continue
        perms = member.guild_permissions
        if member.id == guild.owner_id or perms.administrator or perms.manage_guild or perms.ban_members or perms.kick_members or perms.manage_roles:
            found.append(member)
            if len(found) >= STAFF_LIMIT:
                break
    return found


def impersonation_hit(guild: discord.Guild, member: discord.Member, threshold: float) -> Optional[str]:
    mine = _names(member)
    if not mine:
        return None
    for staff in staff_members(guild):
        if staff.id == member.id:
            continue
        for theirs in _names(staff):
            for name in mine:
                if _similar(name, theirs) >= threshold:
                    return staff.display_name
    return None


async def _bans(guild: discord.Guild) -> list[tuple[int, Optional[str], str]]:
    cached = _ban_cache.get(guild.id)
    if cached and time.time() - cached[0] < BAN_CACHE_SECONDS:
        return cached[1]
    if guild.me is None or not guild.me.guild_permissions.ban_members:
        return []
    entries: list[tuple[int, Optional[str], str]] = []
    try:
        async for entry in guild.bans(limit=BAN_CACHE_LIMIT):
            user = entry.user
            key = user.avatar.key if user.avatar else None
            entries.append((user.id, key, squash(user.name)))
    except discord.HTTPException:
        return cached[1] if cached else []
    _ban_cache[guild.id] = (time.time(), entries)
    return entries


def forget_bans(guild_id: int) -> None:
    _ban_cache.pop(guild_id, None)


async def evasion_hit(guild: discord.Guild, member: discord.Member, threshold: float) -> Optional[str]:
    avatar = member.avatar.key if member.avatar else None
    mine = _names(member)
    for user_id, banned_avatar, banned_name in await _bans(guild):
        if user_id == member.id:
            continue
        if avatar and banned_avatar and avatar == banned_avatar:
            return f"same avatar as banned user {user_id}"
        if len(banned_name) >= MIN_NAME_LENGTH and any(_similar(name, banned_name) >= threshold for name in mine):
            return f"name matches banned user {user_id}"
    return None


async def snapshot_invites(guild: discord.Guild) -> Optional[dict[str, int]]:
    if guild.me is None or not guild.me.guild_permissions.manage_guild:
        return None
    try:
        invites = await guild.invites()
    except discord.HTTPException:
        return None
    return {invite.code: invite.uses or 0 for invite in invites}


async def used_invite(guild: discord.Guild, member: discord.Member) -> Optional[str]:
    before = _invite_uses.get(guild.id)
    after = await snapshot_invites(guild)
    if after is None:
        return None
    _invite_uses[guild.id] = after
    if before is None:
        return None
    for code, uses in after.items():
        if uses > before.get(code, 0):
            _join_invites[guild.id].append((time.time(), member.id, code))
            return code
    return None


async def prime_invites(guild: discord.Guild) -> None:
    snapshot = await snapshot_invites(guild)
    if snapshot is not None:
        _invite_uses[guild.id] = snapshot


def note_invite_created(guild_id: int, code: str, uses: int) -> None:
    if guild_id in _invite_uses:
        _invite_uses[guild_id][code] = uses


def note_invite_deleted(guild_id: int, code: str) -> None:
    _invite_uses.get(guild_id, {}).pop(code, None)


def invite_for(guild_id: int, user_id: int) -> Optional[str]:
    for _, uid, code in reversed(_join_invites[guild_id]):
        if uid == user_id:
            return code
    return None


def recent_by_invite(guild_id: int, window: float) -> dict[str, list[int]]:
    now = time.time()
    grouped: dict[str, list[int]] = defaultdict(list)
    for ts, user_id, code in _join_invites[guild_id]:
        if now - ts <= window:
            grouped[code].append(user_id)
    return grouped
