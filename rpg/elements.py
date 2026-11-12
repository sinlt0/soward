ELEMENTS = {
    "metal": {"name": "Metal", "zh": "金", "weak": "fire", "color": (200, 215, 235)},
    "wood": {"name": "Wood", "zh": "木", "weak": "metal", "color": (110, 220, 140)},
    "water": {"name": "Water", "zh": "水", "weak": "earth", "color": (90, 170, 255)},
    "fire": {"name": "Fire", "zh": "火", "weak": "water", "color": (255, 130, 60)},
    "earth": {"name": "Earth", "zh": "土", "weak": "wood", "color": (214, 170, 100)},
    "thunder": {"name": "Thunder", "zh": "雷", "weak": "earth", "color": (170, 140, 255)},
}
WEAK_MULT = 1.35
RESIST_MULT = 0.8

TECH_ELEMENT = {
    "flying_sword": "metal", "twin_swords": "metal", "sword_intent": "metal", "ten_thousand_swords": "metal", "sword_heart": "metal",
    "heaven_cleaver": "metal", "iron_bone": "metal", "golden_body": "metal", "way_vajra_palm": "metal", "sect_formation": "metal",
    "pangu_fist": "earth", "quake_palm": "earth", "way_suppress": "earth", "sect_seal": "earth", "sect_shield": "earth", "binding_array": "earth",
    "blood_surge": "wood", "rejuvenation": "wood", "life_pill": "wood", "way_lotus_shield": "wood", "race_spirit": "wood", "way_gu_release": "wood",
    "way_gu_swarm": "wood", "way_blood_gu": "wood", "poison_mist": "wood", "bone_dissolving": "wood", "gathering_array": "wood",
    "pill_fire": "fire", "true_fire": "fire", "way_heart_demon": "fire", "way_wrath_king": "fire", "sect_wrath": "fire", "blood_roar": "fire",
    "mirror_array": "water", "way_netherstep": "water", "way_yin_wind": "water", "way_soul_wail": "water", "race_ghost": "water", "heavenly_net": "water",
    "way_thunder_seal": "thunder", "star_array": "thunder", "killing_array": "thunder", "way_gamble": "thunder", "race_demonic": "thunder",
}


def of(tech_key: str) -> str:
    return TECH_ELEMENT.get(tech_key, "")


def modifier(tech_key: str, target: str) -> float:
    element = of(tech_key)
    if not element or not target or target not in ELEMENTS:
        return 1.0
    if element == ELEMENTS[target]["weak"]:
        return WEAK_MULT
    if element == target:
        return RESIST_MULT
    return 1.0


def essence(element: str) -> str:
    return f"essence_{element}"
