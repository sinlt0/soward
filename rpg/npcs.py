NPCS = {
    "elder_mu": {
        "name": "Keeper Mu Qinghe", "title": "Keeper of the Qingxu Refuge", "place": "the Refuge", "realm": 0,
        "about": "A stern, tired elder who rebuilt the Qingxu Refuge on the broken mountain.",
        "favor": {"type": "qi", "hours": 2, "text": "Elder Mu corrects your breathing and you gather qi faster."},
        "lines": (
            (0, "Sweep first, dream later. Every great cultivator started with a broom."),
            (0, "Your root is only a seed. Water it every day or it will rot."),
            (0, "Qingxu once taught thousands. Now it has me, a broom and you."),
            (1, "A foundation is a promise. Do not make it and then break it."),
            (2, "The Chaos Tide will reach the Refuge. When it does, I want you standing."),
            (3, "I have felt the Heaven Gate only once, long ago. I did not like how it felt back."),
        ),
    },
    "granny_yao": {
        "name": "Granny Yao", "title": "Pill Seller", "place": "the pill stall at the mountain gate", "realm": 0,
        "about": "A sharp-eyed old woman who sells pills and never gives credit.",
        "favor": {"type": "coins", "range": (15, 35), "item": "qi_pill", "item_chance": 0.12, "text": "Granny Yao presses a little something into your hand."},
        "lines": (
            (0, "Pills are cheap. Regret is expensive. Buy the pill."),
            (0, "I brewed for clan elders before you were born. I will still be brewing after you retire."),
            (0, "Do not haggle. I have never lost a haggle."),
            (1, "A Healing Pill for the injured, a Heaven-Defying Pill for the brave and a Qi Pill for everyone else."),
            (2, "Each year the herbs grow thinner. Even the soil remembers the Shattering."),
            (3, "Tell Daoist Wuming I want my cauldron back. He knows the one."),
        ),
    },
    "tie_gu": {
        "name": "Tie Gu", "title": "Wandering Smith", "place": "the forge below the steps", "realm": 0,
        "about": "A huge, quiet smith who says he forged blades for the old clans.",
        "favor": {"type": "coins", "range": (15, 35), "text": "Tie Gu pays you for hauling charcoal."},
        "lines": (
            (0, "Iron remembers every hit. So do people."),
            (0, "Come back when you have something worth forging."),
            (1, "A good blade is mostly patience. The rest is hitting it."),
            (2, "The anvils of the old halls still ring in the ruins at night. I do not go up there."),
            (3, "Someday you will bring me a core worth a real weapon."),
        ),
    },
    "madam_zhu": {
        "name": "Madam Zhu Yunniang", "title": "Matron of the Hundred Steps Auction House", "place": "the Hundred Steps Auction House", "realm": 1,
        "about": "A smiling matron who runs the auctions and knows the price of everything.",
        "favor": {"type": "coins", "range": (25, 55), "text": "Madam Zhu tips you for a rumor worth hearing."},
        "lines": (
            (1, "Every lot has a story. The best ones are even true."),
            (1, "I buy relics, sell secrets and forget names. It keeps me alive."),
            (2, "Strange relics are reaching my vault. Chaos-touched, they say. They sell quickly."),
            (3, "Clans and families send bidders now. The auction is the only place everyone sits in the same room."),
        ),
    },
    "shen_wu": {
        "name": "Shen Wuyou", "title": "Rival Disciple", "place": "the training grounds", "realm": 0,
        "about": "A proud disciple from a famous Tianji Pavilion family who has decided you are his rival.",
        "favor": {"type": "qi", "hours": 1.5, "text": "Shen Wu's taunts push you to train harder."},
        "lines": (
            (0, "You will never catch me. Try anyway, I enjoy it."),
            (1, "A foundation already? Fine. I was holding back."),
            (2, "Do not think a core makes you my equal. It makes you my problem."),
            (3, "Nascent Soul. Fine. You win this round. Do not get comfortable."),
        ),
    },
    "hermit": {
        "name": "Daoist Wuming", "title": "The Nameless Daoist", "place": "the misty ridge", "realm": 1,
        "about": "A wandering daoist who appears only to those with a foundation. Wuming means 'nameless', and he will not say more.",
        "favor": {"type": "bonus", "amount": 5, "text": "Daoist Wuming murmurs a few words that steady your heart before a tribulation."},
        "lines": (
            (1, "The Dao did not die. It broke. There is a difference."),
            (1, "Ask me again when you can climb the ridge without the stairs."),
            (2, "Pangu thought he had slain all three thousand. Count again. That is the dangerous part."),
            (3, "The Heaven Gate is not locked from outside. Think about that."),
        ),
    },
}
