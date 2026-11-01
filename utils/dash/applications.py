from __future__ import annotations

import discord

from utils import applications as store
from utils.dash.base import (
    ActionContext, action, button, fld, need_bool, need_int, need_text, opt_channel, row, section, table,
)

MODULE = "applications"
LIMIT = 25


def _cog(ctx: ActionContext):
    cog = ctx.bot.get_cog("Applications")
    if cog is None:
        raise ValueError("The applications system is not loaded.")
    return cog


def _reviewer(ctx: ActionContext) -> discord.Member:
    member = ctx.guild.get_member(ctx.user_id)
    if member is None:
        raise ValueError("You must be a member of this server to review applications.")
    return member


def _form_fields() -> list:
    return [
        fld("enabled", "Accepting applications", "bool"),
        fld("channel", "Review channel", "channel", help="Where new applications are posted for reviewers."),
        fld("require_reason", "Require a reason to deny", "bool"),
        fld("interview_delete", "Delete interview channel after accept or deny", "bool"),
        fld("interview_delay", "Minutes before deleting (0 is right away)", "int", lo=0, hi=1440),
    ]


def _form_values(form: dict) -> dict:
    return {
        "enabled": bool(form["enabled"]),
        "channel": str(form["channel_id"]) if form["channel_id"] else "",
        "require_reason": bool(form["require_reason"]),
        "interview_delete": bool(form["interview_delete"]),
        "interview_delay": form["interview_delay_minutes"],
    }


@section(MODULE)
async def forms_section(guild: discord.Guild) -> dict:
    forms = await store.list_forms(guild.id)
    rows = []
    for name, form in forms.items():
        channel = guild.get_channel(form["channel_id"]) if form["channel_id"] else None
        cleanup = f"after {form['interview_delay_minutes']}m" if form["interview_delete"] and form["interview_delay_minutes"] else (
            "right away" if form["interview_delete"] else "off")
        rows.append(row(
            name,
            [form["title"] or name, "Open" if form["enabled"] else "Closed", f"#{channel.name}" if channel else "Not set",
             len(form["questions"]), cleanup],
            actions=[button("form_save", "Settings", _form_fields(), title=f"Settings for {name}", prefill=True, submit="Save settings")],
            values=_form_values(form),
        ))
    return table(
        "forms", f"Application forms ({len(forms)})", ["Form", "Status", "Review channel", "Questions", "Delete interview"], rows,
        "No forms yet. Create one with the application create command, then manage it here.",
        description="Build questions and roles with the application commands. Review channel, reasons and interview cleanup are set here.",
    )


@section(MODULE)
async def pending_section(guild: discord.Guild) -> dict:
    from utils import db

    rows_db = await db.raw_fetch(
        "SELECT app_id FROM app_submissions WHERE guild_id=? AND status='pending' ORDER BY app_id LIMIT ?", (guild.id, LIMIT))
    forms = await store.list_forms(guild.id)
    rows = []
    for r in rows_db:
        sub = await store.get_sub(guild.id, r["app_id"])
        if sub is None:
            continue
        form = forms.get(sub["form"]) or store._merge({})
        user = guild.get_member(sub["user_id"])
        up, down = await store.vote_counts(guild.id, sub["app_id"])
        preview = "; ".join(f"{a.get('q', '')[:30]}: {str(a.get('a', ''))[:60]}" for a in sub["answers"][:3]) if isinstance(sub["answers"], list) else ""
        actions = [
            button("app_read", "Read", style="ghost", title=f"Application #{sub['app_id']}"),
            button("app_accept", "Accept", style="primary", confirm=f"Accept application #{sub['app_id']}? Roles and the DM are applied now."),
            button("app_deny", "Deny", [fld("reason", "Reason", "textarea", maxlen=500,
                                          help="Required for this form." if form["require_reason"] else "Optional. Sent to the applicant.")],
                   style="danger", title=f"Deny application #{sub['app_id']}", submit="Deny"),
        ]
        if not sub.get("interview_channel_id"):
            actions.insert(2, button("app_interview", "Interview", confirm="Open a private interview channel with the applicant?"))
        rows.append(row(
            sub["app_id"],
            [f"#{sub['app_id']} {sub['form']}", user.display_name if user else sub["user_id"], f"+{up} / -{down}", preview or "-"],
            actions=actions,
        ))
    return table(
        "pending", "Pending applications", ["Application", "Applicant", "Votes", "Answers"], rows, "No applications are waiting for review.",
        description="Reviewers need Manage Server or a reviewer role for the form. Your decision runs as you and is recorded under your name.",
    )


@section(MODULE)
async def recent_section(guild: discord.Guild) -> dict:
    from utils import db

    rows_db = await db.raw_fetch(
        "SELECT app_id FROM app_submissions WHERE guild_id=? AND status!='pending' ORDER BY decided_at DESC LIMIT ?", (guild.id, 15))
    rows = []
    for r in rows_db:
        sub = await store.get_sub(guild.id, r["app_id"])
        if sub is None:
            continue
        user = guild.get_member(sub["user_id"])
        reviewer = guild.get_member(sub["reviewer_id"]) if sub.get("reviewer_id") else None
        rows.append(row(
            sub["app_id"],
            [f"#{sub['app_id']} {sub['form']}", user.display_name if user else sub["user_id"],
             store.STATUS_LABELS.get(sub["status"], sub["status"]), reviewer.display_name if reviewer else "-",
             "Open" if sub.get("interview_channel_id") else "-"],
            actions=[button("app_read", "Read", title=f"Application #{sub['app_id']}")],
        ))
    return table("recent", "Recent decisions", ["Application", "Applicant", "Result", "Reviewer", "Interview"], rows, "Nothing has been decided yet.")


async def _pending(ctx: ActionContext, payload: dict) -> tuple[dict, dict]:
    try:
        app_id = int(payload.get("id"))
    except (TypeError, ValueError):
        raise ValueError("Unknown application.")
    sub = await store.get_sub(ctx.guild.id, app_id)
    if sub is None:
        raise ValueError("That application no longer exists.")
    form = await store.get_form(ctx.guild.id, sub["form"]) or store._merge({})
    return sub, form


@action(MODULE, "app_read")
async def app_read(ctx: ActionContext, payload: dict) -> list:
    sub, _ = await _pending(ctx, payload)
    lines = [f"#{sub['app_id']} ({sub['status']})"]
    if isinstance(sub["answers"], list):
        for a in sub["answers"]:
            lines.append(f"{str(a.get('q', ''))[:80]}: {str(a.get('a', ''))[:300]}")
    return lines


@action(MODULE, "app_accept")
async def app_accept(ctx: ActionContext, payload: dict) -> list:
    sub, _ = await _pending(ctx, payload)
    ok, message = await _cog(ctx).decide(ctx.guild, sub["app_id"], True, _reviewer(ctx), "")
    if not ok:
        raise ValueError(message)
    return [f"Accepted application #{sub['app_id']}"]


@action(MODULE, "app_deny")
async def app_deny(ctx: ActionContext, payload: dict) -> list:
    sub, form = await _pending(ctx, payload)
    reason = need_text(payload.get("values") or {}, "reason", "Reason", maxlen=500, required=bool(form["require_reason"]))
    ok, message = await _cog(ctx).decide(ctx.guild, sub["app_id"], False, _reviewer(ctx), reason)
    if not ok:
        raise ValueError(message)
    return [f"Denied application #{sub['app_id']}"]


@action(MODULE, "app_interview")
async def app_interview(ctx: ActionContext, payload: dict) -> list:
    sub, form = await _pending(ctx, payload)
    cog = _cog(ctx)
    reviewer = _reviewer(ctx)
    if not cog.is_reviewer(reviewer, form):
        raise ValueError("You are not allowed to review this application.")
    if sub["status"] != "pending":
        raise ValueError("This application was already decided.")
    if sub.get("interview_channel_id"):
        raise ValueError("An interview channel already exists.")
    channel = await cog._open_interview(ctx.guild, sub, form)
    if channel is None:
        raise ValueError("Could not create the interview channel. Check that the bot has Manage Channels.")
    sub["interview_channel_id"] = channel.id
    await cog._refresh_review(ctx.guild, sub)
    return [f"Interview channel created: #{channel.name}"]


@action(MODULE, "form_save")
async def form_save(ctx: ActionContext, payload: dict) -> list:
    name = str(payload.get("id") or "")
    form = await store.get_form(ctx.guild.id, name)
    if form is None:
        raise ValueError("That form no longer exists.")
    values = payload.get("values") or {}
    channel = opt_channel(ctx.guild, values, "channel", "Review channel")
    form["enabled"] = need_bool(values, "enabled")
    form["require_reason"] = need_bool(values, "require_reason")
    form["interview_delete"] = need_bool(values, "interview_delete")
    form["interview_delay_minutes"] = need_int(values, "interview_delay", "Minutes before deleting", 0, 1440)
    if channel is not None:
        form["channel_id"] = channel.id
    await store.save_form(ctx.guild.id, name, form)
    return [f"Updated form {name}"]
