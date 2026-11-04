import re
import secrets
import time
from typing import Optional

import config
from utils import db


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text.replace("@everyone", "everyone").replace("@here", "here")[:config.TODO_TEXT_MAX]


async def items(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM todos WHERE user_id=? ORDER BY done, created_at", (user_id,))
    return [dict(r) for r in rows]


async def add(user_id: int, text: str) -> Optional[dict]:
    if len(await items(user_id)) >= config.TODO_LIMIT:
        return None
    todo_id = secrets.token_hex(4)
    await db.raw_execute("INSERT INTO todos (todo_id, user_id, text, done, created_at) VALUES (?, ?, ?, 0, ?)", (todo_id, user_id, clean(text), time.time()))
    return {"todo_id": todo_id, "text": clean(text)}


async def at(user_id: int, number: int) -> Optional[dict]:
    listing = await items(user_id)
    return listing[number - 1] if 1 <= number <= len(listing) else None


async def set_done(todo_id: str, done: bool) -> None:
    await db.raw_execute("UPDATE todos SET done=?, done_at=? WHERE todo_id=?", (1 if done else 0, time.time() if done else None, todo_id))


async def edit(todo_id: str, text: str) -> None:
    await db.raw_execute("UPDATE todos SET text=? WHERE todo_id=?", (clean(text), todo_id))


async def remove(todo_id: str) -> None:
    await db.raw_execute("DELETE FROM todos WHERE todo_id=?", (todo_id,))


async def clear_done(user_id: int) -> int:
    cursor = await db.raw_execute("DELETE FROM todos WHERE user_id=? AND done=1", (user_id,))
    return getattr(cursor, "rowcount", 0)
