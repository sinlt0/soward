import functools
from typing import Callable, Union

import discord
from discord.ext import commands

import config
from utils import db

async def has_fake_permission(guild_id: int, user: discord.Member, node: str) -> bool:
    user_row = await db.raw_fetchone(
        "SELECT 1 FROM fakeperm_grants WHERE guild_id=? AND target_id=? AND target_type='user' AND node IN (?, 'administrator')",
        (guild_id, user.id, node),
    )
    if user_row:
        return True

    role_ids = [r.id for r in user.roles]
    if not role_ids:
        return False
    placeholders = ",".join("?" * len(role_ids))
    row = await db.raw_fetchone(
        f"SELECT 1 FROM fakeperm_grants WHERE guild_id=? AND target_id IN ({placeholders}) AND target_type='role' AND node IN (?, 'administrator')",
        (guild_id, *role_ids, node),
    )
    return row is not None

def is_privileged():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in config.ALL_PRIVILEGED_IDS:
            return True
        if ctx.guild:
            member_role_ids = {r.id for r in ctx.author.roles}
            if member_role_ids & set(config.DEV_ROLE_IDS):
                return True
        raise commands.CheckFailure("You must be a bot developer to use this command.")

    return commands.check(predicate)

def is_owner():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in config.OWNER_IDS:
            return True
        raise commands.CheckFailure("Only the bot owner can use this command.")

    return commands.check(predicate)

def has_guild_permission(discord_perm: str, fake_node: str = None):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in config.ALL_PRIVILEGED_IDS:
            return True
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        discord_check = getattr(ctx.author.guild_permissions, discord_perm, False)
        if discord_check:
            return True

        node = fake_node or discord_perm
        if await has_fake_permission(ctx.guild.id, ctx.author, node):
            return True

        raise commands.MissingPermissions([discord_perm])

    return commands.check(predicate)

def premium_only():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in config.ALL_PRIVILEGED_IDS:
            return True
        if ctx.guild:
            row = await db.raw_fetchone(
                "SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?",
                (ctx.guild.id,),
            )
            if row and row["premium"]:
                import time
                if row["premium_expires_at"] is None or row["premium_expires_at"] > time.time():
                    return True
        raise commands.CheckFailure("This feature requires Soward Premium.")

    return commands.check(predicate)
