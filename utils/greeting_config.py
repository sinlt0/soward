import time
from typing import Optional

import discord

from utils import db, message_vars
import config


async def get_config(guild_id: int, trigger_type: str) -> dict:
    row = await db.raw_fetchone(
        "SELECT * FROM guild_greeting_config WHERE guild_id=? AND trigger_type=?", (guild_id, trigger_type)
    )
    if row:
        return dict(row)

    return {
        "guild_id": guild_id, "trigger_type": trigger_type, "enabled": 0, "channel_id": None,
        "message_text": None, "embed_name": None, "send_as_dm": 0, "dm_fallback_to_channel": 1,
        "use_card": 0, "card_layout": config.GREETING_DEFAULT_CARD_LAYOUT, "card_background_url": None,
        "card_accent_color": None, "join_role_delay_seconds": 0, "delete_after_seconds": None,
    }


async def set_config_fields(guild_id: int, trigger_type: str, **fields) -> None:
    if trigger_type not in config.GREETING_TRIGGER_TYPES:
        raise ValueError(f"Invalid trigger_type: {trigger_type}")

    existing = await get_config(guild_id, trigger_type)
    existing.update(fields)
    now = time.time()

    await db.raw_execute(
        "INSERT INTO guild_greeting_config"
        " (guild_id, trigger_type, enabled, channel_id, message_text, embed_name, send_as_dm,"
        "  dm_fallback_to_channel, use_card, card_layout, card_background_url, card_accent_color,"
        "  join_role_delay_seconds, delete_after_seconds, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, trigger_type) DO UPDATE SET"
        " enabled=excluded.enabled, channel_id=excluded.channel_id, message_text=excluded.message_text,"
        " embed_name=excluded.embed_name, send_as_dm=excluded.send_as_dm,"
        " dm_fallback_to_channel=excluded.dm_fallback_to_channel, use_card=excluded.use_card,"
        " card_layout=excluded.card_layout, card_background_url=excluded.card_background_url,"
        " card_accent_color=excluded.card_accent_color, join_role_delay_seconds=excluded.join_role_delay_seconds,"
        " delete_after_seconds=excluded.delete_after_seconds, updated_at=excluded.updated_at",
        (
            guild_id, trigger_type, int(existing["enabled"]), existing["channel_id"], existing["message_text"],
            existing["embed_name"], int(existing["send_as_dm"]), int(existing["dm_fallback_to_channel"]),
            int(existing["use_card"]), existing["card_layout"], existing["card_background_url"],
            existing["card_accent_color"], existing["join_role_delay_seconds"], existing["delete_after_seconds"],
            existing.get("created_at") or now, now,
        ),
    )


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _boost_level_for_count(count: int) -> int:
    level = 0
    for lvl, threshold in sorted(config.BOOST_LEVEL_THRESHOLDS.items()):
        if count >= threshold:
            level = lvl
    return level


def _boosts_until_next_level(count: int) -> Optional[int]:
    current_level = _boost_level_for_count(count)
    if current_level >= max(config.BOOST_LEVEL_THRESHOLDS):
        return None
    next_threshold = config.BOOST_LEVEL_THRESHOLDS[current_level + 1]
    return max(0, next_threshold - count)


def build_greeting_variables(member: discord.Member, guild: discord.Guild, trigger_type: str, ban_reason: Optional[str] = None) -> dict:
    var_map = message_vars.build_base_variables(member, guild)
    var_map["membercount_ordinal"] = _ordinal(guild.member_count)

    if trigger_type == "boost":
        boost_count = guild.premium_subscription_count or 0
        remaining = _boosts_until_next_level(boost_count)
        var_map["server_boostcount"] = str(boost_count)
        var_map["server_boostlevel"] = str(guild.premium_tier)
        var_map["server_boosts_until_next_level"] = str(remaining) if remaining is not None else "Max level reached"
        if member.premium_since:
            var_map["user_boosting_since"] = f"<t:{int(member.premium_since.timestamp())}:D>"
        else:
            var_map["user_boosting_since"] = "Unknown"

    if trigger_type == "ban":
        var_map["ban_reason"] = ban_reason or "No reason provided"

    return var_map


GREETING_VARIABLE_DOCS = {
    "membercount_ordinal": "The member's join position, e.g. '214th'",
    "server_boostcount": "Total active boosts on the server (boost trigger only)",
    "server_boostlevel": "The server's current boost level, 0-3 (boost trigger only)",
    "server_boosts_until_next_level": "Boosts needed to reach the next level (boost trigger only)",
    "user_boosting_since": "The date this member started boosting (boost trigger only)",
    "ban_reason": "The reason given for the ban, if any (ban trigger only)",
}
