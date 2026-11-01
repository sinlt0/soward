import time
from collections import defaultdict
from typing import Optional

from utils import db, guild_settings

KEYS = {
    "enabled": ("staff_report_enabled", False),
    "channel": ("staff_report_channel_id", None),
    "spike": ("staff_spike_limit", 8),
}
FIELDS = ("actions", "warns", "tickets_closed", "tickets_claimed", "applications", "appeals", "reports")
SEVERE = ("ban", "kick", "tempban", "massban")


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    out["spike"] = max(3, int(out["spike"] or 8))
    return out


async def set_config(guild_id: int, name: str, value) -> None:
    key, _ = KEYS[name]
    if value is None:
        await guild_settings.delete(guild_id, key)
    else:
        await guild_settings.set(guild_id, key, value)


async def collect(guild_id: int, since: float, until: Optional[float] = None) -> dict[int, dict]:
    until = until or time.time()
    stats: dict[int, dict] = defaultdict(lambda: {f: 0 for f in FIELDS})
    queries = (
        ("actions", "SELECT moderator_id AS uid, COUNT(*) AS c FROM mod_cases WHERE guild_id=? AND created_at>=? AND created_at<? GROUP BY moderator_id"),
        ("warns", "SELECT moderator_id AS uid, COUNT(*) AS c FROM warn_cases WHERE guild_id=? AND created_at>=? AND created_at<? GROUP BY moderator_id"),
        ("tickets_closed", "SELECT closed_by AS uid, COUNT(*) AS c FROM tickets WHERE guild_id=? AND closed_at>=? AND closed_at<? AND closed_by IS NOT NULL GROUP BY closed_by"),
        ("tickets_claimed", "SELECT claimed_by AS uid, COUNT(*) AS c FROM tickets WHERE guild_id=? AND created_at>=? AND created_at<? AND claimed_by IS NOT NULL GROUP BY claimed_by"),
        ("applications", "SELECT reviewer_id AS uid, COUNT(*) AS c FROM app_submissions WHERE guild_id=? AND decided_at>=? AND decided_at<? AND reviewer_id IS NOT NULL GROUP BY reviewer_id"),
        ("appeals", "SELECT reviewer_id AS uid, COUNT(*) AS c FROM ban_appeals WHERE guild_id=? AND decided_at>=? AND decided_at<? AND reviewer_id IS NOT NULL GROUP BY reviewer_id"),
        ("reports", "SELECT handler_id AS uid, COUNT(*) AS c FROM message_reports WHERE guild_id=? AND handled_at>=? AND handled_at<? AND handler_id IS NOT NULL GROUP BY handler_id"),
    )
    for field, sql in queries:
        for row in await db.raw_fetch(sql, (guild_id, since, until)):
            stats[int(row["uid"])][field] = int(row["c"])
    return dict(stats)


def total(entry: dict) -> int:
    return sum(entry.values())


async def severe_recent(guild_id: int, moderator_id: int, window: float = 3600) -> int:
    marks = ",".join("?" for _ in SEVERE)
    row = await db.raw_fetchone(
        f"SELECT COUNT(*) AS c FROM mod_cases WHERE guild_id=? AND moderator_id=? AND created_at>? AND action IN ({marks})",
        (guild_id, moderator_id, time.time() - window, *SEVERE))
    return int(row["c"]) if row else 0


def render_line(uid: int, entry: dict) -> str:
    bits = []
    labels = (("actions", "mod actions"), ("warns", "warns"), ("tickets_closed", "tickets closed"), ("tickets_claimed", "claimed"),
              ("applications", "applications"), ("appeals", "appeals"), ("reports", "reports"))
    for key, label in labels:
        if entry[key]:
            bits.append(f"{entry[key]} {label}")
    return f"<@{uid}> · " + (", ".join(bits) if bits else "no activity")
