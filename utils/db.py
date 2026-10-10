import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite
import motor.motor_asyncio

import config

log = logging.getLogger("soward.db")

_mongo_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_mongo_db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
_mongo_available: bool = False
_sqlite_conn: Optional[aiosqlite.Connection] = None
_last_mongo_check: float = 0.0

async def _check_mongo_availability() -> bool:
    global _mongo_client, _mongo_db, _mongo_available
    try:
        if _mongo_client is None:
            _mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                config.MONGODB_URI, serverSelectionTimeoutMS=3000
            )
            _mongo_db = _mongo_client[config.MONGODB_DB_NAME]
        await _mongo_client.admin.command("ping")
        if not _mongo_available:
            log.info("MongoDB connection established.")
        _mongo_available = True
    except Exception as exc:
        if _mongo_available:
            log.warning("MongoDB became unavailable: %s", exc)
        _mongo_available = False
    return _mongo_available

async def _mongo_reconnect_loop() -> None:
    while True:
        await asyncio.sleep(config.MONGO_RECONNECT_INTERVAL)
        global _last_mongo_check
        _last_mongo_check = time.monotonic()
        await _check_mongo_availability()

async def init(bot_loop: asyncio.AbstractEventLoop) -> None:
    global _sqlite_conn

    await _check_mongo_availability()
    asyncio.ensure_future(_mongo_reconnect_loop())

    sqlite_path = Path(config.SQLITE_PATH)
    legacy_path = sqlite_path.parent / "nexus.db"
    if not sqlite_path.exists() and legacy_path.exists():
        legacy_path.rename(sqlite_path)
        for suffix in ("-wal", "-shm"):
            legacy_extra = sqlite_path.parent / f"nexus.db{suffix}"
            if legacy_extra.exists():
                legacy_extra.rename(sqlite_path.parent / f"soward.db{suffix}")
        log.info("Renamed legacy nexus.db to soward.db after rebrand.")

    is_fresh_database = not sqlite_path.exists() or sqlite_path.stat().st_size == 0

    _sqlite_conn = await aiosqlite.connect(config.SQLITE_PATH)
    _sqlite_conn.row_factory = aiosqlite.Row
    await _sqlite_conn.execute("PRAGMA journal_mode=WAL")
    await _sqlite_conn.execute("PRAGMA foreign_keys=ON")
    await _migrate_legacy_custom_commands()
    await _bootstrap_sqlite()

    try:
        await _sqlite_conn.execute("ALTER TABLE lofi_state ADD COLUMN radio_key TEXT NOT NULL DEFAULT 'lofi_girl'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE giveaways ADD COLUMN required_role_id INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE giveaways ADD COLUMN min_account_age_days INTEGER NOT NULL DEFAULT 0")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE embed_templates ADD COLUMN title_url TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE embed_templates ADD COLUMN author_url TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE guild_anime_daily_config ADD COLUMN nsfw INTEGER NOT NULL DEFAULT 0")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE guild_anime_daily_config ADD COLUMN post_minute_utc INTEGER NOT NULL DEFAULT 0")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_panels ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_bindings ADD COLUMN binding_mode TEXT NOT NULL DEFAULT 'normal'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_bindings ADD COLUMN swap_role_id INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_bindings ADD COLUMN group_id TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_bindings ADD COLUMN required_role_id INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_bindings ADD COLUMN blacklist_role_id INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE reaction_role_panels ADD COLUMN panel_type TEXT NOT NULL DEFAULT 'reaction'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN panel_id TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN number INTEGER NOT NULL DEFAULT 0")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN subject TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN last_activity REAL")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN close_reason TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN closed_by INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE tickets ADD COLUMN answers TEXT")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE ticket_panels ADD COLUMN category_ids TEXT NOT NULL DEFAULT '[]'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE ticket_panels ADD COLUMN questions TEXT NOT NULL DEFAULT '[]'")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE ticket_panels ADD COLUMN transcript_channel_id INTEGER")
        await _sqlite_conn.commit()
    except Exception:
        pass

    try:
        await _sqlite_conn.execute("ALTER TABLE ticket_panels ADD COLUMN one_per_user INTEGER NOT NULL DEFAULT 1")
        await _sqlite_conn.commit()
    except Exception:
        pass

    await _sqlite_conn.execute(
        "UPDATE ticket_panels SET category_ids = '[' || category_id || ']' "
        "WHERE category_id IS NOT NULL AND category_ids = '[]'"
    )
    await _sqlite_conn.commit()

    log.info("SQLite ready at %s", config.SQLITE_PATH)

    if _mongo_available:
        from utils import mongo_sync
        if is_fresh_database:
            log.info("Local SQLite database is empty/missing — attempting restore from MongoDB mirror...")
            restored = await mongo_sync.restore_all_from_mongo()
            total_restored = sum(restored.values())
            if total_restored:
                log.info("Restored %d total row(s) from MongoDB across %d table(s).", total_restored, len(restored))
            else:
                log.info("No prior MongoDB mirror data found — starting with a clean database.")
        else:
            await mongo_sync.initial_sync_if_empty()
        mongo_sync.start_sync_loop()
        log.info("MongoDB row-level sync loop started (interval: %ds).", config.MONGO_SYNC_INTERVAL)

async def close() -> None:
    from utils import mongo_sync
    mongo_sync.stop_sync_loop()
    if _mongo_available:
        log.info("Performing final MongoDB sync before shutdown...")
        try:
            await mongo_sync.sync_all_tables()
        except Exception:
            log.exception("Final MongoDB sync failed during shutdown.")
    if _sqlite_conn is not None:
        await _sqlite_conn.close()

async def _migrate_legacy_custom_commands() -> None:
    cur = await _sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='custom_commands'"
    )
    exists = await cur.fetchone()
    if not exists:
        return

    cur = await _sqlite_conn.execute("PRAGMA table_info(custom_commands)")
    columns = {row["name"] for row in await cur.fetchall()}

    if "trigger" not in columns:
        log.warning("Legacy custom_commands schema detected — dropping and recreating with the new format. Existing custom commands will need to be re-added.")
        await _sqlite_conn.execute("DROP TABLE custom_commands")
        await _sqlite_conn.commit()

async def _bootstrap_sqlite() -> None:
    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS kv (
            ns TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (ns, key)
        )""",
        """CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY,
            prefix TEXT NOT NULL DEFAULT '!',
            premium INTEGER NOT NULL DEFAULT 0,
            premium_expires_at REAL,
            server_np_enabled INTEGER NOT NULL DEFAULT 1,
            incident_state INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS premium_keys (
            key_id TEXT PRIMARY KEY,
            duration_days INTEGER NOT NULL,
            duration_label TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            used_by INTEGER,
            used_at REAL,
            created_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS warn_cases (
            case_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS mod_cases (
            case_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            duration INTEGER,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS fakeperm_grants (
            guild_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            node TEXT NOT NULL,
            granted_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, target_id, target_type, node)
        )""",
        """CREATE TABLE IF NOT EXISTS temp_bans (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            unban_at REAL NOT NULL,
            reason TEXT,
            moderator_id INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS mod_notes (
            note_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS xp (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            last_xp_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            last_daily REAL,
            last_work REAL
        )""",
        """CREATE TABLE IF NOT EXISTS custom_commands (
            guild_id INTEGER NOT NULL,
            trigger TEXT NOT NULL,
            numeric_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, trigger)
        )""",
        """CREATE TABLE IF NOT EXISTS custom_command_groups (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (guild_id, name)
        )""",
        """CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            claimed_by INTEGER,
            status TEXT NOT NULL DEFAULT 'open',
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            closed_at REAL,
            panel_id TEXT,
            number INTEGER NOT NULL DEFAULT 0,
            priority TEXT NOT NULL DEFAULT 'normal',
            subject TEXT,
            last_activity REAL,
            close_reason TEXT,
            closed_by INTEGER,
            answers TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS ticket_panels (
            panel_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            channel_id INTEGER,
            message_id INTEGER,
            category_id INTEGER,
            category_ids TEXT NOT NULL DEFAULT '[]',
            staff_role_ids TEXT NOT NULL DEFAULT '[]',
            questions TEXT NOT NULL DEFAULT '[]',
            transcript_channel_id INTEGER,
            one_per_user INTEGER NOT NULL DEFAULT 1,
            button_label TEXT NOT NULL DEFAULT 'Open a Ticket',
            welcome_text TEXT,
            ask_subject INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS ticket_settings (
            guild_id INTEGER PRIMARY KEY,
            log_channel_id INTEGER,
            max_open INTEGER NOT NULL DEFAULT 3,
            auto_close_hours INTEGER NOT NULL DEFAULT 0,
            counter INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS dashboard_audit (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            module TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS giveaways (
            giveaway_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            prize TEXT NOT NULL,
            winner_count INTEGER NOT NULL DEFAULT 1,
            ends_at REAL NOT NULL,
            host_id INTEGER NOT NULL,
            ended INTEGER NOT NULL DEFAULT 0,
            required_role_id INTEGER,
            min_account_age_days INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS giveaway_bonus_roles (
            giveaway_id TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            bonus_entries INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (giveaway_id, role_id)
        )""",
        """CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            identifier TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, message_id, identifier)
        )""",
        """CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL,
            PRIMARY KEY (guild_id, setting_key)
        )""",
        """CREATE TABLE IF NOT EXISTS antinuke_whitelist (
            guild_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            added_by INTEGER,
            added_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, target_id)
        )""",
        """CREATE TABLE IF NOT EXISTS panic_mode_state (
            guild_id INTEGER PRIMARY KEY,
            active INTEGER NOT NULL DEFAULT 0,
            started_at REAL,
            expires_at REAL,
            triggered_by TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS quarantine_history (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            offense_count INTEGER NOT NULL DEFAULT 0,
            last_offense_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS antinuke_action_punishments (
            guild_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            punishment TEXT NOT NULL,
            PRIMARY KEY (guild_id, action_type)
        )""",
        """CREATE TABLE IF NOT EXISTS security_permit_tiers (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            tier TEXT NOT NULL,
            granted_by INTEGER NOT NULL,
            granted_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS pending_verification (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS dev_stats_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message_id INTEGER,
            last_updated_at REAL
        )""",
        """CREATE TABLE IF NOT EXISTS guild_anime_daily_config (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            channel_id INTEGER,
            media_type TEXT NOT NULL DEFAULT 'ANIME',
            genre_filter TEXT,
            post_hour_utc INTEGER NOT NULL DEFAULT 12,
            post_minute_utc INTEGER NOT NULL DEFAULT 0,
            last_posted_at REAL,
            role_id INTEGER,
            nsfw INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS anime_daily_history (
            guild_id INTEGER NOT NULL,
            media_id INTEGER NOT NULL,
            posted_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, media_id, posted_at)
        )""",
        """CREATE TABLE IF NOT EXISTS member_afk (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT,
            set_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            original_nick TEXT,
            auto_return_at REAL,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS global_afk (
            user_id INTEGER PRIMARY KEY,
            message TEXT,
            set_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            auto_return_at REAL
        )""",
        """CREATE TABLE IF NOT EXISTS global_afk_mention_log (
            afk_user_id INTEGER NOT NULL,
            mentioner_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            content_preview TEXT,
            mentioned_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS afk_mention_log (
            guild_id INTEGER NOT NULL,
            afk_user_id INTEGER NOT NULL,
            mentioner_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            content_preview TEXT,
            mentioned_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS reaction_role_panels (
            panel_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER,
            message_id INTEGER,
            embed_name TEXT,
            fallback_title TEXT,
            fallback_description TEXT,
            mode TEXT NOT NULL DEFAULT 'toggle',
            panel_type TEXT NOT NULL DEFAULT 'reaction',
            max_roles INTEGER,
            required_role_id INTEGER,
            blacklist_role_id INTEGER,
            locked INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS reaction_role_bindings (
            panel_id TEXT NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            label TEXT,
            binding_mode TEXT NOT NULL DEFAULT 'normal',
            swap_role_id INTEGER,
            group_id TEXT,
            required_role_id INTEGER,
            blacklist_role_id INTEGER,
            PRIMARY KEY (panel_id, emoji)
        )""",
        """CREATE TABLE IF NOT EXISTS guild_greeting_config (
            guild_id INTEGER NOT NULL,
            trigger_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            channel_id INTEGER,
            message_text TEXT,
            embed_name TEXT,
            send_as_dm INTEGER NOT NULL DEFAULT 0,
            dm_fallback_to_channel INTEGER NOT NULL DEFAULT 1,
            use_card INTEGER NOT NULL DEFAULT 0,
            card_layout TEXT NOT NULL DEFAULT 'classic',
            card_background_url TEXT,
            card_accent_color TEXT,
            join_role_delay_seconds INTEGER NOT NULL DEFAULT 0,
            delete_after_seconds INTEGER,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            updated_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, trigger_type)
        )""",
        """CREATE TABLE IF NOT EXISTS quarantine (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT,
            saved_roles TEXT NOT NULL DEFAULT '[]',
            quarantined_by INTEGER,
            quarantined_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            released_at REAL,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS antinuke_log (
            log_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            actor_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            punishment TEXT,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS antiraid_state (
            guild_id INTEGER PRIMARY KEY,
            raid_mode INTEGER NOT NULL DEFAULT 0,
            raid_mode_started_at REAL,
            raid_mode_expires_at REAL,
            triggered_by TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS raid_join_log (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at REAL NOT NULL,
            account_created_at REAL NOT NULL,
            had_avatar INTEGER NOT NULL DEFAULT 1,
            flagged INTEGER NOT NULL DEFAULT 0,
            action_taken TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS heat_scores (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            heat REAL NOT NULL DEFAULT 0,
            last_updated REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            mute_multiplier INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS global_no_prefix (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER NOT NULL,
            added_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS user_playlists (
            playlist_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            tracks TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS vc247_state (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            voice_channel_id INTEGER,
            text_channel_id INTEGER
        )""",
        """CREATE TABLE IF NOT EXISTS custom_lofi_stations (
            guild_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            added_by INTEGER,
            PRIMARY KEY (guild_id, key)
        )""",
        """CREATE TABLE IF NOT EXISTS lofi_state (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            text_channel_id INTEGER,
            enabled INTEGER NOT NULL DEFAULT 0,
            radio_key TEXT NOT NULL DEFAULT 'lofi_girl'
        )""",
        """CREATE TABLE IF NOT EXISTS log_channels (
            guild_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            webhook_url TEXT,
            PRIMARY KEY (guild_id, category)
        )""",
        """CREATE TABLE IF NOT EXISTS log_disabled_events (
            guild_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            PRIMARY KEY (guild_id, event)
        )""",
        """CREATE TABLE IF NOT EXISTS blacklist (
            target_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            reason TEXT,
            blacklisted_by INTEGER,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (target_id, target_type)
        )""",
        """CREATE TABLE IF NOT EXISTS alert_subscriptions (
            subscription_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_name TEXT,
            announce_channel_id INTEGER NOT NULL,
            ping_role_id INTEGER,
            custom_message TEXT,
            live_enabled INTEGER NOT NULL DEFAULT 1,
            upload_enabled INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS alert_state (
            platform TEXT NOT NULL,
            target_id TEXT NOT NULL,
            last_video_id TEXT,
            last_live_stream_id TEXT,
            is_live INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (platform, target_id)
        )""",
        """CREATE TABLE IF NOT EXISTS alert_sent_log (
            subscription_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            sent_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (subscription_id, content_id)
        )""",
        """CREATE TABLE IF NOT EXISTS guild_leveling_config (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            xp_min INTEGER NOT NULL DEFAULT 15,
            xp_max INTEGER NOT NULL DEFAULT 25,
            text_cooldown_seconds INTEGER NOT NULL DEFAULT 60,
            voice_xp_per_minute INTEGER NOT NULL DEFAULT 10,
            voice_enabled INTEGER NOT NULL DEFAULT 1,
            voice_require_unmuted INTEGER NOT NULL DEFAULT 1,
            voice_require_others INTEGER NOT NULL DEFAULT 1,
            role_stack_mode TEXT NOT NULL DEFAULT 'stack',
            announce_mode TEXT NOT NULL DEFAULT 'channel',
            announce_channel_id INTEGER,
            announce_message TEXT,
            weekly_reset_enabled INTEGER NOT NULL DEFAULT 0,
            monthly_reset_enabled INTEGER NOT NULL DEFAULT 0,
            top_role_id INTEGER,
            prestige_level_cap INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS member_xp (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            prestige INTEGER NOT NULL DEFAULT 0,
            last_text_xp_at REAL NOT NULL DEFAULT 0,
            voice_join_at REAL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            total_voice_minutes INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS member_xp_periodic (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            period TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, period)
        )""",
        """CREATE TABLE IF NOT EXISTS leveling_period_state (
            guild_id INTEGER NOT NULL,
            period TEXT NOT NULL,
            period_start REAL NOT NULL,
            PRIMARY KEY (guild_id, period)
        )""",
        """CREATE TABLE IF NOT EXISTS level_role_rewards (
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, level, role_id)
        )""",
        """CREATE TABLE IF NOT EXISTS xp_multipliers (
            multiplier_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER,
            multiplier REAL NOT NULL DEFAULT 1.0,
            label TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS xp_no_xp_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        )""",
        """CREATE TABLE IF NOT EXISTS xp_no_xp_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )""",
        """CREATE TABLE IF NOT EXISTS embed_templates (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            title TEXT,
            title_url TEXT,
            description TEXT,
            color TEXT,
            author_text TEXT,
            author_icon TEXT,
            author_url TEXT,
            footer_text TEXT,
            footer_icon TEXT,
            image_url TEXT,
            thumbnail_url TEXT,
            use_timestamp INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL,
            created_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            updated_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, name)
        )""",
        """CREATE TABLE IF NOT EXISTS embed_template_fields (
            guild_id INTEGER NOT NULL,
            embed_name TEXT NOT NULL,
            position INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT NOT NULL,
            inline INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, embed_name, position)
        )""",
        """CREATE TABLE IF NOT EXISTS nsfw_config (
            guild_id INTEGER PRIMARY KEY,
            role_id INTEGER NOT NULL,
            updated_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0)
        )""",
        """CREATE TABLE IF NOT EXISTS nsfw_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            snapshot TEXT,
            added_by INTEGER,
            added_at REAL NOT NULL DEFAULT ((julianday('now') - 2440587.5) * 86400.0),
            PRIMARY KEY (guild_id, channel_id)
        )""",
        """CREATE TABLE IF NOT EXISTS polls (
            poll_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            question TEXT NOT NULL,
            options TEXT NOT NULL,
            votes TEXT NOT NULL DEFAULT '{}',
            ends_at REAL,
            ended INTEGER NOT NULL DEFAULT 0
        )""",
    ]
    for stmt in ddl_statements:
        await _sqlite_conn.execute(stmt)
    await _sqlite_conn.commit()

def _serialize(value: Any) -> str:
    return json.dumps(value)

def _deserialize(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

async def get(ns: str, key: str) -> Optional[Any]:
    if _mongo_available and _mongo_db is not None:
        try:
            doc = await _mongo_db[ns].find_one({"_id": key})
            if doc:
                return doc.get("value")
        except Exception as exc:
            log.debug("Mongo read failed, falling back to SQLite: %s", exc)

    async with _sqlite_conn.execute(
        "SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)
    ) as cur:
        row = await cur.fetchone()
    if row:
        return _deserialize(row["value"])
    return None

async def set(ns: str, key: str, value: Any) -> None:
    serialized = _serialize(value)
    now = time.time()

    if _mongo_available and _mongo_db is not None:
        try:
            await _mongo_db[ns].update_one(
                {"_id": key},
                {"$set": {"value": value, "updated_at": now}},
                upsert=True,
            )
        except Exception as exc:
            log.debug("Mongo write failed: %s", exc)

    await _sqlite_conn.execute(
        "INSERT INTO kv (ns, key, value, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(ns, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (ns, key, serialized, now),
    )
    await _sqlite_conn.commit()

async def delete(ns: str, key: str) -> None:
    if _mongo_available and _mongo_db is not None:
        try:
            await _mongo_db[ns].delete_one({"_id": key})
        except Exception as exc:
            log.debug("Mongo delete failed: %s", exc)

    await _sqlite_conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))
    await _sqlite_conn.commit()

async def find(ns: str, query: dict) -> list[dict]:
    if _mongo_available and _mongo_db is not None:
        try:
            cursor = _mongo_db[ns].find(query)
            return await cursor.to_list(length=1000)
        except Exception as exc:
            log.debug("Mongo find failed, using SQLite: %s", exc)

    async with _sqlite_conn.execute(
        "SELECT key, value FROM kv WHERE ns = ?", (ns,)
    ) as cur:
        rows = await cur.fetchall()

    results = []
    for row in rows:
        try:
            doc = _deserialize(row["value"])
            if isinstance(doc, dict):
                match = all(doc.get(k) == v for k, v in query.items())
                if match:
                    results.append(doc)
        except Exception:
            pass
    return results

async def raw_execute(sql: str, params: tuple = ()) -> aiosqlite.Cursor:
    cur = await _sqlite_conn.execute(sql, params)
    await _sqlite_conn.commit()
    return cur

async def raw_fetch(sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
    async with _sqlite_conn.execute(sql, params) as cur:
        return await cur.fetchall()

async def raw_fetchone(sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
    async with _sqlite_conn.execute(sql, params) as cur:
        return await cur.fetchone()

async def get_last_backup_info() -> Optional[dict]:
    if not _mongo_available or _mongo_db is None:
        return None
    try:
        from utils import mongo_sync
        latest_synced_at = None
        total_docs = 0
        for table in mongo_sync.TABLE_KEYS.keys() | set(mongo_sync.ROWID_TABLES):
            collection = _mongo_db[f"mirror_{table}"]
            doc = await collection.find_one(sort=[("_synced_at", -1)])
            if doc and doc.get("_synced_at"):
                if latest_synced_at is None or doc["_synced_at"] > latest_synced_at:
                    latest_synced_at = doc["_synced_at"]
            total_docs += await collection.estimated_document_count()
        if latest_synced_at is None:
            return None
        return {"saved_at": latest_synced_at, "size_bytes": total_docs}
    except Exception:
        return None

async def mongo_collection(collection: str):
    if _mongo_available and _mongo_db is not None:
        return _mongo_db[collection]
    return None

def is_mongo_available() -> bool:
    return _mongo_available
