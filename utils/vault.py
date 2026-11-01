import csv
import io
import json
import re
import time
from typing import Optional

import config
from utils import db, premium_limits

MENTION = re.compile(r"^<@!?(\d+)>$|^(\d{15,20})$")
FILTERS = ("user", "by", "action", "days")
SKIP_KEYS = {"guild_id", "action", "user_id", "moderator_id", "actor_id", "channel_id"}


async def retention_days(guild_id: int) -> int:
    free, paid = config.VAULT_RETENTION_DAYS
    return paid if await premium_limits.is_premium(guild_id) else free


def _int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _detail(kwargs: dict) -> str:
    parts = {}
    for key, value in kwargs.items():
        if key in SKIP_KEYS or value is None or value == "":
            continue
        parts[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    return json.dumps(parts, ensure_ascii=False)[: config.VAULT_DETAIL_MAX]


async def record(guild_id: int, action: str, **kwargs) -> None:
    actor = kwargs.get("moderator_id")
    if actor is None:
        actor = kwargs.get("actor_id")
    await db.raw_execute(
        "INSERT INTO vault_entries (guild_id, action, user_id, actor_id, channel_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, str(action)[:60], _int(kwargs.get("user_id")), _int(actor), _int(kwargs.get("channel_id")), _detail(kwargs), time.time()),
    )


async def prune() -> None:
    free, paid = config.VAULT_RETENTION_DAYS
    now = time.time()
    await db.raw_execute(
        "DELETE FROM vault_entries WHERE created_at<? AND guild_id NOT IN "
        "(SELECT guild_id FROM guilds WHERE premium=1 AND (premium_expires_at IS NULL OR premium_expires_at>?))",
        (now - free * 86400, now),
    )
    await db.raw_execute("DELETE FROM vault_entries WHERE created_at<?", (now - paid * 86400,))


def parse_query(text: str) -> tuple[dict, list[str]]:
    found: dict = {}
    problems: list[str] = []
    for token in (text or "").split():
        name, _, value = token.partition(":")
        name = name.lower()
        if name not in FILTERS or not value:
            problems.append(token)
            continue
        if name in ("user", "by"):
            match = MENTION.match(value)
            if not match:
                problems.append(token)
                continue
            found[name] = int(match.group(1) or match.group(2))
        elif name == "days":
            if not value.isdigit() or not 1 <= int(value) <= 365:
                problems.append(token)
                continue
            found["days"] = int(value)
        else:
            found["action"] = value.lower()[:60]
    return found, problems


def _where(guild_id: int, since: float, filters: dict) -> tuple[str, list]:
    clause = "guild_id=? AND created_at>=?"
    args: list = [guild_id, since]
    if "user" in filters:
        clause += " AND user_id=?"
        args.append(filters["user"])
    if "by" in filters:
        clause += " AND actor_id=?"
        args.append(filters["by"])
    if "action" in filters:
        clause += " AND action LIKE ? ESCAPE '\\'"
        args.append(filters["action"].replace("\\", "").replace("%", "").replace("_", "\\_") + "%")
    return clause, args


async def window_start(guild_id: int, filters: dict) -> float:
    cap = await retention_days(guild_id)
    days = min(int(filters.get("days") or cap), cap)
    return time.time() - days * 86400


async def count(guild_id: int, filters: dict) -> int:
    clause, args = _where(guild_id, await window_start(guild_id, filters), filters)
    row = await db.raw_fetchone(f"SELECT COUNT(*) AS n FROM vault_entries WHERE {clause}", tuple(args))
    return int(row["n"])


async def page(guild_id: int, filters: dict, offset: int, limit: int) -> list[dict]:
    clause, args = _where(guild_id, await window_start(guild_id, filters), filters)
    rows = await db.raw_fetch(
        f"SELECT * FROM vault_entries WHERE {clause} ORDER BY created_at DESC, entry_id DESC LIMIT ? OFFSET ?",
        (*args, limit, offset),
    )
    return [dict(r) for r in rows]


async def summary(guild_id: int, filters: dict) -> list[tuple[str, int]]:
    clause, args = _where(guild_id, await window_start(guild_id, filters), filters)
    rows = await db.raw_fetch(
        f"SELECT action, COUNT(*) AS n FROM vault_entries WHERE {clause} GROUP BY action ORDER BY n DESC LIMIT 12",
        tuple(args),
    )
    return [(r["action"], int(r["n"])) for r in rows]


async def totals(guild_id: int) -> dict:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n, MIN(created_at) AS first FROM vault_entries WHERE guild_id=?", (guild_id,))
    return {"count": int(row["n"]), "first": row["first"]}


def describe(entry: dict) -> str:
    try:
        detail = json.loads(entry.get("detail") or "{}")
    except ValueError:
        detail = {}
    text = detail.get("reason") or detail.get("detail") or ""
    if not text:
        text = ", ".join(f"{k}: {v}" for k, v in list(detail.items())[:3])
    return str(text).replace("\n", " ")[:120]


def line(entry: dict) -> str:
    who = f" · <@{entry['user_id']}>" if entry.get("user_id") else ""
    by = f" · by <@{entry['actor_id']}>" if entry.get("actor_id") else ""
    extra = describe(entry)
    return f"<t:{int(entry['created_at'])}:d> <t:{int(entry['created_at'])}:t> `{entry['action']}`{who}{by}" + (f"\n-# {extra}" if extra else "")


async def export_csv(guild_id: int, filters: dict) -> tuple[bytes, int]:
    clause, args = _where(guild_id, await window_start(guild_id, filters), filters)
    rows = await db.raw_fetch(
        f"SELECT * FROM vault_entries WHERE {clause} ORDER BY created_at DESC LIMIT ?",
        (*args, config.VAULT_EXPORT_MAX),
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["time_utc", "action", "user_id", "actor_id", "channel_id", "detail"])
    for r in rows:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["created_at"]))
        detail = str(r["detail"] or "")
        if detail[:1] in ("=", "+", "-", "@"):
            detail = "'" + detail
        writer.writerow([stamp, r["action"], r["user_id"] or "", r["actor_id"] or "", r["channel_id"] or "", detail])
    return out.getvalue().encode("utf-8"), len(rows)
