import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "devs.json", "r") as _f:
    _devs_data = json.load(_f)

BOT_TOKEN: str = os.getenv("SOWARD_TOKEN", "")
MONGODB_URI: str = os.getenv("SOWARD_MONGO_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME: str = os.getenv("SOWARD_MONGO_DB", "soward")
DATA_DIR: Path = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SQLITE_PATH: str = str(DATA_DIR / "soward.db")

DEFAULT_PREFIX: str = "!"
BOT_NAME: str = "Soward"
BOT_VERSION: str = "1.0.0"
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
ALERT_MAX_SUBSCRIPTIONS_PER_PLATFORM: int = 5

EMBED_TEMPLATE_MAX_FREE: int = 100
EMBED_TEMPLATE_MAX_PREMIUM: int = 250
COMMAND_COOLDOWN: int = 3

PREMIUM_DURATION_PRESETS: dict = {
    "3d": 3, "6d": 6, "1w": 7, "2w": 14,
    "1m": 30, "33d": 33, "60d": 60,
    "2mo": 60, "3mo": 90, "6mo": 180, "1y": 365,
}

SERVER_NO_PREFIX_ENABLED_DEFAULT: bool = True

XP_PER_MESSAGE_MIN: int = 5
XP_PER_MESSAGE_MAX: int = 15
XP_COOLDOWN_SECONDS: int = 60
LEVEL_XP_FORMULA_BASE: int = 100
LEVEL_XP_FORMULA_MULTIPLIER: float = 1.5

DAILY_CURRENCY_MIN: int = 100
DAILY_CURRENCY_MAX: int = 500
WORK_CURRENCY_MIN: int = 50
WORK_CURRENCY_MAX: int = 200
GAMBLE_MAX_BET: int = 10000

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

VERIFICATION_LEVELS: dict = {
    "none": 0,
    "reaction": 1,
    "button": 2,
    "captcha": 3,
    "manual": 4,
}

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
AUTOMOD_BASE_MUTE_SECONDS: int = 300
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
    "antinuke_quarantine",
    "antiraid_action",
    "antiraid_raid_mode",
    "verification_action",
    "autorole_action",
]

LOG_CATEGORY_NAME: str = "soward-logs"

LOG_CATEGORIES: dict[str, dict] = {
    "mod": {
        "label": "Moderation",
        "channel_name": "mod-logs",
        "events": ["ban", "softban", "unban", "kick", "mute", "unmute", "warn", "purge", "lockdown", "unlock", "slowmode"],
    },
    "security": {
        "label": "Security",
        "channel_name": "security-logs",
        "events": [
            "automod_action",
            "antinuke_action",
            "antinuke_quarantine",
            "antiraid_action",
            "antiraid_raid_mode",
            "verification_action",
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
        "events": ["role_change", "role_create", "role_delete", "channel_change", "channel_create", "channel_delete"],
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
GIVEAWAY_CHECK_INTERVAL: int = 10

HELP_HIDDEN_CATEGORIES: set[str] = {
    "Premium",
    "GlobalNoPrefix",
    "Dev",
}

LOFI_STREAM_URL: str = "https://www.youtube.com/watch?v=jfKfPfyJRdk"
AUTOPLAY_RELATED_SEARCH_SUFFIX: str = "official audio"
MUSIC_MAX_PLAYLIST_TRACKS: int = 200

AFK_MAX_AUTO_RETURN_MINUTES: int = 1440
AFK_MENTION_LOG_LIMIT: int = 15
AFK_NICK_PREFIX: str = "[AFK] "

GREETING_TRIGGER_TYPES: tuple = ("join", "leave", "boost", "ban")
GREETING_CARD_LAYOUTS: tuple = ("classic", "left", "right", "banner")
GREETING_DEFAULT_CARD_LAYOUT: str = "classic"
GREETING_MAX_JOIN_ROLE_DELAY_SECONDS: int = 3600
BOOST_LEVEL_THRESHOLDS: dict = {1: 2, 2: 7, 3: 14}
