from __future__ import annotations

import json
import random
import re
import time
import uuid

import discord

import config
from utils import db, emoji_manager
from utils.colors import ERROR, SUCCESS
from utils.dash.base import (
    ActionContext, action, button, fld, need_bool, need_channel, need_choice, need_int, need_role, need_text, opt_role, row,
    section, table,
)

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)


def _duration(values: dict, key: str, label: str) -> int:
    text = need_text(values, key, label, maxlen=40).lower().replace(" ", "")
    if not re.fullmatch(r"(\d+[smhdw])+", text):
        raise ValueError(f"{label} must look like 30m, 2h or 1d12h.")
    total = sum(int(n) * UNITS[u] for n, u in re.findall(r"(\d+)([smhdw])", text))
    if total < 10 or total > 365 * 86400:
        raise ValueError(f"{label} must be between 10 seconds and 365 days.")
    return total


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(float(ts)))


async def _giveaway(ctx: ActionContext, payload: dict, *, active: bool = True) -> dict:
    found = await db.raw_fetchone("SELECT * FROM giveaways WHERE giveaway_id=? AND guild_id=?", (payload.get("id") or "", ctx.guild.id))
    if found is None:
        raise ValueError("That giveaway no longer exists.")
    found = dict(found)
    if active and found["ended"]:
        raise ValueError("That giveaway has already ended.")
    return found


@section("giveaways")
async def giveaways_section(guild: discord.Guild) -> dict:
    found = await db.raw_fetch("SELECT * FROM giveaways WHERE guild_id=? ORDER BY ended ASC, ends_at DESC LIMIT ?", (guild.id, config.DASHBOARD_LIST_LIMIT))
    roles = await db.raw_fetch(
        "SELECT g.giveaway_id AS giveaway_id, b.role_id AS role_id, b.bonus_entries AS bonus_entries FROM giveaway_bonus_roles b"
        " JOIN giveaways g ON g.giveaway_id=b.giveaway_id WHERE g.guild_id=?", (guild.id,),
    )
    bonus = {}
    for r in roles:
        bonus.setdefault(r["giveaway_id"], []).append(r)
    rows = []
    for g in map(dict, found):
        channel = guild.get_channel(g["channel_id"])
        entries = await db.raw_fetchone("SELECT COUNT(*) AS n FROM giveaway_entries WHERE giveaway_id=?", (g["giveaway_id"],))
        values = {
            "required_role": str(g["required_role_id"]) if g["required_role_id"] else "",
            "min_age": g["min_account_age_days"], "bonus_role": "", "bonus_entries": 1,
        }
        if g["ended"]:
            acts = [button("giveaway_reroll", "Reroll", style="primary", confirm="Pick a new random winner and announce it in the giveaway channel?")]
        else:
            acts = [
                button("giveaway_edit", "Requirements", [
                    fld("required_role", "Required role", "role", help="Entrants must have this role. Leave empty for none."),
                    fld("min_age", "Minimum account age (days)", "int", lo=0, hi=3650),
                    fld("bonus_role", "Bonus entry role", "role", help="Members with this role get extra entries."),
                    fld("bonus_entries", "Extra entries for that role", "int", lo=0, hi=50, help="0 removes the bonus for the chosen role."),
                ], title=f"Edit {g['prize'][:40]}", prefill=True, submit="Save"),
                button("giveaway_end", "End now", style="primary", confirm=f"End the giveaway for {g['prize'][:60]} now and pick winners?"),
                button("giveaway_cancel", "Cancel", style="danger", confirm=f"Cancel the giveaway for {g['prize'][:60]} without picking a winner?"),
            ]
        rows.append(row(
            g["giveaway_id"],
            [g["prize"][:50], f"#{channel.name}" if channel else "deleted channel", g["winner_count"],
             "Ended" if g["ended"] else _when(g["ends_at"]), entries["n"] if entries else 0],
            actions=acts, values=values,
        ))
    return table(
        "giveaways", "Giveaways", ["Prize", "Channel", "Winners", "Ends", "Entries"], rows, "No giveaways yet.",
        description="Active giveaways first, then recent ones.",
        buttons=[button("giveaway_create", "Start giveaway", [
            fld("prize", "Prize", "text", maxlen=100),
            fld("channel", "Channel", "channel"),
            fld("duration", "Duration", "text", maxlen=40, placeholder="1h30m", help="Combine s, m, h, d and w, for example 2d or 1h30m."),
            fld("winners", "Winners", "int", value=1, lo=1, hi=20),
            fld("required_role", "Required role", "role"),
            fld("min_age", "Minimum account age (days)", "int", value=0, lo=0, hi=3650),
        ], style="primary", title="Start a giveaway", submit="Start")],
    )


@action("giveaways", "giveaway_create")
async def giveaway_create(ctx: ActionContext, payload: dict) -> list:
    from cogs.giveaways import build_giveaway_panel

    values = payload.get("values") or {}
    prize = need_text(values, "prize", "Prize", maxlen=100)
    channel = need_channel(ctx.guild, values, "channel", "Channel")
    seconds = _duration(values, "duration", "Duration")
    winners = need_int(values, "winners", "Winners", 1, 20)
    min_age = need_int(values, "min_age", "Minimum account age", 0, 3650)
    role = opt_role(ctx.guild, values, "required_role", "Required role")
    giveaway_id = str(uuid.uuid4())[:8].upper()
    ends_at = time.time() + seconds
    body = (
        f"Click the button below to enter!\n\n"
        f"**Winners:** {winners}\n**Ends:** <t:{int(ends_at)}:R>\n**Hosted by:** <@{ctx.user_id}>"
    )
    try:
        message = await channel.send(view=build_giveaway_panel(giveaway_id, prize, body), allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the message: {str(exc)[:150]}")
    await db.raw_execute(
        "INSERT INTO giveaways (giveaway_id, guild_id, channel_id, message_id, prize, winner_count, ends_at, host_id, ended,"
        " required_role_id, min_account_age_days) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (giveaway_id, ctx.guild.id, channel.id, message.id, prize, winners, ends_at, ctx.user_id, role.id if role else None, min_age),
    )
    return [f"Started giveaway: {prize}"]


@action("giveaways", "giveaway_edit")
async def giveaway_edit(ctx: ActionContext, payload: dict) -> list:
    g = await _giveaway(ctx, payload)
    values = payload.get("values") or {}
    role = opt_role(ctx.guild, values, "required_role", "Required role")
    min_age = need_int(values, "min_age", "Minimum account age", 0, 3650)
    bonus_role = opt_role(ctx.guild, values, "bonus_role", "Bonus entry role")
    await db.raw_execute("UPDATE giveaways SET required_role_id=?, min_account_age_days=? WHERE giveaway_id=?",
                         (role.id if role else None, min_age, g["giveaway_id"]))
    if bonus_role is not None:
        extra = need_int(values, "bonus_entries", "Extra entries", 0, 50)
        if extra == 0:
            await db.raw_execute("DELETE FROM giveaway_bonus_roles WHERE giveaway_id=? AND role_id=?", (g["giveaway_id"], bonus_role.id))
        else:
            await db.raw_execute(
                "INSERT INTO giveaway_bonus_roles (giveaway_id, role_id, bonus_entries) VALUES (?, ?, ?)"
                " ON CONFLICT(giveaway_id, role_id) DO UPDATE SET bonus_entries=excluded.bonus_entries",
                (g["giveaway_id"], bonus_role.id, extra),
            )
    return [f"Updated giveaway: {g['prize'][:50]}"]


@action("giveaways", "giveaway_end")
async def giveaway_end(ctx: ActionContext, payload: dict) -> list:
    g = await _giveaway(ctx, payload)
    cog = ctx.bot.get_cog("Giveaways")
    if cog is None:
        raise ValueError("The giveaway system is not loaded.")
    await cog._end_giveaway(g)
    return [f"Ended giveaway: {g['prize'][:50]}"]


@action("giveaways", "giveaway_cancel")
async def giveaway_cancel(ctx: ActionContext, payload: dict) -> list:
    from cogs.giveaways import _layout

    e = emoji_manager.get
    g = await _giveaway(ctx, payload)
    await db.raw_execute("UPDATE giveaways SET ended=1 WHERE giveaway_id=?", (g["giveaway_id"],))
    channel = ctx.guild.get_channel(g["channel_id"])
    if channel is not None and g["message_id"]:
        try:
            message = await channel.fetch_message(g["message_id"])
            await message.edit(view=_layout(f"{e('cross')} Giveaway Cancelled", f"**{g['prize']}**\n\nThis giveaway was cancelled by a moderator.", color=ERROR))
        except discord.HTTPException:
            pass
    return [f"Cancelled giveaway: {g['prize'][:50]}"]


@action("giveaways", "giveaway_reroll")
async def giveaway_reroll(ctx: ActionContext, payload: dict) -> list:
    from cogs.giveaways import _layout

    e = emoji_manager.get
    g = await _giveaway(ctx, payload, active=False)
    if not g["ended"]:
        raise ValueError("End the giveaway before rerolling.")
    entries = await db.raw_fetch("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (g["giveaway_id"],))
    user_ids = [r["user_id"] for r in entries]
    if not user_ids:
        raise ValueError("No one entered this giveaway.")
    bonus = await db.raw_fetch("SELECT role_id, bonus_entries FROM giveaway_bonus_roles WHERE giveaway_id=?", (g["giveaway_id"],))
    cog = ctx.bot.get_cog("Giveaways")
    pool = cog._get_weighted_entries(user_ids, ctx.guild, g["giveaway_id"], bonus) if cog is not None else user_ids
    winner = random.choice(pool)
    channel = ctx.guild.get_channel(g["channel_id"])
    if channel is None:
        raise ValueError("The giveaway channel no longer exists.")
    try:
        await channel.send(
            view=_layout(f"{e('giveaway')} Reroll!", f"New winner for **{g['prize']}**: <@{winner}>", color=SUCCESS),
            allowed_mentions=MENTIONS,
        )
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the message: {str(exc)[:150]}")
    return [f"Rerolled giveaway: {g['prize'][:50]}"]


RR_BINDING_MODES = ("normal", "unique", "verify", "reversed", "add_only", "remove_only")
RR_PANEL_MODES = ("toggle", "add_only", "unique")
RR_TYPES = ("reaction", "select")


async def _panel(ctx: ActionContext, panel_id) -> dict:
    from cogs.reaction_roles import get_panel

    found = await get_panel(str(panel_id or "").upper())
    if not found or found["guild_id"] != ctx.guild.id:
        raise ValueError("That panel no longer exists.")
    return dict(found)


async def _resync(ctx: ActionContext, panel: dict) -> None:
    cog = ctx.bot.get_cog("ReactionRoles")
    if cog is not None and panel["message_id"]:
        fresh = await _panel(ctx, panel["panel_id"])
        await cog._sync_panel_message(ctx.guild, fresh)


def _assignable(ctx: ActionContext, role: discord.Role) -> discord.Role:
    if role.managed:
        raise ValueError(f"{role.name} is managed by an integration and cannot be assigned.")
    if role >= ctx.guild.me.top_role:
        raise ValueError(f"{role.name} is at or above the bot's top role, so the bot cannot assign it.")
    return role


@section("reaction_roles")
async def panels_section(guild: discord.Guild) -> dict:
    from cogs.reaction_roles import get_bindings, list_panels

    rows = []
    for p in await list_panels(guild.id):
        channel = guild.get_channel(p["channel_id"]) if p["channel_id"] else None
        count = len(await get_bindings(p["panel_id"]))
        values = {
            "mode": p["mode"], "max_roles": p["max_roles"] or 0, "locked": bool(p["locked"]),
            "required_role": str(p["required_role_id"]) if p["required_role_id"] else "",
            "blacklist_role": str(p["blacklist_role_id"]) if p["blacklist_role_id"] else "",
            "title": p["fallback_title"] or "", "description": p["fallback_description"] or "",
        }
        rows.append(row(
            p["panel_id"],
            [p["panel_id"], p["panel_type"], p["fallback_title"] or "Reaction Roles", f"#{channel.name}" if channel else "Not posted", count, "Locked" if p["locked"] else "Active"],
            actions=[
                button("rr_panel_edit", "Settings", [
                    fld("title", "Title", "text", maxlen=100),
                    fld("description", "Description", "textarea", maxlen=500),
                    fld("mode", "Default mode", "select", options=[(m, m.replace("_", " ").title()) for m in RR_PANEL_MODES]),
                    fld("max_roles", "Max roles per member (0 for no limit)", "int", lo=0, hi=25),
                    fld("required_role", "Required role", "role"),
                    fld("blacklist_role", "Blocked role", "role"),
                    fld("locked", "Locked", "bool", help="Locked panels stop granting and removing roles."),
                ], title=f"Panel {p['panel_id']}", prefill=True, submit="Save"),
                button("rr_panel_post", "Post" if not channel else "Repost", [fld("channel", "Channel", "channel")], style="primary",
                       title=f"Post panel {p['panel_id']}", submit="Post panel"),
                button("rr_panel_delete", "Delete", style="danger", confirm=f"Delete panel {p['panel_id']} and its posted message?"),
            ],
            values=values,
        ))
    return table(
        "rr_panels", "Panels", ["ID", "Type", "Title", "Channel", "Roles", "State"], rows, "No panels yet.",
        description="Add roles to a panel, then post it in a channel.",
        buttons=[button("rr_panel_create", "Create panel", [
            fld("panel_type", "Type", "select", options=[("reaction", "Reactions"), ("select", "Select menu")]),
            fld("title", "Title", "text", value="Reaction Roles", maxlen=100),
            fld("description", "Description", "textarea", value="React below to receive a role.", maxlen=500),
        ], style="primary", title="Create panel", submit="Create")],
    )


@section("reaction_roles")
async def bindings_section(guild: discord.Guild) -> dict:
    from cogs.reaction_roles import get_bindings, list_panels

    panels = await list_panels(guild.id)
    rows = []
    for p in panels:
        for b in await get_bindings(p["panel_id"]):
            role = guild.get_role(b["role_id"])
            rid = f"{p['panel_id']}|{b['emoji']}"
            rows.append(row(
                rid,
                [p["panel_id"], b["emoji"], f"@{role.name}" if role else "deleted role", b["label"] or "", b["binding_mode"]],
                actions=[
                    button("rr_bind_mode", "Mode", [fld("mode", "Binding mode", "select", options=[(m, m.replace("_", " ").title()) for m in RR_BINDING_MODES])],
                           title=f"Mode for {b['emoji']}", prefill=True, submit="Save"),
                    button("rr_bind_remove", "Remove", style="danger", confirm=f"Remove {b['emoji']} from panel {p['panel_id']}?"),
                ],
                values={"mode": b["binding_mode"] if b["binding_mode"] in RR_BINDING_MODES else "normal"},
            ))
    add = []
    if panels:
        add = [button("rr_bind_add", "Add role", [
            fld("panel", "Panel", "select", options=[(p["panel_id"], f"{p['panel_id']} ({p['panel_type']})") for p in panels]),
            fld("emoji", "Emoji", "text", maxlen=80, help="An emoji for reaction panels, or any short label for select panels."),
            fld("role", "Role", "role"),
            fld("label", "Label", "text", maxlen=80, help="Shown in select menus."),
        ], style="primary", title="Add a role to a panel", submit="Add role")]
    return table("rr_bindings", "Roles on panels", ["Panel", "Emoji", "Role", "Label", "Mode"], rows,
                 "Create a panel first, then add roles to it." if not panels else "No roles added yet.", buttons=add)


@action("reaction_roles", "rr_panel_create")
async def rr_panel_create(ctx: ActionContext, payload: dict) -> list:
    from cogs.reaction_roles import new_panel_id

    values = payload.get("values") or {}
    panel_type = need_choice(values, "panel_type", "Type", list(RR_TYPES))
    title = need_text(values, "title", "Title", maxlen=100)
    description = need_text(values, "description", "Description", maxlen=500, required=False)
    count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM reaction_role_panels WHERE guild_id=?", (ctx.guild.id,))
    if count and count["n"] >= 25:
        raise ValueError("A server can have at most 25 reaction role panels.")
    panel_id = new_panel_id()
    await db.raw_execute(
        "INSERT INTO reaction_role_panels (panel_id, guild_id, embed_name, fallback_title, fallback_description, panel_type, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (panel_id, ctx.guild.id, None, title, description, panel_type, ctx.user_id, time.time()),
    )
    return [f"Created reaction role panel {panel_id}"]


@action("reaction_roles", "rr_panel_edit")
async def rr_panel_edit(ctx: ActionContext, payload: dict) -> list:
    panel = await _panel(ctx, payload.get("id"))
    values = payload.get("values") or {}
    title = need_text(values, "title", "Title", maxlen=100)
    description = need_text(values, "description", "Description", maxlen=500, required=False)
    mode = need_choice(values, "mode", "Default mode", list(RR_PANEL_MODES))
    max_roles = need_int(values, "max_roles", "Max roles", 0, 25)
    required = opt_role(ctx.guild, values, "required_role", "Required role")
    blocked = opt_role(ctx.guild, values, "blacklist_role", "Blocked role")
    await db.raw_execute(
        "UPDATE reaction_role_panels SET fallback_title=?, fallback_description=?, mode=?, max_roles=?, required_role_id=?,"
        " blacklist_role_id=?, locked=? WHERE panel_id=?",
        (title, description, mode, max_roles or None, required.id if required else None, blocked.id if blocked else None,
         int(need_bool(values, "locked")), panel["panel_id"]),
    )
    await _resync(ctx, panel)
    return [f"Updated reaction role panel {panel['panel_id']}"]


@action("reaction_roles", "rr_panel_post")
async def rr_panel_post(ctx: ActionContext, payload: dict) -> list:
    from cogs.reaction_roles import RoleSelectView, append_role_list, build_panel_embed, get_bindings

    panel = await _panel(ctx, payload.get("id"))
    channel = need_channel(ctx.guild, payload.get("values") or {}, "channel", "Channel")
    bindings = await get_bindings(panel["panel_id"])
    if not bindings:
        raise ValueError("Add at least one role to this panel before posting it.")
    embed = await build_panel_embed(ctx.guild, panel)
    await append_role_list(embed, panel["panel_id"])
    if panel["channel_id"] and panel["message_id"]:
        old_channel = ctx.guild.get_channel(panel["channel_id"])
        if old_channel is not None:
            try:
                old = await old_channel.fetch_message(panel["message_id"])
                await old.delete()
            except discord.HTTPException:
                pass
    try:
        if panel["panel_type"] == "select":
            message = await channel.send(embed=embed, view=RoleSelectView(ctx.guild, panel, bindings))
        else:
            message = await channel.send(embed=embed)
            for binding in bindings:
                await message.add_reaction(binding["emoji"])
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the message: {str(exc)[:150]}")
    await db.raw_execute("UPDATE reaction_role_panels SET channel_id=?, message_id=? WHERE panel_id=?", (channel.id, message.id, panel["panel_id"]))
    return [f"Posted panel {panel['panel_id']} in #{channel.name}"]


@action("reaction_roles", "rr_panel_delete")
async def rr_panel_delete(ctx: ActionContext, payload: dict) -> list:
    panel = await _panel(ctx, payload.get("id"))
    if panel["channel_id"] and panel["message_id"]:
        channel = ctx.guild.get_channel(panel["channel_id"])
        if channel is not None:
            try:
                message = await channel.fetch_message(panel["message_id"])
                await message.delete()
            except discord.HTTPException:
                pass
    await db.raw_execute("DELETE FROM reaction_role_bindings WHERE panel_id=?", (panel["panel_id"],))
    await db.raw_execute("DELETE FROM reaction_role_panels WHERE panel_id=?", (panel["panel_id"],))
    return [f"Deleted reaction role panel {panel['panel_id']}"]


@action("reaction_roles", "rr_bind_add")
async def rr_bind_add(ctx: ActionContext, payload: dict) -> list:
    from cogs.reaction_roles import get_bindings

    values = payload.get("values") or {}
    panel = await _panel(ctx, values.get("panel"))
    emoji = need_text(values, "emoji", "Emoji", maxlen=80)
    role = _assignable(ctx, need_role(ctx.guild, values, "role", "Role"))
    label = need_text(values, "label", "Label", maxlen=80, required=False) or None
    existing = await get_bindings(panel["panel_id"])
    if len(existing) >= 20 and not any(b["emoji"] == emoji for b in existing):
        raise ValueError("A panel can have at most 20 roles.")
    await db.raw_execute(
        "INSERT INTO reaction_role_bindings (panel_id, emoji, role_id, label) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(panel_id, emoji) DO UPDATE SET role_id=excluded.role_id, label=excluded.label",
        (panel["panel_id"], emoji, role.id, label),
    )
    await _resync(ctx, panel)
    return [f"Panel {panel['panel_id']}: {emoji} grants {role.name}"]


def _split_binding(raw) -> tuple[str, str]:
    panel_id, _, emoji = str(raw or "").partition("|")
    if not panel_id or not emoji:
        raise ValueError("That role binding no longer exists.")
    return panel_id, emoji


@action("reaction_roles", "rr_bind_mode")
async def rr_bind_mode(ctx: ActionContext, payload: dict) -> list:
    panel_id, emoji = _split_binding(payload.get("id"))
    panel = await _panel(ctx, panel_id)
    mode = need_choice(payload.get("values") or {}, "mode", "Binding mode", list(RR_BINDING_MODES))
    cur = await db.raw_execute("UPDATE reaction_role_bindings SET binding_mode=? WHERE panel_id=? AND emoji=?", (mode, panel["panel_id"], emoji))
    if not cur.rowcount:
        raise ValueError("That role binding no longer exists.")
    return [f"Panel {panel['panel_id']}: {emoji} mode {mode}"]


@action("reaction_roles", "rr_bind_remove")
async def rr_bind_remove(ctx: ActionContext, payload: dict) -> list:
    panel_id, emoji = _split_binding(payload.get("id"))
    panel = await _panel(ctx, panel_id)
    cur = await db.raw_execute("DELETE FROM reaction_role_bindings WHERE panel_id=? AND emoji=?", (panel["panel_id"], emoji))
    if not cur.rowcount:
        raise ValueError("That role binding no longer exists.")
    await _resync(ctx, panel)
    if panel["message_id"] and panel["panel_type"] == "reaction":
        channel = ctx.guild.get_channel(panel["channel_id"])
        if channel is not None:
            try:
                message = await channel.fetch_message(panel["message_id"])
                await message.clear_reaction(emoji)
            except discord.HTTPException:
                pass
    return [f"Panel {panel['panel_id']}: removed {emoji}"]


CC_TYPES = ("command", "starts_with", "contains", "regex", "exact_match")
CC_MAX = 100


def _cc_cog(ctx: ActionContext):
    cog = ctx.bot.get_cog("CustomCommands")
    if cog is None:
        raise ValueError("Custom commands are not loaded.")
    return cog


async def _cc_form_fields() -> list:
    return [
        fld("response", "Response", "textarea", maxlen=4000, help="Supports the same variables as the custom command commands."),
        fld("trigger_type", "Trigger type", "select", options=[(t, t.replace("_", " ").title()) for t in CC_TYPES]),
        fld("cooldown", "Cooldown (seconds)", "int", lo=0, hi=86400),
        fld("cooldown_type", "Cooldown applies to", "select", options=[("user", "Each member"), ("global", "Everyone")]),
        fld("case_sensitive", "Case sensitive", "bool"),
        fld("embed", "Send as embed", "bool"),
        fld("delete_trigger_after", "Delete the trigger message after (seconds, 0 is off)", "int", lo=0, hi=3600),
        fld("delete_response_after", "Delete the response after (seconds, 0 is off)", "int", lo=0, hi=3600),
        fld("enabled", "Enabled", "bool"),
    ]


@section("custom_commands")
async def cc_section(guild: discord.Guild) -> dict:
    from cogs.custom_commands import MAX_COMMANDS_PER_GUILD

    found = await db.raw_fetch("SELECT trigger, data FROM custom_commands WHERE guild_id=? ORDER BY trigger", (guild.id,))
    fields = await _cc_form_fields()
    rows = []
    for r in found:
        data = json.loads(r["data"])
        responses = data.get("responses") or [""]
        kind = data.get("trigger_type", "command")
        editable = kind in CC_TYPES
        values = {
            "response": responses[0], "trigger_type": kind if editable else "command",
            "cooldown": data.get("cooldown", 0), "cooldown_type": data.get("cooldown_type", "user"),
            "case_sensitive": bool(data.get("case_sensitive", False)), "embed": bool(data.get("embed", False)),
            "delete_trigger_after": data.get("delete_trigger_after", 0), "delete_response_after": data.get("delete_response_after", 0),
            "enabled": bool(data.get("enabled", True)),
        }
        acts = [button("cc_save", "Edit", fields, title=f"Edit {r['trigger']}", prefill=True, submit="Save command")] if editable else []
        acts.append(button("cc_toggle", "Disable" if values["enabled"] else "Enable"))
        acts.append(button("cc_delete", "Delete", style="danger", confirm=f"Delete the command {r['trigger']}?"))
        rows.append(row(r["trigger"], [r["trigger"], kind, len(responses), "On" if values["enabled"] else "Off", values["cooldown"] or "None"],
                        actions=acts, values=values))
    create = [fld("trigger", "Trigger", "text", maxlen=50, help="The command name or the text that triggers it.")] + fields
    return table(
        "commands", f"Commands ({len(rows)}/{MAX_COMMANDS_PER_GUILD})", ["Trigger", "Type", "Responses", "State", "Cooldown"], rows,
        "No custom commands yet.",
        description="Extra responses, restrictions, intervals and reactions are still set with the cc commands in Discord.",
        buttons=[button("cc_save", "Create command", create, style="primary", title="Create command", submit="Create command")],
    )


@action("custom_commands", "cc_save")
async def cc_save(ctx: ActionContext, payload: dict) -> list:
    from utils.cc_engine import CustomCommand

    cog = _cc_cog(ctx)
    await cog._ensure_loaded(ctx.guild.id)
    cmds = cog._get_commands(ctx.guild.id)
    values = payload.get("values") or {}
    existing_key = payload.get("id")
    if existing_key:
        cmd = cmds.get(existing_key)
        if cmd is None:
            raise ValueError("That command no longer exists.")
    else:
        trigger = need_text(values, "trigger", "Trigger", maxlen=50).lower()
        if ctx.bot.get_command(trigger):
            raise ValueError(f"{trigger} conflicts with an existing bot command.")
        if trigger in cmds:
            raise ValueError("A custom command with that trigger already exists.")
        if len(cmds) >= CC_MAX:
            raise ValueError(f"A server can have at most {CC_MAX} custom commands.")
        cmd = None

    response = need_text(values, "response", "Response", maxlen=4000)
    kind = need_choice(values, "trigger_type", "Trigger type", list(CC_TYPES))
    if kind == "regex":
        try:
            re.compile(existing_key or trigger)
        except re.error as exc:
            raise ValueError(f"The trigger is not a valid regex: {exc}")
    if cmd is None:
        cmd = CustomCommand(trigger, {"responses": [response], "numeric_id": cog._alloc_id()})
        cmds[trigger] = cmd
        creator = ctx.user_id
    else:
        cmd.responses[0] = response
        creator = None
    cmd.trigger_type = kind
    cmd.cooldown = need_int(values, "cooldown", "Cooldown", 0, 86400)
    cmd.cooldown_type = need_choice(values, "cooldown_type", "Cooldown type", ["user", "global"])
    cmd.case_sensitive = need_bool(values, "case_sensitive")
    cmd.embed = need_bool(values, "embed")
    trigger_secs = need_int(values, "delete_trigger_after", "Trigger delete delay", 0, 3600)
    cmd.delete_trigger = trigger_secs > 0
    cmd.delete_trigger_after = trigger_secs
    cmd.delete_response_after = need_int(values, "delete_response_after", "Response delete delay", 0, 3600)
    cmd.enabled = need_bool(values, "enabled")
    await cog._save_command(ctx.guild.id, cmd, created_by=creator)
    return [f"{'Updated' if existing_key else 'Created'} custom command {cmd.trigger}"]


@action("custom_commands", "cc_toggle")
async def cc_toggle(ctx: ActionContext, payload: dict) -> list:
    cog = _cc_cog(ctx)
    await cog._ensure_loaded(ctx.guild.id)
    cmd = cog._get_commands(ctx.guild.id).get(payload.get("id"))
    if cmd is None:
        raise ValueError("That command no longer exists.")
    cmd.enabled = not cmd.enabled
    await cog._save_command(ctx.guild.id, cmd)
    return [f"Custom command {cmd.trigger}: {'enabled' if cmd.enabled else 'disabled'}"]


@action("custom_commands", "cc_delete")
async def cc_delete(ctx: ActionContext, payload: dict) -> list:
    cog = _cc_cog(ctx)
    await cog._ensure_loaded(ctx.guild.id)
    trigger = payload.get("id")
    if trigger not in cog._get_commands(ctx.guild.id):
        raise ValueError("That command no longer exists.")
    del cog._cache[ctx.guild.id][trigger]
    await cog._delete_command(ctx.guild.id, trigger)
    return [f"Deleted custom command {trigger}"]


@section("alerts")
async def alerts_section(guild: discord.Guild) -> dict:
    found = await db.raw_fetch("SELECT * FROM alert_subscriptions WHERE guild_id=? ORDER BY platform, target_name", (guild.id,))
    rows = []
    for s in map(dict, found):
        channel = guild.get_channel(s["announce_channel_id"])
        role = guild.get_role(s["ping_role_id"]) if s["ping_role_id"] else None
        values = {
            "channel": str(s["announce_channel_id"]), "role": str(s["ping_role_id"]) if s["ping_role_id"] else "",
            "message": s["custom_message"] or "", "live": bool(s["live_enabled"]), "upload": bool(s["upload_enabled"]),
        }
        fields = [
            fld("channel", "Announcement channel", "channel"),
            fld("role", "Role to ping", "role"),
            fld("message", "Custom message", "textarea", maxlen=1000, help="Leave empty for the default message."),
            fld("live", "Live notifications", "bool"),
        ]
        if s["platform"] == "youtube":
            fields.append(fld("upload", "Upload notifications", "bool"))
        rows.append(row(
            s["subscription_id"],
            [s["platform"].title(), s["target_name"] or s["target_id"], f"#{channel.name}" if channel else "deleted channel",
             f"@{role.name}" if role else "None"],
            actions=[
                button("alert_edit", "Edit", fields, title=f"Edit {s['target_name'] or s['target_id']}", prefill=True, submit="Save"),
                button("alert_remove", "Remove", style="danger", confirm=f"Stop alerts for {s['target_name'] or s['target_id']}?"),
            ],
            values=values,
        ))
    return table(
        "alerts", "Subscriptions", ["Platform", "Channel", "Posts in", "Pings"], rows, "No alert subscriptions yet.",
        buttons=[button("alert_add", "Add subscription", [
            fld("platform", "Platform", "select", options=[("youtube", "YouTube"), ("twitch", "Twitch")]),
            fld("target", "Channel handle or ID / username", "text", maxlen=100),
            fld("channel", "Announcement channel", "channel"),
        ], style="primary", title="Add subscription", submit="Subscribe")],
    )


async def _subscription(ctx: ActionContext, payload: dict) -> dict:
    found = await db.raw_fetchone("SELECT * FROM alert_subscriptions WHERE subscription_id=? AND guild_id=?", (str(payload.get("id") or "").upper(), ctx.guild.id))
    if found is None:
        raise ValueError("That subscription no longer exists.")
    return dict(found)


@action("alerts", "alert_add")
async def alert_add(ctx: ActionContext, payload: dict) -> list:
    cog = ctx.bot.get_cog("Alerts")
    if cog is None:
        raise ValueError("Alerts are not loaded.")
    values = payload.get("values") or {}
    platform = need_choice(values, "platform", "Platform", ["youtube", "twitch"])
    target = need_text(values, "target", "Channel or username", maxlen=100)
    channel = need_channel(ctx.guild, values, "channel", "Announcement channel")
    count = await db.raw_fetchone("SELECT COUNT(*) AS c FROM alert_subscriptions WHERE guild_id=? AND platform=?", (ctx.guild.id, platform))
    if count and count["c"] >= config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM:
        raise ValueError(f"A server can have at most {config.ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM} {platform.title()} subscriptions.")
    if platform == "youtube":
        if not config.YOUTUBE_API_KEY:
            raise ValueError("The bot owner has not set up a YouTube API key.")
        resolved = await cog._youtube.resolve_channel_id(target)
        if not resolved:
            raise ValueError(f"Could not find a YouTube channel matching {target}.")
        target_id, name = resolved["channel_id"], resolved["title"]
    else:
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            raise ValueError("The bot owner has not set up Twitch API credentials.")
        resolved = await cog._twitch.resolve_user(target)
        if not resolved:
            raise ValueError(f"Could not find a Twitch user named {target}.")
        target_id, name = resolved["login"], resolved["display_name"]
    clash = await db.raw_fetchone("SELECT 1 FROM alert_subscriptions WHERE guild_id=? AND platform=? AND target_id=?", (ctx.guild.id, platform, target_id))
    if clash:
        raise ValueError(f"Already subscribed to {name}.")
    subscription_id = str(uuid.uuid4())[:8].upper()
    await db.raw_execute(
        "INSERT INTO alert_subscriptions (subscription_id, guild_id, platform, target_id, target_name, announce_channel_id, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (subscription_id, ctx.guild.id, platform, target_id, name, channel.id, ctx.user_id, time.time()),
    )
    if platform == "youtube":
        latest = await cog._youtube.get_latest_upload(resolved["uploads_playlist_id"])
        if latest:
            await db.raw_execute(
                "INSERT INTO alert_state (platform, target_id, last_video_id, updated_at) VALUES ('youtube', ?, ?, ?)"
                " ON CONFLICT(platform, target_id) DO UPDATE SET last_video_id=excluded.last_video_id, updated_at=excluded.updated_at",
                (target_id, latest["video_id"], time.time()),
            )
    return [f"Subscribed to {platform.title()} {name}"]


@action("alerts", "alert_edit")
async def alert_edit(ctx: ActionContext, payload: dict) -> list:
    sub = await _subscription(ctx, payload)
    values = payload.get("values") or {}
    channel = need_channel(ctx.guild, values, "channel", "Announcement channel")
    role = opt_role(ctx.guild, values, "role", "Role to ping")
    message = need_text(values, "message", "Custom message", maxlen=1000, required=False) or None
    upload = need_bool(values, "upload") if sub["platform"] == "youtube" else bool(sub["upload_enabled"])
    await db.raw_execute(
        "UPDATE alert_subscriptions SET announce_channel_id=?, ping_role_id=?, custom_message=?, live_enabled=?, upload_enabled=? WHERE subscription_id=?",
        (channel.id, role.id if role else None, message, int(need_bool(values, "live")), int(upload), sub["subscription_id"]),
    )
    return [f"Updated alerts for {sub['target_name'] or sub['target_id']}"]


@action("alerts", "alert_remove")
async def alert_remove(ctx: ActionContext, payload: dict) -> list:
    sub = await _subscription(ctx, payload)
    await db.raw_execute("DELETE FROM alert_subscriptions WHERE subscription_id=?", (sub["subscription_id"],))
    return [f"Removed alerts for {sub['target_name'] or sub['target_id']}"]
