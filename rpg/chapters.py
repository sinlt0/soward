ACTS = {
    1: ("Act I", "The Refuge", "青虚"),
    2: ("Act II", "The Hundred Steps", "百阶"),
    3: ("Act III", "The Chaos Tide", "混沌潮"),
    4: ("Act IV", "The Heaven Gate", "天门"),
}

GOAL_LABELS = {
    "meditate": "Meditate",
    "win": "Win fights",
    "explore": "Explore the wilds",
    "talk": "Talk to travelers or friends",
    "event": "Resolve crossroads events",
    "rift": "Enter a rift",
    "spar": "Spar with a traveler",
    "craft": "Craft a piece of gear",
    "refine": "Refine gear successfully",
    "brew": "Brew a pill",
}


def chapter(key, act, realm, title, zh, npc, scene, goals, reward, outro, boss=None, choice=None, echo=()):
    return {"key": key, "act": act, "realm": realm, "title": title, "zh": zh, "npc": npc, "scene": scene, "goals": goals,
            "reward": reward, "outro": outro, "boss": boss, "choice": choice, "echo": echo}


CHAPTERS = (
    chapter(
        "last_broom", 1, 0, "The Last Broom", "最后的扫帚", "Keeper Mu Qinghe",
        "Rain hammers the broken roof of the Qingxu Refuge. Keeper Mu hands you a broom with a nick in the handle that looks suspiciously like a sword-guard.\n\n"
        "*\"Qingxu once taught ten thousand disciples,\"* she says. *\"Now it has a leaking roof, a hungry cave and you. Gather qi. Learn to fight. "
        "The Chaos Tide is coming, and a sect of one is still a sect.\"*",
        (("meditate", 3), ("win", 2)),
        {"coins": 1200, "items": {"qi_pill": 2, "relic_mu_blade": 1}},
        "Mu takes the broom and presses her old blade into your hands instead. *\"Sweep with it. It is the only way I know to make a blade humble.\"*",
    ),
    chapter(
        "debt_of_pills", 1, 0, "A Debt of Pills", "欠丹", "Granny Yao",
        "Granny Yao's stall at the mountain gate is half empty. She taps a jar with nothing in it. *\"The soil is forgetting how to grow. "
        "Even the Shattering left herbs behind, and now those are gone too.\"*\n\n"
        "She needs someone to walk the wilds and find where the last herbs still grow, and she needs to talk to someone who is not a customer.",
        (("explore", 4), ("talk", 1)),
        {"coins": 1000, "items": {"qi_pill": 3}},
        "Yao counts her jars twice, then a third time. *\"Do not tell anyone I was worried.\"*",
        choice={"flag": "herbs", "prompt": "You found her last field of herbs. Yao names a price.", "options": (
            ("pay", "Pay her full price", "Yao stares at the spirit stones, then at you. *\"Fool. A generous fool.\"* She presses two Healing Pills into your hand anyway.", {"items": {"healing_pill": 2}}),
            ("haggle", "Haggle her down", "Yao laughs until she coughs. *\"Finally, a customer worth cheating.\"* You keep a few spirit stones from the deal.", {"coins": 400}),
        )},
    ),
    chapter(
        "cave_beneath", 1, 0, "The Cave Beneath", "洞下", "Keeper Mu Qinghe",
        "The spring beneath the Refuge has gone dry. Mu leads you down the broken stairs to the old water cave and stops at the last torch.\n\n"
        "*\"Something is drinking the mountain's qi. Something big.\"* A coil as wide as a well scrapes across the stone in the dark. "
        "*\"The Qingxu Cave Serpent King. My master kept it asleep for forty years. I did not know how.\"*",
        (("win", 3),),
        {"coins": 1800},
        "The cave breathes out. Water, thin and cold, begins to run again over the stones.",
        boss="cave_serpent_king",
        choice={"flag": "serpent", "prompt": "The Serpent King lies broken, still alive, its great eye on you.", "options": (
            ("seal", "Seal the cave and let it sleep", "You trace Mu's old sealing marks across the entrance. The serpent shuts its eye. Mu's shoulders loosen for the first time in years.", {"items": {"rift_shard": 2}}),
            ("scale", "Take its scales", "The scales come away heavy and green, still warm. Mu looks away, but she does not stop you.", {"items": {"relic_scale_robe": 1}}),
        )},
    ),
    chapter(
        "foundation_day", 1, 0, "Foundation Day", "筑基", "Keeper Mu Qinghe",
        "Qi stirs in you like a tide held behind a dam. Mu sweeps the courtyard one last time, then stops.\n\n"
        "*\"A foundation is a promise,\"* she says. *\"Make it properly. If you break it, the Refuge breaks with you.\"*",
        (("meditate", 2), ("realm", 1)),
        {"coins": 3000, "items": {"tribulation_pill": 1}},
        "The dam breaks and holds. For the first time in years, the Refuge bell rings, and nobody rang it.",
    ),
    chapter(
        "hundred_steps", 2, 1, "The Hundred Steps", "百阶", "Madam Zhu Yunniang",
        "The Hundred Steps Auction House is the loudest place in Canhuang that still pretends the world is whole. Madam Zhu smiles at you from her balcony like someone who has already priced you.\n\n"
        "Below, Shen Wuyou of Tianji Pavilion pushes through the crowd, points at you and announces to the entire room that you are his rival.",
        (("win", 3), ("explore", 4)),
        {"coins": 4000},
        "Zhu writes your name in a small black ledger. *\"Interesting. Not a threat yet. Merely interesting.\"*",
        choice={"flag": "rival", "prompt": "Shen Wuyou stands before you, furious, with the whole auction watching.", "options": (
            ("befriend", "Offer him your hand", "Shen stares at your hand as if it were a trick. Then he takes it, very stiffly. *\"This changes nothing,\"* he says, and gives you a purse of spirit stones to prove it.", {"coins": 600}),
            ("humble", "Beat him in front of the crowd", "You humble him, and the room cheers. Shen walks out without a word, but a Spirit Iron falls from his sleeve as he goes.", {"items": {"spirit_iron": 3}}),
        )},
    ),
    chapter(
        "nameless_daoist", 2, 1, "The Nameless Daoist", "无名", "Daoist Wuming",
        "On the misty ridge above the Refuge, an old man waits who was not there yesterday. He will not give his name. *\"Wuming,\"* he says. *\"Nameless. It saves paperwork.\"*\n\n"
        "He pours two cups of nothing and slides one toward you. *\"Everyone who climbs this ridge is cultivating for something. Tell me yours.\"*",
        (("talk", 2), ("event", 2)),
        {"coins": 3500, "items": {"relic_wuming_jade": 1}},
        "Wuming presses a blank jade into your palm. *\"For when you forget what you were answering.\"* When you look up, the ridge is empty.",
        choice={"flag": "answer", "prompt": "Wuming waits. The mist waits with him. What do you cultivate for?", "options": (
            ("strength", "Strength", "*\"Honest,\"* Wuming says. *\"Dangerous. But honest.\"* He tosses you a Demon Core as if it were a pebble.", {"items": {"beast_core": 3}}),
            ("people", "The people behind me", "Wuming is quiet for a long moment. *\"Then keep them breathing.\"* He leaves you two Healing Pills.", {"items": {"healing_pill": 2}}),
            ("truth", "To see what lies beyond the Gate", "Wuming's cup stops halfway to his mouth. *\"Careful. The Gate sees back.\"* He gives you two Rift Shards without explanation.", {"items": {"rift_shard": 2}}),
        )},
    ),
    chapter(
        "corpse_king", 2, 1, "The Corpse King", "尸王", "Keeper Mu Qinghe",
        "The valley bells ring at noon, which they should not. Farmers come up the mountain pale and silent: the dead of the Lower Valley have stood up from their graves, and something wearing a king's crown walks at their head.\n\n"
        "*\"The Corpse King,\"* Mu says. *\"A cultivator who refused to stay dead. He is not evil. He is merely very, very hungry.\"*",
        (("win", 4), ("explore", 3)),
        {"coins": 5000, "items": {"relic_corpse_banner": 1}},
        "The dead lie down again, gently, as if someone had told them a bedtime story. The black banner trembles in the dust at your feet.",
        boss="corpse_king",
    ),
    chapter(
        "core_of_the_matter", 2, 1, "Core of the Matter", "结丹", "Keeper Mu Qinghe",
        "Mu hands you a cup of tea so bitter it makes your eyes water. *\"Core Formation,\"* she says. *\"You compress everything you are into a single point. If you are not sure what you are, do not try it.\"*\n\n"
        "She watches you across the steam. *\"Are you sure?\"*",
        (("meditate", 2), ("realm", 2)),
        {"coins": 8000, "items": {"tribulation_pill": 2}},
        "The core spins inside you, small and bright and entirely yours. Far above the mountain, thunder pauses to look.",
    ),
    chapter(
        "chaos_tide", 3, 2, "The Chaos Tide", "混沌潮", "Keeper Mu Qinghe",
        "It arrives at dusk: a line of grey on the horizon, then a wall, then a sound. The Chaos Tide eats the lower valley whole and leaves nothing behind but silence. Villagers pour up the mountain toward the Refuge gates.\n\n"
        "*\"I told you it was coming,\"* Mu says, quite calmly, and lifts her blade for the first time in your presence.",
        (("win", 5), ("explore", 4)),
        {"coins": 10000},
        "By dawn the tide has drawn back, leaving a coastline of broken stone and a Refuge that is no longer empty.",
        choice={"flag": "tide", "prompt": "The tide is still rising. The villagers cannot all fit through the gate in time.", "options": (
            ("evacuate", "Lead the villagers out through the cave", "You take the long way, through the old water cave. Every one of them lives. The spirit stones pressed into your hands come from gratitude, not payment.", {"coins": 2000}),
            ("hold", "Hold the line at the gate", "You hold the gate until the tide breaks. The villagers hand up everything they carry: pills, mostly, and a great deal of tea.", {"items": {"qi_pill": 4}}),
        )},
        echo=(("serpent", "seal", "In the cave below, the sealed serpent stirs once, and the tide turns aside around it."), ("serpent", "scale", "You wear the serpent's scales as the tide crests, and the grey seems to slide off them.")),
    ),
    chapter(
        "thunder_over_qingxu", 3, 2, "Thunder Over Qingxu", "雷降青虚", "Keeper Mu Qinghe",
        "The Chaos Tide has opened a door in the sky above the Refuge, and something with the shape of a dragon and the temper of a storm is coming through it.\n\n"
        "Mu squints upward. *\"The Nine Heavens Thunder Dragon. It has been looking for somewhere to land since the Shattering. I would very much prefer it did not choose my roof.\"*",
        (("win", 3), ("event", 2)),
        {"coins": 12000, "items": {"relic_dragon_horn": 1}},
        "The dragon spirals back into the broken sky. One great horn remains in the courtyard, humming like a held note.",
        boss="thunder_dragon",
    ),
    chapter(
        "grannys_cauldron", 3, 2, "Granny Yao's Cauldron", "药鼎", "Granny Yao",
        "Daoist Wuming has come down from the ridge, which is the first sign something is wrong. He wants Granny Yao's old cauldron. Yao has been keeping it under a blanket for sixty years and has told no one why.\n\n"
        "*\"It is not for brewing,\"* she mutters when you ask. *\"It is for holding something down.\"*",
        (("talk", 2), ("explore", 3)),
        {"coins": 6000},
        "Whatever lay under that cauldron lid is quiet now. Yao pours you tea from it, to prove it is only a pot.",
        choice={"flag": "cauldron", "prompt": "Wuming and Yao both stare at you. The cauldron sits between them.", "options": (
            ("give", "Carry the cauldron to Wuming", "Wuming takes it with both hands, like a sleeping child. Yao says nothing, then tosses you her old pill gourd. *\"It will outlast me.\"*", {"items": {"relic_yao_gourd": 1}}),
            ("keep", "Tell Wuming it is not for sale", "Wuming bows, to your surprise. *\"Then it was meant to stay. Good.\"* Yao charges you for the tea anyway, and then pays you for the answer.", {"coins": 5000}),
        )},
        echo=(("tide", "evacuate", "Some of the evacuated villagers have set up stalls at the gate. Yao glares at the competition."), ("tide", "hold", "The gate still smells of smoke. Yao has sold the villagers half her stock, at cost, and will deny it.")),
    ),
    chapter(
        "nascent_dawn", 3, 2, "Nascent Dawn", "元婴", "Keeper Mu Qinghe",
        "Mu will not look you in the eye. *\"Nascent Soul. You split yourself in two and the second half survives. I tried once.\"* She taps her chest. *\"It did not survive.\"*\n\n"
        "*\"Do it anyway. Someone should.\"*",
        (("meditate", 2), ("realm", 3)),
        {"coins": 20000, "items": {"healing_pill": 3}},
        "A second self sits cross-legged in the courtyard, smiling. The Refuge bell rings again, and this time you hear who rings it: all of them.",
    ),
    chapter(
        "gate_remembers", 4, 3, "What the Gate Remembers", "门忆", "Keeper Mu Qinghe",
        "On the night of the new moon Mu finally tells you the thing she has kept for forty years. She was there when the Heaven Gate cracked. She was one of the disciples sent to hold it shut.\n\n"
        "*\"Ten thousand of us went up the steps. I walked down alone.\"* She looks at your second self, then at you. *\"The Gate remembers all of them. It wants more.\"*",
        (("explore", 5), ("win", 4)),
        {"coins": 15000, "items": {"rift_shard": 3}},
        "Mu sleeps for the first time in what you suspect is decades. Outside, something enormous pauses on the far side of the sky.",
        echo=(("answer", "strength", "Wuming's first question rings in your head: *what do you cultivate for?* You said strength. The Gate may remember that too."), ("answer", "people", "Wuming's first question rings in your head: *what do you cultivate for?* You said the people behind you. They are all behind you now."), ("answer", "truth", "Wuming's first question rings in your head: *what do you cultivate for?* You said truth. Mu has just handed you some.")),
    ),
    chapter(
        "hollow_throne", 4, 3, "The Hollow Throne", "空座", "Shen Wuyou",
        "Shen Wuyou comes back to the Refuge alone. His robes are torn and his eyes are the wrong shade of gold. *\"The Gate called me,\"* he says. *\"There is a throne behind it. It is empty. It has been empty since Pangu.\"*\n\n"
        "He laughs once, helplessly. *\"It wants me to sit in it.\"*",
        (("win", 5),),
        {"coins": 10000},
        "The gold fades from Shen's eyes, slowly. Whether he thanks you or hates you, he does it quietly.",
        choice={"flag": "shen", "prompt": "Shen is shaking. The gold is spreading up his throat. You have a moment to decide.", "options": (
            ("forgive", "Hear him out and bind his wounds", "You sit with him through the night. By dawn the gold has receded to a single line at his collar. *\"I owe you,\"* Shen says. *\"I hate that.\"*", {"items": {"healing_pill": 3}}),
            ("strike", "End it before the Gate takes him", "You do what has to be done, quickly and without a speech. Whatever the Gate wanted from him, it cannot have now. You find his purse beside the body.", {"coins": 10000}),
        )},
        echo=(("rival", "befriend", "He still wears the glove you shook hands on. It is a very expensive glove."), ("rival", "humble", "You can see him still resenting that auction. It is the only part of him that is still entirely himself.")),
    ),
    chapter(
        "avatar_of_chaos", 4, 3, "The Chaos Avatar", "混沌化身", "Keeper Mu Qinghe",
        "The sky above the Refuge splits like a seam and a figure steps out of it, shaped like a god and dressed in the wreckage of three thousand more. It is a fragment of a Chaos Demon God that Pangu never finished killing.\n\n"
        "*\"I cannot hold it,\"* Mu says, quietly. *\"You can. That was always the point of you.\"*",
        (("win", 4), ("meditate", 2)),
        {"coins": 30000, "items": {"relic_chaos_carapace": 1}},
        "The Avatar falls apart into grey light, and the light folds itself into a carapace at your feet, still warm and faintly humming.",
        boss="chaos_avatar",
    ),
    chapter(
        "dao_remains", 4, 3, "The Dao Remains", "道存", "Keeper Mu Qinghe",
        "The Heaven Gate stands open at the top of the sky, and for the first time you can see what is behind it. A throne. A world. Pangu's shadow, folded small. Everything the Shattering broke, waiting to be put right or put out.\n\n"
        "Mu stands beside you at the edge of the Refuge. *\"Whatever you choose,\"* she says, *\"Qingxu will be here. A sect of one is still a sect.\"*",
        (("win", 3), ("event", 1)),
        {"coins": 50000, "items": {"relic_pangu_rib": 1, "chaos_shard": 5}},
        "The first act of the Dao is over. Beyond the Gate lies Soul Transformation, and every road after it, still unwalked.\n\n**To be continued.**",
        choice={"flag": "ending", "prompt": "The Gate waits for your answer.", "options": (
            ("seal", "Seal the Heaven Gate", "You close the Gate. The sky knits shut behind you, and Canhuang is safe, small and sealed forever.", {}),
            ("open", "Open the Heaven Gate", "You open it. The light that pours down is older than the world. What comes after is anyone's guess.", {}),
            ("own", "Walk your own Dao", "You turn your back on the Gate and the throne. Behind you the sky holds. Ahead of you the world is just a road.", {}),
        )},
        echo=(("shen", "forgive", "Shen stands at your shoulder, gold line gleaming at his collar, and does not say a word."), ("shen", "strike", "Shen's empty place at your shoulder is the loudest thing on the mountain."), ("serpent", "seal", "Far below, the Serpent King sleeps on, and the spring runs sweet.")),
    ),
)

TOTAL = len(CHAPTERS)
INDEX = {item["key"]: number for number, item in enumerate(CHAPTERS)}
