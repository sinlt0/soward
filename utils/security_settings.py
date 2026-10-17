import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import config
from utils import guild_settings
from utils.converters import format_duration

MODULES = ("security", "antinuke", "antiraid", "automod", "verification")
MODULE_TITLES = {
    "security": "Security core",
    "antinuke": "AntiNuke",
    "antiraid": "AntiRaid",
    "automod": "AutoMod",
    "verification": "Verification",
}

GATE_ACTIONS = ("none", "timeout", "kick", "ban", "quarantine")
PUNISH_ACTIONS = ("quarantine", "strip_roles", "kick", "ban", "kick_bot")
HEAT_ACTIONS = ("timeout", "kick", "ban", "quarantine", "none")
VERIFY_LEVEL_NAMES = tuple(config.VERIFICATION_LEVELS)

DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
TRUE_WORDS = {"on", "true", "yes", "1", "enable", "enabled", "y"}
FALSE_WORDS = {"off", "false", "no", "0", "disable", "disabled", "n"}


@dataclass(frozen=True)
class Setting:
    module: str
    key: str
    kind: str
    default: Any
    label: str
    help: str = ""
    lo: Optional[float] = None
    hi: Optional[float] = None
    choices: tuple = ()
    group: str = "General"
    critical: bool = False
    mapping: tuple = ()

    @property
    def store(self) -> str:
        return f"{self.module}_{self.key}"

    @property
    def path(self) -> str:
        return f"{self.module}.{self.key}"


_REGISTRY: dict[str, Setting] = {}


def _add(setting: Setting) -> None:
    _REGISTRY[setting.path] = setting


def _bool(module, key, default, label, help="", group="General", critical=False):
    _add(Setting(module, key, "bool", default, label, help, group=group, critical=critical))


def _int(module, key, default, lo, hi, label, help="", group="General"):
    _add(Setting(module, key, "int", default, label, help, lo, hi, group=group))


def _float(module, key, default, lo, hi, label, help="", group="General"):
    _add(Setting(module, key, "float", default, label, help, lo, hi, group=group))


def _duration(module, key, default, lo, hi, label, help="", group="General"):
    _add(Setting(module, key, "duration", default, label, help, lo, hi, group=group))


def _choice(module, key, default, choices, label, help="", group="General", critical=False):
    _add(Setting(module, key, "choice", default, label, help, choices=tuple(choices), group=group, critical=critical))


def _role(module, key, label, help="", group="General"):
    _add(Setting(module, key, "role", None, label, help, group=group))


def _channel(module, key, label, help="", group="General"):
    _add(Setting(module, key, "channel", None, label, help, group=group))


def _list(module, key, kind, label, help="", group="General", limit=100):
    _add(Setting(module, key, kind, [], label, help, hi=limit, group=group))


def _build() -> None:
    _bool("security", "lock", config.SECURITY_LOCK_DEFAULT, "Tier lock", "When on, only the owner, Extra Owners and Trusted Admins can change security settings.", critical=True)
    _channel("security", "log_channel_id", "Security log channel", "Where every security action is logged.")
    _channel("security", "alert_channel_id", "Alert channel", "Where urgent alerts are posted. Falls back to the log channel.")
    _role("security", "alert_role_id", "Alert role", "Pinged when AntiNuke triggers or a raid starts.")
    _bool("security", "alert_owner", True, "DM the owner", "Direct message the server owner on serious detections.")
    _bool("security", "auto_backup", False, "Automatic backups", "Snapshot roles and channels on a schedule so they can be restored.")
    _int("security", "backup_interval_hours", 6, 1, 168, "Backup interval (hours)")
    _int("security", "backup_keep", 5, 1, 25, "Automatic backups to keep")
    _duration("security", "lockdown_duration", 1800, 60, 86400, "Lockdown length", "How long a lockdown lasts before it lifts on its own.")
    _bool("security", "lockdown_on_nuke", False, "Lock the server after an AntiNuke trigger")
    _bool("security", "lockdown_on_raid", False, "Lock the server when raid mode starts")
    _list("security", "lockdown_skip_channels", "channels", "Channels lockdown skips", "Channels left open during a lockdown.", limit=50)
    _list("security", "protected_roles", "roles", "Protected roles", "Only trusted members can give or remove these roles.", limit=25)
    _bool("security", "threat_score", True, "Threat score", "Raise protection automatically when many detections happen close together.")
    _int("security", "threat_threshold", 8, 2, 100, "Threat points that trigger Beast Mode")
    _duration("security", "threat_window", 600, 60, 86400, "Threat window")

    _bool("antinuke", "enabled", False, "AntiNuke", "Master switch for AntiNuke.", critical=True)
    _bool("antinuke", "restore_from_backup", False, "Restore from backup after an attack", "After an AntiNuke incident, recreate missing roles, channels and bans from the latest backup.")
    _bool("antinuke", "strict_mode", config.ANTINUKE_STRICT_MODE_DEFAULT, "Strict mode", "Any dangerous permission grant by an untrusted member is punished at once.")
    _bool("antinuke", "admin_bypass", config.ANTINUKE_ADMIN_BYPASS_DEFAULT, "Administrator bypass", "Let members with Administrator skip AntiNuke without being trusted.", critical=True)
    _bool("antinuke", "watch_quarantined", config.ANTINUKE_WATCH_QUARANTINED_DEFAULT, "Watch quarantined members", "Any action by a quarantined member is punished immediately.")
    _bool("antinuke", "quarantine_hold", True, "Quarantine hold", "Punish anyone who changes the roles of a quarantined member.")
    _bool("antinuke", "restore", config.ANTINUKE_RESTORE_DEFAULT, "Auto restore", "Recreate deleted channels and roles and remove what a flagged member created.")
    _bool("antinuke", "bot_add_block", config.ANTINUKE_BOT_ADD_BLOCK_DEFAULT, "Block untrusted bot adds", "Kick bots added by untrusted members.")
    _bool("antinuke", "monitor_overwrites", True, "Monitor channel permissions", "Revert dangerous permission overwrites for @everyone.")
    _bool("antinuke", "protect_everyone", True, "Protect @everyone", "Revert and punish dangerous permissions given to @everyone at once.")
    _bool("antinuke", "alert_owner", config.ANTINUKE_ALERT_OWNER_DEFAULT, "DM the owner")
    _channel("antinuke", "alert_channel_id", "Alert channel")
    _duration("antinuke", "window", config.ANTINUKE_THRESHOLD_WINDOW_SECONDS, 3, 3600, "Short window", "Actions are counted over this window against the per-action limit.")
    _choice("antinuke", "punishment", config.ANTINUKE_DEFAULT_PUNISHMENT, PUNISH_ACTIONS, "Default punishment")
    _duration("antinuke", "punish_cooldown", config.ANTINUKE_PUNISH_COOLDOWN_SECONDS, 5, 600, "Repeat punishment cooldown")
    _duration("antinuke", "rollback_window", config.ANTINUKE_ROLLBACK_WINDOW_SECONDS, 30, 3600, "Rollback window", "How far back a flagged member's changes are undone.")
    for name, limit in config.ANTINUKE_DEFAULT_THRESHOLDS.items():
        label = name.replace("_", " ").capitalize()
        _int("antinuke", f"threshold_{name}", limit, 1, 100, f"{label} limit", "Actions allowed inside the short window.", group="Limits")
        _int("antinuke", f"hourly_{name}", 0, 0, 1000, f"{label} hourly limit", "Actions allowed per hour. 0 turns it off.", group="Hourly limits")
        _bool("antinuke", f"enabled_{name}", True, f"Watch {label.lower()}", group="Filters")
    for name, limit in {"vanity_change": 1, "invite_delete": 5, "quarantine_touch": 1, "protected_role": 1, "channel_permission": 1}.items():
        label = name.replace("_", " ").capitalize()
        _int("antinuke", f"threshold_{name}", limit, 1, 100, f"{label} limit", group="Limits")
        _int("antinuke", f"hourly_{name}", 0, 0, 1000, f"{label} hourly limit", group="Hourly limits")
        _bool("antinuke", f"enabled_{name}", True, f"Watch {label.lower()}", group="Filters")

    _bool("antiraid", "enabled", config.ANTIRAID_ENABLED_DEFAULT, "AntiRaid", "Master switch for AntiRaid.", critical=True)
    _int("antiraid", "join_velocity_count", config.ANTIRAID_JOIN_VELOCITY_COUNT, 2, 200, "Joins that trigger a raid", group="Raid detection")
    _duration("antiraid", "join_velocity_window", config.ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS, 2, 600, "Join window", group="Raid detection")
    _duration("antiraid", "raid_mode_duration", config.ANTIRAID_RAID_MODE_DURATION_SECONDS, 60, 86400, "Raid mode length", group="Raid detection")
    _choice("antiraid", "raid_mode_action", config.ANTIRAID_RAID_MODE_ACTION, GATE_ACTIONS[1:], "Action during raid mode", group="Raid detection")
    _choice("antiraid", "raid_target", "all", ("all", "suspicious"), "Who raid mode acts on", "All new joins, or only suspicious ones.", group="Raid detection")
    _bool("antiraid", "sweep", config.ANTIRAID_SWEEP_DEFAULT, "Sweep the join burst", group="Raid detection")
    _bool("antiraid", "raise_verification", config.ANTIRAID_RAISE_VERIFICATION_DEFAULT, "Raise server verification level", group="Raid detection")
    _bool("antiraid", "follow_antinuke", config.ANTIRAID_FOLLOW_ANTINUKE_DEFAULT, "Start raid mode on AntiNuke triggers", group="Raid detection")
    _bool("antiraid", "id_cluster", True, "Account age cluster flag", "Raid mode when many accounts created close together join.", group="Raid detection")
    _duration("antiraid", "id_window", 3600, 60, 604800, "Account creation spread", group="Raid detection")
    _int("antiraid", "id_count", 4, 2, 50, "Accounts in the cluster", group="Raid detection")
    _bool("antiraid", "similar_names", True, "Similar name flag", "Raid mode when many joiners share the same name pattern.", group="Raid detection")
    _int("antiraid", "similar_count", 4, 2, 50, "Similar names to trigger", group="Raid detection")
    _channel("antiraid", "alert_channel_id", "Alert channel", group="Raid detection")
    _bool("antiraid", "action_dm", False, "DM before acting", "Tell the member why before they are kicked or banned.", group="Join gate")
    _choice("antiraid", "join_action", config.ANTIRAID_JOIN_ACTION, GATE_ACTIONS[1:], "Default gate action", group="Join gate")
    _bool("antiraid", "gate_age_enabled", True, "Account age filter", group="Join gate")
    _duration("antiraid", "min_age_seconds", config.ANTIRAID_MIN_ACCOUNT_AGE_SECONDS, 0, 31536000, "Minimum account age", group="Join gate")
    _choice("antiraid", "gate_age_action", "default", ("default",) + GATE_ACTIONS[1:], "Account age action", group="Join gate")
    _bool("antiraid", "gate_age_dm", False, "Show the age requirement in the DM", group="Join gate")
    _bool("antiraid", "gate_noavatar_enabled", config.ANTIRAID_FLAG_NO_AVATAR, "No avatar filter", group="Join gate")
    _choice("antiraid", "gate_noavatar_action", "default", ("default",) + GATE_ACTIONS[1:], "No avatar action", group="Join gate")
    _bool("antiraid", "gate_name_enabled", False, "Advertising name filter", "Names containing invites or links.", group="Join gate")
    _choice("antiraid", "gate_name_action", "default", ("default",) + GATE_ACTIONS[1:], "Advertising name action", group="Join gate")
    _list("antiraid", "name_filter", "words", "Blocked name patterns", "Joins whose name contains one of these are flagged.", group="Join gate", limit=50)
    _choice("antiraid", "name_filter_action", "default", ("default",) + GATE_ACTIONS[1:], "Name pattern action", group="Join gate")
    _bool("antiraid", "gate_unverified_bots", False, "Unverified bot filter", "Bots without Discord's verified badge.", group="Join gate")
    _choice("antiraid", "gate_unverified_bots_action", "kick", GATE_ACTIONS[1:], "Unverified bot action", group="Join gate")
    _bool("antiraid", "gate_suspicious_enabled", False, "Suspicious account filter", "Scores new accounts by age, avatar, name and badges.", group="Join gate")
    _int("antiraid", "gate_suspicious_score", 3, 1, 10, "Suspicion score needed", group="Join gate")
    _choice("antiraid", "gate_suspicious_action", "default", ("default",) + GATE_ACTIONS[1:], "Suspicious account action", group="Join gate")
    _duration("antiraid", "timeout_duration", 3600, 60, 2419200, "Timeout length", group="Join gate")
    _bool("antiraid", "gate_impersonation_enabled", False, "Staff impersonation filter", "Joins whose name is nearly the same as a staff member's.", group="Join gate")
    _float("antiraid", "impersonation_threshold", 0.88, 0.7, 1.0, "Impersonation similarity", "How alike two names must be, from 0.7 to 1.0.", group="Join gate")
    _choice("antiraid", "gate_impersonation_action", "default", ("default",) + GATE_ACTIONS[1:], "Impersonation action", group="Join gate")
    _bool("antiraid", "gate_evasion_enabled", False, "Ban evasion filter", "Joins that look like a banned user: same avatar or a very similar name. A heuristic, not proof.", group="Join gate")
    _float("antiraid", "evasion_threshold", 0.92, 0.8, 1.0, "Ban evasion name similarity", group="Join gate")
    _choice("antiraid", "gate_evasion_action", "default", ("default",) + GATE_ACTIONS[1:], "Ban evasion action", group="Join gate")
    _bool("antiraid", "invite_tracking", False, "Invite tracking", "Remember which invite each member used. Needs Manage Server.", group="Invites")
    _bool("antiraid", "revoke_invites", False, "Revoke raid invites", "Delete an invite when several flagged joins came through it.", group="Invites")
    _int("antiraid", "revoke_invite_min", 3, 2, 50, "Flagged joins before revoking", group="Invites")
    _duration("antiraid", "invite_window", 600, 60, 86400, "Invite window", "How far back flagged joins are counted.", group="Invites")

    _bool("automod", "enabled", False, "AutoMod", "Master switch for AutoMod.", critical=True)
    _bool("automod", "block_invites", False, "Block invite links", group="Filters")
    _int("automod", "mention_limit", config.AUTOMOD_MENTION_LIMIT, 2, 50, "Mention limit", group="Filters")
    _int("automod", "attachment_limit", config.AUTOMOD_ATTACHMENT_LIMIT, 2, 20, "Attachment limit", group="Filters")
    _int("automod", "emoji_limit", 10, 3, 100, "Emoji limit", group="Filters")
    _int("automod", "caps_min_length", config.AUTOMOD_CAPS_MIN_LENGTH, 5, 200, "Caps minimum length", group="Filters")
    _float("automod", "caps_ratio", config.AUTOMOD_CAPS_RATIO, 0.3, 1.0, "Caps ratio", group="Filters")
    _int("automod", "wall_length", 600, 200, 4000, "Text wall length", group="Filters")
    _duration("automod", "duplicate_window", config.AUTOMOD_DUPLICATE_WINDOW_SECONDS, 5, 600, "Duplicate window", group="Filters")
    _float("automod", "duplicate_similarity", config.AUTOMOD_DUPLICATE_SIMILARITY, 0.5, 1.0, "Duplicate similarity", group="Filters")
    for name, default in {"scamlinks": True, "caps": True, "zalgo": True, "duplicates": True, "emoji": True, "attachments": True, "wholeword": False}.items():
        _bool("automod", f"filter_{name}", default, f"Filter: {name}", group="Filters")
    _list("automod", "banned_words", "words", "Banned words", group="Lists", limit=200)
    _list("automod", "link_blocklist", "domains", "Blocked domains", group="Lists", limit=200)
    _list("automod", "link_allowlist", "domains", "Allowed domains", "Once set, only these domains are permitted.", group="Lists", limit=200)
    _list("automod", "exempt_channels", "channels", "Exempt channels", group="Lists", limit=50)
    _list("automod", "exempt_roles", "roles", "Exempt roles", group="Lists", limit=50)
    _float("automod", "mute_threshold", config.AUTOMOD_HEAT_MUTE_THRESHOLD, 3, 200, "Heat that triggers a punishment", group="Heat")
    _float("automod", "panic_threshold", config.AUTOMOD_HEAT_PANIC_THRESHOLD, 5, 500, "Heat that triggers the severe action", group="Heat")
    _float("automod", "decay", config.AUTOMOD_HEAT_DECAY_PER_SECOND, 0.1, 20, "Heat lost per second", group="Heat")
    _choice("automod", "mute_action", "timeout", HEAT_ACTIONS, "First strike action", group="Heat")
    _choice("automod", "panic_action", "quarantine", HEAT_ACTIONS, "Severe action", group="Heat")
    _duration("automod", "base_mute", config.AUTOMOD_BASE_MUTE_SECONDS, 10, 2419200, "Base timeout length", group="Heat")
    _int("automod", "max_multiplier", 10, 1, 50, "Maximum timeout multiplier", group="Heat")
    _duration("automod", "multiplier_reset", config.AUTOMOD_MUTE_MULTIPLIER_RESET_SECONDS, 60, 604800, "Multiplier reset time", group="Heat")
    _bool("automod", "reset_heat_on_punish", True, "Reset heat after a punishment", group="Heat")
    _float("automod", "raid_heat_factor", config.AUTOMOD_RAID_HEAT_FACTOR, 1.0, 5.0, "Heat factor during raid mode", group="Heat")
    _float("automod", "unverified_heat_factor", 1.5, 1.0, 5.0, "Heat factor for unverified members", group="Heat")
    _bool("automod", "warn_ladder_enabled", False, "Warning ladder", "Escalate members who collect warnings: timeout, then kick, then ban.", group="Warnings")
    _duration("automod", "warn_window", 2592000, 3600, 31536000, "Warnings count for", "Older warnings stop counting toward the ladder.", group="Warnings")
    _int("automod", "warn_timeout_at", 3, 0, 50, "Timeout at warnings", "0 turns this step off.", group="Warnings")
    _duration("automod", "warn_timeout_duration", 3600, 60, 2419200, "Ladder timeout length", group="Warnings")
    _int("automod", "warn_kick_at", 5, 0, 50, "Kick at warnings", "0 turns this step off.", group="Warnings")
    _int("automod", "warn_ban_at", 7, 0, 50, "Ban at warnings", "0 turns this step off.", group="Warnings")
    _bool("automod", "warn_on_punish", False, "AutoMod punishments add a warning", group="Warnings")
    _bool("automod", "webhook_protection", False, "Webhook message protection", "Delete webhook posts that ping everyone, carry invites or mass-mention.", group="Webhooks")
    _bool("automod", "webhook_delete", False, "Delete abusive webhooks", "Also delete the webhook itself. Needs Manage Webhooks.", group="Webhooks")
    _bool("automod", "burst_lockdown", False, "Mass-mention burst lockdown", "Lock the server when many mass-mention messages land at once.", group="Webhooks")
    _int("automod", "burst_count", 5, 2, 50, "Mass-mention messages", group="Webhooks")
    _duration("automod", "burst_window", 30, 5, 600, "Burst window", group="Webhooks")
    _bool("automod", "delete_flagged", True, "Delete flagged messages", group="Responses")
    _bool("automod", "notify", True, "Tell the member why", group="Responses")
    _duration("automod", "notify_delete_after", 6, 2, 120, "Notice lifetime", group="Responses")
    _bool("automod", "purge_on_punish", True, "Remove the member's recent messages", group="Responses")
    for event, weight in config.AUTOMOD_HEAT_EVENTS.items():
        _float("automod", f"weight_{event}", weight, 0, 100, f"Heat: {event.replace('_', ' ')}", group="Heat weights")

    _add(Setting("verification", "level", "enum", 0, "Verification type", "How members prove they are real.",
                 choices=VERIFY_LEVEL_NAMES, group="Verification", mapping=tuple(config.VERIFICATION_LEVELS.items())))
    _role("verification", "role_id", "Verified role", group="Verification")
    _role("verification", "gate_role_id", "Gate role", group="Verification")
    _channel("verification", "channel_id", "Verification channel", group="Verification")
    _int("verification", "max_attempts", config.VERIFICATION_MAX_ATTEMPTS_DEFAULT, 1, 10, "Wrong codes allowed", group="Challenge")
    _duration("verification", "lockout_seconds", config.VERIFICATION_LOCKOUT_SECONDS, 30, 86400, "Lockout length", group="Challenge")
    _duration("verification", "click_cooldown", config.VERIFICATION_CLICK_COOLDOWN_SECONDS, 1, 300, "Button cooldown", group="Challenge")
    _int("verification", "captcha_length", config.VERIFICATION_CAPTCHA_LENGTH, 4, 8, "Captcha length", group="Challenge")
    _duration("verification", "captcha_lifetime", 180, 30, 3600, "Captcha lifetime", group="Challenge")
    _int("verification", "min_account_age_hours", 0, 0, 720, "Minimum account age (hours)", group="Requirements")
    _choice("verification", "target", "all", ("all", "suspicious"), "Who must verify", "Everyone, or only suspicious accounts.", group="Requirements")
    _int("verification", "fail_lockouts", 0, 0, 10, "Lockouts before the fail action", "0 turns the fail action off.", group="Failure")
    _choice("verification", "fail_action", "kick", GATE_ACTIONS[1:], "Fail action", group="Failure")
    _bool("verification", "pending_timeout_enabled", config.VERIFICATION_PENDING_TIMEOUT_ENABLED_DEFAULT, "Remove members who never verify", group="Failure")
    _int("verification", "pending_timeout_minutes", config.VERIFICATION_PENDING_TIMEOUT_MINUTES_DEFAULT, 5, 10080, "Minutes before removal", group="Failure")
    _choice("verification", "pending_timeout_action", config.VERIFICATION_PENDING_TIMEOUT_ACTION_DEFAULT, ("kick", "ban"), "Removal action", group="Failure")
    _bool("verification", "log_attempts", True, "Log verification attempts", group="Failure")


_build()


def all_settings() -> list[Setting]:
    return list(_REGISTRY.values())


def module_settings(module: str) -> list[Setting]:
    return [s for s in _REGISTRY.values() if s.module == module]


def find(module: str, key: str) -> Optional[Setting]:
    return _REGISTRY.get(f"{module.lower()}.{key.lower()}")


def parse_duration(raw: str) -> int:
    text = raw.strip().lower().replace(" ", "")
    if text.isdigit():
        return int(text)
    matches = re.findall(r"(\d+)([smhdw])", text)
    if not matches or "".join(f"{n}{u}" for n, u in matches) != text:
        raise ValueError("Use a duration such as `30s`, `10m`, `2h` or `1d`.")
    return sum(int(n) * DURATION_UNITS[u] for n, u in matches)


def parse_scalar(setting: Setting, raw: Any) -> Any:
    label = setting.label
    if setting.kind == "bool":
        if isinstance(raw, bool):
            return raw
        word = str(raw).strip().lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
        raise ValueError(f"{label} must be `on` or `off`.")
    if setting.kind == "int":
        try:
            number = int(str(raw).strip())
        except ValueError:
            raise ValueError(f"{label} must be a whole number.")
    elif setting.kind == "float":
        try:
            number = float(str(raw).strip())
        except ValueError:
            raise ValueError(f"{label} must be a number.")
    elif setting.kind == "duration":
        number = parse_duration(str(raw)) if not isinstance(raw, (int, float)) else int(raw)
    elif setting.kind == "enum":
        lookup = dict(setting.mapping)
        if isinstance(raw, int) and raw in lookup.values():
            return raw
        word = str(raw).strip().lower()
        if word not in lookup:
            raise ValueError(f"{label} must be one of: {', '.join(lookup)}.")
        return lookup[word]
    elif setting.kind == "choice":
        word = str(raw).strip().lower()
        if word not in setting.choices:
            raise ValueError(f"{label} must be one of: {', '.join(setting.choices)}.")
        return word
    else:
        raise ValueError(f"{label} cannot be set this way.")
    if setting.lo is not None and number < setting.lo or setting.hi is not None and number > setting.hi:
        low = format_duration(int(setting.lo)) if setting.kind == "duration" else setting.lo
        high = format_duration(int(setting.hi)) if setting.kind == "duration" else setting.hi
        raise ValueError(f"{label} must be between {low} and {high}.")
    return number


def display(setting: Setting, value: Any) -> str:
    if value is None:
        return "not set"
    if setting.kind == "bool":
        return "on" if value else "off"
    if setting.kind == "enum":
        return next((name for name, stored in setting.mapping if stored == value), str(value))
    if setting.kind == "duration":
        return format_duration(int(value))
    if setting.kind == "role":
        return f"<@&{value}>"
    if setting.kind == "channel":
        return f"<#{value}>"
    if setting.kind in ("words", "domains"):
        return f"{len(value)} entr{'y' if len(value) == 1 else 'ies'}"
    if setting.kind == "roles":
        return " ".join(f"<@&{v}>" for v in value) or "none"
    if setting.kind == "channels":
        return " ".join(f"<#{v}>" for v in value) or "none"
    return str(value)


async def get(guild_id: int, module: str, key: str) -> Any:
    setting = _REGISTRY[f"{module}.{key}"]
    return await guild_settings.get(guild_id, setting.store, setting.default)


async def put(guild_id: int, setting: Setting, value: Any) -> None:
    if value is None:
        await guild_settings.delete(guild_id, setting.store)
    else:
        await guild_settings.set(guild_id, setting.store, value)


async def reset(guild_id: int, setting: Setting) -> None:
    await guild_settings.delete(guild_id, setting.store)


async def snapshot(guild_id: int, module: Optional[str] = None) -> dict[str, Any]:
    out = {}
    for setting in all_settings():
        if module and setting.module != module:
            continue
        out[setting.path] = await guild_settings.get(guild_id, setting.store, setting.default)
    return out


async def export_json(guild_id: int) -> str:
    changed = {}
    for setting in all_settings():
        value = await guild_settings.get(guild_id, setting.store, setting.default)
        if value != setting.default:
            changed[setting.path] = value
    return json.dumps({"version": 1, "settings": changed}, indent=2, sort_keys=True)


def validate_import(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("settings"), dict):
        raise ValueError("That file is not a Soward security export.")
    clean = {}
    for path, value in payload["settings"].items():
        setting = _REGISTRY.get(path)
        if setting is None:
            continue
        if setting.kind in ("words", "domains", "roles", "channels"):
            if not isinstance(value, list) or len(value) > int(setting.hi or 100):
                raise ValueError(f"{setting.label} has an invalid list.")
            clean[path] = [int(v) if setting.kind in ("roles", "channels") else str(v)[:100] for v in value]
        elif setting.kind in ("role", "channel"):
            clean[path] = int(value) if value else None
        else:
            clean[path] = parse_scalar(setting, value)
    return clean


PRESETS: dict[str, dict[str, Any]] = {
    "relaxed": {
        "antinuke.enabled": True, "antinuke.strict_mode": False, "antinuke.admin_bypass": True, "antinuke.window": 20,
        "antinuke.threshold_ban": 8, "antinuke.threshold_kick": 8, "antinuke.threshold_channel_delete": 5, "antinuke.threshold_role_delete": 5,
        "antiraid.enabled": True, "antiraid.join_velocity_count": 15, "antiraid.min_age_seconds": 86400, "antiraid.gate_noavatar_enabled": False,
        "antiraid.raid_mode_action": "timeout", "antiraid.join_action": "timeout",
        "automod.enabled": True, "automod.mute_threshold": 14, "automod.panic_threshold": 45,
        "verification.max_attempts": 5,
    },
    "balanced": {
        "antinuke.enabled": True, "antinuke.strict_mode": False, "antinuke.admin_bypass": False, "antinuke.window": 10,
        "antinuke.threshold_ban": 5, "antinuke.threshold_kick": 5, "antinuke.threshold_channel_delete": 3, "antinuke.threshold_role_delete": 3,
        "antinuke.restore": True, "antinuke.bot_add_block": True, "antinuke.quarantine_hold": True,
        "antiraid.enabled": True, "antiraid.join_velocity_count": 10, "antiraid.min_age_seconds": 7 * 86400, "antiraid.gate_noavatar_enabled": True,
        "antiraid.raid_mode_action": "kick", "antiraid.join_action": "kick", "antiraid.sweep": True,
        "automod.enabled": True, "automod.mute_threshold": 10, "automod.panic_threshold": 30, "automod.filter_scamlinks": True,
        "verification.max_attempts": 3,
    },
    "strict": {
        "antinuke.enabled": True, "antinuke.strict_mode": True, "antinuke.admin_bypass": False, "antinuke.window": 10,
        "antinuke.threshold_ban": 3, "antinuke.threshold_kick": 3, "antinuke.threshold_channel_delete": 2, "antinuke.threshold_role_delete": 2,
        "antinuke.threshold_channel_create": 3, "antinuke.threshold_role_create": 3, "antinuke.threshold_webhook_create": 1,
        "antinuke.restore": True, "antinuke.bot_add_block": True, "antinuke.quarantine_hold": True, "antinuke.monitor_overwrites": True,
        "antiraid.enabled": True, "antiraid.join_velocity_count": 7, "antiraid.min_age_seconds": 14 * 86400, "antiraid.gate_noavatar_enabled": True,
        "antiraid.raid_mode_action": "ban", "antiraid.join_action": "kick", "antiraid.sweep": True, "antiraid.gate_name_enabled": True,
        "antiraid.gate_suspicious_enabled": True, "antiraid.gate_unverified_bots": True, "antiraid.raise_verification": True,
        "antiraid.gate_impersonation_enabled": True, "antiraid.invite_tracking": True, "automod.webhook_protection": True,
        "automod.enabled": True, "automod.mute_threshold": 8, "automod.panic_threshold": 24, "automod.block_invites": True, "automod.mention_limit": 4,
        "verification.max_attempts": 3, "verification.min_account_age_hours": 24, "verification.fail_lockouts": 2,
        "security.threat_score": True, "security.lock": True,
    },
    "paranoid": {
        "antinuke.enabled": True, "antinuke.strict_mode": True, "antinuke.admin_bypass": False, "antinuke.window": 15,
        "antinuke.threshold_ban": 2, "antinuke.threshold_kick": 2, "antinuke.threshold_channel_delete": 1, "antinuke.threshold_role_delete": 1,
        "antinuke.threshold_channel_create": 2, "antinuke.threshold_role_create": 2, "antinuke.threshold_webhook_create": 1,
        "antinuke.threshold_emoji_change": 3, "antinuke.threshold_sticker_change": 3, "antinuke.threshold_channel_update": 3, "antinuke.threshold_role_update": 2,
        "antinuke.punishment": "ban", "antinuke.restore": True, "antinuke.bot_add_block": True, "antinuke.quarantine_hold": True,
        "antinuke.monitor_overwrites": True, "antinuke.protect_everyone": True, "antinuke.restore_from_backup": True,
        "antiraid.gate_impersonation_enabled": True, "antiraid.gate_evasion_enabled": True, "antiraid.invite_tracking": True, "antiraid.revoke_invites": True,
        "automod.webhook_protection": True, "automod.burst_lockdown": True, "automod.warn_ladder_enabled": True,
        "antiraid.enabled": True, "antiraid.join_velocity_count": 5, "antiraid.join_velocity_window": 10, "antiraid.min_age_seconds": 30 * 86400,
        "antiraid.gate_noavatar_enabled": True, "antiraid.raid_mode_action": "ban", "antiraid.join_action": "ban", "antiraid.sweep": True,
        "antiraid.gate_name_enabled": True, "antiraid.gate_suspicious_enabled": True, "antiraid.gate_unverified_bots": True,
        "antiraid.raise_verification": True, "antiraid.action_dm": False,
        "automod.enabled": True, "automod.mute_threshold": 6, "automod.panic_threshold": 18, "automod.block_invites": True, "automod.mention_limit": 3,
        "verification.max_attempts": 2, "verification.min_account_age_hours": 72, "verification.fail_lockouts": 1, "verification.level": "captcha",
        "security.threat_score": True, "security.lock": True, "security.auto_backup": True, "security.lockdown_on_nuke": True,
    },
}


async def apply_preset(guild_id: int, name: str) -> list[str]:
    values = PRESETS[name]
    changed = []
    for path, value in values.items():
        setting = _REGISTRY[path]
        if setting.kind == "enum":
            value = parse_scalar(setting, value)
        current = await guild_settings.get(guild_id, setting.store, setting.default)
        if current == value:
            continue
        await put(guild_id, setting, value)
        changed.append(f"{setting.label}: {display(setting, value)}")
    return changed
