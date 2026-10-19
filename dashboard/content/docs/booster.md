---
title: Booster Perks
description: Tier roles for boosters, custom booster roles and the settings that control them.
order: 43
group: Community
---

## What it does

Booster Perks rewards members who boost your server:

- **Tier roles**: roles that depend on how much someone boosts, for example **Rich** at 1 boost and **Wealthy** at 2.
- **Custom roles**: boosters create and edit their own role (name, colour, icon) within limits you set.
- **Cleanup**: roles are removed when a boost ends, with an optional grace period, and a custom role comes back if the member boosts again.
- **XP bonus**: give a tier a leveling multiplier.

## Quick start

```
!booster setup
!booster backfill
!booster custom on
```

`setup` turns the system on and creates two starter tiers: **Rich** (1 boost) and **Wealthy** (2 boosts). Add more with `!booster tier create <number> <name>` if you want them, and rename or recolour the roles however you like. Soward needs Manage Roles and its role must sit above the roles it manages.

## How boosts are counted

Discord does not tell bots how many boosts one member gives. It only shows whether someone is boosting and since when. Soward therefore uses two methods:

- **Count mode** (default): Soward counts the boost messages Discord posts in your system channel while it is online, and `booster backfill` reads recent history. Boosting messages must be switched on in Server Settings. If a member removes one of several boosts, Discord does not announce it, so correct them with `!booster set @member <count>`.
- **Days mode**: `!booster mode days` tiers by how long someone has been boosting. This needs no message tracking and is always accurate.

A member who stops boosting completely loses the roles and their count resets.

## Tier commands

| Command | What it does |
|---|---|
| `!booster tier add <number> <@role>` | Use an existing role for a tier |
| `!booster tier create <number> <name> [colour]` | Create the role and the tier |
| `!booster tier remove <number>` | Remove a tier. The role itself is not deleted |
| `!booster tier xp <number> <multiplier>` | XP multiplier for that tier, 1 removes it |
| `!booster tier list` | Show tiers |
| `!booster stack <highest\|all>` | Give only the highest tier, or every tier reached |
| `!booster base <@role\|off>` | A role every booster gets |
| `!booster grace <hours>` | Keep roles for a while after a boost ends |
| `!booster keep <remove\|keep> [restore on\|off]` | What happens to custom roles when a boost ends |
| `!booster set <@member> <count>` | Correct a member's boost count |
| `!booster check <@member>`, `list`, `sync` | Inspect and recheck boosters |

## Custom roles

Members use `!booster role`:

```
!booster role create Sunrise #FF8C42
!booster role name <name>
!booster role color <colour>
!booster role icon        (attach a PNG or JPG under 256 KB)
!booster role hoist on
!booster role perms embed_links attach_files
!booster role delete
```

### What you control

| Command | What it does |
|---|---|
| `!booster custom on\|off` | Turn custom roles on or off |
| `!booster custom min <number>` | Boosts (or days) needed |
| `!booster custom allow <name\|color\|icon\|hoist\|perms> <on\|off>` | What members may change |
| `!booster custom position <above\|below> [@role]` | Where new roles are created |
| `!booster custom reposition` | Move existing custom roles to the current position |
| `!booster custom cooldown <hours>` | Time between edits |
| `!booster custom maxname <1-100>`, `filter <on\|off>` | Name length and the word filter |
| `!booster custom blocked add\|remove\|list <word>` | Words that cannot appear in a role name |

- **Display separately** (`hoist`) is off for members until you allow it, because it adds a group to the member list for each role.
- **Permissions** are off by default. When on, members can only pick harmless ones: change nickname, embed links, attach files, external emojis and stickers, add reactions, create public threads, thread messages, stream, voice activity, soundboard and external sounds. Dangerous permissions can never be given.
- **Position**: new roles are placed directly above or below the role you choose. With no role chosen, Soward uses the booster role you set with `booster base`, then Discord's Server Booster role. Soward can only place roles below its own top role.
- **Icons** need Boost Level 2 on the server.
- Names cannot contain mentions or links, cannot copy an existing role name, and are checked against your blocked words.

## Limits to know about

- A server holds up to 15 tiers and Discord's 250 role limit applies.
- Count mode only knows about boosts it saw. Use `booster backfill` once, then `booster set` for any fix.
- Soward checks boosters every 15 minutes in case it was offline when something changed.
