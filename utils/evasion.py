import json
import re
import time
import uuid
from difflib import SequenceMatcher
from typing import Optional

from utils import db, guild_settings

KEYS = {
    "enabled": ("evasion_enabled", True),
    "channel": ("evasion_channel_id", None),
    "threshold": ("evasion_threshold", 60),
    "action": ("evasion_action", "none"),
}
ACTIONS = ("none", "timeout", "kick")
WINDOW_DAYS = 120


def name_key(name: Optional[str]) -> str:
    return re.sub(r"[\d_.\-\s]+", "", str(name or "").lower())


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    out["threshold"] = max(30, min(100, int(out["threshold"] or 60)))
    if out["action"] not in ACTIONS:
        out["action"] = "none"
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


def score(candidate: dict, banned: dict) -> tuple[int, list[str]]:
    points, why = 0, []
    if candidate.get("avatar") and candidate["avatar"] == banned.get("avatar"):
        points += 50
        why.append("same custom avatar")
    names = [n for n in (candidate.get("name_key"), candidate.get("global_key")) if n and len(n) >= 3]
    others = [n for n in (banned.get("name_key"), banned.get("global_key")) if n and len(n) >= 3]
    best = 0.0
    for a in names:
        for b in others:
            best = max(best, 1.0 if a == b else SequenceMatcher(None, a, b).ratio())
    if best >= 0.999:
        points += 30
        why.append("same name apart from numbers")
    elif best >= 0.85:
        points += 18
        why.append("very similar name")
    if candidate.get("invite") and candidate["invite"] == banned.get("invite"):
        points += 15
        why.append(f"same invite `{candidate['invite']}`")
    created, banned_at = candidate.get("account_created"), banned.get("banned_at")
    if created and banned_at and created > banned_at:
        points += 10
        why.append("account made after the ban")
    return min(points, 100), why


async def remember_ban(guild_id: int, user_id: int, *, name: str, global_name: Optional[str], avatar: Optional[str],
                       account_created: Optional[float], invite: Optional[str], reason: Optional[str]) -> None:
    await db.raw_execute(
        "INSERT INTO ban_fingerprints (guild_id, user_id, name, name_key, global_key, avatar, account_created, invite, reason, banned_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET name=excluded.name, name_key=excluded.name_key, global_key=excluded.global_key, avatar=excluded.avatar,"
        " account_created=excluded.account_created, invite=COALESCE(excluded.invite, ban_fingerprints.invite), reason=excluded.reason",
        (guild_id, user_id, name[:80], name_key(name), name_key(global_name), avatar, account_created, invite, (reason or "")[:200], time.time()))


async def forget_ban(guild_id: int, user_id: int) -> None:
    await db.raw_execute("DELETE FROM ban_fingerprints WHERE guild_id=? AND user_id=?", (guild_id, user_id))


async def banned_profiles(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM ban_fingerprints WHERE guild_id=?", (guild_id,))
    return [dict(r) for r in rows]


async def matches(guild_id: int, candidate: dict, threshold: int) -> list[tuple[int, dict, list[str]]]:
    out = []
    for banned in await banned_profiles(guild_id):
        if banned["user_id"] == candidate["user_id"]:
            continue
        points, why = score(candidate, banned)
        if points >= threshold:
            out.append((points, banned, why))
    return sorted(out, key=lambda x: -x[0])


async def dismissed(guild_id: int, user_id: int, banned_id: int) -> bool:
    row = await db.raw_fetchone(
        "SELECT 1 FROM evasion_links WHERE guild_id=? AND user_id=? AND banned_id=? AND status='dismissed'", (guild_id, user_id, banned_id))
    return row is not None


async def create_link(guild_id: int, user_id: int, banned_id: int, points: int, reasons: list[str]) -> str:
    link_id = uuid.uuid4().hex[:8].upper()
    await db.raw_execute(
        "INSERT INTO evasion_links (link_id, guild_id, user_id, banned_id, score, reasons, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
        (link_id, guild_id, user_id, banned_id, points, json.dumps(reasons), time.time()))
    return link_id


async def get_link(guild_id: int, link_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM evasion_links WHERE guild_id=? AND link_id=?", (guild_id, link_id.upper()))
    if row is None:
        return None
    data = dict(row)
    data["reasons"] = json.loads(data["reasons"] or "[]")
    return data


async def remember_message(link_id: str, channel_id: int, message_id: int) -> None:
    await db.raw_execute("UPDATE evasion_links SET channel_id=?, message_id=? WHERE link_id=?", (channel_id, message_id, link_id))


async def resolve(link_id: str, status: str, handler_id: int) -> None:
    await db.raw_execute("UPDATE evasion_links SET status=?, handler_id=?, handled_at=? WHERE link_id=?", (status, handler_id, time.time(), link_id))


async def recent_links(guild_id: int, limit: int = 15) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM evasion_links WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, limit))
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        out.append(d)
    return out
