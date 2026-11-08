import time
from typing import Optional

from rpg import chapters, engine, gear, quest, races, settings, titles, ways
from utils import db

MAX_MATERIALS = 99
MAX_PILLS = 10


def realm_index(text: str) -> Optional[int]:
    text = text.strip().lower()
    if text.isdigit():
        number = int(text)
        return number if 0 <= number < len(settings.REALMS) else None
    for index, info in enumerate(settings.REALMS):
        if text in (info["name"].lower(), info["name"].lower().replace(" ", "_"), info["name"].lower().replace(" ", "")):
            return index
    return None


def stage_index(realm: int, text: str) -> Optional[int]:
    stages = settings.REALMS[realm]["stages"]
    text = text.strip().lower()
    if text in ("max", "peak", "last"):
        return len(stages) - 1
    if text.isdigit():
        number = int(text) - 1
        return number if 0 <= number < len(stages) else None
    for index, name in enumerate(stages):
        if text == name.lower() or text == name.lower().replace(" ", ""):
            return index
    return None


def item_valid(key: str) -> bool:
    return key in settings.ITEMS or key in settings.BREWS or key in gear.MATERIALS or gear.parse(key) is not None


async def ensure(user_id: int) -> dict:
    character = await engine.get(user_id)
    if character is None:
        character = await engine.awaken(user_id)
    return character


async def set_progress(user_id: int, realm: int, stage: int, qi: Optional[int] = None) -> dict:
    character = await ensure(user_id)
    character["realm"] = realm
    character["stage"] = stage
    character["qi"] = max(0, min(int(qi), engine.need(character))) if qi is not None else 0
    character["last_tick"] = time.time()
    character["injured_until"] = 0
    await engine.save(character)
    return await engine.get(user_id)


async def set_way(user_id: int, way: str) -> bool:
    if way not in ways.WAYS:
        return False
    await ensure(user_id)
    await db.raw_execute("UPDATE cult_characters SET way=? WHERE user_id=?", (way, user_id))
    return True


async def set_path(user_id: int, path: str) -> bool:
    if path not in settings.PATHS:
        return False
    await ensure(user_id)
    await db.raw_execute("UPDATE cult_characters SET path=?, last_tick=? WHERE user_id=?", (path, time.time(), user_id))
    return True


async def set_race(user_id: int, race: str) -> bool:
    if race not in races.RACES:
        return False
    await ensure(user_id)
    await db.raw_execute("UPDATE cult_characters SET race=? WHERE user_id=?", (race, user_id))
    return True


async def set_root(user_id: int, rarity: str, root: str, quality: str) -> bool:
    names = settings.ROOTS.get(rarity, {}).get("names", ())
    root = next((name for name in names if name.lower() == root.lower()), None)
    quality = next((q["name"] for q in settings.QUALITIES if q["name"].lower() == quality.lower()), None)
    if root is None or quality is None:
        return False
    await ensure(user_id)
    await db.raw_execute("UPDATE cult_characters SET rarity=?, root=?, quality=? WHERE user_id=?", (rarity, root, quality, user_id))
    return True


async def give_item(user_id: int, key: str, qty: int) -> bool:
    if not item_valid(key) or qty <= 0:
        return False
    await engine.add_item(user_id, key, qty)
    return True


async def top_up(user_id: int, key: str, target: int) -> None:
    have = (await engine.inventory(user_id)).get(key, 0)
    if have < target:
        await engine.add_item(user_id, key, target - have)


async def max_account(user_id: int, path: Optional[str] = None, way: Optional[str] = None) -> dict:
    character = await ensure(user_id)
    way = way if way in ways.WAYS else (character["way"] or "immortal")
    path = path if path in settings.PATHS else (character["path"] or engine.allowed_paths(character)[0])
    realm = len(settings.REALMS) - 1
    stage = len(settings.REALMS[realm]["stages"]) - 1
    best = len(gear.GRADES) - 1
    await db.raw_execute(
        "UPDATE cult_characters SET way=?, path=?, realm=?, stage=?, injured_until=0, bonds=?, last_tick=?,"
        " weapon=?, armor=?, charm=?, weapon_r=?, armor_r=?, charm_r=?, weapon_e=?, armor_e=?, charm_e=? WHERE user_id=?",
        (way, path, realm, stage, settings.BOND_MAX, time.time(),
         gear.key("weapon", best), gear.key("armor", best), gear.key("charm", best),
         gear.REFINE_MAX, gear.REFINE_MAX, gear.REFINE_MAX, "sharpness", "fortitude", "prosperity", user_id))
    character = await engine.get(user_id)
    character["qi"] = engine.need(character)
    await engine.save(character)
    for key in gear.MATERIALS:
        await top_up(user_id, key, MAX_MATERIALS)
    for key in list(settings.ITEMS) + list(settings.BREWS):
        await top_up(user_id, key, MAX_PILLS)
    for key in gear.RELICS:
        await top_up(user_id, key, 1)
    await quest.set_chapter(user_id, chapters.TOTAL)
    now = time.time()
    for key in titles.TITLES:
        await db.raw_execute("INSERT INTO cult_titles (user_id, title_key, earned_at) VALUES (?, ?, ?) ON CONFLICT(user_id, title_key) DO NOTHING", (user_id, key, now))
    return await engine.get(user_id)


async def set_chapter(user_id: int, index: int) -> int:
    await ensure(user_id)
    await quest.set_chapter(user_id, index)
    row = await quest.get_row(user_id)
    return row["chapter"]
