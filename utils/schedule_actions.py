import json
import re
import time
import uuid
from typing import Optional

import config
from utils import db, scheduler

KINDS = ("say", "lock", "unlock", "role_add", "role_remove")
GRACE = 600
REPEAT_NAMES = {"daily": 86400, "weekly": 7 * 86400, "hourly": 3600}


def parse_repeat(text: str) -> Optional[int]:
    word = (text or "").strip().lower()
    if word in REPEAT_NAMES:
        return REPEAT_NAMES[word]
    match = re.fullmatch(r"(?:every)?(\d+)\s*([a-z]+)", word)
    if not match or match.group(2) not in scheduler.UNITS:
        return None
    seconds = int(match.group(1)) * scheduler.UNITS[match.group(2)]
    return seconds if seconds >= config.SCHEDULE_MIN_REPEAT else None


def split_repeat(text: str) -> tuple[str, Optional[int]]:
    match = re.search(r"\s+repeat\s+(daily|weekly|hourly|(?:every)?\d+\s*[a-z]+)\s*$", text, re.I)
    if not match:
        return text.strip(), 0
    seconds = parse_repeat(match.group(1))
    return text[: match.start()].strip(), seconds


async def tz_for(guild_id: int):
    cfg = await scheduler.get_config(guild_id)
    return scheduler.parse_tz(cfg["timezone"]) or scheduler.parse_tz("UTC"), cfg["timezone"]


async def count(guild_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM scheduled_actions WHERE guild_id=?", (guild_id,))
    return int(row["n"])


async def create(guild_id: int, created_by: int, kind: str, run_at: float, repeat: int, payload: dict) -> str:
    action_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute(
        "INSERT INTO scheduled_actions (action_id, guild_id, kind, run_at, repeat_seconds, payload, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (action_id, guild_id, kind, run_at, repeat, json.dumps(payload), created_by, time.time()),
    )
    return action_id


async def get(guild_id: int, action_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM scheduled_actions WHERE guild_id=? AND action_id=?", (guild_id, action_id.strip().upper()))
    return dict(row) if row else None


async def listing(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM scheduled_actions WHERE guild_id=? ORDER BY run_at", (guild_id,))
    return [dict(r) for r in rows]


async def delete(action_id: str) -> None:
    await db.raw_execute("DELETE FROM scheduled_actions WHERE action_id=?", (action_id,))


async def due(now: float) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM scheduled_actions WHERE run_at<=? ORDER BY run_at LIMIT 100", (now,))
    return [dict(r) for r in rows]


def next_run(run_at: float, repeat: int, now: float) -> float:
    if repeat <= 0:
        return run_at
    steps = int((now - run_at) // repeat) + 1
    return run_at + steps * repeat


async def finish(row: dict, now: float, error: Optional[str]) -> None:
    repeat = int(row["repeat_seconds"] or 0)
    if repeat <= 0:
        await delete(row["action_id"])
        return
    await db.raw_execute(
        "UPDATE scheduled_actions SET run_at=?, last_run=?, runs=runs+1, last_error=? WHERE action_id=?",
        (next_run(float(row["run_at"]), repeat, now), now, error, row["action_id"]),
    )


def describe(row: dict) -> str:
    payload = json.loads(row["payload"] or "{}")
    kind = row["kind"]
    if kind == "say":
        target = f"<#{payload.get('channel_id')}>"
        return f"post in {target}: {str(payload.get('text', ''))[:60]}"
    if kind in ("lock", "unlock"):
        return f"{kind} <#{payload.get('channel_id')}>"
    verb = "give" if kind == "role_add" else "remove"
    prep = "to" if kind == "role_add" else "from"
    return f"{verb} <@&{payload.get('role_id')}> {prep} <@{payload.get('user_id')}>"


def every(seconds: int) -> str:
    for name, size in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds % size == 0:
            n = seconds // size
            return f"every {name}" if n == 1 else f"every {n} {name}s"
    return f"every {seconds}s"
