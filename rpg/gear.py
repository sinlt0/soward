GRADES = (
    {"name": "Yellow", "zh": "黄", "material": "beast_core", "coins": 300},
    {"name": "Mystic", "zh": "玄", "material": "spirit_iron", "coins": 1500},
    {"name": "Earth", "zh": "地", "material": "thunder_crystal", "coins": 6000},
    {"name": "Heaven", "zh": "天", "material": "chaos_shard", "coins": 25000},
)

MATERIALS = {
    "beast_core": {"name": "Demon Core", "zh": "妖丹"},
    "spirit_iron": {"name": "Spirit Iron", "zh": "灵铁"},
    "thunder_crystal": {"name": "Thunder Crystal", "zh": "雷晶"},
    "chaos_shard": {"name": "Chaos Shard", "zh": "混沌碎片"},
    "rift_shard": {"name": "Rift Shard", "zh": "裂隙碎片"},
    "spirit_fiber": {"name": "Spirit Fiber", "zh": "灵纤"},
    "beast_hide": {"name": "Beast Hide", "zh": "兽皮"},
    "realm_key": {"name": "Realm Key", "zh": "秘境钥"},
    "essence_metal": {"name": "Metal Essence", "zh": "金之精"},
    "essence_wood": {"name": "Wood Essence", "zh": "木之精"},
    "essence_water": {"name": "Water Essence", "zh": "水之精"},
    "essence_fire": {"name": "Fire Essence", "zh": "火之精"},
    "essence_earth": {"name": "Earth Essence", "zh": "土之精"},
    "essence_thunder": {"name": "Thunder Essence", "zh": "雷之精"},
}

HERB_NAMES = {
    "vigor_pill": (("ember_root", "Ember Root", "炎根"), ("flame_lotus", "Flame Lotus", "烈焰莲"), ("sunfire_blossom", "Sunfire Blossom", "日炎花"), ("phoenix_bloom", "Phoenix Bloom", "凤凰花")),
    "ironskin_pill": (("stone_moss", "Stone Moss", "石苔"), ("iron_bark_fungus", "Iron Bark Fungus", "铁皮菇"), ("jade_ginseng", "Jade Ginseng", "玉参"), ("diamond_orchid", "Diamond Orchid", "金刚兰")),
    "windstep_pill": (("wind_orchid", "Wind Orchid", "风兰"), ("cloud_fern", "Cloud Fern", "云蕨"), ("storm_lily", "Storm Lily", "暴风莲"), ("sky_lotus", "Sky Lotus", "天云莲")),
    "fortune_pill": (("lucky_clover", "Lucky Clover", "福运草"), ("golden_chrysanthemum", "Golden Chrysanthemum", "金菊"), ("dragon_blood_fruit", "Dragon Blood Fruit", "龙血果"), ("heavenly_peach", "Heavenly Peach", "蟠桃")),
}
HERBS = {key: {"name": name, "zh": zh, "tier": tier, "brew": brew, "herb": True}
         for brew, line in HERB_NAMES.items() for tier, (key, name, zh) in enumerate(line)}
MATERIALS.update(HERBS)
HERB_VALUE = (6, 30, 120, 500)
MATERIAL_VALUE = {"beast_core": 10, "spirit_iron": 50, "thunder_crystal": 200, "chaos_shard": 800, "rift_shard": 400, "spirit_fiber": 15, "beast_hide": 15, "realm_key": 300, "essence_metal": 120, "essence_wood": 120, "essence_water": 120, "essence_fire": 120, "essence_earth": 120, "essence_thunder": 120}
BREW_HERBS = 2


def herb_for(brew: str, tier: int) -> str:
    return HERB_NAMES[brew][min(tier, 3)][0]


def is_herb(key: str) -> bool:
    return key in HERBS


def value(key: str) -> int:
    if key in HERBS:
        return HERB_VALUE[HERBS[key]["tier"]]
    return MATERIAL_VALUE.get(key, 10)


POUCHES = {
    "herb": {"name": "Herb Pouch", "zh": "药袋", "holds": "herbs", "material": "spirit_fiber"},
    "material": {"name": "Material Pouch", "zh": "材料袋", "holds": "ore, cores and other materials", "material": "beast_hide"},
}
POUCH_BASE = 40
POUCH_TIERS = (
    {"name": "Cloth", "zh": "布", "cap": 100, "coins": 2000, "materials": 5, "shards": 0},
    {"name": "Silk", "zh": "丝", "cap": 250, "coins": 10000, "materials": 15, "shards": 0},
    {"name": "Spirit Silk", "zh": "灵丝", "cap": 600, "coins": 50000, "materials": 30, "shards": 5},
    {"name": "Qiankun", "zh": "乾坤", "cap": 1500, "coins": 250000, "materials": 60, "shards": 15},
    {"name": "Void", "zh": "虚空", "cap": 4000, "coins": 1000000, "materials": 100, "shards": 40},
)


def pouch_cap(tier: int) -> int:
    return POUCH_TIERS[tier - 1]["cap"] if tier > 0 else POUCH_BASE


def pouch_name(kind: str, tier: int) -> str:
    return f"{POUCH_TIERS[tier - 1]['name']} {POUCHES[kind]['name']}" if tier > 0 else f"Plain {POUCHES[kind]['name']}"


def pool(key: str) -> str:
    if key in HERBS:
        return "herb"
    return "material" if key in MATERIALS else ""

SLOTS = {
    "weapon": {"name": "Flying Blade", "bonus": (0.10, 0.20, 0.32, 0.45), "info": "attack"},
    "armor": {"name": "Spirit Robe", "bonus": (0.10, 0.20, 0.32, 0.45), "info": "health and defense"},
    "charm": {"name": "Jade Charm", "bonus": (3, 5, 7, 9), "info": "dodge chance"},
}

CRAFT_MATERIALS = 5


WEAPONS = {
    "spear": {"name": "Dragon Spear", "zh": "龙枪", "mult": 0.9, "perk": {"crit": 8}, "info": "attack and +8% critical chance"},
    "saber": {"name": "Demon Saber", "zh": "魔刀", "mult": 0.85, "perk": {"crit": 12}, "info": "attack and +12% critical chance"},
    "daggers": {"name": "Twin Daggers", "zh": "双匕", "mult": 0.8, "perk": {"crit": 10, "dodge": 3}, "info": "attack, +10% critical chance and +3% dodge"},
    "bow": {"name": "Sky Bow", "zh": "天弓", "mult": 0.85, "perk": {"dodge": 4, "crit": 5}, "info": "attack, +4% dodge and +5% critical chance"},
    "staff": {"name": "Spirit Staff", "zh": "灵杖", "mult": 0.8, "perk": {"tech": 1.18}, "info": "attack and +18% technique power"},
    "fan": {"name": "Wind Fan", "zh": "风扇", "mult": 0.8, "perk": {"tech": 1.10, "dodge": 3}, "info": "attack, +10% technique power and +3% dodge"},
    "hammer": {"name": "Mountain Hammer", "zh": "山锤", "mult": 1.15, "perk": {"dodge": -2}, "info": "heavy attack, -2% dodge"},
}

RELICS = {
    "relic_mu_blade": {"slot": "weapon", "grade": 0, "name": "Qingxu Sweeping Blade", "zh": "青虚扫尘剑", "bonus": 0.14, "perk": {"crit": 4}, "info": "Keeper Mu's old blade, worn thin from sweeping the Refuge steps."},
    "relic_scale_robe": {"slot": "armor", "grade": 0, "name": "Serpent King's Scale Robe", "zh": "蛇王鳞衣", "bonus": 0.14, "perk": {"def": 1.05}, "info": "Woven from the scales of the Qingxu cave serpent."},
    "relic_wuming_jade": {"slot": "charm", "grade": 1, "name": "Wuming's Nameless Jade", "zh": "无名玉", "bonus": 6, "perk": {"crit": 4}, "info": "A blank jade the Nameless Daoist pressed into your palm."},
    "relic_corpse_banner": {"slot": "weapon", "grade": 1, "name": "Black Corpse Banner", "zh": "黑尸幡", "bonus": 0.24, "perk": {"tech": 1.10}, "info": "The banner the Corpse King led his dead beneath."},
    "relic_dragon_horn": {"slot": "weapon", "grade": 2, "name": "Thunder Dragon Horn", "zh": "雷龙角", "bonus": 0.36, "perk": {"crit": 8, "tech": 1.08}, "info": "A horn that still hums when storms gather."},
    "relic_yao_gourd": {"slot": "charm", "grade": 2, "name": "Granny Yao's Pill Gourd", "zh": "姚婆药葫芦", "bonus": 8, "perk": {"hp": 1.05}, "info": "The gourd that never ran out of pills, as long as she was paid."},
    "relic_chaos_carapace": {"slot": "armor", "grade": 3, "name": "Chaos Demon God's Carapace", "zh": "混沌神甲", "bonus": 0.50, "perk": {"def": 1.08, "hp": 1.06}, "info": "Armor grown from a fallen Chaos Demon God's shell."},
    "relic_pangu_rib": {"slot": "weapon", "grade": 3, "name": "Pangu's Last Rib", "zh": "盘古遗骨", "bonus": 0.50, "perk": {"crit": 10, "tech": 1.12}, "info": "A splinter of the first giant's bone, awake again."},
}


def key(slot: str, grade: int) -> str:
    return f"{slot}_{grade}"


def parse(item: str):
    relic = RELICS.get(item)
    if relic:
        return relic["slot"], relic["grade"]
    kind, _, grade = item.rpartition("_")
    if grade.isdigit() and int(grade) < len(GRADES):
        if kind in SLOTS:
            return kind, int(grade)
        if kind in WEAPONS:
            return "weapon", int(grade)
    return None


def kind_of(item: str) -> str:
    kind, _, _ = (item or "").rpartition("_")
    return kind if kind in WEAPONS else ""


def soulbound(item: str) -> bool:
    return item in RELICS or bool(kind_of(item))


WEAPON_QUALITIES = (
    {"name": "Crude", "mult": 0.85, "dur": 0.7, "craft": 25, "drop": 40},
    {"name": "Common", "mult": 1.0, "dur": 1.0, "craft": 45, "drop": 40},
    {"name": "Fine", "mult": 1.12, "dur": 1.1, "craft": 20, "drop": 14},
    {"name": "Superb", "mult": 1.25, "dur": 1.25, "craft": 8, "drop": 5},
    {"name": "Flawless", "mult": 1.45, "dur": 1.5, "craft": 2, "drop": 1},
)
DURABILITY = (40, 60, 80, 100)
REPAIR_LOSS = 0.15
REPAIR_MIN = 10
SOULBOUND_DROP_CHANCE = 2
FORGE_MATERIALS = 15
FORGE_SHARDS = 4
FORGE_COIN_MULT = 12
FORGE_CHANCE = (40, 30, 22, 15)
FORGE_REFUND = 50


def roll_quality(rng, source: str = "craft") -> int:
    return rng.choices(range(len(WEAPON_QUALITIES)), [q[source] for q in WEAPON_QUALITIES])[0]


def max_durability(grade: int, quality: int) -> int:
    return max(1, int(DURABILITY[grade] * WEAPON_QUALITIES[quality]["dur"]))


def weapon_bonus(grade: int, quality: int, plus: int = 0) -> float:
    return SLOTS["weapon"]["bonus"][grade] * WEAPON_QUALITIES[quality]["mult"] * (1 + REFINE_STEP * plus)


def weapon_label(info: dict) -> str:
    return f"{WEAPON_QUALITIES[info['quality']]['name']} {GRADES[info['grade']]['name']}-grade Flying Blade ({GRADES[info['grade']]['zh']}阶)"


def weapon_line(info: dict) -> str:
    return f"{weapon_label(info)} · {info['durability']}/{info['max_durability']} durability"


def repair_cost(info: dict) -> dict:
    return {"coins": max(1, GRADES[info["grade"]]["coins"] // 2), "material": GRADES[info["grade"]]["material"], "materials": 1,
            "max": max(REPAIR_MIN, int(info["max_durability"] * (1 - REPAIR_LOSS)))}


def forge_cost(grade: int) -> dict:
    return {"coins": GRADES[grade]["coins"] * FORGE_COIN_MULT, "material": GRADES[grade]["material"], "materials": FORGE_MATERIALS, "shards": FORGE_SHARDS, "chance": FORGE_CHANCE[grade]}


LABELS: dict = {}


def remember(item: str, info: dict) -> None:
    if len(LABELS) > 2000:
        LABELS.clear()
    LABELS[item] = f"{WEAPON_QUALITIES[info['quality']]['name']} {GRADES[info['grade']]['name']}-grade Flying Blade ({GRADES[info['grade']]['zh']}阶) #{item[2:]}"


def name(item: str) -> str:
    if item.startswith("w:"):
        return LABELS.get(item, f"Flying Blade #{item[2:]}")
    relic = RELICS.get(item)
    if relic:
        return f"{relic['name']} ({relic['zh']})"
    parsed = parse(item)
    if not parsed:
        return item
    slot, grade = parsed
    label = WEAPONS[kind_of(item)]["name"] if kind_of(item) else SLOTS[slot]["name"]
    return f"{GRADES[grade]['name']}-grade {label} ({GRADES[grade]['zh']}阶)"


def perk(item: str) -> dict:
    relic = RELICS.get(item)
    if relic:
        return relic["perk"]
    kind = kind_of(item)
    return WEAPONS[kind]["perk"] if kind else {}


def drop(rng, tier: int) -> str:
    slot = rng.choice(list(SLOTS))
    if slot == "weapon" and rng.randint(1, 100) <= SOULBOUND_DROP_CHANCE:
        return key(rng.choice(list(WEAPONS)), tier)
    return key(slot, tier)


REFINE_MAX = 5
REFINE_CHANCE = (100, 90, 75, 60, 45)
REFINE_STEP = 0.15


def refine_cost(grade: int, plus: int) -> dict:
    return {"materials": plus + 1, "coins": GRADES[grade]["coins"] * (plus + 1) // 5, "material": GRADES[grade]["material"], "chance": REFINE_CHANCE[plus]}


def bonus(item: str, plus: int = 0) -> float:
    parsed = parse(item or "")
    if not parsed:
        return 0
    slot, grade = parsed
    relic = RELICS.get(item)
    base = relic["bonus"] if relic else SLOTS[slot]["bonus"][grade] * (WEAPONS[kind_of(item)]["mult"] if kind_of(item) else 1)
    return base * (1 + REFINE_STEP * plus)


def find(text: str):
    text = text.lower().strip().replace("-", " ")
    for relic_key, info in RELICS.items():
        if text in (relic_key, info["name"].lower()):
            return relic_key
    for kind, info in WEAPONS.items():
        for grade, data in enumerate(GRADES):
            if text in (key(kind, grade), f"{data['name']} {kind}".lower(), f"{data['name']} {info['name']}".lower(), f"{data['name']} grade {info['name']}".lower()):
                return key(kind, grade)
    for slot, info in SLOTS.items():
        for grade, data in enumerate(GRADES):
            if text in (key(slot, grade), f"{data['name']} {slot}".lower(), f"{data['name']} {info['name']}".lower(), f"{data['name']} grade {info['name']}".lower()):
                return key(slot, grade)
    return None


ENCHANT_SHARDS = 2
ENCHANT_COINS = 2000
ENCHANTS = {
    "sharpness": {"name": "Sharpness", "zh": "锋", "slots": ("weapon",), "info": "+10% attack", "atk": 1.10},
    "swiftness": {"name": "Swiftness", "zh": "迅", "slots": ("weapon", "charm"), "info": "+4% dodge", "dodge": 4},
    "fortitude": {"name": "Fortitude", "zh": "固", "slots": ("armor",), "info": "+12% defense", "def": 1.12},
    "vitality": {"name": "Vitality", "zh": "命", "slots": ("armor",), "info": "+12% health", "hp": 1.12},
    "prosperity": {"name": "Prosperity", "zh": "财", "slots": ("charm",), "info": "+10% spirit stones from fights", "coins": 1.10},
}


def find_enchant(text: str):
    text = text.strip().lower()
    for key, info in ENCHANTS.items():
        if text in (key, info["name"].lower()):
            return key
    return None
