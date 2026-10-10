import functools
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import markdown
import requests
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup

import config
from dashboard.ipc import BotClient, BotError, BotUnavailable

BASE = Path(__file__).resolve().parent
CONTENT = BASE / "content"
DISCORD_API = "https://discord.com/api/v10"
MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8
SESSION_TTL = config.DASHBOARD_SESSION_DAYS * 86400

NAV = [
    ("Commands", "commands_page"),
    ("Docs", "docs_index"),
    ("Changelog", "changelog_page"),
    ("Team", "team_page"),
]

DEFAULT_COMMANDS_TTL = 300
DEFAULT_STATUS_TTL = 15

_cache: dict[str, tuple[float, object]] = {}
_sessions: dict[str, dict] = {}


def _cached(key: str, ttl: int, loader):
    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = loader()
    _cache[key] = (now + ttl, value)
    return value


def _parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            text = text[end + 4:].lstrip("\n")
    return meta, text


def _render_markdown(text: str) -> Markup:
    return Markup(markdown.markdown(text, extensions=["fenced_code", "tables", "toc", "sane_lists"]))


def _load_docs() -> list[dict]:
    docs = []
    for path in sorted((CONTENT / "docs").glob("*.md")):
        meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        docs.append({
            "slug": path.stem,
            "title": meta.get("title", path.stem.replace("-", " ").title()),
            "description": meta.get("description", ""),
            "order": int(meta.get("order", 99)),
            "body": body,
        })
    return sorted(docs, key=lambda d: d["order"])


def _load_changelog() -> list[dict]:
    with open(CONTENT / "changelog.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(BASE / "static"), template_folder=str(BASE / "templates"))
    ipc = BotClient()
    base_url = config.DASHBOARD_URL
    app.secret_key = os.getenv("SOWARD_SESSION_SECRET") or hashlib.sha256((ipc.secret + config.BOT_TOKEN).encode()).hexdigest()
    app.config.update(
        SESSION_COOKIE_NAME="soward_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=base_url.startswith("https://"),
        MAX_CONTENT_LENGTH=256 * 1024,
        PERMANENT_SESSION_LIFETIME=SESSION_TTL,
        TEMPLATES_AUTO_RELOAD=False,
    )

    client_secret = os.getenv("SOWARD_CLIENT_SECRET", "")
    support_url = os.getenv("SOWARD_SUPPORT_URL", "")

    def bot_status() -> dict:
        def load():
            try:
                return ipc.get("/status")
            except (BotUnavailable, BotError):
                return {"ready": False, "name": config.BOT_NAME, "version": config.BOT_VERSION, "guilds": 0, "users": 0,
                        "latency_ms": 0, "uptime": 0, "commands": 0, "avatar": "", "user_id": None, "dashboard_enabled": True}
        return _cached("status", DEFAULT_STATUS_TTL, load)

    def client_id() -> Optional[str]:
        return os.getenv("SOWARD_CLIENT_ID") or bot_status().get("user_id")

    def invite_url() -> str:
        cid = client_id()
        if not cid:
            return "#"
        query = urlencode({"client_id": cid, "permissions": 8, "scope": "bot applications.commands"})
        return f"https://discord.com/oauth2/authorize?{query}"

    def redirect_uri() -> str:
        root = base_url or request.url_root.rstrip("/")
        return f"{root}/callback"

    def current_user() -> Optional[dict]:
        sid = session.get("sid")
        data = _sessions.get(sid) if sid else None
        if data is None:
            return None
        if data["exp"] < time.time():
            _sessions.pop(sid, None)
            return None
        return data

    @app.context_processor
    def inject_globals():
        status = bot_status()
        return {
            "bot_name": config.BOT_NAME,
            "bot_version": config.BOT_VERSION,
            "bot_avatar": status.get("avatar", ""),
            "nav": NAV,
            "user": current_user(),
            "invite_url": invite_url(),
            "support_url": support_url,
            "csrf_token": session.get("csrf", ""),
            "year": time.gmtime().tm_year,
        }

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.path.startswith(("/dashboard", "/api", "/login", "/callback")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def render_error(status: int, title: str, message: str, action: Optional[tuple] = None):
        return render_template("error.html", status=status, title=title, message=message, action=action), status

    @app.errorhandler(404)
    def not_found(_):
        return render_error(404, "Page not found", "That page does not exist. Check the address or head back home.", ("Go home", url_for("home")))

    @app.errorhandler(500)
    def server_error(_):
        return render_error(500, "Something broke", "The dashboard hit an error. Try again in a moment.", ("Go home", url_for("home")))

    def login_required(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if current_user() is None:
                session["next"] = request.full_path if request.query_string else request.path
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapper

    def bot_call(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BotUnavailable:
                if request.path.startswith("/api"):
                    return jsonify(error="The bot is not reachable right now. Try again in a moment."), 503
                return render_error(503, "Bot is starting", "Soward is not reachable yet. This usually clears up within a minute.", ("Try again", request.path))
            except BotError as exc:
                if request.path.startswith("/api"):
                    return jsonify(error=_friendly(exc)), exc.status
                return _bot_error_page(exc)
        return wrapper

    def _friendly(exc: BotError) -> str:
        return {
            "global_off": "The dashboard is turned off right now.",
            "guild_off": "Dashboard access is turned off for this server.",
            "no_permission": "You need Manage Server in this server.",
            "not_member": "You are not a member of this server.",
            "guild": "Soward is not in that server.",
            "module": "That module does not exist.",
        }.get(exc.message, exc.message)

    def _bot_error_page(exc: BotError):
        if exc.message == "global_off":
            return render_error(503, "Dashboard is off", "The bot team has switched the dashboard off for now. Commands still work in Discord.", ("Back to site", url_for("home")))
        if exc.message == "guild_off":
            return render_error(403, "Dashboard is off for this server", "A server manager turned off web access. Run the dashboard on command in Discord to turn it back on.", ("Pick another server", url_for("servers")))
        if exc.message in ("no_permission", "not_member"):
            return render_error(403, "No access", "You need the Manage Server permission in that server.", ("Pick another server", url_for("servers")))
        if exc.status == 404:
            return render_error(404, "Not found", "Soward is not in that server, or the page does not exist.", ("Pick a server", url_for("servers")))
        return render_error(exc.status, "Request failed", _friendly(exc), ("Back", url_for("servers")))

    def csrf_required(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            token = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(token, expected):
                return jsonify(error="Your session expired. Reload the page and try again."), 403
            if current_user() is None:
                return jsonify(error="Sign in again to continue."), 401
            return view(*args, **kwargs)
        return wrapper

    @app.route("/")
    def home():
        status = bot_status()
        try:
            catalog = _cached("commands", DEFAULT_COMMANDS_TTL, lambda: ipc.get("/commands"))["categories"]
        except (BotUnavailable, BotError):
            catalog = []
        showcase = [
            {"name": c["name"], "description": c["description"], "commands": c["commands"][:6], "total": len(c["commands"])}
            for c in catalog
        ]
        return render_template("home.html", status=status, showcase=showcase)

    @app.route("/commands")
    def commands_page():
        try:
            catalog = _cached("commands", DEFAULT_COMMANDS_TTL, lambda: ipc.get("/commands"))["categories"]
            loaded = True
        except (BotUnavailable, BotError):
            catalog, loaded = [], False
        total = sum(len(c["commands"]) for c in catalog)
        return render_template("commands.html", categories=catalog, total=total, loaded=loaded)

    @app.route("/docs")
    def docs_index():
        return render_template("docs_index.html", docs=_cached("docs", 60, _load_docs))

    @app.route("/docs/<slug>")
    def doc_page(slug: str):
        docs = _cached("docs", 60, _load_docs)
        doc = next((d for d in docs if d["slug"] == slug), None)
        if doc is None:
            abort(404)
        return render_template("doc.html", docs=docs, doc=doc, html=_render_markdown(doc["body"]))

    @app.route("/changelog")
    def changelog_page():
        return render_template("changelog.html", entries=_cached("changelog", 60, _load_changelog))

    def _legal(slug: str, title: str):
        path = CONTENT / "legal" / f"{slug}.md"
        text = path.read_text(encoding="utf-8").replace("{BOT_NAME}", config.BOT_NAME)
        meta, body = _parse_front_matter(text)
        return render_template("legal.html", title=title, updated=meta.get("updated", ""), html=_render_markdown(body))

    @app.route("/terms")
    def terms_page():
        return _legal("terms", "Terms of Service")

    @app.route("/privacy")
    def privacy_page():
        return _legal("privacy", "Privacy Policy")

    @app.route("/credits")
    def credits_page():
        text = (config.BASE_DIR / "CREDITS.md").read_text(encoding="utf-8")
        return render_template("legal.html", title="Credits", updated="", html=_render_markdown(text))

    @app.route("/team")
    @app.route("/devs")
    def team_page():
        try:
            team = _cached("team", 600, lambda: ipc.get("/team"))["team"]
        except (BotUnavailable, BotError):
            team = []
        return render_template("team.html", team=team)

    @app.route("/invite")
    def invite():
        return redirect(invite_url())

    @app.route("/support")
    def support():
        return redirect(support_url) if support_url else redirect(url_for("docs_index"))

    @app.route("/health")
    def health():
        status = bot_status()
        if status.get("ready"):
            return jsonify(status="ok")
        return jsonify(status="starting"), 503

    @app.route("/login")
    def login():
        cid = client_id()
        if not cid or not client_secret:
            return render_error(503, "Sign-in is not set up", "The bot owner has not added Discord OAuth credentials yet.", ("Back to site", url_for("home")))
        state = secrets.token_urlsafe(24)
        session["oauth_state"] = state
        query = urlencode({
            "client_id": cid, "redirect_uri": redirect_uri(), "response_type": "code",
            "scope": "identify guilds", "state": state, "prompt": "none",
        })
        return redirect(f"https://discord.com/oauth2/authorize?{query}")

    @app.route("/callback")
    def callback():
        state = request.args.get("state", "")
        expected = session.pop("oauth_state", "")
        if not expected or not hmac.compare_digest(state, expected):
            return render_error(400, "Sign-in expired", "The sign-in link is no longer valid. Start again.", ("Sign in", url_for("login")))
        code = request.args.get("code")
        if not code:
            return redirect(url_for("home"))
        try:
            token = requests.post(
                f"{DISCORD_API}/oauth2/token",
                data={"client_id": client_id(), "client_secret": client_secret, "grant_type": "authorization_code",
                      "code": code, "redirect_uri": redirect_uri()},
                headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10,
            )
            token.raise_for_status()
            access = token.json()["access_token"]
            auth = {"Authorization": f"Bearer {access}"}
            me = requests.get(f"{DISCORD_API}/users/@me", headers=auth, timeout=10)
            me.raise_for_status()
            guilds = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=auth, timeout=10)
            guilds.raise_for_status()
        except (requests.RequestException, KeyError, ValueError):
            return render_error(502, "Discord did not respond", "Sign-in failed. Try again in a moment.", ("Sign in", url_for("login")))
        profile = me.json()
        sid = secrets.token_urlsafe(32)
        avatar = (
            f"https://cdn.discordapp.com/avatars/{profile['id']}/{profile['avatar']}.png?size=64"
            if profile.get("avatar") else "https://cdn.discordapp.com/embed/avatars/0.png"
        )
        _sessions[sid] = {
            "id": profile["id"], "name": profile.get("global_name") or profile["username"], "avatar": avatar,
            "guilds": guilds.json(), "exp": time.time() + SESSION_TTL,
        }
        session.clear()
        session["sid"] = sid
        session["csrf"] = secrets.token_urlsafe(24)
        session.permanent = True
        target = session.pop("next", None)
        if target and target.startswith("/") and not target.startswith("//"):
            return redirect(target)
        return redirect(url_for("servers"))

    @app.route("/logout")
    def logout():
        sid = session.get("sid")
        _sessions.pop(sid, None)
        session.clear()
        return redirect(url_for("home"))

    def manageable(user: dict) -> list[dict]:
        out = []
        for g in user["guilds"]:
            perms = int(g.get("permissions", 0))
            if g.get("owner") or perms & (MANAGE_GUILD | ADMINISTRATOR):
                out.append(g)
        return out

    @app.route("/dashboard")
    @login_required
    @bot_call
    def servers():
        user = current_user()
        guilds = manageable(user)
        present = ipc.post("/guilds/present", {"ids": [g["id"] for g in guilds]}, user["id"])
        items = []
        for g in guilds:
            info = present["present"].get(g["id"])
            icon = f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png?size=128" if g.get("icon") else ""
            items.append({"id": g["id"], "name": g["name"], "icon": icon, "installed": info is not None,
                          "members": info["member_count"] if info else 0})
        items.sort(key=lambda i: (not i["installed"], i["name"].lower()))
        return render_template("servers.html", servers=items, global_enabled=present["global_enabled"])

    @app.route("/dashboard/<gid>")
    @login_required
    @bot_call
    def server_page(gid: str):
        if not gid.isdigit():
            abort(404)
        user = current_user()
        overview = ipc.get(f"/guild/{gid}", user["id"])
        grouped = []
        for category in overview["categories"]:
            mods = [m for m in overview["modules"] if m["category"] == category]
            if mods:
                grouped.append({"name": category, "modules": mods})
        return render_template("server.html", g=overview, grouped=grouped)

    @app.route("/dashboard/<gid>/m/<key>")
    @login_required
    @bot_call
    def module_page(gid: str, key: str):
        if not gid.isdigit() or not re.fullmatch(r"[a-z_]+", key):
            abort(404)
        user = current_user()
        overview = ipc.get(f"/guild/{gid}", user["id"])
        module = ipc.get(f"/guild/{gid}/module/{key}", user["id"])
        groups: dict[str, list] = {}
        for f in module["fields"]:
            groups.setdefault(f["group"], []).append(f)
        return render_template("module.html", g=overview, m=module, groups=groups)

    @app.route("/dashboard/<gid>/audit")
    @login_required
    @bot_call
    def audit_page(gid: str):
        if not gid.isdigit():
            abort(404)
        user = current_user()
        overview = ipc.get(f"/guild/{gid}", user["id"])
        entries = ipc.get(f"/guild/{gid}/audit", user["id"])["entries"]
        return render_template("audit.html", g=overview, entries=entries)

    @app.route("/api/g/<gid>/settings", methods=["POST"])
    @csrf_required
    @bot_call
    def api_settings(gid: str):
        if not gid.isdigit():
            abort(404)
        return jsonify(ipc.post(f"/guild/{gid}/settings", request.get_json(silent=True) or {}, current_user()["id"]))

    @app.route("/api/g/<gid>/m/<key>", methods=["POST"])
    @csrf_required
    @bot_call
    def api_module_save(gid: str, key: str):
        if not gid.isdigit() or not re.fullmatch(r"[a-z_]+", key):
            abort(404)
        return jsonify(ipc.post(f"/guild/{gid}/module/{key}", request.get_json(silent=True) or {}, current_user()["id"]))

    @app.route("/api/g/<gid>/m/<key>/toggle", methods=["POST"])
    @csrf_required
    @bot_call
    def api_module_toggle(gid: str, key: str):
        if not gid.isdigit() or not re.fullmatch(r"[a-z_]+", key):
            abort(404)
        return jsonify(ipc.post(f"/guild/{gid}/module/{key}/toggle", request.get_json(silent=True) or {}, current_user()["id"]))

    @app.template_filter("ago")
    def ago(ts) -> str:
        delta = max(0, int(time.time() - float(ts)))
        for size, name in ((86400, "d"), (3600, "h"), (60, "m")):
            if delta >= size:
                return f"{delta // size}{name} ago"
        return "just now"

    @app.template_filter("uptime")
    def uptime(seconds) -> str:
        seconds = int(seconds)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        if days:
            return f"{days}d {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    return app
