import os

from rpg import arts

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "anims")

GOLD = (255, 214, 120)
STEEL = (190, 215, 255)
BLOOD = (230, 60, 70)
FIRE = (255, 130, 50)
JADE = (110, 230, 160)
VIOLET = (170, 110, 255)
AZURE = (90, 170, 255)
EARTH = (214, 170, 100)
SMOKE = (150, 150, 170)
POISON = (140, 230, 90)
PINK = (255, 140, 200)
WHITE = (255, 255, 255)

SPECS = {
    "flying_sword": ("slash", STEEL, WHITE, {"count": 1}),
    "twin_swords": ("slash", STEEL, AZURE, {"count": 2}),
    "sword_intent": ("aura", STEEL, WHITE, {"swords": True}),
    "ten_thousand_swords": ("blades", STEEL, GOLD, {"count": 22}),
    "sword_heart": ("execute", STEEL, BLOOD, {}),
    "heaven_cleaver": ("cleave", GOLD, WHITE, {}),
    "iron_bone": ("shield", EARTH, GOLD, {"hex": False}),
    "blood_roar": ("roar", BLOOD, FIRE, {"buff": True}),
    "pangu_fist": ("burst", EARTH, GOLD, {"cracks": True}),
    "blood_surge": ("aura", BLOOD, PINK, {}),
    "quake_palm": ("quake", EARTH, GOLD, {}),
    "golden_body": ("shield", GOLD, WHITE, {"hex": True}),
    "pill_fire": ("flame", FIRE, GOLD, {"burst": True}),
    "poison_mist": ("cloud", POISON, VIOLET, {}),
    "rejuvenation": ("aura", JADE, WHITE, {}),
    "bone_dissolving": ("cloud", POISON, WHITE, {"bones": True}),
    "life_pill": ("aura", GOLD, JADE, {"big": True}),
    "true_fire": ("flame", FIRE, AZURE, {"big": True}),
    "binding_array": ("rune", AZURE, WHITE, {"chains": True}),
    "gathering_array": ("rune", JADE, GOLD, {"inward": True}),
    "mirror_array": ("shield", AZURE, WHITE, {"hex": True, "mirror": True}),
    "killing_array": ("rune", BLOOD, GOLD, {"spikes": True}),
    "heavenly_net": ("net", GOLD, WHITE, {}),
    "star_array": ("stars", VIOLET, GOLD, {}),
    "way_thunder_seal": ("bolt", AZURE, WHITE, {"seal": True}),
    "way_radiance": ("aura", GOLD, WHITE, {"big": True}),
    "way_suppress": ("press", GOLD, WHITE, {}),
    "way_blood_rite": ("drain", BLOOD, PINK, {}),
    "way_soul_devour": ("drain", VIOLET, WHITE, {"souls": True}),
    "way_heart_demon": ("aura", BLOOD, VIOLET, {"flames": True}),
    "way_yin_wind": ("wind", VIOLET, STEEL, {"blades": True}),
    "way_netherstep": ("smoke", VIOLET, SMOKE, {}),
    "way_soul_wail": ("roar", VIOLET, WHITE, {}),
    "way_vajra_palm": ("burst", GOLD, WHITE, {"palm": True}),
    "way_lotus_shield": ("lotus", PINK, WHITE, {}),
    "way_wrath_king": ("roar", FIRE, GOLD, {"big": True}),
    "way_gu_release": ("swarm", POISON, WHITE, {"few": True}),
    "way_blood_gu": ("drain", BLOOD, POISON, {"swarm": True}),
    "way_gu_swarm": ("swarm", POISON, BLOOD, {}),
    "way_backstab": ("execute", SMOKE, BLOOD, {"behind": True}),
    "way_smoke": ("smoke", SMOKE, WHITE, {"bomb": True}),
    "way_gamble": ("coins", GOLD, WHITE, {}),
    "race_human": ("aura", AZURE, WHITE, {}),
    "race_demon": ("claw", VIOLET, BLOOD, {"big": True}),
    "race_beast": ("claw", EARTH, WHITE, {"count": 3}),
    "race_spirit": ("bloom", JADE, PINK, {}),
    "race_witch": ("totem", BLOOD, GOLD, {}),
    "race_witchhuman": ("burst", BLOOD, GOLD, {"double": True}),
    "race_ghost": ("smoke", AZURE, WHITE, {"ghost": True}),
    "race_immortal": ("cleave", WHITE, GOLD, {"halo": True}),
    "race_demonic": ("claw", VIOLET, WHITE, {"count": 4}),
    "sect_shield": ("shield", JADE, WHITE, {"hex": True}),
    "sect_formation": ("blades", GOLD, STEEL, {"count": 12}),
    "sect_chant": ("aura", JADE, GOLD, {"notes": True}),
    "sect_seal": ("press", AZURE, GOLD, {"seal": True}),
    "sect_wrath": ("cleave", FIRE, GOLD, {"big": True}),
    "attack": ("burst", STEEL, WHITE, {"small": True}),
    "defend": ("shield", AZURE, WHITE, {"hex": False, "small": True}),
    "foe_attack": ("foe", BLOOD, WHITE, {}),
    "foe_skill": ("foe", VIOLET, BLOOD, {"big": True}),
}


def all_keys() -> list:
    return list(SPECS)


def path(key: str) -> str:
    return os.path.join(DIR, f"{key}.gif")


def exists(key: str) -> bool:
    return key in SPECS and os.path.isfile(path(key))


def known_techniques() -> set:
    keys = set()
    for table in (arts.TECHNIQUES, arts.WAY_TECHNIQUES, arts.RACE_TECHNIQUES, arts.SECT_TECHNIQUES):
        keys.update(table)
    return keys
