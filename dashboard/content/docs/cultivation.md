---
title: Cultivation
description: Awaken a spiritual root, gather qi, take pills and break through realms in the cultivation RPG.
order: 56
group: Fun
---

## Getting started

`!cultivate awaken` rolls your **spiritual root**. You can reroll it once, then you choose a **path** you cannot change later. After that, qi gathers on its own while you are away, and you speed it up with commands.

`!cultivate` shows your progress, and `!world guide` shows your personal guide and what to do next.

## Races

Your race is rolled together with your root when you awaken, and rerolled with it. Each race has a strength and a flaw. Some close paths: a witch can only walk the Body path.

| Race | Chance | Strength | Flaw |
| --- | --- | --- | --- |
| Human (人族) | 35% | +5% tribulation chance | None |
| Demon (妖族) | 12% | +10% qi speed | -5% tribulation chance |
| Beastkin (兽族) | 12% | +15% idle qi, injuries heal 25% faster | Body and Sword paths only |
| Spirit (灵族) | 10% | +15% qi speed, +3 hours of stored qi | Pills are 20% weaker |
| Witch (巫族) | 10% | +25% idle qi, +5% tribulation chance | Body path only, pills are 30% weaker |
| Witch-Human (巫人) | 10% | +5% qi speed, +15% meditation | Body and Sword paths only |
| Ghost (鬼族) | 6% | +10% qi speed, +6 hours of stored qi | Meditation is 20% weaker, no Body path |
| Immortal (仙族) | 3% | +25% qi speed, +8% tribulation chance | Pills cost 25% more |
| Demonic (魔族) | 2% | +30% qi speed, injuries heal twice as fast | -8% tribulation chance |

`!cultivate races` shows them in the bot. Players who awakened before races existed count as human.

## Ways (cultivator types)

Your way is the kind of cultivator you are. You choose it once when you awaken, before your path, and it stacks with your race and path. Players who awakened earlier can pick theirs with `!cultivate way <name>`.

| Way | Strength | Flaw |
| --- | --- | --- |
| Immortal Cultivator (仙修) | +6% tribulation chance, injuries heal 20% faster | -5% qi speed |
| Demonic Cultivator (魔修) | +20% qi speed | -6% tribulation chance, injuries last 25% longer |
| Ghost Cultivator (鬼修) | +10% idle qi, +4 hours of stored qi | Pills are 15% weaker |
| Buddhist Cultivator (佛修) | +4% tribulation chance, injuries heal twice as fast | -8% qi speed |
| Gu Cultivator (蛊修) | +15% idle qi | -3% tribulation chance |
| Rogue Cultivator (散修) | +20% meditation qi, pills cost 10% less | -3 hours of stored qi |

`!cultivate ways` lists them in the bot.

## Spiritual roots

| Rarity | Chance | Roots | Qi speed |
| --- | --- | --- | --- |
| Common | 85% | Fire, Water, Wood, Metal, Earth | x1.0 |
| Rare | 12% | Lightning, Ice, Wind | x1.15 |
| Legendary | 3% | Heavenly, Chaos | x1.4 |

Your root also has a quality: Mortal (x0.85), Spirit (x1.0), Earth (x1.2) or Heaven (x1.5). Rarity times quality sets how fast you gather qi.

## Paths

| Path | Perk |
| --- | --- |
| Sword (Wanjian Pavilion) | +10% qi from meditation |
| Body (Xuanwu Hall) | +10% idle qi |
| Alchemy (Danding Valley) | Pills are 15% stronger and 10% cheaper |
| Formation (Tianji Pavilion) | +5% breakthrough chance and 2 more hours of stored qi |

## Gathering qi

- **Idle qi:** qi builds in the background and is stored for up to 12 hours. It stops when your qi is full.
- `!cultivate meditate` gives a burst of qi every 4 hours.
- `!cultivate use qi_pill` gives qi at once, up to 3 pills a day.

## Breakthroughs

When your qi is full, `!cultivate breakthrough` tries to move you up.

- **Within a realm:** 85% chance. A failure costs some qi and a short pause.
- **To the next realm (tribulation):** 55% chance and a coin fee. Heaven-Defying Pills add up to +30%. A failure costs qi and leaves you injured for 12 hours, and the fee is lost. You never fall back a realm.

A Healing Pill cures injuries.

## Realms

| Realm | Stages | Qi per hour |
| --- | --- | --- |
| Qi Condensation | 9 layers | 20 |
| Foundation Establishment | 4 | 60 |
| Core Formation | 4 | 180 |
| Nascent Soul | 4 | 540 |

More realms will open later. `!cultivate realms` shows the list.

## Pills

| Pill | What it does |
| --- | --- |
| Qi Gathering Pill | Qi worth 8 hours of idle gain |
| Heaven-Defying Pill | +15% on your next tribulation, up to +30% |
| Healing Pill | Cures an injury |

Pills cost coins, and the price of most pills rises with your realm. `!cultivate shop`, `!cultivate buy <pill> [amount]`, `!cultivate use <pill>` and `!cultivate bag` manage them.

## Combat

`!cultivate fight` starts a turn-based fight against a monster of your realm. You get 8 fights a day, and you cannot fight while injured. Each turn you press a button:

- **Attack:** a free qi palm.
- **Defend:** halve the next hit.
- **Technique:** pick one from the menu. Techniques come from your path, way, race and clan, and recharge after a few turns.
- **Flee:** a 60% chance to get away with no penalty.

Winning pays coins, a little qi, crafting materials and a rare gear drop. Losing costs 3% of your stage's qi. You are never injured and never lose a realm. Fights end in a draw after 30 turns.

Techniques come from four places, and everything you qualify for shows in the menu:

| Source | Techniques |
| --- | --- |
| Path | Six each. Sword has Flying Sword Strike, Twin Sword Dance, Sword Intent, Ten Thousand Swords, Heart-Piercing Sword and Heaven-Cleaving Sword. Body, Alchemy and Formation each have six of their own. |
| Way | Three each, unlocked at Qi Condensation, Foundation Establishment and Core Formation. For example the Demonic way has Blood Sacrifice, Soul Devouring and Heart-Demon Rampage. |
| Race | One each, from the start. Humans have Willpower Surge, Witches have the Pangu Blood Totem, Ghosts have Phantom Veil, and so on. |
| Clan | The Scripture Pavilion techniques. |

Techniques do different things: plain damage, multi-hit strikes, buffs that raise your damage for a few turns, life-stealing hits, execute strikes that hit harder against a weakened foe, poison, stuns, weakening hits that make the enemy hit softer, guards, dodges and heals. `!cultivate techniques` lists all of them and when the locked ones open up.

Your path, race and way also change your combat stats. Some weapons and relics add a critical chance, which makes a hit deal 50% more, or extra technique power. `!cultivate techniques` lists your techniques and `!cultivate bestiary` shows the monsters you can meet.

## Gear

Monsters drop materials for their realm: Demon Core, Spirit Iron, Thunder Crystal and Chaos Shard. Five of them plus coins craft a weapon, armor or charm in the matching grade: Yellow (黄), Mystic (玄), Earth (地) and Heaven (天). You can only craft and wear grades up to your realm.

| Slot | Boost | Yellow to Heaven |
| --- | --- | --- |
| Weapon | Attack | +10%, +20%, +32%, +45% for the Flying Blade |
| Spirit Robe | Health and defense | +10%, +20%, +32%, +45% |
| Jade Charm | Dodge chance | +3, +5, +7, +9 |

### Weapon types

The weapon slot has eight types. Each one trades a little raw attack for a perk, and every type comes in all four grades.

| Weapon | Perk |
| --- | --- |
| Flying Blade (飞剑) | Balanced attack |
| Dragon Spear (龙枪) | +8% critical chance |
| Demon Saber (魔刀) | +12% critical chance |
| Twin Daggers (双匕) | +10% critical chance and +3% dodge |
| Sky Bow (天弓) | +4% dodge and +5% critical chance |
| Spirit Staff (灵杖) | +18% technique power |
| Wind Fan (风扇) | +10% technique power and +3% dodge |
| Mountain Hammer (山锤) | Heavy attack, -2% dodge |

`!cultivate gear` shows what you wear and what you can craft. `!cultivate gear craft <weapon type|armor|charm> [grade]` forges an item, for example `!cultivate gear craft spear mystic`, and `!cultivate gear equip <name>` wears it, for example `earth dragon spear` or `yellow armor`.

### Relics

Relics are named pieces of gear you earn from the main story, such as the Qingxu Sweeping Blade, Serpent King's Scale Robe, Black Corpse Banner and Pangu's Last Rib. Each one is stronger than normal gear of its realm and carries a perk. You equip them by name, and you can refine and enchant them like any other gear.

### Refining

`cultivate gear refine <slot>` upgrades the gear you are wearing, from +1 up to +5. Each step adds 15% to that gear's bonus, so a +5 piece gives 75% more than the same piece at +0.

| Step | Materials | Success chance |
|---|---|---|
| +1 | 1 | 100% |
| +2 | 2 | 90% |
| +3 | 3 | 75% |
| +4 | 4 | 60% |
| +5 | 5 | 45% |

Materials are the kind your gear's grade uses, and each step also costs coins (a fifth of the grade's crafting price per step number). A failed attempt loses the materials and coins but never lowers the level. Swapping to a different piece resets the level, so refine the gear you plan to keep.

### Enchanting

`cultivate gear enchant <slot> <enchant>` adds one rune to the gear you are wearing. Each enchant costs 2 Rift Shards, which come from rifts, plus coins that grow with your realm.

| Enchant | Fits | Effect |
|---|---|---|
| Sharpness | Weapon | +10% attack |
| Swiftness | Weapon, charm | +4% dodge |
| Fortitude | Armor | +12% defense |
| Vitality | Armor | +12% health |
| Prosperity | Charm | +10% coins from `cultivate fight` wins |

A slot holds one enchant and a new one replaces it. Swapping the gear itself removes its enchant and refinement.

## Raids and the safe

`!cultivate raid <user>` lets you rob another cultivator's pouch in a turn-based fight against their stats. Both sides are protected by rules:

- Cultivators still in their first realm, or in their first 7 days, are protected, and cannot raid either.
- You can only raid someone within 2 realms of you.
- You get 5 raids a day, one per target every 6 hours. A target can be robbed 3 times a day, and they must carry at least 200 coins.
- Partners, family and clan members cannot raid each other.
- Winning takes 8% of their pouch, up to 3,000 coins. Only the pouch can be robbed: coins in the safe, diamonds and the clan bank are immune.
- The loser loses a little qi (3% of the stage). A raider who loses also loses 5% of their pouch, up to 1,500 coins, which are burned and not paid to the defender. Each side has a small chance to lose one item from the bag. Nobody ever loses a realm or their character.

`!cultivate safe` shows your safe, and `!cultivate safe deposit <amount>` or `withdraw <amount>` moves coins. The safe holds 2,000 coins and triples with every realm. `!cultivate raid` with no user shows the rules and whether you are protected.

## Family and lineage

`!lineage` shows your cultivating family. It works with the marriage and adoption system.

**Dual cultivation:** `!lineage dual [partner]` lets married partners cultivate together. Your partner has to accept. Both gain 2.5 hours of qi (a 25% bonus on 2 hours), and each couple can do it every 8 hours.

**Bloodline:** when an adopted child awakens or rerolls, they have a 35% chance to inherit their parent's spiritual root if it is rarer than the one they rolled, and a 25% chance to take on their parent's race. Their status shows what they inherited.

**Family treasury:** `!lineage treasury` is a shared coffer that cannot be raided. Your partners, children, parent and siblings can add coins, and only you can withdraw. It holds 10,000 coins plus 5,000 for each relative, up to 100,000. Use `!lineage treasury deposit <amount> [owner]` and `withdraw <amount>`.

**Inheritance:** `!lineage heir <user>` names a partner, child, parent or sibling as your heir. If you are gone for 60 days, they can claim the treasury with `!lineage inherit <you>`.

**Family dungeon:** `!lineage dungeon` opens a party panel. Your family joins with a button and you press Start with 2 to 4 members. You control the fight, and the party's health and attack combine into one fighter against a dungeon boss that grows with party size. Each member can enter 2 dungeons a day. Everyone who joined gets double coins, extra qi, materials and a better chance at gear. If the party loses, everyone loses a little qi.

## Clans, the great families

In this world a clan is a great family, not just a group. Once you join one, your status shows your standing: the leader is the **Young Master** of the fallen clan, officers are **Elders**, and everyone else is a **Member**. `!clan` handles joining and running it, and `!sect` is its hall: the clan bank pays for buildings, and the Young Master and Elders use `!sect build <building>`. A building can reach level 5, and no higher than the clan's tier. Every member gets the benefit.

| Building | Effect per level | Costs for levels 1 to 5 |
| --- | --- | --- |
| Spirit Gathering Array (聚灵阵) | +2% idle qi | 20,000 / 50,000 / 120,000 / 250,000 / 500,000 |
| Alchemy Pavilion (丹阁) | Pills cost 3% less | same |
| Martial Hall (演武堂) | +3% attack and +2% health in combat | same |
| Scripture Pavilion (藏经阁) | Unlocks a clan technique | same |
| Mountain Guardian Formation (护山大阵) | Raiders steal 10% less from members | same |

**Clan techniques:** each Scripture Pavilion level unlocks a technique that every member can use in any fight, whatever their path: Sect Guardian Shield, Clan Blade Formation, Spirit Mending Chant, Heaven-Shaking Seal and Ancestral Wrath. `!sect techniques` lists them.

**Boss raids:** `!sect boss` shows your clan's boss, an abyssal lord that gets tougher as the clan tier rises. Members strike it with `!sect attack` up to 3 times a day, each a 10-turn fight, and damage adds up across the clan. Higher realms deal more. When it falls, everyone who struck it shares coins, materials and a chance at gear, and the clan bank gets a bonus. A boss flees after 7 days, and a new one appears 48 hours after one is slain.

**Clan wars:** clans of tier 2 or higher can fight. The Young Master or an Elder uses `!sect war declare <clan>` and the other side accepts with `!sect war accept`. For 48 hours, each `!cultivate raid` win against a member of the enemy clan scores points for your clan, more against higher realms. If the winner has at least 5 points, they take 5% of the loser's bank, up to 100,000 coins. Clans cannot fight again for 72 hours.

## The world

`!cultivate lore [world|abyss|clans|rifts]` tells the story: Hundun, the Great Dao and the Chaos Demon Gods, Pangu and Honghuang, the Shattering that split it into lower worlds, middle worlds and the Immortal World, and Canhuang, the world made of its remnants where your story begins. The main story is told in chapters, described below.

## Your journey

`!world` is your personal guide. When you awaken, a guide with a random name and a fallen clan of their own finds you, and `!world guide` shows a checklist of what to do next with their advice. Every player meets different people, so no two journeys look alike.

### The main story

`!world chapter` opens the Qingxu saga, sixteen chapters in four acts. Each chapter opens with a scene and a short list of goals: meditate, win fights, explore, talk to people, resolve events and so on. Everything you already do in the game counts. Some chapters end with a boss fight, and some ask you to make a choice that changes the rewards and echoes through later chapters. When every goal is done, press the button to complete the chapter and take its rewards, which include relics and coins.

Chapters wait for the right realm: Act I is Qi Condensation, Act II is Foundation Establishment, Act III is Core Formation and Act IV is Nascent Soul. A few chapters ask you to break through a realm as their goal. Finishing each act earns a title. `!world chapter log` lists the chapters you have finished and the choices you made.

### Alchemy

`world brew` lists four battle pills you can brew from fight materials:

| Pill | Effect until midnight UTC |
|---|---|
| Vigor Pill | +20% attack |
| Iron Skin Pill | +20% health and defense |
| Windstep Pill | +8% dodge |
| Fortune Pill | +50% coins from `cultivate fight` wins |

Brewing one costs 3 of the material for your realm's grade (the same ones used for crafting gear) and some coins that grow with your realm. Alchemy cultivators brew two pills at a time and pay less. Use `world brew <pill>` to brew and `world brew drink <pill>` to take one. A pill of the same kind cannot be taken again while it is still working.

### Titles

`world titles` lists twelve titles you earn by playing, such as Foundation Builder, Spirit Smith, Rune Weaver, Roadwalker, Clan Pillar and Rift Walker. They unlock when you check the list or your `cultivate status`. Wear one with `world titles set <name>` and it shows next to your realm on your status. `world titles clear` removes it. Titles are cosmetic.

### Daily bounties

`world bounty` shows three bounties that change every day, such as taking on fights, exploring, sparring or entering a rift. Finish them, then run the command again to claim. Each bounty pays coins and a little qi, which grow with your realm. Claiming all three also opens a chest with extra coins and crafting materials.

### Raid log

`world raids` lists your last raids and the raids against you from the past two weeks, with the coins and items that moved.

## Exploring the wilds

`!world explore` sends you into the wilds. You can explore 12 times a day, with a few minutes between trips. Each trip can bring:

- **An abyssal beast** (渊兽): a monster formed from the resentment of a cultivator who died in the great calamities. You fight it turn by turn. It pays less than a normal fight.
- **An abyssal lord**: a rare, stronger beast that pays well and can drop gear and Rift Shards.
- **A traveler:** a person with a randomly generated Chinese name and a backstory. Alchemists, hermit swordsmen, fallen clan survivors, rift scouts, ghost merchants and rivals all behave differently.
- **A cache** to open boldly or carefully, a **crossroads** with a choice, or a **rift**.

**People:** `!world people` lists everyone you have met, up to 12. `!world talk <name>` speaks with them once a day and builds friendship. At 25 they become friends and give a gift, at 50 they share a secret and qi, and at 100 they become a **Dao companion** who makes your qi 1% faster, up to 5 companions. Each kind has a button action: alchemists sell pills at 70%, swordsmen share guidance, survivors tell stories, scouts find rifts, merchants buy your crafting materials and rivals will spar.

## Rifts

A rift is a tear to a randomly generated lower world, such as the Withered Lotus World (枯莲界). `!world rift` shows yours and lets you enter. It closes after 24 hours, and you can enter 2 a day. Inside are 5 rooms (beasts, caches, traps, springs and travelers) and a guardian. You decide how to handle each room, and you can retreat with your loot between rooms. Clearing a rift pays coins, materials, qi, a chance at gear and Rift Shards. If you are beaten you keep only half your coins. Three Rift Shards open a new rift with `!world rift open`.

## Wild spawns

A server admin with Manage Server permission can use `!world spawn on` in a channel. While people chat there, abyssal beasts and lords occasionally appear. The first cultivator to press the button takes a beast. A lord can be struck by anyone, twice each, and everyone who hurt it shares the rewards when it falls.

## Old Qingxu Refuge

`!cultivate npcs` lists the fixed residents of the Qingxu Refuge, and `!cultivate talk <name>` lets you speak with them. Each gives a small favor once a day, and they appear as you reach higher realms.

## Events

`!cultivate event` sends you wandering into a situation with a few choices. Some choices are safe, some cost coins and pay off with luck, and some give qi, pills or tribulation luck. You can face 3 a day.

## All commands

`!world` (`guide`, `chapter`, `explore`, `people`, `talk`, `rift`, `spawn`), `!cultivate`, `awaken`, `status [user]`, `meditate`, `breakthrough`, `shop`, `buy`, `use`, `bag`, `realms`, `roots`, `paths`, `lore`, `races`, `ways`, `way`, `npcs`, `talk`, `event`, `fight`, `raid`, `safe`, `techniques`, `bestiary`, `gear`, `top`. Everything is also available as `/cultivate` slash commands.
