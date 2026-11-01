import json
import time
import uuid
from collections import Counter
from typing import Optional

import discord

from utils import db, emoji_manager, guild_settings
from utils import security_settings as settings

QUIET_SECONDS = 180
MAX_TIMELINE = 30
MAX_LISTED = 12

_open: dict[int, dict] = {}


def _fresh(guild_id: int, kind: str) -> dict:
    now = time.time()
    return {
        "id": uuid.uuid4().hex[:8].upper(), "guild_id": guild_id, "kind": kind, "started": now, "last": now,
        "triggers": [], "members": [], "limits": [], "undone": Counter(), "timeline": [], "flags": set(), "peak": 0.0,
    }


def _incident(guild_id: int, kind: str = "incident") -> dict:
    current = _open.get(guild_id)
    if current is None:
        current = _open[guild_id] = _fresh(guild_id, kind)
    current["last"] = time.time()
    return current


def _note(item: dict, text: str) -> None:
    if len(item["timeline"]) < MAX_TIMELINE:
        item["timeline"].append((time.time(), text))


def is_open(guild_id: int) -> bool:
    return guild_id in _open


def begin(guild_id: int, kind: str, trigger: str) -> None:
    item = _incident(guild_id, kind)
    item["flags"].add(kind)
    if trigger and trigger not in item["triggers"]:
        item["triggers"].append(trigger)
    _note(item, trigger or kind)


def flag(guild_id: int, name: str, text: str = "") -> None:
    item = _incident(guild_id)
    item["flags"].add(name)
    if text:
        _note(item, text)


def member_action(guild_id: int, user_id: int, action: str, reason: str) -> None:
    if guild_id not in _open:
        return
    item = _incident(guild_id)
    item["members"].append((user_id, action, reason[:80]))
    if len(item["members"]) > 500:
        del item["members"][:100]


def limit_fired(guild_id: int, actor_id: int, action: str, count: int, threshold: int, punishment: str) -> None:
    item = _incident(guild_id, "antinuke")
    item["flags"].add("antinuke")
    item["limits"].append((actor_id, action, count, threshold, punishment))
    _note(item, f"AntiNuke limit hit: {action.replace('_', ' ')} by {actor_id} ({count}/{threshold})")


def undone(guild_id: int, what: str, count: int = 1) -> None:
    if count > 0 and guild_id in _open:
        _incident(guild_id)["undone"][what] += count


def note(guild_id: int, text: str) -> None:
    if guild_id not in _open:
        return
    _note(_incident(guild_id), text)


async def _still_active(guild_id: int) -> bool:
    from utils import threat
    if threat.is_beast(guild_id):
        return True
    row = await db.raw_fetchone("SELECT raid_mode FROM antiraid_state WHERE guild_id=?", (guild_id,))
    if row and row["raid_mode"]:
        return True
    lock = await db.raw_fetchone("SELECT active FROM security_lockdown WHERE guild_id=?", (guild_id,))
    return bool(lock and lock["active"])


def _span(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def _serialise(item: dict, ended: float, peak: float) -> dict:
    return {
        "id": item["id"], "kind": item["kind"], "started": item["started"], "ended": ended, "triggers": item["triggers"],
        "members": item["members"][-200:], "limits": item["limits"], "undone": dict(item["undone"]),
        "timeline": item["timeline"], "flags": sorted(item["flags"]), "peak": peak,
    }


def render(data: dict) -> discord.ui.LayoutView:
    e = emoji_manager.get
    flags = set(data.get("flags", []))
    lines = [
        f"## {e('shield')} Incident post-mortem `{data['id']}`",
        f"**Duration:** {_span(data['ended'] - data['started'])} · started <t:{int(data['started'])}:R>",
    ]
    triggers = data.get("triggers") or []
    lines.append("**What started it:** " + (", ".join(f"`{t[:70]}`" for t in triggers[:4]) if triggers else "AntiNuke detection"))

    protections = []
    if "raid" in flags:
        protections.append("Raid mode")
    if "beast" in flags:
        protections.append("Beast Mode")
    if "whitelist_suspended" in flags:
        protections.append("whitelists suspended")
    if "lockdown" in flags:
        protections.append("server lockdown")
    if "verification" in flags:
        protections.append("verification level raised")
    if protections:
        lines.append("**Protection raised:** " + ", ".join(protections))
    if data.get("peak"):
        lines.append(f"**Peak threat score:** {data['peak']:.1f}")

    members = data.get("members", [])
    if members:
        counts = Counter(action for _, action, _ in members)
        summary = ", ".join(f"{n} {a}" for a, n in counts.most_common())
        lines.append(f"\n**Accounts actioned ({len(members)}):** {summary}")
        for user_id, action, reason in members[:MAX_LISTED]:
            lines.append(f"- <@{user_id}> `{action}` · {reason}")
        if len(members) > MAX_LISTED:
            lines.append(f"-# and {len(members) - MAX_LISTED} more")

    limits = data.get("limits", [])
    if limits:
        lines.append(f"\n**Limits that fired ({len(limits)}):**")
        for actor_id, action, count, threshold, punishment in limits[:MAX_LISTED]:
            lines.append(f"- <@{actor_id}> {action.replace('_', ' ')} {count}/{threshold} → `{punishment}`")

    undone = data.get("undone", {})
    lines.append("\n**What was undone:** " + (", ".join(f"{n} {what}" for what, n in undone.items()) if undone else "nothing needed undoing"))

    timeline = data.get("timeline", [])
    if timeline:
        lines.append("\n**Timeline**")
        for ts, text in timeline[:10]:
            lines.append(f"- <t:{int(ts)}:T> {text[:100]}")

    container = discord.ui.Container(accent_color=0xFEE75C)
    container.add_item(discord.ui.TextDisplay("\n".join(lines)[:3900]))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


async def _target_channel(guild: discord.Guild) -> Optional[discord.abc.Messageable]:
    for module, key in (("antinuke", "alert_channel_id"), ("security", "alert_channel_id"), ("antiraid", "alert_channel_id"), ("security", "log_channel_id")):
        channel_id = await settings.get(guild.id, module, key)
        if channel_id:
            break
    else:
        channel_id = await guild_settings.get(guild.id, "log_channel_id")
    return guild.get_channel(int(channel_id)) if channel_id else None


async def finish(guild: discord.Guild, post: bool = True) -> Optional[dict]:
    from utils import threat
    item = _open.pop(guild.id, None)
    if item is None:
        return None
    ended = time.time()
    peak = max(item["peak"], await threat.score(guild.id))
    data = _serialise(item, ended, peak)
    if not await settings.get(guild.id, "security", "postmortem"):
        return None
    await db.raw_execute(
        "INSERT INTO security_incidents (incident_id, guild_id, kind, started_at, ended_at, summary) VALUES (?, ?, ?, ?, ?, ?)",
        (data["id"], guild.id, item["kind"], item["started"], ended, json.dumps(data)),
    )
    stale = await db.raw_fetch("SELECT incident_id FROM security_incidents WHERE guild_id=? ORDER BY ended_at DESC LIMIT -1 OFFSET 50", (guild.id,))
    for row in stale:
        await db.raw_execute("DELETE FROM security_incidents WHERE incident_id=?", (row["incident_id"],))
    if post:
        channel = await _target_channel(guild)
        if channel is not None:
            try:
                await channel.send(view=render(data))
            except discord.HTTPException:
                pass
    return data


async def sweep(bot) -> None:
    from utils import threat
    now = time.time()
    for guild_id in list(_open):
        item = _open.get(guild_id)
        if item is None:
            continue
        guild = bot.get_guild(guild_id)
        if guild is None:
            _open.pop(guild_id, None)
            continue
        item["peak"] = max(item["peak"], await threat.score(guild_id))
        if now - item["last"] < QUIET_SECONDS or await _still_active(guild_id):
            continue
        await finish(guild)


async def history(guild_id: int, limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch("SELECT incident_id, kind, started_at, ended_at FROM security_incidents WHERE guild_id=? ORDER BY ended_at DESC LIMIT ?", (guild_id, limit))
    return [dict(r) for r in rows]


async def load(guild_id: int, incident_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT summary FROM security_incidents WHERE guild_id=? AND incident_id=?", (guild_id, incident_id.upper()))
    return json.loads(row["summary"]) if row else None
