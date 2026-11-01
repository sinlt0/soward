import re
import time
from collections import defaultdict, deque
from typing import Optional

import discord

YOUNG_ACCOUNT_SECONDS = 14 * 86400
ID_SPREAD_SECONDS = 600

_recent: dict[int, deque] = defaultdict(lambda: deque(maxlen=200))
_flagged: dict[int, dict[int, float]] = defaultdict(dict)


def _name_key(name: str) -> str:
    return re.sub(r"[\d_.\-\s]+", "", name.lower())[:10]


def signals(member: discord.Member, invite: Optional[str]) -> dict:
    return {
        "user_id": member.id,
        "joined": time.time(),
        "created": member.created_at.timestamp(),
        "avatar": member.avatar.key if member.avatar is not None else None,
        "invite": invite,
        "name": _name_key(member.name),
    }


def _groups(entry: dict, others: list[dict]) -> list[tuple[str, list[dict]]]:
    now = entry["joined"]
    young = now - entry["created"] <= YOUNG_ACCOUNT_SECONDS
    found: list[tuple[str, list[dict]]] = []
    if entry["avatar"]:
        same = [o for o in others if o["avatar"] == entry["avatar"]]
        found.append(("the same custom avatar", same))
    if entry["invite"] and young:
        same = [o for o in others if o["invite"] == entry["invite"] and now - o["created"] <= YOUNG_ACCOUNT_SECONDS]
        found.append((f"new accounts from invite `{entry['invite']}`", same))
    if len(entry["name"]) >= 3:
        same = [o for o in others if o["name"] == entry["name"]]
        found.append((f"the name pattern `{entry['name']}`", same))
    if young:
        same = [o for o in others if abs(o["created"] - entry["created"]) <= ID_SPREAD_SECONDS]
        found.append(("accounts created minutes apart", same))
    return found


def check(guild_id: int, entry: dict, count: int, window: float) -> Optional[tuple[str, list[int]]]:
    now = entry["joined"]
    pool = _recent[guild_id]
    while pool and now - pool[0]["joined"] > window:
        pool.popleft()
    others = [o for o in pool if o["user_id"] != entry["user_id"]]
    pool.append(entry)
    best: Optional[tuple[str, list[int]]] = None
    for reason, same in _groups(entry, others):
        if len(same) + 1 < count:
            continue
        members = [o["user_id"] for o in same] + [entry["user_id"]]
        if best is None or len(members) > len(best[1]):
            best = (f"{len(members)} joins with {reason}", members)
    return best


def unflagged(guild_id: int, user_ids: list[int]) -> list[int]:
    now = time.time()
    done = _flagged[guild_id]
    for user_id in [u for u, t in done.items() if now - t > 3600]:
        done.pop(user_id, None)
    fresh = [u for u in user_ids if u not in done]
    for user_id in fresh:
        done[user_id] = now
    return fresh
