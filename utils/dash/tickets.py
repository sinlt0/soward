from __future__ import annotations

import json

import discord

import config
from utils import db, tickets as tk
from utils.dash.base import (
    ActionContext, action, button, fld, need_bool, need_categories, need_choice, need_lines, need_roles, need_text,
    opt_channel, row, section, table,
)

MODULE = "tickets"


def _cog(ctx: ActionContext):
    return ctx.bot.get_cog("Tickets")


async def _panel_fields(guild: discord.Guild) -> list:
    staff_limit = await tk.limit_for(guild.id, "staff_roles")
    cat_limit = await tk.limit_for(guild.id, "categories")
    q_limit = await tk.limit_for(guild.id, "questions")
    return [
        fld("name", "Panel name", "text", maxlen=60),
        fld("button_label", "Button label", "text", maxlen=80, placeholder="Open a ticket"),
        fld("welcome_text", "Panel and welcome text", "textarea", maxlen=1000, help="Shown on the panel and in new tickets. Leave empty for the default."),
        fld("staff_roles", "Staff roles", "roles", help=f"Up to {staff_limit}. Staff can see and manage every ticket from this panel."),
        fld("categories", "Ticket categories", "categories", help=f"Up to {cat_limit}. New tickets go to the category with the most room."),
        fld("questions", "Intake questions", "lines", maxlen=45, help=f"One per line, up to {q_limit}, 45 characters each."),
        fld("transcript_channel", "Transcript channel", "channel", help="Leave empty to use the server ticket log channel."),
        fld("ask_subject", "Ask for a subject", "bool"),
        fld("one_per_user", "One open ticket per member", "bool"),
    ]


def _panel_values(panel: dict) -> dict:
    return {
        "name": panel["name"],
        "button_label": panel["button_label"],
        "welcome_text": panel["welcome_text"] or "",
        "staff_roles": [str(i) for i in tk.parse_ids(panel["staff_role_ids"])],
        "categories": [str(i) for i in tk.parse_ids(panel["category_ids"])],
        "questions": tk.parse_list(panel["questions"]),
        "transcript_channel": str(panel["transcript_channel_id"]) if panel["transcript_channel_id"] else "",
        "ask_subject": bool(panel["ask_subject"]),
        "one_per_user": bool(panel["one_per_user"]),
    }


@section(MODULE)
async def panels_section(guild: discord.Guild) -> dict:
    panels = await tk.list_panels(guild.id)
    limit = await tk.limit_for(guild.id, "panels")
    fields = await _panel_fields(guild)
    rows = []
    for p in panels:
        channel = guild.get_channel(p["channel_id"]) if p["channel_id"] else None
        rows.append(row(
            p["panel_id"],
            [p["name"], f"#{channel.name}" if channel else "Not posted",
             len(tk.parse_ids(p["staff_role_ids"])), len(tk.parse_list(p["questions"]))],
            actions=[
                button("panel_save", "Edit", fields, title=f"Edit {p['name']}", prefill=True, submit="Save panel"),
                button("panel_post", "Post" if not channel else "Repost", [fld("channel", "Channel", "channel")],
                       style="primary", title=f"Post {p['name']}", submit="Post panel"),
                button("panel_delete", "Delete", style="danger",
                       confirm=f"Delete {p['name']}? The panel message is removed. Open tickets are not affected."),
            ],
            values=_panel_values(p),
        ))
    return table(
        "panels", f"Panels ({len(panels)}/{limit})", ["Name", "Channel", "Staff roles", "Questions"], rows,
        "No panels yet. Create one to let members open tickets.",
        description="Each panel is a message with an Open ticket button, its own staff, categories and intake form.",
        buttons=[button("panel_save", "Create panel", fields, style="primary", title="Create panel", submit="Create panel")],
    )


@section(MODULE)
async def open_section(guild: discord.Guild) -> dict:
    open_tickets = await tk.list_open(guild.id, config.DASHBOARD_LIST_LIMIT)
    total = await tk.active_count(guild.id)
    rows = []
    for t in open_tickets:
        channel = guild.get_channel(t["channel_id"])
        owner = guild.get_member(t["owner_id"])
        claimed = guild.get_member(t["claimed_by"]) if t["claimed_by"] else None
        rows.append(row(
            t["ticket_id"],
            [f"#{t['number']:04d} {('#' + channel.name) if channel else 'deleted channel'}",
             owner.display_name if owner else t["owner_id"], t["priority"],
             claimed.display_name if claimed else "Unclaimed"],
            actions=[
                button("ticket_priority", "Priority",
                       [fld("priority", "Priority", "select", value=t["priority"], options=[(p, p.title()) for p in config.TICKET_PRIORITIES])],
                       title=f"Priority for #{t['number']:04d}", prefill=False, submit="Set priority"),
                button("ticket_close", "Close", [fld("reason", "Reason", "text", maxlen=300)], style="danger",
                       title=f"Close #{t['number']:04d}", submit="Close ticket"),
            ],
        ))
    note = f" Showing {len(open_tickets)} of {total}." if total > len(open_tickets) else ""
    return table("open", "Open tickets", ["Ticket", "Opened by", "Priority", "Claimed by"], rows, "There are no open tickets.",
                 description="Closing sends the transcript to the log channel and the member." + note)


@action(MODULE, "panel_save")
async def panel_save(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    values = payload.get("values") or {}
    panel_id = payload.get("id")
    existing = await tk.get_panel(panel_id) if panel_id else None
    if panel_id and (existing is None or existing["guild_id"] != guild.id):
        raise ValueError("That panel no longer exists.")

    name = need_text(values, "name", "Panel name", maxlen=60)
    clash = await tk.find_panel(guild.id, name)
    if clash and (existing is None or clash["panel_id"] != existing["panel_id"]):
        raise ValueError("A panel with that name already exists.")
    if existing is None:
        limit = await tk.limit_for(guild.id, "panels")
        if len(await tk.list_panels(guild.id)) >= limit:
            raise ValueError(f"Panel limit reached ({limit}). Premium raises it to {tk.premium_limit('panels')}.")

    label = need_text(values, "button_label", "Button label", maxlen=80, required=False) or "Open a ticket"
    welcome = need_text(values, "welcome_text", "Panel text", maxlen=1000, required=False) or None
    staff = need_roles(guild, values, "staff_roles", "Staff roles", limit=await tk.limit_for(guild.id, "staff_roles"))
    categories = need_categories(guild, values, "categories", "Ticket categories", limit=await tk.limit_for(guild.id, "categories"))
    questions = need_lines(values, "questions", "Intake questions", limit=await tk.limit_for(guild.id, "questions"), maxlen=45)
    transcript = opt_channel(guild, values, "transcript_channel", "Transcript channel")

    if existing is None:
        panel_id = await tk.create_panel(guild.id, name)
        old_staff: list[int] = []
    else:
        old_staff = tk.parse_ids(existing["staff_role_ids"])

    await tk.update_panel(
        panel_id,
        name=name, button_label=label[:80], welcome_text=welcome,
        staff_role_ids=json.dumps([r.id for r in staff]),
        category_ids=json.dumps([c.id for c in categories]),
        questions=json.dumps(questions),
        transcript_channel_id=transcript.id if transcript else None,
        ask_subject=int(need_bool(values, "ask_subject")),
        one_per_user=int(need_bool(values, "one_per_user")),
    )

    cog = _cog(ctx)
    if cog is not None and existing is not None:
        new_ids = {r.id for r in staff}
        for rid in set(old_staff) - new_ids:
            role = guild.get_role(rid)
            if role is not None:
                await cog._sync_staff_role(guild, panel_id, role, False)
        for role in staff:
            if role.id not in old_staff:
                await cog._sync_staff_role(guild, panel_id, role, True)
        await cog._refresh_panel(guild, panel_id)
    return [f"Panel {'created' if existing is None else 'updated'}: {name}"]


@action(MODULE, "panel_post")
async def panel_post(ctx: ActionContext, payload: dict) -> list:
    from cogs import tickets as ticket_cog

    guild = ctx.guild
    panel = await tk.get_panel(payload.get("id") or "")
    if panel is None or panel["guild_id"] != guild.id:
        raise ValueError("That panel no longer exists.")
    channel = opt_channel(guild, payload.get("values") or {}, "channel", "Channel")
    if channel is None:
        raise ValueError("Channel is required.")
    if not tk.parse_ids(panel["staff_role_ids"]):
        raise ValueError("Add at least one staff role to this panel before posting it.")
    if panel["channel_id"] and panel["message_id"]:
        old_channel = guild.get_channel(panel["channel_id"])
        if old_channel is not None:
            try:
                old = await old_channel.fetch_message(panel["message_id"])
                await old.delete()
            except discord.HTTPException:
                pass
    try:
        message = await channel.send(view=ticket_cog.build_panel_view(panel))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the message: {str(exc)[:150]}")
    await tk.update_panel(panel["panel_id"], channel_id=channel.id, message_id=message.id)
    return [f"Posted panel {panel['name']} in #{channel.name}"]


@action(MODULE, "panel_delete")
async def panel_delete(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    panel = await tk.get_panel(payload.get("id") or "")
    if panel is None or panel["guild_id"] != guild.id:
        raise ValueError("That panel no longer exists.")
    if panel["channel_id"] and panel["message_id"]:
        channel = guild.get_channel(panel["channel_id"])
        if channel is not None:
            try:
                message = await channel.fetch_message(panel["message_id"])
                await message.delete()
            except discord.HTTPException:
                pass
    await tk.delete_panel(panel["panel_id"])
    return [f"Panel deleted: {panel['name']}"]


async def _open_ticket(ctx: ActionContext, payload: dict) -> dict:
    found = await db.raw_fetchone("SELECT * FROM tickets WHERE ticket_id=? AND guild_id=? AND status='open'", (payload.get("id") or "", ctx.guild.id))
    if found is None:
        raise ValueError("That ticket is already closed.")
    return dict(found)


@action(MODULE, "ticket_priority")
async def ticket_priority(ctx: ActionContext, payload: dict) -> list:
    ticket = await _open_ticket(ctx, payload)
    level = need_choice(payload.get("values") or {}, "priority", "Priority", list(config.TICKET_PRIORITIES))
    await tk.update_ticket(ticket["ticket_id"], priority=level)
    return [f"Ticket #{ticket['number']:04d} priority: {level}"]


@action(MODULE, "ticket_close")
async def ticket_close(ctx: ActionContext, payload: dict) -> list:
    from cogs import tickets as ticket_cog

    ticket = await _open_ticket(ctx, payload)
    reason = need_text(payload.get("values") or {}, "reason", "Reason", maxlen=300, required=False) or "Closed from the dashboard"
    channel = ctx.guild.get_channel(ticket["channel_id"])
    closer = ctx.guild.get_member(ctx.user_id)
    await ticket_cog.close_ticket(ctx.bot, ctx.guild, channel, ticket, closer, reason)
    return [f"Closed ticket #{ticket['number']:04d}"]
