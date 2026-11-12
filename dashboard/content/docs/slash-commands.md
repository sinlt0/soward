---
title: Slash Commands
description: Use the everyday commands as organised slash commands.
order: 57
group: Utility
---

The everyday commands also work as slash commands. They are grouped, and each one asks only for what it needs.

| Group | Examples |
|---|---|
| `/interact` | `/interact kiss target:@user`, `/interact cry` (the target is optional), `/interact more ...` for the rest |
| `/fun` | `/fun games tic-tac-toe`, `/fun games trivia`, `/fun ship target1:@a target2:@b`, `/fun anime ...`, `/fun wordle ...` |
| `/utility` | `/utility ping`, `/utility userinfo`, `/utility remind set text:2h call mum`, `/utility todo add` |
| `/levels` | `/levels rank`, `/levels leaderboard` |
| `/eco` | `/eco reward`, `/eco work`, `/eco job list`, `/eco gather`, `/eco coinflip`, `/eco coins balance`, `/eco coins give` |
| `/family`, `/clan`, `/profile`, `/pet` | `/family marry`, `/clan info`, `/profile theme set`, `/pet shop` |
| `/community` | `/community birthday ...`, `/community confess ...` |

Required options come first and optional ones are marked by Discord. A slash command runs the normal command, so permissions, cooldowns, premium limits and blacklists behave exactly the same. Moderation, security and other staff tools stay prefix-only.

`/eco` holds every economy command: rewards, work, sect jobs, the gather, hunt, mine and ruins trips, gambling and the wallet under `/eco coins`. If it ever grows past 25 entries, the extra commands move to `/eco-extra`.

`/autopartner` holds the auto partner setup and management commands.

`/cultivate` holds the cultivation RPG commands. `/lineage` holds the family cultivation commands: dual cultivation, treasury and dungeons. `/sect` holds the clan hall commands: buildings, boss raids and wars. `/world` holds exploration, travelers, rifts and your guide.

## Use Zyro anywhere (user apps)

Some groups also work as a **user app**. Add Zyro to your account once and you can use these commands in any server, in DMs and in group chats, even where Zyro is not added.

To add it, open Zyro's profile in Discord, choose **Add App**, then **Add to My Apps**.

| Works anywhere | Commands |
|---|---|
| `/interact` | Hugs, kisses, pats and the rest. Pick the person with the `target` option. |
| `/cultivate`, `/heaven` | The whole cultivation RPG. |
| `/world`, `/pouch`, `/realm`, `/board` | Exploring, storage pouches, secret realms and the calamity board. |
| `/market`, `/auction` | The player marketplace and auction house. |
| `/eco`, `/profile`, `/pet` | Coins, jobs, your profile card and your pets. |

Things to know:

- Your progress is the same everywhere. Your cultivation, coins and pets are global, so a cultivation session started in a DM carries over to a server.
- Commands that need Zyro in the server, such as spawning rift events with `/world spawn`, tell you so instead of running.
- Where Zyro is not added, buttons and menus work the same, but Zyro cannot read the chat, so anything that watches messages does not apply there.
- Zyro cannot see members or roles in a server it is not added to, so `target` pickers show the person Discord gives it and not their server nickname.
- If the server blocks external emoji or apps, Discord may hide Zyro's replies or icons there.
- Maintenance mode and bans apply everywhere, including user apps.
