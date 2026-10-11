from __future__ import annotations

import datetime
import re
import time

import discord

import config
from utils import cases, db, emoji_manager
from utils.components import info_layout
from utils.dash.base import ActionContext, action, button, fld, need_text, row, section, table

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
MAX_TIMEOUT = 28 * 86400


def _duration(values: dict, key: str, label: str, *, required: bool, ceiling: int) -> int:
    text = need_text(values, key, label, maxlen=40, required=required).lower().replace(" ", "")
    if not text:
        return 0
    if not re.fullmatch(r"(\d+[smhdw])+", text):
        raise ValueError(f"{label} must look like 30m, 2h or 1d12h.")
    total = sum(int(n) * UNITS[u] for n, u in re.findall(r"(\d+)([smhdw])", text))
    if total < 1 or total > ceiling:
        raise ValueError(f"{label} is out of range.")
    return total


def _user_id(values: dict) -> int:
    raw = str(values.get("user_id", "")).strip().strip("<@!>")
    if not raw.isdigit() or not 15 <= len(raw) <= 21:
        raise ValueError("Enter the member's Discord user ID.")
    return int(raw)


def _reason(values: dict) -> str:
    return need_text(values, "reason", "Reason", maxlen=400, required=False) or "No reason provided"


def _perm(ctx: ActionContext, name: str) -> discord.Member:
    actor = ctx.guild.get_member(ctx.user_id)
    if ctx.user_id in config.ALL_PRIVILEGED_IDS or ctx.user_id == ctx.guild.owner_id:
        return actor
    if actor is None:
        raise ValueError("You are not a member of this server.")
    perms = actor.guild_permissions
    if not (perms.administrator or getattr(perms, name)):
        raise ValueError(f"You need the {name.replace('_', ' ').title()} permission in this server for that action.")
    return actor


async def _target(ctx: ActionContext, actor, user_id: int) -> discord.Member:
    member = ctx.guild.get_member(user_id)
    if member is None:
        try:
            member = await ctx.guild.fetch_member(user_id)
        except discord.HTTPException:
            raise ValueError("That user is not in this server.")
    guard(ctx, actor, member)
    return member


def guard(ctx: ActionContext, actor, member: discord.Member) -> None:
    me = ctx.guild.me
    if member.id == ctx.guild.owner_id:
        raise ValueError("The server owner cannot be moderated.")
    if member.id == me.id:
        raise ValueError("The bot cannot moderate itself.")
    if member.id == ctx.user_id:
        raise ValueError("You cannot moderate yourself.")
    if member.top_role >= me.top_role:
        raise ValueError("That member's top role is at or above the bot's top role.")
    privileged = ctx.user_id in config.ALL_PRIVILEGED_IDS or ctx.user_id == ctx.guild.owner_id
    if not privileged and actor is not None and member.top_role >= actor.top_role:
        raise ValueError("You cannot act on someone with a higher or equal role.")


async def _finish(ctx: ActionContext, kind: str, user_id: int, reason: str, duration=None, log_reason=None) -> str:
    case_id = await cases.create_mod_case(ctx.guild.id, kind, user_id, ctx.user_id, reason, duration)
    cog = ctx.bot.get_cog("Moderation")
    if cog is not None:
        await cog._log(ctx.guild, "ban" if kind == "tempban" else kind, user_id=user_id, moderator_id=ctx.user_id,
                       reason=log_reason or reason, case_id=case_id)
    return case_id


def _stamp(ctx: ActionContext, reason: str) -> str:
    return f"{ctx.user_name} (dashboard) | {reason}"[:512]


@section("moderation")
async def actions_section(guild: discord.Guild) -> dict:
    user = fld("user_id", "Member ID", "text", maxlen=25, placeholder="123456789012345678", help="Enable Developer Mode in Discord, then right click a member and copy their ID.")
    reason = fld("reason", "Reason", "text", maxlen=400)
    return table(
        "actions", "Take action", ["Action", "What it does"], [
            row("warn", ["Warn", "Records a warning and sends the member a direct message."], [button("mod_warn", "Warn", [user, reason], title="Warn a member", submit="Warn")]),
            row("mute", ["Timeout", "Stops the member talking for a set time."], [
                button("mod_mute", "Timeout", [user, fld("duration", "Duration", "text", maxlen=40, placeholder="1h", help="Up to 28 days."), reason], title="Timeout a member", submit="Timeout"),
                button("mod_unmute", "Remove", [user, reason], title="Remove a timeout", submit="Remove timeout"),
            ]),
            row("kick", ["Kick", "Removes the member. They can rejoin."], [button("mod_kick", "Kick", [user, reason], style="danger", title="Kick a member", submit="Kick")]),
            row("ban", ["Ban", "Bans a member by ID, optionally for a set time."], [
                button("mod_ban", "Ban", [user, fld("duration", "Duration", "text", maxlen=40, placeholder="Leave empty for permanent"), reason], style="danger", title="Ban a user", submit="Ban"),
                button("mod_unban", "Unban", [user, reason], title="Unban a user", submit="Unban"),
            ]),
        ], "", description="Every action is recorded as a case and follows the same role hierarchy rules as the commands.",
    )


@section("moderation")
async def warnings_section(guild: discord.Guild) -> dict:
    found = await db.raw_fetch("SELECT * FROM warn_cases WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild.id, config.DASHBOARD_LIST_LIMIT))
    rows = []
    for w in found:
        member = guild.get_member(w["user_id"])
        rows.append(row(
            w["case_id"],
            [w["case_id"], member.display_name if member else w["user_id"], (w["reason"] or "No reason")[:100],
             time.strftime("%Y-%m-%d", time.gmtime(float(w["created_at"])))],
            actions=[button("mod_delwarn", "Delete", style="danger", confirm=f"Delete warning {w['case_id']}?")],
        ))
    return table("warnings", "Recent warnings", ["Case", "Member", "Reason", "Date"], rows, "No warnings have been issued.")


@action("moderation", "mod_warn")
async def mod_warn(ctx: ActionContext, payload: dict) -> list:
    e = emoji_manager.get
    values = payload.get("values") or {}
    actor = _perm(ctx, "manage_messages")
    member = await _target(ctx, actor, _user_id(values))
    reason = _reason(values)
    case_id = await cases.create_warn(ctx.guild.id, member.id, ctx.user_id, reason)
    try:
        await member.send(view=info_layout(f"{e('warn')} You were warned in {ctx.guild.name}", f"**Reason:** {reason}\n**Case:** `{case_id}`"))
    except discord.HTTPException:
        pass
    cog = ctx.bot.get_cog("Moderation")
    if cog is not None:
        await cog._log(ctx.guild, "warn", user_id=member.id, moderator_id=ctx.user_id, reason=reason, case_id=case_id)
    return [f"Warned {member.display_name} ({case_id})"]


@action("moderation", "mod_mute")
async def mod_mute(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    actor = _perm(ctx, "moderate_members")
    member = await _target(ctx, actor, _user_id(values))
    seconds = _duration(values, "duration", "Duration", required=True, ceiling=MAX_TIMEOUT)
    reason = _reason(values)
    until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
    try:
        await member.timeout(until, reason=_stamp(ctx, reason))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the timeout: {str(exc)[:150]}")
    case_id = await _finish(ctx, "mute", member.id, reason, seconds)
    return [f"Timed out {member.display_name} ({case_id})"]


@action("moderation", "mod_unmute")
async def mod_unmute(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    actor = _perm(ctx, "moderate_members")
    member = await _target(ctx, actor, _user_id(values))
    reason = _reason(values)
    try:
        await member.timeout(None, reason=_stamp(ctx, reason))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the change: {str(exc)[:150]}")
    case_id = await _finish(ctx, "unmute", member.id, reason)
    return [f"Removed timeout for {member.display_name} ({case_id})"]


@action("moderation", "mod_kick")
async def mod_kick(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    actor = _perm(ctx, "kick_members")
    member = await _target(ctx, actor, _user_id(values))
    reason = _reason(values)
    try:
        await member.kick(reason=_stamp(ctx, reason))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the kick: {str(exc)[:150]}")
    case_id = await _finish(ctx, "kick", member.id, reason)
    return [f"Kicked {member.display_name} ({case_id})"]


@action("moderation", "mod_ban")
async def mod_ban(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    actor = _perm(ctx, "ban_members")
    user_id = _user_id(values)
    seconds = _duration(values, "duration", "Duration", required=False, ceiling=3650 * 86400)
    reason = _reason(values)
    member = ctx.guild.get_member(user_id)
    if member is not None:
        guard(ctx, actor, member)
    elif user_id in (ctx.guild.owner_id, ctx.guild.me.id, ctx.user_id):
        raise ValueError("That user cannot be banned.")
    try:
        await ctx.guild.ban(discord.Object(id=user_id), reason=_stamp(ctx, reason))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the ban: {str(exc)[:150]}")
    if seconds:
        await db.raw_execute(
            "INSERT INTO temp_bans (guild_id, user_id, unban_at, reason, moderator_id) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET unban_at=excluded.unban_at, reason=excluded.reason, moderator_id=excluded.moderator_id",
            (ctx.guild.id, user_id, time.time() + seconds, reason, ctx.user_id),
        )
    case_id = await _finish(ctx, "tempban" if seconds else "ban", user_id, reason, seconds or None)
    return [f"Banned {user_id} ({case_id})"]


@action("moderation", "mod_unban")
async def mod_unban(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    _perm(ctx, "ban_members")
    user_id = _user_id(values)
    reason = _reason(values)
    try:
        await ctx.guild.unban(discord.Object(id=user_id), reason=_stamp(ctx, reason))
    except discord.NotFound:
        raise ValueError("That user is not banned.")
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the unban: {str(exc)[:150]}")
    await db.raw_execute("DELETE FROM temp_bans WHERE guild_id=? AND user_id=?", (ctx.guild.id, user_id))
    case_id = await _finish(ctx, "unban", user_id, reason)
    return [f"Unbanned {user_id} ({case_id})"]


@action("moderation", "mod_delwarn")
async def mod_delwarn(ctx: ActionContext, payload: dict) -> list:
    _perm(ctx, "manage_messages")
    case_id = str(payload.get("id") or "").upper()
    if not await cases.delete_warn(case_id, ctx.guild.id):
        raise ValueError("That warning no longer exists.")
    return [f"Deleted warning {case_id}"]
