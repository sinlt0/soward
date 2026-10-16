import time
from typing import Iterable, Optional

import discord

from utils import db

SCOPES: dict[str, str] = {
    "all": "Every security system",
    "antinuke": "AntiNuke limits and quarantine hold",
    "antiraid": "Join gate and raid actions",
    "automod": "Every AutoMod filter",
    "spam": "Duplicates, caps, walls, emoji and attachment spam",
    "mentions": "Mass mention filter",
    "invites": "Invite link filter",
    "links": "Link allowlist, blocklist and scam link filters",
    "words": "Banned word filter",
    "quarantine": "Allowed to touch quarantined members",
}
TARGET_TYPES = ("user", "role", "channel")
CACHE_SECONDS = 20
MAX_ENTRIES_PER_GUILD = 500

_cache: dict[int, tuple[float, dict[int, set[str]], dict[int, str]]] = {}


def invalidate(guild_id: int) -> None:
    _cache.pop(guild_id, None)


async def _load(guild_id: int) -> tuple[dict[int, set[str]], dict[int, str]]:
    cached = _cache.get(guild_id)
    now = time.time()
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1], cached[2]
    rows = await db.raw_fetch("SELECT target_id, target_type, scope FROM security_whitelist WHERE guild_id=?", (guild_id,))
    scopes: dict[int, set[str]] = {}
    types: dict[int, str] = {}
    for row in rows:
        scopes.setdefault(int(row["target_id"]), set()).add(row["scope"])
        types[int(row["target_id"])] = row["target_type"]
    _cache[guild_id] = (now, scopes, types)
    return scopes, types


async def add(guild_id: int, target_id: int, target_type: str, scope: str, added_by: Optional[int]) -> bool:
    if scope not in SCOPES or target_type not in TARGET_TYPES:
        return False
    existing = await db.raw_fetchone(
        "SELECT 1 FROM security_whitelist WHERE guild_id=? AND target_id=? AND scope=?", (guild_id, target_id, scope)
    )
    if existing:
        return False
    count = await db.raw_fetchone("SELECT COUNT(*) AS c FROM security_whitelist WHERE guild_id=?", (guild_id,))
    if count and count["c"] >= MAX_ENTRIES_PER_GUILD:
        raise ValueError(f"A server can have up to {MAX_ENTRIES_PER_GUILD} whitelist entries.")
    await db.raw_execute(
        "INSERT INTO security_whitelist (guild_id, target_id, target_type, scope, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, target_id, target_type, scope, added_by, time.time()),
    )
    invalidate(guild_id)
    return True


async def remove(guild_id: int, target_id: int, scope: Optional[str] = None) -> int:
    if scope is None:
        cur = await db.raw_execute("DELETE FROM security_whitelist WHERE guild_id=? AND target_id=?", (guild_id, target_id))
    else:
        cur = await db.raw_execute(
            "DELETE FROM security_whitelist WHERE guild_id=? AND target_id=? AND scope=?", (guild_id, target_id, scope)
        )
    invalidate(guild_id)
    return cur.rowcount


async def clear(guild_id: int, scope: Optional[str] = None) -> int:
    if scope is None:
        cur = await db.raw_execute("DELETE FROM security_whitelist WHERE guild_id=?", (guild_id,))
    else:
        cur = await db.raw_execute("DELETE FROM security_whitelist WHERE guild_id=? AND scope=?", (guild_id, scope))
    invalidate(guild_id)
    return cur.rowcount


async def list_entries(guild_id: int, scope: Optional[str] = None) -> list[dict]:
    if scope is None:
        rows = await db.raw_fetch(
            "SELECT * FROM security_whitelist WHERE guild_id=? ORDER BY target_type, target_id, scope", (guild_id,)
        )
    else:
        rows = await db.raw_fetch(
            "SELECT * FROM security_whitelist WHERE guild_id=? AND scope=? ORDER BY target_type, target_id", (guild_id, scope)
        )
    return [dict(r) for r in rows]


def _target_ids(member: Optional[discord.abc.User], channel: Optional[discord.abc.GuildChannel]) -> list[int]:
    ids: list[int] = []
    if member is not None:
        ids.append(member.id)
        ids.extend(r.id for r in getattr(member, "roles", []) if not r.is_default())
    if channel is not None:
        ids.append(channel.id)
        for attr in ("category_id", "parent_id"):
            value = getattr(channel, attr, None)
            if value:
                ids.append(value)
        parent = getattr(channel, "parent", None)
        parent_category = getattr(parent, "category_id", None)
        if parent_category:
            ids.append(parent_category)
    return ids


async def scopes_for(guild_id: int, member: Optional[discord.abc.User] = None, channel: Optional[discord.abc.GuildChannel] = None) -> set[str]:
    scopes, _ = await _load(guild_id)
    if not scopes:
        return set()
    found: set[str] = set()
    for target_id in _target_ids(member, channel):
        found |= scopes.get(target_id, set())
    return found


async def is_whitelisted(guild_id: int, scope_names: Iterable[str], member: Optional[discord.abc.User] = None, channel: Optional[discord.abc.GuildChannel] = None) -> bool:
    found = await scopes_for(guild_id, member, channel)
    if not found:
        return False
    return "all" in found or any(name in found for name in scope_names)


async def user_ids_for(guild_id: int, scope: str) -> set[int]:
    scopes, types = await _load(guild_id)
    return {tid for tid, names in scopes.items() if types.get(tid) == "user" and ("all" in names or scope in names)}
