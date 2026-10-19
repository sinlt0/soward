import re
import time
from typing import Optional

import discord

import config
from utils import db, guild_settings

CFG_DEFAULTS = {
    "enabled": 0, "tier_mode": "count", "stack_mode": "highest", "base_role_id": None, "grace_hours": 0,
    "custom_enabled": 0, "custom_min": 1, "allow_name": 1, "allow_color": 1, "allow_icon": 1, "allow_hoist": 0, "allow_perms": 0,
    "position_mode": "below", "position_ref_id": None, "cooldown_hours": 1, "name_filter": 1, "max_name_len": 32,
    "remove_on_unboost": 1, "restore_on_reboost": 1,
}
BOOST_TYPES = (
    discord.MessageType.premium_guild_subscription, discord.MessageType.premium_guild_tier_1,
    discord.MessageType.premium_guild_tier_2, discord.MessageType.premium_guild_tier_3,
)
BLOCKED_KEY = "booster_blocked_names"
COLOR_NAMES = {
    "red": 0xE74C3C, "orange": 0xE67E22, "yellow": 0xF1C40F, "gold": 0xFFD700, "green": 0x2ECC71, "teal": 0x1ABC9C, "blue": 0x3498DB,
    "purple": 0x9B59B6, "pink": 0xFF69B4, "white": 0xECF0F1, "black": 0x23272A, "grey": 0x95A5A6, "gray": 0x95A5A6, "cyan": 0x00BCD4,
}


class BoosterError(Exception):
    pass


async def get_cfg(guild_id: int) -> dict:
    row = await db.raw_fetchone("SELECT * FROM booster_config WHERE guild_id=?", (guild_id,))
    cfg = dict(CFG_DEFAULTS)
    if row:
        cfg.update({k: row[k] for k in CFG_DEFAULTS})
    cfg["guild_id"] = guild_id
    return cfg


async def set_cfg(guild_id: int, **fields) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO booster_config (guild_id) VALUES (?)", (guild_id,))
    for column, value in fields.items():
        if column not in CFG_DEFAULTS:
            raise KeyError(column)
        await db.raw_execute(f"UPDATE booster_config SET {column}=? WHERE guild_id=?", (value, guild_id))


async def list_tiers(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT boosts, role_id FROM booster_tiers WHERE guild_id=? ORDER BY boosts", (guild_id,))
    return [dict(r) for r in rows]


async def get_record(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM booster_members WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return dict(row) if row else None


async def ensure_record(guild_id: int, member: discord.Member) -> dict:
    now = time.time()
    since = member.premium_since.timestamp() if member.premium_since else now
    await db.raw_execute(
        "INSERT OR IGNORE INTO booster_members (guild_id, user_id, boost_count, boosting_since, updated_at) VALUES (?, ?, 1, ?, ?)",
        (guild_id, member.id, since, now),
    )
    await db.raw_execute("UPDATE booster_members SET ended_at=NULL WHERE guild_id=? AND user_id=? AND ended_at IS NOT NULL", (guild_id, member.id))
    return await get_record(guild_id, member.id)


async def set_count(guild_id: int, member: discord.Member, count: int) -> None:
    await ensure_record(guild_id, member)
    count = max(1, min(count, config.BOOSTER_MAX_COUNT))
    await db.raw_execute("UPDATE booster_members SET boost_count=?, updated_at=? WHERE guild_id=? AND user_id=?", (count, time.time(), guild_id, member.id))


async def add_boosts(guild_id: int, member: discord.Member, amount: int) -> int:
    record = await ensure_record(guild_id, member)
    total = max(1, min(record["boost_count"] + amount, config.BOOSTER_MAX_COUNT))
    await db.raw_execute("UPDATE booster_members SET boost_count=?, updated_at=? WHERE guild_id=? AND user_id=?", (total, time.time(), guild_id, member.id))
    return total


def metric(cfg: dict, record: Optional[dict], member: discord.Member) -> int:
    if cfg["tier_mode"] == "days":
        if member.premium_since is None:
            return 0
        return int((time.time() - member.premium_since.timestamp()) // 86400)
    return record["boost_count"] if record else (1 if member.premium_since else 0)


def metric_label(cfg: dict) -> str:
    return "days" if cfg["tier_mode"] == "days" else "boosts"


def _manageable(guild: discord.Guild, role: Optional[discord.Role]) -> bool:
    return role is not None and not role.is_default() and not role.managed and role < guild.me.top_role


async def sync_member(guild: discord.Guild, member: discord.Member, cfg: Optional[dict] = None, tiers: Optional[list] = None) -> None:
    cfg = cfg or await get_cfg(guild.id)
    if not cfg["enabled"] or member.bot:
        return
    tiers = tiers if tiers is not None else await list_tiers(guild.id)
    managed = {t["role_id"] for t in tiers}
    if cfg["base_role_id"]:
        managed.add(cfg["base_role_id"])
    desired: set[int] = set()
    if member.premium_since is not None:
        record = await ensure_record(guild.id, member)
        value = metric(cfg, record, member)
        qualifying = [t for t in tiers if t["boosts"] <= value]
        if qualifying:
            desired = {qualifying[-1]["role_id"]} if cfg["stack_mode"] == "highest" else {t["role_id"] for t in qualifying}
        if cfg["base_role_id"]:
            desired.add(cfg["base_role_id"])
    else:
        record = await get_record(guild.id, member.id)
        if record and record["ended_at"] is None:
            await db.raw_execute("UPDATE booster_members SET ended_at=? WHERE guild_id=? AND user_id=?", (time.time(), guild.id, member.id))
            record["ended_at"] = time.time()
        if record and cfg["grace_hours"] and record["ended_at"] and time.time() < record["ended_at"] + cfg["grace_hours"] * 3600:
            return
    current = {r.id for r in member.roles}
    add = [r for r in (guild.get_role(i) for i in desired - current) if _manageable(guild, r)]
    remove = [r for r in (guild.get_role(i) for i in (managed - desired) & current) if _manageable(guild, r)]
    try:
        if add:
            await member.add_roles(*add, reason="Soward booster tier")
        if remove:
            await member.remove_roles(*remove, reason="Soward booster tier")
    except discord.HTTPException:
        pass
    if member.premium_since is None:
        await finish_boost(guild, member.id, cfg)


async def finish_boost(guild: discord.Guild, user_id: int, cfg: dict) -> None:
    record = await get_record(guild.id, user_id)
    if record is None:
        return
    if record["ended_at"] is None:
        return
    if cfg["grace_hours"] and time.time() < record["ended_at"] + cfg["grace_hours"] * 3600:
        return
    if cfg["remove_on_unboost"]:
        await delete_custom(guild, user_id, keep_settings=True)
    await db.raw_execute("DELETE FROM booster_members WHERE guild_id=? AND user_id=?", (guild.id, user_id))


async def drop_member(guild: discord.Guild, user_id: int) -> None:
    await delete_custom(guild, user_id, keep_settings=False)
    await db.raw_execute("DELETE FROM booster_members WHERE guild_id=? AND user_id=?", (guild.id, user_id))


def parse_color(text: str) -> int:
    value = text.strip().lower()
    if value in COLOR_NAMES:
        return COLOR_NAMES[value]
    value = value.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{6}", value):
        return int(value, 16)
    if re.fullmatch(r"[0-9a-f]{3}", value):
        return int("".join(c * 2 for c in value), 16)
    raise BoosterError("Use a hex colour such as `#FF69B4` or a name such as `gold`, `pink` or `blue`.")


async def blocked_words(guild_id: int) -> list[str]:
    value = await guild_settings.get(guild_id, BLOCKED_KEY, [])
    return [str(w).lower() for w in value] if isinstance(value, list) else []


async def validate_name(guild: discord.Guild, cfg: dict, name: str, own_role_id: Optional[int] = None) -> str:
    name = " ".join(name.replace("\n", " ").split())
    if not name:
        raise BoosterError("The role needs a name.")
    if len(name) > min(cfg["max_name_len"], 100):
        raise BoosterError(f"Role names can be up to {min(cfg['max_name_len'], 100)} characters.")
    lowered = name.lower()
    if "@" in name or "everyone" in lowered or lowered == "here" or "http" in lowered or "discord.gg" in lowered:
        raise BoosterError("That name is not allowed. No mentions or links.")
    if cfg["name_filter"]:
        for word in await blocked_words(guild.id):
            if word and word in lowered:
                raise BoosterError("That name contains a word this server does not allow.")
    for role in guild.roles:
        if role.id != own_role_id and role.name.lower() == lowered:
            raise BoosterError("A role with that name already exists. Pick another name.")
    return name


async def target_position(guild: discord.Guild, cfg: dict) -> int:
    ref = guild.get_role(cfg["position_ref_id"]) if cfg["position_ref_id"] else None
    if ref is None and cfg["base_role_id"]:
        ref = guild.get_role(cfg["base_role_id"])
    if ref is None:
        ref = guild.premium_subscriber_role
    top = guild.me.top_role.position
    if ref is None:
        return max(1, top - 1)
    position = ref.position if cfg["position_mode"] == "below" else ref.position + 1
    return max(1, min(position, top - 1))


def safe_permissions(names: list[str]) -> discord.Permissions:
    valid = discord.Permissions.VALID_FLAGS
    chosen = [n for n in names if n in config.BOOSTER_SAFE_PERMS and n in valid]
    return discord.Permissions(**{n: True for n in chosen})


def perm_names(value: int) -> list[str]:
    perms = discord.Permissions(value)
    return [n for n in config.BOOSTER_SAFE_PERMS if getattr(perms, n, False)]


async def get_custom(guild: discord.Guild, user_id: int) -> tuple[Optional[dict], Optional[discord.Role]]:
    row = await db.raw_fetchone("SELECT * FROM booster_roles WHERE guild_id=? AND user_id=?", (guild.id, user_id))
    if not row:
        return None, None
    record = dict(row)
    role = guild.get_role(record["role_id"]) if record["role_id"] else None
    if role is None and record["role_id"]:
        await db.raw_execute("UPDATE booster_roles SET role_id=NULL WHERE guild_id=? AND user_id=?", (guild.id, user_id))
        record["role_id"] = None
    return record, role


def eligible(cfg: dict, member: discord.Member, record: Optional[dict]) -> Optional[str]:
    if not cfg["enabled"] or not cfg["custom_enabled"]:
        return "Custom booster roles are turned off on this server."
    if member.premium_since is None:
        return "Only server boosters can have a custom role."
    if metric(cfg, record, member) < cfg["custom_min"]:
        return f"You need at least {cfg['custom_min']} {metric_label(cfg)} for a custom role."
    return None


async def _store(guild_id: int, user_id: int, role_id: Optional[int], **fields) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO booster_roles (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
    await db.raw_execute("UPDATE booster_roles SET role_id=? WHERE guild_id=? AND user_id=?", (role_id, guild_id, user_id))
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE booster_roles SET {column}=? WHERE guild_id=? AND user_id=?", (value, guild_id, user_id))


async def create_custom(guild: discord.Guild, member: discord.Member, cfg: dict, name: str, color: int = 0, hoist: bool = False,
                        perms: int = 0, restoring: bool = False) -> discord.Role:
    if len(guild.roles) >= config.BOOSTER_ROLE_CAP:
        raise BoosterError("This server has reached Discord's role limit.")
    if not restoring:
        name = await validate_name(guild, cfg, name)
    hoist = bool(hoist and cfg["allow_hoist"])
    permissions = safe_permissions(perm_names(perms)) if cfg["allow_perms"] else discord.Permissions.none()
    role = await guild.create_role(
        name=name, colour=discord.Colour(color), hoist=hoist, permissions=permissions, mentionable=False,
        reason=f"Soward custom booster role for {member}",
    )
    try:
        await role.edit(position=await target_position(guild, cfg), reason="Soward custom booster role position")
    except discord.HTTPException:
        pass
    await member.add_roles(role, reason="Soward custom booster role")
    await _store(guild.id, member.id, role.id, name=name, color=color, hoist=int(hoist), perms=permissions.value, last_edit=time.time())
    return role


async def edit_custom(guild: discord.Guild, member: discord.Member, cfg: dict, role: discord.Role, record: dict, *,
                      name: Optional[str] = None, color: Optional[int] = None, hoist: Optional[bool] = None,
                      perms: Optional[list] = None, icon: Optional[bytes] = None, clear_icon: bool = False) -> None:
    wait = record["last_edit"] + cfg["cooldown_hours"] * 3600 - time.time()
    if wait > 0 and cfg["cooldown_hours"]:
        raise BoosterError(f"You can edit your role again <t:{int(time.time() + wait)}:R>.")
    kwargs: dict = {}
    fields: dict = {}
    if name is not None:
        if not cfg["allow_name"]:
            raise BoosterError("Changing the role name is turned off on this server.")
        kwargs["name"] = await validate_name(guild, cfg, name, role.id)
        fields["name"] = kwargs["name"]
    if color is not None:
        if not cfg["allow_color"]:
            raise BoosterError("Changing the role colour is turned off on this server.")
        kwargs["colour"] = discord.Colour(color)
        fields["color"] = color
    if hoist is not None:
        if not cfg["allow_hoist"]:
            raise BoosterError("Showing the role separately in the member list is turned off on this server.")
        kwargs["hoist"] = hoist
        fields["hoist"] = int(hoist)
    if perms is not None:
        if not cfg["allow_perms"]:
            raise BoosterError("Custom role permissions are turned off on this server.")
        permissions = safe_permissions(perms)
        kwargs["permissions"] = permissions
        fields["perms"] = permissions.value
    if icon is not None or clear_icon:
        if not cfg["allow_icon"]:
            raise BoosterError("Role icons are turned off on this server.")
        if icon is not None and "ROLE_ICONS" not in guild.features:
            raise BoosterError("This server needs Boost Level 2 to use role icons.")
        kwargs["display_icon"] = icon if icon is not None else None
    if not kwargs:
        raise BoosterError("Nothing to change.")
    await role.edit(reason=f"Soward custom booster role edited by {member}", **kwargs)
    fields["last_edit"] = time.time()
    await _store(guild.id, member.id, role.id, **fields)


async def delete_custom(guild: discord.Guild, user_id: int, keep_settings: bool) -> None:
    record, role = await get_custom(guild, user_id)
    if record is None:
        return
    if role is not None:
        try:
            await role.delete(reason="Soward custom booster role removed")
        except discord.HTTPException:
            pass
    if keep_settings:
        await db.raw_execute("UPDATE booster_roles SET role_id=NULL WHERE guild_id=? AND user_id=?", (guild.id, user_id))
    else:
        await db.raw_execute("DELETE FROM booster_roles WHERE guild_id=? AND user_id=?", (guild.id, user_id))


async def restore_custom(guild: discord.Guild, member: discord.Member, cfg: dict) -> Optional[discord.Role]:
    if not (cfg["enabled"] and cfg["custom_enabled"] and cfg["restore_on_reboost"]) or member.premium_since is None:
        return None
    record, role = await get_custom(guild, member.id)
    if record is None or role is not None or not record["name"]:
        return None
    try:
        return await create_custom(guild, member, cfg, record["name"], record["color"], bool(record["hoist"]), record["perms"], restoring=True)
    except (BoosterError, discord.HTTPException):
        return None


async def reposition_all(guild: discord.Guild, cfg: dict) -> int:
    rows = await db.raw_fetch("SELECT role_id FROM booster_roles WHERE guild_id=? AND role_id IS NOT NULL", (guild.id,))
    position = await target_position(guild, cfg)
    moved = 0
    for row in rows:
        role = guild.get_role(row["role_id"])
        if role is None or role >= guild.me.top_role:
            continue
        try:
            await role.edit(position=position, reason="Soward custom booster role position")
            moved += 1
        except discord.HTTPException:
            continue
    return moved
