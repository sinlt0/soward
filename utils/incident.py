import logging
import time
from typing import Optional

from utils import db
from utils.events_bus import bus, INCIDENT_STATE_CHANGED
import config

log = logging.getLogger("soward.incident")

_cache: dict[int, int] = {}

async def get_state(guild_id: int) -> int:
    if guild_id in _cache:
        return _cache[guild_id]
    row = await db.raw_fetchone(
        "SELECT incident_state FROM guilds WHERE guild_id=?", (guild_id,)
    )
    state = row["incident_state"] if row else config.INCIDENT_STATES["normal"]
    _cache[guild_id] = state
    return state

async def set_state(guild_id: int, state: int, actor_id: Optional[int] = None) -> None:
    previous = await get_state(guild_id)
    if previous == state:
        return

    _cache[guild_id] = state
    await db.raw_execute(
        "INSERT INTO guilds (guild_id, incident_state) VALUES (?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET incident_state=excluded.incident_state",
        (guild_id, state),
    )

    state_names = {v: k for k, v in config.INCIDENT_STATES.items()}
    log.warning(
        "Guild %d incident state: %s → %s (actor=%s)",
        guild_id,
        state_names.get(previous, previous),
        state_names.get(state, state),
        actor_id,
    )

    await bus.publish(
        INCIDENT_STATE_CHANGED,
        guild_id=guild_id,
        previous_state=previous,
        new_state=state,
        actor_id=actor_id,
    )

async def escalate(guild_id: int, actor_id: Optional[int] = None) -> int:
    current = await get_state(guild_id)
    max_state = max(config.INCIDENT_STATES.values())
    new_state = min(current + 1, max_state)
    await set_state(guild_id, new_state, actor_id)
    return new_state

async def de_escalate(guild_id: int, actor_id: Optional[int] = None) -> int:
    current = await get_state(guild_id)
    new_state = max(current - 1, 0)
    await set_state(guild_id, new_state, actor_id)
    return new_state

async def reset(guild_id: int, actor_id: Optional[int] = None) -> None:
    await set_state(guild_id, config.INCIDENT_STATES["normal"], actor_id)
