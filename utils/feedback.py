import hashlib
import re
import secrets
import time
import uuid
from collections import Counter
from typing import Optional

from utils import db, guild_settings

KEYS = {
    "enabled": ("feedback_enabled", False),
    "channel": ("feedback_channel_id", None),
}
DAILY_LIMIT = 3
STOP = set("the a an and or but to of in on at for is are was were be been it this that with as my me i you we they he she not no so if do did does have has had from by about just very really would could should can will than then them their there what when where who how too also more some any".split())


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


async def author_hash(guild_id: int, user_id: int) -> str:
    salt = await guild_settings.get(guild_id, "feedback_salt", None)
    if not salt:
        salt = secrets.token_hex(16)
        await guild_settings.set(guild_id, "feedback_salt", salt)
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:24]


async def blocked(guild_id: int, digest: str) -> bool:
    return digest in (await guild_settings.get(guild_id, "feedback_blocked", []) or [])


async def block(guild_id: int, digest: str) -> None:
    current = list(await guild_settings.get(guild_id, "feedback_blocked", []) or [])
    if digest not in current:
        current.append(digest)
        await guild_settings.set(guild_id, "feedback_blocked", current[-500:])


async def sent_today(guild_id: int, digest: str) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) AS c FROM staff_feedback WHERE guild_id=? AND author_hash=? AND created_at>?", (guild_id, digest, time.time() - 86400))
    return int(row["c"]) if row else 0


async def create(guild_id: int, digest: str, topic: str, about: str, body: str) -> str:
    feedback_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute(
        "INSERT INTO staff_feedback (feedback_id, guild_id, author_hash, topic, about, body, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'new', ?)",
        (feedback_id, guild_id, digest, topic[:60], about[:80], body[:1500], time.time()))
    return feedback_id


async def get(guild_id: int, feedback_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM staff_feedback WHERE guild_id=? AND feedback_id=?", (guild_id, feedback_id.upper()))
    return dict(row) if row else None


async def remember_message(feedback_id: str, channel_id: int, message_id: int) -> None:
    await db.raw_execute("UPDATE staff_feedback SET channel_id=?, message_id=? WHERE feedback_id=?", (channel_id, message_id, feedback_id))


async def resolve(feedback_id: str, handler_id: int) -> None:
    await db.raw_execute("UPDATE staff_feedback SET status='resolved', handler_id=?, handled_at=? WHERE feedback_id=?", (handler_id, time.time(), feedback_id))


async def since(guild_id: int, ts: float) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM staff_feedback WHERE guild_id=? AND created_at>? ORDER BY created_at DESC", (guild_id, ts))
    return [dict(r) for r in rows]


def summarize(rows: list[dict]) -> dict:
    about = Counter(r["about"].strip().lower() for r in rows if r["about"] and r["about"].strip())
    words = Counter()
    for r in rows:
        for w in set(re.findall(r"[a-z']{4,}", r["body"].lower())):
            if w not in STOP:
                words[w] += 1
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "new"),
        "topics": Counter(r["topic"].strip().lower() for r in rows if r["topic"]).most_common(5),
        "about": [(k, v) for k, v in about.most_common(5) if v >= 2],
        "themes": [(k, v) for k, v in words.most_common(8) if v >= 2],
    }
