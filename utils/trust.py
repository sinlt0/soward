import time
import uuid
from typing import Optional

import discord

from utils import db, guild_settings
from utils import reports as report_store
from utils import security_settings

TIERS = ((75, "Trusted"), (50, "Established"), (30, "Unproven"), (0, "Risky"))
DAY = 86400


def tier(score: int) -> str:
    for floor, name in TIERS:
        if score >= floor:
            return name
    return "Risky"


def compute(*, account_days: float, member_days: float, verified: bool, level: int, warns: int, mutes: int, kicks: int,
            upheld: int, open_reports: int, adjustment: int) -> tuple[int, list[tuple[str, int]]]:
    parts: list[tuple[str, int]] = [("Base", 25)]
    parts.append(("Account age", min(15, int(account_days / 365 * 15))))
    parts.append(("Time in server", min(15, int(member_days / 90 * 15))))
    if verified:
        parts.append(("Verified", 10))
    parts.append(("Activity level", min(10, int(level / 20 * 10))))
    penalties = 0
    if warns:
        value = -min(32, warns * 8)
        parts.append((f"Warnings ({warns})", value))
        penalties += 1
    if mutes:
        value = -min(24, mutes * 6)
        parts.append((f"Timeouts ({mutes})", value))
        penalties += 1
    if kicks:
        value = -min(30, kicks * 15)
        parts.append((f"Kicks ({kicks})", value))
        penalties += 1
    if upheld:
        parts.append((f"Upheld reports ({upheld})", -min(24, upheld * 6)))
        penalties += 1
    if open_reports:
        parts.append((f"Open reports ({open_reports})", -min(6, open_reports * 2)))
    if penalties == 0 and member_days >= 30:
        parts.append(("Clean record", 20))
    if adjustment:
        parts.append(("Staff adjustment", max(-50, min(50, adjustment))))
    score = max(0, min(100, sum(v for _, v in parts)))
    return score, parts


async def gather(guild: discord.Guild, member: discord.Member) -> tuple[int, list[tuple[str, int]]]:
    now = time.time()
    since = now - 90 * DAY
    role_id = await security_settings.get(guild.id, "verification", "role_id")
    verified = bool(role_id and any(r.id == int(role_id) for r in member.roles))
    xp = await db.raw_fetchone("SELECT level FROM member_xp WHERE guild_id=? AND user_id=?", (guild.id, member.id))
    warns = await db.raw_fetchone("SELECT COUNT(*) AS c FROM warn_cases WHERE guild_id=? AND user_id=? AND created_at>?", (guild.id, member.id, since))
    cases = await db.raw_fetch("SELECT action, COUNT(*) AS c FROM mod_cases WHERE guild_id=? AND user_id=? AND created_at>? GROUP BY action", (guild.id, member.id, since))
    counted = {r["action"]: int(r["c"]) for r in cases}
    reports = await report_store.received_counts(guild.id, member.id)
    adj = await db.raw_fetchone("SELECT COALESCE(SUM(delta), 0) AS s FROM trust_adjustments WHERE guild_id=? AND user_id=?", (guild.id, member.id))
    joined = member.joined_at.timestamp() if member.joined_at else now
    return compute(
        account_days=(now - member.created_at.timestamp()) / DAY,
        member_days=(now - joined) / DAY,
        verified=verified,
        level=int(xp["level"]) if xp else 0,
        warns=int(warns["c"]) if warns else 0,
        mutes=counted.get("mute", 0) + counted.get("timeout", 0),
        kicks=counted.get("kick", 0),
        upheld=reports["upheld"],
        open_reports=reports["open"],
        adjustment=int(adj["s"]) if adj else 0,
    )


async def adjust(guild_id: int, user_id: int, delta: int, reason: str, moderator_id: int) -> str:
    adj_id = uuid.uuid4().hex[:8].upper()
    await db.raw_execute(
        "INSERT INTO trust_adjustments (adj_id, guild_id, user_id, delta, reason, moderator_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (adj_id, guild_id, user_id, delta, reason[:300], moderator_id, time.time()))
    return adj_id


async def adjustments(guild_id: int, user_id: int, limit: int = 8) -> list:
    return await db.raw_fetch(
        "SELECT * FROM trust_adjustments WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, user_id, limit))


async def line(guild: discord.Guild, member: discord.Member) -> str:
    score, _ = await gather(guild, member)
    return f"**Trust:** {score}/100 · {tier(score)}"
