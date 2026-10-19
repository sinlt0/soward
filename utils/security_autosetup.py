import asyncio
import statistics
import time

import discord

import config
from utils import db, guild_settings
from utils import security_settings as settings
from utils.events_bus import LOG_EVENT, bus

DAY = 86400
MAX_OVERWRITES = 120
PRESET_ORDER = ("relaxed", "balanced", "strict", "paranoid")


async def analyse(guild: discord.Guild) -> dict:
    now = discord.utils.utcnow()
    members = list(guild.members)
    humans = [m for m in members if not m.bot]
    bots = [m for m in members if m.bot]
    size = guild.member_count or len(members)

    def age(moment) -> float:
        return (now - moment).total_seconds()

    week = [m for m in humans if m.joined_at and age(m.joined_at) < 7 * DAY]
    month = [m for m in humans if m.joined_at and age(m.joined_at) < 30 * DAY]
    buckets: dict[int, int] = {}
    for member in week:
        key = int(member.joined_at.timestamp() // 3600)
        buckets[key] = buckets.get(key, 0) + 1
    young = [m for m in week if age(m.created_at) < 7 * DAY]
    admin_roles = [r for r in guild.roles if r.permissions.administrator and not r.managed and not r.is_default()]
    admin_humans = {m.id for r in admin_roles for m in r.members if not m.bot and m.id != guild.owner_id}
    admin_bots = [m for m in bots if m.guild_permissions.administrator and m.id != guild.me.id]

    since = time.time() - 30 * DAY
    cases = await db.raw_fetchone("SELECT COUNT(*) AS c FROM mod_cases WHERE guild_id=? AND created_at>?", (guild.id, since))
    chatters = await db.raw_fetchone(
        "SELECT COUNT(*) AS c FROM member_xp_periodic WHERE guild_id=? AND period='weekly' AND xp>0", (guild.id,)
    )
    leveling = await db.raw_fetchone("SELECT enabled FROM guild_leveling_config WHERE guild_id=?", (guild.id,))
    voice = sum(len([m for m in vc.members if not m.bot]) for vc in guild.voice_channels)
    features = set(guild.features)

    return {
        "size": size,
        "humans": len(humans),
        "bots": len(bots),
        "coverage": min(1.0, len(members) / size) if size else 1.0,
        "joins_7d": len(week),
        "joins_30d": len(month),
        "peak_hour": max(buckets.values(), default=0),
        "young_share": len(young) / len(week) if week else 0.0,
        "median_age_days": statistics.median([age(m.created_at) for m in week]) / DAY if week else 0.0,
        "noavatar_share": len([m for m in month if m.avatar is None]) / len(month) if month else 0.0,
        "admin_roles": len(admin_roles),
        "admin_humans": len(admin_humans),
        "admin_bots": [b.mention for b in admin_bots],
        "cases_30d": cases["c"] if cases else 0,
        "weekly_chatters": chatters["c"] if chatters and leveling and leveling["enabled"] else None,
        "voice_now": voice,
        "channels": len(guild.channels),
        "roles": len(guild.roles),
        "public": bool({"COMMUNITY", "DISCOVERABLE"} & features),
        "mfa": guild.mfa_level is discord.MFALevel.require_2fa,
        "boost_tier": guild.premium_tier,
    }


def _bot_permissions(guild: discord.Guild) -> dict[str, bool]:
    perms = guild.me.guild_permissions
    return {
        "manage_channels": perms.manage_channels or perms.administrator,
        "manage_roles": perms.manage_roles or perms.administrator,
        "manage_webhooks": perms.manage_webhooks or perms.administrator,
    }


async def build_plan(guild: discord.Guild, a: dict, force: str = "") -> dict:
    risk = 0
    reasons: list[str] = []
    size = a["size"]

    if size >= 10000:
        risk += 2
        reasons.append(f"{size:,} members makes the server a frequent raid target")
    elif size >= 1000:
        risk += 1
        reasons.append(f"{size:,} members makes the server a likely raid target")
    if a["joins_7d"] >= 50 or (size and a["joins_7d"] / size > 0.05 and a["joins_7d"] >= 10):
        risk += 1
        reasons.append(f"{a['joins_7d']} members joined this week, which is fast growth")
    if a["joins_7d"] >= 10 and a["young_share"] > 0.25:
        risk += 1
        reasons.append(f"{a['young_share']:.0%} of this week's joiners have accounts under 7 days old")
    if a["admin_humans"] > 5 or a["admin_bots"]:
        risk += 1
        reasons.append("many accounts or bots hold Administrator")
    if a["public"]:
        risk += 1
        reasons.append("the server is a public community")
    if size and a["cases_30d"] / size > 0.02:
        risk += 1
        reasons.append(f"{a['cases_30d']} moderation cases in 30 days is a busy moderation load")

    if size < 50 and risk <= 1:
        preset = "relaxed"
        reasons.insert(0, "a small, low-risk server does not need heavy limits")
    elif risk <= 1:
        preset = "balanced"
        reasons.insert(0, "no strong risk signals, so sensible defaults fit")
    elif risk <= 3:
        preset = "strict"
    else:
        preset = "paranoid"
    if size >= 200 and preset == "relaxed":
        preset = "balanced"

    if force in settings.PRESETS:
        preset = force
        reasons.insert(0, f"you asked for the {force} preset")
    values = settings.PRESETS[preset]
    tweaks: dict[str, object] = {}
    notes: list[str] = []

    base = int(values.get("antiraid.join_velocity_count", settings._REGISTRY["antiraid.join_velocity_count"].default))
    if a["peak_hour"] >= 20:
        tuned = min(base * 3, base + a["peak_hour"] // 20)
        if tuned != base:
            tweaks["antiraid.join_velocity_count"] = tuned
            notes.append(f"Raid trigger raised to {tuned} joins because your busiest hour had {a['peak_hour']} joins")
    tweaks["security.auto_backup"] = True
    interval = 6 if size >= 1000 else 12 if size >= 200 else 24
    tweaks["security.backup_interval_hours"] = interval
    notes.append(f"Automatic backups every {interval} hours")

    recommendations: list[str] = []
    verification_level = await guild_settings.get(guild.id, "verification_level", 0)
    if not verification_level:
        if risk >= 3:
            recommendations.append("Turn on web verification with `verification type web` to catch VPN and alt accounts")
        elif risk >= 1:
            recommendations.append("Turn on button or captcha verification with `verification type captcha`")
    if a["admin_humans"] and not a["mfa"]:
        recommendations.append("Require 2FA for moderators in Server Settings, Safety Setup. This is a Discord setting")
    if a["admin_bots"]:
        recommendations.append(f"Review bots with Administrator: {', '.join(a['admin_bots'][:6])}")
    if a["admin_humans"] > 3:
        recommendations.append(f"{a['admin_humans']} members get Administrator through roles. Trim it, or make the trusted ones Trusted Admins with `security trusted add`")
    me = guild.me
    if guild.roles and me.top_role.position < max(r.position for r in guild.roles) - 3:
        recommendations.append("Move Soward's role higher so it can act on more roles")
    if a["coverage"] < 0.8:
        recommendations.append("Soward can only see part of the member list, so the join statistics are approximate")

    perms = _bot_permissions(guild)
    steps: list[str] = []
    skipped: list[str] = []
    log_row = await db.raw_fetchone("SELECT 1 FROM log_channels WHERE guild_id=? AND category='security'", (guild.id,))
    if not log_row and not await guild_settings.get(guild.id, "security_log_channel_id"):
        (steps if perms["manage_channels"] and perms["manage_webhooks"] else skipped).append("Create the log channels and set the security log")
    qrole_id = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    if not (qrole_id and guild.get_role(int(qrole_id))):
        (steps if perms["manage_roles"] else skipped).append("Create a Quarantined role that cannot see any channel")
    if not await db.raw_fetchone("SELECT 1 FROM security_backups WHERE guild_id=?", (guild.id,)):
        steps.append("Take a first backup of roles, channels, bans and settings")

    return {
        "risk": risk,
        "preset": preset,
        "reasons": reasons,
        "tweaks": tweaks,
        "notes": notes,
        "recommendations": recommendations,
        "steps": steps,
        "skipped": skipped,
    }


def summary(a: dict, plan: dict) -> str:
    activity = f"{a['weekly_chatters']} active chatters this week" if a["weekly_chatters"] is not None else f"{a['voice_now']} in voice now"
    return (
        f"**Server:** {a['size']:,} members · {a['joins_7d']} joined this week · {activity}\n"
        f"**Accounts:** {a['young_share']:.0%} new (under 7 days) among this week's joins · {a['admin_humans']} admins · {len(a['admin_bots'])} bots with Administrator\n"
        f"**Risk score:** {plan['risk']}/7 · **Preset:** `{plan['preset']}`\n"
        + ("**Why:** " + "; ".join(plan["reasons"][:4]) + "\n" if plan["reasons"] else "")
        + "\n**Soward will:**\n"
        + f"- Apply the `{plan['preset']}` preset. Verification settings are left as they are\n"
        + "\n".join(f"- {line}" for line in plan["notes"])
        + ("\n" if plan["notes"] else "")
        + "\n".join(f"- {line}" for line in plan["steps"])
        + ("\n" if plan["steps"] else "")
        + ("\n**Cannot do, missing permissions:** " + "; ".join(plan["skipped"]) if plan["skipped"] else "")
    )[:1900]


async def _lock_channels(guild: discord.Guild, role: discord.Role) -> int:
    overwrite = discord.PermissionOverwrite(view_channel=False, send_messages=False, connect=False, speak=False, add_reactions=False)
    targets = [
        ch for ch in guild.channels
        if isinstance(ch, discord.CategoryChannel) or ch.category is None or not ch.permissions_synced
    ][:MAX_OVERWRITES]
    done = 0
    for channel in targets:
        if role in channel.overwrites:
            continue
        try:
            await channel.set_permissions(role, overwrite=overwrite, reason="Soward security setup")
            done += 1
        except discord.HTTPException:
            continue
        await asyncio.sleep(0.4)
    return done


async def apply(bot, guild: discord.Guild, actor_id: int, plan: dict) -> tuple[list[str], list[str], str]:
    done: list[str] = []
    failed: list[str] = []
    before = await settings.export_json(guild.id)

    changed = await settings.apply_preset(guild.id, plan["preset"], skip=("verification",))
    done.append(f"Applied the `{plan['preset']}` preset ({len(changed)} setting(s) changed)")
    for path, value in plan["tweaks"].items():
        setting = settings._REGISTRY[path]
        await settings.put(guild.id, setting, value)
    done.extend(plan["notes"])

    logging_cog = bot.get_cog("Logging")
    log_row = await db.raw_fetchone("SELECT channel_id FROM log_channels WHERE guild_id=? AND category='security'", (guild.id,))
    if (not log_row) and any("log channels" in s for s in plan["steps"]) and logging_cog:
        try:
            await logging_cog.provision_channels(guild)
            done.append("Created the log channels")
        except discord.HTTPException as exc:
            failed.append(f"Log channels: {exc}")
        log_row = await db.raw_fetchone("SELECT channel_id FROM log_channels WHERE guild_id=? AND category='security'", (guild.id,))
    if log_row:
        for key in ("log_channel_id", "alert_channel_id"):
            setting = settings._REGISTRY[f"security.{key}"]
            if not await guild_settings.get(guild.id, setting.store):
                await settings.put(guild.id, setting, int(log_row["channel_id"]))
        done.append(f"Security log and alerts go to <#{log_row['channel_id']}>")

    qrole_id = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    if any("Quarantined role" in s for s in plan["steps"]) and not (qrole_id and guild.get_role(int(qrole_id))):
        try:
            role = await guild.create_role(name="Quarantined", permissions=discord.Permissions.none(), reason="Soward security setup")
            try:
                await role.edit(position=max(1, guild.me.top_role.position - 1))
            except discord.HTTPException:
                pass
            await guild_settings.set(guild.id, "antinuke_quarantine_role_id", role.id)
            locked = await _lock_channels(guild, role)
            done.append(f"Created {role.mention} and hid {locked} channel(s) or categories from it")
        except discord.HTTPException as exc:
            failed.append(f"Quarantine role: {exc}")

    lockdown = bot.get_cog("Lockdown")
    if any("first backup" in s for s in plan["steps"]) and lockdown:
        try:
            backup_id = await lockdown.create_backup(guild, "security setup", actor_id)
            done.append(f"Took backup `{backup_id}`")
        except Exception as exc:
            failed.append(f"Backup: {exc}")

    await bus.publish(
        LOG_EVENT, guild_id=guild.id, action="security_change", actor_id=actor_id,
        detail=f"Ran security setup with the **{plan['preset']}** preset.",
    )
    return done, failed, before
