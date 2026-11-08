import random
import secrets
import time
from typing import Optional

from rpg import bestiary, combat, engine, gear, quest, rifts, settings, wanderers
from utils import clans, coins, db

CROSSROADS = (
    {"text": "A broken shrine stands where two roads meet. Something glints in the ash at its feet.",
     "options": (("Search the ash", {"qi": 4, "coins": 3, "nothing": 2, "loss": 1}), ("Pray and move on", {"qi": 2, "nothing": 3}))},
    {"text": "A child's lantern floats above the road, burning with a pale, patient light.",
     "options": (("Follow it", {"qi": 4, "coins": 2, "loss": 2}), ("Put it out", {"nothing": 3, "qi": 1}))},
    {"text": "A dead cultivator sits against a tree, smiling. His hand is still closed around a pouch.",
     "options": (("Take the pouch", {"coins": 5, "loss": 2, "nothing": 1}), ("Bury him", {"qi": 4, "nothing": 2}))},
    {"text": "A stream runs backwards up a hill, glowing faintly with spiritual qi.",
     "options": (("Drink", {"qi": 5, "loss": 1}), ("Fill a flask", {"coins": 3, "qi": 2}))},
    {"text": "You hear a voice from a hollow stump, humming a lullaby from a world that no longer exists.",
     "options": (("Hum along", {"qi": 3, "nothing": 3}), ("Burn the stump", {"coins": 3, "loss": 3}))},
    {"text": "A trader's cart lies overturned. The horses are gone, but the crates are intact.",
     "options": (("Loot the crates", {"coins": 4, "loss": 2, "nothing": 1}), ("Right the cart", {"qi": 3, "coins": 2}))},
)

FLAVOR = (
    "The wind carries ash from a clan hall burned a thousand years ago. You find nothing, but you learn the way home a little better.",
    "A flock of pale birds crosses the sky in the shape of a sword. They vanish before you can follow.",
    "You walk for an hour and find only a signpost with the name scratched out.",
    "A distant howl rolls across the hills and fades. Whatever it was, it did not notice you.",
)


async def count_people(user_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM cult_npcs WHERE user_id=?", (user_id,))
    return int(row["n"]) if row else 0


async def meet(user_id: int, rng=None, kind: Optional[str] = None, now: Optional[float] = None) -> Optional[dict]:
    rng = rng or random
    if await count_people(user_id) >= settings.NPC_LIMIT:
        return None
    npc = wanderers.create(rng, kind)
    npc["npc_id"] = secrets.token_hex(3)
    await db.raw_execute(
        "INSERT INTO cult_npcs (user_id, npc_id, kind, name, zh, race, tale, affinity, met_at, last_talk) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 0)",
        (user_id, npc["npc_id"], npc["kind"], npc["name"], npc["zh"], npc["race"], npc["tale"], now or time.time()))
    return await person(user_id, npc["npc_id"])


async def person(user_id: int, npc_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM cult_npcs WHERE user_id=? AND npc_id=?", (user_id, npc_id))
    return dict(row) if row else None


async def people(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM cult_npcs WHERE user_id=? ORDER BY affinity DESC, met_at ASC", (user_id,))
    return [dict(row) for row in rows]


async def find_person(user_id: int, text: str) -> Optional[dict]:
    text = text.strip().lower()
    if not text:
        return None
    found = await people(user_id)
    exact = [npc for npc in found if text in (npc["npc_id"], npc["name"].lower(), npc["zh"])]
    if exact:
        return exact[0]
    partial = [npc for npc in found if text in npc["name"].lower()]
    return partial[0] if len(partial) == 1 else None


def friendship(affinity: int) -> str:
    if affinity >= 100:
        return "Dao companion"
    if affinity >= 50:
        return "confidant"
    if affinity >= 25:
        return "friend"
    return "acquaintance"


async def set_affinity(user_id: int, npc_id: str, amount: int) -> tuple[int, int]:
    npc = await person(user_id, npc_id)
    before = npc["affinity"]
    after = min(100, before + amount)
    await db.raw_execute("UPDATE cult_npcs SET affinity=? WHERE user_id=? AND npc_id=?", (after, user_id, npc_id))
    return before, after


async def milestone_rewards(user_id: int, character: dict, labels: list, rng, now: float) -> dict:
    rewards: dict = {}
    for label in labels:
        if label == "friend":
            amount = 100 * (character["realm"] + 1)
            await coins.add(user_id, amount)
            await engine.add_item(user_id, "qi_pill")
            rewards["friend"] = {"coins": amount, "item": "qi_pill"}
        elif label == "confidant":
            engine.settle(character, now)
            gained = engine.add_qi(character, int(engine.hourly(character) * 2))
            await engine.save(character)
            rewards["confidant"] = {"qi": gained, "secret": wanderers.secret(rng)}
        elif label == "companion":
            if character.get("bonds", 0) < settings.BOND_MAX:
                await db.raw_execute("UPDATE cult_characters SET bonds=bonds+1 WHERE user_id=?", (user_id,))
                rewards["companion"] = {"bond": True}
            else:
                amount = 500 * (character["realm"] + 1)
                await coins.add(user_id, amount)
                rewards["companion"] = {"coins": amount}
    return rewards


async def talk_person(user_id: int, npc_id: str, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    npc = await person(user_id, npc_id)
    if character is None or npc is None:
        return {"ok": False, "reason": "none"}
    if engine.today(npc["last_talk"]) == engine.today(now) and npc["last_talk"] > 0:
        return {"ok": False, "reason": "done", "npc": npc}
    await db.raw_execute("UPDATE cult_npcs SET last_talk=? WHERE user_id=? AND npc_id=?", (now, user_id, npc_id))
    before, after = await set_affinity(user_id, npc_id, rng.randint(*settings.TALK_AFFINITY))
    labels = wanderers.crossed(before, after)
    rewards = await milestone_rewards(user_id, await engine.get(user_id), labels, rng, now)
    await quest.bump(user_id, "talk")
    return {"ok": True, "npc": await person(user_id, npc_id), "line": wanderers.line(npc["kind"], rng), "before": before, "after": after, "milestones": labels, "rewards": rewards}


async def act(user_id: int, npc_id: str, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    npc = await person(user_id, npc_id)
    if character is None or npc is None or not wanderers.KINDS[npc["kind"]]["action"]:
        return {"ok": False, "reason": "none"}
    kind = npc["kind"]
    if kind != "merchant" and await engine.claim_daily(user_id, f"cult_act_{npc_id}", 1, now) is None:
        return {"ok": False, "reason": "done"}
    result: dict = {"ok": True, "kind": kind}
    if kind == "alchemist":
        cost = max(1, int(engine.price("qi_pill", character) * 0.7))
        if not await coins.spend(user_id, cost):
            await db.raw_execute("UPDATE activity_state SET count=0 WHERE user_id=? AND activity=?", (user_id, f"cult_act_{npc_id}"))
            return {"ok": False, "reason": "coins", "cost": cost}
        await engine.add_item(user_id, "qi_pill")
        result["cost"] = cost
        await set_affinity(user_id, npc_id, 3)
    elif kind == "swordsman":
        engine.settle(character, now)
        result["qi"] = engine.add_qi(character, int(engine.hourly(character) * 1.5 * (1 + npc["affinity"] / 200)))
        await engine.save(character)
        await set_affinity(user_id, npc_id, 3)
    elif kind == "survivor":
        cost = 20 * (character["realm"] + 1)
        if not await coins.spend(user_id, cost):
            await db.raw_execute("UPDATE activity_state SET count=0 WHERE user_id=? AND activity=?", (user_id, f"cult_act_{npc_id}"))
            return {"ok": False, "reason": "coins", "cost": cost}
        result["cost"] = cost
        result["secret"] = wanderers.secret(rng)
        before, after = await set_affinity(user_id, npc_id, 10)
        result["milestones"] = wanderers.crossed(before, after)
        result["rewards"] = await milestone_rewards(user_id, await engine.get(user_id), result["milestones"], rng, now)
    elif kind == "scout":
        rift = await rift_get(user_id, now)
        if rift is None:
            result["rift"] = await rift_create(user_id, now, rng)
        else:
            await engine.add_item(user_id, "rift_shard")
            result["shard"] = True
        await set_affinity(user_id, npc_id, 3)
    elif kind == "merchant":
        items = await engine.inventory(user_id)
        total = 0
        sold: dict = {}
        for key, qty in items.items():
            value = settings.MATERIAL_VALUES.get(key)
            if value and qty > 0 and key != "rift_shard":
                for _ in range(qty):
                    if not await engine.take_item(user_id, key):
                        break
                    total += int(value * 1.2)
                    sold[key] = sold.get(key, 0) + 1
        if not sold:
            return {"ok": False, "reason": "nothing"}
        await coins.add(user_id, total)
        result.update({"coins": total, "sold": sold})
        await set_affinity(user_id, npc_id, 2)
    elif kind == "rival":
        return {"ok": False, "reason": "spar"}
    return result


async def spar_start(user_id: int, npc_id: str, now: Optional[float] = None) -> dict:
    now = now or time.time()
    character = await engine.get(user_id)
    npc = await person(user_id, npc_id)
    if character is None or npc is None or npc["kind"] != "rival":
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    if await engine.claim_daily(user_id, "cult_spar", settings.SPAR_DAILY, now) is None:
        return {"ok": False, "reason": "limit"}
    mods = engine.fight_mods(character)
    foe = dict(character)
    state = combat.new_duel(character, mods, foe, dict(mods, hp=mods["hp"] * 0.95), 0, npc["name"])
    state.pop("pvp", None)
    state["spar"] = npc_id
    return {"ok": True, "state": state}


async def spar_finish(user_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    npc_id = state["spar"]
    result = state["done"]
    parts: dict = {}
    if result == "win":
        character = await engine.get(user_id)
        engine.settle(character, now)
        parts["qi"] = engine.add_qi(character, int(engine.hourly(character)))
        await engine.save(character)
        before, after = await set_affinity(user_id, npc_id, 15)
    else:
        before, after = await set_affinity(user_id, npc_id, 3)
    parts["milestones"] = wanderers.crossed(before, after)
    parts["rewards"] = await milestone_rewards(user_id, await engine.get(user_id), parts["milestones"], rng, now)
    return {"result": result, "parts": parts}


async def rift_get(user_id: int, now: Optional[float] = None) -> Optional[dict]:
    now = now or time.time()
    row = await db.raw_fetchone("SELECT * FROM cult_rifts WHERE user_id=?", (user_id,))
    if row is None:
        return None
    if row["expires_at"] <= now:
        await db.raw_execute("DELETE FROM cult_rifts WHERE user_id=?", (user_id,))
        return None
    return dict(row)


async def rift_create(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    name, zh, about = rifts.world(rng)
    await db.raw_execute(
        "INSERT INTO cult_rifts (user_id, world, zh, about, found_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET world=excluded.world, zh=excluded.zh, about=excluded.about, found_at=excluded.found_at, expires_at=excluded.expires_at",
        (user_id, name, zh, about, now, now + rifts.EXPIRY_HOURS * 3600))
    return await rift_get(user_id, now)


async def rift_open_with_shards(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    if await rift_get(user_id, now):
        return {"ok": False, "reason": "open"}
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item='rift_shard' AND qty>=?", (rifts.SHARDS_TO_OPEN, user_id, rifts.SHARDS_TO_OPEN))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "shards"}
    return {"ok": True, "rift": await rift_create(user_id, now, rng)}


def tier_coins(character: dict) -> int:
    low, high = settings.FIGHT_COINS[min(character["realm"], len(settings.FIGHT_COINS) - 1)]
    return (low + high) // 2


async def rift_enter(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    rift = await rift_get(user_id, now)
    if rift is None:
        return {"ok": False, "reason": "no_rift"}
    if await engine.claim_daily(user_id, "cult_rift", rifts.DAILY, now) is None:
        return {"ok": False, "reason": "limit"}
    await db.raw_execute("DELETE FROM cult_rifts WHERE user_id=?", (user_id,))
    run = {"world": rift["world"], "zh": rift["zh"], "about": rift["about"], "rooms": rifts.rooms(rng), "index": 0,
           "loot": {"coins": 0, "qi": 0, "materials": {}, "gear": [], "shards": 0}, "safe": rng.randint(0, 1), "user_id": user_id}
    return {"ok": True, "run": run}


def beast_state(character: dict, rng, boss: bool = False, tag: Optional[str] = None, key: Optional[str] = None) -> dict:
    mods = engine.fight_mods(character)
    if boss:
        key = bestiary.boss_for(character["realm"])
        info = bestiary.BOSSES[key]
        state = combat.new_fight(character, mods, "grey_wolf")
        size = combat.scale(character["realm"], character["stage"])
        hp = int(100 * size * info["hp"] * 1.4)
        state["m"].update({"key": key, "name": info["name"], "zh": info["zh"], "skill": info["skill"], "hp": hp, "max": hp,
                           "atk": 14 * size * info["atk"], "def": 4 * size * info["def"]})
    else:
        key = key if key in bestiary.MONSTERS else rng.choice(bestiary.for_realm(character["realm"]))
        state = combat.new_fight(character, mods, key)
    state["remnant"] = bestiary.remnant(rng)
    state["wild"] = "boss" if boss else "beast"
    if tag:
        state["tag"] = tag
    return state


async def explore(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"ok": False, "reason": "none"}
    if engine.hurt(character, now):
        return {"ok": False, "reason": "hurt", "wait": engine.hurt(character, now)}
    last, _, _ = await engine.activity_row(user_id, "cult_explore_at")
    if last + settings.EXPLORE_COOLDOWN > now:
        return {"ok": False, "reason": "cooldown", "wait": last + settings.EXPLORE_COOLDOWN - now}
    left = await engine.claim_daily(user_id, "cult_explore", settings.EXPLORE_DAILY, now)
    if left is None:
        return {"ok": False, "reason": "limit"}
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, 'cult_explore_at', ?, '', 0)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at", (user_id, now))
    kind = rng.choices(list(settings.EXPLORE_WEIGHTS), weights=list(settings.EXPLORE_WEIGHTS.values()))[0]
    if kind == "traveler":
        npc = await meet(user_id, rng, now=now)
        if npc is None:
            kind = "event"
        else:
            return {"ok": True, "kind": "traveler", "npc": npc, "left": left}
    if kind == "rift":
        if await rift_get(user_id, now) is None:
            return {"ok": True, "kind": "rift", "rift": await rift_create(user_id, now, rng), "left": left}
        await engine.add_item(user_id, "rift_shard")
        return {"ok": True, "kind": "shard", "left": left}
    if kind in ("beast", "boss"):
        return {"ok": True, "kind": kind, "state": beast_state(character, rng, kind == "boss"), "left": left}
    if kind == "treasure":
        return {"ok": True, "kind": "treasure", "text": rng.choice(rifts.TREASURE_TEXT), "trap": rng.random() < 0.25, "left": left}
    if kind == "event":
        index = rng.randrange(len(CROSSROADS))
        return {"ok": True, "kind": "event", "index": index, "event": CROSSROADS[index], "left": left}
    return {"ok": True, "kind": "nothing", "text": rng.choice(FLAVOR), "left": left}


async def crossroads(user_id: int, index: int, option: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    weights = CROSSROADS[index]["options"][option][1]
    outcome = rng.choices(list(weights), weights=list(weights.values()))[0]
    result: dict = {"outcome": outcome}
    if outcome == "qi":
        engine.settle(character, now)
        result["qi"] = engine.add_qi(character, int(engine.hourly(character) * 0.8))
        await engine.save(character)
    elif outcome == "coins":
        amount = tier_coins(character)
        await coins.add(user_id, amount)
        result["coins"] = amount
    elif outcome == "loss":
        engine.settle(character, now)
        loss = min(character["qi"], int(engine.need(character) * 0.02))
        character["qi"] -= loss
        await engine.save(character)
        result["loss"] = loss
    return result


async def treasure(user_id: int, careful: bool, trap: bool, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    tier = min(character["realm"], len(gear.GRADES) - 1)
    if not careful and trap:
        engine.settle(character, now)
        loss = min(character["qi"], int(engine.need(character) * 0.03))
        character["qi"] -= loss
        await engine.save(character)
        return {"trap": True, "loss": loss}
    amount = tier_coins(character) * (1 if careful else 3)
    await coins.add(user_id, amount)
    result: dict = {"coins": amount}
    if rng.random() < (0.4 if careful else 0.7):
        material = gear.GRADES[tier]["material"]
        count = rng.randint(1, 2)
        await engine.add_item(user_id, material, count)
        result["material"] = (material, count)
    return result


async def wild_finish(user_id: int, state: dict, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    if character is None:
        return {"result": state["done"], "parts": {}}
    result = state["done"]
    parts: dict = {}
    boss = state.get("wild") == "boss"
    tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
    if result == "win":
        await quest.bump(user_id, "win")
        amount = int(rng.randint(*settings.FIGHT_COINS[tier]) * (settings.WILD_BOSS_COIN_MULT if boss else settings.WILD_COIN_MULT))
        await coins.add(user_id, max(1, amount))
        parts["coins"] = max(1, amount)
        engine.settle(character, now)
        parts["qi"] = engine.add_qi(character, int(engine.hourly(character) * (1.5 if boss else 0.5)))
        if boss or rng.randint(1, 100) <= 25:
            material = gear.GRADES[tier]["material"]
            count = rng.randint(2, 4) if boss else 1
            await engine.add_item(user_id, material, count)
            parts["material"] = (material, count)
        if boss:
            if rng.randint(1, 100) <= settings.WILD_BOSS_GEAR_CHANCE:
                drop = gear.drop(rng, tier)
                await engine.add_item(user_id, drop)
                parts["gear"] = drop
            if rng.randint(1, 100) <= settings.WILD_BOSS_SHARD_CHANCE:
                await engine.add_item(user_id, "rift_shard")
                parts["shard"] = True
        await engine.save(character)
    elif result == "lose":
        engine.settle(character, now)
        loss = min(character["qi"], int(engine.need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        parts["qi_lost"] = loss
        await engine.save(character)
    return {"result": result, "parts": parts}


def room_fight(character: dict, rng, guardian: bool) -> dict:
    state = beast_state(character, rng, guardian)
    state["run"] = True
    return state


def add_loot(run: dict, character: dict, factor: float, rng, material_chance: int = 35) -> dict:
    tier = min(character["realm"], len(gear.GRADES) - 1)
    amount = int(tier_coins(character) * factor)
    run["loot"]["coins"] += amount
    got = {"coins": amount}
    if rng.randint(1, 100) <= material_chance:
        material = gear.GRADES[tier]["material"]
        run["loot"]["materials"][material] = run["loot"]["materials"].get(material, 0) + 1
        got["material"] = material
    return got


async def rift_finish(user_id: int, run: dict, outcome: str, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    loot = run["loot"]
    tier = min(character["realm"], len(gear.GRADES) - 1)
    summary: dict = {"outcome": outcome}
    scale = 0.5 if outcome == "fail" else 1.0
    summary["coins"] = int(loot["coins"] * scale)
    if summary["coins"] > 0:
        await coins.add(user_id, summary["coins"])
    engine.settle(character, now)
    if outcome == "clear":
        summary["coins"] += int(tier_coins(character) * 4)
        await coins.add(user_id, int(tier_coins(character) * 4))
        loot["shards"] += rng.randint(1, 2)
        material = gear.GRADES[tier]["material"]
        loot["materials"][material] = loot["materials"].get(material, 0) + rng.randint(2, 4)
        if rng.randint(1, 100) <= 40:
            loot["gear"].append(gear.drop(rng, tier))
        loot["qi"] += int(engine.hourly(character) * 2)
    if outcome != "fail":
        for material, count in loot["materials"].items():
            await engine.add_item(user_id, material, count)
        if loot["shards"]:
            await engine.add_item(user_id, "rift_shard", loot["shards"])
        for drop in loot["gear"]:
            await engine.add_item(user_id, drop)
        summary["materials"] = dict(loot["materials"])
        summary["shards"] = loot["shards"]
        summary["gear"] = list(loot["gear"])
        summary["qi"] = engine.add_qi(character, int(loot["qi"]))
    else:
        loss = min(character["qi"], int(engine.need(character) * settings.FIGHT_DEFEAT_QI))
        character["qi"] -= loss
        summary["qi_lost"] = loss
    await engine.save(character)
    return summary


def strike_state(character: dict, boss: dict) -> dict:
    state = combat.new_fight(character, engine.fight_mods(character), "grey_wolf")
    base = bestiary.BOSSES[bestiary.boss_for(character["realm"])]
    size = combat.scale(character["realm"], character["stage"])
    hp = int(100 * size * base["hp"] * settings.BOSS_PERSONAL_HP)
    state["m"].update({"key": boss["key"], "name": boss["name"], "zh": boss["zh"], "skill": boss["skill"], "hp": hp, "max": hp,
                       "atk": 14 * size * base["atk"], "def": 4 * size * base["def"]})
    state["limit"] = settings.BOSS_TURNS
    state["world_boss"] = True
    return state


def strike_units(character: dict, state: dict) -> int:
    m = state["m"]
    fraction = max(0.0, min(1.0, (m["max"] - max(0, m["hp"])) / m["max"]))
    return int(1000 * fraction * (1 + character["realm"]))


async def world_boss_payout(damages: dict, rng=None) -> dict:
    rng = rng or random
    if not damages:
        return {}
    average = sum(damages.values()) / len(damages)
    payouts: dict = {}
    for user_id, damage in damages.items():
        character = await engine.get(user_id)
        if character is None:
            continue
        tier = min(character["realm"], len(settings.FIGHT_COINS) - 1)
        low, high = settings.FIGHT_COINS[tier]
        ratio = damage / average if average else 1
        amount = int((low + high) / 2 * settings.BOSS_COINS_MULT * (0.5 + min(1.5, ratio)))
        await coins.add(user_id, amount)
        material = gear.GRADES[tier]["material"]
        count = rng.randint(2, 4)
        await engine.add_item(user_id, material, count)
        entry: dict = {"coins": amount, "damage": damage, "material": (material, count)}
        if rng.randint(1, 100) <= 25:
            drop = gear.drop(rng, tier)
            await engine.add_item(user_id, drop)
            entry["gear"] = drop
        if rng.randint(1, 100) <= 40:
            await engine.add_item(user_id, "rift_shard")
            entry["shard"] = True
        payouts[user_id] = entry
    return payouts


async def guide_steps(user_id: int, character: dict) -> list[tuple[bool, str, str]]:
    fought = (await engine.activity_row(user_id, "cult_fight"))[0] > 0
    explored = (await engine.activity_row(user_id, "cult_explore"))[0] > 0
    rifted = (await engine.activity_row(user_id, "cult_rift"))[0] > 0
    in_clan = await clans.membership(user_id) is not None
    return [
        (bool(character["path"]), "Choose your way and path", "`cultivate awaken`"),
        (character["last_meditate"] > 0, "Meditate to gather qi", "`cultivate meditate`"),
        (fought, "Defeat an abyssal beast", "`cultivate fight`"),
        (explored, "Explore the wilds and meet travelers", "`world explore`"),
        (character["realm"] > 0 or character["stage"] > 0, "Break through to the next layer", "`cultivate breakthrough`"),
        (in_clan, "Join or found a clan, your great family", "`clan create <name>` or ask for an invite"),
        (rifted, "Enter a rift into a lower world", "`world rift`"),
    ]


async def run_action(user_id: int, run: dict, action: str, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    rng = rng or random
    character = await engine.get(user_id)
    loot = run["loot"]
    result: dict = {"action": action}
    if action == "sneak":
        if rng.random() < 0.6:
            result["sneaked"] = True
        else:
            result["caught"] = True
    elif action in ("careful", "open"):
        trapped = run.get("trap", False)
        if action == "open" and trapped:
            lost = int(loot["coins"] * 0.25)
            loot["coins"] -= lost
            result["trap"] = lost
        else:
            factor = 1.0 if action == "careful" else 2.5
            result.update(add_loot(run, character, factor, rng, 40 if action == "careful" else 70))
    elif action in ("left", "right"):
        if (0 if action == "left" else 1) == run["safe"]:
            result.update(add_loot(run, character, 0.8, rng, 30))
            result["safe"] = True
        else:
            lost = int(loot["coins"] * 0.25)
            loot["coins"] -= lost
            result["fell"] = lost
    elif action == "spring":
        gained = int(engine.hourly(character) * 0.5)
        loot["qi"] += gained
        result["qi"] = gained
    elif action == "talk":
        npc = await meet(user_id, rng, now=now)
        result["npc"] = npc
        result.update(add_loot(run, character, 0.5, rng, 20))
    return result
