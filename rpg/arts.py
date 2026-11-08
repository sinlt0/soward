PATH_STATS = {
    "sword": {"atk": 1.20, "hp": 0.90},
    "body": {"hp": 1.35, "def": 1.30, "atk": 0.95},
    "alchemy": {"hp": 1.05},
    "formation": {"def": 1.15, "dodge": 4},
}

def tech(name, zh, realm, cd, kind, info, **extra):
    return {"name": name, "zh": zh, "realm": realm, "cd": cd, "kind": kind, "info": info, **extra}


TECHNIQUES = {
    "flying_sword": {"path": "sword", **tech("Flying Sword Strike", "飞剑斩", 0, 2, "damage", "A swift sword light for 1.8x damage.", power=1.8)},
    "twin_swords": {"path": "sword", **tech("Twin Sword Dance", "双剑舞", 0, 3, "multi", "Two blades strike for 1.2x damage each.", power=1.2, hits=2)},
    "sword_intent": {"path": "sword", **tech("Sword Intent", "剑意", 1, 4, "buff", "Sharpen your will: +40% damage for 3 turns.", mult=1.4, turns=3)},
    "ten_thousand_swords": {"path": "sword", **tech("Ten Thousand Swords", "万剑归宗", 1, 4, "damage", "A storm of blades for 3x damage.", power=3.0)},
    "sword_heart": {"path": "sword", **tech("Heart-Piercing Sword", "斩心剑", 2, 4, "execute", "2.4x damage, and 1.8x more against a weakened foe.", power=2.4, bonus=1.8, below=0.35)},
    "heaven_cleaver": {"path": "sword", **tech("Heaven-Cleaving Sword", "开天一剑", 3, 6, "damage", "One sword cuts the sky for 5.5x damage.", power=5.5)},
    "iron_bone": {"path": "body", **tech("Iron Bone Guard", "铁骨诀", 0, 4, "guard", "Harden your body: halve damage taken for 2 turns.", turns=2)},
    "blood_roar": {"path": "body", **tech("Blood Qi Roar", "血气咆哮", 0, 4, "buff", "Rouse your blood: +30% damage for 3 turns.", mult=1.3, turns=3)},
    "pangu_fist": {"path": "body", **tech("Pangu Fist", "盘古拳", 1, 3, "damage", "A fist that carries the weight of mountains for 2.3x damage.", power=2.3)},
    "blood_surge": {"path": "body", **tech("Qi Blood Surge", "气血涌", 1, 5, "heal", "Your blood runs hot and heals 40% of your health.", amount=0.4)},
    "quake_palm": {"path": "body", **tech("Earth-Quake Palm", "震地掌", 2, 4, "stun", "1.4x damage and the enemy loses its next turn.", power=1.4)},
    "golden_body": {"path": "body", **tech("Vajra Golden Body", "金刚不坏", 3, 6, "guard", "A body of gold: halve damage taken for 3 turns.", turns=3)},
    "pill_fire": {"path": "alchemy", **tech("Pill Fire Burst", "丹火爆", 0, 3, "poison", "1.3x damage and burns for 3 turns.", power=1.3, turns=3)},
    "poison_mist": {"path": "alchemy", **tech("Miasma Mist", "毒雾", 0, 4, "weaken", "0.8x damage and the enemy hits 30% softer for 3 turns.", power=0.8, turns=3, cut=0.3)},
    "rejuvenation": {"path": "alchemy", **tech("Rejuvenation Pill", "回春丹", 1, 5, "heal", "Swallow a pill and heal 35% of your health.", amount=0.35)},
    "bone_dissolving": {"path": "alchemy", **tech("Bone-Dissolving Pill", "蚀骨丹", 1, 4, "poison", "1.6x damage and burns for 4 turns.", power=1.6, turns=4)},
    "life_pill": {"path": "alchemy", **tech("Nine-Turn Life Pill", "九转还魂丹", 2, 6, "heal", "A legendary pill that heals 60% of your health.", amount=0.6)},
    "true_fire": {"path": "alchemy", **tech("Samadhi True Fire", "三昧真火", 3, 5, "poison", "3x damage and burns for 4 turns.", power=3.0, turns=4)},
    "binding_array": {"path": "formation", **tech("Binding Array", "缚灵阵", 0, 4, "stun", "0.8x damage and the enemy loses its next turn.", power=0.8)},
    "gathering_array": {"path": "formation", **tech("Gathering Array", "聚灵阵", 0, 5, "heal", "The array pulls in qi and heals 25% of your health.", amount=0.25)},
    "mirror_array": {"path": "formation", **tech("Mirror Array", "镜花阵", 1, 4, "evade", "Dodge the next attack completely.")},
    "killing_array": {"path": "formation", **tech("Killing Array", "杀阵", 1, 4, "multi", "Three beams strike for 0.9x damage each.", power=0.9, hits=3)},
    "heavenly_net": {"path": "formation", **tech("Heaven-Earth Net", "天罗地网", 2, 5, "weaken", "1.2x damage and the enemy hits 30% softer for 3 turns.", power=1.2, turns=3, cut=0.3)},
    "star_array": {"path": "formation", **tech("Great Star Array", "周天星斗阵", 3, 6, "damage", "A sky of stars falls for 4.8x damage.", power=4.8)},
}

WAY_TECHNIQUES = {
    "way_thunder_seal": {"way": "immortal", **tech("Heavenly Thunder Seal", "天雷符", 0, 3, "damage", "A talisman calls thunder for 2x damage.", power=2.0)},
    "way_radiance": {"way": "immortal", **tech("Celestial Radiance", "仙光", 1, 5, "heal", "Heavenly light heals 30% of your health.", amount=0.3)},
    "way_suppress": {"way": "immortal", **tech("Dao Law Suppression", "道法镇压", 2, 5, "stun", "1.5x damage and the enemy loses its next turn.", power=1.5)},
    "way_blood_rite": {"way": "demonic", **tech("Blood Sacrifice", "血祭", 0, 4, "lifesteal", "1.6x damage, and you heal half of it.", power=1.6, steal=0.5)},
    "way_soul_devour": {"way": "demonic", **tech("Soul Devouring", "噬魂", 1, 5, "lifesteal", "2.2x damage, and you heal 40% of it.", power=2.2, steal=0.4)},
    "way_heart_demon": {"way": "demonic", **tech("Heart-Demon Rampage", "心魔狂乱", 2, 6, "buff", "Let the demon loose: +60% damage for 3 turns.", mult=1.6, turns=3)},
    "way_yin_wind": {"way": "ghost", **tech("Yin Wind Slash", "阴风刃", 0, 3, "multi", "Two cold blades for 1.1x damage each.", power=1.1, hits=2)},
    "way_netherstep": {"way": "ghost", **tech("Netherworld Step", "幽冥步", 1, 4, "evade", "Slip between worlds and dodge the next attack.")},
    "way_soul_wail": {"way": "ghost", **tech("Soul Rending Wail", "裂魂啸", 2, 5, "weaken", "1.5x damage and the enemy hits 30% softer for 3 turns.", power=1.5, turns=3, cut=0.3)},
    "way_vajra_palm": {"way": "buddhist", **tech("Vajra Palm", "金刚掌", 0, 3, "damage", "A palm of gold for 1.9x damage.", power=1.9)},
    "way_lotus_shield": {"way": "buddhist", **tech("Lotus Shield", "莲华盾", 1, 4, "guard", "A lotus blooms: halve damage taken for 2 turns.", turns=2)},
    "way_wrath_king": {"way": "buddhist", **tech("Wrathful King Roar", "怒目金刚", 2, 5, "stun", "1.6x damage and the enemy loses its next turn.", power=1.6)},
    "way_gu_release": {"way": "gu", **tech("Venom Gu Release", "放蛊", 0, 3, "poison", "1.1x damage and venom burns for 4 turns.", power=1.1, turns=4)},
    "way_blood_gu": {"way": "gu", **tech("Blood-Feeding Gu", "噬血蛊", 1, 4, "lifesteal", "1.5x damage, and the gu heals you for 60% of it.", power=1.5, steal=0.6)},
    "way_gu_swarm": {"way": "gu", **tech("Ten-Thousand Gu Swarm", "万蛊噬心", 2, 5, "poison", "2x damage and venom burns for 4 turns.", power=2.0, turns=4)},
    "way_backstab": {"way": "rogue", **tech("Backstab", "偷袭", 0, 3, "execute", "1.8x damage, and 1.8x more against a weakened foe.", power=1.8, bonus=1.8, below=0.5)},
    "way_smoke": {"way": "rogue", **tech("Smoke Bomb", "烟雾弹", 1, 4, "evade", "Vanish in smoke and dodge the next attack.")},
    "way_gamble": {"way": "rogue", **tech("Gambler's Strike", "孤注一掷", 2, 5, "damage", "Stake everything on one blow for 3.2x damage.", power=3.2)},
}

RACE_TECHNIQUES = {
    "race_human": {"race": "human", **tech("Willpower Surge", "意志爆发", 0, 5, "buff", "Human will: +25% damage for 3 turns.", mult=1.25, turns=3)},
    "race_demon": {"race": "demon", **tech("True Form Strike", "本相击", 0, 4, "damage", "Your true form strikes for 2.1x damage.", power=2.1)},
    "race_beast": {"race": "beast", **tech("Savage Pounce", "野性扑杀", 0, 5, "stun", "1.6x damage and the enemy loses its next turn.", power=1.6)},
    "race_spirit": {"race": "spirit", **tech("Elemental Bloom", "灵元绽放", 0, 5, "heal", "The elements answer and heal 30% of your health.", amount=0.3)},
    "race_witch": {"race": "witch", **tech("Pangu Blood Totem", "盘古血图腾", 0, 5, "lifesteal", "1.4x damage, and the totem heals you for half of it.", power=1.4, steal=0.5)},
    "race_witchhuman": {"race": "witchhuman", **tech("Twin-Blood Rush", "双血突", 0, 4, "multi", "Two rushes for 1.2x damage each.", power=1.2, hits=2)},
    "race_ghost": {"race": "ghost", **tech("Phantom Veil", "幻影帷", 0, 5, "evade", "You turn to mist and dodge the next attack.")},
    "race_immortal": {"race": "immortal", **tech("Fallen Immortal's Radiance", "仙陨光", 0, 5, "execute", "2x damage, and 1.8x more against a weakened foe.", power=2.0, bonus=1.8, below=0.4)},
    "race_demonic": {"race": "demonic", **tech("Primordial Chaos Claw", "混沌爪", 0, 4, "damage", "Chaos tears for 2.4x damage.", power=2.4)},
}


SECT_TECHNIQUES = {
    "sect_shield": {"name": "Sect Guardian Shield", "zh": "护宗诀", "sect": 1, "cd": 4, "kind": "guard", "turns": 2,
                    "info": "Sect technique: halve damage taken for 2 turns."},
    "sect_formation": {"name": "Clan Blade Formation", "zh": "合击阵", "sect": 2, "cd": 3, "kind": "damage", "power": 2.0,
                       "info": "Sect technique: the clan's blades strike together for 2x damage."},
    "sect_chant": {"name": "Spirit Mending Chant", "zh": "愈灵咒", "sect": 3, "cd": 5, "kind": "heal", "amount": 0.30,
                   "info": "Sect technique: heal 30% of your health."},
    "sect_seal": {"name": "Heaven-Shaking Seal", "zh": "震天印", "sect": 4, "cd": 5, "kind": "stun", "power": 1.0,
                  "info": "Sect technique: 1x damage and the enemy loses its next turn."},
    "sect_wrath": {"name": "Ancestral Wrath", "zh": "先祖之怒", "sect": 5, "cd": 5, "kind": "damage", "power": 3.5,
                   "info": "Sect technique: the ancestors strike for 3.5x damage."},
}


def sect_unlocked(level: int) -> dict:
    return {key: item for key, item in SECT_TECHNIQUES.items() if item["sect"] <= level}


def unlocked(path: str, realm: int) -> dict:
    return {key: item for key, item in TECHNIQUES.items() if item["path"] == path and item["realm"] <= realm}


def way_unlocked(way: str, realm: int) -> dict:
    return {key: item for key, item in WAY_TECHNIQUES.items() if item["way"] == way and item["realm"] <= realm}


def race_unlocked(race: str, realm: int) -> dict:
    return {key: item for key, item in RACE_TECHNIQUES.items() if item["race"] == race and item["realm"] <= realm}


def known(character: dict, sect: int = 0) -> dict:
    realm = character["realm"]
    return {**unlocked(character["path"], realm), **way_unlocked(character.get("way") or "", realm), **race_unlocked(character.get("race") or "", realm), **sect_unlocked(sect)}
