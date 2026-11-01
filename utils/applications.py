import copy
import json
import time
from typing import Optional

from utils import db

QUESTION_TYPES = {
    "text": "Short text",
    "paragraph": "Long text",
    "choice": "Pick one",
    "multi": "Pick several",
    "yesno": "Yes or no",
}
ROLE_LISTS = {
    "ping": "Pinged when an application arrives",
    "required": "Applicants must have all of these",
    "blocked": "Applicants with any of these cannot apply",
    "reviewers": "Can accept, deny and vote",
    "accept_add": "Given on acceptance",
    "accept_remove": "Removed on acceptance",
    "deny_add": "Given on denial",
    "deny_remove": "Removed on denial",
}
MAX_QUESTIONS = 25
MAX_OPTIONS = 25
STATUS_LABELS = {"pending": "Pending", "accepted": "Accepted", "denied": "Denied", "withdrawn": "Withdrawn"}

DEFAULT_FORM = {
    "title": "",
    "description": "",
    "enabled": True,
    "channel_id": None,
    "color": "#5865F2",
    "cooldown_hours": 0,
    "min_account_days": 0,
    "min_join_days": 0,
    "slots": 0,
    "accepted": 0,
    "thread": True,
    "votes": True,
    "require_reason": False,
    "autodeny_leave": True,
    "interview_category_id": None,
    "interview_delete": False,
    "interview_delay_minutes": 5,
    "dm_submit": "Your application for **{form}** in {server} was received. Staff will review it soon. Your application number is **#{id}**.",
    "dm_accept": "Congratulations {username}! Your application for **{form}** in {server} was **accepted**.{reason}",
    "dm_deny": "Your application for **{form}** in {server} was **denied**.{reason}",
    "roles": {key: [] for key in ROLE_LISTS},
    "questions": [],
}


def new_form(title: str) -> dict:
    form = copy.deepcopy(DEFAULT_FORM)
    form["title"] = title
    return form


def _merge(data: dict) -> dict:
    form = copy.deepcopy(DEFAULT_FORM)
    for key, value in data.items():
        if key == "roles" and isinstance(value, dict):
            form["roles"].update({k: list(v) for k, v in value.items() if k in ROLE_LISTS})
        else:
            form[key] = value
    return form


async def get_form(guild_id: int, name: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT data FROM app_forms WHERE guild_id=? AND name=?", (guild_id, name.lower()))
    return _merge(json.loads(row["data"])) if row else None


async def list_forms(guild_id: int) -> dict[str, dict]:
    rows = await db.raw_fetch("SELECT name, data FROM app_forms WHERE guild_id=? ORDER BY name", (guild_id,))
    return {row["name"]: _merge(json.loads(row["data"])) for row in rows}


async def save_form(guild_id: int, name: str, form: dict) -> None:
    await db.raw_execute(
        "INSERT INTO app_forms (guild_id, name, data, created_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id, name) DO UPDATE SET data=excluded.data",
        (guild_id, name.lower(), json.dumps(form), time.time()),
    )


async def delete_form(guild_id: int, name: str) -> None:
    await db.raw_execute("DELETE FROM app_forms WHERE guild_id=? AND name=?", (guild_id, name.lower()))


def _sub(row) -> dict:
    data = dict(row)
    data["answers"] = json.loads(data["answers"] or "[]")
    return data


async def get_sub(guild_id: int, app_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM app_submissions WHERE guild_id=? AND app_id=?", (guild_id, app_id))
    return _sub(row) if row else None


async def next_id(guild_id: int) -> int:
    row = await db.raw_fetchone("SELECT COALESCE(MAX(app_id), 0) AS n FROM app_submissions WHERE guild_id=?", (guild_id,))
    return int(row["n"]) + 1


async def insert_sub(sub: dict) -> None:
    await db.raw_execute(
        "INSERT INTO app_submissions (guild_id, app_id, form, user_id, answers, status, reviewer_id, reason, message_id, channel_id,"
        " thread_id, interview_channel_id, created_at, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sub["guild_id"], sub["app_id"], sub["form"], sub["user_id"], json.dumps(sub["answers"]), sub["status"], sub.get("reviewer_id"),
         sub.get("reason"), sub.get("message_id"), sub.get("channel_id"), sub.get("thread_id"), sub.get("interview_channel_id"),
         sub["created_at"], sub.get("decided_at")),
    )


async def update_sub(guild_id: int, app_id: int, **fields) -> None:
    for column, value in fields.items():
        await db.raw_execute(f"UPDATE app_submissions SET {column}=? WHERE guild_id=? AND app_id=?", (value, guild_id, app_id))


async def vote_counts(guild_id: int, app_id: int) -> tuple[int, int]:
    rows = await db.raw_fetch("SELECT vote, COUNT(*) AS n FROM app_votes WHERE guild_id=? AND app_id=? GROUP BY vote", (guild_id, app_id))
    tally = {r["vote"]: r["n"] for r in rows}
    return tally.get(1, 0), tally.get(-1, 0)


async def toggle_vote(guild_id: int, app_id: int, user_id: int, vote: int) -> None:
    row = await db.raw_fetchone("SELECT vote FROM app_votes WHERE guild_id=? AND app_id=? AND user_id=?", (guild_id, app_id, user_id))
    if row and row["vote"] == vote:
        await db.raw_execute("DELETE FROM app_votes WHERE guild_id=? AND app_id=? AND user_id=?", (guild_id, app_id, user_id))
        return
    await db.raw_execute(
        "INSERT INTO app_votes (guild_id, app_id, user_id, vote) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(guild_id, app_id, user_id) DO UPDATE SET vote=excluded.vote",
        (guild_id, app_id, user_id, vote),
    )


def fill(template: str, **values) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def color_int(value: str) -> int:
    try:
        return int(str(value).lstrip("#"), 16)
    except ValueError:
        return 0x5865F2


def panel_state(entries: list[tuple[str, dict]]) -> str:
    return ",".join(f"{name}:{1 if form['enabled'] else 0}" for name, form in entries)


async def record_panel(guild_id: int, channel_id: int, message_id: int, names: list[str], state: str) -> None:
    await db.raw_execute(
        "INSERT INTO app_panels (message_id, guild_id, channel_id, forms, state) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(message_id) DO UPDATE SET forms=excluded.forms, state=excluded.state",
        (message_id, guild_id, channel_id, json.dumps(names), state))


async def panels(guild_id: Optional[int] = None) -> list[dict]:
    if guild_id is None:
        rows = await db.raw_fetch("SELECT * FROM app_panels")
    else:
        rows = await db.raw_fetch("SELECT * FROM app_panels WHERE guild_id=?", (guild_id,))
    out = []
    for row in rows:
        item = dict(row)
        item["forms"] = json.loads(item["forms"])
        out.append(item)
    return out


async def set_panel_state(message_id: int, state: str) -> None:
    await db.raw_execute("UPDATE app_panels SET state=? WHERE message_id=?", (state, message_id))


async def delete_panel(message_id: int) -> None:
    await db.raw_execute("DELETE FROM app_panels WHERE message_id=?", (message_id,))
