import functools
import hmac
import re
import time
from urllib.parse import urlencode

from flask import abort, jsonify, redirect, render_template, request, session, url_for

import config
from dashboard.ipc import BotClient, BotError, BotUnavailable

POST_ROUTES = (
    re.compile(r"^profile$"),
    re.compile(r"^presence$"),
    re.compile(r"^maintenance$"),
    re.compile(r"^dashboard$"),
    re.compile(r"^reload$"),
    re.compile(r"^slashsync$"),
    re.compile(r"^restart$"),
    re.compile(r"^premium/keys$"),
    re.compile(r"^premium/keys/delete$"),
    re.compile(r"^bans/(add|remove)$"),
    re.compile(r"^user/\d{5,25}/wallet$"),
    re.compile(r"^commands/(disable|enable)$"),
    re.compile(r"^database/sync$"),
    re.compile(r"^send$"),
    re.compile(r"^guild/\d{5,25}/(invite|leave|ban|unban|dashboard|premium)$"),
)
SLOW = {"profile": 40.0, "reload": 60.0, "slashsync": 40.0, "database/sync": 120.0}
IMAGE_BODY = 16 * 1024 * 1024
PAGES = (
    ("overview", "Overview", "admin_home"),
    ("profile", "Bot profile", "admin_profile"),
    ("servers", "Servers", "admin_servers"),
    ("users", "Users", "admin_users"),
    ("premium", "Premium", "admin_premium"),
    ("bans", "Bans", "admin_bans"),
    ("commands", "Commands", "admin_commands"),
    ("database", "Database", "admin_database"),
    ("system", "System", "admin_system"),
)


def is_staff(user) -> bool:
    return bool(user) and str(user.get("id", "")).isdigit() and int(user["id"]) in config.ALL_PRIVILEGED_IDS


def is_owner(user) -> bool:
    return bool(user) and str(user.get("id", "")).isdigit() and int(user["id"]) in config.OWNER_IDS


def register(app, ipc: BotClient, current_user, render_error) -> None:
    @app.template_filter("stamp")
    def stamp(ts) -> str:
        if not ts:
            return "never"
        return time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(ts))) + " UTC"

    @app.template_filter("until")
    def until(ts) -> str:
        if ts is None:
            return "lifetime"
        delta = int(float(ts) - time.time())
        if delta <= 0:
            return "expired"
        for size, name in ((86400, "d"), (3600, "h"), (60, "m")):
            if delta >= size:
                return f"{delta // size}{name} left"
        return "under 1m left"

    def staff_required(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                session["next"] = request.full_path if request.query_string else request.path
                return redirect(url_for("login"))
            if not is_staff(user):
                abort(404)
            try:
                return view(*args, **kwargs)
            except BotUnavailable:
                return render_error(503, "Bot is starting", "Zyro is not reachable yet. This usually clears up within a minute.", ("Try again", request.path))
            except BotError as exc:
                return render_error(exc.status, "Request failed", exc.message, ("Back", url_for("admin_home")))
        return wrapper

    def page(template: str, active: str, **ctx):
        user = current_user()
        return render_template(template, active=active, pages=PAGES, can_edit=is_owner(user), **ctx)

    def fetch(path: str):
        return ipc.get(path, current_user()["id"])

    @app.route("/admin")
    @staff_required
    def admin_home():
        return page("admin/home.html", "overview", d=fetch("/admin/overview"), staff=fetch("/admin/staff")["staff"])

    @app.route("/admin/profile")
    @staff_required
    def admin_profile():
        return page("admin/profile.html", "profile", p=fetch("/admin/profile"))

    @app.route("/admin/servers")
    @staff_required
    def admin_servers():
        args = {k: request.args.get(k, "") for k in ("q", "filter", "sort", "page")}
        args = {k: v[:80] for k, v in args.items() if v}
        data = fetch("/admin/guilds" + ("?" + urlencode(args) if args else ""))
        return page("admin/servers.html", "servers", d=data, args=args)

    @app.route("/admin/servers/<gid>")
    @staff_required
    def admin_server(gid: str):
        if not gid.isdigit():
            abort(404)
        return page("admin/server.html", "servers", g=fetch(f"/admin/guild/{gid}"))

    @app.route("/admin/users")
    @staff_required
    def admin_users():
        target = request.args.get("id", "").strip()
        if target.isdigit() and 5 <= len(target) <= 25:
            return redirect(url_for("admin_user", uid=target))
        return page("admin/users.html", "users", u=None, error="Enter a numeric Discord user ID." if target else "")

    @app.route("/admin/users/<uid>")
    @staff_required
    def admin_user(uid: str):
        if not uid.isdigit() or not 5 <= len(uid) <= 25:
            abort(404)
        try:
            data = fetch(f"/admin/user/{uid}")
        except BotError as exc:
            if exc.status == 404:
                return page("admin/users.html", "users", u=None, error="No Discord user has that ID.")
            raise
        return page("admin/users.html", "users", u=data, error="")

    @app.route("/admin/commands")
    @staff_required
    def admin_commands():
        return page("admin/commands.html", "commands", d=fetch("/admin/commands"))

    @app.route("/admin/database")
    @staff_required
    def admin_database():
        return page("admin/database.html", "database", d=fetch("/admin/database"))

    @app.route("/admin/premium")
    @staff_required
    def admin_premium():
        return page("admin/premium.html", "premium", d=fetch("/admin/premium"))

    @app.route("/admin/bans")
    @staff_required
    def admin_bans():
        return page("admin/bans.html", "bans", d=fetch("/admin/bans"))

    @app.route("/admin/system")
    @staff_required
    def admin_system():
        return page("admin/system.html", "system", d=fetch("/admin/overview"), cogs=fetch("/admin/cogs")["cogs"])

    @app.route("/api/admin/logs")
    def api_admin_logs():
        user = current_user()
        if not is_staff(user):
            return jsonify(error="Not found."), 404
        lines = request.args.get("lines", "200")
        try:
            return jsonify(ipc.get(f"/admin/logs?lines={int(lines) if lines.isdigit() else 200}", user["id"]))
        except BotUnavailable:
            return jsonify(error="The bot is not reachable right now."), 503
        except BotError as exc:
            return jsonify(error=exc.message), exc.status

    @app.route("/api/admin/<path:sub>", methods=["POST"])
    def api_admin(sub: str):
        user = current_user()
        token = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf", "")
        if not expected or not hmac.compare_digest(token, expected):
            return jsonify(error="Your session expired. Reload the page and try again."), 403
        if user is None:
            return jsonify(error="Sign in again to continue."), 401
        if not is_staff(user):
            return jsonify(error="Not found."), 404
        if not any(pattern.match(sub) for pattern in POST_ROUTES):
            return jsonify(error="Unknown action."), 404
        if sub == "profile":
            request.max_content_length = IMAGE_BODY
        body = request.get_json(silent=True) or {}
        try:
            result = ipc.request("POST", f"/admin/{sub}", user["id"], body, timeout=SLOW.get(sub, 12.0), name=user["name"])
        except BotUnavailable:
            return jsonify(error="The bot is not reachable right now. Try again in a moment."), 503
        except BotError as exc:
            return jsonify(error=exc.message), exc.status
        return jsonify(result)
