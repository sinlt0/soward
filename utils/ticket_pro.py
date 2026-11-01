import base64
import re
import time
import zlib
from typing import Optional

import config
from utils import db

NAME = re.compile(r"^[a-z0-9_-]{1,30}$")


async def canned_list(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM ticket_canned WHERE guild_id=? ORDER BY name", (guild_id,))
    return [dict(r) for r in rows]


async def canned_get(guild_id: int, name: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM ticket_canned WHERE guild_id=? AND name=?", (guild_id, name.lower()))
    return dict(row) if row else None


async def canned_set(guild_id: int, name: str, content: str, user_id: int) -> None:
    await db.raw_execute(
        "INSERT INTO ticket_canned (guild_id, name, content, created_by) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, name) DO UPDATE SET content=excluded.content, created_by=excluded.created_by",
        (guild_id, name.lower(), content, user_id),
    )


async def canned_delete(guild_id: int, name: str) -> bool:
    row = await canned_get(guild_id, name)
    if row is None:
        return False
    await db.raw_execute("DELETE FROM ticket_canned WHERE guild_id=? AND name=?", (guild_id, name.lower()))
    return True


async def save_rating(ticket: dict, user_id: int, rating: int) -> bool:
    if await db.raw_fetchone("SELECT 1 FROM ticket_ratings WHERE ticket_id=?", (ticket["ticket_id"],)):
        return False
    await db.raw_execute(
        "INSERT INTO ticket_ratings (ticket_id, guild_id, user_id, staff_id, rating, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket["ticket_id"], ticket["guild_id"], user_id, ticket.get("claimed_by"), rating, time.time()),
    )
    return True


async def rating_stats(guild_id: int, days: int = 90) -> dict:
    since = time.time() - days * 86400
    total = await db.raw_fetchone("SELECT COUNT(*) AS n, AVG(rating) AS avg FROM ticket_ratings WHERE guild_id=? AND created_at>=?", (guild_id, since))
    spread = await db.raw_fetch("SELECT rating, COUNT(*) AS n FROM ticket_ratings WHERE guild_id=? AND created_at>=? GROUP BY rating", (guild_id, since))
    staff = await db.raw_fetch(
        "SELECT staff_id, COUNT(*) AS n, AVG(rating) AS avg FROM ticket_ratings WHERE guild_id=? AND created_at>=? AND staff_id IS NOT NULL "
        "GROUP BY staff_id ORDER BY avg DESC, n DESC LIMIT 10",
        (guild_id, since),
    )
    return {
        "count": int(total["n"]),
        "avg": float(total["avg"] or 0),
        "spread": {int(r["rating"]): int(r["n"]) for r in spread},
        "staff": [(int(r["staff_id"]), int(r["n"]), float(r["avg"])) for r in staff],
    }


def pack(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 9)).decode("ascii")


def unpack(text: str) -> bytes:
    return zlib.decompress(base64.b64decode(text))


async def archive(ticket: dict, data: bytes) -> bool:
    packed = pack(data)
    if len(packed) > config.TICKET_ARCHIVE_MAX_BYTES:
        return False
    await db.raw_execute(
        "INSERT OR REPLACE INTO ticket_transcripts (ticket_id, guild_id, number, owner_id, closed_at, data) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket["ticket_id"], ticket["guild_id"], ticket["number"], ticket["owner_id"], time.time(), packed),
    )
    stale = await db.raw_fetch(
        "SELECT ticket_id FROM ticket_transcripts WHERE guild_id=? ORDER BY closed_at DESC LIMIT -1 OFFSET ?",
        (ticket["guild_id"], config.TICKET_ARCHIVE_KEEP),
    )
    for row in stale:
        await db.raw_execute("DELETE FROM ticket_transcripts WHERE ticket_id=?", (row["ticket_id"],))
    return True


async def archive_list(guild_id: int, limit: int = 20) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT ticket_id, number, owner_id, closed_at FROM ticket_transcripts WHERE guild_id=? ORDER BY closed_at DESC LIMIT ?", (guild_id, limit)
    )
    return [dict(r) for r in rows]


async def archive_get(guild_id: int, number: int) -> Optional[tuple[dict, bytes]]:
    row = await db.raw_fetchone("SELECT * FROM ticket_transcripts WHERE guild_id=? AND number=?", (guild_id, number))
    if row is None:
        return None
    return dict(row), unpack(row["data"])
