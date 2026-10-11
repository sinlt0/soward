from __future__ import annotations

import asyncio
import datetime
from typing import Optional

import discord

import config
from utils import cases, db, guild_settings, nsfw, security
from utils.dash.base import (
    ActionContext, action, button, fld, need_channel, need_choice, need_int, need_role, need_text, row, section, table,
)
from utils.events_bus import LOG_EVENT, bus

PUNISHMENT_OPTIONS = [
    ("ban", "Ban"), ("kick", "Kick"), ("kick_bot", "Kick bot"), ("strip_roles", "Strip roles"), ("quarantine", "Quarantine"),
]
TIER_OPTIONS = [(config.SECURITY_TIER_EXTRA_OWNER, "Extra Owner"), (config.SECURITY_TIER_TRUSTED_ADMIN, "Trusted Admin")]
TIER_LABELS = dict(TIER_OPTIONS)
ID_FIELD_HELP = "Right-click the member and copy their ID."


def _when(stamp: Optional[float]) -> str:
    if not stamp:
        return "Never"
    return datetime.datetime.fromtimestamp(float(stamp), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _role_name(guild: discord.Guild, role_id: Optional[int]) -> str:
    if not role_id:
        return "Not set"
    role = guild.get_role(int(role_id))
    return role.name if role else "Deleted role"


def _channel_name(guild: discord.Guild, channel_id: Optional[int]) -> str:
    if not channel_id:
        return "Not set"
    channel = guild.get_channel(int(channel_id))
    return f"#{channel.name}" if channel else "Deleted channel"


def _member_label(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(int(user_id))
    return f"{member.display_name} ({user_id})" if member else f"Left server ({user_id})"


def _id_field(label: str = "Member ID") -> dict:
    return fld("user_id", label, "text", maxlen=20, help=ID_FIELD_HELP, placeholder="123456789012345678")


def _need_member(guild: discord.Guild, values: dict) -> discord.Member:
    raw = str(values.get("user_id", "")).strip()
    member = guild.get_member(int(raw)) if raw.isdigit() else None
    if member is None:
        raise ValueError("That user ID is not a member of this server.")
    return member


def _target_values(payload: dict) -> dict:
    values = dict(payload.get("values") or {})
    if payload.get("id"):
        values["user_id"] = payload["id"]
    return values


def _assignable_role(guild: discord.Guild, role: discord.Role) -> discord.Role:
    me = guild.me
    if role.managed:
        raise ValueError("Pick a normal role. Bot and integration roles cannot be used here.")
    if not me.guild_permissions.administrator and role.position >= me.top_role.position:
        raise ValueError(f"{role.name} is above my highest role. Move my role higher first.")
    return role


def _need_bot_perms(guild: discord.Guild, **perms: bool) -> None:
    held = guild.me.guild_permissions
    missing = [name.replace("_", " ") for name in perms if not getattr(held, name)]
    if missing:
        raise ValueError("I am missing these permissions: " + ", ".join(missing) + ".")


def _http_error(exc: Exception) -> ValueError:
    if isinstance(exc, discord.Forbidden):
        return ValueError("Discord refused: I need Manage Channels and Manage Roles, and my role must be above the role involved.")
    return ValueError(f"Discord refused the request: {str(exc)[:150]}")


@section("nsfw")
async def nsfw_role_section(guild: discord.Guild) -> dict:
    role_id = await nsfw.get_role_id(guild.id)
    actions = [button("nsfw_role_set", "Set role", [fld("role", "NSFW role", "role", value=str(role_id) if role_id else "")],
                      style="primary", title="Set NSFW role", submit="Set role")]
    if role_id:
        actions.append(button("nsfw_role_clear", "Clear", style="danger",
                              confirm="Clear the NSFW role? Every registered channel is restored to the permissions it had before it was locked."))
    return table(
        "nsfw_role", "NSFW role", ["Setting", "Value"],
        [row("role", ["NSFW role", _role_name(guild, role_id)], actions=actions)],
        "",
        description="Registered channels are hidden from everyone except this role.",
    )


@section("nsfw")
async def nsfw_channels_section(guild: discord.Guild) -> dict:
    role_id = await nsfw.get_role_id(guild.id)
    ids = await nsfw.get_channel_ids(guild.id)
    rows = []
    for cid in ids:
        channel = guild.get_channel(cid)
        if channel is None:
            state = "Channel no longer exists"
        elif role_id and nsfw.is_locked(channel):
            state = "Locked to the NSFW role"
        else:
            state = "Not locked"
        rows.append(row(cid, [_channel_name(guild, cid), state],
                        actions=[button("nsfw_channel_remove", "Remove", style="danger",
                                        confirm="Unregister this channel and restore its original permissions?")]))
    return table(
        "nsfw_channels", f"NSFW channels ({len(ids)}/{config.NSFW_MAX_CHANNELS})", ["Channel", "State"], rows,
        "No channels registered.",
        buttons=[
            button("nsfw_channel_add", "Add channel", [fld("channel", "Channel", "channel")], style="primary",
                   title="Add NSFW channel", submit="Add channel"),
            button("nsfw_sync", "Sync", confirm="Re-apply the NSFW lock to every registered channel?"),
        ],
    )


def _nsfw_reason(ctx: ActionContext, what: str) -> str:
    return f"[Soward NSFW] {what} - requested by {ctx.user_name} ({ctx.user_id}) from the dashboard"


async def _nsfw_log(ctx: ActionContext, detail: str) -> None:
    await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="nsfw_action", user_id=ctx.user_id, detail=detail)


async def _nsfw_apply_all(guild: discord.Guild, role: discord.Role, snapshots: dict, ids: list, reason: str) -> tuple[list, list]:
    from cogs.nsfw import _API_DELAY, _fmt_error

    done, failed = [], []
    for cid in ids:
        channel = guild.get_channel(cid)
        if channel is None:
            continue
        try:
            await nsfw.lock_channel(channel, role, snapshots, reason)
            done.append(channel)
        except Exception as exc:
            failed.append(f"Could not lock #{channel.name}: {_fmt_error(exc)}")
        await asyncio.sleep(_API_DELAY)
    return done, failed


@action("nsfw", "nsfw_role_set")
async def nsfw_role_set(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    role = _assignable_role(guild, need_role(guild, payload.get("values") or {}, "role", "NSFW role"))
    _need_bot_perms(guild, manage_channels=True, manage_roles=True)
    async with nsfw.guild_lock(guild.id):
        if await nsfw.get_role_id(guild.id) == role.id:
            raise ValueError("That role is already the NSFW role. Use Sync to re-apply permissions.")
        ids = await nsfw.get_channel_ids(guild.id)
        snapshots = await nsfw.get_snapshots(guild.id)
        done, failed = await _nsfw_apply_all(guild, role, snapshots, ids, _nsfw_reason(ctx, "NSFW role set"))
        await nsfw.set_role_id(guild.id, role.id)
        await nsfw.save_channels(guild.id, ids, snapshots)
    await _nsfw_log(ctx, f"NSFW role set to **{role.name}** ({len(done)} channel(s) updated)")
    return [f"NSFW role set to {role.name} ({len(done)} channel(s) updated)", *failed]


@action("nsfw", "nsfw_role_clear")
async def nsfw_role_clear(ctx: ActionContext, payload: dict) -> list:
    from cogs.nsfw import _API_DELAY, _fmt_error

    guild = ctx.guild
    if await nsfw.get_role_id(guild.id) is None:
        raise ValueError("No NSFW role is set.")
    _need_bot_perms(guild, manage_channels=True, manage_roles=True)
    failed = []
    async with nsfw.guild_lock(guild.id):
        ids = await nsfw.get_channel_ids(guild.id)
        snapshots = await nsfw.get_snapshots(guild.id)
        for cid in ids:
            try:
                await nsfw.unlock_channel(guild, guild.get_channel(cid), snapshots, _nsfw_reason(ctx, "NSFW role reset"))
            except Exception as exc:
                failed.append(f"Could not restore {_channel_name(guild, cid)}: {_fmt_error(exc)}")
            await asyncio.sleep(_API_DELAY)
        await nsfw.set_role_id(guild.id, None)
        await nsfw.save_channels(guild.id, ids, snapshots)
    await _nsfw_log(ctx, "NSFW role reset - channel permissions restored")
    return ["NSFW role cleared and channel permissions restored", *failed]


@action("nsfw", "nsfw_channel_add")
async def nsfw_channel_add(ctx: ActionContext, payload: dict) -> list:
    from cogs.nsfw import _API_DELAY, _fmt_error

    guild = ctx.guild
    channel = need_channel(guild, payload.get("values") or {}, "channel", "Channel", nsfw.SUPPORTED_CHANNEL_TYPES)
    _need_bot_perms(guild, manage_channels=True, manage_roles=True)
    async with nsfw.guild_lock(guild.id):
        ids = await nsfw.get_channel_ids(guild.id)
        if channel.id in ids:
            raise ValueError("That channel is already registered.")
        if len(ids) >= config.NSFW_MAX_CHANNELS:
            raise ValueError(f"Limit of {config.NSFW_MAX_CHANNELS} NSFW channels reached.")
        role_id = await nsfw.get_role_id(guild.id)
        role = guild.get_role(role_id) if role_id else None
        snapshots = await nsfw.get_snapshots(guild.id)
        if role is not None:
            try:
                await nsfw.lock_channel(channel, role, snapshots, _nsfw_reason(ctx, "NSFW channel added"))
            except Exception as exc:
                raise ValueError(f"Could not lock #{channel.name}: {_fmt_error(exc)}")
            await asyncio.sleep(_API_DELAY)
        ids.append(channel.id)
        await nsfw.save_channels(guild.id, ids, snapshots, ctx.user_id)
    await _nsfw_log(ctx, f"NSFW channel(s) added: {channel.mention}")
    note = "" if role is not None else " (no NSFW role is set, so it is not locked yet)"
    return [f"NSFW channel added: #{channel.name}{note}"]


@action("nsfw", "nsfw_channel_remove")
async def nsfw_channel_remove(ctx: ActionContext, payload: dict) -> list:
    from cogs.nsfw import _API_DELAY, _fmt_error

    guild = ctx.guild
    raw = str(payload.get("id") or "")
    _need_bot_perms(guild, manage_channels=True, manage_roles=True)
    notes = []
    async with nsfw.guild_lock(guild.id):
        ids = await nsfw.get_channel_ids(guild.id)
        if not raw.isdigit() or int(raw) not in ids:
            raise ValueError("That channel is not registered.")
        channel_id = int(raw)
        snapshots = await nsfw.get_snapshots(guild.id)
        channel = guild.get_channel(channel_id)
        try:
            await nsfw.unlock_channel(guild, channel, snapshots, _nsfw_reason(ctx, "NSFW channel removed"))
        except Exception as exc:
            notes.append(f"Could not fully restore permissions: {_fmt_error(exc)}. Check them manually.")
        ids.remove(channel_id)
        await nsfw.save_channels(guild.id, ids, snapshots, ctx.user_id)
        await asyncio.sleep(_API_DELAY)
    label = _channel_name(guild, channel_id)
    await _nsfw_log(ctx, f"NSFW channel(s) removed: {channel.mention if channel else label}")
    return [f"NSFW channel removed: {label}", *notes]


@action("nsfw", "nsfw_sync")
async def nsfw_sync(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    _need_bot_perms(guild, manage_channels=True, manage_roles=True)
    async with nsfw.guild_lock(guild.id):
        role_id = await nsfw.get_role_id(guild.id)
        role = guild.get_role(role_id) if role_id else None
        if role is None:
            raise ValueError("Set an NSFW role first.")
        ids = await nsfw.get_channel_ids(guild.id)
        snapshots = await nsfw.get_snapshots(guild.id)
        done, failed = await _nsfw_apply_all(guild, role, snapshots, ids, _nsfw_reason(ctx, "NSFW sync"))
        await nsfw.save_channels(guild.id, ids, snapshots)
    return [f"Re-applied the NSFW lock to {len(done)} channel(s)", *failed]


async def _log_rows() -> dict:
    return {}


@section("logging")
async def log_channels_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT category, channel_id FROM log_channels WHERE guild_id=?", (guild.id,))
    configured = {r["category"]: r["channel_id"] for r in rows_db}
    rows = []
    for key, meta in config.LOG_CATEGORIES.items():
        channel_id = configured.get(key)
        actions = [button("log_channel_set", "Set channel", [fld("channel", "Channel", "channel", value=str(channel_id) if channel_id else "")],
                          title=f"Log channel for {meta['label']}", submit="Set channel")]
        if channel_id:
            actions.append(button("log_channel_remove", "Remove", style="danger",
                                  confirm=f"Stop logging {meta['label']} and delete its webhook?"))
        rows.append(row(key, [meta["label"], _channel_name(guild, channel_id) if channel_id else "Not set", len(meta["events"])], actions=actions))
    return table(
        "log_channels", "Log channels", ["Category", "Channel", "Events"], rows, "",
        description="Each category posts through its own webhook in the channel you choose.",
        buttons=[button("log_setup", "Run setup", style="primary",
                        confirm=f"Create the {config.LOG_CATEGORY_NAME} category with a channel and webhook for every log category that is not set up yet?")],
    )


@section("logging")
async def log_events_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT event FROM log_disabled_events WHERE guild_id=?", (guild.id,))
    disabled = {r["event"] for r in rows_db}
    owner = {event: meta["label"] for meta in config.LOG_CATEGORIES.values() for event in meta["events"] for _ in [0]}
    rows = []
    for event in config.LOG_EVENTS:
        off = event in disabled
        rows.append(row(
            event, [event, owner.get(event, "No category"), "Disabled" if off else "Enabled"],
            actions=[button("log_event_toggle", "Enable" if off else "Disable", style="ghost" if off else "danger",
                            confirm=f"{'Enable' if off else 'Disable'} logging for {event}?")],
        ))
    return table("log_events", "Event types", ["Event", "Category", "State"], rows, "No events.",
                 description="Disabled events are skipped even when their category has a channel.")


def _log_category(key: str) -> str:
    if key not in config.LOG_CATEGORIES:
        raise ValueError("That log category does not exist.")
    return key


def _log_cog(ctx: ActionContext):
    return ctx.bot.get_cog("Logging")


def _forget_webhook(ctx: ActionContext, category: str) -> None:
    cog = _log_cog(ctx)
    if cog is not None:
        cog._webhook_cache.pop((ctx.guild.id, category), None)


async def _store_log_channel(ctx: ActionContext, category: str, channel: discord.TextChannel) -> None:
    webhook = await channel.create_webhook(name=f"{config.BOT_NAME} Logs")
    await db.raw_execute(
        "INSERT INTO log_channels (guild_id, category, channel_id, webhook_url) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id, category) DO UPDATE SET channel_id=excluded.channel_id, webhook_url=excluded.webhook_url",
        (ctx.guild.id, category, channel.id, webhook.url),
    )
    _forget_webhook(ctx, category)


@action("logging", "log_channel_set")
async def log_channel_set(ctx: ActionContext, payload: dict) -> list:
    category = _log_category(str(payload.get("id") or ""))
    channel = need_channel(ctx.guild, payload.get("values") or {}, "channel", "Channel")
    if not channel.permissions_for(ctx.guild.me).manage_webhooks:
        raise ValueError(f"I need Manage Webhooks in #{channel.name}.")
    try:
        await _store_log_channel(ctx, category, channel)
    except discord.HTTPException as exc:
        raise ValueError(f"Could not create the webhook: {str(exc)[:150]}")
    return [f"{config.LOG_CATEGORIES[category]['label']} logs now go to #{channel.name}"]


@action("logging", "log_channel_remove")
async def log_channel_remove(ctx: ActionContext, payload: dict) -> list:
    category = _log_category(str(payload.get("id") or ""))
    found = await db.raw_fetchone("SELECT * FROM log_channels WHERE guild_id=? AND category=?", (ctx.guild.id, category))
    if not found:
        raise ValueError("Logging is not set up for that category.")
    if found["webhook_url"]:
        try:
            await discord.Webhook.from_url(found["webhook_url"], client=ctx.bot).delete()
        except discord.HTTPException:
            pass
    await db.raw_execute("DELETE FROM log_channels WHERE guild_id=? AND category=?", (ctx.guild.id, category))
    _forget_webhook(ctx, category)
    return [f"Logging removed for {config.LOG_CATEGORIES[category]['label']}"]


@action("logging", "log_event_toggle")
async def log_event_toggle(ctx: ActionContext, payload: dict) -> list:
    event = str(payload.get("id") or "")
    if event not in config.LOG_EVENTS:
        raise ValueError("That event type does not exist.")
    found = await db.raw_fetchone("SELECT 1 FROM log_disabled_events WHERE guild_id=? AND event=?", (ctx.guild.id, event))
    if found:
        await db.raw_execute("DELETE FROM log_disabled_events WHERE guild_id=? AND event=?", (ctx.guild.id, event))
        return [f"Logging enabled for {event}"]
    await db.raw_execute("INSERT INTO log_disabled_events (guild_id, event) VALUES (?, ?)", (ctx.guild.id, event))
    return [f"Logging disabled for {event}"]


@action("logging", "log_setup")
async def log_setup(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    _need_bot_perms(guild, manage_channels=True, manage_webhooks=True)
    changes = []
    try:
        folder = discord.utils.get(guild.categories, name=config.LOG_CATEGORY_NAME) or await guild.create_category(
            config.LOG_CATEGORY_NAME,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_webhooks=True),
            },
        )
        for key, meta in config.LOG_CATEGORIES.items():
            found = await db.raw_fetchone("SELECT channel_id FROM log_channels WHERE guild_id=? AND category=?", (guild.id, key))
            if found and guild.get_channel(int(found["channel_id"])):
                continue
            channel = discord.utils.get(folder.channels, name=meta["channel_name"]) or await guild.create_text_channel(
                meta["channel_name"], category=folder
            )
            await _store_log_channel(ctx, key, channel)
            changes.append(f"Log channel ready: #{channel.name} for {meta['label']}")
    except discord.HTTPException as exc:
        raise ValueError(f"Setup stopped early: {str(exc)[:150]}. {len(changes)} categor(ies) were created first.")
    return changes or ["Every log category was already set up"]


@section("antinuke")
async def trusted_section(guild: discord.Guild) -> dict:
    rows = [
        row(r["target_id"], [_member_label(guild, r["target_id"]), _member_label(guild, r["added_by"]) if r["added_by"] else "Unknown"],
            actions=[button("trust_remove", "Remove", style="danger", confirm="Remove this member from the trusted list?")])
        for r in await security.list_trusted(guild.id)
    ]
    return table(
        "trusted", "Trusted members", ["Member", "Added by"], rows, "No trusted members.",
        description="Trusted members bypass AntiNuke entirely.",
        buttons=[button("trust_add", "Add trusted member", [_id_field()], style="primary", title="Trust a member", submit="Trust member")],
    )


@section("antinuke")
async def permits_section(guild: discord.Guild) -> dict:
    rows = [
        row(r["user_id"], [_member_label(guild, r["user_id"]), TIER_LABELS.get(r["tier"], r["tier"])],
            actions=[button("permit_revoke", "Revoke", style="danger", confirm="Revoke this permit tier?")])
        for r in await security.list_permit_tiers(guild.id)
    ]
    return table(
        "permits", "Permit tiers", ["Member", "Tier"], rows, "No Extra Owners or Trusted Admins.",
        description="Only the server owner can grant Extra Owner. The owner or an Extra Owner can grant Trusted Admin.",
        buttons=[button("permit_grant", "Grant tier", [_id_field(), fld("tier", "Tier", "select", value=config.SECURITY_TIER_TRUSTED_ADMIN, options=TIER_OPTIONS)],
                        style="primary", title="Grant a permit tier", submit="Grant tier")],
    )


def _antinuke_actions() -> dict:
    from cogs.antinuke import ACTION_LABELS

    merged = dict(ACTION_LABELS)
    for key in config.ANTINUKE_PER_ACTION_PUNISHMENT_DEFAULT:
        merged.setdefault(key, key.replace("_", " ").capitalize())
    return merged


@section("antinuke")
async def overrides_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch("SELECT action_type, punishment FROM antinuke_action_punishments WHERE guild_id=?", (guild.id,))
    overrides = {r["action_type"]: r["punishment"] for r in rows_db}
    rows = []
    for key, label in _antinuke_actions().items():
        override = overrides.get(key)
        effective = await security.get_action_punishment(guild.id, key)
        actions = [button("override_set", "Set", [fld("punishment", "Punishment", "select", value=override or effective, options=PUNISHMENT_OPTIONS)],
                          title=f"Punishment for {label}", submit="Save override")]
        if override:
            actions.append(button("override_clear", "Remove", style="danger", confirm=f"Remove the override for {label}?"))
        rows.append(row(key, [label, override or "None", effective], actions=actions))
    return table(
        "overrides", "Punishment per action", ["Action", "Override", "Applies"], rows, "",
        description="An override beats the default punishment on the module settings.",
    )


@section("antinuke")
async def thresholds_section(guild: discord.Guild) -> dict:
    rows = []
    for key, default in config.ANTINUKE_DEFAULT_THRESHOLDS.items():
        value = await guild_settings.get(guild.id, f"antinuke_threshold_{key}", default)
        rows.append(row(
            key, [key.replace("_", " ").capitalize(), value, default],
            actions=[button("threshold_set", "Edit", [fld("value", "Threshold", "int", value=value, lo=1, hi=1000)],
                            title=f"Threshold for {key.replace('_', ' ')}", submit="Save threshold")],
        ))
    return table(
        "thresholds", "Action thresholds", ["Action", "Threshold", "Default"], rows, "",
        description=f"How many times a member may do this within {config.ANTINUKE_THRESHOLD_WINDOW_SECONDS} seconds before AntiNuke reacts.",
    )


@section("antinuke")
async def quarantine_role_section(guild: discord.Guild) -> dict:
    role_id = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    return table(
        "quarantine_role", "Quarantine role", ["Setting", "Value"],
        [row("role", ["Quarantine role", _role_name(guild, role_id)], actions=[
            button("quarantine_role_set", "Set role", [fld("role", "Role", "role", value=str(role_id) if role_id else "")],
                   title="Set quarantine role", submit="Set role"),
        ])],
        "",
        description="Give this role no permissions and deny it access everywhere.",
    )


@section("antinuke")
async def quarantined_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch(
        "SELECT user_id, reason, quarantined_at FROM quarantine WHERE guild_id=? AND released_at IS NULL ORDER BY quarantined_at DESC",
        (guild.id,),
    )
    rows = [
        row(r["user_id"], [_member_label(guild, r["user_id"]), r["reason"] or "No reason", _when(r["quarantined_at"])],
            actions=[button("quarantine_release", "Release", style="primary",
                            confirm="Release this member and restore their roles? Only the server owner can do this.")])
        for r in rows_db
    ]
    return table(
        "quarantined", "Quarantined members", ["Member", "Reason", "Since"], rows, "No members are quarantined.",
        description="Only the real server owner can release a member.",
        buttons=[button("quarantine_add", "Quarantine member", [_id_field(), fld("reason", "Reason", "text", maxlen=300)],
                        style="danger", title="Quarantine a member", submit="Quarantine")],
    )


@action("antinuke", "trust_add")
async def trust_add(ctx: ActionContext, payload: dict) -> list:
    member = _need_member(ctx.guild, payload.get("values") or {})
    if any(r["target_id"] == member.id for r in await security.list_trusted(ctx.guild.id)):
        raise ValueError("That member is already trusted.")
    await security.add_trusted(ctx.guild.id, member.id, ctx.user_id)
    return [f"Trusted member added: {member.display_name}"]


@action("antinuke", "trust_remove")
async def trust_remove(ctx: ActionContext, payload: dict) -> list:
    raw = str(payload.get("id") or "")
    if not raw.isdigit() or not await security.remove_trusted(ctx.guild.id, int(raw)):
        raise ValueError("That member is not in the trusted list.")
    return [f"Trusted member removed: {_member_label(ctx.guild, int(raw))}"]


@action("antinuke", "permit_grant")
async def permit_grant(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    member = _need_member(ctx.guild, values)
    tier = need_choice(values, "tier", "Tier", list(TIER_LABELS))
    ok, message = await security.grant_permit_tier(ctx.guild, ctx.user_id, member.id, tier)
    if not ok:
        raise ValueError(message)
    return [f"{member.display_name}: {message}"]


@action("antinuke", "permit_revoke")
async def permit_revoke(ctx: ActionContext, payload: dict) -> list:
    raw = str(payload.get("id") or "")
    if not raw.isdigit():
        raise ValueError("That member does not hold a permit tier.")
    ok, message = await security.revoke_permit_tier(ctx.guild, ctx.user_id, int(raw))
    if not ok:
        raise ValueError(message)
    return [f"{_member_label(ctx.guild, int(raw))}: {message}"]


@action("antinuke", "override_set")
async def override_set(ctx: ActionContext, payload: dict) -> list:
    key = str(payload.get("id") or "")
    actions = _antinuke_actions()
    if key not in actions:
        raise ValueError("That action type does not exist.")
    punishment = need_choice(payload.get("values") or {}, "punishment", "Punishment", [v for v, _ in PUNISHMENT_OPTIONS])
    await security.set_action_punishment(ctx.guild.id, key, punishment)
    return [f"{actions[key]} now triggers {punishment}"]


@action("antinuke", "override_clear")
async def override_clear(ctx: ActionContext, payload: dict) -> list:
    key = str(payload.get("id") or "")
    if not await security.clear_action_punishment(ctx.guild.id, key):
        raise ValueError("There is no override for that action.")
    return [f"Override removed for {_antinuke_actions().get(key, key)}"]


@action("antinuke", "threshold_set")
async def threshold_set(ctx: ActionContext, payload: dict) -> list:
    key = str(payload.get("id") or "")
    if key not in config.ANTINUKE_DEFAULT_THRESHOLDS:
        raise ValueError("That action type does not exist.")
    value = need_int(payload.get("values") or {}, "value", "Threshold", 1, 1000)
    await guild_settings.set(ctx.guild.id, f"antinuke_threshold_{key}", value)
    return [f"Threshold for {key} set to {value}"]


@action("antinuke", "quarantine_role_set")
async def quarantine_role_set(ctx: ActionContext, payload: dict) -> list:
    role = _assignable_role(ctx.guild, need_role(ctx.guild, payload.get("values") or {}, "role", "Role"))
    await guild_settings.set(ctx.guild.id, "antinuke_quarantine_role_id", role.id)
    return [f"Quarantine role set to {role.name}"]


@action("antinuke", "quarantine_add")
async def quarantine_add(ctx: ActionContext, payload: dict) -> list:
    guild = ctx.guild
    values = payload.get("values") or {}
    member = _need_member(guild, values)
    reason = need_text(values, "reason", "Reason", maxlen=300, required=False) or "Manually quarantined from the dashboard"
    if member.id == guild.owner_id or member.bot and member.id == guild.me.id:
        raise ValueError("That member cannot be quarantined.")
    if member.top_role.position >= guild.me.top_role.position:
        raise ValueError("That member's highest role is at or above mine, so I cannot quarantine them.")
    if not await security.quarantine_member(guild, member, reason, by=ctx.user_id):
        raise ValueError("That member is already quarantined.")
    return [f"Quarantined {member.display_name}"]


@action("antinuke", "quarantine_release")
async def quarantine_release(ctx: ActionContext, payload: dict) -> list:
    if not await security.is_real_owner(ctx.guild, ctx.user_id):
        raise ValueError("Only the server owner can release a quarantined member.")
    raw = str(payload.get("id") or "")
    if not raw.isdigit() or not await security.release_member(ctx.guild, int(raw), by=ctx.user_id):
        raise ValueError("That member is not quarantined.")
    return [f"Released {_member_label(ctx.guild, int(raw))} from quarantine"]


@section("antiraid")
async def raid_mode_section(guild: discord.Guild) -> dict:
    state = await db.raw_fetchone("SELECT * FROM antiraid_state WHERE guild_id=?", (guild.id,))
    active = bool(state and state["raid_mode"])
    panic = await security.is_panic_mode_active(guild.id)
    expires = state["raid_mode_expires_at"] if active and state else None
    cells = [
        "Active" if active else "Inactive",
        state["triggered_by"] if active and state["triggered_by"] else "None",
        _when(expires) if expires else ("Manual only" if active else "None"),
        "Active" if panic else "Inactive",
    ]
    toggle = button("raid_mode_toggle", "End raid mode" if active else "Start raid mode", style="ghost" if active else "danger",
                    confirm="End raid mode and return to normal join processing?" if active
                    else "Start raid mode? Every new join is scrutinized and flagged members are actioned automatically.")
    return table(
        "raid_mode", "Raid mode", ["Raid mode", "Triggered by", "Expires", "Server panic mode"],
        [row("state", cells, actions=[toggle])], "",
        description="Panic mode is shared with AutoMod and AntiNuke.",
    )


@section("antiraid")
async def flagged_joins_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch(
        "SELECT user_id, action_taken, joined_at FROM raid_join_log WHERE guild_id=? AND flagged=1 ORDER BY joined_at DESC LIMIT ?",
        (guild.id, config.DASHBOARD_LIST_LIMIT),
    )
    rows = [
        row(f"{r['user_id']}:{int(r['joined_at'])}", [_member_label(guild, r["user_id"]), r["action_taken"] or "No action", _when(r["joined_at"])])
        for r in rows_db
    ]
    return table("flagged_joins", "Recent flagged joins", ["Member", "Action", "When"], rows, "No flagged joins have been logged.")


@action("antiraid", "raid_mode_toggle")
async def raid_mode_toggle(ctx: ActionContext, payload: dict) -> list:
    cog = ctx.bot.get_cog("AntiRaid")
    if cog is None:
        raise ValueError("The AntiRaid module is not loaded.")
    if await cog._is_raid_mode(ctx.guild.id):
        await cog.end_raid_mode(ctx.guild, ended_by=ctx.user_id)
        return ["Raid mode ended"]
    await cog.start_raid_mode(ctx.guild, triggered_by=f"manual:{ctx.user_id}")
    return ["Raid mode started"]


def _automod_heat():
    from cogs import automod as automod_cog

    return automod_cog


@section("automod")
async def heat_section(guild: discord.Guild) -> dict:
    automod_cog = _automod_heat()
    rows = []
    for user_id in list(automod_cog._heat.get(guild.id, {})):
        heat, multiplier = automod_cog._get_heat(guild.id, user_id)
        if heat < 0.05 and multiplier <= 1:
            continue
        rows.append(row(
            user_id, [_member_label(guild, user_id), f"{heat:.1f}", f"{multiplier}x"],
            actions=[button("heat_reset", "Reset", style="danger", confirm="Clear this member's heat score and mute multiplier?")],
        ))
    return table(
        "heat", "AutoMod heat", ["Member", "Heat", "Mute multiplier"], rows, "No members currently carry heat.",
        description=f"Mute at {config.AUTOMOD_HEAT_MUTE_THRESHOLD} heat, panic at {config.AUTOMOD_HEAT_PANIC_THRESHOLD}. Heat decays over time and is kept in memory.",
        buttons=[
            button("heat_check", "Check member", [_id_field()], title="Check a member's heat", submit="Check heat"),
            button("heat_reset", "Reset member", [_id_field()], style="danger", title="Reset a member's heat", submit="Reset heat"),
        ],
    )


@action("automod", "heat_check")
async def heat_check(ctx: ActionContext, payload: dict) -> list:
    member = _need_member(ctx.guild, _target_values(payload))
    heat, multiplier = _automod_heat()._get_heat(ctx.guild.id, member.id)
    return [f"{member.display_name}: heat {heat:.1f}, mute multiplier {multiplier}x"]


@action("automod", "heat_reset")
async def heat_reset(ctx: ActionContext, payload: dict) -> list:
    member = _need_member(ctx.guild, _target_values(payload))
    automod_cog = _automod_heat()
    automod_cog._heat[ctx.guild.id].pop(member.id, None)
    automod_cog._reset_multiplier(ctx.guild.id, member.id)
    return [f"Heat score and mute multiplier cleared for {member.display_name}"]


@section("verification")
async def panel_section(guild: discord.Guild) -> dict:
    channel_id = await guild_settings.get(guild.id, "verification_channel_id")
    message_id = await guild_settings.get(guild.id, "verification_panel_message_id")
    level = await guild_settings.get(guild.id, "verification_level", config.VERIFICATION_LEVELS["none"])
    level_name = next((k for k, v in config.VERIFICATION_LEVELS.items() if v == level), "none").title()
    posted = bool(channel_id and message_id)
    return table(
        "panel", "Verification panel", ["Type", "Channel"],
        [row("panel", [level_name, _channel_name(guild, channel_id) if posted else "Not posted"], actions=[
            button("panel_post", "Repost" if posted else "Post", [fld("channel", "Channel", "channel", value=str(channel_id) if channel_id else "")],
                   style="primary", title="Post verification panel", submit="Post panel"),
        ])],
        "",
        description="Keep this channel hidden from your verified role so only unverified members see it.",
    )


@section("verification")
async def pending_section(guild: discord.Guild) -> dict:
    rows_db = await db.raw_fetch(
        "SELECT user_id, joined_at FROM pending_verification WHERE guild_id=? ORDER BY joined_at DESC LIMIT ?",
        (guild.id, config.DASHBOARD_LIST_LIMIT),
    )
    rows = [
        row(r["user_id"], [_member_label(guild, r["user_id"]), _when(r["joined_at"])],
            actions=[button("approve", "Approve", style="primary", confirm="Approve this member and grant access?")])
        for r in rows_db
    ]
    return table(
        "pending", "Pending members", ["Member", "Joined"], rows, "No members are waiting for verification.",
        buttons=[button("approve", "Approve by ID", [_id_field()], title="Approve a member", submit="Approve member")],
    )


@action("verification", "panel_post")
async def panel_post(ctx: ActionContext, payload: dict) -> list:
    from cogs.verification import VerificationPanelClassicView, VerificationPanelLayout

    guild = ctx.guild
    channel = need_channel(guild, payload.get("values") or {}, "channel", "Channel")
    level = await guild_settings.get(guild.id, "verification_level", config.VERIFICATION_LEVELS["none"])
    if level == config.VERIFICATION_LEVELS["none"]:
        raise ValueError("Set a verification type first.")
    cog = ctx.bot.get_cog("Verification")
    if cog is None:
        raise ValueError("The Verification module is not loaded.")
    if not channel.permissions_for(guild.me).send_messages:
        raise ValueError(f"I cannot send messages in #{channel.name}.")
    old_channel_id = await guild_settings.get(guild.id, "verification_channel_id")
    old_message_id = await guild_settings.get(guild.id, "verification_panel_message_id")
    embeds, text = await cog._resolve_panel_content(guild, guild.get_member(ctx.user_id) or guild.me)
    try:
        if embeds:
            message = await channel.send(content=text, embeds=embeds, view=VerificationPanelClassicView())
        else:
            message = await channel.send(view=VerificationPanelLayout(guild.name, custom_text=text))
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the message: {str(exc)[:150]}")
    old_channel = guild.get_channel(int(old_channel_id)) if old_channel_id else None
    if old_channel is not None and old_message_id:
        try:
            await (await old_channel.fetch_message(int(old_message_id))).delete()
        except discord.HTTPException:
            pass
    await guild_settings.set(guild.id, "verification_channel_id", channel.id)
    await guild_settings.set(guild.id, "verification_panel_message_id", message.id)
    return [f"Verification panel posted in #{channel.name}"]


@action("verification", "approve")
async def approve(ctx: ActionContext, payload: dict) -> list:
    from cogs.verification import _complete_verification

    member = _need_member(ctx.guild, _target_values(payload))
    await _complete_verification(ctx.guild, member)
    return [f"Approved {member.display_name}"]


@section("moderation")
async def cases_section(guild: discord.Guild) -> dict:
    found = await cases.get_mod_cases(guild.id)
    rows = [
        row(r["case_id"], [
            r["case_id"], str(r["action"]).title(), _member_label(guild, r["user_id"]), _member_label(guild, r["moderator_id"]),
            (r["reason"] or "No reason")[:120], _when(r["created_at"]),
        ])
        for r in list(found)[:config.DASHBOARD_LIST_LIMIT]
    ]
    return table(
        "cases", "Recent cases", ["Case", "Action", "Member", "Moderator", "Reason", "When"], rows, "No moderation cases yet.",
        description="The 50 most recent cases.",
    )
