import json
import secrets
import time
from typing import Optional

import config
from utils import db, guild_settings
from utils.ticket_pro import pack, unpack

KEYS = {
    "enabled": ("deepbackup_enabled", False),
    "hours": ("deepbackup_hours", 24),
}


async def get_config(guild_id: int) -> dict:
    return {name: await guild_settings.get(guild_id, key, default) for name, (key, default) in KEYS.items()}


async def set_config(guild_id: int, name: str, value) -> None:
    await guild_settings.set(guild_id, KEYS[name][0], value)


async def save(guild_id: int, data: dict, label: str, created_by: Optional[int], auto: bool, counts: dict) -> str:
    backup_id = secrets.token_hex(4)
    await db.raw_execute(
        "INSERT INTO deep_backups (backup_id, guild_id, label, created_by, created_at, auto, counts, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (backup_id, guild_id, label[:60], created_by, time.time(), 1 if auto else 0, json.dumps(counts), pack(json.dumps(data).encode())),
    )
    keep = config.DEEP_BACKUP_KEEP if auto else config.DEEP_BACKUP_MAX_MANUAL
    stale = await db.raw_fetch(
        "SELECT backup_id FROM deep_backups WHERE guild_id=? AND auto=? ORDER BY created_at DESC LIMIT -1 OFFSET ?",
        (guild_id, 1 if auto else 0, keep),
    )
    for row in stale:
        await db.raw_execute("DELETE FROM deep_backups WHERE backup_id=?", (row["backup_id"],))
    return backup_id


async def listing(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT backup_id, label, created_by, created_at, auto, counts FROM deep_backups WHERE guild_id=? ORDER BY created_at DESC LIMIT 30", (guild_id,))
    return [dict(r) for r in rows]


async def find(guild_id: int, backup_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM deep_backups WHERE guild_id=? AND backup_id=?", (guild_id, backup_id.strip().lower()))
    return dict(row) if row else None


def load(row: dict) -> dict:
    return json.loads(unpack(row["data"]))


async def delete(backup_id: str) -> None:
    await db.raw_execute("DELETE FROM deep_backups WHERE backup_id=?", (backup_id,))


async def last_auto(guild_id: int) -> float:
    row = await db.raw_fetchone("SELECT MAX(created_at) AS t FROM deep_backups WHERE guild_id=? AND auto=1", (guild_id,))
    return float(row["t"] or 0)


def describe_counts(counts: dict) -> str:
    return f"{counts.get('roles', 0)} roles, {counts.get('channels', 0)} channels, {counts.get('settings', 0)} settings, {counts.get('embeds', 0)} embeds, {counts.get('commands', 0)} custom commands"
