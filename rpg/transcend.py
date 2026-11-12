import random
import time
from typing import Optional

from rpg import engine, settings, titles
from utils import coins, db

KINDS = {
    "splitting": {"name": "Splitting Bolt", "zh": "裂空雷", "best": "dodge", "omen": "The clouds fork and crawl across the sky."},
    "crushing": {"name": "Crushing Bolt", "zh": "镇岳雷", "best": "endure", "omen": "The sky sinks and the air turns heavy."},
    "piercing": {"name": "Piercing Bolt", "zh": "穿心雷", "best": "strike", "omen": "A single white thread gathers above you."},
}
ACTIONS = ("dodge", "endure", "strike", "circulate")
ACTION_NAMES = {"dodge": "Dodge", "endure": "Endure", "strike": "Strike back", "circulate": "Circulate qi"}
VOICE = {
    "intro": ["The heavens go silent.", "You stand against the sky and the sky answers."],
    "right": ["You read the heavens and the bolt breaks against you.", "The lightning finds nothing to hold.", "Your Dao answers the sky."],
    "wrong": ["The bolt was not what you thought it was.", "The heavens laugh and the thunder lands in full.", "You misread the sky and pay for it."],
    "heal": ["You draw qi through your meridians and mend what you can."],
    "win": ["The last bolt dies and the clouds tear open.", "The heavens fall quiet, and for the first time they bow."],
    "lose": ["The thunder takes everything and the sky closes.", "Heaven does not forgive."],
}


def tier_for(character: dict) -> int:
    return int(character.get("transcend") or 0) + 1


def waves_for(tier: int) -> int:
    return min(settings.TRANSCEND_WAVES_MAX, settings.TRANSCEND_WAVES + (tier + 1) // 2)


def fee_for(tier: int) -> int:
    return settings.TRANSCEND_FEE * tier


def omen_chance(tier: int) -> int:
    return max(settings.TRANSCEND_OMEN_MIN, settings.TRANSCEND_OMEN - settings.TRANSCEND_OMEN_STEP * tier)


def check(character: Optional[dict], now: Optional[float] = None) -> Optional[str]:
    now = now or time.time()
    if character is None or not character["path"]:
        return "none"
    if int(character.get("transcend") or 0) >= settings.TRANSCEND_MAX:
        return "max"
    if engine.gate_open(character):
        return "open"
    if not engine.is_major(character):
        return "stage"
    if engine.hurt(character, now):
        return "hurt"
    if character["qi"] < engine.need(character):
        return "qi"
    return None


def wave_damage(state: dict, rng) -> tuple:
    kind = rng.choice(list(KINDS))
    omen = kind if rng.randint(1, 100) <= omen_chance(state["tier"]) else rng.choice([k for k in KINDS if k != kind])
    return kind, omen


def new_state(character: dict, mods: dict, rng=None) -> dict:
    from rpg import combat
    rng = rng or random
    tier = tier_for(character)
    stats = combat.player_stats(character, mods)
    state = {
        "tier": tier, "waves": waves_for(tier), "wave": 0, "hp": stats["max"], "max": stats["max"],
        "heals": settings.TRANSCEND_HEALS, "relief": min(0.2, int(character.get("chance_bonus") or 0) / 100),
        "dodge": min(40, stats["dodge"]), "guard": min(0.3, max(0.0, (mods.get("def", 1.0) - 1) * 0.15)),
        "done": None, "log": list(VOICE["intro"]), "history": [],
    }
    state["bolt"], state["omen"] = wave_damage(state, rng)
    return state


def base_fraction(state: dict) -> float:
    return settings.TRANSCEND_BASE + settings.TRANSCEND_WAVE_STEP * state["wave"] + settings.TRANSCEND_TIER_STEP * state["tier"]


def act(state: dict, action: str, rng=None) -> dict:
    rng = rng or random
    if state["done"] or action not in ACTIONS:
        return state
    if action == "circulate" and state["heals"] <= 0:
        state["log"] = ["You have no qi left to circulate."]
        return state
    bolt = KINDS[state["bolt"]]
    fraction = base_fraction(state) * (1 - state["relief"]) * (1 - state["guard"])
    lines = []
    if action == "circulate":
        state["heals"] -= 1
        gained = min(state["max"] - state["hp"], int(state["max"] * settings.TRANSCEND_HEAL))
        state["hp"] += gained
        lines.append(rng.choice(VOICE["heal"]) + f" (+{gained})")
        factor, tag = settings.TRANSCEND_WRONG, "wrong"
    elif action == bolt["best"]:
        factor, tag = settings.TRANSCEND_RIGHT, "right"
    else:
        factor, tag = settings.TRANSCEND_WRONG, "wrong"
    if action == "dodge" and tag == "wrong" and rng.randint(1, 100) <= state["dodge"]:
        factor, tag = settings.TRANSCEND_RIGHT, "right"
        lines.append("A lucky step carries you clear.")
    damage = max(1, int(state["max"] * fraction * factor * rng.uniform(0.8, 1.25)))
    state["hp"] -= damage
    lines.append(f"**{bolt['name']}** ({bolt['zh']}) hits for **{damage}**. " + rng.choice(VOICE[tag]))
    state["history"].append({"bolt": state["bolt"], "action": action, "tag": tag, "damage": damage})
    state["last"] = {"bolt": state["bolt"], "action": action, "tag": tag, "damage": damage}
    state["log"] = lines
    if state["hp"] <= 0:
        state["hp"] = 0
        state["done"] = "lose"
        state["log"].append(rng.choice(VOICE["lose"]))
        return state
    state["wave"] += 1
    if state["wave"] >= state["waves"]:
        state["done"] = "win"
        state["log"].append(rng.choice(VOICE["win"]))
        return state
    state["bolt"], state["omen"] = wave_damage(state, rng)
    return state


async def start(user_id: int, now: Optional[float] = None, rng=None) -> dict:
    now = now or time.time()
    character = await engine.get(user_id)
    reason = check(character, now)
    if reason:
        return {"ok": False, "reason": reason, "character": character}
    tier = tier_for(character)
    fee = fee_for(tier)
    if not await coins.spend(user_id, fee):
        return {"ok": False, "reason": "fee", "fee": fee, "character": character}
    state = new_state(character, engine.fight_mods(character), rng)
    state["fee"] = fee
    return {"ok": True, "state": state, "character": character}


async def finish(user_id: int, state: dict, now: Optional[float] = None) -> dict:
    now = now or time.time()
    character = await engine.get(user_id)
    if character is None or not character["path"]:
        return {"won": False}
    won = state["done"] == "win"
    before = engine.realm_text(character)
    if won:
        character["transcend"] = int(character.get("transcend") or 0) + 1
        character["trans_realm"] = character["realm"]
        character["qi"] = 0
        character["chance_bonus"] = 0
        character["breakthroughs"] += 1
        if (character.get("title") or "") in ("", "transcendent"):
            character["title"] = "transcendent"
        await db.raw_execute("INSERT INTO cult_titles (user_id, title_key, earned_at) VALUES (?, ?, ?) ON CONFLICT(user_id, title_key) DO NOTHING", (user_id, "transcendent", now))
        await db.raw_execute("UPDATE cult_characters SET title=? WHERE user_id=?", (character["title"], user_id))
    else:
        cost = engine.need(character)
        character["qi"] = max(0, character["qi"] - int(cost * settings.TRANSCEND_FAIL_QI))
        character["chance_bonus"] = 0
        character["injured_until"] = now + settings.INJURY_SECONDS * settings.TRANSCEND_INJURY * engine.race_info(character).get("injury", 1.0) * engine.way_info(character).get("injury", 1.0)
    await engine.save(character)
    return {"won": won, "tier": int(character.get("transcend") or 0), "before": before, "after": engine.realm_text(character), "character": character, "title": titles.label("transcendent", int(character.get("transcend") or 0)) if won else ""}
