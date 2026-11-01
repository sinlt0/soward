import calendar
import re
import time
import uuid
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional

from utils import db, guild_settings

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

KEYS = {
    "channel": ("event_channel_id", None),
    "timezone": ("event_timezone", "UTC"),
    "role": ("event_ping_role_id", None),
}
REPEATS = {"none": 0, "daily": 86400, "weekly": 7 * 86400}
STATUSES = ("going", "maybe", "no", "waitlist")
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9
WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
WEEKDAYS.update({name.lower(): i for i, name in enumerate(calendar.day_abbr)})
UNITS = {"m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
         "d": 86400, "day": 86400, "days": 86400, "w": 604800, "wk": 604800, "week": 604800, "weeks": 604800}


def parse_tz(text: str) -> Optional[tzinfo]:
    value = str(text or "").strip()
    match = re.fullmatch(r"(?:utc|gmt)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", value, re.I)
    if match:
        sign = -1 if match.group(1) == "-" else 1
        hours, minutes = int(match.group(2)), int(match.group(3) or 0)
        if hours > 14 or minutes > 59:
            return None
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    if value.lower() in ("utc", "gmt", "z"):
        return timezone.utc
    if ZoneInfo is not None:
        try:
            return ZoneInfo(value)
        except Exception:
            return None
    return None


def parse_when(text: str, now: float, tz: tzinfo) -> Optional[float]:
    raw = str(text or "").strip().lower()
    if not raw:
        return None
    stamp = re.search(r"<t:(\d{9,11})(?::[a-z])?>", raw)
    if stamp:
        return float(stamp.group(1))
    if re.fullmatch(r"\d{10}", raw):
        return float(raw)
    rel = re.fullmatch(r"(?:in\s+)?((?:\d+\s*[a-z]+\s*)+)", raw)
    if rel and (raw.startswith("in ") or re.search(r"\d\s*[a-z]", raw) and not re.search(r"\d{1,2}\s*(am|pm)\b|:", raw) and not any(m in raw.split() for m in MONTHS)):
        total = 0
        parts = re.findall(r"(\d+)\s*([a-z]+)", rel.group(1))
        if parts and all(unit in UNITS for _, unit in parts):
            for amount, unit in parts:
                total += int(amount) * UNITS[unit]
            return now + total if total else None
    local_now = datetime.fromtimestamp(now, tz)
    working = raw
    hour = minute = None
    clock = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", working)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2))
        if clock.group(3):
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if clock.group(3) == "pm" else 0)
        working = working.replace(clock.group(0), " ")
    else:
        short = re.search(r"\b(\d{1,2})\s*(am|pm)\b", working)
        if short:
            hour = int(short.group(1))
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if short.group(2) == "pm" else 0)
            minute = 0
            working = working.replace(short.group(0), " ")
    if hour is None or minute is None or hour > 23 or minute > 59:
        return None
    working = working.replace(",", " ").replace(" at ", " ").replace(" on ", " ")
    tokens = working.split()
    date = None
    iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", working)
    dmy = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", working)
    try:
        if iso:
            date = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), tzinfo=tz)
        elif dmy:
            year = int(dmy.group(3)) if dmy.group(3) else local_now.year
            year += 2000 if year < 100 else 0
            date = datetime(year, int(dmy.group(2)), int(dmy.group(1)), tzinfo=tz)
        else:
            cleaned = [re.sub(r"(st|nd|rd|th)$", "", t) for t in tokens]
            for i, tok in enumerate(cleaned):
                if tok in MONTHS:
                    nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""
                    prv = cleaned[i - 1] if i > 0 else ""
                    day = int(nxt) if nxt.isdigit() and len(nxt) <= 2 else int(prv) if prv.isdigit() and len(prv) <= 2 else None
                    if day is None:
                        return None
                    year = local_now.year
                    for neighbor in (nxt, prv):
                        if neighbor.isdigit() and len(neighbor) == 4:
                            year = int(neighbor)
                    date = datetime(year, MONTHS[tok], day, tzinfo=tz)
                    break
            if date is None:
                if "tomorrow" in cleaned:
                    date = local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                elif "today" in cleaned:
                    date = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    for tok in cleaned:
                        if tok in WEEKDAYS:
                            ahead = (WEEKDAYS[tok] - local_now.weekday()) % 7
                            date = local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=ahead)
                            break
    except ValueError:
        return None
    explicit = date is not None
    if date is None:
        date = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    moment = date.replace(hour=hour, minute=minute)
    if not explicit and moment.timestamp() <= now:
        moment += timedelta(days=1)
    elif explicit and iso is None and dmy is None and moment.timestamp() <= now and not any(t in ("today", "tomorrow") for t in tokens):
        if any(t in WEEKDAYS for t in tokens):
            moment += timedelta(days=7)
        elif any(re.sub(r"(st|nd|rd|th)$", "", t) in MONTHS for t in tokens) and not re.search(r"\b\d{4}\b", working):
            try:
                moment = moment.replace(year=moment.year + 1)
            except ValueError:
                return None
    return moment.timestamp()


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


async def create(guild_id: int, creator_id: int, title: str, description: str, starts_at: float, channel_id: int, *, duration: int = 60,
                 role_id: Optional[int] = None, voice_id: Optional[int] = None, capacity: int = 0, repeat: str = "none") -> str:
    event_id = uuid.uuid4().hex[:6].upper()
    await db.raw_execute(
        "INSERT INTO server_events (event_id, guild_id, title, description, starts_at, duration_minutes, channel_id, voice_channel_id, role_id, creator_id,"
        " repeat, capacity, status, reminded, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', 0, ?)",
        (event_id, guild_id, title[:100], description[:1000], starts_at, duration, channel_id, voice_id, role_id, creator_id, repeat, capacity, time.time()))
    return event_id


async def get(guild_id: int, event_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM server_events WHERE guild_id=? AND event_id=?", (guild_id, event_id.upper()))
    return dict(row) if row else None


async def upcoming(guild_id: int, limit: int = 15) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT * FROM server_events WHERE guild_id=? AND status IN ('scheduled', 'started') ORDER BY starts_at LIMIT ?", (guild_id, limit))
    return [dict(r) for r in rows]


async def live_events() -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM server_events WHERE status IN ('scheduled', 'started')")
    return [dict(r) for r in rows]


async def update(event_id: str, **fields) -> None:
    if not fields:
        return
    names = ", ".join(f"{k}=?" for k in fields)
    await db.raw_execute(f"UPDATE server_events SET {names} WHERE event_id=?", (*fields.values(), event_id))


async def rsvps(event_id: str) -> dict[str, list[int]]:
    rows = await db.raw_fetch("SELECT user_id, status FROM event_rsvps WHERE event_id=? ORDER BY created_at", (event_id,))
    out: dict[str, list[int]] = {s: [] for s in STATUSES}
    for r in rows:
        out.setdefault(r["status"], []).append(r["user_id"])
    return out


async def rsvp(event: dict, user_id: int, wanted: str) -> str:
    current = await rsvps(event["event_id"])
    if wanted == "going" and user_id not in current["going"]:
        capacity = int(event.get("capacity") or 0)
        if capacity and len(current["going"]) >= capacity:
            wanted = "waitlist"
    await db.raw_execute(
        "INSERT INTO event_rsvps (event_id, user_id, status, created_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(event_id, user_id) DO UPDATE SET status=excluded.status",
        (event["event_id"], user_id, wanted, time.time()))
    if user_id in current["going"] and wanted != "going":
        await promote(event)
    return wanted


async def promote(event: dict) -> Optional[int]:
    current = await rsvps(event["event_id"])
    capacity = int(event.get("capacity") or 0)
    if not current["waitlist"] or (capacity and len(current["going"]) >= capacity):
        return None
    chosen = current["waitlist"][0]
    await db.raw_execute("UPDATE event_rsvps SET status='going' WHERE event_id=? AND user_id=?", (event["event_id"], chosen))
    return chosen
