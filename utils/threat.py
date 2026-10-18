import time
from collections import defaultdict, deque

from utils import security_settings as settings
from utils.events_bus import LOG_EVENT, bus

_events: dict[int, deque] = defaultdict(lambda: deque(maxlen=200))
_beast_until: dict[int, float] = {}

POINTS = {
    "antinuke": 4.0,
    "raid_mode": 3.0,
    "automod_severe": 2.0,
    "automod_punish": 1.0,
    "raid_join": 0.5,
    "verify_lockout": 1.0,
    "verify_alt": 1.5,
    "verify_vpn": 0.5,
    "quarantine_touch": 3.0,
}


async def _enabled(guild_id: int) -> bool:
    return bool(await settings.get(guild_id, "security", "threat_score"))


async def score(guild_id: int) -> float:
    window = await settings.get(guild_id, "security", "threat_window")
    now = time.time()
    events = _events[guild_id]
    while events and now - events[0][0] > window:
        events.popleft()
    return sum(points for _, points, _ in events)


def is_beast(guild_id: int) -> bool:
    until = _beast_until.get(guild_id, 0)
    if until and time.time() < until:
        return True
    _beast_until.pop(guild_id, None)
    return False


def deactivate(guild_id: int) -> bool:
    return _beast_until.pop(guild_id, None) is not None


async def add(guild_id: int, kind: str, reason: str = "") -> float:
    if not await _enabled(guild_id):
        return 0.0
    _events[guild_id].append((time.time(), POINTS.get(kind, 1.0), reason or kind))
    total = await score(guild_id)
    threshold = await settings.get(guild_id, "security", "threat_threshold")
    if total >= threshold and not is_beast(guild_id):
        window = await settings.get(guild_id, "security", "threat_window")
        _beast_until[guild_id] = time.time() + window
        await bus.publish(LOG_EVENT, guild_id=guild_id, action="beast_mode", active=True, reason=f"threat score {total:.1f}")
    return total


async def recent(guild_id: int, limit: int = 10) -> list[tuple[float, float, str]]:
    await score(guild_id)
    return list(_events[guild_id])[-limit:]
