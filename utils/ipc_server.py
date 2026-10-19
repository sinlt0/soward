from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time

import discord
from aiohttp import web
from discord.ext import commands

import config
from utils import db, dashboard_modules as dm, guild_settings, prefix as prefix_utils
from utils.dash import ActionContext

log = logging.getLogger("soward.ipc")

_start_time = time.time()
_global_key = ("dashboard", "global_enabled")


async def global_enabled() -> bool:
    row = await db.raw_fetchone("SELECT value FROM kv WHERE ns=? AND key=?", _global_key)
    if row is None:
        return config.DASHBOARD_ENABLED_DEFAULT
    return row["value"] == "1"


async def set_global_enabled(enabled: bool) -> None:
    await db.raw_execute(
        "INSERT INTO kv (ns, key, value, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(ns, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (*_global_key, "1" if enabled else "0", time.time()),
    )


async def guild_enabled(guild_id: int) -> bool:
    return bool(await guild_settings.get(guild_id, "dashboard_enabled", True))


async def set_guild_enabled(guild_id: int, enabled: bool) -> None:
    await guild_settings.set(guild_id, "dashboard_enabled", bool(enabled))


async def record_audit(guild_id: int, user_id: int, user_name: str, module: str, summary: str) -> None:
    await db.raw_execute(
        "INSERT INTO dashboard_audit (guild_id, user_id, user_name, module, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, user_id, user_name[:80], module, summary[:400], time.time()),
    )


def _err(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


@web.middleware
async def _auth(request: web.Request, handler):
    secret = request.app["secret"]
    given = request.headers.get("X-Soward-Secret", "")
    if not secret or not hmac.compare_digest(given.encode(), secret.encode()):
        return _err("Unauthorized.", 401)
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception:
        log.error("IPC handler failed for %s", request.path, exc_info=True)
        return _err("Internal error.", 500)


def _bot(request: web.Request) -> commands.Bot:
    return request.app["bot"]


def _user_id(request: web.Request) -> int:
    raw = request.headers.get("X-Soward-User", "")
    if not raw.isdigit():
        raise web.HTTPBadRequest(text="missing user")
    return int(raw)


async def _authorize(request: web.Request) -> tuple[discord.Guild, int, str]:
    bot = _bot(request)
    uid = _user_id(request)
    guild = bot.get_guild(int(request.match_info["gid"]))
    if guild is None:
        raise web.HTTPNotFound(text="guild")
    privileged = uid in config.ALL_PRIVILEGED_IDS
    if not await global_enabled() and not privileged:
        raise web.HTTPServiceUnavailable(text="global_off")
    if not await guild_enabled(guild.id) and not privileged:
        raise web.HTTPForbidden(text="guild_off")
    name = str(uid)
    if privileged:
        return guild, uid, name
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except discord.HTTPException:
            member = None
    if member is None:
        raise web.HTTPForbidden(text="not_member")
    perms = member.guild_permissions
    if not (guild.owner_id == uid or perms.administrator or perms.manage_guild):
        raise web.HTTPForbidden(text="no_permission")
    return guild, uid, str(member)


def _http_error(exc: web.HTTPException) -> web.Response:
    return _err(exc.text or exc.reason, exc.status)


@web.middleware
async def _http_errors(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException as exc:
        return _http_error(exc)


async def status(request: web.Request) -> web.Response:
    bot = _bot(request)
    ready = bot.is_ready()
    return web.json_response({
        "ready": ready,
        "name": config.BOT_NAME,
        "version": config.BOT_VERSION,
        "user_id": str(bot.user.id) if bot.user else None,
        "avatar": bot.user.display_avatar.replace(size=256).url if ready and bot.user else "",
        "guilds": len(bot.guilds) if ready else 0,
        "users": sum(g.member_count or 0 for g in bot.guilds) if ready else 0,
        "latency_ms": round(bot.latency * 1000) if ready else 0,
        "uptime": int(time.time() - _start_time),
        "commands": len({c for c in bot.walk_commands() if not c.hidden}) if ready else 0,
        "dashboard_enabled": await global_enabled(),
    })


def _command_usage(command: commands.Command) -> str:
    return f"{command.qualified_name} {command.signature}".strip()


def _command_perms(command: commands.Command) -> list[str]:
    found = []
    for check in command.checks:
        name = getattr(check, "__qualname__", "")
        for cell in (getattr(check, "__closure__", None) or []):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, str) and value.replace("_", "").isalpha() and hasattr(discord.Permissions, value):
                found.append(value.replace("_", " ").title())
        if "guild_only" in name:
            continue
    return sorted(set(found))


async def command_catalog(request: web.Request) -> web.Response:
    from cogs.help import CATEGORY_DESCRIPTIONS

    bot = _bot(request)
    categories: dict[str, dict] = {}
    for command in sorted(bot.walk_commands(), key=lambda c: c.qualified_name):
        if command.hidden or command.qualified_name.split(" ")[0] in ("jsk", "jishaku"):
            continue
        cog = command.cog
        category = getattr(cog, "category", None) or command.cog_name or "Other"
        if category in config.HELP_HIDDEN_CATEGORIES:
            continue
        entry = categories.setdefault(category, {
            "name": category, "description": CATEGORY_DESCRIPTIONS.get(category, ""), "commands": [],
        })
        entry["commands"].append({
            "name": command.qualified_name,
            "module": command.cog_name or "",
            "usage": _command_usage(command),
            "help": (command.help or "").strip(),
            "aliases": list(command.aliases),
            "permissions": _command_perms(command),
        })
    ordered = sorted(categories.values(), key=lambda c: c["name"])
    return web.json_response({"categories": ordered})


async def team(request: web.Request) -> web.Response:
    bot = _bot(request)
    out = []
    seen = set()
    for role, ids in (("Owner", config.OWNER_IDS), ("Developer", config.DEV_IDS)):
        for uid in ids:
            if uid in seen:
                continue
            seen.add(uid)
            try:
                user = await bot.fetch_user(uid)
                out.append({"id": str(uid), "name": str(user), "avatar": user.display_avatar.replace(size=128).url, "role": role})
            except discord.HTTPException:
                out.append({"id": str(uid), "name": f"User {uid}", "avatar": "", "role": role})
    return web.json_response({"team": out})


async def guilds_present(request: web.Request) -> web.Response:
    bot = _bot(request)
    body = await request.json()
    ids = [int(x) for x in body.get("ids", []) if str(x).isdigit()]
    present = {}
    for gid in ids:
        guild = bot.get_guild(gid)
        if guild is not None:
            present[str(gid)] = {"member_count": guild.member_count or 0}
    return web.json_response({"present": present, "global_enabled": await global_enabled()})


async def guild_overview(request: web.Request) -> web.Response:
    guild, uid, _ = await _authorize(request)
    from utils import tickets as ticket_utils

    premium_row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild.id,))
    premium = await ticket_utils.is_premium(guild.id)
    return web.json_response({
        "id": str(guild.id),
        "name": guild.name,
        "icon": guild.icon.replace(size=128).url if guild.icon else "",
        "member_count": guild.member_count or 0,
        "prefix": await prefix_utils.get_guild_prefix(guild.id),
        "premium": premium,
        "premium_expires_at": premium_row["premium_expires_at"] if premium_row and premium else None,
        "server_np": await prefix_utils._is_server_np_enabled(guild.id),
        "dashboard_enabled": await guild_enabled(guild.id),
        "modules": await dm.module_summary(guild),
        "categories": dm.CATEGORY_ORDER,
    })


async def guild_settings_update(request: web.Request) -> web.Response:
    guild, uid, name = await _authorize(request)
    body = await request.json()
    changes = []
    if "prefix" in body:
        value = str(body["prefix"]).strip()
        if not value or len(value) > 5 or " " in value:
            raise ValueError("Prefix must be 1 to 5 characters with no spaces.")
        if value != await prefix_utils.get_guild_prefix(guild.id):
            await prefix_utils.set_guild_prefix(guild.id, value)
            changes.append(f"Prefix: {value}")
    if "server_np" in body:
        enabled = bool(body["server_np"])
        if not await _premium(guild.id) and enabled:
            raise ValueError("No-prefix mode needs Premium.")
        if enabled != await prefix_utils._is_server_np_enabled(guild.id):
            await prefix_utils.set_server_np_enabled(guild.id, enabled)
            changes.append(f"No-prefix mode: {'on' if enabled else 'off'}")
    if "dashboard_enabled" in body:
        enabled = bool(body["dashboard_enabled"])
        if enabled != await guild_enabled(guild.id):
            await set_guild_enabled(guild.id, enabled)
            changes.append(f"Dashboard access: {'on' if enabled else 'off'}")
    if changes:
        await record_audit(guild.id, uid, name, "server", "; ".join(changes))
    return web.json_response({"changes": changes})


async def _premium(guild_id: int) -> bool:
    from utils import tickets as ticket_utils

    return await ticket_utils.is_premium(guild_id)


def _module(request: web.Request) -> dm.Module:
    module = dm.MODULE_INDEX.get(request.match_info["key"])
    if module is None:
        raise web.HTTPNotFound(text="module")
    return module


async def module_get(request: web.Request) -> web.Response:
    guild, _, _ = await _authorize(request)
    module = _module(request)
    detail = await dm.module_detail(guild, module)
    detail.update(dm.guild_choices(guild))
    return web.json_response(detail)


async def module_save(request: web.Request) -> web.Response:
    guild, uid, name = await _authorize(request)
    module = _module(request)
    body = await request.json()
    changes = await dm.apply_module(guild, module, body.get("values", {}))
    if changes:
        await record_audit(guild.id, uid, name, module.key, "; ".join(changes))
    return web.json_response({"changes": changes})


async def module_toggle(request: web.Request) -> web.Response:
    guild, uid, name = await _authorize(request)
    module = _module(request)
    body = await request.json()
    enabled = bool(body.get("enabled"))
    changed = await dm.set_toggle(guild, module, enabled)
    if changed:
        await record_audit(guild.id, uid, name, module.key, f"{module.name}: {'enabled' if enabled else 'disabled'}")
    return web.json_response({"enabled": enabled, "changed": changed})


async def module_action(request: web.Request) -> web.Response:
    guild, uid, name = await _authorize(request)
    module = _module(request)
    body = await request.json()
    ctx = ActionContext(bot=_bot(request), guild=guild, user_id=uid, user_name=name)
    changes = await dm.run_action(ctx, module, body)
    if changes:
        await record_audit(guild.id, uid, name, module.key, "; ".join(changes))
    detail = await dm.module_detail(guild, module)
    return web.json_response({"changes": changes, "sections": detail["sections"]})


async def audit_list(request: web.Request) -> web.Response:
    guild, _, _ = await _authorize(request)
    rows = await db.raw_fetch(
        "SELECT user_id, user_name, module, summary, created_at FROM dashboard_audit WHERE guild_id=?"
        " ORDER BY entry_id DESC LIMIT ?",
        (guild.id, config.DASHBOARD_AUDIT_PAGE_SIZE),
    )
    return web.json_response({"entries": [
        {"user_id": str(r["user_id"]), "user": r["user_name"], "module": r["module"],
         "summary": r["summary"], "at": r["created_at"]} for r in rows
    ]})


async def public_verify_info(request: web.Request) -> web.Response:
    from utils import web_verify
    info = await web_verify.lookup_token(request.match_info["token"])
    if info is None:
        return _err("invalid", 404)
    guild = _bot(request).get_guild(info["guild_id"])
    return web.json_response({"guild": guild.name if guild else "the server"})


async def public_verify_complete(request: web.Request) -> web.Response:
    import ipaddress
    cog = _bot(request).get_cog("Verification")
    if cog is None:
        return _err("Verification is unavailable.", 503)
    body = await request.json()
    try:
        ip = str(ipaddress.ip_address(str(body.get("ip", ""))))
    except ValueError:
        return _err("Could not read your address.", 400)
    result = await cog.web_complete(request.match_info["token"], ip, str(body.get("fingerprint", ""))[:128])
    return web.json_response(result)


async def public_websub_verify(request: web.Request) -> web.Response:
    cog = _bot(request).get_cog("Alerts")
    if cog is None:
        return _err("Unavailable.", 503)
    query = request.query
    challenge = await cog.websub_verify(
        query.get("hub.mode", ""), query.get("hub.topic", ""), query.get("hub.challenge", ""), query.get("hub.lease_seconds", "")
    )
    if challenge is None:
        return _err("Not found.", 404)
    return web.json_response({"challenge": challenge})


async def public_websub_push(request: web.Request) -> web.Response:
    from utils import websub
    cog = _bot(request).get_cog("Alerts")
    if cog is None or not websub.enabled():
        return _err("Unavailable.", 503)
    body = await request.json()
    raw = str(body.get("body", "")).encode("utf-8")
    if len(raw) > config.WEBSUB_MAX_BODY_BYTES or not websub.signature_valid(raw, str(body.get("signature", ""))):
        return _err("Invalid signature.", 403)
    entries = websub.parse_feed(raw)
    if entries:
        asyncio.create_task(cog.handle_websub_push(entries))
    return web.json_response({"ok": True})


def build_app(bot: commands.Bot, secret: str) -> web.Application:
    app = web.Application(middlewares=[_auth, _http_errors])
    app["bot"] = bot
    app["secret"] = secret
    app.router.add_get("/public/verify/{token}", public_verify_info)
    app.router.add_post("/public/verify/{token}", public_verify_complete)
    app.router.add_get("/public/websub/youtube", public_websub_verify)
    app.router.add_post("/public/websub/youtube", public_websub_push)
    app.router.add_get("/status", status)
    app.router.add_get("/commands", command_catalog)
    app.router.add_get("/team", team)
    app.router.add_post("/guilds/present", guilds_present)
    app.router.add_get("/guild/{gid}", guild_overview)
    app.router.add_post("/guild/{gid}/settings", guild_settings_update)
    app.router.add_get("/guild/{gid}/module/{key}", module_get)
    app.router.add_post("/guild/{gid}/module/{key}", module_save)
    app.router.add_post("/guild/{gid}/module/{key}/toggle", module_toggle)
    app.router.add_post("/guild/{gid}/module/{key}/action", module_action)
    app.router.add_get("/guild/{gid}/audit", audit_list)
    return app


def socket_path() -> str:
    path = os.getenv("SOWARD_IPC_PATH", config.DASHBOARD_IPC_SOCKET)
    return os.path.abspath(path)


def uses_unix_socket() -> bool:
    return hasattr(__import__("socket"), "AF_UNIX") and os.name != "nt"


async def start_ipc(bot: commands.Bot, secret: str) -> web.AppRunner:
    runner = web.AppRunner(build_app(bot, secret))
    await runner.setup()
    if uses_unix_socket():
        path = socket_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            os.unlink(path)
        site: web.BaseSite = web.UnixSite(runner, path)
        await site.start()
        os.chmod(path, 0o600)
        log.info("Dashboard IPC listening on unix socket %s", path)
    else:
        port = int(os.getenv("SOWARD_IPC_PORT", config.DASHBOARD_IPC_FALLBACK_PORT))
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        log.info("Dashboard IPC listening on 127.0.0.1:%d (no unix sockets on this platform)", port)
    return runner
