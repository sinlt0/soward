import time
from typing import Optional

import discord

import config
from utils import db

maintenance = {"on": False, "reason": "", "since": 0.0}
notified: dict = {}
disabled: dict = {}


async def load() -> None:
    data = await db.get("dev", "maintenance")
    if isinstance(data, dict):
        maintenance.update({"on": bool(data.get("on")), "reason": str(data.get("reason", "")), "since": float(data.get("since", 0))})
    rows = await db.get("dev", "disabled_commands")
    disabled.clear()
    if isinstance(rows, dict):
        disabled.update({str(k): str(v) for k, v in rows.items()})


async def save_disabled() -> None:
    await db.set("dev", "disabled_commands", dict(disabled))


def disabled_reason(qualified_name: str) -> Optional[str]:
    for name, reason in disabled.items():
        if qualified_name == name or qualified_name.startswith(name + " "):
            return reason or ""
    return None


async def set_maintenance(on: bool, reason: str = "") -> None:
    maintenance.update({"on": on, "reason": reason if on else "", "since": time.time() if on else 0.0})
    await db.set("dev", "maintenance", dict(maintenance))


def exempt(user_id: int, roles=()) -> bool:
    if user_id in config.ALL_PRIVILEGED_IDS:
        return True
    return bool({r.id for r in roles} & set(config.DEV_ROLE_IDS))


def blocks(user: discord.abc.User) -> bool:
    return maintenance["on"] and not exempt(user.id, getattr(user, "roles", ()))


def notice_due(user_id: int) -> bool:
    now = time.time()
    if now - notified.get(user_id, 0) < 15:
        return False
    notified[user_id] = now
    return True


def notice_text() -> str:
    reason = f"\n\n**Reason:** {maintenance['reason']}" if maintenance["reason"] else ""
    return f"{config.BOT_NAME} is under maintenance right now. Everything is paused and will be back soon.{reason}"
