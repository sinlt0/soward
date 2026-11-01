import json
import time
import uuid
from typing import Optional

import config
from utils import db, guild_settings

DEFAULT_QUESTIONS = (
    "Why were you banned, in your own words?",
    "Why should we lift your ban?",
    "What will you do differently if you come back?",
)
MAX_QUESTIONS = 5
MAX_QUESTION = 200
MAX_ANSWER = 1000
STATUS_LABELS = {"pending": "Pending", "accepted": "Accepted", "denied": "Denied", "withdrawn": "Withdrawn"}
KEYS = {
    "enabled": ("appeal_enabled", True),
    "channel": ("appeal_channel_id", None),
    "questions": ("appeal_questions", None),
    "votes": ("appeal_votes_needed", 1),
    "cooldown": ("appeal_cooldown_days", 7),
    "notice": ("appeal_notice", ""),
    "role": ("appeal_ping_role_id", None),
    "rejoin": ("appeal_rejoin_channel_id", None),
    "show_reason": ("appeal_show_reason", True),
    "dm": ("appeal_dm", True),
}


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    questions = out["questions"]
    if not isinstance(questions, list) or not [q for q in questions if str(q).strip()]:
        out["questions"] = list(DEFAULT_QUESTIONS)
    else:
        out["questions"] = [str(q).strip()[:MAX_QUESTION] for q in questions if str(q).strip()][:MAX_QUESTIONS]
    out["votes"] = max(1, int(out["votes"] or 1))
    out["cooldown"] = max(0, int(out["cooldown"] if out["cooldown"] is not None else 7))
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


def appeal_url(guild_id: int) -> str:
    return f"{config.DASHBOARD_URL}/appeal/{guild_id}" if config.DASHBOARD_URL else ""


def ban_reason_text(raw: Optional[str]) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if " | " in text:
        text = text.split(" | ", 1)[1].strip()
    return text[:300]


async def create(guild_id: int, user_id: int, user_name: str, answers: list[dict], ban_reason: str) -> str:
    appeal_id = uuid.uuid4().hex[:8].upper()
    await db.raw_execute(
        "INSERT INTO ban_appeals (appeal_id, guild_id, user_id, user_name, answers, ban_reason, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (appeal_id, guild_id, user_id, user_name[:80], json.dumps(answers), ban_reason[:300], time.time()),
    )
    return appeal_id


def _row(row) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    try:
        data["answers"] = json.loads(data.get("answers") or "[]")
    except json.JSONDecodeError:
        data["answers"] = []
    return data


async def get(guild_id: int, appeal_id: str) -> Optional[dict]:
    return _row(await db.raw_fetchone("SELECT * FROM ban_appeals WHERE guild_id=? AND appeal_id=?", (guild_id, appeal_id.upper())))


async def latest_for(guild_id: int, user_id: int) -> Optional[dict]:
    return _row(await db.raw_fetchone(
        "SELECT * FROM ban_appeals WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1", (guild_id, user_id)))


async def listing(guild_id: int, status: Optional[str] = "pending", limit: int = 25) -> list[dict]:
    if status:
        rows = await db.raw_fetch(
            "SELECT * FROM ban_appeals WHERE guild_id=? AND status=? ORDER BY created_at DESC LIMIT ?", (guild_id, status, limit))
    else:
        rows = await db.raw_fetch("SELECT * FROM ban_appeals WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, limit))
    return [_row(r) for r in rows]


async def waiting_state(guild_id: int, user_id: int, cooldown_days: int) -> Optional[tuple[str, Optional[float]]]:
    last = await latest_for(guild_id, user_id)
    if last is None:
        return None
    if last["status"] == "pending":
        return "pending", None
    if last["status"] == "denied" and cooldown_days and last["decided_at"]:
        ready = last["decided_at"] + cooldown_days * 86400
        if time.time() < ready:
            return "cooldown", ready
    return None


async def set_vote(appeal_id: str, user_id: int, vote: int) -> None:
    await db.raw_execute(
        "INSERT INTO appeal_votes (appeal_id, user_id, vote) VALUES (?, ?, ?)"
        " ON CONFLICT(appeal_id, user_id) DO UPDATE SET vote=excluded.vote", (appeal_id, user_id, vote))


async def votes(appeal_id: str) -> tuple[int, int]:
    rows = await db.raw_fetch("SELECT vote, COUNT(*) AS c FROM appeal_votes WHERE appeal_id=? GROUP BY vote", (appeal_id,))
    counts = {r["vote"]: r["c"] for r in rows}
    return counts.get(1, 0), counts.get(-1, 0)


async def finish(appeal_id: str, status: str, reviewer_id: Optional[int], note: str) -> None:
    await db.raw_execute(
        "UPDATE ban_appeals SET status=?, reviewer_id=?, decision_note=?, decided_at=? WHERE appeal_id=?",
        (status, reviewer_id, note[:500], time.time(), appeal_id))


async def remember_message(appeal_id: str, channel_id: int, message_id: int) -> None:
    await db.raw_execute("UPDATE ban_appeals SET channel_id=?, message_id=? WHERE appeal_id=?", (channel_id, message_id, appeal_id))
