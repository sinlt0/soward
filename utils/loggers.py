import io
import logging
import math
import time
import traceback
from typing import Optional

import discord
from PIL import Image, ImageDraw, ImageFont

import config
from utils import db

log = logging.getLogger("soward.loggers")

LEVEL_COLORS = {
    "ready": 0x3BA55D,
    "info": 0x5865F2,
    "command": 0x8A63F2,
    "warning": 0xFAA61A,
    "error": 0xED4245,
}

_webhook_cache: dict[str, discord.Webhook] = {}


def _get_webhook(url: str, bot: discord.Client) -> Optional[discord.Webhook]:
    if not url:
        return None
    if url not in _webhook_cache:
        try:
            _webhook_cache[url] = discord.Webhook.from_url(url, client=bot)
        except ValueError:
            log.error("Invalid webhook URL configured.")
            return None
    return _webhook_cache[url]


async def close() -> None:
    return


def _layout(container_builder) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = container_builder()
    view.add_item(container)
    return view


async def _send_layout(bot: discord.Client, url: str, view: discord.ui.LayoutView) -> None:
    webhook = _get_webhook(url, bot)
    if not webhook:
        return
    try:
        await webhook.send(view=view)
    except discord.HTTPException:
        log.warning("Failed to send log message to webhook.", exc_info=True)


async def log_ready(bot: discord.Client) -> None:
    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["ready"])
        container.add_item(discord.ui.TextDisplay(f"## ✅ Bot Ready"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"**Logged in as**\n{bot.user.mention} (`{bot.user.id}`)"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Guilds**\n`{len(bot.guilds)}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    await _send_layout(bot, config.DEV_LOG_LIFECYCLE_WEBHOOK_URL, _layout(build))


async def log_shutdown(bot: discord.Client, reason: str = "Graceful shutdown") -> None:
    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["warning"])
        container.add_item(discord.ui.TextDisplay("## 🛑 Bot Shutting Down"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Reason**\n{reason}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    await _send_layout(bot, config.DEV_LOG_LIFECYCLE_WEBHOOK_URL, _layout(build))


async def log_guild_join(bot: discord.Client, guild: discord.Guild) -> None:
    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["ready"])
        container.add_item(discord.ui.TextDisplay("## 📥 Joined Guild"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Server**\n{guild.name} (`{guild.id}`)"))
        container.add_item(discord.ui.Separator())
        owner_text = f"{guild.owner.mention} — {guild.owner} (`{guild.owner_id}`)" if guild.owner else f"`{guild.owner_id}`"
        container.add_item(discord.ui.TextDisplay(f"**Owner**\n{owner_text}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Members**\n`{guild.member_count}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Total guilds now**\n`{len(bot.guilds)}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    webhook = _get_webhook(config.DEV_LOG_GUILDS_WEBHOOK_URL, bot)
    if not webhook:
        return
    try:
        await webhook.send(view=_layout(build), allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning("Failed to send guild join log to webhook.", exc_info=True)


async def log_guild_leave(bot: discord.Client, guild: discord.Guild) -> None:
    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["warning"])
        container.add_item(discord.ui.TextDisplay("## 📤 Left Guild"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Server**\n{guild.name} (`{guild.id}`)"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Total guilds now**\n`{len(bot.guilds)}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    await _send_layout(bot, config.DEV_LOG_GUILDS_WEBHOOK_URL, _layout(build))


def _detect_invocation_context(ctx) -> str:
    prefix = ctx.prefix or ""
    bot_id = ctx.bot.user.id if ctx.bot.user else 0
    if prefix.strip() in (f"<@{bot_id}>", f"<@!{bot_id}>"):
        return "MENTION"
    if prefix == "":
        return "NOPREFIX"
    return "PREFIX"


async def log_command(ctx) -> None:
    invocation_context = _detect_invocation_context(ctx)

    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["command"])
        container.add_item(discord.ui.TextDisplay("## 📜 Command Executed"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Command**\n`{ctx.command.qualified_name}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Context**\n`{invocation_context}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"**User**\n{ctx.author.mention} — {ctx.author} (`{ctx.author.id}`)"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"**Channel**\n{ctx.channel.mention if ctx.guild else 'Direct Message'} (`{ctx.channel.id}`)"
        ))
        container.add_item(discord.ui.Separator())
        if ctx.guild:
            container.add_item(discord.ui.TextDisplay(f"**Server**\n{ctx.guild.name} (`{ctx.guild.id}`)"))
        else:
            container.add_item(discord.ui.TextDisplay("**Server**\nDirect Message"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    webhook = _get_webhook(config.DEV_LOG_COMMANDS_WEBHOOK_URL, ctx.bot)
    if not webhook:
        return
    try:
        await webhook.send(view=_layout(build), allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning("Failed to send command log to webhook.", exc_info=True)


async def log_error(bot: discord.Client, context: str, error: Exception) -> None:
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    if len(tb) > 3500:
        tb = tb[:1700] + "\n...\n" + tb[-1700:]

    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS["error"])
        container.add_item(discord.ui.TextDisplay("## ❌ Error"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Context**\n{context}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Traceback**\n```py\n{tb}\n```"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    await _send_layout(bot, config.DEV_LOG_ERRORS_WEBHOOK_URL, _layout(build))


async def log_console(bot: discord.Client, message: str, level: str = "info") -> None:
    def build():
        container = discord.ui.Container(accent_color=LEVEL_COLORS.get(level, LEVEL_COLORS["info"]))
        container.add_item(discord.ui.TextDisplay(f"## {level.upper()}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(message))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# <t:{int(time.time())}:F>"))
        return container

    await _send_layout(bot, config.DEV_LOG_LIFECYCLE_WEBHOOK_URL, _layout(build))


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


async def _gather_stats(bot: discord.Client) -> dict:
    guild_count = len(bot.guilds)
    member_count = sum(g.member_count or 0 for g in bot.guilds)
    command_count = len(set(bot.walk_commands()))
    cog_count = len(bot.cogs)

    table_rows = await db.raw_fetch("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    total_rows = 0
    for t in table_rows:
        try:
            count_row = await db.raw_fetchone(f"SELECT COUNT(*) as c FROM {t['name']}")
            total_rows += count_row["c"] if count_row else 0
        except Exception:
            continue

    mongo_status = "Connected" if db.is_mongo_available() else "Unavailable"
    backup_info = await db.get_last_backup_info()
    last_sync = f"{int(time.time() - backup_info['saved_at'])}s ago" if backup_info and backup_info.get("saved_at") else "Never"

    return {
        "guild_count": guild_count,
        "member_count": member_count,
        "command_count": command_count,
        "cog_count": cog_count,
        "table_count": len(table_rows),
        "total_rows": total_rows,
        "mongo_status": mongo_status,
        "last_sync": last_sync,
        "gateway_latency_ms": 0 if math.isnan(bot.latency) else round(bot.latency * 1000),
    }


def _render_stats_image(stats: dict, bot_name: str) -> io.BytesIO:
    W, H = 600, 340
    bg = (18, 18, 21)
    card = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(card)

    accent = (127, 179, 213)
    text_bright = (223, 231, 236)
    text_dim = (138, 150, 158)
    label_color = (108, 158, 189)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse([W - 260, -160, W + 140, 240], fill=(60, 90, 105, 40))
    card.paste(Image.alpha_composite(card.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(card)

    title_font = _load_font(26, bold=True)
    subtitle_font = _load_font(13, bold=False)
    label_font = _load_font(12, bold=False)
    value_font = _load_font(20, bold=True)
    footer_font = _load_font(11, bold=False)

    draw.text((28, 24), f"{bot_name} / Database", font=title_font, fill=text_bright)
    draw.text((28, 60), "DATABASE MONITORING SYSTEM", font=subtitle_font, fill=accent)

    stat_blocks_row1 = [
        ("TABLES", str(stats["table_count"])),
        ("TOTAL ROWS", f"{stats['total_rows']:,}"),
        ("MONGO MIRROR", stats["mongo_status"]),
    ]
    stat_blocks_row2 = [
        ("LAST SYNC", stats["last_sync"]),
        ("SERVERS", f"{stats['guild_count']:,}"),
        ("MEMBERS", f"{stats['member_count']:,}"),
    ]

    col_x = [28, 232, 436]
    row_y = [112, 200]

    for (label, value), x in zip(stat_blocks_row1, col_x):
        draw.text((x, row_y[0]), label, font=label_font, fill=label_color)
        draw.text((x, row_y[0] + 20), value, font=value_font, fill=text_bright)

    for (label, value), x in zip(stat_blocks_row2, col_x):
        draw.text((x, row_y[1]), label, font=label_font, fill=label_color)
        draw.text((x, row_y[1] + 20), value, font=value_font, fill=text_bright)

    draw.line([(28, 268), (W - 28, 268)], fill=(48, 52, 58), width=1)
    draw.text(
        (28, 282),
        f"Commands: {stats['command_count']} · Cogs: {stats['cog_count']} · Gateway: {stats['gateway_latency_ms']}ms",
        font=footer_font, fill=text_dim,
    )
    draw.text((28, 302), f"Auto-updated every {config.DEV_STATS_UPDATE_INTERVAL // 60} min · Soward stats monitor", font=footer_font, fill=text_dim)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf


class DevStatsUpdater:

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._channel_id: Optional[int] = None

    def _resolve_channel_id(self) -> Optional[int]:
        if self._channel_id:
            return self._channel_id
        if not config.DEV_STATS_WEBHOOK_URL:
            return None
        try:
            webhook = discord.Webhook.from_url(config.DEV_STATS_WEBHOOK_URL, client=self.bot)
            self._channel_id = webhook.channel_id
            return self._channel_id
        except ValueError:
            log.error("SOWARD_DEV_STATS_WEBHOOK is not a valid webhook URL.")
            return None

    async def _build_view(self, stats: dict) -> discord.ui.LayoutView:
        status_emoji = "✅" if stats["mongo_status"] == "Connected" else "⚠️"
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x2B2D31)
        container.add_item(discord.ui.TextDisplay(f"## {config.BOT_NAME} — Database Stats"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"{status_emoji} Mongo mirror: **{stats['mongo_status']}** · Last sync: **{stats['last_sync']}**"
        ))
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media="attachment://db-stats.png")
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"-# Refreshes every {config.DEV_STATS_UPDATE_INTERVAL // 60} minutes · <t:{int(time.time())}:R>"
        ))
        view.add_item(container)
        return view

    async def update(self) -> None:
        channel_id = self._resolve_channel_id()
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            log.warning("DevStatsUpdater: channel %s not found or not cached.", channel_id)
            return

        stats = await _gather_stats(self.bot)
        image_buf = _render_stats_image(stats, config.BOT_NAME)
        file = discord.File(image_buf, filename="db-stats.png")
        view = await self._build_view(stats)

        row = await db.raw_fetchone("SELECT * FROM dev_stats_state WHERE id=1")
        message_id = row["message_id"] if row else None

        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(content=None, embed=None, embeds=[], attachments=[file], view=view)
                await db.raw_execute(
                    "INSERT INTO dev_stats_state (id, message_id, last_updated_at) VALUES (1, ?, ?)"
                    " ON CONFLICT(id) DO UPDATE SET last_updated_at=excluded.last_updated_at",
                    (message_id, time.time()),
                )
                return
            except discord.NotFound:
                message_id = None
            except discord.HTTPException:
                log.warning("DevStatsUpdater: edit failed, will try resending.", exc_info=True)
                message_id = None

        try:
            message = await channel.send(file=file, view=view)
            await db.raw_execute(
                "INSERT INTO dev_stats_state (id, message_id, last_updated_at) VALUES (1, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET message_id=excluded.message_id, last_updated_at=excluded.last_updated_at",
                (message.id, time.time()),
            )
        except discord.HTTPException:
            log.error("DevStatsUpdater: failed to send stats message.", exc_info=True)
