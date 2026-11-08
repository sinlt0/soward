MONSTERS = {
    "mountain_rat": {"realm": 0, "name": "Mountain Rat Demon", "zh": "山鼠妖", "hp": 0.8, "atk": 0.8, "def": 0.6, "skill": "Gnawing Frenzy"},
    "boar_spirit": {"realm": 0, "name": "Wild Boar Spirit", "zh": "野猪精", "hp": 1.2, "atk": 0.9, "def": 1.0, "skill": "Mountain Charge"},
    "grey_wolf": {"realm": 0, "name": "Grey Wolf Demon", "zh": "灰狼妖", "hp": 1.0, "atk": 1.1, "def": 0.8, "skill": "Moonlit Bite"},
    "ghost_fire": {"realm": 0, "name": "Wandering Ghost Fire", "zh": "鬼火", "hp": 0.7, "atk": 1.2, "def": 0.5, "skill": "Soul Scorch"},
    "stone_golem": {"realm": 1, "name": "Stone Golem", "zh": "石魔", "hp": 1.4, "atk": 0.9, "def": 1.3, "skill": "Boulder Slam"},
    "ironback_bear": {"realm": 1, "name": "Iron-Back Bear", "zh": "铁背熊", "hp": 1.3, "atk": 1.0, "def": 1.1, "skill": "Rending Claws"},
    "blood_bats": {"realm": 1, "name": "Blood Bat Swarm", "zh": "血蝠群", "hp": 0.8, "atk": 1.2, "def": 0.6, "skill": "Blood Drain"},
    "corpse_cultivator": {"realm": 1, "name": "Corpse Cultivator", "zh": "尸修", "hp": 1.1, "atk": 1.1, "def": 0.9, "skill": "Corpse Qi Burst"},
    "thunder_roc": {"realm": 2, "name": "Thunder Roc", "zh": "雷鹏", "hp": 0.9, "atk": 1.3, "def": 0.7, "skill": "Thunder Dive"},
    "black_water_serpent": {"realm": 2, "name": "Black Water Serpent", "zh": "玄水蛇", "hp": 1.2, "atk": 1.0, "def": 1.0, "skill": "Venom Tide"},
    "jade_skeleton": {"realm": 2, "name": "Jade Skeleton Fiend", "zh": "玉骨魔", "hp": 1.3, "atk": 1.0, "def": 1.3, "skill": "Bone Spear"},
    "crimson_fox": {"realm": 2, "name": "Crimson Fox Demon", "zh": "赤狐妖", "hp": 1.0, "atk": 1.2, "def": 0.8, "skill": "Illusion Fire"},
    "chaos_shade": {"realm": 3, "name": "Chaos Shade", "zh": "混沌魔影", "hp": 1.0, "atk": 1.3, "def": 0.8, "skill": "Void Rend"},
    "taotie": {"realm": 3, "name": "Taotie", "zh": "饕餮", "hp": 1.5, "atk": 1.1, "def": 1.1, "skill": "Devouring Maw"},
    "xiangliu": {"realm": 3, "name": "Xiangliu", "zh": "相柳", "hp": 1.2, "atk": 1.2, "def": 1.0, "skill": "Nine-Headed Venom"},
    "demon_god_remnant": {"realm": 3, "name": "Chaos Demon God's Remnant", "zh": "混沌魔神残魂", "hp": 1.4, "atk": 1.3, "def": 1.2, "skill": "Primordial Roar"},
}


BOSSES = {
    "cave_serpent_king": {"realm": 0, "name": "Qingxu Cave Serpent King", "zh": "青虚洞蛇王", "hp": 2.0, "atk": 1.1, "def": 1.0, "skill": "Coiling Crush"},
    "corpse_king": {"realm": 1, "name": "Corpse King of the Lower Valley", "zh": "下谷尸王", "hp": 2.0, "atk": 1.2, "def": 1.1, "skill": "Corpse Qi Storm"},
    "thunder_dragon": {"realm": 2, "name": "Nine Heavens Thunder Dragon", "zh": "九霄雷龙", "hp": 2.0, "atk": 1.3, "def": 1.1, "skill": "Dragon Lightning"},
    "chaos_avatar": {"realm": 3, "name": "Avatar of a Chaos Demon God", "zh": "混沌魔神化身", "hp": 2.2, "atk": 1.4, "def": 1.2, "skill": "Primordial Annihilation"},
}


CLAN_BOSSES = (
    {"key": "bloodmoon_wolf", "name": "Bloodmoon Wolf King", "zh": "血月狼王", "skill": "Bloodmoon Howl", "level": 1},
    {"key": "ghost_general", "name": "Ghost General of the Underworld", "zh": "幽冥鬼将", "skill": "Soul-Rending Blade", "level": 2},
    {"key": "jade_python", "name": "Thousand-Year Jade Python", "zh": "千年玉蟒", "skill": "Coiling Heaven", "level": 3},
    {"key": "nine_tail", "name": "Nine-Tailed Heavenly Fox", "zh": "九尾天狐", "skill": "Nine Tails Illusion", "level": 4},
    {"key": "fire_qilin", "name": "Vermilion Fire Qilin", "zh": "赤焰麒麟", "skill": "Qilin Flame", "level": 5},
    {"key": "chaos_beast", "name": "Beast of the Great Chaos", "zh": "大混沌兽", "skill": "Chaos Devouring", "level": 6},
)


def boss_for(realm: int) -> str:
    tier = min(realm, 3)
    return next(key for key, boss in BOSSES.items() if boss["realm"] == tier)


REMNANTS = (
    "the resentment of a Core Formation elder who fell sealing a breach",
    "the grief of a whole sect that died in one night",
    "the last hatred of a sword cultivator betrayed by a friend",
    "the unfinished vow of an alchemist who never saved her disciple",
    "the dying rage of a clan head who watched his house burn",
    "the lingering fear of a thousand disciples crushed at the Heaven Gate",
    "the bitterness of a pilgrim who walked west and never arrived",
)


def remnant(rng) -> str:
    return rng.choice(REMNANTS)


def for_realm(realm: int) -> list:
    tier = min(realm, 3)
    return [key for key, monster in MONSTERS.items() if monster["realm"] == tier]


for table in (MONSTERS, BOSSES):
    for beast in table.values():
        beast["name"] = "Abyssal " + beast["name"].replace(" Demon", "").replace("Wandering ", "")
        beast["zh"] = "渊·" + beast["zh"]

for beast in CLAN_BOSSES:
    beast["name"] = "Abyssal " + beast["name"]
    beast["zh"] = "渊·" + beast["zh"]
