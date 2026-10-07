import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

log = logging.getLogger("soward.bus")

class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, coro: Callable[..., Coroutine]) -> None:
        self._listeners[event].append(coro)
        log.debug("Bus: %s subscribed to '%s'", coro.__qualname__, event)

    def unsubscribe(self, event: str, coro: Callable) -> None:
        try:
            self._listeners[event].remove(coro)
        except ValueError:
            pass

    async def publish(self, event: str, **kwargs: Any) -> None:
        listeners = self._listeners.get(event, [])
        if not listeners:
            return
        log.debug("Bus: publishing '%s' to %d listener(s)", event, len(listeners))
        results = await asyncio.gather(
            *[listener(**kwargs) for listener in listeners], return_exceptions=True
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error("Bus listener error on '%s' (listener %d): %s", event, i, result)

bus = EventBus()

AUTOMOD_VIOLATION = "automod.violation"
ANTINUKE_TRIGGERED = "antinuke.triggered"
ANTINUKE_INCIDENT = "antinuke.incident"
ANTINUKE_QUARANTINED = "antinuke.quarantined"
ANTINUKE_RELEASED = "antinuke.released"
ANTIRAID_JOIN_FLAGGED = "antiraid.join_flagged"
ANTIRAID_RAID_MODE_STARTED = "antiraid.raid_mode_started"
ANTIRAID_RAID_MODE_ENDED = "antiraid.raid_mode_ended"
VERIFICATION_SUCCESS = "verification.success"
VERIFICATION_FAILED = "verification.failed"
MEMBER_VERIFIED = "member.verified"
MEMBER_JOINED_UNVERIFIED = "member.joined_unverified"
AUTOROLE_ASSIGN = "autorole.assign"
AUTOROLE_STRIP = "autorole.strip"
INCIDENT_STATE_CHANGED = "incident.state_changed"
MOD_ACTION = "mod.action"
LOG_EVENT = "log.event"
PANIC_MODE_STARTED = "panic_mode.started"
PANIC_MODE_ENDED = "panic_mode.ended"
