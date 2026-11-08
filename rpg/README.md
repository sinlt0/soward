# rpg

Everything for the cultivation RPG lives here. The Discord commands are in `cogs/cultivation.py` and only call into this package.

| File | What it holds |
| --- | --- |
| `story.py` | The world story, the abyss, clans and rifts |
| `names.py` | Random Chinese names and fallen clan names |
| `wanderers.py` | The generated travelers and their kinds, dialogue and friendship |
| `rifts.py` | Lower world names and rift room generation |
| `wild.py` | Exploring, the journey, rift runs and wild spawn rewards |
| `races.py` | The races, their rarity, traits, flaws and which paths they can walk |
| `ways.py` | The cultivator types (immortal, demonic, ghost, Buddhist, Gu, rogue) and their traits |
| `npcs.py` | The people of the world: dialogue, locations, unlock realm and daily favors |
| `events.py` | Wander events with choices and weighted outcomes |
| `settings.py` | Roots, paths, realms, pills and every number that balances the game |
| `arts.py` | Combat techniques per path |
| `bestiary.py` | The monsters of each realm |
| `combat.py` | The turn-based fight rules and balance |
| `gear.py` | Gear grades, slots, materials and crafting recipes |
| `engine.py` (lineage section) | Dual cultivation, bloodline, the treasury, inheritance and family dungeons |
| `sect.py` | Sect buildings, clan boss raids and sect wars |
| `engine.py` | The game logic: awakening, qi, breakthroughs, pills, talking and events |

To add a way, add an entry to `WAYS`. To add a race, add an entry to `RACES` (weights must add up to 100). To add a realm, append to `REALMS`. To add a person, add an entry to `NPCS`. To add an event, add an entry to `EVENTS`; outcome weights in one choice must add up to 100.
