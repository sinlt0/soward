import time
import uuid
from datetime import datetime
from typing import Optional

from utils import db, guild_settings, scheduler, staff_stats

KEYS = {
    "enabled": ("shift_enabled", False),
    "channel": ("shift_channel_id", None),
    "role": ("shift_role_id", None),
    "staff_role": ("shift_staff_role_id", None),
    "coverage_start": ("shift_coverage_start", None),
    "coverage_end": ("shift_coverage_end", None),
    "coverage_min": ("shift_coverage_min", 1),
}
MAX_SHIFT = 12 * 3600
ALERT_GAP = 7200


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


async def active(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM staff_shifts WHERE guild_id=? AND user_id=? AND ended_at IS NULL", (guild_id, user_id))
    return dict(row) if row else None


async def on_duty(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM staff_shifts WHERE guild_id=? AND ended_at IS NULL ORDER BY started_at", (guild_id,))
    return [dict(r) for r in rows]


async def start(guild_id: int, user_id: int) -> str:
    shift_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute("INSERT INTO staff_shifts (shift_id, guild_id, user_id, started_at, notes) VALUES (?, ?, ?, ?, '')", (shift_id, guild_id, user_id, time.time()))
    return shift_id


async def add_note(shift_id: str, text: str) -> None:
    row = await db.raw_fetchone("SELECT notes FROM staff_shifts WHERE shift_id=?", (shift_id,))
    current = (row["notes"] if row else "") or ""
    joined = (current + "\n" + text.strip()).strip()
    await db.raw_execute("UPDATE staff_shifts SET notes=? WHERE shift_id=?", (joined[-1500:], shift_id))


async def end(shift_id: str, auto: bool = False) -> Optional[dict]:
    await db.raw_execute("UPDATE staff_shifts SET ended_at=?, auto_ended=? WHERE shift_id=? AND ended_at IS NULL", (time.time(), 1 if auto else 0, shift_id))
    row = await db.raw_fetchone("SELECT * FROM staff_shifts WHERE shift_id=?", (shift_id,))
    return dict(row) if row else None


async def activity(guild_id: int, shift: dict) -> dict:
    stats = await staff_stats.collect(guild_id, shift["started_at"], shift.get("ended_at") or time.time())
    return stats.get(int(shift["user_id"]), {f: 0 for f in staff_stats.FIELDS})


async def open_work(guild_id: int) -> dict:
    queries = {
        "reports": "SELECT COUNT(*) AS c FROM message_reports WHERE guild_id=? AND status='open'",
        "appeals": "SELECT COUNT(*) AS c FROM ban_appeals WHERE guild_id=? AND status='pending'",
        "tickets": "SELECT COUNT(*) AS c FROM tickets WHERE guild_id=? AND status='open'",
        "applications": "SELECT COUNT(*) AS c FROM app_submissions WHERE guild_id=? AND status='pending'",
    }
    out = {}
    for name, sql in queries.items():
        try:
            row = await db.raw_fetchone(sql, (guild_id,))
            out[name] = int(row["c"]) if row else 0
        except Exception:
            out[name] = 0
    return out


async def recent(guild_id: int, user_id: Optional[int] = None, limit: int = 10) -> list[dict]:
    if user_id:
        rows = await db.raw_fetch("SELECT * FROM staff_shifts WHERE guild_id=? AND user_id=? AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT ?", (guild_id, user_id, limit))
    else:
        rows = await db.raw_fetch("SELECT * FROM staff_shifts WHERE guild_id=? AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT ?", (guild_id, limit))
    return [dict(r) for r in rows]


async def last_handover(guild_id: int, exclude_user: Optional[int] = None) -> Optional[dict]:
    for row in await recent(guild_id, limit=10):
        if row["notes"] and row["user_id"] != exclude_user:
            return row
    return None


async def totals(guild_id: int, since: float) -> list[tuple[int, int, int]]:
    rows = await db.raw_fetch(
        "SELECT user_id, COUNT(*) AS n, SUM(COALESCE(ended_at, ?) - started_at) AS secs FROM staff_shifts WHERE guild_id=? AND started_at>=? GROUP BY user_id ORDER BY secs DESC",
        (time.time(), guild_id, since))
    return [(int(r["user_id"]), int(r["n"]), int(r["secs"] or 0)) for r in rows]


async def stale() -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM staff_shifts WHERE ended_at IS NULL AND started_at<?", (time.time() - MAX_SHIFT,))
    return [dict(r) for r in rows]


def parse_hour(text: str) -> Optional[int]:
    text = text.strip().lower().replace(":00", "")
    try:
        if text.endswith(("am", "pm")):
            hour = int(text[:-2]) % 12 + (12 if text.endswith("pm") else 0)
        else:
            hour = int(text)
    except ValueError:
        return None
    return hour if 0 <= hour <= 24 else None


def in_window(start_hour: int, end_hour: int, hour: int) -> bool:
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


async def local_hour(guild_id: int) -> int:
    cfg = await scheduler.get_config(guild_id)
    tz = scheduler.parse_tz(cfg["timezone"]) or scheduler.parse_tz("UTC")
    return datetime.now(tz).hour


def span(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
