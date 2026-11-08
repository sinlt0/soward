WAYS = {
    "immortal": {
        "name": "Immortal Cultivator", "zh": "仙修",
        "about": "The orthodox way of sects and heavenly law. Steady, righteous and favored by the Dao.",
        "perk": "Heaven-favored: +6% tribulation chance and injuries heal 20% faster.",
        "flaw": "Orthodox restraint: -5% qi speed.",
        "qi": 0.95, "chance": 6, "injury": 0.8, "fight": {"def": 1.05},
    },
    "demonic": {
        "name": "Demonic Cultivator", "zh": "魔修",
        "about": "The evil way that takes power by blood and forbidden arts, whatever the cost.",
        "perk": "Forbidden arts: +20% qi speed.",
        "flaw": "Heart-demons: -6% tribulation chance and injuries last 25% longer.",
        "qi": 1.20, "chance": -6, "injury": 1.25, "fight": {"atk": 1.12},
    },
    "ghost": {
        "name": "Ghost Cultivator", "zh": "鬼修",
        "about": "Cultivators of yin energy who walk between the living world and the Underworld.",
        "perk": "Yin energy: +10% idle qi and +4 hours of stored qi.",
        "flaw": "Living medicine sits poorly with yin: pills are 15% weaker.",
        "idle": 1.10, "offline": 4, "pills": 0.85, "fight": {"dodge": 4},
    },
    "buddhist": {
        "name": "Buddhist Cultivator", "zh": "佛修",
        "about": "Monks who temper the heart with compassion and the golden body of the Dharma.",
        "perk": "Steady heart: +4% tribulation chance and injuries heal twice as fast.",
        "flaw": "Detachment: -8% qi speed.",
        "qi": 0.92, "chance": 4, "injury": 0.5, "fight": {"hp": 1.12, "def": 1.10},
    },
    "gu": {
        "name": "Gu Cultivator", "zh": "蛊修",
        "about": "Southern cultivators who raise venomous gu worms that feed on their qi and feed it back.",
        "perk": "Gu worms: +15% idle qi.",
        "flaw": "Gu backlash: -3% tribulation chance.",
        "idle": 1.15, "chance": -3,
    },
    "rogue": {
        "name": "Rogue Cultivator", "zh": "散修",
        "about": "Free cultivators bound to no sect, scraping for every resource on their own.",
        "perk": "Self-made: +20% qi from meditation and pills cost 10% less.",
        "flaw": "No sect to store your qi: -3 hours of stored qi.",
        "meditate": 1.20, "price": 0.90, "offline": -3,
    },
}
