import time

import discord
from aiohttp import web

import config
from web.templates import base_page

_start_time = time.time()
_dev_cache: dict[int, dict] = {}
_dev_cache_at: float = 0.0
_DEV_CACHE_TTL = 600


def _format_uptime(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


def _bot_avatar_url(bot) -> str:
    if bot.is_ready() and bot.user:
        return bot.user.display_avatar.replace(size=256).url
    return ""


FEATURES = [
    ("AN", "AntiNuke & AntiRaid", "Automatic protection against malicious admin actions and mass-join raids, with quarantine and instant lockdown."),
    ("MOD", "Full Moderation Suite", "Ban, kick, mute, warn, purge, tempban, softban, and a complete case history for every action."),
    ("MUS", "Music & Lofi Radio", "High-quality queued playback, audio filters, and 24/7 lofi radio stations with custom station support."),
    ("VER", "Verification Gate", "Button, captcha, or manual verification to keep raiders and bots out of your community."),
    ("CMD", "Custom Commands", "Build your own commands with triggers, conditionals, role/channel restrictions, and action tags."),
    ("LOG", "Multi-Channel Logging", "Moderation, security, member, message, and server logs routed to dedicated webhook channels."),
]


def _index_page(bot) -> str:
    ready = bot.is_ready()
    guild_count = len(bot.guilds) if ready else 0
    user_count = sum(g.member_count or 0 for g in bot.guilds) if ready else 0
    latency_ms = round(bot.latency * 1000) if ready else 0
    uptime_str = _format_uptime(int(time.time() - _start_time))
    status = "online" if ready else "starting"
    total_commands = len(set(bot.walk_commands())) if ready else 0
    avatar_url = _bot_avatar_url(bot)

    invite_url = "#"
    if ready and bot.user:
        perms = discord.Permissions(administrator=True)
        invite_url = discord.utils.oauth_url(bot.user.id, permissions=perms, scopes=("bot", "applications.commands"))

    dot_class = "status-dot" if status == "online" else "status-dot starting"
    logo_block = f'<img class="hero-logo" src="{avatar_url}" alt="{config.BOT_NAME}">' if avatar_url else ""

    feature_cards = "".join(f"""
    <div class="feature-card">
      <div class="mark">{mark}</div>
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>""" for mark, title, desc in FEATURES)

    body = f"""
<div class="hero">
  {logo_block}
  <div class="status-pill">
    <span class="{dot_class}"></span>
    {status.title()} · v{config.BOT_VERSION} · up {uptime_str}
  </div>
  <h1>{config.BOT_NAME}</h1>
  <p>An all-in-one Discord bot for moderation, security, music, and server utility —
     built entirely on Discord's newest Components V2 interface.</p>
  <div class="hero-buttons">
    <a class="btn btn-primary" href="{invite_url}">Add to Discord</a>
    <a class="btn btn-secondary" href="/commands">Browse Commands</a>
  </div>
</div>

<div class="stats-grid">
  <div class="stat-card"><div class="stat-value">{guild_count:,}</div><div class="stat-label">Servers</div></div>
  <div class="stat-card"><div class="stat-value">{user_count:,}</div><div class="stat-label">Users</div></div>
  <div class="stat-card"><div class="stat-value">{total_commands}</div><div class="stat-label">Commands</div></div>
  <div class="stat-card"><div class="stat-value">{latency_ms}ms</div><div class="stat-label">Latency</div></div>
</div>

<div class="section">
  <div class="container">
    <div class="section-title">Everything your server needs</div>
    <div class="section-sub">Security, moderation, music, and engagement — all in one bot.</div>
    <div class="feature-grid">{feature_cards}</div>
  </div>
</div>
"""
    return base_page(f"{config.BOT_NAME} — Discord Bot", body, bot_avatar_url=avatar_url)


def _commands_page(bot) -> str:
    from cogs.help import CATEGORY_DESCRIPTIONS

    avatar_url = _bot_avatar_url(bot)

    by_category: dict[str, list] = {}
    for command in sorted(set(bot.walk_commands()), key=lambda c: c.qualified_name):
        cog_name = command.cog_name or "Uncategorized"
        if cog_name in config.HELP_HIDDEN_CATEGORIES:
            continue
        if command.hidden:
            continue
        by_category.setdefault(cog_name, []).append(command)

    cards = []
    for category in sorted(by_category.keys()):
        commands_list = by_category[category]
        chips = "".join(
            f'<div class="chip"><strong>{cmd.qualified_name}</strong>'
            + (f'<span class="desc">{cmd.help[:70]}</span>' if cmd.help else "")
            + "</div>"
            for cmd in commands_list
        )
        description = CATEGORY_DESCRIPTIONS.get(category, "")
        cards.append(f"""
<div class="category-card">
  <div class="category-header">
    <h3>{category}</h3>
    <span class="category-count">{len(commands_list)} command{'s' if len(commands_list) != 1 else ''}</span>
  </div>
  {f'<div class="category-desc">{description}</div>' if description else ''}
  <div class="command-chips">{chips}</div>
</div>""")

    body = f"""
<div class="section" style="padding-top: clamp(48px, 8vw, 72px);">
  <div class="container">
    <div class="section-title">Commands</div>
    <div class="section-sub">Every command {config.BOT_NAME} has to offer, grouped by category.</div>
    <input class="search-box" type="text" placeholder="Search commands..." oninput="filterCommands(this.value)">
    <div class="card-list" id="command-list">
      {''.join(cards) if cards else '<div class="empty-state">No commands loaded yet.</div>'}
    </div>
  </div>
</div>
<script>
function filterCommands(query) {{
  query = query.trim().toLowerCase();
  document.querySelectorAll('.category-card').forEach(function(card) {{
    var chips = card.querySelectorAll('.chip');
    var anyVisible = false;
    chips.forEach(function(chip) {{
      var match = chip.textContent.toLowerCase().includes(query);
      chip.style.display = match ? '' : 'none';
      if (match) anyVisible = true;
    }});
    card.style.display = (query === '' || anyVisible) ? '' : 'none';
  }});
}}
</script>
"""
    return base_page(f"Commands — {config.BOT_NAME}", body, bot_avatar_url=avatar_url)


async def _get_dev_users(bot) -> list[dict]:
    global _dev_cache, _dev_cache_at

    if time.time() - _dev_cache_at < _DEV_CACHE_TTL and _dev_cache:
        return list(_dev_cache.values())

    fresh: dict[int, dict] = {}
    for user_id in config.OWNER_IDS:
        try:
            user = await bot.fetch_user(user_id)
            fresh[user_id] = {
                "id": user.id,
                "name": str(user),
                "avatar": user.display_avatar.replace(size=128).url,
                "role": "Owner",
            }
        except discord.HTTPException:
            fresh[user_id] = {"id": user_id, "name": f"User {user_id}", "avatar": "", "role": "Owner"}

    for user_id in config.DEV_IDS:
        if user_id in fresh:
            continue
        try:
            user = await bot.fetch_user(user_id)
            fresh[user_id] = {
                "id": user.id,
                "name": str(user),
                "avatar": user.display_avatar.replace(size=128).url,
                "role": "Developer",
            }
        except discord.HTTPException:
            fresh[user_id] = {"id": user_id, "name": f"User {user_id}", "avatar": "", "role": "Developer"}

    _dev_cache = fresh
    _dev_cache_at = time.time()
    return list(fresh.values())


async def _devs_page(bot) -> str:
    avatar_url = _bot_avatar_url(bot)
    devs = await _get_dev_users(bot)

    cards = "".join(f"""
<div class="dev-card">
  <img class="dev-avatar" src="{d['avatar']}" alt="{d['name']}" onerror="this.style.visibility='hidden'">
  <div class="dev-name">{d['name']}</div>
  <span class="dev-role">{d['role']}</span>
</div>""" for d in devs)

    body = f"""
<div class="section" style="padding-top: clamp(48px, 8vw, 72px);">
  <div class="container">
    <div class="section-title">Developers</div>
    <div class="section-sub">The people behind {config.BOT_NAME}.</div>
    <div class="dev-grid">
      {cards if cards else '<div class="empty-state">No developers configured.</div>'}
    </div>
  </div>
</div>
"""
    return base_page(f"Developers — {config.BOT_NAME}", body, bot_avatar_url=avatar_url)


def create_app(bot) -> web.Application:
    app = web.Application()

    async def index(request: web.Request) -> web.Response:
        return web.Response(text=_index_page(bot), content_type="text/html")

    async def commands_route(request: web.Request) -> web.Response:
        return web.Response(text=_commands_page(bot), content_type="text/html")

    async def devs_route(request: web.Request) -> web.Response:
        return web.Response(text=await _devs_page(bot), content_type="text/html")

    async def health(request: web.Request) -> web.Response:
        if bot.is_ready():
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "starting"}, status=503)

    app.router.add_get("/", index)
    app.router.add_get("/commands", commands_route)
    app.router.add_get("/devs", devs_route)
    app.router.add_get("/health", health)
    return app


async def start_web_server(bot, host: str = "0.0.0.0", port: int = 8080):
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
