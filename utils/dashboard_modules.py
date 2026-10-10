from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import discord

import config
from utils import db, greeting_config, guild_settings, tickets as ticket_utils, xp_engine

_LEVEL_COLUMNS = {
    "enabled", "xp_min", "xp_max", "text_cooldown_seconds", "voice_enabled", "voice_xp_per_minute",
    "voice_require_unmuted", "voice_require_others", "role_stack_mode", "announce_mode",
    "announce_channel_id", "weekly_reset_enabled", "monthly_reset_enabled",
}
_TICKET_COLUMNS = {"log_channel_id", "max_open", "auto_close_hours"}
_GREETING_COLUMNS = {"enabled", "channel_id", "message_text", "send_as_dm", "use_card"}


class GS:
    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default

    async def get(self, guild_id: int) -> Any:
        return await guild_settings.get(guild_id, self.key, self.default)

    async def set(self, guild_id: int, value: Any) -> None:
        if value is None:
            await guild_settings.delete(guild_id, self.key)
        else:
            await guild_settings.set(guild_id, self.key, value)


class LevelCol:
    def __init__(self, column: str):
        if column not in _LEVEL_COLUMNS:
            raise ValueError(column)
        self.column = column

    async def get(self, guild_id: int) -> Any:
        return (await xp_engine.get_guild_config(guild_id))[self.column]

    async def set(self, guild_id: int, value: Any) -> None:
        if isinstance(value, bool):
            value = int(value)
        await db.raw_execute(
            f"INSERT INTO guild_leveling_config (guild_id, {self.column}) VALUES (?, ?)"
            f" ON CONFLICT(guild_id) DO UPDATE SET {self.column}=excluded.{self.column}",
            (guild_id, value),
        )


class TicketCol:
    def __init__(self, column: str):
        if column not in _TICKET_COLUMNS:
            raise ValueError(column)
        self.column = column

    async def get(self, guild_id: int) -> Any:
        return (await ticket_utils.get_settings(guild_id))[self.column]

    async def set(self, guild_id: int, value: Any) -> None:
        await ticket_utils.update_settings(guild_id, **{self.column: value})


class GreetCol:
    def __init__(self, trigger: str, column: str):
        if column not in _GREETING_COLUMNS or trigger not in config.GREETING_TRIGGER_TYPES:
            raise ValueError(column)
        self.trigger = trigger
        self.column = column

    async def get(self, guild_id: int) -> Any:
        return (await greeting_config.get_config(guild_id, self.trigger))[self.column]

    async def set(self, guild_id: int, value: Any) -> None:
        if isinstance(value, bool):
            value = int(value)
        await greeting_config.set_config_fields(guild_id, self.trigger, **{self.column: value})


@dataclass
class Field:
    key: str
    label: str
    kind: str
    store: Any
    help: str = ""
    min: Optional[int] = None
    max: Optional[int] = None
    scale: int = 1
    options: list = field(default_factory=list)
    maxlen: int = 200
    group: str = ""
    placeholder: str = ""


@dataclass
class Module:
    key: str
    name: str
    description: str
    category: str
    icon: str
    fields: list = field(default_factory=list)
    toggle: Any = None
    commands: str = ""
    note: str = ""
    extra: Optional[Callable[[discord.Guild], Awaitable[list]]] = None


def _bool(key, label, store, help="", group=""):
    return Field(key, label, "bool", store, help=help, group=group)


def _int(key, label, store, lo, hi, help="", scale=1, group=""):
    return Field(key, label, "int", store, help=help, min=lo, max=hi, scale=scale, group=group)


def _select(key, label, store, options, help="", group=""):
    return Field(key, label, "select", store, help=help, options=options, group=group)


def _channel(key, label, store, help="", group=""):
    return Field(key, label, "channel", store, help=help, group=group)


def _role(key, label, store, help="", group=""):
    return Field(key, label, "role", store, help=help, group=group)


def _roles(key, label, store, help="", group=""):
    return Field(key, label, "roles", store, help=help, group=group)


def _lines(key, label, store, help="", placeholder="", group=""):
    return Field(key, label, "lines", store, help=help, placeholder=placeholder, group=group)


def _text(key, label, store, help="", maxlen=500, group=""):
    return Field(key, label, "textarea", store, help=help, maxlen=maxlen, group=group)


PUNISHMENTS = [("quarantine", "Quarantine"), ("strip_roles", "Strip roles"), ("kick", "Kick"), ("ban", "Ban")]
RAID_ACTIONS = [("kick", "Kick"), ("ban", "Ban"), ("timeout", "Timeout")]
VERIFY_LEVELS = [(v, k.title()) for k, v in config.VERIFICATION_LEVELS.items()]


def _greeting_fields() -> list:
    labels = {"join": "Member joins", "leave": "Member leaves", "boost": "Server boosted", "ban": "Member banned"}
    out = []
    for trigger in config.GREETING_TRIGGER_TYPES:
        group = labels[trigger]
        out.append(_bool(f"{trigger}_enabled", "Enabled", GreetCol(trigger, "enabled"), group=group))
        out.append(_channel(f"{trigger}_channel", "Channel", GreetCol(trigger, "channel_id"), group=group))
        out.append(_text(f"{trigger}_message", "Message", GreetCol(trigger, "message_text"),
                         help="Supports the same placeholders as the greet commands.", maxlen=1500, group=group))
        out.append(_bool(f"{trigger}_card", "Send an image card", GreetCol(trigger, "use_card"), group=group))
        out.append(_bool(f"{trigger}_dm", "Send as a direct message", GreetCol(trigger, "send_as_dm"), group=group))
    return out


async def _tickets_extra(guild: discord.Guild) -> list:
    panels = await ticket_utils.list_panels(guild.id)
    limit = await ticket_utils.limit_for(guild.id, "panels")
    rows = []
    for p in panels:
        channel = guild.get_channel(p["channel_id"]) if p["channel_id"] else None
        rows.append([
            p["name"],
            f"#{channel.name}" if channel else "Not posted",
            str(len(ticket_utils.parse_ids(p["staff_role_ids"]))),
            str(len(ticket_utils.parse_list(p["questions"]))),
        ])
    open_now = await ticket_utils.active_count(guild.id)
    active_limit = await ticket_utils.limit_for(guild.id, "active")
    return [
        {"title": f"Panels ({len(panels)}/{limit})", "columns": ["Panel", "Posted in", "Staff roles", "Questions"], "rows": rows,
         "empty": "No panels yet. Create one with the ticket panel create command."},
        {"title": "Usage", "columns": ["Open tickets", "Server limit"], "rows": [[str(open_now), str(active_limit)]], "empty": ""},
    ]


async def _logging_extra(guild: discord.Guild) -> list:
    rows = await db.raw_fetch("SELECT category, channel_id FROM log_channels WHERE guild_id=?", (guild.id,))
    out = []
    for r in rows:
        channel = guild.get_channel(r["channel_id"]) if r["channel_id"] else None
        label = config.LOG_CATEGORIES.get(r["category"], {}).get("label", r["category"])
        out.append([label, f"#{channel.name}" if channel else "Missing channel"])
    return [{"title": "Log channels", "columns": ["Category", "Channel"], "rows": out,
             "empty": "Logging is not set up yet. Run the logs setup command in Discord."}]


async def _nsfw_extra(guild: discord.Guild) -> list:
    role_row = await db.raw_fetchone("SELECT role_id FROM nsfw_config WHERE guild_id=?", (guild.id,))
    channels = await db.raw_fetch("SELECT channel_id FROM nsfw_channels WHERE guild_id=?", (guild.id,))
    role = guild.get_role(role_row["role_id"]) if role_row else None
    rows = [["NSFW role", f"@{role.name}" if role else "Not set"], ["Registered channels", str(len(channels))]]
    return [{"title": "Status", "columns": ["Setting", "Value"], "rows": rows, "empty": ""}]


MODULES: list[Module] = [
    Module("automod", "AutoMod", "Filter banned words, invites and unwanted links automatically.", "Security", "shield",
           toggle=GS("automod_enabled", False), commands="AutoMod", fields=[
               _bool("block_invites", "Block Discord invites", GS("automod_block_invites", False)),
               _lines("banned_words", "Banned words", GS("automod_banned_words", []), help="One word or phrase per line.", placeholder="word"),
               _lines("link_blocklist", "Blocked links", GS("automod_link_blocklist", []), help="One domain per line."),
               _lines("link_allowlist", "Allowed links", GS("automod_link_allowlist", []), help="Domains that are always allowed, one per line."),
           ]),
    Module("antinuke", "AntiNuke", "Stop malicious admin actions such as mass bans and channel deletion.", "Security", "lock",
           toggle=GS("antinuke_enabled", False), commands="AntiNuke", fields=[
               _bool("strict_mode", "Strict mode", GS("antinuke_strict_mode", config.ANTINUKE_STRICT_MODE_DEFAULT),
                     help="Treat any dangerous permission grant as a violation."),
               _select("punishment", "Default punishment", GS("antinuke_punishment", config.ANTINUKE_DEFAULT_PUNISHMENT), PUNISHMENTS),
               _bool("watch_quarantined", "Keep watching quarantined members", GS("antinuke_watch_quarantined", config.ANTINUKE_WATCH_QUARANTINED_DEFAULT)),
           ]),
    Module("antiraid", "AntiRaid", "Detect join floods and new accounts, and lock down during a raid.", "Security", "radar",
           toggle=GS("antiraid_enabled", config.ANTIRAID_ENABLED_DEFAULT), commands="AntiRaid", fields=[
               _int("min_age", "Minimum account age (days)", GS("antiraid_min_age_seconds", config.ANTIRAID_MIN_ACCOUNT_AGE_SECONDS), 0, 365, scale=86400),
               _int("velocity_count", "Joins that trigger a raid", GS("antiraid_join_velocity_count", config.ANTIRAID_JOIN_VELOCITY_COUNT), 2, 200),
               _int("velocity_window", "Within this many seconds", GS("antiraid_join_velocity_window", config.ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS), 2, 300),
               _bool("flag_no_avatar", "Flag accounts without an avatar", GS("antiraid_flag_no_avatar", config.ANTIRAID_FLAG_NO_AVATAR)),
               _select("join_action", "Action on flagged joins", GS("antiraid_join_action", config.ANTIRAID_JOIN_ACTION), RAID_ACTIONS),
               _int("raid_duration", "Raid mode length (minutes)", GS("antiraid_raid_mode_duration", config.ANTIRAID_RAID_MODE_DURATION_SECONDS), 1, 1440, scale=60),
               _channel("alert_channel", "Alert channel", GS("antiraid_alert_channel_id")),
           ]),
    Module("verification", "Verification", "Gate new members behind a button, captcha or manual review.", "Security", "badge",
           commands="Verification", fields=[
               _select("level", "Verification type", GS("verification_level", config.VERIFICATION_LEVELS["none"]), VERIFY_LEVELS,
                       help="Post the panel with the verification setup command after changing this."),
               _role("verified_role", "Verified role", GS("verification_role_id")),
               _role("gate_role", "Gate role", GS("verification_gate_role_id"), help="Given on join and removed after verifying."),
               _bool("timeout_enabled", "Remove members who never verify", GS("verification_pending_timeout_enabled", config.VERIFICATION_PENDING_TIMEOUT_ENABLED_DEFAULT)),
               _int("timeout_minutes", "Minutes before removal", GS("verification_pending_timeout_minutes", config.VERIFICATION_PENDING_TIMEOUT_MINUTES_DEFAULT), 1, 10080),
               _select("timeout_action", "Removal action", GS("verification_pending_timeout_action", config.VERIFICATION_PENDING_TIMEOUT_ACTION_DEFAULT),
                       [("kick", "Kick"), ("ban", "Ban")]),
           ]),
    Module("autorole", "AutoRole", "Give roles automatically when members or bots join or verify.", "Security", "tag",
           commands="AutoRole", fields=[
               _roles("human_join", "Roles for new members", GS("autorole_human_join", [])),
               _roles("bot_join", "Roles for new bots", GS("autorole_bot_join", [])),
               _roles("on_verify", "Roles after verifying", GS("autorole_on_verify", [])),
           ]),
    Module("moderation", "Moderation", "Ban, kick, mute, warn and purge with a full case history.", "Moderation", "gavel",
           commands="Moderation", note="Moderation runs from commands. Use the command list to see everything available."),
    Module("logging", "Logging", "Send moderation, security, member and message logs to dedicated channels.", "Moderation", "scroll",
           commands="Logging", note="Log channels are created with webhooks by the bot. Set them up with the logs commands.", extra=_logging_extra),
    Module("leveling", "Leveling", "Reward activity in text and voice with XP, levels and role rewards.", "Community", "chart",
           toggle=LevelCol("enabled"), commands="Leveling", fields=[
               _int("xp_min", "XP per message (min)", LevelCol("xp_min"), 1, 500, group="Text XP"),
               _int("xp_max", "XP per message (max)", LevelCol("xp_max"), 1, 500, group="Text XP"),
               _int("cooldown", "Cooldown between XP gains (seconds)", LevelCol("text_cooldown_seconds"), 0, 3600, group="Text XP"),
               _bool("voice_enabled", "Voice XP", LevelCol("voice_enabled"), group="Voice XP"),
               _int("voice_xp", "XP per minute in voice", LevelCol("voice_xp_per_minute"), 0, 500, group="Voice XP"),
               _bool("voice_unmuted", "Require unmuted", LevelCol("voice_require_unmuted"), group="Voice XP"),
               _bool("voice_others", "Require other members present", LevelCol("voice_require_others"), group="Voice XP"),
               _select("role_mode", "Role rewards", LevelCol("role_stack_mode"), [("stack", "Stack all earned roles"), ("nonstack", "Keep only the highest")], group="Rewards"),
               _bool("weekly", "Weekly leaderboard reset", LevelCol("weekly_reset_enabled"), group="Rewards"),
               _bool("monthly", "Monthly leaderboard reset", LevelCol("monthly_reset_enabled"), group="Rewards"),
               _select("announce_mode", "Level-up announcements", LevelCol("announce_mode"),
                       [("channel", "In a channel"), ("dm", "Direct message"), ("off", "Off")], group="Announcements"),
               _channel("announce_channel", "Announcement channel", LevelCol("announce_channel_id"), group="Announcements"),
           ]),
    Module("greetings", "Greetings", "Welcome, farewell, boost and ban messages with optional image cards.", "Community", "wave",
           commands="Greetings", fields=_greeting_fields()),
    Module("tickets", "Tickets", "Private support tickets with panels, forms, claiming and transcripts.", "Community", "ticket",
           commands="Tickets", fields=[
               _channel("log_channel", "Log channel", TicketCol("log_channel_id"), help="Where ticket logs and transcripts are sent."),
               _int("max_open", "Open tickets per member", TicketCol("max_open"), 1, config.TICKET_MAX_OPEN_LIMIT),
               _int("auto_close", "Close inactive tickets after (hours, 0 is off)", TicketCol("auto_close_hours"), 0, 720),
           ], extra=_tickets_extra),
    Module("giveaways", "Giveaways", "Run giveaways with role and account age requirements.", "Community", "gift", commands="Giveaways",
           note="Giveaways are created from commands so each one can be configured on the spot."),
    Module("reaction_roles", "Reaction Roles", "Let members pick their own roles from buttons and menus.", "Community", "mouse", commands="ReactionRoles",
           note="Reaction role panels are built from commands."),
    Module("custom_commands", "Custom Commands", "Build your own commands with triggers, conditions and actions.", "Community", "terminal", commands="CustomCommands",
           note="Custom commands are built from commands."),
    Module("alerts", "Alerts", "Post YouTube uploads, streams and Twitch go-lives.", "Community", "bell", commands="Alerts",
           note="Alerts are subscribed to from commands."),
    Module("music", "Music", "Play music and 24/7 lofi radio in voice channels.", "Fun", "music", commands="Music", fields=[
        _select("source", "Default search source", GS("music_source", "youtube"),
                [("youtube", "YouTube"), ("soundcloud", "SoundCloud"), ("spotify", "Spotify")]),
    ]),
    Module("fun", "Fun", "Ship, quotes, truth or dare, anime lookups and social commands.", "Fun", "spark", commands="Fun",
           note="Fun commands need no setup."),
    Module("utility", "Utility", "Server info, AFK status, embeds and bot customization.", "Utility", "wrench", commands="Utility",
           note="Utility commands need no setup."),
    Module("nsfw", "NSFW Channels", "Lock NSFW channels to a role instead of a one-click age gate.", "Utility", "eye", commands="NSFW",
           note="NSFW channels change channel permissions, so they are managed from commands.", extra=_nsfw_extra),
]

MODULE_INDEX: dict[str, Module] = {m.key: m for m in MODULES}
CATEGORY_ORDER = ["Security", "Moderation", "Community", "Fun", "Utility"]


def _display(fld: Field, raw: Any) -> Any:
    if fld.kind == "bool":
        return bool(raw)
    if fld.kind == "int":
        if raw is None:
            return None
        value = raw / fld.scale if fld.scale != 1 else raw
        return int(value) if float(value).is_integer() else round(value, 2)
    if fld.kind == "lines":
        return "\n".join(str(x) for x in (raw or []))
    if fld.kind == "roles":
        return [int(x) for x in (raw or [])]
    if fld.kind in ("channel", "role"):
        return int(raw) if raw else None
    if fld.kind == "select":
        return raw
    return raw or ""


async def module_enabled(guild: discord.Guild, module: Module) -> Optional[bool]:
    if module.toggle is None:
        return None
    return bool(await module.toggle.get(guild.id))


async def module_summary(guild: discord.Guild) -> list[dict]:
    out = []
    for m in MODULES:
        out.append({
            "key": m.key, "name": m.name, "description": m.description, "category": m.category, "icon": m.icon,
            "toggleable": m.toggle is not None, "enabled": await module_enabled(guild, m),
            "configurable": bool(m.fields), "commands": m.commands,
        })
    return out


def guild_choices(guild: discord.Guild) -> dict:
    channels = [
        {"id": str(c.id), "name": c.name, "parent": c.category.name if c.category else ""}
        for c in sorted(guild.text_channels, key=lambda c: (c.category.position if c.category else -1, c.position))
    ]
    roles = [
        {"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}" if r.color.value else ""}
        for r in sorted(guild.roles, key=lambda r: -r.position) if not r.is_default()
    ]
    return {"channels": channels, "roles": roles}


async def module_detail(guild: discord.Guild, module: Module) -> dict:
    fields = []
    for f in module.fields:
        value = _display(f, await f.store.get(guild.id))
        if f.kind in ("channel", "role") and value is not None:
            value = str(value)
        if f.kind == "roles":
            value = [str(v) for v in value]
        fields.append({
            "key": f.key, "label": f.label, "kind": f.kind, "help": f.help, "min": f.min, "max": f.max,
            "options": [{"value": str(v), "label": l} for v, l in f.options], "group": f.group,
            "placeholder": f.placeholder, "maxlen": f.maxlen, "value": value,
        })
    extras = await module.extra(guild) if module.extra else []
    return {
        "key": module.key, "name": module.name, "description": module.description, "category": module.category,
        "icon": module.icon, "toggleable": module.toggle is not None, "enabled": await module_enabled(guild, module),
        "note": module.note, "commands": module.commands, "fields": fields, "extras": extras,
    }


def _coerce(guild: discord.Guild, fld: Field, raw: Any) -> Any:
    if fld.kind == "bool":
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "on", "yes")
        return bool(raw)
    if fld.kind == "int":
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{fld.label} must be a number.")
        if (fld.min is not None and number < fld.min) or (fld.max is not None and number > fld.max):
            raise ValueError(f"{fld.label} must be between {fld.min} and {fld.max}.")
        return int(round(number * fld.scale))
    if fld.kind == "select":
        for value, _ in fld.options:
            if str(value) == str(raw):
                return value
        raise ValueError(f"{fld.label} has an invalid option.")
    if fld.kind == "channel":
        if raw in (None, "", "0"):
            return None
        channel = guild.get_channel(int(raw)) if str(raw).isdigit() else None
        if not isinstance(channel, discord.TextChannel):
            raise ValueError(f"{fld.label} must be a text channel in this server.")
        return channel.id
    if fld.kind == "role":
        if raw in (None, "", "0"):
            return None
        role = guild.get_role(int(raw)) if str(raw).isdigit() else None
        if role is None or role.is_default():
            raise ValueError(f"{fld.label} must be a role in this server.")
        return role.id
    if fld.kind == "roles":
        items = raw if isinstance(raw, list) else []
        ids = []
        for item in items:
            role = guild.get_role(int(item)) if str(item).isdigit() else None
            if role is None or role.is_default():
                raise ValueError(f"{fld.label} contains a role that no longer exists.")
            if role.id not in ids:
                ids.append(role.id)
        if len(ids) > 20:
            raise ValueError(f"{fld.label} can have up to 20 roles.")
        return ids
    if fld.kind == "lines":
        text = raw if isinstance(raw, str) else "\n".join(raw or [])
        items = []
        for line in text.splitlines():
            line = line.strip()
            if line and line not in items:
                items.append(line[:100])
        if len(items) > 100:
            raise ValueError(f"{fld.label} can have up to 100 entries.")
        return items
    text = (raw or "").strip() if isinstance(raw, str) else ""
    if len(text) > fld.maxlen:
        raise ValueError(f"{fld.label} can be at most {fld.maxlen} characters.")
    return text or None


def _describe(fld: Field, value: Any) -> str:
    if fld.kind == "bool":
        return "on" if value else "off"
    if fld.kind == "int":
        shown = _display(fld, value)
        return str(shown)
    if fld.kind in ("lines", "roles"):
        return f"{len(value or [])} item(s)"
    if fld.kind in ("textarea",):
        return "updated"
    return str(value) if value is not None else "none"


async def apply_module(guild: discord.Guild, module: Module, values: dict) -> list[str]:
    by_key = {f.key: f for f in module.fields}
    staged = {}
    for key, raw in values.items():
        fld = by_key.get(key)
        if fld is None:
            raise ValueError("Unknown setting.")
        staged[key] = _coerce(guild, fld, raw)

    if module.key == "leveling":
        lo = staged.get("xp_min", await by_key["xp_min"].store.get(guild.id))
        hi = staged.get("xp_max", await by_key["xp_max"].store.get(guild.id))
        if lo > hi:
            raise ValueError("Minimum XP cannot be higher than maximum XP.")

    changes = []
    for key, value in staged.items():
        fld = by_key[key]
        current = await fld.store.get(guild.id)
        if fld.kind == "lines":
            same = list(current or []) == value
        elif fld.kind == "roles":
            same = [int(x) for x in (current or [])] == value
        elif fld.kind == "bool":
            same = bool(current) == value
        else:
            same = current == value
        if same:
            continue
        await fld.store.set(guild.id, value)
        changes.append(f"{fld.label}: {_describe(fld, value)}")
    return changes


async def set_toggle(guild: discord.Guild, module: Module, enabled: bool) -> bool:
    if module.toggle is None:
        raise ValueError("This module has no on/off switch.")
    current = bool(await module.toggle.get(guild.id))
    if current == enabled:
        return False
    await module.toggle.set(guild.id, enabled)
    return True
