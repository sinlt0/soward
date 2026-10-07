import math
import random
import time
import uuid

import discord

from utils import db

SCOPE_GLOBAL = "global"
SCOPE_CHANNEL = "channel"
SCOPE_ROLE = "role"


def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


def level_from_xp(xp: int) -> int:
    level = 0
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def xp_progress(xp: int, level: int) -> tuple[int, int]:
    floor = xp_for_level(level)
    ceiling = xp_for_level(level + 1)
    return xp - floor, ceiling - floor


def roll_text_xp(guild_config: dict) -> int:
    return random.randint(guild_config["xp_min"], guild_config["xp_max"])


async def get_guild_config(guild_id: int) -> dict:
    row = await db.raw_fetchone("SELECT * FROM guild_leveling_config WHERE guild_id=?", (guild_id,))
    if row:
        return dict(row)

    defaults = {
        "guild_id": guild_id, "enabled": 0, "xp_min": 15, "xp_max": 25,
        "text_cooldown_seconds": 60, "voice_xp_per_minute": 10, "voice_enabled": 1,
        "voice_require_unmuted": 1, "voice_require_others": 1, "role_stack_mode": "stack",
        "announce_mode": "channel", "announce_channel_id": None, "announce_message": None,
        "weekly_reset_enabled": 0, "monthly_reset_enabled": 0, "top_role_id": None,
        "prestige_level_cap": 0,
    }
    await db.raw_execute(
        "INSERT INTO guild_leveling_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING",
        (guild_id,),
    )
    return defaults


async def is_no_xp_channel(guild_id: int, channel_id: int) -> bool:
    row = await db.raw_fetchone(
        "SELECT 1 FROM xp_no_xp_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id)
    )
    return row is not None


async def has_no_xp_role(guild_id: int, member: discord.Member) -> bool:
    if not member.roles:
        return False
    role_ids = [r.id for r in member.roles]
    placeholders = ",".join("?" for _ in role_ids)
    row = await db.raw_fetchone(
        f"SELECT 1 FROM xp_no_xp_roles WHERE guild_id=? AND role_id IN ({placeholders})",
        (guild_id, *role_ids),
    )
    return row is not None


async def resolve_multiplier(guild_id: int, member: discord.Member, channel_id: int) -> float:
    rows = await db.raw_fetch("SELECT * FROM xp_multipliers WHERE guild_id=?", (guild_id,))
    if not rows:
        return 1.0

    role_ids = {r.id for r in member.roles}
    best_by_scope: dict[str, float] = {}

    for row in rows:
        scope_type = row["scope_type"]
        scope_id = row["scope_id"]
        value = row["multiplier"]

        applies = (
            (scope_type == SCOPE_GLOBAL) or
            (scope_type == SCOPE_CHANNEL and scope_id == channel_id) or
            (scope_type == SCOPE_ROLE and scope_id in role_ids)
        )
        if not applies:
            continue

        current_best = best_by_scope.get(scope_type)
        if current_best is None or value > current_best:
            best_by_scope[scope_type] = value

    total = 1.0
    for value in best_by_scope.values():
        total *= value
    return total


async def add_xp(guild_id: int, user_id: int, base_xp: int, member: discord.Member, channel_id: int) -> dict:
    multiplier = await resolve_multiplier(guild_id, member, channel_id)
    final_xp = max(1, math.floor(base_xp * multiplier))

    row = await db.raw_fetchone("SELECT * FROM member_xp WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    old_xp = row["xp"] if row else 0
    old_level = row["level"] if row else 0
    new_xp = old_xp + final_xp
    new_level = level_from_xp(new_xp)

    await db.raw_execute(
        "INSERT INTO member_xp (guild_id, user_id, xp, level, last_text_xp_at, total_messages)"
        " VALUES (?, ?, ?, ?, ?, 1)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level,"
        " last_text_xp_at=excluded.last_text_xp_at, total_messages=total_messages + 1",
        (guild_id, user_id, new_xp, new_level, time.time()),
    )

    for period in ("weekly", "monthly"):
        await db.raw_execute(
            "INSERT INTO member_xp_periodic (guild_id, user_id, period, xp) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id, period) DO UPDATE SET xp=xp + excluded.xp",
            (guild_id, user_id, period, final_xp),
        )

    return {
        "xp_gained": final_xp,
        "multiplier": multiplier,
        "old_level": old_level,
        "new_level": new_level,
        "leveled_up": new_level > old_level,
        "total_xp": new_xp,
    }


async def apply_role_rewards(guild: discord.Guild, member: discord.Member, new_level: int, stack_mode: str) -> list[discord.Role]:
    rows = await db.raw_fetch(
        "SELECT level, role_id FROM level_role_rewards WHERE guild_id=? AND level<=? ORDER BY level ASC",
        (guild.id, new_level),
    )
    if not rows:
        return []

    all_reward_role_ids = {r["role_id"] for r in
                            await db.raw_fetch("SELECT role_id FROM level_role_rewards WHERE guild_id=?", (guild.id,))}

    earned_role_ids = [r["role_id"] for r in rows]
    earned_roles = [guild.get_role(rid) for rid in earned_role_ids]
    earned_roles = [r for r in earned_roles if r]

    to_add = [r for r in earned_roles if r not in member.roles]
    if to_add:
        try:
            await member.add_roles(*to_add, reason="Leveling: role reward")
        except discord.HTTPException:
            pass

    if stack_mode == "nonstack":
        highest_role_id = earned_role_ids[-1] if earned_role_ids else None
        to_remove = [
            r for r in member.roles
            if r.id in all_reward_role_ids and r.id != highest_role_id
        ]
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason="Leveling: non-stack role cleanup")
            except discord.HTTPException:
                pass

    return to_add


async def get_leaderboard(guild_id: int, period: str = "alltime", limit: int = 10) -> list[dict]:
    if period == "alltime":
        rows = await db.raw_fetch(
            "SELECT user_id, xp, level FROM member_xp WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
            (guild_id, limit),
        )
        return [dict(r) for r in rows]

    rows = await db.raw_fetch(
        "SELECT user_id, xp FROM member_xp_periodic WHERE guild_id=? AND period=? ORDER BY xp DESC LIMIT ?",
        (guild_id, period, limit),
    )
    return [dict(r) for r in rows]


async def reset_period(guild_id: int, period: str) -> None:
    await db.raw_execute("DELETE FROM member_xp_periodic WHERE guild_id=? AND period=?", (guild_id, period))
    await db.raw_execute(
        "INSERT INTO leveling_period_state (guild_id, period, period_start) VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id, period) DO UPDATE SET period_start=excluded.period_start",
        (guild_id, period, time.time()),
    )


def new_multiplier_id() -> str:
    return str(uuid.uuid4())[:8].upper()
