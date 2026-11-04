import time
from typing import Optional

import config
from utils import clans, db, family, supporters, votes

THEMES = {
    "graphite": {"label": "Graphite", "price": 0, "bg": ((30, 31, 34), (50, 52, 56)), "accent": (190, 192, 200), "pattern": "none"},
    "slate": {"label": "Slate", "price": 0, "bg": ((36, 42, 52), (58, 68, 82)), "accent": (150, 180, 215), "pattern": "dots"},
    "midnight": {"label": "Midnight", "price": 4000, "bg": ((14, 16, 38), (40, 34, 86)), "accent": (150, 130, 255), "pattern": "stars"},
    "ocean": {"label": "Ocean", "price": 5000, "bg": ((8, 40, 70), (20, 110, 140)), "accent": (110, 220, 235), "pattern": "waves"},
    "forest": {"label": "Forest", "price": 5000, "bg": ((14, 44, 30), (46, 96, 62)), "accent": (150, 225, 140), "pattern": "dots"},
    "sakura": {"label": "Sakura", "price": 6000, "bg": ((72, 34, 56), (150, 84, 116)), "accent": (255, 190, 215), "pattern": "petals"},
    "sunset": {"label": "Sunset", "price": 7000, "bg": ((86, 28, 60), (214, 106, 70)), "accent": (255, 214, 140), "pattern": "waves"},
    "neon": {"label": "Neon", "price": 9000, "bg": ((10, 8, 28), (30, 10, 62)), "accent": (60, 255, 200), "pattern": "grid"},
    "aurora": {"label": "Aurora", "price": 12000, "bg": ((8, 26, 44), (60, 40, 110)), "accent": (130, 255, 200), "pattern": "stars"},
    "gold": {"label": "Royal Gold", "price": 15000, "bg": ((44, 32, 10), (120, 88, 24)), "accent": (255, 220, 120), "pattern": "grid"},
}

SPECIES = {
    "kitten": {"label": "Kitten", "price": 0, "body": (240, 170, 100), "belly": (255, 232, 205), "accent": (255, 150, 160)},
    "puppy": {"label": "Puppy", "price": 0, "body": (222, 184, 135), "belly": (250, 236, 214), "accent": (150, 100, 70)},
    "chick": {"label": "Chick", "price": 0, "body": (255, 224, 90), "belly": (255, 240, 160), "accent": (255, 150, 50)},
    "fox": {"label": "Fox", "price": 15000, "body": (238, 124, 52), "belly": (255, 244, 232), "accent": (60, 40, 36)},
    "panda": {"label": "Panda", "price": 20000, "body": (250, 250, 250), "belly": (255, 255, 255), "accent": (40, 40, 44)},
    "penguin": {"label": "Penguin", "price": 20000, "body": (54, 62, 84), "belly": (246, 248, 252), "accent": (255, 168, 50)},
    "dragon": {"label": "Dragon", "price": 50000, "body": (130, 100, 220), "belly": (216, 200, 255), "accent": (110, 220, 150)},
}
FREE_SPECIES = [key for key, item in SPECIES.items() if item["price"] == 0]

OUTFITS = {
    "bandana": {"label": "Bandana", "price": 0},
    "bow": {"label": "Bow", "price": 2000},
    "scarf": {"label": "Scarf", "price": 3000},
    "glasses": {"label": "Glasses", "price": 4000},
    "partyhat": {"label": "Party Hat", "price": 4000},
    "headphones": {"label": "Headphones", "price": 6000},
    "cape": {"label": "Cape", "price": 8000},
    "wizard": {"label": "Wizard Hat", "price": 9000},
    "crown": {"label": "Crown", "price": 12000},
}

STAGES = [(0, "Baby"), (150, "Young"), (600, "Teen"), (1800, "Adult"), (5000, "Legendary")]

BADGE_STYLES = {
    "supporter": ("Supporter", (255, 200, 60)),
    "voter": ("Voter", (110, 190, 255)),
    "devoted": ("Devoted Voter", (150, 130, 255)),
    "married": ("Married", (255, 130, 170)),
    "parent": ("Parent", (120, 220, 160)),
    "clan": ("Clan", (255, 150, 90)),
}


def stage_index(xp: int) -> int:
    index = 0
    for number, (need, _) in enumerate(STAGES):
        if xp >= need:
            index = number
    return index


def stage_name(xp: int) -> str:
    return STAGES[stage_index(xp)][1]


def stage_progress(xp: int) -> tuple[int, int, Optional[int]]:
    index = stage_index(xp)
    floor = STAGES[index][0]
    if index + 1 >= len(STAGES):
        return xp - floor, 0, None
    ceiling = STAGES[index + 1][0]
    return xp - floor, ceiling - floor, ceiling


async def get(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT theme, title FROM user_cosmetics WHERE user_id=?", (user_id,))
    return {"theme": row["theme"], "title": row["title"]} if row else {"theme": "graphite", "title": ""}


async def _save(user_id: int, theme: str, title: str) -> None:
    await db.raw_execute(
        "INSERT INTO user_cosmetics (user_id, theme, title) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme, title=excluded.title",
        (user_id, theme, title))


async def set_theme(user_id: int, theme: str) -> None:
    current = await get(user_id)
    await _save(user_id, theme, current["title"])


async def set_title(user_id: int, title: str) -> None:
    current = await get(user_id)
    await _save(user_id, current["theme"], title[:24])


async def owns(user_id: int, item_id: str, price: int = 1) -> bool:
    if price == 0:
        return True
    row = await db.raw_fetchone("SELECT 1 FROM user_items WHERE user_id=? AND item_id=?", (user_id, item_id))
    return row is not None


async def grant(user_id: int, item_id: str) -> None:
    await db.raw_execute("INSERT OR IGNORE INTO user_items (user_id, item_id, acquired_at) VALUES (?, ?, ?)", (user_id, item_id, time.time()))


async def owned_ids(user_id: int) -> set[str]:
    rows = await db.raw_fetch("SELECT item_id FROM user_items WHERE user_id=?", (user_id,))
    return {r["item_id"] for r in rows}


async def badges(user_id: int) -> list[str]:
    found = []
    if await supporters.get(user_id):
        found.append("supporter")
    vote = await votes.get(user_id)
    if vote:
        if vote["total"] >= config.DEDICATED_VOTER_TOTAL:
            found.append("devoted")
        if time.time() - vote["last_vote_at"] <= config.VOTER_BADGE_HOURS * 3600:
            found.append("voter")
    if await family.partners(user_id):
        found.append("married")
    if await family.children_of(user_id):
        found.append("parent")
    if await clans.membership(user_id):
        found.append("clan")
    return found
