import secrets
import time
from typing import Optional

import config
from utils import cosmetics, db


async def all_of(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM pets WHERE owner_id=? ORDER BY born_at", (user_id,))
    return [dict(r) for r in rows]


async def active(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM pets WHERE owner_id=? AND active=1", (user_id,))
    return dict(row) if row else None


async def find(user_id: int, name: str) -> Optional[dict]:
    key = name.strip().lower()
    for pet in await all_of(user_id):
        if pet["name"].lower() == key or pet["pet_id"] == key:
            return pet
    return None


async def adopt(user_id: int, species: str, name: str) -> dict:
    existing = await all_of(user_id)
    pet_id = secrets.token_hex(4)
    make_active = 0 if any(p["active"] for p in existing) else 1
    await db.raw_execute(
        "INSERT INTO pets (pet_id, owner_id, species, name, xp, outfit, active, born_at) VALUES (?, ?, ?, ?, 0, '', ?, ?)",
        (pet_id, user_id, species, name[:config.PET_NAME_MAX], make_active, time.time()))
    row = await db.raw_fetchone("SELECT * FROM pets WHERE pet_id=?", (pet_id,))
    return dict(row)


async def set_active(user_id: int, pet_id: str) -> None:
    await db.raw_execute("UPDATE pets SET active=0 WHERE owner_id=?", (user_id,))
    await db.raw_execute("UPDATE pets SET active=1 WHERE owner_id=? AND pet_id=?", (user_id, pet_id))


async def rename(pet_id: str, name: str) -> None:
    await db.raw_execute("UPDATE pets SET name=? WHERE pet_id=?", (name[:config.PET_NAME_MAX], pet_id))


async def wear(pet_id: str, outfit: str) -> None:
    await db.raw_execute("UPDATE pets SET outfit=? WHERE pet_id=?", (outfit, pet_id))


async def release(user_id: int, pet_id: str) -> None:
    pet = await db.raw_fetchone("SELECT active FROM pets WHERE pet_id=? AND owner_id=?", (pet_id, user_id))
    await db.raw_execute("DELETE FROM pets WHERE pet_id=? AND owner_id=?", (pet_id, user_id))
    if pet and pet["active"]:
        remaining = await all_of(user_id)
        if remaining:
            await set_active(user_id, remaining[0]["pet_id"])


async def add_xp(user_id: int, amount: int) -> Optional[dict]:
    pet = await active(user_id)
    if pet is None:
        return None
    before = cosmetics.stage_index(pet["xp"])
    await db.raw_execute("UPDATE pets SET xp=xp+? WHERE pet_id=?", (int(amount), pet["pet_id"]))
    after = cosmetics.stage_index(pet["xp"] + int(amount))
    pet["xp"] += int(amount)
    pet["grew"] = after > before
    return pet
