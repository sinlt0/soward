import random

from rpg import names, races

KINDS = {
    "guide": {
        "title": "Your Guide", "zh": "引路人", "action": None,
        "intro": "found you collapsed on the road and decided to teach you how to survive.",
        "lines": (
            "Qi first, courage second. Meditate, then fight, in that order.",
            "Abyssal beasts are old resentment given a shape. Strike them down and the world gets a little lighter.",
            "Do not walk the wilds without pills. I have buried enough travelers.",
            "Join a clan if you can. A cultivator with no family is a cultivator with no one to avenge them.",
            "Rifts open where the world is thinnest. They are dangerous, and they are where the good fortune hides.",
        ),
    },
    "alchemist": {
        "title": "Wandering Alchemist", "zh": "游方丹师", "action": "Buy a discounted pill",
        "intro": "carries a cauldron on their back and sells pills from the roadside.",
        "lines": (
            "The herbs are thin these days, but a good pill is a good pill.",
            "I learned my craft in a clan that no longer exists. The recipes are all that is left.",
            "Never take two pills at once. I say it to everyone, and everyone does it anyway.",
            "Bring me a Demon Core someday and I will show you what a real furnace does.",
        ),
    },
    "swordsman": {
        "title": "Hermit Swordsman", "zh": "隐世剑客", "action": "Ask for guidance",
        "intro": "wanders with a single blade and speaks very little.",
        "lines": (
            "A sword is a question. The answer is how you hold it.",
            "I have fought abyssal beasts that wore the faces of my old masters. Do not hesitate when it happens.",
            "Sit. Breathe. Strike. Everything else is decoration.",
            "My clan taught ten thousand swords. I remember eleven.",
        ),
    },
    "survivor": {
        "title": "Fallen Clan Survivor", "zh": "没落世家子", "action": "Share a meal",
        "intro": "is all that remains of a once proud family.",
        "lines": (
            "There was a banner above our gate once. I still dream of it.",
            "Do not pity me. Pity is the one thing I cannot eat.",
            "Everyone in Canhuang belongs to a fallen house. I just say it out loud.",
            "If you ever found a clan of your own, treat them like blood. I did not, and I regret it.",
        ),
    },
    "scout": {
        "title": "Rift Scout", "zh": "裂隙斥候", "action": "Ask about rifts",
        "intro": "follows the cracks in the world and sells what they find.",
        "lines": (
            "The Shattering never stopped. It just got quiet.",
            "Every rift leads somewhere that used to be a whole world. Remember that when you step through.",
            "I count my steps coming out. Always count your steps.",
            "Lower worlds do not forgive. They also do not forget a kindness.",
        ),
    },
    "merchant": {
        "title": "Ghost Merchant", "zh": "鬼商", "action": "Sell materials",
        "intro": "drifts between the living and the dead, buying whatever the dead leave behind.",
        "lines": (
            "I pay well for things nobody else wants. That is the whole business.",
            "Do not ask where my spirit stones come from. I do not ask where your materials come from.",
            "Everything has a price. Even regret. Especially regret.",
            "Spirit Iron? Thunder Crystal? Lovely. Names fade, but material is forever.",
        ),
    },
    "rival": {
        "title": "Wandering Rival", "zh": "宿敌", "action": "Spar",
        "intro": "has decided you are their rival and will not be talked out of it.",
        "lines": (
            "Last time was luck. This time I brought a plan.",
            "Do not let your guard down. I never do.",
            "One day I will beat you, and then I will have nothing to chase. Strange, how I fear that.",
            "Spar with me. I learn more from losing than from winning, and I hate that.",
        ),
    },
}

WEIGHTS = {"alchemist": 20, "swordsman": 18, "survivor": 20, "scout": 14, "merchant": 14, "rival": 14}

FALLS = (
    "the abyssal tide swallowed its ancestral mountain",
    "a lower-world rift opened beneath its main hall",
    "its patriarch fell trying to seal the Heaven Gate",
    "a rival clan allied with the demons and burned it down in a single night",
    "the old wards failed and the beasts came for the children first",
    "its treasures were sold off one by one until nothing was left to defend",
)
GOALS = (
    "looking for the last relic of the family",
    "chasing a rumor of a surviving sibling",
    "gathering enough strength to reclaim the old estate",
    "trying to forget, and failing",
    "walking until the Dao shows them where to stop",
    "hunting the abyssal beast that wears their father's shape",
)
TITLES = {
    "alchemist": ("an Alchemist", "a Pill Master"),
    "swordsman": ("a Sword Cultivator", "a Wandering Blade"),
    "survivor": ("a Young Master", "a Young Mistress", "a Retainer"),
    "scout": ("a Scout", "a Cartographer"),
    "merchant": ("a Peddler", "a Broker"),
    "rival": ("a Prodigy", "a Challenger"),
    "guide": ("a Senior Disciple", "an Elder Sibling"),
}
MILESTONES = (
    (25, "friend"),
    (50, "confidant"),
    (100, "companion"),
)
SECRETS = (
    "Abyssal beasts remember. Each one carries the last thought of the cultivator it was born from, and that thought is always rage.",
    "The Shattering did not end in one day. Lower worlds are still breaking off, one rift at a time.",
    "Every clan that fell left a hall behind. The halls are still standing in the lower worlds, waiting for someone to enter.",
    "A bonded companion walks beside you in the Dao. It is the only way to cultivate without being alone.",
    "The Heaven Gate was sealed from inside. Ask yourself who wanted that.",
    "Pangu's bones are not the strongest thing in Canhuang. Pangu's regret is.",
    "Some beasts are not made of rage. They are made of grief, and they hesitate before they strike.",
)


def create(rng=None, kind: str = None) -> dict:
    rng = rng or random
    kind = kind or rng.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
    name, zh = names.person(rng)
    clan_name, clan_zh = names.clan(rng)
    race = rng.choices(list(races.RACES), weights=[info["weight"] for info in races.RACES.values()])[0]
    title = rng.choice(TITLES[kind])
    tale = f"{title.capitalize()} of the fallen {clan_name} Clan ({clan_zh}), whose house collapsed when {rng.choice(FALLS)}. They are {rng.choice(GOALS)}."
    if kind == "guide":
        tale = f"{title.capitalize()} of the fallen {clan_name} Clan ({clan_zh}). They {KINDS['guide']['intro']}"
    return {"kind": kind, "name": name, "zh": zh, "race": race, "tale": tale, "clan": clan_name}


def line(kind: str, rng=None) -> str:
    return (rng or random).choice(KINDS[kind]["lines"])


def secret(rng=None) -> str:
    return (rng or random).choice(SECRETS)


def crossed(before: int, after: int) -> list[str]:
    return [label for threshold, label in MILESTONES if before < threshold <= after]
