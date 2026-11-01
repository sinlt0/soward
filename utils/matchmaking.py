import time
import uuid
from typing import Optional

from utils import db, guild_settings

KEYS = {
    "enabled": ("match_enabled", False),
    "channel": ("match_channel_id", None),
    "category": ("match_category_id", None),
    "role": ("match_role_id", None),
    "age": ("match_min_account_days", 7),
    "minutes": ("match_minutes", 10),
}
REPEAT_DAYS = 7


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    out["age"] = max(0, int(out["age"] or 0))
    out["minutes"] = max(3, min(60, int(out["minutes"] or 10)))
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


async def queue(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, joined_at FROM match_queue WHERE guild_id=? ORDER BY joined_at", (guild_id,))
    return [dict(r) for r in rows]


async def in_queue(guild_id: int, user_id: int) -> bool:
    return await db.raw_fetchone("SELECT 1 FROM match_queue WHERE guild_id=? AND user_id=?", (guild_id, user_id)) is not None


async def join(guild_id: int, user_id: int) -> None:
    await db.raw_execute(
        "INSERT INTO match_queue (guild_id, user_id, joined_at) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET joined_at=excluded.joined_at",
        (guild_id, user_id, time.time()))


async def leave(guild_id: int, user_id: int) -> None:
    await db.raw_execute("DELETE FROM match_queue WHERE guild_id=? AND user_id=?", (guild_id, user_id))


async def active_for(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone(
        "SELECT * FROM match_sessions WHERE guild_id=? AND status='active' AND (user_a=? OR user_b=?)", (guild_id, user_id, user_id))
    return dict(row) if row else None


async def active(guild_id: Optional[int] = None) -> list[dict]:
    if guild_id is None:
        rows = await db.raw_fetch("SELECT * FROM match_sessions WHERE status='active'")
    else:
        rows = await db.raw_fetch("SELECT * FROM match_sessions WHERE guild_id=? AND status='active'", (guild_id,))
    return [dict(r) for r in rows]


async def get_session(session_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM match_sessions WHERE session_id=?", (session_id,))
    return dict(row) if row else None


async def create_session(guild_id: int, a: int, b: int, voice_id: int, minutes: int) -> str:
    session_id = uuid.uuid4().hex[:8].upper()
    now = time.time()
    await db.raw_execute(
        "INSERT INTO match_sessions (session_id, guild_id, user_a, user_b, voice_id, channel_id, started_at, ends_at, status, extended)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0)", (session_id, guild_id, a, b, voice_id, voice_id, now, now + minutes * 60))
    return session_id


async def remember_message(session_id: str, message_id: int) -> None:
    await db.raw_execute("UPDATE match_sessions SET message_id=? WHERE session_id=?", (message_id, session_id))


async def choose(session: dict, user_id: int, choice: int) -> dict:
    column = "choice_a" if session["user_a"] == user_id else "choice_b"
    await db.raw_execute(f"UPDATE match_sessions SET {column}=? WHERE session_id=?", (choice, session["session_id"]))
    return await get_session(session["session_id"])


async def extend(session_id: str, seconds: int) -> None:
    await db.raw_execute("UPDATE match_sessions SET ends_at=ends_at+?, extended=1 WHERE session_id=?", (seconds, session_id))


async def finish(session_id: str, status: str = "ended") -> None:
    await db.raw_execute("UPDATE match_sessions SET status=? WHERE session_id=?", (status, session_id))


async def block(guild_id: int, user_id: int, blocked_id: int) -> None:
    await db.raw_execute(
        "INSERT INTO match_blocks (guild_id, user_id, blocked_id, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, blocked_id) DO NOTHING",
        (guild_id, user_id, blocked_id, time.time()))


async def unblock(guild_id: int, user_id: int, blocked_id: int) -> None:
    await db.raw_execute("DELETE FROM match_blocks WHERE guild_id=? AND user_id=? AND blocked_id=?", (guild_id, user_id, blocked_id))


async def blocks(guild_id: int) -> set[tuple[int, int]]:
    rows = await db.raw_fetch("SELECT user_id, blocked_id FROM match_blocks WHERE guild_id=?", (guild_id,))
    pairs = set()
    for r in rows:
        pairs.add((r["user_id"], r["blocked_id"]))
        pairs.add((r["blocked_id"], r["user_id"]))
    return pairs


async def recent_pairs(guild_id: int) -> set[tuple[int, int]]:
    rows = await db.raw_fetch(
        "SELECT user_a, user_b FROM match_sessions WHERE guild_id=? AND started_at>?", (guild_id, time.time() - REPEAT_DAYS * 86400))
    pairs = set()
    for r in rows:
        pairs.add((r["user_a"], r["user_b"]))
        pairs.add((r["user_b"], r["user_a"]))
    return pairs


async def blocked_list(guild_id: int, user_id: int) -> list[int]:
    rows = await db.raw_fetch("SELECT blocked_id FROM match_blocks WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return [r["blocked_id"] for r in rows]


def pick_pairs(entries: list[dict], interests: dict[int, list[str]], banned: set[tuple[int, int]]) -> list[tuple[int, int]]:
    waiting = [e["user_id"] for e in sorted(entries, key=lambda e: e["joined_at"])]
    pairs: list[tuple[int, int]] = []
    used: set[int] = set()
    for a in waiting:
        if a in used:
            continue
        best, best_score = None, -1
        for b in waiting:
            if b == a or b in used or (a, b) in banned:
                continue
            score = len(set(interests.get(a, [])) & set(interests.get(b, [])))
            if score > best_score:
                best, best_score = b, score
        if best is not None:
            pairs.append((a, best))
            used.update((a, best))
    return pairs
