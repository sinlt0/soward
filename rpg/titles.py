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
    "vault": {"name": "Vault Keeper", "zh": "守库", "about": "Keep 50,000 coins in your safe.", "need": lambda f: f["safe"] >= 50000},
    "riftwalker": {"name": "Rift Walker", "zh": "裂行者", "about": "Open a rift into a lower world.", "need": lambda f: f["rifts"] >= 1},
    "heir": {"name": "Refuge Heir", "zh": "青虚传人", "about": "Finish Act I of the main story.", "need": lambda f: f["chapters"] >= 4},
    "stepwalker": {"name": "Hundred Steps Walker", "zh": "百阶行者", "about": "Finish Act II of the main story.", "need": lambda f: f["chapters"] >= 8},
    "tidebreaker": {"name": "Tide Breaker", "zh": "破潮者", "about": "Finish Act III of the main story.", "need": lambda f: f["chapters"] >= 12},
    "daobearer": {"name": "Dao Bearer", "zh": "载道者", "about": "Finish the main story.", "need": lambda f: f["chapters"] >= 16},
    "companion": {"name": "Dao Companion", "zh": "道侣", "about": "Have a partner to cultivate with.", "need": lambda f: f["partnered"]},
}


def find(text: str):
    text = text.strip().lower()
    for key, info in TITLES.items():
        if text in (key, info["name"].lower()):
            return key
    return None
