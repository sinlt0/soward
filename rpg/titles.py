TITLES = {
    "seeker": {"name": "Dao Seeker", "zh": "问道者", "about": "Awaken and walk a path.", "need": lambda f: f["awakened"]},
    "foundation": {"name": "Foundation Builder", "zh": "筑基者", "about": "Reach Foundation Establishment.", "need": lambda f: f["realm"] >= 1},
    "core": {"name": "Core Forger", "zh": "结丹者", "about": "Reach Core Formation.", "need": lambda f: f["realm"] >= 2},
    "nascent": {"name": "Nascent Soul", "zh": "元婴", "about": "Reach Nascent Soul.", "need": lambda f: f["realm"] >= 3},
    "smith": {"name": "Spirit Smith", "zh": "灵匠", "about": "Refine a piece of gear to +5.", "need": lambda f: f["refine"] >= 5},
    "runeweaver": {"name": "Rune Weaver", "zh": "符师", "about": "Wear an enchant on all three gear slots.", "need": lambda f: f["enchants"] >= 3},
    "roadwalker": {"name": "Roadwalker", "zh": "行者", "about": "Meet six travelers in the wilds.", "need": lambda f: f["met"] >= 6},
    "sworn": {"name": "Sworn Friend", "zh": "知己", "about": "Build three bonds.", "need": lambda f: f["bonds"] >= 3},
    "pillar": {"name": "Clan Pillar", "zh": "族柱", "about": "Become an Elder or Young Master of a clan.", "need": lambda f: f["role"] in ("owner", "officer")},
    "vault": {"name": "Vault Keeper", "zh": "守库", "about": "Keep 50,000 spirit stones in your safe.", "need": lambda f: f["safe"] >= 50000},
    "riftwalker": {"name": "Rift Walker", "zh": "裂行者", "about": "Open a rift into a lower world.", "need": lambda f: f["rifts"] >= 1},
    "heir": {"name": "Refuge Heir", "zh": "青虚传人", "about": "Finish Act I of the main story.", "need": lambda f: f["chapters"] >= 4},
    "stepwalker": {"name": "Hundred Steps Walker", "zh": "百阶行者", "about": "Finish Act II of the main story.", "need": lambda f: f["chapters"] >= 8},
    "tidebreaker": {"name": "Tide Breaker", "zh": "破潮者", "about": "Finish Act III of the main story.", "need": lambda f: f["chapters"] >= 12},
    "daobearer": {"name": "Dao Bearer", "zh": "载道者", "about": "Finish the main story.", "need": lambda f: f["chapters"] >= 16},
    "stonebearer": {"name": "Stone Bearer", "zh": "灵石客", "about": "Hold a high-grade spirit stone.", "need": lambda f: f["wealth"] >= 10000},
    "stonelord": {"name": "Stone Lord", "zh": "灵石主", "about": "Hold 100 high-grade spirit stones.", "need": lambda f: f["wealth"] >= 1000000},
    "bagmaster": {"name": "Qiankun Keeper", "zh": "乾坤客", "about": "Upgrade a storage pouch to Qiankun.", "need": lambda f: f["pouch_top"] >= 4},
    "voidkeeper": {"name": "Void Keeper", "zh": "虚空藏", "about": "Upgrade both storage pouches to Void.", "need": lambda f: f["pouch_min"] >= 5},
    "soulblade": {"name": "Soul Blade", "zh": "本命", "about": "Forge your own soul-bound weapon.", "need": lambda f: f["soulbound"] >= 1},
    "armory": {"name": "Hundred Arms", "zh": "百兵", "about": "Own four different soul-bound weapons.", "need": lambda f: f["soulbound"] >= 4},
    "masterwork": {"name": "Masterwork Smith", "zh": "神兵匠", "about": "Own a Flawless weapon.", "need": lambda f: f["flawless"]},
    "transcendent": {"name": "Transcendent", "zh": "超脱者", "about": "Defy the heavens and survive the tribulation of transcendence. It grows each time you transcend again.", "need": lambda f: f["transcend"] >= 1},
    "realmbreaker": {"name": "Realm Breaker", "zh": "破境者", "about": "Clear a secret realm.", "need": lambda f: f["realms"] >= 1},
    "realmlord": {"name": "Realm Sovereign", "zh": "秘境主", "about": "Clear 25 secret realms.", "need": lambda f: f["realms"] >= 25},
    "fivefold": {"name": "Six Elements Walker", "zh": "六行者", "about": "Clear a secret realm of every element.", "need": lambda f: f["realm_elements"] >= 6},
    "calamityslayer": {"name": "Calamity Slayer", "zh": "灾厄斩", "about": "Defeat 10 bosses from the calamity board.", "need": lambda f: f["calamities"] >= 10},
    "companion": {"name": "Dao Companion", "zh": "道侣", "about": "Have a partner to cultivate with.", "need": lambda f: f["partnered"]},
}


def find(text: str):
    text = text.strip().lower()
    for key, info in TITLES.items():
        if text in (key, info["name"].lower()):
            return key
    return None


BONUS = {
    "seeker": {"qi": 1.02},
    "foundation": {"hp": 1.03},
    "core": {"atk": 1.03},
    "nascent": {"atk": 1.02, "hp": 1.02, "def": 1.02},
    "smith": {"atk": 1.04},
    "runeweaver": {"tech": 1.04},
    "roadwalker": {"coins": 1.04},
    "sworn": {"qi": 1.03},
    "pillar": {"hp": 1.03, "def": 1.03},
    "vault": {"coins": 1.03},
    "riftwalker": {"dodge": 2},
    "heir": {"hp": 1.03},
    "stepwalker": {"atk": 1.03},
    "tidebreaker": {"def": 1.04},
    "daobearer": {"atk": 1.03, "hp": 1.03, "def": 1.03},
    "stonebearer": {"coins": 1.03},
    "stonelord": {"coins": 1.06},
    "bagmaster": {"qi": 1.03},
    "voidkeeper": {"qi": 1.05},
    "soulblade": {"crit": 3},
    "armory": {"atk": 1.04},
    "masterwork": {"atk": 1.05},
    "companion": {"qi": 1.04},
    "realmbreaker": {"hp": 1.03},
    "realmlord": {"atk": 1.04, "hp": 1.04},
    "fivefold": {"tech": 1.05},
    "calamityslayer": {"crit": 3, "atk": 1.03},
}
ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")
STAT_LABELS = {"atk": "attack", "hp": "health", "def": "defense", "tech": "technique power", "qi": "qi gain", "coins": "spirit stones from fights", "dodge": "dodge", "crit": "critical chance"}


def bonus(key: str, tier: int = 0) -> dict:
    if key == "transcendent":
        tier = max(1, min(int(tier), len(ROMAN) - 1))
        return {"atk": 1 + 0.02 * tier, "hp": 1 + 0.02 * tier, "def": 1 + 0.02 * tier, "qi": 1 + 0.03 * tier, "coins": 1 + 0.02 * tier, "dodge": tier, "crit": tier}
    return dict(BONUS.get(key, {}))


def label(key: str, tier: int = 0) -> str:
    info = TITLES.get(key)
    if info is None:
        return ""
    if key == "transcendent" and tier > 0:
        return f"{info['name']} {ROMAN[min(tier, len(ROMAN) - 1)]}"
    return info["name"]


def bonus_text(key: str, tier: int = 0) -> str:
    parts = []
    for stat, value in bonus(key, tier).items():
        if stat in ("dodge", "crit"):
            parts.append(f"+{value}% {STAT_LABELS[stat]}")
        else:
            parts.append(f"+{round((value - 1) * 100)}% {STAT_LABELS[stat]}")
    return ", ".join(parts)
