from __future__ import annotations

import html
import io
import json
import time
import uuid
from typing import Optional

import discord

import config
from utils import db


def new_id() -> str:
    return uuid.uuid4().hex[:8].upper()


def parse_ids(raw: Optional[str]) -> list[int]:
    try:
        return [int(r) for r in json.loads(raw or "[]")]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def parse_list(raw: Optional[str]) -> list:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


async def is_premium(guild_id: int) -> bool:
    row = await db.raw_fetchone(
        "SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild_id,)
    )
    if not row or not row["premium"]:
        return False
    expires = row["premium_expires_at"]
    return expires is None or expires > time.time()


async def limit_for(guild_id: int, key: str) -> int:
    tier = "premium" if await is_premium(guild_id) else "free"
    return config.TICKET_LIMITS[tier][key]


def premium_limit(key: str) -> int:
    return config.TICKET_LIMITS["premium"][key]


async def get_settings(guild_id: int) -> dict:
    row = await db.raw_fetchone("SELECT * FROM ticket_settings WHERE guild_id=?", (guild_id,))
    if row:
        return dict(row)
    return {"guild_id": guild_id, "log_channel_id": None, "max_open": 3, "auto_close_hours": 0, "counter": 0}


async def update_settings(guild_id: int, **fields) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO ticket_settings (guild_id) VALUES (?)", (guild_id,))
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE ticket_settings SET {column}=? WHERE guild_id=?", (value, guild_id))


async def next_number(guild_id: int) -> int:
    await db.raw_execute("INSERT OR IGNORE INTO ticket_settings (guild_id) VALUES (?)", (guild_id,))
    await db.raw_execute("UPDATE ticket_settings SET counter = counter + 1 WHERE guild_id=?", (guild_id,))
    row = await db.raw_fetchone("SELECT counter FROM ticket_settings WHERE guild_id=?", (guild_id,))
    return row["counter"]


async def get_panel(panel_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM ticket_panels WHERE panel_id=?", (panel_id,))
    return dict(row) if row else None


async def find_panel(guild_id: int, identifier: str) -> Optional[dict]:
    row = await db.raw_fetchone(
        "SELECT * FROM ticket_panels WHERE guild_id=? AND (panel_id=? OR LOWER(name)=LOWER(?))",
        (guild_id, identifier.upper(), identifier),
    )
    return dict(row) if row else None


async def list_panels(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM ticket_panels WHERE guild_id=? ORDER BY created_at", (guild_id,))
    return [dict(r) for r in rows]


async def create_panel(guild_id: int, name: str) -> str:
    panel_id = new_id()
    await db.raw_execute(
        "INSERT INTO ticket_panels (panel_id, guild_id, name, created_at) VALUES (?, ?, ?, ?)",
        (panel_id, guild_id, name, time.time()),
    )
    return panel_id


async def update_panel(panel_id: str, **fields) -> None:
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE ticket_panels SET {column}=? WHERE panel_id=?", (value, panel_id))


async def delete_panel(panel_id: str) -> None:
    await db.raw_execute("DELETE FROM ticket_panels WHERE panel_id=?", (panel_id,))


async def open_for_panel(panel_id: str) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM tickets WHERE panel_id=? AND status='open'", (panel_id,))
    return [dict(r) for r in rows]


async def active_count(guild_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND status='open'", (guild_id,))
    return row["n"] if row else 0


async def has_open_in_panel(panel_id: str, user_id: int) -> bool:
    row = await db.raw_fetchone(
        "SELECT 1 AS x FROM tickets WHERE panel_id=? AND owner_id=? AND status='open' LIMIT 1",
        (panel_id, user_id),
    )
    return row is not None


async def list_open(guild_id: int, limit: int) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT * FROM tickets WHERE guild_id=? AND status='open' ORDER BY created_at LIMIT ?",
        (guild_id, limit),
    )
    return [dict(r) for r in rows]


async def stats(guild_id: int) -> dict:
    totals = await db.raw_fetchone(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_count,"
        " SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed_count,"
        " SUM(CASE WHEN claimed_by IS NOT NULL THEN 1 ELSE 0 END) AS claimed_count"
        " FROM tickets WHERE guild_id=?",
        (guild_id,),
    )
    top = await db.raw_fetch(
        "SELECT claimed_by, COUNT(*) AS n FROM tickets WHERE guild_id=? AND claimed_by IS NOT NULL"
        " GROUP BY claimed_by ORDER BY n DESC LIMIT 5",
        (guild_id,),
    )
    return {
        "total": totals["total"] or 0,
        "open": totals["open_count"] or 0,
        "closed": totals["closed_count"] or 0,
        "claimed": totals["claimed_count"] or 0,
        "top": [(r["claimed_by"], r["n"]) for r in top],
    }


def pick_category(guild: discord.Guild, panel: dict) -> tuple[Optional[discord.CategoryChannel], bool]:
    best = None
    best_count = None
    configured = False
    for category_id in parse_ids(panel.get("category_ids")):
        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            continue
        configured = True
        count = len(category.channels)
        if count >= config.TICKET_CATEGORY_CHANNEL_CAP:
            continue
        if best is None or count < best_count:
            best, best_count = category, count
    return best, configured and best is None


_sessions: dict[tuple[int, int, str], dict] = {}


def _prune_sessions() -> None:
    now = time.monotonic()
    for key in [k for k, v in _sessions.items() if v["expires"] < now]:
        _sessions.pop(key, None)


def start_session(guild_id: int, user_id: int, panel_id: str) -> None:
    _prune_sessions()
    _sessions[(guild_id, user_id, panel_id)] = {
        "answers": {},
        "expires": time.monotonic() + config.TICKET_FORM_SESSION_TTL,
    }


def record_answers(guild_id: int, user_id: int, panel_id: str, entries: list[tuple[int, str, str]]) -> bool:
    session = _sessions.get((guild_id, user_id, panel_id))
    if session is None or session["expires"] < time.monotonic():
        return False
    for index, question, answer in entries:
        session["answers"][index] = {"question": question, "answer": answer}
    return True


def get_answers(guild_id: int, user_id: int, panel_id: str) -> list[dict]:
    session = _sessions.get((guild_id, user_id, panel_id))
    if session is None:
        return []
    return [session["answers"][i] for i in sorted(session["answers"])]


def clear_session(guild_id: int, user_id: int, panel_id: str) -> None:
    _sessions.pop((guild_id, user_id, panel_id), None)


async def get_ticket_by_channel(channel_id: int) -> Optional[dict]:
    row = await db.raw_fetchone(
        "SELECT * FROM tickets WHERE channel_id=? AND status='open'", (channel_id,)
    )
    return dict(row) if row else None


async def open_count(guild_id: int, user_id: int) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND owner_id=? AND status='open'",
        (guild_id, user_id),
    )
    return row["n"] if row else 0


async def open_channel_ids() -> set[int]:
    rows = await db.raw_fetch("SELECT channel_id FROM tickets WHERE status='open'")
    return {r["channel_id"] for r in rows}


async def create_ticket(
    guild_id: int, channel_id: int, owner_id: int, panel_id: str, number: int,
    subject: Optional[str], answers: Optional[list] = None,
) -> str:
    ticket_id = new_id()
    now = time.time()
    await db.raw_execute(
        "INSERT INTO tickets (ticket_id, guild_id, channel_id, owner_id, panel_id, number, subject, created_at, last_activity, answers)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, guild_id, channel_id, owner_id, panel_id, number, subject, now, now,
         json.dumps(answers) if answers else None),
    )
    return ticket_id


async def update_ticket(ticket_id: str, **fields) -> None:
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE tickets SET {column}=? WHERE ticket_id=?", (value, ticket_id))


async def touch(channel_id: int) -> None:
    await db.raw_execute(
        "UPDATE tickets SET last_activity=? WHERE channel_id=? AND status='open'",
        (time.time(), channel_id),
    )


async def stale_tickets(guild_id: int, hours: int) -> list[dict]:
    cutoff = time.time() - hours * 3600
    rows = await db.raw_fetch(
        "SELECT * FROM tickets WHERE guild_id=? AND status='open' AND COALESCE(last_activity, created_at) < ?",
        (guild_id, cutoff),
    )
    return [dict(r) for r in rows]


async def guilds_with_autoclose() -> list[dict]:
    rows = await db.raw_fetch("SELECT guild_id, auto_close_hours FROM ticket_settings WHERE auto_close_hours > 0")
    return [dict(r) for r in rows]


def is_staff(member: discord.Member, panel: Optional[dict]) -> bool:
    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild or perms.manage_channels:
        return True
    if member.id in config.ALL_PRIVILEGED_IDS:
        return True
    if panel is None:
        return False
    staff_ids = set(parse_ids(panel.get("staff_role_ids")))
    return any(role.id in staff_ids for role in member.roles)


def build_overwrites(guild: discord.Guild, owner: discord.Member, staff_roles: list[discord.Role]) -> dict:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_channels=True,
            manage_permissions=True, attach_files=True, embed_links=True,
        ),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True,
            embed_links=True, manage_messages=True,
        )
    return overwrites


async def build_transcript(channel: discord.abc.Messageable, title: str) -> bytes:
    rows = []
    async for message in channel.history(limit=config.TICKET_TRANSCRIPT_MESSAGE_LIMIT, oldest_first=True):
        if message.author.bot and not message.content and not message.attachments:
            continue
        stamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = html.escape(f"{message.author} ({message.author.id})")
        text = html.escape(message.clean_content or "")
        extras = "".join(
            f'<div class="att"><a href="{html.escape(a.url)}">{html.escape(a.filename)}</a></div>'
            for a in message.attachments
        )
        if message.embeds and not text:
            text = f"<i>{len(message.embeds)} embed(s)</i>"
        rows.append(
            f'<div class="msg"><div class="meta"><span class="who">{author}</span> <span class="ts">{stamp}</span></div>'
            f'<div class="body">{text.replace(chr(10), "<br>")}</div>{extras}</div>'
        )
    document = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + html.escape(title) + '</title><style>'
        "body{background:#1e1f22;color:#dbdee1;font-family:Segoe UI,Arial,sans-serif;margin:0;padding:24px}"
        "h1{font-size:20px;margin:0 0 16px}.msg{padding:8px 12px;border-left:3px solid #5865f2;margin-bottom:8px;background:#2b2d31;border-radius:4px}"
        ".who{font-weight:600;color:#fff}.ts{color:#949ba4;font-size:12px;margin-left:8px}.body{margin-top:4px;word-break:break-word}"
        ".att a{color:#00a8fc;font-size:13px}</style></head><body><h1>" + html.escape(title) + "</h1>"
        + "".join(rows) + "</body></html>"
    )
    return document.encode("utf-8")


def transcript_name(channel_id: int) -> str:
    return f"transcript-{channel_id}.html"


def transcript_file(data: bytes, channel_id: int) -> discord.File:
    return discord.File(io.BytesIO(data), filename=transcript_name(channel_id))
