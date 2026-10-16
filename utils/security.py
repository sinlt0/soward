import ast
import datetime
import time
from typing import Optional

import discord

from utils import db, guild_settings
from utils import security_whitelist as whitelist
from utils.events_bus import (
    ANTINUKE_QUARANTINED,
    ANTINUKE_RELEASED,
    LOG_EVENT,
    PANIC_MODE_ENDED,
    PANIC_MODE_STARTED,
    bus,
)
import config


async def is_trusted_id(guild_id: int, user_id: int, owner_id: Optional[int] = None) -> bool:
    if owner_id is not None and user_id == owner_id:
        return True
    if user_id in config.ALL_PRIVILEGED_IDS:
        return True
    if await get_permit_tier(guild_id, user_id) is not None:
        return True
    return user_id in await whitelist.user_ids_for(guild_id, "antinuke")


async def is_trusted(guild_id: int, member: discord.Member) -> bool:
    if await is_trusted_id(guild_id, member.id, member.guild.owner_id):
        return True
    if await whitelist.is_whitelisted(guild_id, ("antinuke",), member):
        return True
    if member.guild_permissions.administrator:
        return bool(await guild_settings.get(guild_id, "antinuke_admin_bypass", config.ANTINUKE_ADMIN_BYPASS_DEFAULT))
    return False


async def is_exempt(guild_id: int, member: discord.Member, scope: str = "automod", channel: Optional[discord.abc.GuildChannel] = None) -> bool:
    if member.guild_permissions.administrator:
        return True
    if await is_trusted_id(guild_id, member.id, member.guild.owner_id):
        return True
    return await whitelist.is_whitelisted(guild_id, (scope,), member, channel)


def dangerous_permissions(permissions: discord.Permissions) -> list[str]:
    return [perm for perm in config.ANTINUKE_DANGEROUS_PERMISSIONS if getattr(permissions, perm, False)]


async def is_real_owner(guild: discord.Guild, user_id: int) -> bool:
    if user_id in config.ALL_PRIVILEGED_IDS:
        return True
    return guild.owner_id == user_id


async def get_permit_tier(guild_id: int, user_id: int) -> Optional[str]:
    row = await db.raw_fetchone(
        "SELECT tier FROM security_permit_tiers WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    return row["tier"] if row else None


async def _count_tier(guild_id: int, tier: str) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) as c FROM security_permit_tiers WHERE guild_id=? AND tier=?", (guild_id, tier)
    )
    return row["c"] if row else 0


async def grant_permit_tier(guild: discord.Guild, granter_id: int, target_id: int, tier: str) -> tuple[bool, str]:
    if tier not in (config.SECURITY_TIER_EXTRA_OWNER, config.SECURITY_TIER_TRUSTED_ADMIN):
        return False, "Invalid tier."

    granter_is_owner = await is_real_owner(guild, granter_id)
    granter_tier = await get_permit_tier(guild.id, granter_id)

    if tier == config.SECURITY_TIER_EXTRA_OWNER:
        if not granter_is_owner:
            return False, "Only the server owner can grant Extra Owner."
    else:
        if not (granter_is_owner or granter_tier == config.SECURITY_TIER_EXTRA_OWNER):
            return False, "Only the server owner or an Extra Owner can grant Trusted Admin."

    existing_tier = await get_permit_tier(guild.id, target_id)
    if existing_tier == tier:
        return False, f"That member already holds {tier.replace('_', ' ').title()}."

    if existing_tier is None:
        current_count = await _count_tier(guild.id, tier)
        if current_count >= config.SECURITY_TIER_MAX_PER_TIER:
            return False, f"This server already has the maximum of {config.SECURITY_TIER_MAX_PER_TIER} {tier.replace('_', ' ').title()}(s)."

    now = time.time()
    await db.raw_execute(
        "INSERT INTO security_permit_tiers (guild_id, user_id, tier, granted_by, granted_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET tier=excluded.tier, granted_by=excluded.granted_by, granted_at=excluded.granted_at",
        (guild.id, target_id, tier, granter_id, now),
    )
    return True, f"Granted {tier.replace('_', ' ').title()}."


async def revoke_permit_tier(guild: discord.Guild, revoker_id: int, target_id: int) -> tuple[bool, str]:
    existing_tier = await get_permit_tier(guild.id, target_id)
    if existing_tier is None:
        return False, "That member does not hold a permit tier."

    revoker_is_owner = await is_real_owner(guild, revoker_id)
    revoker_tier = await get_permit_tier(guild.id, revoker_id)

    if existing_tier == config.SECURITY_TIER_EXTRA_OWNER:
        if not revoker_is_owner:
            return False, "Only the server owner can revoke an Extra Owner."
    else:
        if not (revoker_is_owner or revoker_tier == config.SECURITY_TIER_EXTRA_OWNER):
            return False, "Only the server owner or an Extra Owner can revoke Trusted Admin."

    await db.raw_execute(
        "DELETE FROM security_permit_tiers WHERE guild_id=? AND user_id=?", (guild.id, target_id)
    )
    return True, f"Revoked {existing_tier.replace('_', ' ').title()}."


async def list_permit_tiers(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM security_permit_tiers WHERE guild_id=? ORDER BY tier ASC", (guild_id,))
    return [dict(r) for r in rows]


async def add_trusted(guild_id: int, target_id: int, added_by: int) -> bool:
    return await whitelist.add(guild_id, target_id, "user", "antinuke", added_by)


async def remove_trusted(guild_id: int, target_id: int) -> bool:
    return await whitelist.remove(guild_id, target_id, "antinuke") > 0


async def list_trusted(guild_id: int) -> list[dict]:
    return [r for r in await whitelist.list_entries(guild_id, "antinuke") if r["target_type"] == "user"]


async def _quarantine_role(guild: discord.Guild) -> Optional[discord.Role]:
    role_id = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    if not role_id:
        return None
    return guild.get_role(int(role_id))


async def is_quarantined(guild_id: int, user_id: int) -> bool:
    row = await db.raw_fetchone(
        "SELECT 1 FROM quarantine WHERE guild_id=? AND user_id=? AND released_at IS NULL",
        (guild_id, user_id),
    )
    return row is not None


async def get_offense_multiplier(guild_id: int, user_id: int) -> int:
    row = await db.raw_fetchone(
        "SELECT * FROM quarantine_history WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    if not row:
        return 1

    window = config.QUARANTINE_ESCALATION_WINDOW_SECONDS
    if time.time() - row["last_offense_at"] > window:
        return 1
    return max(1, row["offense_count"])


async def _record_offense(guild_id: int, user_id: int) -> int:
    row = await db.raw_fetchone(
        "SELECT * FROM quarantine_history WHERE guild_id=? AND user_id=?", (guild_id, user_id)
    )
    now = time.time()
    window = config.QUARANTINE_ESCALATION_WINDOW_SECONDS

    if row and (now - row["last_offense_at"]) <= window:
        new_count = row["offense_count"] + 1
    else:
        new_count = 1

    await db.raw_execute(
        "INSERT INTO quarantine_history (guild_id, user_id, offense_count, last_offense_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET offense_count=excluded.offense_count, last_offense_at=excluded.last_offense_at",
        (guild_id, user_id, new_count, now),
    )
    return new_count


async def _lock_member(guild: discord.Guild, member: discord.Member, reason: str) -> None:
    quarantine_role = await _quarantine_role(guild)
    removable = [r for r in member.roles if not r.is_default() and not r.managed and r < guild.me.top_role and r != quarantine_role]
    try:
        if removable:
            await member.remove_roles(*removable, reason=reason)
    except discord.HTTPException:
        removable = []
    try:
        if quarantine_role and quarantine_role < guild.me.top_role and quarantine_role not in member.roles:
            await member.add_roles(quarantine_role, reason=reason)
    except discord.HTTPException:
        pass

    kept = [r for r in member.roles if not r.is_default() and r != quarantine_role and r not in removable]
    remaining_dangerous = any(dangerous_permissions(r.permissions) for r in kept)
    if quarantine_role is None or remaining_dangerous:
        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=config.QUARANTINE_TIMEOUT_SECONDS)
            await member.timeout(until, reason=reason)
        except discord.HTTPException:
            pass


async def strip_member(guild: discord.Guild, member: discord.Member, reason: str) -> bool:
    removable = [r for r in member.roles if not r.is_default() and not r.managed and r < guild.me.top_role]
    try:
        if removable:
            await member.remove_roles(*removable, reason=reason)
    except discord.HTTPException:
        removable = []
    kept = [r for r in member.roles if not r.is_default() and r not in removable]
    if any(dangerous_permissions(r.permissions) for r in kept):
        try:
            until = discord.utils.utcnow() + datetime.timedelta(seconds=config.QUARANTINE_TIMEOUT_SECONDS)
            await member.timeout(until, reason=reason)
        except discord.HTTPException:
            return False
    return True


async def quarantine_member(guild: discord.Guild, member: discord.Member, reason: str, by: Optional[int] = None, *, track_escalation: bool = True) -> bool:
    existing = await db.raw_fetchone(
        "SELECT 1 FROM quarantine WHERE guild_id=? AND user_id=? AND released_at IS NULL",
        (guild.id, member.id),
    )
    if existing:
        return False

    quarantine_role = await _quarantine_role(guild)
    saved_role_ids = [r.id for r in member.roles if not r.is_default() and r != quarantine_role]

    await db.raw_execute(
        "INSERT INTO quarantine (guild_id, user_id, reason, saved_roles, quarantined_by, quarantined_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason, saved_roles=excluded.saved_roles,"
        " quarantined_by=excluded.quarantined_by, quarantined_at=excluded.quarantined_at, released_at=NULL",
        (guild.id, member.id, reason, repr(saved_role_ids), by, time.time()),
    )

    await _lock_member(guild, member, reason)

    if track_escalation:
        await _record_offense(guild.id, member.id)

    await bus.publish(ANTINUKE_QUARANTINED, guild_id=guild.id, user_id=member.id, reason=reason)
    await bus.publish(LOG_EVENT, guild_id=guild.id, action="antinuke_quarantine", user_id=member.id, reason=reason)
    return True


async def enforce_quarantine(guild: discord.Guild, member: discord.Member, reason: str) -> bool:
    if not await is_quarantined(guild.id, member.id):
        return False
    quarantine_role = await _quarantine_role(guild)
    extra = [r for r in member.roles if not r.is_default() and not r.managed and r != quarantine_role]
    missing_role = quarantine_role is not None and quarantine_role not in member.roles
    if not extra and not missing_role:
        return False
    await _lock_member(guild, member, reason)
    return True


async def release_member(guild: discord.Guild, user_id: int, by: Optional[int] = None) -> bool:
    row = await db.raw_fetchone(
        "SELECT saved_roles FROM quarantine WHERE guild_id=? AND user_id=? AND released_at IS NULL",
        (guild.id, user_id),
    )
    if not row:
        return False

    await db.raw_execute(
        "UPDATE quarantine SET released_at=? WHERE guild_id=? AND user_id=? AND released_at IS NULL",
        (time.time(), guild.id, user_id),
    )

    member = guild.get_member(user_id)
    quarantine_role = await _quarantine_role(guild)

    if member:
        try:
            if quarantine_role and quarantine_role in member.roles:
                await member.remove_roles(quarantine_role, reason="Security: quarantine released")
            saved_ids = ast.literal_eval(row["saved_roles"]) if row["saved_roles"] else []
            roles_to_restore = [guild.get_role(rid) for rid in saved_ids]
            roles_to_restore = [r for r in roles_to_restore if r and not r.managed and r < guild.me.top_role]
            if roles_to_restore:
                await member.add_roles(*roles_to_restore, reason="Security: quarantine released")
            if member.is_timed_out():
                await member.timeout(None, reason="Security: quarantine released")
        except discord.HTTPException:
            pass
        except (ValueError, SyntaxError):
            pass

    await bus.publish(ANTINUKE_RELEASED, guild_id=guild.id, user_id=user_id)
    await bus.publish(LOG_EVENT, guild_id=guild.id, action="antinuke_quarantine_release", user_id=user_id)
    return True


async def get_action_punishment(guild_id: int, action_type: str) -> str:
    row = await db.raw_fetchone(
        "SELECT punishment FROM antinuke_action_punishments WHERE guild_id=? AND action_type=?",
        (guild_id, action_type),
    )
    if row:
        return row["punishment"]

    general = await guild_settings.get(guild_id, "antinuke_punishment", None)
    if general:
        return general

    return config.ANTINUKE_PER_ACTION_PUNISHMENT_DEFAULT.get(action_type, config.ANTINUKE_DEFAULT_PUNISHMENT)


async def set_action_punishment(guild_id: int, action_type: str, punishment: str) -> None:
    await db.raw_execute(
        "INSERT INTO antinuke_action_punishments (guild_id, action_type, punishment) VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id, action_type) DO UPDATE SET punishment=excluded.punishment",
        (guild_id, action_type, punishment),
    )


async def clear_action_punishment(guild_id: int, action_type: str) -> bool:
    cur = await db.raw_execute(
        "DELETE FROM antinuke_action_punishments WHERE guild_id=? AND action_type=?", (guild_id, action_type)
    )
    return cur.rowcount > 0


async def is_panic_mode_active(guild_id: int) -> bool:
    row = await db.raw_fetchone("SELECT * FROM panic_mode_state WHERE guild_id=?", (guild_id,))
    if not row or not row["active"]:
        return False
    if row["expires_at"] and time.time() > row["expires_at"]:
        await end_panic_mode(guild_id, ended_by="auto-expiry")
        return False
    return True


async def trigger_panic_mode(guild_id: int, triggered_by: str, duration_seconds: Optional[int] = None) -> None:
    duration = duration_seconds or config.PANIC_MODE_DURATION_SECONDS
    now = time.time()
    await db.raw_execute(
        "INSERT INTO panic_mode_state (guild_id, active, started_at, expires_at, triggered_by) VALUES (?, 1, ?, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET active=1, started_at=excluded.started_at,"
        " expires_at=excluded.expires_at, triggered_by=excluded.triggered_by",
        (guild_id, now, now + duration, triggered_by),
    )
    await bus.publish(PANIC_MODE_STARTED, guild_id=guild_id, triggered_by=triggered_by, duration_seconds=duration)
    await bus.publish(LOG_EVENT, guild_id=guild_id, action="antiraid_raid_mode", active=True, triggered_by=triggered_by)


async def end_panic_mode(guild_id: int, ended_by: Optional[str] = None) -> None:
    await db.raw_execute("UPDATE panic_mode_state SET active=0 WHERE guild_id=?", (guild_id,))
    await bus.publish(PANIC_MODE_ENDED, guild_id=guild_id, ended_by=ended_by)
    await bus.publish(LOG_EVENT, guild_id=guild_id, action="antiraid_raid_mode", active=False, ended_by=ended_by)
