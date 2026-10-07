import time
from typing import Union

import discord
from discord.ext import commands

from utils import db
import config

_prefix_cache: dict[int, str] = {}
_guild_premium_cache: dict[int, bool] = {}
_guild_server_np_cache: dict[int, bool] = {}
_global_np_cache: set[int] = set()
_global_np_loaded: bool = False

async def _load_global_np_cache() -> None:
    global _global_np_loaded
    rows = await db.raw_fetch("SELECT user_id FROM global_no_prefix")
    _global_np_cache.clear()
    _global_np_cache.update(row["user_id"] for row in rows)
    _global_np_loaded = True

async def is_global_no_prefix(user_id: int) -> bool:
    if not _global_np_loaded:
        await _load_global_np_cache()
    return user_id in _global_np_cache or user_id in config.ALL_PRIVILEGED_IDS

async def add_global_no_prefix(user_id: int, added_by: int) -> None:
    await db.raw_execute(
        "INSERT OR IGNORE INTO global_no_prefix (user_id, added_by, added_at) VALUES (?, ?, ?)",
        (user_id, added_by, time.time()),
    )
    _global_np_cache.add(user_id)

async def remove_global_no_prefix(user_id: int) -> bool:
    cur = await db.raw_execute("DELETE FROM global_no_prefix WHERE user_id=?", (user_id,))
    _global_np_cache.discard(user_id)
    return cur.rowcount > 0

async def list_global_no_prefix() -> list[int]:
    if not _global_np_loaded:
        await _load_global_np_cache()
    return list(_global_np_cache)

async def _is_guild_premium(guild_id: int) -> bool:
    if guild_id in _guild_premium_cache:
        return _guild_premium_cache[guild_id]

    row = await db.raw_fetchone(
        "SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild_id,)
    )
    if not row or not row["premium"]:
        _guild_premium_cache[guild_id] = False
        return False

    if row["premium_expires_at"] and row["premium_expires_at"] < time.time():
        _guild_premium_cache[guild_id] = False
        return False

    _guild_premium_cache[guild_id] = True
    return True

def invalidate_premium_cache(guild_id: int) -> None:
    _guild_premium_cache.pop(guild_id, None)

async def _is_server_np_enabled(guild_id: int) -> bool:
    if guild_id in _guild_server_np_cache:
        return _guild_server_np_cache[guild_id]

    row = await db.raw_fetchone(
        "SELECT server_np_enabled FROM guilds WHERE guild_id=?", (guild_id,)
    )
    enabled = bool(row["server_np_enabled"]) if row else config.SERVER_NO_PREFIX_ENABLED_DEFAULT
    _guild_server_np_cache[guild_id] = enabled
    return enabled

def invalidate_server_np_cache(guild_id: int) -> None:
    _guild_server_np_cache.pop(guild_id, None)

async def get_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    prefixes = [f"<@{bot.user.id}> ", f"<@!{bot.user.id}> "]

    if message.guild is None:
        if await is_global_no_prefix(message.author.id):
            prefixes.append("")
        prefixes.append(config.DEFAULT_PREFIX)
        return prefixes

    guild_id = message.guild.id
    if guild_id not in _prefix_cache:
        row = await db.raw_fetchone(
            "SELECT prefix FROM guilds WHERE guild_id=?", (guild_id,)
        )
        _prefix_cache[guild_id] = row["prefix"] if row else config.DEFAULT_PREFIX

    prefixes.append(_prefix_cache[guild_id])

    if await is_global_no_prefix(message.author.id):
        prefixes.append("")
        return prefixes

    guild_premium = await _is_guild_premium(guild_id)
    server_np_enabled = await _is_server_np_enabled(guild_id)
    if guild_premium and server_np_enabled:
        prefixes.append("")

    return prefixes

async def set_guild_prefix(guild_id: int, prefix: str) -> None:
    _prefix_cache[guild_id] = prefix
    await db.raw_execute(
        "INSERT INTO guilds (guild_id, prefix) VALUES (?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET prefix=excluded.prefix",
        (guild_id, prefix),
    )

async def get_guild_prefix(guild_id: int) -> str:
    if guild_id in _prefix_cache:
        return _prefix_cache[guild_id]
    row = await db.raw_fetchone(
        "SELECT prefix FROM guilds WHERE guild_id=?", (guild_id,)
    )
    prefix = row["prefix"] if row else config.DEFAULT_PREFIX
    _prefix_cache[guild_id] = prefix
    return prefix

async def set_server_np_enabled(guild_id: int, enabled: bool) -> None:
    _guild_server_np_cache[guild_id] = enabled
    await db.raw_execute(
        "INSERT INTO guilds (guild_id, server_np_enabled) VALUES (?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET server_np_enabled=excluded.server_np_enabled",
        (guild_id, int(enabled)),
    )
