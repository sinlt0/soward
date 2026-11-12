from __future__ import annotations

import asyncio
import base64
import os
import platform
import sys
import time

import discord
from aiohttp import web
from discord.ext import commands

import config
from utils import blacklist, crypto_pay, db, dev_state, prefix as prefix_utils, platform_spoof, presence_rotation, slash_sync

PAGE_SIZE = 20
IMAGE_LIMIT = 8 * 1024 * 1024
BIO_LIMIT = 400
RESERVED = {"jishaku"}


def _bot(request: web.Request) -> commands.Bot:
    return request.app["bot"]


def _uid(request: web.Request) -> int:
    raw = request.headers.get("X-Zyro-User", "")
    if not raw.isdigit():
        raise web.HTTPBadRequest(text="missing user")
    return int(raw)


def _staff(request: web.Request) -> int:
    uid = _uid(request)
    if uid not in config.ALL_PRIVILEGED_IDS:
        raise web.HTTPForbidden(text="Owners and developers only.")
    return uid


def _owner(request: web.Request) -> int:
    uid = _staff(request)
    if uid not in config.OWNER_IDS:
        raise web.HTTPForbidden(text="Only bot owners can do this.")
    return uid


def _who(request: web.Request, uid: int) -> str:
    return request.headers.get("X-Zyro-Name") or str(uid)


async def _audit(request: web.Request, uid: int, summary: str, guild_id: int = 0) -> None:
    await db.raw_execute(
        "INSERT INTO dashboard_audit (guild_id, user_id, user_name, module, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, uid, _who(request, uid)[:80], "admin", summary[:400], time.time()),
    )


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _gid(request: web.Request) -> int:
    raw = request.match_info["gid"]
    if not raw.isdigit():
        raise web.HTTPNotFound(text="guild")
    return int(raw)


def _icon(guild: discord.Guild) -> str:
    return guild.icon.replace(size=128).url if guild.icon else ""


async def _premium_map() -> dict:
    rows = await db.raw_fetch("SELECT guild_id, premium_expires_at FROM guilds WHERE premium=1")
    now = time.time()
    out = {}
    for row in rows:
        expires = row["premium_expires_at"]
        if expires is None or expires > now:
            out[int(row["guild_id"])] = expires
    return out


async def _banned_map() -> dict:
    rows = await db.raw_fetch("SELECT target_id, target_type, reason, blacklisted_by, created_at FROM blacklist")
    return {
        "guild": {int(r["target_id"]): r for r in rows if r["target_type"] == "guild"},
        "user": {int(r["target_id"]): r for r in rows if r["target_type"] == "user"},
    }


def _memory_mb() -> float:
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1048576 if sys.platform == "darwin" else 1024), 1)
    except ImportError:
        return 0.0


async def apply_presence(bot: commands.Bot) -> None:
    await presence_rotation.apply(bot)


async def overview(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    premium = await _premium_map()
    banned = await _banned_map()
    now = time.time()
    audit = await db.raw_fetch("SELECT guild_id, user_name, summary, created_at FROM dashboard_audit WHERE module='admin' ORDER BY created_at DESC LIMIT 15")
    keys = await db.raw_fetchone("SELECT COUNT(*) AS n FROM premium_keys WHERE used=0")
    return web.json_response({
        "ready": bot.is_ready(),
        "latency_ms": round(bot.latency * 1000) if bot.is_ready() else 0,
        "uptime": int(now - getattr(bot, "start_time", now)),
        "guilds": len(bot.guilds),
        "members": sum(g.member_count or 0 for g in bot.guilds),
        "commands": len({c for c in bot.walk_commands() if not c.hidden}),
        "cogs": len(bot.cogs),
        "extensions": len(bot.extensions),
        "memory_mb": _memory_mb(),
        "python": platform.python_version(),
        "discord_py": discord.__version__,
        "premium_guilds": len(premium),
        "expiring_soon": sum(1 for e in premium.values() if e is not None and e - now < 7 * 86400),
        "unused_keys": int(keys["n"]) if keys else 0,
        "banned_guilds": len(banned["guild"]),
        "banned_users": len(banned["user"]),
        "maintenance": dict(dev_state.maintenance),
        "dashboard_enabled": await _dashboard_global(),
        "presence": presence_rotation.current(),
        "audit": [{"guild_id": str(r["guild_id"]), "user": r["user_name"], "summary": r["summary"], "at": r["created_at"]} for r in audit],
    })


async def _dashboard_global() -> bool:
    from utils import ipc_server
    return await ipc_server.global_enabled()


async def profile_get(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    user = bot.user
    description = ""
    try:
        data = await bot.http.request(discord.http.Route("GET", "/applications/@me"))
        description = str(data.get("description") or "")
    except discord.HTTPException:
        pass
    return web.json_response({
        "id": str(user.id) if user else "",
        "name": user.name if user else config.BOT_NAME,
        "avatar": user.display_avatar.replace(size=256).url if user else "",
        "banner": user.banner.replace(size=512).url if user and user.banner else "",
        "description": description,
        "presence": presence_rotation.current(),
        "placeholders": presence_rotation.PLACEHOLDERS,
        "platforms": platform_spoof.LABELS,
        "platform_active": platform_spoof.active,
        "default_items": [i["text"] for i in presence_rotation.DEFAULT_ITEMS],
        "limits": {"min": presence_rotation.MIN_INTERVAL, "max": presence_rotation.MAX_INTERVAL, "items": presence_rotation.MAX_ITEMS},
        "can_edit": _uid(request) in config.OWNER_IDS,
    })


def _image(value) -> bytes | None:
    if not value:
        return None
    if isinstance(value, str) and "," in value[:80]:
        value = value.split(",", 1)[1]
    try:
        raw = base64.b64decode(value, validate=False)
    except Exception:
        raise ValueError("That image could not be read.")
    if len(raw) > IMAGE_LIMIT:
        raise ValueError("Images must be 8 MB or smaller.")
    if not (raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8") or raw.startswith(b"GIF8") or raw.startswith(b"RIFF")):
        raise ValueError("Use a PNG, JPG, GIF or WebP image.")
    return raw


async def profile_update(request: web.Request) -> web.Response:
    uid = _owner(request)
    bot = _bot(request)
    body = await _body(request)
    edits: dict = {}
    changed: list[str] = []
    username = str(body.get("username", "")).strip()
    if username and username != bot.user.name:
        if not 2 <= len(username) <= 32:
            raise ValueError("The name must be 2 to 32 characters.")
        edits["username"] = username
        changed.append("name")
    if body.get("avatar"):
        edits["avatar"] = _image(body["avatar"])
        changed.append("avatar")
    elif body.get("remove_avatar"):
        edits["avatar"] = None
        changed.append("avatar removed")
    if body.get("banner"):
        edits["banner"] = _image(body["banner"])
        changed.append("banner")
    elif body.get("remove_banner"):
        edits["banner"] = None
        changed.append("banner removed")
    try:
        if edits:
            await bot.user.edit(**edits)
        if "description" in body:
            description = str(body["description"]).strip()
            if len(description) > BIO_LIMIT:
                raise ValueError(f"The bio can be at most {BIO_LIMIT} characters.")
            await bot.http.request(discord.http.Route("PATCH", "/applications/@me"), json={"description": description})
            changed.append("bio")
    except discord.HTTPException as exc:
        raise ValueError(f"Discord refused the change: {str(exc.text or exc)[:200]}")
    if not changed:
        raise ValueError("Nothing to change.")
    await _audit(request, uid, "Bot profile updated: " + ", ".join(changed))
    return web.json_response({"ok": True, "message": "Updated " + ", ".join(changed) + ".", "avatar": bot.user.display_avatar.replace(size=256).url})


async def presence_update(request: web.Request) -> web.Response:
    uid = _staff(request)
    body = await _body(request)
    saved = presence_rotation.current()
    if "platform" not in body:
        body["platform"] = saved["platform"]
    data = presence_rotation.validate(body)
    if data["platform"] != saved["platform"] and uid not in config.OWNER_IDS:
        raise web.HTTPForbidden(text="Only bot owners can change the platform.")
    await presence_rotation.save(data)
    platform_spoof.select(data["platform"])
    await presence_rotation.reset(_bot(request))
    if data["mode"] == "off":
        shown = "no activity"
    elif data["mode"] == "default":
        shown = "built-in rotation"
    else:
        shown = f"rotating {len(data['items'])} every {data['interval']}s" if data["rotate"] else "single activity"
    await _audit(request, uid, f"Presence set: {data['status']}, {shown}, platform {data['platform']}")
    message = "Presence updated."
    if data["platform"] != platform_spoof.active:
        message += " The platform changes after the next restart."
    return web.json_response({"ok": True, "message": message})


def _guild_row(guild: discord.Guild, premium: dict, banned: dict) -> dict:
    expires = premium.get(guild.id)
    return {
        "id": str(guild.id),
        "name": guild.name,
        "icon": _icon(guild),
        "members": guild.member_count or 0,
        "owner_id": str(guild.owner_id),
        "joined": guild.me.joined_at.timestamp() if guild.me and guild.me.joined_at else 0,
        "premium": guild.id in premium,
        "expires": expires,
        "banned": guild.id in banned["guild"],
    }


async def guilds_list(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    q = request.query.get("q", "").strip().lower()
    flt = request.query.get("filter", "all")
    sort = request.query.get("sort", "members")
    page = max(1, int(request.query.get("page", "1") or 1)) if request.query.get("page", "1").isdigit() else 1
    premium = await _premium_map()
    banned = await _banned_map()
    rows = [_guild_row(g, premium, banned) for g in bot.guilds]
    total_members = sum(r["members"] for r in rows)
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q == r["id"] or q == r["owner_id"]]
    if flt == "premium":
        rows = [r for r in rows if r["premium"]]
    elif flt == "banned":
        rows = [r for r in rows if r["banned"]]
    elif flt == "free":
        rows = [r for r in rows if not r["premium"]]
    keys = {"members": lambda r: (-r["members"], r["name"].lower()), "name": lambda r: r["name"].lower(), "newest": lambda r: -r["joined"], "oldest": lambda r: r["joined"]}
    rows.sort(key=keys.get(sort, keys["members"]))
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(page, pages)
    chunk = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    return web.json_response({"guilds": chunk, "total": len(rows), "page": page, "pages": pages, "all_guilds": len(bot.guilds), "all_members": total_members, "premium": len(premium), "filter": flt, "sort": sort, "q": q})


async def guild_detail(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    gid = _gid(request)
    guild = bot.get_guild(gid)
    premium = await _premium_map()
    banned = await _banned_map()
    row = await db.raw_fetchone("SELECT premium, premium_expires_at, prefix FROM guilds WHERE guild_id=?", (gid,))
    from utils import ipc_server
    ban = banned["guild"].get(gid)
    base = {
        "id": str(gid),
        "present": guild is not None,
        "premium": gid in premium,
        "expires": premium.get(gid),
        "lifetime": bool(row and row["premium"] and row["premium_expires_at"] is None),
        "banned": ban is not None,
        "ban_reason": ban["reason"] if ban else "",
        "dashboard_enabled": await ipc_server.guild_enabled(gid),
        "prefix": row["prefix"] if row else "",
    }
    if guild is None:
        base.update({"name": f"Server {gid}", "icon": ""})
        return web.json_response(base)
    tickets = await db.raw_fetchone("SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND status='open'", (gid,))
    owner = guild.get_member(guild.owner_id)
    bots = sum(1 for m in guild.members if m.bot)
    base.update({
        "name": guild.name,
        "icon": _icon(guild),
        "owner_id": str(guild.owner_id),
        "owner_name": str(owner) if owner else "",
        "members": guild.member_count or 0,
        "bots": bots,
        "text_channels": len(guild.text_channels),
        "voice_channels": len(guild.voice_channels),
        "categories": len(guild.categories),
        "roles": len(guild.roles),
        "emojis": len(guild.emojis),
        "boosts": guild.premium_subscription_count or 0,
        "boost_tier": guild.premium_tier,
        "created": guild.created_at.timestamp(),
        "joined": guild.me.joined_at.timestamp() if guild.me and guild.me.joined_at else 0,
        "locale": str(guild.preferred_locale),
        "verification": str(guild.verification_level).title(),
        "features": sorted(guild.features)[:12],
        "open_tickets": int(tickets["n"]) if tickets else 0,
        "bot_admin": bool(guild.me and guild.me.guild_permissions.administrator),
        "shard": guild.shard_id,
    })
    return web.json_response(base)


async def guild_invite(request: web.Request) -> web.Response:
    uid = _staff(request)
    guild = _bot(request).get_guild(_gid(request))
    if guild is None:
        raise web.HTTPNotFound(text="Zyro is not in that server.")
    body = await _body(request)
    hours = float(body.get("hours", 1))
    uses = int(body.get("uses", 1))
    if not 0 <= hours <= 168 or not 0 <= uses <= 100:
        raise ValueError("Hours can be 0 to 168 (0 never expires) and uses 0 to 100 (0 unlimited).")
    me = guild.me
    candidates = [guild.system_channel, guild.rules_channel, guild.public_updates_channel] + list(guild.text_channels) + list(guild.voice_channels)
    for channel in candidates:
        if channel is None or me is None or not channel.permissions_for(me).create_instant_invite:
            continue
        try:
            invite = await channel.create_invite(max_age=int(hours * 3600), max_uses=uses, unique=True, reason=f"Dashboard admin {uid}")
        except discord.HTTPException:
            continue
        await _audit(request, uid, f"Invite created for {guild.name}", guild.id)
        return web.json_response({"ok": True, "message": "Invite created.", "url": invite.url})
    raise ValueError("Zyro needs Create Invite in at least one channel there.")


async def guild_leave(request: web.Request) -> web.Response:
    uid = _staff(request)
    guild = _bot(request).get_guild(_gid(request))
    if guild is None:
        raise web.HTTPNotFound(text="Zyro is not in that server.")
    name = guild.name
    try:
        await guild.leave()
    except discord.HTTPException as exc:
        raise ValueError(f"Could not leave: {str(exc.text or exc)[:150]}")
    await _audit(request, uid, f"Left server {name}", guild.id)
    return web.json_response({"ok": True, "message": f"Left {name}."})


async def guild_ban(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    gid = _gid(request)
    body = await _body(request)
    reason = str(body.get("reason", "")).strip()[:200] or "No reason provided"
    guild = bot.get_guild(gid)
    label = f"{guild.name}: {reason}" if guild else reason
    await blacklist.add(gid, "guild", label[:200], uid)
    left = False
    if guild:
        try:
            await guild.leave()
            left = True
        except discord.HTTPException:
            pass
    await _audit(request, uid, f"Banned server {guild.name if guild else gid}: {reason}", gid)
    return web.json_response({"ok": True, "message": "Server banned." + (" Zyro left it." if left else "")})


async def guild_unban(request: web.Request) -> web.Response:
    uid = _staff(request)
    gid = _gid(request)
    if not await blacklist.remove(gid, "guild"):
        raise ValueError("That server is not banned.")
    await _audit(request, uid, "Unbanned server", gid)
    return web.json_response({"ok": True, "message": "Server unbanned."})


async def guild_dashboard(request: web.Request) -> web.Response:
    uid = _staff(request)
    from utils import ipc_server
    gid = _gid(request)
    enabled = bool((await _body(request)).get("enabled"))
    await ipc_server.set_guild_enabled(gid, enabled)
    await _audit(request, uid, f"Dashboard access for the server: {'on' if enabled else 'off'}", gid)
    return web.json_response({"ok": True, "message": f"Dashboard access {'on' if enabled else 'off'} for that server."})


def _days(body: dict) -> int | None:
    if body.get("lifetime"):
        return None
    raw = str(body.get("days", "")).strip().lower()
    if raw in config.PREMIUM_DURATION_PRESETS:
        return config.PREMIUM_DURATION_PRESETS[raw]
    if raw.isdigit() and 1 <= int(raw) <= 3650:
        return int(raw)
    raise ValueError("Enter a number of days from 1 to 3650, or choose lifetime.")


async def guild_premium(request: web.Request) -> web.Response:
    uid = _staff(request)
    gid = _gid(request)
    body = await _body(request)
    action = str(body.get("action", ""))
    if action == "revoke":
        await db.raw_execute("UPDATE guilds SET premium=0, premium_expires_at=NULL WHERE guild_id=?", (gid,))
        prefix_utils.invalidate_premium_cache(gid)
        await _audit(request, uid, "Premium revoked", gid)
        return web.json_response({"ok": True, "message": "Premium revoked."})
    if action != "grant":
        raise ValueError("Unknown premium action.")
    days = _days(body)
    row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (gid,))
    if row and row["premium"] and row["premium_expires_at"] is None and days is not None:
        raise ValueError("This server already has lifetime Premium. Revoke it first to set a timed plan.")
    expires = await crypto_pay.grant_server(gid, days)
    await _audit(request, uid, "Premium granted: " + ("lifetime" if days is None else f"{days} days"), gid)
    until = "lifetime" if expires is None else "until " + time.strftime("%Y-%m-%d", time.gmtime(expires)) + " UTC"
    return web.json_response({"ok": True, "message": f"Premium granted ({until}).", "expires": expires})


async def premium_overview(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    rows = await db.raw_fetch("SELECT guild_id, premium_expires_at FROM guilds WHERE premium=1")
    now = time.time()
    banned = await _banned_map()
    guilds = []
    for row in rows:
        expires = row["premium_expires_at"]
        active = expires is None or expires > now
        gid = int(row["guild_id"])
        guild = bot.get_guild(gid)
        guilds.append({
            "id": str(gid), "name": guild.name if guild else f"Server {gid}", "icon": _icon(guild) if guild else "",
            "present": guild is not None, "members": guild.member_count if guild else 0,
            "expires": expires, "active": active, "lifetime": expires is None, "banned": gid in banned["guild"],
        })
    guilds.sort(key=lambda g: (not g["active"], g["expires"] is not None, g["expires"] or 0))
    keys = await db.raw_fetch("SELECT key_id, duration_days, duration_label, used, used_by, used_at, created_by, created_at FROM premium_keys ORDER BY used ASC, created_at DESC LIMIT 200")
    return web.json_response({
        "guilds": guilds,
        "active": sum(1 for g in guilds if g["active"]),
        "lifetime": sum(1 for g in guilds if g["lifetime"]),
        "expired": sum(1 for g in guilds if not g["active"]),
        "expiring": sum(1 for g in guilds if g["active"] and g["expires"] and g["expires"] - now < 7 * 86400),
        "keys": [{"key": k["key_id"], "label": k["duration_label"], "days": k["duration_days"], "used": bool(k["used"]), "used_by": str(k["used_by"]) if k["used_by"] else "", "used_at": k["used_at"], "created_at": k["created_at"]} for k in keys],
        "presets": list(config.PREMIUM_DURATION_PRESETS),
    })


async def premium_keys_create(request: web.Request) -> web.Response:
    uid = _staff(request)
    body = await _body(request)
    count = int(body.get("count", 1) or 1)
    if not 1 <= count <= 25:
        raise ValueError("Create between 1 and 25 keys at once.")
    days = _days(body)
    label = "lifetime" if days is None else str(body.get("days")).strip().lower()
    made = [await crypto_pay.create_key(days, label, uid) for _ in range(count)]
    await _audit(request, uid, f"Generated {count} premium key(s): {label}")
    return web.json_response({"ok": True, "message": f"Created {count} key(s).", "keys": made})


async def premium_keys_delete(request: web.Request) -> web.Response:
    uid = _staff(request)
    key = str((await _body(request)).get("key", "")).upper().strip()
    row = await db.raw_fetchone("SELECT used FROM premium_keys WHERE key_id=?", (key,))
    if not row:
        raise ValueError("That key does not exist.")
    if row["used"]:
        raise ValueError("Used keys are kept as a record and cannot be deleted.")
    await db.raw_execute("DELETE FROM premium_keys WHERE key_id=?", (key,))
    await _audit(request, uid, f"Deleted unused premium key {key[:9]}...")
    return web.json_response({"ok": True, "message": "Key deleted."})


async def bans_list(request: web.Request) -> web.Response:
    _staff(request)
    bot = _bot(request)
    banned = await _banned_map()

    def rows(kind: str) -> list:
        out = []
        for tid, r in banned[kind].items():
            guild = bot.get_guild(tid) if kind == "guild" else None
            user = bot.get_user(tid) if kind == "user" else None
            out.append({"id": str(tid), "name": guild.name if guild else (str(user) if user else ""), "reason": r["reason"] or "", "by": str(r["blacklisted_by"] or ""), "at": r["created_at"]})
        out.sort(key=lambda x: -(x["at"] or 0))
        return out

    return web.json_response({"users": rows("user"), "guilds": rows("guild")})


async def bans_add(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    body = await _body(request)
    kind = str(body.get("type", ""))
    target = str(body.get("id", "")).strip()
    reason = str(body.get("reason", "")).strip()[:200] or "No reason provided"
    if kind not in ("user", "guild") or not target.isdigit():
        raise ValueError("Enter a valid type and numeric ID.")
    tid = int(target)
    if kind == "user" and (tid in config.ALL_PRIVILEGED_IDS):
        raise ValueError("Owners and developers cannot be banned.")
    left = False
    if kind == "guild":
        guild = bot.get_guild(tid)
        if guild:
            reason_label = f"{guild.name}: {reason}"[:200]
            await blacklist.add(tid, "guild", reason_label, uid)
            try:
                await guild.leave()
                left = True
            except discord.HTTPException:
                pass
        else:
            await blacklist.add(tid, "guild", reason, uid)
    else:
        await blacklist.add(tid, "user", reason, uid)
    await _audit(request, uid, f"Banned {kind} {tid}: {reason}", tid if kind == "guild" else 0)
    return web.json_response({"ok": True, "message": f"{kind.title()} banned." + (" Zyro left the server." if left else "")})


async def bans_remove(request: web.Request) -> web.Response:
    uid = _staff(request)
    body = await _body(request)
    kind = str(body.get("type", ""))
    target = str(body.get("id", "")).strip()
    if kind not in ("user", "guild") or not target.isdigit():
        raise ValueError("Enter a valid type and numeric ID.")
    if not await blacklist.remove(int(target), kind):
        raise ValueError("That target is not banned.")
    await _audit(request, uid, f"Unbanned {kind} {target}", int(target) if kind == "guild" else 0)
    return web.json_response({"ok": True, "message": f"{kind.title()} unbanned."})


async def maintenance_set(request: web.Request) -> web.Response:
    uid = _staff(request)
    body = await _body(request)
    on = bool(body.get("on"))
    reason = str(body.get("reason", "")).strip()[:200]
    await dev_state.set_maintenance(on, reason)
    await _audit(request, uid, "Maintenance " + ("on" + (f": {reason}" if reason else "") if on else "off"))
    return web.json_response({"ok": True, "message": "Maintenance is " + ("on." if on else "off.")})


async def dashboard_set(request: web.Request) -> web.Response:
    uid = _staff(request)
    from utils import ipc_server
    enabled = bool((await _body(request)).get("enabled"))
    await ipc_server.set_global_enabled(enabled)
    await _audit(request, uid, f"Dashboard for all servers: {'on' if enabled else 'off'}")
    return web.json_response({"ok": True, "message": f"Dashboard is {'on' if enabled else 'off'} for every server."})


async def extensions_list(request: web.Request) -> web.Response:
    _staff(request)
    names = sorted(n.split(".")[-1] for n in _bot(request).extensions if n not in RESERVED)
    return web.json_response({"cogs": names})


async def reload_cogs(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    name = str((await _body(request)).get("name", "all")).strip() or "all"
    loaded = sorted(n for n in bot.extensions if n not in RESERVED)
    targets = loaded if name == "all" else [n for n in loaded if n == name or n.split(".")[-1] == name]
    if not targets:
        raise ValueError(f"No loaded cog called {name}.")
    done, failed = 0, []
    for target in targets:
        try:
            await bot.reload_extension(target)
            done += 1
        except Exception as exc:
            failed.append(f"{target.split('.')[-1]}: {str(exc)[:80]}")
    await _audit(request, uid, f"Reloaded {done} cog(s)" + (f", {len(failed)} failed" if failed else ""))
    return web.json_response({"ok": not failed, "message": f"Reloaded {done} cog(s)." + (" Failed: " + "; ".join(failed[:3]) if failed else "")})


async def slash_sync_now(request: web.Request) -> web.Response:
    uid = _staff(request)
    bot = _bot(request)
    try:
        await slash_sync.sync(bot)
        await db.set("slash", "version", slash_sync.digest(bot))
    except discord.HTTPException as exc:
        raise ValueError(f"Sync failed: {str(exc.text or exc)[:150]}")
    await _audit(request, uid, "Slash commands synced")
    return web.json_response({"ok": True, "message": f"{len(bot.tree.get_commands())} slash commands are live."})


async def logs_tail(request: web.Request) -> web.Response:
    _staff(request)
    lines = max(10, min(int(request.query.get("lines", "200") or 200), 1000)) if request.query.get("lines", "200").isdigit() else 200
    try:
        with open("bot.log", "r", encoding="utf-8", errors="replace") as handle:
            tail = handle.readlines()[-lines:]
    except OSError:
        return web.json_response({"text": ""})
    text = "".join(tail)
    if config.BOT_TOKEN:
        text = text.replace(config.BOT_TOKEN, "[token]")
    return web.json_response({"text": text[-60000:]})


async def restart(request: web.Request) -> web.Response:
    uid = _owner(request)
    bot = _bot(request)
    await _audit(request, uid, "Bot restart requested")

    async def go():
        await asyncio.sleep(1.5)
        try:
            await bot.close()
        except Exception:
            pass
        import logging
        logging.shutdown()
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except OSError:
            os._exit(1)

    asyncio.get_event_loop().create_task(go())
    return web.json_response({"ok": True, "message": "Restarting. The page will work again in a moment."})


def register(app: web.Application) -> None:
    r = app.router
    r.add_get("/admin/overview", overview)
    r.add_get("/admin/profile", profile_get)
    r.add_post("/admin/profile", profile_update)
    r.add_post("/admin/presence", presence_update)
    r.add_get("/admin/guilds", guilds_list)
    r.add_get("/admin/guild/{gid}", guild_detail)
    r.add_post("/admin/guild/{gid}/invite", guild_invite)
    r.add_post("/admin/guild/{gid}/leave", guild_leave)
    r.add_post("/admin/guild/{gid}/ban", guild_ban)
    r.add_post("/admin/guild/{gid}/unban", guild_unban)
    r.add_post("/admin/guild/{gid}/dashboard", guild_dashboard)
    r.add_post("/admin/guild/{gid}/premium", guild_premium)
    r.add_get("/admin/premium", premium_overview)
    r.add_post("/admin/premium/keys", premium_keys_create)
    r.add_post("/admin/premium/keys/delete", premium_keys_delete)
    r.add_get("/admin/bans", bans_list)
    r.add_post("/admin/bans/add", bans_add)
    r.add_post("/admin/bans/remove", bans_remove)
    r.add_post("/admin/maintenance", maintenance_set)
    r.add_post("/admin/dashboard", dashboard_set)
    r.add_get("/admin/cogs", extensions_list)
    r.add_post("/admin/reload", reload_cogs)
    r.add_post("/admin/slashsync", slash_sync_now)
    r.add_get("/admin/logs", logs_tail)
    r.add_post("/admin/restart", restart)
