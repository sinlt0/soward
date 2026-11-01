import time
from typing import Iterable, Optional

import discord

import config
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
_used: dict[tuple, float] = {}


def invalidate(guild_id: int) -> None:
    _cache.pop(guild_id, None)


async def _load(guild_id: int) -> tuple[dict[int, set[str]], dict[int, str]]:
    cached = _cache.get(guild_id)
    now = time.time()
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1], cached[2]
    rows = await db.raw_fetch(
        "SELECT target_id, target_type, scope FROM security_whitelist WHERE guild_id=? AND (expires_at IS NULL OR expires_at>?)", (guild_id, now)
    )
    scopes: dict[int, set[str]] = {}
    types: dict[int, str] = {}
    for row in rows:
        scopes.setdefault(int(row["target_id"]), set()).add(row["scope"])
        types[int(row["target_id"])] = row["target_type"]
    _cache[guild_id] = (now, scopes, types)
    return scopes, types


async def add(guild_id: int, target_id: int, target_type: str, scope: str, added_by: Optional[int], expires_at: Optional[float] = None) -> bool:
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
        "INSERT INTO security_whitelist (guild_id, target_id, target_type, scope, added_by, added_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, target_id, target_type, scope, added_by, time.time(), expires_at),
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
    now = time.time()
    for target_id in _target_ids(member, channel):
        matched = scopes.get(target_id, set())
        found |= matched
        for scope in matched:
            _used[("e", guild_id, target_id, scope)] = now
    return found


async def is_whitelisted(guild_id: int, scope_names: Iterable[str], member: Optional[discord.abc.User] = None, channel: Optional[discord.abc.GuildChannel] = None) -> bool:
    scopes, _ = await _load(guild_id)
    if not scopes:
        return False
    names = set(scope_names)
    now = time.time()
    hit = False
    for target_id in _target_ids(member, channel):
        for scope in scopes.get(target_id, ()):
            if scope == "all" or scope in names:
                _used[("e", guild_id, target_id, scope)] = now
                hit = True
    return hit


async def user_ids_for(guild_id: int, scope: str) -> set[int]:
    scopes, types = await _load(guild_id)
    return {tid for tid, names in scopes.items() if types.get(tid) == "user" and ("all" in names or scope in names)}


ACTION_KEYS: tuple[str, ...] = tuple(config.ANTINUKE_DEFAULT_THRESHOLDS) + ("vanity_change", "invite_delete", "protected_role", "channel_permission")
ACTION_GROUPS: dict[str, tuple[str, ...]] = {
    "channels": ("channel_create", "channel_update", "channel_delete", "channel_permission"),
    "roles": ("role_create", "role_update", "role_delete", "protected_role", "permission_escalation"),
    "members": ("ban", "kick", "prune", "timeout"),
    "webhooks": ("webhook_create", "webhook_delete"),
    "emojis": ("emoji_change", "sticker_change"),
    "server": ("guild_update", "vanity_change", "invite_delete", "integration_change", "bot_add"),
}
AUTOMOD_RULES: dict[str, str] = {
    "invite": "Allow a specific invite link or server's invites",
    "link": "Allow a specific domain through the link filters",
    "word": "Allow a specific banned word",
}
RULE_TARGET_TYPES = ("user", "role", "channel", "server")
RULE_CACHE_SECONDS = 20
MAX_RULES_PER_GUILD = 500
MAX_RULE_VALUE = 100

_rule_cache: dict[int, tuple[float, list[tuple[int, str, str]]]] = {}


def action_label(action: str) -> str:
    return action.replace("_", " ").capitalize()


def rule_scope_label(scope: str) -> str:
    kind, _, name = scope.partition(".")
    if kind == "antinuke":
        return f"AntiNuke: {action_label(name).lower()}"
    return f"AutoMod: {AUTOMOD_RULES.get(name, name).lower()}"


def resolve_actions(tokens: Iterable[str]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        for part in token.lower().replace(",", " ").split():
            part = part.replace("-", "_")
            if part.startswith("antinuke."):
                part = part.split(".", 1)[1]
            names = ACTION_GROUPS.get(part) or ((part,) if part in ACTION_KEYS else None)
            if names is None:
                raise ValueError(f"`{part}` is not an AntiNuke action or group. Run `whitelist scopes` to see them.")
            for name in names:
                if name not in out:
                    out.append(name)
    if not out:
        raise ValueError("Name at least one AntiNuke action or group.")
    return out


def resolve_rule_scope(text: str) -> str:
    name = text.lower().strip().replace("-", "_")
    if "." in name:
        kind, _, rest = name.partition(".")
        if (kind == "antinuke" and rest in ACTION_KEYS) or (kind == "automod" and rest in AUTOMOD_RULES):
            return name
    elif name in AUTOMOD_RULES:
        return f"automod.{name}"
    elif name in ACTION_KEYS:
        return f"antinuke.{name}"
    raise ValueError(f"`{text}` is not a granular whitelist scope. Run `whitelist scopes` to see them.")


def normalize_rule_value(scope: str, raw: str) -> str:
    text = raw.strip().lower()
    if not text:
        raise ValueError("A value is required.")
    if scope == "automod.invite":
        text = text.replace("https://", "").replace("http://", "").replace("www.", "")
        if text.isdigit() and len(text) >= 15:
            return f"g:{text}"
        for marker in ("discord.com/invite/", "discordapp.com/invite/", "discord.gg/", "dsc.gg/", "invite.gg/", "discord.me/", "discord.link/"):
            if text.startswith(marker):
                text = text[len(marker):]
                break
        text = text.split("?")[0].split("#")[0].strip("/")
        if not text or not all(c.isalnum() or c == "-" for c in text):
            raise ValueError("Give an invite link, an invite code or a server ID.")
    elif scope == "automod.link":
        from utils import automod_filters

        text = automod_filters.clean_domain(text)
        if "." not in text:
            raise ValueError("Give a domain such as `youtube.com`.")
    elif scope == "automod.word":
        from utils import automod_filters

        text = automod_filters.normalize(text).strip()
    if len(text) > MAX_RULE_VALUE:
        raise ValueError(f"Values can be at most {MAX_RULE_VALUE} characters.")
    return text


def invalidate_rules(guild_id: int) -> None:
    _rule_cache.pop(guild_id, None)


async def _load_rules(guild_id: int) -> list[tuple[int, str, str]]:
    cached = _rule_cache.get(guild_id)
    now = time.time()
    if cached and now - cached[0] < RULE_CACHE_SECONDS:
        return cached[1]
    rows = await db.raw_fetch(
        "SELECT target_id, scope, value FROM security_whitelist_rules WHERE guild_id=? AND (expires_at IS NULL OR expires_at>?)", (guild_id, now)
    )
    loaded = [(int(r["target_id"]), r["scope"], r["value"]) for r in rows]
    _rule_cache[guild_id] = (now, loaded)
    return loaded


async def rule_add(guild_id: int, target_id: int, target_type: str, scope: str, value: str, added_by: Optional[int], expires_at: Optional[float] = None) -> bool:
    if target_type not in RULE_TARGET_TYPES:
        return False
    existing = await db.raw_fetchone(
        "SELECT 1 FROM security_whitelist_rules WHERE guild_id=? AND target_id=? AND scope=? AND value=?", (guild_id, target_id, scope, value)
    )
    if existing:
        return False
    count = await db.raw_fetchone("SELECT COUNT(*) AS c FROM security_whitelist_rules WHERE guild_id=?", (guild_id,))
    if count and count["c"] >= MAX_RULES_PER_GUILD:
        raise ValueError(f"A server can have up to {MAX_RULES_PER_GUILD} granular whitelist rules.")
    await db.raw_execute(
        "INSERT INTO security_whitelist_rules (guild_id, target_id, target_type, scope, value, added_by, added_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, target_id, target_type, scope, value, added_by, time.time(), expires_at),
    )
    invalidate_rules(guild_id)
    return True


async def rule_remove(guild_id: int, target_id: int, scope: str, value: Optional[str] = None) -> int:
    if value is None:
        cur = await db.raw_execute(
            "DELETE FROM security_whitelist_rules WHERE guild_id=? AND target_id=? AND scope=?", (guild_id, target_id, scope)
        )
    else:
        cur = await db.raw_execute(
            "DELETE FROM security_whitelist_rules WHERE guild_id=? AND target_id=? AND scope=? AND value=?", (guild_id, target_id, scope, value)
        )
    invalidate_rules(guild_id)
    return cur.rowcount


async def rule_clear(guild_id: int, scope: Optional[str] = None) -> int:
    if scope is None:
        cur = await db.raw_execute("DELETE FROM security_whitelist_rules WHERE guild_id=?", (guild_id,))
    else:
        cur = await db.raw_execute("DELETE FROM security_whitelist_rules WHERE guild_id=? AND scope=?", (guild_id, scope))
    invalidate_rules(guild_id)
    return cur.rowcount


async def rule_list(guild_id: int, scope: Optional[str] = None) -> list[dict]:
    if scope is None:
        rows = await db.raw_fetch(
            "SELECT * FROM security_whitelist_rules WHERE guild_id=? ORDER BY scope, target_type, target_id, value", (guild_id,)
        )
    else:
        rows = await db.raw_fetch(
            "SELECT * FROM security_whitelist_rules WHERE guild_id=? AND scope=? ORDER BY target_type, target_id, value", (guild_id, scope)
        )
    return [dict(r) for r in rows]


async def rule_values(guild_id: int, scope: str, member: Optional[discord.abc.User] = None, channel: Optional[discord.abc.GuildChannel] = None) -> set[str]:
    rules = await _load_rules(guild_id)
    if not rules:
        return set()
    ids = set(_target_ids(member, channel))
    ids.add(guild_id)
    now = time.time()
    found: set[str] = set()
    for target_id, rule_scope, value in rules:
        if rule_scope == scope and target_id in ids:
            found.add(value)
            _used[("r", guild_id, target_id, scope, value)] = now
    return found


async def action_whitelisted(guild_id: int, action: str, actor_id: int, member: Optional[discord.abc.User] = None) -> bool:
    from utils import threat

    if threat.is_forced(guild_id):
        return False
    return bool(await rule_values(guild_id, f"antinuke.{action}", member or discord.Object(id=actor_id)))


def parse_expiry(token: str) -> Optional[float]:
    text = token.lower().strip()
    if len(text) < 2 or text[-1] not in "smhdw" or not text[:-1].isdigit():
        return None
    seconds = int(text[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[text[-1]]
    if seconds < 60 or seconds > 365 * 86400:
        return None
    return time.time() + seconds


def split_expiry(tokens: Iterable[str]) -> tuple[list[str], Optional[float]]:
    rest: list[str] = []
    expires: Optional[float] = None
    for token in tokens:
        parsed = parse_expiry(token)
        if parsed is not None and expires is None:
            expires = parsed
        else:
            rest.append(token)
    return rest, expires


async def set_expiry(guild_id: int, target_id: int, expires_at: Optional[float]) -> int:
    total = 0
    for table in ("security_whitelist", "security_whitelist_rules"):
        cur = await db.raw_execute(f"UPDATE {table} SET expires_at=? WHERE guild_id=? AND target_id=?", (expires_at, guild_id, target_id))
        total += cur.rowcount
    invalidate(guild_id)
    invalidate_rules(guild_id)
    return total


async def flush_usage() -> int:
    if not _used:
        return 0
    batch = dict(_used)
    _used.clear()
    for key, stamp in batch.items():
        if key[0] == "e":
            _, guild_id, target_id, scope = key
            await db.raw_execute(
                "UPDATE security_whitelist SET last_used=? WHERE guild_id=? AND target_id=? AND scope=?", (stamp, guild_id, target_id, scope)
            )
        else:
            _, guild_id, target_id, scope, value = key
            await db.raw_execute(
                "UPDATE security_whitelist_rules SET last_used=? WHERE guild_id=? AND target_id=? AND scope=? AND value=?",
                (stamp, guild_id, target_id, scope, value),
            )
    return len(batch)


async def purge_expired() -> list[dict]:
    now = time.time()
    removed: list[dict] = []
    for table in ("security_whitelist", "security_whitelist_rules"):
        rows = await db.raw_fetch(f"SELECT * FROM {table} WHERE expires_at IS NOT NULL AND expires_at<=?", (now,))
        for row in rows:
            entry = dict(row)
            entry["table"] = table
            removed.append(entry)
        if rows:
            await db.raw_execute(f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at<=?", (now,))
    for guild_id in {r["guild_id"] for r in removed}:
        invalidate(guild_id)
        invalidate_rules(guild_id)
    return removed


async def audit(guild_id: int, stale_days: int, soon_days: int = 7) -> dict[str, list[dict]]:
    await flush_usage()
    now = time.time()
    stale_before = now - stale_days * 86400
    report: dict[str, list[dict]] = {"unused": [], "stale": [], "expiring": []}
    for table in ("security_whitelist", "security_whitelist_rules"):
        rows = await db.raw_fetch(f"SELECT * FROM {table} WHERE guild_id=?", (guild_id,))
        for row in rows:
            entry = dict(row)
            entry["table"] = table
            added = entry.get("added_at") or now
            used = entry.get("last_used")
            expires = entry.get("expires_at")
            if expires and expires - now <= soon_days * 86400:
                report["expiring"].append(entry)
            if used is None and added < stale_before:
                report["unused"].append(entry)
            elif used is not None and used < stale_before:
                report["stale"].append(entry)
    return report
