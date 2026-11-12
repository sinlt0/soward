import time

import discord
from discord.ext import commands

import config
from utils import db, platform_spoof

KEY = ("dev", "presence")
STATUSES = {"online": discord.Status.online, "idle": discord.Status.idle, "dnd": discord.Status.dnd, "invisible": discord.Status.invisible}
KINDS = ("playing", "watching", "listening", "competing", "custom")
MIN_INTERVAL = 30
MAX_INTERVAL = 3600
MAX_ITEMS = 10
TEXT_LIMIT = 128
PLACEHOLDERS = "{servers} {members} {commands} {version} {ping}"
MODES = ("default", "custom", "off")
DEFAULT_INTERVAL = 30
DEFAULT_ITEMS = (
    {"kind": "playing", "text": "{servers} servers"},
    {"kind": "playing", "text": "{members} members"},
    {"kind": "playing", "text": f"{config.BOT_NAME} • prefix-only"},
)

state = {"index": 0, "next": 0.0}
_cfg: dict = {}


def default() -> dict:
    return {"status": "online", "mode": "default", "rotate": False, "interval": 60, "items": [], "platform": "desktop"}


def _items(raw) -> list:
    clean = []
    for item in raw or []:
        if isinstance(item, dict) and item.get("kind") in KINDS and str(item.get("text", "")).strip():
            clean.append({"kind": item["kind"], "text": str(item["text"]).strip()[:TEXT_LIMIT]})
    return clean[:MAX_ITEMS]


def normalize(data) -> dict:
    out = default()
    if not isinstance(data, dict):
        return out
    out["status"] = data.get("status") if data.get("status") in STATUSES else "online"
    out["rotate"] = bool(data.get("rotate"))
    try:
        out["interval"] = max(MIN_INTERVAL, min(MAX_INTERVAL, int(data.get("interval", 60))))
    except (TypeError, ValueError):
        out["interval"] = 60
    items = data.get("items")
    if items is None and data.get("kind") in KINDS and str(data.get("text", "")).strip():
        items = [{"kind": data["kind"], "text": data["text"]}]
    out["items"] = _items(items)
    out["platform"] = platform_spoof.normalize(data.get("platform"))
    mode = data.get("mode")
    if mode not in MODES:
        mode = "custom" if out["items"] else ("off" if data.get("kind") == "none" else "default")
    out["mode"] = mode
    return out


def validate(data: dict) -> dict:
    status = str(data.get("status", "online"))
    if status not in STATUSES:
        raise ValueError("Pick a valid status.")
    mode = str(data.get("mode", "custom"))
    if mode not in MODES:
        raise ValueError("Pick a valid presence mode.")
    platform = str(data.get("platform", "desktop"))
    if platform not in platform_spoof.PLATFORMS:
        raise ValueError("Pick a valid platform.")
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        raise ValueError(f"Use at most {MAX_ITEMS} activities.")
    items = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError("Activities are invalid.")
        kind = str(item.get("kind", ""))
        text = str(item.get("text", "")).strip()
        if kind not in KINDS:
            raise ValueError(f"Activity {index} has an invalid type.")
        if not text:
            raise ValueError(f"Activity {index} needs text.")
        items.append({"kind": kind, "text": text[:TEXT_LIMIT]})
    try:
        interval = int(data.get("interval", 60))
    except (TypeError, ValueError):
        raise ValueError("The interval must be a number of seconds.")
    if not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise ValueError(f"The interval must be {MIN_INTERVAL} to {MAX_INTERVAL} seconds.")
    rotate = bool(data.get("rotate"))
    if mode == "custom":
        if not items:
            raise ValueError("Add at least one activity, or choose Off to show only the status.")
        if rotate and len(items) < 2:
            raise ValueError("Add at least two activities to rotate between them.")
    return {"status": status, "mode": mode, "rotate": rotate, "interval": interval, "items": items, "platform": platform}


def effective(cfg: dict) -> tuple:
    if cfg["mode"] == "off":
        return [], False, cfg["interval"]
    if cfg["mode"] == "default":
        return list(DEFAULT_ITEMS), True, DEFAULT_INTERVAL
    return cfg["items"], cfg["rotate"], cfg["interval"]


def render(bot: commands.Bot, text: str) -> str:
    values = {
        "{servers}": f"{len(bot.guilds):,}",
        "{members}": f"{sum(g.member_count or 0 for g in bot.guilds):,}",
        "{commands}": str(len({c for c in bot.walk_commands() if not c.hidden})),
        "{version}": str(config.BOT_VERSION),
        "{ping}": f"{round(bot.latency * 1000)}ms" if bot.latency == bot.latency else "0ms",
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text[:TEXT_LIMIT]


def build(bot: commands.Bot, item: dict):
    text = render(bot, item["text"])
    if item["kind"] == "custom":
        return discord.CustomActivity(name=text)
    kinds = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
    return discord.Activity(type=kinds[item["kind"]], name=text)


async def load() -> dict:
    global _cfg
    _cfg = normalize(await db.get(*KEY))
    return _cfg


async def save(data: dict) -> dict:
    global _cfg
    _cfg = normalize(data)
    await db.set(*KEY, _cfg)
    return _cfg


def current() -> dict:
    return _cfg or default()


async def apply(bot: commands.Bot) -> None:
    cfg = await load() if not _cfg else _cfg
    items, rotate, interval = effective(cfg)
    status = STATUSES[cfg["status"]]
    if not items:
        await bot.change_presence(status=status, activity=None)
        state["next"] = 0.0
        return
    index = state["index"] % len(items) if rotate else 0
    await bot.change_presence(status=status, activity=build(bot, items[index]))
    if rotate and len(items) > 1:
        state["index"] = (index + 1) % len(items)
        state["next"] = time.time() + interval
    else:
        state["index"] = 0
        state["next"] = 0.0


async def reset(bot: commands.Bot) -> None:
    state["index"] = 0
    state["next"] = 0.0
    await apply(bot)


async def tick(bot: commands.Bot) -> None:
    items, rotate, _ = effective(current())
    if not rotate or len(items) < 2:
        return
    if time.time() >= state["next"]:
        await apply(bot)
