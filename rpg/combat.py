import random

from rpg import arts, bestiary, elements

MAX_TURNS = 30
TRAIT_SKILL_EVERY = 3
SKILL_POWER = 1.6
FLEE_CHANCE = 60
ATTUNE_MULT = 1.25


def scale(realm: int, stage: int) -> float:
    return (4 ** realm) * (1 + 0.1 * stage)


def hit(attack: float, power: float, defense: float, rng) -> int:
    return max(1, int(attack * power * rng.uniform(0.9, 1.1) - defense * 0.6))


def player_stats(character: dict, mods: dict) -> dict:
    size = scale(character["realm"], character["stage"])
    hp = 120 * size * mods.get("hp", 1.0)
    return {
        "hp": int(hp), "max": int(hp),
        "atk": 14 * size * mods.get("atk", 1.0),
        "def": 5 * size * mods.get("def", 1.0),
        "dodge": min(40, 5 + mods.get("dodge", 0)),
        "crit": min(60, mods.get("crit", 0)),
        "tech": mods.get("tech", 1.0),
        "attune": mods.get("attune", ""),
    }


def affix_scale(state: dict, damage: int, rng) -> tuple:
    m = state["m"]
    affixes = m.get("affixes", ())
    note = ""
    if "evasive" in affixes and rng.random() < 0.2:
        return 0, " It slips away from the blow."
    if "bulwark" in affixes and state["turn"] <= 3:
        damage = max(1, int(damage * 0.55))
        note = " Its ward absorbs part of the blow."
    return damage, note


def strike(state: dict, power: float, rng, tech: bool = False, key: str = "") -> tuple:
    p, m = state["p"], state["m"]
    if tech:
        power *= p.get("tech", 1.0)
    if p.get("buff", 0) > 0:
        power *= p["buff_mult"]
    damage = hit(p["atk"], power, m["def"], rng)
    crit = rng.random() * 100 < p.get("crit", 0)
    if crit:
        damage = int(damage * 1.5)
    if tech and key:
        multiplier = elements.modifier(key, m.get("element", ""))
        if p.get("attune") and elements.of(key) == p["attune"]:
            multiplier *= ATTUNE_MULT
        if multiplier != 1.0:
            damage = max(1, int(damage * multiplier))
            state["element_note"] = " **Weakness!**" if multiplier > 1 else " Resisted."
    return damage, crit


def new_fight(character: dict, mods: dict, monster_key: str) -> dict:
    monster = bestiary.MONSTERS[monster_key]
    size = scale(character["realm"], character["stage"])
    hp = int(100 * size * monster["hp"])
    player = player_stats(character, mods)
    player.update({"cd": {}, "guard": 0, "evade": 0, "buff": 0, "buff_mult": 1.0})
    return {
        "p": player,
        "m": {"key": monster_key, "name": monster["name"], "zh": monster["zh"], "skill": monster["skill"], "hp": hp, "max": hp,
              "atk": 14 * size * monster["atk"], "def": 4 * size * monster["def"], "poison": 0, "poison_dmg": 0, "stun": 0, "acts": 0},
        "path": character["path"], "realm": character["realm"], "turn": 1, "log": [], "done": None,
        "techs": arts.known(character, mods.get("sect", 0)),
    }


def new_duel(character: dict, mods: dict, target: dict, target_mods: dict, target_id: int, name: str) -> dict:
    state = new_fight(character, mods, "grey_wolf")
    foe = player_stats(target, target_mods)
    best = max(arts.unlocked(target["path"], target["realm"]).values(), key=lambda tech: tech["realm"], default=None)
    state["m"] = {"key": "duel", "name": name, "zh": "", "skill": best["name"] if best else "Killing Intent", "hp": foe["hp"], "max": foe["max"],
                  "atk": foe["atk"], "def": foe["def"], "poison": 0, "poison_dmg": 0, "stun": 0, "acts": 0}
    state["pvp"] = True
    state["target"] = target_id
    return state


def new_party(members: list, leader_names: list, boss_key: str) -> dict:
    leader_character, leader_mods = members[0]
    stats = [player_stats(character, mods) for character, mods in members]
    boss = bestiary.BOSSES[boss_key]
    top = max(scale(character["realm"], character["stage"]) for character, _ in members)
    count = len(members)
    state = new_fight(leader_character, leader_mods, "grey_wolf")
    hp = sum(item["hp"] for item in stats)
    atk_sorted = sorted((item["atk"] for item in stats), reverse=True)
    def_sorted = sorted((item["def"] for item in stats), reverse=True)
    state["p"].update({
        "hp": hp, "max": hp,
        "atk": atk_sorted[0] + 0.6 * sum(atk_sorted[1:]),
        "def": def_sorted[0] + 0.5 * sum(def_sorted[1:]),
    })
    boss_hp = int(100 * top * boss["hp"] * (1 + 1.0 * (count - 1)))
    state["m"] = {"key": boss_key, "name": boss["name"], "zh": boss["zh"], "skill": boss["skill"], "hp": boss_hp, "max": boss_hp,
                  "atk": 14 * top * boss["atk"] * (1 + 0.15 * (count - 1)), "def": 4 * top * boss["def"], "poison": 0, "poison_dmg": 0, "stun": 0, "acts": 0}
    state["party"] = [character["user_id"] for character, _ in members]
    return state


def ready(state: dict) -> dict:
    return {key: tech for key, tech in state["techs"].items() if state["p"]["cd"].get(key, 0) <= 0}


def reflect(state: dict, damage: int) -> None:
    m, p = state["m"], state["p"]
    if "thorns" in m.get("affixes", ()) and damage > 0:
        back = max(1, int(damage * 0.12))
        p["hp"] -= back
        state["log"].append(f"Thorns lash back for {back}.")
        if p["hp"] <= 0:
            state["done"] = "lose"


def monster_turn(state: dict, rng) -> None:
    p, m = state["p"], state["m"]
    if state["done"]:
        return
    if "regen" in m.get("affixes", ()) and m["hp"] > 0:
        gained = min(m["max"] - m["hp"], max(1, int(m["max"] * 0.04)))
        if gained:
            m["hp"] += gained
            state["log"].append(f"{m['name']} regenerates {gained}.")
    if m["poison"] > 0:
        m["hp"] -= m["poison_dmg"]
        m["poison"] -= 1
        state["log"].append(f"The burn eats at {m['name']} for {m['poison_dmg']}.")
        if m["hp"] <= 0:
            state["done"] = "win"
            return
    if m["stun"] > 0:
        m["stun"] -= 1
        state["log"].append(f"{m['name']} is bound and cannot move.")
        return
    m["acts"] += 1
    heavy = m["acts"] % TRAIT_SKILL_EVERY == 0
    label = m["skill"] if heavy else "attacks"
    if p["evade"] > 0:
        p["evade"] -= 1
        state["log"].append(f"{m['name']} {'uses ' + label if heavy else label}, but the array bends the blow away.")
        return
    if rng.random() * 100 < p["dodge"]:
        state["log"].append(f"{m['name']} {'uses ' + label if heavy else label}, but you slip aside.")
        return
    attack = m["atk"]
    if "frenzy" in m.get("affixes", ()) and m["hp"] <= m["max"] * 0.5:
        attack *= 1.35
    if m.get("weak", 0) > 0:
        attack *= 1 - m.get("weak_cut", 0.3)
        m["weak"] -= 1
    damage = hit(attack, SKILL_POWER if heavy else 1.0, p["def"], rng)
    if p["guard"] > 0:
        damage = max(1, damage // 2)
        p["guard"] -= 1
    p["hp"] -= damage
    state["foe"] = "foe_skill" if heavy else "foe_attack"
    if "vampiric" in m.get("affixes", ()):
        drained = min(m["max"] - m["hp"], int(damage * 0.35))
        if drained > 0:
            m["hp"] += drained
            state["log"].append(f"{m['name']} drinks {drained} health from the wound.")
    if "venom" in m.get("affixes", ()):
        extra = max(1, int(p["max"] * 0.04))
        p["hp"] -= extra
        state["log"].append(f"Venom burns you for {extra}.")
    state["log"].append(f"{m['name']} {'uses **' + label + '**' if heavy else label} for {damage}.")
    if p["hp"] <= 0:
        state["done"] = "lose"


def act(state: dict, action: str, rng=None) -> dict:
    rng = rng or random
    p, m = state["p"], state["m"]
    state["log"] = []
    state["anim"] = None
    state["foe"] = None
    if action == "flee":
        if rng.randint(1, 100) <= FLEE_CHANCE:
            state["done"] = "flee"
            state["log"].append("You break away and escape.")
            return state
        state["log"].append("You try to flee, but it blocks your way.")
    elif action == "defend":
        p["guard"] = max(p["guard"], 1)
        state["anim"] = "defend"
        state["log"].append("You brace yourself.")
    elif action == "attack":
        damage, crit = strike(state, 1.0, rng)
        damage, note = affix_scale(state, damage, rng)
        m["hp"] -= damage
        state["anim"] = "attack"
        state["log"].append(f"You strike with a qi palm for {damage}." + (" **Critical!**" if crit else "") + note)
        reflect(state, damage)
    else:
        tech = state["techs"].get(action)
        if tech is None or p["cd"].get(action, 0) > 0:
            state["log"].append("That technique is not ready.")
            return state
        p["cd"][action] = tech["cd"] + 1
        state["anim"] = action
        kind = tech["kind"]
        if kind in ("damage", "poison", "stun", "weaken", "lifesteal", "execute"):
            power = tech["power"]
            if kind == "execute" and m["hp"] <= m["max"] * tech["below"]:
                power *= tech["bonus"]
            state["element_note"] = ""
            damage, crit = strike(state, power, rng, True, action)
            damage, note = affix_scale(state, damage, rng)
            m["hp"] -= damage
            state["log"].append(f"**{tech['name']}** hits for {damage}." + (" **Critical!**" if crit else "") + state["element_note"] + note)
            reflect(state, damage)
            if kind == "poison":
                m["poison"] = tech["turns"]
                m["poison_dmg"] = max(1, int(p["atk"] * 0.3))
            if kind == "stun":
                m["stun"] = 1
            if kind == "weaken":
                m["weak"] = tech["turns"]
                m["weak_cut"] = tech["cut"]
            if kind == "lifesteal":
                gained = min(p["max"] - p["hp"], int(damage * tech["steal"]))
                p["hp"] += gained
                if gained:
                    state["log"].append(f"You drink in {gained} health.")
        elif kind == "multi":
            total = 0
            state["element_note"] = ""
            for _ in range(tech["hits"]):
                damage, _crit = strike(state, tech["power"], rng, True, action)
                damage, _note = affix_scale(state, damage, rng)
                total += damage
            m["hp"] -= total
            state["log"].append(f"**{tech['name']}** lands {tech['hits']} hits for {total}." + state["element_note"])
            reflect(state, total)
        elif kind == "buff":
            p["buff"] = tech["turns"] + 1
            p["buff_mult"] = tech["mult"]
            state["log"].append(f"**{tech['name']}** surges through you.")
        elif kind == "guard":
            p["guard"] = tech["turns"]
            state["log"].append(f"**{tech['name']}** hardens your body.")
        elif kind == "heal":
            amount = int(p["max"] * tech["amount"])
            before = p["hp"]
            p["hp"] = min(p["max"], p["hp"] + amount)
            state["log"].append(f"**{tech['name']}** restores {p['hp'] - before} health.")
        elif kind == "evade":
            p["evade"] = 1
            state["log"].append(f"**{tech['name']}** shimmers around you.")
    if m["hp"] <= 0:
        state["done"] = "win"
        return state
    monster_turn(state, rng)
    if state["done"]:
        return state
    for key in list(p["cd"]):
        p["cd"][key] -= 1
    if p.get("buff", 0) > 0:
        p["buff"] -= 1
    state["turn"] += 1
    if state["turn"] > state.get("limit", MAX_TURNS):
        state["done"] = "flee"
        state["log"].append("Both of you are exhausted and the fight ends in a draw.")
    return state
