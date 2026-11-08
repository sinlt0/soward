import random
import time
from datetime import datetime, timezone
from typing import Optional

from rpg import quest, arts, bestiary, combat, events, gear, npcs, races, settings, story, titles, ways
from utils import clans, coins, db, family

FIELDS = ("path", "realm", "stage", "qi", "last_tick", "last_meditate", "injured_until", "chance_bonus", "pill_day", "pill_count", "rerolls", "breakthroughs")


def realm_of(character: dict) -> dict:
    return settings.REALMS[character["realm"]]


def stage_cost(realm: int, stage: int) -> int:
    info = settings.REALMS[realm]
    return int(info["base"] * info["growth"] ** stage)


def need(character: dict) -> int:
    return stage_cost(character["realm"], character["stage"])


def stage_name(character: dict) -> str:
    info = realm_of(character)
    return f"{info['name']} {info['stages'][character['stage']]}"


def is_major(character: dict) -> bool:
    return character["stage"] == len(realm_of(character)["stages"]) - 1


def gate_open(character: dict) -> bool:
    return character["realm"] + 1 < len(settings.REALMS)


def multiplier(character: dict) -> float:
    rarity = settings.ROOTS[character["rarity"]]["mult"]
    quality = next(q["mult"] for q in settings.QUALITIES if q["name"] == character["quality"])
    return rarity * quality * race_info(character).get("qi", 1.0) * way_info(character).get("qi", 1.0) * (1 + settings.BOND_QI * min(settings.BOND_MAX, int(character.get("bonds", 0))))


def race_info(character: dict) -> dict:
    return races.RACES.get(character.get("race") or races.DEFAULT_RACE, races.RACES[races.DEFAULT_RACE])


def way_info(character: dict) -> dict:
    return ways.WAYS.get(character.get("way") or "", {})


def allowed_paths(character: dict) -> tuple:
    return race_info(character).get("paths") or tuple(settings.PATHS)


def path_info(character: dict) -> dict:
    return settings.PATHS.get(character["path"], {})


def hourly(character: dict) -> float:
    return realm_of(character)["gain"] * multiplier(character)


def idle_rate(character: dict) -> float:
    return hourly(character) * path_info(character).get("idle", 1.0) * race_info(character).get("idle", 1.0) * way_info(character).get("idle", 1.0) * (1 + 0.02 * sect_level(character, "array"))


def offline_hours(character: dict) -> int:
    return max(1, settings.OFFLINE_HOURS + path_info(character).get("offline", 0) + race_info(character).get("offline", 0) + way_info(character).get("offline", 0))


def roll_race(rng: Optional[random.Random] = None) -> str:
    rng = rng or random
    keys = list(races.RACES)
    return rng.choices(keys, [races.RACES[key]["weight"] for key in keys])[0]


def roll_root(rng: Optional[random.Random] = None) -> tuple[str, str, str]:
    rng = rng or random
    rarities = list(settings.ROOTS)
    rarity = rng.choices(rarities, [settings.ROOTS[r]["weight"] for r in rarities])[0]
    root = rng.choice(settings.ROOTS[rarity]["names"])
    quality = rng.choices(settings.QUALITIES, [q["weight"] for q in settings.QUALITIES])[0]["name"]
    return rarity, root, quality


SECT_CACHE: dict = {}
SECT_CACHE_SECONDS = 20


async def building_levels(clan_id: str) -> dict:
    cached = SECT_CACHE.get(clan_id)
    if cached and time.time() - cached[0] < SECT_CACHE_SECONDS:
        return cached[1]
    rows = await db.raw_fetch("SELECT building, level FROM clan_buildings WHERE clan_id=?", (clan_id,))
    levels = {row["building"]: int(row["level"]) for row in rows}
    SECT_CACHE[clan_id] = (time.time(), levels)
    return levels


async def sect_levels(user_id: int) -> dict:
    mine = await clans.membership(user_id)
    if mine is None:
        return {}
    return await building_levels(mine["clan_id"])


def sect_level(character: dict, building: str) -> int:
    return int((character.get("_sect") or {}).get(building, 0))


async def get(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM cult_characters WHERE user_id=?", (user_id,))
    if not row:
        return None
    character = dict(row)
    character["_sect"] = await sect_levels(user_id)
    character["_buffs"] = await active_buffs(user_id, time.time())
    return character


async def save(character: dict) -> None:
    sets = ", ".join(f"{field}=?" for field in FIELDS)
    await db.raw_execute(f"UPDATE cult_characters SET {sets} WHERE user_id=?", tuple(character[f] for f in FIELDS) + (character["user_id"],))


async def inherit_blood(user_id: int, rarity: str, root: str, race: str, rng) -> tuple:
    rng = rng or random
    parent_id = await family.parent_of(user_id)
    parent = await get(parent_id) if parent_id else None
    tags = []
    if parent and parent["path"]:
        if settings.ROOTS[parent["rarity"]]["weight"] < settings.ROOTS[rarity]["weight"] and rng.randint(1, 100) <= settings.BLOOD_ROOT_CHANCE:
            rarity, root = parent["rarity"], parent["root"]
            tags.append("root")
        if parent["race"] != race and rng.randint(1, 100) <= settings.BLOOD_RACE_CHANCE:
            race = parent["race"]
            tags.append("race")
    return rarity, root, race, "+".join(tags)


async def awaken(user_id: int, rng: Optional[random.Random] = None) -> dict:
    rarity, root, quality = roll_root(rng)
    race = roll_race(rng)
    rarity, root, race, blood = await inherit_blood(user_id, rarity, root, race, rng)
    now = time.time()
    await db.raw_execute(
        "INSERT INTO cult_characters (user_id, race, root, rarity, quality, bloodline, last_tick, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, race, root, rarity, quality, blood, now, now))
    return await get(user_id)


async def reroll(user_id: int, rng: Optional[random.Random] = None) -> Optional[dict]:
    character = await get(user_id)
    if character is None or character["path"] or character["rerolls"] >= settings.REROLLS:
        return None
    rarity, root, quality = roll_root(rng)
    race = roll_race(rng)
    rarity, root, race, blood = await inherit_blood(user_id, rarity, root, race, rng)
    await db.raw_execute("UPDATE cult_characters SET race=?, root=?, rarity=?, quality=?, bloodline=?, rerolls=rerolls+1 WHERE user_id=?", (race, root, rarity, quality, blood, user_id))
    return await get(user_id)


async def choose_way(user_id: int, way: str) -> Optional[dict]:
    character = await get(user_id)
    if character is None or character["way"] or way not in ways.WAYS:
        return None
    await db.raw_execute("UPDATE cult_characters SET way=? WHERE user_id=?", (way, user_id))
    return await get(user_id)


async def choose_path(user_id: int, path: str) -> Optional[dict]:
    character = await get(user_id)
    if character is None or character["path"] or not character["way"] or path not in settings.PATHS or path not in allowed_paths(character):
        return None
    now = time.time()
    await db.raw_execute("UPDATE cult_characters SET path=?, last_tick=? WHERE user_id=?", (path, now, user_id))
    return await get(user_id)


def settle(character: dict, now: float) -> int:
    if not character["path"]:
        return 0
    hours = max(0.0, min((now - character["last_tick"]) / 3600, offline_hours(character)))
    gained = int(hours * idle_rate(character))
    room = max(0, need(character) - character["qi"])
    gained = min(gained, room)
    character["qi"] += gained
    character["last_tick"] = now
    return gained


def hurt(character: dict, now: float) -> float:
    return max(0.0, character["injured_until"] - now)


def coin_mult(character: dict) -> float:
    mult = 1.0
    if "fortune_pill" in (character.get("_buffs") or ()):
        mult *= settings.BREWS["fortune_pill"]["coins"]
    for slot in gear.SLOTS:
        mult *= gear.ENCHANTS.get(character.get(f"{slot}_e") or "", {}).get("coins", 1.0)
    return mult


async def active_buffs(user_id: int, now: float) -> set:
    rows = await db.raw_fetch("SELECT activity, day, count FROM activity_state WHERE user_id=? AND activity LIKE 'cult_buff_%'", (user_id,))
    return {row["activity"][len("cult_buff_"):] for row in rows if row["day"] == today(now) and int(row["count"]) >= 1}


def today(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")


async def meditate(user_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    settle(character, now)
    wait = character["last_meditate"] + settings.MEDITATE_COOLDOWN - now
    if hurt(character, now):
        await save(character)
        return {"ok": False, "reason": "hurt", "wait": hurt(character, now), "character": character}
    if wait > 0:
        await save(character)
        return {"ok": False, "reason": "cooldown", "wait": wait, "character": character}
    if character["qi"] >= need(character):
        await save(character)
        return {"ok": False, "reason": "full", "character": character}
    gain = int(hourly(character) * settings.MEDITATE_HOURS * path_info(character).get("meditate", 1.0) * race_info(character).get("meditate", 1.0) * way_info(character).get("meditate", 1.0))
    gain = min(gain, need(character) - character["qi"])
    character["qi"] += gain
    character["last_meditate"] = now
    await save(character)
    await quest.bump(user_id, "meditate")
    return {"ok": True, "gain": gain, "character": character}


def major_chance(character: dict) -> int:
    return max(5, min(settings.CHANCE_CAP, settings.MAJOR_CHANCE + character["chance_bonus"] + path_info(character).get("chance", 0) + race_info(character).get("chance", 0) + way_info(character).get("chance", 0)))


def minor_chance(character: dict) -> int:
    return min(settings.CHANCE_CAP, settings.MINOR_CHANCE + path_info(character).get("chance", 0))


async def breakthrough(user_id: int, now: Optional[float] = None, rng: Optional[random.Random] = None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    settle(character, now)
    cost = need(character)
    if hurt(character, now):
        await save(character)
        return {"ok": False, "reason": "hurt", "wait": hurt(character, now), "character": character}
    if character["qi"] < cost:
        await save(character)
        return {"ok": False, "reason": "qi", "missing": cost - character["qi"], "character": character}
    major = is_major(character)
    if major and not gate_open(character):
        await save(character)
        return {"ok": False, "reason": "gate", "character": character}
    fee = realm_of(character)["fee"] if major else 0
    if fee and not await coins.spend(user_id, fee):
        await save(character)
        return {"ok": False, "reason": "fee", "fee": fee, "character": character}
    chance = major_chance(character) if major else minor_chance(character)
    won = rng.randint(1, 100) <= chance
    before = stage_name(character)
    if won:
        if major:
            character["realm"] += 1
            character["stage"] = 0
        else:
            character["stage"] += 1
        character["qi"] = 0
        character["breakthroughs"] += 1
        character["chance_bonus"] = 0
    else:
        loss = int(cost * (settings.MAJOR_LOSS if major else settings.MINOR_LOSS))
        character["qi"] = max(0, character["qi"] - loss)
        character["injured_until"] = now + (settings.INJURY_SECONDS if major else settings.DEVIATION_SECONDS) * race_info(character).get("injury", 1.0) * way_info(character).get("injury", 1.0)
        if major:
            character["chance_bonus"] = 0
    await save(character)
    return {"ok": True, "won": won, "major": major, "chance": chance, "fee": fee, "before": before, "after": stage_name(character), "character": character}


def price(key: str, character: Optional[dict]) -> int:
    item = settings.ITEMS[key]
    value = item["price"] * ((character["realm"] + 1) if item["scale"] and character else 1)
    if character:
        value *= path_info(character).get("pill_price", 1.0) * race_info(character).get("price", 1.0) * way_info(character).get("price", 1.0) * (1 - 0.03 * sect_level(character, "pavilion"))
    return max(1, int(value))


async def inventory(user_id: int) -> dict[str, int]:
    rows = await db.raw_fetch("SELECT item, qty FROM cult_items WHERE user_id=? AND qty>0", (user_id,))
    return {row["item"]: int(row["qty"]) for row in rows}


async def buy(user_id: int, key: str, qty: int) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    cost = price(key, character) * qty
    if not await coins.spend(user_id, cost):
        return {"ok": False, "reason": "coins", "cost": cost}
    await add_item(user_id, key, qty)
    return {"ok": True, "cost": cost}


async def take_item(user_id: int, key: str) -> bool:
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-1 WHERE user_id=? AND item=? AND qty>0", (user_id, key))
    return getattr(cursor, "rowcount", 0) > 0


async def give_item(user_id: int, key: str) -> None:
    await db.raw_execute("UPDATE cult_items SET qty=qty+1 WHERE user_id=? AND item=?", (user_id, key))


async def use(user_id: int, key: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    settle(character, now)
    if not await take_item(user_id, key):
        await save(character)
        return {"ok": False, "reason": "missing"}
    if key == "qi_pill":
        if character["pill_day"] != today(now):
            character["pill_day"], character["pill_count"] = today(now), 0
        if character["pill_count"] >= settings.PILL_DAILY_LIMIT:
            await give_item(user_id, key)
            await save(character)
            return {"ok": False, "reason": "limit"}
        if character["qi"] >= need(character):
            await give_item(user_id, key)
            await save(character)
            return {"ok": False, "reason": "full"}
        gain = int(hourly(character) * settings.ITEMS[key]["hours"] * path_info(character).get("pill_power", 1.0) * race_info(character).get("pills", 1.0) * way_info(character).get("pills", 1.0))
        gain = min(gain, need(character) - character["qi"])
        character["qi"] += gain
        character["pill_count"] += 1
        await save(character)
        return {"ok": True, "key": key, "gain": gain, "character": character}
    if key == "tribulation_pill":
        if character["chance_bonus"] >= 30:
            await give_item(user_id, key)
            await save(character)
            return {"ok": False, "reason": "stacked"}
        character["chance_bonus"] = min(30, character["chance_bonus"] + settings.ITEMS[key]["chance"])
        await save(character)
        return {"ok": True, "key": key, "character": character}
    if key == "healing_pill":
        if not hurt(character, now):
            await give_item(user_id, key)
            await save(character)
            return {"ok": False, "reason": "healthy"}
        character["injured_until"] = 0
        await save(character)
        return {"ok": True, "key": key, "character": character}
    await give_item(user_id, key)
    return {"ok": False, "reason": "unknown"}


async def top(limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM cult_characters WHERE path!='' ORDER BY realm DESC, stage DESC, qi DESC LIMIT ?", (limit,))
    return [dict(row) for row in rows]


async def add_item(user_id: int, key: str, qty: int = 1) -> None:
    await db.raw_execute(
        "INSERT INTO cult_items (user_id, item, qty) VALUES (?, ?, ?) ON CONFLICT(user_id, item) DO UPDATE SET qty=qty+excluded.qty",
        (user_id, key, qty))


def add_qi(character: dict, amount: int) -> int:
    gained = max(0, min(amount, need(character) - character["qi"]))
    character["qi"] += gained
    return gained


async def claim_daily(user_id: int, activity: str, limit: int, now: float) -> Optional[int]:
    row = await db.raw_fetchone("SELECT day, count FROM activity_state WHERE user_id=? AND activity=?", (user_id, activity))
    day, count = (row["day"], int(row["count"])) if row else ("", 0)
    if day != today(now):
        day, count = today(now), 0
    if count >= limit:
        return None
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at, day=excluded.day, count=excluded.count",
        (user_id, activity, now, day, count + 1))
    if activity in quest.BUMPS:
        await quest.bump(user_id, quest.BUMPS[activity])
    return limit - count - 1


def npc_unlocked(key: str, character: dict) -> bool:
    return character["realm"] >= npcs.NPCS[key]["realm"]


def find_npc(text: str) -> Optional[str]:
    text = text.strip().lower().replace(" ", "_")
    for key, npc in npcs.NPCS.items():
        if text in (key, npc["name"].lower().replace(" ", "_")):
            return key
    matches = [key for key, npc in npcs.NPCS.items() if text in key or text in npc["name"].lower().replace(" ", "_")]
    return matches[0] if len(matches) == 1 else None


async def apply_rewards(user_id: int, character: dict, outcome: dict, now: float, rng) -> dict:
    parts: dict = {}
    if outcome.get("coins"):
        amount = rng.randint(*outcome["coins"])
        await coins.add(user_id, amount)
        parts["coins"] = amount
    if outcome.get("lose"):
        amount = min(rng.randint(*outcome["lose"]), await coins.balance(user_id))
        if amount > 0 and await coins.spend(user_id, amount):
            parts["lost"] = amount
    if outcome.get("qi_hours"):
        settle(character, now)
        parts["qi"] = add_qi(character, int(hourly(character) * outcome["qi_hours"]))
    if outcome.get("item"):
        await add_item(user_id, outcome["item"])
        parts["item"] = outcome["item"]
    if outcome.get("bonus"):
        before = character["chance_bonus"]
        character["chance_bonus"] = min(30, before + outcome["bonus"])
        parts["bonus"] = character["chance_bonus"] - before
    await save(character)
    return parts


async def talk(user_id: int, key: str, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if not npc_unlocked(key, character):
        return {"ok": False, "reason": "locked"}
    npc = npcs.NPCS[key]
    line = rng.choice([text for need_realm, text in npc["lines"] if need_realm <= character["realm"]])
    favor = None
    if await claim_daily(user_id, f"cult_talk:{key}", settings.TALK_DAILY, now) is not None:
        rule = npc["favor"]
        outcome: dict = {}
        if rule["type"] == "coins":
            outcome["coins"] = rule["range"]
            if rule.get("item") and rng.random() < rule["item_chance"]:
                outcome["item"] = rule["item"]
        elif rule["type"] == "qi":
            outcome["qi_hours"] = rule["hours"]
        elif rule["type"] == "bonus":
            outcome["bonus"] = rule["amount"]
        parts = await apply_rewards(user_id, character, outcome, now, rng)
        favor = {"text": rule["text"], **parts}
    await quest.bump(user_id, "talk")
    return {"ok": True, "npc": npc, "line": line, "favor": favor, "character": character}


def pick_event(character: dict, rng=None) -> dict:
    rng = rng or random
    return rng.choice([event for event in events.EVENTS if event["realm"] <= character["realm"]])


async def start_event(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    left = await claim_daily(user_id, "cult_event", settings.EVENT_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    return {"ok": True, "event": pick_event(character, rng), "left": left}


async def resolve_event(user_id: int, event: dict, index: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await get(user_id)
    if character is None:
        return {"ok": False, "reason": "none"}
    choice = event["choices"][index]
    if choice.get("cost") and not await coins.spend(user_id, choice["cost"]):
        return {"ok": False, "reason": "cost", "cost": choice["cost"]}
    outcome = rng.choices(choice["outcomes"], [o["w"] for o in choice["outcomes"]])[0]
    parts = await apply_rewards(user_id, character, outcome, now, rng)
    if choice.get("cost"):
        parts["paid"] = choice["cost"]
    await quest.bump(user_id, "event")
    return {"ok": True, "text": outcome["text"], "parts": parts}


def fight_mods(character: dict) -> dict:
    mods = {"hp": 1.0, "atk": 1.0, "def": 1.0, "dodge": 0, "crit": 0, "tech": 1.0}
    sources = [arts.PATH_STATS.get(character["path"], {}), race_info(character).get("fight", {}), way_info(character).get("fight", {})]
    for source in sources:
        for key, value in source.items():
            mods[key] = mods[key] + value if key in ("dodge", "crit") else mods[key] * value
    weapon, armor, charm = (character.get(slot) or "" for slot in ("weapon", "armor", "charm"))
    for worn in (weapon, armor, charm):
        for stat, value in gear.perk(worn).items():
            mods[stat] = mods[stat] + value if stat in ("dodge", "crit") else mods[stat] * value
    plus = {slot: int(character.get(f"{slot}_r") or 0) for slot in gear.SLOTS}
    mods["atk"] *= 1 + gear.bonus(weapon, plus["weapon"])
    mods["hp"] *= 1 + gear.bonus(armor, plus["armor"])
    mods["def"] *= 1 + gear.bonus(armor, plus["armor"])
    mods["dodge"] += gear.bonus(charm, plus["charm"])
    for slot in gear.SLOTS:
        for stat, value in gear.ENCHANTS.get(character.get(f"{slot}_e") or "", {}).items():
            if stat in ("atk", "hp", "def"):
                mods[stat] *= value
            elif stat == "dodge":
                mods["dodge"] += value
    for key in character.get("_buffs") or ():
        for stat, value in settings.BREWS.get(key, {}).items():
            if stat in ("atk", "hp", "def"):
                mods[stat] *= value
            elif stat == "dodge":
                mods["dodge"] += value
    mods["atk"] *= 1 + 0.03 * sect_level(character, "hall")
    mods["hp"] *= 1 + 0.02 * sect_level(character, "hall")
    mods["sect"] = sect_level(character, "scripture")
    return mods


async def fight_start(user_id: int, monster_key: Optional[str] = None, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": hurt(character, now)}
    pool = bestiary.for_realm(character["realm"])
    key = monster_key if monster_key in pool else rng.choice(pool)
    left = await claim_daily(user_id, "cult_fight", settings.FIGHT_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    return {"ok": True, "state": combat.new_fight(character, fight_mods(character), key), "left": left}


async def fight_finish(user_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await get(user_id)
    if character is None:
        return {"result": state["done"]}
    result = state["done"]
    parts: dict = {}
    if result == "win":
        tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
        amount = rng.randint(*settings.FIGHT_COINS[tier])
        amount = int(amount * coin_mult(character))
        await coins.add(user_id, amount)
        parts["coins"] = amount
        await quest.bump(user_id, "win")
        settle(character, now)
        parts["qi"] = add_qi(character, int(hourly(character) * settings.FIGHT_QI_HOURS))
        if rng.randint(1, 100) <= settings.FIGHT_MATERIAL_CHANCE:
            material = gear.GRADES[tier]["material"]
            count = rng.randint(1, 2)
            await add_item(user_id, material, count)
            parts["material"] = (material, count)
        if rng.randint(1, 100) <= settings.FIGHT_GEAR_CHANCE:
            drop = gear.drop(rng, tier)
            await add_item(user_id, drop)
            parts["gear"] = drop
        await save(character)
    elif result == "lose":
        settle(character, now)
        loss = min(character["qi"], int(need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        parts["qi_lost"] = loss
        await save(character)
    return {"result": result, "parts": parts}


async def craft(user_id: int, slot: str, grade: int) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if (slot not in gear.SLOTS and slot not in gear.WEAPONS) or not 0 <= grade < len(gear.GRADES) or grade > character["realm"]:
        return {"ok": False, "reason": "grade"}
    info = gear.GRADES[grade]
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (gear.CRAFT_MATERIALS, user_id, info["material"], gear.CRAFT_MATERIALS))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "materials", "need": gear.CRAFT_MATERIALS, "material": info["material"]}
    if not await coins.spend(user_id, info["coins"]):
        await add_item(user_id, info["material"], gear.CRAFT_MATERIALS)
        return {"ok": False, "reason": "coins", "cost": info["coins"]}
    item = gear.key(slot, grade)
    await add_item(user_id, item)
    await quest.bump(user_id, "craft")
    return {"ok": True, "item": item, "cost": info["coins"]}


async def equip(user_id: int, item: str) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    parsed = gear.parse(item)
    if parsed is None:
        return {"ok": False, "reason": "unknown"}
    slot, grade = parsed
    if grade > character["realm"]:
        return {"ok": False, "reason": "realm", "need": grade}
    if not await take_item(user_id, item):
        return {"ok": False, "reason": "missing"}
    previous = character[slot]
    if previous:
        await add_item(user_id, previous)
    await db.raw_execute(f"UPDATE cult_characters SET {slot}=?, {slot}_r=0, {slot}_e='' WHERE user_id=?", (item, user_id))
    return {"ok": True, "item": item, "previous": previous, "lost_plus": int(character.get(f"{slot}_r") or 0) if previous else 0, "lost_enchant": character.get(f"{slot}_e") or "" if previous else ""}


async def refine(user_id: int, slot: str, rng=None) -> dict:
    rng = rng or random
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    parsed = gear.parse(character.get(slot) or "") if slot in gear.SLOTS else None
    if parsed is None:
        return {"ok": False, "reason": "empty"}
    plus = int(character.get(f"{slot}_r") or 0)
    if plus >= gear.REFINE_MAX:
        return {"ok": False, "reason": "max"}
    cost = gear.refine_cost(parsed[1], plus)
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (cost["materials"], user_id, cost["material"], cost["materials"]))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "materials", **cost}
    if not await coins.spend(user_id, cost["coins"]):
        await add_item(user_id, cost["material"], cost["materials"])
        return {"ok": False, "reason": "coins", **cost}
    success = rng.randint(1, 100) <= cost["chance"]
    if success:
        await db.raw_execute(f"UPDATE cult_characters SET {slot}_r={slot}_r+1 WHERE user_id=? AND {slot}_r=?", (user_id, plus))
        await quest.bump(user_id, "refine")
    return {"ok": True, "success": success, "plus": plus + 1 if success else plus, "slot": slot, "item": character[slot], **cost}


def bounty_day(now: float) -> int:
    return int(now // 86400)


BOUNTY_POOL = (
    ("cult_fight", "Take on {n} fights", (2, 4)),
    ("cult_explore", "Explore the wilds {n} times", (4, 8)),
    ("cult_wild", "Fight {n} wild abyssal beasts", (2, 3)),
    ("cult_spar", "Spar with a traveler {n} time(s)", (1, 2)),
    ("cult_rift", "Enter a rift", (1, 1)),
)


async def activity_count(user_id: int, activity: str, now: float) -> int:
    row = await db.raw_fetchone("SELECT day, count FROM activity_state WHERE user_id=? AND activity=?", (user_id, activity))
    return int(row["count"]) if row and row["day"] == today(now) else 0


def bounty_rewards(character: dict) -> dict:
    realm = character["realm"]
    return {"coins": int(settings.BOUNTY_COINS * (1 + 0.5 * realm)), "qi": settings.BOUNTY_QI, "bonus_coins": int(settings.BOUNTY_BONUS_COINS * (1 + 0.5 * realm)), "material": gear.GRADES[min(realm, len(gear.GRADES) - 1)]["material"], "material_qty": settings.BOUNTY_BONUS_MATERIALS}


async def bounties(user_id: int, now: Optional[float] = None) -> Optional[dict]:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return None
    picker = random.Random(user_id * 100003 + bounty_day(now))
    chosen = picker.sample(BOUNTY_POOL, settings.BOUNTY_COUNT)
    items = []
    for index, (activity, text, span) in enumerate(chosen):
        goal = picker.randint(*span)
        done = await activity_count(user_id, activity, now)
        row = await db.raw_fetchone("SELECT day, count FROM activity_state WHERE user_id=? AND activity=?", (user_id, f"cult_bounty_{index}"))
        claimed = bool(row and row["day"] == today(now) and int(row["count"]) >= 1)
        items.append({"index": index, "text": text.format(n=goal), "goal": goal, "done": min(done, goal), "claimed": claimed})
    return {"items": items, "rewards": bounty_rewards(character)}


async def claim_bounties(user_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    board = await bounties(user_id, now)
    if board is None:
        return {"ok": False, "reason": "none"}
    character = await get(user_id)
    rewards = board["rewards"]
    claimed = 0
    for item in board["items"]:
        if item["claimed"] or item["done"] < item["goal"]:
            continue
        if await claim_daily(user_id, f"cult_bounty_{item['index']}", 1, now) is None:
            continue
        item["claimed"] = True
        claimed += 1
    if not claimed:
        return {"ok": False, "reason": "nothing", "board": board}
    total_coins = rewards["coins"] * claimed
    await coins.add(user_id, total_coins)
    settle(character, now)
    gained = add_qi(character, int(need(character) * rewards["qi"] * claimed))
    await save(character)
    chest = all(item["claimed"] for item in board["items"]) and await claim_daily(user_id, "cult_bounty_chest", 1, now) is not None
    if chest:
        await coins.add(user_id, rewards["bonus_coins"])
        await add_item(user_id, rewards["material"], rewards["material_qty"])
    return {"ok": True, "claimed": claimed, "coins": total_coins, "qi": gained, "chest": chest, "rewards": rewards, "board": board}


async def raid_log(user_id: int, limit: int = 10) -> list:
    rows = await db.raw_fetch("SELECT * FROM cult_raid_log WHERE attacker_id=? OR target_id=? ORDER BY at DESC LIMIT ?", (user_id, user_id, limit))
    return [dict(row) for row in rows]


def shielded(character: dict, now: float) -> bool:
    return character["realm"] == 0 or now - character["created_at"] < settings.SHIELD_DAYS * 86400


def safe_cap(character: dict) -> int:
    return settings.SAFE_BASE * settings.SAFE_GROWTH ** min(character["realm"], len(settings.REALMS) - 1)


async def safe_move(user_id: int, amount: int, deposit: bool) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    amount = int(amount)
    if amount <= 0:
        return {"ok": False, "reason": "amount"}
    cap = safe_cap(character)
    if deposit:
        cursor = await db.raw_execute("UPDATE cult_characters SET safe=safe+? WHERE user_id=? AND safe+?<=?", (amount, user_id, amount, cap))
        if getattr(cursor, "rowcount", 0) <= 0:
            return {"ok": False, "reason": "full", "cap": cap, "safe": character["safe"]}
        if not await coins.spend(user_id, amount):
            await db.raw_execute("UPDATE cult_characters SET safe=safe-? WHERE user_id=?", (amount, user_id))
            return {"ok": False, "reason": "coins"}
    else:
        cursor = await db.raw_execute("UPDATE cult_characters SET safe=safe-? WHERE user_id=? AND safe>=?", (amount, user_id, amount))
        if getattr(cursor, "rowcount", 0) <= 0:
            return {"ok": False, "reason": "safe", "safe": character["safe"]}
        await coins.add(user_id, amount)
    return {"ok": True, "character": await get(user_id), "cap": cap}


async def activity_row(user_id: int, activity: str) -> tuple:
    row = await db.raw_fetchone("SELECT used_at, day, count FROM activity_state WHERE user_id=? AND activity=?", (user_id, activity))
    return (float(row["used_at"]), row["day"], int(row["count"])) if row else (0.0, "", 0)


async def robbed_today(user_id: int, now: float) -> int:
    _, day, count = await activity_row(user_id, "pvp_robbed")
    return count if day == today(now) else 0


async def related(a: int, b: int) -> Optional[str]:
    if b in await family.partners(a):
        return "partner"
    if await family.parent_of(a) == b or await family.parent_of(b) == a:
        return "family"
    mine, theirs = await clans.membership(a), await clans.membership(b)
    if mine and theirs and mine["clan_id"] == theirs["clan_id"]:
        return "clan"
    return None


async def pvp_start(attacker_id: int, target_id: int, name: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    me = await get(attacker_id)
    if me is None or not me["path"]:
        return {"ok": False, "reason": "none"}
    if attacker_id == target_id:
        return {"ok": False, "reason": "self"}
    them = await get(target_id)
    if them is None or not them["path"]:
        return {"ok": False, "reason": "target_none"}
    if hurt(me, now):
        return {"ok": False, "reason": "hurt", "wait": hurt(me, now)}
    if shielded(me, now):
        return {"ok": False, "reason": "shield_self"}
    if shielded(them, now):
        return {"ok": False, "reason": "shield_target"}
    if abs(me["realm"] - them["realm"]) > settings.PVP_REALM_GAP:
        return {"ok": False, "reason": "gap"}
    link = await related(attacker_id, target_id)
    if link:
        return {"ok": False, "reason": link}
    last, _, _ = await activity_row(attacker_id, f"pvp_hit_{target_id}")
    if last + settings.PVP_TARGET_COOLDOWN > now:
        return {"ok": False, "reason": "cooldown", "wait": last + settings.PVP_TARGET_COOLDOWN - now}
    if await robbed_today(target_id, now) >= settings.PVP_ROBBED_DAILY:
        return {"ok": False, "reason": "looted"}
    if await coins.balance(target_id) < settings.PVP_MIN_POUCH:
        return {"ok": False, "reason": "poor"}
    left = await claim_daily(attacker_id, "pvp_attack", settings.PVP_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, ?, ?, '', 0)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at",
        (attacker_id, f"pvp_hit_{target_id}", now))
    state = combat.new_duel(me, fight_mods(me), them, fight_mods(them), target_id, name)
    return {"ok": True, "state": state, "left": left}


async def drop_item(source: int, receiver: Optional[int], rng) -> Optional[str]:
    items = await inventory(source)
    if not items or rng.randint(1, 100) > settings.PVP_ITEM_DROP:
        return None
    key = rng.choice(list(items))
    if not await take_item(source, key):
        return None
    if receiver:
        await add_item(receiver, key)
    return key


async def pvp_finish(attacker_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    result = state["done"]
    target_id = state["target"]
    parts: dict = {}
    if result == "win":
        them = await get(target_id)
        if them is not None:
            settle(them, now)
            loss = min(them["qi"], int(need(them) * settings.FIGHT_DEFEAT_QI))
            them["qi"] -= loss
            parts["target_qi"] = loss
            await save(them)
        if await claim_daily(target_id, "pvp_robbed", settings.PVP_ROBBED_DAILY, now) is None:
            parts["capped"] = True
        else:
            pouch = await coins.balance(target_id)
            guard = sect_level(them, "guard") if them is not None else 0
            amount = min(int(pouch * settings.PVP_STEAL_PCT * (1 - 0.1 * guard)), settings.PVP_STEAL_MAX)
            if amount > 0 and await coins.spend(target_id, amount):
                await coins.add(attacker_id, amount)
                parts["stolen"] = amount
        item = await drop_item(target_id, attacker_id, rng)
        if item:
            parts["item"] = item
        points = await war_point(attacker_id, target_id, now)
        if points:
            parts["war"] = points
    elif result == "lose":
        me = await get(attacker_id)
        if me is not None:
            settle(me, now)
            loss = min(me["qi"], int(need(me) * settings.FIGHT_DEFEAT_QI))
            me["qi"] -= loss
            parts["qi_lost"] = loss
            await save(me)
        pouch = await coins.balance(attacker_id)
        amount = min(int(pouch * settings.PVP_LOSS_PCT), settings.PVP_LOSS_MAX)
        if amount > 0 and await coins.spend(attacker_id, amount):
            parts["coins_lost"] = amount
        item = await drop_item(attacker_id, None, rng)
        if item:
            parts["item_lost"] = item
    money = parts.get("stolen", 0) if result == "win" else -parts.get("coins_lost", 0)
    await db.raw_execute("DELETE FROM cult_raid_log WHERE at<?", (now - 14 * 86400,))
    await db.raw_execute(
        "INSERT INTO cult_raid_log (attacker_id, target_id, result, coins, item, at) VALUES (?, ?, ?, ?, ?, ?)",
        (attacker_id, target_id, result, money, parts.get("item") or parts.get("item_lost") or "", now))
    return {"result": result, "parts": parts}


async def circle(user_id: int) -> list[int]:
    found = set(await family.partners(user_id)) | set(await family.children_of(user_id))
    parent = await family.parent_of(user_id)
    if parent:
        found.add(parent)
        found |= set(await family.children_of(parent))
    found.discard(user_id)
    return sorted(found)


async def dual(user_id: int, partner_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    me, them = await get(user_id), await get(partner_id)
    if me is None or not me["path"] or them is None or not them["path"]:
        return {"ok": False, "reason": "none"}
    if not await family.marriage(user_id, partner_id):
        return {"ok": False, "reason": "unmarried"}
    low, high = family.pair(user_id, partner_id)
    key = f"dual_{high}"
    last, _, _ = await activity_row(low, key)
    if last + settings.DUAL_COOLDOWN > now:
        return {"ok": False, "reason": "cooldown", "wait": last + settings.DUAL_COOLDOWN - now}
    gains = {}
    for character in (me, them):
        settle(character, now)
        gains[character["user_id"]] = add_qi(character, int(hourly(character) * settings.DUAL_HOURS * settings.DUAL_BONUS))
    if not any(gains.values()):
        await save(me)
        await save(them)
        return {"ok": False, "reason": "full"}
    await save(me)
    await save(them)
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, ?, ?, '', 0)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at",
        (low, key, now))
    return {"ok": True, "gains": gains}


async def treasury_cap(owner_id: int) -> int:
    return min(settings.TREASURY_MAX, settings.TREASURY_BASE + settings.TREASURY_PER_MEMBER * len(await circle(owner_id)))


async def treasury(owner_id: int) -> dict:
    await db.raw_execute("INSERT OR IGNORE INTO cult_treasury (owner_id, coins, heir) VALUES (?, 0, 0)", (owner_id,))
    row = await db.raw_fetchone("SELECT * FROM cult_treasury WHERE owner_id=?", (owner_id,))
    return dict(row)


async def treasury_move(user_id: int, owner_id: int, amount: int, deposit: bool) -> dict:
    amount = int(amount)
    if amount <= 0:
        return {"ok": False, "reason": "amount"}
    me = await get(user_id)
    if me is None or not me["path"]:
        return {"ok": False, "reason": "none"}
    if deposit:
        if user_id != owner_id and owner_id not in await circle(user_id):
            return {"ok": False, "reason": "stranger"}
        await treasury(owner_id)
        cap = await treasury_cap(owner_id)
        cursor = await db.raw_execute("UPDATE cult_treasury SET coins=coins+? WHERE owner_id=? AND coins+?<=?", (amount, owner_id, amount, cap))
        if getattr(cursor, "rowcount", 0) <= 0:
            return {"ok": False, "reason": "full", "cap": cap}
        if not await coins.spend(user_id, amount):
            await db.raw_execute("UPDATE cult_treasury SET coins=coins-? WHERE owner_id=?", (amount, owner_id))
            return {"ok": False, "reason": "coins"}
    else:
        if user_id != owner_id:
            return {"ok": False, "reason": "owner"}
        cursor = await db.raw_execute("UPDATE cult_treasury SET coins=coins-? WHERE owner_id=? AND coins>=?", (amount, owner_id, amount))
        if getattr(cursor, "rowcount", 0) <= 0:
            return {"ok": False, "reason": "empty"}
        await coins.add(user_id, amount)
    return {"ok": True, "treasury": await treasury(owner_id), "cap": await treasury_cap(owner_id)}


async def set_heir(owner_id: int, heir_id: int) -> dict:
    me, them = await get(owner_id), await get(heir_id)
    if me is None or not me["path"]:
        return {"ok": False, "reason": "none"}
    if heir_id == owner_id or heir_id not in await circle(owner_id):
        return {"ok": False, "reason": "not_family"}
    if them is None or not them["path"]:
        return {"ok": False, "reason": "heir_none"}
    await treasury(owner_id)
    await db.raw_execute("UPDATE cult_treasury SET heir=? WHERE owner_id=?", (heir_id, owner_id))
    return {"ok": True}


async def inherit(heir_id: int, owner_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    row = await db.raw_fetchone("SELECT coins, heir FROM cult_treasury WHERE owner_id=?", (owner_id,))
    if row is None or int(row["heir"]) != heir_id:
        return {"ok": False, "reason": "not_heir"}
    owner = await get(owner_id)
    if owner is not None:
        idle = now - max(owner["last_tick"], owner["last_meditate"])
        if idle < settings.INHERIT_DAYS * 86400:
            return {"ok": False, "reason": "active", "wait": settings.INHERIT_DAYS * 86400 - idle}
    cursor = await db.raw_execute("UPDATE cult_treasury SET coins=0, heir=0 WHERE owner_id=? AND heir=? AND coins>0", (owner_id, heir_id))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "empty"}
    amount = int(row["coins"])
    await coins.add(heir_id, amount)
    return {"ok": True, "amount": amount}


async def dungeon_start(leader_id: int, member_ids: list, now: Optional[float] = None) -> dict:
    now = now or time.time()
    ids = [leader_id] + [m for m in member_ids if m != leader_id]
    if len(ids) < 2 or len(ids) > settings.DUNGEON_MAX_PARTY:
        return {"ok": False, "reason": "size"}
    allowed = set(await circle(leader_id)) | {leader_id}
    characters = []
    for uid in ids:
        character = await get(uid)
        if uid not in allowed:
            return {"ok": False, "reason": "stranger", "user": uid}
        if character is None or not character["path"]:
            return {"ok": False, "reason": "none", "user": uid}
        if hurt(character, now):
            return {"ok": False, "reason": "hurt", "user": uid}
        _, day, count = await activity_row(uid, "cult_dungeon")
        if day == today(now) and count >= settings.DUNGEON_DAILY:
            return {"ok": False, "reason": "limit", "user": uid}
        characters.append(character)
    for uid in ids:
        if await claim_daily(uid, "cult_dungeon", settings.DUNGEON_DAILY, now) is None:
            return {"ok": False, "reason": "limit", "user": uid}
    boss = bestiary.boss_for(max(character["realm"] for character in characters))
    state = combat.new_party([(character, fight_mods(character)) for character in characters], [], boss)
    return {"ok": True, "state": state}


async def dungeon_finish(state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    result = state["done"]
    members: dict = {}
    for uid in state["party"]:
        character = await get(uid)
        if character is None:
            continue
        parts: dict = {}
        if result == "win":
            tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
            amount = rng.randint(*settings.FIGHT_COINS[tier]) * settings.DUNGEON_COIN_MULT
            await coins.add(uid, amount)
            parts["coins"] = amount
            settle(character, now)
            parts["qi"] = add_qi(character, int(hourly(character) * settings.FIGHT_QI_HOURS * 2))
            if rng.randint(1, 100) <= settings.DUNGEON_MATERIAL_CHANCE:
                material = gear.GRADES[tier]["material"]
                count = rng.randint(1, 3)
                await add_item(uid, material, count)
                parts["material"] = (material, count)
            if rng.randint(1, 100) <= settings.DUNGEON_GEAR_CHANCE:
                drop = gear.drop(rng, tier)
                await add_item(uid, drop)
                parts["gear"] = drop
            await save(character)
        elif result == "lose":
            settle(character, now)
            loss = min(character["qi"], int(need(character) * settings.FIGHT_DEFEAT_QI))
            character["qi"] -= loss
            parts["qi_lost"] = loss
            await save(character)
        members[uid] = parts
    return {"result": result, "members": members}


async def active_war(clan_id: str, now: float) -> Optional[dict]:
    row = await db.raw_fetchone(
        "SELECT * FROM clan_wars WHERE status='active' AND ends_at>? AND (clan_a=? OR clan_b=?)", (now, clan_id, clan_id))
    return dict(row) if row else None


async def war_point(attacker_id: int, target_id: int, now: float) -> int:
    mine, theirs = await clans.membership(attacker_id), await clans.membership(target_id)
    if not mine or not theirs or mine["clan_id"] == theirs["clan_id"]:
        return 0
    war = await active_war(mine["clan_id"], now)
    if war is None or theirs["clan_id"] not in (war["clan_a"], war["clan_b"]):
        return 0
    a, b = await get(attacker_id), await get(target_id)
    points = 1 + max(0, min(2, (b["realm"] - a["realm"]) if a and b else 0))
    column = "score_a" if war["clan_a"] == mine["clan_id"] else "score_b"
    await db.raw_execute(f"UPDATE clan_wars SET {column}={column}+? WHERE war_id=?", (points, war["war_id"]))
    return points


async def brew(user_id: int, key: str) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if key not in settings.BREWS:
        return {"ok": False, "reason": "unknown"}
    info = gear.GRADES[min(character["realm"], len(gear.GRADES) - 1)]
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (settings.BREW_MATERIALS, user_id, info["material"], settings.BREW_MATERIALS))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "materials", "need": settings.BREW_MATERIALS, "material": info["material"]}
    cost = int(settings.BREW_COINS * (1 + character["realm"]) * path_info(character).get("pill_price", 1.0))
    if not await coins.spend(user_id, cost):
        await add_item(user_id, info["material"], settings.BREW_MATERIALS)
        return {"ok": False, "reason": "coins", "cost": cost}
    qty = 2 if character["path"] == "alchemy" else 1
    await add_item(user_id, key, qty)
    await quest.bump(user_id, "brew")
    return {"ok": True, "item": key, "qty": qty, "cost": cost}


async def drink(user_id: int, key: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if key not in settings.BREWS:
        return {"ok": False, "reason": "unknown"}
    if key in character["_buffs"]:
        return {"ok": False, "reason": "active"}
    if not await take_item(user_id, key):
        return {"ok": False, "reason": "missing"}
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, ?, ?, ?, 1)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at, day=excluded.day, count=1",
        (user_id, "cult_buff_" + key, now, today(now)))
    return {"ok": True, "item": key}


def find_brew(text: str) -> Optional[str]:
    text = text.strip().lower().replace(" ", "_").replace("-", "_")
    for key, info in settings.BREWS.items():
        name = info["name"].lower().replace(" ", "_")
        if text in (key, name, key.replace("_pill", ""), name.replace("_pill", "")):
            return key
    return None


async def enchant(user_id: int, slot: str, key: str) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    info = gear.ENCHANTS.get(key)
    if slot not in gear.SLOTS or info is None or slot not in info["slots"]:
        return {"ok": False, "reason": "slot"}
    if not character.get(slot):
        return {"ok": False, "reason": "empty"}
    if character.get(f"{slot}_e") == key:
        return {"ok": False, "reason": "same"}
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item='rift_shard' AND qty>=?", (gear.ENCHANT_SHARDS, user_id, gear.ENCHANT_SHARDS))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "materials", "need": gear.ENCHANT_SHARDS}
    cost = gear.ENCHANT_COINS * (1 + character["realm"])
    if not await coins.spend(user_id, cost):
        await add_item(user_id, "rift_shard", gear.ENCHANT_SHARDS)
        return {"ok": False, "reason": "coins", "cost": cost}
    await db.raw_execute(f"UPDATE cult_characters SET {slot}_e=? WHERE user_id=?", (key, user_id))
    return {"ok": True, "slot": slot, "enchant": key, "cost": cost, "replaced": character.get(f"{slot}_e") or ""}


async def title_facts(user_id: int, character: dict) -> dict:
    met = await db.raw_fetchone("SELECT COUNT(*) AS n FROM cult_npcs WHERE user_id=?", (user_id,))
    rift = await db.raw_fetchone("SELECT 1 AS n FROM cult_rifts WHERE user_id=?", (user_id,))
    earned = await db.raw_fetchone("SELECT 1 AS n FROM cult_titles WHERE user_id=? AND title_key='riftwalker'", (user_id,))
    member = await clans.membership(user_id)
    story_row = await db.raw_fetchone("SELECT chapter FROM cult_story WHERE user_id=?", (user_id,))
    return {
        "chapters": int(story_row["chapter"]) if story_row else 0,
        "awakened": bool(character["path"]),
        "realm": character["realm"],
        "refine": max(int(character.get(f"{slot}_r") or 0) for slot in gear.SLOTS),
        "enchants": sum(1 for slot in gear.SLOTS if character.get(f"{slot}_e")),
        "met": int(met["n"]) if met else 0,
        "bonds": int(character.get("bonds") or 0),
        "role": member["role"] if member else "",
        "safe": int(character.get("safe") or 0),
        "rifts": 1 if rift or earned else 0,
        "partnered": bool(await family.partners(user_id)),
    }


async def title_rows(user_id: int) -> dict:
    rows = await db.raw_fetch("SELECT title_key, earned_at FROM cult_titles WHERE user_id=?", (user_id,))
    return {row["title_key"]: row["earned_at"] for row in rows}


async def check_titles(user_id: int, now: Optional[float] = None) -> list:
    now = now or time.time()
    character = await get(user_id)
    if character is None or not character["path"]:
        return []
    facts = await title_facts(user_id, character)
    have = await title_rows(user_id)
    fresh = []
    for key, info in titles.TITLES.items():
        if key not in have and info["need"](facts):
            await db.raw_execute("INSERT INTO cult_titles (user_id, title_key, earned_at) VALUES (?, ?, ?) ON CONFLICT(user_id, title_key) DO NOTHING", (user_id, key, now))
            fresh.append(key)
    return fresh


async def set_title(user_id: int, key: str) -> dict:
    character = await get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if key and key not in await title_rows(user_id):
        return {"ok": False, "reason": "locked"}
    await db.raw_execute("UPDATE cult_characters SET title=? WHERE user_id=?", (key, user_id))
    return {"ok": True, "title": key}
