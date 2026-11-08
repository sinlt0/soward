import asyncio
import logging
import time
from typing import Any, Optional

import config

log = logging.getLogger("soward.mongo_sync")

TABLE_KEYS: dict[str, list[str]] = {
    "kv": ["ns", "key"],
    "guilds": ["guild_id"],
    "premium_keys": ["key_id"],
    "warn_cases": ["case_id"],
    "mod_cases": ["case_id"],
    "fakeperm_grants": ["guild_id", "target_id", "target_type", "node"],
    "temp_bans": ["guild_id", "user_id"],
    "mod_notes": ["note_id"],
    "xp": ["guild_id", "user_id"],
    "economy": ["user_id"],
    "custom_commands": ["guild_id", "trigger"],
    "custom_command_groups": ["guild_id", "name"],
    "tickets": ["ticket_id"],
    "ticket_panels": ["panel_id"],
    "ticket_settings": ["guild_id"],
    "dashboard_audit": ["entry_id"],
    "giveaways": ["giveaway_id"],
    "giveaway_entries": ["giveaway_id", "user_id"],
    "giveaway_bonus_roles": ["giveaway_id", "role_id"],
    "reaction_roles": ["guild_id", "message_id", "identifier"],
    "guild_settings": ["guild_id", "setting_key"],
    "antinuke_whitelist": ["guild_id", "target_id"],
    "panic_mode_state": ["guild_id"],
    "quarantine_history": ["guild_id", "user_id"],
    "antinuke_action_punishments": ["guild_id", "action_type"],
    "security_permit_tiers": ["guild_id", "user_id"],
    "security_whitelist": ["guild_id", "target_id", "scope"],
    "security_whitelist_rules": ["guild_id", "target_id", "scope", "value"],
    "security_backups": ["backup_id"],
    "security_incidents": ["incident_id"],
    "ban_appeals": ["appeal_id"],
    "appeal_votes": ["appeal_id", "user_id"],
    "message_reports": ["report_id"],
    "trust_adjustments": ["adj_id"],
    "member_profiles": ["guild_id", "user_id"],
    "match_queue": ["guild_id", "user_id"],
    "match_sessions": ["session_id"],
    "match_blocks": ["guild_id", "user_id", "blocked_id"],
    "server_events": ["event_id"],
    "event_rsvps": ["event_id", "user_id"],
    "timed_roles": ["guild_id", "user_id", "role_id"],
    "seasonal_roles": ["season_id"],
    "commemorative_badges": ["badge_id"],
    "badge_claims": ["badge_id", "user_id"],
    "ban_fingerprints": ["guild_id", "user_id"],
    "evasion_links": ["link_id"],
    "staff_feedback": ["feedback_id"],
    "staff_shifts": ["shift_id"],
    "np_targets": ["guild_id", "target_id"],
    "supporters": ["user_id"],
    "votes": ["user_id"],
    "premium_trials": ["guild_id"],
    "wallets": ["user_id"],
    "wallet_state": ["user_id"],
    "user_jobs": ["user_id"],
    "premium_coin_buys": ["user_id"],
    "vote_diamonds": ["user_id", "site"],
    "autopartner_config": ["guild_id"],
    "autopartner_tickets": ["channel_id"],
    "autopartner_posts": ["post_id"],
    "autopartner_hashes": ["guild_id", "digest"],
    "activity_state": ["user_id", "activity"],
    "user_profiles": ["user_id"],
    "user_cosmetics": ["user_id"],
    "user_items": ["user_id", "item_id"],
    "game_stats": ["user_id", "game"],
    "pets": ["pet_id"],
    "reminders": ["reminder_id"],
    "todos": ["todo_id"],
    "user_timezones": ["user_id"],
    "marriages": ["user_a", "user_b"],
    "family_children": ["child_id"],
    "family_slots": ["user_id"],
    "clans": ["clan_id"],
    "clan_members": ["user_id"],
    "clan_contributions": ["clan_id", "user_id"],
    "cult_characters": ["user_id"],
    "cult_items": ["user_id", "item"],
    "cult_treasury": ["owner_id"],
    "cult_raid_log": ["attacker_id", "target_id", "at"],
    "cult_titles": ["user_id", "title_key"],
    "cult_story": ["user_id"],
    "clan_branches": ["clan_id", "branch_key"],
    "cult_npcs": ["user_id", "npc_id"],
    "cult_rifts": ["user_id"],
    "cult_spawn_channels": ["channel_id"],
    "clan_buildings": ["clan_id", "building"],
    "clan_boss": ["clan_id"],
    "clan_boss_hits": ["clan_id", "user_id"],
    "clan_wars": ["war_id"],
    "clan_invites": ["clan_id", "user_id"],
    "activity_likes": ["user_id", "track_id"],
    "activity_history": ["entry_id"],
    "activity_playlists": ["playlist_id"],
    "vault_entries": ["entry_id"],
    "scheduled_actions": ["action_id"],
    "ticket_canned": ["guild_id", "name"],
    "ticket_ratings": ["ticket_id"],
    "ticket_transcripts": ["ticket_id"],
    "deep_backups": ["backup_id"],
    "member_seen": ["guild_id", "user_id"],
    "security_lockdown": ["guild_id"],
    "pending_verification": ["guild_id", "user_id"],
    "web_verify_tokens": ["token_hash"],
    "web_verifications": ["guild_id", "user_id"],
    "dev_stats_state": ["id"],
    "guild_anime_daily_config": ["guild_id"],
    "anime_daily_history": ["guild_id", "media_id", "posted_at"],
    "counting_state": ["guild_id"],
    "counting_users": ["guild_id", "user_id"],
    "wordle_games": ["guild_id", "user_id", "day"],
    "wordle_stats": ["guild_id", "user_id"],
    "app_forms": ["guild_id", "name"],
    "app_panels": ["message_id"],
    "crypto_invoices": ["invoice_id"],
    "crypto_payments": ["txid", "address"],
    "app_submissions": ["guild_id", "app_id"],
    "app_votes": ["guild_id", "app_id", "user_id"],
    "birthdays": ["guild_id", "user_id"],
    "confessions": ["guild_id", "number"],
    "confession_bans": ["guild_id", "user_id"],
    "suggestions": ["guild_id", "number"],
    "suggestion_votes": ["guild_id", "number", "user_id"],
    "starboard_posts": ["guild_id", "message_id"],
    "member_afk": ["guild_id", "user_id"],
    "global_afk": ["user_id"],
    "reaction_role_panels": ["panel_id"],
    "reaction_role_bindings": ["panel_id", "emoji"],
    "guild_greeting_config": ["guild_id", "trigger_type"],
    "quarantine": ["guild_id", "user_id"],
    "antinuke_log": ["log_id"],
    "antiraid_state": ["guild_id"],
    "heat_scores": ["guild_id", "user_id"],
    "global_no_prefix": ["user_id"],
    "user_playlists": ["playlist_id"],
    "vc247_state": ["guild_id"],
    "custom_lofi_stations": ["guild_id", "key"],
    "lofi_state": ["guild_id"],
    "log_channels": ["guild_id", "category"],
    "log_disabled_events": ["guild_id", "event"],
    "blacklist": ["target_id", "target_type"],
    "alert_subscriptions": ["subscription_id"],
    "alert_state": ["platform", "target_id"],
    "alert_sent_log": ["subscription_id", "content_id"],
    "websub_subscriptions": ["channel_id"],
    "server_templates": ["code"],
    "jtc_hubs": ["channel_id"],
    "jtc_channels": ["channel_id"],
    "jtc_prefs": ["guild_id", "user_id"],
    "booster_config": ["guild_id"],
    "booster_tiers": ["guild_id", "boosts"],
    "booster_members": ["guild_id", "user_id"],
    "booster_roles": ["guild_id", "user_id"],
    "guild_leveling_config": ["guild_id"],
    "member_xp": ["guild_id", "user_id"],
    "member_xp_periodic": ["guild_id", "user_id", "period"],
    "leveling_period_state": ["guild_id", "period"],
    "level_role_rewards": ["guild_id", "level", "role_id"],
    "xp_multipliers": ["multiplier_id"],
    "xp_no_xp_channels": ["guild_id", "channel_id"],
    "xp_no_xp_roles": ["guild_id", "role_id"],
    "embed_templates": ["guild_id", "name"],
    "embed_template_fields": ["guild_id", "embed_name", "position"],
    "polls": ["poll_id"],
    "nsfw_config": ["guild_id"],
    "nsfw_channels": ["guild_id", "channel_id"],
}

ROWID_TABLES: list[str] = ["raid_join_log", "afk_mention_log", "global_afk_mention_log"]

_sync_task: Optional[asyncio.Task] = None


def _row_key(table: str, row: dict) -> str:
    if table in ROWID_TABLES:
        return str(row["_rowid"])
    keys = TABLE_KEYS[table]
    return "|".join(str(row[k]) for k in keys)


async def _get_sqlite_rows(table: str) -> dict[str, dict]:
    from utils import db

    if table in ROWID_TABLES:
        rows = await db.raw_fetch(f"SELECT rowid AS _rowid, * FROM {table}")
    else:
        rows = await db.raw_fetch(f"SELECT * FROM {table}")

    return {_row_key(table, dict(r)): dict(r) for r in rows}


async def sync_table(table: str) -> dict:
    from utils import db

    collection = await db.mongo_collection(f"mirror_{table}")
    if collection is None:
        return {"synced": False}

    sqlite_rows = await _get_sqlite_rows(table)

    mongo_docs = {}
    async for doc in collection.find({}, {"_sync_key": 1}):
        mongo_docs[doc["_sync_key"]] = doc["_id"]

    sqlite_keys = set(sqlite_rows.keys())
    mongo_keys = set(mongo_docs.keys())

    to_upsert = sqlite_keys
    to_delete = mongo_keys - sqlite_keys

    upserted = 0
    for key in to_upsert:
        row_data = sqlite_rows[key]
        await collection.update_one(
            {"_sync_key": key},
            {"$set": {"_sync_key": key, "_synced_at": time.time(), **row_data}},
            upsert=True,
        )
        upserted += 1

    deleted = 0
    if to_delete:
        result = await collection.delete_many({"_sync_key": {"$in": list(to_delete)}})
        deleted = result.deleted_count

    return {"synced": True, "upserted": upserted, "deleted": deleted, "total": len(sqlite_keys)}


async def sync_all_tables() -> dict:
    from utils import db

    if not db.is_mongo_available():
        return {}

    results = {}
    for table in TABLE_KEYS.keys() | set(ROWID_TABLES):
        try:
            results[table] = await sync_table(table)
        except Exception as exc:
            log.warning("Failed to sync table '%s' to MongoDB: %s", table, exc)
            results[table] = {"synced": False, "error": str(exc)}
    return results


async def initial_sync_if_empty() -> None:
    from utils import db

    if not db.is_mongo_available():
        return

    for table in TABLE_KEYS.keys() | set(ROWID_TABLES):
        try:
            collection = await db.mongo_collection(f"mirror_{table}")
            if collection is None:
                continue
            existing_count = await collection.estimated_document_count()
            if existing_count > 0:
                continue
            result = await sync_table(table)
            if result.get("total", 0) > 0:
                log.info("Initial MongoDB mirror seeded for '%s': %d row(s).", table, result["total"])
        except Exception as exc:
            log.warning("Initial sync failed for table '%s': %s", table, exc)


async def restore_table_from_mongo(table: str) -> int:
    from utils import db

    collection = await db.mongo_collection(f"mirror_{table}")
    if collection is None:
        return 0

    columns_cache: Optional[list[str]] = None
    restored = 0

    async for doc in collection.find({}):
        doc.pop("_id", None)
        doc.pop("_sync_key", None)
        doc.pop("_synced_at", None)
        row_id = doc.pop("_rowid", None)

        if columns_cache is None:
            columns_cache = list(doc.keys())

        placeholders = ", ".join("?" for _ in columns_cache)
        col_names = ", ".join(columns_cache)
        values = tuple(doc.get(c) for c in columns_cache)

        try:
            await db.raw_execute(
                f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                values,
            )
            restored += 1
        except Exception as exc:
            log.warning("Failed to restore a row into '%s' from MongoDB: %s", table, exc)

    return restored


async def restore_all_from_mongo() -> dict:
    from utils import db

    if not db.is_mongo_available():
        return {}

    results = {}
    for table in TABLE_KEYS.keys() | set(ROWID_TABLES):
        try:
            count = await restore_table_from_mongo(table)
            results[table] = count
            if count:
                log.info("Restored %d row(s) into '%s' from MongoDB mirror.", count, table)
        except Exception as exc:
            log.warning("Failed to restore table '%s' from MongoDB: %s", table, exc)
            results[table] = 0
    return results


async def _sync_loop():
    from utils import db

    while True:
        await asyncio.sleep(config.MONGO_SYNC_INTERVAL)
        if not db.is_mongo_available():
            continue
        try:
            results = await sync_all_tables()
            total_upserted = sum(r.get("upserted", 0) for r in results.values())
            total_deleted = sum(r.get("deleted", 0) for r in results.values())
            if total_upserted or total_deleted:
                log.debug("MongoDB sync complete: %d upserted, %d deleted across %d table(s).",
                          total_upserted, total_deleted, len(results))
        except Exception:
            log.exception("Unhandled error during MongoDB sync loop.")


def start_sync_loop() -> asyncio.Task:
    global _sync_task
    _sync_task = asyncio.ensure_future(_sync_loop())
    return _sync_task


def stop_sync_loop() -> None:
    if _sync_task is not None:
        _sync_task.cancel()
