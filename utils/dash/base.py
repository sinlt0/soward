from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import discord

SECTIONS: dict[str, list[Callable[[discord.Guild], Awaitable[dict]]]] = {}
ACTIONS: dict[tuple[str, str], Callable[["ActionContext", dict], Awaitable[list]]] = {}


@dataclass
class ActionContext:
    bot: Any
    guild: discord.Guild
    user_id: int
    user_name: str


def section(module: str):
    def register(func):
        SECTIONS.setdefault(module, []).append(func)
        return func
    return register


def action(module: str, name: str):
    def register(func):
        ACTIONS[(module, name)] = func
        return func
    return register


def fld(key: str, label: str, kind: str, value: Any = None, help: str = "", placeholder: str = "", maxlen: int = 200,
        lo: Optional[int] = None, hi: Optional[int] = None, options: Optional[list] = None) -> dict:
    return {
        "key": key, "label": label, "kind": kind, "value": value, "help": help, "placeholder": placeholder,
        "maxlen": maxlen, "min": lo, "max": hi,
        "options": [{"value": str(v), "label": l} for v, l in (options or [])],
    }


def button(name: str, label: str, fields: Optional[list] = None, style: str = "ghost", confirm: str = "",
           title: str = "", prefill: bool = False, submit: str = "") -> dict:
    return {
        "name": name, "label": label, "style": style, "confirm": confirm, "title": title or label,
        "fields": fields, "prefill": prefill, "submit": submit or label,
    }


def table(key: str, title: str, columns: list, rows: list, empty: str, description: str = "", buttons: Optional[list] = None) -> dict:
    return {
        "key": key, "title": title, "description": description, "columns": columns, "rows": rows, "empty": empty,
        "buttons": buttons or [],
    }


def row(row_id: Any, cells: list, actions: Optional[list] = None, values: Optional[dict] = None) -> dict:
    return {"id": str(row_id), "cells": [str(c) for c in cells], "actions": actions or [], "values": values or {}}


def need_text(values: dict, key: str, label: str, *, maxlen: int = 200, required: bool = True) -> str:
    raw = values.get(key)
    text = str(raw).strip() if raw is not None else ""
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > maxlen:
        raise ValueError(f"{label} must be {maxlen} characters or fewer.")
    return text


def need_int(values: dict, key: str, label: str, lo: int, hi: int) -> int:
    try:
        number = int(float(values.get(key)))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if number < lo or number > hi:
        raise ValueError(f"{label} must be between {lo} and {hi}.")
    return number


def need_bool(values: dict, key: str) -> bool:
    raw = values.get(key)
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "on", "yes")
    return bool(raw)


def need_lines(values: dict, key: str, label: str, *, limit: int, maxlen: int = 200) -> list[str]:
    raw = values.get(key)
    items = raw if isinstance(raw, list) else str(raw or "").splitlines()
    out = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if len(text) > maxlen:
            raise ValueError(f"Each entry in {label} must be {maxlen} characters or fewer.")
        out.append(text)
    if len(out) > limit:
        raise ValueError(f"{label} allows at most {limit} entries.")
    return out


def need_choice(values: dict, key: str, label: str, allowed: list[str]) -> str:
    raw = str(values.get(key, ""))
    if raw not in allowed:
        raise ValueError(f"{label} has an invalid option.")
    return raw


def opt_channel(guild: discord.Guild, values: dict, key: str, label: str, kinds: tuple = (discord.TextChannel,)) -> Optional[discord.abc.GuildChannel]:
    raw = values.get(key)
    if raw in (None, "", "0"):
        return None
    channel = guild.get_channel(int(raw)) if str(raw).isdigit() else None
    if channel is None or not isinstance(channel, kinds):
        raise ValueError(f"{label} must be a channel in this server.")
    return channel


def need_channel(guild: discord.Guild, values: dict, key: str, label: str, kinds: tuple = (discord.TextChannel,)) -> discord.abc.GuildChannel:
    channel = opt_channel(guild, values, key, label, kinds)
    if channel is None:
        raise ValueError(f"{label} is required.")
    return channel


def opt_role(guild: discord.Guild, values: dict, key: str, label: str) -> Optional[discord.Role]:
    raw = values.get(key)
    if raw in (None, "", "0"):
        return None
    role = guild.get_role(int(raw)) if str(raw).isdigit() else None
    if role is None or role.is_default():
        raise ValueError(f"{label} must be a role in this server.")
    return role


def need_role(guild: discord.Guild, values: dict, key: str, label: str) -> discord.Role:
    role = opt_role(guild, values, key, label)
    if role is None:
        raise ValueError(f"{label} is required.")
    return role


def need_roles(guild: discord.Guild, values: dict, key: str, label: str, *, limit: int) -> list[discord.Role]:
    raw = values.get(key)
    roles = []
    for item in raw if isinstance(raw, list) else []:
        role = guild.get_role(int(item)) if str(item).isdigit() else None
        if role is None or role.is_default():
            raise ValueError(f"{label} contains a role that no longer exists.")
        if role not in roles:
            roles.append(role)
    if len(roles) > limit:
        raise ValueError(f"{label} allows at most {limit} roles.")
    return roles


def need_categories(guild: discord.Guild, values: dict, key: str, label: str, *, limit: int) -> list[discord.CategoryChannel]:
    raw = values.get(key)
    found = []
    for item in raw if isinstance(raw, list) else []:
        category = guild.get_channel(int(item)) if str(item).isdigit() else None
        if not isinstance(category, discord.CategoryChannel):
            raise ValueError(f"{label} contains a category that no longer exists.")
        if category not in found:
            found.append(category)
    if len(found) > limit:
        raise ValueError(f"{label} allows at most {limit} categories.")
    return found


async def collect_sections(guild: discord.Guild, module: str) -> list[dict]:
    return [await func(guild) for func in SECTIONS.get(module, [])]
