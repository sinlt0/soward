import datetime
import random
import time
from typing import Optional

from rpg import combat, elements, engine, feats, gear, pouch, quest, schema, settings
from utils import coins, db

SPECIES = (
    ("Serpent", "蛇", 1.0, 1.0, 0.9), ("Wolf", "狼", 0.9, 1.15, 0.8), ("Tiger", "虎", 1.0, 1.15, 0.9), ("Crane", "鹤", 0.85, 1.1, 0.7),
    ("Toad", "蟾", 1.25, 0.9, 1.1), ("Centipede", "蜈蚣", 0.95, 1.1, 1.0), ("Tortoise", "龟", 1.3, 0.8, 1.35), ("Ape", "猿", 1.1, 1.1, 1.0),
    ("Bat", "蝠", 0.8, 1.2, 0.7), ("Spider", "蛛", 0.95, 1.1, 0.9), ("Boar", "猪", 1.25, 1.0, 1.1), ("Fox", "狐", 0.85, 1.15, 0.8),
    ("Flood Dragon", "蛟", 1.1, 1.15, 1.0), ("Roc", "鹏", 0.9, 1.2, 0.8), ("Corpse", "尸", 1.15, 1.0, 1.1), ("Wraith", "魂", 0.8, 1.2, 0.6),
    ("Puppet", "傀儡", 1.2, 0.95, 1.25), ("Lotus Demon", "莲妖", 1.0, 1.05, 0.95),
)
PLACES = (
    ("of the Black Marsh", "黑沼"), ("of the Withered Peak", "枯峰"), ("of the Ninth Abyss", "九渊"), ("of Thousand-Bone Valley", "千骨谷"),
    ("of the Cloudsea Ruins", "云海遗迹"), ("of the Crimson Sands", "赤沙"), ("of the Frozen Tomb", "寒陵"), ("of the Thunder Pit", "雷坑"),
    ("of the Sunken Temple", "沉殿"), ("of the Ashen Forest", "灰林"),
)
ADJECTIVES = {
    "metal": (("Ironclad", "铁甲"), ("Blade-scaled", "刃鳞")),
    "wood": (("Thornbound", "棘缚"), ("Verdant", "青翠")),
    "water": (("Tidal", "潮汐"), ("Abyssal", "深渊")),
    "fire": (("Blazing", "炽焰"), ("Ember-eyed", "烬眼")),
    "earth": (("Stonehide", "石皮"), ("Mountain-born", "山生")),
    "thunder": (("Stormcalling", "唤雷"), ("Skyrending", "裂天")),
}
SKILLS = {
    "metal": ("Ten Thousand Needles", "Bladestorm Molt", "Iron Rain"),
    "wood": ("Strangling Roots", "Spore Bloom", "Verdant Maw"),
    "water": ("Drowning Tide", "Frostbite Surge", "Abyssal Whirl"),
    "fire": ("Crimson Lotus Burst", "Ashfall Roar", "Cinder Dive"),
    "earth": ("Mountain Fall", "Quake Crown", "Boulder Hail"),
    "thunder": ("Nine Heavens Strike", "Chain Lightning", "Storm Judgement"),
}
RANKS = {
    "minion": {"name": "Servant", "zh": "仆", "hp": 1.0, "atk": 0.62, "def": 0.9, "affixes": 0, "coins": 1, "materials": 1, "herbs": 1, "gear": 4, "shards": 0, "keys": 0},
    "elite": {"name": "Warden", "zh": "守卫", "hp": 2.5, "atk": 0.86, "def": 1.0, "affixes": 1, "coins": 4, "materials": 3, "herbs": 2, "gear": 12, "shards": 0, "keys": 0},
    "lord": {"name": "Lord", "zh": "王", "hp": 2.5, "atk": 0.79, "def": 1.1, "affixes": 2, "coins": 10, "materials": 5, "herbs": 3, "gear": 28, "shards": 1, "keys": 1},
    "calamity": {"name": "Calamity", "zh": "灾厄", "hp": 2.8, "atk": 0.81, "def": 1.2, "affixes": 2, "coins": 24, "materials": 8, "herbs": 5, "gear": 55, "shards": 3, "keys": 2},
}
AFFIXES = {
    "regen": ("Regenerating", "再生", "Heals 4% of its health every turn."),
    "vampiric": ("Vampiric", "嗜血", "Drinks a third of the damage it deals."),
    "thorns": ("Thorned", "荆棘", "Reflects part of your damage."),
    "frenzy": ("Frenzied", "狂暴", "Hits much harder below half health."),
    "venom": ("Venomous", "剧毒", "Every hit also burns you."),
    "armored": ("Armored", "重甲", "Takes far less from plain attacks."),
    "evasive": ("Evasive", "灵动", "One blow in five misses."),
    "bulwark": ("Warded", "护体", "Takes less damage for the first three turns."),
}
SLOTS = ("elite", "elite", "lord", "calamity")
RESET_HOUR_UTC = 0


def today(now: Optional[float] = None) -> str:
    stamp = datetime.datetime.fromtimestamp(now or time.time(), datetime.timezone.utc)
    return stamp.strftime("%Y-%m-%d")


def generate(seed: str, rank: str, element: str = "") -> dict:
    rng = random.Random(seed)
    info = RANKS[rank]
    picked = rng.choice(list(elements.ELEMENTS))
    element = element or picked
    species = rng.choice(SPECIES)
    adjective = rng.choice(ADJECTIVES[element])
    place = rng.choice(PLACES)
    keys = rng.sample(list(AFFIXES), info["affixes"])
    name = f"{adjective[0]} {species[0]} {info['name']} {place[0]}"
    zh = f"{place[1]}{adjective[1]}{species[1]}{info['zh']}"
    return {
        "id": seed, "rank": rank, "element": element, "species": species[0], "name": name, "zh": zh, "affixes": keys,
        "skill": rng.choice(SKILLS[element]), "look": rng.randint(0, 10 ** 6),
        "hp": info["hp"] * species[2], "atk": info["atk"] * species[3], "def": info["def"] * species[4] * (1.4 if "armored" in keys else 1.0),
    }


def board(day: Optional[str] = None) -> list:
    day = day or today()
    return [dict(generate(f"{day}:{slot}", rank), slot=slot) for slot, rank in enumerate(SLOTS)]


def weakness(boss: dict) -> str:
    return elements.ELEMENTS[boss["element"]]["weak"]


def affix_text(boss: dict) -> str:
    return ", ".join(f"{AFFIXES[key][0]}" for key in boss["affixes"])


def new_state(character: dict, mods: dict, boss: dict) -> dict:
    state = combat.new_fight(character, mods, "grey_wolf")
    size = combat.scale(character["realm"], character["stage"])
    hp = int(100 * size * boss["hp"])
    state["m"].update({
        "key": boss["id"], "name": boss["name"], "zh": boss["zh"], "skill": boss["skill"], "hp": hp, "max": hp,
        "atk": 14 * size * boss["atk"], "def": 4 * size * boss["def"], "element": boss["element"], "affixes": tuple(boss["affixes"]),
    })
    state["tag"] = f"{RANKS[boss['rank']]['name'].lower()} · {elements.ELEMENTS[boss['element']]['name']}"
    state["calamity"] = boss["slot"]
    state["day"] = today()
    return state


async def attempts(user_id: int, day: Optional[str] = None) -> dict:
    await schema.ensure()
    rows = await db.raw_fetch("SELECT slot, won FROM cult_calamity WHERE user_id=? AND day=?", (user_id, day or today()))
    return {int(row["slot"]): int(row["won"]) for row in rows}


async def begin(user_id: int, slot: int, now: Optional[float] = None) -> dict:
    await schema.ensure()
    now = now or time.time()
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    day = today(now)
    boss = next((item for item in board(day) if item["slot"] == slot), None)
    if boss is None:
        return {"ok": False, "reason": "slot"}
    cursor = await db.raw_execute("INSERT INTO cult_calamity (user_id, day, slot, won, started_at) VALUES (?, ?, ?, 0, ?) ON CONFLICT(user_id, day, slot) DO NOTHING", (user_id, day, slot, now))
    if getattr(cursor, "rowcount", 1) <= 0:
        return {"ok": False, "reason": "done"}
    state = new_state(character, engine.fight_mods(character), boss)
    return {"ok": True, "state": state, "boss": boss, "character": character}


async def finish(user_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    rng = rng or random
    now = now or time.time()
    result = state["done"]
    character = await engine.get(user_id)
    if character is None:
        return {"result": result, "parts": {}}
    parts: dict = {}
    if result != "win":
        engine.settle(character, now)
        loss = min(character["qi"], int(engine.need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        parts["qi_lost"] = loss
        await engine.save(character)
        await engine.wear_parts(user_id, parts)
        return {"result": result, "parts": parts}
    boss = next(item for item in board(state["day"]) if item["slot"] == state["calamity"])
    info = RANKS[boss["rank"]]
    tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
    average = sum(settings.FIGHT_COINS[tier]) // 2
    amount = int(average * info["coins"] * rng.uniform(0.9, 1.1) * engine.coin_mult(character))
    await coins.add(user_id, amount)
    parts["coins"] = amount
    loot = []
    material = gear.GRADES[tier]["material"]
    loot.append((material, await pouch.stash(user_id, material, info["materials"], parts)))
    brew = rng.choice(list(gear.HERB_NAMES))
    herb = gear.herb_for(brew, min(character["realm"], 3))
    loot.append((herb, await pouch.stash(user_id, herb, info["herbs"], parts)))
    if info["shards"]:
        loot.append(("rift_shard", await pouch.stash(user_id, "rift_shard", info["shards"], parts)))
    if info["keys"]:
        loot.append(("realm_key", await pouch.stash(user_id, "realm_key", info["keys"], parts)))
    essence = elements.essence(boss["element"])
    loot.append((essence, await pouch.stash(user_id, essence, rng.randint(1, info["keys"] + 2), parts)))
    parts["loot"] = [(key, count) for key, count in loot if count]
    if rng.randint(1, 100) <= info["gear"]:
        parts["gear"] = await engine.give_gear(user_id, gear.drop(rng, tier), rng)
    engine.settle(character, now)
    parts["qi"] = engine.add_qi(character, int(engine.hourly(character) * settings.FIGHT_QI_HOURS * 4))
    await engine.save(character)
    await db.raw_execute("UPDATE cult_calamity SET won=1 WHERE user_id=? AND day=? AND slot=?", (user_id, state["day"], state["calamity"]))
    await quest.bump(user_id, "win")
    await quest.bump(user_id, "calamity")
    await engine.claim_daily(user_id, "cult_calamity", 99, now)
    await feats.add(user_id, "calamity_win")
    await engine.wear_parts(user_id, parts)
    parts["boss"] = boss
    return {"result": "win", "parts": parts}
