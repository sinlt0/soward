import random
import time
from typing import Optional

from rpg import calamity, elements, engine, feats, gear, pouch, quest, settings
from utils import coins, db

THEMES = {
    "metal": ("Hall of Ten Thousand Blades", "万剑殿", "A buried sect hall where every wall is a sheathed sword."),
    "wood": ("Verdant Sea Grotto", "青海洞", "A living cave where the roots remember everyone who walked in."),
    "water": ("Sunken Moon Palace", "沉月宫", "A drowned palace lit by a moon that sank with it."),
    "fire": ("Crimson Lotus Furnace", "赤莲炉", "An alchemy furnace big enough to burn a mountain, still lit."),
    "earth": ("Mountain-Heart Vault", "山心库", "A vault carved into the core of a peak, guarded by what it is made of."),
    "thunder": ("Nine Heavens Thunder Pit", "九霄雷坑", "A crater where the sky strikes back at anyone who looks up."),
}
FLOORS = 5
HIDDEN_FLOORS = 7
HIDDEN_CHANCE = 35
DAILY = 3
KEY_COST = 1
HIDDEN_KEY_COST = 2
KINDS = {"monster": 45, "elite": 15, "treasure": 15, "spring": 10, "shrine": 15}
ATTUNE_COST = 3
ATTUNE_HOURS = 12
MIGHT = 1.15
VIGOR_HEAL = 0.25
SPRING_HEAL = 0.4
RETURN_KEY = 30
HIDDEN_RETURN_KEY = 60
COIN_FACTOR = {"monster": 1.0, "elite": 2.5, "guardian": 8.0, "treasure": 3.0}


def open_realms(day: Optional[str] = None) -> list:
    day = day or calamity.today()
    rng = random.Random(f"realms:{day}")
    order = list(elements.ELEMENTS)
    rng.shuffle(order)
    found = [{"slot": i, "element": el, "hidden": False} for i, el in enumerate(order[:2])]
    if rng.randint(1, 100) <= HIDDEN_CHANCE:
        found.append({"slot": 2, "element": order[2], "hidden": True})
    for realm in found:
        name, zh, about = THEMES[realm["element"]]
        realm.update({
            "id": f"{day}:{realm['slot']}", "name": ("Hidden " if realm["hidden"] else "") + name, "zh": zh, "about": about,
            "floors": HIDDEN_FLOORS if realm["hidden"] else FLOORS, "keys": HIDDEN_KEY_COST if realm["hidden"] else KEY_COST,
        })
    return found


def layout(realm: dict, rng) -> list:
    kinds = ["monster"]
    for _ in range(realm["floors"] - 1):
        kinds.append(rng.choices(list(KINDS), weights=list(KINDS.values()))[0])
    return kinds + ["guardian"]


def counter(realm: dict) -> str:
    return elements.ELEMENTS[elements.ELEMENTS[realm["element"]]["weak"]]["name"]


def attunement(character: dict, now: Optional[float] = None) -> Optional[tuple]:
    now = now or time.time()
    if character.get("attune") and float(character.get("attune_until") or 0) > now:
        return character["attune"], float(character["attune_until"]) - now
    return None


async def attune(user_id: int, element: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    if element not in elements.ELEMENTS:
        return {"ok": False, "reason": "unknown"}
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    key = elements.essence(element)
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (ATTUNE_COST, user_id, key, ATTUNE_COST))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "essence", "key": key}
    await db.raw_execute("UPDATE cult_characters SET attune=?, attune_until=? WHERE user_id=?", (element, now + ATTUNE_HOURS * 3600, user_id))
    return {"ok": True, "element": element}


async def begin(user_id: int, slot: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    realm = next((item for item in open_realms(calamity.today(now)) if item["slot"] == slot), None)
    if realm is None:
        return {"ok": False, "reason": "slot"}
    if await engine.activity_count(user_id, "cult_realm", now) >= DAILY:
        return {"ok": False, "reason": "limit"}
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item='realm_key' AND qty>=?", (realm["keys"], user_id, realm["keys"]))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "key", "need": realm["keys"]}
    await engine.claim_daily(user_id, "cult_realm", DAILY, now)
    run = {
        "user_id": user_id, "realm": realm, "floors": layout(realm, rng), "index": 0, "hp": 1.0, "might": False, "seed": f"{realm['id']}:{user_id}:{int(now)}",
        "loot": {"coins": 0, "essence": 0, "materials": {}, "herbs": {}, "gear": [], "keys": 0, "qi": 0},
    }
    return {"ok": True, "run": run}


def kind_at(run: dict) -> str:
    return run["floors"][run["index"]]


def boss_for(run: dict) -> dict:
    kind = kind_at(run)
    rank = {"monster": "minion", "elite": "elite"}.get(kind, "calamity" if run["realm"]["hidden"] else "lord")
    boss = calamity.generate(f"{run['seed']}:{run['index']}", rank, run["realm"]["element"])
    boss["slot"] = -1
    return boss


def fight_state(character: dict, run: dict) -> dict:
    mods = engine.fight_mods(character)
    state = calamity.new_state(character, mods, boss_for(run))
    p = state["p"]
    if run["might"]:
        p["atk"] *= MIGHT
    p["hp"] = max(1, int(p["max"] * run["hp"]))
    state["tag"] = f"{run['realm']['name']}, floor {run['index'] + 1}"
    state["realm"] = True
    return state


def tier_of(character: dict) -> int:
    return min(character["realm"], len(gear.GRADES) - 1)


def add_loot(run: dict, character: dict, kind: str, rng, careful: bool = False) -> dict:
    loot = run["loot"]
    tier = tier_of(character)
    hidden = 2 if run["realm"]["hidden"] else 1
    got: dict = {}
    amount = int(sum(settings.FIGHT_COINS[min(tier, len(settings.FIGHT_COINS) - 1)]) / 2 * COIN_FACTOR[kind] * hidden)
    loot["coins"] += amount
    got["coins"] = amount
    chance = {"monster": 30, "elite": 75, "treasure": 60 if careful else 40, "guardian": 100}[kind]
    if rng.randint(1, 100) <= chance:
        qty = {"guardian": 3 * hidden}.get(kind, rng.randint(1, 2))
        loot["essence"] += qty
        got["essence"] = qty
    if kind in ("monster", "elite") and rng.randint(1, 100) <= 40:
        material = gear.GRADES[tier]["material"]
        loot["materials"][material] = loot["materials"].get(material, 0) + 1
        got["material"] = material
    if kind in ("treasure", "guardian"):
        herb = gear.herb_for(rng.choice(list(gear.HERB_NAMES)), min(tier, 3))
        qty = rng.randint(1, 3) * hidden
        loot["herbs"][herb] = loot["herbs"].get(herb, 0) + qty
        got["herb"] = (herb, qty)
    return got


def treasure(run: dict, character: dict, careful: bool, rng) -> dict:
    if not careful and rng.random() < 0.3:
        run["hp"] = max(0.05, run["hp"] - 0.15)
        return {"trap": True, "hp": run["hp"]}
    got = add_loot(run, character, "treasure", rng, careful)
    if not careful:
        run["loot"]["coins"] += got["coins"]
        got["coins"] *= 2
    return got


def rest(run: dict, amount: float) -> float:
    before = run["hp"]
    run["hp"] = min(1.0, run["hp"] + amount)
    return run["hp"] - before


def pray(run: dict, boon: str) -> dict:
    if boon == "might":
        run["might"] = True
        run["hp"] = max(0.05, run["hp"] - 0.1)
        return {"boon": "might"}
    return {"boon": "vigor", "healed": rest(run, VIGOR_HEAL)}


def advance(run: dict) -> bool:
    run["index"] += 1
    return run["index"] >= len(run["floors"])


async def finish(user_id: int, run: dict, outcome: str, now: Optional[float] = None, rng=None) -> dict:
    rng = rng or random
    now = now or time.time()
    character = await engine.get(user_id)
    loot = run["loot"]
    element = run["realm"]["element"]
    scale = 0.5 if outcome == "fail" else 1.0
    parts: dict = {"outcome": outcome}
    items: dict = {}
    for key, qty in loot["materials"].items():
        items[key] = items.get(key, 0) + int(qty * scale)
    for key, qty in loot["herbs"].items():
        items[key] = items.get(key, 0) + int(qty * scale)
    items[elements.essence(element)] = int(loot["essence"] * scale)
    amount = int(loot["coins"] * scale)
    if outcome == "clear":
        hidden = run["realm"]["hidden"]
        amount += int(sum(settings.FIGHT_COINS[min(tier_of(character), len(settings.FIGHT_COINS) - 1)]) / 2 * 4 * (2 if hidden else 1))
        if rng.randint(1, 100) <= (HIDDEN_RETURN_KEY if hidden else RETURN_KEY):
            loot["keys"] += 1
        if rng.randint(1, 100) <= (70 if hidden else 40):
            loot["gear"].append(gear.drop(rng, tier_of(character)))
    if loot["keys"]:
        items["realm_key"] = loot["keys"]
    if amount:
        await coins.add(user_id, amount)
    parts["coins"] = amount
    stored = {}
    for key, qty in items.items():
        if qty > 0:
            got = await pouch.stash(user_id, key, qty, parts)
            if got:
                stored[key] = got
    parts["items"] = stored
    parts["gear"] = []
    if outcome != "fail":
        for dropped in loot["gear"]:
            parts["gear"].append(await engine.give_gear(user_id, dropped, rng))
    engine.settle(character, now)
    if outcome == "fail":
        loss = min(character["qi"], int(engine.need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        parts["qi_lost"] = loss
    elif outcome == "clear":
        parts["qi"] = engine.add_qi(character, int(engine.hourly(character) * settings.FIGHT_QI_HOURS * 6))
    await engine.save(character)
    if outcome == "clear":
        await feats.add(user_id, "realm_clear")
        await feats.add(user_id, f"realm_el_{element}")
        await engine.claim_daily(user_id, "cult_realm_clear", 99, now)
        await quest.bump(user_id, "realm_clear")
    await engine.wear_parts(user_id, parts)
    return parts
