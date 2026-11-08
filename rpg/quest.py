import json
import time
from typing import Optional

from rpg import bestiary, chapters, combat
from utils import coins, db

BUMPS = {"cult_fight": "fight", "cult_explore": "explore", "cult_rift": "rift", "cult_spar": "spar"}
BOSS_HP = 1.4


def decode(text: str) -> dict:
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def get_row(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT chapter, progress, flags FROM cult_story WHERE user_id=?", (user_id,))
    if row is None:
        await db.raw_execute("INSERT INTO cult_story (user_id, chapter, progress, flags, updated_at) VALUES (?, 0, '{}', '{}', ?) ON CONFLICT(user_id) DO NOTHING", (user_id, time.time()))
        return {"chapter": 0, "progress": {}, "flags": {}, "raw": "{}"}
    return {"chapter": int(row["chapter"]), "progress": decode(row["progress"]), "flags": decode(row["flags"]), "raw": row["progress"] or "{}"}


def current(row: dict) -> Optional[dict]:
    return chapters.CHAPTERS[row["chapter"]] if row["chapter"] < chapters.TOTAL else None


async def write_progress(user_id: int, row: dict, progress: dict) -> bool:
    cursor = await db.raw_execute(
        "UPDATE cult_story SET progress=?, updated_at=? WHERE user_id=? AND chapter=? AND progress=?",
        (json.dumps(progress), time.time(), user_id, row["chapter"], row["raw"]))
    return getattr(cursor, "rowcount", 1) > 0


async def bump(user_id: int, key: str, amount: int = 1) -> None:
    row = await get_row(user_id)
    chapter = current(row)
    if chapter is None:
        return
    for goal, need in chapter["goals"]:
        if goal == key and goal != "realm":
            progress = dict(row["progress"])
            progress[key] = min(need, int(progress.get(key, 0)) + amount)
            await write_progress(user_id, row, progress)
            return


def goal_rows(chapter: dict, progress: dict, character: dict) -> list:
    rows = []
    for goal, need in chapter["goals"]:
        if goal == "realm":
            from rpg import settings
            have = need if character["realm"] >= need else 0
            rows.append((f"Reach {settings.REALMS[need]['name']}", have, 1))
        else:
            rows.append((f"{chapters.GOAL_LABELS.get(goal, goal)}", min(need, int(progress.get(goal, 0))), need))
    return rows


async def status(user_id: int, character: dict) -> dict:
    row = await get_row(user_id)
    chapter = current(row)
    if chapter is None:
        return {"finished": True, "row": row}
    goals = goal_rows(chapter, row["progress"], character)
    goals_done = all(have >= need for _, have, need in goals)
    boss_done = bool(row["progress"].get("boss")) if chapter["boss"] else True
    choice_made = row["progress"].get("choice") if chapter["choice"] else "-"
    locked = character["realm"] < chapter["realm"]
    echoes = [text for flag, value, text in chapter["echo"] if row["flags"].get(flag) == value]
    if locked:
        stage = "locked"
    elif not goals_done:
        stage = "goals"
    elif not boss_done:
        stage = "boss"
    elif not choice_made:
        stage = "choice"
    else:
        stage = "ready"
    return {"finished": False, "row": row, "chapter": chapter, "index": row["chapter"], "goals": goals, "stage": stage,
            "boss_done": boss_done, "choice": choice_made if chapter["choice"] else None, "echoes": echoes}


def boss_state(character: dict, mods: dict, key: str) -> dict:
    info = bestiary.BOSSES[key]
    state = combat.new_fight(character, mods, "grey_wolf")
    size = combat.scale(character["realm"], character["stage"])
    hp = int(100 * size * info["hp"] * BOSS_HP)
    state["m"].update({"key": key, "name": info["name"], "zh": info["zh"], "skill": info["skill"], "hp": hp, "max": hp,
                       "atk": 14 * size * info["atk"], "def": 4 * size * info["def"]})
    state["tag"] = "story boss"
    state["story"] = key
    return state


async def boss_finish(user_id: int, state: dict) -> dict:
    result = state["done"]
    if result != "win":
        return {"result": result}
    row = await get_row(user_id)
    chapter = current(row)
    if chapter is not None and chapter["boss"] == state.get("story") and not row["progress"].get("boss"):
        progress = dict(row["progress"])
        progress["boss"] = 1
        await write_progress(user_id, row, progress)
    return {"result": result}


async def grant(user_id: int, reward: dict) -> dict:
    from rpg import engine
    given = {"coins": 0, "items": {}}
    if reward.get("coins"):
        await coins.add(user_id, reward["coins"])
        given["coins"] = reward["coins"]
    for key, qty in (reward.get("items") or {}).items():
        await engine.add_item(user_id, key, qty)
        given["items"][key] = qty
    return given


async def choose(user_id: int, option: str) -> Optional[dict]:
    row = await get_row(user_id)
    chapter = current(row)
    if chapter is None or not chapter["choice"] or row["progress"].get("choice"):
        return None
    picked = next((item for item in chapter["choice"]["options"] if item[0] == option), None)
    if picked is None:
        return None
    progress = dict(row["progress"])
    progress["choice"] = option
    if not await write_progress(user_id, row, progress):
        return None
    flags = dict(row["flags"])
    flags[chapter["choice"]["flag"]] = option
    await db.raw_execute("UPDATE cult_story SET flags=? WHERE user_id=?", (json.dumps(flags), user_id))
    given = await grant(user_id, picked[3])
    return {"text": picked[2], "given": given, "label": picked[1]}


async def complete(user_id: int, character: dict) -> Optional[dict]:
    info = await status(user_id, character)
    if info["finished"] or info["stage"] != "ready":
        return None
    row = info["row"]
    cursor = await db.raw_execute(
        "UPDATE cult_story SET chapter=chapter+1, progress='{}', updated_at=? WHERE user_id=? AND chapter=?",
        (time.time(), user_id, row["chapter"]))
    if getattr(cursor, "rowcount", 1) <= 0:
        return None
    given = await grant(user_id, info["chapter"]["reward"])
    return {"chapter": info["chapter"], "given": given, "next": current({"chapter": row["chapter"] + 1})}


async def journal(user_id: int) -> list:
    row = await get_row(user_id)
    lines = []
    for index in range(min(row["chapter"], chapters.TOTAL)):
        chapter = chapters.CHAPTERS[index]
        picked = row["flags"].get(chapter["choice"]["flag"]) if chapter["choice"] else None
        label = next((item[1] for item in chapter["choice"]["options"] if item[0] == picked), None) if picked else None
        lines.append((chapter, label))
    return lines


async def set_chapter(user_id: int, index: int) -> None:
    await get_row(user_id)
    index = max(0, min(chapters.TOTAL, index))
    flags = {}
    for chapter in chapters.CHAPTERS[:index]:
        if chapter["choice"]:
            flags[chapter["choice"]["flag"]] = chapter["choice"]["options"][0][0]
    await db.raw_execute("UPDATE cult_story SET chapter=?, progress='{}', flags=?, updated_at=? WHERE user_id=?", (index, json.dumps(flags), time.time(), user_id))
