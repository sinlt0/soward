from __future__ import annotations

import discord

import config
from utils import db, xp_engine
from utils.dash.base import (
    ActionContext, action, button, fld, need_channel, need_choice, need_int, need_role, need_text, row, section, table,
)

MODULE = "leveling"
MAX_MULTIPLIER = 100.0
MAX_XP = 1_000_000_000
SCOPE_LABELS = {
    xp_engine.SCOPE_GLOBAL: "Server-wide",
    xp_engine.SCOPE_CHANNEL: "Channel",
    xp_engine.SCOPE_ROLE: "Role",
}


def _role_name(guild: discord.Guild, role_id: int) -> str:
    role = guild.get_role(role_id)
    return role.name if role else f"Deleted role ({role_id})"


def _channel_name(guild: discord.Guild, channel_id: int) -> str:
    channel = guild.get_channel(channel_id)
    return f"#{channel.name}" if channel else f"Deleted channel ({channel_id})"


def _member_name(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.display_name if member else f"Left server ({user_id})"


def _usable_role(guild: discord.Guild, role: discord.Role) -> discord.Role:
    me = guild.me
    if role.managed:
        raise ValueError("Pick a normal role. Bot and integration roles cannot be given to members.")
    if me is not None and not me.guild_permissions.administrator and role.position >= me.top_role.position:
        raise ValueError(f"{role.name} is above my highest role. Move my role higher first.")
    return role


def _member(guild: discord.Guild, values: dict) -> discord.Member:
    raw = str(values.get("user_id", "")).strip()
    member = guild.get_member(int(raw)) if raw.isdigit() else None
    if member is None:
        raise ValueError("That user ID is not a member of this server.")
    return member


@section(MODULE)
async def rewards_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch(
        "SELECT level, role_id FROM level_role_rewards WHERE guild_id=? ORDER BY level ASC", (guild.id,)
    )
    fields = [
        fld("level", "Level", "int", lo=1, hi=1000),
        fld("role", "Role", "role"),
    ]
    rows = [
        row(
            f"{r['level']}:{r['role_id']}",
            [r["level"], _role_name(guild, r["role_id"])],
            actions=[button("reward_remove", "Remove", style="danger", confirm="Remove this role reward? Members keep roles they already earned.")],
        )
        for r in rows_db
    ]
    return table(
        "rewards", "Level role rewards", ["Level", "Role"], rows, "No role rewards configured.",
        description="Members receive the role when they reach the level.",
        buttons=[button("reward_add", "Add reward", fields, style="primary", title="Add role reward", submit="Add reward")],
    )


@section(MODULE)
async def noxp_channels_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT channel_id FROM xp_no_xp_channels WHERE guild_id=?", (guild.id,))
    rows = [
        row(r["channel_id"], [_channel_name(guild, r["channel_id"])],
            actions=[button("noxp_channel_remove", "Remove", style="danger", confirm="This channel will earn XP again. Continue?")])
        for r in rows_db
    ]
    return table(
        "noxp_channels", "No-XP channels", ["Channel"], rows, "Every channel earns XP.",
        buttons=[button("noxp_channel_add", "Add channel", [fld("channel", "Channel", "channel")], style="primary",
                        title="Add no-XP channel", submit="Add channel")],
    )


@section(MODULE)
async def noxp_roles_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT role_id FROM xp_no_xp_roles WHERE guild_id=?", (guild.id,))
    rows = [
        row(r["role_id"], [_role_name(guild, r["role_id"])],
            actions=[button("noxp_role_remove", "Remove", style="danger", confirm="Members with this role will earn XP again. Continue?")])
        for r in rows_db
    ]
    return table(
        "noxp_roles", "No-XP roles", ["Role"], rows, "Every role earns XP.",
        buttons=[button("noxp_role_add", "Add role", [fld("role", "Role", "role")], style="primary",
                        title="Add no-XP role", submit="Add role")],
    )


@section(MODULE)
async def multipliers_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT * FROM xp_multipliers WHERE guild_id=?", (guild.id,))
    fields = [
        fld("scope", "Applies to", "select", value=xp_engine.SCOPE_GLOBAL, options=list(SCOPE_LABELS.items())),
        fld("channel", "Channel", "channel", help="Used when Applies to is Channel."),
        fld("role", "Role", "role", help="Used when Applies to is Role."),
        fld("value", "Multiplier", "text", value="2", maxlen=8, help=f"Greater than 0, up to {MAX_MULTIPLIER:g}. 2 doubles XP."),
    ]
    rows = []
    for r in rows_db:
        if r["scope_type"] == xp_engine.SCOPE_CHANNEL:
            target = _channel_name(guild, r["scope_id"])
        elif r["scope_type"] == xp_engine.SCOPE_ROLE:
            target = _role_name(guild, r["scope_id"])
        else:
            target = "Whole server"
        rows.append(row(
            r["multiplier_id"],
            [r["multiplier_id"], SCOPE_LABELS.get(r["scope_type"], r["scope_type"]), target, f"{r['multiplier']:g}x"],
            actions=[button("multiplier_remove", "Remove", style="danger", confirm="Remove this multiplier?")],
        ))
    return table(
        "multipliers", "XP multipliers", ["ID", "Scope", "Target", "Multiplier"], rows, "No multipliers configured.",
        description="Within each scope the highest multiplier applies; different scopes multiply together.",
        buttons=[button("multiplier_add", "Add multiplier", fields, style="primary", title="Add XP multiplier", submit="Add multiplier")],
    )


@section(MODULE)
async def members_section(guild: discord.Guild) -> dict:
    top = await xp_engine.get_leaderboard(guild.id, "alltime", config.DASHBOARD_LIST_LIMIT)
    xp_fields = [
        fld("user_id", "Member ID", "text", maxlen=20, placeholder="Right-click the member and copy their ID"),
        fld("amount", "Total XP", "int", value=0, lo=0, hi=MAX_XP),
    ]
    reset_fields = [fld("user_id", "Member ID", "text", maxlen=20, placeholder="Right-click the member and copy their ID")]
    rows = []
    for entry in top:
        uid = entry["user_id"]
        rows.append(row(
            uid,
            [_member_name(guild, uid), f"{entry['xp']:,}", entry["level"]],
            actions=[
                button("xp_set", "Set XP", [fld("amount", "Total XP", "int", value=entry["xp"], lo=0, hi=MAX_XP)],
                       title="Set XP", submit="Set XP"),
                button("xp_reset", "Reset", style="danger", confirm="Reset this member's XP and level to zero?"),
            ],
        ))
    return table(
        "members", "Member XP", ["Member", "XP", "Level"], rows, "No one has earned XP yet.",
        description="Top members. Use the buttons for anyone else by their user ID. Role rewards are not re-synced, the same as the commands.",
        buttons=[
            button("xp_set", "Set XP by ID", xp_fields, style="primary", title="Set member XP", submit="Set XP"),
            button("xp_reset", "Reset XP by ID", reset_fields, style="danger", title="Reset member XP", submit="Reset XP"),
        ],
    )


@action(MODULE, "reward_add")
async def reward_add(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    level = need_int(values, "level", "Level", 1, 1000)
    role = _usable_role(ctx.guild, need_role(ctx.guild, values, "role", "Role"))
    cur = await db.raw_execute(
        "INSERT OR IGNORE INTO level_role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
        (ctx.guild.id, level, role.id),
    )
    if not cur.rowcount:
        raise ValueError("That role reward already exists.")
    return [f"Role reward added: {role.name} at level {level}"]


@action(MODULE, "reward_remove")
async def reward_remove(ctx: ActionContext, payload: dict) -> list:
    level, _, role_id = str(payload.get("id") or "").partition(":")
    if not level.isdigit() or not role_id.isdigit():
        raise ValueError("That role reward no longer exists.")
    cur = await db.raw_execute(
        "DELETE FROM level_role_rewards WHERE guild_id=? AND level=? AND role_id=?", (ctx.guild.id, int(level), int(role_id))
    )
    if not cur.rowcount:
        raise ValueError("That role reward no longer exists.")
    return [f"Role reward removed: {_role_name(ctx.guild, int(role_id))} at level {level}"]


@action(MODULE, "noxp_channel_add")
async def noxp_channel_add(ctx: ActionContext, payload: dict) -> list:
    channel = need_channel(ctx.guild, payload.get("values") or {}, "channel", "Channel")
    if await xp_engine.is_no_xp_channel(ctx.guild.id, channel.id):
        raise ValueError("That channel is already a no-XP channel.")
    await db.raw_execute("INSERT INTO xp_no_xp_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, channel.id))
    return [f"No-XP channel added: #{channel.name}"]


@action(MODULE, "noxp_channel_remove")
async def noxp_channel_remove(ctx: ActionContext, payload: dict) -> list:
    raw = str(payload.get("id") or "")
    if not raw.isdigit():
        raise ValueError("That channel is not in the list.")
    cur = await db.raw_execute("DELETE FROM xp_no_xp_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, int(raw)))
    if not cur.rowcount:
        raise ValueError("That channel is not in the list.")
    return [f"No-XP channel removed: {_channel_name(ctx.guild, int(raw))}"]


@action(MODULE, "noxp_role_add")
async def noxp_role_add(ctx: ActionContext, payload: dict) -> list:
    role = need_role(ctx.guild, payload.get("values") or {}, "role", "Role")
    existing = await db.raw_fetchone("SELECT 1 FROM xp_no_xp_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
    if existing:
        raise ValueError("That role is already a no-XP role.")
    await db.raw_execute("INSERT INTO xp_no_xp_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
    return [f"No-XP role added: {role.name}"]


@action(MODULE, "noxp_role_remove")
async def noxp_role_remove(ctx: ActionContext, payload: dict) -> list:
    raw = str(payload.get("id") or "")
    if not raw.isdigit():
        raise ValueError("That role is not in the list.")
    cur = await db.raw_execute("DELETE FROM xp_no_xp_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, int(raw)))
    if not cur.rowcount:
        raise ValueError("That role is not in the list.")
    return [f"No-XP role removed: {_role_name(ctx.guild, int(raw))}"]


@action(MODULE, "multiplier_add")
async def multiplier_add(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    values = payload.get("values") or {}
    scope = need_choice(values, "scope", "Applies to", list(SCOPE_LABELS))
    try:
        value = float(need_text(values, "value", "Multiplier", maxlen=8))
    except ValueError:
        raise ValueError("Multiplier must be a number.")
    if not 0 < value <= MAX_MULTIPLIER:
        raise ValueError(f"Multiplier must be greater than 0 and at most {MAX_MULTIPLIER:g}.")
    scope_id = None
    if scope == xp_engine.SCOPE_CHANNEL:
        scope_id = need_channel(guild, values, "channel", "Channel").id
    elif scope == xp_engine.SCOPE_ROLE:
        scope_id = need_role(guild, values, "role", "Role").id
    multiplier_id = xp_engine.new_multiplier_id()
    await db.raw_execute(
        "INSERT INTO xp_multipliers (multiplier_id, guild_id, scope_type, scope_id, multiplier) VALUES (?, ?, ?, ?, ?)",
        (multiplier_id, guild.id, scope, scope_id, value),
    )
    return [f"Multiplier {multiplier_id} added: {SCOPE_LABELS[scope].lower()} at {value:g}x"]


@action(MODULE, "multiplier_remove")
async def multiplier_remove(ctx: ActionContext, payload: dict) -> list:
    multiplier_id = str(payload.get("id") or "").upper()
    cur = await db.raw_execute(
        "DELETE FROM xp_multipliers WHERE multiplier_id=? AND guild_id=?", (multiplier_id, ctx.guild.id)
    )
    if not cur.rowcount:
        raise ValueError("That multiplier no longer exists.")
    return [f"Multiplier removed: {multiplier_id}"]


def _target_values(payload: dict) -> dict:
    values = dict(payload.get("values") or {})
    if payload.get("id"):
        values["user_id"] = payload["id"]
    return values


@action(MODULE, "xp_set")
async def xp_set(ctx: ActionContext, payload: dict) -> list:
    values = _target_values(payload)
    member = _member(ctx.guild, values)
    amount = need_int(values, "amount", "Total XP", 0, MAX_XP)
    level = xp_engine.level_from_xp(amount)
    await db.raw_execute(
        "INSERT INTO member_xp (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
        (ctx.guild.id, member.id, amount, level),
    )
    return [f"Set {member.display_name} to {amount:,} XP (level {level})"]


@action(MODULE, "xp_reset")
async def xp_reset(ctx: ActionContext, payload: dict) -> list:
    member = _member(ctx.guild, _target_values(payload))
    await db.raw_execute(
        "INSERT INTO member_xp (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=0, level=0",
        (ctx.guild.id, member.id),
    )
    return [f"Reset XP for {member.display_name}"]
