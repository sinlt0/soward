import json
import re
import time
from typing import Optional

from utils import db

LIMITS = {"bio": 400, "looking_for": 200, "relationship": 40, "pronouns": 30, "timezone": 40}
MAX_INTERESTS = 10
MAX_INTEREST_LEN = 24


def clean(text: str, limit: int) -> str:
    text = re.sub(r"https?://\S+", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("@everyone", "everyone").replace("@here", "here")
    return text[:limit]


def parse_interests(text: str) -> list[str]:
    seen, out = set(), []
    for part in re.split(r"[,\n;]", str(text or "")):
        item = clean(part, MAX_INTEREST_LEN).lower()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
        if len(out) >= MAX_INTERESTS:
            break
    return out


def _row(row) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    try:
        data["interests"] = json.loads(data.get("interests") or "[]")
    except json.JSONDecodeError:
        data["interests"] = []
    data["hidden"] = bool(data.get("hidden"))
    return data


async def get(guild_id: int, user_id: int) -> Optional[dict]:
    return _row(await db.raw_fetchone("SELECT * FROM member_profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id)))


async def save(guild_id: int, user_id: int, *, bio: str, interests: list[str], looking_for: str, relationship: str, pronouns: str) -> None:
    await db.raw_execute(
        "INSERT INTO member_profiles (guild_id, user_id, bio, interests, looking_for, relationship, pronouns, hidden, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET bio=excluded.bio, interests=excluded.interests, looking_for=excluded.looking_for,"
        " relationship=excluded.relationship, pronouns=excluded.pronouns, updated_at=excluded.updated_at",
        (guild_id, user_id, clean(bio, LIMITS["bio"]), json.dumps(interests), clean(looking_for, LIMITS["looking_for"]),
         clean(relationship, LIMITS["relationship"]), clean(pronouns, LIMITS["pronouns"]), time.time()))


async def set_hidden(guild_id: int, user_id: int, hidden: bool) -> bool:
    row = await db.raw_fetchone("SELECT 1 FROM member_profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    if row is None:
        return False
    await db.raw_execute("UPDATE member_profiles SET hidden=?, updated_at=? WHERE guild_id=? AND user_id=?", (1 if hidden else 0, time.time(), guild_id, user_id))
    return True


async def clear(guild_id: int, user_id: int) -> None:
    await db.raw_execute("DELETE FROM member_profiles WHERE guild_id=? AND user_id=?", (guild_id, user_id))


def shared(a: list[str], b: list[str]) -> list[str]:
    other = set(b)
    return [x for x in a if x in other]
