from __future__ import annotations

import discord

from utils import appeals as store
from utils.dash.base import ActionContext, action, button, fld, need_text, row, section, table

MODULE = "appeals"
LIMIT = 25


def _cog(ctx: ActionContext):
    cog = ctx.bot.get_cog("Appeals")
    if cog is None:
        raise ValueError("The appeals system is not loaded.")
    return cog


def _reviewer(ctx: ActionContext) -> discord.Member:
    member = ctx.guild.get_member(ctx.user_id)
    if member is None:
        raise ValueError("You must be a member of this server to review appeals.")
    return member


@section(MODULE)
async def pending_section(guild: discord.Guild) -> dict:
    appeals = await store.listing(guild.id, "pending", LIMIT)
    cfg = await store.get_config(guild.id)
    rows = []
    for appeal in appeals:
        up, down = await store.votes(appeal["appeal_id"])
        preview = "; ".join(f"{str(a.get('a', ''))[:50]}" for a in appeal["answers"][:2])
        votes = f"+{up} / -{down} (needs {cfg['votes']})" if cfg["votes"] > 1 else "-"
        rows.append(row(
            appeal["appeal_id"],
            [f"#{appeal['appeal_id']}", appeal.get("user_name") or appeal["user_id"], appeal.get("ban_reason") or "-", votes, preview or "-"],
            actions=[
                button("appeal_read", "Read", title=f"Appeal #{appeal['appeal_id']}"),
                button("appeal_accept", "Accept", style="primary", confirm=f"Accept appeal #{appeal['appeal_id']} and unban the member?"),
                button("appeal_deny", "Deny", [fld("note", "Reason (sent to the member)", "textarea", maxlen=500, help="Optional.")],
                       style="danger", title=f"Deny appeal #{appeal['appeal_id']}", submit="Deny"),
            ],
        ))
    return table(
        "pending", "Pending appeals", ["Appeal", "Member", "Ban reason", "Votes", "Answers"], rows, "No appeals are waiting for review.",
        description="Your decision runs as you and is recorded under your name. Accepting unbans the member and messages them.",
    )


@section(MODULE)
async def recent_section(guild: discord.Guild) -> dict:
    rows = []
    for appeal in [a for a in await store.listing(guild.id, None, 30) if a["status"] != "pending"][:15]:
        reviewer = guild.get_member(appeal["reviewer_id"]) if appeal.get("reviewer_id") else None
        rows.append(row(
            appeal["appeal_id"],
            [f"#{appeal['appeal_id']}", appeal.get("user_name") or appeal["user_id"], store.STATUS_LABELS.get(appeal["status"], appeal["status"]),
             reviewer.display_name if reviewer else "-"],
            actions=[button("appeal_read", "Read", title=f"Appeal #{appeal['appeal_id']}")],
        ))
    return table("recent", "Recent decisions", ["Appeal", "Member", "Result", "Reviewer"], rows, "Nothing has been decided yet.")


async def _appeal(ctx: ActionContext, payload: dict) -> dict:
    appeal = await store.get(ctx.guild.id, str(payload.get("id") or ""))
    if appeal is None:
        raise ValueError("That appeal no longer exists.")
    return appeal


@action(MODULE, "appeal_read")
async def appeal_read(ctx: ActionContext, payload: dict) -> list:
    appeal = await _appeal(ctx, payload)
    lines = [f"#{appeal['appeal_id']} ({appeal['status']})"]
    if appeal.get("ban_reason"):
        lines.append(f"Ban reason: {appeal['ban_reason'][:200]}")
    for item in appeal["answers"]:
        lines.append(f"{str(item.get('q', ''))[:80]}: {str(item.get('a', ''))[:400]}")
    return lines


@action(MODULE, "appeal_accept")
async def appeal_accept(ctx: ActionContext, payload: dict) -> list:
    appeal = await _appeal(ctx, payload)
    ok, message = await _cog(ctx).cast(ctx.guild, appeal["appeal_id"], True, _reviewer(ctx), "")
    if not ok:
        raise ValueError(message)
    return [f"Appeal #{appeal['appeal_id']}: {message}"]


@action(MODULE, "appeal_deny")
async def appeal_deny(ctx: ActionContext, payload: dict) -> list:
    appeal = await _appeal(ctx, payload)
    note = need_text(payload.get("values") or {}, "note", "Reason", maxlen=500, required=False)
    ok, message = await _cog(ctx).cast(ctx.guild, appeal["appeal_id"], False, _reviewer(ctx), note)
    if not ok:
        raise ValueError(message)
    return [f"Appeal #{appeal['appeal_id']}: {message}"]
