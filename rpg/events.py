EVENTS = (
    {"id": "scrolls", "npc": "elder_mu", "realm": 0, "title": "Old scrolls",
     "text": "Elder Mu hands you a heavy stack of old scrolls and points up the Hundred Steps.",
     "choices": (
         {"label": "Carry them all at once", "outcomes": (
             {"w": 60, "text": "Your arms burn, but your body tempers. Qi settles in your limbs.", "qi_hours": 1.5},
             {"w": 40, "text": "The stack scatters down the steps and you spend the afternoon gathering it."})},
         {"label": "Make two trips", "outcomes": ({"w": 100, "text": "Elder Mu nods and pays you a few coins.", "coins": (10, 25)},)},
         {"label": "Refuse politely", "outcomes": ({"w": 100, "text": "Elder Mu sighs and carries them himself."},)},
     )},
    {"id": "pouch", "npc": "granny_yao", "realm": 0, "title": "A lost pouch",
     "text": "A pill pouch lies in the road with Granny Yao's mark stitched on it.",
     "choices": (
         {"label": "Return it to her", "outcomes": (
             {"w": 85, "text": "Granny Yao grunts and rewards you.", "coins": (20, 40)},
             {"w": 15, "text": "Granny Yao stares at you, then hands over a pill.", "item": "qi_pill"})},
         {"label": "Keep it", "outcomes": (
             {"w": 50, "text": "Nobody saw you. The pouch holds a few coins.", "coins": (40, 90)},
             {"w": 50, "text": "Granny Yao always knows. She collects a steep 'tax' from you.", "lose": (30, 60)})},
     )},
    {"id": "race", "npc": "shen_wu", "realm": 0, "title": "The race",
     "text": "Shen Wu blocks your way and challenges you to a race up the Hundred Steps.",
     "choices": (
         {"label": "Race him", "outcomes": (
             {"w": 50, "text": "You edge past him at the last step and your lungs fill with qi.", "qi_hours": 2},
             {"w": 50, "text": "He wins and makes you pay for the privilege of losing.", "lose": (10, 30)})},
         {"label": "Decline", "outcomes": ({"w": 100, "text": "Shen Wu scoffs and walks away."},)},
     )},
    {"id": "scrap", "npc": "tie_gu", "realm": 0, "title": "Scrap iron",
     "text": "Tie Gu offers a sack of scrap iron for 50 coins and swears there is ore in it.",
     "choices": (
         {"label": "Buy it (50 coins)", "cost": 50, "outcomes": (
             {"w": 55, "text": "There really is ore in it. You sell it back to him for more.", "coins": (90, 160)},
             {"w": 45, "text": "It is just rust. Tie Gu shrugs."})},
         {"label": "Walk away", "outcomes": ({"w": 100, "text": "Tie Gu puts the sack away without a word."},)},
     )},
    {"id": "charcoal", "npc": "tie_gu", "realm": 1, "title": "Charcoal run",
     "text": "Tie Gu will repair your robes if you haul charcoal from the lower valley.",
     "choices": (
         {"label": "Haul it", "outcomes": (
             {"w": 100, "text": "The work is heavy but honest. He pays you and your robes look new.", "coins": (20, 45)},)},
         {"label": "Skip it", "outcomes": ({"w": 100, "text": "Your robes stay patched."},)},
     )},
    {"id": "lot", "npc": "madam_zhu", "realm": 1, "title": "A private lot",
     "text": "Madam Zhu lets you bid on a sealed lot before the public auction opens.",
     "choices": (
         {"label": "Bid 150 coins", "cost": 150, "outcomes": (
             {"w": 30, "text": "The lot was a relic. She buys it back at a premium.", "coins": (180, 260)},
             {"w": 30, "text": "The lot was a sealed pill. You keep it.", "item": "qi_pill"},
             {"w": 40, "text": "The lot was a fake. Madam Zhu smiles sympathetically."})},
         {"label": "Watch quietly", "outcomes": ({"w": 100, "text": "You watch how the bidders move and learn a little patience.", "qi_hours": 1},)},
     )},
    {"id": "riddle", "npc": "hermit", "realm": 1, "title": "A riddle",
     "text": "Daoist Wuming asks: \"What shatters the moment you say its name?\"",
     "choices": (
         {"label": "Silence", "outcomes": ({"w": 100, "text": "Daoist Wuming smiles. 'Good.' Your heart feels steadier about tribulations.", "bonus": 5},)},
         {"label": "A promise", "outcomes": ({"w": 100, "text": "Daoist Wuming shakes his head slowly. 'Close.'"},)},
         {"label": "The Dao", "outcomes": ({"w": 100, "text": "Daoist Wuming laughs for a long while. His laughter tastes of qi.", "qi_hours": 0.5},)},
     )},
    {"id": "patrol", "npc": "elder_mu", "realm": 1, "title": "Gate patrol",
     "text": "Elder Mu hears chaos whispers in the mist and asks for a volunteer to walk the gate.",
     "choices": (
         {"label": "Volunteer", "outcomes": (
             {"w": 70, "text": "You find only mist and a stray pelt. Elder Mu pays you.", "coins": (30, 60)},
             {"w": 30, "text": "Something formless moves in the fog. You run, losing coins from your purse.", "lose": (20, 40)})},
         {"label": "Report it and stay put", "outcomes": ({"w": 100, "text": "Elder Mu notes it down and gives you a few coins for the report.", "coins": (5, 15)},)},
     )},
    {"id": "spar", "npc": "shen_wu", "realm": 2, "title": "Sparring bet",
     "text": "Shen Wu challenges you to a sparring match with 60 coins on it.",
     "choices": (
         {"label": "Accept (60 coins)", "cost": 60, "outcomes": (
             {"w": 55, "text": "You win the exchange and he pays double.", "coins": (120, 120)},
             {"w": 45, "text": "He wins and gloats."})},
         {"label": "Decline", "outcomes": ({"w": 100, "text": "Shen Wu calls you a coward, then leaves."},)},
     )},
    {"id": "herb", "npc": "granny_yao", "realm": 2, "title": "A rare herb",
     "text": "A rare spirit herb has appeared at Granny Yao's stall for 400 coins.",
     "choices": (
         {"label": "Buy it (400 coins)", "cost": 400, "outcomes": (
             {"w": 100, "text": "You grind it and drink. Qi floods your meridians.", "qi_hours": 5},)},
         {"label": "Not today", "outcomes": ({"w": 100, "text": "Granny Yao puts it back in the jar."},)},
     )},
    {"id": "gate", "npc": "hermit", "realm": 3, "title": "The Heaven Gate",
     "text": "Daoist Wuming finally speaks of the Heaven Gate, sealed above the clouds.",
     "choices": (
         {"label": "Listen", "outcomes": ({"w": 100, "text": "He tells you the Heaven Gate was sealed from the inside. You do not sleep well, but your qi stirs.", "qi_hours": 2},)},
         {"label": "Question him", "outcomes": (
             {"w": 30, "text": "He gives you a Heaven-Defying Pill and says nothing more.", "item": "tribulation_pill"},
             {"w": 70, "text": "He answers with another riddle and your qi shifts a little.", "qi_hours": 0.5})},
     )},
)
