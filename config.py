import json
import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "devs.json", "r") as _f:
    _devs_data = json.load(_f)

def _load_addons() -> dict:
    try:
        import addons
    except ImportError:
        return {}
    except Exception:
        logging.getLogger("soward.config").error("addons.py could not be loaded, using defaults.", exc_info=True)
        return {}
    return {k: v for k, v in vars(addons).items() if not k.startswith("_") and isinstance(v, dict)}


ADDONS: dict = _load_addons()
_DASH_ADDON: dict = ADDONS.get("dash") if isinstance(ADDONS.get("dash"), dict) else {}


def _addon_port(value, fallback: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return fallback
    return port if 1 <= port <= 65535 else fallback


BOT_TOKEN: str = os.getenv("SOWARD_TOKEN", "")
MONGODB_URI: str = os.getenv("SOWARD_MONGO_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME: str = os.getenv("SOWARD_MONGO_DB", "soward")
DATA_DIR: Path = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SQLITE_PATH: str = str(DATA_DIR / "soward.db")

DEFAULT_PREFIX: str = "!"
BOT_NAME: str = "Soward"
BOT_VERSION: str = "3.1"
DEVELOPER_USER_ID: int = 1181137505505001544

OWNER_IDS: list[int] = _devs_data.get("owner_ids", [DEVELOPER_USER_ID])
DEV_IDS: list[int] = _devs_data.get("dev_ids", [DEVELOPER_USER_ID])
DEV_ROLE_IDS: list[int] = _devs_data.get("dev_role_ids", [])

ALL_PRIVILEGED_IDS: list[int] = list(set(OWNER_IDS + DEV_IDS))

MONGO_RECONNECT_INTERVAL: int = 30
MONGO_SYNC_INTERVAL: int = 300

DEV_LOG_COMMANDS_WEBHOOK_URL: str = os.getenv("SOWARD_DEV_LOG_COMMANDS_WEBHOOK", "")
DEV_LOG_LIFECYCLE_WEBHOOK_URL: str = os.getenv("SOWARD_DEV_LOG_LIFECYCLE_WEBHOOK", "")
DEV_LOG_ERRORS_WEBHOOK_URL: str = os.getenv("SOWARD_DEV_LOG_ERRORS_WEBHOOK", "")
DEV_LOG_GUILDS_WEBHOOK_URL: str = os.getenv("SOWARD_DEV_LOG_GUILDS_WEBHOOK", "")
DEV_STATS_WEBHOOK_URL: str = os.getenv("SOWARD_DEV_STATS_WEBHOOK", "")
DEV_STATS_UPDATE_INTERVAL: int = 300

YOUTUBE_API_KEY: str = os.getenv("SOWARD_YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID: str = os.getenv("SOWARD_TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET: str = os.getenv("SOWARD_TWITCH_CLIENT_SECRET", "")

ALERT_POLL_INTERVAL: int = 120
ALERT_YOUTUBE_FALLBACK_INTERVAL: int = 900
ALERT_UPCOMING_CHECK_INTERVAL: int = 60
ALERT_UPCOMING_MAX_AGE: int = 259200
ALERT_UPLOAD_MAX_AGE: int = 43200
WEBSUB_HUB_URL: str = "https://pubsubhubbub.appspot.com/subscribe"
WEBSUB_LEASE_SECONDS: int = 864000
WEBSUB_RENEW_BEFORE_SECONDS: int = 172800
WEBSUB_RENEW_INTERVAL: int = 1800
WEBSUB_PENDING_RETRY_SECONDS: int = 900
WEBSUB_MAX_BODY_BYTES: int = 65536
WEBSUB_ENABLED_FLAG: bool = os.getenv("SOWARD_WEBSUB", "1") not in ("0", "false", "no")
WEBSUB_SECRET: str = os.getenv("SOWARD_WEBSUB_SECRET", "") or os.getenv("SOWARD_IPC_SECRET", "")

EMBED_TEMPLATE_MAX_FREE: int = 100
EMBED_TEMPLATE_MAX_PREMIUM: int = 250
COMMAND_COOLDOWN: int = 3

PREMIUM_DURATION_PRESETS: dict = {
    "3d": 3, "6d": 6, "1w": 7, "2w": 14,
    "1m": 30, "33d": 33, "60d": 60,
    "2mo": 60, "3mo": 90, "6mo": 180, "1y": 365,
}

SERVER_NO_PREFIX_ENABLED_DEFAULT: bool = True
NP_TARGETS_MAX: int = 50

CRYPTO_PLANS: dict = {
    "1m": {"label": "1 month", "days": 30, "usd": 3.0},
    "3m": {"label": "3 months", "days": 90, "usd": 8.0},
    "1y": {"label": "1 year", "days": 365, "usd": 20.0},
}
CRYPTO_LEGACY_PLANS: dict = {
    "lifetime": {"label": "Lifetime", "days": None, "usd": 25.0},
}
CRYPTO_COINS: dict = {"btc": "Bitcoin", "ltc": "Litecoin"}
CRYPTO_INVOICE_MINUTES: int = 30
CRYPTO_GRACE_HOURS: int = 24
CRYPTO_POLL_SECONDS: int = 45
CRYPTO_CONFIRMATIONS: dict = {"btc": 1, "ltc": 1}
CRYPTO_UNDERPAY_TOLERANCE: float = 0.01
CRYPTO_MAX_OPEN_PER_USER: int = 2
BLOCKCYPHER_TOKEN: str = os.getenv("SOWARD_BLOCKCYPHER_TOKEN", "")
CRYPTO_MIN_AGREE: int = 2
CRYPTO_GRACE_POLL_SECONDS: int = 600
CRYPTO_PROVIDERS: dict = {
    "btc": [("esplora", "https://mempool.space/api"), ("esplora", "https://blockstream.info/api"), ("blockchair", "https://api.blockchair.com/bitcoin")],
    "ltc": [("esplora", "https://litecoinspace.org/api"), ("blockchair", "https://api.blockchair.com/litecoin"), ("blockcypher", "https://api.blockcypher.com/v1/ltc/main")],
}

XP_PER_MESSAGE_MIN: int = 5
XP_PER_MESSAGE_MAX: int = 15
XP_COOLDOWN_SECONDS: int = 60
LEVEL_XP_FORMULA_BASE: int = 100
LEVEL_XP_FORMULA_MULTIPLIER: float = 1.5

DAILY_CURRENCY_MIN: int = 100
DAILY_CURRENCY_MAX: int = 500

ANTINUKE_DEFAULT_THRESHOLDS: dict = {
    "channel_delete": 3,
    "channel_create": 5,
    "channel_update": 5,
    "role_delete": 3,
    "role_create": 5,
    "role_update": 3,
    "ban": 5,
    "kick": 5,
    "prune": 1,
    "webhook_create": 3,
    "webhook_delete": 3,
    "emoji_change": 5,
    "sticker_change": 5,
    "bot_add": 1,
    "permission_escalation": 2,
    "guild_update": 2,
    "integration_change": 2,
    "timeout": 10,
}

ANTINUKE_THRESHOLD_WINDOW_SECONDS: int = 10

ANTINUKE_DEFAULT_PUNISHMENT: str = "quarantine"

ANTINUKE_STRICT_MODE_DEFAULT: bool = False
ANTINUKE_DANGEROUS_PERMISSIONS: list[str] = [
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
    "ban_members",
    "kick_members",
]

ANTINUKE_WATCH_QUARANTINED_DEFAULT: bool = True
ANTINUKE_ADMIN_BYPASS_DEFAULT: bool = False
ANTINUKE_RESTORE_DEFAULT: bool = True
ANTINUKE_BOT_ADD_BLOCK_DEFAULT: bool = True
ANTINUKE_ALERT_OWNER_DEFAULT: bool = True
ANTINUKE_AUDIT_MAX_AGE_SECONDS: int = 20
ANTINUKE_PUNISH_COOLDOWN_SECONDS: int = 30
ANTINUKE_ROLLBACK_WINDOW_SECONDS: int = 120
QUARANTINE_TIMEOUT_SECONDS: int = 2419200

VERIFICATION_LEVELS: dict = {
    "none": 0,
    "reaction": 1,
    "button": 2,
    "captcha": 3,
    "manual": 4,
    "web": 5,
}

WEB_VERIFY_TOKEN_TTL_SECONDS: int = 900
WEB_VERIFY_PROVIDER: str = os.getenv("SOWARD_IPINTEL_PROVIDER", "none").lower()
WEB_VERIFY_PROVIDER_KEY: str = os.getenv("SOWARD_IPINTEL_KEY", "")
WEB_VERIFY_SALT: str = os.getenv("SOWARD_IP_SALT", "")
WEB_VERIFY_TURNSTILE_SITE: str = os.getenv("SOWARD_TURNSTILE_SITE_KEY", "")
WEB_VERIFY_TURNSTILE_SECRET: str = os.getenv("SOWARD_TURNSTILE_SECRET", "")
WEB_VERIFY_BEHIND_PROXY: bool = os.getenv("SOWARD_BEHIND_PROXY", "") in ("1", "true", "yes")

VERIFICATION_MAX_ATTEMPTS_DEFAULT: int = 3
VERIFICATION_LOCKOUT_SECONDS: int = 300
VERIFICATION_CLICK_COOLDOWN_SECONDS: int = 5
VERIFICATION_CAPTCHA_LENGTH: int = 6
VERIFICATION_PENDING_TIMEOUT_ENABLED_DEFAULT: bool = False
VERIFICATION_PENDING_TIMEOUT_MINUTES_DEFAULT: int = 30
VERIFICATION_PENDING_TIMEOUT_ACTION_DEFAULT: str = "kick"

INCIDENT_STATES: dict = {
    "normal": 0,
    "elevated": 1,
    "lockdown": 2,
}

ANTIRAID_ENABLED_DEFAULT: bool = False
ANTIRAID_JOIN_VELOCITY_COUNT: int = 10
ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS: int = 10
ANTIRAID_MIN_ACCOUNT_AGE_SECONDS: int = 7 * 86400
ANTIRAID_FLAG_NO_AVATAR: bool = True
ANTIRAID_JOIN_ACTION: str = "kick"
ANTIRAID_RAID_MODE_DURATION_SECONDS: int = 600
ANTIRAID_RAID_MODE_ACTION: str = "kick"
ANTIRAID_SWEEP_DEFAULT: bool = True
ANTIRAID_RAISE_VERIFICATION_DEFAULT: bool = True
ANTIRAID_FOLLOW_ANTINUKE_DEFAULT: bool = True
ANTIRAID_LOG_RETENTION_SECONDS: int = 30 * 86400

AUTOMOD_HEAT_DECAY_PER_SECOND: float = 1.0
AUTOMOD_HEAT_MUTE_THRESHOLD: float = 10.0
AUTOMOD_HEAT_PANIC_THRESHOLD: float = 30.0
AUTOMOD_HEAT_EVENTS: dict = {
    "message": 2.0,
    "mention": 1.5,
    "link": 2.0,
    "invite": 4.0,
    "banned_word": 5.0,
    "duplicate_message": 3.0,
}
AUTOMOD_HEAT_EVENTS.update({
    "everyone": 4.0,
    "phishing": 12.0,
    "iplogger": 12.0,
    "caps": 1.5,
    "zalgo": 3.0,
    "attachments": 2.0,
    "emoji": 1.5,
    "wall": 1.0,
})
AUTOMOD_BASE_MUTE_SECONDS: int = 300
AUTOMOD_RAID_HEAT_FACTOR: float = 1.5
AUTOMOD_DUPLICATE_WINDOW_SECONDS: int = 30
AUTOMOD_DUPLICATE_SIMILARITY: float = 0.9
AUTOMOD_CAPS_MIN_LENGTH: int = 15
AUTOMOD_CAPS_RATIO: float = 0.7
AUTOMOD_ATTACHMENT_LIMIT: int = 6
AUTOMOD_MENTION_LIMIT: int = 5
AUTOMOD_STALE_SECONDS: int = 3600
AUTOMOD_MUTE_MULTIPLIER_RESET_SECONDS: int = 3600

PANIC_MODE_RAIDER_COUNT: int = 3
PANIC_MODE_WINDOW_SECONDS: int = 60
PANIC_MODE_DURATION_SECONDS: int = 600
PANIC_MODE_ACTION: str = "timeout"

ANTINUKE_PER_ACTION_PUNISHMENT_DEFAULT: dict = {
    "channel_delete": "quarantine",
    "channel_create": "quarantine",
    "role_delete": "quarantine",
    "role_create": "quarantine",
    "ban": "quarantine",
    "kick": "quarantine",
    "timeout": "quarantine",
    "webhook_create": "quarantine",
    "permission_grant": "quarantine",
    "bot_add": "kick_bot",
    "prune": "quarantine",
}

QUARANTINE_ESCALATION_ENABLED_DEFAULT: bool = True
QUARANTINE_ESCALATION_WINDOW_SECONDS: int = 86400

SECURITY_TIER_EXTRA_OWNER: str = "extra_owner"
SECURITY_TIER_TRUSTED_ADMIN: str = "trusted_admin"
SECURITY_TIER_MAX_PER_TIER: int = 5
SECURITY_LOCK_DEFAULT: bool = True

LOG_EVENTS: list[str] = [
    "ban",
    "softban",
    "unban",
    "kick",
    "mute",
    "unmute",
    "warn",
    "purge",
    "lockdown",
    "unlock",
    "slowmode",
    "message_edit",
    "message_delete",
    "message_bulk_delete",
    "member_join",
    "member_leave",
    "member_update",
    "role_change",
    "role_create",
    "role_delete",
    "channel_change",
    "channel_create",
    "channel_delete",
    "voice_state_update",
    "automod_action",
    "antinuke_action",
    "antinuke_triggered",
    "antinuke_quarantine",
    "antinuke_quarantine_release",
    "antiraid_action",
    "antiraid_raid_mode",
    "verification_action",
    "beast_mode",
    "server_lockdown",
    "security_backup",
    "security_whitelist",
    "security_change",
    "autorole_action",
    "nsfw_action",
    "ticket_action",
    "warn_ladder",
    "role_add",
    "role_remove",
    "fakeperm_grant",
    "fakeperm_revoke",
    "support_access_granted",
    "support_access_revoked",
]

LOG_CATEGORY_NAME: str = "soward-logs"

LOG_CATEGORIES: dict[str, dict] = {
    "mod": {
        "label": "Moderation",
        "channel_name": "mod-logs",
        "events": ["ban", "softban", "unban", "kick", "mute", "unmute", "warn", "warn_ladder", "purge", "lockdown", "unlock", "slowmode", "role_add", "role_remove"],
    },
    "security": {
        "label": "Security",
        "channel_name": "security-logs",
        "events": [
            "automod_action",
            "antinuke_action",
            "antinuke_triggered",
            "antinuke_quarantine",
            "antinuke_quarantine_release",
            "antiraid_action",
            "antiraid_raid_mode",
            "verification_action",
            "beast_mode",
            "server_lockdown",
            "security_backup",
            "security_whitelist",
            "security_change",
            "fakeperm_grant",
            "fakeperm_revoke",
            "support_access_granted",
            "support_access_revoked",
        ],
    },
    "member": {
        "label": "Member Activity",
        "channel_name": "member-logs",
        "events": ["member_join", "member_leave", "member_update", "autorole_action", "voice_state_update"],
    },
    "message": {
        "label": "Messages",
        "channel_name": "message-logs",
        "events": ["message_edit", "message_delete", "message_bulk_delete"],
    },
    "server": {
        "label": "Server Changes",
        "channel_name": "server-logs",
        "events": ["role_change", "role_create", "role_delete", "channel_change", "channel_create", "channel_delete", "nsfw_action", "ticket_action"],
    },
}

MUSIC_INACTIVITY_TIMEOUT: int = 300
MUSIC_MAX_QUEUE_SIZE: int = 200

LAVALINK_HOST: str = os.getenv("SOWARD_LAVALINK_HOST", "127.0.0.1")
LAVALINK_PORT: int = int(os.getenv("SOWARD_LAVALINK_PORT", "2333"))
LAVALINK_PASSWORD: str = os.getenv("SOWARD_LAVALINK_PASSWORD", "youshallnotpass")
LAVALINK_SECURE: bool = os.getenv("SOWARD_LAVALINK_SECURE", "false").lower() == "true"

def _parse_lavalink_nodes() -> list[dict]:
    import json as _json
    raw = os.getenv("SOWARD_LAVALINK_NODES")
    if raw:
        try:
            return _json.loads(raw)
        except Exception:
            pass
    return [
        {
            "host": LAVALINK_HOST,
            "port": LAVALINK_PORT,
            "password": LAVALINK_PASSWORD,
            "secure": LAVALINK_SECURE,
            "identifier": "SOWARD-MAIN",
        }
    ]

LAVALINK_NODES: list[dict] = _parse_lavalink_nodes()

SPOTIFY_SEARCH_CONFIGURED: bool = os.getenv("SOWARD_SPOTIFY_CLIENT_ID", "") != "" and os.getenv("SOWARD_SPOTIFY_CLIENT_SECRET", "") != ""

TICKET_TRANSCRIPT_FORMAT: str = "html"
TICKET_MAX_OPEN_LIMIT: int = 25
TICKET_TRANSCRIPT_MESSAGE_LIMIT: int = 1500
TICKET_AUTOCLOSE_CHECK_MINUTES: int = 10
TICKET_PRIORITIES: tuple = ("low", "normal", "high", "urgent")
GIVEAWAY_CHECK_INTERVAL: int = 10

HELP_HIDDEN_COMMANDS: set[str] = {
    "premium generate",
    "premium keys",
    "premium revoke",
    "globalnp",
    "crypto",
    "coins grant",
}

HELP_HIDDEN_CATEGORIES: set[str] = {
    "GlobalNoPrefix",
    "Dev",
    "Jishaku",
}

LOFI_STREAM_URL: str = "https://www.youtube.com/watch?v=jfKfPfyJRdk"
AUTOPLAY_RELATED_SEARCH_SUFFIX: str = "official audio"

AFK_MAX_AUTO_RETURN_MINUTES: int = 1440
AFK_MENTION_LOG_LIMIT: int = 15
AFK_NICK_PREFIX: str = "[AFK] "

GREETING_TRIGGER_TYPES: tuple = ("join", "leave", "boost", "ban")
GREETING_CARD_LAYOUTS: tuple = ("classic", "left", "right", "banner")
GREETING_DEFAULT_CARD_LAYOUT: str = "classic"
GREETING_MAX_JOIN_ROLE_DELAY_SECONDS: int = 3600
BOOST_LEVEL_THRESHOLDS: dict = {1: 2, 2: 7, 3: 14}


TICKET_LIMITS: dict = {
    "free": {"panels": 3, "staff_roles": 10, "categories": 5, "questions": 5, "active": 25},
    "premium": {"panels": 10, "staff_roles": 20, "categories": 10, "questions": 10, "active": 250},
}
TICKET_MODAL_PAGE_SIZE: int = 5
PREMIUM_LIMITS: dict = {
    "custom_commands": (100, 250, "Custom commands"),
    "custom_command_groups": (20, 50, "Custom command groups"),
    "custom_command_responses": (10, 25, "Responses per custom command"),
    "embed_templates": (EMBED_TEMPLATE_MAX_FREE, EMBED_TEMPLATE_MAX_PREMIUM, "Embed templates"),
    "application_forms": (5, 25, "Application forms"),
    "application_questions": (25, 40, "Questions per application"),
    "jtc_hubs": (2, 10, "Join to Create hubs"),
    "alert_subscriptions": (5, 15, "YouTube and Twitch alerts (each)"),
    "server_templates": (5, 15, "Saved server templates"),
    "music_stations": (20, 60, "Custom radio stations"),
    "music_playlist_tracks": (200, 500, "Tracks loaded from a playlist"),
    "booster_tiers": (15, 30, "Booster tiers"),
    "nsfw_channels": (25, 50, "NSFW channels"),
    "automod_words": (200, 500, "AutoMod banned words"),
    "automod_domains": (200, 500, "AutoMod blocked and allowed domains (each)"),
    "automod_exempt": (50, 150, "AutoMod exempt channels and roles (each)"),
    "antiraid_patterns": (50, 150, "AntiRaid name patterns"),
}
JTC_MAX_ACTIVE_PER_GUILD: int = 150
JTC_CREATE_COOLDOWN: float = 6.0
JTC_DEFAULT_NAME: str = "{user}'s room"
JTC_CATEGORY_NAME: str = "Temporary Voice"
JTC_HUB_NAME: str = "Join to Create"
JTC_SWEEP_SECONDS: int = 300
BOOSTER_SWEEP_SECONDS: int = 900
BOOSTER_MAX_COUNT: int = 99
BOOSTER_ICON_MAX_BYTES: int = 262144
BOOSTER_ROLE_CAP: int = 245
BOOSTER_BACKFILL_LIMIT: int = 3000
BOOSTER_SAFE_PERMS: tuple = (
    "change_nickname", "embed_links", "attach_files", "use_external_emojis", "use_external_stickers", "add_reactions",
    "create_public_threads", "send_messages_in_threads", "stream", "use_voice_activation", "use_soundboard", "use_external_sounds",
)
BOOSTER_PRESET_TIERS: tuple = (
    (1, "Rich", 0xF1C40F), (2, "Wealthy", 0xF39C12),
)
TICKET_FORM_SESSION_TTL: int = 600
TICKET_CATEGORY_CHANNEL_CAP: int = 50
TICKET_LIST_LIMIT: int = 15

DASHBOARD_ENABLED_DEFAULT: bool = True
DASHBOARD_IPC_SOCKET: str = "data/soward-ipc.sock"
DASHBOARD_IPC_FALLBACK_PORT: int = 8765
DASHBOARD_SESSION_DAYS: int = 7
DASHBOARD_AUDIT_PAGE_SIZE: int = 25
DASHBOARD_LIST_LIMIT: int = 25
DASHBOARD_RESTART_DELAY_SECONDS: int = 5
DASHBOARD_URL: str = os.getenv("SOWARD_DASHBOARD_URL", "").rstrip("/")
WEBSUB_CALLBACK_URL: str = os.getenv("SOWARD_WEBSUB_CALLBACK", "") or (DASHBOARD_URL + "/websub/youtube" if DASHBOARD_URL else "")
DASHBOARD_ADDON_ENABLED: bool = bool(_DASH_ADDON.get("dashboard", True))
DASHBOARD_PORT: int = _addon_port(_DASH_ADDON.get("dashboard_port"), _addon_port(os.getenv("PORT"), 8080))


VAULT_RETENTION_DAYS = (7, 365)
VAULT_PAGE_SIZE = 10
VAULT_EXPORT_MAX = 20000
VAULT_DETAIL_MAX = 1500
SCHEDULE_MAX_ACTIONS = 25
SCHEDULE_MIN_REPEAT = 300
TICKET_CANNED_MAX = 25
TICKET_ARCHIVE_KEEP = 200
TICKET_ARCHIVE_MAX_BYTES = 4000000
DEEP_BACKUP_KEEP = 14
DEEP_BACKUP_MIN_HOURS = 6
DEEP_BACKUP_MAX_MANUAL = 10

def _flag(value, default: bool = True) -> bool:
    return default if value is None else bool(value)


_activities: dict = ADDONS.get("activities", {})
_lobby = _activities.get("game_lobby", _activities.get("game-lobby", {}))
if not isinstance(_lobby, dict):
    _lobby = {"enabled": bool(_lobby)}
_activities_on = _flag(_activities.get("enabled")) and os.getenv("SOWARD_ACTIVITY", "1") != "0"
ACTIVITY_MUSIC: bool = _activities_on and _flag(_activities.get("music"))
ACTIVITY_GAME_LIST: dict = {"chess": _activities_on and _flag(_lobby.get("enabled")) and _flag(_lobby.get("chess", _lobby.get("chess-enabled")))}
ACTIVITY_GAMES: bool = any(ACTIVITY_GAME_LIST.values())
ACTIVITY_ENABLED: bool = ACTIVITY_MUSIC or ACTIVITY_GAMES
SUPPORT_AMOUNTS: tuple = (1, 3, 5, 10, 25)
SUPPORT_MIN_USD = 1.0
SUPPORT_MAX_USD = 500.0
DIAMOND_PER_USD: int = 1000
DIAMOND_TO_COINS: int = 10
COIN_TOPUP_AMOUNTS: tuple = (1, 3, 5, 10, 25)
COIN_TOPUP_MIN_USD: float = 1.0
COIN_TOPUP_MAX_USD: float = 500.0
VOTE_COINS: dict = {"discordbotlist": 200}
SUPPORT_COINS: int = 5000
COIN_TRANSFER_MIN: int = 10
PREMIUM_COIN_PLAN: str = "1m"
PREMIUM_DIAMOND_PLANS: dict = {
    "1m": {"label": "1 month", "days": 30, "diamonds": 3000},
    "3m": {"label": "3 months", "days": 90, "diamonds": 8000},
    "1y": {"label": "1 year", "days": 365, "diamonds": 20000},
}
COIN_GIVE_MIN: int = 100
VOTE_DIAMONDS_MIN: int = 1
VOTE_DIAMONDS_MAX: int = 10
VOTE_DIAMONDS_COOLDOWN_HOURS: int = 24
DIAMOND_DROPS: dict = {
    "reward": (0.10, 1, 5),
    "work": (0.04, 1, 2),
    "gather": (0.06, 1, 2),
    "hunt": (0.08, 1, 3),
    "mine": (0.10, 1, 3),
    "ruins": (0.20, 2, 6),
}
PREMIUM_COIN_COOLDOWN_DAYS: int = 90
MARRIAGE_SLOTS_DEFAULT: int = 1
MARRIAGE_SLOTS_MAX: int = 3
MARRIAGE_SLOT_COST: int = 50000
ADOPT_SLOTS_DEFAULT: int = 5
ADOPT_SLOTS_MAX: int = 15
ADOPT_SLOT_COST: int = 10000
FAMILY_REQUEST_SECONDS: int = 120
CLAN_CREATE_COST: int = 20000
CLAN_BASE_MEMBERS: int = 10
CLAN_LEVEL_MEMBERS: int = 5
CLAN_MAX_LEVEL: int = 10
CLAN_UPGRADE_COST: int = 30000
CLAN_INVITE_HOURS: int = 24
PET_XP_PER_COMMAND: int = 2
PET_XP_COOLDOWN: int = 20
PET_DAILY_XP_CAP: int = 150
PET_LIMIT: int = 3
PET_NAME_MAX: int = 16
VOTER_BADGE_HOURS: int = 48
DEDICATED_VOTER_TOTAL: int = 25
REMINDER_LIMIT: int = 25
REMINDER_MIN_SECONDS: int = 30
REMINDER_MIN_REPEAT_SECONDS: int = 3600
REMINDER_MAX_DAYS: int = 730
REMINDER_TEXT_MAX: int = 500
REMINDER_CHECK_SECONDS: int = 20
TODO_LIMIT: int = 50
TODO_TEXT_MAX: int = 200
SUPPORT_URL: str = os.getenv("SOWARD_SUPPORT_URL", "").strip()
VOTE_DBL_SECRET: str = os.getenv("SOWARD_VOTE_DBL_SECRET", "").strip()
VOTE_DBL_TOKEN: str = os.getenv("SOWARD_DBL_TOKEN", "").strip()
VOTE_STATS_MINUTES = 30
VOTE_NP_HOURS: int = max(1, int(os.getenv("SOWARD_VOTE_NP_HOURS", "12") or 12))
VOTE_STREAK_WINDOW_HOURS = 36
SUPPORT_GUILD_ID: int = int(os.getenv("SOWARD_SUPPORT_GUILD", "0") or 0)
SUPPORTER_ROLE_ID: int = int(os.getenv("SOWARD_SUPPORTER_ROLE", "0") or 0)
_ads: dict = ADDONS.get("ads", {})
ADS_UNIT: str = str(_ads.get("aads_unit", "") or "").strip()
ADS_ENABLED: bool = bool(_ads.get("enabled", False)) and ADS_UNIT.isdigit()
ACTIVITY_MAX_LIKES = 1000
ACTIVITY_MAX_PLAYLISTS = 20
ACTIVITY_MAX_PLAYLIST_TRACKS = 300
ACTIVITY_HISTORY_KEEP = 200
ACTIVITY_SEARCH_RESULTS = 20
ACTIVITY_STREAM_TTL = 6 * 3600
ACTIVITY_RESOLVE_TTL = 1200
ACTIVITY_HOME_QUERIES = ("top hits official audio", "new music this week", "trending songs", "chill songs", "bollywood hits", "lofi beats")

SLASH_LAYOUT: dict = {
    "interact": {"description": "Hug, kiss, pat and other actions", "entries": ["Social"]},
    "fun": {"description": "Games, ship, anime and more", "entries": [["games", "Games"], "Ship", ["anime", "Anime"], ["icebreakers", "Icebreakers"], ["truth-or-dare", "TruthOrDare"], ["quote", "Quote"], "Wordle", "Matchmaking"]},
    "utility": {"description": "Info, reminders, to-do and other tools", "entries": ["Utility", "Lookups", "AFK", "Reminders", "Todo", "Votes"]},
    "levels": {"description": "Your rank and the leaderboard", "entries": ["Leveling"]},
    "eco": {"description": "Coins, diamonds, jobs and ways to earn", "entries": ["Earn", "Economy"]},
    "autopartner": {"description": "Automatic server partnerships", "flatten": "autopartner"},
    "family": {"description": "Marriage, adoption and family", "entries": ["Family"]},
    "clan": {"description": "Global clans", "flatten": "clan"},
    "profile": {"description": "Your global profile card", "flatten": "profile"},
    "pet": {"description": "Your pets and their outfits", "flatten": "pet"},
    "community": {"description": "Birthdays, confessions and suggestions", "entries": ["Birthdays", "Confessions", "Suggestions"]},
}
SLASH_EXCLUDE: set[str] = {"leveling", "suggestions", "tod", "familysize"}
SLASH_RENAMES: dict[str, str] = {"tictactoe": "tic-tac-toe", "connect4": "connect-4", "truthordare": "truth-or-dare"}
SLASH_BARE_NAMES: dict[str, str] = {"remind": "set", "todo": "list", "coins": "balance", "birthday": "view", "clan": "info", "games": "list", "autopartner": "status"}
SLASH_GROUP_LIMIT: int = 25
SLASH_OVERFLOW_GROUPS: dict[str, str] = {"eco": "eco-extra"}

GAME_INVITE_SECONDS: int = 120
GAME_MOVE_SECONDS: int = 180
TRIVIA_SECONDS: int = 20
TYPERACE_SECONDS: int = 45
HANGMAN_LIVES: int = 6

TRANSLATE_DEEPL_KEY: str = os.getenv("SOWARD_DEEPL_KEY", "").strip()
TRANSLATE_EMAIL: str = os.getenv("SOWARD_TRANSLATE_EMAIL", "").strip()
TRANSLATE_MAX_CHARS: int = 6000
SLASH_OPTION_DESCRIPTIONS: dict[str, str] = {
    "translate.language": "Language name or code, like spanish or es (default english)",
    "translate.text": "Text to translate, or a link to a message",
    "time.target": "A member, or a timezone like Asia/Dhaka",
    "weather.city": "City name",
    "calc.expression": "For example (3+4)*5 or sqrt(144)",
}

FAMILY_TREE_LIMIT: int = 250
CLAN_TREE_LIMIT: int = 300

REWARD_BASE: int = 150
REWARD_STREAK_STEP: int = 15
REWARD_STREAK_MAX_BONUS: int = 150
REWARD_COOLDOWN_HOURS: int = 20
REWARD_STREAK_WINDOW_HOURS: int = 48
WORK_COOLDOWN_SECONDS: int = 3600
WORK_DAILY_LIMIT: int = 4
GAMBLE_MIN_BET: int = 10
GAMBLE_MAX_BET: int = 5000
GAMBLE_COOLDOWN_SECONDS: int = 6
COINFLIP_PAYOUT: float = 1.9
CULTIVATION_JOBS: tuple = (
    {"key": "sweeper", "name": "Sect Ground Sweeper", "shifts": 0, "min": 30, "max": 50, "tasks": ("swept the training grounds of the sect", "cleared fallen leaves from the Hundred Steps", "scrubbed the disciple courtyard", "polished the stone lanterns of the main hall")},
    {"key": "herbalist", "name": "Herb Garden Tender", "shifts": 15, "min": 40, "max": 65, "tasks": ("watered the spirit herb beds", "pulled weeds from the moonlotus pond", "harvested ripe frostleaf for the pill hall", "guarded the garden from sneaky spirit rats")},
    {"key": "keeper", "name": "Spirit Beast Keeper", "shifts": 40, "min": 50, "max": 80, "tasks": ("fed the cloud cranes at dawn", "brushed the thunder boar herd", "cleaned the spirit beast stables", "calmed a restless flame fox")},
    {"key": "scribe", "name": "Formation Scribe", "shifts": 80, "min": 60, "max": 95, "tasks": ("redrew a fading guardian formation", "copied array diagrams for the library", "refreshed the sect's gate seal", "inked talismans for the outer disciples")},
    {"key": "alchemist", "name": "Alchemy Furnace Attendant", "shifts": 140, "min": 75, "max": 115, "tasks": ("kept the pill furnace at the perfect flame", "ground spirit herbs for a healing pill batch", "sorted finished pills by grade", "stirred a cauldron without ruining it")},
    {"key": "clerk", "name": "Auction House Clerk", "shifts": 220, "min": 90, "max": 140, "tasks": ("appraised a pile of spirit artifacts", "wrote lot descriptions for the evening auction", "escorted a bidder to the private rooms", "tallied the day's winning bids")},
    {"key": "auctioneer", "name": "Auction House Manager", "shifts": 350, "min": 110, "max": 170, "tasks": ("ran a packed auction for a heaven-grade sword", "drove up the bidding on a rare core", "settled a bidding dispute between two clans", "negotiated consignment with a wandering elder")},
    {"key": "treasurer", "name": "Sect Treasurer Elder", "shifts": 520, "min": 140, "max": 210, "tasks": ("audited the sect's spirit stone vault", "approved the yearly resource budget", "traded surplus herbs with a merchant guild", "uncovered a thieving steward")},
)
CULTIVATION_DEFAULT_JOB: str = "sweeper"
CULTIVATION_ACTIVITIES: dict = {
    "gather": {"cooldown": 7200, "daily": 2, "min": 8, "max": 20, "fail": 0.10, "icon": "egather", "title": "Herb gathering",
               "wins": ("You climbed a misty ridge and picked a bundle of spirit herbs worth", "You found a hidden patch of moonlotus and sold it for"),
               "fails": ("The herbs wilted before you could carry them down.", "A rival disciple beat you to the herb patch.")},
    "hunt": {"cooldown": 5400, "daily": 2, "min": 20, "max": 60, "fail": 0.40, "icon": "ehunt", "title": "Beast hunt",
             "wins": ("You felled a wild spirit boar and sold its core for", "You drove off a pack of mist wolves and collected pelts worth"),
             "fails": ("The beast slipped away into the forest.", "You came back empty handed and a little bruised.")},
    "mine": {"cooldown": 10800, "daily": 2, "min": 12, "max": 32, "fail": 0.15, "icon": "emine", "title": "Spirit stone mine",
             "wins": ("You chipped out spirit stone shards worth", "You opened a fresh vein and sold the ore for"),
             "fails": ("The tunnel collapsed before you found anything.", "The vein turned out to be plain rock.")},
    "ruins": {"cooldown": 14400, "daily": 1, "min": 30, "max": 120, "fail": 0.40, "icon": "eruins", "title": "Ancient ruins",
              "wins": ("You braved the ruins and carried out relics worth", "You cracked a sealed chamber and found treasure worth"),
              "fails": ("A guardian formation drove you out with nothing.", "The chamber was already looted long ago.")},
}
GAMBLE_TIERS: tuple = ((0.50, 0.0), (0.30, 1.5), (0.15, 2.0), (0.04, 3.0), (0.01, 6.0))

AUTOPARTNER_AD_MAX_CHARS: int = 1800
AUTOPARTNER_MAX_ATTEMPTS: int = 3
AUTOPARTNER_OCR_THRESHOLD: float = 0.6
AUTOPARTNER_CODE_MATCH: float = 0.85
AUTOPARTNER_MAX_IMAGE_BYTES: int = 8 * 1024 * 1024
AUTOPARTNER_OCR_TIMEOUT: int = 25
AUTOPARTNER_REPEAT_DAYS: int = 7
AUTOPARTNER_CLOSE_DELAY: int = 20
AUTOPARTNER_IDLE_HOURS: int = 24
