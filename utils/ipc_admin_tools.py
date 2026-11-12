from __future__ import annotations

import time

import discord
from aiohttp import web
from discord.ext import commands

import config
from utils import blacklist, coins as coin_store, db, dev_state
from utils.ipc_admin import _audit, _body, _bot, _owner, _staff

MAX_AMOUNT = 1_000_000_000
PROTECTED = {"help"}


def _uid_param(request: web.Request) -> int:
    raw = request.match_info["uid"]
    if not raw.isdigit() or not 5 <= len(raw) <= 25:
        raise web.HTTPNotFound(text="user")
    return int(raw)


async def _find_user(bot: commands.Bot, uid: int):
    user = bot.get_user(uid)
    if user is not None:
        return user
    try:
        return await bot.fetch_user(uid)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        raise ValueError("Discord could not look that user up right now.")


async def user_detail(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    uid = _uid_param(request)
    user = await _find_user(bot, uid)
    if user is None:
        raise web.HTTPNotFound(text="No Discord user has that ID.")
    wallet = await coin_store.balances(uid)
    ban = await db.raw_fetchone("SELECT reason, blacklisted_by, created_at FROM blacklist WHERE target_id=? AND target_type='user'", (uid,))
    mutual = []
    for guild in bot.guilds:
        if guild.get_member(uid) is not None:
            mutual.append({"id": str(guild.id), "name": guild.name, "owner": guild.owner_id == uid})
    mutual.sort(key=lambda g: (not g["owner"], g["name"].lower()))
    return web.json_response({
        "id": str(uid),
        "name": str(user),
        "display": getattr(user, "global_name", None) or user.name,
        "bot": user.bot,
        "avatar": user.display_avatar.replace(size=128).url,
        "created": user.created_at.timestamp(),
        "coins": wallet["coins"],
        "diamonds": wallet["diamonds"],
        "banned": ban is not None,
        "ban_reason": (ban["reason"] or "") if ban else "",
        "staff": "owner" if uid in config.OWNER_IDS else ("developer" if uid in config.ALL_PRIVILEGED_IDS else ""),
        "mutual": mutual[:30],
        "mutual_count": len(mutual),
    })


async def user_wallet(request: web.Request) -> web.Response:
    uid_staff = _staff(request)
    uid = _uid_param(request)
    body = await _body(request)
    currency = str(body.get("currency", ""))
    action = str(body.get("action", ""))
    if currency not in ("coins", "diamonds") or action not in ("add", "remove"):
        raise ValueError("Choose coins or diamonds, and add or remove.")
    try:
        amount = int(body.get("amount", 0))
    except (TypeError, ValueError):
        raise ValueError("Enter a whole number.")
    if not 1 <= amount <= MAX_AMOUNT:
        raise ValueError(f"The amount must be 1 to {MAX_AMOUNT:,}.")
    if action == "add":
        await (coin_store.add if currency == "coins" else coin_store.add_diamonds)(uid, amount)
    else:
        spent = await (coin_store.spend if currency == "coins" else coin_store.spend_diamonds)(uid, amount)
        if not spent:
            raise ValueError("That user does not have enough to remove.")
    wallet = await coin_store.balances(uid)
    await _audit(request, uid_staff, f"{action.title()} {amount:,} {currency} for user {uid}")
    return web.json_response({"ok": True, "message": f"{'Added' if action == 'add' else 'Removed'} {amount:,} {currency}.", "coins": wallet["coins"], "diamonds": wallet["diamonds"]})


def _resolve(bot: commands.Bot, name: str):
    name = " ".join(name.lower().split())
    command = bot.get_command(name)
    if command is None:
        raise ValueError(f"There is no command called {name}.")
    return command


async def commands_list(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    names = sorted(c.qualified_name for c in bot.walk_commands() if not c.hidden)
    return web.json_response({
        "disabled": [{"name": n, "reason": r} for n, r in sorted(dev_state.disabled.items())],
        "commands": names,
    })


async def command_disable(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    body = await _body(request)
    command = _resolve(bot, str(body.get("name", "")))
    root = command.root_parent or command
    if root.qualified_name in PROTECTED or (command.cog and command.cog.qualified_name == "Dev"):
        raise ValueError("That command cannot be turned off.")
    reason = str(body.get("reason", "")).strip()[:150]
    dev_state.disabled[command.qualified_name] = reason
    await dev_state.save_disabled()
    await _audit(request, uid, f"Command turned off: {command.qualified_name}" + (f" ({reason})" if reason else ""))
    return web.json_response({"ok": True, "message": f"{command.qualified_name} is off for everyone except owners and developers."})


async def command_enable(request: web.Request) -> web.Response:
    uid = _staff(request)
    name = " ".join(str((await _body(request)).get("name", "")).lower().split())
    if name not in dev_state.disabled:
        raise ValueError("That command is not turned off.")
    dev_state.disabled.pop(name)
    await dev_state.save_disabled()
    await _audit(request, uid, f"Command turned on: {name}")
    return web.json_response({"ok": True, "message": f"{name} is back on."})


async def database_info(request: web.Request) -> web.Response:
    _staff(request)
    tables = await db.raw_fetch("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    out = []
    for table in tables:
        name = str(table["name"]).replace('"', '""')
        row = await db.raw_fetchone(f'SELECT COUNT(*) AS c FROM "{name}"')
        out.append({"name": table["name"], "rows": int(row["c"]) if row else 0})
    backup = await db.get_last_backup_info()
    return web.json_response({
        "mongo": db.is_mongo_available(),
        "tables": out,
        "total_rows": sum(t["rows"] for t in out),
        "last_sync": float(backup["saved_at"]) if backup and backup.get("saved_at") else None,
    })


async def database_sync(request: web.Request) -> web.Response:
    uid = _staff(request)
    if not db.is_mongo_available():
        raise ValueError("MongoDB is not connected, so there is nothing to sync to.")
    from utils import mongo_sync
    results = await mongo_sync.sync_all_tables()
    upserted = sum(r.get("upserted", 0) for r in results.values())
    deleted = sum(r.get("deleted", 0) for r in results.values())
    failed = [t for t, r in results.items() if not r.get("synced")]
    await _audit(request, uid, f"MongoDB sync: {upserted} upserted, {deleted} deleted, {len(failed)} failed")
    message = f"Synced {len(results) - len(failed)}/{len(results)} tables. {upserted:,} rows upserted, {deleted:,} deleted."
    if failed:
        message += " Failed: " + ", ".join(failed[:5])
    return web.json_response({"ok": not failed, "message": message})


async def send_message(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    body = await _body(request)
    raw = str(body.get("channel_id", "")).strip()
    content = str(body.get("content", "")).strip()
    if not raw.isdigit():
        raise ValueError("Enter a valid channel ID.")
    if not 1 <= len(content) <= 2000:
        raise ValueError("The message must be 1 to 2000 characters.")
    channel = bot.get_channel(int(raw))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(raw))
        except discord.HTTPException:
            raise ValueError("Zyro cannot see that channel.")
    if not hasattr(channel, "send"):
        raise ValueError("That channel cannot receive messages.")
    try:
        sent = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused: {str(exc.text or exc)[:150]}")
    guild_id = getattr(getattr(channel, "guild", None), "id", 0) or 0
    await _audit(request, uid, f"Sent a message to channel {raw}", guild_id)
    return web.json_response({"ok": True, "message": "Message sent.", "url": sent.jump_url})


async def staff_list(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    out = []
    for uid in sorted(set(config.OWNER_IDS) | set(config.DEV_IDS)):
        user = bot.get_user(uid)
        out.append({"id": str(uid), "name": str(user) if user else "", "role": "Owner" if uid in config.OWNER_IDS else "Developer"})
    return web.json_response({"staff": out})


def register(app: web.Application) -> None:
    r = app.router
    r.add_get("/admin/user/{uid}", user_detail)
    r.add_post("/admin/user/{uid}/wallet", user_wallet)
    r.add_get("/admin/commands", commands_list)
    r.add_post("/admin/commands/disable", command_disable)
    r.add_post("/admin/commands/enable", command_enable)
    r.add_get("/admin/database", database_info)
    r.add_post("/admin/database/sync", database_sync)
    r.add_post("/admin/send", send_message)
    r.add_get("/admin/staff", staff_list)
