import json
import time
import uuid
from typing import Optional

from utils import db, guild_settings

KEYS = {
    "enabled": ("report_enabled", True),
    "channel": ("report_channel_id", None),
    "role": ("report_ping_role_id", None),
    "threshold": ("report_alert_threshold", 3),
    "notify": ("report_notify_reporter", True),
    "daily": ("report_limit_day", 10),
}
OUTCOMES = {"warned": "Warned", "timeout": "Timed out", "banned": "Banned", "dismissed": "Dismissed", "deleted": "Message deleted"}
UPHELD = ("warned", "timeout", "banned", "deleted")


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    out["threshold"] = max(2, int(out["threshold"] or 3))
    out["daily"] = max(1, int(out["daily"] or 10))
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


def _row(row) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    for key in ("attachments", "context"):
        try:
            data[key] = json.loads(data.get(key) or "[]")
        except json.JSONDecodeError:
            data[key] = []
    return data


async def create(guild_id: int, reporter_id: int, target_id: int, reason: str, *, channel_id: Optional[int], message_id: Optional[int],
                 content: str, attachments: list, context: list, source: str = "message") -> str:
    report_id = uuid.uuid4().hex[:8].upper()
    await db.raw_execute(
        "INSERT INTO message_reports (report_id, guild_id, reporter_id, target_id, channel_id, message_id, content, attachments, context, reason, source, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
        (report_id, guild_id, reporter_id, target_id, channel_id, message_id, content[:1500], json.dumps(attachments[:6]), json.dumps(context[:12]), reason[:500], source, time.time()),
    )
    return report_id


async def get(guild_id: int, report_id: str) -> Optional[dict]:
    return _row(await db.raw_fetchone("SELECT * FROM message_reports WHERE guild_id=? AND report_id=?", (guild_id, report_id.upper())))


async def listing(guild_id: int, status: Optional[str] = "open", limit: int = 25) -> list[dict]:
    if status:
        rows = await db.raw_fetch("SELECT * FROM message_reports WHERE guild_id=? AND status=? ORDER BY created_at DESC LIMIT ?", (guild_id, status, limit))
    else:
        rows = await db.raw_fetch("SELECT * FROM message_reports WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, limit))
    return [_row(r) for r in rows]


async def duplicate(guild_id: int, reporter_id: int, message_id: int) -> bool:
    row = await db.raw_fetchone("SELECT 1 FROM message_reports WHERE guild_id=? AND reporter_id=? AND message_id=?", (guild_id, reporter_id, message_id))
    return row is not None


async def reporter_today(guild_id: int, reporter_id: int) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) AS c FROM message_reports WHERE guild_id=? AND reporter_id=? AND created_at>?", (guild_id, reporter_id, time.time() - 86400))
    return int(row["c"]) if row else 0


async def against(guild_id: int, target_id: int, since: float) -> dict:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) AS total, COUNT(DISTINCT reporter_id) AS reporters,"
        " SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count"
        " FROM message_reports WHERE guild_id=? AND target_id=? AND created_at>?", (guild_id, target_id, since))
    return {"total": int(row["total"] or 0), "reporters": int(row["reporters"] or 0), "open": int(row["open_count"] or 0)} if row else {"total": 0, "reporters": 0, "open": 0}


async def remember_review(report_id: str, channel_id: int, message_id: int) -> None:
    await db.raw_execute("UPDATE message_reports SET review_channel_id=?, review_message_id=? WHERE report_id=?", (channel_id, message_id, report_id))


async def remember_thread(report_id: str, thread_id: int) -> None:
    await db.raw_execute("UPDATE message_reports SET thread_id=? WHERE report_id=?", (thread_id, report_id))


async def resolve(report_id: str, status: str, outcome: str, handler_id: Optional[int]) -> None:
    await db.raw_execute(
        "UPDATE message_reports SET status=?, outcome=?, handler_id=?, handled_at=? WHERE report_id=?", (status, outcome, handler_id, time.time(), report_id))


async def received_counts(guild_id: int, user_id: int) -> dict:
    rows = await db.raw_fetch("SELECT outcome, status, COUNT(*) AS c FROM message_reports WHERE guild_id=? AND target_id=? GROUP BY outcome, status", (guild_id, user_id))
    upheld = sum(r["c"] for r in rows if r["outcome"] in UPHELD)
    open_count = sum(r["c"] for r in rows if r["status"] == "open")
    dismissed = sum(r["c"] for r in rows if r["outcome"] == "dismissed")
    return {"upheld": upheld, "open": open_count, "dismissed": dismissed}


async def false_reports(guild_id: int, reporter_id: int) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) AS c FROM message_reports WHERE guild_id=? AND reporter_id=? AND outcome='dismissed' AND source='message'", (guild_id, reporter_id))
    return int(row["c"]) if row else 0
