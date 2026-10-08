from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db

log = logging.getLogger("soward.nsfw")

SUPPORTED_CHANNEL_TYPES = (discord.TextChannel, discord.ForumChannel)

_locks: dict[int, asyncio.Lock] = {}


def guild_lock(guild_id: int) -> asyncio.Lock:
    return _locks.setdefault(guild_id, asyncio.Lock())


async def get_role_id(guild_id: int) -> Optional[int]:
    row = await db.raw_fetchone("SELECT role_id FROM nsfw_config WHERE guild_id=?", (guild_id,))
    return row["role_id"] if row else None


async def set_role_id(guild_id: int, role_id: Optional[int]) -> None:
    if role_id is None:
        await db.raw_execute("DELETE FROM nsfw_config WHERE guild_id=?", (guild_id,))
        return
    await db.raw_execute(
        "INSERT INTO nsfw_config (guild_id, role_id, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET role_id=excluded.role_id, updated_at=excluded.updated_at",
        (guild_id, role_id, time.time()),
    )


async def get_channel_ids(guild_id: int) -> list[int]:
    rows = await db.raw_fetch(
        "SELECT channel_id FROM nsfw_channels WHERE guild_id=? ORDER BY added_at, channel_id",
        (guild_id,),
    )
    return [row["channel_id"] for row in rows]


async def get_snapshots(guild_id: int) -> dict:
    rows = await db.raw_fetch(
        "SELECT channel_id, snapshot FROM nsfw_channels WHERE guild_id=? AND snapshot IS NOT NULL",
        (guild_id,),
    )
    snapshots = {}
    for row in rows:
        try:
            snapshots[str(row["channel_id"])] = json.loads(row["snapshot"])
        except (json.JSONDecodeError, TypeError):
            continue
    return snapshots


async def save_channels(guild_id: int, channel_ids: list[int], snapshots: dict, added_by: Optional[int] = None) -> None:
    existing = set(await get_channel_ids(guild_id))
    wanted = set(channel_ids)
    for channel_id in existing - wanted:
        await db.raw_execute(
            "DELETE FROM nsfw_channels WHERE guild_id=? AND channel_id=?",
            (guild_id, channel_id),
        )
    for channel_id in channel_ids:
        snapshot = snapshots.get(str(channel_id))
        await db.raw_execute(
            "INSERT INTO nsfw_channels (guild_id, channel_id, snapshot, added_by, added_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, channel_id) DO UPDATE SET snapshot=excluded.snapshot",
            (guild_id, channel_id, json.dumps(snapshot) if snapshot is not None else None, added_by, time.time()),
        )


def _base_channel(channel):
    return channel.parent if isinstance(channel, discord.Thread) and channel.parent else channel


def is_locked(channel) -> bool:
    channel = _base_channel(channel)
    return channel.permissions_for(channel.guild.default_role).view_channel is False


async def is_registered(channel) -> bool:
    channel = _base_channel(channel)
    if getattr(channel, "guild", None) is None:
        return False
    return channel.id in await get_channel_ids(channel.guild.id)


async def is_nsfw_channel(channel) -> bool:
    channel = _base_channel(channel)
    if getattr(channel, "guild", None) is None:
        return False
    if await get_role_id(channel.guild.id) is None:
        return False
    return await is_registered(channel) and is_locked(channel)


async def member_has_role(member: discord.Member) -> bool:
    role_id = await get_role_id(member.guild.id)
    return role_id is not None and any(r.id == role_id for r in member.roles)


def nsfw_only(*, require_role: bool = False):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if await get_role_id(ctx.guild.id) is None:
            raise commands.CheckFailure("NSFW isn't set up on this server yet. An admin needs to run `nsfw role` first.")
        if not await is_registered(ctx.channel):
            raise commands.CheckFailure("This command only works in a registered NSFW channel (`nsfw addchannel`).")
        if not is_locked(ctx.channel):
            raise commands.CheckFailure("This NSFW channel isn't locked to the NSFW role right now. An admin should run `nsfw sync`.")
        if require_role and not await member_has_role(ctx.author):
            raise commands.CheckFailure("You need the NSFW role to use this command.")
        return True
    return commands.check(predicate)


def _view(channel, target) -> Optional[bool]:
    return channel.overwrites_for(target).view_channel


async def _set_view(channel, target, value: Optional[bool], reason: str) -> None:
    overwrite = channel.overwrites_for(target)
    if overwrite.view_channel is value:
        return
    overwrite.view_channel = value
    if overwrite.is_empty():
        await channel.set_permissions(target, overwrite=None, reason=reason)
    else:
        await channel.set_permissions(target, overwrite=overwrite, reason=reason)


async def lock_channel(channel, role: discord.Role, snapshots: dict, reason: str) -> None:
    guild = channel.guild
    me = guild.me
    key = str(channel.id)
    entry = snapshots.get(key)
    created = entry is None
    if created:
        entry = {
            "nsfw": channel.nsfw,
            "everyone": _view(channel, guild.default_role),
            "role_id": role.id,
            "role": _view(channel, role),
        }
        if not me.guild_permissions.administrator:
            entry["me"] = _view(channel, me)
        snapshots[key] = entry
    elif entry.get("role_id") != role.id:
        old_role = guild.get_role(entry.get("role_id") or 0)
        if old_role is not None:
            await _set_view(channel, old_role, entry.get("role"), reason)
        entry["role_id"] = role.id
        entry["role"] = _view(channel, role)

    try:
        if "me" in entry:
            await _set_view(channel, me, True, reason)
        await _set_view(channel, role, True, reason)
        await _set_view(channel, guild.default_role, False, reason)
        if not channel.nsfw:
            await channel.edit(nsfw=True, reason=reason)
    except Exception:
        if created:
            try:
                await unlock_channel(guild, channel, snapshots, reason="NSFW lock failed, rolling back")
            except Exception:
                log.warning("Rollback after failed NSFW lock also failed for channel %s", channel.id, exc_info=True)
        raise


async def unlock_channel(guild: discord.Guild, channel, snapshots: dict, reason: str) -> None:
    if channel is None:
        return
    entry = snapshots.pop(str(channel.id), None)
    if entry is None:
        return
    role = guild.get_role(entry["role_id"]) if entry.get("role_id") else None
    errors = []
    steps = [(guild.default_role, entry.get("everyone"))]
    if role is not None:
        steps.append((role, entry.get("role")))
    if "me" in entry:
        steps.append((guild.me, entry["me"]))
    for target, value in steps:
        try:
            await _set_view(channel, target, value, reason)
        except Exception as exc:
            errors.append(exc)
    try:
        original_nsfw = entry.get("nsfw")
        if isinstance(original_nsfw, bool) and channel.nsfw != original_nsfw:
            await channel.edit(nsfw=original_nsfw, reason=reason)
    except Exception as exc:
        errors.append(exc)
    if errors:
        raise errors[0]
