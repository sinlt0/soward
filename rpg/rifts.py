import random

PREFIXES = (
    ("Withered", "枯"), ("Crimson", "赤"), ("Frozen", "寒"), ("Sunken", "沉"), ("Hollow", "空"), ("Thunder-Scarred", "雷"),
    ("Verdant", "青"), ("Ashen", "灰"), ("Moonlit", "月"), ("Silent", "寂"), ("Golden", "金"), ("Bone", "骨"),
)
NOUNS = (
    ("Lotus", "莲"), ("Dragon", "龙"), ("Sword", "剑"), ("Mulberry", "桑"), ("Crane", "鹤"), ("Tomb", "冢"), ("Sea", "海"),
    ("Mountain", "山"), ("Banner", "旗"), ("Lantern", "灯"), ("Pagoda", "塔"), ("Bridge", "桥"),
)
ABOUT = (
    "A world whose sun died long ago, lit only by the glow of old spells.",
    "A world of endless ruins where every hall still has its door open.",
    "A world drowned in mist, where the beasts move like thoughts.",
    "A world whose mountains are the bones of something that did not finish dying.",
    "A world of burnt libraries, and the ghosts who still read in them.",
    "A world where the sky is a cracked mirror and shows other worlds.",
)
ROOMS = {
    "beast": 40, "treasure": 20, "traveler": 12, "trap": 15, "spring": 8,
}
ROOM_COUNT = 5
EXPIRY_HOURS = 24
DAILY = 2
SHARDS_TO_OPEN = 3

TREASURE_TEXT = (
    "A lacquered chest sits in the middle of a collapsed hall, still sealed.",
    "A jade casket rests on a toppled altar. Something in it hums.",
    "A forgotten cache of a long-dead clan lies beneath a cracked banner.",
)
TRAP_TEXT = (
    "The corridor splits in two. One path is lit by a faint blue glow, the other is dark and silent.",
    "Two bridges cross a black gap. One of them is real.",
    "A hall has two doors. A whisper tells you the left one is safe. A second whisper says the right one.",
)
SPRING_TEXT = (
    "A spring of pale light rises through the cracked floor.",
    "A lone lantern burns in the dark, and the air around it is warm.",
)


def world(rng=None) -> tuple[str, str, str]:
    rng = rng or random
    prefix, noun = rng.choice(PREFIXES), rng.choice(NOUNS)
    return f"{prefix[0]} {noun[0]} World", f"{prefix[1]}{noun[1]}界", rng.choice(ABOUT)


def rooms(rng=None) -> list[str]:
    rng = rng or random
    found = rng.choices(list(ROOMS), weights=list(ROOMS.values()), k=ROOM_COUNT)
    if "beast" not in found:
        found[0] = "beast"
    return found + ["guardian"]
